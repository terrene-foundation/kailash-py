"""Unit tests for migration models."""

import hashlib
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.utils.migrations.models import (
    DataMigration,
    Migration,
    MigrationHistory,
    MigrationPlan,
    SchemaMigration,
)


class TestMigrationHistory:
    """Test MigrationHistory dataclass."""

    def test_migration_history_creation(self):
        """Test creating migration history record."""
        now = datetime.now(UTC)
        history = MigrationHistory(
            migration_id="001_initial",
            applied_at=now,
            applied_by="test_user",
            execution_time=1.5,
            success=True,
            error_message=None,
            rollback_at=None,
            rollback_by=None,
        )

        assert history.migration_id == "001_initial"
        assert history.applied_at == now
        assert history.applied_by == "test_user"
        assert history.execution_time == 1.5
        assert history.success is True
        assert history.error_message is None
        assert history.rollback_at is None
        assert history.rollback_by is None

    def test_migration_history_with_error(self):
        """Test creating migration history with error."""
        now = datetime.now(UTC)
        history = MigrationHistory(
            migration_id="002_failed",
            applied_at=now,
            applied_by="test_user",
            execution_time=0.5,
            success=False,
            error_message="Table already exists",
        )

        assert history.success is False
        assert history.error_message == "Table already exists"

    def test_migration_history_with_rollback(self):
        """Test creating migration history with rollback info."""
        applied_at = datetime.now(UTC)
        rollback_at = datetime.now(UTC)

        history = MigrationHistory(
            migration_id="003_rolled_back",
            applied_at=applied_at,
            applied_by="test_user",
            execution_time=2.0,
            success=True,
            error_message=None,
            rollback_at=rollback_at,
            rollback_by="admin_user",
        )

        assert history.rollback_at == rollback_at
        assert history.rollback_by == "admin_user"


class TestMigration:
    """Test Migration base class."""

    def test_migration_requires_id(self):
        """Test migration requires id to be set."""

        class TestMigration(Migration):
            description = "Test migration"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        with pytest.raises(ValueError, match="Migration must have an id"):
            TestMigration()

    def test_migration_requires_description(self):
        """Test migration requires description to be set."""

        class TestMigration(Migration):
            id = "001_test"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        with pytest.raises(ValueError, match="Migration must have a description"):
            TestMigration()

    def test_valid_migration(self):
        """Test creating a valid migration."""

        class TestMigration(Migration):
            id = "001_test"
            description = "Test migration"
            dependencies = ["000_initial"]

            async def forward(self, connection):
                await connection.execute("CREATE TABLE test (id INT)")

            async def backward(self, connection):
                await connection.execute("DROP TABLE test")

        migration = TestMigration()
        assert migration.id == "001_test"
        assert migration.description == "Test migration"
        assert migration.dependencies == ["000_initial"]

    @pytest.mark.asyncio
    async def test_migration_validate_default(self):
        """Test default validation returns True."""

        class TestMigration(Migration):
            id = "001_test"
            description = "Test migration"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestMigration()
        mock_connection = Mock()

        result = await migration.validate(mock_connection)
        assert result is True

    @pytest.mark.asyncio
    async def test_migration_custom_validation(self):
        """Test custom validation logic."""

        class TestMigration(Migration):
            id = "001_test"
            description = "Test migration"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

            async def validate(self, connection):
                # Custom validation
                result = await connection.fetch_one("SELECT 1")
                return result is not None

        migration = TestMigration()
        mock_connection = AsyncMock()
        mock_connection.fetch_one.return_value = {"result": 1}

        result = await migration.validate(mock_connection)
        assert result is True
        mock_connection.fetch_one.assert_called_once_with("SELECT 1")

    def test_migration_get_hash(self):
        """Test migration hash generation."""

        class TestMigration(Migration):
            id = "001_test"
            description = "Test migration"
            dependencies = ["000_initial", "000_base"]

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestMigration()
        hash_value = migration.get_hash()

        # Verify hash format
        assert isinstance(hash_value, str)
        assert len(hash_value) == 16  # First 16 chars of SHA256

        # Verify deterministic
        hash_value2 = migration.get_hash()
        assert hash_value == hash_value2

        # Verify content-based
        expected_content = "001_test:Test migration:000_initial,000_base"
        expected_hash = hashlib.sha256(expected_content.encode()).hexdigest()[:16]
        assert hash_value == expected_hash

    @pytest.mark.asyncio
    async def test_migration_forward_backward_abstract(self):
        """Test forward and backward are abstract methods."""
        # Can't instantiate without implementing abstract methods
        with pytest.raises(TypeError):
            Migration()


