# Contributing

## Setup

```bash
uv sync     # install all dependencies
poe init    # install git hooks
poe nb      # generate .ipynb notebooks from .py sources (run once after cloning)
```

Run `poe` with no arguments to see all available tasks.

## Notebooks

Source files are `.py` (percent format). Notebooks are derived and gitignored.

This project uses [juplit](https://github.com/deanlight/juplit) to keep `.py` and `.ipynb` in sync. The short version:

- Edit `.py` files — they are the source of truth.
- Run `poe sync` after editing to propagate changes to `.ipynb`.
- Commit only `.py` files.

The pre-commit hook runs `juplit sync` automatically before each commit.
