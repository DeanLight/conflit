# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.2
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # CLI helpers
#
# Thin cyclopts wrapper around `conflit.load`. A user-facing `@cli` decorator
# turns a `main(cfg)` function into a runnable CLI that accepts:
#
# - a positional YAML config path (with `_compose` support),
# - `--set key=value ...` dotted overrides (YAML-parsed values),
# - a `--help` epilogue rendering the Pydantic schema source.
#
# The decorator returns the underlying cyclopts `App`, so users can attach
# extra subcommands with `@app.command`.

# %%
from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Annotated, Any, TypeVar

import yaml
from cyclopts import App, Parameter
from juplit import test
from pydantic import BaseModel

from conflit.config import load

T = TypeVar("T", bound=BaseModel)


# %% [markdown]
# ## Dotted-key override parsing

# %%
def parse_dotted_overrides(args: Iterable[str]) -> dict[str, Any]:
    """Parse ``["key=value", "a.b=value"]`` into a nested dict.

    Values are YAML-parsed so booleans, ints, floats, and ``null`` round-trip
    correctly (e.g. ``enable=false`` → ``False``). Plain strings are unchanged.
    """
    result: dict[str, Any] = {}
    for arg in args:
        key, sep, value = arg.partition("=")
        if not sep:
            raise ValueError(f"override {arg!r} is not in key=value form")
        parts = key.strip().split(".")
        d = result
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = yaml.safe_load(value.strip())
    return result


# %%
if test():
    assert parse_dotted_overrides(["task_id=my-task"]) == {"task_id": "my-task"}
    assert parse_dotted_overrides(["client.base_url=http://localhost"]) == {
        "client": {"base_url": "http://localhost"}
    }
    assert parse_dotted_overrides(["a.b.c=1", "a.b.d=2"]) == {
        "a": {"b": {"c": 1, "d": 2}}
    }
    assert parse_dotted_overrides(["enable=false", "n=5", "x=null"]) == {
        "enable": False,
        "n": 5,
        "x": None,
    }
    assert parse_dotted_overrides([]) == {}


# %% [markdown]
# ## Schema-driven help epilogue

# %%
def format_schema_help(classes: Iterable[type]) -> str:
    """Render Pydantic model source as a markdown ``--help`` epilogue.

    Falls back to the class name when source is unavailable (e.g., models
    constructed dynamically).
    """
    parts = ["### Config schema", ""]
    for cls in classes:
        try:
            src = inspect.getsource(cls).rstrip()
            parts.append(f"```python\n{src}\n```")
        except (OSError, TypeError):
            parts.append(f"`{cls.__module__}.{cls.__qualname__}`")
        parts.append("")
    return "\n".join(parts).rstrip()


# %%
if test():
    class _Demo(BaseModel):
        x: int = 1

    out = format_schema_help([_Demo])
    assert "class _Demo" in out
    assert "x: int" in out


# %% [markdown]
# ## Building-blocks helper: `load_cli_config`
#
# For CLIs with custom flags (e.g. ``--var x=3``, ``--readvar y=path``) or a
# positional argument that maps to a config key, drop down from the `@cli`
# decorator and write your own cyclopts ``@app.default``. ``load_cli_config``
# bundles the parse-overrides + deep-merge + ``load`` step so the body of your
# entry point stays short.

