# Getting Started

This guide walks through the core `conflit` flow using a realistic example:
managing ML training configuration for a model called **Orion** across
a baseline and a GPU-cluster override layer.

The same pattern works for any domain — web services, data pipelines,
infrastructure — anywhere you want layered config with precise merge control.

## The core flow

1. Write layered YAML files — each file only contains what it changes.
2. Declare composition order with `_compose`.
3. Use `!merge` to deep-merge nested dicts; use `!append` to accumulate lists.
4. Call `load()` to get a merged dict, or pass `schema=YourModel` for a validated
   Pydantic instance.

## Why a single YAML file is still useful

Even if your project uses layered `_compose` configs, a single YAML file is
often the best starting point when you want one self-contained artifact for:

- documenting an experiment run and its exact parameters,
- capturing a one-off environment configuration,
- sharing a reproducible setup in a PR or issue.

`load()` accepts either a standalone YAML or a composed entry point — the
caller does not need to know which.

## 1. Install and setup

```bash
uv sync
poe init
```

## 2. Write the baseline

`base.yaml` — shared defaults used by every environment:

```yaml
model:
  architecture: transformer
  num_layers: 6
  hidden_dim: 512

training:
  optimizer: adamw
  learning_rate: 0.0001
  batch_size: 32
  max_epochs: 20

features:
  - mixed_precision
  - gradient_checkpointing
```

## 3. Write an override layer

`gpu_large.yaml` — scale up for a GPU cluster without repeating unchanged keys.
`!merge` descends into the nested dict; `!append` extends the list:

```yaml
model: !merge
  num_layers: 12
  hidden_dim: 1024

training: !merge
  batch_size: 256
  max_epochs: 100

features: !append
  - distributed_training
  - compile_model
```

## 4. Compose the layers

`experiment.yaml` — the entry point that ties everything together:

```yaml
_compose:
  - base.yaml
  - gpu_large.yaml

experiment:
  name: orion-v1-large
  seed: 42

features: !append
  - wandb_logging
```

## 5. Load the merged config

```python
from pathlib import Path
from conflit import load

cfg = load(Path("experiment.yaml"))
print(cfg["model"])
# {"architecture": "transformer", "num_layers": 12, "hidden_dim": 1024}

print(cfg["features"])
# ["mixed_precision", "gradient_checkpointing",
#  "distributed_training", "compile_model", "wandb_logging"]
```

`model` is the result of deep-merging: `base.yaml` set `num_layers: 6`,
`gpu_large.yaml` overrode it to `12` while leaving `architecture` untouched.
`features` is the full accumulated list across all three files.

## 6. Validate with Pydantic

Pass `schema=YourModel` to get a typed, auto-completed config object.
Pydantic raises a clear error on missing fields or type mismatches — no
more silent config bugs at runtime:

```python
from pathlib import Path
from pydantic import BaseModel
from conflit import load

class ModelConfig(BaseModel):
    architecture: str
    num_layers: int
    hidden_dim: int

class TrainingConfig(BaseModel):
    optimizer: str
    learning_rate: float
    batch_size: int
    max_epochs: int

class OrionConfig(BaseModel):
    model: ModelConfig
    training: TrainingConfig
    features: list[str]

cfg = load(Path("experiment.yaml"), schema=OrionConfig)
print(cfg.model.num_layers)   # 12
print(cfg.training.optimizer) # "adamw"
print(cfg.features[-1])       # "wandb_logging"
```

## 7. Compose files under a specific key

By default `_compose` merges each file at the root. Add a `namespace` field to
scope an entire file under a dotted key instead:

```yaml
# experiment.yaml
_compose:
  - base.yaml
  - gpu_large.yaml
  - path: hardware.yaml      # keys land at hardware.*, not at root
    namespace: hardware
```

`hardware.yaml` can then be a clean, self-contained document:

```yaml
# hardware.yaml
accelerator: a100
count: 8
memory_gb: 80
```

After loading, those keys are accessible at `cfg["hardware"]["accelerator"]` or
`cfg.hardware.accelerator` when validated through a Pydantic model.  This lets
you keep per-concern config files flat internally while composing them into a
structured hierarchy.

## 8. Explore the full example

The `examples/` directory contains the complete four-file Orion setup (including
`hardware.yaml` scoped under a namespace) together with a notebook-style
walkthrough that prints each YAML layer, the compose expansion, the final merged
dict, and the Pydantic-validated result:

```bash
uv run python examples/compose_walkthrough.py
```

See [`examples/`](https://github.com/DeanLight/conflit/tree/main/examples) for
the source files.
