"""Real SQLite handles distinguish closed stores from actual leaks."""

import sqlite3
import warnings

import pytest

from kailash.tracking.storage.database import SQLiteStorage


@pytest.mark.parametrize("context_managed", [False, True])
def test_closed_store_does_not_emit_leak_warning(tmp_path, context_managed):
    store = SQLiteStorage(str(tmp_path / "tracking.db"))
    assert store.conn.execute("SELECT 1").fetchone() == (1,)
    if context_managed:
        with store:
            pass
    else:
        store.close()
    store.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        store.conn.execute("SELECT 1")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        store.__del__()
    assert not caught


def test_open_store_still_warns_without_closing_handle(tmp_path):
    store = SQLiteStorage(str(tmp_path / "tracking.db"))
    try:
        with pytest.warns(ResourceWarning, match="Unclosed SQLiteStorage"):
            store.__del__()
        assert store.conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        store.close()


def test_failed_schema_initialization_closes_real_connection(tmp_path):
    # A real incompatible schema fails after connect, without a mocked backend.
    path = str(tmp_path / "invalid.db")
    with sqlite3.connect(path) as seed:
        seed.execute("CREATE TABLE schema_version (wrong_column INTEGER)")
    seed.close()
    store = SQLiteStorage.__new__(SQLiteStorage)
    with pytest.raises(sqlite3.OperationalError, match="no such column: version"):
        store.__init__(path)
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        store.conn.execute("SELECT 1")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ResourceWarning)
        store.__del__()
    assert not caught
