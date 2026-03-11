"""
Integration tests for real bulk_update database operations.

Tests both filter-based and data-based bulk update modes with real PostgreSQL.
"""

import pytest
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def setup_test_table(test_suite):
    """Create test table with sample data."""
    connection_string = test_suite.config.url

    # Drop and create table
    drop_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS products CASCADE",
        validate_queries=False,
    )
    await drop_node.async_run()
    await drop_node.cleanup()

    setup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        CREATE TABLE products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            stock INTEGER DEFAULT 0,
            active BOOLEAN DEFAULT true
        )
        """,
        validate_queries=False,
    )
    await setup_node.async_run()
    await setup_node.cleanup()

    # Insert test data
    insert_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="""
        INSERT INTO products (name, category, price, stock, active)
        VALUES
            ('Widget A', 'electronics', 29.99, 100, true),
            ('Widget B', 'electronics', 49.99, 50, true),
            ('Gadget X', 'electronics', 99.99, 25, true),
            ('Tool Y', 'hardware', 19.99, 200, true),
            ('Tool Z', 'hardware', 39.99, 150, false)
        """,
        validate_queries=False,
    )
    await insert_node.async_run()
    await insert_node.cleanup()

    yield connection_string

    # Cleanup
    cleanup_node = AsyncSQLDatabaseNode(
        connection_string=connection_string,
        database_type="postgresql",
        query="DROP TABLE IF EXISTS products CASCADE",
        validate_queries=False,
    )
    await cleanup_node.async_run()
    await cleanup_node.cleanup()


class TestBulkUpdateFilterBased:
    """Test filter-based bulk update operations."""

    @pytest.mark.asyncio
    async def test_bulk_update_with_specific_filter(self, setup_test_table):
        """Test updating records with specific filter criteria."""
        connection_string = setup_test_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class Product:
            name: str
            category: str
            price: float
            stock: int
            active: bool

        # Update all electronics to 20% discount
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_electronics",
            {
                "filter": {"category": "electronics"},
                "update": {"price": 19.99},
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        update_result = results.get("update_electronics")
        assert update_result is not None, "No result returned from bulk update"
        assert update_result.get(
            "success"
        ), f"Update failed: {update_result.get('error')}"
        assert (
            update_result.get("processed") == 3
        ), f"Expected 3 updated, got {update_result.get('processed')}"

        # Verify the updates
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT COUNT(*) as count FROM products WHERE category = 'electronics' AND price = 19.99",
            fetch_mode="all",
            validate_queries=False,
        )
        result = await verify_node.async_run()
        count = result["result"]["data"][0]["count"]
        assert count == 3, f"Expected 3 electronics at $19.99, found {count}"

    @pytest.mark.asyncio
    async def test_bulk_update_with_empty_filter_confirmed(self, setup_test_table):
        """Test updating ALL records with empty filter and confirmation."""
        connection_string = setup_test_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class Product:
            name: str
            category: str
            price: float
            stock: int
            active: bool

        # Update ALL products to active with empty filter
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductBulkUpdateNode",
            "activate_all",
            {
                "filter": {},  # Empty filter = update all
                "update": {"active": True},
                "confirmed": True,
                "safe_mode": False,
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        update_result = results.get("activate_all")
        assert update_result is not None
        assert update_result.get("success")
        assert update_result.get("processed") == 5, "Should update all 5 records"

        # Verify all are active
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT COUNT(*) as count FROM products WHERE active = true",
            fetch_mode="all",
            validate_queries=False,
        )
        result = await verify_node.async_run()
        count = result["result"]["data"][0]["count"]
        assert count == 5, f"Expected all 5 active, found {count}"

    @pytest.mark.asyncio
    async def test_bulk_update_empty_filter_without_confirmation_fails(
        self, setup_test_table
    ):
        """Test that empty filter without confirmation raises error."""
        from kailash.sdk_exceptions import RuntimeExecutionError

        connection_string = setup_test_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class Product:
            name: str
            category: str
            price: float
            stock: int
            active: bool

        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_all",
            {
                "filter": {},  # Empty filter without confirmation
                "update": {"stock": 0},
            },
        )

        runtime = LocalRuntime()

        # Should raise error about confirmation requirement
        with pytest.raises(RuntimeExecutionError) as exc_info:
            results, run_id = runtime.execute(workflow.build())

        error_msg = str(exc_info.value)
        assert "confirmed" in error_msg.lower()
        assert "empty filter" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_bulk_update_filter_no_matches(self, setup_test_table):
        """Test bulk update with filter that matches no records."""
        connection_string = setup_test_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class Product:
            name: str
            category: str
            price: float
            stock: int
            active: bool

        # Update with filter that matches nothing
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_nonexistent",
            {
                "filter": {"category": "nonexistent"},
                "update": {"price": 999.99},
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        update_result = results.get("update_nonexistent")
        assert update_result is not None
        assert update_result.get("success")
        assert update_result.get("processed") == 0, "Should update 0 records"


class TestBulkUpdateDataBased:
    """Test data-based bulk update operations."""

    @pytest.mark.asyncio
    async def test_bulk_update_with_data_list(self, setup_test_table):
        """Test updating multiple records by id using data list."""
        connection_string = setup_test_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class Product:
            name: str
            category: str
            price: float
            stock: int
            active: bool

        # Update specific products by id
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_by_ids",
            {
                "data": [
                    {"id": 1, "price": 24.99, "stock": 120},
                    {"id": 2, "price": 44.99, "stock": 60},
                    {"id": 3, "price": 89.99, "stock": 30},
                ]
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        update_result = results.get("update_by_ids")
        assert update_result is not None
        assert update_result.get(
            "success"
        ), f"Update failed: {update_result.get('error')}"
        assert (
            update_result.get("processed") == 3
        ), f"Expected 3 updated, got {update_result.get('processed')}"

        # Verify the updates
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT price, stock FROM products WHERE id = 1",
            fetch_mode="all",
            validate_queries=False,
        )
        result = await verify_node.async_run()
        product = result["result"]["data"][0]
        assert float(product["price"]) == 24.99
        assert product["stock"] == 120

    @pytest.mark.asyncio
    async def test_bulk_update_empty_data_list(self, setup_test_table):
        """Test bulk update with empty data list."""
        connection_string = setup_test_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class Product:
            name: str
            category: str
            price: float
            stock: int
            active: bool

        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_empty",
            {"data": []},  # Empty list
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        update_result = results.get("update_empty")
        assert update_result is not None
        assert update_result.get("success")
        assert update_result.get("processed") == 0

    @pytest.mark.asyncio
    async def test_bulk_update_single_record(self, setup_test_table):
        """Test updating a single record via data-based update."""
        connection_string = setup_test_table

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class Product:
            name: str
            category: str
            price: float
            stock: int
            active: bool

        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_one",
            {"data": [{"id": 4, "name": "Updated Tool Y", "price": 15.99}]},
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        update_result = results.get("update_one")
        assert update_result is not None
        assert update_result.get("success")
        assert update_result.get("processed") == 1

        # Verify the update
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT name, price FROM products WHERE id = 4",
            fetch_mode="all",
            validate_queries=False,
        )
        result = await verify_node.async_run()
        product = result["result"]["data"][0]
        assert product["name"] == "Updated Tool Y"
        assert float(product["price"]) == 15.99


class TestBulkUpdatePerformance:
    """Test bulk update performance and edge cases."""

    @pytest.mark.asyncio
    async def test_bulk_update_large_batch(self, setup_test_table):
        """Test bulk update with large number of records."""
        connection_string = setup_test_table

        # Insert many records
        insert_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            INSERT INTO products (name, category, price, stock, active)
            SELECT
                'Product ' || i,
                'category_' || (i % 5),
                (i % 100) + 10.0,
                i % 1000,
                true
            FROM generate_series(1, 1000) i
            """,
            validate_queries=False,
        )
        await insert_node.async_run()
        await insert_node.cleanup()

        df = DataFlow(connection_string, auto_migrate=False)

        @df.model
        class Product:
            name: str
            category: str
            price: float
            stock: int
            active: bool

        # Update all category_0 products
        workflow = WorkflowBuilder()
        workflow.add_node(
            "ProductBulkUpdateNode",
            "update_category",
            {
                "filter": {"category": "category_0"},
                "update": {"price": 5.99},
            },
        )

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        update_result = results.get("update_category")
        assert update_result is not None
        assert update_result.get("success")
        # Should update 200 records (1000 / 5 categories)
        assert update_result.get("processed") == 200
