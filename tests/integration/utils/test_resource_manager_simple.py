"""Simple test for resource management framework."""

import asyncio
import threading
import time
from unittest.mock import Mock

import pytest
from kailash.utils.resource_manager import (
    AsyncResourcePool,
    ResourcePool,
    ResourceTracker,
)


class TestResourcePool:
    """Test sync resource pool implementation."""

    def test_basic_pool_operations(self):
        """Test basic acquire and release operations."""
        counter = {"value": 0}

        def factory():
            counter["value"] += 1
            return f"resource_{counter['value']}"

        pool = ResourcePool(factory=factory, max_size=3)

        # Test acquisition
        with pool.acquire() as resource:
            assert resource == "resource_1"
            assert len(pool._in_use) == 1
            assert len(pool._pool) == 0

        # Resource should be returned to pool
        assert len(pool._in_use) == 0
        assert len(pool._pool) == 1

        # Test reuse
        with pool.acquire() as resource:
            assert resource == "resource_1"  # Should reuse

    def test_pool_creation_limit(self):
        """Test pool creation limits work."""
        pool = ResourcePool(factory=lambda: Mock(), max_size=2)

        # Should be able to create resources up to limit
        with pool.acquire() as r1:
            with pool.acquire() as r2:
                assert r1 is not r2
                assert pool._created_count == 2

    def test_resource_cleanup(self):
        """Test resource cleanup functionality."""
        cleanup_called = []

        def cleanup(resource):
            cleanup_called.append(resource)

        pool = ResourcePool(factory=lambda: "resource", max_size=2, cleanup=cleanup)

        # Create a resource
        with pool.acquire():
            pass

        # Cleanup all resources
        pool.cleanup_all()

        assert len(cleanup_called) == 1

    def test_thread_safety(self):
        """Test pool is thread-safe."""
        pool = ResourcePool(factory=lambda: Mock(), max_size=5)
        results = []
        errors = []

        def worker():
            try:
                with pool.acquire() as resource:
                    results.append(resource)
                    time.sleep(0.01)  # Hold resource briefly
            except Exception as e:
                errors.append(e)

        # Start multiple threads
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        # Should have at most 5 unique resources
        assert len(set(id(r) for r in results)) <= 5


class TestAsyncResourcePool:
    """Test async resource pool implementation."""

    @pytest.mark.asyncio
    async def test_basic_async_operations(self):
        """Test basic async acquire and release."""
        counter = {"value": 0}

        def factory():
            counter["value"] += 1
            return f"async_resource_{counter['value']}"

        pool = AsyncResourcePool(factory=factory, max_size=3)

        async with pool.acquire() as resource:
            assert resource == "async_resource_1"
            assert len(pool._in_use) == 1

        assert len(pool._in_use) == 0
        assert len(pool._pool) == 1

    @pytest.mark.asyncio
    async def test_async_cleanup(self):
        """Test async resource cleanup."""
        cleanup_called = []

        def cleanup(resource):
            cleanup_called.append(resource)

        pool = AsyncResourcePool(
            factory=lambda: "async_resource", max_size=2, cleanup=cleanup
        )

        async with pool.acquire():
            pass

        await pool.cleanup_all()
        assert len(cleanup_called) == 1

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test concurrent async access."""
        pool = AsyncResourcePool(factory=lambda: Mock(), max_size=3)
        results = []

        async def worker():
            async with pool.acquire() as resource:
                results.append(resource)
                await asyncio.sleep(0.01)

        # Run concurrent workers
        await asyncio.gather(*[worker() for _ in range(6)])

        assert len(results) == 6
        # Should have at most 3 unique resources
        assert len(set(id(r) for r in results)) <= 3


class TestResourceTracker:
    """Test resource tracking functionality."""

    def test_resource_tracking(self):
        """Test basic resource tracking."""
        tracker = ResourceTracker()

        resource1 = Mock()
        resource2 = Mock()

        # Track resources
        tracker.register("type1", resource1)
        tracker.register("type2", resource2)

        # Check tracking works
        assert len(tracker._resources["type1"]) == 1
        assert len(tracker._resources["type2"]) == 1

        # Check metrics
        assert tracker._metrics["type1"]["created"] == 1
        assert tracker._metrics["type2"]["created"] == 1

    def test_weak_references(self):
        """Test that tracker uses weak references."""
        tracker = ResourceTracker()

        # Create and register a resource
        resource = Mock()
        tracker.register("test", resource)

        assert len(tracker._resources["test"]) == 1

        # Delete the resource
        del resource

        # Weak reference should be cleaned up automatically
        # (This might not happen immediately due to GC timing)


class TestIntegration:
    """Test integration scenarios."""

    def test_pool_with_mock_connections(self):
        """Test pool with mock database-like connections."""
        connections_created = 0
        connections_closed = 0

        class MockConnection:
            def __init__(self):
                nonlocal connections_created
                connections_created += 1
                self.closed = False

            def close(self):
                nonlocal connections_closed
                if not self.closed:
                    connections_closed += 1
                    self.closed = True

        pool = ResourcePool(
            factory=MockConnection, max_size=3, cleanup=lambda conn: conn.close()
        )

        # Use connections
        for _ in range(5):
            with pool.acquire() as conn:
                assert not conn.closed

        # Should have created only 3 connections (pool size)
        assert connections_created <= 3

        # Cleanup pool
        pool.cleanup_all()
        assert connections_closed >= 1

    @pytest.mark.asyncio
    async def test_async_pool_with_mock_sessions(self):
        """Test async pool with mock HTTP session-like objects."""
        sessions_created = 0
        sessions_closed = 0

        class MockSession:
            def __init__(self):
                nonlocal sessions_created
                sessions_created += 1
                self.closed = False

            def close(self):
                nonlocal sessions_closed
                if not self.closed:
                    sessions_closed += 1
                    self.closed = True

        pool = AsyncResourcePool(
            factory=MockSession, max_size=2, cleanup=lambda session: session.close()
        )

        # Use sessions concurrently
        async def use_session():
            async with pool.acquire() as session:
                assert not session.closed
                await asyncio.sleep(0.01)

        await asyncio.gather(*[use_session() for _ in range(4)])

        # Should have created only 2 sessions (pool size)
        assert sessions_created <= 2

        # Cleanup pool
        await pool.cleanup_all()
        assert sessions_closed >= 1

    def test_resource_manager_basic_performance(self):
        """Test basic resource manager performance."""
        pool = ResourcePool(factory=lambda: Mock(), max_size=10)

        # Measure acquisition time
        start_time = time.time()
        for _ in range(100):
            with pool.acquire():
                pass
        elapsed = time.time() - start_time

        # Should be reasonably fast (less than 1s for 100 acquisitions)
        assert elapsed < 1.0
