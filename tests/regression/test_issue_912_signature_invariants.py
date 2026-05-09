# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: #912 typed time-limit kwargs (additive scope).

Issue #912 introduces ``soft_time_limit`` / ``time_limit`` as keyword-only
typed kwargs on every concrete BaseRuntime subclass. Per the corrected
RC1 disposition (workspace journal 2026-05-09), Shard 1 is **additive
only** — the existing ``**kwargs`` signature is preserved for one
deprecation cycle (Rule 6a). A future shard will tighten the surface
once the deprecation window closes.

This test pins TWO invariants that, taken together, define the additive
contract:

  1. **Typed-kwarg presence**: every runtime's ``execute*`` method
     exposes ``soft_time_limit`` and ``time_limit`` as KEYWORD_ONLY
     parameters defaulting to ``None``. A future refactor that drops
     either kwarg surface fails this test loudly.

  2. **Backwards-compat ``**kwargs`` retention**: the abstract
     ``BaseRuntime.execute`` and the three runtimes the brief explicitly
     names as the producer surface (``LocalRuntime``,
     ``AsyncLocalRuntime``, ``DistributedRuntime``) STILL accept
     ``**kwargs``. A future shard that removes ``**kwargs`` without
     a deprecation cycle (Rule 6a) fails this test.

The cross-SDK invariant per ``cross-sdk-inspection.md`` Rule 3a is
documented in workspaces/issue-912-task-time-limits/02-todos/todos.md
§ "Cross-SDK alignment notes" — kailash-rs may eventually mirror with
``WorkerConfig`` / ``DiagnosticsConfig`` time-limit slots.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

# Methods that MUST gain typed time-limit kwargs (Shard 1 surface).
# Each entry: (import_path, attribute_name) where attribute_name is the
# method on the imported class. async-ness is irrelevant for signature
# inspection.
_RUNTIME_METHOD_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("kailash.runtime.base", "BaseRuntime", "execute"),
    ("kailash.runtime.local", "LocalRuntime", "execute"),
    ("kailash.runtime.async_local", "AsyncLocalRuntime", "execute"),
    ("kailash.runtime.async_local", "AsyncLocalRuntime", "execute_workflow_async"),
    ("kailash.runtime.distributed", "DistributedRuntime", "execute"),
    ("kailash.runtime.docker", "DockerRuntime", "execute"),
    ("kailash.runtime.parallel", "ParallelRuntime", "execute"),
    ("kailash.runtime.parallel_cyclic", "ParallelCyclicRuntime", "execute"),
    ("kailash.runtime.access_controlled", "AccessControlledRuntime", "execute"),
    ("kailash.runtime.durable", "DurableExecutionEngine", "execute"),
)


# Subset that MUST retain ``**kwargs`` per Rule 6a additive contract.
# The brief explicitly names BaseRuntime + LocalRuntime + AsyncLocalRuntime +
# DistributedRuntime as the producer surface that already accepted **kwargs;
# additive scope keeps **kwargs alive on all of them.
_KWARGS_RETAIN_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("kailash.runtime.base", "BaseRuntime", "execute"),
    ("kailash.runtime.local", "LocalRuntime", "execute"),
    ("kailash.runtime.async_local", "AsyncLocalRuntime", "execute"),
    ("kailash.runtime.distributed", "DistributedRuntime", "execute"),
)


def _resolve_method(mod_path: str, cls_name: str, attr: str) -> Any:
    import importlib

    module = importlib.import_module(mod_path)
    cls = getattr(module, cls_name)
    return getattr(cls, attr)


