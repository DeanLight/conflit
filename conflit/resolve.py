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
# # Back-compat entry point
#
# Implementation lives in :mod:`conflit.compose`; this module re-exports the public API unchanged.

# %%
from conflit.compose import (
    ComposeSpec,
    YamlRootError,
    accumulate_resolved_documents,
    expand_compositions,
    load_main_yaml_dict,
    merge_yaml_document_stack,
    nest_under_into,
    normalize_compose_specs,
    read_yaml_strict,
    resolve_yaml_document,
    strip_top_compose,
)

__all__ = [
    "ComposeSpec",
    "YamlRootError",
    "accumulate_resolved_documents",
    "expand_compositions",
    "load_main_yaml_dict",
    "merge_yaml_document_stack",
    "nest_under_into",
    "normalize_compose_specs",
    "read_yaml_strict",
    "resolve_yaml_document",
    "strip_top_compose",
]
