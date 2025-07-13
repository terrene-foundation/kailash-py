"""Comprehensive functional tests for nodes/cache/cache.py to boost coverage."""

import asyncio
import hashlib
import json
import pickle
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
import redis


class TestCacheNodeInitialization:
    """Test CacheNode initialization and configuration."""

    def test_cache_node_basic_initialization(self):
        """Test basic CacheNode initialization with defaults."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode()

            # Verify default settings
            assert node.cache_type == "memory"  # Default
            assert node.ttl == 3600  # Default 1 hour
            assert node.max_size == 1000  # Default
            assert node.eviction_policy == "lru"  # Default
            assert hasattr(node, "_cache")
            assert hasattr(node, "_access_times")
            assert hasattr(node, "_access_counts")
            assert hasattr(node, "_lock")

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_cache_node_with_configuration(self):
        """Test CacheNode initialization with custom configuration."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(
                cache_type="redis",
                ttl=7200,
                max_size=5000,
                eviction_policy="lfu",
                redis_host="localhost",
                redis_port=6380,
                redis_db=1,
                enable_compression=True,
                compression_threshold=1024,
            )

            assert node.cache_type == "redis"
            assert node.ttl == 7200
            assert node.max_size == 5000
            assert node.eviction_policy == "lfu"
            assert node.redis_host == "localhost"
            assert node.redis_port == 6380
            assert node.redis_db == 1
            assert node.enable_compression is True
            assert node.compression_threshold == 1024

        except ImportError:
            pytest.skip("CacheNode not available")

    @patch("redis.Redis")
    def test_redis_cache_initialization(self, mock_redis_class):
        """Test Redis cache initialization."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            mock_redis = Mock()
            mock_redis_class.return_value = mock_redis

            node = CacheNode(
                cache_type="redis",
                redis_host="redis.example.com",
                redis_port=6379,
                redis_password="secret",
                redis_db=0,
            )

            # Verify Redis client was created
            mock_redis_class.assert_called_once_with(
                host="redis.example.com",
                port=6379,
                password="secret",
                db=0,
                decode_responses=True,
            )

            assert node._redis_client == mock_redis

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCacheNodeOperations:
    """Test CacheNode CRUD operations."""

    def test_memory_cache_set_and_get(self):
        """Test memory cache set and get operations."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Test set
            result = node.execute(
                action="set", key="test_key", value={"data": "test_value", "number": 42}
            )

            assert result["success"] is True
            assert result["key"] == "test_key"

            # Test get
            result = node.execute(action="get", key="test_key")

            assert result["success"] is True
            assert result["value"]["data"] == "test_value"
            assert result["value"]["number"] == 42
            assert result["hit"] is True

            # Test get non-existent key
            result = node.execute(action="get", key="non_existent")

            assert result["success"] is True
            assert result["value"] is None
            assert result["hit"] is False

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory", ttl=1)  # 1 second TTL

            # Set value
            node.execute(action="set", key="expire_test", value="will_expire")

            # Get immediately - should exist
            result = node.execute(action="get", key="expire_test")
            assert result["hit"] is True
            assert result["value"] == "will_expire"

            # Wait for expiration
            time.sleep(1.1)

            # Get after expiration - should not exist
            result = node.execute(action="get", key="expire_test")
            assert result["hit"] is False
            assert result["value"] is None

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_cache_delete_operation(self):
        """Test cache delete operation."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Set value
            node.execute(action="set", key="delete_test", value="to_delete")

            # Verify it exists
            result = node.execute(action="get", key="delete_test")
            assert result["hit"] is True

            # Delete
            result = node.execute(action="delete", key="delete_test")
            assert result["success"] is True
            assert result["deleted"] is True

            # Verify it's gone
            result = node.execute(action="get", key="delete_test")
            assert result["hit"] is False

            # Delete non-existent key
            result = node.execute(action="delete", key="never_existed")
            assert result["success"] is True
            assert result["deleted"] is False

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_cache_clear_operation(self):
        """Test cache clear operation."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Set multiple values
            for i in range(5):
                node.execute(action="set", key=f"key_{i}", value=f"value_{i}")

            # Verify they exist
            result = node.execute(action="get", key="key_0")
            assert result["hit"] is True

            # Clear cache
            result = node.execute(action="clear")
            assert result["success"] is True
            assert result["cleared"] is True

            # Verify all are gone
            for i in range(5):
                result = node.execute(action="get", key=f"key_{i}")
                assert result["hit"] is False

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCacheEvictionPolicies:
    """Test cache eviction policies."""

    def test_lru_eviction_policy(self):
        """Test LRU (Least Recently Used) eviction."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory", max_size=3, eviction_policy="lru")

            # Fill cache to capacity
            node.execute(action="set", key="key1", value="value1")
            node.execute(action="set", key="key2", value="value2")
            node.execute(action="set", key="key3", value="value3")

            # Access key1 and key2 to make them recently used
            node.execute(action="get", key="key1")
            node.execute(action="get", key="key2")

            # Add new key - should evict key3 (least recently used)
            node.execute(action="set", key="key4", value="value4")

            # Verify key3 was evicted
            result = node.execute(action="get", key="key3")
            assert result["hit"] is False

            # Verify others still exist
            assert node.execute(action="get", key="key1")["hit"] is True
            assert node.execute(action="get", key="key2")["hit"] is True
            assert node.execute(action="get", key="key4")["hit"] is True

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_lfu_eviction_policy(self):
        """Test LFU (Least Frequently Used) eviction."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory", max_size=3, eviction_policy="lfu")

            # Fill cache
            node.execute(action="set", key="key1", value="value1")
            node.execute(action="set", key="key2", value="value2")
            node.execute(action="set", key="key3", value="value3")

            # Access key1 and key2 multiple times
            for _ in range(3):
                node.execute(action="get", key="key1")
                node.execute(action="get", key="key2")

            # Access key3 only once
            node.execute(action="get", key="key3")

            # Add new key - should evict key3 (least frequently used)
            node.execute(action="set", key="key4", value="value4")

            # Verify key3 was evicted
            result = node.execute(action="get", key="key3")
            assert result["hit"] is False

            # Verify frequently used keys remain
            assert node.execute(action="get", key="key1")["hit"] is True
            assert node.execute(action="get", key="key2")["hit"] is True

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_fifo_eviction_policy(self):
        """Test FIFO (First In First Out) eviction."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory", max_size=3, eviction_policy="fifo")

            # Fill cache in order
            node.execute(action="set", key="first", value="value1")
            node.execute(action="set", key="second", value="value2")
            node.execute(action="set", key="third", value="value3")

            # Add new key - should evict "first" (oldest)
            node.execute(action="set", key="fourth", value="value4")

            # Verify first was evicted
            result = node.execute(action="get", key="first")
            assert result["hit"] is False

            # Verify others remain
            assert node.execute(action="get", key="second")["hit"] is True
            assert node.execute(action="get", key="third")["hit"] is True
            assert node.execute(action="get", key="fourth")["hit"] is True

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCacheCompression:
    """Test cache compression functionality."""

    def test_compression_for_large_values(self):
        """Test automatic compression for large values."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(
                cache_type="memory",
                enable_compression=True,
                compression_threshold=100,  # Low threshold for testing
            )

            # Create large value
            large_value = {"data": "x" * 1000, "array": list(range(100))}

            # Set large value
            result = node.execute(action="set", key="large_key", value=large_value)

            assert result["success"] is True
            assert result.get("compressed", False) is True

            # Get compressed value
            result = node.execute(action="get", key="large_key")

            assert result["success"] is True
            assert result["value"] == large_value  # Should decompress automatically

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_no_compression_for_small_values(self):
        """Test no compression for small values."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(
                cache_type="memory", enable_compression=True, compression_threshold=1000
            )

            # Small value
            small_value = {"data": "small"}

            # Set small value
            result = node.execute(action="set", key="small_key", value=small_value)

            assert result["success"] is True
            assert result.get("compressed", False) is False

        except ImportError:
            pytest.skip("CacheNode not available")


class TestRedisCache:
    """Test Redis cache functionality."""

    @patch("redis.Redis")
    def test_redis_set_and_get(self, mock_redis_class):
        """Test Redis cache set and get operations."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            mock_redis = Mock()
            mock_redis_class.return_value = mock_redis

            # Mock Redis responses
            mock_redis.setex.return_value = True
            mock_redis.get.return_value = '{"data": "redis_value"}'
            mock_redis.ttl.return_value = 3500

            node = CacheNode(cache_type="redis", ttl=3600)

            # Test set
            result = node.execute(
                action="set", key="redis_key", value={"data": "redis_value"}
            )

            assert result["success"] is True

            # Verify Redis setex was called
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == "redis_key"
            assert call_args[0][1] == 3600  # TTL
            assert "redis_value" in call_args[0][2]

            # Test get
            result = node.execute(action="get", key="redis_key")

            assert result["success"] is True
            assert result["value"]["data"] == "redis_value"
            assert result["ttl"] == 3500

            mock_redis.get.assert_called_once_with("redis_key")

        except ImportError:
            pytest.skip("CacheNode not available")

    @patch("redis.Redis")
    def test_redis_delete_and_clear(self, mock_redis_class):
        """Test Redis delete and clear operations."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            mock_redis = Mock()
            mock_redis_class.return_value = mock_redis

            mock_redis.delete.return_value = 1
            mock_redis.flushdb.return_value = True

            node = CacheNode(cache_type="redis")

            # Test delete
            result = node.execute(action="delete", key="redis_key")
            assert result["success"] is True
            assert result["deleted"] is True

            mock_redis.delete.assert_called_once_with("redis_key")

            # Test clear
            result = node.execute(action="clear")
            assert result["success"] is True

            mock_redis.flushdb.assert_called_once()

        except ImportError:
            pytest.skip("CacheNode not available")

    @patch("redis.Redis")
    def test_redis_connection_error_handling(self, mock_redis_class):
        """Test Redis connection error handling."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            mock_redis = Mock()
            mock_redis_class.return_value = mock_redis

            # Mock connection error
            mock_redis.get.side_effect = redis.ConnectionError("Connection failed")

            node = CacheNode(cache_type="redis")

            # Should handle error gracefully
            result = node.execute(action="get", key="error_key")

            assert result["success"] is False
            assert "error" in result
            assert "Connection failed" in result["error"]

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCacheStatistics:
    """Test cache statistics and monitoring."""

    def test_cache_hit_miss_statistics(self):
        """Test cache hit/miss statistics tracking."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Generate some hits and misses
            node.execute(action="set", key="stat_key", value="stat_value")

            # Hits
            for _ in range(3):
                node.execute(action="get", key="stat_key")

            # Misses
            for _ in range(2):
                node.execute(action="get", key="missing_key")

            # Get statistics
            result = node.execute(action="stats")

            assert result["success"] is True
            stats = result["statistics"]

            assert stats["hits"] == 3
            assert stats["misses"] == 2
            assert stats["hit_rate"] == 0.6  # 3/5
            assert stats["total_requests"] == 5
            assert stats["cache_size"] == 1

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_cache_size_monitoring(self):
        """Test cache size monitoring."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory", max_size=10)

            # Add items
            for i in range(5):
                node.execute(action="set", key=f"size_key_{i}", value=f"value_{i}")

            # Check size
            result = node.execute(action="size")

            assert result["success"] is True
            assert result["size"] == 5
            assert result["max_size"] == 10
            assert result["usage_percent"] == 50.0

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCacheConcurrency:
    """Test cache concurrency handling."""

    def test_thread_safe_operations(self):
        """Test thread-safe cache operations."""
        try:
            import threading

            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")
            results = []

            def cache_operation(thread_id):
                for i in range(10):
                    # Set
                    node.execute(
                        action="set",
                        key=f"thread_{thread_id}_key_{i}",
                        value=f"thread_{thread_id}_value_{i}",
                    )

                    # Get
                    result = node.execute(
                        action="get", key=f"thread_{thread_id}_key_{i}"
                    )

                    results.append(result["hit"])

            # Run multiple threads
            threads = []
            for i in range(5):
                thread = threading.Thread(target=cache_operation, args=(i,))
                threads.append(thread)
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join()

            # All operations should succeed
            assert all(results)
            assert len(results) == 50  # 5 threads * 10 operations

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCachePatternOperations:
    """Test cache pattern-based operations."""

    def test_get_multiple_keys(self):
        """Test getting multiple keys at once."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Set multiple keys
            keys = ["multi_1", "multi_2", "multi_3"]
            for i, key in enumerate(keys):
                node.execute(action="set", key=key, value=f"value_{i}")

            # Get multiple
            result = node.execute(action="mget", keys=keys)

            assert result["success"] is True
            assert len(result["values"]) == 3
            assert result["values"]["multi_1"] == "value_0"
            assert result["values"]["multi_2"] == "value_1"
            assert result["values"]["multi_3"] == "value_2"

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_set_multiple_keys(self):
        """Test setting multiple keys at once."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Set multiple
            items = {
                "batch_1": "value_1",
                "batch_2": {"nested": "value_2"},
                "batch_3": [1, 2, 3],
            }

            result = node.execute(action="mset", items=items)

            assert result["success"] is True
            assert result["set_count"] == 3

            # Verify all were set
            for key, expected_value in items.items():
                get_result = node.execute(action="get", key=key)
                assert get_result["value"] == expected_value

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_key_pattern_matching(self):
        """Test finding keys by pattern."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Set keys with patterns
            node.execute(action="set", key="user:1:name", value="Alice")
            node.execute(action="set", key="user:1:email", value="alice@example.com")
            node.execute(action="set", key="user:2:name", value="Bob")
            node.execute(action="set", key="product:1:name", value="Widget")

            # Find user keys
            result = node.execute(action="keys", pattern="user:*")

            assert result["success"] is True
            assert len(result["keys"]) == 3
            assert "user:1:name" in result["keys"]
            assert "user:1:email" in result["keys"]
            assert "user:2:name" in result["keys"]
            assert "product:1:name" not in result["keys"]

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCacheTagging:
    """Test cache tagging functionality."""

    def test_set_with_tags(self):
        """Test setting cache entries with tags."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Set with tags
            result = node.execute(
                action="set",
                key="tagged_item",
                value={"data": "tagged_value"},
                tags=["user_data", "premium", "v2"],
            )

            assert result["success"] is True

            # Get by tag
            result = node.execute(action="get_by_tag", tag="user_data")

            assert result["success"] is True
            assert len(result["keys"]) == 1
            assert "tagged_item" in result["keys"]

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_invalidate_by_tag(self):
        """Test invalidating cache entries by tag."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Set multiple items with tags
            node.execute(action="set", key="tag_1", value="value1", tags=["group1"])
            node.execute(
                action="set", key="tag_2", value="value2", tags=["group1", "group2"]
            )
            node.execute(action="set", key="tag_3", value="value3", tags=["group2"])

            # Invalidate by tag
            result = node.execute(action="invalidate_tag", tag="group1")

            assert result["success"] is True
            assert result["invalidated_count"] == 2

            # Verify invalidation
            assert node.execute(action="get", key="tag_1")["hit"] is False
            assert node.execute(action="get", key="tag_2")["hit"] is False
            assert (
                node.execute(action="get", key="tag_3")["hit"] is True
            )  # Not tagged with group1

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCacheWarmup:
    """Test cache warmup functionality."""

    def test_cache_warmup_from_data(self):
        """Test warming up cache from provided data."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Warmup data
            warmup_data = {
                "warm_1": {"value": "data1", "ttl": 3600},
                "warm_2": {"value": "data2", "ttl": 7200},
                "warm_3": {"value": {"nested": "data3"}, "ttl": 1800},
            }

            result = node.execute(action="warmup", data=warmup_data)

            assert result["success"] is True
            assert result["warmed_up_count"] == 3

            # Verify all data was loaded
            for key in warmup_data:
                get_result = node.execute(action="get", key=key)
                assert get_result["hit"] is True

        except ImportError:
            pytest.skip("CacheNode not available")

    @patch("requests.get")
    def test_cache_warmup_from_url(self, mock_get):
        """Test warming up cache from URL."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Mock warmup data from URL
            mock_response = Mock()
            mock_response.json.return_value = {
                "cache_data": {"api_1": "response1", "api_2": "response2"}
            }
            mock_get.return_value = mock_response

            result = node.execute(
                action="warmup_from_url", url="https://api.example.com/cache-warmup"
            )

            assert result["success"] is True
            assert result["warmed_up_count"] == 2

            mock_get.assert_called_once_with("https://api.example.com/cache-warmup")

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCacheSerialization:
    """Test cache serialization options."""

    def test_json_serialization(self):
        """Test JSON serialization for cache values."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory", serialization="json")

            # Complex object
            complex_value = {
                "string": "text",
                "number": 42,
                "float": 3.14,
                "bool": True,
                "null": None,
                "array": [1, 2, 3],
                "nested": {"key": "value"},
            }

            # Set and get
            node.execute(action="set", key="json_test", value=complex_value)
            result = node.execute(action="get", key="json_test")

            assert result["value"] == complex_value

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_pickle_serialization(self):
        """Test pickle serialization for cache values."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory", serialization="pickle")

            # Object that JSON can't serialize
            class CustomObject:
                def __init__(self, value):
                    self.value = value

                def __eq__(self, other):
                    return self.value == other.value

            custom_obj = CustomObject("test")

            # Set and get
            node.execute(action="set", key="pickle_test", value=custom_obj)
            result = node.execute(action="get", key="pickle_test")

            assert isinstance(result["value"], CustomObject)
            assert result["value"].value == "test"

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCacheInvalidation:
    """Test cache invalidation strategies."""

    def test_time_based_invalidation(self):
        """Test time-based cache invalidation."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Set with specific TTL
            node.execute(
                action="set", key="timed_key", value="timed_value", ttl=2  # 2 seconds
            )

            # Should exist immediately
            assert node.execute(action="get", key="timed_key")["hit"] is True

            # Wait for expiration
            time.sleep(2.1)

            # Should be expired
            assert node.execute(action="get", key="timed_key")["hit"] is False

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_dependency_based_invalidation(self):
        """Test dependency-based cache invalidation."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Set parent and dependent entries
            node.execute(action="set", key="parent_key", value="parent_value")
            node.execute(
                action="set",
                key="child_key",
                value="child_value",
                dependencies=["parent_key"],
            )

            # Both should exist
            assert node.execute(action="get", key="parent_key")["hit"] is True
            assert node.execute(action="get", key="child_key")["hit"] is True

            # Invalidate parent
            node.execute(action="delete", key="parent_key")

            # Child should also be invalidated
            assert node.execute(action="get", key="parent_key")["hit"] is False
            assert node.execute(action="get", key="child_key")["hit"] is False

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCachePerformance:
    """Test cache performance features."""

    def test_cache_benchmarking(self):
        """Test cache operation benchmarking."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory", enable_benchmarking=True)

            # Perform operations
            for i in range(100):
                node.execute(action="set", key=f"bench_{i}", value=f"value_{i}")
                node.execute(action="get", key=f"bench_{i}")

            # Get benchmark results
            result = node.execute(action="benchmark")

            assert result["success"] is True
            bench = result["benchmark"]

            assert "avg_set_time_ms" in bench
            assert "avg_get_time_ms" in bench
            assert "total_operations" in bench
            assert bench["total_operations"] == 200

            # Performance should be reasonable
            assert bench["avg_get_time_ms"] < 10  # Should be very fast for memory cache
            assert bench["avg_set_time_ms"] < 10

        except ImportError:
            pytest.skip("CacheNode not available")


class TestCacheErrorHandling:
    """Test cache error handling."""

    def test_invalid_action_handling(self):
        """Test handling of invalid cache actions."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Invalid action
            result = node.execute(action="invalid_action", key="test")

            assert result["success"] is False
            assert "error" in result
            assert "Invalid action" in result["error"]

        except ImportError:
            pytest.skip("CacheNode not available")

    def test_missing_required_parameters(self):
        """Test handling of missing required parameters."""
        try:
            from kailash.nodes.cache.cache import CacheNode

            node = CacheNode(cache_type="memory")

            # Set without key
            result = node.execute(action="set", value="test")

            assert result["success"] is False
            assert "error" in result
            assert "key" in result["error"].lower()

            # Get without key
            result = node.execute(action="get")

            assert result["success"] is False
            assert "error" in result

        except ImportError:
            pytest.skip("CacheNode not available")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
