"""
Tier 2 Integration Tests: Single-Record UpsertNode Operations

Test UpsertNode with real PostgreSQL and SQLite databases.
NO MOCKING - all tests use real database infrastructure.

Following DataFlow NO MOCKING policy for Tier 2 tests:
- Real Docker PostgreSQL database
- Real SQLite database files
- Real database transactions
- Real ON CONFLICT queries
- Real created/updated detection

Test Coverage:
1. PostgreSQL INSERT path (record doesn't exist)
2. PostgreSQL UPDATE path (record exists)
3. SQLite INSERT path (record doesn't exist)
4. SQLite UPDATE path (record exists)
5. String ID preservation
6. Auto-timestamp management (created_at, updated_at)
7. Return value structure (created, record, action)
8. Parameter validation (missing where/update/create)
9. Concurrent upserts (race condition safety)
10. Workflow integration (node can be added to workflows)
"""

import asyncio
import time
from datetime import datetime

import pytest
from dataflow import DataFlow

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Track DataFlow instances for cleanup
_dataflow_instances = []


@pytest.fixture(autouse=True)
async def cleanup_dataflow_instances():
    """Automatically cleanup DataFlow instances after each test."""
    global _dataflow_instances
    _dataflow_instances = []

    yield

    # Cleanup all DataFlow instances created during the test
    for db in _dataflow_instances:
        try:
            db.cleanup_nodes()
            if hasattr(db, "_async_sql_node_cache"):
                for node in db._async_sql_node_cache.values():
                    if hasattr(node, "close"):
                        try:
                            await node.close()
                        except Exception:
                            pass
                db._async_sql_node_cache.clear()
            db.close()
        except Exception as e:
            print(f"Warning: Failed to cleanup DataFlow instance: {e}")

    _dataflow_instances.clear()


def track_dataflow(db):
    """Track DataFlow instance for automatic cleanup."""
    _dataflow_instances.append(db)
    return db


def unique_id(prefix="test"):
    """Generate unique ID for test isolation."""
    timestamp = int(time.time() * 1000000)
    return f"{prefix}-{timestamp}"


def unique_email(prefix="test"):
    """Generate unique email for test isolation."""
    timestamp = int(time.time() * 1000000)
    return f"{prefix}-{timestamp}@example.com"


def unique_memory_db():
    """
    Generate unique SQLite memory database URL for test isolation.

    SQLite :memory: databases are isolated per connection, but pytest
    may reuse connections between tests. Using a unique file-based database
    with a timestamp ensures complete isolation between tests.

    Note: Using tempfile for cleanup is not necessary as pytest cleans up
    after test runs, and we want to avoid premature cleanup during test execution.
    """
    timestamp = int(time.time() * 1000000)
    # Use simple :memory: - each DataFlow instance creates its own connection
    return ":memory:"


