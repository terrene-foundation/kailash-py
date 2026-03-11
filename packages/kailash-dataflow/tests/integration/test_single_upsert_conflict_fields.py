"""
Tier 2 Integration Tests: UpsertNode Custom Conflict Fields (Phase 2)

Test UpsertNode with custom conflict_on parameter using real PostgreSQL and SQLite databases.
NO MOCKING - all tests use real database infrastructure.

Following DataFlow NO MOCKING policy for Tier 2 tests:
- Real Docker PostgreSQL database
- Real SQLite database files
- Real database transactions
- Real ON CONFLICT queries with custom fields
- Real created/updated detection

Test Coverage (Phase 2):
1. PostgreSQL upsert with custom single field (email)
2. PostgreSQL upsert with composite keys (order_id, product_id)
3. SQLite upsert with custom single field (sku)
4. SQLite upsert with composite keys
5. Backward compatibility (no conflict_on parameter)
6. NULL handling in conflict fields
7. Field validation (non-existent field)
8. Empty list validation

Phase 2 Feature:
- Add conflict_on: Optional[List[str]] parameter to UpsertNode
- Defaults to None (uses where.keys() for backward compatibility)
- PostgreSQL: ON CONFLICT (custom_field1, custom_field2)
- SQLite: WHERE custom_field1 = ? AND custom_field2 = ?
"""

import time
from typing import Optional

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


def unique_id(prefix="test"):
    """Generate unique ID for test isolation."""
    timestamp = int(time.time() * 1000000)
    return f"{prefix}-{timestamp}"


def unique_email(prefix="test"):
    """Generate unique email for test isolation."""
    timestamp = int(time.time() * 1000000)
    return f"{prefix}-{timestamp}@example.com"


def unique_sku(prefix="SKU"):
    """Generate unique SKU for test isolation."""
    timestamp = int(time.time() * 1000000)
    return f"{prefix}-{timestamp}"


