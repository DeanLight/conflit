"""Pytest smoke tests: import, compose, merge, and Pydantic validation."""

from pathlib import Path

from pydantic import BaseModel


class _ModelCfg(BaseModel):
    architecture: str
    num_layers: int
    hidden_dim: int
    num_heads: int
    dropout: float


class _TrainingCfg(BaseModel):
    optimizer: str
    learning_rate: float
    weight_decay: float
    max_epochs: int
    batch_size: int
    gradient_clip: float
    warmup_steps: int


class _DataCfg(BaseModel):
    train_path: str
    val_path: str
    num_workers: int
    pin_memory: bool


class _LoggingCfg(BaseModel):
    level: str
    log_every_n_steps: int
    save_dir: str


class _ExperimentMeta(BaseModel):
    name: str
    seed: int
    tags: list[str]


class _OrionConfig(BaseModel):
    model: _ModelCfg
    training: _TrainingCfg
    data: _DataCfg
    logging: _LoggingCfg
    experiment: _ExperimentMeta
    features: list[str]


EXPERIMENT = Path("examples/experiment.yaml")


def test_load_returns_dict_with_expected_keys() -> None:
    import conflit

    cfg = conflit.load(EXPERIMENT)
    assert isinstance(cfg, dict)
    assert "model" in cfg
    assert "training" in cfg
    assert "features" in cfg
    assert "experiment" in cfg


def test_merge_semantics() -> None:
    """gpu_large.yaml deep-merges model and training; base.yaml values win where not overridden."""
    import conflit

    cfg = conflit.load(EXPERIMENT)
    # gpu_large.yaml overrides these
    assert cfg["model"]["num_layers"] == 12
    assert cfg["model"]["hidden_dim"] == 1024
    assert cfg["training"]["batch_size"] == 256
    # base.yaml values untouched by gpu_large.yaml
    assert cfg["training"]["optimizer"] == "adamw"
    assert cfg["data"]["train_path"] == "data/train.parquet"


def test_append_semantics() -> None:
    """Features list accumulates across all three layers."""
    import conflit

    cfg = conflit.load(EXPERIMENT)
    features = cfg["features"]
    # base.yaml contributes these
    assert "mixed_precision" in features
    assert "gradient_checkpointing" in features
    # gpu_large.yaml appends these
    assert "distributed_training" in features
    assert "compile_model" in features
    # experiment.yaml appends this
    assert "wandb_logging" in features
    # order is preserved: base → gpu_large → experiment
    assert features.index("mixed_precision") < features.index("distributed_training")
    assert features.index("distributed_training") < features.index("wandb_logging")


def test_pydantic_validation() -> None:
    """load(schema=Model) returns a validated model instance with correct field values."""
    import conflit

    cfg = conflit.load(EXPERIMENT, schema=_OrionConfig)
    assert isinstance(cfg, _OrionConfig)
    assert cfg.model.num_layers == 12
    assert cfg.training.batch_size == 256
    assert cfg.data.pin_memory is True
    assert cfg.experiment.name == "orion-v1-large"
    assert "wandb_logging" in cfg.features
