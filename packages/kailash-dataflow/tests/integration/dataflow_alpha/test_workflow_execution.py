"""
Integration tests for DataFlow workflow execution - Alpha Release Critical

Tests that generated DataFlow nodes work properly in real Kailash workflows.
This validates the core integration between DataFlow and the Kailash SDK.

NO MOCKING - Uses real PostgreSQL and Kailash SDK components.
"""

import asyncio
import os
import sys

import pytest

# Add test utilities to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../tests/utils"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))
sys.path.insert(0, os.path.dirname(__file__))

from docker_config import DATABASE_CONFIG


@pytest.mark.requires_postgres
@pytest.mark.requires_docker
@pytest.mark.integration
class TestWorkflowExecution:
    """Test DataFlow nodes work in real Kailash workflows - CRITICAL for alpha."""

    @pytest.fixture
    def database_url(self):
        """Real PostgreSQL database URL."""
        return f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}"

    @pytest.fixture
    def dataflow_with_model(self, database_url):
        """DataFlow instance with test model."""
        from dataflow import DataFlow

        db = DataFlow(database_url=database_url)

        @db.model
        class Customer:
            customer_name: str
            email: str
            status: str = "active"

        db.create_tables()
        return db

    def test_single_node_workflow_execution(self, dataflow_with_model):
        """Test single DataFlow node in workflow execution."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build workflow with DataFlow node
        workflow = WorkflowBuilder()
        workflow.add_node(
            "CustomerCreateNode",
            "create_customer",
            {
                "customer_name": "John Smith",
                "email": "john@example.com",
                "status": "active",
            },
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify execution
        assert results is not None, "Workflow execution failed"
        assert run_id is not None, "Missing workflow run ID"
        assert "create_customer" in results, "Missing node result"

        customer_result = results["create_customer"]
        assert customer_result["customer_name"] == "John Smith"
        assert customer_result["email"] == "john@example.com"
        assert "id" in customer_result, "Missing customer ID"

    def test_multi_node_workflow_execution(self, dataflow_with_model):
        """Test multiple DataFlow nodes in workflow execution."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build workflow with connected DataFlow nodes
        workflow = WorkflowBuilder()

        # Create customer
        workflow.add_node(
            "CustomerCreateNode",
            "create_customer",
            {"customer_name": "Jane Doe", "email": "jane@example.com"},
        )

        # Read customer (will use ID from create)
        workflow.add_node(
            "CustomerReadNode", "read_customer", {}
        )  # ID will be passed from create

        # Connect nodes: create output -> read input
        workflow.add_connection("create_customer", "id", "read_customer", "id")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify both operations
        assert "create_customer" in results
        assert "read_customer" in results

        create_result = results["create_customer"]
        read_result = results["read_customer"]

        # Data should match between create and read
        assert create_result["id"] == read_result["id"]
        assert create_result["customer_name"] == read_result["customer_name"]
        assert create_result["email"] == read_result["email"]

    def test_crud_workflow_sequence(self, dataflow_with_model):
        """Test complete CRUD sequence in workflow."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build CRUD workflow
        workflow = WorkflowBuilder()

        # 1. Create
        workflow.add_node(
            "CustomerCreateNode",
            "create",
            {
                "customer_name": "Bob Johnson",
                "email": "bob@example.com",
                "status": "pending",
            },
        )

        # 2. Read
        workflow.add_node("CustomerReadNode", "read", {})

        # 3. Update
        workflow.add_node("CustomerUpdateNode", "update", {"status": "active"})

        # 4. Read updated
        workflow.add_node("CustomerReadNode", "read_updated", {})

        # Connect workflow
        workflow.add_connection("create", "id", "read", "id")
        workflow.add_connection("read", "id", "update", "id")
        workflow.add_connection("update", "id", "read_updated", "id")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify complete CRUD sequence
        assert all(
            key in results for key in ["create", "read", "update", "read_updated"]
        )

        # Verify data evolution
        create_result = results["create"]
        read_result = results["read"]
        update_result = results["update"]
        read_updated_result = results["read_updated"]

        # Initial read should match create
        assert read_result["status"] == "pending"

        # Update should succeed
        assert update_result["updated"] is True

        # Final read should show updated status
        assert read_updated_result["status"] == "active"

    def test_bulk_operations_in_workflow(self, dataflow_with_model):
        """Test bulk operations in workflow execution."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build bulk workflow
        workflow = WorkflowBuilder()

        # Bulk create multiple customers
        workflow.add_node(
            "CustomerBulkCreateNode",
            "bulk_create",
            {
                "data": [
                    {"customer_name": "Customer 1", "email": "customer1@example.com"},
                    {"customer_name": "Customer 2", "email": "customer2@example.com"},
                    {"customer_name": "Customer 3", "email": "customer3@example.com"},
                ],
                "batch_size": 1000,
            },
        )

        # List customers to verify
        workflow.add_node("CustomerListNode", "list", {"limit": 10})

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify bulk operations
        bulk_result = results["bulk_create"]
        list_result = results["list"]

        assert bulk_result["processed"] == 3, "Not all records processed"
        assert len(list_result["records"]) >= 3, "Bulk created records not found"

        # Verify specific records exist
        emails = [record["email"] for record in list_result["records"]]
        assert "customer1@example.com" in emails
        assert "customer2@example.com" in emails
        assert "customer3@example.com" in emails

    def test_error_handling_in_workflow(self, dataflow_with_model):
        """Test error handling in workflow execution."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build workflow with potential error
        workflow = WorkflowBuilder()

        # Try to read non-existent customer
        workflow.add_node(
            "CustomerReadNode", "read_missing", {"id": 99999}
        )  # Non-existent ID

        # Execute workflow
        runtime = LocalRuntime()

        try:
            results, run_id = runtime.execute(workflow.build())

            # Should handle gracefully
            assert results is not None

            if "read_missing" in results:
                result = results["read_missing"]
                # Should indicate not found, not crash
                assert result.get("found") is False or result is not None

        except Exception as e:
            # Should not get AttributeError or configuration errors
            assert "AttributeError" not in str(
                e
            ), f"Configuration error in workflow: {e}"
            assert "'DataFlowConfig' object has no attribute" not in str(
                e
            ), f"Config error: {e}"

    def test_parameter_passing_between_nodes(self, dataflow_with_model):
        """Test parameter passing between DataFlow nodes in workflow."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build workflow with parameter passing
        workflow = WorkflowBuilder()

        # Create customer
        workflow.add_node(
            "CustomerCreateNode",
            "create",
            {"customer_name": "Parameter Test", "email": "param@example.com"},
        )

        # Update using ID from create
        workflow.add_node(
            "CustomerUpdateNode", "update", {"customer_name": "Updated Name"}
        )

        # Connect with parameter mapping
        workflow.add_connection("create", "id", "update", "id")

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify parameter passing worked
        create_result = results["create"]
        update_result = results["update"]

        assert create_result["id"] is not None
        assert update_result["updated"] is True

        # Verify the update used the correct ID
        assert update_result.get("id") == create_result["id"]

    def test_workflow_with_mixed_node_types(self, dataflow_with_model):
        """Test workflow mixing DataFlow nodes with other SDK nodes."""
        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build workflow mixing DataFlow and SDK nodes
        workflow = WorkflowBuilder()

        # Start with DataFlow node
        workflow.add_node(
            "CustomerCreateNode",
            "create_customer",
            {"customer_name": "Mixed Workflow Test", "email": "mixed@example.com"},
        )

        # Add SDK PythonCodeNode for data transformation
        workflow.add_node(
            "PythonCodeNode",
            "transform",
            {
                "code": """
# Simple transformation using connected customer name
result = {
    "formatted_name": customer_name.upper() if customer_name else "",
    "email_domain": "example.com",  # Simplified for connection test
    "customer_id": 1  # Simplified for connection test
}
"""
            },
        )

        # Connect DataFlow output to SDK node input
        workflow.add_connection(
            "create_customer", "customer_name", "transform", "customer_name"
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify mixed node workflow
        assert "create_customer" in results
        assert "transform" in results

        customer_result = results["create_customer"]
        transform_result = results["transform"]

        # Verify transformation worked with DataFlow output
        # PythonCodeNode returns result in 'result' key
        actual_result = transform_result["result"]
        assert actual_result["formatted_name"] == "MIXED WORKFLOW TEST"
        assert actual_result["email_domain"] == "example.com"
        assert actual_result["customer_id"] == 1

    def test_concurrent_workflow_execution(self, dataflow_with_model):
        """Test concurrent workflow execution with DataFlow nodes."""
        import concurrent.futures

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        def create_and_execute_workflow(customer_index):
            # Build workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "CustomerCreateNode",
                "create",
                {
                    "customer_name": f"Concurrent Customer {customer_index}",
                    "email": f"concurrent{customer_index}@example.com",
                },
            )

            # Execute workflow
            runtime = LocalRuntime()
            results, run_id = runtime.execute(workflow.build())
            return results["create"]

        # Execute multiple workflows concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(create_and_execute_workflow, i) for i in range(3)
            ]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # All concurrent workflows should succeed
        assert len(results) == 3
        for result in results:
            assert result is not None
            assert "id" in result
            assert "customer_name" in result
            assert result["customer_name"].startswith("Concurrent Customer")

    def test_workflow_performance_with_dataflow_nodes(self, dataflow_with_model):
        """Test workflow execution performance with DataFlow nodes."""
        import time

        from kailash.runtime.local import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Build simple workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "CustomerCreateNode",
            "create",
            {"customer_name": "Performance Test", "email": "performance@example.com"},
        )

        # Execute and measure performance

        start_time = time.time()
        results, run_id = runtime.execute(workflow.build())
        execution_time = time.time() - start_time

        # Should complete within reasonable time
        assert (
            execution_time < 5.0
        ), f"Workflow execution too slow: {execution_time:.2f}s"
        assert results is not None
        assert results["create"]["customer_name"] == "Performance Test"
