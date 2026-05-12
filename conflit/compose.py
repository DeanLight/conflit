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
#       display_name: Python 3
#       language: python
#       name: python3
# ---

# %% [markdown]
# # YAML ``_compose`` pipeline
#
# Normalize ``_compose`` specs, recurse depth-first with cycle detection, nest ``into`` targets,
# and expose ``expand_compositions`` (composed vs inline) plus stacking helpers for files.
# Tag semantics live in :mod:`conflit.merge_strategy` / :mod:`conflit.yaml_loading`.

# %%
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from juplit import test

from conflit.merge_strategy import merge_into, strip_conflit_markers
from conflit.yaml_loading import load_yaml_path


class YamlRootError(ValueError):
    """YAML document root is ``null``, a scalar, or a sequence."""


def read_yaml_strict(path: Path) -> dict[str, Any]:
    """Load YAML with tags; mapping root required."""
    raw = load_yaml_path(path)
    if raw is None:
        raise YamlRootError(f"{path}: YAML root is empty (expected a mapping)")
    if not isinstance(raw, dict):
        raise YamlRootError(
            f"{path}: YAML root must be a mapping, got {type(raw).__name__}."
        )
    return raw


def _normalize_into(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    if not isinstance(value, str):
        raise TypeError("`into` path must be a string or null")
    if any(seg == "" for seg in value.split(".")):
        raise ValueError(f"`into` contains an empty dotted segment in {value!r}")
    return value


def _resolve_include_path(candidate: Path, base_dir: Path) -> Path:
    if candidate.is_absolute():
        return candidate.resolve()
    return (base_dir / candidate).resolve()


@dataclass(frozen=True, slots=True)
class ComposeSpec:
    path: Path  # resolved absolute path
    into: str | None


def normalize_compose_specs(raw_compose: Any, base_dir: Path) -> list[ComposeSpec]:
    """Normalize a ``_compose`` list."""
    if raw_compose is None:
        return []
    if not isinstance(raw_compose, list):
        raise TypeError("_compose must be a list")
    specs: list[ComposeSpec] = []
    for item in raw_compose:
        if isinstance(item, str):
            specs.append(ComposeSpec(_resolve_include_path(Path(item), base_dir), None))
        elif isinstance(item, dict):
            allowed_keys = frozenset({"path", "file", "into", "merge_into"})
            if unknown := sorted(frozenset(item) - allowed_keys):
                raise ValueError(f"_compose mapping has unsupported keys: {unknown!r}")

            cand = item.get("path")
            alt = item.get("file")
            if cand is None and alt is None:
                raise ValueError('_compose mapping needs "path" or "file"')
            if cand is not None and alt is not None:
                raise ValueError('use only one of "path" or "file"')

            resolved = cand if cand is not None else alt

            if "into" in item and "merge_into" in item:
                raise ValueError('provide at most one of "into" or "merge_into"')
            merged_into = item["into"] if "into" in item else item.get("merge_into")
            specs.append(
                ComposeSpec(
                    _resolve_include_path(Path(resolved), base_dir),
                    _normalize_into(merged_into),
                )
            )
        else:
            raise TypeError("_compose entries must be str or minimal dict mappings")
    return specs


def strip_top_compose(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Drop top-level `_compose`; keep overlays (tags / legacy markers)."""
    return {k: v for k, v in dict(raw).items() if k != "_compose"}


def nest_under_into(data: Mapping[str, Any], into: str | None) -> dict[str, Any]:
    inner = dict(data)
    if not into:
        return inner
    out: dict[str, Any] = {}
    cursor = out
    parts = into.split(".")
    for segment in parts[:-1]:
        nxt = {}
        cursor[segment] = nxt
        cursor = nxt
    cursor[parts[-1]] = inner
    return out


def expand_compositions(
    path: Path,
    *,
    stack: frozenset[Path] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    canon = Path(path).resolve()
    visited = frozenset() if stack is None else stack
    if canon in visited:
        cycle = [*sorted(str(p) for p in visited), str(canon)]
        raise ValueError(f"YAML compose cycle detected involving {cycle!r}")

    raw = read_yaml_strict(canon)
    next_stack = visited | {canon}

    composed: dict[str, Any] = {}
    specs = normalize_compose_specs(raw.get("_compose"), canon.parent)

    for spec in specs:
        child_composed, child_inline = expand_compositions(spec.path, stack=next_stack)
        merge_into(composed, nest_under_into(child_composed, spec.into))
        merge_into(composed, nest_under_into(child_inline, spec.into))

    inline = strip_top_compose(raw)
    return composed, inline


def resolve_yaml_document(
    path: Path,
    *,
    stack: frozenset[Path] | None = None,
) -> dict[str, Any]:
    composed, inline = expand_compositions(path, stack=stack)
    merge_into(composed, inline)
    return composed


def load_main_yaml_dict(main_path: Path) -> dict[str, Any]:
    """Resolve ``_compose``, drop ``description``, strip merge tags for plain dict output."""
    data = resolve_yaml_document(main_path.resolve())
    for key in {"description"}:
        data.pop(key, None)
    return strip_conflit_markers(data)


def accumulate_resolved_documents(paths: list[Path]) -> dict[str, Any]:
    """Merge paths left→right without final tag stripping (for further merges)."""
    merged: dict[str, Any] = {}
    for raw in paths:
        composed, inline = expand_compositions(Path(raw).resolve())
        merge_into(merged, composed)
        merge_into(merged, inline)
    return merged


def merge_yaml_document_stack(paths: list[Path]) -> dict[str, Any]:
    return strip_conflit_markers(accumulate_resolved_documents(paths))


# %%
if test():
    assert nest_under_into({"x": 1}, "client.server") == {"client": {"server": {"x": 1}}}


# %%
if test():
    raise_ok = False
    try:
        normalize_compose_specs({"bad": 1}, Path.cwd())
    except TypeError:
        raise_ok = True
    assert raise_ok


# %%
if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        (t / "leaf.yaml").write_text("deep: leaf\n", encoding="utf-8")
        (t / "inner.yaml").write_text(
            f"_compose:\n  - {(t / 'leaf.yaml').name!r}\nmiddle: 'yes'\n",
            encoding="utf-8",
        )
        root = t / "root.yaml"
        root.write_text(
            f"_compose:\n  - {(t / 'inner.yaml').name!r}\ntop: main\n",
            encoding="utf-8",
        )
        merged = resolve_yaml_document(root.resolve())
        assert merged == {"deep": "leaf", "middle": "yes", "top": "main"}


# %%
if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        (t / "patch.yaml").write_text("secret: xyzzy\n")
        root = t / "main.yaml"
        root.write_text(
            yaml.dump({"_compose": [{"path": "patch.yaml", "into": "vault"}]}),
            encoding="utf-8",
        )
        assert load_main_yaml_dict(root) == {"vault": {"secret": "xyzzy"}}


# %%
if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        a = t / "a.yaml"
        b = t / "b.yaml"
        a.write_text(f'_compose:\n  - "{b.name}"\n', encoding="utf-8")
        b.write_text(f'_compose:\n  - "{a.name}"\n', encoding="utf-8")

        crashed = False
        try:
            resolve_yaml_document(a.resolve())
        except ValueError as exc:
            crashed = True
            assert "cycle" in str(exc).lower()
        assert crashed


# %%
if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        root = Path(tmp_s) / "oops.yaml"
        root.write_text("[1, 2, 3]\n", encoding="utf-8")
        try:
            read_yaml_strict(root)
        except YamlRootError as exc:
            assert "mapping" in str(exc).lower()
        else:
            raise AssertionError("expected YamlRootError")


# %%
if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        root = Path(tmp_s) / "meta.yaml"
        root.write_text(
            "description: only metadata\nextras: kept\n",
            encoding="utf-8",
        )
        merged = load_main_yaml_dict(root)
        assert merged == {"extras": "kept"}


# %%
if test():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_s:
        t = Path(tmp_s)
        (t / "a.yaml").write_text(
            "shared: !merge\n  v: from_a\ncount: 1\n",
            encoding="utf-8",
        )
        (t / "b.yaml").write_text(
            "shared: !merge\n  w: from_b\n",
            encoding="utf-8",
        )
        stacked = merge_yaml_document_stack([t / "a.yaml", t / "b.yaml"])
        assert stacked["shared"] == {"v": "from_a", "w": "from_b"}

# %%
