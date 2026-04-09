# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression test for gh#362: sync product functions must not block the event loop.

Before the fix, PipelineExecutor called sync product functions directly on the
event loop thread. A sync function doing I/O (e.g., reading a file, calling a
blocking HTTP client) would block the entire event loop for the duration of
the call, starving all concurrent async tasks.

After the fix, sync product functions are offloaded to a thread via
``asyncio.to_thread()``, keeping the event loop responsive.

Tier 2 integration test: real PipelineExecutor, real InMemoryFabricCacheBackend,
NO mocking.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

import pytest

from dataflow.fabric.cache import InMemoryFabricCacheBackend
from dataflow.fabric.context import PipelineContext
from dataflow.fabric.pipeline import PipelineExecutor

pytestmark = [pytest.mark.regression, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Minimal DataFlow stand-in (same pattern as test_issue_358)
# ---------------------------------------------------------------------------


class _FakeDataFlow:
    """Minimal DataFlow stand-in for PipelineExecutor construction."""

    class _Database:
        def get_pool_size(self, _env: str) -> int:
            return 5

    class _Config:
        database = None
        environment = "development"

        def __init__(self) -> None:
            self.database = _FakeDataFlow._Database()

    def __init__(self) -> None:
        self.config = _FakeDataFlow._Config()


# ---------------------------------------------------------------------------
# Sync product function that blocks for a measurable duration
# ---------------------------------------------------------------------------

_BLOCK_SECONDS = 0.3


def sync_product_blocking(ctx: Any) -> Dict[str, Any]:
    """A sync product function that blocks the calling thread."""
    time.sleep(_BLOCK_SECONDS)
    return {"status": "computed", "blocked_for": _BLOCK_SECONDS}


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_sync_product_does_not_block_event_loop() -> None:
    """A sync product function should be offloaded to a thread, not blocking the loop.

    Strategy: run the sync product function through PipelineExecutor while
    concurrently scheduling a lightweight async probe. If the sync function
    blocked the loop, the probe would not get scheduled until after the
    blocking call completes (~0.3s). If offloaded to a thread, the probe
    runs almost immediately.
    """
    backend = InMemoryFabricCacheBackend()
    executor = PipelineExecutor(
        _FakeDataFlow(),
        cache_backend=backend,
        dev_mode=True,
    )

    ctx = PipelineContext(express=None, sources={}, products_cache={})

    # Track when the probe completes relative to when the pipeline started
    probe_completed_at: list[float] = []

    async def probe_task() -> None:
        """An async task that should run while the sync product is in a thread."""
        # Yield control to the event loop; if the loop is blocked,
        # this won't run until the blocking call finishes.
        await asyncio.sleep(0)
        probe_completed_at.append(time.monotonic())

    t0 = time.monotonic()

    # Start both the pipeline execution and the probe concurrently
    pipeline_task = asyncio.create_task(
        executor.execute_product(
            product_name="blocking_product",
            product_fn=sync_product_blocking,
            context=ctx,
        )
    )
    # Give the pipeline task a moment to enter the semaphore and start
    # the product function call before launching the probe.
    await asyncio.sleep(0.05)
    probe = asyncio.create_task(probe_task())

    result = await pipeline_task
    await probe

    # The product should have executed successfully
    assert result.data["status"] == "computed"
    assert result.data["blocked_for"] == _BLOCK_SECONDS

    # The probe should have completed WELL before the blocking function
    # finished. If the loop was blocked, the probe would complete at
    # approximately t0 + BLOCK_SECONDS. If offloaded to a thread, the
    # probe completes almost immediately after being scheduled.
    assert len(probe_completed_at) == 1
    probe_elapsed = probe_completed_at[0] - t0

    # The probe should have completed in under 0.2s (generous margin).
    # If the loop was blocked, probe_elapsed would be >= BLOCK_SECONDS (~0.3s).
    assert probe_elapsed < 0.2, (
        f"Probe took {probe_elapsed:.3f}s to complete — the event loop "
        f"appears to have been blocked by the sync product function. "
        f"Expected < 0.2s (sync function blocks for {_BLOCK_SECONDS}s)."
    )

    await executor.close()


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_sync_product_with_params_does_not_block_event_loop() -> None:
    """Sync product with params should also be offloaded to a thread."""
    backend = InMemoryFabricCacheBackend()
    executor = PipelineExecutor(
        _FakeDataFlow(),
        cache_backend=backend,
        dev_mode=True,
    )

    ctx = PipelineContext(express=None, sources={}, products_cache={})

    def sync_product_with_params(ctx: Any, params: Dict[str, Any]) -> Dict[str, Any]:
        time.sleep(0.2)
        return {"echo": params, "source": "sync"}

    probe_completed_at: list[float] = []

    async def probe_task() -> None:
        await asyncio.sleep(0)
        probe_completed_at.append(time.monotonic())

    t0 = time.monotonic()

    pipeline_task = asyncio.create_task(
        executor.execute_product(
            product_name="param_product",
            product_fn=sync_product_with_params,
            context=ctx,
            params={"key": "value"},
        )
    )
    await asyncio.sleep(0.05)
    probe = asyncio.create_task(probe_task())

    result = await pipeline_task
    await probe

    assert result.data["echo"] == {"key": "value"}
    assert result.data["source"] == "sync"

    probe_elapsed = probe_completed_at[0] - t0
    assert probe_elapsed < 0.15, (
        f"Probe took {probe_elapsed:.3f}s — event loop was blocked by "
        f"sync product function with params."
    )

    await executor.close()


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_async_product_still_works_after_sync_fix() -> None:
    """Async product functions must continue to work correctly (no regression)."""
    backend = InMemoryFabricCacheBackend()
    executor = PipelineExecutor(
        _FakeDataFlow(),
        cache_backend=backend,
        dev_mode=True,
    )

    ctx = PipelineContext(express=None, sources={}, products_cache={})

    async def async_product(ctx: Any) -> Dict[str, Any]:
        await asyncio.sleep(0.01)
        return {"source": "async", "value": 42}

    result = await executor.execute_product(
        product_name="async_product",
        product_fn=async_product,
        context=ctx,
    )

    assert result.data["source"] == "async"
    assert result.data["value"] == 42
    assert result.content_changed is True  # First write

    await executor.close()
