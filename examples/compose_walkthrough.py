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
# # Conflit compose walkthrough
#
# This notebook-style script prints each YAML layer (anchors included),
# shows compose expansion into `(namespace, yaml_obj)` pairs, and then
# prints the final merged output.

# %%
from pathlib import Path

from rich import print
from rich.pretty import Pretty
from rich.syntax import Syntax

from conflit import load, load_yaml_documents

EXAMPLES_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path("examples").resolve()
MAIN_FILE = EXAMPLES_DIR / "main.yaml"

# %% [markdown]
# ## Raw YAML source (anchors + aliases for DRY)

# %%
for source in ("common.yaml", "production.yaml", "main.yaml"):
    path = EXAMPLES_DIR / source
    text = path.read_text(encoding="utf-8")
    print(f"\n[bold cyan]{source}[/bold cyan]")
    print(Syntax(text, "yaml", word_wrap=True))

# %% [markdown]
# ## Compose expansion output (`namespace`, `yaml object`)

# %%
docs = load_yaml_documents(MAIN_FILE)
for namespace, payload in docs:
    print(f"\n[green]namespace[/green] = [bold]{namespace}[/bold]")
    print(Pretty(payload))

# %% [markdown]
# ## Final merged config

# %%
final_config = load(MAIN_FILE)
print(Pretty(final_config))
