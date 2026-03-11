"""Integration tests for ExpressDataFlow.

Tests ExpressDataFlow with real database operations using PostgreSQL.
Tier 2: NO MOCKING - uses real infrastructure.
"""

import asyncio
import random
import time

import asyncpg
import pytest

from dataflow import DataFlow


def get_unique_suffix():
    """Generate unique suffix for test table names."""
    return f"_{int(time.time())}_{random.randint(1000, 9999)}"


# Test database URL for direct PostgreSQL connection
TEST_DATABASE_URL = "postgresql://test_user:test_password@localhost:5434/kailash_test"


async def setup_test_table(table_name: str) -> None:
    """Create test table using direct asyncpg connection."""
    conn = await asyncpg.connect(
        host="localhost",
        port=5434,
        user="test_user",
        password="test_password",
        database="kailash_test",
    )
    try:
        await conn.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
        await conn.execute(
            f"""
            CREATE TABLE {table_name} (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
    finally:
        await conn.close()


async def cleanup_test_table(table_name: str) -> None:
    """Drop test table using direct asyncpg connection."""
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5434,
            user="test_user",
            password="test_password",
            database="kailash_test",
        )
        try:
            await conn.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
        finally:
            await conn.close()
    except Exception:
        pass


def create_dataflow_with_model(table_name: str, model_suffix: str = ""):
    """Create a DataFlow instance with a uniquely-named model.

    Args:
        table_name: The database table name
        model_suffix: Optional suffix to make model name unique across tests

    Returns:
        Tuple of (DataFlow instance, model name string)
    """
    db = DataFlow(
        database_url=TEST_DATABASE_URL,
        existing_schema_mode=True,
        auto_migrate=False,
        cache_enabled=False,
        pool_size=1,
        pool_max_overflow=0,
    )

    # Create model with unique name AND table name to avoid node collisions
    # Each test gets its own model class to avoid global node registry conflicts
    model_name = f"User{model_suffix}" if model_suffix else "User"

    UserModel = type(
        model_name,
        (),
        {
            "__annotations__": {
                "id": str,
                "name": str,
                "email": str,
                "active": bool,
            },
            "__tablename__": table_name,
            "active": True,
        },
    )
    db.model(UserModel)
    return db, model_name


class TestExpressDataFlowCRUD:
    """Integration tests for ExpressDataFlow CRUD operations."""

    # ========================================================================
    # Create Operations
    # ========================================================================

    @pytest.mark.asyncio
    async def test_create_basic(self):
        """Test basic record creation."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            user = await db.express.create(
                model_name,
                {
                    "id": "user-001",
                    "name": "Alice",
                    "email": "alice@example.com",
                    "active": True,
                },
            )

            assert user is not None
            assert user["id"] == "user-001"
            assert user["name"] == "Alice"
            assert user["email"] == "alice@example.com"
            assert user["active"] is True

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_create_with_defaults(self):
        """Test record creation with default values."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create without specifying 'active' - should use default True from DB
            user = await db.express.create(
                model_name,
                {"id": "user-002", "name": "Bob", "email": "bob@example.com"},
            )

            assert user is not None
            assert user["id"] == "user-002"
            # active defaults to True in the database schema

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_create_multiple_records(self):
        """Test creating multiple records sequentially."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            users = []
            for i in range(3):
                user = await db.express.create(
                    model_name,
                    {
                        "id": f"user-{i:03d}",
                        "name": f"User {i}",
                        "email": f"user{i}@example.com",
                    },
                )
                users.append(user)

            assert len(users) == 3
            assert users[0]["id"] == "user-000"
            assert users[1]["id"] == "user-001"
            assert users[2]["id"] == "user-002"

            db.close()
        finally:
            await cleanup_test_table(table_name)

    # ========================================================================
    # Read Operations
    # ========================================================================

    @pytest.mark.asyncio
    async def test_read_by_id(self):
        """Test reading a record by ID."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create a record first
            await db.express.create(
                model_name,
                {
                    "id": "user-read-001",
                    "name": "Charlie",
                    "email": "charlie@example.com",
                },
            )

            # Read it back
            user = await db.express.read(model_name, "user-read-001")

            assert user is not None
            assert user["id"] == "user-read-001"
            assert user["name"] == "Charlie"

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_read_nonexistent(self):
        """Test reading a nonexistent record returns None."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            user = await db.express.read(model_name, "nonexistent-id")
            assert user is None

            db.close()
        finally:
            await cleanup_test_table(table_name)

    # ========================================================================
    # Find One Operations (Non-PK Lookup)
    # ========================================================================

    @pytest.mark.asyncio
    async def test_find_one_by_email(self):
        """Test finding a single record by non-PK field (email)."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create a record first
            await db.express.create(
                model_name,
                {
                    "id": "user-find-001",
                    "name": "FindMe",
                    "email": "findme@example.com",
                },
            )

            # Find by email (non-PK field)
            user = await db.express.find_one(
                model_name, {"email": "findme@example.com"}
            )

            assert user is not None
            assert user["id"] == "user-find-001"
            assert user["name"] == "FindMe"
            assert user["email"] == "findme@example.com"

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_find_one_with_multiple_criteria(self):
        """Test finding a record with multiple filter criteria."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create multiple records
            await db.express.create(
                model_name,
                {
                    "id": "user-find-002",
                    "name": "Alice",
                    "email": "alice@example.com",
                    "active": True,
                },
            )
            await db.express.create(
                model_name,
                {
                    "id": "user-find-003",
                    "name": "Bob",
                    "email": "bob@example.com",
                    "active": False,
                },
            )

            # Find with multiple criteria
            user = await db.express.find_one(
                model_name, {"name": "Bob", "active": False}
            )

            assert user is not None
            assert user["id"] == "user-find-003"
            assert user["name"] == "Bob"
            assert user["active"] is False

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_find_one_returns_none_when_not_found(self):
        """Test find_one returns None when no record matches."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create a record
            await db.express.create(
                model_name,
                {
                    "id": "user-find-004",
                    "name": "Charlie",
                    "email": "charlie@example.com",
                },
            )

            # Find with non-matching criteria
            user = await db.express.find_one(
                model_name, {"email": "nonexistent@example.com"}
            )

            assert user is None

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_find_one_requires_non_empty_filter(self):
        """Test find_one raises ValueError with empty filter."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Empty filter should raise ValueError
            with pytest.raises(ValueError, match="requires a non-empty filter"):
                await db.express.find_one(model_name, {})

            db.close()
        finally:
            await cleanup_test_table(table_name)

    # ========================================================================
    # Update Operations
    # ========================================================================

    @pytest.mark.asyncio
    async def test_update_single_field(self):
        """Test updating a single field."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create
            await db.express.create(
                model_name,
                {"id": "user-update-001", "name": "Dave", "email": "dave@example.com"},
            )

            # Update
            updated = await db.express.update(
                model_name,
                "user-update-001",
                {"name": "David"},
            )

            assert updated is not None
            assert updated["id"] == "user-update-001"
            assert updated["name"] == "David"
            assert updated["email"] == "dave@example.com"  # unchanged

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self):
        """Test updating multiple fields at once."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create
            await db.express.create(
                model_name,
                {
                    "id": "user-update-002",
                    "name": "Eve",
                    "email": "eve@example.com",
                    "active": True,
                },
            )

            # Update multiple fields
            updated = await db.express.update(
                model_name,
                "user-update-002",
                {"name": "Eva", "email": "eva@newdomain.com", "active": False},
            )

            assert updated is not None
            assert updated["name"] == "Eva"
            assert updated["email"] == "eva@newdomain.com"
            assert updated["active"] is False

            db.close()
        finally:
            await cleanup_test_table(table_name)

    # ========================================================================
    # Delete Operations
    # ========================================================================

    @pytest.mark.asyncio
    async def test_delete_record(self):
        """Test deleting a record."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create
            await db.express.create(
                model_name,
                {
                    "id": "user-delete-001",
                    "name": "Frank",
                    "email": "frank@example.com",
                },
            )

            # Verify exists
            user = await db.express.read(model_name, "user-delete-001")
            assert user is not None

            # Delete
            result = await db.express.delete(model_name, "user-delete-001")
            assert result is True

            # Verify deleted
            user = await db.express.read(model_name, "user-delete-001")
            assert user is None

            db.close()
        finally:
            await cleanup_test_table(table_name)

    # ========================================================================
    # List Operations
    # ========================================================================

    @pytest.mark.asyncio
    async def test_list_all_records(self):
        """Test listing all records."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create multiple records
            for i in range(5):
                await db.express.create(
                    model_name,
                    {
                        "id": f"user-list-{i:03d}",
                        "name": f"User {i}",
                        "email": f"user{i}@example.com",
                    },
                )

            # List all
            users = await db.express.list(model_name)

            assert len(users) == 5

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_list_with_filter(self):
        """Test listing records with filter."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create records with different active states
            await db.express.create(
                model_name,
                {
                    "id": "user-filter-001",
                    "name": "Active 1",
                    "email": "a1@example.com",
                    "active": True,
                },
            )
            await db.express.create(
                model_name,
                {
                    "id": "user-filter-002",
                    "name": "Inactive 1",
                    "email": "i1@example.com",
                    "active": False,
                },
            )
            await db.express.create(
                model_name,
                {
                    "id": "user-filter-003",
                    "name": "Active 2",
                    "email": "a2@example.com",
                    "active": True,
                },
            )

            # List only active users
            active_users = await db.express.list(model_name, filter={"active": True})

            assert len(active_users) == 2

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_list_with_limit(self):
        """Test listing records with limit."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create multiple records
            for i in range(10):
                await db.express.create(
                    model_name,
                    {
                        "id": f"user-limit-{i:03d}",
                        "name": f"User {i}",
                        "email": f"user{i}@example.com",
                    },
                )

            # List with limit
            users = await db.express.list(model_name, limit=3)

            assert len(users) == 3

            db.close()
        finally:
            await cleanup_test_table(table_name)


