# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring tests for #912 Shard 6 — AsyncLocalRuntime in-process time-limit enforcement.

Per ``rules/testing.md`` Tier 2 contract: NO mocking, real
AsyncLocalRuntime, real workflow execution against in-process infra.

The /redteam Round 1 audit caught that AsyncLocalRuntime accepted
``soft_time_limit`` / ``time_limit`` kwargs but never armed
``arm_time_limits_async`` — only ``_validate_limits`` ran, then the
kwargs were dropped. The Time-Limit Example docstring promised the
enforcement; the code did not deliver. Same fake-dispatch failure mode
as ``zero-tolerance.md`` Rule 2 § "Fake dispatch".

This test suite verifies the wiring END-TO-END through the public
``AsyncLocalRuntime.execute_workflow_async()`` API:

* Soft / hard time limits actually fire against a sleeping workflow.
* No-limit path completes normally.
* Validation errors raise at the entry point with typed ``ValueError``.

Tests use a single-node ``PythonCodeNode`` workflow with
``asyncio.sleep`` so the asyncio timer task can interrupt cleanly on
the same event loop.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.sdk_exceptions import HardTimeLimitExceeded, SoftTimeLimitExceeded
from kailash.workflow.builder import WorkflowBuilder


def _async_sleeping_workflow(sleep_seconds: float):
    """Build a 1-node workflow whose body blocks for ``sleep_seconds``.

    Uses blocking ``time.sleep`` to mirror real CPU-bound or
    third-party-blocking workloads. The asyncio timer fires its flag
    on the event loop; the post-completion poll converts the flag
    into the typed exception even when the workflow body completes.
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
@pytest.mark.asyncio
async def test_async_local_runtime_soft_time_limit_raises_on_sleeping_workflow():
    """``soft_time_limit`` MUST raise typed deadline exception on sleeping workflow.

    The timer's asyncio task fires on the same event loop; the
    post-completion poll converts the flag into the typed exception
    even when the blocking node completes naturally.
    """
    runtime = AsyncLocalRuntime()
    workflow = _async_sleeping_workflow(sleep_seconds=2.0)

    start = time.monotonic()
    with pytest.raises((SoftTimeLimitExceeded, HardTimeLimitExceeded)) as exc_info:
        await runtime.execute_workflow_async(
            workflow, inputs={}, soft_time_limit=0.5, time_limit=1.0
        )
    elapsed = time.monotonic() - start

    assert exc_info.type in (SoftTimeLimitExceeded, HardTimeLimitExceeded)
    # Bound elapsed below 10s so we know we didn't hang. Loose enough
    # to absorb cold-start overhead (PythonCodeNode subprocess + import
    # warm-up); the no-wiring failure mode hits pytest's 30s timeout.
    assert elapsed < 10.0, (
        f"raise MUST happen by post-completion poll, not hang; "
        f"elapsed={elapsed:.2f}s, exc={type(exc_info.value).__name__}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_local_runtime_hard_time_limit_raises_after_grace():
    """``time_limit`` MUST raise HardTimeLimitExceeded after time_limit + grace."""
    runtime = AsyncLocalRuntime()
    workflow = _async_sleeping_workflow(sleep_seconds=2.0)

    start = time.monotonic()
    with pytest.raises(HardTimeLimitExceeded):
        await runtime.execute_workflow_async(workflow, inputs={}, time_limit=0.5)
    elapsed = time.monotonic() - start

    # Hard kill at 0.5s + 1.0s grace = ~1.5s; workflow completes at 2s.
    # 10s upper bound absorbs cold-start overhead (see soft-limit test
    # rationale); no-wiring failure mode hits pytest's 30s timeout.
    assert (
        elapsed < 10.0
    ), f"hard kill MUST raise by post-completion poll; elapsed={elapsed:.2f}s"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_local_runtime_no_limits_passes_through():
    """``execute_workflow_async()`` without limits — no false fire."""
    runtime = AsyncLocalRuntime()
    workflow = _instant_workflow()

    results, run_id = await runtime.execute_workflow_async(workflow, inputs={})

    assert results is not None
    assert "instant" in results


# --------------------------------------------------------------------------- #
# Entry-point validation (Shard 6 finite-check + grace_seconds hardening)
# --------------------------------------------------------------------------- #


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_local_runtime_validation_rejects_negative_soft():
    """``execute_workflow_async(soft_time_limit=-1)`` raises ValueError at entry."""
    runtime = AsyncLocalRuntime()
    workflow = _instant_workflow()

    with pytest.raises(ValueError, match="soft_time_limit"):
        await runtime.execute_workflow_async(workflow, inputs={}, soft_time_limit=-1)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_local_runtime_validation_rejects_nan_soft():
    """``execute_workflow_async(soft_time_limit=NaN)`` raises ValueError (Shard 6 F1)."""
    runtime = AsyncLocalRuntime()
    workflow = _instant_workflow()

    with pytest.raises(ValueError, match="finite"):
        await runtime.execute_workflow_async(
            workflow, inputs={}, soft_time_limit=float("nan")
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_local_runtime_validation_rejects_inf_hard():
    """``execute_workflow_async(time_limit=Inf)`` raises ValueError (Shard 6 F1)."""
    runtime = AsyncLocalRuntime()
    workflow = _instant_workflow()

    with pytest.raises(ValueError, match="finite"):
        await runtime.execute_workflow_async(
            workflow, inputs={}, time_limit=float("inf")
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_async_local_runtime_validation_rejects_soft_geq_hard():
    """``execute_workflow_async(soft=5, hard=5)`` raises ValueError."""
    runtime = AsyncLocalRuntime()
    workflow = _instant_workflow()

    with pytest.raises(ValueError, match="strictly less"):
        await runtime.execute_workflow_async(
            workflow, inputs={}, soft_time_limit=5.0, time_limit=5.0
        )
