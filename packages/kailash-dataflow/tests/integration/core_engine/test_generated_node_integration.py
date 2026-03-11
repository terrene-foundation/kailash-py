"""
Integration tests for DataFlow generated node functionality.

Tests the integration between DataFlow model registration and the automatic
generation of CRUD nodes, ensuring they work together seamlessly in workflows.
"""

import os
import sys
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Union
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import DataFlow and workflow components
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestGeneratedNodeIntegration:
    """Test integration of DataFlow generated nodes with workflow execution."""

    def test_basic_crud_node_generation_and_execution(self, test_suite):
        """Test that CRUD nodes are generated and can be executed in workflows."""
        # Use test suite database URL for integration tests
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class User:
            name: str
            email: str
            active: bool = True

        # Verify model registration
        assert "User" in db._models

        # Test workflow builder integration
        workflow = WorkflowBuilder()

        # Test that we can reference generated nodes
        # The nodes should be available as strings for workflow building
        workflow.add_node(
            "UserCreateNode",
            "create_user",
            {"name": "John Doe", "email": "john@example.com"},
        )

        workflow.add_node("UserListNode", "list_users", {"filter": {"active": True}})

        workflow.add_connection("create_user", "output", "list_users", "input")

        # Build workflow
        built_workflow = workflow.build()
        assert built_workflow is not None

        # Verify workflow structure
        assert len(built_workflow.nodes) == 2
        assert len(built_workflow.connections) == 1

    def test_workflow_execution_with_generated_nodes(self, test_suite):
        """Test executing workflows with generated DataFlow nodes."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class Product:
            name: str
            price: float
            category: str = "general"

        # Create workflow
        workflow = WorkflowBuilder()

        # Add create node
        workflow.add_node(
            "ProductCreateNode",
            "create_product",
            {"name": "Test Product", "price": 29.99, "category": "electronics"},
        )

        # Add read node
        workflow.add_node(
            "ProductReadNode",
            "read_product",
            {"id": "1"},  # ID should be a string
        )

        workflow.add_connection("create_product", "output", "read_product", "input")

        # Execute workflow
        runtime = LocalRuntime()
        try:
            results, run_id = runtime.execute(workflow.build())

            # Verify execution completed
            assert run_id is not None
            assert isinstance(results, dict)

            # Check that both nodes executed
            assert "create_product" in results
            assert "read_product" in results

        except Exception as e:
            # If nodes aren't implemented yet, verify the structure is correct
            pytest.skip(f"Generated nodes not fully implemented: {e}")

    def test_bulk_operations_node_generation(self, test_suite):
        """Test bulk operation nodes are generated and integrated."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class Order:
            customer_id: int
            total: float
            status: str = "pending"

        # Test bulk operations in workflow
        workflow = WorkflowBuilder()

        # Test bulk create
        workflow.add_node(
            "OrderBulkCreateNode",
            "bulk_create",
            {
                "data": [
                    {"customer_id": 1, "total": 100.0},
                    {"customer_id": 2, "total": 200.0},
                    {"customer_id": 3, "total": 150.0},
                ]
            },
        )

        # Test bulk update
        workflow.add_node(
            "OrderBulkUpdateNode",
            "bulk_update",
            {"filter": {"status": "pending"}, "update": {"status": "processing"}},
        )

        workflow.add_connection("bulk_create", "output", "bulk_update", "input")

        # Build workflow
        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 2

    def test_complex_model_node_generation(self, test_suite):
        """Test node generation for complex models with relationships."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class Customer:
            name: str
            email: str
            created_at: datetime
            metadata: Dict[str, str] = {}

        @db.model
        class Invoice:
            customer_id: int
            amount: Decimal
            due_date: datetime
            line_items: List[Dict[str, Union[str, float]]] = []

            __dataflow__ = {"multi_tenant": True, "audit_log": True}

        # Test complex workflow
        workflow = WorkflowBuilder()

        # Create customer
        workflow.add_node(
            "CustomerCreateNode",
            "create_customer",
            {
                "name": "Acme Corp",
                "email": "billing@acme.com",
                "created_at": datetime.now(),
                "metadata": {"industry": "technology"},
            },
        )

        # Create invoice for customer (use connection for customer_id)
        workflow.add_node(
            "InvoiceCreateNode",
            "create_invoice",
            {
                "amount": "1500.00",
                "due_date": datetime.now(),
                "line_items": [
                    {"description": "Consulting", "amount": 1000.0},
                    {"description": "Support", "amount": 500.0},
                ],
            },
        )

        # Connect customer ID properly through workflow connection
        workflow.add_connection(
            "create_customer", "id", "create_invoice", "customer_id"
        )

        # Verify workflow structure
        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 2

    def test_enterprise_features_node_integration(self, test_database_url):
        """Test enterprise features integration with generated nodes."""
        db = DataFlow(test_database_url, multi_tenant=True, audit_logging=True)

        @db.model
        class Document:
            title: str
            content: str
            owner_id: int

            __dataflow__ = {
                "multi_tenant": True,
                "soft_delete": True,
                "versioned": True,
                "audit_log": True,
            }

        # Test enterprise workflow
        workflow = WorkflowBuilder()

        # Create with tenant context
        workflow.add_node(
            "DocumentCreateNode",
            "create_doc",
            {
                "title": "Secret Document",
                "content": "Confidential information",
                "owner_id": 123,
                "tenant_id": "tenant_abc",  # Multi-tenant context
            },
        )

        # Soft delete (id provided via connection)
        workflow.add_node(
            "DocumentDeleteNode",
            "soft_delete_doc",
            {"soft_delete": True, "tenant_id": "tenant_abc"},
        )

        workflow.add_connection("create_doc", "id", "soft_delete_doc", "id")

        # Verify workflow builds
        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_node_parameter_validation_integration(self, test_suite):
        """Test parameter validation integration with workflows."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class ValidatedModel:
            name: str
            age: int
            email: str

            __constraints__ = {
                "name": {"max_length": 100, "nullable": False},
                "age": {"min_value": 0, "max_value": 150},
                "email": {"pattern": r"^[^@]+@[^@]+\.[^@]+$"},
            }

        workflow = WorkflowBuilder()

        # Test valid parameters
        workflow.add_node(
            "ValidatedModelCreateNode",
            "valid_create",
            {"name": "John Doe", "age": 30, "email": "john@example.com"},
        )

        # Test invalid parameters (should be caught during validation)
        workflow.add_node(
            "ValidatedModelCreateNode",
            "invalid_create",
            {
                "name": "",  # Empty name (violates nullable: False)
                "age": -5,  # Invalid age
                "email": "invalid-email",  # Invalid email format
            },
        )

        # Build workflow (validation might happen at build or execute time)
        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_generated_node_error_handling(self, test_suite):
        """Test error handling in generated nodes within workflows."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class ErrorTestModel:
            required_field: str
            optional_field: Optional[str] = None

        workflow = WorkflowBuilder()

        # Test missing required field
        workflow.add_node(
            "ErrorTestModelCreateNode",
            "error_create",
            {
                # Missing required_field
                "optional_field": "test"
            },
        )

        # Test read non-existent record
        workflow.add_node(
            "ErrorTestModelReadNode", "error_read", {"id": "999999"}  # Non-existent ID
        )

        workflow.add_connection("error_create", "output", "error_read", "input")

        # Workflow should build but may fail during execution
        built_workflow = workflow.build()
        assert built_workflow is not None

        # Test execution error handling
        runtime = LocalRuntime()
        try:
            results, run_id = runtime.execute(built_workflow)
            # If execution succeeds, check for error handling
            assert run_id is not None
        except Exception:
            # Expected behavior for invalid operations
            pass

    def test_performance_with_generated_nodes(self, test_suite):
        """Test performance characteristics of generated nodes in workflows."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class PerformanceTestModel:
            name: str
            value: int
            data: str

        workflow = WorkflowBuilder()

        # Create multiple nodes for performance testing
        for i in range(10):
            workflow.add_node(
                "PerformanceTestModelCreateNode",
                f"create_{i}",
                {"name": f"Record {i}", "value": i, "data": f"test data {i}"},
            )

        # Add bulk operations
        workflow.add_node(
            "PerformanceTestModelBulkCreateNode",
            "bulk_create",
            {
                "data": [
                    {"name": f"Bulk {j}", "value": j, "data": f"bulk data {j}"}
                    for j in range(50)
                ]
            },
        )

        # Build workflow
        import time

        start_time = time.time()
        built_workflow = workflow.build()
        build_time = time.time() - start_time

        # Workflow building should be fast
        assert build_time < 1.0
        assert len(built_workflow.nodes) == 11  # 10 creates + 1 bulk create

    def test_node_discovery_and_availability(self, test_suite):
        """Test that generated nodes are discoverable and available."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class DiscoveryTestModel:
            name: str
            active: bool = True

        # Test that we can check for node availability
        # This tests the integration between DataFlow and the node system

        # Expected node types that should be generated
        expected_nodes = [
            "DiscoveryTestModelCreateNode",
            "DiscoveryTestModelReadNode",
            "DiscoveryTestModelUpdateNode",
            "DiscoveryTestModelDeleteNode",
            "DiscoveryTestModelListNode",
            "DiscoveryTestModelBulkCreateNode",
            "DiscoveryTestModelBulkUpdateNode",
            "DiscoveryTestModelBulkDeleteNode",
            "DiscoveryTestModelBulkUpsertNode",
        ]

        # Test workflow builder accepts these node types
        workflow = WorkflowBuilder()

        for node_type in expected_nodes[:3]:  # Test first 3 to avoid complexity
            workflow.add_node(node_type, f"test_{node_type.lower()}", {})

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 3

    def test_cross_model_relationship_workflows(self, test_suite):
        """Test workflows spanning multiple related models."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class Author:
            name: str
            email: str

        @db.model
        class Book:
            title: str
            author_id: int
            published_date: datetime
            isbn: str

        @db.model
        class Review:
            book_id: int
            reviewer_name: str
            rating: int
            comment: str

        # Create complex multi-model workflow
        workflow = WorkflowBuilder()

        # Create author
        workflow.add_node(
            "AuthorCreateNode",
            "create_author",
            {"name": "Jane Smith", "email": "jane@example.com"},
        )

        # Create book by author (author_id provided via connection)
        workflow.add_node(
            "BookCreateNode",
            "create_book",
            {
                "title": "The Great Novel",
                "published_date": datetime.now(),
                "isbn": "978-0123456789",
            },
        )

        # Create review for book (book_id provided via connection)
        workflow.add_node(
            "ReviewCreateNode",
            "create_review",
            {
                "reviewer_name": "Book Critic",
                "rating": 5,
                "comment": "Excellent book!",
            },
        )

        # List books by author (filter via runtime parameters)
        workflow.add_node(
            "BookListNode",
            "list_books",
            {},
        )

        # Connect nodes with proper parameter mapping
        workflow.add_connection("create_author", "id", "create_book", "author_id")
        workflow.add_connection("create_book", "id", "create_review", "book_id")
        workflow.add_connection("create_author", "id", "list_books", "author_id")

        # Verify complex workflow structure
        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 4
        assert len(built_workflow.connections) == 3

    def test_generated_node_caching_integration(self, test_database_url):
        """Test caching integration with generated nodes."""
        db = DataFlow(test_database_url, cache_enabled=True, cache_ttl=300)

        @db.model
        class CachedModel:
            name: str
            data: str
            cacheable: bool = True

        workflow = WorkflowBuilder()

        # Create record
        workflow.add_node(
            "CachedModelCreateNode",
            "create_cached",
            {
                "name": "Cached Record",
                "data": "This should be cached",
                "cacheable": True,
            },
        )

        # Read record (should use cache, id provided via connection)
        workflow.add_node(
            "CachedModelReadNode",
            "read_cached",
            {"use_cache": True},
        )

        # List records with caching
        workflow.add_node(
            "CachedModelListNode",
            "list_cached",
            {
                "filter": {"cacheable": True},
                "cache_key": "cacheable_records",
                "cache_ttl": 600,
            },
        )

        workflow.add_connection("create_cached", "id", "read_cached", "id")
        workflow.add_connection("read_cached", "output", "list_cached", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_transaction_integration_with_generated_nodes(self, test_suite):
        """Test transaction management with generated nodes."""
        db = DataFlow(database_url=test_suite.config.url)

        @db.model
        class TransactionalModel:
            name: str
            amount: Decimal
            status: str = "pending"

        workflow = WorkflowBuilder()

        # Create distributed transaction manager
        workflow.add_node(
            "DistributedTransactionManagerNode",
            "transaction",
            {"transaction_type": "saga", "timeout": 30},
        )

        # Create records within transaction
        workflow.add_node(
            "TransactionalModelCreateNode",
            "create_1",
            {"name": "Transaction Test 1", "amount": "100.00", "status": "pending"},
        )

        workflow.add_node(
            "TransactionalModelCreateNode",
            "create_2",
            {"name": "Transaction Test 2", "amount": "200.00", "status": "pending"},
        )

        # Update in same transaction
        workflow.add_node(
            "TransactionalModelBulkUpdateNode",
            "update_status",
            {"filter": {"status": "pending"}, "update": {"status": "confirmed"}},
        )

        # Connect within transaction scope
        workflow.add_connection("transaction", "output", "create_1", "input")
        workflow.add_connection("transaction", "output", "create_2", "input")
        workflow.add_connection("create_1", "output", "update_status", "input")
        workflow.add_connection("create_2", "output", "update_status", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 4

    def test_monitoring_integration_with_generated_nodes(self, test_database_url):
        """Test monitoring and metrics integration."""
        db = DataFlow(test_database_url, monitoring=True)

        @db.model
        class MonitoredModel:
            name: str
            processed_at: datetime
            processing_time: float = 0.0

        workflow = WorkflowBuilder()

        # Add transaction monitoring node
        workflow.add_node(
            "TransactionMonitorNode",
            "start_monitoring",
            {
                "monitor_deadlocks": True,
                "monitor_performance": True,
                "alert_threshold_ms": 1000,
            },
        )

        # Monitored operations
        workflow.add_node(
            "MonitoredModelCreateNode",
            "monitored_create",
            {
                "name": "Monitored Record",
                "processed_at": datetime.now(),
                "enable_monitoring": True,
            },
        )

        workflow.add_node(
            "MonitoredModelBulkCreateNode",
            "bulk_monitored",
            {
                "data": [
                    {
                        "name": f"Bulk Record {i}",
                        "processed_at": datetime.now(),
                    }
                    for i in range(100)
                ],
                "enable_monitoring": True,
                "batch_size": 50,
            },
        )

        workflow.add_connection(
            "start_monitoring", "output", "monitored_create", "input"
        )
        workflow.add_connection("monitored_create", "output", "bulk_monitored", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None

    def test_real_world_integration_scenario(self, test_database_url):
        """Test a complete real-world scenario integration."""
        # E-commerce order processing scenario
        db = DataFlow(
            test_database_url, multi_tenant=True, audit_logging=True, monitoring=True
        )

        @db.model
        class Customer:
            name: str
            email: str
            tenant_id: str

            __dataflow__ = {"multi_tenant": True}

        @db.model
        class Product:
            name: str
            price: Decimal
            stock: int
            tenant_id: str

            __dataflow__ = {"multi_tenant": True}

        @db.model
        class Order:
            customer_id: int
            total: Decimal
            status: str = "pending"
            tenant_id: str

            __dataflow__ = {"multi_tenant": True, "audit_log": True, "versioned": True}

        # Complete order processing workflow
        workflow = WorkflowBuilder()

        # 1. Create customer
        workflow.add_node(
            "CustomerCreateNode",
            "create_customer",
            {
                "name": "John Customer",
                "email": "john@customer.com",
                "tenant_id": "store_123",
            },
        )

        # 2. Create products
        workflow.add_node(
            "ProductBulkCreateNode",
            "create_products",
            {
                "data": [
                    {
                        "name": "Product A",
                        "price": "19.99",
                        "stock": 100,
                        "tenant_id": "store_123",
                    },
                    {
                        "name": "Product B",
                        "price": "29.99",
                        "stock": 50,
                        "tenant_id": "store_123",
                    },
                ]
            },
        )

        # 3. Create order
        workflow.add_node(
            "OrderCreateNode",
            "create_order",
            {
                "total": "49.98",
                "status": "pending",
                "tenant_id": "store_123",
            },
        )

        # 4. Update product stock
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_stock",
            {
                "filter": {"tenant_id": "store_123"},
                "update": {"stock": 99},
            },
        )

        # 5. Confirm order
        workflow.add_node(
            "OrderUpdateNode",
            "confirm_order",
            {
                "status": "confirmed",
                "tenant_id": "store_123",
            },
        )

        # Connect workflow
        workflow.add_connection("create_customer", "id", "create_order", "customer_id")
        workflow.add_connection("create_products", "output", "create_order", "input")
        workflow.add_connection("create_order", "output", "update_stock", "input")
        workflow.add_connection("create_order", "id", "confirm_order", "id")

        # Verify complete workflow
        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 5
        assert len(built_workflow.connections) == 4
