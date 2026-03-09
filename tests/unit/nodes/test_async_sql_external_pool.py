"""Unit tests for AsyncSQLDatabaseNode external pool injection.

Tests verify that users can inject their own connection pool (e.g., asyncpg.Pool)
and the SDK borrows it without creating internal pools or closing it on cleanup.

Reference:
- Analysis: workspaces/async-sql-connection-leak/01-analysis/
- Plan: workspaces/async-sql-connection-leak/02-plans/01-implementation-plan.md
"""

import gc
import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


def _mock_pool(db_type="postgresql"):
    """Create a MagicMock that passes pool type validation for the given db_type.

    When the async driver is installed, uses spec= so isinstance() passes.
    When not installed, falls back to plain MagicMock (validation is skipped).
    """
    if db_type == "postgresql":
        try:
            import asyncpg

            pool = MagicMock(spec=asyncpg.Pool)
        except ImportError:
            pool = MagicMock()
    elif db_type == "mysql":
        try:
            import aiomysql

            pool = MagicMock(spec=aiomysql.Pool)
        except ImportError:
            pool = MagicMock()
    elif db_type == "sqlite":
        try:
            import aiosqlite

            pool = MagicMock(spec=aiosqlite.Connection)
        except ImportError:
            pool = MagicMock()
    else:
        pool = MagicMock()
    # Ensure close is an AsyncMock for assertion checks
    pool.close = AsyncMock()
    return pool


class TestExternalPoolParameter:
    """Test external_pool parameter handling in __init__."""

    def test_external_pool_sets_share_pool_false(self):
        """When external_pool is provided, share_pool must be forced to False."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
            share_pool=True,  # Explicitly set True — should be overridden
        )
        assert node._share_pool is False
        assert node._external_pool is mock_pool

    def test_external_pool_popped_from_config(self):
        """external_pool must be popped from config (not passed to parent)."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        # external_pool should not appear in the node's config dict
        assert "external_pool" not in node.config

    def test_no_external_pool_default_behavior(self):
        """Without external_pool, share_pool defaults to True (existing behavior)."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            connection_string="postgresql://localhost/test",
        )
        assert node._share_pool is True
        assert node._external_pool is None

    def test_explicit_none_external_pool_treated_as_no_pool(self):
        """Explicitly passing external_pool=None must behave like no external pool."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            connection_string="postgresql://localhost/test",
            external_pool=None,
        )
        assert node._external_pool is None
        assert node._share_pool is True


class TestValidateConfig:
    """Test _validate_config bypass for external pools."""

    def test_external_pool_skips_connection_validation(self):
        """With external_pool, node must NOT require connection_string/host/database."""
        mock_pool = _mock_pool()
        # This should NOT raise even though no connection info is given
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        assert node._external_pool is mock_pool

    def test_no_external_pool_requires_connection_params(self):
        """Without external_pool, missing connection params must raise."""
        # NodeConfigurationError wraps NodeValidationError during __init__
        with pytest.raises(Exception, match="requires host and database"):
            AsyncSQLDatabaseNode(
                name="test_node",
                database_type="postgresql",
                query="SELECT 1",
                # No connection_string, host, or database
            )

    def test_unsupported_database_type_still_validated_with_external_pool(self):
        """database_type validation must still run even with external_pool."""
        mock_pool = MagicMock()
        with pytest.raises(Exception, match="Must be one of"):
            AsyncSQLDatabaseNode(
                name="test_node",
                database_type="mssql",
                query="SELECT 1",
                external_pool=mock_pool,
            )


