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
# # Unified YAML pipeline
#
# Single-file implementation for:
# - YAML constructors (`!merge` / `!append`)
# - compose expansion into `(namespace, yaml_obj)` records
# - recursive merge semantics
# - optional Pydantic validation
# - top-level `load(...)`

# %%
from __future__ import annotations

import copy
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

import structlog
import yaml
from juplit import test
from pydantic import BaseModel
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, SequenceNode

T = TypeVar("T", bound=BaseModel)
log = structlog.stdlib.get_logger(__name__)
stdlib_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TaggedMerge:
    """YAML `!merge` marker."""

    mapping: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TaggedAppend:
    """YAML `!append` marker."""

    sequence: list[Any]


TAG_MERGE = "!merge"
TAG_APPEND = "!append"


class ConflitLoader(yaml.SafeLoader):
    """SafeLoader with conflict-resolution tags."""


def _construct_merge(loader: yaml.Loader, node: MappingNode) -> TaggedMerge:
    if not isinstance(node, MappingNode):
        raise ConstructorError(None, None, "!merge expects a mapping", node.start_mark)
    return TaggedMerge(mapping=dict(loader.construct_mapping(node, deep=True)))


def _construct_append(loader: yaml.Loader, node: SequenceNode) -> TaggedAppend:
    if not isinstance(node, SequenceNode):
        raise ConstructorError(None, None, "!append expects a sequence", node.start_mark)
    return TaggedAppend(sequence=list(loader.construct_sequence(node, deep=True)))


yaml.add_constructor(TAG_MERGE, _construct_merge, Loader=ConflitLoader)
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
merged: !merge
  x: 1
items: !append
  - a
"""
    )
    assert isinstance(tagged["merged"], TaggedMerge)
    assert isinstance(tagged["items"], TaggedAppend)


if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        path = Path(tmp_s) / "simple.yaml"
        path.write_text("value: 1\n", encoding="utf-8")
        assert read_yaml_strict(path) == {"value": 1}


NamespaceDoc = tuple[str, dict[str, Any]]


def load_namespaces(
    path: Path,
    *,
    compose_key: str = "_compose",
    stack: tuple[Path, ...] = (),
) -> list[NamespaceDoc]:
    """
    Load one YAML and expand `_compose` into ordered `(namespace, yaml_obj)` records.

    Rules:
    - Namespace `"."` means root merge.
    - `_compose` is a list of YAML file paths.
    - Resolution is depth-first: children first, then current document body.

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
        for include_path in raw_compose:
            if not isinstance(include_path, str):
                raise TypeError(f"{compose_key} entries must be file paths (strings)")
            include_abs = Path(include_path)
            include_abs = (
                include_abs.resolve() if include_abs.is_absolute() else (canon.parent / include_abs).resolve()
            )
            docs.extend(load_namespaces(include_abs, compose_key=compose_key, stack=(*stack, canon)))

    docs.append((".", {k: v for k, v in raw.items() if k != compose_key}))
    return docs


if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        (t / "base.yaml").write_text("a: 1\n", encoding="utf-8")
        (t / "main.yaml").write_text("_compose:\n  - base.yaml\nb: 2\n", encoding="utf-8")
        assert load_namespaces(t / "main.yaml") == [(".", {"a": 1}), (".", {"b": 2})]


class MergeStrategy(StrEnum):
    OVERRIDE = "override"
    MERGE = "merge"
    APPEND = "append"


def peel_merge_strategy(value: Any) -> tuple[MergeStrategy, Any]:
    if isinstance(value, TaggedMerge):
        return MergeStrategy.MERGE, value.mapping
    if isinstance(value, TaggedAppend):
        return MergeStrategy.APPEND, value.sequence
    if isinstance(value, dict) and "_conflit" in value:
        raw = value["_conflit"]
        if not isinstance(raw, str):
            raise TypeError(f"_conflit must be a string strategy, got {type(raw).__name__}")
        try:
            strategy = MergeStrategy(raw.strip().lower())
        except ValueError as exc:
            raise ValueError(f"unknown _conflit strategy {raw!r}") from exc
        return strategy, {k: v for k, v in value.items() if k != "_conflit"}
    return MergeStrategy.OVERRIDE, value


if test():
    assert peel_merge_strategy(TaggedMerge({"x": 1}))[0] is MergeStrategy.MERGE
    assert peel_merge_strategy(TaggedAppend(["a"]))[0] is MergeStrategy.APPEND
    assert peel_merge_strategy({"_conflit": "merge", "x": 1}) == (
        MergeStrategy.MERGE,
        {"x": 1},
    )


def _coerce_append_list(peeled: Any) -> list[Any]:
    if isinstance(peeled, list):
        return copy.deepcopy(peeled)
    if isinstance(peeled, dict):
        if len(peeled) != 1:
            raise ValueError(
                "append with a bare mapping expects exactly one list-valued field; "
                f"got keys {list(peeled)!r}"
            )
        (_name, seq), = peeled.items()
        if not isinstance(seq, list):
            raise TypeError("append legacy mapping field must hold a list")
        return copy.deepcopy(seq)
    raise TypeError(f"append expects list payload, got {type(peeled).__name__}")


class _Miss:
    ...


_MISSING = _Miss()


