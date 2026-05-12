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
# # Back-compat YAML loading API
#
# Loader and tag constructors now live in :mod:`conflit.config`.

# %%
from conflit.config import (
    TAG_APPEND,
    TAG_MERGE,
    ConflitLoader,
    TaggedAppend,
    TaggedMerge,
    load_yaml_path,
    load_yaml_text,
)

__all__ = [
    "TAG_APPEND",
    "TAG_MERGE",
    "ConflitLoader",
    "TaggedAppend",
    "TaggedMerge",
    "load_yaml_path",
    "load_yaml_text",
]
