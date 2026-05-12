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
# # Strategic merge per key (YAML tags / legacy ``_conflit``)
#
# Prefer YAML tags (**``!merge``**, ``!append``) on the incoming value (:mod:`conflit.yaml_loading`).
# Legacy configs may still embed ``_conflit`` as a sibling strategy field (`override` / ``merge`` / ``append``).
# Untagged mappings follow **override** semantics (incoming subtree replaces the base).

# %%
from __future__ import annotations

import copy
from enum import StrEnum
from typing import Any

from juplit import test

from conflit.yaml_loading import TaggedAppend, TaggedMerge

# %%
class MergeStrategy(StrEnum):
    OVERRIDE = "override"
    MERGE = "merge"
    APPEND = "append"


def peel_merge_strategy(value: Any) -> tuple[MergeStrategy, Any]:
    """Derive merge strategy + payload from YAML tags or legacy ``_conflit``."""
    if isinstance(value, TaggedMerge):
        return MergeStrategy.MERGE, value.mapping
    if isinstance(value, TaggedAppend):
        return MergeStrategy.APPEND, value.sequence

    if isinstance(value, dict) and "_conflit" in value:
        raw = value["_conflit"]
        if not isinstance(raw, str):
            raise TypeError(f"_conflit must be a string strategy name, got {type(raw).__name__}")
        try:
            strat = MergeStrategy(raw.strip().lower())
        except ValueError as exc:
            raise ValueError(f"unknown _conflit strategy {raw!r} (use override, merge, append)") from exc
        rest = {k: v for k, v in value.items() if k != "_conflit"}
        return strat, rest

    return MergeStrategy.OVERRIDE, value


def _coerce_append_list(peeled: Any) -> list[Any]:
    if isinstance(peeled, list):
        return copy.deepcopy(peeled)
    if isinstance(peeled, dict):
        if len(peeled) != 1:
            raise ValueError(
                "append with a bare mapping expects exactly one list-valued field "
                f"(legacy ``_conflit`` form), got keys {list(peeled)!r}"
            )
        (_name, seq), = peeled.items()
        if not isinstance(seq, list):
            raise TypeError("append legacy mapping field must hold a list")
        return copy.deepcopy(seq)
    raise TypeError(f"append expects a YAML sequence (!append) or legacy mapping, got {type(peeled)!r}")


class _Miss:
    ...


_MISSING = _Miss()


def merge_into(base: dict[str, Any], overlay: dict[str, Any]) -> None:
    """Merge *overlay* into *base* using tags / legacy markers on incoming values."""
    for key, raw_ov in overlay.items():
        strat, peeled = peel_merge_strategy(raw_ov)
        existing = base.get(key, _MISSING)

        if strat == MergeStrategy.OVERRIDE:
            base[key] = copy.deepcopy(peeled)
            continue

        if strat == MergeStrategy.APPEND:
            incoming_list = _coerce_append_list(peeled)
            if existing is _MISSING or existing is None:
                base[key] = copy.deepcopy(incoming_list)
            elif isinstance(existing, list):
                base[key] = [*existing, *incoming_list]
            else:
                raise TypeError(
                    f"append at key {key!r}: base must be list or absent, "
                    f"got {type(existing).__name__}"
                )
            continue

        if isinstance(peeled, dict):
            if existing is _MISSING or existing is None:
                nested: dict[str, Any] = {}
                base[key] = nested
                merge_into(nested, peeled)
            elif isinstance(existing, dict):
                merge_into(existing, peeled)
            else:
                base[key] = copy.deepcopy(peeled)
        else:
            base[key] = copy.deepcopy(peeled)


def strip_conflit_markers(obj: Any) -> Any:
    """Flatten tags & strip ``_conflit`` for validation / serialization."""
    if isinstance(obj, TaggedMerge):
        return strip_conflit_markers(obj.mapping)
    if isinstance(obj, TaggedAppend):
        return [strip_conflit_markers(x) for x in obj.sequence]
    if isinstance(obj, dict):
        return {
            k: strip_conflit_markers(v) for k, v in obj.items() if str(k) != "_conflit"
        }
    if isinstance(obj, list):
        return [strip_conflit_markers(x) for x in obj]
    return obj


# %%
if test():
    assert peel_merge_strategy({"a": 1})[0] is MergeStrategy.OVERRIDE
    assert peel_merge_strategy(TaggedMerge({"x": 1}))[0] is MergeStrategy.MERGE


# %%
if test():
    b = {"nested": {"x": 1, "y": 0}}
    merge_into(b, {"nested": TaggedMerge({"y": 2, "z": 3})})
    assert b["nested"] == {"x": 1, "y": 2, "z": 3}


# %%
if test():
    legacy = peel_merge_strategy({"_conflit": "merge", "x": 1})
    assert legacy[0] is MergeStrategy.MERGE


# %%
if test():
    o = {"nested": {"x": 1}}
    merge_into(o, {"nested": {"y": 2}})
    assert o["nested"] == {"y": 2}


# %%
if test():
    b = {"tags": ["a"]}
    merge_into(b, {"tags": TaggedAppend(["b", "c"])})
    assert b["tags"] == ["a", "b", "c"]


# %%
if test():
    assert strip_conflit_markers(TaggedMerge({"a": {"deep": TaggedAppend(["x"])}})) == {
        "a": {"deep": ["x"]},
    }


# %%
if test():
    assert strip_conflit_markers({"a": {"_conflit": "merge", "b": 1}}) == {"a": {"b": 1}}

# %%
