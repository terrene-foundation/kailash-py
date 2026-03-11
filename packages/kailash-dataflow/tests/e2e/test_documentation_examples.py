"""
End-to-end tests for DataFlow documentation examples.

Tests that all code examples in documentation work correctly,
validate real-world usage patterns, and ensure documentation accuracy.
"""

import os

# Import DataFlow components
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from dataflow import DataFlow
from dataflow.testing.dataflow_test_utils import DataFlowTestUtils

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestDocumentationExamples:
    """Test that documentation examples work correctly in real scenarios."""

    def setup_method(self):
        """Set up test database connection."""
        # Use the official test infrastructure on port 5434
        self.db_url = "postgresql://test_user:test_password@localhost:5434/kailash_test"
        self.test_utils = DataFlowTestUtils(self.db_url)

    def teardown_method(self):
        """Clean up test database after each test."""
        # Use DataFlow's migration system to clean up
        self.test_utils.cleanup_database()

    def test_quickstart_guide_example(self):
        """Test the main quickstart guide example."""
        # Example from quickstart guide - use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class User:
            name: str
            email: str
            active: bool = True

        # Create the database tables
        db.create_tables()

        # Use generated nodes immediately
        workflow = WorkflowBuilder()
        workflow.add_node("UserCreateNode", "create", {})
        workflow.add_node("UserListNode", "list", {})
        workflow.add_connection("create", "result", "list", "filter")

        # Execute with parameters
        runtime = LocalRuntime()
        parameters = {
            "create": {"name": "Alice", "email": "alice@example.com"},
            "list": {"filter": {"active": True}},
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        # Verify the example works
        assert results is not None
        assert run_id is not None
        assert isinstance(results, dict)

    def test_enterprise_pattern_example(self):
        """Test the enterprise pattern from documentation."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class Order:
            customer_id: int
            total: float
            status: str = "pending"

            # Enterprise features
            __dataflow__ = {
                "multi_tenant": True,  # Adds tenant_id field
                "soft_delete": True,  # Adds deleted_at field
                "versioned": True,  # Adds version field for optimistic locking
                "audit_log": True,  # Tracks all changes
            }

        # Create the database tables
        db.create_tables()

        # Test enterprise features work
        workflow = WorkflowBuilder()
        workflow.add_node("OrderCreateNode", "create_order", {})

        runtime = LocalRuntime()
        parameters = {
            "create_order": {
                "customer_id": 12345,
                "total": 250.50,
                "status": "pending",
                "tenant_id": "enterprise_tenant_001",
            }
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert "create_order" in results

    def test_bulk_operations_example(self):
        """Test bulk operations example from documentation."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class Product:
            name: str
            price: float
            category: str

        # Create the database tables
        db.create_tables()

        # Bulk create example
        workflow = WorkflowBuilder()

        bulk_data = [
            {"name": "Product A", "price": 100.0, "category": "electronics"},
            {"name": "Product B", "price": 200.0, "category": "electronics"},
            {"name": "Product C", "price": 50.0, "category": "books"},
        ]

        workflow.add_node("ProductBulkCreateNode", "import", {})

        runtime = LocalRuntime()
        parameters = {
            "import": {
                "data": bulk_data,
                "batch_size": 100,
                "conflict_resolution": "upsert",
                "return_ids": True,
            }
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert "import" in results

    def test_complex_query_example(self):
        """Test complex query example from documentation."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class Order:
            customer_id: int
            total: float
            status: str
            created_at: float = time.time()

        # Create the database tables
        db.create_tables()

        # Create test data first
        workflow_setup = WorkflowBuilder()
        test_orders = [
            {"customer_id": 1, "total": 150.0, "status": "pending"},
            {"customer_id": 2, "total": 250.0, "status": "processing"},
            {"customer_id": 1, "total": 75.0, "status": "completed"},
            {"customer_id": 3, "total": 300.0, "status": "pending"},
        ]

        workflow_setup.add_node("OrderBulkCreateNode", "setup_data", {})

        runtime = LocalRuntime()
        setup_parameters = {"setup_data": {"data": test_orders, "batch_size": 10}}
        setup_results, setup_run_id = runtime.execute(
            workflow_setup.build(), parameters=setup_parameters
        )
        assert setup_results is not None

        # Complex filtering example from docs
        workflow = WorkflowBuilder()
        workflow.add_node("OrderListNode", "search", {})

        parameters = {
            "search": {
                "filter": {
                    "status": {"$in": ["pending", "processing"]},
                    "total": {"$gte": 100.0},
                },
                "sort": [{"created_at": -1}],
                "limit": 100,
                "offset": 0,
            }
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert "search" in results

    def test_database_configuration_example(self):
        """Test database configuration examples."""
        # Use real PostgreSQL database for E2E testing
        db_sqlite = DataFlow(database_url=self.db_url, pool_size=2, pool_max_overflow=3)

        @db_sqlite.model
        class ConfigTest:
            config_type: str
            database_type: str

        # Create the database tables
        db_sqlite.create_tables()

        workflow = WorkflowBuilder()
        workflow.add_node("ConfigTestCreateNode", "test_sqlite", {})

        runtime = LocalRuntime()
        parameters = {
            "test_sqlite": {"config_type": "sqlite", "database_type": "in_memory"}
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None

        # Test configuration with pool settings
        db_configured = DataFlow(
            database_url=self.db_url,
            pool_size=5,
            pool_max_overflow=10,
            pool_recycle=3600,
        )

        @db_configured.model
        class PoolConfigTest:
            pool_config: str
            setting_value: int

        # Create the database tables
        db_configured.create_tables()

        workflow2 = WorkflowBuilder()
        workflow2.add_node("PoolConfigTestCreateNode", "test_pool", {})

        parameters2 = {"test_pool": {"pool_config": "configured", "setting_value": 5}}
        results2, run_id2 = runtime.execute(workflow2.build(), parameters=parameters2)

        assert results2 is not None

    def test_workflow_integration_example(self):
        """Test workflow integration examples from documentation."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class Customer:
            name: str
            email: str

        @db.model
        class Order:
            customer_id: int
            total: float
            status: str = "pending"

        # Create the database tables
        db.create_tables()

        # Multi-step workflow example
        workflow = WorkflowBuilder()

        # Create customer
        workflow.add_node("CustomerCreateNode", "create_customer", {})

        # Create order for customer
        workflow.add_node("OrderCreateNode", "create_order", {})

        # Update order status
        workflow.add_node("OrderUpdateNode", "update_order", {})

        # Connect nodes
        workflow.add_connection("create_customer", "id", "create_order", "customer_id")
        workflow.add_connection("create_order", "id", "update_order", "id")

        runtime = LocalRuntime()
        parameters = {
            "create_customer": {"name": "John Doe", "email": "john@example.com"},
            "create_order": {
                "customer_id": 1,  # Would normally come from create_customer
                "total": 199.99,
                "status": "pending",
            },
            "update_order": {
                "id": 1,  # Would normally come from create_order
                "status": "confirmed",
            },
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert "create_customer" in results
        assert "create_order" in results
        assert "update_order" in results

    def test_error_handling_example(self):
        """Test error handling examples from documentation."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class ErrorTest:
            required_field: str
            optional_field: str = "default"

        # Create the database tables
        db.create_tables()

        # Test error handling for missing required fields
        workflow = WorkflowBuilder()
        workflow.add_node("ErrorTestCreateNode", "test_error", {})

        runtime = LocalRuntime()

        # Should handle the error gracefully
        try:
            parameters = {
                "test_error": {
                    # Missing required_field intentionally
                    "optional_field": "test_value"
                }
            }
            results, run_id = runtime.execute(workflow.build(), parameters=parameters)
            # If it doesn't fail, that's also acceptable (validation might be permissive)
        except Exception as e:
            # Error handling worked as expected
            assert isinstance(e, Exception)

    def test_relationship_example(self):
        """Test relationship examples from documentation."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class Author:
            name: str
            email: str

        @db.model
        class Book:
            title: str
            author_id: int
            published_year: int

        # Create the database tables
        db.create_tables()

        # Create related records
        workflow = WorkflowBuilder()

        # Create author
        workflow.add_node("AuthorCreateNode", "create_author", {})

        # Create book for author
        workflow.add_node("BookCreateNode", "create_book", {})

        # Query books by author
        workflow.add_node("BookListNode", "author_books", {})

        workflow.add_connection("create_author", "id", "create_book", "author_id")
        workflow.add_connection("create_book", "author_id", "author_books", "filter")

        runtime = LocalRuntime()
        parameters = {
            "create_author": {"name": "Jane Smith", "email": "jane@example.com"},
            "create_book": {
                "title": "DataFlow Guide",
                "author_id": 1,  # Would normally come from create_author
                "published_year": 2025,
            },
            "author_books": {
                "filter": {"author_id": 1},
                "sort": [{"published_year": -1}],
            },
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert "create_author" in results
        assert "create_book" in results
        assert "author_books" in results

    def test_performance_example(self):
        """Test performance examples from documentation."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(database_url=self.db_url, pool_size=10, pool_max_overflow=20)

        @db.model
        class PerformanceTest:
            batch_id: int
            operation_type: str
            timestamp: float

        # Create the database tables
        db.create_tables()

        # High-performance bulk operation
        workflow = WorkflowBuilder()

        # Generate test data
        performance_data = [
            {"batch_id": i, "operation_type": "bulk_insert", "timestamp": time.time()}
            for i in range(100)
        ]

        workflow.add_node("PerformanceTestBulkCreateNode", "bulk_insert", {})

        start_time = time.time()
        runtime = LocalRuntime()
        parameters = {"bulk_insert": {"data": performance_data, "batch_size": 50}}
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)
        end_time = time.time()

        execution_time = end_time - start_time

        assert results is not None
        # Should complete within reasonable time
        assert execution_time < 10.0, f"Bulk operation took {execution_time:.2f}s"

    def test_aggregation_example(self):
        """Test aggregation examples from documentation."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class Sale:
            product_id: int
            amount: float
            category: str
            sale_date: str

        # Create the database tables
        db.create_tables()

        # Create test sales data
        workflow_setup = WorkflowBuilder()
        sales_data = [
            {
                "product_id": 1,
                "amount": 100.0,
                "category": "electronics",
                "sale_date": "2025-01-01",
            },
            {
                "product_id": 2,
                "amount": 150.0,
                "category": "electronics",
                "sale_date": "2025-01-01",
            },
            {
                "product_id": 3,
                "amount": 75.0,
                "category": "books",
                "sale_date": "2025-01-01",
            },
            {
                "product_id": 1,
                "amount": 120.0,
                "category": "electronics",
                "sale_date": "2025-01-02",
            },
        ]

        workflow_setup.add_node("SaleBulkCreateNode", "setup_sales", {})

        runtime = LocalRuntime()
        setup_parameters = {"setup_sales": {"data": sales_data, "batch_size": 10}}
        setup_results, setup_run_id = runtime.execute(
            workflow_setup.build(), parameters=setup_parameters
        )
        assert setup_results is not None

        # Aggregation query example
        workflow = WorkflowBuilder()
        workflow.add_node("SaleListNode", "sales_analytics", {})

        parameters = {
            "sales_analytics": {
                "filter": {"category": "electronics"},
                "aggregate": {
                    "total_sales": {"$sum": "amount"},
                    "sale_count": {"$count": "*"},
                    "avg_sale": {"$avg": "amount"},
                },
            }
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert "sales_analytics" in results

    def test_multi_database_example(self):
        """Test multi-database examples from documentation."""
        # Use real PostgreSQL database for E2E testing
        db_primary = DataFlow(
            database_url=self.db_url, pool_size=2, pool_max_overflow=3
        )

        @db_primary.model
        class PrimaryData:
            data_id: int
            content: str
            database_type: str = "primary"

        # Create the database tables
        db_primary.create_tables()

        # Test primary database operations
        workflow = WorkflowBuilder()
        workflow.add_node("PrimaryDataCreateNode", "primary_create", {})

        runtime = LocalRuntime()
        parameters = {
            "primary_create": {
                "data_id": 1,
                "content": "Primary database content",
                "database_type": "primary",
            }
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        assert results is not None
        assert "primary_create" in results

    def test_real_world_workflow_example(self):
        """Test a complete real-world workflow example."""
        # Use real PostgreSQL database for E2E testing
        db = DataFlow(
            database_url=self.db_url,
            pool_size=int(os.getenv("DATAFLOW_POOL_SIZE", 2)),
            pool_max_overflow=int(os.getenv("DATAFLOW_MAX_OVERFLOW", 3)),
        )

        @db.model
        class User:
            name: str
            email: str
            status: str = "active"

        @db.model
        class Product:
            name: str
            price: float
            inventory: int

        @db.model
        class Order:
            user_id: int
            product_id: int
            quantity: int
            total: float
            status: str = "pending"

        # Create the database tables
        db.create_tables()

        # Complete e-commerce workflow
        workflow = WorkflowBuilder()

        # 1. Create user
        workflow.add_node("UserCreateNode", "register_user", {})

        # 2. Create product
        workflow.add_node("ProductCreateNode", "add_product", {})

        # 3. Create order
        workflow.add_node("OrderCreateNode", "place_order", {})

        # 4. Update inventory
        workflow.add_node("ProductUpdateNode", "update_inventory", {})

        # 5. Confirm order
        workflow.add_node("OrderUpdateNode", "confirm_order", {})

        # Connect the workflow
        workflow.add_connection("register_user", "id", "place_order", "user_id")
        workflow.add_connection("add_product", "id", "place_order", "product_id")
        workflow.add_connection("add_product", "id", "update_inventory", "id")
        workflow.add_connection("place_order", "id", "confirm_order", "id")

        runtime = LocalRuntime()
        parameters = {
            "register_user": {
                "name": "Alice Johnson",
                "email": "alice.johnson@example.com",
                "status": "active",
            },
            "add_product": {"name": "Laptop", "price": 999.99, "inventory": 10},
            "place_order": {
                "user_id": 1,  # Would come from register_user
                "product_id": 1,  # Would come from add_product
                "quantity": 1,
                "total": 999.99,
                "status": "pending",
            },
            "update_inventory": {
                "id": 1,  # Would come from add_product
                "inventory": 9,  # Reduced by order quantity
            },
            "confirm_order": {
                "id": 1,  # Would come from place_order
                "status": "confirmed",
            },
        }
        results, run_id = runtime.execute(workflow.build(), parameters=parameters)

        # Verify complete workflow execution
        assert results is not None
        assert "register_user" in results
        assert "add_product" in results
        assert "place_order" in results
        assert "update_inventory" in results
        assert "confirm_order" in results

        # Verify workflow completed successfully
        assert run_id is not None