class TestExpressDataFlowBulkOperations:
    """Integration tests for ExpressDataFlow bulk operations."""

    @pytest.mark.asyncio
    async def test_bulk_create(self):
        """Test bulk create operation."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            records = [
                {
                    "id": f"bulk-{i:03d}",
                    "name": f"Bulk User {i}",
                    "email": f"bulk{i}@example.com",
                }
                for i in range(5)
            ]

            result = await db.express.bulk_create(model_name, records)

            assert result is not None
            assert len(result) == 5

            # Verify all created
            all_users = await db.express.list(model_name)
            assert len(all_users) == 5

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_bulk_delete(self):
        """Test bulk delete operation."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create records
            for i in range(5):
                await db.express.create(
                    model_name,
                    {
                        "id": f"bulk-del-{i:03d}",
                        "name": f"Bulk Delete {i}",
                        "email": f"bd{i}@example.com",
                    },
                )

            # Delete some
            ids_to_delete = ["bulk-del-001", "bulk-del-003"]
            result = await db.express.bulk_delete(model_name, ids_to_delete)

            assert result is True

            # Verify remaining
            remaining = await db.express.list(model_name)
            assert len(remaining) == 3

            db.close()
        finally:
            await cleanup_test_table(table_name)


class TestExpressDataFlowUpsert:
    """Integration tests for ExpressDataFlow upsert operations."""

    @pytest.mark.asyncio
    async def test_upsert_insert(self):
        """Test upsert when record doesn't exist (insert)."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            result = await db.express.upsert(
                model_name,
                {
                    "id": "upsert-001",
                    "name": "Upsert New",
                    "email": "upsert@example.com",
                },
            )

            assert result is not None
            assert result["id"] == "upsert-001"
            assert result["name"] == "Upsert New"

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_upsert_update(self):
        """Test upsert when record exists (update)."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create initial record
            await db.express.create(
                model_name,
                {
                    "id": "upsert-002",
                    "name": "Original",
                    "email": "original@example.com",
                },
            )

            # Upsert with same ID - should update
            result = await db.express.upsert(
                model_name,
                {"id": "upsert-002", "name": "Updated", "email": "updated@example.com"},
            )

            assert result is not None
            assert result["id"] == "upsert-002"
            assert result["name"] == "Updated"
            assert result["email"] == "updated@example.com"

            # Verify only one record exists
            all_users = await db.express.list(model_name)
            assert len(all_users) == 1

            db.close()
        finally:
            await cleanup_test_table(table_name)


