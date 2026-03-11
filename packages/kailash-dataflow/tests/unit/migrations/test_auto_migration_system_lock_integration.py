"""
Tier 1 Unit Tests: AutoMigrationSystem Integration with MigrationLockManager

Tests the integration of MigrationLockManager into AutoMigrationSystem
for concurrent migration safety. Fast execution (<1 second per test).
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from dataflow.core.config import DatabaseConfig, DataFlowConfig
from dataflow.migrations.auto_migration_system import AutoMigrationSystem
from dataflow.migrations.concurrent_access_manager import MigrationLockManager
from dataflow.utils.connection_adapter import ConnectionManagerAdapter


class TestAutoMigrationSystemLockIntegration:
    """Test AutoMigrationSystem integration with MigrationLockManager."""

    def test_auto_migration_system_accepts_dataflow_instance(self):
        """Test that AutoMigrationSystem can accept a DataFlow instance for lock integration."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        mock_dataflow.config.environment = "test"

        # AutoMigrationSystem should accept dataflow_instance parameter
        migration_system = AutoMigrationSystem(
            connection_string="sqlite:///:memory:",
            dataflow_instance=mock_dataflow,
        )

        # Should have migration lock manager initialized
        assert hasattr(migration_system, "_migration_lock_manager")
        assert isinstance(
            migration_system._migration_lock_manager, MigrationLockManager
        )
        assert hasattr(migration_system, "_connection_adapter")
        assert isinstance(
            migration_system._connection_adapter, ConnectionManagerAdapter
        )

    @pytest.mark.asyncio
    async def test_lock_integration_in_auto_migrate(self):
        """Test that auto_migrate uses MigrationLockManager instead of advisory locks."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        mock_dataflow.config.environment = "test"

        migration_system = AutoMigrationSystem(
            connection_string="sqlite:///:memory:",
            dataflow_instance=mock_dataflow,
        )

        # Mock the lock manager methods
        migration_system._migration_lock_manager.acquire_migration_lock = AsyncMock(
            return_value=True
        )
        migration_system._migration_lock_manager.release_migration_lock = AsyncMock()

        # Mock other methods to prevent actual migration execution
        migration_system._ensure_migration_table = AsyncMock()
        migration_system._load_migration_history = AsyncMock()
        migration_system.inspector = Mock()
        migration_system.inspector.get_current_schema = AsyncMock(return_value={})
        migration_system.comparator = Mock()
        migration_system.comparator.compare_schemas = Mock()
        migration_system.comparator.compare_schemas.return_value.has_changes.return_value = (
            False
        )

        # Test auto_migrate
        target_schema = {}
        success, migrations = await migration_system.auto_migrate(
            target_schema, dry_run=True, auto_confirm=True
        )

        # Should have tried to acquire lock
        migration_system._migration_lock_manager.acquire_migration_lock.assert_called_once()

        # Should have released lock
        migration_system._migration_lock_manager.release_migration_lock.assert_called_once()

    @pytest.mark.asyncio
    async def test_lock_acquisition_failure_raises_error(self):
        """Test that auto_migrate raises error when lock acquisition fails."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        mock_dataflow.config.environment = "test"

        migration_system = AutoMigrationSystem(
            connection_string="sqlite:///:memory:",
            dataflow_instance=mock_dataflow,
        )

        # Mock lock manager to fail acquisition
        migration_system._migration_lock_manager.acquire_migration_lock = AsyncMock(
            return_value=False
        )

        # Test auto_migrate should raise RuntimeError
        target_schema = {}
        with pytest.raises(RuntimeError, match="Cannot proceed without migration lock"):
            await migration_system.auto_migrate(target_schema, dry_run=True)

    @pytest.mark.asyncio
    async def test_lock_is_released_on_exception(self):
        """Test that migration lock is released even if auto_migrate fails."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        mock_dataflow.config.environment = "test"

        migration_system = AutoMigrationSystem(
            connection_string="sqlite:///:memory:",
            dataflow_instance=mock_dataflow,
        )

        # Mock lock manager
        migration_system._migration_lock_manager.acquire_migration_lock = AsyncMock(
            return_value=True
        )
        migration_system._migration_lock_manager.release_migration_lock = AsyncMock()

        # Mock migration process to fail
        migration_system._ensure_migration_table = AsyncMock(
            side_effect=Exception("Test error")
        )

        # Test auto_migrate should still release lock on exception (returns False, doesn't raise)
        target_schema = {}
        success, migrations = await migration_system.auto_migrate(
            target_schema, dry_run=True
        )

        # Should return failure instead of raising
        assert not success
        assert migrations == []

        # Should have acquired lock
        migration_system._migration_lock_manager.acquire_migration_lock.assert_called_once()

        # Should have released lock even on exception
        migration_system._migration_lock_manager.release_migration_lock.assert_called_once()

    @pytest.mark.asyncio
    async def test_schema_name_generation_for_lock(self):
        """Test that schema name for locking is generated correctly."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        mock_dataflow.config.environment = "test"

        migration_system = AutoMigrationSystem(
            connection_string="sqlite:///:memory:",
            dataflow_instance=mock_dataflow,
        )

        # Mock lock manager
        migration_system._migration_lock_manager.acquire_migration_lock = AsyncMock(
            return_value=True
        )
        migration_system._migration_lock_manager.release_migration_lock = AsyncMock()

        # Mock other methods
        migration_system._ensure_migration_table = AsyncMock()
        migration_system._load_migration_history = AsyncMock()
        migration_system.inspector = Mock()
        migration_system.inspector.get_current_schema = AsyncMock(return_value={})
        migration_system.comparator = Mock()
        migration_system.comparator.compare_schemas = Mock()
        migration_system.comparator.compare_schemas.return_value.has_changes.return_value = (
            False
        )

        target_schema = {}
        await migration_system.auto_migrate(
            target_schema, dry_run=True, auto_confirm=True
        )

        # Should have called with database name extracted from connection string
        migration_system._migration_lock_manager.acquire_migration_lock.assert_called_once_with(
            ":memory:"
        )
        migration_system._migration_lock_manager.release_migration_lock.assert_called_once_with(
            ":memory:"
        )

    def test_fallback_to_advisory_locks_when_no_dataflow_instance(self):
        """Test fallback to advisory locks when no DataFlow instance is provided."""
        migration_system = AutoMigrationSystem(
            connection_string="sqlite:///:memory:"
            # No dataflow_instance parameter
        )

        # Should not have migration lock manager (falls back to advisory locks)
        assert (
            not hasattr(migration_system, "_migration_lock_manager")
            or migration_system._migration_lock_manager is None
        )

        # Should use the original advisory lock methods
        assert hasattr(migration_system, "_acquire_postgresql_migration_lock")
        assert hasattr(migration_system, "_release_postgresql_migration_lock")


