# conflit

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

### Editing notebooks

1. Edit `.py` files directly — these are the source of truth.
2. Run `poe sync` to propagate changes to `.ipynb` notebooks.
3. Commit only `.py` files (`.ipynb` files are gitignored).

## Examples

See [`examples/`](https://github.com/DeanLight/conflit/tree/main/examples) for a layered compose
example (including YAML anchors) and a percent-format notebook script that rich-prints
composition steps.
