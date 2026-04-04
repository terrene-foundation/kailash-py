"""Tests for PR 5B: Fabric Cache Control + Shutdown (#246, #247, #251).

Tests cache invalidation, drain(), and refresh bypass on PipelineExecutor.
"""

import asyncio
from collections import OrderedDict
from unittest.mock import MagicMock

import pytest


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


# ---------------------------------------------------------------------------
# #246 — Cache invalidation
# ---------------------------------------------------------------------------


class TestCacheInvalidation:
    """Tests for PipelineExecutor.invalidate() and invalidate_all()."""

    @pytest.mark.regression
    def test_invalidate_existing_entry(self, pipeline):
        """Invalidating a cached product returns True and removes entry."""
        pipeline._cache_data["test_product"] = {"value": 42}
        pipeline._cache_hash["test_product"] = b"hash123"
        pipeline._cache_metadata["test_product"] = {"ts": 1}

        result = pipeline.invalidate("test_product")
        assert result is True
        assert "test_product" not in pipeline._cache_data
        assert "test_product" not in pipeline._cache_hash
        assert "test_product" not in pipeline._cache_metadata

    @pytest.mark.regression
    def test_invalidate_nonexistent_entry(self, pipeline):
        """Invalidating a non-cached product returns False."""
        result = pipeline.invalidate("nonexistent")
        assert result is False

    @pytest.mark.regression
    def test_invalidate_all_clears_everything(self, pipeline):
        """invalidate_all() clears all caches and returns count."""
        pipeline._cache_data["p1"] = {"a": 1}
        pipeline._cache_data["p2"] = {"b": 2}
        pipeline._cache_data["p3"] = {"c": 3}
        pipeline._cache_hash["p1"] = b"h1"
        pipeline._cache_hash["p2"] = b"h2"
        pipeline._cache_hash["p3"] = b"h3"

        count = pipeline.invalidate_all()
        assert count == 3
        assert len(pipeline._cache_data) == 0
        assert len(pipeline._cache_hash) == 0

    @pytest.mark.regression
    def test_invalidate_all_empty_cache(self, pipeline):
        """invalidate_all() on empty cache returns 0."""
        count = pipeline.invalidate_all()
        assert count == 0


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
