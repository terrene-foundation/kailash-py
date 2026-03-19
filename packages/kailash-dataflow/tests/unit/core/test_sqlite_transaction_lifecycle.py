#!/usr/bin/env python3
"""
Unit tests for SQLiteTransaction lifecycle management.

Tests two features:
  TODO-003: __del__ fallback for SQLiteTransaction (ResourceWarning on GC without commit/rollback)
  TODO-008: Pool-level leak detection via WeakSet in SQLiteAdapter

Uses standardized unit test fixtures and follows Tier 1 testing policy:
- SQLite databases (both :memory: and file-based)
- Mocks and stubs for external services
- NO PostgreSQL connections
"""

import gc
import warnings
import weakref

import pytest

from dataflow.adapters.sqlite import SQLiteAdapter, SQLiteTransaction


# ---------------------------------------------------------------------------
# TODO-003  __del__ Fallback for SQLiteTransaction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSQLiteTransactionDel:
    """Tests that SQLiteTransaction.__del__ warns on leaked (uncommitted) transactions."""

    def test_class_level_defaults_exist(self):
        """Class-level defaults must exist so __del__ is safe even if __init__ fails."""
        assert hasattr(SQLiteTransaction, "_committed")
        assert hasattr(SQLiteTransaction, "_rolled_back")
        assert hasattr(SQLiteTransaction, "connection")
        assert hasattr(SQLiteTransaction, "_source_traceback")

        # Verify default values
        assert SQLiteTransaction._committed is False
        assert SQLiteTransaction._rolled_back is False
        assert SQLiteTransaction.connection is None
        assert SQLiteTransaction._source_traceback is None

    def test_init_sets_instance_state(self):
        """__init__ must set _committed, _rolled_back, and _source_traceback on the instance."""
        adapter = SQLiteAdapter(":memory:")
        txn = SQLiteTransaction(adapter)

        assert txn._committed is False
        assert txn._rolled_back is False
        assert txn.connection is None
        # In debug mode (__debug__ is True in normal pytest), traceback should be captured
        assert txn._source_traceback is not None

    def test_del_silent_when_committed(self):
        """__del__ must not warn when the transaction was committed."""
        adapter = SQLiteAdapter(":memory:")
        txn = SQLiteTransaction(adapter)
        txn._committed = True
        txn.connection = object()  # Simulate a non-None connection

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            txn.__del__()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert len(resource_warnings) == 0, "No warning expected after commit"

    def test_del_silent_when_rolled_back(self):
        """__del__ must not warn when the transaction was rolled back."""
        adapter = SQLiteAdapter(":memory:")
        txn = SQLiteTransaction(adapter)
        txn._rolled_back = True
        txn.connection = object()  # Simulate a non-None connection

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            txn.__del__()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert len(resource_warnings) == 0, "No warning expected after rollback"

    def test_del_silent_when_connection_is_none(self):
        """__del__ must not warn when connection was never acquired."""
        adapter = SQLiteAdapter(":memory:")
        txn = SQLiteTransaction(adapter)
        # connection is None by default — never entered __aenter__

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            txn.__del__()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert len(resource_warnings) == 0, (
            "No warning expected when connection is None"
        )

    def test_del_warns_on_leaked_transaction(self):
        """__del__ must emit ResourceWarning when transaction has a connection but was never committed/rolled back."""
        adapter = SQLiteAdapter(":memory:")
        txn = SQLiteTransaction(adapter)
        # Simulate a connection was acquired but never committed or rolled back
        txn.connection = object()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            txn.__del__()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert len(resource_warnings) == 1, "Expected exactly one ResourceWarning"
        msg = str(resource_warnings[0].message)
        assert "SQLiteTransaction GC'd without commit/rollback" in msg

    def test_del_warning_includes_traceback_when_available(self):
        """__del__ warning message should include source traceback if available."""
        adapter = SQLiteAdapter(":memory:")
        txn = SQLiteTransaction(adapter)
        txn.connection = object()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            txn.__del__()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert len(resource_warnings) == 1
        msg = str(resource_warnings[0].message)
        # The traceback should reference this test file
        assert "test_sqlite_transaction_lifecycle" in msg or "Created at:" in msg

    def test_del_attempts_sync_rollback(self):
        """__del__ should attempt a synchronous rollback via the underlying sqlite3 connection."""

        class FakeUnderlyingConn:
            def __init__(self):
                self.rollback_called = False

            def rollback(self):
                self.rollback_called = True

        class FakeConnection:
            def __init__(self):
                self._conn = FakeUnderlyingConn()

        adapter = SQLiteAdapter(":memory:")
        txn = SQLiteTransaction(adapter)
        fake_conn = FakeConnection()
        txn.connection = fake_conn

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            txn.__del__()

        assert fake_conn._conn.rollback_called, (
            "Expected __del__ to call _conn.rollback()"
        )

    @pytest.mark.asyncio
    async def test_aexit_sets_committed_on_success(self):
        """__aexit__ with no exception should set _committed = True."""
        adapter = SQLiteAdapter(":memory:")
        await adapter.connect()
        try:
            txn = adapter.transaction()
            async with txn:
                pass  # No exception — should commit
            assert txn._committed is True
            assert txn._rolled_back is False
        finally:
            await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_aexit_sets_rolled_back_on_exception(self):
        """__aexit__ with an exception should set _rolled_back = True."""
        adapter = SQLiteAdapter(":memory:")
        await adapter.connect()
        try:
            txn = adapter.transaction()
            with pytest.raises(ValueError, match="test error"):
                async with txn:
                    raise ValueError("test error")
            assert txn._rolled_back is True
            assert txn._committed is False
        finally:
            await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_commit_sets_committed_flag(self):
        """Explicit commit() should set _committed = True."""
        adapter = SQLiteAdapter(":memory:")
        await adapter.connect()
        try:
            txn = adapter.transaction()
            async with txn:
                await txn.commit()
            assert txn._committed is True
        finally:
            await adapter.disconnect()

    @pytest.mark.asyncio
    async def test_rollback_sets_rolled_back_flag(self):
        """Explicit rollback() should set _rolled_back = True."""
        adapter = SQLiteAdapter(":memory:")
        await adapter.connect()
        try:
            txn = adapter.transaction()
            async with txn:
                await txn.rollback()
            assert txn._rolled_back is True
        finally:
            await adapter.disconnect()