class TestReinitializeFromConfig:
    """Test _reinitialize_from_config guard for external pools."""

    def test_reinitialize_preserves_share_pool_false(self):
        """_reinitialize_from_config must keep share_pool=False for external pools."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        assert node._share_pool is False

        # Simulate config reload that sets share_pool=True
        node.config["share_pool"] = True
        node._reinitialize_from_config()

        # Guard must have forced it back to False
        assert node._share_pool is False


class TestWrapExternalPool:
    """Test _wrap_external_pool() method."""

    def test_wrap_creates_adapter_with_injected_pool(self):
        """Wrapped adapter must use the external pool as its _pool."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        adapter = node._wrap_external_pool(mock_pool)
        assert adapter._pool is mock_pool
        assert adapter._connected is True

    @pytest.mark.asyncio
    async def test_wrapped_adapter_disconnect_is_noop(self):
        """disconnect() on wrapped adapter must NOT close the external pool."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        adapter = node._wrap_external_pool(mock_pool)

        # Call disconnect — should be no-op
        await adapter.disconnect()

        # Pool's close must NOT have been called
        mock_pool.close.assert_not_called()
        # Adapter marked as disconnected
        assert adapter._connected is False

    def test_wrap_postgresql_uses_postgresql_adapter(self):
        """PostgreSQL type should create a PostgreSQLAdapter."""
        from kailash.nodes.data.async_sql import PostgreSQLAdapter

        mock_pool = _mock_pool("postgresql")
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        adapter = node._wrap_external_pool(mock_pool)
        assert isinstance(adapter, PostgreSQLAdapter)

    def test_wrap_sqlite_uses_sqlite_adapter(self):
        """SQLite type should create a SQLiteAdapter."""
        from kailash.nodes.data.async_sql import SQLiteAdapter

        mock_pool = _mock_pool("sqlite")
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="sqlite",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        adapter = node._wrap_external_pool(mock_pool)
        assert isinstance(adapter, SQLiteAdapter)

    def test_wrap_mysql_uses_mysql_adapter(self):
        """MySQL type should create a MySQLAdapter."""
        from kailash.nodes.data.async_sql import MySQLAdapter

        mock_pool = _mock_pool("mysql")
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="mysql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        adapter = node._wrap_external_pool(mock_pool)
        assert isinstance(adapter, MySQLAdapter)

    def test_wrap_uses_placeholder_for_postgresql_without_connection_info(self):
        """When no connection info given, PostgreSQL gets placeholder connection string."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        adapter = node._wrap_external_pool(mock_pool)
        assert adapter.config.connection_string == "external-pool://injected"

    def test_wrap_uses_memory_placeholder_for_sqlite_without_connection_info(self):
        """When no connection info given, SQLite gets :memory: placeholder."""
        mock_pool = _mock_pool("sqlite")
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="sqlite",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        adapter = node._wrap_external_pool(mock_pool)
        assert adapter.config.database == ":memory:"

    def test_wrap_uses_explicit_connection_string_when_provided(self):
        """When connection_string is provided, it passes through to adapter config."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
            connection_string="postgresql://real-host/real-db",
        )
        adapter = node._wrap_external_pool(mock_pool)
        assert adapter.config.connection_string == "postgresql://real-host/real-db"

    @pytest.mark.asyncio
    async def test_noop_disconnect_after_adapter_gc(self):
        """_noop_disconnect must handle the adapter being GC'd gracefully."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        adapter = node._wrap_external_pool(mock_pool)
        disconnect_fn = adapter.disconnect

        # Drop all references to the adapter
        del adapter
        node._adapter = None
        gc.collect()

        # Calling disconnect after adapter is GC'd should not raise
        await disconnect_fn()


class TestPoolTypeValidation:
    """Test _validate_pool_type() for type mismatch detection."""

    def test_mismatched_pool_type_raises_for_postgresql(self):
        """Non-asyncpg pool must be rejected for postgresql type."""
        try:
            import asyncpg  # noqa: F401

            # Create a non-asyncpg pool object (spec=[] ensures no isinstance match)
            fake_pool = MagicMock(spec=[])
            with pytest.raises(NodeValidationError, match="expected asyncpg.Pool"):
                node = AsyncSQLDatabaseNode(
                    name="test_node",
                    database_type="postgresql",
                    query="SELECT 1",
                    external_pool=fake_pool,
                )
                # Validation fires in _wrap_external_pool, called by _get_adapter
                node._wrap_external_pool(fake_pool)
        except ImportError:
            pytest.skip("asyncpg not installed — type validation skipped")

    def test_mismatched_pool_type_raises_for_mysql(self):
        """Non-aiomysql pool must be rejected for mysql type."""
        try:
            import aiomysql  # noqa: F401

            fake_pool = MagicMock(spec=[])
            node = AsyncSQLDatabaseNode(
                name="test_node",
                database_type="mysql",
                query="SELECT 1",
                external_pool=fake_pool,
            )
            with pytest.raises(NodeValidationError, match="expected aiomysql.Pool"):
                node._wrap_external_pool(fake_pool)
        except ImportError:
            pytest.skip("aiomysql not installed — type validation skipped")

    def test_mismatched_pool_type_raises_for_sqlite(self):
        """Non-aiosqlite pool must be rejected for sqlite type."""
        try:
            import aiosqlite  # noqa: F401

            fake_pool = MagicMock(spec=[])
            node = AsyncSQLDatabaseNode(
                name="test_node",
                database_type="sqlite",
                query="SELECT 1",
                external_pool=fake_pool,
            )
            with pytest.raises(
                NodeValidationError, match="expected aiosqlite.Connection"
            ):
                node._wrap_external_pool(fake_pool)
        except ImportError:
            pytest.skip("aiosqlite not installed — type validation skipped")

    def test_correct_pool_type_accepted(self):
        """Properly typed pool must pass validation."""
        mock_pool = _mock_pool("postgresql")
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        # Should not raise
        adapter = node._wrap_external_pool(mock_pool)
        assert adapter._pool is mock_pool