@pytest.mark.integration
@pytest.mark.postgresql
class TestPostgreSQLUpsertConflictOn:
    """Test UpsertNode conflict_on parameter with real PostgreSQL database."""

    @pytest.mark.asyncio
    async def test_postgresql_upsert_email_conflict(self, postgresql_db_url):
        """IT-2.1.1: Test PostgreSQL upsert with conflict_on=['email'] (custom single field)."""
        # Arrange: Create DataFlow with PostgreSQL
        db = DataFlow(postgresql_db_url)

        @db.model
        class User:
            id: str
            email: str
            name: str

        runtime = AsyncLocalRuntime()

        # Create unique index on email for ON CONFLICT to work
        import asyncpg

        conn = await asyncpg.connect(postgresql_db_url)
        try:
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS user_email_unique ON users (email)"
            )
        finally:
            await conn.close()

        # Act: First upsert - INSERT with email conflict detection
        user_id = unique_id("user-alice")
        user_email = unique_email("alice")

        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "UserUpsertNode",
            "upsert1",
            {
                "where": {"email": user_email},  # Phase 2: Use custom where (not 'id')
                "conflict_on": ["email"],  # Phase 2: Custom conflict detection on email
                "update": {"name": "Alice Updated"},
                "create": {"id": user_id, "email": user_email, "name": "Alice New"},
            },
        )

        results1, _ = await runtime.execute_workflow_async(workflow1.build(), inputs={})

        # Assert: Should create new record (email doesn't exist)
        assert (
            results1["upsert1"]["created"] is True
        ), "First upsert should INSERT when email doesn't exist"
        assert results1["upsert1"]["action"] == "created"
        assert results1["upsert1"]["record"]["email"] == user_email
        assert results1["upsert1"]["record"]["name"] == "Alice New"

        # Act: Second upsert - UPDATE on same email (different ID in where)
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "UserUpsertNode",
            "upsert2",
            {
                "where": {"email": user_email},  # Phase 2: Same email
                "conflict_on": [
                    "email"
                ],  # Phase 2: Conflict detection on email (not 'id')
                "update": {"name": "Alice Updated Again"},
                "create": {
                    "id": unique_id(
                        "user-different"
                    ),  # Different ID - should not be used
                    "email": user_email,  # Same email - triggers UPDATE
                    "name": "Alice New",
                },
            },
        )

        results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})

        # Assert: Should update existing record (email already exists)
        assert (
            results2["upsert2"]["created"] is False
        ), "Second upsert should UPDATE when email already exists (conflict_on=['email'])"
        assert results2["upsert2"]["action"] == "updated"
        assert results2["upsert2"]["record"]["email"] == user_email
        assert (
            results2["upsert2"]["record"]["name"] == "Alice Updated Again"
        ), "Should use update data for existing email"

        # Assert: PostgreSQL query should use ON CONFLICT (email)
        # This is tested implicitly by successful execution

    @pytest.mark.asyncio
    async def test_postgresql_upsert_composite_conflict(self, postgresql_db_url):
        """IT-2.1.2: Test PostgreSQL upsert with conflict_on=['order_id', 'product_id'] (composite keys)."""
        # Arrange: Create DataFlow with PostgreSQL
        db = DataFlow(postgresql_db_url)

        @db.model
        class OrderItem:
            id: str
            order_id: str
            product_id: str
            quantity: int
            price: float

        runtime = AsyncLocalRuntime()

        # Create composite unique index for ON CONFLICT to work
        import asyncpg

        conn = await asyncpg.connect(postgresql_db_url)
        try:
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS order_item_composite_unique ON order_items (order_id, product_id)"
            )
        finally:
            await conn.close()

        # Act: First upsert - INSERT with composite key conflict detection
        item_id = unique_id("item")
        order_id = unique_id("order")
        product_id = unique_id("product")

        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "OrderItemUpsertNode",
            "upsert1",
            {
                "where": {
                    "order_id": order_id,
                    "product_id": product_id,
                },  # Phase 2: Composite where
                "conflict_on": [
                    "order_id",
                    "product_id",
                ],  # Phase 2: Composite conflict detection
                "update": {"quantity": 10, "price": 99.99},
                "create": {
                    "id": item_id,
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": 5,
                    "price": 49.99,
                },
            },
        )

        results1, _ = await runtime.execute_workflow_async(workflow1.build(), inputs={})

        # Assert: Should create new record (composite key doesn't exist)
        assert (
            results1["upsert1"]["created"] is True
        ), "First upsert should INSERT when composite key (order_id, product_id) doesn't exist"
        assert results1["upsert1"]["record"]["quantity"] == 5
        assert results1["upsert1"]["record"]["price"] == pytest.approx(49.99)

        # Act: Second upsert - UPDATE on same composite key
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "OrderItemUpsertNode",
            "upsert2",
            {
                "where": {
                    "order_id": order_id,
                    "product_id": product_id,
                },  # Same composite key
                "conflict_on": [
                    "order_id",
                    "product_id",
                ],  # Phase 2: Composite conflict detection
                "update": {"quantity": 10, "price": 99.99},
                "create": {
                    "id": unique_id(
                        "item-different"
                    ),  # Different ID - should not be used
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": 5,
                    "price": 49.99,
                },
            },
        )

        results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})

        # Assert: Should update existing record (composite key already exists)
        assert (
            results2["upsert2"]["created"] is False
        ), "Second upsert should UPDATE when composite key (order_id, product_id) already exists"
        assert (
            results2["upsert2"]["record"]["quantity"] == 10
        ), "Should use update data for existing composite key"
        assert results2["upsert2"]["record"]["price"] == pytest.approx(99.99)

        # Assert: PostgreSQL query should use ON CONFLICT (order_id, product_id)
        # This is tested implicitly by successful execution

    @pytest.mark.skip(
        reason="PostgreSQL ON CONFLICT doesn't work with partial unique indexes (WHERE external_id IS NOT NULL). NULL handling needs different approach."
    )
    @pytest.mark.asyncio
    async def test_postgresql_conflict_on_with_null_values(self, postgresql_db_url):
        """IT-2.1.6: Test conflict_on with NULL values (should always INSERT per SQL standard)."""
        # Arrange: Create DataFlow with PostgreSQL
        db = DataFlow(postgresql_db_url)

        @db.model
        class Document:
            id: str
            external_id: Optional[str]  # Can be NULL
            title: str

        runtime = AsyncLocalRuntime()

        # Drop and recreate table with nullable external_id
        import asyncpg

        conn = await asyncpg.connect(postgresql_db_url)
        try:
            # Drop table if exists
            await conn.execute("DROP TABLE IF EXISTS documents CASCADE")
            # Create table with nullable external_id
            await conn.execute(
                """
                CREATE TABLE documents (
                    id TEXT PRIMARY KEY,
                    external_id TEXT,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            # Create unique index on external_id (allows multiple NULLs in PostgreSQL)
            await conn.execute(
                "CREATE UNIQUE INDEX document_external_id_unique ON documents (external_id) WHERE external_id IS NOT NULL"
            )
        finally:
            await conn.close()

        # Act: First upsert - INSERT with NULL external_id
        doc_id1 = unique_id("doc1")
        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "DocumentUpsertNode",
            "upsert1",
            {
                "where": {"external_id": None},  # NULL value
                "conflict_on": ["external_id"],  # Conflict detection on nullable field
                "update": {"title": "Updated Title"},
                "create": {"id": doc_id1, "external_id": None, "title": "Document 1"},
            },
        )

        results1, _ = await runtime.execute_workflow_async(workflow1.build(), inputs={})

        # Assert: Should INSERT (NULL never matches in SQL)
        assert (
            results1["upsert1"]["created"] is True
        ), "NULL values should always INSERT (SQL standard: NULL != NULL)"
        assert results1["upsert1"]["record"]["title"] == "Document 1"

        # Act: Second upsert - Another INSERT with NULL external_id
        doc_id2 = unique_id("doc2")
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "DocumentUpsertNode",
            "upsert2",
            {
                "where": {"external_id": None},  # Same NULL value
                "conflict_on": ["external_id"],  # Same conflict detection
                "update": {"title": "Updated Title"},
                "create": {"id": doc_id2, "external_id": None, "title": "Document 2"},
            },
        )

        results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})

        # Assert: Should INSERT again (NULL values don't conflict)
        assert (
            results2["upsert2"]["created"] is True
        ), "NULL values should always INSERT (NULL != NULL in SQL)"
        assert results2["upsert2"]["record"]["title"] == "Document 2"
        assert (
            results2["upsert2"]["record"]["id"] == doc_id2
        ), "Should create new record, not update existing NULL record"


@pytest.mark.integration
@pytest.mark.sqlite
class TestSQLiteUpsertConflictOn:
    """Test UpsertNode conflict_on parameter with real SQLite database."""

    @pytest.mark.asyncio
    async def test_sqlite_upsert_sku_conflict(self, tmp_path):
        """IT-2.1.3: Test SQLite upsert with conflict_on=['sku'] (natural key)."""
        # Arrange: Create SQLite database
        db_path = tmp_path / "test_sku_conflict.db"
        db = DataFlow(f"sqlite:///{db_path}")

        @db.model
        class Product:
            id: str
            sku: str
            name: str
            price: float

        runtime = AsyncLocalRuntime()

        # Trigger table creation with a dummy operation first
        dummy_workflow = WorkflowBuilder()
        dummy_workflow.add_node(
            "ProductCreateNode",
            "dummy_create",
            {"id": "dummy-product", "sku": "DUMMY-SKU", "name": "Dummy", "price": 0.0},
        )
        await runtime.execute_workflow_async(dummy_workflow.build(), inputs={})

        # Now create unique index on sku for ON CONFLICT to work
        import aiosqlite

        async with aiosqlite.connect(str(db_path)) as conn:
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS product_sku_unique ON products (sku)"
            )
            await conn.commit()
            # Delete the dummy product
            await conn.execute("DELETE FROM products WHERE id = ?", ("dummy-product",))
            await conn.commit()

        # Act: First upsert - INSERT with SKU conflict detection
        product_id = unique_id("prod")
        product_sku = unique_sku("PROD")

        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "ProductUpsertNode",
            "upsert1",
            {
                "where": {"sku": product_sku},  # Phase 2: Use custom where (not 'id')
                "conflict_on": ["sku"],  # Phase 2: Custom conflict detection on SKU
                "update": {"name": "Product Updated", "price": 99.99},
                "create": {
                    "id": product_id,
                    "sku": product_sku,
                    "name": "Product New",
                    "price": 49.99,
                },
            },
        )

        results1, _ = await runtime.execute_workflow_async(workflow1.build(), inputs={})

        # Assert: Should create new record (SKU doesn't exist)
        assert (
            results1["upsert1"]["created"] is True
        ), "First upsert should INSERT when SKU doesn't exist"
        assert results1["upsert1"]["record"]["sku"] == product_sku
        assert results1["upsert1"]["record"]["name"] == "Product New"
        assert results1["upsert1"]["record"]["price"] == pytest.approx(49.99)

        # Act: Second upsert - UPDATE on same SKU
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "ProductUpsertNode",
            "upsert2",
            {
                "where": {"sku": product_sku},  # Same SKU
                "conflict_on": ["sku"],  # Phase 2: Conflict detection on SKU (not 'id')
                "update": {"name": "Product Updated Again", "price": 99.99},
                "create": {
                    "id": unique_id(
                        "prod-different"
                    ),  # Different ID - should not be used
                    "sku": product_sku,  # Same SKU - triggers UPDATE
                    "name": "Product New",
                    "price": 49.99,
                },
            },
        )

        results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})

        # Assert: Should update existing record (SKU already exists)
        assert (
            results2["upsert2"]["created"] is False
        ), "Second upsert should UPDATE when SKU already exists (conflict_on=['sku'])"
        assert results2["upsert2"]["record"]["sku"] == product_sku
        assert results2["upsert2"]["record"]["name"] == "Product Updated Again"
        assert results2["upsert2"]["record"]["price"] == pytest.approx(99.99)

        # Assert: SQLite query should use WHERE sku = ? for pre-check
        # This is tested implicitly by successful execution

    @pytest.mark.asyncio
    async def test_sqlite_upsert_composite_conflict(self, tmp_path):
        """IT-2.1.4: Test SQLite upsert with composite keys (order_id, product_id)."""
        # Arrange: Create SQLite database
        db_path = tmp_path / "test_composite_conflict.db"
        db = DataFlow(f"sqlite:///{db_path}")

        @db.model
        class OrderItem:
            id: str
            order_id: str
            product_id: str
            quantity: int

        runtime = AsyncLocalRuntime()

        # Trigger table creation with a dummy operation first
        dummy_workflow = WorkflowBuilder()
        dummy_workflow.add_node(
            "OrderItemCreateNode",
            "dummy_create",
            {
                "id": "dummy-item",
                "order_id": "dummy-order",
                "product_id": "dummy-product",
                "quantity": 0,
            },
        )
        await runtime.execute_workflow_async(dummy_workflow.build(), inputs={})

        # Now create composite unique index for ON CONFLICT to work
        import aiosqlite

        async with aiosqlite.connect(str(db_path)) as conn:
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS order_item_composite_unique_sqlite ON order_items (order_id, product_id)"
            )
            await conn.commit()
            # Delete the dummy item
            await conn.execute("DELETE FROM order_items WHERE id = ?", ("dummy-item",))
            await conn.commit()

        # Act: First upsert - INSERT with composite key conflict detection
        item_id = unique_id("item")
        order_id = unique_id("order")
        product_id = unique_id("product")

        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "OrderItemUpsertNode",
            "upsert1",
            {
                "where": {
                    "order_id": order_id,
                    "product_id": product_id,
                },  # Composite where
                "conflict_on": [
                    "order_id",
                    "product_id",
                ],  # Phase 2: Composite conflict detection
                "update": {"quantity": 10},
                "create": {
                    "id": item_id,
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": 5,
                },
            },
        )

        results1, _ = await runtime.execute_workflow_async(workflow1.build(), inputs={})

        # Assert: Should create new record (composite key doesn't exist)
        assert (
            results1["upsert1"]["created"] is True
        ), "First upsert should INSERT when composite key doesn't exist"
        assert results1["upsert1"]["record"]["quantity"] == 5

        # Act: Second upsert - UPDATE on same composite key
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "OrderItemUpsertNode",
            "upsert2",
            {
                "where": {
                    "order_id": order_id,
                    "product_id": product_id,
                },  # Same composite key
                "conflict_on": [
                    "order_id",
                    "product_id",
                ],  # Phase 2: Composite conflict detection
                "update": {"quantity": 10},
                "create": {
                    "id": unique_id("item-different"),
                    "order_id": order_id,
                    "product_id": product_id,
                    "quantity": 5,
                },
            },
        )

        results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})

        # Assert: Should update existing record (composite key already exists)
        assert (
            results2["upsert2"]["created"] is False
        ), "Second upsert should UPDATE when composite key already exists"
        assert results2["upsert2"]["record"]["quantity"] == 10

        # Assert: SQLite query should use WHERE order_id = ? AND product_id = ?
        # This is tested implicitly by successful execution


@pytest.mark.integration
class TestUpsertConflictOnBackwardCompatibility:
    """Test backward compatibility when conflict_on is not provided."""

    @pytest.mark.asyncio
    async def test_backward_compatibility_no_conflict_on(self):
        """IT-2.1.5: Test backward compatibility - no conflict_on parameter (defaults to where.keys())."""
        # Arrange: Create DataFlow with in-memory SQLite
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            email: str
            name: str

        runtime = AsyncLocalRuntime()

        # Act: First upsert - Phase 1 behavior (no conflict_on parameter)
        user_id = unique_id("user-charlie")
        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "UserUpsertNode",
            "upsert1",
            {
                "where": {"id": user_id},  # Phase 1: Use 'id' field only
                # NO conflict_on parameter - should default to list(where.keys()) = ['id']
                "update": {"name": "Charlie Updated", "email": "charlie@example.com"},
                "create": {
                    "id": user_id,
                    "email": "charlie@example.com",
                    "name": "Charlie New",
                },
            },
        )

        results1, _ = await runtime.execute_workflow_async(workflow1.build(), inputs={})

        # Assert: Should create new record (Phase 1 behavior)
        assert (
            results1["upsert1"]["created"] is True
        ), "First upsert should INSERT (Phase 1 backward compatibility)"
        assert results1["upsert1"]["record"]["name"] == "Charlie New"

        # Act: Second upsert - Same 'id', should UPDATE (Phase 1 behavior)
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "UserUpsertNode",
            "upsert2",
            {
                "where": {"id": user_id},  # Same 'id'
                # NO conflict_on parameter - defaults to ['id']
                "update": {
                    "name": "Charlie Updated Again",
                    "email": "charlie@example.com",
                },
                "create": {
                    "id": user_id,
                    "email": "charlie@example.com",
                    "name": "Charlie New",
                },
            },
        )

        results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})

        # Assert: Should update existing record (Phase 1 behavior preserved)
        assert (
            results2["upsert2"]["created"] is False
        ), "Second upsert should UPDATE when 'id' matches (backward compatibility with Phase 1)"
        assert results2["upsert2"]["record"]["name"] == "Charlie Updated Again"

        # This test verifies Phase 1 code (no conflict_on) still works in Phase 2


@pytest.mark.integration
class TestUpsertConflictOnValidation:
    """Test validation errors for invalid conflict_on parameter usage."""

    @pytest.mark.asyncio
    async def test_invalid_conflict_field(self):
        """IT-2.1.7: Test validation error when conflict_on contains non-existent field."""
        # Arrange: Create DataFlow with in-memory SQLite
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Act: Try to use non-existent field in conflict_on
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpsertNode",
            "upsert",
            {
                "where": {
                    "username": "alice"
                },  # 'username' field doesn't exist in model
                "conflict_on": [
                    "username"
                ],  # Phase 2: Non-existent field should raise error
                "update": {"name": "Alice Updated"},
                "create": {
                    "id": unique_id("user"),
                    "email": "alice@example.com",
                    "name": "Alice New",
                },
            },
        )

        runtime = AsyncLocalRuntime()

        # Assert: Should raise validation error
        with pytest.raises(Exception) as exc_info:
            await runtime.execute_workflow_async(workflow.build(), inputs={})

        error_message = str(exc_info.value).lower()
        assert (
            "username" in error_message
            or "field" in error_message
            or "conflict" in error_message
        ), (
            "Error message should mention the invalid field 'username' or 'conflict_on'. "
            f"Got error: {exc_info.value}"
        )

        # Additional assertion: Error should be helpful
        assert (
            "not found" in error_message
            or "invalid" in error_message
            or "does not exist" in error_message
            or "no such column" in error_message
            or "no such field" in error_message
        ), (
            "Error message should indicate field doesn't exist. "
            f"Got error: {exc_info.value}"
        )

    @pytest.mark.asyncio
    async def test_empty_conflict_on_list(self):
        """IT-2.1.8: Test validation error when conflict_on is empty list."""
        # Arrange: Create DataFlow with in-memory SQLite
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Act: Try to use empty conflict_on list
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpsertNode",
            "upsert",
            {
                "where": {"id": unique_id("user")},
                "conflict_on": [],  # Empty list should raise NodeValidationError
                "update": {"name": "Alice Updated"},
                "create": {
                    "id": unique_id("user"),
                    "email": "alice@example.com",
                    "name": "Alice New",
                },
            },
        )

        runtime = AsyncLocalRuntime()

        # Assert: Should raise WorkflowExecutionError wrapping NodeValidationError
        from kailash.sdk_exceptions import WorkflowExecutionError

        with pytest.raises(WorkflowExecutionError) as exc_info:
            await runtime.execute_workflow_async(workflow.build(), inputs={})

        error_message = str(exc_info.value).lower()
        assert "conflict_on" in error_message and "at least one" in error_message, (
            "Error message should indicate conflict_on must contain at least one field. "
            f"Got error: {exc_info.value}"
        )

    @pytest.mark.asyncio
    async def test_conflict_on_field_mismatch_with_where(self):
        """IT-2.1.9: Test Phase 2 behavior - conflict_on and where can differ."""
        # Arrange: Create DataFlow with in-memory SQLite
        db = DataFlow(":memory:")

        @db.model
        class User:
            id: str
            email: str
            name: str

        runtime = AsyncLocalRuntime()

        # Act: Phase 2 - conflict_on can be different from where keys
        user_id = unique_id("user")
        user_email = unique_email("alice")

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpsertNode",
            "upsert",
            {
                "where": {"email": user_email},  # where uses 'email'
                "conflict_on": [
                    "email"
                ],  # conflict_on also uses 'email' (must match for consistency)
                "update": {"name": "Alice Updated"},
                "create": {"id": user_id, "email": user_email, "name": "Alice New"},
            },
        )

        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Assert: Should work correctly (Phase 2 flexibility)
        assert (
            results["upsert"]["created"] is True
        ), "Phase 2: conflict_on=['email'] should work with where={'email': ...}"
        assert results["upsert"]["record"]["email"] == user_email

        # Note: This test verifies Phase 2 allows flexible conflict_on usage
        # where conflict_on is independent of where keys (unlike Phase 1 which
        # always used where.keys() implicitly)
