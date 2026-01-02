"""Unit tests for migration runner."""

import asyncio
import time
from datetime import UTC, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Type
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
from kailash.utils.migrations.models import Migration, MigrationHistory, MigrationPlan
from kailash.utils.migrations.runner import MigrationRunner


def create_mock_connection_manager(mock_conn):
    """Helper to create a properly mocked connection manager."""
    # Set up the transaction context manager
    mock_transaction = MagicMock()
    mock_transaction.__aenter__ = AsyncMock(return_value=None)
    mock_transaction.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_transaction)

    # Set up the connection manager
    mock_cm = Mock()
    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_conn
    mock_context.__aexit__.return_value = None
    mock_cm.get_connection.return_value = mock_context
    return mock_cm


# Test migration classes (named to avoid pytest collection)
class MockMigration1(Migration):
    """Test migration 1."""

    id = "001_test_migration_1"
    description = "Test migration 1"
    dependencies = []

    async def forward(self, connection):
        await connection.execute("CREATE TABLE test1 (id INT)")

    async def backward(self, connection):
        await connection.execute("DROP TABLE test1")


class MockMigration2(Migration):
    """Test migration 2 with dependency."""

    id = "002_test_migration_2"
    description = "Test migration 2"
    dependencies = ["001_test_migration_1"]

    async def forward(self, connection):
        await connection.execute("CREATE TABLE test2 (id INT)")

    async def backward(self, connection):
        await connection.execute("DROP TABLE test2")


class MockMigration3(Migration):
    """Test migration 3 with multiple dependencies."""

    id = "003_test_migration_3"
    description = "Test migration 3"
    dependencies = ["001_test_migration_1", "002_test_migration_2"]

    async def forward(self, connection):
        await connection.execute("CREATE TABLE test3 (id INT)")

    async def backward(self, connection):
        await connection.execute("DROP TABLE test3")


class MockFailingMigration(Migration):
    """Test migration that fails."""

    id = "004_failing_migration"
    description = "Failing migration"
    dependencies = []

    async def forward(self, connection):
        raise Exception("Migration failed")

    async def backward(self, connection):
        raise Exception("Rollback failed")


class TestMigrationRunnerInitialization:
    """Test MigrationRunner initialization."""

    def test_init_default_values(self):
        """Test initialization with default values."""
        db_config = {"type": "postgresql"}
        runner = MigrationRunner(db_config)

        assert runner.db_config == db_config
        assert runner.tenant_id == "default"
        assert runner.migration_table == "kailash_migrations"
        assert runner.registered_migrations == {}
        assert runner._initialized is False

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        db_config = {"type": "mysql"}
        runner = MigrationRunner(
            db_config, tenant_id="tenant_123", migration_table="custom_migrations"
        )

        assert runner.tenant_id == "tenant_123"
        assert runner.migration_table == "custom_migrations"

    @patch("kailash.utils.migrations.runner.get_connection_manager")
    def test_connection_manager_initialization(self, mock_get_cm):
        """Test connection manager is properly initialized."""
        mock_cm = Mock()
        mock_get_cm.return_value = mock_cm

        runner = MigrationRunner({"type": "postgresql"})
        assert runner.connection_manager == mock_cm


class TestInitializeMethod:
    """Test initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_creates_table(self):
        """Test initialize creates migration table."""
        runner = MigrationRunner({"type": "postgresql"})

        mock_conn = AsyncMock()
        runner.connection_manager = create_mock_connection_manager(mock_conn)

        await runner.initialize()

        assert runner._initialized is True
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS kailash_migrations" in call_args

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        """Test initialize is idempotent."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = True

        mock_cm = Mock()
        runner.connection_manager = mock_cm

        await runner.initialize()

        # Should not create connection if already initialized
        mock_cm.get_connection.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_migration_table_postgresql(self):
        """Test PostgreSQL migration table creation."""
        runner = MigrationRunner({"type": "postgresql"})
        mock_conn = AsyncMock()

        await runner._create_migration_table(mock_conn)

        call_args = mock_conn.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS kailash_migrations" in call_args
        assert "migration_id VARCHAR(255) PRIMARY KEY" in call_args
        assert "applied_at TIMESTAMP NOT NULL" in call_args

    @pytest.mark.asyncio
    async def test_create_migration_table_mysql(self):
        """Test MySQL migration table creation."""
        runner = MigrationRunner({"type": "mysql"})
        mock_conn = AsyncMock()

        await runner._create_migration_table(mock_conn)

        call_args = mock_conn.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS kailash_migrations" in call_args
        assert "migration_id VARCHAR(255) PRIMARY KEY" in call_args

    @pytest.mark.asyncio
    async def test_create_migration_table_sqlite(self):
        """Test SQLite migration table creation."""
        runner = MigrationRunner({"type": "sqlite"})
        mock_conn = AsyncMock()

        await runner._create_migration_table(mock_conn)

        call_args = mock_conn.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS kailash_migrations" in call_args
        assert "migration_id TEXT PRIMARY KEY" in call_args
        assert "success INTEGER NOT NULL" in call_args

    @pytest.mark.asyncio
    async def test_create_migration_table_unsupported(self):
        """Test unsupported database type raises error."""
        runner = MigrationRunner({"type": "mongodb"})
        mock_conn = AsyncMock()

        with pytest.raises(ValueError, match="Unsupported database type: mongodb"):
            await runner._create_migration_table(mock_conn)


