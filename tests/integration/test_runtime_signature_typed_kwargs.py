# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Integration: #912 Shard 1 runtime typed kwargs additive contract (Tier 2).

Issue #912 — per-task soft/hard time limits. Shard 1 lands the typed
kwargs SLOT on every runtime ``execute*`` method without enforcing the
deadline yet (Shard 2 wires the timer). This Tier 2 test exercises the
slot end-to-end:

  * Real ``LocalRuntime`` + real ``WorkflowBuilder`` — no mocks.
  * Asserts the typed kwarg is accepted at call time without raising.
  * Asserts the additive ``**kwargs`` contract still absorbs unknown
    kwargs (an unrecognised name MUST NOT raise TypeError until a
    future shard with a Rule 6a deprecation cycle removes ``**kwargs``).
  * Asserts validation fires on negative input.

The test does NOT assert deadline enforcement — that is Shard 2's
responsibility. Asserting enforcement here would silently mask Shard 2's
absence per ``zero-tolerance.md`` Rule 3c (kwarg accepted but unused).
"""

from __future__ import annotations

import pytest

from kailash.access_control import UserContext
from kailash.runtime.access_controlled import AccessControlledRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def _user_context() -> UserContext:
    """Construct a minimal UserContext for AccessControlledRuntime tests.

    Access control is disabled by default at the manager level, so the
    user identity does not gate execution — this fixture exists only to
    satisfy the constructor.
    """
    return UserContext(
        user_id="test-912-shard-1",
        tenant_id="test-tenant",
        email="test@example.com",
        roles=["analyst"],
    )


def _trivial_workflow():
    """Build the smallest possible workflow that LocalRuntime can execute.

    Uses ``PythonCodeNode`` returning a constant — no external dependencies,
    no DB, no network. Tier 2 because we exercise the real runtime, not
    because of infrastructure heaviness.
    """
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "noop",
        {"code": "result = {'ok': True}"},
    )
    return workflow.build()


@pytest.mark.integration
def test_local_runtime_accepts_soft_time_limit_kwarg():
    """LocalRuntime.execute(...) MUST accept soft_time_limit without raising.

    Per #912 Shard 1: slot lands now, enforcement lands in Shard 2.
    """
    workflow = _trivial_workflow()
    with LocalRuntime() as runtime:
        # No raise = signature accepts the kwarg.
        results, _ = runtime.execute(workflow, soft_time_limit=2.0)
    assert results is not None


@pytest.mark.integration
def test_local_runtime_accepts_time_limit_kwarg():
    """LocalRuntime.execute(...) MUST accept time_limit without raising."""
    workflow = _trivial_workflow()
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow, time_limit=10.0)
    assert results is not None


@pytest.mark.integration
def test_local_runtime_accepts_both_typed_kwargs():
    """Both kwargs together MUST work when soft < hard."""
    workflow = _trivial_workflow()
    with LocalRuntime() as runtime:
        results, _ = runtime.execute(workflow, soft_time_limit=2.0, time_limit=10.0)
    assert results is not None


@pytest.mark.integration
def test_local_runtime_kwargs_absorption_still_works():
    """Per the additive Shard 1 contract, **kwargs MUST still absorb unknown kwargs.

    A future shard with a Rule 6a deprecation cycle MAY remove **kwargs.
    Until then, callers passing arbitrary kwargs continue to work.
    """
    workflow = _trivial_workflow()
    with LocalRuntime() as runtime:
        # Garbage kwarg silently absorbed by **kwargs — no TypeError.
        results, _ = runtime.execute(workflow, garbage_kwarg_for_912=1)
    assert results is not None


@pytest.mark.integration
def test_local_runtime_rejects_negative_soft_time_limit():
    """Validation fires at the entry point, not at the timer thread."""
    workflow = _trivial_workflow()
    with LocalRuntime() as runtime:
        with pytest.raises(ValueError):
            runtime.execute(workflow, soft_time_limit=-1)


@pytest.mark.integration
def test_local_runtime_rejects_negative_time_limit():
    """Validation fires at the entry point on negative hard limit too."""
    workflow = _trivial_workflow()
    with LocalRuntime() as runtime:
        with pytest.raises(ValueError):
            runtime.execute(workflow, time_limit=-1)


@pytest.mark.integration
def test_local_runtime_rejects_soft_ge_hard():
    """``soft_time_limit >= time_limit`` is invalid — caller bug, raise loudly."""
    workflow = _trivial_workflow()
    with LocalRuntime() as runtime:
        with pytest.raises(ValueError):
            runtime.execute(workflow, soft_time_limit=10, time_limit=5)


@pytest.mark.integration
def test_access_controlled_runtime_accepts_typed_kwargs():
    """AccessControlledRuntime forwards typed kwargs to its inner runtime.

    Access-control manager defaults to disabled, so we exercise the
    short-circuit path (acm.enabled is False without explicit setup),
    still proving the wrapper accepts and forwards the typed kwargs.
    """
    workflow = _trivial_workflow()
    with AccessControlledRuntime(user_context=_user_context()) as runtime:
        results, _ = runtime.execute(workflow, soft_time_limit=2.0, time_limit=10.0)
    assert results is not None


@pytest.mark.integration
def test_access_controlled_runtime_validates_typed_kwargs():
    """AccessControlledRuntime MUST surface validation errors from typed kwargs."""
    workflow = _trivial_workflow()
    with AccessControlledRuntime(user_context=_user_context()) as runtime:
        with pytest.raises(ValueError):
            runtime.execute(workflow, soft_time_limit=-1)