@pytest.mark.regression
@pytest.mark.parametrize("mod_path,cls_name,attr", _RUNTIME_METHOD_TARGETS)
def test_runtime_method_exposes_soft_time_limit_kwarg(mod_path, cls_name, attr):
    """Every runtime ``execute*`` method MUST accept ``soft_time_limit`` keyword-only."""
    method = _resolve_method(mod_path, cls_name, attr)
    sig = inspect.signature(method)
    params = sig.parameters

    assert "soft_time_limit" in params, (
        f"{cls_name}.{attr} MUST accept 'soft_time_limit' kwarg per #912 Shard 1; "
        f"current signature: {sig}"
    )
    p = params["soft_time_limit"]
    assert p.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"{cls_name}.{attr}::soft_time_limit MUST be KEYWORD_ONLY (got {p.kind.name}); "
        f"positional-or-keyword would let callers pass it by mistake at the wrong slot"
    )
    assert p.default is None, (
        f"{cls_name}.{attr}::soft_time_limit MUST default to None (got {p.default!r}); "
        f"a non-None default would force every existing caller into time-limit semantics"
    )


@pytest.mark.regression
@pytest.mark.parametrize("mod_path,cls_name,attr", _RUNTIME_METHOD_TARGETS)
def test_runtime_method_exposes_time_limit_kwarg(mod_path, cls_name, attr):
    """Every runtime ``execute*`` method MUST accept ``time_limit`` keyword-only."""
    method = _resolve_method(mod_path, cls_name, attr)
    sig = inspect.signature(method)
    params = sig.parameters

    assert "time_limit" in params, (
        f"{cls_name}.{attr} MUST accept 'time_limit' kwarg per #912 Shard 1; "
        f"current signature: {sig}"
    )
    p = params["time_limit"]
    assert (
        p.kind == inspect.Parameter.KEYWORD_ONLY
    ), f"{cls_name}.{attr}::time_limit MUST be KEYWORD_ONLY (got {p.kind.name})"
    assert (
        p.default is None
    ), f"{cls_name}.{attr}::time_limit MUST default to None (got {p.default!r})"


@pytest.mark.regression
@pytest.mark.parametrize("mod_path,cls_name,attr", _KWARGS_RETAIN_TARGETS)
def test_kwargs_still_present_per_additive_contract(mod_path, cls_name, attr):
    """Per RC1 corrected scope, ``**kwargs`` MUST remain on the producer surface.

    A future shard MAY remove ``**kwargs`` after a Rule 6a deprecation
    cycle. Until that shard ships, removing ``**kwargs`` here would be a
    silent BC break for every caller forwarding extra runtime-specific
    kwargs.
    """
    method = _resolve_method(mod_path, cls_name, attr)
    sig = inspect.signature(method)
    var_keyword = [
        p for p in sig.parameters.values() if p.kind == inspect.Parameter.VAR_KEYWORD
    ]
    assert var_keyword, (
        f"{cls_name}.{attr} MUST retain **kwargs for the additive Shard 1 scope; "
        f"current signature: {sig}. Removing **kwargs without a deprecation cycle "
        f"violates zero-tolerance.md Rule 6a."
    )


# ---------------------------------------------------------------------------
# Shard 3 — WorkflowScheduler signature pins
# ---------------------------------------------------------------------------
# Shard 3 wired ``default_soft_time_limit`` / ``default_time_limit`` onto
# ``WorkflowScheduler.__init__`` AND ``soft_time_limit`` / ``time_limit`` onto
# every public ``schedule_*`` entry-point. Per-task limits MUST win over
# scheduler defaults; pins below structurally guarantee BOTH layers stay
# wired so a future refactor that drops either layer fails loudly.
_SCHEDULER_PER_FIRE_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("kailash.runtime.scheduler", "WorkflowScheduler", "schedule_cron"),
    ("kailash.runtime.scheduler", "WorkflowScheduler", "schedule_interval"),
    ("kailash.runtime.scheduler", "WorkflowScheduler", "schedule_once"),
)


