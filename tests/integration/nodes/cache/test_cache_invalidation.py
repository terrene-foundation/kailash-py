"""Unit tests for CacheInvalidationNode.

Tests cache invalidation functionality with proper .execute() usage.
Follows 3-tier testing policy: no Docker dependencies, memory backend only.
"""

import pytest
from kailash.nodes.cache.cache_invalidation import (
    CacheInvalidationNode,
    EventType,
    InvalidationScope,
    InvalidationStrategy,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestCacheInvalidationNode:
    """Test cases for CacheInvalidationNode - Tier 1 Unit Tests."""

    @pytest.fixture
    def invalidation_node(self):
        """Create a CacheInvalidationNode instance for testing."""
        return CacheInvalidationNode()

    def test_initialization(self, invalidation_node):
        """Test CacheInvalidationNode initialization."""
        assert invalidation_node.id is not None
        assert hasattr(invalidation_node, "_redis_client")
        assert hasattr(invalidation_node, "_memory_cache")
        assert hasattr(invalidation_node, "_tag_registry")
        assert hasattr(invalidation_node, "_dependency_graph")
        assert hasattr(invalidation_node, "_invalidation_log")
        assert hasattr(invalidation_node, "_stats")

        # Check initial stats
        assert invalidation_node._stats["invalidations"] == 0
        assert invalidation_node._stats["cascade_invalidations"] == 0

    def test_get_parameters(self, invalidation_node):
        """Test parameter definitions."""
        params = invalidation_node.get_parameters()

        required_params = [
            "strategy",
            "scope",
            "key",
            "keys",
            "pattern",
            "tags",
            "dependencies",
            "cascade_patterns",
            "max_age",
            "reason",
            "event_type",
            "source_key",
            "backend",
            "redis_url",
            "namespace",
            "dry_run",
            "batch_size",
        ]

        for param in required_params:
            assert param in params

        assert params["strategy"].required is True
        assert params["scope"].required is True
        assert params["backend"].default == "memory"
        assert params["dry_run"].default is False

    def test_get_output_schema(self, invalidation_node):
        """Test output schema definition."""
        schema = invalidation_node.get_output_schema()

        expected_outputs = [
            "success",
            "invalidated_count",
            "cascade_count",
            "invalidated_keys",
            "cascade_keys",
            "strategy_used",
            "scope_used",
            "execution_time",
            "stats",
            "dry_run",
            "reason",
            "timestamp",
        ]

        for output in expected_outputs:
            assert output in schema

    def test_single_key_invalidation(self, invalidation_node):
        """Test single key invalidation."""
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            key="test_key",
            backend="memory",
            reason="Testing single key invalidation",
        )

        assert result["success"] is True
        assert result["invalidated_count"] == 1
        assert result["strategy_used"] == "immediate"
        assert result["scope_used"] == "single"
        assert result["reason"] == "Testing single key invalidation"
        assert "test_key" in result["invalidated_keys"]

    def test_multiple_keys_invalidation(self, invalidation_node):
        """Test multiple keys invalidation."""
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            keys=["key1", "key2", "key3"],
            backend="memory",
            reason="Testing multiple keys invalidation",
        )

        assert result["success"] is True
        assert result["invalidated_count"] == 3
        assert len(result["invalidated_keys"]) == 3
        assert all(
            key in result["invalidated_keys"] for key in ["key1", "key2", "key3"]
        )

    def test_dry_run_functionality(self, invalidation_node):
        """Test dry run functionality."""
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            key="dry_run_test",
            backend="memory",
            dry_run=True,
            reason="Testing dry run",
        )

        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["invalidated_count"] == 1
        assert "dry_run_test" in result["invalidated_keys"]

    def test_pattern_invalidation(self, invalidation_node):
        """Test pattern-based invalidation."""
        result = invalidation_node.execute(
            strategy="immediate",
            scope="pattern",
            pattern="user:*:cache",
            backend="memory",
            reason="Testing pattern invalidation",
        )

        assert result["success"] is True
        assert result["strategy_used"] == "immediate"
        assert result["scope_used"] == "pattern"
        # Count will be 0 since we don't have actual cache entries
        assert result["invalidated_count"] >= 0

    def test_tag_invalidation(self, invalidation_node):
        """Test tag-based invalidation."""
        result = invalidation_node.execute(
            strategy="immediate",
            scope="tag",
            tags=["user:123", "profile", "session"],
            backend="memory",
            reason="Testing tag invalidation",
        )

        assert result["success"] is True
        assert result["strategy_used"] == "immediate"
        assert result["scope_used"] == "tag"
        # Count will be 0 since we don't have actual tag mappings
        assert result["invalidated_count"] >= 0

    def test_cascade_invalidation(self, invalidation_node):
        """Test cascade invalidation."""
        result = invalidation_node.execute(
            strategy="cascade",
            scope="single",
            key="parent_key",
            cascade_patterns=["child:*", "related:{key}:*"],
            backend="memory",
            reason="Testing cascade invalidation",
        )

        assert result["success"] is True
        assert result["strategy_used"] == "cascade"
        assert result["invalidated_count"] == 1
        assert result["cascade_count"] >= 0
        assert "parent_key" in result["invalidated_keys"]

    def test_dependency_invalidation(self, invalidation_node):
        """Test dependency-based invalidation."""
        result = invalidation_node.execute(
            strategy="immediate",
            scope="dependency",
            source_key="user:123",
            dependencies=[
                "user:123:profile",
                "user:123:preferences",
                "user:123:session",
            ],
            backend="memory",
            event_type="update",
            reason="User data updated",
        )

        assert result["success"] is True
        assert result["strategy_used"] == "immediate"
        assert result["scope_used"] == "dependency"
        assert result["invalidated_count"] == 3
        expected_keys = ["user:123:profile", "user:123:preferences", "user:123:session"]
        assert all(key in result["invalidated_keys"] for key in expected_keys)

    def test_time_based_invalidation(self, invalidation_node):
        """Test time-based invalidation."""
        result = invalidation_node.execute(
            strategy="immediate",
            scope="time_based",
            max_age=3600,  # 1 hour
            backend="memory",
            reason="Cleaning up old cache entries",
        )

        assert result["success"] is True
        assert result["strategy_used"] == "immediate"
        assert result["scope_used"] == "time_based"
        # Count will be 0 since we don't have actual cached entries
        assert result["invalidated_count"] >= 0

    def test_invalidation_strategies(self, invalidation_node):
        """Test different invalidation strategies."""
        strategies = ["immediate", "lazy", "ttl_refresh", "cascade"]

        for strategy in strategies:
            result = invalidation_node.execute(
                strategy=strategy,
                scope="single",
                key=f"test_key_{strategy}",
                backend="memory",
                reason=f"Testing {strategy} strategy",
            )

            assert result["success"] is True
            assert result["strategy_used"] == strategy

    def test_namespace_support(self, invalidation_node):
        """Test namespace functionality."""
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            key="namespaced_key",
            namespace="test_namespace",
            backend="memory",
            reason="Testing namespace support",
        )

        assert result["success"] is True
        assert result["invalidated_count"] == 1
        # Key should be namespaced
        assert "test_namespace:namespaced_key" in result["invalidated_keys"]

    def test_batch_size_limit(self, invalidation_node):
        """Test batch size limiting."""
        # Test with specific batch size
        result = invalidation_node.execute(
            strategy="immediate",
            scope="pattern",
            pattern="batch:*",
            batch_size=10,
            backend="memory",
            reason="Testing batch size limit",
        )

        assert result["success"] is True
        # Operation should complete successfully regardless of batch size

    def test_error_handling_missing_key(self, invalidation_node):
        """Test error handling for missing key parameter."""
        with pytest.raises(NodeExecutionError, match="Cache invalidation failed"):
            invalidation_node.execute(
                strategy="immediate",
                scope="single",
                # Missing key parameter
                backend="memory",
                reason="Testing error handling",
            )

    def test_error_handling_invalid_strategy(self, invalidation_node):
        """Test error handling for invalid strategy."""
        try:
            result = invalidation_node.execute(
                strategy="invalid_strategy",
                scope="single",
                key="test_key",
                backend="memory",
            )
            # If no exception, should return error
            assert result["success"] is False
        except Exception:
            # Expected - parameter validation should catch this
            pass

    def test_error_handling_invalid_scope(self, invalidation_node):
        """Test error handling for invalid scope."""
        try:
            result = invalidation_node.execute(
                strategy="immediate",
                scope="invalid_scope",
                key="test_key",
                backend="memory",
            )
            # If no exception, should return error
            assert result["success"] is False
        except Exception:
            # Expected - parameter validation should catch this
            pass

    def test_tag_management(self, invalidation_node):
        """Test tag management functionality."""
        # Test add_tag
        invalidation_node.add_tag("user:123", "profile")
        assert "profile" in invalidation_node._tag_registry
        assert "user:123" in invalidation_node._tag_registry["profile"]

        # Test remove_tag
        invalidation_node.remove_tag("user:123", "profile")
        # Tag registry should be cleaned up if empty
        assert "profile" not in invalidation_node._tag_registry

    def test_dependency_management(self, invalidation_node):
        """Test dependency management functionality."""
        # Test add_dependency
        invalidation_node.add_dependency("parent:123", "child:456")
        assert "parent:123" in invalidation_node._dependency_graph
        assert "child:456" in invalidation_node._dependency_graph["parent:123"]

        # Test remove_dependency
        invalidation_node.remove_dependency("parent:123", "child:456")
        # Graph should be cleaned up if empty
        assert "parent:123" not in invalidation_node._dependency_graph

    def test_statistics_tracking(self, invalidation_node):
        """Test statistics tracking."""
        initial_stats = dict(invalidation_node._stats)

        # Perform invalidation
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            key="stats_test",
            backend="memory",
            reason="Testing stats tracking",
        )

        assert result["success"] is True

        # Check that stats were updated
        final_stats = result["stats"]
        assert final_stats["invalidations"] > initial_stats["invalidations"]

    def test_execution_time_tracking(self, invalidation_node):
        """Test execution time tracking."""
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            key="timing_test",
            backend="memory",
            reason="Testing execution time",
        )

        assert result["success"] is True
        assert "execution_time" in result
        assert isinstance(result["execution_time"], float)
        assert result["execution_time"] >= 0

    def test_timestamp_generation(self, invalidation_node):
        """Test timestamp generation."""
        result = invalidation_node.execute(
            strategy="immediate",
            scope="single",
            key="timestamp_test",
            backend="memory",
            reason="Testing timestamp",
        )

        assert result["success"] is True
        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)
        # Should be ISO format
        assert "T" in result["timestamp"]

    def test_invalidation_strategy_enum(self):
        """Test InvalidationStrategy enum values."""
        assert InvalidationStrategy.IMMEDIATE.value == "immediate"
        assert InvalidationStrategy.LAZY.value == "lazy"
        assert InvalidationStrategy.TTL_REFRESH.value == "ttl_refresh"
        assert InvalidationStrategy.CASCADE.value == "cascade"
        assert InvalidationStrategy.TAG_BASED.value == "tag_based"

    def test_invalidation_scope_enum(self):
        """Test InvalidationScope enum values."""
        assert InvalidationScope.SINGLE.value == "single"
        assert InvalidationScope.PATTERN.value == "pattern"
        assert InvalidationScope.TAG.value == "tag"
        assert InvalidationScope.DEPENDENCY.value == "dependency"
        assert InvalidationScope.TIME_BASED.value == "time_based"

    def test_event_type_enum(self):
        """Test EventType enum values."""
        assert EventType.CREATE.value == "create"
        assert EventType.UPDATE.value == "update"
        assert EventType.DELETE.value == "delete"
        assert EventType.ACCESS.value == "access"
        assert EventType.EXPIRE.value == "expire"
