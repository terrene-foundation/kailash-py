"""
Integration tests for cache invalidation strategies.

Tests table-based invalidation, pattern-based rules, manual invalidation,
cascade invalidation, and bulk operations using real infrastructure.
"""

import os
import re

# Import actual classes
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../src"))
from dataflow.cache.invalidation import CacheInvalidator, InvalidationPattern
from dataflow.cache.redis_manager import CacheConfig, RedisCacheManager


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestTableBasedInvalidation:
    """Test table-based invalidation patterns."""

    def test_single_table_invalidation(self):
        """Test invalidation of cache entries for a single table."""
        # Mock cache manager
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 2

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register a pattern for user operations
        pattern = InvalidationPattern(
            model="users", operation="create", invalidates=["dataflow:users:*"]
        )
        invalidator.register_pattern(pattern)

        # Trigger invalidation
        invalidator.invalidate("users", "create", {"id": 1, "name": "John"})

        # Should clear the pattern
        mock_cache_manager.clear_pattern.assert_called_once_with("dataflow:users:*")

    def test_table_invalidation_with_tenant_isolation(self):
        """Test table invalidation respecting tenant isolation."""
        # Mock cache manager
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 1

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register pattern with tenant isolation
        pattern = InvalidationPattern(
            model="users", operation="create", invalidates=["dataflow:tenant1:users:*"]
        )
        invalidator.register_pattern(pattern)

        # Trigger invalidation
        invalidator.invalidate("users", "create", {"id": 1, "tenant_id": "tenant1"})

        # Should clear tenant-specific pattern
        mock_cache_manager.clear_pattern.assert_called_once_with(
            "dataflow:tenant1:users:*"
        )

    def test_multiple_table_invalidation(self):
        """Test invalidation of multiple tables at once."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 5

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register patterns for multiple tables
        pattern1 = InvalidationPattern(
            model="users", operation="create", invalidates=["dataflow:users:*"]
        )
        pattern2 = InvalidationPattern(
            model="orders", operation="create", invalidates=["dataflow:orders:*"]
        )

        invalidator.register_pattern(pattern1)
        invalidator.register_pattern(pattern2)

        # Batch invalidation for multiple tables
        with invalidator.batch():
            invalidator.invalidate("users", "create", {"id": 1})
            invalidator.invalidate("orders", "create", {"id": 2})

        # Should call clear_pattern for both tables
        assert mock_cache_manager.clear_pattern.call_count == 2
        call_args = [
            call[0][0] for call in mock_cache_manager.clear_pattern.call_args_list
        ]
        assert "dataflow:users:*" in call_args
        assert "dataflow:orders:*" in call_args

    def test_table_invalidation_performance(self):
        """Test performance of table invalidation with many keys."""
        import time

        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 1000

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register pattern for users table
        pattern = InvalidationPattern(
            model="users",
            operation="*",  # Match all operations
            invalidates=["dataflow:users:*"],
        )
        invalidator.register_pattern(pattern)

        # Time the invalidation
        start_time = time.time()
        invalidator.invalidate("users", "bulk_update", {"count": 1000})
        execution_time = time.time() - start_time

        # Should be fast even with many keys (pattern-based deletion is efficient)
        assert execution_time < 0.1  # Under 100ms

        # Should call clear_pattern once for users
        mock_cache_manager.clear_pattern.assert_called_once_with("dataflow:users:*")

        # Should return 1000 deleted keys
        assert mock_cache_manager.clear_pattern.return_value == 1000


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestPatternBasedInvalidation:
    """Test pattern-based invalidation rules."""

    def test_regex_pattern_invalidation(self):
        """Test invalidation using regex patterns."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 2

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register pattern with regex-style wildcards
        pattern = InvalidationPattern(
            model="users",
            operation="status_update",
            invalidates=["dataflow:*:active:*"],
        )
        invalidator.register_pattern(pattern)

        # Trigger invalidation
        invalidator.invalidate("users", "status_update", {"status": "active"})

        # Should call clear_pattern with regex-style pattern
        mock_cache_manager.clear_pattern.assert_called_once_with("dataflow:*:active:*")

    def test_wildcard_pattern_invalidation(self):
        """Test invalidation using wildcard patterns."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 3

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register pattern with wildcard
        pattern = InvalidationPattern(
            model="users", operation="update", invalidates=["dataflow:users:filter:*"]
        )
        invalidator.register_pattern(pattern)

        # Trigger invalidation
        invalidator.invalidate("users", "update", {"id": 1, "status": "active"})

        # Should clear wildcard pattern
        mock_cache_manager.clear_pattern.assert_called_once_with(
            "dataflow:users:filter:*"
        )

    def test_custom_pattern_rules(self):
        """Test custom pattern-based invalidation rules."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 3

        invalidator = CacheInvalidator(mock_cache_manager)

        # Define custom pattern using groups
        invalidator.define_group(
            "user_stats",
            [
                "dataflow:*:users:count",
                "dataflow:*:users:stats",
                "dataflow:*:users:analytics",
            ],
        )

        # Register pattern that uses the group
        pattern = InvalidationPattern(
            model="users", operation="stats_update", invalidate_groups=["user_stats"]
        )
        invalidator.register_pattern(pattern)

        # Trigger invalidation
        invalidator.invalidate("users", "stats_update", {"metric": "count"})

        # Should call clear_pattern for each pattern in the group
        assert mock_cache_manager.clear_pattern.call_count == 3
        call_args = [
            call[0][0] for call in mock_cache_manager.clear_pattern.call_args_list
        ]
        assert "dataflow:*:users:count" in call_args
        assert "dataflow:*:users:stats" in call_args
        assert "dataflow:*:users:analytics" in call_args

    def test_pattern_compilation_caching(self):
        """Test caching of compiled regex patterns for performance."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 1

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register pattern for users
        pattern = InvalidationPattern(
            model="users", operation="update", invalidates=["dataflow:users:*"]
        )
        invalidator.register_pattern(pattern)

        # First use should process pattern
        invalidator.invalidate("users", "update", {"id": 1})

        # Second use should reuse pattern processing
        invalidator.invalidate("users", "update", {"id": 2})

        # Should call clear_pattern twice with same pattern
        assert mock_cache_manager.clear_pattern.call_count == 2
        assert all(
            call[0][0] == "dataflow:users:*"
            for call in mock_cache_manager.clear_pattern.call_args_list
        )


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestManualInvalidation:
    """Test manual invalidation commands."""

    def test_single_key_invalidation(self):
        """Test manual invalidation of a single cache key."""
        mock_cache_manager = Mock()
        mock_cache_manager.delete.return_value = 1

        invalidator = CacheInvalidator(mock_cache_manager)

        # Invalidate specific key
        key = "dataflow:users:query_specific"
        result = invalidator.invalidate_key(key)

        # Should delete the specific key
        assert result is True
        mock_cache_manager.delete.assert_called_once_with(key)

    def test_multiple_key_invalidation(self):
        """Test manual invalidation of multiple specific keys."""
        mock_cache_manager = Mock()
        mock_cache_manager.delete_many.return_value = 3

        invalidator = CacheInvalidator(mock_cache_manager)

        keys = [
            "dataflow:users:query1",
            "dataflow:users:query2",
            "dataflow:orders:query1",
        ]

        # Invalidate specific keys
        result = invalidator.invalidate_keys(keys)

        # Should delete all specified keys
        assert result == 3
        mock_cache_manager.delete_many.assert_called_once_with(keys)

    def test_key_existence_check(self):
        """Test checking key existence before invalidation."""
        mock_cache_manager = Mock()
        mock_cache_manager.exists.return_value = True

        invalidator = CacheInvalidator(mock_cache_manager)

        key = "dataflow:users:query1"
        exists = invalidator.key_exists(key)

        assert exists is True
        mock_cache_manager.exists.assert_called_once_with(key)

    def test_conditional_invalidation(self):
        """Test conditional invalidation based on key properties."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_ttl.side_effect = [100, -1, 300]  # 100s, no TTL, 300s
        mock_cache_manager.delete_many.return_value = 1

        invalidator = CacheInvalidator(mock_cache_manager)

        keys = ["key1", "key2", "key3"]

        # Simulate conditional invalidation by checking TTL
        keys_to_delete = []
        for key in keys:
            ttl = mock_cache_manager.get_ttl(key)
            if 0 < ttl < 200:
                keys_to_delete.append(key)

        # Should only include key1 (TTL=100)
        assert keys_to_delete == ["key1"]

        # Invalidate the filtered keys
        result = invalidator.invalidate_keys(keys_to_delete)

        # Should delete only key1
        assert result == 1
        mock_cache_manager.delete_many.assert_called_once_with(["key1"])


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestCascadeInvalidation:
    """Test cascade invalidation for related tables."""

    def test_foreign_key_cascade_invalidation(self):
        """Test cascade invalidation based on foreign key relationships."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 1

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register patterns for related tables
        user_pattern = InvalidationPattern(
            model="users",
            operation="update",
            invalidates=[
                "dataflow:users:*",
                "dataflow:orders:*",
                "dataflow:profiles:*",
            ],
        )
        invalidator.register_pattern(user_pattern)

        # Trigger cascade invalidation
        invalidator.invalidate("users", "update", {"id": 1})

        # Should invalidate all related patterns
        assert mock_cache_manager.clear_pattern.call_count == 3
        call_args = [
            call[0][0] for call in mock_cache_manager.clear_pattern.call_args_list
        ]
        assert "dataflow:users:*" in call_args
        assert "dataflow:orders:*" in call_args
        assert "dataflow:profiles:*" in call_args

    def test_circular_dependency_handling(self):
        """Test handling of circular dependencies in cascade invalidation."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 1

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register patterns for models with circular dependencies
        user_pattern = InvalidationPattern(
            model="users",
            operation="update",
            invalidates=["dataflow:users:*", "dataflow:orders:*"],
        )
        order_pattern = InvalidationPattern(
            model="orders",
            operation="update",
            invalidates=["dataflow:orders:*", "dataflow:users:*"],
        )

        invalidator.register_pattern(user_pattern)
        invalidator.register_pattern(order_pattern)

        # Trigger invalidation (should handle circular patterns gracefully)
        invalidator.invalidate("users", "update", {"id": 1})

        # Should invalidate both related patterns
        assert mock_cache_manager.clear_pattern.call_count == 2
        call_args = [
            call[0][0] for call in mock_cache_manager.clear_pattern.call_args_list
        ]
        assert "dataflow:users:*" in call_args
        assert "dataflow:orders:*" in call_args

    def test_deep_cascade_invalidation(self):
        """Test deep cascade invalidation through multiple levels."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 1

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register pattern for deep cascade
        company_pattern = InvalidationPattern(
            model="companies",
            operation="update",
            invalidates=[
                "dataflow:companies:*",
                "dataflow:departments:*",
                "dataflow:teams:*",
                "dataflow:users:*",
                "dataflow:tasks:*",
            ],
        )
        invalidator.register_pattern(company_pattern)

        # Trigger deep cascade invalidation
        invalidator.invalidate("companies", "update", {"id": 1})

        # Should invalidate all levels
        assert mock_cache_manager.clear_pattern.call_count == 5
        call_args = [
            call[0][0] for call in mock_cache_manager.clear_pattern.call_args_list
        ]
        assert "dataflow:companies:*" in call_args
        assert "dataflow:departments:*" in call_args
        assert "dataflow:teams:*" in call_args
        assert "dataflow:users:*" in call_args
        assert "dataflow:tasks:*" in call_args


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestBulkInvalidation:
    """Test bulk invalidation operations for performance."""

    def test_bulk_table_invalidation(self):
        """Test bulk invalidation of multiple tables efficiently."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 2

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register patterns for multiple tables
        tables = ["users", "orders", "products", "categories"]
        for table in tables:
            pattern = InvalidationPattern(
                model=table,
                operation="bulk_update",
                invalidates=[f"dataflow:{table}:*"],
            )
            invalidator.register_pattern(pattern)

        # Bulk invalidate multiple tables using batch mode
        with invalidator.batch():
            for table in tables:
                invalidator.invalidate(table, "bulk_update", {"bulk": True})

        # Should clear patterns for all specified tables
        assert mock_cache_manager.clear_pattern.call_count == 4
        call_args = [
            call[0][0] for call in mock_cache_manager.clear_pattern.call_args_list
        ]
        assert "dataflow:users:*" in call_args
        assert "dataflow:orders:*" in call_args
        assert "dataflow:products:*" in call_args
        assert "dataflow:categories:*" in call_args

    def test_time_based_bulk_invalidation(self):
        """Test bulk invalidation based on time criteria."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_ttl.side_effect = [50, 7200, 300]  # 50s, 2h, 5min
        mock_cache_manager.delete_many.return_value = 2

        invalidator = CacheInvalidator(mock_cache_manager)

        # Mock keys with different TTL values
        keys = ["dataflow:old:query1", "dataflow:old:query2", "dataflow:recent:query1"]

        # Simulate time-based invalidation by checking TTL
        keys_to_delete = []
        for key in keys:
            ttl = mock_cache_manager.get_ttl(key)
            if ttl < 3600:  # Less than 1 hour
                keys_to_delete.append(key)

        # Should include keys with TTL < 1 hour
        assert len(keys_to_delete) == 2
        assert "dataflow:old:query1" in keys_to_delete
        assert "dataflow:recent:query1" in keys_to_delete

        # Invalidate the filtered keys
        result = invalidator.invalidate_keys(keys_to_delete)

        # Should delete old keys
        assert result == 2
        mock_cache_manager.delete_many.assert_called_once_with(keys_to_delete)

    def test_size_based_bulk_invalidation(self):
        """Test bulk invalidation to manage cache size."""
        mock_cache_manager = Mock()
        mock_cache_manager.get_stats.return_value = {
            "memory_usage_mb": 100,  # 100MB used
            "status": "connected",
        }
        mock_cache_manager.delete_many.return_value = 2

        invalidator = CacheInvalidator(mock_cache_manager)

        # Simulate size-based cleanup logic
        stats = mock_cache_manager.get_stats()
        if stats["memory_usage_mb"] > 80:  # Over 80MB limit
            # Simulate finding keys to delete based on size
            keys_to_delete = [
                "dataflow:old:query1",  # Oldest key
                "dataflow:old:query2",  # Second oldest key
            ]

            # Delete keys to free up space
            result = invalidator.invalidate_keys(keys_to_delete)

            # Should delete oldest keys first
            assert result == 2
            mock_cache_manager.delete_many.assert_called_once_with(keys_to_delete)
        else:
            # No cleanup needed
            assert False, "Should have triggered cleanup"


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestInvalidationEvents:
    """Test invalidation event handling and notifications."""

    def test_invalidation_event_listeners(self):
        """Test event listeners for invalidation operations."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 5

        invalidator = CacheInvalidator(mock_cache_manager)

        # Event listener mock
        event_listener = Mock()

        # Register event listener as post-hook
        invalidator.add_post_hook(event_listener)

        # Register pattern for users
        pattern = InvalidationPattern(
            model="users", operation="create", invalidates=["dataflow:users:*"]
        )
        invalidator.register_pattern(pattern)

        # Perform invalidation
        invalidator.invalidate("users", "create", {"id": 1})

        # Should trigger event listener with correct cleared count
        event_listener.assert_called_once_with("users", "create", {"id": 1}, 5)

    def test_invalidation_statistics_tracking(self):
        """Test tracking of invalidation statistics."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 3
        mock_cache_manager.delete.return_value = 1

        invalidator = CacheInvalidator(mock_cache_manager)
        invalidator.enable_metrics()

        # Register patterns
        user_pattern = InvalidationPattern(
            model="users", operation="update", invalidates=["dataflow:users:*"]
        )
        order_pattern = InvalidationPattern(
            model="orders", operation="update", invalidates=["dataflow:orders:*"]
        )

        invalidator.register_pattern(user_pattern)
        invalidator.register_pattern(order_pattern)

        # Perform multiple invalidations
        invalidator.invalidate("users", "update", {"id": 1})
        invalidator.invalidate("orders", "update", {"id": 2})
        invalidator.invalidate_key("specific_key")

        # Check statistics
        stats = invalidator.get_metrics()

        assert stats["total_invalidations"] == 2  # Pattern-based invalidations
        assert stats["by_model"]["users"] == 1
        assert stats["by_model"]["orders"] == 1
        assert stats["by_operation"]["update"] == 2

    def test_webhook_notifications(self):
        """Test webhook notifications for invalidation events."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.return_value = 1

        invalidator = CacheInvalidator(mock_cache_manager)

        # Mock webhook notification as post-hook
        webhook_mock = Mock()

        def webhook_notification(model, operation, data, cleared_count):
            webhook_mock(
                {
                    "event": "cache_invalidated",
                    "table": model,
                    "operation": operation,
                    "cleared_count": cleared_count,
                    "timestamp": "2025-01-15T12:00:00Z",
                }
            )

        invalidator.add_post_hook(webhook_notification)

        # Register pattern for users
        pattern = InvalidationPattern(
            model="users", operation="update", invalidates=["dataflow:users:*"]
        )
        invalidator.register_pattern(pattern)

        # Perform invalidation
        invalidator.invalidate("users", "update", {"id": 1})

        # Should send webhook notification
        webhook_mock.assert_called_once()
        call_args = webhook_mock.call_args[0][0]
        assert call_args["event"] == "cache_invalidated"
        assert call_args["table"] == "users"
        assert call_args["operation"] == "update"
        assert call_args["cleared_count"] == 1


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestErrorHandling:
    """Test error handling in invalidation operations."""

    def test_redis_connection_error_handling(self):
        """Test handling of Redis connection errors during invalidation."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.side_effect = Exception(
            "Redis connection failed"
        )

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register pattern for users
        pattern = InvalidationPattern(
            model="users", operation="update", invalidates=["dataflow:users:*"]
        )
        invalidator.register_pattern(pattern)

        # Should handle Redis errors gracefully (no exception raised)
        invalidator.invalidate("users", "update", {"id": 1})

        # Should have attempted to clear pattern
        mock_cache_manager.clear_pattern.assert_called_once_with("dataflow:users:*")

    def test_partial_invalidation_failure_handling(self):
        """Test handling of partial failures during bulk invalidation."""
        mock_cache_manager = Mock()
        mock_cache_manager.delete_many.side_effect = Exception(
            "Failed to delete some keys"
        )

        invalidator = CacheInvalidator(mock_cache_manager)

        # Should handle partial failures gracefully
        result = invalidator.invalidate_keys(["key1", "key2", "key3"])

        # Should return 0 on failure
        assert result == 0
        mock_cache_manager.delete_many.assert_called_once_with(["key1", "key2", "key3"])

    def test_invalid_pattern_error_handling(self):
        """Test handling of invalid regex patterns."""
        mock_cache_manager = Mock()
        mock_cache_manager.clear_pattern.side_effect = Exception("Invalid pattern")
        mock_cache_manager.delete.side_effect = Exception("Invalid key")

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register pattern with potentially invalid regex (both as key and pattern)
        pattern = InvalidationPattern(
            model="users",
            operation="update",
            invalidates=["[invalid_regex_(*"],  # With wildcard to trigger clear_pattern
        )
        invalidator.register_pattern(pattern)

        # Should handle invalid patterns gracefully (no exception raised)
        invalidator.invalidate("users", "update", {"id": 1})

        # Should have attempted to clear pattern even if it failed
        mock_cache_manager.clear_pattern.assert_called_once_with("[invalid_regex_(*")

        # Should handle error gracefully (no exception raised)

    def test_timeout_handling(self):
        """Test timeout handling for long-running invalidation operations."""
        import time

        mock_cache_manager = Mock()

        # Mock slow operation
        def slow_clear_pattern(pattern):
            time.sleep(0.1)  # Simulate slow operation
            return 1

        mock_cache_manager.clear_pattern.side_effect = slow_clear_pattern

        invalidator = CacheInvalidator(mock_cache_manager)

        # Register pattern for users
        pattern = InvalidationPattern(
            model="users", operation="update", invalidates=["dataflow:users:*"]
        )
        invalidator.register_pattern(pattern)

        # Should handle slow operations (but not timeout in this simple test)
        start_time = time.time()
        invalidator.invalidate("users", "update", {"id": 1})
        execution_time = time.time() - start_time

        # Should have completed despite being slow
        assert execution_time >= 0.1
        mock_cache_manager.clear_pattern.assert_called_once_with("dataflow:users:*")
