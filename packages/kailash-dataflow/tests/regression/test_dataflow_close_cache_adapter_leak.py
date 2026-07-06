# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: ``DataFlow.close`` / ``close_async`` MUST close the Express cache
backend's executor thread pool.

``DataFlowExpress.__init__`` eagerly auto-detects a cache backend. When Redis is
reachable that backend is an ``AsyncRedisCacheAdapter`` owning a
``ThreadPoolExecutor``; neither ``DataFlow.close()`` nor ``DataFlow.close_async()``
used to tear it down, so the worker threads leaked and the adapter emitted
``ResourceWarning: AsyncRedisCacheAdapter not closed`` at GC. The fix gives
``DataFlowExpress`` a ``close``/``close_async`` that closes ``_cache_manager`` and
wires both engine close paths to invoke it.

These tests are DETERMINISTIC and infra-free: the real leak only manifests when
Redis is reachable (the in-memory fallback owns no executor), which would make a
warning-based test pass vacuously on a ``[dev]``-only CI runner. Instead they
inject a recording cache-manager and assert the close wiring actually invokes it
on BOTH paths — the wiring is what regressed, and the wiring is what we pin.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import pytest
from dataflow import DataFlow


class _RecordingCacheManager:
    """Stand-in for the auto-detected cache backend that records teardown.

    Mirrors the ``AsyncRedisCacheAdapter`` teardown surface (a sync ``close`` and
    an async ``close_async``) so the engine's duck-typed teardown reaches it.
    """

    def __init__(self) -> None:
        self.close_called = False
        self.close_async_called = False

    def close(self) -> None:
        self.close_called = True

    async def close_async(self) -> None:
        self.close_async_called = True


def test_dataflow_express_exposes_cache_close_methods():
    """``DataFlowExpress`` MUST expose sync ``close`` and async ``close_async`` so
    the engine teardown has a wiring target (the methods that regressed absent)."""
    from dataflow.features.express import DataFlowExpress

    assert callable(getattr(DataFlowExpress, "close", None)), (
        "DataFlowExpress.close missing — the sync engine close() path has no way "
        "to release the cache backend's executor thread pool"
    )
    assert callable(getattr(DataFlowExpress, "close_async", None)), (
        "DataFlowExpress.close_async missing — the async engine close_async() "
        "path has no way to release the cache backend's executor thread pool"
    )


@pytest.mark.asyncio
async def test_close_async_closes_express_cache_backend():
    """``DataFlow.close_async()`` MUST call the Express cache backend's
    ``close_async`` so a Redis-backed adapter's executor is torn down."""
    db = DataFlow("sqlite:///:memory:")
    recorder = _RecordingCacheManager()
    # Inject the recording backend where the real AsyncRedisCacheAdapter lives.
    db._express_dataflow._cache_manager = recorder

    await db.close_async()

    assert recorder.close_async_called, (
        "DataFlow.close_async() did not close the Express cache backend — the "
        "AsyncRedisCacheAdapter executor thread pool leaks on GC"
    )


def test_close_sync_closes_express_cache_backend():
    """``DataFlow.close()`` MUST call the Express cache backend's sync ``close``."""
    db = DataFlow("sqlite:///:memory:")
    recorder = _RecordingCacheManager()
    db._express_dataflow._cache_manager = recorder

    db.close()

    assert recorder.close_called, (
        "DataFlow.close() did not close the Express cache backend — the "
        "AsyncRedisCacheAdapter executor thread pool leaks on GC"
    )


@pytest.mark.asyncio
async def test_close_async_closes_engine_cache_integration_backend():
    """``DataFlow.close_async()`` MUST also close the engine-level
    ``_cache_integration`` cache backend — a SECOND, distinct adapter (own
    executor) auto-detected in ``_initialize_cache_integration``, separate from
    the Express one. Pins the ``_cache_integration`` teardown block so deleting
    it does not pass silently."""
    from types import SimpleNamespace

    db = DataFlow("sqlite:///:memory:")
    recorder = _RecordingCacheManager()
    # _cache_integration wraps its backend as `.cache_manager` (ListNodeCacheIntegration).
    db._cache_integration = SimpleNamespace(cache_manager=recorder)

    await db.close_async()

    assert recorder.close_async_called, (
        "DataFlow.close_async() did not close the engine-level _cache_integration "
        "backend — its AsyncRedisCacheAdapter executor leaks on GC"
    )
    assert db._cache_integration is None


def test_close_sync_closes_engine_cache_integration_backend():
    """``DataFlow.close()`` MUST also close the engine-level ``_cache_integration``
    backend via its sync ``close`` (sync path counterpart of the test above)."""
    from types import SimpleNamespace

    db = DataFlow("sqlite:///:memory:")
    recorder = _RecordingCacheManager()
    db._cache_integration = SimpleNamespace(cache_manager=recorder)

    db.close()

    assert recorder.close_called, (
        "DataFlow.close() did not close the engine-level _cache_integration "
        "backend — its AsyncRedisCacheAdapter executor leaks on GC"
    )
    assert db._cache_integration is None


@pytest.mark.asyncio
async def test_async_redis_adapter_has_idempotent_sync_and_async_close():
    """The adapter MUST expose an idempotent sync ``close`` AND ``close_async``
    (both shut the executor); double-close is a no-op."""
    from concurrent.futures import ThreadPoolExecutor
    from unittest.mock import MagicMock

    from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter

    adapter = AsyncRedisCacheAdapter(redis_manager=MagicMock())
    assert isinstance(adapter._executor, ThreadPoolExecutor)
    assert adapter._closed is False

    adapter.close()
    assert adapter._closed is True
    adapter.close()  # idempotent — no raise
    await adapter.close_async()  # already closed — no raise
    assert adapter._closed is True


@pytest.mark.asyncio
async def test_close_async_shuts_executor_via_offload_path():
    """``close_async()`` on a FRESH adapter (no prior sync ``close()``) MUST run
    the ``asyncio.to_thread(shutdown, wait=True)`` offload path and mark the
    adapter closed. The idempotency test above closes sync-first, which
    short-circuits ``close_async``; this test pins the offload path itself so a
    regression in it cannot ship green."""
    from unittest.mock import MagicMock

    from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter

    adapter = AsyncRedisCacheAdapter(redis_manager=MagicMock())
    assert adapter._closed is False

    await adapter.close_async()  # exercises the to_thread offload (no prior close)

    assert adapter._closed is True
    assert adapter._executor._shutdown is True
