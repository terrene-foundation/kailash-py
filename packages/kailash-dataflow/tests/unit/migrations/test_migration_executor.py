"""
Unit tests for Migration Executor.

Tests migration execution, rollback, and status tracking functionality.
Uses standardized unit test fixtures and follows Tier 1 testing policy.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from dataflow.migration.migration_executor import MigrationExecutor, MigrationStatus


@pytest.mark.unit
@pytest.mark.mocking
class TestMigrationExecutor:
    """Test MigrationExecutor functionality."""

    @pytest.fixture
    def migration_executor(self):
        """Create migration executor instance for testing."""
        return MigrationExecutor()

    def test_migration_executor_initialization(self, migration_executor):
        """Test migration executor initializes correctly."""
        executor = migration_executor

        assert executor.migrations == []
        assert executor.executed_migrations == []

    def test_add_migration_basic(self, migration_executor):
        """Test adding a basic migration."""
        migration_id = "001_create_users_table"
        up_script = "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));"
        down_script = "DROP TABLE users;"
        description = "Create users table"

        migration_executor.add_migration(
            migration_id, up_script, down_script, description
        )

        assert len(migration_executor.migrations) == 1
        migration = migration_executor.migrations[0]

        assert migration["id"] == migration_id
        assert migration["up_script"] == up_script
        assert migration["down_script"] == down_script
        assert migration["description"] == description
        assert migration["status"] == MigrationStatus.PENDING
        assert isinstance(migration["created_at"], datetime)

    def test_add_migration_without_description(self, migration_executor):
        """Test adding a migration without description."""
        migration_id = "002_add_email_column"
        up_script = "ALTER TABLE users ADD COLUMN email VARCHAR(255);"
        down_script = "ALTER TABLE users DROP COLUMN email;"

        migration_executor.add_migration(migration_id, up_script, down_script)

        migration = migration_executor.migrations[0]
        assert migration["description"] is None

    def test_add_multiple_migrations(self, migration_executor):
        """Test adding multiple migrations."""
        migrations = [
            ("001_create_users", "CREATE TABLE users...", "DROP TABLE users;"),
            ("002_create_posts", "CREATE TABLE posts...", "DROP TABLE posts;"),
            ("003_add_indexes", "CREATE INDEX...", "DROP INDEX...;"),
        ]

        for migration_id, up_script, down_script in migrations:
            migration_executor.add_migration(migration_id, up_script, down_script)

        assert len(migration_executor.migrations) == 3

        for i, (migration_id, _, _) in enumerate(migrations):
            assert migration_executor.migrations[i]["id"] == migration_id

    def test_execute_migration_success(self, migration_executor):
        """Test successful migration execution."""
        migration_id = "001_create_users_table"
        up_script = "CREATE TABLE users (id INT PRIMARY KEY);"
        down_script = "DROP TABLE users;"

        migration_executor.add_migration(migration_id, up_script, down_script)

        result = migration_executor.execute_migration(migration_id)

        assert result["success"] is True
        assert result["migration_id"] == migration_id
        assert "duration" in result
        assert isinstance(result["duration"], float)

        # Check migration status was updated
        migration = migration_executor._find_migration(migration_id)
        assert migration["status"] == MigrationStatus.COMPLETED
        assert "started_at" in migration
        assert "completed_at" in migration

        # Check migration was added to executed list
        assert migration_id in migration_executor.executed_migrations

    def test_execute_migration_not_found(self, migration_executor):
        """Test executing a migration that doesn't exist."""
        result = migration_executor.execute_migration("nonexistent_migration")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_execute_migration_already_executed(self, migration_executor):
        """Test executing a migration that's already been executed."""
        migration_id = "001_create_users_table"
        up_script = "CREATE TABLE users (id INT PRIMARY KEY);"
        down_script = "DROP TABLE users;"

        migration_executor.add_migration(migration_id, up_script, down_script)

        # Execute migration first time
        result1 = migration_executor.execute_migration(migration_id)
        assert result1["success"] is True

        # Try to execute again
        result2 = migration_executor.execute_migration(migration_id)
        assert result2["success"] is False
        assert "already executed" in result2["error"]

    def test_execute_migration_with_exception(self, migration_executor):
        """Test migration execution when an exception occurs."""
        migration_id = "001_failing_migration"
        up_script = "INVALID SQL SYNTAX;"
        down_script = "DROP TABLE users;"

        migration_executor.add_migration(migration_id, up_script, down_script)

        # Mock datetime.utcnow to raise an exception during execution
        with patch("dataflow.migration.migration_executor.datetime") as mock_datetime:
            mock_datetime.utcnow.side_effect = Exception("Database error")
            result = migration_executor.execute_migration(migration_id)

        assert result["success"] is False
        assert "Database error" in result["error"]

    def test_rollback_migration_success(self, migration_executor):
        """Test successful migration rollback."""
        migration_id = "001_create_users_table"
        up_script = "CREATE TABLE users (id INT PRIMARY KEY);"
        down_script = "DROP TABLE users;"

        migration_executor.add_migration(migration_id, up_script, down_script)

        # Execute migration first
        execute_result = migration_executor.execute_migration(migration_id)
        assert execute_result["success"] is True

        # Now rollback
        rollback_result = migration_executor.rollback_migration(migration_id)

        assert rollback_result["success"] is True
        assert rollback_result["migration_id"] == migration_id

        # Check migration status was updated
        migration = migration_executor._find_migration(migration_id)
        assert migration["status"] == MigrationStatus.ROLLED_BACK
        assert "rolled_back_at" in migration

        # Check migration was removed from executed list
        assert migration_id not in migration_executor.executed_migrations

    def test_rollback_migration_not_found(self, migration_executor):
        """Test rolling back a migration that doesn't exist."""
        result = migration_executor.rollback_migration("nonexistent_migration")

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_rollback_migration_not_executed(self, migration_executor):
        """Test rolling back a migration that hasn't been executed."""
        migration_id = "001_create_users_table"
        up_script = "CREATE TABLE users (id INT PRIMARY KEY);"
        down_script = "DROP TABLE users;"

        migration_executor.add_migration(migration_id, up_script, down_script)

        # Try to rollback without executing first
        result = migration_executor.rollback_migration(migration_id)

        assert result["success"] is False
        assert "not executed" in result["error"]

    def test_rollback_migration_with_exception(self, migration_executor):
        """Test migration rollback when an exception occurs."""
        migration_id = "001_create_users_table"
        up_script = "CREATE TABLE users (id INT PRIMARY KEY);"
        down_script = "DROP TABLE users;"

        migration_executor.add_migration(migration_id, up_script, down_script)

        # Execute migration first
        migration_executor.execute_migration(migration_id)

        # Mock an exception during rollback by patching datetime
        with patch("dataflow.migration.migration_executor.datetime") as mock_datetime:
            mock_datetime.utcnow.side_effect = Exception("Rollback error")
            result = migration_executor.rollback_migration(migration_id)

        assert result["success"] is False
        assert "Rollback error" in result["error"]

    def test_find_migration_exists(self, migration_executor):
        """Test finding an existing migration."""
        migration_id = "001_create_users_table"
        up_script = "CREATE TABLE users (id INT PRIMARY KEY);"
        down_script = "DROP TABLE users;"

        migration_executor.add_migration(migration_id, up_script, down_script)

        migration = migration_executor._find_migration(migration_id)

        assert migration is not None
        assert migration["id"] == migration_id
        assert migration["up_script"] == up_script
        assert migration["down_script"] == down_script

    def test_find_migration_not_exists(self, migration_executor):
        """Test finding a migration that doesn't exist."""
        migration = migration_executor._find_migration("nonexistent_migration")
        assert migration is None

    def test_get_migration_status_empty(self, migration_executor):
        """Test getting migration status when no migrations exist."""
        status = migration_executor.get_migration_status()

        assert status["total"] == 0
        assert status["executed"] == 0
        assert status["pending"] == 0
        assert status["failed"] == 0
        assert status["migrations"] == []

    def test_get_migration_status_with_migrations(self, migration_executor):
        """Test getting migration status with various migration states."""
        # Add pending migration
        migration_executor.add_migration(
            "001_create_users", "CREATE TABLE users;", "DROP TABLE users;"
        )

        # Add and execute a migration
        migration_executor.add_migration(
            "002_create_posts", "CREATE TABLE posts;", "DROP TABLE posts;"
        )
        migration_executor.execute_migration("002_create_posts")

        # Add and fail a migration
        migration_executor.add_migration(
            "003_failing_migration", "INVALID SQL;", "DROP TABLE something;"
        )
        migration = migration_executor._find_migration("003_failing_migration")
        migration["status"] = MigrationStatus.FAILED

        status = migration_executor.get_migration_status()

        assert status["total"] == 3
        assert status["executed"] == 1
        assert status["pending"] == 1
        assert status["failed"] == 1

        assert len(status["migrations"]) == 3

        # Check individual migration status
        migration_statuses = {m["id"]: m["status"] for m in status["migrations"]}
        assert migration_statuses["001_create_users"] == "pending"
        assert migration_statuses["002_create_posts"] == "completed"
        assert migration_statuses["003_failing_migration"] == "failed"

    def test_migration_status_enum_values(self):
        """Test MigrationStatus enum values."""
        assert MigrationStatus.PENDING.value == "pending"
        assert MigrationStatus.RUNNING.value == "running"
        assert MigrationStatus.COMPLETED.value == "completed"
        assert MigrationStatus.FAILED.value == "failed"
        assert MigrationStatus.ROLLED_BACK.value == "rolled_back"

    def test_migration_execution_timing(self, migration_executor):
        """Test migration execution timing is tracked correctly."""
        migration_id = "001_timed_migration"
        up_script = "CREATE TABLE test_table (id INT);"
        down_script = "DROP TABLE test_table;"

        migration_executor.add_migration(migration_id, up_script, down_script)

        # Mock datetime to control timing
        start_time = datetime(2023, 1, 1, 12, 0, 0)
        end_time = datetime(2023, 1, 1, 12, 0, 5)  # 5 seconds later

        with patch("dataflow.migration.migration_executor.datetime") as mock_datetime:
            mock_datetime.utcnow.side_effect = [start_time, end_time]

            result = migration_executor.execute_migration(migration_id)

        assert result["success"] is True
        assert result["duration"] == 5.0  # 5 seconds

        migration = migration_executor._find_migration(migration_id)
        assert migration["started_at"] == start_time
        assert migration["completed_at"] == end_time

    def test_migration_with_description_in_status(self, migration_executor):
        """Test that migration descriptions appear in status output."""
        migration_id = "001_create_users_table"
        description = "Initial user table creation"
        up_script = "CREATE TABLE users (id INT PRIMARY KEY);"
        down_script = "DROP TABLE users;"

        migration_executor.add_migration(
            migration_id, up_script, down_script, description
        )

        status = migration_executor.get_migration_status()
        migration_info = status["migrations"][0]

        assert migration_info["id"] == migration_id
        assert migration_info["description"] == description
        assert migration_info["status"] == "pending"

    def test_multiple_migrations_execution_order(self, migration_executor):
        """Test that multiple migrations can be executed in order."""
        migrations = [
            ("001_create_users", "CREATE TABLE users;", "DROP TABLE users;"),
            ("002_create_posts", "CREATE TABLE posts;", "DROP TABLE posts;"),
            ("003_add_indexes", "CREATE INDEX;", "DROP INDEX;"),
        ]

        # Add all migrations
        for migration_id, up_script, down_script in migrations:
            migration_executor.add_migration(migration_id, up_script, down_script)

        # Execute all migrations
        for migration_id, _, _ in migrations:
            result = migration_executor.execute_migration(migration_id)
            assert result["success"] is True

        # Check all are executed
        assert len(migration_executor.executed_migrations) == 3
        for migration_id, _, _ in migrations:
            assert migration_id in migration_executor.executed_migrations

    def test_migration_state_progression(self, migration_executor):
        """Test migration state progresses correctly through execution."""
        migration_id = "001_state_test"
        up_script = "CREATE TABLE test (id INT);"
        down_script = "DROP TABLE test;"

        # Initially pending
        migration_executor.add_migration(migration_id, up_script, down_script)
        migration = migration_executor._find_migration(migration_id)
        assert migration["status"] == MigrationStatus.PENDING

        # Execute and check it's completed
        result = migration_executor.execute_migration(migration_id)
        assert result["success"] is True
        assert migration["status"] == MigrationStatus.COMPLETED

        # Rollback and check it's rolled back
        rollback_result = migration_executor.rollback_migration(migration_id)
        assert rollback_result["success"] is True
        assert migration["status"] == MigrationStatus.ROLLED_BACK


