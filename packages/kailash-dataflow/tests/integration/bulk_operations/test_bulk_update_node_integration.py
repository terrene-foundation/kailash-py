"""
Integration tests for BulkUpdateNode with real database connections.
Tests against PostgreSQL using Docker test environment.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List

import pytest
from dataflow.nodes.bulk_update import BulkUpdateNode
from pytest import approx

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestBulkUpdateNodeIntegration:
    """Integration tests for BulkUpdateNode with real database."""

    def _extract_result_data(self, result):
        """Extract data from AsyncSQLDatabaseNode result format."""
        if (
            isinstance(result, dict)
            and "result" in result
            and "data" in result["result"]
        ):
            return result["result"]["data"]
        return result

    @pytest.fixture
    async def setup_test_table(self, test_suite):
        """Create test table with data and clean up after test."""
        # Use test suite database URL
        connection_string = test_suite.config.url

        # Create table using AsyncSQLDatabaseNode
        setup_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            CREATE TABLE IF NOT EXISTS test_bulk_products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price NUMERIC(10,2) NOT NULL,
                category VARCHAR(50),
                status VARCHAR(20) DEFAULT 'active',
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            validate_queries=False,
        )

        # Drop and recreate table for clean state
        drop_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="DROP TABLE IF EXISTS test_bulk_products CASCADE",
            validate_queries=False,
        )

        await drop_node.async_run()
        await setup_node.async_run()

        # Insert test data
        insert_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            INSERT INTO test_bulk_products (name, price, category, status)
            VALUES
                ('Product A', 100.00, 'electronics', 'active'),
                ('Product B', 200.00, 'electronics', 'active'),
                ('Product C', 150.00, 'books', 'active'),
                ('Product D', 300.00, 'electronics', 'pending'),
                ('Product E', 50.00, 'books', 'active')
            """,
            validate_queries=False,
        )
        await insert_node.async_run()

        # Clean up the nodes to close connections
        await setup_node.cleanup()
        await drop_node.cleanup()
        await insert_node.cleanup()

        yield connection_string

        # Cleanup after test with new node instance
        cleanup_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="DROP TABLE IF EXISTS test_bulk_products CASCADE",
            validate_queries=False,
        )
        await cleanup_node.async_run()
        await cleanup_node.cleanup()

    @pytest.mark.asyncio
    async def test_bulk_update_by_filter(self, setup_test_table):
        """Test bulk update using filter criteria."""
        connection_string = setup_test_table

        # Create BulkUpdateNode
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="test_bulk_products",
            database_type="postgresql",
            connection_string=connection_string,
        )

        # Update all active electronics products
        result = await node.async_run(
            filter={"category": "electronics", "status": "active"},
            update_fields={"price": {"$multiply": 0.9}},  # 10% discount
        )

        # Verify results
        assert result["success"]
        assert result["updated"] == 2  # Products A and B

        # Verify the updates
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT name, price FROM test_bulk_products WHERE category = 'electronics' AND status = 'active' ORDER BY name",
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)
        assert len(data) == 2
        assert float(data[0]["price"]) == 90.00  # Product A: 100 * 0.9
        assert float(data[1]["price"]) == 180.00  # Product B: 200 * 0.9

    @pytest.mark.asyncio
    async def test_bulk_update_by_ids(self, setup_test_table):
        """Test bulk update using ID list."""
        connection_string = setup_test_table

        # Get some IDs first
        id_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT id FROM test_bulk_products WHERE category = 'books' ORDER BY id",
            validate_queries=False,
        )
        id_result = await id_node.async_run()
        await id_node.cleanup()
        ids = [row["id"] for row in self._extract_result_data(id_result)]

        # Create BulkUpdateNode
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="test_bulk_products",
            database_type="postgresql",
            connection_string=connection_string,
        )

        # Update specific products by ID
        result = await node.async_run(
            filter={"id": {"$in": ids}},
            update_fields={"category": "literature", "price": {"$multiply": 1.1}},
        )

        assert result["success"]
        assert result["updated"] == 2  # Products C and E

        # Verify updates
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT category, price FROM test_bulk_products WHERE id = ANY(:ids) ORDER BY id",
            params={"ids": ids},
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)
        assert all(row["category"] == "literature" for row in data)
        assert float(data[0]["price"]) == 165.00  # Product C: 150 * 1.1
        assert float(data[1]["price"]) == 55.00  # Product E: 50 * 1.1

    @pytest.mark.asyncio
    async def test_bulk_update_by_data_list(self, setup_test_table):
        """Test bulk update using data list with individual updates."""
        connection_string = setup_test_table

        # Get product IDs
        id_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT id, name FROM test_bulk_products ORDER BY name LIMIT 3",
            validate_queries=False,
        )
        id_result = await id_node.async_run()
        await id_node.cleanup()
        products = self._extract_result_data(id_result)

        # Create BulkUpdateNode
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="test_bulk_products",
            database_type="postgresql",
            connection_string=connection_string,
            batch_size=2,  # Test batching
        )

        # Update data with individual prices
        update_data = [
            {"id": products[0]["id"], "price": 99.99, "status": "sale"},
            {"id": products[1]["id"], "price": 199.99, "status": "sale"},
            {"id": products[2]["id"], "price": 149.99, "status": "sale"},
        ]

        result = await node.async_run(data=update_data)

        assert result["success"]
        assert result["updated"] == 3
        assert result["batches"] == 2  # 3 records with batch_size=2

        # Verify updates
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT name, price, status FROM test_bulk_products WHERE status = 'sale' ORDER BY name",
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)
        assert len(data) == 3
        assert all(row["status"] == "sale" for row in data)

    @pytest.mark.asyncio
    async def test_version_control_optimistic_locking(self, setup_test_table):
        """Test optimistic locking with version control."""
        connection_string = setup_test_table

        # Get a product with version
        id_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT id, version FROM test_bulk_products WHERE name = 'Product A'",
            validate_queries=False,
        )
        id_result = await id_node.async_run()
        await id_node.cleanup()
        product = self._extract_result_data(id_result)[0]

        # Create BulkUpdateNode with versioning
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="test_bulk_products",
            database_type="postgresql",
            connection_string=connection_string,
            enable_versioning=True,
        )

        # First update should succeed
        result1 = await node.async_run(
            data=[{"id": product["id"], "version": product["version"], "price": 111.11}]
        )

        assert result1["success"]
        assert result1["updated"] == 1
        assert result1["conflicts"] == 0

        # Second update with old version should fail
        result2 = await node.async_run(
            data=[
                {
                    "id": product["id"],
                    "version": product["version"],  # Old version
                    "price": 222.22,
                }
            ]
        )

        assert result2["success"]
        assert result2["updated"] == 0
        assert result2["conflicts"] == 1

        # Verify final state
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT price, version FROM test_bulk_products WHERE id = :id",
            params={"id": product["id"]},
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)[0]
        assert float(data["price"]) == 111.11
        assert data["version"] == 2  # Version incremented

    @pytest.mark.asyncio
    async def test_auto_timestamps(self, setup_test_table):
        """Test automatic updated_at timestamp."""
        connection_string = setup_test_table

        # Get original timestamp
        before_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_bulk_products WHERE name = 'Product A' LIMIT 1",
            validate_queries=False,
        )
        before_result = await before_node.async_run()
        await before_node.cleanup()
        data = self._extract_result_data(before_result)
        if not data:
            raise AssertionError("No data found for Product A")
        before_data = data[0]
        product_id = before_data["id"]
        original_timestamp = before_data["updated_at"]

        # Wait a moment to ensure timestamp difference
        await asyncio.sleep(0.1)

        # Create BulkUpdateNode with auto timestamps
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="test_bulk_products",
            database_type="postgresql",
            connection_string=connection_string,
            auto_timestamps=True,
        )

        # Update the product
        result = await node.async_run(
            filter={"id": product_id}, update_fields={"status": "updated"}
        )

        assert result["success"]
        assert result["updated"] == 1

        # Verify timestamp was updated
        after_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT * FROM test_bulk_products WHERE id = :id LIMIT 1",
            params={"id": product_id},
            validate_queries=False,
        )

        after_result = await after_node.async_run()
        await after_node.cleanup()
        after_data = self._extract_result_data(after_result)[0]

        # Timestamp should be newer
        assert after_data["updated_at"] > original_timestamp

    @pytest.mark.asyncio
    async def test_multi_tenant_update(self, setup_test_table):
        """Test multi-tenant support."""
        connection_string = setup_test_table

        # Add tenant_id column
        alter_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="ALTER TABLE test_bulk_products ADD COLUMN tenant_id VARCHAR(50)",
            validate_queries=False,
        )
        await alter_node.async_run()

        # Set tenant IDs
        tenant_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            UPDATE test_bulk_products
            SET tenant_id = CASE
                WHEN category = 'electronics' THEN 'tenant_001'
                ELSE 'tenant_002'
            END
            """,
            validate_queries=False,
        )
        await tenant_node.async_run()
        await alter_node.cleanup()
        await tenant_node.cleanup()

        # Create BulkUpdateNode with multi-tenant support
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="test_bulk_products",
            database_type="postgresql",
            connection_string=connection_string,
            multi_tenant=True,
        )

        # Update only tenant_001 products
        result = await node.async_run(
            filter={"status": "active"},
            update_fields={"price": {"$multiply": 0.8}},
            tenant_id="tenant_001",
        )

        # Should only update electronics (tenant_001)
        assert result["success"]
        assert result["updated"] == 2  # Only active electronics

        # Verify tenant isolation worked
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            SELECT tenant_id, COUNT(*) as count, AVG(price) as avg_price
            FROM test_bulk_products
            WHERE status = 'active'
            GROUP BY tenant_id
            ORDER BY tenant_id
            """,
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)

        # tenant_001 should have discounted prices
        tenant_001 = next(row for row in data if row["tenant_id"] == "tenant_001")
        tenant_002 = next(row for row in data if row["tenant_id"] == "tenant_002")

        # tenant_001 had electronics (100 and 200), both active, so 0.8 * (100+200)/2 = 0.8 * 150 = 120
        assert float(tenant_001["avg_price"]) == pytest.approx(
            120.0, rel=0.01
        )  # Discounted
        # tenant_002 had books (150 and 50), average 100, not discounted
        assert float(tenant_002["avg_price"]) == pytest.approx(
            100.0, rel=0.01
        )  # Not discounted

    @pytest.mark.asyncio
    async def test_return_updated_records(self, setup_test_table):
        """Test returning updated records option."""
        connection_string = setup_test_table

        # Create BulkUpdateNode
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="test_bulk_products",
            database_type="postgresql",
            connection_string=connection_string,
        )

        # Update with return_updated option
        result = await node.async_run(
            filter={"category": "books"},
            update_fields={"status": "bestseller"},
            return_updated=True,
        )

        assert result["success"]
        assert result["updated"] == 2
        assert "records" in result
        assert len(result["records"]) == 2

        # Verify returned records have updated values
        for record in result["records"]:
            assert record["status"] == "bestseller"
            assert record["category"] == "books"

    @pytest.mark.asyncio
    async def test_performance_large_update(self, setup_test_table):
        """Test performance with larger update set."""
        connection_string = setup_test_table

        # Insert more test data
        insert_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="""
            INSERT INTO test_bulk_products (name, price, category, status)
            SELECT
                'Product ' || generate_series,
                100 + (random() * 400),
                CASE WHEN random() > 0.5 THEN 'electronics' ELSE 'books' END,
                'active'
            FROM generate_series(1, 1000)
            """,
            validate_queries=False,
        )
        await insert_node.async_run()
        await insert_node.cleanup()

        # Create BulkUpdateNode with larger batch size
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="test_bulk_products",
            database_type="postgresql",
            connection_string=connection_string,
            batch_size=500,
        )

        # Update all active products
        result = await node.async_run(
            filter={"status": "active"},
            update_fields={"price": {"$multiply": 0.95}},  # 5% discount
        )

        assert result["success"]
        assert result["updated"] >= 1000  # At least our inserted records

        # Check performance metrics
        metrics = result["performance_metrics"]
        print(f"\nPerformance: {metrics['records_per_second']:.2f} records/sec")
        print(f"Total updated: {result['updated']}")
        print(f"Elapsed time: {metrics['duration_seconds']:.3f} seconds")

        # For integration tests, we check reasonable performance
        assert metrics["records_per_second"] > 100  # At least 100/sec in test env

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, setup_test_table):
        """Test dry run mode."""
        connection_string = setup_test_table

        # Create BulkUpdateNode
        node = BulkUpdateNode(
            node_id="test_bulk_update",
            table_name="test_bulk_products",
            database_type="postgresql",
            connection_string=connection_string,
        )

        # Run in dry run mode
        result = await node.async_run(
            filter={"category": "electronics"},
            update_fields={"price": 0.01},  # Extreme price change
            dry_run=True,
        )

        assert result["success"]
        assert "would_update" in result
        assert "query" in result
        assert "parameters" in result

        # Verify no actual changes were made
        verify_node = AsyncSQLDatabaseNode(
            connection_string=connection_string,
            database_type="postgresql",
            query="SELECT MIN(price) as min_price FROM test_bulk_products WHERE category = 'electronics'",
            validate_queries=False,
        )

        verify_result = await verify_node.async_run()
        await verify_node.cleanup()
        data = self._extract_result_data(verify_result)[0]

        # Price should not be 0.01
        assert float(data["min_price"]) > 1.0