class TestConnectionAdapterInjection:
    """Test connection adapter injection patterns."""

    def test_connection_adapter_initialization(self):
        """Test ConnectionManagerAdapter is initialized correctly."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        mock_dataflow.config.database.url = "sqlite:///:memory:"
        mock_dataflow.config.environment = "test"

        migration_system = AutoMigrationSystem(
            connection_string="sqlite:///:memory:",
            dataflow_instance=mock_dataflow,
        )

        # Connection adapter should be initialized with the DataFlow instance
        assert migration_system._connection_adapter.dataflow == mock_dataflow
        # Parameter style is auto-detected from database type (sqlite in this case)
        assert migration_system._connection_adapter._parameter_style == "sqlite"

    def test_sqlite_connection_adapter(self):
        """Test ConnectionManagerAdapter works with SQLite."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///test.db"
        )
        mock_dataflow.config.database.url = "sqlite:///test.db"
        mock_dataflow.config.environment = "test"

        migration_system = AutoMigrationSystem(
            connection_string="sqlite:///test.db", dataflow_instance=mock_dataflow
        )

        # Should detect SQLite and create appropriate adapter
        assert migration_system._connection_adapter.dataflow == mock_dataflow
        assert migration_system._connection_adapter._database_type == "sqlite"
        # Parameter style is auto-detected from database type
        assert migration_system._connection_adapter._parameter_style == "sqlite"

    def test_lock_timeout_configuration(self):
        """Test that lock timeout can be configured."""
        mock_dataflow = Mock()
        mock_dataflow.config.database.get_connection_url.return_value = (
            "sqlite:///:memory:"
        )
        mock_dataflow.config.environment = "test"

        migration_system = AutoMigrationSystem(
            connection_string="sqlite:///:memory:",
            dataflow_instance=mock_dataflow,
            lock_timeout=60,  # Custom timeout
        )

        # Lock manager should have custom timeout
        assert migration_system._migration_lock_manager.lock_timeout == 60


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=1"])
