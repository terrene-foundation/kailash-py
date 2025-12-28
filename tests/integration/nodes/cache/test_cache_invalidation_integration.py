"""Integration tests for CacheInvalidationNode using real Redis.

Tests cache invalidation functionality with real Redis backend and component interactions.
Follows 3-tier testing policy: uses real Docker services, no mocking.
"""

import time
from datetime import UTC, datetime

import pytest
from kailash.nodes.cache.cache import CacheNode
from kailash.nodes.cache.cache_invalidation import CacheInvalidationNode
from kailash.sdk_exceptions import NodeExecutionError

# Mark all tests in this file as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.requires_docker]


class TestCacheInvalidationNodeIntegration:
    """Integration tests for CacheInvalidationNode with Redis backend."""

    @pytest.fixture(scope="class")
    def cache_node(self):
        """Create a CacheNode instance for setting up test data."""
        return CacheNode()

    @pytest.fixture(scope="class")
    def invalidation_node(self):
        """Create a CacheInvalidationNode instance for testing."""
        return CacheInvalidationNode()

    @pytest.fixture
    def test_data_setup(self, cache_node):
        """Set up test data in Redis for invalidation testing."""
        # Set up various cache entries for testing
        test_entries = {
            "user:123:profile": {
                "user_id": 123,
                "name": "John Doe",
                "email": "john@test.com",
            },
            "user:123:preferences": {"theme": "dark", "notifications": True},
            "user:123:session": {
                "session_id": "abc123",
                "expires_at": time.time() + 3600,
            },
            "user:456:profile": {
                "user_id": 456,
                "name": "Jane Smith",
                "email": "jane@test.com",
            },
            "user:456:preferences": {"theme": "light", "notifications": False},
            "product:789:details": {
                "product_id": 789,
                "name": "Test Product",
                "price": 99.99,
            },
            "product:789:inventory": {"product_id": 789, "stock": 50, "warehouse": "A"},
            "session:abc123": {"user_id": 123, "created_at": time.time()},
            "session:def456": {"user_id": 456, "created_at": time.time()},
            "cache:stats:hourly": {
                "requests": 1000,
                "errors": 5,
                "timestamp": time.time(),
            },
        }

        for key, value in test_entries.items():
            cache_node.execute(
                operation="set",
                key=key,
                value=value,
                backend="redis",
                redis_url="redis://localhost:6380",
                ttl=3600,  # 1 hour TTL
            )

        return test_entries

    def test_redis_single_key_invalidation(
        self, invalidation_node, test_data_setup, cache_node
    ):
        """Test single key invalidation with Redis backend."""
        # Verify key exists before invalidation
        pre_result = cache_node.execute(
            operation="get",
            key="user:123:profile",
            backend="redis",
            redis_url="redis://localhost:6380",
        )
        assert pre_result["hit"] is True

        # Invalidate single key
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            key="user:123:profile",
            backend="redis",
            redis_url="redis://localhost:6380",
            reason="User profile updated",
        )

        assert result["success"] is True
        assert result["invalidated_count"] == 1
        assert result["strategy_used"] == "immediate"
        assert result["scope_used"] == "single"
        assert "user:123:profile" in result["invalidated_keys"]

        # Verify key is actually invalidated
        post_result = cache_node.execute(
            operation="get",
            key="user:123:profile",
            backend="redis",
            redis_url="redis://localhost:6380",
        )
        assert post_result["hit"] is False

    def test_redis_multiple_keys_invalidation(
        self, invalidation_node, test_data_setup, cache_node
    ):
        """Test multiple keys invalidation with Redis backend."""
        keys_to_invalidate = ["user:123:preferences", "user:123:session"]

        # Verify keys exist before invalidation
        for key in keys_to_invalidate:
            pre_result = cache_node.execute(
                operation="get",
                key=key,
                backend="redis",
                redis_url="redis://localhost:6380",
            )
            assert pre_result["hit"] is True

        # Invalidate multiple keys
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            keys=keys_to_invalidate,
            backend="redis",
            redis_url="redis://localhost:6380",
            reason="User session cleanup",
        )

        assert result["success"] is True
        assert result["invalidated_count"] == 2
        assert all(key in result["invalidated_keys"] for key in keys_to_invalidate)

        # Verify keys are actually invalidated
        for key in keys_to_invalidate:
            post_result = cache_node.execute(
                operation="get",
                key=key,
                backend="redis",
                redis_url="redis://localhost:6380",
            )
            assert post_result["hit"] is False

    def test_redis_pattern_invalidation(
        self, invalidation_node, test_data_setup, cache_node
    ):
        """Test pattern-based invalidation with Redis backend."""
        # Set up additional test data for pattern matching
        pattern_keys = ["temp:data:1", "temp:data:2", "temp:other:1"]
        for key in pattern_keys:
            cache_node.execute(
                operation="set",
                key=key,
                value={"temp": True, "key": key},
                backend="redis",
                redis_url="redis://localhost:6380",
                ttl=300,
            )

        # Invalidate by pattern
        result = invalidation_node.execute(
            strategy="immediate",
            scope="pattern",
            pattern="temp:data:*",
            backend="redis",
            redis_url="redis://localhost:6380",
            reason="Pattern cleanup",
        )

        assert result["success"] is True
        assert result["strategy_used"] == "immediate"
        assert result["scope_used"] == "pattern"
        # Should match temp:data:1 and temp:data:2 but not temp:other:1
        assert result["invalidated_count"] == 2

        # Verify pattern matches were invalidated
        get_result1 = cache_node.execute(
            operation="get",
            key="temp:data:1",
            backend="redis",
            redis_url="redis://localhost:6380",
        )
        assert get_result1["hit"] is False

        # Verify non-matches still exist
        get_result2 = cache_node.execute(
            operation="get",
            key="temp:other:1",
            backend="redis",
            redis_url="redis://localhost:6380",
        )
        assert get_result2["hit"] is True

    def test_redis_cascade_invalidation(
        self, invalidation_node, test_data_setup, cache_node
    ):
        """Test cascade invalidation with Redis backend."""
        # Set up cascade test data
        parent_key = "parent:item:123"
        dependent_keys = [
            "child:item:123:a",
            "child:item:123:b",
            "related:item:123:cache",
        ]

        # Set parent and dependent data
        cache_node.execute(
            operation="set",
            key=parent_key,
            value={"parent_id": 123, "status": "active"},
            backend="redis",
            redis_url="redis://localhost:6380",
        )

        for dep_key in dependent_keys:
            cache_node.execute(
                operation="set",
                key=dep_key,
                value={"parent_ref": 123, "dependency": True},
                backend="redis",
                redis_url="redis://localhost:6380",
            )

        # Perform cascade invalidation
        result = invalidation_node.execute(
            strategy="cascade",
            scope="single",
            key=parent_key,
            cascade_patterns=["child:item:123:*", "related:item:123:*"],
            backend="redis",
            redis_url="redis://localhost:6380",
            reason="Parent item updated - cascade cleanup",
        )

        assert result["success"] is True
        assert result["strategy_used"] == "cascade"
        assert result["invalidated_count"] == 1  # Parent key
        assert result["cascade_count"] >= 3  # Dependent keys
        assert parent_key in result["invalidated_keys"]

        # Small delay to ensure Redis operations are completed
        import time

        time.sleep(0.1)

        # Verify parent is invalidated
        parent_result = cache_node.execute(
            operation="get",
            key=parent_key,
            backend="redis",
            redis_url="redis://localhost:6380",
        )
        assert parent_result["hit"] is False

        # Verify dependent keys are invalidated
        for dep_key in dependent_keys:
            dep_result = cache_node.execute(
                operation="get",
                key=dep_key,
                backend="redis",
                redis_url="redis://localhost:6380",
            )
            assert dep_result["hit"] is False

    def test_redis_dependency_invalidation(
        self, invalidation_node, test_data_setup, cache_node
    ):
        """Test dependency-based invalidation with Redis backend."""
        # Set up dependency test data
        dependencies = ["dep:cache:1", "dep:cache:2", "dep:cache:3"]

        for dep in dependencies:
            cache_node.execute(
                operation="set",
                key=dep,
                value={"dependency": True, "key": dep},
                backend="redis",
                redis_url="redis://localhost:6380",
            )

        # Test dependency invalidation
        result = invalidation_node.execute(
            strategy="immediate",
            scope="dependency",
            source_key="source:item:789",
            dependencies=dependencies,
            event_type="update",
            backend="redis",
            redis_url="redis://localhost:6380",
            reason="Source data updated",
        )

        assert result["success"] is True
        assert result["strategy_used"] == "immediate"
        assert result["scope_used"] == "dependency"
        assert result["invalidated_count"] == 3
        assert all(dep in result["invalidated_keys"] for dep in dependencies)

        # Verify dependencies are invalidated
        for dep in dependencies:
            dep_result = cache_node.execute(
                operation="get",
                key=dep,
                backend="redis",
                redis_url="redis://localhost:6380",
            )
            assert dep_result["hit"] is False

    def test_redis_lazy_invalidation_strategy(
        self, invalidation_node, test_data_setup, cache_node
    ):
        """Test lazy invalidation strategy with Redis backend."""
        # Set up test data
        lazy_key = "lazy:test:key"
        cache_node.execute(
            operation="set",
            key=lazy_key,
            value={"test": "lazy_invalidation"},
            backend="redis",
            redis_url="redis://localhost:6380",
        )

        # Perform lazy invalidation
        result = invalidation_node.execute(
            strategy="lazy",
            scope="single",
            key=lazy_key,
            backend="redis",
            redis_url="redis://localhost:6380",
            reason="Lazy cleanup test",
        )

        assert result["success"] is True
        assert result["strategy_used"] == "lazy"
        assert result["invalidated_count"] == 1
        assert lazy_key in result["invalidated_keys"]

        # Note: Lazy invalidation marks for deletion but doesn't immediately remove
        # The actual verification depends on implementation details

    def test_redis_ttl_refresh_strategy(
        self, invalidation_node, test_data_setup, cache_node
    ):
        """Test TTL refresh invalidation strategy with Redis backend."""
        # Set up test data with longer TTL
        ttl_key = "ttl:refresh:test"
        cache_node.execute(
            operation="set",
            key=ttl_key,
            value={"test": "ttl_refresh"},
            backend="redis",
            redis_url="redis://localhost:6380",
            ttl=300,  # 5 minutes
        )

        # Perform TTL refresh (should shorten TTL)
        result = invalidation_node.execute(
            strategy="ttl_refresh",
            scope="single",
            key=ttl_key,
            new_ttl=1,  # 1 second
            backend="redis",
            redis_url="redis://localhost:6380",
            reason="TTL refresh test",
        )

        assert result["success"] is True
        assert result["strategy_used"] == "ttl_refresh"
        assert result["invalidated_count"] == 1

        # Wait for new TTL to expire (longer than TTL)
        time.sleep(1.1)

        # Verify key expired due to shortened TTL
        expired_result = cache_node.execute(
            operation="get",
            key=ttl_key,
            backend="redis",
            redis_url="redis://localhost:6380",
        )
        assert expired_result["hit"] is False

    def test_redis_namespace_invalidation(self, invalidation_node, cache_node):
        """Test namespace-based invalidation with Redis backend."""
        namespace = "test_namespace"

        # Set up namespaced test data
        namespaced_keys = ["ns_key_1", "ns_key_2", "ns_key_3"]
        for key in namespaced_keys:
            cache_node.execute(
                operation="set",
                key=key,
                value={"namespaced": True, "key": key},
                backend="redis",
                redis_url="redis://localhost:6380",
                namespace=namespace,
            )

        # Invalidate with namespace
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            keys=namespaced_keys,
            namespace=namespace,
            backend="redis",
            redis_url="redis://localhost:6380",
            reason="Namespace cleanup",
        )

        assert result["success"] is True
        assert result["invalidated_count"] == 3

        # Verify namespaced keys are invalidated
        for key in namespaced_keys:
            ns_result = cache_node.execute(
                operation="get",
                key=key,
                namespace=namespace,
                backend="redis",
                redis_url="redis://localhost:6380",
            )
            assert ns_result["hit"] is False

    def test_redis_dry_run_invalidation(
        self, invalidation_node, test_data_setup, cache_node
    ):
        """Test dry run functionality with Redis backend."""
        # Verify original data exists
        dry_run_key = "user:456:profile"
        pre_result = cache_node.execute(
            operation="get",
            key=dry_run_key,
            backend="redis",
            redis_url="redis://localhost:6380",
        )
        assert pre_result["hit"] is True

        # Perform dry run invalidation
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            key=dry_run_key,
            backend="redis",
            redis_url="redis://localhost:6380",
            dry_run=True,
            reason="Dry run test",
        )

        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["invalidated_count"] == 1
        assert dry_run_key in result["invalidated_keys"]

        # Verify data still exists (dry run should not actually invalidate)
        post_result = cache_node.execute(
            operation="get",
            key=dry_run_key,
            backend="redis",
            redis_url="redis://localhost:6380",
        )
        assert post_result["hit"] is True  # Should still exist

    def test_redis_batch_invalidation(self, invalidation_node, cache_node):
        """Test batch invalidation with Redis backend."""
        # Set up large number of keys for batch testing
        batch_keys = []
        for i in range(25):  # Create 25 keys
            key = f"batch:test:{i}"
            batch_keys.append(key)
            cache_node.execute(
                operation="set",
                key=key,
                value={"batch_id": i, "test": True},
                backend="redis",
                redis_url="redis://localhost:6380",
            )

        # Perform batch invalidation with batch size limit
        result = invalidation_node.execute(
            strategy="immediate",
            scope="pattern",
            pattern="batch:test:*",
            batch_size=10,  # Process in batches of 10
            backend="redis",
            redis_url="redis://localhost:6380",
            reason="Batch cleanup test",
        )

        assert result["success"] is True
        assert result["invalidated_count"] == 25
        assert result["strategy_used"] == "immediate"

        # Verify all batch keys are invalidated
        for key in batch_keys[:5]:  # Check first 5 keys
            batch_result = cache_node.execute(
                operation="get",
                key=key,
                backend="redis",
                redis_url="redis://localhost:6380",
            )
            assert batch_result["hit"] is False

    def test_redis_error_handling(self, invalidation_node):
        """Test error handling with Redis backend."""
        # Test connection to invalid Redis URL
        with pytest.raises(NodeExecutionError, match="Failed to connect to Redis"):
            invalidation_node.execute(
                strategy="immediate",
                scope="single",
                key="error_test",
                backend="redis",
                redis_url="redis://invalid:9999",  # Invalid Redis URL
                reason="Error test",
            )

    def test_redis_statistics_tracking(self, invalidation_node, cache_node):
        """Test statistics tracking with Redis backend."""
        # Set up test data for stats
        stats_keys = ["stats:test:1", "stats:test:2", "stats:test:3"]
        for key in stats_keys:
            cache_node.execute(
                operation="set",
                key=key,
                value={"stats": True},
                backend="redis",
                redis_url="redis://localhost:6380",
            )

        # Perform invalidation to generate stats
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            keys=stats_keys,
            backend="redis",
            redis_url="redis://localhost:6380",
            reason="Statistics test",
        )

        assert result["success"] is True
        assert "stats" in result
        assert "execution_time" in result
        assert "timestamp" in result

        stats = result["stats"]
        assert stats["invalidations"] >= 3
        assert result["execution_time"] > 0

    def test_redis_hybrid_backend_invalidation(self, invalidation_node, cache_node):
        """Test invalidation with hybrid backend (Redis + memory)."""
        # Set up data in hybrid backend
        hybrid_key = "hybrid:invalidation:test"
        cache_node.execute(
            operation="set",
            key=hybrid_key,
            value={"hybrid": True, "backend": "redis+memory"},
            backend="hybrid",
            redis_url="redis://localhost:6380",
        )

        # Verify data exists
        pre_result = cache_node.execute(
            operation="get",
            key=hybrid_key,
            backend="hybrid",
            redis_url="redis://localhost:6380",
        )
        assert pre_result["hit"] is True

        # Invalidate from hybrid backend
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            key=hybrid_key,
            backend="hybrid",
            redis_url="redis://localhost:6380",
            reason="Hybrid backend test",
        )

        assert result["success"] is True
        assert result["invalidated_count"] == 1

        # Small delay to ensure Redis operations are completed
        import time

        time.sleep(0.1)

        # Verify invalidation worked
        post_result = cache_node.execute(
            operation="get",
            key=hybrid_key,
            backend="hybrid",
            redis_url="redis://localhost:6380",
        )
        assert post_result["hit"] is False
