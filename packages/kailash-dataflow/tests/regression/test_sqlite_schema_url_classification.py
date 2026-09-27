"""SQLite schema dispatch depends on URL schemes, never filename substrings."""

import logging
import sqlite3
from urllib.parse import quote

import pytest
from test_memory_cache_instance_identity import (
    owned_sqlite_file_pools as owned_sqlite_file_pools,
)

from dataflow import DataFlow
from dataflow.exceptions import EnhancedDataFlowError


def memory_url(tmp_path, kind):
    if kind == "shared":
        return f"file:{tmp_path / 'shared'}?mode=memory&cache=shared"
    name = {"postgres_vfs": "postgres_catalog", "mysql_vfs": "mysql_catalog"}.get(
        kind, "catalog"
    )
    return f"file:{tmp_path / name}?vfs=memdb"


def assert_no_warnings(caplog):
    assert not [
        (record.name, record.getMessage())
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("filename", ["catalog.db", "postgresql_catalog.db"])
async def test_native_file_schema_inspection_uses_sqlite(tmp_path, filename, caplog):
    path = tmp_path / filename
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE proof (id INTEGER PRIMARY KEY, value TEXT)")
        connection.execute("INSERT INTO proof VALUES (1, 'retained')")
    connection.close()
    url = f"file:{quote(str(path))}?mode=ro"
    db = DataFlow(url, auto_migrate=False, test_mode=False)
    try:
        with caplog.at_level(logging.WARNING):
            schema = await db.discover_schema_async(use_real_inspection=True)
        assert set(schema) == {"proof"}
        assert [column["name"] for column in schema["proof"]["columns"]] == [
            "id",
            "value",
        ]
        assert schema["proof"]["columns"][0]["primary_key"] is True
        assert db.config.database.url == url
        assert_no_warnings(caplog)
    finally:
        await db.close_async()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["vfs", "shared", "postgres_vfs", "mysql_vfs"])
async def test_async_memory_model_registration_avoids_schema_discovery(
    tmp_path, kind, caplog
):
    url = memory_url(tmp_path, kind)
    db = DataFlow(url, test_mode=False)
    try:
        with caplog.at_level(logging.WARNING):

            @db.model
            class SchemaRow:
                id: str
                value: str

            assert await db.initialize()
            assert await db.ensure_table_exists("SchemaRow")
            created = await db.express.create(
                "SchemaRow", {"id": "one", "value": "retained"}
            )
            assert created["value"] == "retained"
            assert (await db.express.read("SchemaRow", "one"))["value"] == "retained"
            assert await db._verify_table_physically_exists("SchemaRow", url) is True
            fields = dict(db._model_fields["SchemaRow"])
            fields["note"] = {"type": str, "required": False}
            await db._reconcile_columns_async("SchemaRow", fields, url)
            with db._open_sqlite_connection(url) as connection:
                assert "note" in {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(schema_rows)")
                }
            connection.close()
        assert db.config.database.url == url
        assert_no_warnings(caplog)
    finally:
        await db.close_async()


@pytest.mark.parametrize("kind", ["vfs", "shared", "postgres_vfs", "mysql_vfs"])
def test_sync_memory_model_registration_avoids_schema_discovery(tmp_path, kind, caplog):
    url = memory_url(tmp_path, kind)
    db = DataFlow(url, test_mode=False)
    try:
        with caplog.at_level(logging.WARNING):

            @db.model
            class SchemaRow:
                id: str
                value: str

            # Legacy synchronous callers still invoke this sibling directly;
            # @model now defers relationship processing to async initialize().
            db._auto_detect_relationships("SchemaRow", db._model_fields["SchemaRow"])
            created = db.express_sync.create(
                "SchemaRow", {"id": "one", "value": "retained"}
            )
            assert created["value"] == "retained"
            assert db.express_sync.read("SchemaRow", "one")["value"] == "retained"
        assert db.config.database.url == url
        assert_no_warnings(caplog)
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["vfs", "shared"])
async def test_explicit_memory_schema_inspection_remains_unsupported(tmp_path, kind):
    db = DataFlow(memory_url(tmp_path, kind), test_mode=False)
    try:
        with pytest.raises(EnhancedDataFlowError, match="in-memory SQLite"):
            await db.discover_schema_async(use_real_inspection=True)
    finally:
        await db.close_async()


@pytest.mark.asyncio
async def test_postgres_named_sqlite_uses_real_sqlite_audit_backend(
    tmp_path, monkeypatch, caplog
):
    from dataflow.core.event_stores.sqlite import SQLiteEventStore

    monkeypatch.chdir(tmp_path)
    db = DataFlow(
        memory_url(tmp_path, "postgres_vfs"), audit_logging=True, test_mode=False
    )
    try:
        with caplog.at_level(logging.WARNING):
            assert await db.initialize()
        assert isinstance(db._audit_backend, SQLiteEventStore)
        with sqlite3.connect(tmp_path / "audit_events.db") as connection:
            assert connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'audit_events'"
            ).fetchall() == [("audit_events",)]
        connection.close()
        assert_no_warnings(caplog)
    finally:
        await db.close_async()


@pytest.mark.parametrize("kind", ["vfs", "postgres_vfs"])
def test_native_memory_schema_operations_retain_sqlite_dialect(tmp_path, kind, caplog):
    db = DataFlow(memory_url(tmp_path, kind), test_mode=False)
    try:
        with caplog.at_level(logging.WARNING):
            # The sync migration wrapper is the production consumer, not a
            # replacement driver or a generated-SQL-only assertion.
            db._execute_multi_statement_ddl(
                [
                    "CREATE TABLE proof (id INTEGER PRIMARY KEY, value TEXT)",
                    "ALTER TABLE proof ADD COLUMN note TEXT",
                ]
            )
            with db._open_sqlite_connection(db._effective_database_url()) as connection:
                assert [
                    row[1] for row in connection.execute("PRAGMA table_info(proof)")
                ] == ["id", "value", "note"]
            connection.close()
            columns = db._convert_fields_to_columns({"id": {"type": int}})
            assert columns["id"]["type"] == "INTEGER"
            assert columns["id"]["default"] is None
        assert_no_warnings(caplog)
    finally:
        db.close()
