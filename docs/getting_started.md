# Getting Started

This guide shows the core `conflit` flow:

1. Write layered YAML files.
2. Compose them with `_compose`.
3. Use `!merge` / `!append` for merge semantics.
4. Load merged config as `dict` or validate into a Pydantic model.

## 1) Install and setup

```bash
uv sync
poe init
```

## 2) Create layered YAML

`base.yaml`

```yaml
service:
  host: localhost
  timeout_seconds: 5
tags:
  - base
```

`prod.yaml`

```yaml
service: !merge
  timeout_seconds: 30
tags: !append
  - prod
```

`main.yaml`

```yaml
_compose:
  - base.yaml
  - prod.yaml
description: app config
```

## 3) Load merged config

```python
from pathlib import Path
from conflit import load

cfg = load(Path("main.yaml"))
print(cfg)
# {
#   "service": {"host": "localhost", "timeout_seconds": 30},
#   "tags": ["base", "prod"],
#   "description": "app config",
# }
```

## 4) Validate with Pydantic

```python
from pathlib import Path
from pydantic import BaseModel
from conflit import load

class Service(BaseModel):
    host: str
    timeout_seconds: int

class Config(BaseModel):
    service: Service
    tags: list[str]
    description: str

validated = load(Path("main.yaml"), as_=Config)
print(validated.service.timeout_seconds)  # 30
```

## 5) Inspect the examples

See [`examples/`](https://github.com/DeanLight/conflit/tree/main/examples) for a richer compose
setup with anchors and the notebook-style walkthrough script.
