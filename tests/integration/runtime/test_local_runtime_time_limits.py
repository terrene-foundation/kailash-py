# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring tests for #912 Shard 6 — LocalRuntime in-process time-limit enforcement.

Per ``rules/testing.md`` Tier 2 contract: NO mocking, real LocalRuntime,
real workflow execution against in-process infra (no external services).

The /redteam Round 1 audit caught that LocalRuntime accepted
``soft_time_limit`` / ``time_limit`` kwargs but never armed
``arm_time_limits`` — only ``_validate_limits`` ran, then the kwargs
were dropped. The README quickstart::

    runtime = LocalRuntime()
    runtime.execute(workflow.build(), soft_time_limit=2)

silently failed: a workflow that ran longer than 2s would never raise
``SoftTimeLimitExceeded``. Same fake-dispatch failure mode as
``zero-tolerance.md`` Rule 2 § "Fake dispatch".

This test suite verifies the wiring END-TO-END through the public
``LocalRuntime.execute()`` API:

* Soft / hard time limits actually fire against a sleeping workflow.
* No-limit path completes normally (no allocation overhead, no false
  positives).
* Validation errors (negative / NaN / Inf) raise at the entry point
  with the typed ``ValueError`` per Shard 6 input-validation hardening.

Tests use a single-node ``PythonCodeNode`` workflow that sleeps
deterministically. We construct workflows in-process (no
``Workflow.to_dict()`` round-trip) to sidestep the pre-existing
``PythonCodeNode.code`` serialization gap noted in the Shard-4 tests.
"""

from __future__ import annotations

import time

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import HardTimeLimitExceeded, SoftTimeLimitExceeded
from kailash.workflow.builder import WorkflowBuilder


def _sleeping_workflow(sleep_seconds: float):
    """Build a 1-node workflow whose body blocks for ``sleep_seconds``.

    Uses ``time.sleep`` (blocking) so the time-limit timer is the only
    way to interrupt — mirrors a real workload that doesn't poll
    cancellation between sub-steps.
    """
    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode",
        "sleeper",
        {"code": f"import time as _t; _t.sleep({sleep_seconds!r}); result = 'done'"},
    )
    return builder.build()


def _instant_workflow():
    """Build a 1-node workflow that returns immediately."""
    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode",
        "instant",
        {"code": "result = 42"},
    )
    return builder.build()


# --------------------------------------------------------------------------- #
# End-to-end enforcement — soft + hard time limits actually fire
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_local_runtime_soft_time_limit_raises_on_sleeping_workflow():
    """``soft_time_limit`` MUST raise (Soft|Hard)TimeLimitExceeded against a sleeping workflow.

    The README quickstart promise — runtime arms a soft + hard timer,
    the workflow's blocking sleep does NOT poll the cancellation
    token, so the soft signal cannot interrupt mid-sleep. The hard
    timer fires its flag, and the post-completion poll in
    ``LocalRuntime.execute`` raises ``HardTimeLimitExceeded`` per
    Shard 2 invariant 5 (hard kill is non-negotiable).

    Single-node workflows whose body blocks past the soft deadline
    raise the typed deadline exception AT completion (the runtime's
    inter-node poll never fires for a 1-node workflow). Multi-node
    workflows or workflows whose nodes poll cancellation observe the
    soft signal earlier.
    """
    runtime = LocalRuntime()
    workflow = _sleeping_workflow(sleep_seconds=2.0)

    start = time.monotonic()
    with pytest.raises((SoftTimeLimitExceeded, HardTimeLimitExceeded)) as exc_info:
        runtime.execute(workflow, soft_time_limit=0.5, time_limit=1.0)
    elapsed = time.monotonic() - start

    # The deadline raise MUST fire by the post-completion poll. The
    # blocking sleep means we wait the full 2s, but the typed
    # exception MUST be raised (NOT the unstubbed quickstart success).
    assert exc_info.type in (SoftTimeLimitExceeded, HardTimeLimitExceeded)
    # Bound elapsed below 10s so we know we didn't hang waiting on a
    # never-firing timer (the no-wiring failure mode would hit pytest's
    # 30s timeout). The bound is loose enough to absorb cold-start
    # overhead — PythonCodeNode subprocess + import-cache warm-up can
    # add several seconds beyond the 2s workflow sleep on a fresh
    # interpreter. The test's purpose is "did the timer fire at all",
    # which the typed exception assertion already proves; the elapsed
    # bound only guards against the no-wiring "completes successfully"
    # path masquerading as a typed-exception raise.
    assert elapsed < 10.0, (
        f"raise MUST happen by post-completion poll, not hang; "
        f"elapsed={elapsed:.2f}s, exc={type(exc_info.value).__name__}"
    )


@pytest.mark.integration
def test_local_runtime_hard_time_limit_raises_after_grace():
    """``time_limit`` MUST raise HardTimeLimitExceeded after time_limit + grace.

    No soft limit — only hard. The hard timer's flag fires
    unconditionally after grace; the post-completion poll in
    ``LocalRuntime.execute`` raises ``HardTimeLimitExceeded`` even
    when the workflow's body completes "successfully" (the deadline
    elapsed during the blocking node).
    """
    runtime = LocalRuntime()
    workflow = _sleeping_workflow(sleep_seconds=2.0)

    start = time.monotonic()
    with pytest.raises(HardTimeLimitExceeded):
        runtime.execute(workflow, time_limit=0.5)
    elapsed = time.monotonic() - start

    # Hard kill at 0.5s + 1.0s grace = 1.5s; the blocking sleep
    # finishes at 2.0s, so the post-completion poll fires at ~2s.
    # 10s upper bound absorbs cold-start overhead (see soft-limit test
    # above for rationale); the no-wiring failure mode hits pytest's
    # 30s timeout, not this bound.
    assert elapsed < 10.0, (
        f"hard kill MUST raise by post-completion poll; " f"elapsed={elapsed:.2f}s"
    )


@pytest.mark.integration
def test_local_runtime_no_limits_passes_through():
    """``runtime.execute(workflow.build())`` without limits — no timer arms, no false fire.

    The no-limit path is the most-common path; it MUST stay
    allocation-free (no token wrap, no timer thread) AND MUST NOT
    raise spurious SoftTimeLimitExceeded / HardTimeLimitExceeded for
    a workflow that completes naturally.
    """
    runtime = LocalRuntime()
    workflow = _instant_workflow()

    results, run_id = runtime.execute(workflow)

    assert results is not None
    assert "instant" in results
    assert results["instant"]["result"] == 42


# --------------------------------------------------------------------------- #
# Entry-point validation (Shard 6 finite-check + grace_seconds hardening)
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_local_runtime_validation_rejects_negative_soft():
    """``runtime.execute(soft_time_limit=-1)`` raises ValueError at entry point.

    The validator is the single source of truth — caller error MUST
    raise here, not later from a timer thread.
    """
    runtime = LocalRuntime()
    workflow = _instant_workflow()

    with pytest.raises(ValueError, match="soft_time_limit"):
        runtime.execute(workflow, soft_time_limit=-1)


@pytest.mark.integration
def test_local_runtime_validation_rejects_negative_hard():
    """``runtime.execute(time_limit=-1)`` raises ValueError at entry point."""
    runtime = LocalRuntime()
    workflow = _instant_workflow()

    with pytest.raises(ValueError, match="time_limit"):
        runtime.execute(workflow, time_limit=-1)


@pytest.mark.integration
def test_local_runtime_validation_rejects_nan_soft():
    """``runtime.execute(soft_time_limit=NaN)`` raises ValueError (Shard 6 F1).

    NaN bypassed the original ``<= 0`` check; the finite-check added
    in Shard 6 catches it at the entry point so ``Timer(nan, ...)``
    is never armed.
    """
    runtime = LocalRuntime()
    workflow = _instant_workflow()

    with pytest.raises(ValueError, match="finite"):
        runtime.execute(workflow, soft_time_limit=float("nan"))


@pytest.mark.integration
def test_local_runtime_validation_rejects_inf_hard():
    """``runtime.execute(time_limit=Inf)`` raises ValueError (Shard 6 F1).

    Inf bypassed the original ``<= 0`` check; without the finite-check,
    ``Timer(inf, ...)`` would sleep forever and the workflow would be
    uncancellable.
    """
    runtime = LocalRuntime()
    workflow = _instant_workflow()

    with pytest.raises(ValueError, match="finite"):
        runtime.execute(workflow, time_limit=float("inf"))


@pytest.mark.integration
def test_local_runtime_validation_rejects_soft_geq_hard():
    """``runtime.execute(soft_time_limit=5, time_limit=5)`` raises ValueError.

    Celery-style soft-then-hard contract: the soft signal MUST precede
    the hard kill with a non-zero warning window.
    """
    runtime = LocalRuntime()
    workflow = _instant_workflow()

    with pytest.raises(ValueError, match="strictly less"):
        runtime.execute(workflow, soft_time_limit=5.0, time_limit=5.0)
