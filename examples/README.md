# Examples

This folder demonstrates how to use `conflit` for layered YAML config management.

- `common.yaml`: baseline config with YAML anchors.
- `production.yaml`: environment-specific overrides using `!merge` and `!append`.
- `main.yaml`: top-level file that composes both with `_compose`.
- `compose_walkthrough.py`: percent notebook that rich-prints source YAML, compose expansion, and final merged output.
