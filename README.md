# conflit

Layered YAML configuration for Python. Compose multiple config files, patch nested keys without repeating unchanged ones, accumulate lists across layers, and optionally validate the result with Pydantic.

## TLDR

```yaml
# base.yaml
model:
  num_layers: 6
  hidden_dim: 512
features:
  - mixed_precision
```

```yaml
# gpu_large.yaml — only what changes; hidden_dim is preserved
model:
  num_layers: 12
features: !append
  - distributed_training
```

```yaml
# experiment.yaml
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

cfg = load(Path("experiment.yaml"), schema=OrionConfig)
cfg.model.num_layers  # 12 — typed, validated
```

See [`examples/`](https://github.com/DeanLight/conflit/tree/main/examples) for the full walkthrough and [`docs/`](https://github.com/DeanLight/conflit/tree/main/docs) for the configuration model reference.

## Install

```bash
uv sync
poe  # list available tasks
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
