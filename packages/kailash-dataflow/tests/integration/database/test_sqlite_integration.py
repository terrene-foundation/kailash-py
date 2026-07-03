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

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


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
        # File-backed SQLite: a bare ":memory:" gives every pooled / per-node
        # connection its OWN in-memory database (the shared-cache URI rewrite in
        # SQLiteAdapter is not wired to the CRUD node hot path — tracked
        # separately). File-backed is the supported multi-connection config
        # (tests/CLAUDE.md), so CREATE and LIST share one database.
        fd, _db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        _db_url = f"sqlite:///{_db_path}"
        try:
            # Create DataFlow instance
            db = DataFlow(_db_url)

            # Define model
            @db.model
            class Product:
                name: str
                price: float
                in_stock: bool = True

            # Initialize the database (create tables)
            await db.initialize()

            # Test CREATE node. DataFlow-generated nodes use the registering
            # instance's database configuration internally — passing an explicit
            # database_url spins up a SEPARATE connection/pool that does not share
            # the instance's committed data, so it is omitted here.
            workflow = WorkflowBuilder()
            workflow.add_node(
                "ProductCreateNode",
                "create_product",
                {
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
                {"limit": 10},
            )

            results, run_id = runtime.execute(workflow.build())

            assert "list_products" in results, "List node result missing"
            assert not results["list_products"].get(
                "error"
            ), f"ProductListNode failed: {results['list_products']}"

            # CREATE and LIST share one file-backed database (both use the
            # instance config), so the created product MUST be visible to LIST.
            product_list = results["list_products"].get("records", [])
            assert any(
                p.get("name") == "Test Widget" for p in product_list
            ), f"Created product should be listed, got: {product_list}"

        except Exception as e:
            pytest.fail(f"Auto-generated nodes test failed: {e}")
        finally:
            if os.path.exists(_db_path):
                os.unlink(_db_path)

    @pytest.mark.asyncio
    async def test_schema_migration(self, test_suite):
        """Test schema migration with SQLite."""
        # File-backed SQLite: per schema-migration.md Rule 5, :memory: is not
        # appropriate for migration validation (each connection sees a separate
        # DB). Re-decorating the same class name to "add a field" is NOT the
        # DataFlow migration mechanism — it hits the duplicate-registration guard
        # — so this exercises the auto_migrate path on a single registered model.
        fd, _db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            # Create DataFlow instance
            db = DataFlow(f"sqlite:///{_db_path}")

            # Define model
            @db.model
            class Customer:
                name: str
                email: str

            # Initialize the schema
            await db.initialize()

            # Run auto-migrate (dry-run): the registered schema matches the
            # created tables, so the migration planner MUST complete successfully.
            # auto_migrate returns a (success, migrations) tuple.
            success, _migrations = await db.auto_migrate(
                dry_run=True, interactive=False
            )

            assert success is True, "Schema migration failed"

        except Exception as e:
            pytest.fail(f"Schema migration test failed: {e}")
        finally:
            if os.path.exists(_db_path):
                os.unlink(_db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