class TestMigrationRegistration:
    """Test migration registration."""

    def test_register_migration(self):
        """Test registering a migration."""
        runner = MigrationRunner({"type": "postgresql"})

        runner.register_migration(MockMigration1)

        assert "001_test_migration_1" in runner.registered_migrations
        assert runner.registered_migrations["001_test_migration_1"] == MockMigration1

    def test_register_duplicate_migration_raises_error(self):
        """Test registering duplicate migration raises error."""
        runner = MigrationRunner({"type": "postgresql"})

        runner.register_migration(MockMigration1)

        with pytest.raises(
            ValueError, match="Migration 001_test_migration_1 already registered"
        ):
            runner.register_migration(MockMigration1)

    def test_register_migrations_from_module(self):
        """Test registering all migrations from a module."""
        runner = MigrationRunner({"type": "postgresql"})

        # Create mock module
        mock_module = type(
            "Module",
            (),
            {
                "MockMigration1": MockMigration1,
                "MockMigration2": MockMigration2,
                "NotAMigration": str,
                "some_function": lambda: None,
            },
        )()

        runner.register_migrations_from_module(mock_module)

        assert "001_test_migration_1" in runner.registered_migrations
        assert "002_test_migration_2" in runner.registered_migrations
        assert len(runner.registered_migrations) == 2


class TestGetAppliedMigrations:
    """Test getting applied migrations."""

    @pytest.mark.asyncio
    async def test_get_applied_migrations(self):
        """Test getting list of applied migrations."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = True

        mock_conn = AsyncMock()
        mock_rows = [
            {"migration_id": "001_test_migration_1"},
            {"migration_id": "002_test_migration_2"},
        ]
        mock_conn.fetch.return_value = mock_rows

        runner.connection_manager = create_mock_connection_manager(mock_conn)

        applied = await runner.get_applied_migrations()

        assert applied == {"001_test_migration_1", "002_test_migration_2"}
        assert "success = true" in mock_conn.fetch.call_args[0][0]
        assert "rollback_at IS NULL" in mock_conn.fetch.call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_applied_migrations_initializes_if_needed(self):
        """Test get_applied_migrations initializes runner if needed."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = False

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []

        runner.connection_manager = create_mock_connection_manager(mock_conn)

        with patch.object(runner, "initialize", new_callable=AsyncMock) as mock_init:
            await runner.get_applied_migrations()
            mock_init.assert_called_once()


class TestGetMigrationHistory:
    """Test getting migration history."""

    @pytest.mark.asyncio
    async def test_get_all_migration_history(self):
        """Test getting all migration history."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = True

        mock_conn = AsyncMock()
        mock_rows = [
            {
                "migration_id": "001_test",
                "applied_at": datetime.now(UTC),
                "applied_by": "user1",
                "execution_time": 1.5,
                "success": True,
                "error_message": None,
                "rollback_at": None,
                "rollback_by": None,
            }
        ]
        mock_conn.fetch.return_value = mock_rows

        runner.connection_manager = create_mock_connection_manager(mock_conn)

        history = await runner.get_migration_history()

        assert len(history) == 1
        assert isinstance(history[0], MigrationHistory)
        assert history[0].migration_id == "001_test"

    @pytest.mark.asyncio
    async def test_get_specific_migration_history(self):
        """Test getting history for specific migration."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = True

        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []

        runner.connection_manager = create_mock_connection_manager(mock_conn)

        await runner.get_migration_history("001_specific")

        call_args = mock_conn.fetch.call_args
        assert "WHERE migration_id = $1" in call_args[0][0]
        assert call_args[0][1] == "001_specific"


