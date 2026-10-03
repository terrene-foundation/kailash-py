"""SQLite bootstrap and DLQ owners deterministically release real handles."""

import contextlib
import os
import sqlite3

import pytest

from kailash.runtime.scheduler import _secure_init_sqlite_jobstore
from kailash.workflow.dlq import PersistentDLQ


@pytest.mark.skipif(os.name != "posix", reason="POSIX jobstore initialization")
@pytest.mark.parametrize("fail", [False, True])
def test_jobstore_bootstrap_closes_connection_on_every_exit(
    tmp_path, monkeypatch, fail
):
    connections = []
    original_connect = sqlite3.connect
    failure = RuntimeError("bootstrap initialization failed")

    class Connection(sqlite3.Connection):
        def execute(self, statement, *args, **kwargs):
            if fail and statement.startswith("CREATE TABLE"):
                raise failure
            return super().execute(statement, *args, **kwargs)

    def connect(*args, **kwargs):
        connection = original_connect(*args, factory=Connection, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    path = tmp_path / "schedule.sqlite"
    try:
        if fail:
            with pytest.raises(RuntimeError) as caught:
                _secure_init_sqlite_jobstore(str(path))
            assert caught.value is failure
        else:
            _secure_init_sqlite_jobstore(str(path))
        assert len(connections) == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connections[0].execute("SELECT 1")
        if not fail:
            with contextlib.closing(original_connect(path)) as reopened:
                assert reopened.execute("PRAGMA journal_mode").fetchone() == ("wal",)
                assert reopened.execute(
                    "SELECT count(*) FROM _kailash_secure_init"
                ).fetchone() == (0,)
    finally:
        for connection in connections:
            connection.close()


@pytest.mark.parametrize("boundary", ["close", "context"])
def test_explicit_dlq_disposal_does_not_emit_unclosed_warning(tmp_path, boundary):
    queue = PersistentDLQ(str(tmp_path / "dlq.sqlite"))
    warnings = []
    try:
        queue.__del__(_warn=lambda *args: warnings.append(args))
        assert len(warnings) == 1  # Negative control: an open owner is detected.
        warnings.clear()
        if boundary == "context":
            with queue:
                assert queue.get_stats()["total"] == 0
        else:
            queue.close()
        queue.close()
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            queue._conn.execute("SELECT 1")
        queue.__del__(_warn=lambda *args: warnings.append(args))
        assert warnings == []
    finally:
        queue.close()
        queue._conn = None


def test_failed_dlq_constructor_closes_connection_and_preserves_failure(tmp_path):
    owners = []
    failure = RuntimeError("schema initialization failed")

    class BrokenDLQ(PersistentDLQ):
        def _initialize_schema(self):
            owners.append(self)
            raise failure

    try:
        with pytest.raises(RuntimeError) as caught:
            BrokenDLQ(str(tmp_path / "broken.sqlite"))
        assert caught.value is failure
        assert len(owners) == 1
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            owners[0]._conn.execute("SELECT 1")
    finally:
        for owner in owners:
            owner.close()
            owner._conn = None