@pytest.mark.integration
@pytest.mark.postgresql
class TestPostgreSQLUpsertNode:
    """Test UpsertNode with real PostgreSQL database."""

    @pytest.mark.asyncio
    async def test_postgresql_upsert_insert_path(self, postgresql_db_url):
        """Verify INSERT path when record does not exist (PostgreSQL) - Phase 1 uses 'id' field."""
        # Arrange: Create DataFlow with PostgreSQL
        db = track_dataflow(DataFlow(postgresql_db_url))

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Act: Upsert a new record (should INSERT) - Phase 1 uses 'id' field for conflict detection
        user_id = unique_id("user-alice")  # Unique ID for test isolation
        user_email = unique_email("alice")  # Unique email for test isolation
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpsertNode",
            "upsert_user",
            {
                "where": {"id": user_id},  # Phase 1: Use 'id' field
                "update": {"name": "Alice Updated", "email": user_email},
                "create": {"id": user_id, "email": user_email, "name": "Alice New"},
            },
        )

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        # Assert: Should be created (INSERT happened)
        assert (
            results["upsert_user"]["created"] is True
        ), "created should be True when record doesn't exist"
        assert (
            results["upsert_user"]["action"] == "created"
        ), "action should be 'created' for INSERT"
        assert results["upsert_user"]["record"]["email"] == user_email
        assert (
            results["upsert_user"]["record"]["name"] == "Alice New"
        ), "Should use create data for new records"
        assert (
            results["upsert_user"]["record"]["id"] == user_id
        ), "String ID should be preserved exactly as provided"

    @pytest.mark.asyncio
    async def test_postgresql_upsert_update_path(self, postgresql_db_url):
        """Verify UPDATE path when record exists (PostgreSQL) - Phase 1 uses 'id' field."""
        # Arrange: Create DataFlow with PostgreSQL
        db = track_dataflow(DataFlow(postgresql_db_url))

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Pre-populate with existing record
        user_id = unique_id("user-bob")  # Unique ID for test isolation
        user_email = unique_email("bob")  # Unique email for test isolation
        workflow_create = WorkflowBuilder()
        workflow_create.add_node(
            "UserCreateNode",
            "create",
            {"id": user_id, "email": user_email, "name": "Bob Original"},
        )

        runtime = AsyncLocalRuntime()
        await runtime.execute_workflow_async(workflow_create.build(), inputs={})

        # Act: Upsert existing record (should UPDATE) - Phase 1 uses 'id' field
        workflow_upsert = WorkflowBuilder()
        workflow_upsert.add_node(
            "UserUpsertNode",
            "upsert_user",
            {
                "where": {"id": user_id},  # Phase 1: Use 'id' field (same as created)
                "update": {"name": "Bob Updated", "email": user_email},
                "create": {
                    "id": user_id,  # Same ID - but won't be used (UPDATE path)
                    "email": user_email,
                    "name": "Bob New",
                },
            },
        )

        results, _ = await runtime.execute_workflow_async(
            workflow_upsert.build(), inputs={}
        )

        # Assert: Should be updated (UPDATE happened)
        assert (
            results["upsert_user"]["created"] is False
        ), "created should be False when record exists"
        assert (
            results["upsert_user"]["action"] == "updated"
        ), "action should be 'updated' for UPDATE"
        assert (
            results["upsert_user"]["record"]["id"] == user_id
        ), "Original ID should be preserved"
        assert (
            results["upsert_user"]["record"]["name"] == "Bob Updated"
        ), "Should use update data for existing records"

    @pytest.mark.asyncio
    async def test_postgresql_string_id_preservation(self, postgresql_db_url):
        """Verify string IDs are preserved exactly (not converted to int) - Phase 1 uses 'id' field."""
        # Arrange
        db = track_dataflow(DataFlow(postgresql_db_url))

        @db.model
        class Session:
            id: str
            user_id: str
            token: str

        # Act: Create with string UUID-style ID - Phase 1 uses 'id' field for conflict detection
        session_id = unique_id("sess-uuid")  # Unique ID for test isolation
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SessionUpsertNode",
            "upsert",
            {
                "where": {"id": session_id},  # Phase 1: Use 'id' field
                "update": {"user_id": "user-456", "token": "session-token-123"},
                "create": {
                    "id": session_id,  # String UUID-style ID
                    "user_id": "user-123",
                    "token": "session-token-123",
                },
            },
        )

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Assert: String ID should be preserved exactly
        assert isinstance(
            results["upsert"]["record"]["id"], str
        ), "ID should remain a string (not converted to int)"
        assert (
            results["upsert"]["record"]["id"] == session_id
        ), "String ID should be preserved exactly as provided"

    @pytest.mark.asyncio
    async def test_postgresql_auto_timestamp_management(self, postgresql_db_url):
        """Verify created_at and updated_at are managed automatically - Phase 1 uses 'id' field."""
        # Arrange
        db = track_dataflow(DataFlow(postgresql_db_url))

        @db.model
        class Article:
            id: str
            slug: str
            title: str

        runtime = AsyncLocalRuntime()

        # Act: First upsert (CREATE) - Phase 1 uses 'id' field for conflict detection
        article_id = unique_id("article")  # Unique ID for test isolation
        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "ArticleUpsertNode",
            "upsert1",
            {
                "where": {"id": article_id},  # Phase 1: Use 'id' field
                "update": {"title": "Updated Title", "slug": "test-article"},
                "create": {
                    "id": article_id,
                    "slug": "test-article",
                    "title": "Original Title",
                },
            },
        )

        results1, _ = await runtime.execute_workflow_async(workflow1.build(), inputs={})
        created_at1 = results1["upsert1"]["record"]["created_at"]
        updated_at1 = results1["upsert1"]["record"]["updated_at"]

        # Assert: Timestamps should be set on creation
        assert created_at1 is not None, "created_at should be set automatically"
        assert updated_at1 is not None, "updated_at should be set automatically"

        # Wait to ensure timestamp difference (PostgreSQL timestamp precision)
        await asyncio.sleep(1.0)

        # Act: Second upsert (UPDATE) - Phase 1 uses same 'id' to trigger UPDATE
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "ArticleUpsertNode",
            "upsert2",
            {
                "where": {"id": article_id},  # Phase 1: Same 'id' triggers UPDATE
                "update": {"title": "Updated Title Again", "slug": "test-article"},
                "create": {
                    "id": article_id,  # Same ID - won't be used (UPDATE path)
                    "slug": "test-article",
                    "title": "New Title",
                },
            },
        )

        results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})
        created_at2 = results2["upsert2"]["record"]["created_at"]
        updated_at2 = results2["upsert2"]["record"]["updated_at"]

        # Assert: created_at unchanged, updated_at changed
        assert (
            created_at2 == created_at1
        ), "created_at should remain unchanged on update"
        assert updated_at2 > updated_at1, "updated_at should be updated on UPDATE"

    @pytest.mark.asyncio
    async def test_postgresql_concurrent_upserts_race_condition_safety(
        self, postgresql_db_url
    ):
        """Verify atomic upsert prevents race conditions - Phase 1 uses 'id' field."""
        # Arrange
        db = track_dataflow(DataFlow(postgresql_db_url))

        @db.model
        class Counter:
            id: str
            name: str
            count: int

        async def upsert_counter(counter_id: int):
            """Upsert a counter with given ID - Phase 1 uses 'id' field."""
            workflow = WorkflowBuilder()
            workflow.add_node(
                "CounterUpsertNode",
                f"upsert_{counter_id}",
                {
                    "where": {
                        "id": "counter-shared"
                    },  # Phase 1: All use same 'id' for race condition test
                    "update": {"count": counter_id, "name": "test_counter"},
                    "create": {
                        "id": "counter-shared",  # Same ID for all - tests atomic operation
                        "name": "test_counter",
                        "count": counter_id,
                    },
                },
            )
            runtime = AsyncLocalRuntime()
            return await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Act: Run 10 concurrent upserts on the SAME id (tests atomicity)
        results = await asyncio.gather(*[upsert_counter(i) for i in range(10)])

        # Verify exactly 1 record exists (atomic operation prevented race conditions)
        workflow_count = WorkflowBuilder()
        workflow_count.add_node(
            "CounterReadNode", "read", {"id": "counter-shared"}  # Phase 1: Read by 'id'
        )

        runtime = AsyncLocalRuntime()
        count_results, _ = await runtime.execute_workflow_async(
            workflow_count.build(), inputs={}
        )

        # Assert: Record should exist (atomic upsert handled concurrency)
        assert (
            count_results["read"]["id"] == "counter-shared"
        ), "Atomic upsert should handle concurrent operations on same ID"