class TestCreatePlan:
    """Test migration plan creation."""

    @pytest.mark.asyncio
    async def test_create_forward_plan(self):
        """Test creating forward migration plan."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = True

        # Register migrations
        runner.register_migration(MockMigration1)
        runner.register_migration(MockMigration2)
        runner.register_migration(MockMigration3)

        # Mock applied migrations
        with patch.object(runner, "get_applied_migrations", return_value=set()):
            plan = await runner.create_plan()

        assert len(plan.migrations_to_apply) == 3
        assert plan.migrations_to_apply[0].id == "001_test_migration_1"
        assert plan.migrations_to_apply[1].id == "002_test_migration_2"
        assert plan.migrations_to_apply[2].id == "003_test_migration_3"

    @pytest.mark.asyncio
    async def test_create_plan_with_applied_migrations(self):
        """Test creating plan skips applied migrations."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = True

        runner.register_migration(MockMigration1)
        runner.register_migration(MockMigration2)

        # Mock that migration 1 is already applied
        with patch.object(
            runner, "get_applied_migrations", return_value={"001_test_migration_1"}
        ):
            plan = await runner.create_plan()

        assert len(plan.migrations_to_apply) == 1
        assert plan.migrations_to_apply[0].id == "002_test_migration_2"

    @pytest.mark.asyncio
    async def test_create_plan_with_target_migration(self):
        """Test creating plan with target migration."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = True

        runner.register_migration(MockMigration1)
        runner.register_migration(MockMigration2)
        runner.register_migration(MockMigration3)

        with patch.object(runner, "get_applied_migrations", return_value=set()):
            plan = await runner.create_plan(target_migration="002_test_migration_2")

        assert len(plan.migrations_to_apply) == 2
        assert plan.migrations_to_apply[0].id == "001_test_migration_1"
        assert plan.migrations_to_apply[1].id == "002_test_migration_2"
        # Migration 3 should not be included

    @pytest.mark.asyncio
    async def test_create_rollback_plan(self):
        """Test creating rollback plan."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = True

        runner.register_migration(MockMigration1)

        # Mock that migration is applied
        with patch.object(
            runner, "get_applied_migrations", return_value={"001_test_migration_1"}
        ):
            plan = await runner.create_plan(
                target_migration="001_test_migration_1", rollback=True
            )

        assert len(plan.migrations_to_rollback) == 1
        assert plan.migrations_to_rollback[0].id == "001_test_migration_1"

    @pytest.mark.asyncio
    async def test_create_rollback_plan_without_target_raises_error(self):
        """Test rollback plan requires target migration."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = True

        # Mock connection manager to avoid real database connections
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        runner.connection_manager = create_mock_connection_manager(mock_conn)

        with pytest.raises(ValueError, match="target_migration required for rollback"):
            await runner.create_plan(rollback=True)

    @pytest.mark.asyncio
    async def test_create_plan_with_missing_dependencies(self):
        """Test plan warns about missing dependencies."""
        runner = MigrationRunner({"type": "postgresql"})
        runner._initialized = True

        # Only register migration 2, which depends on migration 1
        runner.register_migration(MockMigration2)

        with patch.object(runner, "get_applied_migrations", return_value=set()):
            plan = await runner.create_plan()

        assert "missing dependencies" in plan.warnings[0]
        assert "001_test_migration_1" in plan.warnings[0]


class TestTopologicalSort:
    """Test topological sorting of migrations."""

    def test_topological_sort_simple(self):
        """Test simple topological sort."""
        runner = MigrationRunner({"type": "postgresql"})

        migrations = [
            MockMigration1(),
            MockMigration2(),
            MockMigration3(),
        ]

        sorted_migrations = runner._topological_sort(migrations)

        assert len(sorted_migrations) == 3
        assert sorted_migrations[0].id == "001_test_migration_1"
        assert sorted_migrations[1].id == "002_test_migration_2"
        assert sorted_migrations[2].id == "003_test_migration_3"

    def test_topological_sort_circular_dependency(self):
        """Test circular dependency detection."""
        runner = MigrationRunner({"type": "postgresql"})

        # Create circular dependency
        class CircularMigration1(Migration):
            id = "circ_1"
            description = "Circular 1"
            dependencies = ["circ_2"]

            async def forward(self, conn):
                pass

            async def backward(self, conn):
                pass

        class CircularMigration2(Migration):
            id = "circ_2"
            description = "Circular 2"
            dependencies = ["circ_1"]

            async def forward(self, conn):
                pass

            async def backward(self, conn):
                pass

        migrations = [CircularMigration1(), CircularMigration2()]

        with pytest.raises(ValueError, match="Circular dependencies detected"):
            runner._topological_sort(migrations)


class TestExecutePlan:
    """Test plan execution."""

    @pytest.mark.asyncio
    async def test_execute_forward_plan(self):
        """Test executing forward migration plan."""
        runner = MigrationRunner({"type": "postgresql"})

        plan = MigrationPlan()
        plan.migrations_to_apply = [MockMigration1()]
        plan.dependency_order = ["001_test_migration_1"]

        with patch.object(
            runner, "_apply_migration", new_callable=AsyncMock
        ) as mock_apply:
            mock_apply.return_value = MigrationHistory(
                migration_id="001_test_migration_1",
                applied_at=datetime.now(UTC),
                applied_by="test",
                execution_time=1.0,
                success=True,
            )

            history = await runner.execute_plan(plan, user="test_user")

        assert len(history) == 1
        assert history[0].success is True
        mock_apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_plan_stops_on_failure(self):
        """Test execution stops on migration failure."""
        runner = MigrationRunner({"type": "postgresql"})

        plan = MigrationPlan()
        plan.migrations_to_apply = [MockMigration1(), MockMigration2()]
        plan.dependency_order = ["001_test_migration_1", "002_test_migration_2"]

        with patch.object(
            runner, "_apply_migration", new_callable=AsyncMock
        ) as mock_apply:
            # First migration fails
            mock_apply.return_value = MigrationHistory(
                migration_id="001_test_migration_1",
                applied_at=datetime.now(UTC),
                applied_by="test",
                execution_time=1.0,
                success=False,
                error_message="Failed",
            )

            history = await runner.execute_plan(plan)

        assert len(history) == 1
        assert history[0].success is False
        # Should only be called once, not for second migration
        mock_apply.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_rollback_plan(self):
        """Test executing rollback plan."""
        runner = MigrationRunner({"type": "postgresql"})

        plan = MigrationPlan()
        plan.migrations_to_rollback = [MockMigration1()]

        # Mock the is_safe method to return True
        with (
            patch.object(plan, "is_safe", return_value=True),
            patch.object(
                runner, "_rollback_migration", new_callable=AsyncMock
            ) as mock_rollback,
        ):
            mock_rollback.return_value = MigrationHistory(
                migration_id="001_test_migration_1",
                applied_at=datetime.now(UTC),
                applied_by="test",
                execution_time=1.0,
                success=True,
                rollback_at=datetime.now(UTC),
                rollback_by="test",
            )

            history = await runner.execute_plan(plan)

        assert len(history) == 1
        assert history[0].rollback_at is not None

    @pytest.mark.asyncio
    async def test_execute_unsafe_plan_raises_error(self):
        """Test executing unsafe plan raises error."""
        runner = MigrationRunner({"type": "postgresql"})

        plan = MigrationPlan()
        plan.migrations_to_rollback = [MockMigration1()]  # Rollback makes plan unsafe

        with pytest.raises(ValueError, match="Migration plan is not safe"):
            await runner.execute_plan(plan)


class TestApplyMigration:
    """Test applying individual migrations."""

    @pytest.mark.asyncio
    async def test_apply_migration_success(self):
        """Test successful migration application."""
        runner = MigrationRunner({"type": "postgresql"})

        mock_conn = AsyncMock()
        runner.connection_manager = create_mock_connection_manager(mock_conn)

        migration = MockMigration1()

        with patch.object(runner, "_record_migration", new_callable=AsyncMock):
            history = await runner._apply_migration(
                migration, "test_user", dry_run=False
            )

        assert history.success is True
        assert history.migration_id == "001_test_migration_1"
        mock_conn.execute.assert_called_once_with("CREATE TABLE test1 (id INT)")

    @pytest.mark.asyncio
    async def test_apply_migration_validation_failure(self):
        """Test migration validation failure."""
        runner = MigrationRunner({"type": "postgresql"})

        mock_conn = AsyncMock()
        runner.connection_manager = create_mock_connection_manager(mock_conn)

        # Create migration that fails validation
        class FailingValidationMigration(Migration):
            id = "fail_validation"
            description = "Fails validation"
            dependencies = []

            async def forward(self, conn):
                pass

            async def backward(self, conn):
                pass

            async def validate(self, conn):
                return False

        migration = FailingValidationMigration()

        history = await runner._apply_migration(migration, "test_user", dry_run=False)

        assert history.success is False
        assert "validation failed" in history.error_message

    @pytest.mark.asyncio
    async def test_apply_migration_dry_run(self):
        """Test dry run doesn't execute migration."""
        runner = MigrationRunner({"type": "postgresql"})

        mock_conn = AsyncMock()
        runner.connection_manager = create_mock_connection_manager(mock_conn)

        migration = MockMigration1()

        history = await runner._apply_migration(migration, "test_user", dry_run=True)

        # Should validate but not execute
        assert history.success is True
        # execute should not be called for actual migration
        assert mock_conn.execute.call_count == 0

    @pytest.mark.asyncio
    async def test_apply_migration_records_failure(self):
        """Test failed migration is recorded."""
        runner = MigrationRunner({"type": "postgresql"})

        mock_conn = AsyncMock()
        runner.connection_manager = create_mock_connection_manager(mock_conn)

        migration = MockFailingMigration()

        with patch.object(
            runner, "_record_migration", new_callable=AsyncMock
        ) as mock_record:
            history = await runner._apply_migration(
                migration, "test_user", dry_run=False
            )

        assert history.success is False
        # Should be called to record the failure
        mock_record.assert_called_once()
        call_args = mock_record.call_args[0]
        assert call_args[4] is False  # success parameter
        assert "Migration failed" in call_args[5]  # error message


