"""Pytest entry for package import smoke checks."""

from pathlib import Path


def test_import_and_load_smoke() -> None:
    import conflit

    sample = conflit.load(Path("examples/main.yaml"))
    assert "service" in sample