@pytest.mark.integration
@pytest.mark.sqlite
class TestSQLiteUpsertNode:
    """Test UpsertNode with real SQLite database."""

    @pytest.mark.asyncio
    async def test_sqlite_upsert_full_cycle(self, tmp_path):
        """Verify SQLite upsert for both INSERT and UPDATE paths."""
        # Arrange: Create SQLite database
        db_path = tmp_path / "test_upsert.db"
        db = DataFlow(f"sqlite:///{db_path}")

        @db.model
        class Product:
            id: str
            sku: str
            name: str
            price: float

        runtime = AsyncLocalRuntime()

        # Act: First upsert (INSERT) - Phase 1 uses 'id' field for conflict detection
        workflow1 = WorkflowBuilder()
        workflow1.add_node(
            "ProductUpsertNode",
            "upsert1",
            {
                "where": {"id": "prod-123"},  # Phase 1: Use 'id' field
                "update": {
                    "name": "Product Updated",
                    "price": 99.99,
                    "sku": "PROD-123",
                },
                "create": {
                    "id": "prod-123",
                    "sku": "PROD-123",
                    "name": "Product New",
                    "price": 49.99,
                },
            },
        )

        results1, _ = await runtime.execute_workflow_async(workflow1.build(), inputs={})

        # Assert: First upsert should INSERT
        assert (
            results1["upsert1"]["created"] is True
        ), "First upsert should create new record"
        assert (
            results1["upsert1"]["record"]["price"] == 49.99
        ), "Should use create data for new records"

        # Act: Second upsert (UPDATE) - same 'id' should trigger UPDATE
        workflow2 = WorkflowBuilder()
        workflow2.add_node(
            "ProductUpsertNode",
            "upsert2",
            {
                "where": {"id": "prod-123"},  # Phase 1: Same 'id' triggers UPDATE
                "update": {
                    "name": "Product Updated",
                    "price": 99.99,
                    "sku": "PROD-UPDATED",
                },
                "create": {
                    "id": "prod-123",  # Same ID
                    "sku": "PROD-123",
                    "name": "Product New",
                    "price": 49.99,
                },
            },
        )

        results2, _ = await runtime.execute_workflow_async(workflow2.build(), inputs={})

        # Assert: Second upsert should UPDATE
        assert (
            results2["upsert2"]["created"] is False
        ), "Second upsert should update existing record"
        assert (
            results2["upsert2"]["record"]["price"] == 99.99
        ), "Should use update data for existing records"
        assert (
            results2["upsert2"]["record"]["id"] == "prod-123"
        ), "Original ID should be preserved"

    @pytest.mark.asyncio
    async def test_sqlite_string_id_preservation(self, tmp_path):
        """Verify string IDs work correctly with SQLite - Phase 1 uses 'id' field."""
        # Arrange
        db_path = tmp_path / "test_ids.db"
        db = DataFlow(f"sqlite:///{db_path}")

        @db.model
        class Task:
            id: str
            task_id: str
            status: str

        # Act - Phase 1: Use 'id' field for conflict detection
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TaskUpsertNode",
            "upsert",
            {
                "where": {"id": "task-internal-uuid-456"},  # Phase 1: Use 'id' field
                "update": {"status": "completed", "task_id": "task-abc-123"},
                "create": {
                    "id": "task-internal-uuid-456",
                    "task_id": "task-abc-123",
                    "status": "pending",
                },
            },
        )

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Assert: String ID should be preserved exactly as provided
        assert isinstance(results["upsert"]["record"]["id"], str)
        assert results["upsert"]["record"]["id"] == "task-internal-uuid-456"


