# CLI

`conflit.cli` is a thin [cyclopts](https://cyclopts.readthedocs.io/) wrapper
around [`conflit.load`](api.md). It ships two layers:

1. The **`@cli` decorator** — a 4-line setup for the common case: YAML config
   path + `--set k=v` dotted overrides + schema-driven `--help`.
2. The **building blocks** — `parse_dotted_overrides` and `load_cli_config` —
   so when you outgrow `--set` you can drop down to cyclopts directly without
   re-implementing the merge.

The decorator handles the 80% case. For custom flags (`--var`, `--readvar`,
positional arguments mapped to config keys, …), write your own cyclopts entry
point — conflit does not invent a flag DSL on top of one.

## Quick start: the `@cli` decorator

```python
from pydantic import BaseModel
from conflit.cli import cli


class AgentConfig(BaseModel):
    task: str
    model: str = "gpt-4o-mini"
    max_iter: int = 10


@cli(schema=AgentConfig)
def app(cfg: AgentConfig) -> None:
    """Run the agent."""
    print(cfg)


if __name__ == "__main__":
    app()
```

```text
$ my-agent configs/agent.yaml --set max_iter=5 task="rewrite"
```

The decorator returns the underlying cyclopts `App`, so subcommands work too:

```python
@app.command
def report(out_dir: Path) -> None: ...
```

## Custom flags: drop down to cyclopts

Want a positional that maps to `cfg.task`, plus `--var x=3` and
`--readvar y=path/to/file`? Skip the decorator and write a cyclopts
`@app.default` yourself, then call `load_cli_config`:

```python
from pathlib import Path
from typing import Annotated, Any

from cyclopts import App, Parameter
from conflit.cli import load_cli_config, parse_dotted_overrides

app = App(help="Run the agent.")


@app.default
def run(
    task: Annotated[str, Parameter(help="The task description.")],   # positional
    main_config: Annotated[Path, Parameter()] = Path("configs/agent.yaml"),
    set_: Annotated[
        list[str],
        Parameter(name="--set", consume_multiple=True, negative=()),
    ] = [],
    var: Annotated[
        list[str],
        Parameter(name="--var", consume_multiple=True, negative=(),
                  help="Inline values, e.g. --var x=3 y=hello"),
    ] = [],
    readvar: Annotated[
        list[str],
        Parameter(name="--readvar", consume_multiple=True, negative=(),
                  help="Load a file's contents into a var, e.g. --readvar prompt=./p.txt"),
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
        task=task,        # positional → cfg.task
        vars=vars_,       # deep-merges with vars from YAML / --set
    )
    ...
```

**Override precedence (later wins):**

1. The composed YAML stack (`_compose` + the main file).
2. Dotted `--set` overrides.
3. Keyword arguments to `load_cli_config` — typically values from positional
   args or typed cyclopts flags. Nested dicts are deep-merged.

## Walkthrough

A runnable notebook with both patterns lives in
[`examples/cli_walkthrough.ipynb`](https://github.com/DeanLight/conflit/blob/main/examples/cli_walkthrough.ipynb).

## Reference

::: conflit.cli
    options:
      members:
        - cli
        - load_cli_config
        - parse_dotted_overrides
        - format_schema_help
