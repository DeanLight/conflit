# API Reference

## Public API

::: conflit
    options:
      members:
        - load
        - Context
        - TrackedVar

## CLI

See the [CLI guide](cli.md) for an introduction. Reference:

::: conflit.cli
    options:
      members:
        - cli
        - load_cli_config
        - parse_dotted_overrides
        - format_schema_help

## Core implementation details

The full pipeline implementation lives in `conflit.config`:

::: conflit.config
    options:
      members:
        - load_namespaces
        - merge_yamls
        - yaml_validate

## Context groups

See the [Context Groups guide](contextgroup.md) for an introduction. Reference:

::: conflit.contextgroup
    options:
      members:
        - Context
        - TrackedVar