class TestSchemaMigration:
    """Test SchemaMigration class."""

    def test_schema_migration_initialization(self):
        """Test schema migration initialization."""

        class TestSchemaMigration(SchemaMigration):
            id = "001_schema"
            description = "Schema test"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestSchemaMigration()
        assert migration.operations == []

    def test_add_table_operation(self):
        """Test adding create table operation."""

        class TestSchemaMigration(SchemaMigration):
            id = "001_schema"
            description = "Add users table"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestSchemaMigration()

        columns = [
            {"name": "id", "type": "INT", "primary_key": True},
            {"name": "email", "type": "VARCHAR(255)", "nullable": False},
            {"name": "created_at", "type": "TIMESTAMP", "default": "CURRENT_TIMESTAMP"},
        ]
        indexes = [{"name": "idx_email", "columns": ["email"], "unique": True}]

        migration.add_table("users", columns, indexes)

        assert len(migration.operations) == 1
        op = migration.operations[0]
        assert op["type"] == "create_table"
        assert op["table"] == "users"
        assert op["columns"] == columns
        assert op["indexes"] == indexes

    def test_drop_table_operation(self):
        """Test adding drop table operation."""

        class TestSchemaMigration(SchemaMigration):
            id = "002_schema"
            description = "Drop legacy table"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestSchemaMigration()
        migration.drop_table("legacy_users")

        assert len(migration.operations) == 1
        op = migration.operations[0]
        assert op["type"] == "drop_table"
        assert op["table"] == "legacy_users"

    def test_add_column_operation(self):
        """Test adding column operation."""

        class TestSchemaMigration(SchemaMigration):
            id = "003_schema"
            description = "Add column"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestSchemaMigration()
        migration.add_column(
            "users", "phone", "VARCHAR(20)", nullable=True, default=None
        )

        assert len(migration.operations) == 1
        op = migration.operations[0]
        assert op["type"] == "add_column"
        assert op["table"] == "users"
        assert op["column"] == "phone"
        assert op["column_type"] == "VARCHAR(20)"
        assert op["nullable"] is True
        assert op["default"] is None

    def test_drop_column_operation(self):
        """Test dropping column operation."""

        class TestSchemaMigration(SchemaMigration):
            id = "004_schema"
            description = "Drop column"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestSchemaMigration()
        migration.drop_column("users", "deprecated_field")

        assert len(migration.operations) == 1
        op = migration.operations[0]
        assert op["type"] == "drop_column"
        assert op["table"] == "users"
        assert op["column"] == "deprecated_field"

    def test_add_index_operation(self):
        """Test adding index operation."""

        class TestSchemaMigration(SchemaMigration):
            id = "005_schema"
            description = "Add index"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestSchemaMigration()
        migration.add_index("users", "idx_created_at", ["created_at"], unique=False)

        assert len(migration.operations) == 1
        op = migration.operations[0]
        assert op["type"] == "create_index"
        assert op["table"] == "users"
        assert op["index"] == "idx_created_at"
        assert op["columns"] == ["created_at"]
        assert op["unique"] is False

    def test_drop_index_operation(self):
        """Test dropping index operation."""

        class TestSchemaMigration(SchemaMigration):
            id = "006_schema"
            description = "Drop index"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestSchemaMigration()
        migration.drop_index("users", "idx_old_index")

        assert len(migration.operations) == 1
        op = migration.operations[0]
        assert op["type"] == "drop_index"
        assert op["table"] == "users"
        assert op["index"] == "idx_old_index"

    def test_multiple_operations(self):
        """Test adding multiple operations."""

        class TestSchemaMigration(SchemaMigration):
            id = "007_schema"
            description = "Complex migration"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestSchemaMigration()

        # Add multiple operations
        migration.add_table("posts", [{"name": "id", "type": "INT"}])
        migration.add_column("users", "status", "VARCHAR(20)")
        migration.add_index("posts", "idx_user_id", ["user_id"])

        assert len(migration.operations) == 3
        assert migration.operations[0]["type"] == "create_table"
        assert migration.operations[1]["type"] == "add_column"
        assert migration.operations[2]["type"] == "create_index"


