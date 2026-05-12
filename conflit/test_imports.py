"""Pytest entry: submodule imports execute juplit ``if test()`` blocks in those modules."""

def test_import_package_runs_inline_checks() -> None:
    import conflit  # noqa: F401 — config, compose, yaml_loading guarded blocks

    import conflit.merge_strategy  # noqa: F401 — not re-exported at package root
