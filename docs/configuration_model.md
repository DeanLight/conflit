# Configuration Model

`conflit` processes configuration in three phases:

1. **Load + expand namespaces** via `_compose`
2. **Merge namespace/object pairs** using merge semantics
3. **Optional validation** into a Pydantic model

---

## `_compose` behavior

`_compose` is a list of YAML file paths:

```yaml
_compose:
  - defaults.yaml
  - production.yaml
```

Resolution is depth-first and cycle-checked. Each loaded YAML contributes a namespace/object pair where namespace `"."` means root merge.

---

## Merge semantics

### Default behavior (override)

If no tag is present, incoming values override existing values at the key.

### `!merge` for mappings

```yaml
service: !merge
  retries: 5
```

Recursively merges mapping keys into existing mapping values.

### `!append` for lists

```yaml
tags: !append
  - prod
  - metrics
```

Appends incoming list items onto the existing list.

### Legacy `_conflit` key

`_conflit` is still recognized for compatibility:

```yaml
service:
  _conflit: merge
  retries: 5
```

Supported strategy values: `override`, `merge`, `append`.

---

## Validation

Pass `as_` (or `as` alias) to `load(...)` with a Pydantic model:

```python
from pathlib import Path
from pydantic import BaseModel
from conflit import load

class AppConfig(BaseModel):
    name: str

cfg = load(Path("main.yaml"), as_=AppConfig)
```

If no model is provided, `load(...)` returns a merged dictionary.
