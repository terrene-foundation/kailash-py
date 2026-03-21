"""
Unit tests for MySQLTransaction __del__ fallback and __aexit__ hardening.

Tests the hardened MySQLTransaction class which adds:
- Class-level defaults for safety if __init__ fails partially
- State tracking (_committed, _rolled_back) to prevent double-commit/rollback
- Exception handling in __aexit__ so cleanup errors don't mask the original exception
- __del__ ResourceWarning when a transaction is GC'd without commit/rollback
- Connection release in a finally block so it always happens

These are Tier 1 (unit) tests -- mocks are allowed for aiomysql connections.
"""

import sys
import warnings
from unittest.mock import AsyncMock, Mock

import pytest
from dataflow.adapters.mysql import MySQLTransaction


class TestMySQLTransactionClassDefaults:
    """Test that MySQLTransaction has class-level safety defaults."""

    def test_class_level_committed_default(self):
        """_committed must default to False at the class level."""
        assert hasattr(MySQLTransaction, "_committed")
        assert MySQLTransaction._committed is False

    def test_class_level_rolled_back_default(self):
        """_rolled_back must default to False at the class level."""
        assert hasattr(MySQLTransaction, "_rolled_back")
        assert MySQLTransaction._rolled_back is False

    def test_class_level_connection_default(self):
        """connection must default to None at the class level."""
        assert hasattr(MySQLTransaction, "connection")
        assert MySQLTransaction.connection is None

    def test_class_level_source_traceback_default(self):
        """_source_traceback must default to None at the class level."""
        assert hasattr(MySQLTransaction, "_source_traceback")
        assert MySQLTransaction._source_traceback is None


class TestMySQLTransactionInit:
    """Test that __init__ properly sets instance-level state."""

    def test_init_sets_committed_false(self):
        """__init__ must set _committed to False on the instance."""
        pool = Mock()
        txn = MySQLTransaction(pool)
        assert txn._committed is False

    def test_init_sets_rolled_back_false(self):
        """__init__ must set _rolled_back to False on the instance."""
        pool = Mock()
        txn = MySQLTransaction(pool)
        assert txn._rolled_back is False

    def test_init_stores_pool_reference(self):
        """__init__ must store the pool reference; connection is None until __aenter__."""
        pool = Mock()
        txn = MySQLTransaction(pool)
        assert txn.connection_pool is pool
        assert txn.connection is None

    def test_init_captures_source_traceback_in_debug_mode(self):
        """In debug mode (__debug__ is True), __init__ must capture source traceback."""
        # __debug__ is True by default in CPython (unless -O flag is used)
        if not __debug__:
            pytest.skip("Test requires __debug__ == True (no -O flag)")

        pool = Mock()
        txn = MySQLTransaction(pool)
        assert txn._source_traceback is not None
        assert len(txn._source_traceback) > 0