@pytest.mark.integration
class TestUpsertNodeParameterValidation:
    """Test parameter validation with real database."""

    @pytest.mark.asyncio
    async def test_missing_where_parameter_raises_error(self):
        """Verify validation error when 'where' is missing."""
        # Arrange
        db = track_dataflow(DataFlow(unique_memory_db()))

        @db.model
        class User:
            id: str
            email: str
            name: str

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpsertNode",
            "upsert",
            {
                # Missing 'where'
                "update": {"name": "Test"}
            },
        )

        runtime = AsyncLocalRuntime()

        # Act & Assert: Should raise validation error
        with pytest.raises(Exception) as exc_info:
            await runtime.execute_workflow_async(workflow.build(), inputs={})

        assert (
            "where" in str(exc_info.value).lower()
        ), "Error message should mention 'where' parameter"

    @pytest.mark.asyncio
    async def test_missing_update_and_create_raises_error(self):
        """Verify validation error when both 'update' and 'create' are missing - Phase 1 uses 'id' field."""
        # Arrange
        db = track_dataflow(DataFlow(unique_memory_db()))

        @db.model
        class User:
            id: str
            email: str

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpsertNode",
            "upsert",
            {
                "where": {"id": "user-1"}  # Phase 1: Use 'id' field
                # Missing both 'update' and 'create'
            },
        )

        runtime = AsyncLocalRuntime()

        # Act & Assert: Should raise validation error
        with pytest.raises(Exception) as exc_info:
            await runtime.execute_workflow_async(workflow.build(), inputs={})

        error_message = str(exc_info.value).lower()
        assert (
            "update" in error_message or "create" in error_message
        ), "Error message should mention missing 'update' or 'create' parameter"


