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
# # Conflit CLI walkthrough
#
# `conflit.cli` ships two layers:
#
# 1. The **`@cli` decorator** — a 4-line setup for the common case: YAML config
#    path + `--set key=value` dotted overrides.
# 2. The **building-blocks helper `load_cli_config`** — for CLIs that need
#    custom typed flags or a positional that maps to a config key. You write
#    your own cyclopts entry point; conflit just handles the merge.
#
# This notebook walks through both patterns against `examples/agent.yaml`.

# %%
from pathlib import Path
from typing import Annotated, Any

from cyclopts import App, Parameter
from pydantic import BaseModel
from rich import print

from conflit import load
from conflit.cli import cli, load_cli_config, parse_dotted_overrides

EXAMPLES_DIR = (
    Path(__file__).resolve().parent if "__file__" in globals() else Path("examples").resolve()
)
CONFIG = EXAMPLES_DIR / "agent.yaml"
print(f"[cyan]{CONFIG.name}:[/cyan]\n{CONFIG.read_text()}")


# %% [markdown]
# ## Pattern 1: the `@cli` decorator
#
# Wraps `main(cfg)` so that:
#
# - the first positional argument is the YAML config path,
# - `--set k=v ...` collects dotted overrides,
# - `--help` renders the schema as a markdown epilogue.
#
# The decorator *returns the cyclopts `App`*, so `app.command(...)` still works
# for adding subcommands.

# %%
class AgentConfig(BaseModel):
    task: str
    model: str
    max_iter: int = 10
    vars: dict[str, Any] = {}


@cli(schema=AgentConfig)
def app(cfg: AgentConfig) -> None:
    """Run the agent."""
    print(f"[green]task[/green]: {cfg.task}")
    print(f"[green]model[/green]: {cfg.model}")
    print(f"[green]vars[/green]: {cfg.vars}")


# Drive it in-process with `result_action="return_value"` so cyclopts doesn't
# call `sys.exit`. In a real script you'd just write `if __name__ == "__main__": app()`.
app([str(CONFIG), "--set", "max_iter=5", 'task="rewrite"'], result_action="return_value")


# %% [markdown]
# ## Pattern 2: drop down to cyclopts for custom flags
#
# When you outgrow `--set` — for example you want:
#
# - a **positional argument** that maps to `cfg.task`,
# - a `--var x=3 y=hello` flag that fills `cfg.vars` with parsed values,
# - a `--readvar name=path` flag that reads file contents into `cfg.vars`,
#
# write your own cyclopts `@app.default` and call `load_cli_config(...)`. Conflit
# does not invent a flag DSL — cyclopts already has one.
#
# Override precedence (later wins): YAML stack → `--set` → keyword args you
# pass to `load_cli_config` (so positional/typed flags beat string overrides).

# %%
# A throwaway file to demo --readvar.
prompt_path = EXAMPLES_DIR / "prompt.txt"
prompt_path.write_text("You are a helpful summariser.\n", encoding="utf-8")


custom = App(help="Run the agent (custom CLI).")


@custom.default
def run(
    task: Annotated[str, Parameter(help="The task description (positional).")],
    main_config: Annotated[
        Path, Parameter(help="YAML config.")
    ] = CONFIG,
    set_: Annotated[
        list[str],
        Parameter(name="--set", consume_multiple=True, negative=()),
    ] = [],
    var: Annotated[
        list[str],
        Parameter(
            name="--var",
            consume_multiple=True,
            negative=(),
            help="Inline values: --var x=3 y=hello",
        ),
    ] = [],
    readvar: Annotated[
        list[str],
        Parameter(
            name="--readvar",
            consume_multiple=True,
            negative=(),
            help="Load file contents into a var: --readvar name=path",
        ),
    ] = [],
) -> None:
    vars_: dict[str, Any] = parse_dotted_overrides(var)
    for item in readvar:
        k, _, p = item.partition("=")
        vars_[k] = Path(p).read_text()

    cfg = load_cli_config(
        main_config,
        set_=set_,
        schema=AgentConfig,
        task=task,           # positional → cfg.task
        vars=vars_,          # deep-merges with vars from YAML / --set
    )
    print(f"[green]task[/green]: {cfg.task}")
    print(f"[green]vars[/green]: {cfg.vars}")


custom(
    [
        "Summarise this PR.",                   # positional → task
        "--var", "tone=concise", "length=2",
        "--readvar", f"system={prompt_path}",
    ],
    result_action="return_value",
)


# %% [markdown]
# ## What if you skip the helper?
#
# `load_cli_config` is just sugar over `parse_dotted_overrides` + `conflit.load`
# with a deep-merge of extra kwargs. If you'd rather build the override dict
# yourself, this is the equivalent of the call above:

# %%
overrides: dict[str, Any] = parse_dotted_overrides([])
overrides["task"] = "Summarise this PR."
overrides["vars"] = {"tone": "concise", "length": 2, "system": prompt_path.read_text()}
cfg = load(CONFIG, overrides=overrides, schema=AgentConfig)
print(cfg.model_dump())

# %%
prompt_path.unlink()