class TestMySQLTransactionAexit:
    """Test hardened __aexit__ behavior."""

    @pytest.mark.asyncio
    async def test_aexit_commits_on_success(self):
        """__aexit__ must commit when no exception occurred."""
        mock_connection = AsyncMock()
        mock_pool = Mock()
        mock_pool.release = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection

        await txn.__aexit__(None, None, None)

        mock_connection.commit.assert_called_once()
        mock_connection.rollback.assert_not_called()
        assert txn._committed is True

    @pytest.mark.asyncio
    async def test_aexit_rolls_back_on_exception(self):
        """__aexit__ must rollback when an exception occurred."""
        mock_connection = AsyncMock()
        mock_pool = Mock()
        mock_pool.release = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection

        await txn.__aexit__(ValueError, ValueError("test"), None)

        mock_connection.rollback.assert_called_once()
        mock_connection.commit.assert_not_called()
        assert txn._rolled_back is True

    @pytest.mark.asyncio
    async def test_aexit_releases_connection_on_success(self):
        """__aexit__ must release the connection back to pool on success."""
        mock_connection = AsyncMock()
        mock_pool = Mock()
        mock_pool.release = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection

        await txn.__aexit__(None, None, None)

        mock_pool.release.assert_called_once_with(mock_connection)

    @pytest.mark.asyncio
    async def test_aexit_releases_connection_on_exception(self):
        """__aexit__ must release the connection back to pool on exception."""
        mock_connection = AsyncMock()
        mock_pool = Mock()
        mock_pool.release = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection

        await txn.__aexit__(RuntimeError, RuntimeError("fail"), None)

        mock_pool.release.assert_called_once_with(mock_connection)

    @pytest.mark.asyncio
    async def test_aexit_releases_connection_even_when_commit_fails(self):
        """Connection must be released even when commit() raises."""
        mock_connection = AsyncMock()
        mock_connection.commit.side_effect = Exception("commit failed")
        mock_pool = Mock()
        mock_pool.release = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection

        # Should NOT raise -- the error is logged but connection is still released
        await txn.__aexit__(None, None, None)

        mock_pool.release.assert_called_once_with(mock_connection)

    @pytest.mark.asyncio
    async def test_aexit_releases_connection_even_when_rollback_fails(self):
        """Connection must be released even when rollback() raises."""
        mock_connection = AsyncMock()
        mock_connection.rollback.side_effect = Exception("rollback failed")
        mock_pool = Mock()
        mock_pool.release = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection

        # Should NOT raise -- the error is logged but connection is still released
        await txn.__aexit__(ValueError, ValueError("original"), None)

        mock_pool.release.assert_called_once_with(mock_connection)

    @pytest.mark.asyncio
    async def test_aexit_skips_commit_if_already_committed(self):
        """__aexit__ must not commit again if _committed is already True."""
        mock_connection = AsyncMock()
        mock_pool = Mock()
        mock_pool.release = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection
        txn._committed = True

        await txn.__aexit__(None, None, None)

        mock_connection.commit.assert_not_called()
        mock_connection.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_aexit_skips_rollback_if_already_rolled_back(self):
        """__aexit__ must not rollback again if _rolled_back is already True."""
        mock_connection = AsyncMock()
        mock_pool = Mock()
        mock_pool.release = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection
        txn._rolled_back = True

        await txn.__aexit__(RuntimeError, RuntimeError("fail"), None)

        mock_connection.rollback.assert_not_called()
        mock_connection.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_aexit_skips_rollback_if_already_committed(self):
        """__aexit__ must not rollback if _committed is True (even on exception)."""
        mock_connection = AsyncMock()
        mock_pool = Mock()
        mock_pool.release = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection
        txn._committed = True

        await txn.__aexit__(RuntimeError, RuntimeError("fail"), None)

        mock_connection.rollback.assert_not_called()
        mock_connection.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_aexit_skips_release_if_connection_is_none(self):
        """__aexit__ must not call release if connection is None."""
        mock_pool = Mock()
        mock_pool.release = Mock()

        txn = MySQLTransaction(mock_pool)
        # connection stays None (never entered)

        await txn.__aexit__(None, None, None)

        mock_pool.release.assert_not_called()


class TestMySQLTransactionDel:
    """Test __del__ ResourceWarning for leaked transactions."""

    def test_del_warns_on_uncommitted_transaction(self):
        """__del__ must emit ResourceWarning if not committed or rolled back."""
        mock_pool = Mock()
        mock_connection = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection
        # Simulate: transaction was entered but never exited

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()

            assert len(w) == 1
            assert issubclass(w[0].category, ResourceWarning)
            assert "MySQLTransaction GC'd without commit/rollback" in str(w[0].message)

    def test_del_silent_if_committed(self):
        """__del__ must not warn if transaction was committed."""
        mock_pool = Mock()
        mock_connection = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection
        txn._committed = True

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 0

    def test_del_silent_if_rolled_back(self):
        """__del__ must not warn if transaction was rolled back."""
        mock_pool = Mock()
        mock_connection = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection
        txn._rolled_back = True

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 0

    def test_del_silent_if_connection_is_none(self):
        """__del__ must not warn if connection is None (never entered)."""
        mock_pool = Mock()

        txn = MySQLTransaction(mock_pool)
        # connection stays None (never entered)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 0

    def test_del_includes_source_traceback_in_warning(self):
        """__del__ warning must include source traceback when available."""
        if not __debug__:
            pytest.skip("Test requires __debug__ == True (no -O flag)")

        mock_pool = Mock()
        mock_connection = Mock()

        txn = MySQLTransaction(mock_pool)
        txn.connection = mock_connection
        # _source_traceback should be set by __init__ in debug mode

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()

            assert len(w) == 1
            warning_message = str(w[0].message)
            assert "Created at:" in warning_message
            # The traceback should contain a reference to this test file
            assert "test_mysql_transaction_hardening" in warning_message


class TestMySQLTransactionInitSignature:
    """Test that the __init__ signature accepts pool; connection is set in __aenter__."""

    def test_init_requires_pool_only(self):
        """__init__ must accept pool as the sole positional arg; connection starts as None."""
        pool = Mock()
        txn = MySQLTransaction(pool)
        assert txn.connection_pool is pool
        assert txn.connection is None


class TestMySQLTransactionAenter:
    """Test that __aenter__ still works correctly with the new init signature."""

    @pytest.mark.asyncio
    async def test_aenter_begins_transaction(self):
        """__aenter__ must acquire connection from pool and call begin()."""
        mock_connection = AsyncMock()
        mock_pool = AsyncMock()
        mock_pool.acquire = AsyncMock(return_value=mock_connection)

        txn = MySQLTransaction(mock_pool)
        result = await txn.__aenter__()

        mock_pool.acquire.assert_called_once()
        mock_connection.begin.assert_called_once()
        assert result is txn
        assert txn.connection is mock_connection
