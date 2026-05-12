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
# # Tagged YAML (:class:`ConflitLoader`)
#
# - ``!merge`` — attach to a **mapping** for recursive deep-merge.
# - ``!append`` — attach to a **sequence** for list concatenation.

# %%
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from juplit import test
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, SequenceNode


@dataclass(frozen=True, slots=True)
class TaggedMerge:
    """YAML ``!merge`` — merge ``mapping`` recursively into the existing dict at this key."""

    mapping: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TaggedAppend:
    """YAML ``!append`` — extend the destination list with ``sequence``."""

    sequence: list[Any]


TAG_MERGE = "!merge"
TAG_APPEND = "!append"


class ConflitLoader(yaml.SafeLoader):
    """``SafeLoader`` plus ``!merge`` and ``!append``."""


def _construct_merge(loader: yaml.Loader, node: MappingNode) -> TaggedMerge:
    if not isinstance(node, MappingNode):
        raise ConstructorError(None, None, "!merge expects a mapping", node.start_mark)
    data = loader.construct_mapping(node, deep=True)
    return TaggedMerge(mapping=dict(data))


def _construct_append(loader: yaml.Loader, node: SequenceNode) -> TaggedAppend:
    if not isinstance(node, SequenceNode):
        raise ConstructorError(None, None, "!append expects a sequence", node.start_mark)
    seq = loader.construct_sequence(node, deep=True)
    return TaggedAppend(sequence=list(seq))


yaml.add_constructor(TAG_MERGE, _construct_merge, Loader=ConflitLoader)
yaml.add_constructor(TAG_APPEND, _construct_append, Loader=ConflitLoader)


def load_yaml_path(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=ConflitLoader)


def load_yaml_text(text: str) -> Any:
    return yaml.load(text, Loader=ConflitLoader)


# %%
if test():
    doc = yaml.load(
        """
nested: !merge
  x: 1
tags: !append
  - a
  - b
""",
        Loader=ConflitLoader,
    )
    assert isinstance(doc["nested"], TaggedMerge)
    assert isinstance(doc["tags"], TaggedAppend)


# %%
if test():
    crashed = False
    try:
        yaml.load("bad: !append\n x: wrong", Loader=ConflitLoader)
    except (ConstructorError, yaml.YAMLError):
        crashed = True
    assert crashed


# %%
if test():
    lst = yaml.load("tags: !append []\n", Loader=ConflitLoader)
    assert isinstance(lst["tags"], TaggedAppend)

# %%
