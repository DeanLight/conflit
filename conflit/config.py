# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Configuration loading API
#
# Wraps recursive ``_compose`` resolution (:mod:`conflit.compose`) with Dynaconf and Pydantic.
# Per-key behavior uses YAML tags (``!merge``, ``!append`` — :mod:`conflit.yaml_loading`)
# and merge rules in :mod:`conflit.merge_strategy`.

# %%
from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import yaml
from dynaconf import Dynaconf
from juplit import test
from pydantic import BaseModel

from conflit.merge_strategy import merge_into, strip_conflit_markers
from conflit.compose import accumulate_resolved_documents, load_main_yaml_dict
from conflit.yaml_loading import TaggedMerge, load_yaml_text

T = TypeVar("T", bound=BaseModel)


def merged_dict_to_dynaconf(merged: dict[str, Any]) -> Dynaconf:
    """Load ``.env`` and load a merged mapping (metadata stripped via :func:`~conflit.merge_strategy.strip_conflit_markers`)."""
    settings = Dynaconf(environments=False, load_dotenv=True)
    clean = strip_conflit_markers(merged)
    if clean:
        settings.update(clean, merge=False)
    return settings


def load_settings(
    config_files: list[Path],
    overrides: dict[str, Any] | None = None,
) -> Dynaconf:
    """Resolve each YAML path (recursive ``_compose``) in order; optional override dict merges last."""
    body = accumulate_resolved_documents(config_files)
    if overrides:
        merge_into(body, overrides)
    return merged_dict_to_dynaconf(body)


def parse_dotted_overrides(args: list[str]) -> dict[str, Any]:
    """``key=value`` pairs; dotted keys nest; values use :func:`~conflit.yaml_loading.load_yaml_text` so tags work."""
    result: dict[str, Any] = {}
    for arg in args:
        key, _, value = arg.partition("=")
        parts = key.strip().split(".")
        branch = result
        for part in parts[:-1]:
            nxt = branch.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                branch[part] = nxt
            branch = nxt
        branch[parts[-1]] = load_yaml_text(value.strip())
    return result


def _lower_keys(obj: Any) -> Any:
    """Lower-case dict keys for Pydantic (Dynaconf normalizes casing internally)."""
    if isinstance(obj, dict):
        return {str(k).lower(): _lower_keys(v) for k, v in obj.items()}
    return obj


def validate_config(settings: Dynaconf, config_cls: type[T]) -> T:
    """Validate Dynaconf state into ``config_cls``."""
    return config_cls.model_validate(_lower_keys(settings.as_dict()))


def load_and_validate(
    config_cls: type[T],
    config_files: list[Path],
    overrides: dict[str, Any] | None = None,
    set_args: list[str] | None = None,
) -> T:
    merged = accumulate_resolved_documents(config_files)
    if overrides:
        merge_into(merged, overrides)
    if set_args:
        merge_into(merged, parse_dotted_overrides(set_args))
    return validate_config(merged_dict_to_dynaconf(merged), config_cls)


def load_main_and_validate(
    config_cls: type[T],
    main_config: Path,
    set_args: list[str] | None = None,
) -> T:
    """Load a main YAML (recursive ``_compose``, ``description`` stripped), then ``--set`` overrides."""
    body = dict(load_main_yaml_dict(Path(main_config)))
    if set_args:
        merge_into(body, parse_dotted_overrides(set_args))
    return validate_config(merged_dict_to_dynaconf(body), config_cls)


# %%
if test():
    import tempfile

    from pydantic import BaseModel as PBM
    from pydantic import Field

    assert parse_dotted_overrides([]) == {}
    assert parse_dotted_overrides(["task_id=my-task"]) == {"task_id": "my-task"}
    assert parse_dotted_overrides(
        ["max_iter=5", "client.url=http://localhost"],
    ) == {"max_iter": 5, "client": {"url": "http://localhost"}}

    class _ScenarioInner(PBM):
        url: str = "http://default"
        retries: int = 3

    class _Scenario(PBM):
        name: str = "unspecified"
        x: int = 0
        value: int = 0
        inner: _ScenarioInner = _ScenarioInner()
        a: int = 0
        b: str = ""
        nested: dict[str, int] = Field(default_factory=dict)

    assert validate_config(merged_dict_to_dynaconf({"name": "solo", "x": 42}), _Scenario).x == 42

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8",
    ) as f:
        tmp_flat = Path(f.name)
        f.write(
            yaml.safe_dump(
                {
                    "name": "from-yaml",
                    "value": 10,
                    "inner": {"url": "http://yaml", "retries": 5},
                },
            ),
        )

    try:
        cfg = load_and_validate(_Scenario, [tmp_flat])
        assert cfg.inner.retries == 5

        merged_inner = load_and_validate(
            _Scenario,
            [tmp_flat],
            overrides={"inner": TaggedMerge({"url": "http://override"})},
        )
        assert merged_inner.inner.url == "http://override"
        assert merged_inner.inner.retries == 5
        assert load_and_validate(_Scenario, [tmp_flat], overrides={"value": 99}).value == 99

        cfg_m = load_and_validate(
            _Scenario,
            [tmp_flat],
            set_args=["inner.url=http://set-arg", "inner.retries=9"],
        )
        assert cfg_m.inner.url == "http://set-arg"
        assert cfg_m.inner.retries == 9

        cfg_os = load_and_validate(
            _Scenario,
            [tmp_flat],
            overrides={"value": 1},
            set_args=["value=2"],
        )
        assert cfg_os.value == 2
    finally:
        tmp_flat.unlink()

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        (t / "base.yaml").write_text(
            yaml.safe_dump({"a": 1, "nested": {"x": 1}}),
            encoding="utf-8",
        )
        (t / "overlay.yaml").write_text(
            "nested: !merge\n  y: 2\nb: hi\n",
            encoding="utf-8",
        )
        (t / "main.yaml").write_text(
            "_compose:\n  - base.yaml\n  - overlay.yaml\ndescription: ignored\nnested: !merge\n  z: 3\n",
            encoding="utf-8",
        )
        out = load_main_and_validate(
            _Scenario,
            t / "main.yaml",
            set_args=["name=from-main"],
        )
        assert out.name == "from-main"
        assert out.a == 1
        assert out.b == "hi"
        assert out.nested == {"x": 1, "y": 2, "z": 3}

        assert load_main_yaml_dict(t / "main.yaml") == {
            "a": 1,
            "b": "hi",
            "nested": {"x": 1, "y": 2, "z": 3},
        }


# %%
