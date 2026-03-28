"""Unit tests for __del__ fallback on all DataFlow transaction classes (TODO-025).

Tests that __del__ fires ResourceWarning correctly on:
- SQLiteTransaction
- PostgreSQLTransaction
- MySQLTransaction
- SQLiteEnterpriseTransaction

Each class is tested for:
1. ResourceWarning on leaked transaction (connection set, not committed/rolled back)
2. No warning when committed
3. No warning when rolled back
4. No warning when connection is None
5. Source traceback included in warning message (debug mode)
"""

import warnings

import pytest

dataflow = pytest.importorskip("dataflow", reason="kailash-dataflow not installed")

from dataflow.adapters.mysql import MySQLTransaction
from dataflow.adapters.postgresql import PostgreSQLTransaction
from dataflow.adapters.sqlite import SQLiteTransaction
from dataflow.adapters.sqlite_enterprise import SQLiteEnterpriseTransaction

# --- Helpers ---


def _make_sqlite_txn():
    """Create a SQLiteTransaction with a fake adapter, simulating a leaked connection."""
    txn = SQLiteTransaction.__new__(SQLiteTransaction)
    txn.connection = object()  # Non-None = "has a connection"
    txn._committed = False
    txn._rolled_back = False
    txn._source_traceback = None
    txn._pool_cm = None
    return txn


def _make_postgresql_txn():
    txn = PostgreSQLTransaction.__new__(PostgreSQLTransaction)
    txn.connection = object()
    txn.transaction = None
    txn._committed = False
    txn._rolled_back = False
    txn._source_traceback = None
    return txn


def _make_mysql_txn():
    txn = MySQLTransaction.__new__(MySQLTransaction)
    txn.connection = object()
    txn._committed = False
    txn._rolled_back = False
    txn._source_traceback = None
    return txn


def _make_enterprise_txn():
    txn = SQLiteEnterpriseTransaction.__new__(SQLiteEnterpriseTransaction)
    txn.connection = object()
    txn._committed = False
    txn._rolled_back = False
    txn._source_traceback = None
    txn.transaction_started = True  # Enterprise checks this too
    txn.savepoints = []
    return txn


# --- SQLiteTransaction ---


class TestSQLiteTransactionDel:
    def test_warns_on_leaked_transaction(self):
        txn = _make_sqlite_txn()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 1
            assert "SQLiteTransaction GC'd" in str(rw[0].message)

    def test_silent_when_committed(self):
        txn = _make_sqlite_txn()
        txn._committed = True
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_silent_when_rolled_back(self):
        txn = _make_sqlite_txn()
        txn._rolled_back = True
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_silent_when_connection_is_none(self):
        txn = _make_sqlite_txn()
        txn.connection = None
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_source_traceback_in_warning(self):
        import traceback as tb_mod

        txn = _make_sqlite_txn()
        txn._source_traceback = tb_mod.extract_stack()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 1
            msg = str(rw[0].message)
            assert "test_transaction_del_fallback" in msg


# --- PostgreSQLTransaction ---


class TestPostgreSQLTransactionDel:
    def test_warns_on_leaked_transaction(self):
        txn = _make_postgresql_txn()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 1
            assert "PostgreSQLTransaction GC'd" in str(rw[0].message)

    def test_silent_when_committed(self):
        txn = _make_postgresql_txn()
        txn._committed = True
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_silent_when_rolled_back(self):
        txn = _make_postgresql_txn()
        txn._rolled_back = True
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_silent_when_connection_is_none(self):
        txn = _make_postgresql_txn()
        txn.connection = None
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_no_sync_operations_attempted(self):
        """PostgreSQL __del__ should NOT attempt sync rollback."""
        import inspect

        source = inspect.getsource(PostgreSQLTransaction.__del__)
        assert "rollback()" not in source or "Cannot do sync" in source


# --- MySQLTransaction ---


class TestMySQLTransactionDel:
    def test_warns_on_leaked_transaction(self):
        txn = _make_mysql_txn()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 1
            assert "MySQLTransaction GC'd" in str(rw[0].message)

    def test_silent_when_committed(self):
        txn = _make_mysql_txn()
        txn._committed = True
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_silent_when_rolled_back(self):
        txn = _make_mysql_txn()
        txn._rolled_back = True
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_silent_when_connection_is_none(self):
        txn = _make_mysql_txn()
        txn.connection = None
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_no_sync_operations_attempted(self):
        """MySQL __del__ should NOT attempt sync rollback."""
        import inspect

        source = inspect.getsource(MySQLTransaction.__del__)
        assert "rollback()" not in source or "Cannot do sync" in source


# --- SQLiteEnterpriseTransaction ---


class TestSQLiteEnterpriseTransactionDel:
    def test_warns_on_leaked_transaction(self):
        txn = _make_enterprise_txn()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 1
            assert "SQLiteEnterpriseTransaction GC'd" in str(rw[0].message)

    def test_silent_when_committed(self):
        txn = _make_enterprise_txn()
        txn._committed = True
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_silent_when_rolled_back(self):
        txn = _make_enterprise_txn()
        txn._rolled_back = True
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_silent_when_connection_is_none(self):
        txn = _make_enterprise_txn()
        txn.connection = None
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_silent_when_transaction_not_started(self):
        """Enterprise __del__ also checks transaction_started."""
        txn = _make_enterprise_txn()
        txn.transaction_started = False
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 0

    def test_source_traceback_in_warning(self):
        import traceback as tb_mod

        txn = _make_enterprise_txn()
        txn._source_traceback = tb_mod.extract_stack()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            txn.__del__()
            rw = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(rw) == 1
            msg = str(rw[0].message)
            assert "test_transaction_del_fallback" in msg
