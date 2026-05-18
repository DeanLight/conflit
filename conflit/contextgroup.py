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
# # Context groups
#
# Primitives for tracking values that flow through nested scopes:
#
# - `TrackedVar` — a `ContextVar` that knows how to derive its child value
#   from its parent.
# - `Context` — a group of `TrackedVar`s bound together via a single
#   `bind()` context manager, with optional structlog sync and an `on_bind`
#   hook fired after binding.

# %%
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Generic, TypeVar

import structlog
from juplit import test

T = TypeVar("T")


# %% [markdown]
# ## TrackedVar


# %%
class TrackedVar(Generic[T]):
    """A ContextVar that knows how to derive its child value from its parent value.

    Args:
        name:    Used as the ContextVar name and as the structlog key.
        default: Initial value before any context is entered.
        derive:  ``(parent_value, sibling_new_values) -> child_value``.
                 Defaults to identity (inherit parent value unchanged).
        shared:  If True, all contexts share one mutable box. Mutations are
                 permanent and visible to parent + siblings. reset() is a no-op.
    """

    def __init__(
        self,
        name: str,
        default: T,
        derive: Callable[[T, dict[str, Any]], T] | None = None,
        shared: bool = False,
    ):
        self.name = name
        self.default = default
        self.shared = shared
        self.derive = derive or (lambda parent, _: parent)

        if shared:
            self._box: list[T] = [default]
            self.var: ContextVar[T] | None = None
        else:
            self.var = ContextVar(name, default=default)

    def get(self) -> T:
        if self.shared:
            return self._box[0]
        return self.var.get()

    def set(self, value: T) -> Any:
        if self.shared:
            self._box[0] = value
            return None
        return self.var.set(value)

    def reset(self, token: Any) -> None:
        if self.shared or token is None:
            return
        self.var.reset(token)


# %% [markdown]
# ## Context


# %%
class Context:
    """A group of TrackedVars with a shared bind() context manager.

    Vars are derived in declaration order, so put dependencies before dependents.
    Each var's derive() receives ``(parent_value, inputs)`` where inputs is the
    union of caller-supplied kwargs and already-derived sibling new values.

    Args:
        *vars:           The tracked variables in this group.
        structlog_keys:  Subset of var names to mirror into structlog
                         contextvars on bind. ``None`` mirrors all of them;
                         pass ``[]`` to disable the sync entirely.
        on_bind:         Optional zero-arg hook fired once per ``bind()``,
                         after vars are set and structlog has been synced.
                         Useful for side effects that should run inside the
                         bound scope (e.g. emitting a "scope entered" log).
    """

    def __init__(
        self,
        *vars: TrackedVar,
        structlog_keys: list[str] | None = None,
        on_bind: Callable[[], None] | None = None,
    ):
        self.vars = vars
        self.structlog_keys = structlog_keys
        self._on_bind = on_bind

    def reset(self) -> None:
        for tracked in self.vars:
            tracked.set(tracked.default)

    @contextmanager
    def bind(self, **inputs):
        raw_tokens: dict[str, Any] = {}
        new_values: dict[str, Any] = {}

        for tracked in self.vars:
            parent_val = tracked.get()
            new_val = tracked.derive(parent_val, {**inputs, **new_values})
            new_values[tracked.name] = new_val

        for tracked in self.vars:
            raw_tokens[tracked.name] = tracked.set(new_values[tracked.name])

        structlog_tokens: dict[str, Any] = {}
        if self.structlog_keys is None:
            sync_names = {t.name for t in self.vars}
        else:
            sync_names = set(self.structlog_keys)

        if sync_names:
            structlog_tokens = structlog.contextvars.bind_contextvars(
                **{t.name: t.get() for t in self.vars if t.name in sync_names}
            )

        if self._on_bind is not None:
            self._on_bind()

        try:
            yield new_values
        finally:
            for tracked in self.vars:
                tracked.reset(raw_tokens[tracked.name])
            if structlog_tokens:
                structlog.contextvars.reset_contextvars(**structlog_tokens)


# %% [markdown]
# ## Tests


# %%
if test():
    # Basic derive + nesting + restoration.
    cg = Context(
        TrackedVar("depth", default=0, derive=lambda parent, _: parent + 1),
    )

    with cg.bind() as top:
        assert top["depth"] == 1
        with cg.bind() as nested:
            assert nested["depth"] == 2

    assert cg.vars[0].get() == 0


# %%
if test():
    # Sibling values flow through `inputs` in declaration order, and a shared
    # var leaks mutations out past the bind scope.
    cg = Context(
        TrackedVar("node_id", default=0, shared=True, derive=lambda p, _: p + 1),
        TrackedVar(
            "ancestry",
            default=(),
            derive=lambda parent, inputs: parent + (inputs["node_id"],),
        ),
    )

    with cg.bind() as outer:
        assert outer["node_id"] == 1
        assert outer["ancestry"] == (1,)
        with cg.bind() as inner:
            assert inner["node_id"] == 2
            assert inner["ancestry"] == (1, 2)

    # ancestry is a normal ContextVar — restored on exit.
    assert cg.vars[1].get() == ()
    # node_id is shared — mutations persist.
    assert cg.vars[0].get() == 2


# %%
if test():
    # on_bind fires once per bind(), and sees the new var values via .get().
    calls: list[int] = []
    tv = TrackedVar("depth", default=0, derive=lambda p, _: p + 1)

    def hook() -> None:
        calls.append(tv.get())

    cg = Context(tv, on_bind=hook)

    with cg.bind():
        with cg.bind():
            pass

    assert calls == [1, 2]


# %%
if test():
    # structlog_keys controls which vars are mirrored. By default, all are.
    tv_a = TrackedVar("a", default=0, derive=lambda p, _: p + 1)
    tv_b = TrackedVar("b", default=0, derive=lambda p, _: p + 10)

    cg_all = Context(tv_a, tv_b)
    with cg_all.bind():
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("a") == 1
        assert ctx.get("b") == 10
    assert "a" not in structlog.contextvars.get_contextvars()
    assert "b" not in structlog.contextvars.get_contextvars()

    cg_subset = Context(tv_a, tv_b, structlog_keys=["a"])
    with cg_subset.bind():
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("a") == 1
        assert "b" not in ctx

    cg_none = Context(tv_a, tv_b, structlog_keys=[])
    with cg_none.bind():
        ctx = structlog.contextvars.get_contextvars()
        assert "a" not in ctx
        assert "b" not in ctx
