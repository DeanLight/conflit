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
# One file now owns the complete pipeline:
# - YAML constructors (`!merge` / `!append`)
# - loading + compose expansion into `(namespace, yaml_obj)` documents
# - recursive merge with strategy wrappers and structlog tracing
# - Pydantic validation
# - top-level `load(...)` entrypoint

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
from dynaconf import Dynaconf
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
    return yaml.load(text, Loader=ConflitLoader)


def load_yaml_path(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=ConflitLoader)


class YamlRootError(ValueError):
    """YAML root must be a mapping."""


def read_yaml_strict(path: Path) -> dict[str, Any]:
    raw = load_yaml_path(path)
    if raw is None:
        raise YamlRootError(f"{path}: YAML root is empty (expected mapping)")
    if not isinstance(raw, dict):
        raise YamlRootError(f"{path}: YAML root must be a mapping, got {type(raw).__name__}")
    return raw


@dataclass(frozen=True, slots=True)
class ComposeSpec:
    path: Path
    into: str | None


def _resolve_include_path(candidate: Path, base_dir: Path) -> Path:
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def _normalize_namespace(namespace: Any) -> str | None:
    if namespace is None:
        return None
    if not isinstance(namespace, str):
        raise TypeError("compose namespace must be a string or null")
    clean = namespace.strip()
    if clean in {"", "."}:
        return None
    if any(seg == "" for seg in clean.split(".")):
        raise ValueError(f"compose namespace contains empty segment: {namespace!r}")
    return clean


def normalize_compose_specs(raw_compose: Any, base_dir: Path) -> list[ComposeSpec]:
    """Normalize `_compose` into resolved include specs."""
    if raw_compose is None:
        return []
    if not isinstance(raw_compose, list):
        raise TypeError("_compose must be a list")
    specs: list[ComposeSpec] = []
    for item in raw_compose:
        if isinstance(item, str):
            specs.append(ComposeSpec(path=_resolve_include_path(Path(item), base_dir), into=None))
            continue
        if not isinstance(item, dict):
            raise TypeError("_compose entries must be strings or mappings")
        allowed = {"path", "file", "into", "merge_into"}
        unknown = sorted(set(item) - allowed)
        if unknown:
            raise ValueError(f"_compose mapping has unsupported keys: {unknown!r}")
        raw_path = item.get("path", item.get("file"))
        if raw_path is None:
            raise ValueError('_compose mapping requires "path" or "file"')
        if "path" in item and "file" in item:
            raise ValueError('use only one of "path" or "file" in _compose mapping')
        into = item["into"] if "into" in item else item.get("merge_into")
        if "into" in item and "merge_into" in item:
            raise ValueError('use only one of "into" or "merge_into" in _compose mapping')
        specs.append(
            ComposeSpec(
                path=_resolve_include_path(Path(raw_path), base_dir),
                into=_normalize_namespace(into),
            )
        )
    return specs


def _join_namespace(parent: str | None, child: str) -> str:
    parent_ns = "." if not parent else parent
    child_ns = child.strip() if child else "."
    if child_ns == ".":
        return parent_ns
    if parent_ns == ".":
        return child_ns
    return f"{parent_ns}.{child_ns}"


def _nest_under_namespace(data: Mapping[str, Any], namespace: str) -> dict[str, Any]:
    if namespace == ".":
        return dict(data)
    result: dict[str, Any] = {}
    cursor = result
    parts = namespace.split(".")
    for part in parts[:-1]:
        nxt: dict[str, Any] = {}
        cursor[part] = nxt
        cursor = nxt
    cursor[parts[-1]] = dict(data)
    return result


def strip_top_compose(raw: Mapping[str, Any], compose_key: str = "_compose") -> dict[str, Any]:
    return {k: v for k, v in dict(raw).items() if k != compose_key}


def nest_under_into(data: Mapping[str, Any], into: str | None) -> dict[str, Any]:
    return _nest_under_namespace(data, "." if into is None else into)