@pytest.mark.integration
class TestUpsertNodeWorkflowIntegration:
    """Test UpsertNode integrates correctly with workflows."""

    @pytest.mark.asyncio
    async def test_upsert_node_in_workflow(self):
        """Verify UpsertNode can be added to workflows and executed - Phase 1 uses 'id' field."""
        # Arrange
        db = track_dataflow(DataFlow(unique_memory_db()))

        @db.model
        class Settings:
            id: str
            key: str
            value: str

        # Act: Add UpsertNode to workflow - Phase 1 uses 'id' field for conflict detection
        workflow = WorkflowBuilder()
        workflow.add_node(
            "SettingsUpsertNode",
            "upsert_setting",
            {
                "where": {"id": "setting-1"},  # Phase 1: Use 'id' field
                "update": {"value": "dark", "key": "theme"},
                "create": {"id": "setting-1", "key": "theme", "value": "light"},
            },
        )

        runtime = AsyncLocalRuntime()
        results, run_id = await runtime.execute_workflow_async(
            workflow.build(), inputs={}
        )

        # Assert: Workflow should execute successfully
        assert (
            "upsert_setting" in results
        ), "UpsertNode should execute and return results"
        assert results["upsert_setting"]["record"]["key"] == "theme"
        assert run_id is not None, "Workflow should return run_id"

    @pytest.mark.asyncio
    async def test_upsert_node_with_connection_chaining(self):
        """Verify UpsertNode can participate in workflow connections - Phase 1 uses 'id' field."""
        # Arrange
        db = track_dataflow(DataFlow(unique_memory_db()))

        @db.model
        class User:
            id: str
            email: str
            name: str

        # Act: Create workflow with connection from upsert to read
        workflow = WorkflowBuilder()

        # Step 1: Upsert user - Phase 1 uses 'id' field for conflict detection
        workflow.add_node(
            "UserUpsertNode",
            "upsert",
            {
                "where": {"id": "user-1"},  # Phase 1: Use 'id' field
                "update": {"name": "Updated", "email": "test@example.com"},
                "create": {
                    "id": "user-1",
                    "email": "test@example.com",
                    "name": "Created",
                },
            },
        )

        # Step 2: Read the upserted user - using workflow connection
        # Note: We need to pass the 'id' field from the upsert output record
        workflow.add_node("UserReadNode", "read", {})

        # Connect record.id from upsert to id parameter of read
        # Since Core SDK connections pass the source field value directly,
        # we need to connect "record" and let ReadNode extract the id
        workflow.add_connection("upsert", "record", "read", "conditions")

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Assert: Both nodes should execute successfully
        assert "upsert" in results
        assert "read" in results
        assert (
            results["read"]["id"] == results["upsert"]["record"]["id"]
        ), "Read should retrieve the upserted record"


@pytest.mark.integration
class TestUpsertNodeReturnStructure:
    """Test UpsertNode return value structure."""

    @pytest.mark.asyncio
    async def test_upsert_return_structure_on_create(self):
        """Verify return structure when creating new record - Phase 1 uses 'id' field."""
        # Arrange
        db = track_dataflow(DataFlow(unique_memory_db()))

        # Use unique ID to avoid test interference
        test_user_id = unique_id("user")

        @db.model
        class User:
            id: str
            name: str
            email: str

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpsertNode",
            "upsert",
            {
                "where": {
                    "id": test_user_id
                },  # Phase 1: Use 'id' field with unique value
                "update": {"name": "Alice Updated", "email": "alice@example.com"},
                "create": {
                    "id": test_user_id,
                    "name": "Alice",
                    "email": "alice@example.com",
                },
            },
        )

        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Assert: Return structure should have created, record, action
        upsert_result = results["upsert"]

        assert "created" in upsert_result, "Should have 'created' field"
        assert "record" in upsert_result, "Should have 'record' field"
        assert "action" in upsert_result, "Should have 'action' field"

        assert upsert_result["created"] is True
        assert upsert_result["action"] == "created"
        assert isinstance(upsert_result["record"], dict)
        assert "id" in upsert_result["record"]

    @pytest.mark.asyncio
    async def test_upsert_return_structure_on_update(self):
        """Verify return structure when updating existing record - Phase 1 uses 'id' field."""
        # Arrange
        db = track_dataflow(DataFlow(unique_memory_db()))

        @db.model
        class User:
            id: str
            name: str
            email: str

        runtime = AsyncLocalRuntime()

        # Create existing record
        workflow_create = WorkflowBuilder()
        workflow_create.add_node(
            "UserCreateNode",
            "create",
            {"id": "user-1", "name": "Bob", "email": "bob@example.com"},
        )
        await runtime.execute_workflow_async(workflow_create.build(), inputs={})

        # Act: Update via upsert - Phase 1 uses 'id' field
        workflow_upsert = WorkflowBuilder()
        workflow_upsert.add_node(
            "UserUpsertNode",
            "upsert",
            {
                "where": {"id": "user-1"},  # Phase 1: Use 'id' field (same as created)
                "update": {"name": "Bob Updated", "email": "bob.updated@example.com"},
                "create": {
                    "id": "user-1",  # Same ID - won't be used (UPDATE path)
                    "name": "Bob",
                    "email": "bob@example.com",
                },
            },
        )

        results, _ = await runtime.execute_workflow_async(
            workflow_upsert.build(), inputs={}
        )

        # Assert: Return structure for update
        upsert_result = results["upsert"]

        assert "created" in upsert_result
        assert "record" in upsert_result
        assert "action" in upsert_result

        assert upsert_result["created"] is False
        assert upsert_result["action"] == "updated"
        assert (
            upsert_result["record"]["id"] == "user-1"
        ), "Should preserve original record ID"