@pytest.mark.regression
@pytest.mark.parametrize("mod_path,cls_name,attr", _SCHEDULER_PER_FIRE_TARGETS)
def test_scheduler_method_exposes_soft_time_limit_kwarg(mod_path, cls_name, attr):
    """Each ``WorkflowScheduler.schedule_*`` MUST accept ``soft_time_limit`` kw-only."""
    method = _resolve_method(mod_path, cls_name, attr)
    sig = inspect.signature(method)
    params = sig.parameters

    assert "soft_time_limit" in params, (
        f"{cls_name}.{attr} MUST accept 'soft_time_limit' kwarg per #912 Shard 3; "
        f"current signature: {sig}"
    )
    p = params["soft_time_limit"]
    assert (
        p.kind == inspect.Parameter.KEYWORD_ONLY
    ), f"{cls_name}.{attr}::soft_time_limit MUST be KEYWORD_ONLY (got {p.kind.name})"
    assert (
        p.default is None
    ), f"{cls_name}.{attr}::soft_time_limit MUST default to None (got {p.default!r})"


@pytest.mark.regression
@pytest.mark.parametrize("mod_path,cls_name,attr", _SCHEDULER_PER_FIRE_TARGETS)
def test_scheduler_method_exposes_time_limit_kwarg(mod_path, cls_name, attr):
    """Each ``WorkflowScheduler.schedule_*`` MUST accept ``time_limit`` kw-only."""
    method = _resolve_method(mod_path, cls_name, attr)
    sig = inspect.signature(method)
    params = sig.parameters

    assert "time_limit" in params, (
        f"{cls_name}.{attr} MUST accept 'time_limit' kwarg per #912 Shard 3; "
        f"current signature: {sig}"
    )
    p = params["time_limit"]
    assert (
        p.kind == inspect.Parameter.KEYWORD_ONLY
    ), f"{cls_name}.{attr}::time_limit MUST be KEYWORD_ONLY (got {p.kind.name})"
    assert (
        p.default is None
    ), f"{cls_name}.{attr}::time_limit MUST default to None (got {p.default!r})"


@pytest.mark.regression
def test_scheduler_init_exposes_default_soft_time_limit():
    """``WorkflowScheduler.__init__`` MUST accept ``default_soft_time_limit`` kw-only.

    Per #912 Shard 3 Q1: scheduler-default falls through to per-task value;
    per-task value wins; final fallthrough is None (no limit).
    """
    method = _resolve_method(
        "kailash.runtime.scheduler", "WorkflowScheduler", "__init__"
    )
    sig = inspect.signature(method)
    params = sig.parameters

    assert "default_soft_time_limit" in params, (
        f"WorkflowScheduler.__init__ MUST accept 'default_soft_time_limit' "
        f"per #912 Shard 3; current signature: {sig}"
    )
    p = params["default_soft_time_limit"]
    assert (
        p.kind == inspect.Parameter.KEYWORD_ONLY
    ), f"default_soft_time_limit MUST be KEYWORD_ONLY (got {p.kind.name})"
    assert (
        p.default is None
    ), f"default_soft_time_limit MUST default to None (got {p.default!r})"


@pytest.mark.regression
def test_scheduler_init_exposes_default_time_limit():
    """``WorkflowScheduler.__init__`` MUST accept ``default_time_limit`` kw-only."""
    method = _resolve_method(
        "kailash.runtime.scheduler", "WorkflowScheduler", "__init__"
    )
    sig = inspect.signature(method)
    params = sig.parameters

    assert "default_time_limit" in params, (
        f"WorkflowScheduler.__init__ MUST accept 'default_time_limit' "
        f"per #912 Shard 3; current signature: {sig}"
    )
    p = params["default_time_limit"]
    assert (
        p.kind == inspect.Parameter.KEYWORD_ONLY
    ), f"default_time_limit MUST be KEYWORD_ONLY (got {p.kind.name})"
    assert (
        p.default is None
    ), f"default_time_limit MUST default to None (got {p.default!r})"


# ---------------------------------------------------------------------------
# Shard 4 — Worker signature + TaskMessage wire-format pins
# ---------------------------------------------------------------------------
# Shard 4 wired ``default_soft_time_limit`` / ``default_time_limit`` /
# ``hard_time_limit_grace_seconds`` onto ``Worker.__init__`` AND added the
# ``execution_limits`` field to ``TaskMessage``. Per-task limits ALWAYS win
# over Worker defaults; the wire field is OPTIONAL so older workers running
# pre-Shard-4 SDK silently ignore it (forward-compat).


