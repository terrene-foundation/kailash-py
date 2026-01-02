"""Unit tests for edge consistency managers."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from kailash.edge.consistency import (
    BoundedStalenessManager,
    CausalConsistencyManager,
    ConsistencyLevel,
    EventualConsistencyManager,
    StrongConsistencyManager,
    Version,
)


class TestConsistencyManagers:
    """Test suite for consistency managers."""

    @pytest.mark.asyncio
    async def test_strong_consistency_all_success(self):
        """Test strong consistency with all replicas succeeding."""
        write_callback = AsyncMock(return_value=True)
        read_callback = AsyncMock(
            return_value={"data": "value", "timestamp": time.time()}
        )

        manager = StrongConsistencyManager(write_callback, read_callback)

        # Test write
        success = await manager.write(
            "test_key",
            "test_value",
            ["replica1", "replica2", "replica3"],
            ConsistencyLevel.ALL,
        )

        assert success is True
        assert manager.metrics.writes_succeeded == 1
        assert manager.metrics.writes_failed == 0

        # Test read
        result = await manager.read(
            "test_key", ["replica1", "replica2", "replica3"], ConsistencyLevel.ALL
        )

        assert result is not None
        assert manager.metrics.reads_total == 1

    @pytest.mark.asyncio
    async def test_strong_consistency_partial_failure(self):
        """Test strong consistency with some replicas failing."""
        # Mock prepare phase with one failure
        manager = StrongConsistencyManager(AsyncMock(), AsyncMock())
        manager._prepare_write = AsyncMock(side_effect=[True, False, True])
        manager._abort_transaction = AsyncMock()

        success = await manager.write(
            "test_key",
            "test_value",
            ["replica1", "replica2", "replica3"],
            ConsistencyLevel.ALL,
        )

        assert success is False
        assert manager.metrics.writes_failed == 1
        assert manager._abort_transaction.called

    @pytest.mark.asyncio
    async def test_eventual_consistency_write(self):
        """Test eventual consistency write operation."""
        write_results = []

        async def track_writes(replica, key, value):
            write_results.append((replica, key, value))
            return True

        manager = EventualConsistencyManager(track_writes, AsyncMock())

        success = await manager.write(
            "test_key",
            "test_value",
            ["primary", "secondary1", "secondary2"],
            ConsistencyLevel.ONE,
        )

        assert success is True
        assert manager.metrics.writes_succeeded == 1

        # Primary should be written immediately
        assert ("primary", "test_key", "test_value") in write_results

        # Wait for async replication
        await asyncio.sleep(0.1)

        # All replicas should eventually have the data
        assert len(write_results) == 3

    @pytest.mark.asyncio
    async def test_eventual_consistency_read_staleness(self):
        """Test eventual consistency detects stale reads."""
        # Return old data
        read_callback = AsyncMock(
            return_value={
                "data": "old_value",
                "timestamp": time.time() - 10,  # 10 seconds old
            }
        )

        manager = EventualConsistencyManager(AsyncMock(), read_callback)

        result = await manager.read("test_key", ["replica1"], ConsistencyLevel.ONE)

        assert result is not None
        assert manager.metrics.reads_stale == 1

    @pytest.mark.asyncio
    async def test_causal_consistency_vector_clock(self):
        """Test causal consistency with vector clock tracking."""
        write_callback = AsyncMock(return_value=True)
        read_callback = AsyncMock()

        manager = CausalConsistencyManager(write_callback, read_callback)

        # First write
        success = await manager.write(
            "key1", "value1", ["node1", "node2"], ConsistencyLevel.QUORUM
        )

        assert success is True
        assert manager.vector_clocks["key1"]["node1"] == 1

        # Verify causal metadata was included
        write_call = write_callback.call_args_list[0]
        causal_value = write_call[0][2]  # Third argument
        assert "vector_clock" in causal_value
        assert causal_value["vector_clock"]["node1"] == 1

    @pytest.mark.asyncio
    async def test_causal_consistency_dependency_wait(self):
        """Test causal consistency waits for dependencies."""
        # First call returns None (dependency not met), second returns data
        read_callback = AsyncMock(side_effect=[None, {"data": "dep_value"}])
        write_callback = AsyncMock(return_value=True)

        manager = CausalConsistencyManager(write_callback, read_callback)

        # Write with dependency
        causal_value = {
            "data": "value",
            "dependencies": ["dep_key"],
            "vector_clock": {"node1": 1},
            "timestamp": time.time(),
        }

        success = await manager._write_with_dependencies(
            "replica1", "test_key", causal_value
        )

        assert success is True
        assert read_callback.call_count == 2  # Checked dependency twice

    @pytest.mark.asyncio
    async def test_bounded_staleness_fresh_read(self):
        """Test bounded staleness with fresh data."""
        # Return fresh data
        read_callback = AsyncMock(
            return_value={
                "data": "fresh_value",
                "write_timestamp": time.time() - 0.5,  # 500ms old
                "primary_replica": "primary",
            }
        )

        manager = BoundedStalenessManager(
            AsyncMock(), read_callback, max_staleness_ms=5000  # 5 seconds
        )

        result = await manager.read("test_key", ["replica1"], ConsistencyLevel.ONE)

        assert result == "fresh_value"
        assert manager.metrics.reads_stale == 0

    @pytest.mark.asyncio
    async def test_bounded_staleness_stale_refresh(self):
        """Test bounded staleness refreshes stale data."""
        # First call returns stale data, second returns fresh
        read_callback = AsyncMock(
            side_effect=[
                {
                    "data": "stale_value",
                    "write_timestamp": time.time() - 10,  # 10 seconds old
                    "primary_replica": "primary",
                },
                {
                    "data": "fresh_value",
                    "write_timestamp": time.time(),
                    "primary_replica": "primary",
                },
            ]
        )

        manager = BoundedStalenessManager(
            AsyncMock(), read_callback, max_staleness_ms=5000  # 5 seconds
        )

        result = await manager.read("test_key", ["replica1"], ConsistencyLevel.ONE)

        assert result == "fresh_value"
        assert manager.metrics.reads_stale == 1
        assert read_callback.call_count == 2

    @pytest.mark.asyncio
    async def test_consistency_level_one(self):
        """Test ConsistencyLevel.ONE requires at least one success."""
        manager = StrongConsistencyManager(AsyncMock(), AsyncMock())

        assert manager._check_consistency_level(1, 3, ConsistencyLevel.ONE) is True
        assert manager._check_consistency_level(0, 3, ConsistencyLevel.ONE) is False

    @pytest.mark.asyncio
    async def test_consistency_level_quorum(self):
        """Test ConsistencyLevel.QUORUM requires majority."""
        manager = StrongConsistencyManager(AsyncMock(), AsyncMock())

        # 3 replicas: need 2 for quorum
        assert manager._check_consistency_level(2, 3, ConsistencyLevel.QUORUM) is True
        assert manager._check_consistency_level(1, 3, ConsistencyLevel.QUORUM) is False

        # 5 replicas: need 3 for quorum
        assert manager._check_consistency_level(3, 5, ConsistencyLevel.QUORUM) is True
        assert manager._check_consistency_level(2, 5, ConsistencyLevel.QUORUM) is False

    @pytest.mark.asyncio
    async def test_consistency_level_all(self):
        """Test ConsistencyLevel.ALL requires all replicas."""
        manager = StrongConsistencyManager(AsyncMock(), AsyncMock())

        assert manager._check_consistency_level(3, 3, ConsistencyLevel.ALL) is True
        assert manager._check_consistency_level(2, 3, ConsistencyLevel.ALL) is False

    def test_version_comparison(self):
        """Test Version comparison logic."""
        # Test timestamp comparison
        v1 = Version(1, datetime.now(UTC), "edge1")
        v2 = Version(2, datetime.now(UTC) - timedelta(seconds=10), "edge2")

        assert v1.is_newer_than(v2) is True

        # Test vector clock comparison
        v3 = Version(
            3, datetime.now(UTC), "edge1", vector_clock={"node1": 2, "node2": 1}
        )
        v4 = Version(
            4, datetime.now(UTC), "edge2", vector_clock={"node1": 1, "node2": 1}
        )

        assert v3.is_newer_than(v4) is True  # v3 dominates v4
        assert v4.is_newer_than(v3) is False

    @pytest.mark.asyncio
    async def test_causal_consistency_clock_dominance(self):
        """Test causal consistency vector clock dominance check."""
        manager = CausalConsistencyManager(AsyncMock(), AsyncMock())

        # Clock1 dominates clock2
        clock1 = {"node1": 2, "node2": 1, "node3": 3}
        clock2 = {"node1": 1, "node2": 1, "node3": 2}

        assert manager._dominates(clock1, clock2) is True
        assert manager._dominates(clock2, clock1) is False

        # Concurrent clocks (neither dominates)
        clock3 = {"node1": 2, "node2": 1}
        clock4 = {"node1": 1, "node2": 2}

        assert manager._dominates(clock3, clock4) is False
        assert manager._dominates(clock4, clock3) is False

    @pytest.mark.asyncio
    async def test_metrics_tracking(self):
        """Test metrics are properly tracked."""
        write_callback = AsyncMock(return_value=True)
        read_callback = AsyncMock(
            return_value={"data": "value", "timestamp": time.time()}
        )

        manager = EventualConsistencyManager(write_callback, read_callback)

        # Perform operations
        await manager.write("k1", "v1", ["r1", "r2"])
        await manager.write("k2", "v2", ["r1", "r2"])
        await manager.read("k1", ["r1"])

        assert manager.metrics.writes_total == 2
        assert manager.metrics.writes_succeeded == 2
        assert manager.metrics.reads_total == 1

    @pytest.mark.asyncio
    async def test_replication_lag_tracking(self):
        """Test replication lag is tracked in eventual consistency."""
        manager = EventualConsistencyManager(AsyncMock(return_value=True), AsyncMock())

        await manager.write("key", "value", ["primary", "secondary1", "secondary2"])

        # Wait for async replication
        await asyncio.sleep(0.1)

        # Check lag metrics
        assert manager.metrics.average_replication_lag_ms > 0
        assert manager.metrics.max_replication_lag_ms > 0