class TestExpressDataFlowCount:
    """Integration tests for ExpressDataFlow count operations."""

    @pytest.mark.asyncio
    async def test_count_all(self):
        """Test counting all records."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create records
            for i in range(7):
                await db.express.create(
                    model_name,
                    {
                        "id": f"count-{i:03d}",
                        "name": f"Count User {i}",
                        "email": f"count{i}@example.com",
                    },
                )

            count = await db.express.count(model_name)
            assert count == 7

            db.close()
        finally:
            await cleanup_test_table(table_name)

    @pytest.mark.asyncio
    async def test_count_with_filter(self):
        """Test counting records with filter."""
        suffix = get_unique_suffix()
        table_name = f"test_users_express{suffix}"
        model_suffix = suffix.replace("_", "").replace("-", "")

        await setup_test_table(table_name)
        try:
            db, model_name = create_dataflow_with_model(table_name, model_suffix)
            await db.initialize()

            # Create records with different active states
            for i in range(4):
                await db.express.create(
                    model_name,
                    {
                        "id": f"count-active-{i:03d}",
                        "name": f"Active {i}",
                        "email": f"a{i}@example.com",
                        "active": True,
                    },
                )
            for i in range(3):
                await db.express.create(
                    model_name,
                    {
                        "id": f"count-inactive-{i:03d}",
                        "name": f"Inactive {i}",
                        "email": f"ia{i}@example.com",
                        "active": False,
                    },
                )

            active_count = await db.express.count(model_name, filter={"active": True})
            inactive_count = await db.express.count(
                model_name, filter={"active": False}
            )

            assert active_count == 4
            assert inactive_count == 3

            db.close()
        finally:
            await cleanup_test_table(table_name)
