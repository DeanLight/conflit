# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.2
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Unified YAML pipeline
#
# Single-file implementation for:
# - YAML constructors (`!override` / `!append`)
# - compose expansion into `(namespace, yaml_obj)` records
# - recursive merge semantics
# - optional Pydantic validation
# - top-level `load(...)`

# %%
from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml
from juplit import test
from pydantic import BaseModel
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, SequenceNode

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class TaggedOverride:
    """YAML `!override` marker — explicitly replace a value instead of merging."""

    value: Any


@dataclass(frozen=True, slots=True)
class TaggedAppend:
    """YAML `!append` marker."""

    sequence: list[Any]


TAG_OVERRIDE = "!override"
TAG_APPEND = "!append"


class ConflitLoader(yaml.SafeLoader):
    """SafeLoader with conflict-resolution tags."""


def _construct_override(loader: ConflitLoader, node: yaml.Node) -> TaggedOverride:
    if isinstance(node, MappingNode):
        return TaggedOverride(value=dict(loader.construct_mapping(node, deep=True)))
    if isinstance(node, SequenceNode):
        return TaggedOverride(value=list(loader.construct_sequence(node, deep=True)))
    return TaggedOverride(value=loader.construct_scalar(node))


def _construct_append(loader: ConflitLoader, node: SequenceNode) -> TaggedAppend:
    if not isinstance(node, SequenceNode):
        raise ConstructorError(None, None, "!append expects a sequence", node.start_mark)
    return TaggedAppend(sequence=list(loader.construct_sequence(node, deep=True)))


yaml.add_constructor(TAG_OVERRIDE, _construct_override, Loader=ConflitLoader)
yaml.add_constructor(TAG_APPEND, _construct_append, Loader=ConflitLoader)


def load_yaml_text(text: str) -> Any:
    """Load YAML text with conflit tags enabled."""
    return yaml.load(text, Loader=ConflitLoader)


def load_yaml_path(path: Path) -> Any:
    """Load YAML file with conflit tags enabled."""
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=ConflitLoader)


class YamlRootError(ValueError):
    """YAML root must be a mapping."""


def read_yaml_strict(path: Path) -> dict[str, Any]:
    """Load YAML and require a mapping at the document root."""
    raw = load_yaml_path(path)
    if raw is None:
        raise YamlRootError(f"{path}: YAML root is empty (expected mapping)")
    if not isinstance(raw, dict):
        raise YamlRootError(f"{path}: YAML root must be a mapping, got {type(raw).__name__}")
    return raw


if test():
    tagged = load_yaml_text(
        """
replaced: !override
  x: 1
items: !append
  - a
replaced_list: !override
  - x
  - y
"""
    )
    assert isinstance(tagged["replaced"], TaggedOverride)
    assert isinstance(tagged["items"], TaggedAppend)
    assert isinstance(tagged["replaced_list"], TaggedOverride)
    assert tagged["replaced_list"].value == ["x", "y"]


if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        path = Path(tmp_s) / "simple.yaml"
        path.write_text("value: 1\n", encoding="utf-8")
        assert read_yaml_strict(path) == {"value": 1}


NamespaceDoc = tuple[str, dict[str, Any]]


def _parse_compose_entry(entry: Any, compose_key: str) -> tuple[str, str]:
    """Return ``(file_path_str, namespace)`` from a ``_compose`` list entry.

    Accepts either a plain path string (namespace ``"."``) or a single-key
    mapping whose key is the target namespace and whose value is the file path::

        _compose:
          - base.yaml                 # merged at root
          - hardware: hardware.yaml   # merged under "hardware"
          - infra.storage: db.yaml    # merged under "infra.storage"
    """
    if isinstance(entry, str):
        return entry, "."
    if isinstance(entry, dict):
        if len(entry) != 1:
            raise TypeError(
                f"{compose_key} dict entry must have exactly one key (the namespace), "
                f"got {list(entry)!r}"
            )
        (namespace, path), = entry.items()
        if not isinstance(path, str):
            raise TypeError(
                f"{compose_key} dict entry value must be a file path string, "
                f"got {type(path).__name__!r}"
            )
        return path, str(namespace)
    raise TypeError(
        f"{compose_key} entries must be a file path string or a {{namespace: path}} mapping, "
        f"got {type(entry).__name__!r}"
    )


