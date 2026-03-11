"""
Unit tests for SchemaCache component.

Tests schema caching system with TTL, size limits, invalidation patterns,
and performance requirements (<100ms operations).
"""

import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

# Import the classes we'll implement
from dataflow.migrations.schema_state_manager import (
    CacheEntry,
    DatabaseSchema,
    SchemaCache,
)


class TestSchemaCache:
    """Test cases for SchemaCache component."""

    def test_schema_cache_initialization_default_params(self):
        """Test SchemaCache initialization with default parameters."""
        cache = SchemaCache()

        assert cache.ttl == 300  # 5 minutes default
        assert cache.max_size == 100  # Default max size
        assert cache._cache == {}
        assert cache._access_times == {}

    def test_schema_cache_initialization_custom_params(self):
        """Test SchemaCache initialization with custom parameters."""
        cache = SchemaCache(ttl=600, max_size=50)

        assert cache.ttl == 600
        assert cache.max_size == 50
        assert cache._cache == {}
        assert cache._access_times == {}

    def test_cache_schema_stores_entry_with_timestamp(self):
        """Test that caching a schema stores it with current timestamp."""
        cache = SchemaCache(ttl=300)
        mock_schema = Mock(spec=DatabaseSchema)
        connection_id = "test_connection_1"

        before_cache = datetime.now()
        cache.cache_schema(connection_id, mock_schema)
        after_cache = datetime.now()

        assert connection_id in cache._cache
        cached_entry = cache._cache[connection_id]
        assert cached_entry.schema == mock_schema
        assert before_cache <= cached_entry.timestamp <= after_cache
        assert connection_id in cache._access_times

    def test_get_cached_schema_returns_valid_entry(self):
        """Test retrieving a valid cached schema."""
        cache = SchemaCache(ttl=300)
        mock_schema = Mock(spec=DatabaseSchema)
        connection_id = "test_connection_1"

        cache.cache_schema(connection_id, mock_schema)
        retrieved_schema = cache.get_cached_schema(connection_id)

        assert retrieved_schema == mock_schema

    def test_get_cached_schema_returns_none_for_nonexistent_key(self):
        """Test retrieving schema for non-existent connection ID."""
        cache = SchemaCache()

        result = cache.get_cached_schema("nonexistent_connection")

        assert result is None

    def test_get_cached_schema_respects_ttl_expiration(self):
        """Test that expired cache entries return None."""
        cache = SchemaCache(ttl=1)  # 1 second TTL
        mock_schema = Mock(spec=DatabaseSchema)
        connection_id = "test_connection_1"

        cache.cache_schema(connection_id, mock_schema)

        # Verify entry exists immediately
        assert cache.get_cached_schema(connection_id) == mock_schema

        # Wait for TTL to expire
        time.sleep(1.1)

        # Entry should be expired
        assert cache.get_cached_schema(connection_id) is None

        # Entry should be cleaned up from internal storage
        assert connection_id not in cache._cache

    def test_cache_size_limit_enforcement_lru_eviction(self):
        """Test that cache respects size limits with LRU eviction."""
        cache = SchemaCache(ttl=300, max_size=3)

        # Fill cache to capacity
        for i in range(3):
            mock_schema = Mock(spec=DatabaseSchema)
            cache.cache_schema(f"connection_{i}", mock_schema)

        assert len(cache._cache) == 3

        # Access connection_1 to make it recently used
        cache.get_cached_schema("connection_1")

        # Add one more entry to trigger eviction
        mock_schema_new = Mock(spec=DatabaseSchema)
        cache.cache_schema("connection_3", mock_schema_new)

        # Should still have max_size entries
        assert len(cache._cache) == 3

        # connection_0 should be evicted (least recently used)
        assert "connection_0" not in cache._cache
        assert "connection_1" in cache._cache  # Recently accessed
        assert "connection_2" in cache._cache
        assert "connection_3" in cache._cache  # Newly added

    def test_invalidate_cache_specific_connection(self):
        """Test invalidating cache for specific connection ID."""
        cache = SchemaCache()
        mock_schema_1 = Mock(spec=DatabaseSchema)
        mock_schema_2 = Mock(spec=DatabaseSchema)

        cache.cache_schema("connection_1", mock_schema_1)
        cache.cache_schema("connection_2", mock_schema_2)

        assert len(cache._cache) == 2

        cache.invalidate_cache("connection_1")

        assert "connection_1" not in cache._cache
        assert "connection_2" in cache._cache
        assert len(cache._cache) == 1

    def test_invalidate_cache_all_connections(self):
        """Test invalidating entire cache."""
        cache = SchemaCache()

        # Add multiple entries
        for i in range(5):
            mock_schema = Mock(spec=DatabaseSchema)
            cache.cache_schema(f"connection_{i}", mock_schema)

        assert len(cache._cache) == 5

        cache.invalidate_cache()  # No connection_id = invalidate all

        assert len(cache._cache) == 0
        assert len(cache._access_times) == 0

    @patch("dataflow.migrations.schema_state_manager.datetime")
    def test_cache_entry_timestamp_precision(self, mock_datetime):
        """Test that cache entries store precise timestamps."""
        fixed_time = datetime(2023, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = fixed_time

        cache = SchemaCache()
        mock_schema = Mock(spec=DatabaseSchema)

        cache.cache_schema("test_connection", mock_schema)

        cached_entry = cache._cache["test_connection"]
        assert cached_entry.timestamp == fixed_time

    def test_concurrent_cache_operations_thread_safety(self):
        """Test cache operations are thread-safe."""
        import concurrent.futures
        import threading

        cache = SchemaCache(max_size=100)
        results = []

        def cache_operation(connection_id):
            try:
                mock_schema = Mock(spec=DatabaseSchema)
                cache.cache_schema(f"connection_{connection_id}", mock_schema)
                retrieved = cache.get_cached_schema(f"connection_{connection_id}")
                return retrieved is not None
            except Exception as e:
                return False

        # Run concurrent operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(cache_operation, i) for i in range(50)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # All operations should succeed
        assert all(results)
        assert len(cache._cache) == 50

    def test_cache_performance_under_100ms(self):
        """Test that cache operations complete within 100ms performance requirement."""
        cache = SchemaCache(max_size=1000)

        # Pre-populate cache
        for i in range(100):
            mock_schema = Mock(spec=DatabaseSchema)
            cache.cache_schema(f"connection_{i}", mock_schema)

        # Test cache retrieval performance
        start_time = time.perf_counter()

        for i in range(100):
            cache.get_cached_schema(f"connection_{i}")

        end_time = time.perf_counter()
        total_time = (end_time - start_time) * 1000  # Convert to milliseconds
        avg_time_per_operation = total_time / 100

        # Each operation should be well under 100ms
        assert avg_time_per_operation < 1.0  # Should be much faster than 100ms

        # Test cache storage performance
        start_time = time.perf_counter()

        for i in range(100, 200):
            mock_schema = Mock(spec=DatabaseSchema)
            cache.cache_schema(f"connection_{i}", mock_schema)

        end_time = time.perf_counter()
        total_time = (end_time - start_time) * 1000
        avg_time_per_operation = total_time / 100

        assert avg_time_per_operation < 1.0

    def test_cache_hit_rate_tracking(self):
        """Test cache hit rate calculation and tracking."""
        cache = SchemaCache()

        # Add some entries
        for i in range(10):
            mock_schema = Mock(spec=DatabaseSchema)
            cache.cache_schema(f"connection_{i}", mock_schema)

        # Simulate cache hits and misses
        hits = 0
        total_requests = 20

        for i in range(total_requests):
            connection_id = f"connection_{i % 15}"  # Mix of existing and non-existing
            result = cache.get_cached_schema(connection_id)
            if result is not None:
                hits += 1

        hit_rate = hits / total_requests

        # With our pattern, we get:
        # First 10 requests (i % 15 = 0-9): hits on existing connections
        # Next 10 requests (i % 15 = 10-14, then 0-4): 5 misses + 5 hits
        # Total: 15 hits out of 20 requests = 75% hit rate
        expected_hit_rate = 15 / 20  # 75% hit rate
        assert abs(hit_rate - expected_hit_rate) < 0.1

    def test_cache_memory_efficiency_with_large_schemas(self):
        """Test cache handles large schema objects efficiently."""
        cache = SchemaCache(max_size=10)

        # Create mock schemas with large data
        large_schemas = []
        for i in range(15):  # More than max_size to test eviction
            mock_schema = Mock(spec=DatabaseSchema)
            mock_schema.tables = {
                f"table_{j}": f"large_data_{j}" * 100 for j in range(100)
            }
            large_schemas.append(mock_schema)
            cache.cache_schema(f"connection_{i}", mock_schema)

        # Cache should maintain size limit
        assert len(cache._cache) == 10

        # Recently added schemas should be present
        for i in range(5, 15):  # Last 10 entries
            assert f"connection_{i}" in cache._cache

    def test_invalidate_nonexistent_connection_graceful_handling(self):
        """Test that invalidating non-existent connection handles gracefully."""
        cache = SchemaCache()

        # Should not raise exception
        cache.invalidate_cache("nonexistent_connection")

        # Cache should remain empty
        assert len(cache._cache) == 0

    def test_cache_entry_dataclass_structure(self):
        """Test that CacheEntry dataclass has correct structure."""
        mock_schema = Mock(spec=DatabaseSchema)
        timestamp = datetime.now()

        entry = CacheEntry(schema=mock_schema, timestamp=timestamp)

        assert entry.schema == mock_schema
        assert entry.timestamp == timestamp
        assert hasattr(entry, "schema")
        assert hasattr(entry, "timestamp")
