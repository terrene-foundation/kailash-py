"""Integration tests for BulkUpsertNode conflict_on with real PostgreSQL.

Tests real database operations with custom conflict fields including:
- Natural keys (email, SKU)
- Composite keys (order_id + product_id)
- Metadata and result structure
- Consistency with UpsertNode
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
@pytest.mark.timeout(10)
class TestBulkUpsertSingleConflictField:
    """Test bulk upsert with single conflict field (natural key)."""

    async def test_bulk_upsert_on_email(self, test_suite, users_table):
        """Test bulk upsert using email as conflict field."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
        )

        # First batch: Insert 2 users
        data_batch_1 = [
            {"id": "user-1", "email": "alice@example.com", "name": "Alice Original"},
            {"id": "user-2", "email": "bob@example.com", "name": "Bob"},
        ]

        result = await node.async_run(
            data=data_batch_1,
            conflict_on=["email"],
            merge_strategy="update",
        )

        assert result["success"] is True
        assert result["upserted"] == 2
        assert result["metadata"]["conflict_columns"] == ["email"]

        # Second batch: Update alice, insert charlie
        data_batch_2 = [
            {"id": "user-1", "email": "alice@example.com", "name": "Alice Updated"},
            {"id": "user-3", "email": "charlie@example.com", "name": "Charlie"},
        ]

        result2 = await node.async_run(
            data=data_batch_2,
            conflict_on=["email"],
            merge_strategy="update",
        )

        assert result2["success"] is True
        assert result2["upserted"] == 2

        # Verify database state
        async with test_suite.get_connection() as conn:
            records = await conn.fetch("SELECT * FROM users ORDER BY email")
            assert len(records) == 3
            # Alice should be updated
            alice = [r for r in records if r["email"] == "alice@example.com"][0]
            assert alice["name"] == "Alice Updated"
            assert alice["id"] == "user-1"  # ID unchanged

    async def test_bulk_upsert_on_sku(self, test_suite, products_table):
        """Test bulk upsert using SKU as conflict field."""
        node = BulkUpsertNode(
            table_name="products",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
        )

        # First batch: Insert products
        data_batch_1 = [
            {"id": "prod-1", "sku": "WIDGET-2024", "name": "Widget", "price": 49.99},
            {"id": "prod-2", "sku": "GADGET-2024", "name": "Gadget", "price": 29.99},
        ]

        result = await node.async_run(
            data=data_batch_1,
            conflict_on=["sku"],
            merge_strategy="update",
        )

        assert result["success"] is True
        assert result["upserted"] == 2

        # Second batch: Update widget price, insert new product
        data_batch_2 = [
            {"id": "prod-1", "sku": "WIDGET-2024", "name": "Widget", "price": 99.99},
            {"id": "prod-3", "sku": "TOOL-2024", "name": "Tool", "price": 19.99},
        ]

        result2 = await node.async_run(
            data=data_batch_2,
            conflict_on=["sku"],
            merge_strategy="update",
        )

        assert result2["success"] is True
        assert result2["upserted"] == 2

        # Verify price update
        async with test_suite.get_connection() as conn:
            widget = await conn.fetchrow(
                "SELECT * FROM products WHERE sku = 'WIDGET-2024'"
            )
            assert float(widget["price"]) == 99.99


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestBulkUpsertCompositeConflictFields:
    """Test bulk upsert with composite conflict fields."""

    async def test_bulk_upsert_on_composite_key(self, test_suite, order_items_table):
        """Test bulk upsert using composite key (order_id + product_id)."""
        node = BulkUpsertNode(
            table_name="order_items",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
        )

        # First batch: Insert order items
        data_batch_1 = [
            {
                "id": "item-1",
                "order_id": "order-100",
                "product_id": "prod-A",
                "quantity": 5,
            },
            {
                "id": "item-2",
                "order_id": "order-100",
                "product_id": "prod-B",
                "quantity": 3,
            },
            {
                "id": "item-3",
                "order_id": "order-101",
                "product_id": "prod-A",
                "quantity": 2,
            },
        ]

        result = await node.async_run(
            data=data_batch_1,
            conflict_on=["order_id", "product_id"],
            merge_strategy="update",
        )

        assert result["success"] is True
        assert result["upserted"] == 3
        assert result["metadata"]["conflict_columns"] == ["order_id", "product_id"]

        # Second batch: Update quantities
        data_batch_2 = [
            {
                "id": "item-1",
                "order_id": "order-100",
                "product_id": "prod-A",
                "quantity": 10,
            },  # Updated
            {
                "id": "item-4",
                "order_id": "order-101",
                "product_id": "prod-B",
                "quantity": 7,
            },  # New
        ]

        result2 = await node.async_run(
            data=data_batch_2,
            conflict_on=["order_id", "product_id"],
            merge_strategy="update",
        )

        assert result2["success"] is True
        assert result2["upserted"] == 2

        # Verify database state
        async with test_suite.get_connection() as conn:
            records = await conn.fetch(
                "SELECT * FROM order_items ORDER BY order_id, product_id"
            )
            assert len(records) == 4

            # Verify updated quantity
            updated_item = await conn.fetchrow(
                """
                SELECT * FROM order_items
                WHERE order_id = 'order-100' AND product_id = 'prod-A'
                """
            )
            assert updated_item["quantity"] == 10

    async def test_composite_key_prevents_duplicates_in_batch(
        self, test_suite, order_items_table
    ):
        """Test that duplicates within batch are deduplicated by composite key."""
        node = BulkUpsertNode(
            table_name="order_items",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
            handle_duplicates="last",
        )

        # Batch with duplicate composite key (order-100 + prod-A)
        data_with_duplicates = [
            {
                "id": "item-1",
                "order_id": "order-100",
                "product_id": "prod-A",
                "quantity": 5,
            },
            {
                "id": "item-2",
                "order_id": "order-100",
                "product_id": "prod-B",
                "quantity": 3,
            },
            {
                "id": "item-3",
                "order_id": "order-100",
                "product_id": "prod-A",
                "quantity": 10,
            },  # Duplicate key
        ]

        result = await node.async_run(
            data=data_with_duplicates,
            conflict_on=["order_id", "product_id"],
            merge_strategy="update",
        )

        assert result["success"] is True
        assert result["duplicates_removed"] == 1
        assert result["upserted"] == 2  # Only 2 unique composite keys

        # Verify last occurrence was kept (quantity=10)
        async with test_suite.get_connection() as conn:
            item = await conn.fetchrow(
                """
                SELECT * FROM order_items
                WHERE order_id = 'order-100' AND product_id = 'prod-A'
                """
            )
            assert item["quantity"] == 10


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestBulkUpsertBackwardCompatibility:
    """Test backward compatibility with existing behavior."""

    async def test_omitting_conflict_on_uses_config_default(
        self, test_suite, users_table
    ):
        """Test that omitting conflict_on uses config conflict_columns."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            conflict_columns=["email"],  # Config default
            auto_timestamps=False,
        )

        data = [
            {"id": "user-1", "email": "alice@example.com", "name": "Alice"},
        ]

        # Don't provide conflict_on - should use config default
        result = await node.async_run(
            data=data,
            merge_strategy="update",
        )

        assert result["success"] is True
        assert result["metadata"]["conflict_columns"] == ["email"]

    async def test_runtime_conflict_on_overrides_config(self, test_suite, users_table):
        """Test that runtime conflict_on overrides config conflict_columns."""
        # Add username column with unique constraint
        async with test_suite.get_connection() as conn:
            await conn.execute("ALTER TABLE users ADD COLUMN username TEXT UNIQUE")

        node = BulkUpsertNode(
            table_name="users",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            conflict_columns=["email"],  # Config default
            auto_timestamps=False,
        )

        data = [
            {
                "id": "user-1",
                "email": "alice@example.com",
                "username": "alice",
                "name": "Alice",
            },
        ]

        # Override with username
        result = await node.async_run(
            data=data,
            conflict_on=["username"],  # Runtime override
            merge_strategy="update",
        )

        assert result["success"] is True
        assert result["metadata"]["conflict_columns"] == ["username"]


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestBulkUpsertMergeStrategies:
    """Test different merge strategies with conflict_on."""

    async def test_merge_strategy_update(self, test_suite, users_table):
        """Test that update strategy modifies existing records."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
        )

        # Insert initial record
        data_initial = [
            {"id": "user-1", "email": "alice@example.com", "name": "Alice Old"},
        ]

        await node.async_run(
            data=data_initial,
            conflict_on=["email"],
            merge_strategy="update",
        )

        # Update with same email
        data_update = [
            {"id": "user-1", "email": "alice@example.com", "name": "Alice New"},
        ]

        result = await node.async_run(
            data=data_update,
            conflict_on=["email"],
            merge_strategy="update",
        )

        assert result["success"] is True

        # Verify update occurred
        async with test_suite.get_connection() as conn:
            record = await conn.fetchrow(
                "SELECT * FROM users WHERE email = 'alice@example.com'"
            )
            assert record["name"] == "Alice New"

    async def test_merge_strategy_ignore(self, test_suite, users_table):
        """Test that ignore strategy keeps existing records unchanged."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
        )

        # Insert initial record
        data_initial = [
            {"id": "user-1", "email": "alice@example.com", "name": "Alice Original"},
        ]

        await node.async_run(
            data=data_initial,
            conflict_on=["email"],
            merge_strategy="update",
        )

        # Try to update with ignore strategy
        data_update = [
            {"id": "user-1", "email": "alice@example.com", "name": "Alice Updated"},
        ]

        result = await node.async_run(
            data=data_update,
            conflict_on=["email"],
            merge_strategy="ignore",
        )

        assert result["success"] is True

        # Verify original data unchanged
        async with test_suite.get_connection() as conn:
            record = await conn.fetchrow(
                "SELECT * FROM users WHERE email = 'alice@example.com'"
            )
            assert record["name"] == "Alice Original"  # Unchanged


@pytest.mark.integration
@pytest.mark.timeout(10)
class TestBulkUpsertLargeDatasets:
    """Test bulk upsert with large datasets using conflict_on."""

    async def test_bulk_upsert_1000_records(self, test_suite, users_table):
        """Test bulk upsert with 1000 records using email conflict."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            batch_size=500,  # Test batching
            auto_timestamps=False,
        )

        # Generate 1000 unique records
        data = [
            {
                "id": f"user-{i}",
                "email": f"user{i}@example.com",
                "name": f"User {i}",
            }
            for i in range(1000)
        ]

        result = await node.async_run(
            data=data,
            conflict_on=["email"],
            merge_strategy="update",
        )

        assert result["success"] is True
        assert result["upserted"] == 1000
        assert result["batch_count"] == 2  # 1000 / 500 = 2 batches
        assert result["performance_metrics"]["records_per_second"] > 0

        # Verify all records inserted
        async with test_suite.get_connection() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
            assert count == 1000

    async def test_bulk_upsert_with_updates_in_large_dataset(
        self, test_suite, users_table
    ):
        """Test bulk upsert with mix of inserts and updates in large dataset."""
        node = BulkUpsertNode(
            table_name="users",
            connection_string=test_suite.config.url,
            database_type="postgresql",
            auto_timestamps=False,
        )

        # Insert 500 records
        data_initial = [
            {
                "id": f"user-{i}",
                "email": f"user{i}@example.com",
                "name": f"User {i} Original",
            }
            for i in range(500)
        ]

        await node.async_run(
            data=data_initial,
            conflict_on=["email"],
            merge_strategy="update",
        )

        # Update first 250, insert next 250
        data_mixed = [
            {
                "id": f"user-{i}",
                "email": f"user{i}@example.com",
                "name": f"User {i} Updated",
            }
            for i in range(250)
        ] + [
            {
                "id": f"user-{i}",
                "email": f"user{i}@example.com",
                "name": f"User {i}",
            }
            for i in range(500, 750)
        ]

        result = await node.async_run(
            data=data_mixed,
            conflict_on=["email"],
            merge_strategy="update",
        )

        assert result["success"] is True
        assert result["upserted"] == 500  # 250 updates + 250 inserts

        # Verify total count
        async with test_suite.get_connection() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM users")
            assert count == 750  # 500 original + 250 new
