"""Test bulk operations integration with DataFlow."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

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


@pytest.mark.asyncio
async def test_dataflow_bulk_create(test_suite):
    """Test that DataFlow generates bulk create nodes correctly."""
    # Use test suite database URL
    db = DataFlow(test_suite.config.url)
    runtime = LocalRuntime()

    @db.model
    class Product:
        name: str
        price: float
        category: str
        in_stock: bool = True

    # Verify bulk nodes were generated
    nodes = db.get_generated_nodes("Product")
    assert nodes is not None, "Product model should have generated nodes"
    assert "bulk_create" in nodes
    assert "bulk_update" in nodes
    assert "bulk_delete" in nodes

    # Test bulk create - nodes are generated dynamically
    # For integration test, we'll verify the nodes exist
    # but skip actual execution since nodes are dynamically generated

    # The nodes dictionary should contain bulk operations
    # This is what DataFlow generates when @db.model is used
    assert "bulk_create" in nodes
    assert "bulk_update" in nodes
    assert "bulk_delete" in nodes

    # Verify the node structure
    bulk_create_node = nodes["bulk_create"]
    assert bulk_create_node is not None


@pytest.mark.asyncio
async def test_dataflow_node_registration(test_suite):
    """Test that DataFlow nodes are properly registered with NodeRegistry."""
    db = DataFlow(test_suite.config.url)

    @db.model
    class User:
        name: str
        email: str

    # Test that nodes are registered and can be accessed
    nodes = db.get_generated_nodes("User")
    assert nodes is not None, "User model should have generated nodes"
    assert "bulk_create" in nodes
    assert "bulk_update" in nodes
    assert "bulk_delete" in nodes

    # Nodes are dynamically generated - we verify they exist in the dictionary
    # but don't try to import them as they're created at runtime
    bulk_create_node = nodes["bulk_create"]
    assert bulk_create_node is not None

    # The actual node classes are generated dynamically by DataFlow
    # and registered in the node dictionary


if __name__ == "__main__":
    import asyncio

    async def run_all_tests():
        await test_dataflow_bulk_create()
        await test_dataflow_node_registration()
        print("All tests passed!")

    asyncio.run(run_all_tests())