class TestGetAdapterWithExternalPool:
    """Test _get_adapter() early-return path for external pools."""

    @pytest.mark.asyncio
    async def test_external_pool_bypasses_shared_pools(self):
        """When external_pool is set, _shared_pools must NOT be modified."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        initial_pools = dict(AsyncSQLDatabaseNode._shared_pools)

        adapter = await node._get_adapter()

        assert adapter._pool is mock_pool
        assert node._connected is True
        assert node._pool_key is None
        # _shared_pools unchanged
        assert AsyncSQLDatabaseNode._shared_pools == initial_pools

    @pytest.mark.asyncio
    async def test_get_adapter_idempotent(self):
        """Calling _get_adapter() multiple times returns the same adapter."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        adapter1 = await node._get_adapter()
        adapter2 = await node._get_adapter()
        assert adapter1 is adapter2

    @pytest.mark.asyncio
    async def test_no_external_pool_preserves_defaults(self):
        """Without external_pool, node preserves default pool sharing behavior."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            connection_string="postgresql://localhost/test",
        )
        # Verify the external pool path is NOT entered
        assert node._external_pool is None
        assert node._share_pool is True


class TestCleanupWithExternalPool:
    """Test cleanup() behavior with injected pools."""

    @pytest.mark.asyncio
    async def test_cleanup_through_full_lifecycle(self):
        """cleanup() after _get_adapter() must not close the external pool."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )

        # Use the real _get_adapter() path
        adapter = await node._get_adapter()
        assert adapter._pool is mock_pool
        assert node._connected is True

        # Now cleanup through the real flow
        await node.cleanup()

        mock_pool.close.assert_not_called()
        assert node._connected is False
        assert node._adapter is None

    @pytest.mark.asyncio
    async def test_cleanup_does_not_close_external_pool(self):
        """cleanup() must NOT close the external pool (manual state setup)."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        # Simulate _get_adapter() having run
        adapter = node._wrap_external_pool(mock_pool)
        node._adapter = adapter
        node._connected = True
        node._share_pool = False
        node._pool_key = None

        await node.cleanup()

        # Pool NOT closed
        mock_pool.close.assert_not_called()
        # Node state cleaned up
        assert node._connected is False
        assert node._adapter is None

    @pytest.mark.asyncio
    async def test_cleanup_idempotent(self):
        """Calling cleanup() twice should not error."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        adapter = node._wrap_external_pool(mock_pool)
        node._adapter = adapter
        node._connected = True
        node._share_pool = False
        node._pool_key = None

        await node.cleanup()
        await node.cleanup()  # Second call should be harmless

        assert node._connected is False
        assert node._adapter is None

    def test_del_no_warning_after_cleanup(self):
        """__del__ should NOT emit ResourceWarning if cleanup() already ran."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        # Simulate post-cleanup state
        node._connected = False
        node._adapter = None

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            node.__del__()
            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 0

    def test_del_warns_when_connected_and_not_cleaned(self):
        """__del__ SHOULD emit ResourceWarning if cleanup() was NOT called."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        # Simulate a connected state that was never cleaned up
        node._connected = True
        node._adapter = MagicMock()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            node.__del__()
            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 1


