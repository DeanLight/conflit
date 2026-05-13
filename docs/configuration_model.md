# Configuration Model

`conflit` processes configuration in three phases:

1. **Load + expand namespaces** via `_compose`
2. **Merge namespace/object pairs** using merge semantics
3. **Optional validation** into a Pydantic model

---

## `_compose` behavior

`_compose` is a list of YAML file paths resolved relative to the file that
declares them:

```yaml
_compose:
  - base.yaml
  - gpu_large.yaml
```

Resolution is depth-first and cycle-checked. Each loaded YAML contributes a
`(namespace, payload)` pair — namespace `"."` means root merge. The current
file's own keys are merged last, so it acts as the final override layer on top
of everything it composes.

---

## Merge semantics

### Default behaviour: override

When no tag is present, an incoming value replaces whatever was at that key.
Use this for scalar values (strings, numbers, booleans) that a later layer
should simply swap out.

```yaml
# base.yaml
training:
  max_epochs: 20

# gpu_large.yaml — replaces the whole training mapping
training:
  max_epochs: 100
  batch_size: 256
```

### `!merge` — recursive dict merge

Use `!merge` when you want to update *some* keys inside a nested dict without
having to repeat the ones you are not changing:

```yaml
# gpu_large.yaml — only touches batch_size; max_epochs comes from base.yaml
training: !merge
  batch_size: 256
```

`!merge` is only meaningful on mappings. Applying it to a scalar or list raises
an error.

### `!append` — list accumulation

Use `!append` when a list should grow across layers rather than be replaced.
A common pattern is a feature-flag list that base configs seed and environment
configs extend:

```yaml
# base.yaml
features:
  - mixed_precision

# gpu_large.yaml — extends, does not replace
features: !append
  - distributed_training
  - compile_model

# experiment.yaml — extends again
features: !append
  - wandb_logging
```

The final `features` list will be
`["mixed_precision", "distributed_training", "compile_model", "wandb_logging"]`
— order preserved, no duplicates removed (deduplication is left to the
application if needed).

### Legacy `_conflit` key

`_conflit` is still recognised for compatibility:

```yaml
training:
  _conflit: merge
  batch_size: 256
```

Supported strategy values: `override`, `merge`, `append`.

---

## Validation

Pass `schema=YourModel` to `load()` with a Pydantic model to turn the merged dict
into a validated, typed object:

```python
from pathlib import Path
from pydantic import BaseModel
from conflit import load

class TrainingConfig(BaseModel):
    optimizer: str
    batch_size: int

class AppConfig(BaseModel):
    training: TrainingConfig

cfg = load(Path("experiment.yaml"), schema=AppConfig)
# cfg.training.batch_size → int, IDE-autocompleted, validated
```

If no model is provided, `load()` returns a plain `dict[str, Any]`.

Validation errors from Pydantic (missing required fields, wrong types, failed
validators) surface immediately rather than silently producing wrong runtime
behaviour — which is the main reason to reach for `schema=` in production code.

---

## Programmatic overrides

The `overrides` parameter applies an additional dict on top of the composed
result before validation. This is useful for injecting environment variables,
CLI flags, or test fixtures without touching the YAML files:

```python
cfg = load(
    Path("experiment.yaml"),
    overrides={"training": {"max_epochs": 1}},
    schema=AppConfig,
)
```

`overrides` follows default (override) semantics — it replaces, not merges.