class TestRollbackMigration:
    """Test rolling back migrations."""

    @pytest.mark.asyncio
    async def test_rollback_migration_success(self):
        """Test successful migration rollback."""
        runner = MigrationRunner({"type": "postgresql"})

        mock_conn = AsyncMock()
        runner.connection_manager = create_mock_connection_manager(mock_conn)

        migration = MockMigration1()

        with patch.object(runner, "_update_migration_rollback", new_callable=AsyncMock):
            history = await runner._rollback_migration(
                migration, "test_user", dry_run=False
            )

        assert history.success is True
        assert history.rollback_at is not None
        mock_conn.execute.assert_called_once_with("DROP TABLE test1")

    @pytest.mark.asyncio
    async def test_rollback_migration_failure(self):
        """Test failed migration rollback."""
        runner = MigrationRunner({"type": "postgresql"})

        mock_conn = AsyncMock()
        runner.connection_manager = create_mock_connection_manager(mock_conn)

        migration = MockFailingMigration()

        history = await runner._rollback_migration(
            migration, "test_user", dry_run=False
        )

        assert history.success is False
        assert "Rollback failed" in history.error_message


class TestRecordMigration:
    """Test recording migration execution."""

    @pytest.mark.asyncio
    async def test_record_migration(self):
        """Test recording migration in database."""
        runner = MigrationRunner({"type": "postgresql"})

        mock_conn = AsyncMock()
        migration = MockMigration1()

        await runner._record_migration(
            mock_conn, migration, "test_user", 1.5, True, None
        )

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0]

        assert "INSERT INTO kailash_migrations" in call_args[0]
        assert call_args[1] == "001_test_migration_1"  # migration_id
        assert call_args[3] == "test_user"  # applied_by
        assert call_args[4] == 1.5  # execution_time
        assert call_args[5] is True  # success
        assert call_args[6] is None  # error_message

    @pytest.mark.asyncio
    async def test_update_migration_rollback(self):
        """Test updating migration for rollback."""
        runner = MigrationRunner({"type": "postgresql"})

        mock_conn = AsyncMock()

        await runner._update_migration_rollback(
            mock_conn, "001_test_migration_1", "rollback_user"
        )

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0]

        assert "UPDATE kailash_migrations" in call_args[0]
        assert "SET rollback_at = $1, rollback_by = $2" in call_args[0]
        assert call_args[2] == "rollback_user"
        assert call_args[3] == "001_test_migration_1"
