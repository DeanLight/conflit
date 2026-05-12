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
# # Back-compat merge strategy API
#
# Merge logic now lives in :mod:`conflit.config`.

# %%
from conflit.config import (
    MergeStrategy,
    merge_into,
    merge_yamls,
    peel_merge_strategy,
    strip_conflit_markers,
)

__all__ = [
    "MergeStrategy",
    "merge_into",
    "merge_yamls",
    "peel_merge_strategy",
    "strip_conflit_markers",
]
