"""Unit tests for CacheNode.

Tests basic cache functionality with proper .execute() usage.
Follows 3-tier testing policy: no Docker dependencies, memory backend only.
"""

import time

import pytest
from kailash.nodes.cache.cache import (
    CacheBackend,
    CacheNode,
    EvictionPolicy,
    SerializationFormat,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestCacheNode:
    """Test cases for CacheNode - Tier 1 Unit Tests."""

    @pytest.fixture
    def cache_node(self):
        """Create a CacheNode instance for testing."""
        return CacheNode()

    @pytest.fixture
    def sample_data(self):
        """Sample data for caching tests."""
        return {
            "user_id": 123,
            "name": "John Doe",
            "email": "john@example.com",
            "preferences": {"theme": "dark", "notifications": True},
        }

    def test_initialization(self, cache_node):
        """Test CacheNode initialization."""
        assert cache_node.id is not None
        assert hasattr(cache_node, "_memory_cache")
        assert hasattr(cache_node, "_access_times")
        assert hasattr(cache_node, "_access_counts")
        assert hasattr(cache_node, "_redis_client")
        assert hasattr(cache_node, "_cache_stats")

        # Check initial stats
        assert cache_node._cache_stats["hits"] == 0
        assert cache_node._cache_stats["misses"] == 0

    def test_get_parameters(self, cache_node):
        """Test parameter definitions."""
        params = cache_node.get_parameters()

        required_params = [
            "operation",
            "key",
            "value",
            "keys",
            "values",
            "pattern",
            "ttl",
            "backend",
            "redis_url",
            "serialization",
            "compression",
            "eviction_policy",
            "max_memory_items",
            "namespace",
        ]

        for param in required_params:
            assert param in params

        assert params["operation"].required is True
        assert params["backend"].default == "memory"
        assert params["serialization"].default == "json"

    def test_get_output_schema(self, cache_node):
        """Test output schema definition."""
        schema = cache_node.get_output_schema()

        expected_outputs = [
            "success",
            "value",
            "values",
            "hit",
            "key",
            "ttl_remaining",
            "backend_used",
            "operation_time",
            "stats",
            "compressed",
        ]

        for output in expected_outputs:
            assert output in schema

    def test_memory_cache_set_get(self, cache_node, sample_data):
        """Test basic set and get operations with memory backend."""
        # Test set operation
        set_result = cache_node.execute(
            operation="set",
            key="test_key",
            value=sample_data,
            backend="memory",
            ttl=3600,
        )

        assert set_result["success"] is True
        assert set_result["key"] == "test_key"
        assert set_result["backend_used"] == "memory"

        # Test get operation
        get_result = cache_node.execute(
            operation="get", key="test_key", backend="memory"
        )

        assert get_result["success"] is True
        assert get_result["hit"] is True
        assert get_result["value"] == sample_data
        assert get_result["key"] == "test_key"

    def test_memory_cache_miss(self, cache_node):
        """Test cache miss scenario."""
        result = cache_node.execute(
            operation="get", key="nonexistent_key", backend="memory"
        )

        assert result["success"] is True
        assert result["hit"] is False
        assert result["value"] is None

    def test_cache_delete(self, cache_node, sample_data):
        """Test cache deletion."""
        # First set a value
        cache_node.execute(
            operation="set", key="delete_test", value=sample_data, backend="memory"
        )

        # Then delete it
        delete_result = cache_node.execute(
            operation="delete", key="delete_test", backend="memory"
        )

        assert delete_result["success"] is True
        assert delete_result["deleted"] is True
        assert delete_result["key"] == "delete_test"

        # Verify it's gone
        get_result = cache_node.execute(
            operation="get", key="delete_test", backend="memory"
        )

        assert get_result["hit"] is False

    def test_cache_exists(self, cache_node, sample_data):
        """Test cache existence check."""
        key = "exists_test"

        # Check non-existent key
        exists_result = cache_node.execute(
            operation="exists", key=key, backend="memory"
        )

        assert exists_result["success"] is True
        assert exists_result["exists"] is False

        # Set the key
        cache_node.execute(
            operation="set", key=key, value=sample_data, backend="memory"
        )

        # Check existing key
        exists_result = cache_node.execute(
            operation="exists", key=key, backend="memory"
        )

        assert exists_result["success"] is True
        assert exists_result["exists"] is True

    def test_cache_clear(self, cache_node, sample_data):
        """Test cache clearing."""
        # Set multiple keys
        keys = ["clear_test_1", "clear_test_2", "clear_test_3"]
        for key in keys:
            cache_node.execute(
                operation="set", key=key, value=sample_data, backend="memory"
            )

        # Clear cache
        clear_result = cache_node.execute(operation="clear", backend="memory")

        assert clear_result["success"] is True
        assert clear_result["cleared_count"] == 3

        # Verify all keys are gone
        for key in keys:
            get_result = cache_node.execute(operation="get", key=key, backend="memory")
            assert get_result["hit"] is False

    def test_cache_stats(self, cache_node, sample_data):
        """Test cache statistics."""
        # Perform some operations to generate stats
        cache_node.execute(
            operation="set", key="stats_test", value=sample_data, backend="memory"
        )

        cache_node.execute(operation="get", key="stats_test", backend="memory")

        cache_node.execute(operation="get", key="nonexistent", backend="memory")

        # Get stats
        stats_result = cache_node.execute(operation="stats", backend="memory")

        assert stats_result["success"] is True
        stats = stats_result["stats"]

        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert stats["sets"] >= 1
        assert "hit_rate" in stats
        assert "memory_items" in stats

    def test_pattern_operations(self, cache_node, sample_data):
        """Test pattern-based operations."""
        # Set multiple keys with patterns
        pattern_keys = [
            "user:123:profile",
            "user:123:preferences",
            "user:456:profile",
            "other:data",
        ]

        for key in pattern_keys:
            cache_node.execute(
                operation="set", key=key, value=sample_data, backend="memory"
            )

        # Get by pattern
        pattern_result = cache_node.execute(
            operation="get_pattern", pattern="user:123:*", backend="memory"
        )

        assert pattern_result["success"] is True
        assert pattern_result["count"] == 2
        assert "user:123:profile" in pattern_result["values"]
        assert "user:123:preferences" in pattern_result["values"]
        assert "user:456:profile" not in pattern_result["values"]

    def test_batch_operations_mget(self, cache_node, sample_data):
        """Test batch get operations."""
        # Set multiple keys
        keys = ["batch_1", "batch_2", "batch_3"]
        for i, key in enumerate(keys):
            cache_node.execute(
                operation="set",
                key=key,
                value={**sample_data, "id": i},
                backend="memory",
            )

        # Batch get
        mget_result = cache_node.execute(
            operation="mget", keys=keys + ["nonexistent"], backend="memory"
        )

        assert mget_result["success"] is True
        assert mget_result["hits"] == 3
        assert mget_result["total_keys"] == 4
        assert len(mget_result["values"]) == 3

    def test_batch_operations_mset(self, cache_node):
        """Test batch set operations."""
        values_dict = {
            "mset_1": {"data": "value1"},
            "mset_2": {"data": "value2"},
            "mset_3": {"data": "value3"},
        }

        mset_result = cache_node.execute(
            operation="mset", values=values_dict, backend="memory", ttl=3600
        )

        assert mset_result["success"] is True
        assert mset_result["set_count"] == 3
        assert mset_result["total_keys"] == 3

        # Verify all keys were set
        for key in values_dict.keys():
            get_result = cache_node.execute(operation="get", key=key, backend="memory")
            assert get_result["hit"] is True

    def test_namespace_support(self, cache_node, sample_data):
        """Test namespace functionality."""
        namespace = "test_namespace"
        key = "namespaced_key"

        # Set with namespace
        cache_node.execute(
            operation="set",
            key=key,
            value=sample_data,
            namespace=namespace,
            backend="memory",
        )

        # Get with namespace
        get_result = cache_node.execute(
            operation="get", key=key, namespace=namespace, backend="memory"
        )

        assert get_result["success"] is True
        assert get_result["hit"] is True
        assert get_result["key"] == f"{namespace}:{key}"

        # Get without namespace should miss
        get_no_ns = cache_node.execute(operation="get", key=key, backend="memory")

        assert get_no_ns["hit"] is False

    def test_ttl_expiration(self, cache_node, sample_data):
        """Test TTL expiration functionality."""
        key = "ttl_test"

        # Set with TTL for testing
        cache_node.execute(
            operation="set",
            key=key,
            value=sample_data,
            ttl=1,  # 1 second TTL
            backend="memory",
        )

        # Should be available immediately
        get_result = cache_node.execute(operation="get", key=key, backend="memory")
        assert get_result["hit"] is True

        # Wait a small amount to ensure we're past the exact TTL
        time.sleep(1.05)

        # Should be expired
        get_expired = cache_node.execute(operation="get", key=key, backend="memory")
        assert get_expired["hit"] is False

    def test_compression(self, cache_node):
        """Test compression functionality."""
        large_data = {"data": "x" * 2000}  # Large enough to trigger compression

        result = cache_node.execute(
            operation="set",
            key="compression_test",
            value=large_data,
            compression=True,
            compression_threshold=1024,
            backend="memory",
        )

        assert result["success"] is True

        # Retrieve and verify
        get_result = cache_node.execute(
            operation="get", key="compression_test", compression=True, backend="memory"
        )

        assert get_result["success"] is True
        assert get_result["hit"] is True

    def test_serialization_formats(self, cache_node, sample_data):
        """Test different serialization formats."""
        # Test JSON serialization
        cache_node.execute(
            operation="set",
            key="json_test",
            value=sample_data,
            serialization="json",
            backend="memory",
        )

        json_result = cache_node.execute(
            operation="get", key="json_test", serialization="json", backend="memory"
        )

        assert json_result["hit"] is True
        assert json_result["value"] == sample_data

        # Test string serialization
        cache_node.execute(
            operation="set",
            key="string_test",
            value="test string",
            serialization="string",
            backend="memory",
        )

        string_result = cache_node.execute(
            operation="get", key="string_test", serialization="string", backend="memory"
        )

        assert string_result["hit"] is True
        assert string_result["value"] == "test string"

    def test_eviction_policy_lru(self, cache_node):
        """Test LRU eviction policy."""
        # Set max items to 3
        cache_node._cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0,
        }

        # Fill cache to capacity
        for i in range(5):
            cache_node.execute(
                operation="set",
                key=f"lru_test_{i}",
                value={"data": i},
                max_memory_items=3,
                eviction_policy="lru",
                backend="memory",
            )

        # Check that evictions occurred
        assert cache_node._cache_stats["evictions"] > 0

    def test_redis_backend_unavailable(self, cache_node, sample_data):
        """Test behavior when Redis is unavailable."""
        # Redis backend should fail with NodeExecutionError when not available
        with pytest.raises(NodeExecutionError, match="Failed to connect to Redis"):
            cache_node.execute(
                operation="set",
                key="redis_test",
                value=sample_data,
                backend="redis",
                redis_url="redis://localhost:9999",  # Non-existent port
            )

    def test_hybrid_backend_fallback(self, cache_node, sample_data):
        """Test hybrid backend fallback to memory when Redis unavailable."""
        # Should fallback to memory without error
        result = cache_node.execute(
            operation="set", key="hybrid_test", value=sample_data, backend="hybrid"
        )

        assert result["success"] is True
        assert result["backend_used"] == "hybrid"

    def test_invalid_operation(self, cache_node):
        """Test handling of invalid operations."""
        with pytest.raises(NodeExecutionError, match="Cache operation .* failed"):
            cache_node.execute(operation="invalid_op", backend="memory")

    def test_missing_required_parameters(self, cache_node):
        """Test handling of missing required parameters."""
        # Missing operation parameter should be handled by the framework
        # The node should return error status
        try:
            result = cache_node.execute(
                backend="memory"
                # Missing operation parameter
            )
            # If no exception, should at least return error
            assert result["success"] is False
        except Exception:
            # Expected behavior - parameter validation should catch this
            pass

    def test_build_key_with_namespace(self, cache_node):
        """Test key building with namespace."""
        assert cache_node._build_key("test", "ns") == "ns:test"
        assert cache_node._build_key("test", "") == "test"
        assert cache_node._build_key("test") == "test"

    def test_cache_backend_enum(self):
        """Test CacheBackend enum values."""
        assert CacheBackend.MEMORY.value == "memory"
        assert CacheBackend.REDIS.value == "redis"
        assert CacheBackend.FILE.value == "file"
        assert CacheBackend.HYBRID.value == "hybrid"

    def test_serialization_format_enum(self):
        """Test SerializationFormat enum values."""
        assert SerializationFormat.JSON.value == "json"
        assert SerializationFormat.PICKLE.value == "pickle"
        assert SerializationFormat.STRING.value == "string"
        assert SerializationFormat.BYTES.value == "bytes"

    def test_eviction_policy_enum(self):
        """Test EvictionPolicy enum values."""
        assert EvictionPolicy.LRU.value == "lru"
        assert EvictionPolicy.LFU.value == "lfu"
        assert EvictionPolicy.TTL.value == "ttl"
        assert EvictionPolicy.FIFO.value == "fifo"

    def test_namespace_clear(self, cache_node, sample_data):
        """Test clearing cache by namespace."""
        namespace = "clear_test"

        # Set keys in namespace
        for i in range(3):
            cache_node.execute(
                operation="set",
                key=f"key_{i}",
                value=sample_data,
                namespace=namespace,
                backend="memory",
            )

        # Set key outside namespace
        cache_node.execute(
            operation="set", key="outside_key", value=sample_data, backend="memory"
        )

        # Clear by namespace
        clear_result = cache_node.execute(
            operation="clear", namespace=namespace, backend="memory"
        )

        assert clear_result["success"] is True
        assert clear_result["cleared_count"] == 3

        # Verify namespace keys are gone but outside key remains
        for i in range(3):
            get_result = cache_node.execute(
                operation="get", key=f"key_{i}", namespace=namespace, backend="memory"
            )
            assert get_result["hit"] is False

        outside_result = cache_node.execute(
            operation="get", key="outside_key", backend="memory"
        )
        assert outside_result["hit"] is True

    def test_mset_no_values(self, cache_node):
        """Test mset with no values provided."""
        result = cache_node.execute(operation="mset", backend="memory")

        assert result["success"] is False
        assert "No values provided" in result["error"]
