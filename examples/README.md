# Examples

This folder demonstrates how to use `conflit` for layered YAML config management.

- `common.yaml`: baseline config that uses anchors (`&service_defaults`, `&tls_defaults`) and aliases (`*service_defaults`, `*tls_defaults`) to DRY repeated service blocks.
- `production.yaml`: environment-specific overrides using `!merge` and `!append`.
- `main.yaml`: top-level file that composes both with `_compose`.
- `compose_walkthrough.py`: percent notebook that prints the raw YAML (so anchors are visible), compose expansion, and final merged output.
