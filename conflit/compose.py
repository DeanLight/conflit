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
# # Back-compat compose API
#
# The implementation now lives in :mod:`conflit.config`.

# %%
from conflit.config import (
    ComposeSpec,
    YamlRootError,
    accumulate_resolved_documents,
    expand_compositions,
    load_main_yaml_dict,
    load_yaml_documents,
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
    "load_yaml_documents",
    "merge_yaml_document_stack",
    "nest_under_into",
    "normalize_compose_specs",
    "read_yaml_strict",
    "resolve_yaml_document",
    "strip_top_compose",
]