# ---------------------------------------------------------------------------
# TODO-008  Pool-Level Leak Detection via WeakSet
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSQLiteAdapterWeakSetTracking:
    """Tests that SQLiteAdapter tracks active transactions via WeakSet."""

    def test_adapter_has_active_transactions_weakset(self):
        """SQLiteAdapter must initialise _active_transactions as a WeakSet."""
        adapter = SQLiteAdapter(":memory:")
        assert hasattr(adapter, "_active_transactions")
        assert isinstance(adapter._active_transactions, weakref.WeakSet)

    def test_transaction_added_to_weakset_on_creation(self):
        """Creating a transaction via adapter.transaction() must add it to the WeakSet."""
        adapter = SQLiteAdapter(":memory:")
        adapter.is_connected = True  # Bypass connect check for unit test
        txn = adapter.transaction()
        assert txn in adapter._active_transactions

    def test_weakset_releases_after_gc(self):
        """WeakSet should release the transaction reference after GC."""
        adapter = SQLiteAdapter(":memory:")
        adapter.is_connected = True
        txn = adapter.transaction()
        # Mark as committed so __del__ doesn't warn
        txn._committed = True
        assert len(adapter._active_transactions) == 1

        # Delete and collect
        del txn
        gc.collect()

        assert len(adapter._active_transactions) == 0

    @pytest.mark.asyncio
    async def test_disconnect_warns_on_leaked_transactions(self):
        """disconnect() must warn when there are still-active (uncommitted) transactions."""
        adapter = SQLiteAdapter(":memory:")
        await adapter.connect()

        # Create a transaction object and keep it alive
        txn = adapter.transaction()
        # Simulate that the connection was acquired (so it looks leaked)
        txn.connection = object()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            await adapter.disconnect()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert len(resource_warnings) == 1
        msg = str(resource_warnings[0].message)
        assert "1 transaction(s) still active" in msg
        # Clean up to avoid __del__ warning
        txn._committed = True

    @pytest.mark.asyncio
    async def test_disconnect_no_warning_when_all_committed(self):
        """disconnect() must NOT warn when all transactions were committed."""
        adapter = SQLiteAdapter(":memory:")
        await adapter.connect()

        txn = adapter.transaction()
        txn._committed = True
        txn.connection = object()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            await adapter.disconnect()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert len(resource_warnings) == 0

    @pytest.mark.asyncio
    async def test_disconnect_no_warning_when_all_rolled_back(self):
        """disconnect() must NOT warn when all transactions were rolled back."""
        adapter = SQLiteAdapter(":memory:")
        await adapter.connect()

        txn = adapter.transaction()
        txn._rolled_back = True
        txn.connection = object()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            await adapter.disconnect()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert len(resource_warnings) == 0

    @pytest.mark.asyncio
    async def test_multiple_leaked_transactions_counted(self):
        """disconnect() must report the correct count of leaked transactions."""
        adapter = SQLiteAdapter(":memory:")
        await adapter.connect()

        txns = []
        for _ in range(3):
            txn = adapter.transaction()
            txn.connection = object()
            txns.append(txn)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            await adapter.disconnect()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert len(resource_warnings) == 1
        msg = str(resource_warnings[0].message)
        assert "3 transaction(s) still active" in msg
        # Clean up
        for t in txns:
            t._committed = True

    @pytest.mark.asyncio
    async def test_full_lifecycle_no_leak(self):
        """A properly used transaction should not trigger any leak warnings."""
        adapter = SQLiteAdapter(":memory:")
        await adapter.connect()

        async with adapter.transaction() as txn:
            # Normal transaction usage
            pass

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            await adapter.disconnect()

        resource_warnings = [
            w for w in caught if issubclass(w.category, ResourceWarning)
        ]
        assert len(resource_warnings) == 0