class TestDataMigration:
    """Test DataMigration class."""

    def test_data_migration_initialization(self):
        """Test data migration initialization."""

        class TestDataMigration(DataMigration):
            id = "001_data"
            description = "Data migration"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestDataMigration()
        assert migration.batch_size == 1000

    def test_data_migration_custom_batch_size(self):
        """Test setting custom batch size."""

        class TestDataMigration(DataMigration):
            id = "002_data"
            description = "Large data migration"

            def __init__(self):
                super().__init__()
                self.batch_size = 5000

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestDataMigration()
        assert migration.batch_size == 5000

    @pytest.mark.asyncio
    async def test_process_batch_not_implemented(self):
        """Test process_batch raises NotImplementedError."""

        class TestDataMigration(DataMigration):
            id = "003_data"
            description = "Batch processing"

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migration = TestDataMigration()

        with pytest.raises(NotImplementedError):
            await migration.process_batch(Mock(), "SELECT 1")


class TestMigrationPlan:
    """Test MigrationPlan dataclass."""

    def test_migration_plan_creation(self):
        """Test creating migration plan."""
        plan = MigrationPlan()

        assert plan.migrations_to_apply == []
        assert plan.migrations_to_rollback == []
        assert plan.dependency_order == []
        assert plan.estimated_time == 0.0
        assert plan.warnings == []

    def test_migration_plan_with_data(self):
        """Test creating migration plan with data."""

        class MockMigration(Migration):
            def __init__(self, id, description, dependencies=None):
                self.id = id
                self.description = description
                self.dependencies = dependencies or []

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migrations = [
            MockMigration("001", "First"),
            MockMigration("002", "Second", ["001"]),
        ]

        plan = MigrationPlan(
            migrations_to_apply=migrations,
            dependency_order=["001", "002"],
            estimated_time=5.0,
        )

        assert len(plan.migrations_to_apply) == 2
        assert plan.dependency_order == ["001", "002"]
        assert plan.estimated_time == 5.0

    def test_add_warning(self):
        """Test adding warnings to plan."""
        plan = MigrationPlan()

        plan.add_warning("This migration may take a long time")
        plan.add_warning("Backup recommended")

        assert len(plan.warnings) == 2
        assert "This migration may take a long time" in plan.warnings
        assert "Backup recommended" in plan.warnings

    def test_is_safe_with_rollbacks(self):
        """Test plan is unsafe with rollbacks."""
        plan = MigrationPlan()
        plan.migrations_to_rollback = [Mock()]

        assert plan.is_safe() is False

    def test_is_safe_with_valid_dependencies(self):
        """Test plan is safe with valid dependencies."""

        class MockMigration(Migration):
            def __init__(self, id, dependencies=None):
                self.id = id
                self.description = "Test"
                self.dependencies = dependencies or []

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migrations = [
            MockMigration("001"),
            MockMigration("002", ["001"]),
            MockMigration("003", ["001", "002"]),
        ]

        plan = MigrationPlan(
            migrations_to_apply=migrations, dependency_order=["001", "002", "003"]
        )

        assert plan.is_safe() is True

    def test_is_safe_with_circular_dependencies(self):
        """Test plan is unsafe with circular dependencies."""

        class MockMigration(Migration):
            def __init__(self, id, dependencies=None):
                self.id = id
                self.description = "Test"
                self.dependencies = dependencies or []

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migrations = [
            MockMigration("001", ["002"]),  # Depends on 002
            MockMigration("002", ["001"]),  # Depends on 001 - circular!
        ]

        plan = MigrationPlan(
            migrations_to_apply=migrations, dependency_order=["001", "002"]
        )

        assert plan.is_safe() is False

    def test_is_safe_with_missing_dependency(self):
        """Test plan is unsafe with missing dependency."""

        class MockMigration(Migration):
            def __init__(self, id, dependencies=None):
                self.id = id
                self.description = "Test"
                self.dependencies = dependencies or []

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migrations = [
            MockMigration("002", ["001"])
        ]  # Depends on 001 which is not in plan

        plan = MigrationPlan(migrations_to_apply=migrations, dependency_order=["002"])

        # This should be safe because 001 might already be applied
        assert plan.is_safe() is True

    def test_is_safe_with_out_of_order_dependencies(self):
        """Test plan is unsafe with out-of-order dependencies."""

        class MockMigration(Migration):
            def __init__(self, id, dependencies=None):
                self.id = id
                self.description = "Test"
                self.dependencies = dependencies or []

            async def forward(self, connection):
                pass

            async def backward(self, connection):
                pass

        migrations = [MockMigration("001"), MockMigration("002", ["001"])]

        # Wrong order - 002 before 001
        plan = MigrationPlan(
            migrations_to_apply=migrations, dependency_order=["002", "001"]
        )

        assert plan.is_safe() is False
