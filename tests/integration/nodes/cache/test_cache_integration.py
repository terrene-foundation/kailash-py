"""Integration tests for CacheNode using real Redis.

Tests cache functionality with real Redis backend and component interactions.
Follows 3-tier testing policy: uses real Docker services, no mocking.
"""

import json
import time
from datetime import UTC, datetime

import pytest
from kailash.nodes.cache.cache import CacheNode
from kailash.sdk_exceptions import NodeExecutionError

# Mark all tests in this file as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestCacheNodeIntegration:
    """Integration tests for CacheNode with Redis backend."""

    @pytest.fixture(scope="class")
    def redis_cache_node(self):
        """Create a CacheNode instance for Redis testing."""
        return CacheNode()

    @pytest.fixture
    def large_test_data(self):
        """Large test data for compression and performance testing."""
        return {
            "user_data": {
                "user_id": 12345,
                "profile": {
                    "name": "Integration Test User",
                    "email": "test@integration.com",
                    "preferences": {
                        "theme": "dark",
                        "notifications": True,
                        "language": "en",
                        "timezone": "UTC",
                    },
                    "metadata": {
                        "created_at": datetime.now(UTC).isoformat(),
                        "last_login": datetime.now(UTC).isoformat(),
                        "permissions": ["read", "write", "admin"],
                        "features": ["feature_a", "feature_b", "feature_c"],
                        "large_text": "Lorem ipsum " * 500,  # Create large text
                    },
                },
            }
        }

    def test_redis_connection_and_basic_operations(
        self, redis_cache_node, large_test_data
    ):
        """Test Redis connection and basic cache operations."""
        # Test set operation with Redis
        result = redis_cache_node.execute(
            operation="set",
            key="integration_test:basic",
            value=large_test_data,
            backend="redis",
            redis_url="redis://localhost:6380",
            ttl=300,  # 5 minutes
            serialization="json",
        )

        assert result["success"] is True
        assert result["key"] == "integration_test:basic"
        assert result["backend_used"] == "redis"
        assert result["operation_time"] > 0

        # Test get operation
        get_result = redis_cache_node.execute(
            operation="get",
            key="integration_test:basic",
            backend="redis",
            redis_url="redis://localhost:6380",
            serialization="json",
        )

        assert get_result["success"] is True
        assert get_result["hit"] is True
        assert get_result["value"] == large_test_data
        assert get_result["backend_used"] == "redis"

    def test_redis_ttl_and_expiration(self, redis_cache_node):
        """Test TTL functionality with real Redis."""
        test_data = {"test": "ttl_data", "timestamp": time.time()}

        # Set with short TTL
        redis_cache_node.execute(
            operation="set",
            key="integration_test:ttl",
            value=test_data,
            backend="redis",
            redis_url="redis://localhost:6380",
            ttl=1,  # 1 second
        )

        # Should be available immediately
        result = redis_cache_node.execute(
            operation="get",
            key="integration_test:ttl",
            backend="redis",
            redis_url="redis://localhost:6380",
        )
        assert result["hit"] is True

        # Wait for expiration (longer than TTL)
        time.sleep(1.1)

        # Should be expired
        expired_result = redis_cache_node.execute(
            operation="get",
            key="integration_test:ttl",
            backend="redis",
            redis_url="redis://localhost:6380",
        )
        assert expired_result["hit"] is False

    def test_redis_compression_with_large_data(self, redis_cache_node, large_test_data):
        """Test compression functionality with Redis backend."""
        # Add more data to ensure compression is worthwhile
        large_data = {
            **large_test_data,
            "large_array": list(range(1000)),
            "repeated_text": "This is repeated text. " * 100,
        }

        # Set with compression
        result = redis_cache_node.execute(
            operation="set",
            key="integration_test:compressed",
            value=large_data,
            backend="redis",
            redis_url="redis://localhost:6380",
            compression=True,
            compression_threshold=1024,
            serialization="json",
        )

        assert result["success"] is True

        # Retrieve and verify decompression
        get_result = redis_cache_node.execute(
            operation="get",
            key="integration_test:compressed",
            backend="redis",
            redis_url="redis://localhost:6380",
            compression=True,
            serialization="json",
        )

        assert get_result["success"] is True
        assert get_result["hit"] is True
        assert get_result["value"] == large_data

    def test_redis_batch_operations(self, redis_cache_node):
        """Test batch operations with Redis."""
        # Prepare batch data
        batch_data = {}
        for i in range(10):
            batch_data[f"batch_key_{i}"] = {
                "id": i,
                "data": f"batch_value_{i}",
                "timestamp": time.time(),
            }

        # Batch set
        mset_result = redis_cache_node.execute(
            operation="mset",
            values=batch_data,
            backend="redis",
            redis_url="redis://localhost:6380",
            ttl=300,
            namespace="integration_test",
        )

        assert mset_result["success"] is True
        assert mset_result["set_count"] == 10

        # Batch get
        keys_to_get = [f"integration_test:batch_key_{i}" for i in range(10)]
        mget_result = redis_cache_node.execute(
            operation="mget",
            keys=keys_to_get,
            backend="redis",
            redis_url="redis://localhost:6380",
        )

        assert mget_result["success"] is True
        assert mget_result["hits"] == 10
        assert mget_result["total_keys"] == 10
        assert len(mget_result["values"]) == 10

    def test_redis_pattern_operations(self, redis_cache_node):
        """Test pattern-based operations with Redis."""
        # Set multiple keys with pattern
        pattern_keys = [
            "user:123:profile",
            "user:123:preferences",
            "user:456:profile",
            "session:abc123",
            "session:def456",
        ]

        for key in pattern_keys:
            redis_cache_node.execute(
                operation="set",
                key=key,
                value={"key": key, "data": "test_data"},
                backend="redis",
                redis_url="redis://localhost:6380",
                namespace="integration_test",
            )

        # Get by pattern
        pattern_result = redis_cache_node.execute(
            operation="get_pattern",
            pattern="integration_test:user:123:*",
            backend="redis",
            redis_url="redis://localhost:6380",
        )

        assert pattern_result["success"] is True
        assert pattern_result["count"] == 2

        # Verify the right keys were found
        found_keys = list(pattern_result["values"].keys())
        assert "integration_test:user:123:profile" in found_keys
        assert "integration_test:user:123:preferences" in found_keys

    def test_hybrid_backend_redis_fallback(self, redis_cache_node, large_test_data):
        """Test hybrid backend with Redis as primary."""
        # Test hybrid operation
        result = redis_cache_node.execute(
            operation="set",
            key="hybrid_test",
            value=large_test_data,
            backend="hybrid",
            redis_url="redis://localhost:6380",
            serialization="json",
        )

        assert result["success"] is True
        assert result["backend_used"] == "hybrid"

        # Retrieve from hybrid
        get_result = redis_cache_node.execute(
            operation="get",
            key="hybrid_test",
            backend="hybrid",
            redis_url="redis://localhost:6380",
            serialization="json",
        )

        assert get_result["success"] is True
        assert get_result["hit"] is True
        assert get_result["value"] == large_test_data

    def test_redis_serialization_formats(self, redis_cache_node):
        """Test different serialization formats with Redis."""
        test_data = {
            "string_test": "Hello, Redis!",
            "number_test": 12345,
            "boolean_test": True,
            "array_test": [1, 2, 3, 4, 5],
            "nested_test": {"inner": {"value": "nested"}},
        }

        # Test JSON serialization
        redis_cache_node.execute(
            operation="set",
            key="serialization_json",
            value=test_data,
            backend="redis",
            redis_url="redis://localhost:6380",
            serialization="json",
        )

        json_result = redis_cache_node.execute(
            operation="get",
            key="serialization_json",
            backend="redis",
            redis_url="redis://localhost:6380",
            serialization="json",
        )

        assert json_result["hit"] is True
        assert json_result["value"] == test_data

        # Test pickle serialization
        redis_cache_node.execute(
            operation="set",
            key="serialization_pickle",
            value=test_data,
            backend="redis",
            redis_url="redis://localhost:6380",
            serialization="pickle",
        )

        pickle_result = redis_cache_node.execute(
            operation="get",
            key="serialization_pickle",
            backend="redis",
            redis_url="redis://localhost:6380",
            serialization="pickle",
        )

        assert pickle_result["hit"] is True
        assert pickle_result["value"] == test_data

    def test_redis_namespace_isolation(self, redis_cache_node):
        """Test namespace isolation with Redis."""
        test_data = {"test": "namespace_isolation"}

        # Set in namespace A
        redis_cache_node.execute(
            operation="set",
            key="isolation_test",
            value=test_data,
            backend="redis",
            redis_url="redis://localhost:6380",
            namespace="ns_a",
        )

        # Set different data in namespace B
        redis_cache_node.execute(
            operation="set",
            key="isolation_test",
            value={"test": "different_data"},
            backend="redis",
            redis_url="redis://localhost:6380",
            namespace="ns_b",
        )

        # Get from namespace A
        result_a = redis_cache_node.execute(
            operation="get",
            key="isolation_test",
            backend="redis",
            redis_url="redis://localhost:6380",
            namespace="ns_a",
        )

        # Get from namespace B
        result_b = redis_cache_node.execute(
            operation="get",
            key="isolation_test",
            backend="redis",
            redis_url="redis://localhost:6380",
            namespace="ns_b",
        )

        assert result_a["hit"] is True
        assert result_b["hit"] is True
        assert result_a["value"] != result_b["value"]
        assert result_a["value"] == test_data
        assert result_b["value"] == {"test": "different_data"}

    def test_redis_performance_stats(self, redis_cache_node):
        """Test Redis performance and statistics tracking."""
        # Perform multiple operations to generate stats
        for i in range(5):
            redis_cache_node.execute(
                operation="set",
                key=f"perf_test_{i}",
                value={"id": i, "data": f"performance_test_{i}"},
                backend="redis",
                redis_url="redis://localhost:6380",
            )

        # Perform gets (some hits, some misses)
        for i in range(8):  # More gets than sets to test misses
            redis_cache_node.execute(
                operation="get",
                key=f"perf_test_{i}",
                backend="redis",
                redis_url="redis://localhost:6380",
            )

        # Get statistics
        stats_result = redis_cache_node.execute(
            operation="stats", backend="redis", redis_url="redis://localhost:6380"
        )

        assert stats_result["success"] is True
        stats = stats_result["stats"]

        assert stats["sets"] >= 5
        total_gets = stats["hits"] + stats["misses"]
        assert total_gets >= 8
        assert stats["hits"] >= 5
        assert stats["misses"] >= 3
        assert "hit_rate" in stats
        assert stats["hit_rate"] <= 1.0

    def test_redis_error_handling(self, redis_cache_node):
        """Test error handling with Redis backend."""
        # Test connection to invalid Redis URL
        with pytest.raises(NodeExecutionError, match="Failed to connect to Redis"):
            redis_cache_node.execute(
                operation="set",
                key="error_test",
                value={"test": "data"},
                backend="redis",
                redis_url="redis://invalid:9999",  # Invalid Redis URL
            )

    def test_redis_cleanup_operations(self, redis_cache_node):
        """Test cleanup operations with Redis."""
        # Set test keys
        test_keys = ["cleanup_1", "cleanup_2", "cleanup_3"]
        for key in test_keys:
            redis_cache_node.execute(
                operation="set",
                key=key,
                value={"test": f"cleanup_data_{key}"},
                backend="redis",
                redis_url="redis://localhost:6380",
                namespace="cleanup_test",
            )

        # Test delete operation
        delete_result = redis_cache_node.execute(
            operation="delete",
            key="cleanup_1",
            backend="redis",
            redis_url="redis://localhost:6380",
            namespace="cleanup_test",
        )

        assert delete_result["success"] is True
        assert delete_result["deleted"] is True

        # Verify deletion
        get_result = redis_cache_node.execute(
            operation="get",
            key="cleanup_1",
            backend="redis",
            redis_url="redis://localhost:6380",
            namespace="cleanup_test",
        )
        assert get_result["hit"] is False

        # Test clear operation for namespace
        clear_result = redis_cache_node.execute(
            operation="clear",
            backend="redis",
            redis_url="redis://localhost:6380",
            namespace="cleanup_test",
        )

        assert clear_result["success"] is True
        assert clear_result["cleared_count"] >= 2  # At least cleanup_2 and cleanup_3