@pytest.mark.regression
def test_worker_init_exposes_default_soft_time_limit():
    """``Worker.__init__`` MUST accept ``default_soft_time_limit`` kw-only."""
    method = _resolve_method("kailash.runtime.distributed", "Worker", "__init__")
    sig = inspect.signature(method)
    params = sig.parameters

    assert "default_soft_time_limit" in params, (
        f"Worker.__init__ MUST accept 'default_soft_time_limit' "
        f"per #912 Shard 4; current signature: {sig}"
    )
    p = params["default_soft_time_limit"]
    assert (
        p.kind == inspect.Parameter.KEYWORD_ONLY
    ), f"default_soft_time_limit MUST be KEYWORD_ONLY (got {p.kind.name})"
    assert (
        p.default is None
    ), f"default_soft_time_limit MUST default to None (got {p.default!r})"


@pytest.mark.regression
def test_worker_init_exposes_default_time_limit():
    """``Worker.__init__`` MUST accept ``default_time_limit`` kw-only."""
    method = _resolve_method("kailash.runtime.distributed", "Worker", "__init__")
    sig = inspect.signature(method)
    params = sig.parameters

    assert "default_time_limit" in params, (
        f"Worker.__init__ MUST accept 'default_time_limit' "
        f"per #912 Shard 4; current signature: {sig}"
    )
    p = params["default_time_limit"]
    assert (
        p.kind == inspect.Parameter.KEYWORD_ONLY
    ), f"default_time_limit MUST be KEYWORD_ONLY (got {p.kind.name})"
    assert (
        p.default is None
    ), f"default_time_limit MUST default to None (got {p.default!r})"


@pytest.mark.regression
def test_worker_init_exposes_hard_time_limit_grace_seconds():
    """``Worker.__init__`` MUST accept ``hard_time_limit_grace_seconds`` kw-only.

    Wind-down window between hard-deadline fire and unconditional kill;
    default 1.0s; MUST be >= 0 (per #912 Shard 2 ``arm_time_limits`` contract).
    """
    method = _resolve_method("kailash.runtime.distributed", "Worker", "__init__")
    sig = inspect.signature(method)
    params = sig.parameters

    assert "hard_time_limit_grace_seconds" in params, (
        f"Worker.__init__ MUST accept 'hard_time_limit_grace_seconds' "
        f"per #912 Shard 4; current signature: {sig}"
    )
    p = params["hard_time_limit_grace_seconds"]
    assert (
        p.kind == inspect.Parameter.KEYWORD_ONLY
    ), f"hard_time_limit_grace_seconds MUST be KEYWORD_ONLY (got {p.kind.name})"
    assert (
        p.default == 1.0
    ), f"hard_time_limit_grace_seconds MUST default to 1.0 (got {p.default!r})"


@pytest.mark.regression
def test_task_message_has_execution_limits_field():
    """``TaskMessage`` dataclass MUST expose ``execution_limits`` for forward-compat.

    Per #912 Shard 4: optional ``Dict[str, float]`` carrying per-task soft/hard
    deadlines through the queue boundary. Shape is ONE optional dict (NOT two
    separate fields) so older workers silently ignore the new field. Default
    MUST be None so older-SDK ``TaskMessage.from_json()`` calls without the
    field deserialize correctly.
    """
    import dataclasses
    from kailash.runtime.distributed import TaskMessage

    fields = {f.name: f for f in dataclasses.fields(TaskMessage)}
    assert "execution_limits" in fields, (
        f"TaskMessage MUST expose 'execution_limits' field per #912 Shard 4; "
        f"current fields: {sorted(fields)}"
    )
    f = fields["execution_limits"]
    # Default MUST be None so the wire format omits the field on the common
    # no-limit path AND older workers running pre-Shard-4 SDK silently ignore
    # the unknown payload key.
    assert f.default is None, (
        f"TaskMessage.execution_limits MUST default to None (got {f.default!r}) "
        f"so the no-limit path stays compact and older workers ignore the field"
    )