# %%
def _deep_merge_into(dst: dict[str, Any], src: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge ``src`` into ``dst``. Scalars and lists in ``src`` win."""
    for k, v in src.items():
        if isinstance(v, Mapping) and isinstance(dst.get(k), dict):
            _deep_merge_into(dst[k], v)
        else:
            dst[k] = v
    return dst


def load_cli_config(
    main_config: Path,
    *,
    set_: Iterable[str] = (),
    schema: type[T] | None = None,
    compose_key: str = "_compose",
    **extra_overrides: Any,
) -> dict[str, Any] | T:
    """Parse ``--set`` args, deep-merge extra overrides, and call ``conflit.load``.

    Override precedence (later wins):

    1. The composed YAML stack (handled by :func:`conflit.load`).
    2. Dotted ``--set`` overrides (parsed via :func:`parse_dotted_overrides`).
    3. Keyword ``extra_overrides`` (typically values from typed cyclopts flags
       or positional arguments).

    Args:
        main_config: Path to the top-level YAML config.
        set_: Iterable of ``"key=value"`` or ``"a.b=value"`` strings from a
            ``--set`` flag. Values are YAML-parsed.
        schema: Optional Pydantic model for validation.
        compose_key: YAML key used for composition (default ``_compose``).
        **extra_overrides: Top-level keys to inject as a final override layer.
            Nested dicts are deep-merged into the result.

    Returns:
        Merged ``dict`` (when ``schema`` is ``None``) or a validated model instance.
    """
    overrides: dict[str, Any] = parse_dotted_overrides(set_)
    if extra_overrides:
        _deep_merge_into(overrides, extra_overrides)
    return load(
        main_config,
        compose_key=compose_key,
        overrides=overrides or None,
        schema=schema,
    )


# %%
if test():
    import tempfile

    from pydantic import BaseModel as _BM

    class _C(_BM):
        task: str
        n: int = 0
        vars: dict[str, Any] = {}

    with tempfile.TemporaryDirectory() as tmp_s:
        p = Path(tmp_s) / "c.yaml"
        p.write_text("task: from-yaml\nn: 1\nvars:\n  a: 1\n", encoding="utf-8")

        # No overrides: yaml is loaded verbatim.
        cfg = load_cli_config(p, schema=_C)
        assert cfg.task == "from-yaml" and cfg.n == 1 and cfg.vars == {"a": 1}

        # --set wins over yaml.
        cfg = load_cli_config(p, set_=["n=99"], schema=_C)
        assert cfg.n == 99

        # extra_overrides win over --set.
        cfg = load_cli_config(p, set_=["task=from-set"], schema=_C, task="from-extra")
        assert cfg.task == "from-extra"

        # Nested deep-merge: --set vars.x=1 + extra vars={"y": 2} → {a:1, x:1, y:2}.
        cfg = load_cli_config(p, set_=["vars.x=1"], schema=_C, vars={"y": 2})
        assert cfg.vars == {"a": 1, "x": 1, "y": 2}


# %% [markdown]
# ## The `@cli` decorator

# %%
def cli(
    schema: type[T] | None = None,
    *,
    help_schemas: Iterable[type] | None = None,
    compose_key: str = "_compose",
    app: App | None = None,
    **app_kwargs: Any,
) -> Callable[[Callable[[Any], None]], App]:
    """Decorator: turn ``main(cfg)`` into a cyclopts CLI driven by ``conflit.load``.

    The resulting CLI takes one positional argument — the path to a YAML config
    (which may use ``_compose``) — and an optional ``--set key=value ...`` list
    of dotted overrides merged on top of the composed config.

    Args:
        schema: Optional Pydantic model. When provided, the loaded config is
            validated into ``schema`` before being passed to the wrapped
            function. When ``None``, the wrapped function receives a plain
            ``dict``.
        help_schemas: Additional Pydantic classes to render in the ``--help``
            epilogue (useful for nested config fragments).
        compose_key: Override the YAML key used for composition (default
            ``_compose``).
        app: An existing cyclopts ``App`` to attach to instead of creating one
            (useful when sharing an app across modules).
        **app_kwargs: Forwarded to ``cyclopts.App(...)`` when ``app`` is not
            provided. ``help_format`` and ``help_epilogue`` are filled in by
            default but may be overridden here.

    Returns:
        A decorator. Applied to ``main(cfg)``, it returns the underlying
        cyclopts ``App``. Call the app to invoke the CLI; use
        ``@app.command(...)`` to add subcommands.
    """
    classes: list[type] = []
    if schema is not None:
        classes.append(schema)
    if help_schemas:
        classes.extend(help_schemas)

    def decorator(main_fn: Callable[[Any], None]) -> App:
        nonlocal app
        if app is None:
            kwargs: dict[str, Any] = {
                "help": main_fn.__doc__,
                "help_format": "markdown",
            }
            if classes:
                kwargs["help_epilogue"] = format_schema_help(classes)
            kwargs.update(app_kwargs)
            app = App(**kwargs)

        @app.default
        def _entry(
            main_config: Annotated[
                Path,
                Parameter(help="Main YAML config file (supports _compose)."),
            ],
            set_: Annotated[
                list[str],
                Parameter(
                    name="--set",
                    consume_multiple=True,
                    negative=(),
                    help=(
                        "One or more key=value overrides, e.g. "
                        '`--set a.b=3 task="hi" enable=false`.'
                    ),
                ),
            ] = [],
        ) -> None:
            cfg = load_cli_config(
                main_config,
                set_=set_,
                schema=schema,
                compose_key=compose_key,
            )
            main_fn(cfg)

        return app

    return decorator


# %%
if test():
    import tempfile

    from pydantic import BaseModel as _BM

    class _Cfg(_BM):
        name: str
        n: int = 0

    captured: dict[str, Any] = {}

    @cli(schema=_Cfg)
    def _main(cfg: _Cfg) -> None:
        """Demo CLI."""
        captured["cfg"] = cfg

    assert isinstance(_main, App)

    with tempfile.TemporaryDirectory() as tmp_s:
        p = Path(tmp_s) / "c.yaml"
        p.write_text("name: hello\nn: 1\n", encoding="utf-8")

        _main([str(p)], result_action="return_value")
        assert captured["cfg"].name == "hello"
        assert captured["cfg"].n == 1

        _main([str(p), "--set", "n=42", "name=world"], result_action="return_value")
        assert captured["cfg"].name == "world"
        assert captured["cfg"].n == 42


# %%
if test():
    # No schema → cfg is a plain dict.
    import tempfile

    seen: dict[str, Any] = {}

    @cli()
    def _main2(cfg: dict) -> None:
        seen["cfg"] = cfg

    with tempfile.TemporaryDirectory() as tmp_s:
        p = Path(tmp_s) / "c.yaml"
        p.write_text("a: 1\nb:\n  c: 2\n", encoding="utf-8")
        _main2([str(p), "--set", "b.c=99"], result_action="return_value")
        assert seen["cfg"] == {"a": 1, "b": {"c": 99}}


# %%
if test():
    # Subcommand attachment via the returned App.
    import tempfile

    flags: dict[str, Any] = {}

    @cli(schema=_Cfg)
    def _main3(cfg: _Cfg) -> None:
        flags["ran"] = "default"

    @_main3.command
    def report() -> None:
        flags["ran"] = "report"

    with tempfile.TemporaryDirectory() as tmp_s:
        p = Path(tmp_s) / "c.yaml"
        p.write_text("name: x\n", encoding="utf-8")
        _main3([str(p)], result_action="return_value")
        assert flags["ran"] == "default"
        _main3(["report"], result_action="return_value")
        assert flags["ran"] == "report"
