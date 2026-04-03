"""
Unit Tests for SQLiteEnterpriseTransaction Bug Fixes

Tests for:
- TODO-018: Fix __aexit__ context manager bug (connection leak)
- TODO-006: __del__ fallback for SQLiteEnterpriseTransaction

These tests validate that:
1. The same context manager instance used in __aenter__ is used in __aexit__
2. Connections are properly returned to the pool after transaction exit
3. __del__ warns when a transaction is GC'd without commit/rollback
4. Class-level defaults prevent AttributeError in __del__ if __init__ fails
5. _committed and _rolled_back flags are properly tracked
"""

import asyncio
import gc
import sys
import tempfile
import traceback
import warnings
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataflow.adapters.sqlite_enterprise import (
    SQLiteEnterpriseAdapter,
    SQLiteEnterpriseTransaction,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def temp_sqlite_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    yield db_path

    try:
        Path(db_path).unlink()
        Path(db_path + "-wal").unlink(missing_ok=True)
        Path(db_path + "-shm").unlink(missing_ok=True)
    except Exception:
        pass


@pytest.fixture
async def adapter(temp_sqlite_db):
    """Create and connect an enterprise adapter."""
    adapter = SQLiteEnterpriseAdapter(
        temp_sqlite_db,
        enable_wal=True,
        enable_connection_pooling=True,
        enable_performance_monitoring=False,
        max_connections=5,
    )
    await adapter.connect()
    yield adapter
    await adapter.disconnect()


@pytest.fixture
async def adapter_with_table(adapter):
    """Adapter with a test table created."""
    await adapter.execute_query(
        "CREATE TABLE tx_test (id INTEGER PRIMARY KEY, value TEXT)"
    )
    return adapter


# ---------------------------------------------------------------------------
# TODO-018: Context manager instance reuse tests
# ---------------------------------------------------------------------------


class TestContextManagerInstanceReuse:
    """Verify that __aenter__ and __aexit__ use the SAME context manager instance."""

    async def test_conn_cm_stored_in_aenter(self, adapter_with_table):
        """__aenter__ must store the context manager instance as _conn_cm."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")

        async with tx:
            # The transaction must have a _conn_cm attribute after entering
            assert hasattr(
                tx, "_conn_cm"
            ), "_conn_cm attribute must be set in __aenter__"
            assert tx._conn_cm is not None, "_conn_cm must not be None after __aenter__"

    async def test_connection_not_leaked_on_normal_exit(self, adapter_with_table):
        """After exiting normally, the connection must be returned to the pool."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")

        async with tx:
            await tx.execute("INSERT INTO tx_test (value) VALUES (?)", ["leak_test"])

        # After exit, verify the insert was committed
        result = await adapter_with_table.execute_query(
            "SELECT value FROM tx_test WHERE value = 'leak_test'"
        )
        assert len(result) == 1
        assert result[0]["value"] == "leak_test"

    async def test_connection_not_leaked_on_exception_exit(self, adapter_with_table):
        """After exiting due to exception, the connection must still be returned."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")

        with pytest.raises(ValueError, match="intentional"):
            async with tx:
                await tx.execute(
                    "INSERT INTO tx_test (value) VALUES (?)", ["exception_test"]
                )
                raise ValueError("intentional error")

        # The insert should have been rolled back
        result = await adapter_with_table.execute_query(
            "SELECT value FROM tx_test WHERE value = 'exception_test'"
        )
        assert len(result) == 0

    async def test_multiple_sequential_transactions(self, adapter_with_table):
        """Multiple sequential transactions must not leak connections."""
        for i in range(10):
            async with adapter_with_table.transaction() as tx:
                await tx.execute("INSERT INTO tx_test (value) VALUES (?)", [f"seq_{i}"])

        result = await adapter_with_table.execute_query(
            "SELECT COUNT(*) as count FROM tx_test"
        )
        assert result[0]["count"] == 10

    async def test_aexit_does_not_create_new_context_manager(self, adapter_with_table):
        """__aexit__ must use the stored _conn_cm, not call _get_connection() again."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")

        # Patch _get_connection to track calls after __aenter__
        original_get_connection = adapter_with_table._get_connection
        call_count_before_enter = 0
        call_count_after_enter = 0
        entered = False

        class CountingWrapper:
            """Wraps _get_connection to count calls."""

            def __init__(self):
                self.calls = []

            def __call__(self):
                cm = original_get_connection()
                self.calls.append(cm)
                return cm

        counter = CountingWrapper()

        with patch.object(adapter_with_table, "_get_connection", counter):
            async with tx:
                # One call should have happened during __aenter__
                calls_at_enter = len(counter.calls)
                assert (
                    calls_at_enter == 1
                ), f"Expected exactly 1 call to _get_connection in __aenter__, got {calls_at_enter}"

            # After __aexit__, no additional call to _get_connection should have happened
            calls_at_exit = len(counter.calls)
            assert calls_at_exit == 1, (
                f"Expected no additional calls to _get_connection in __aexit__, "
                f"but got {calls_at_exit} total calls (extra {calls_at_exit - 1} in __aexit__)"
            )