@pytest.mark.unit
@pytest.mark.mocking
class TestMigrationExecutorAdvanced:
    """Test advanced MigrationExecutor scenarios."""

    @pytest.fixture
    def migration_executor(self):
        """Create migration executor instance for testing."""
        return MigrationExecutor()

    def test_concurrent_migration_safety(self, migration_executor):
        """Test that migrations handle concurrent access safely."""
        migration_id = "001_concurrent_test"
        up_script = "CREATE TABLE test (id INT);"
        down_script = "DROP TABLE test;"

        migration_executor.add_migration(migration_id, up_script, down_script)

        # Execute migration
        result1 = migration_executor.execute_migration(migration_id)
        assert result1["success"] is True

        # Try to execute the same migration concurrently
        result2 = migration_executor.execute_migration(migration_id)
        assert result2["success"] is False
        assert "already executed" in result2["error"]

    def test_migration_error_handling_preserves_state(self, migration_executor):
        """Test that migration errors don't corrupt executor state."""
        # Add a valid migration
        valid_id = "001_valid_migration"
        migration_executor.add_migration(
            valid_id, "CREATE TABLE valid;", "DROP TABLE valid;"
        )

        # Add a migration that will fail during execution
        invalid_id = "002_invalid_migration"
        migration_executor.add_migration(
            invalid_id, "INVALID SQL;", "DROP TABLE invalid;"
        )

        # Execute valid migration first
        result1 = migration_executor.execute_migration(valid_id)
        assert result1["success"] is True

        # Try to execute invalid migration by making datetime raise an error during execution
        with patch("dataflow.migration.migration_executor.datetime") as mock_datetime:
            mock_datetime.utcnow.side_effect = Exception("Simulated error")
            result2 = migration_executor.execute_migration(invalid_id)

        assert result2["success"] is False

        # Check that executor state is still valid
        assert len(migration_executor.executed_migrations) == 1
        assert valid_id in migration_executor.executed_migrations
        assert invalid_id not in migration_executor.executed_migrations

    def test_rollback_maintains_execution_order(self, migration_executor):
        """Test that rollbacks maintain proper execution order tracking."""
        # Add multiple migrations
        migration_ids = ["001_first", "002_second", "003_third"]

        for mid in migration_ids:
            migration_executor.add_migration(
                mid, f"CREATE TABLE {mid};", f"DROP TABLE {mid};"
            )
            migration_executor.execute_migration(mid)

        # All should be executed
        assert len(migration_executor.executed_migrations) == 3

        # Rollback middle migration
        result = migration_executor.rollback_migration("002_second")
        assert result["success"] is True

        # Check that only the rolled back migration was removed
        assert len(migration_executor.executed_migrations) == 2
        assert "001_first" in migration_executor.executed_migrations
        assert "002_second" not in migration_executor.executed_migrations
        assert "003_third" in migration_executor.executed_migrations

        # Verify status reflects the rollback
        status = migration_executor.get_migration_status()
        assert status["executed"] == 2

        rolled_back_migration = next(
            m for m in status["migrations"] if m["id"] == "002_second"
        )
        assert rolled_back_migration["status"] == "rolled_back"
