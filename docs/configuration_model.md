# Configuration Model

`conflit` processes configuration in three phases:

1. **Load + expand namespaces** via `_compose`
2. **Merge namespace/object pairs** using merge semantics
3. **Optional validation** into a Pydantic model

---

## `_compose` behavior

`_compose` is a list of entries resolved relative to the file that declares
them. Each entry is either a plain path string or a `{namespace: path}` mapping:

```yaml
_compose:
  - base.yaml                    # merged at root
  - hardware: hardware.yaml      # all keys land under hardware.*
  - infra.storage: db.yaml       # all keys land under infra.storage.*
```

Resolution is depth-first and cycle-checked. Each loaded YAML contributes a
`(namespace, payload)` pair — namespace `"."` means root merge. The current
file's own keys are merged last, so it acts as the final override layer on top
of everything it composes.

Namespace routing is useful when a config file is written as a flat document
but you want it to live under a specific key in the merged result — for example,
composing a standalone `hardware.yaml` under `hardware` so it never collides
with model or training keys.

---

## Merge semantics

### Default behaviour: deep merge

When no tag is present, dicts are **recursively merged** — only the keys
present in the overlay are updated, sibling keys from earlier layers are
preserved. Scalars replace (merging a scalar is the same as replacing it).

```yaml
# base.yaml
training:
  optimizer: adamw
  batch_size: 32
  max_epochs: 20

# gpu_large.yaml — patches two keys; optimizer and max_epochs come from base
training:
  batch_size: 256
  max_epochs: 100
```

Result: `training: {optimizer: adamw, batch_size: 256, max_epochs: 100}`.

### `!override` — explicit replacement

Use `!override` when you want to **replace** an entire value — a nested dict,
a list, or a scalar — discarding whatever the earlier layers set:

```yaml
# gpu_large.yaml — throw away base logging config entirely
logging: !override
  level: warning
  log_every_n_steps: 200
```

`!override` works on mappings, sequences, and scalars.

### `!append` — list accumulation

Use `!append` when a list should **grow** across layers rather than be replaced.
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

`overrides` is merged using the same default deep-merge semantics.
