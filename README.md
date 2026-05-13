# conflit

Lightweight layered YAML configuration for Python.

`conflit` solves a specific problem: you have a set of YAML config files that
should be *composed* rather than repeated. A base file holds shared defaults;
environment or experiment files override only what changes. `conflit` merges
them in order with precise semantics — `!merge` for nested dicts, `!append`
for lists — and optionally validates the result against a Pydantic model.

## Why conflit?

Most config libraries make you choose between two bad options:

- **One big file per environment.** Drift is inevitable. When the base changes,
  every environment file needs updating. Reviewers lose the signal — what
  actually changed?
- **A framework with its own DSL.** You learn the framework's concepts,
  fight its edge cases, and end up locked in.

`conflit` is different: your config is just YAML. Two tags (`!merge`,
`!append`) express how keys combine across layers, and a single `_compose`
list declares the file order. No magic, no hidden state — you can read the
final result in a Python shell in one line.

## Quick example

```yaml
# base.yaml — shared defaults
model:
  num_layers: 6
  hidden_dim: 512
features:
  - mixed_precision
```

```yaml
# gpu_large.yaml — scale up without repeating unchanged keys
model: !merge
  num_layers: 12    # overrides base; hidden_dim is untouched
features: !append
  - distributed_training
```

```yaml
# experiment.yaml — compose entry point
_compose:
  - base.yaml
  - gpu_large.yaml
run_name: orion-v1-large
```

```python
from pathlib import Path
from conflit import load

cfg = load(Path("experiment.yaml"))
# {"model": {"num_layers": 12, "hidden_dim": 512},
#  "features": ["mixed_precision", "distributed_training"],
#  "run_name": "orion-v1-large"}
```

Validate against a Pydantic model with one extra argument:

```python
cfg = load(Path("experiment.yaml"), as_=OrionConfig)
cfg.model.num_layers  # 12 — typed, IDE-autocompleted
```

## Setup

```bash
uv sync      # install dependencies
poe init     # install git hooks
poe nb       # generate .ipynb notebooks from .py source files
```

## Workflow

| Command | What it does |
|---|---|
| `poe nb` | Generate `.ipynb` files from `.py` sources (run after cloning) |
| `poe sync` | Sync `.py` <-> `.ipynb` after editing |
| `poe clean` | Sync then delete all `.ipynb` files |
| `poe test` | Run tests |
| `poe docs` | Serve docs locally |

### Editing notebooks

1. Edit `.py` files directly — these are the source of truth.
2. Run `poe sync` to propagate changes to `.ipynb` notebooks.
3. Commit only `.py` files (`.ipynb` files are gitignored).

## Examples

See [`examples/`](https://github.com/DeanLight/conflit/tree/main/examples) for
the full Orion training config — a three-file compose setup demonstrating
`!merge`, `!append`, Pydantic validation, and a notebook-style walkthrough
that prints each step of the pipeline.