class TestRetryWithExternalPool:
    """Test retry behavior when external pool is closed/unavailable."""

    @pytest.mark.asyncio
    async def test_closed_pool_raises_immediately_no_retry(self):
        """When external pool is closed, must raise immediately instead of retrying."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )

        # Set up adapter via the real flow
        adapter = node._wrap_external_pool(mock_pool)
        node._adapter = adapter
        node._connected = True
        node._pool_key = None

        # Mock the transaction wrapper to simulate pool-closed error
        node._execute_with_transaction = AsyncMock(
            side_effect=Exception("pool is closed")
        )

        with pytest.raises(NodeExecutionError, match="External connection pool"):
            await node._execute_with_retry(adapter, "SELECT 1", None, "all", None)

    @pytest.mark.asyncio
    async def test_closed_pool_error_includes_original_message(self):
        """The error message must include the original exception details."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )

        adapter = node._wrap_external_pool(mock_pool)
        node._adapter = adapter
        node._connected = True
        node._pool_key = None

        # Mock the transaction wrapper to simulate pool-closed error
        node._execute_with_transaction = AsyncMock(
            side_effect=Exception("connection refused: pool is closed by user")
        )

        with pytest.raises(NodeExecutionError, match="pool is closed by user"):
            await node._execute_with_retry(adapter, "SELECT 1", None, "all", None)

    @pytest.mark.asyncio
    async def test_execute_many_closed_pool_raises_immediately(self):
        """_execute_many_with_retry must also fail-fast for external pool errors."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="INSERT INTO t VALUES ($1)",
            external_pool=mock_pool,
        )

        adapter = node._wrap_external_pool(mock_pool)
        node._adapter = adapter
        node._connected = True
        node._pool_key = None

        # Mock the transaction wrapper to simulate pool-closed error
        node._execute_many_with_transaction = AsyncMock(
            side_effect=Exception("pool is closed")
        )

        with pytest.raises(NodeExecutionError, match="External connection pool"):
            await node._execute_many_with_retry(
                adapter, "INSERT INTO t VALUES ($1)", [(1,), (2,)]
            )

    @pytest.mark.asyncio
    async def test_pool_closed_attribute_triggers_failfast(self):
        """When pool._closed is True, must fail-fast even if error message is unusual."""
        mock_pool = _mock_pool()
        mock_pool._closed = True  # asyncpg sets this when pool is terminated
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )

        adapter = node._wrap_external_pool(mock_pool)
        node._adapter = adapter
        node._connected = True
        node._pool_key = None

        # Error message does NOT contain "pool is closed" or "connection"
        node._execute_with_transaction = AsyncMock(
            side_effect=Exception("pool has been terminated")
        )

        with pytest.raises(NodeExecutionError, match="External connection pool"):
            await node._execute_with_retry(adapter, "SELECT 1", None, "all", None)

    def test_del_does_not_sync_close_external_pool_sqlite(self):
        """__del__ must NOT call raw.close() on external SQLite connections."""
        mock_pool = _mock_pool("sqlite")
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="sqlite",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        # Simulate connected state with an adapter that has a _connection
        mock_adapter = MagicMock()
        mock_raw_conn = MagicMock()
        mock_adapter._connection._conn = mock_raw_conn
        node._connected = True
        node._adapter = mock_adapter

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            node.__del__()

        # raw.close() must NOT be called — caller owns the connection
        mock_raw_conn.close.assert_not_called()


class TestSerialization:
    """Test serialization behavior with external pools."""

    def test_to_dict_raises_for_external_pool_node(self):
        """to_dict() must raise when external_pool is set (pool is not serializable)."""
        mock_pool = _mock_pool()
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )

        with pytest.raises(NodeExecutionError, match="cannot be serialized"):
            node.to_dict()

    def test_to_dict_works_without_external_pool(self):
        """to_dict() must work normally for nodes without external pool."""
        node = AsyncSQLDatabaseNode(
            name="test_node",
            database_type="postgresql",
            query="SELECT 1",
            connection_string="postgresql://localhost/test",
        )

        result = node.to_dict()
        assert "config" in result
        assert result["type"] == "AsyncSQLDatabaseNode"


class TestMixedPoolUsage:
    """Test workflows with both injected and internal pool nodes."""

    @pytest.mark.asyncio
    async def test_injected_and_internal_nodes_independent(self):
        """An injected-pool node and a regular node should operate independently."""
        mock_pool = _mock_pool()
        injected_node = AsyncSQLDatabaseNode(
            name="injected",
            database_type="postgresql",
            query="SELECT 1",
            external_pool=mock_pool,
        )
        internal_node = AsyncSQLDatabaseNode(
            name="internal",
            database_type="postgresql",
            query="SELECT 1",
            connection_string="postgresql://localhost/test",
        )

        assert injected_node._external_pool is mock_pool
        assert injected_node._share_pool is False

        assert internal_node._external_pool is None
        assert internal_node._share_pool is True

        # Get adapter for injected node
        adapter = await injected_node._get_adapter()
        assert adapter._pool is mock_pool
        assert injected_node._pool_key is None

        # Internal node should still use normal pool path
        assert internal_node._pool_key is None  # Not yet initialized
        assert internal_node._share_pool is True
