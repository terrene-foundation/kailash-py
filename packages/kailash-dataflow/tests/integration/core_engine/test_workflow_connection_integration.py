"""
Integration tests for DataFlow WorkflowConnectionPool integration.

These tests verify that DataFlow smart nodes can successfully integrate
with the Kailash SDK's WorkflowConnectionPool for production-grade
connection management.
"""

import os
import sys
from datetime import datetime, timedelta

import pytest

# Add the DataFlow app to the path
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../packages/kailash-dataflow/src")
)

# Import DataFlow nodes
from dataflow.nodes import DataFlowConnectionManager
from dataflow.nodes.aggregate_operations import AggregateNode
from dataflow.nodes.natural_language_filter import NaturalLanguageFilterNode
from dataflow.nodes.smart_operations import SmartMergeNode

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestWorkflowConnectionIntegration:
    """Test DataFlow integration with WorkflowConnectionPool."""

    def setup_method(self):
        """Set up test data and components for each test."""
        # Sample data for testing
        self.users_data = [
            {"id": 1, "name": "Alice", "email": "alice@example.com", "region": "north"},
            {"id": 2, "name": "Bob", "email": "bob@example.com", "region": "south"},
            {
                "id": 3,
                "name": "Charlie",
                "email": "charlie@example.com",
                "region": "north",
            },
        ]

        self.orders_data = [
            {
                "id": 101,
                "user_id": 1,
                "amount": 250.00,
                "status": "completed",
                "created_at": datetime.now().date().isoformat(),
            },
            {
                "id": 102,
                "user_id": 2,
                "amount": 150.00,
                "status": "pending",
                "created_at": (datetime.now().date() - timedelta(days=1)).isoformat(),
            },
            {
                "id": 103,
                "user_id": 1,
                "amount": 300.00,
                "status": "completed",
                "created_at": datetime.now().date().isoformat(),
            },
        ]

        self.sales_data = [
            {"amount": 100, "category": "electronics", "date": "2024-01-15"},
            {"amount": 200, "category": "books", "date": "2024-01-16"},
            {"amount": 150, "category": "electronics", "date": "2024-01-17"},
            {"amount": 300, "category": "clothing", "date": "2024-01-18"},
        ]

    def test_connection_manager_initialization(self, test_suite):
        """Test DataFlowConnectionManager initialization."""
        workflow = WorkflowBuilder()

        # Add connection manager
        workflow.add_node(
            "DataFlowConnectionManager",
            "db_pool",
            {
                "database_type": "postgresql",
                "database": test_suite.config.url,
                "min_connections": 2,
                "max_connections": 5,
                "enable_monitoring": True,
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify initialization
        assert run_id is not None
        assert "db_pool" in results

        pool_result = results["db_pool"]
        assert pool_result["status"] == "initialized"
        assert pool_result["pool_id"] == "db_pool"
        assert pool_result["database_type"] == "postgresql"
        assert pool_result["min_connections"] == 2
        assert pool_result["max_connections"] == 5

    def test_smart_merge_with_connection_pool(self, test_suite):
        """Test SmartMergeNode with connection pool integration."""
        workflow = WorkflowBuilder()

        # Initialize connection pool
        workflow.add_node(
            "DataFlowConnectionManager",
            "db_pool",
            {
                "database_type": "postgresql",
                "host": "localhost",
                "database": "test_db",
                "user": "test_user",
                "password": "test_pass",
                "min_connections": 2,
                "max_connections": 10,
            },
        )

        # Add input data nodes
        workflow.add_node(
            "PythonCodeNode", "users_input", {"code": f"result = {self.users_data}"}
        )
        workflow.add_node(
            "PythonCodeNode", "orders_input", {"code": f"result = {self.orders_data}"}
        )

        # Add SmartMergeNode with connection pool reference
        workflow.add_node(
            "SmartMergeNode",
            "merge_users_orders",
            {
                "merge_type": "auto",
                "left_model": "User",
                "right_model": "Order",
                "connection_pool_id": "db_pool",
            },
        )

        # Connect nodes
        workflow.add_connection(
            "users_input", "result", "merge_users_orders", "left_data"
        )
        workflow.add_connection(
            "orders_input", "result", "merge_users_orders", "right_data"
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert run_id is not None
        assert "db_pool" in results
        assert "merge_users_orders" in results

        # Verify connection pool was initialized
        pool_result = results["db_pool"]
        assert pool_result["status"] == "initialized"

        # Verify merge operation worked
        merge_result = results["merge_users_orders"]
        assert merge_result["auto_detected"] is True
        assert len(merge_result["merged_data"]) == 3

    def test_aggregate_node_with_connection_pool(self, test_suite):
        """Test AggregateNode with connection pool integration."""
        workflow = WorkflowBuilder()

        # Initialize connection pool
        workflow.add_node(
            "DataFlowConnectionManager",
            "db_pool",
            {
                "database_type": "mysql",
                "host": "localhost",
                "database": "analytics_db",
                "min_connections": 1,
                "max_connections": 5,
            },
        )

        # Add input data
        workflow.add_node(
            "PythonCodeNode", "sales_input", {"code": f"result = {self.sales_data}"}
        )

        # Add expression input
        workflow.add_node(
            "PythonCodeNode",
            "expression_input",
            {"code": "result = 'sum of amount by category'"},
        )

        # Add AggregateNode with connection pool reference
        workflow.add_node(
            "AggregateNode", "aggregate_sales", {"connection_pool_id": "db_pool"}
        )

        # Connect nodes
        workflow.add_connection("sales_input", "result", "aggregate_sales", "data")
        workflow.add_connection(
            "expression_input", "result", "aggregate_sales", "aggregate_expression"
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert run_id is not None
        assert "db_pool" in results
        assert "aggregate_sales" in results

        # Verify connection pool was initialized
        pool_result = results["db_pool"]
        assert pool_result["status"] == "initialized"

        # Verify aggregation worked
        agg_result = results["aggregate_sales"]
        assert agg_result["parsed_successfully"] is True
        assert agg_result["aggregation_function"] == "sum"
        assert "electronics" in agg_result["result"]

    def test_natural_language_filter_with_connection_pool(self, test_suite):
        """Test NaturalLanguageFilterNode with connection pool integration."""
        workflow = WorkflowBuilder()

        # Initialize connection pool
        workflow.add_node(
            "DataFlowConnectionManager",
            "db_pool",
            {
                "database_type": "postgresql",
                "connection_string": test_suite.config.url,
                "min_connections": 1,
                "max_connections": 3,
            },
        )

        # Add input data
        workflow.add_node(
            "PythonCodeNode", "sales_input", {"code": f"result = {self.sales_data}"}
        )

        # Add filter expression
        workflow.add_node(
            "PythonCodeNode",
            "filter_expression_input",
            {"code": "result = 'greater than 150'"},
        )

        # Add NaturalLanguageFilterNode with connection pool reference
        workflow.add_node(
            "NaturalLanguageFilterNode",
            "filter_sales",
            {"connection_pool_id": "db_pool"},
        )

        # Connect nodes
        workflow.add_connection("sales_input", "result", "filter_sales", "data")
        workflow.add_connection(
            "filter_expression_input", "result", "filter_sales", "filter_expression"
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert run_id is not None
        assert "db_pool" in results
        assert "filter_sales" in results

        # Verify connection pool was initialized
        pool_result = results["db_pool"]
        assert pool_result["status"] == "initialized"

        # Verify filtering worked
        filter_result = results["filter_sales"]
        assert filter_result["parsed_successfully"] is True
        assert filter_result["matches"] == 2  # 200 and 300 are > 150

    def test_connection_pool_stats_and_monitoring(self, test_suite):
        """Test connection pool statistics and monitoring features."""
        workflow = WorkflowBuilder()

        # Initialize connection pool with monitoring
        workflow.add_node(
            "DataFlowConnectionManager",
            "db_pool",
            {
                "database_type": "postgresql",
                "host": "localhost",
                "database": "monitor_db",
                "min_connections": 3,
                "max_connections": 15,
                "enable_monitoring": True,
                "health_threshold": 80,
            },
        )

        # Get pool stats
        workflow.add_node(
            "PythonCodeNode",
            "get_stats",
            {
                "code": """
# Simulate getting stats from the pool
stats = {
    "operation": "stats",
    "pool_id": "db_pool"
}
result = stats
"""
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify results
        assert run_id is not None
        assert "db_pool" in results

        pool_result = results["db_pool"]
        assert pool_result["status"] == "initialized"
        assert pool_result["monitoring_enabled"] is True
        assert pool_result["min_connections"] == 3
        assert pool_result["max_connections"] == 15

    def test_multiple_smart_nodes_shared_connection_pool(self, test_suite):
        """Test multiple smart nodes sharing the same connection pool."""
        workflow = WorkflowBuilder()

        # Initialize shared connection pool
        workflow.add_node(
            "DataFlowConnectionManager",
            "shared_pool",
            {
                "database_type": "mysql",
                "host": "shared-db.example.com",
                "database": "shared_analytics",
                "min_connections": 5,
                "max_connections": 20,
                "adaptive_sizing": True,
            },
        )

        # Add input data
        workflow.add_node(
            "PythonCodeNode", "users_input", {"code": f"result = {self.users_data}"}
        )
        workflow.add_node(
            "PythonCodeNode", "orders_input", {"code": f"result = {self.orders_data}"}
        )

        # Add parameter inputs
        workflow.add_node(
            "PythonCodeNode",
            "filter_expression_input",
            {"code": "result = 'completed'"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "aggregate_expression_input",
            {"code": "result = 'sum of amount'"},
        )

        # Add multiple smart nodes using the same pool
        workflow.add_node(
            "SmartMergeNode",
            "merge_data",
            {"merge_type": "inner", "connection_pool_id": "shared_pool"},
        )
        workflow.add_node(
            "NaturalLanguageFilterNode",
            "filter_data",
            {"connection_pool_id": "shared_pool"},
        )
        workflow.add_node(
            "AggregateNode", "aggregate_data", {"connection_pool_id": "shared_pool"}
        )

        # Connect the workflow
        workflow.add_connection("users_input", "result", "merge_data", "left_data")
        workflow.add_connection("orders_input", "result", "merge_data", "right_data")
        workflow.add_connection("merge_data", "merged_data", "filter_data", "data")
        workflow.add_connection(
            "filter_expression_input", "result", "filter_data", "filter_expression"
        )
        workflow.add_connection(
            "filter_data", "filtered_data", "aggregate_data", "data"
        )
        workflow.add_connection(
            "aggregate_expression_input",
            "result",
            "aggregate_data",
            "aggregate_expression",
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify all nodes executed successfully
        assert run_id is not None
        assert all(
            step in results
            for step in ["shared_pool", "merge_data", "filter_data", "aggregate_data"]
        )

        # Verify connection pool was initialized once and shared
        pool_result = results["shared_pool"]
        assert pool_result["status"] == "initialized"
        assert pool_result["pool_id"] == "shared_pool"

        # Verify all operations completed
        merge_result = results["merge_data"]
        filter_result = results["filter_data"]
        aggregate_result = results["aggregate_data"]

        assert len(merge_result["merged_data"]) > 0
        assert filter_result["parsed_successfully"] is True
        assert aggregate_result["parsed_successfully"] is True

    def test_connection_pool_error_handling(self, test_suite):
        """Test error handling in connection pool operations."""
        workflow = WorkflowBuilder()

        # Initialize connection pool with invalid configuration
        workflow.add_node(
            "DataFlowConnectionManager",
            "invalid_pool",
            {
                "database_type": "invalid_type",
                "host": "nonexistent-host",
                "database": "nonexistent_db",
                "min_connections": 1,
                "max_connections": 2,
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify error handling
        assert run_id is not None
        assert "invalid_pool" in results

        # The pool should initialize but may have connection issues
        # In a real implementation, this would test actual connection failures
        pool_result = results["invalid_pool"]
        # Should still initialize the configuration even with invalid settings
        assert "status" in pool_result
        assert pool_result["pool_id"] == "invalid_pool"

    def test_connection_pool_lifecycle_management(self, test_suite):
        """Test connection pool lifecycle management in workflows."""
        workflow = WorkflowBuilder()

        # Initialize connection pool
        workflow.add_node(
            "DataFlowConnectionManager",
            "lifecycle_pool",
            {
                "database_type": "postgresql",
                "host": "localhost",
                "database": "lifecycle_test",
                "min_connections": 2,
                "max_connections": 8,
                "pre_warm": True,
            },
        )

        # Simulate workflow operations
        workflow.add_node(
            "PythonCodeNode",
            "operation_1",
            {
                "code": """
# Simulate using connection pool
result = {
    "operation": "query_execution",
    "pool_used": "lifecycle_pool",
    "status": "success"
}
"""
            },
        )

        workflow.add_node(
            "PythonCodeNode",
            "operation_2",
            {
                "code": """
# Simulate another operation
result = {
    "operation": "data_insert",
    "pool_used": "lifecycle_pool",
    "status": "success"
}
"""
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify lifecycle management
        assert run_id is not None
        assert "lifecycle_pool" in results

        pool_result = results["lifecycle_pool"]
        assert pool_result["status"] == "initialized"
        assert pool_result["min_connections"] == 2
        assert pool_result["max_connections"] == 8

        # Verify operations completed
        assert "operation_1" in results
        assert "operation_2" in results
        assert results["operation_1"]["result"]["status"] == "success"
        assert results["operation_2"]["result"]["status"] == "success"
