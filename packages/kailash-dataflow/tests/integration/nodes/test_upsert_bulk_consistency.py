"""Consistency tests for BulkUpsertNode with conflict_on parameter.

Verifies that the standalone BulkUpsertNode behaves consistently with expected
upsert semantics when using custom conflict fields.

NOTE: These tests use the standalone BulkUpsertNode from dataflow.nodes.bulk_upsert.
The DataFlow-generated nodes use a different implementation which is being
enhanced separately in features/bulk.py.
"""

import pytest

from dataflow.nodes.bulk_upsert import BulkUpsertNode
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create integration test suite with PostgreSQL infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
async def users_table(test_suite):
    """Create users table with email unique constraint."""
    async with test_suite.get_connection() as conn:
        await conn.execute("DROP TABLE IF EXISTS users CASCADE")
        await conn.execute(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        yield "users"
        await conn.execute("DROP TABLE IF EXISTS users CASCADE")


@pytest.fixture
async def products_table(test_suite):
    """Create products table with SKU unique constraint."""
    async with test_suite.get_connection() as conn:
        await conn.execute("DROP TABLE IF EXISTS products CASCADE")
        await conn.execute(
            """
            CREATE TABLE products (
                id TEXT PRIMARY KEY,
                sku TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        yield "products"
        await conn.execute("DROP TABLE IF EXISTS products CASCADE")


@pytest.fixture
async def order_items_table(test_suite):
    """Create order_items table with composite unique constraint."""
    async with test_suite.get_connection() as conn:
        await conn.execute("DROP TABLE IF EXISTS order_items CASCADE")
        await conn.execute(
            """
            CREATE TABLE order_items (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(order_id, product_id)
            )
        """
        )
        yield "order_items"
        await conn.execute("DROP TABLE IF EXISTS order_items CASCADE")


@pytest.mark.integration
@pytest.mark.timeout(15)
class TestBulkUpsertConflictOnConsistency:
    """Test standalone BulkUpsertNode behaves consistently with expected upsert semantics."""

    async def test_email_conflict_insert_then_update(self, test_suite, users_table):
        """Test that BulkUpsertNode correctly handles INSERT then UPDATE on email."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
        )

        # Test data
        user_data = {
            "id": "user-1",
            "email": "alice@example.com",
            "name": "Alice Original",
        }

        # First upsert (INSERT)
        result1 = await node.async_run(
            data=[user_data],
            conflict_on=["email"],
            merge_strategy="update",
        )

        assert result1["success"] is True
        assert result1["upserted"] == 1
        assert result1["metadata"]["conflict_columns"] == ["email"]

        # Verify INSERT
        async with test_suite.get_connection() as conn:
            record = await conn.fetchrow(
                "SELECT * FROM users WHERE email = 'alice@example.com'"
            )
            assert record["id"] == "user-1"
            assert record["name"] == "Alice Original"

        # Second upsert (UPDATE) - Same email, different name
        user_update = {
            "id": "user-1",
            "email": "alice@example.com",
            "name": "Alice Updated",
        }

        result2 = await node.async_run(
            data=[user_update],
            conflict_on=["email"],
            merge_strategy="update",
        )

        assert result2["success"] is True
        assert result2["upserted"] == 1

        # Verify UPDATE occurred
        async with test_suite.get_connection() as conn:
            record = await conn.fetchrow(
                "SELECT * FROM users WHERE email = 'alice@example.com'"
            )
            assert record["id"] == "user-1"
            assert record["name"] == "Alice Updated"  # Name changed

    async def test_sku_conflict_consistency(self, test_suite, products_table):
        """Test that BulkUpsertNode handles SKU conflict correctly."""
        node = BulkUpsertNode(
            table_name="products",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
        )

        # Insert product
        product1 = {
            "id": "prod-1",
            "sku": "WIDGET-2024",
            "name": "Widget",
            "price": 49.99,
        }

        result1 = await node.async_run(
            data=[product1],
            conflict_on=["sku"],
            merge_strategy="update",
        )

        assert result1["success"] is True
        assert result1["upserted"] == 1

        # Update price via SKU conflict
        product2 = {
            "id": "prod-1",
            "sku": "WIDGET-2024",
            "name": "Widget",
            "price": 99.99,
        }

        result2 = await node.async_run(
            data=[product2],
            conflict_on=["sku"],
            merge_strategy="update",
        )

        assert result2["success"] is True

        # Verify price updated
        async with test_suite.get_connection() as conn:
            record = await conn.fetchrow(
                "SELECT * FROM products WHERE sku = 'WIDGET-2024'"
            )
            assert float(record["price"]) == 99.99

    async def test_composite_key_consistency(self, test_suite, order_items_table):
        """Test that BulkUpsertNode handles composite key conflicts correctly."""
        node = BulkUpsertNode(
            table_name="order_items",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
        )

        # Insert order item
        item1 = {
            "id": "item-1",
            "order_id": "order-100",
            "product_id": "prod-A",
            "quantity": 5,
        }

        result1 = await node.async_run(
            data=[item1],
            conflict_on=["order_id", "product_id"],
            merge_strategy="update",
        )

        assert result1["success"] is True
        assert result1["upserted"] == 1
        assert result1["metadata"]["conflict_columns"] == ["order_id", "product_id"]

        # Update quantity via composite key conflict
        item2 = {
            "id": "item-1",
            "order_id": "order-100",
            "product_id": "prod-A",
            "quantity": 10,
        }

        result2 = await node.async_run(
            data=[item2],
            conflict_on=["order_id", "product_id"],
            merge_strategy="update",
        )

        assert result2["success"] is True

        # Verify quantity updated
        async with test_suite.get_connection() as conn:
            record = await conn.fetchrow(
                """
                SELECT * FROM order_items
                WHERE order_id = 'order-100' AND product_id = 'prod-A'
                """
            )
            assert record["quantity"] == 10

    async def test_conflict_on_overrides_config_default(self, test_suite, users_table):
        """Test that runtime conflict_on overrides config conflict_columns."""
        # Create node with email as config default
        node = BulkUpsertNode(
            table_name="users",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            conflict_columns=["email"],  # Config default
            auto_timestamps=False,
        )

        # Add username column
        async with test_suite.get_connection() as conn:
            await conn.execute("ALTER TABLE users ADD COLUMN username TEXT UNIQUE")

        # Insert with email conflict (config default)
        user1 = {
            "id": "user-1",
            "email": "alice@example.com",
            "username": "alice",
            "name": "Alice",
        }

        result1 = await node.async_run(
            data=[user1],
            # Don't provide conflict_on - uses config default ["email"]
            merge_strategy="update",
        )

        assert result1["success"] is True
        assert result1["metadata"]["conflict_columns"] == ["email"]

        # Update with username conflict (runtime override)
        user2 = {
            "id": "user-2",
            "email": "alice2@example.com",
            "username": "alice",  # Same username, different email
            "name": "Alice 2",
        }

        result2 = await node.async_run(
            data=[user2],
            conflict_on=["username"],  # Runtime override
            merge_strategy="update",
        )

        assert result2["success"] is True
        assert result2["metadata"]["conflict_columns"] == ["username"]

        # Verify only 1 record exists (username conflict won)
        async with test_suite.get_connection() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
            assert count == 1

            record = await conn.fetchrow("SELECT * FROM users WHERE username = 'alice'")
            # Username conflict means UPDATE occurred
            assert record["email"] == "alice2@example.com"
            assert record["name"] == "Alice 2"

    async def test_merge_strategy_consistency(self, test_suite, users_table):
        """Test that merge strategy (update vs ignore) works consistently."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
        )

        # Insert initial record
        user1 = {"id": "user-1", "email": "alice@example.com", "name": "Alice Original"}

        await node.async_run(
            data=[user1],
            conflict_on=["email"],
            merge_strategy="update",
        )

        # Try to update with ignore strategy
        user2 = {"id": "user-1", "email": "alice@example.com", "name": "Alice Updated"}

        result = await node.async_run(
            data=[user2],
            conflict_on=["email"],
            merge_strategy="ignore",
        )

        assert result["success"] is True

        # Verify original data unchanged (ignore strategy)
        async with test_suite.get_connection() as conn:
            record = await conn.fetchrow(
                "SELECT * FROM users WHERE email = 'alice@example.com'"
            )
            assert record["name"] == "Alice Original"  # Unchanged