def load_yaml_documents(
    path: Path,
    *,
    compose_key: str = "_compose",
    stack: frozenset[Path] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """
    Load YAML and return ordered `(namespace, yaml_obj)` documents.

    Namespace `"."` means merge at root. Child compose namespaces are dotted.
    """
    canon = path.resolve()
    visited = frozenset() if stack is None else stack
    if canon in visited:
        cycle = [*sorted(str(p) for p in visited), str(canon)]
        raise ValueError(f"YAML compose cycle detected involving {cycle!r}")

    raw = read_yaml_strict(canon)
    next_stack = visited | {canon}
    docs: list[tuple[str, dict[str, Any]]] = []

    for spec in normalize_compose_specs(raw.get(compose_key), canon.parent):
        parent_namespace = "." if spec.into is None else spec.into
        for child_namespace, child_data in load_yaml_documents(
            spec.path,
            compose_key=compose_key,
            stack=next_stack,
        ):
            docs.append((_join_namespace(parent_namespace, child_namespace), child_data))

    docs.append((".", strip_top_compose(raw, compose_key=compose_key)))
    return docs


def expand_compositions(
    path: Path,
    *,
    compose_key: str = "_compose",
    stack: frozenset[Path] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Back-compat split for older callers.

    Returns `(composed_from_children, inline_current_doc_without_compose)`.
    """
    docs = load_yaml_documents(path, compose_key=compose_key, stack=stack)
    if not docs:
        return {}, {}
    composed: dict[str, Any] = {}
    for namespace, yaml_obj in docs[:-1]:
        merge_yamls(composed, _nest_under_namespace(yaml_obj, namespace))
    return composed, docs[-1][1]


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


def merge_yamls(base: dict[str, Any], overlay: Mapping[str, Any], *, path: str = ".") -> None:
    """Recursively merge `overlay` into `base` using wrapper semantics."""
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
                merge_yamls(nested, peeled, path=key_path)
            elif isinstance(existing, dict):
                merge_yamls(existing, peeled, path=key_path)
            else:
                base[key] = copy.deepcopy(peeled)
        else:
            base[key] = copy.deepcopy(peeled)


def merge_into(base: dict[str, Any], overlay: Mapping[str, Any]) -> None:
    """Back-compat alias used by earlier API."""
    merge_yamls(base, overlay, path=".")


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


def resolve_yaml_document(path: Path, *, compose_key: str = "_compose") -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for namespace, yaml_obj in load_yaml_documents(path, compose_key=compose_key):
        merge_yamls(merged, _nest_under_namespace(yaml_obj, namespace))
    return merged


def accumulate_resolved_documents(
    paths: list[Path],
    *,
    compose_key: str = "_compose",
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for path in paths:
        for namespace, yaml_obj in load_yaml_documents(Path(path), compose_key=compose_key):
            merge_yamls(merged, _nest_under_namespace(yaml_obj, namespace))
    return merged


def merge_yaml_document_stack(paths: list[Path], *, compose_key: str = "_compose") -> dict[str, Any]:
    return strip_conflit_markers(accumulate_resolved_documents(paths, compose_key=compose_key))


def load_main_yaml_dict(main_path: Path, *, compose_key: str = "_compose") -> dict[str, Any]:
    body = resolve_yaml_document(main_path.resolve(), compose_key=compose_key)
    body.pop("description", None)
    return strip_conflit_markers(body)


def _lower_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k).lower(): _lower_keys(v) for k, v in obj.items()}
    return obj


def yaml_validate(obj: Mapping[str, Any], config_cls: type[T]) -> T:
    return config_cls.model_validate(_lower_keys(strip_conflit_markers(dict(obj))))


def load(
    config_files: list[Path] | Path,
    *,
    compose_key: str = "_compose",
    overrides: Mapping[str, Any] | None = None,
    config_cls: type[T] | None = None,
) -> dict[str, Any] | T:
    """
    Main entrypoint: load, compose, merge, optional validate.

    Returns merged dict when no `config_cls` is supplied.
    """
    paths = [config_files] if isinstance(config_files, Path) else list(config_files)
    merged = accumulate_resolved_documents(paths, compose_key=compose_key)
    if overrides:
        merge_yamls(merged, overrides)
    clean = strip_conflit_markers(merged)
    if config_cls is None:
        return clean
    return yaml_validate(clean, config_cls)


def merged_dict_to_dynaconf(merged: dict[str, Any]) -> Dynaconf:
    settings = Dynaconf(environments=False, load_dotenv=True)
    clean = strip_conflit_markers(merged)
    if clean:
        settings.update(clean, merge=False)
    return settings


def load_settings(config_files: list[Path], overrides: Mapping[str, Any] | None = None) -> Dynaconf:
    merged = accumulate_resolved_documents(config_files)
    if overrides:
        merge_yamls(merged, overrides)
    return merged_dict_to_dynaconf(merged)


def parse_dotted_overrides(args: list[str]) -> dict[str, Any]:
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


def validate_config(settings: Dynaconf | Mapping[str, Any], config_cls: type[T]) -> T:
    payload = settings.as_dict() if isinstance(settings, Dynaconf) else dict(settings)
    return yaml_validate(payload, config_cls)


def load_and_validate(
    config_cls: type[T],
    config_files: list[Path],
    overrides: Mapping[str, Any] | None = None,
    set_args: list[str] | None = None,
) -> T:
    merged = accumulate_resolved_documents(config_files)
    if overrides:
        merge_yamls(merged, overrides)
    if set_args:
        merge_yamls(merged, parse_dotted_overrides(set_args))
    return validate_config(merged_dict_to_dynaconf(merged), config_cls)


def load_main_and_validate(
    config_cls: type[T],
    main_config: Path,
    set_args: list[str] | None = None,
) -> T:
    merged = dict(load_main_yaml_dict(Path(main_config)))
    if set_args:
        merge_yamls(merged, parse_dotted_overrides(set_args))
    return validate_config(merged_dict_to_dynaconf(merged), config_cls)


# %%
if test():
    import tempfile

    from pydantic import BaseModel as PBM
    from pydantic import Field

    assert parse_dotted_overrides([]) == {}
    assert parse_dotted_overrides(["task_id=my-task"]) == {"task_id": "my-task"}
    assert parse_dotted_overrides(["max_iter=5", "client.url=http://localhost"]) == {
        "max_iter": 5,
        "client": {"url": "http://localhost"},
    }

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
            "inner: !merge\n  retries: 5\nnested: !merge\n  x: 1\n",
            encoding="utf-8",
        )
        (t / "main.yaml").write_text(
            "_compose:\n  - base.yaml\n  - overlay.yaml\ndescription: ignored\nnested: !merge\n  y: 2\n",
            encoding="utf-8",
        )
        assert load_main_yaml_dict(t / "main.yaml") == {
            "name": "base",
            "inner": {"url": "http://base", "retries": 5},
            "nested": {"x": 1, "y": 2},
        }
        loaded = load([t / "main.yaml"], config_cls=_Scenario)
        assert loaded.inner.retries == 5