def load_namespaces(
    path: Path,
    *,
    compose_key: str = "_compose",
    stack: tuple[Path, ...] = (),
) -> list[NamespaceDoc]:
    """
    Load one YAML and expand `_compose` into ordered `(namespace, yaml_obj)` records.

    Each entry in `_compose` is either a plain path string (merged at root) or a
    single-key mapping whose key is the target namespace and value is the path::

        _compose:
          - base.yaml                   # merged at root
          - hardware: hardware.yaml     # merged under "hardware"
          - infra.storage: db.yaml      # merged under "infra.storage"

    Resolution is depth-first and cycle-checked. Namespace `"."` means root merge.

    Args:
        path: YAML file to load.
        compose_key: Key containing compose entries (defaults to `_compose`).
        stack: Internal recursion chain used for cycle detection.

    Returns:
        Ordered list of namespace/object pairs to merge.
    """
    canon = path.resolve()
    if canon in stack:
        cycle = [*(str(p) for p in stack), str(canon)]
        raise ValueError(f"YAML compose cycle detected involving {cycle!r}")

    raw = read_yaml_strict(canon)
    docs: list[NamespaceDoc] = []
    raw_compose = raw.get(compose_key)
    if raw_compose is not None:
        if not isinstance(raw_compose, list):
            raise TypeError(f"{compose_key} must be a list")
        for entry in raw_compose:
            include_str, namespace = _parse_compose_entry(entry, compose_key)
            include_abs = Path(include_str)
            include_abs = (
                include_abs.resolve() if include_abs.is_absolute() else (canon.parent / include_str).resolve()
            )
            child_docs = load_namespaces(include_abs, compose_key=compose_key, stack=(*stack, canon))
            if namespace == ".":
                docs.extend(child_docs)
            else:
                # Wrap every child namespace under the declared namespace prefix.
                for child_ns, payload in child_docs:
                    combined = namespace if child_ns == "." else f"{namespace}.{child_ns}"
                    docs.append((combined, payload))

    docs.append((".", {k: v for k, v in raw.items() if k != compose_key}))
    return docs


if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        (t / "base.yaml").write_text("a: 1\n", encoding="utf-8")
        (t / "main.yaml").write_text("_compose:\n  - base.yaml\nb: 2\n", encoding="utf-8")
        assert load_namespaces(t / "main.yaml") == [(".", {"a": 1}), (".", {"b": 2})]


if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        (t / "hw.yaml").write_text("gpu: a100\ncount: 8\n", encoding="utf-8")
        (t / "main.yaml").write_text(
            "_compose:\n  - hardware: hw.yaml\na: 1\n",
            encoding="utf-8",
        )
        result = load_namespaces(t / "main.yaml")
        assert result == [("hardware", {"gpu": "a100", "count": 8}), (".", {"a": 1})]


_MISSING = object()


