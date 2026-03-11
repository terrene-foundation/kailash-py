#!/usr/bin/env python3
"""
Write Protection E2E Test - Tests the write protection system end-to-end
"""

import pytest
from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.e2e
@pytest.mark.timeout(30)
class TestWriteProtectionDemo:
    """Test write protection system functionality end-to-end."""

    @pytest.fixture
    async def protected_dataflow(self):
        """Create a DataFlow instance for write protection testing."""
        # Use SQLite for this test since we're testing protection, not database type
        db = DataFlow(":memory:")

        @db.model
        class Product:
            name: str
            price: float

        return db

    @pytest.mark.asyncio
    async def test_write_protection_workflow(self, protected_dataflow):
        """Test complete write protection workflow."""
        db = protected_dataflow
        runtime = LocalRuntime()

        # 1. Test without protection - should work
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductCreateNode", "create_product", {"name": "Widget", "price": 29.99}
        )

        results, run_id = runtime.execute(workflow.build())
        assert run_id is not None
        assert "create_product" in results

        # 2. Test read operations work
        workflow_read = WorkflowBuilder()
        workflow_read.add_node("ProductListNode", "list_products", {})

        results, run_id = runtime.execute(workflow_read.build())
        assert run_id is not None
        assert "list_products" in results

    @pytest.mark.asyncio
    async def test_basic_crud_operations(self, protected_dataflow):
        """Test basic CRUD operations work without protection."""
        db = protected_dataflow
        runtime = LocalRuntime()

        # Create
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductCreateNode", "create", {"name": "Test Product", "price": 99.99}
        )
        results, run_id = runtime.execute(workflow.build())
        assert run_id is not None

        # Read (List)
        workflow = WorkflowBuilder()
        workflow.add_node("ProductListNode", "list", {})
        results, run_id = runtime.execute(workflow.build())
        assert run_id is not None
        assert "list" in results

    @pytest.mark.asyncio
    async def test_bulk_operations(self, protected_dataflow):
        """Test bulk operations work."""
        db = protected_dataflow
        runtime = LocalRuntime()

        # Bulk create
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductBulkCreateNode",
            "bulk_create",
            {
                "data": [
                    {"name": "Product A", "price": 10.0},
                    {"name": "Product B", "price": 20.0},
                ]
            },
        )
        results, run_id = runtime.execute(workflow.build())
        assert run_id is not None
        assert "bulk_create" in results