def _merge_dict(base: dict[str, Any], overlay: Mapping[str, Any], *, path: str = ".") -> None:
    for key, raw_overlay in overlay.items():
        strategy, peeled = peel_merge_strategy(raw_overlay)
        existing = base.get(key, _MISSING)
        key_path = key if path == "." else f"{path}.{key}"
        if stdlib_log.isEnabledFor(logging.DEBUG):
            log.debug(
                "merge.step",
                path=key_path,
                strategy=strategy.value,
                existing_type=type(existing).__name__,
                incoming_type=type(peeled).__name__,
            )

        if strategy == MergeStrategy.OVERRIDE:
            base[key] = copy.deepcopy(peeled)
            continue

        if strategy == MergeStrategy.APPEND:
            incoming_list = _coerce_append_list(peeled)
            if existing is _MISSING or existing is None:
                base[key] = copy.deepcopy(incoming_list)
            elif isinstance(existing, list):
                base[key] = [*existing, *incoming_list]
            else:
                raise TypeError(
                    f"append at {key_path!r}: base must be list or absent, "
                    f"got {type(existing).__name__}"
                )
            continue

        if isinstance(peeled, dict):
            if existing is _MISSING or existing is None:
                nested: dict[str, Any] = {}
                base[key] = nested
                _merge_dict(nested, peeled, path=key_path)
            elif isinstance(existing, dict):
                _merge_dict(existing, peeled, path=key_path)
            else:
                base[key] = copy.deepcopy(peeled)
        else:
            base[key] = copy.deepcopy(peeled)


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
        _merge_dict(merged, _nest_namespace(clean_ns, payload))
    return merged


if test():
    assert merge_yamls([(".", {"x": 1}), ("svc.api", {"timeout": 5})]) == {
        "x": 1,
        "svc": {"api": {"timeout": 5}},
    }
    assert merge_yamls([(".", {"tags": ["a"]}), (".", {"tags": TaggedAppend(["b"])})]) == {
        "tags": ["a", "b"]
    }


def strip_conflit_markers(obj: Any) -> Any:
    if isinstance(obj, TaggedMerge):
        return strip_conflit_markers(obj.mapping)
    if isinstance(obj, TaggedAppend):
        return [strip_conflit_markers(x) for x in obj.sequence]
    if isinstance(obj, dict):
        return {k: strip_conflit_markers(v) for k, v in obj.items() if str(k) != "_conflit"}
    if isinstance(obj, list):
        return [strip_conflit_markers(x) for x in obj]
    return obj


if test():
    assert strip_conflit_markers({"a": TaggedMerge({"b": 1})}) == {"a": {"b": 1}}
    assert strip_conflit_markers({"x": {"_conflit": "merge", "y": 2}}) == {"x": {"y": 2}}


def yaml_validate(obj: Mapping[str, Any], config_cls: type[T]) -> T:
    """Validate merged YAML dict against a Pydantic model class."""
    return config_cls.model_validate(strip_conflit_markers(dict(obj)))


def load(
    config_file: Path,
    *,
    compose_key: str = "_compose",
    overrides: Mapping[str, Any] | None = None,
    as_: type[T] | None = None,
    **kwargs: Any,
) -> dict[str, Any] | T:
    """
    Main entrypoint: load, compose, merge, optional validate.

    Returns merged dict when no model is supplied.
    """
    if "as" in kwargs:
        if as_ is not None:
            raise TypeError("Provide only one of `as_` or `as`")
        as_ = kwargs.pop("as")
    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise TypeError(f"Unexpected keyword argument(s): {unknown}")

    docs = load_namespaces(Path(config_file), compose_key=compose_key)
    if overrides:
        docs.append((".", dict(overrides)))
    clean = strip_conflit_markers(merge_yamls(docs))
    if as_ is None:
        return clean
    return yaml_validate(clean, as_)


# %%
if test():
    import tempfile

    from pydantic import BaseModel as PBM
    from pydantic import Field

    class _ScenarioInner(PBM):
        url: str = "http://default"
        retries: int = 3

    class _Scenario(PBM):
        name: str = "unspecified"
        value: int = 0
        inner: _ScenarioInner = _ScenarioInner()
        nested: dict[str, int] = Field(default_factory=dict)

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        (t / "base.yaml").write_text(
            yaml.safe_dump({"name": "base", "inner": {"url": "http://base", "retries": 1}}),
            encoding="utf-8",
        )
        (t / "overlay.yaml").write_text(
            """
inner: !merge
  retries: 5
nested: !merge
  x: 1
""",
            encoding="utf-8",
        )
        (t / "main.yaml").write_text(
            """
_compose:
  - base.yaml
  - overlay.yaml
description: ignored
nested: !merge
  y: 2
""",
            encoding="utf-8",
        )
        docs = load_namespaces(t / "main.yaml")
        assert docs[0][0] == "."
        assert load(t / "main.yaml") == {
            "name": "base",
            "inner": {"url": "http://base", "retries": 5},
            "description": "ignored",
            "nested": {"x": 1, "y": 2},
        }
        loaded = load(t / "main.yaml", as_=_Scenario)
        assert loaded == _Scenario(
            name="base",
            inner=_ScenarioInner(url="http://base", retries=5),
            nested={"x": 1, "y": 2},
        )
        loaded_via_as_alias = load(t / "main.yaml", **{"as": _Scenario})
        assert loaded_via_as_alias == loaded