def _path_str(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "."


def add_wrappers(obj: Any) -> Any:
    """Recursively normalize objects coming from the YAML loader.

    The loader already emits wrapper types (`TaggedOverride`, `TaggedAppend`) when
    explicit merge tags are used. This function keeps the normalization pass in one
    place and recursively prepares nested values for merge processing.
    """
    match obj:
        case TaggedOverride(value=value):
            return TaggedOverride(add_wrappers(value))
        case TaggedAppend(sequence=sequence):
            return TaggedAppend([add_wrappers(item) for item in sequence])
        case dict() as mapping:
            return {key: add_wrappers(value) for key, value in mapping.items()}
        case list() as sequence:
            return [add_wrappers(item) for item in sequence]
        case _:
            return obj


def merge_value(current: Any, nxt: Any, *, path: tuple[str, ...] = ()) -> Any:
    """Recursively merge two values, honoring explicit wrapper strategies."""
    match nxt:
        case TaggedOverride(value=value):
            return merge_value(_MISSING, value, path=path)
        case TaggedAppend(sequence=sequence):
            incoming = [merge_value(_MISSING, item, path=(*path, str(idx))) for idx, item in enumerate(sequence)]
            if current is _MISSING or current is None:
                return incoming
            if isinstance(current, list):
                return [*current, *incoming]
            raise TypeError(
                f"append at {_path_str(path)!r}: base must be list or absent, "
                f"got {type(current).__name__}"
            )
        case _:
            pass

    match (current, nxt):
        case (dict() as existing_dict, dict() as incoming_dict):
            out = copy.deepcopy(existing_dict)
            for key, value in incoming_dict.items():
                out[key] = merge_value(out.get(key, _MISSING), value, path=(*path, str(key)))
            return out
        case (_, dict() as incoming_dict) if current is _MISSING:
            return {
                key: merge_value(_MISSING, value, path=(*path, str(key)))
                for key, value in incoming_dict.items()
            }
        case (_, list() as incoming_list) if current is _MISSING:
            return [
                merge_value(_MISSING, value, path=(*path, str(idx)))
                for idx, value in enumerate(incoming_list)
            ]
        case (_, _) if current is _MISSING:
            return copy.deepcopy(nxt)
        case _:
            return copy.deepcopy(nxt)


def _nest_namespace(namespace: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if namespace == ".":
        return dict(payload)
    out: dict[str, Any] = {}
    cursor = out
    parts = namespace.split(".")
    for part in parts[:-1]:
        nxt: dict[str, Any] = {}
        cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = dict(payload)
    return out


def merge_yamls(namespaces: list[NamespaceDoc]) -> dict[str, Any]:
    """
    Merge namespace/object pairs into one config dictionary.

    Each `(namespace, obj)` tuple is merged in order. Namespace `"."` targets root,
    and dotted namespaces (for example `service.api`) are nested before merging.
    """
    merged: dict[str, Any] = {}
    for namespace, payload in namespaces:
        if not isinstance(namespace, str):
            raise TypeError("namespace must be a string")
        clean_ns = namespace.strip() or "."
        if clean_ns != "." and any(seg == "" for seg in clean_ns.split(".")):
            raise ValueError(f"namespace contains empty segment: {namespace!r}")
        layer = add_wrappers(_nest_namespace(clean_ns, payload))
        merged = merge_value(merged, layer)
    return merged


if test():
    assert merge_yamls([(".", {"x": 1}), ("svc.api", {"timeout": 5})]) == {
        "x": 1,
        "svc": {"api": {"timeout": 5}},
    }
    assert merge_yamls([(".", {"tags": ["a"]}), (".", {"tags": TaggedAppend(["b"])})]) == {
        "tags": ["a", "b"]
    }
    # Wrapper values are always consumed and absent from the merged output.
    assert merge_yamls([(".", {"cfg": TaggedOverride({"a": TaggedAppend(["x"])})})]) == {
        "cfg": {"a": ["x"]}
    }

if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        (t / "hw.yaml").write_text("gpu: a100\ncount: 8\n", encoding="utf-8")
        (t / "main.yaml").write_text(
            "_compose:\n  - hardware: hw.yaml\na: 1\n",
            encoding="utf-8",
        )
        result = load_namespaces(t / "main.yaml")
        assert merge_yamls(result) == {"hardware": {"gpu": "a100", "count": 8}, "a": 1}


def yaml_validate(obj: Mapping[str, Any], config_cls: type[T]) -> T:
    """Validate a merged YAML dict against a Pydantic model class.

    Args:
        obj: Merged config dict.
        config_cls: Pydantic model class to validate against.

    Returns:
        Validated instance of ``config_cls``.
    """
    return config_cls.model_validate(dict(obj))


def load(
    config_file: Path,
    *,
    compose_key: str = "_compose",
    overrides: Mapping[str, Any] | None = None,
    schema: type[T] | None = None,
    **kwargs: Any,
) -> dict[str, Any] | T:
    """Load, compose, merge, and optionally validate a YAML config file.

    The three-phase pipeline is:

    1. **Expand** — recursively resolve ``_compose`` entries depth-first into
       ordered ``(namespace, payload)`` pairs.
    2. **Merge** — fold pairs into one dict using default dict deep-merge plus
       ``!override`` / ``!append`` semantics.
    3. **Validate** (optional) — pass the merged dict through a Pydantic model.

    Args:
        config_file: Path to the top-level YAML file (may contain ``_compose``).
        compose_key: Key used to declare composed files (default ``_compose``).
        overrides: Optional mapping applied as a final override layer on top of
            the composed result.
        schema: Pydantic model class.  When supplied, the merged dict is
            validated and the model instance is returned instead of a plain dict.
        **kwargs: Accepts ``as_`` and ``as`` as legacy aliases for ``schema``.

    Returns:
        Merged ``dict[str, Any]`` when ``schema`` is ``None``, or a validated
        instance of ``schema`` otherwise.
    """
    for legacy in ("as_", "as"):
        if legacy in kwargs:
            if schema is not None:
                raise TypeError(f"Provide only one of `schema` or `{legacy}`")
            schema = kwargs.pop(legacy)
    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise TypeError(f"Unexpected keyword argument(s): {unknown}")

    docs = load_namespaces(Path(config_file), compose_key=compose_key)
    if overrides:
        docs.append((".", dict(overrides)))
    clean = merge_yamls(docs)
    if schema is None:
        return clean
    return yaml_validate(clean, schema)


# %%
if test():
    # End-to-end: mirrors the examples/ Orion training config story.
    # base.yaml sets defaults; gpu_layer.yaml patches them (dicts merge by
    # default) and appends feature flags; experiment.yaml
    # composes both, scopes hardware.yaml under a namespace, and adds metadata.
    import tempfile

    from pydantic import BaseModel as PBM

    class _ModelCfg(PBM):
        num_layers: int
        hidden_dim: int

    class _TrainingCfg(PBM):
        batch_size: int
        max_epochs: int

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        (t / "base.yaml").write_text(
            """
model:
  num_layers: 6
  hidden_dim: 512
training:
  batch_size: 32
  max_epochs: 20
features:
  - mixed_precision
""",
            encoding="utf-8",
        )
        # Dicts merge by default — no tag needed. gpu_layer.yaml only lists
        # keys it changes; hidden_dim from base.yaml is preserved automatically.
        # !append is still explicit because list accumulation is intentional.
        # !override would be needed only if we wanted to replace a whole dict.
        (t / "gpu_layer.yaml").write_text(
            """
model:
  num_layers: 12
  hidden_dim: 1024
training:
  batch_size: 256
features: !append
  - distributed_training
""",
            encoding="utf-8",
        )
        # hardware.yaml is a flat file composed under a namespace so its keys
        # land at hardware.* without colliding with model/training.
        (t / "hardware.yaml").write_text(
            """
accelerator: a100
count: 8
""",
            encoding="utf-8",
        )
        (t / "experiment.yaml").write_text(
            """
_compose:
  - base.yaml
  - gpu_layer.yaml
  - hardware: hardware.yaml
run_name: orion-v1-large
features: !append
  - wandb_logging
""",
            encoding="utf-8",
        )
        docs = load_namespaces(t / "experiment.yaml")
        assert docs[0][0] == "."   # base layer at root
        assert docs[2][0] == "hardware"  # hardware.yaml scoped under its namespace
        assert load(t / "experiment.yaml") == {
            "model": {"num_layers": 12, "hidden_dim": 1024},
            "training": {"batch_size": 256, "max_epochs": 20},
            "hardware": {"accelerator": "a100", "count": 8},
            "features": ["mixed_precision", "distributed_training", "wandb_logging"],
            "run_name": "orion-v1-large",
        }

        class _HardwareCfg(PBM):
            accelerator: str
            count: int

        class _ExperimentCfgFull(PBM):
            model: _ModelCfg
            training: _TrainingCfg
            hardware: _HardwareCfg
            features: list[str]
            run_name: str

        loaded = load(t / "experiment.yaml", schema=_ExperimentCfgFull)
        assert loaded == _ExperimentCfgFull(
            model=_ModelCfg(num_layers=12, hidden_dim=1024),
            training=_TrainingCfg(batch_size=256, max_epochs=20),
            hardware=_HardwareCfg(accelerator="a100", count=8),
            features=["mixed_precision", "distributed_training", "wandb_logging"],
            run_name="orion-v1-large",
        )
        loaded_via_legacy = load(t / "experiment.yaml", **{"as_": _ExperimentCfgFull})
        assert loaded_via_legacy == loaded

