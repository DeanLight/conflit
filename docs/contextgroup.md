# Context groups

`conflit.Context` and `conflit.TrackedVar` provide a small set of primitives
for tracking values that flow through nested scopes — useful for log
enrichment, recursive call trees, and any value that needs to be derived
from its parent scope.

## TrackedVar

A `TrackedVar` is a typed `ContextVar` plus a `derive` function describing
how its value in a child scope is computed from its parent.

```python
from conflit import TrackedVar

depth = TrackedVar("depth", default=0, derive=lambda parent, _: parent + 1)
```

The `derive` signature is `(parent_value, sibling_inputs) -> child_value`.
`sibling_inputs` is a dict containing both the caller-supplied kwargs to
`Context.bind` and any values already derived by earlier siblings in the
same group.

### Shared vars

Set `shared=True` to make a var act as a single mutable cell that ignores
scope entry/exit. Mutations are visible to parent and sibling scopes —
useful for monotonic counters like global node ids.

```python
node_id = TrackedVar(
    "node_id",
    default=0,
    shared=True,
    derive=lambda parent, _: parent + 1,
)
```

## Context

A `Context` groups several `TrackedVar`s under a single `bind()` context
manager. Vars are derived and applied in declaration order, so put
dependencies before dependents.

```python
from conflit import Context, TrackedVar

ctx = Context(
    TrackedVar("node_id", default=0, shared=True, derive=lambda p, _: p + 1),
    TrackedVar(
        "ancestry",
        default=(),
        derive=lambda parent, inputs: parent + (inputs["node_id"],),
    ),
)

with ctx.bind() as values:
    # values == {"node_id": 1, "ancestry": (1,)}
    with ctx.bind() as inner:
        # inner == {"node_id": 2, "ancestry": (1, 2)}
        ...
```

### Attribute access

Each `TrackedVar` is also reachable as a named attribute on the `Context`
instance. This lets you call `.get()` and `.set()` without searching
`ctx.vars` by name:

```python
log_dir = TrackedVar(
    "log_dir",
    default="/tmp",
    derive=lambda parent, kw: kw.get("log_dir", parent),
)
depth = TrackedVar("depth", default=0, derive=lambda p, _: p + 1)

ctx = Context(log_dir, depth)

with ctx.bind(log_dir="/runs/exp1"):
    print(ctx.log_dir.get())  # /runs/exp1
    print(ctx.depth.get())    # 1
    ctx.log_dir.set("/runs/exp1/phase2")
    print(ctx.log_dir.get())  # /runs/exp1/phase2

print(ctx.log_dir.get())  # /tmp  — restored after bind exits
print(ctx.depth.get())    # 0
```

The names `vars`, `structlog_keys`, `_on_bind`, `reset`, and `bind` are
reserved and must not be used as `TrackedVar` names.

### structlog sync

By default every var in the group is mirrored into structlog's
`contextvars` for the duration of the bind, so any logger call inside the
scope picks them up automatically. Pass `structlog_keys=[...]` to mirror
only a subset, or `structlog_keys=[]` to disable the sync entirely.

### on_bind hook

`on_bind` is a zero-arg callable fired once per `bind()`, after vars have
been set and structlog has been synced, but before `yield`. Use it for
side effects that should run inside the bound scope — for example,
emitting a "scope entered" log line that already carries the new context
values.

```python
import structlog

log = structlog.get_logger()
ctx = Context(
    TrackedVar("depth", default=0, derive=lambda p, _: p + 1),
    on_bind=lambda: log.info("scope entered"),
)
```
