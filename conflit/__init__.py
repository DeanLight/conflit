"""Layered YAML configuration and Pydantic validation."""

from conflit.config import (
    load_and_validate,
    load_main_and_validate,
    load_settings,
    parse_dotted_overrides,
    validate_config,
)
from conflit.compose import YamlRootError
from conflit.yaml_loading import (
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
    "YamlRootError",
    "load_and_validate",
    "load_main_and_validate",
    "load_settings",
    "load_yaml_path",
    "load_yaml_text",
    "parse_dotted_overrides",
    "validate_config",
]