# ---------------------------------------------------------------------------
# TODO-006: __del__ fallback tests
# ---------------------------------------------------------------------------


class TestDelFallback:
    """Verify __del__ warns and attempts cleanup for leaked transactions."""

    def test_class_level_defaults_exist(self):
        """SQLiteEnterpriseTransaction must have class-level defaults for safety."""
        # These must exist as class attributes so __del__ can reference them
        # even if __init__ raised an exception
        assert hasattr(
            SQLiteEnterpriseTransaction, "connection"
        ), "Class-level 'connection' default missing"
        assert hasattr(
            SQLiteEnterpriseTransaction, "_conn_cm"
        ), "Class-level '_conn_cm' default missing"
        assert hasattr(
            SQLiteEnterpriseTransaction, "_committed"
        ), "Class-level '_committed' default missing"
        assert hasattr(
            SQLiteEnterpriseTransaction, "_rolled_back"
        ), "Class-level '_rolled_back' default missing"
        assert hasattr(
            SQLiteEnterpriseTransaction, "transaction_started"
        ), "Class-level 'transaction_started' default missing"
        assert hasattr(
            SQLiteEnterpriseTransaction, "_source_traceback"
        ), "Class-level '_source_traceback' default missing"

    def test_class_level_default_values(self):
        """Class-level defaults must have correct initial values."""
        assert SQLiteEnterpriseTransaction.connection is None
        assert SQLiteEnterpriseTransaction._conn_cm is None
        assert SQLiteEnterpriseTransaction._committed is False
        assert SQLiteEnterpriseTransaction._rolled_back is False
        assert SQLiteEnterpriseTransaction.transaction_started is False
        assert SQLiteEnterpriseTransaction._source_traceback is None

    async def test_committed_flag_set_on_commit(self, adapter_with_table):
        """_committed must be True after successful commit."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")

        async with tx:
            await tx.execute("INSERT INTO tx_test (value) VALUES (?)", ["commit_flag"])

        assert tx._committed is True
        assert tx._rolled_back is False

    async def test_rolled_back_flag_set_on_rollback(self, adapter_with_table):
        """_rolled_back must be True after rollback due to exception."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")

        with pytest.raises(RuntimeError):
            async with tx:
                await tx.execute(
                    "INSERT INTO tx_test (value) VALUES (?)", ["rollback_flag"]
                )
                raise RuntimeError("force rollback")

        assert tx._rolled_back is True
        assert tx._committed is False

    async def test_del_warns_on_uncommitted_transaction(self, adapter_with_table):
        """__del__ must emit ResourceWarning for uncommitted transactions."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")

        # Manually enter but never exit (simulating a leaked transaction)
        await tx.__aenter__()

        # At this point: transaction_started=True, _committed=False, _rolled_back=False
        assert tx.transaction_started is True
        assert tx._committed is False
        assert tx._rolled_back is False
        assert tx.connection is not None

        # __del__ should warn
        with warnings.catch_warnings(record=True) as w:
            warnings.resetwarnings()
            warnings.simplefilter("always")
            tx.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert (
                len(resource_warnings) >= 1
            ), f"Expected at least 1 ResourceWarning, got {len(resource_warnings)}"
            assert "SQLiteEnterpriseTransaction" in str(resource_warnings[0].message)
            assert "commit/rollback" in str(resource_warnings[0].message).lower()

        # Clean up the leaked connection manually
        try:
            await tx.connection.execute("ROLLBACK")
        except Exception:
            pass
        if tx._conn_cm is not None:
            await tx._conn_cm.__aexit__(None, None, None)

    async def test_del_silent_after_commit(self, adapter_with_table):
        """__del__ must NOT warn after a successful commit."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")

        async with tx:
            await tx.execute("INSERT INTO tx_test (value) VALUES (?)", ["del_commit"])

        # After successful commit, __del__ should be silent
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tx.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert (
                len(resource_warnings) == 0
            ), f"Expected no ResourceWarning after commit, got {len(resource_warnings)}"

    async def test_del_silent_after_rollback(self, adapter_with_table):
        """__del__ must NOT warn after a rollback."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")

        with pytest.raises(RuntimeError):
            async with tx:
                raise RuntimeError("force rollback")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tx.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert (
                len(resource_warnings) == 0
            ), f"Expected no ResourceWarning after rollback, got {len(resource_warnings)}"

    async def test_del_silent_when_no_connection(self, adapter_with_table):
        """__del__ must NOT warn if connection was never acquired."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")
        # Never entered, so connection is None

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tx.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 0

    async def test_del_silent_when_transaction_not_started(self, adapter_with_table):
        """__del__ must NOT warn if transaction_started is False."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")
        # Simulate connection acquired but transaction never started
        tx.connection = MagicMock()
        tx.transaction_started = False

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tx.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 0

    def test_source_traceback_captured_in_debug_mode(self):
        """_source_traceback must be captured in debug mode."""
        # __debug__ is True unless Python is run with -O flag
        if not __debug__:
            pytest.skip("Requires debug mode (__debug__ == True)")

        mock_adapter = MagicMock()
        tx = SQLiteEnterpriseTransaction(mock_adapter, "DEFERRED")
        assert (
            tx._source_traceback is not None
        ), "_source_traceback must be set in __init__ when __debug__ is True"
        assert isinstance(tx._source_traceback, list)
        assert len(tx._source_traceback) > 0

    async def test_del_includes_traceback_in_warning(self, adapter_with_table):
        """__del__ warning must include source traceback when available."""
        tx = SQLiteEnterpriseTransaction(adapter_with_table, "DEFERRED")
        await tx.__aenter__()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            tx.__del__()

            resource_warnings = [
                x for x in w if issubclass(x.category, ResourceWarning)
            ]
            assert len(resource_warnings) == 1
            warning_text = str(resource_warnings[0].message)
            # If __debug__ is True, traceback should be included
            if __debug__:
                assert (
                    "test_sqlite_enterprise_transaction" in warning_text
                ), "Warning should include source traceback pointing to test file"

        # Clean up leaked connection
        try:
            await tx.connection.execute("ROLLBACK")
        except Exception:
            pass
        if tx._conn_cm is not None:
            await tx._conn_cm.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# Integration between TODO-018 and TODO-006
# ---------------------------------------------------------------------------


class TestCombinedFixes:
    """Test that both fixes work together correctly."""

    async def test_savepoints_still_work_with_fixes(self, adapter_with_table):
        """Savepoint functionality must not be broken by the fixes."""
        async with adapter_with_table.transaction() as tx:
            await tx.execute("INSERT INTO tx_test (value) VALUES (?)", ["sp_base"])
            await tx.savepoint("sp1")
            await tx.execute("INSERT INTO tx_test (value) VALUES (?)", ["sp_after"])
            await tx.rollback_to_savepoint("sp1")

        result = await adapter_with_table.execute_query("SELECT value FROM tx_test")
        values = [r["value"] for r in result]
        assert "sp_base" in values
        assert "sp_after" not in values

    async def test_nested_transaction_pattern(self, adapter_with_table):
        """Sequential transactions with savepoints must work correctly."""
        # First transaction
        async with adapter_with_table.transaction("IMMEDIATE") as tx:
            await tx.execute("INSERT INTO tx_test (value) VALUES (?)", ["nested_1"])
            await tx.savepoint("sp1")
            await tx.execute("INSERT INTO tx_test (value) VALUES (?)", ["nested_2"])
            await tx.release_savepoint("sp1")

        # Second transaction
        async with adapter_with_table.transaction("IMMEDIATE") as tx:
            result = await tx.execute("SELECT COUNT(*) as count FROM tx_test", [])
            assert result[0]["count"] == 2

    async def test_committed_flag_with_savepoints(self, adapter_with_table):
        """_committed must be True even when savepoints are used."""
        tx = adapter_with_table.transaction("DEFERRED")

        async with tx:
            await tx.execute("INSERT INTO tx_test (value) VALUES (?)", ["sp_commit"])
            await tx.savepoint("sp1")
            await tx.execute("INSERT INTO tx_test (value) VALUES (?)", ["sp_commit_2"])
            await tx.release_savepoint("sp1")

        assert tx._committed is True
        assert tx._rolled_back is False
