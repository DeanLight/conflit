# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Conflit compose walkthrough: Orion training config
#
# This notebook shows how `conflit` builds a complete ML training config from
# three YAML layers:
#
# 1. `base.yaml` — shared defaults (model arch, optimizer, data paths)
# 2. `gpu_large.yaml` — GPU-cluster overrides using `!merge` / `!append`
# 3. `experiment.yaml` — compose entry that ties them together and adds metadata
#
# After walking through the merge steps we validate the result against a
# Pydantic model to get type-checked, auto-completed config objects.

# %%
from pathlib import Path

from pydantic import BaseModel
from rich import print
from rich.pretty import Pretty
from rich.syntax import Syntax

from conflit import load
from conflit.config import load_namespaces

EXAMPLES_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path("examples").resolve()
MAIN_FILE = EXAMPLES_DIR / "experiment.yaml"

# %% [markdown]
# ## Raw YAML source files
#
# Each file is self-contained and human-readable. `!merge` / `!append` tags
# express *how* a key should combine with the layer below — no Python glue needed.

# %%
for source in ("base.yaml", "gpu_large.yaml", "experiment.yaml"):
    path = EXAMPLES_DIR / source
    text = path.read_text(encoding="utf-8")
    print(f"\n[bold cyan]{source}[/bold cyan]")
    print(Syntax(text, "yaml", word_wrap=True))

# %% [markdown]
# ## Compose expansion: what `load_namespaces` sees
#
# `_compose` is expanded depth-first. Each included file becomes a
# `(namespace, payload)` pair. Namespace `"."` means *merge at root*.

# %%
docs = load_namespaces(MAIN_FILE)
for namespace, payload in docs:
    print(f"\n[green]namespace[/green] = [bold]{namespace}[/bold]")
    print(Pretty(payload))

# %% [markdown]
# ## Final merged config (plain dict)
#
# `load()` applies the three-phase pipeline: expand → merge → strip markers.
# Notice that `model`, `training`, and `data` reflect the GPU-layer overrides,
# while `features` is the full accumulated list across all three files.

# %%
final_config = load(MAIN_FILE)
print(Pretty(final_config))

# %% [markdown]
# ## Validated config via Pydantic
#
# Pass `as_=YourModel` to `load()` and get a fully typed config object —
# field access, IDE completion, and validation errors for free.

# %%
class ModelConfig(BaseModel):
    architecture: str
    num_layers: int
    hidden_dim: int
    num_heads: int
    dropout: float


class TrainingConfig(BaseModel):
    optimizer: str
    learning_rate: float
    weight_decay: float
    max_epochs: int
    batch_size: int
    gradient_clip: float
    warmup_steps: int


class DataConfig(BaseModel):
    train_path: str
    val_path: str
    num_workers: int
    pin_memory: bool


class LoggingConfig(BaseModel):
    level: str
    log_every_n_steps: int
    save_dir: str


class ExperimentMeta(BaseModel):
    name: str
    seed: int
    tags: list[str]


class OrionConfig(BaseModel):
    model: ModelConfig
    training: TrainingConfig
    data: DataConfig
    logging: LoggingConfig
    experiment: ExperimentMeta
    features: list[str]


cfg = load(MAIN_FILE, as_=OrionConfig)

print(f"\n[bold]Model:[/bold] {cfg.model.architecture} "
      f"{cfg.model.num_layers}L × {cfg.model.hidden_dim}d")
print(f"[bold]Training:[/bold] {cfg.training.max_epochs} epochs, "
      f"batch {cfg.training.batch_size}, lr {cfg.training.learning_rate}")
print(f"[bold]Features:[/bold] {cfg.features}")
print(f"[bold]Experiment:[/bold] {cfg.experiment.name} (seed={cfg.experiment.seed})")
