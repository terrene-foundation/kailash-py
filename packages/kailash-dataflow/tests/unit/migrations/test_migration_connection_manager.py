"""
Unit tests for MigrationConnectionManager performance optimization.

This module tests the connection pooling integration system that provides:
- Priority-based connection allocation
- Batch operation planning
- Connection pool utilization optimization
"""

import time
import unittest
from dataclasses import dataclass
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, call, patch

import pytest


@dataclass
class MockConnection:
    """Mock database connection for testing."""

    connection_id: str
    is_active: bool = True


class TestMigrationConnectionManager(unittest.TestCase):
    """Test suite for MigrationConnectionManager class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock connection pool
        self.connection_pool = Mock()
        self.pool_config = {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 30,
            "pool_recycle": 3600,
        }

        # Import and create the MigrationConnectionManager
        from dataflow.performance.migration_optimizer import (
            ConnectionPriority,
            MigrationConnectionManager,
        )

        self.connection_manager = MigrationConnectionManager(
            connection_pool=self.connection_pool, pool_config=self.pool_config
        )
        self.ConnectionPriority = ConnectionPriority

    def test_connection_manager_initialization(self):
        """Test MigrationConnectionManager initializes correctly."""
        self.assertIsNotNone(self.connection_manager)
        self.assertEqual(self.connection_manager.connection_pool, self.connection_pool)
        self.assertEqual(self.connection_manager.pool_config, self.pool_config)
        self.assertIsInstance(self.connection_manager._active_connections, dict)

    def test_get_migration_connection_normal_priority(self):
        """Test getting migration connection with normal priority."""
        # Setup mock connection
        mock_connection = MockConnection("conn_123")
        self.connection_pool.get_connection.return_value = mock_connection

        # Execute
        connection = self.connection_manager.get_migration_connection(
            priority=self.ConnectionPriority.NORMAL
        )

        # Verify
        self.assertEqual(connection, mock_connection)
        self.connection_pool.get_connection.assert_called_once_with(timeout=15)

        # Verify connection tracking
        self.assertIn(id(mock_connection), self.connection_manager._active_connections)
        connection_info = self.connection_manager._active_connections[
            id(mock_connection)
        ]
        self.assertEqual(connection_info["connection"], mock_connection)
        self.assertEqual(connection_info["priority"], self.ConnectionPriority.NORMAL)

    def test_get_migration_connection_high_priority(self):
        """Test getting migration connection with high priority."""
        # Setup mock connection
        mock_connection = MockConnection("conn_456")
        self.connection_pool.get_connection.return_value = mock_connection

        # Execute
        connection = self.connection_manager.get_migration_connection(
            priority=self.ConnectionPriority.HIGH
        )

        # Verify higher timeout for high priority
        self.connection_pool.get_connection.assert_called_once_with(timeout=30)
        self.assertIn(id(mock_connection), self.connection_manager._active_connections)

    def test_get_migration_connection_critical_priority(self):
        """Test getting migration connection with critical priority."""
        # Setup mock connection
        mock_connection = MockConnection("conn_789")
        self.connection_pool.get_connection.return_value = mock_connection

        # Execute
        connection = self.connection_manager.get_migration_connection(
            priority=self.ConnectionPriority.CRITICAL
        )

        # Verify highest timeout for critical priority
        self.connection_pool.get_connection.assert_called_once_with(timeout=60)
        connection_info = self.connection_manager._active_connections[
            id(mock_connection)
        ]
        self.assertEqual(connection_info["priority"], self.ConnectionPriority.CRITICAL)

    def test_get_migration_connection_low_priority(self):
        """Test getting migration connection with low priority."""
        # Setup mock connection
        mock_connection = MockConnection("conn_low")
        self.connection_pool.get_connection.return_value = mock_connection

        # Execute
        connection = self.connection_manager.get_migration_connection(
            priority=self.ConnectionPriority.LOW
        )

        # Verify lowest timeout for low priority
        self.connection_pool.get_connection.assert_called_once_with(timeout=5)

    def test_get_migration_connection_error_handling(self):
        """Test error handling when getting migration connection fails."""
        # Setup connection pool to raise exception
        self.connection_pool.get_connection.side_effect = Exception("Pool exhausted")

        # Execute and expect exception
        with self.assertRaises(Exception) as context:
            self.connection_manager.get_migration_connection()

        self.assertEqual(str(context.exception), "Pool exhausted")

    def test_execute_with_pooled_connection_success(self):
        """Test successful execution of migration operations with pooled connections."""
        # Setup mock operations
        migration_ops = [
            {
                "type": "create_table",
                "table": "users",
                "sql": "CREATE TABLE users (id INT)",
            },
            {
                "type": "add_column",
                "table": "users",
                "sql": "ALTER TABLE users ADD COLUMN name VARCHAR(255)",
            },
            {
                "type": "create_index",
                "table": "users",
                "sql": "CREATE INDEX idx_users_name ON users (name)",
            },
        ]

        # Setup mock connections for each operation
        mock_connections = [
            MockConnection(f"conn_{i}") for i in range(len(migration_ops))
        ]
        self.connection_pool.get_connection.side_effect = mock_connections

        # Mock connection plan optimization
        with patch.object(
            self.connection_manager, "optimize_connection_usage"
        ) as mock_optimize:
            from dataflow.performance.migration_optimizer import (
                ConnectionPlan,
                ConnectionPriority,
            )

            mock_optimize.return_value = ConnectionPlan(
                connection_count=3,
                batch_size=1,
                estimated_duration_seconds=0.3,
                priority=ConnectionPriority.NORMAL,
            )

            # Execute
            result = self.connection_manager.execute_with_pooled_connection(
                migration_ops
            )

            # Import the correct MigrationResult type
            from dataflow.performance.migration_optimizer import MigrationResult

            # Verify successful execution
            self.assertIsInstance(result, MigrationResult)
            self.assertTrue(result.success)
            self.assertEqual(result.operations_completed, len(migration_ops))
            self.assertEqual(result.total_operations, len(migration_ops))
            self.assertEqual(result.connections_used, len(migration_ops))
            self.assertLess(result.execution_time_seconds, 1.0)  # Should be fast

    def test_execute_with_pooled_connection_partial_failure(self):
        """Test execution with partial failure in migration operations."""
        # Setup mock operations where second operation fails
        migration_ops = [
            {
                "type": "create_table",
                "table": "users",
                "sql": "CREATE TABLE users (id INT)",
            },
            {
                "type": "add_column",
                "table": "users",
                "sql": "INVALID SQL",
            },  # This will fail
            {
                "type": "create_index",
                "table": "users",
                "sql": "CREATE INDEX idx_users_name ON users (name)",
            },
        ]

        # Setup mock connections
        mock_connections = [
            MockConnection(f"conn_{i}") for i in range(2)
        ]  # Only 2 because 3rd won't be reached
        self.connection_pool.get_connection.side_effect = mock_connections

        # Mock operation execution to fail on second operation
        with patch.object(
            self.connection_manager, "_execute_migration_operation"
        ) as mock_execute:
            mock_execute.side_effect = [
                None,
                Exception("SQL error"),
                None,
            ]  # Second operation fails

            with patch.object(
                self.connection_manager, "optimize_connection_usage"
            ) as mock_optimize:
                from dataflow.performance.migration_optimizer import (
                    ConnectionPlan,
                    ConnectionPriority,
                )

                mock_optimize.return_value = ConnectionPlan(
                    connection_count=2,
                    batch_size=1,
                    estimated_duration_seconds=0.2,
                    priority=ConnectionPriority.NORMAL,
                )

                # Execute
                result = self.connection_manager.execute_with_pooled_connection(
                    migration_ops
                )

                # Verify partial failure
                self.assertFalse(result.success)
                self.assertEqual(
                    result.operations_completed, 1
                )  # Only first operation completed
                self.assertEqual(result.total_operations, len(migration_ops))
                self.assertEqual(
                    result.connections_used, 2
                )  # Two connections were attempted

    def test_optimize_connection_usage_small_operations(self):
        """Test connection usage optimization for small number of operations."""
        # Setup small set of operations
        planned_operations = [
            {"type": "create_table", "complexity": "low"},
            {"type": "add_column", "complexity": "low"},
        ]

        # Execute
        plan = self.connection_manager.optimize_connection_usage(planned_operations)

        # Import the correct ConnectionPlan type
        from dataflow.performance.migration_optimizer import ConnectionPlan

        # Verify optimization for small operations
        self.assertIsInstance(plan, ConnectionPlan)
        self.assertLessEqual(plan.connection_count, len(planned_operations))
        self.assertGreater(plan.batch_size, 0)
        self.assertGreater(plan.estimated_duration_seconds, 0)

    def test_optimize_connection_usage_large_operations(self):
        """Test connection usage optimization for large number of operations."""
        # Setup large set of operations
        planned_operations = [
            {"type": f"operation_{i}", "complexity": "medium"} for i in range(50)
        ]

        # Execute
        plan = self.connection_manager.optimize_connection_usage(planned_operations)

        # Verify optimization for large operations
        self.assertLessEqual(plan.connection_count, self.pool_config["pool_size"])
        self.assertLessEqual(
            plan.connection_count, 4
        )  # Should not exceed reasonable max
        self.assertGreater(plan.batch_size, 1)  # Should batch operations
        self.assertGreater(plan.estimated_duration_seconds, 0)

    def test_optimize_connection_usage_critical_operations(self):
        """Test connection usage optimization for critical operations."""
        # Setup operations with critical types
        planned_operations = [
            {"type": "drop_table", "table": "old_table"},
            {"type": "drop_column", "table": "users", "column": "deprecated_field"},
            {"type": "create_table", "table": "new_table"},
        ]

        # Execute
        plan = self.connection_manager.optimize_connection_usage(planned_operations)

        # Verify critical priority assignment
        from dataflow.performance.migration_optimizer import ConnectionPriority

        self.assertEqual(plan.priority, ConnectionPriority.CRITICAL)

    def test_optimize_connection_usage_error_handling(self):
        """Test error handling in connection usage optimization."""
        # Setup malformed operations that might cause errors
        malformed_operations = [None, {"invalid": "operation"}, {}]

        # Execute - should handle gracefully
        plan = self.connection_manager.optimize_connection_usage(malformed_operations)

        # Verify fallback plan
        self.assertIsNotNone(plan)
        self.assertEqual(plan.connection_count, 1)  # Safe fallback
        self.assertEqual(plan.batch_size, len(malformed_operations))

    def test_connection_priority_determination(self):
        """Test priority determination for different operation types."""
        # Test critical operations
        critical_op = {"type": "drop_table", "table": "users"}
        priority = self.connection_manager._determine_operation_priority(critical_op)
        self.assertEqual(priority, self.ConnectionPriority.CRITICAL)

        # Test high priority operations
        high_op = {"type": "create_table", "table": "new_users"}
        priority = self.connection_manager._determine_operation_priority(high_op)
        self.assertEqual(priority, self.ConnectionPriority.HIGH)

        # Test normal priority operations
        normal_op = {"type": "create_index", "table": "users"}
        priority = self.connection_manager._determine_operation_priority(normal_op)
        self.assertEqual(priority, self.ConnectionPriority.NORMAL)

    def test_connection_return_to_pool(self):
        """Test returning connections to the pool after use."""
        # Setup mock connection
        mock_connection = MockConnection("conn_return_test")

        # Add connection to active tracking
        connection_id = id(mock_connection)
        self.connection_manager._active_connections[connection_id] = {
            "connection": mock_connection,
            "priority": self.ConnectionPriority.NORMAL,
            "acquired_at": time.time(),
        }

        # Execute return
        self.connection_manager._return_connection(mock_connection)

        # Verify connection removed from tracking
        self.assertNotIn(connection_id, self.connection_manager._active_connections)

        # Verify connection returned to pool
        self.connection_pool.return_connection.assert_called_once_with(mock_connection)

    def test_connection_return_error_handling(self):
        """Test error handling when returning connection to pool fails."""
        # Setup mock connection
        mock_connection = MockConnection("conn_error_test")

        # Make pool return raise exception
        self.connection_pool.return_connection.side_effect = Exception("Pool error")

        # Execute - should handle gracefully (no exception raised)
        self.connection_manager._return_connection(mock_connection)

        # Verify pool return was attempted
        self.connection_pool.return_connection.assert_called_once_with(mock_connection)

    def test_concurrent_connection_access(self):
        """Test connection manager behavior under concurrent access."""
        import concurrent.futures
        import threading

        # Setup multiple mock connections
        mock_connections = [MockConnection(f"conn_concurrent_{i}") for i in range(10)]
        self.connection_pool.get_connection.side_effect = mock_connections

        def get_connection_worker():
            return self.connection_manager.get_migration_connection(
                priority=self.ConnectionPriority.NORMAL
            )

        # Execute concurrent connection requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(get_connection_worker) for _ in range(10)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # Verify all connections were acquired
        self.assertEqual(len(results), 10)
        self.assertEqual(len(self.connection_manager._active_connections), 10)

        # Verify all connections are tracked
        for result in results:
            self.assertIn(id(result), self.connection_manager._active_connections)

    def test_connection_timeout_configuration(self):
        """Test that connection timeouts are configured correctly for different priorities."""
        test_cases = [
            (self.ConnectionPriority.LOW, 5),
            (self.ConnectionPriority.NORMAL, 15),
            (self.ConnectionPriority.HIGH, 30),
            (self.ConnectionPriority.CRITICAL, 60),
        ]

        for priority, expected_timeout in test_cases:
            # Reset mock
            self.connection_pool.reset_mock()

            # Setup mock connection
            mock_connection = MockConnection(f"conn_timeout_{priority.value}")
            self.connection_pool.get_connection.return_value = mock_connection

            # Execute
            self.connection_manager.get_migration_connection(priority=priority)

            # Verify timeout
            self.connection_pool.get_connection.assert_called_once_with(
                timeout=expected_timeout
            )

    def test_migration_operation_execution_simulation(self):
        """Test simulation of migration operation execution."""
        operation = {
            "type": "create_table",
            "table": "test_table",
            "sql": "CREATE TABLE test_table (id INT)",
        }
        mock_connection = MockConnection("conn_exec_test")

        # Execute operation simulation
        start_time = time.time()
        self.connection_manager._execute_migration_operation(mock_connection, operation)
        execution_time = time.time() - start_time

        # Verify execution completed in reasonable time
        self.assertLess(execution_time, 0.1)  # Should be very fast (simulated)

    def test_active_connection_tracking(self):
        """Test that active connections are properly tracked."""
        # Start with empty tracking
        self.assertEqual(len(self.connection_manager._active_connections), 0)

        # Get multiple connections
        connections = []
        for i in range(3):
            mock_connection = MockConnection(f"conn_track_{i}")
            self.connection_pool.get_connection.return_value = mock_connection

            conn = self.connection_manager.get_migration_connection(
                priority=self.ConnectionPriority.NORMAL
            )
            connections.append(conn)

        # Verify all connections are tracked
        self.assertEqual(len(self.connection_manager._active_connections), 3)

        # Return connections and verify tracking cleanup
        for conn in connections:
            self.connection_manager._return_connection(conn)

        self.assertEqual(len(self.connection_manager._active_connections), 0)

    def test_pool_integration_configuration(self):
        """Test integration with connection pool configuration."""
        # Verify pool configuration is properly stored
        self.assertEqual(self.connection_manager.pool_config["pool_size"], 10)
        self.assertEqual(self.connection_manager.pool_config["max_overflow"], 20)
        self.assertEqual(self.connection_manager.pool_config["pool_timeout"], 30)

        # Test optimization uses pool configuration
        large_operations = [{"type": f"op_{i}"} for i in range(100)]
        plan = self.connection_manager.optimize_connection_usage(large_operations)

        # Should not exceed pool size
        self.assertLessEqual(plan.connection_count, self.pool_config["pool_size"])


if __name__ == "__main__":
    unittest.main()
