# API Reference

## Public API

::: conflit
    options:
      members:
        - load

## Core implementation details

The full pipeline implementation lives in `conflit.config`:

::: conflit.config
    options:
      members:
        - load_namespaces
        - merge_yamls
        - yaml_validate
