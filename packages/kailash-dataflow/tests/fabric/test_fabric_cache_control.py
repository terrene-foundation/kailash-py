"""Tests for PR 5B: Fabric Cache Control + Shutdown (#246, #247, #251).

Tests cache invalidation, drain(), and refresh bypass on PipelineExecutor.

Phase 5 (DataFlow 2.0): cache methods are now async and delegate to a
FabricCacheBackend. Tests use the backend directly to seed state instead
of mutating the removed ``_cache_data``/``_cache_hash``/``_cache_metadata``
dicts.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from dataflow.fabric.cache import _FabricCacheEntry

# ---------------------------------------------------------------------------
# Fixtures — build a minimal PipelineExecutor without full DataFlow init
# ---------------------------------------------------------------------------


@pytest.fixture
def pipeline():
    """Create a PipelineExecutor with mocked dataflow for cache testing."""
    from dataflow.fabric.pipeline import PipelineExecutor

    mock_df = MagicMock()
    mock_df._config = MagicMock()
    mock_df._config.database = MagicMock()
    mock_df._config.database.get_pool_size = MagicMock(return_value=10)
    mock_df._config.environment = "development"
    mock_df._pool = None

    pe = PipelineExecutor(dataflow=mock_df, max_concurrent=2, dev_mode=True)
    return pe


def _seeded_entry(product_name: str) -> _FabricCacheEntry:
    """Build a minimal cache entry for direct backend seeding."""
    now = datetime.now(timezone.utc)
    return _FabricCacheEntry(
        product_name=product_name,
        tenant_id=None,
        data_bytes=b"value",
        content_hash=f"hash-{product_name}",
        metadata={"ts": 1},
        cached_at=now,
        run_started_at=now,
        size_bytes=5,
    )


# ---------------------------------------------------------------------------
# #246 — Cache invalidation
# ---------------------------------------------------------------------------


class TestCacheInvalidation:
    """Tests for PipelineExecutor.invalidate() and invalidate_all()."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_invalidate_existing_entry(self, pipeline):
        """Invalidating a cached product returns True and removes entry."""
        await pipeline.cache_backend.set("test_product", _seeded_entry("test_product"))

        result = await pipeline.invalidate("test_product")
        assert result is True
        assert await pipeline.cache_backend.get("test_product") is None

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_invalidate_nonexistent_entry(self, pipeline):
        """Invalidating a non-cached product returns False."""
        result = await pipeline.invalidate("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_invalidate_all_clears_everything(self, pipeline):
        """invalidate_all() clears every cached entry."""
        for key in ("p1", "p2", "p3"):
            await pipeline.cache_backend.set(key, _seeded_entry(key))

        await pipeline.invalidate_all()
        for key in ("p1", "p2", "p3"):
            assert await pipeline.cache_backend.get(key) is None

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_invalidate_all_empty_cache(self, pipeline):
        """invalidate_all() on empty cache is a no-op that succeeds."""
        await pipeline.invalidate_all()
        assert await pipeline.cache_backend.get("anything") is None


# ---------------------------------------------------------------------------
# drain()
# ---------------------------------------------------------------------------


class TestDrain:
    """Tests for PipelineExecutor.drain()."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_drain_completes_when_idle(self, pipeline):
        """drain() completes immediately when no executions are running."""
        await pipeline.drain(timeout=2.0)

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_drain_waits_for_in_flight(self, pipeline):
        """drain() waits for in-flight execution to complete."""
        await pipeline._exec_semaphore.acquire()

        async def release_after_delay():
            await asyncio.sleep(0.2)
            pipeline._exec_semaphore.release()

        asyncio.create_task(release_after_delay())
        await pipeline.drain(timeout=5.0)

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_drain_timeout(self, pipeline):
        """drain() returns after timeout if slots are held."""
        for _ in range(pipeline._max_concurrent):
            await pipeline._exec_semaphore.acquire()

        await pipeline.drain(timeout=0.5)

        for _ in range(pipeline._max_concurrent):
            pipeline._exec_semaphore.release()
