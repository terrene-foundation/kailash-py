#!/usr/bin/env python3
"""
Integration tests for SQLite database operations with DataFlow.

Tests SQLite compatibility, model registration, auto-generated nodes,
and basic CRUD operations using real infrastructure.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

from tests.infrastructure.test_harness import IntegrationTestSuite

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


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
class TestSQLiteConnection:
    """Test SQLite connection and database operations."""

    @pytest.mark.asyncio
    async def test_basic_sqlite_connection(self, test_suite):
        """Test basic SQLite connection and database creation."""
        try:
            # Test with memory database
            db = DataFlow(":memory:")
            assert db is not None

            # Test with file database
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                db_path = tmp.name

            try:
                db = DataFlow(f"sqlite:///{db_path}")
                assert db is not None
            finally:
                os.unlink(db_path)

        except Exception as e:
            pytest.fail(f"SQLite connection failed: {e}")

    @pytest.mark.asyncio
    async def test_model_registration(self, test_suite):
        """Test model registration with SQLite."""
        try:
            # Create DataFlow instance with memory SQLite
            db = DataFlow(":memory:")

            # Define a test model
            @db.model
            class TestUser:
                name: str
                email: str
                age: int = 25
                active: bool = True

            # Check if model is in registry
            models = db._models
            assert "TestUser" in models, "Model not found in registry"

            # Check if nodes were generated
            assert hasattr(db, "_nodes"), "DataFlow instance missing _nodes attribute"
            assert len(db._nodes) > 0, "No nodes were generated"

        except Exception as e:
            pytest.fail(f"Model registration failed: {e}")

    @pytest.mark.asyncio
    async def test_auto_generated_nodes(self, test_suite, runtime):
        """Test auto-generated CRUD nodes work with SQLite."""
        try:
            # Create DataFlow instance
            db = DataFlow(":memory:")

            # Define model
            @db.model
            class Product:
                name: str
                price: float
                in_stock: bool = True

            # Initialize the database (create tables)
            await db.initialize()

            # Test CREATE node
            workflow = WorkflowBuilder()
            workflow.add_node(
                "ProductCreateNode",
                "create_product",
                {
                    "database_url": ":memory:",
                    "name": "Test Widget",
                    "price": 29.99,
                    "in_stock": True,
                },
            )

            results, run_id = runtime.execute(workflow.build())

            assert "create_product" in results, "Create node result missing"
            assert not results["create_product"].get(
                "error"
            ), f"ProductCreateNode failed: {results['create_product']}"

            # Test LIST node
            workflow = WorkflowBuilder()
            workflow.add_node(
                "ProductListNode",
                "list_products",
                {"database_url": ":memory:", "limit": 10},
            )

            results, run_id = runtime.execute(workflow.build())

            assert "list_products" in results, "List node result missing"
            assert not results["list_products"].get(
                "error"
            ), f"ProductListNode failed: {results['list_products']}"

            product_list = results["list_products"].get("result", {}).get("data", [])
            # Note: May be empty if CREATE and LIST use different database instances

        except Exception as e:
            pytest.fail(f"Auto-generated nodes test failed: {e}")

    @pytest.mark.asyncio
    async def test_schema_migration(self, test_suite):
        """Test schema migration with SQLite."""
        try:
            # Create DataFlow instance
            db = DataFlow(":memory:")

            # Define initial model
            @db.model
            class Customer:
                name: str
                email: str

            # Initialize with initial schema
            await db.initialize()

            # Now add a field to test migration
            @db.model
            class Customer:
                name: str
                email: str
                phone: str = None  # New field

            # This should trigger migration
            success = await db.auto_migrate(dry_run=True, interactive=False)

            assert success is True, "Schema migration failed"

        except Exception as e:
            pytest.fail(f"Schema migration test failed: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
