"""Every SQLite producer reaches the same physical database and URI options."""

import logging
import sqlite3
from urllib.parse import quote

import pytest
from test_memory_cache_instance_identity import (
    owned_sqlite_file_pools as owned_sqlite_file_pools,
    private_redis as private_redis,
)

from dataflow import DataFlow
from dataflow.migrations.migration_connection_manager import MigrationConnectionManager
from kailash.utils.sqlite_url import sqlite_sqlalchemy_url


@pytest.mark.asyncio
@pytest.mark.parametrize("form", ["two", "three", "four", "file", "file_options"])
async def test_public_crud_registry_and_getter_share_sqlite_file(
    form, tmp_path, monkeypatch, caplog
):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "rows space.db"
    url = {
        "two": "sqlite://rows space.db",
        "three": "sqlite:///rows space.db",
        "four": f"sqlite:///{path}",
        "file": f"file:{quote(str(path))}",
        "file_options": f"file:{quote(str(path))}?mode=rwc",
    }[form]
    db = DataFlow(url, test_mode=False)
    connection = None
    try:

        @db.model
        class AddressRow:
            id: str
            value: str

        assert await db.initialize()
        assert db.config.database.url == url
        await db.express.create("AddressRow", {"id": "one", "value": form})
        assert (await db.express.read("AddressRow", "one"))["value"] == form
        connection = await db._get_async_database_connection()
        async with connection.execute("PRAGMA database_list") as cursor:
            assert (await cursor.fetchone())[2] == str(path)
        async with connection.execute("SELECT value FROM address_rows") as cursor:
            assert await cursor.fetchall() == [(form,)]
        async with connection.execute(
            "SELECT name FROM sqlite_master WHERE name='dataflow_model_registry'"
        ) as cursor:
            assert await cursor.fetchone() == ("dataflow_model_registry",)
        from kailash.db.connection import ConnectionManager

        core = ConnectionManager(url)
        try:
            await core.initialize()
            assert await core.fetch("SELECT value FROM address_rows") == [
                {"value": form}
            ]
        finally:
            await core.close()
        with db._open_sqlite_connection(url) as inspection:
            assert inspection.execute("SELECT value FROM address_rows").fetchone() == (
                form,
            )
        inspection.close()
        assert await db._verify_table_physically_exists("AddressRow", url) is True
        with MigrationConnectionManager(db) as manager:
            with manager.get_connection() as migration_connection:
                assert migration_connection.execute("PRAGMA database_list").fetchone()[
                    2
                ] == str(path)
                assert migration_connection.execute(
                    "SELECT value FROM address_rows"
                ).fetchall() == [(form,)]
        from dataflow.adapters.database_source_adapter import DatabaseSourceAdapter
        from dataflow.database.query_builder import DatabaseType, create_query_builder
        from dataflow.fabric.config import DatabaseSourceConfig

        source = DatabaseSourceAdapter("parity", DatabaseSourceConfig(url=url))
        try:
            await source.connect()
            assert [row["value"] for row in await source.fetch("address_rows")] == [
                form
            ]
        finally:
            await source.disconnect()
        builder = create_query_builder("address_rows", url)
        assert builder.database_type == DatabaseType.SQLITE
        sql, parameters = builder.where("id", "$eq", "one").build_select()
        async with connection.execute(sql, parameters) as cursor:
            assert len(await cursor.fetchall()) == 1
        schema = await db.discover_schema_async(use_real_inspection=True)
        assert "address_rows" in schema
        assert not [
            r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
        ]
    finally:
        if connection is not None:
            await connection.close()
        await db.close_async()


@pytest.mark.asyncio
async def test_cache_identity_is_same_for_aliases_of_one_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "cache.db"
    databases = [
        DataFlow(url, test_mode=False)
        for url in [
            "sqlite://cache.db",
            "sqlite:///cache.db",
            f"sqlite:///{path}",
            f"file:{path}?mode=rwc",
        ]
    ]
    try:
        for db in databases:
            assert await db.initialize()
        query = [db._cache_integration.key_generator.db_identity for db in databases]
        express = [db.express._key_gen.express_db_instance for db in databases]
        assert all(query) and len(set(query)) == 1
        assert all(express) and len(set(express)) == 1
    finally:
        for db in databases:
            await db.close_async()


@pytest.mark.asyncio
async def test_native_readonly_uri_keeps_driver_write_protection(tmp_path):
    path = tmp_path / "readonly.db"
    writable = DataFlow(f"sqlite:///{path}", test_mode=False)
    connection = None
    readonly = None
    try:

        @writable.model
        class ReadOnlyRow:
            id: str
            value: str

        assert await writable.initialize()
        await writable.express.create("ReadOnlyRow", {"id": "one", "value": "retained"})
        readonly = DataFlow(
            f"file:{path}?mode=ro",
            auto_migrate=False,
            existing_schema_mode=True,
            enable_model_persistence=False,
            test_mode=False,
        )
        connection = await readonly._get_async_database_connection()
        async with connection.execute("SELECT value FROM read_only_rows") as cursor:
            assert await cursor.fetchall() == [("retained",)]
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            await connection.execute("DELETE FROM read_only_rows")
        async with connection.execute("SELECT COUNT(*) FROM read_only_rows") as cursor:
            assert await cursor.fetchone() == (1,)
    finally:
        if connection is not None:
            await connection.close()
        if readonly is not None:
            await readonly.close_async()
        await writable.close_async()


@pytest.mark.parametrize(
    "url", ["postgresql://localhost/db", "mysql+pymysql://localhost/db"]
)
def test_other_engine_urls_are_byte_unchanged(url):
    assert sqlite_sqlalchemy_url(url) == url


@pytest.mark.parametrize(
    "suffix", ["mode=memory&mode=rwc", "mode=rwc&mode=memory", "uri=true&uri=false"]
)
def test_duplicate_uri_options_rejected_before_driver(suffix, tmp_path, monkeypatch):
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("driver reached before duplicate validation")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    with pytest.raises(ValueError, match="Duplicate SQLite option"):
        SyncDDLExecutor(f"file:{tmp_path / 'same.db'}?{suffix}")._get_sync_connection()
    assert calls == []


@pytest.mark.asyncio
async def test_sqlalchemy_uri_options_idempotence_and_readonly(tmp_path):
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor
    from kailash.db.connection import ConnectionManager
    from kailash.nodes.data.sql import _configure_sqlite_memory_pool

    path = tmp_path / "options.db"
    with sqlite3.connect(path) as setup:
        setup.execute("CREATE TABLE proof(value TEXT)")
        setup.execute("INSERT INTO proof VALUES ('kept')")
    setup.close()
    url = f"sqlite:///file:{path}?mode=ro&uri=true&timeout=1"
    canonical = sqlite_sqlalchemy_url(url)
    assert sqlite_sqlalchemy_url(canonical) == canonical
    sync_engine = create_engine(_configure_sqlite_memory_pool(url, {}))
    try:
        with sync_engine.connect() as connection:
            assert connection.execute(text("SELECT value FROM proof")).all() == [
                ("kept",)
            ]
            with pytest.raises(OperationalError, match="readonly"):
                connection.execute(text("DELETE FROM proof"))
    finally:
        sync_engine.dispose()
    native = SyncDDLExecutor(url)._get_sync_connection()
    try:
        assert native.execute("SELECT value FROM proof").fetchone() == ("kept",)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            native.execute("DELETE FROM proof")
    finally:
        native.close()
    core = ConnectionManager(f"sqlite+aiosqlite:///{path}?timeout=1")
    try:
        await core.initialize()
        assert await core.fetch("SELECT value FROM proof") == [{"value": "kept"}]
    finally:
        await core.close()


@pytest.mark.asyncio
async def test_native_rw_does_not_create_missing_database(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError

    from dataflow.adapters.sqlite import SQLiteAdapter
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    path = tmp_path / "missing.db"
    url = f"file:{path}?mode=rw"
    with pytest.raises(sqlite3.OperationalError):
        SyncDDLExecutor(url)._get_sync_connection()
    engine = create_engine(sqlite_sqlalchemy_url(url))
    try:
        with pytest.raises(OperationalError):
            engine.connect()
    finally:
        engine.dispose()
    # The direct getter must fail before returning a handle too.
    db = DataFlow(url, test_mode=False)
    try:
        with pytest.raises(sqlite3.OperationalError):
            await db._get_async_database_connection()
    finally:
        await db.close_async()
    assert not path.exists()


@pytest.mark.parametrize("flag", ["false", "0", "off", "no"])
def test_explicit_false_uri_rejected_before_driver(flag, tmp_path, monkeypatch):
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("driver reached before URI option validation")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    url = f"sqlite:///file:{tmp_path / 'readonly.db'}?mode=ro&uri={flag}"
    with pytest.raises(ValueError, match="require uri=true"):
        SyncDDLExecutor(url)._get_sync_connection()
    with pytest.raises(ValueError, match="require uri=true"):
        sqlite_sqlalchemy_url(url)
    assert calls == []


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["query", "express"])
@pytest.mark.parametrize("variant", ["vfs", "filename"])
async def test_real_redis_separates_physical_uri_databases(
    private_redis, surface, variant, tmp_path
):
    from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter

    if variant == "vfs":
        path = tmp_path / "vfs.db"
        urls = [
            f"file:{path}?mode=rwc",
            f"file:{path}?vfs=memdb",
            f"file:{tmp_path}/../{tmp_path.name}/vfs.db?vfs=memdb",
        ]
    else:
        urls = [
            f"file:{quote(str(tmp_path / name))}?mode=rwc"
            for name in [
                "rows#one.db",
                "rows#two.db",
                "rows?one.db",
                "user@雪%two.db",
                "encoded\tname.db",
            ]
        ]
    databases = []
    try:
        for index, url in enumerate(urls):
            db = DataFlow(url, test_mode=False, redis_url=private_redis)
            databases.append(db)
            db.config.cache_redis_url = private_redis

            @db.model
            class UriIdentityRow:
                id: str
                value: str

            assert await db.initialize()
            assert isinstance(
                db._cache_integration.cache_manager, AsyncRedisCacheAdapter
            )
            assert isinstance(db.express._cache_manager, AsyncRedisCacheAdapter)
            await db.express.create(
                "UriIdentityRow", {"id": "one", "value": f"owner-{index}"}
            )

        async def read(db):
            if surface == "express":
                return await db.express.list("UriIdentityRow")
            return (await db._nodes["UriIdentityRowListNode"]().execute_async())[
                "records"
            ]

        for index, db in enumerate(databases):
            connection = await db._get_async_database_connection()
            try:
                async with connection.execute(
                    "SELECT value FROM uri_identity_rows"
                ) as cursor:
                    assert await cursor.fetchall() == [(f"owner-{index}",)]
            finally:
                await connection.close()
            assert [row["value"] for row in await read(db)] == [f"owner-{index}"]
            assert [row["value"] for row in await read(db)] == [f"owner-{index}"]
    finally:
        for db in databases:
            await db.close_async()


@pytest.mark.parametrize(
    "uri",
    [
        "file:private?vfs=memdb",
        "file:private?mode=memory",
        "file::memory:",
        "file:%3Amemory%3A",
        "file:",
        "file:?cache=shared",
    ],
)
@pytest.mark.parametrize("surface", ["primary", "replica"])
def test_dataflow_rejects_private_memory_before_allocation(uri, surface, monkeypatch):
    from dataflow.exceptions import DataFlowConfigurationError
    from dataflow.features.express import DataFlowExpress

    connections = [sqlite3.connect(uri, uri=True) for _ in range(2)]
    try:
        for connection, marker in zip(connections, ["one", "two"]):
            connection.execute("CREATE TABLE proof(value TEXT)")
            connection.execute("INSERT INTO proof VALUES (?)", (marker,))
        assert [
            c.execute("SELECT value FROM proof").fetchone()[0] for c in connections
        ] == ["one", "two"]
    finally:
        for connection in connections:
            connection.close()
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("allocation before admission")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(DataFlowExpress, "__init__", forbidden)
    with pytest.raises(
        DataFlowConfigurationError, match="shared across its connections"
    ):
        if surface == "primary":
            DataFlow(uri, test_mode=False)
        else:
            DataFlow(":memory:", read_url=uri, test_mode=False)
    assert calls == []


@pytest.mark.asyncio
async def test_unknown_uri_option_value_cannot_become_another_option(tmp_path):
    from sqlalchemy import create_engine, text

    path = tmp_path / "escaped.db"
    url = f"file:{path}?extension=literal%26mode%3Dmemory%2Btail&mode=rwc"
    canonical = sqlite_sqlalchemy_url(url)
    assert sqlite_sqlalchemy_url(canonical) == canonical
    engine = create_engine(canonical)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA database_list")).first()[2] == str(
                path
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("encoded", ["%FF", "%FE", "%C0%AF"])
def test_malformed_utf8_filename_rejected_before_allocation(
    encoded, tmp_path, monkeypatch
):
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor
    from kailash.utils.sqlite_url import sqlite_cache_identity_url

    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("lossy filename reached driver")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    url = f"file:{tmp_path}/{encoded}.db?mode=rwc"
    with pytest.raises(UnicodeDecodeError):
        SyncDDLExecutor(url)._get_sync_connection()
    with pytest.raises(UnicodeDecodeError):
        sqlite_cache_identity_url(url)
    with pytest.raises(UnicodeDecodeError):
        DataFlow(url, test_mode=False)
    assert calls == []


@pytest.mark.parametrize(
    "suffix", ["mode=memory&%256dode=rwc", "%256dode=rwc&mode=memory"]
)
def test_encoded_duplicate_semantic_keys_fail_closed(suffix, tmp_path):
    from kailash.utils.sqlite_url import (
        sqlite_cache_identity_url,
        sqlite_connection_target,
    )

    url = f"sqlite:///file:{tmp_path}/rows.db?{suffix}"
    for resolve in [
        sqlite_connection_target,
        sqlite_sqlalchemy_url,
        sqlite_cache_identity_url,
    ]:
        with pytest.raises(ValueError, match="Duplicate SQLite option: mode"):
            resolve(url)


@pytest.mark.asyncio
async def test_relative_owners_pin_creation_directory_before_first_operation(
    tmp_path, monkeypatch
):
    roots = [tmp_path / name for name in ["owner-a", "owner-b", "later"]]
    for root in roots:
        root.mkdir()
    databases = []
    try:
        for root in roots[:2]:
            monkeypatch.chdir(root)
            db = DataFlow("sqlite:///rows.db", test_mode=False)
            databases.append(db)

            @db.model
            class DirectoryRow:
                id: str
                value: str

        monkeypatch.chdir(roots[2])
        for index, db in enumerate(databases):
            assert db.config.database.url == "sqlite:///rows.db"
            assert await db.initialize()
            await db.express.create("DirectoryRow", {"id": "one", "value": str(index)})
            assert [
                r["value"]
                for r in (await db._nodes["DirectoryRowListNode"]().execute_async())[
                    "records"
                ]
            ] == [str(index)]
            connection = await db._get_async_database_connection()
            try:
                async with connection.execute("PRAGMA database_list") as cursor:
                    assert (await cursor.fetchone())[2] == str(roots[index] / "rows.db")
            finally:
                await connection.close()
        assert not (roots[2] / "rows.db").exists()
        assert (
            databases[0].express._key_gen.express_db_instance
            != databases[1].express._key_gen.express_db_instance
        )
    finally:
        for db in databases:
            await db.close_async()


@pytest.mark.parametrize("form", ["relative", "shared_encoded", "managed_memory"])
def test_sync_transactions_share_owner_target_and_rollback(form, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    later = tmp_path / "later"
    later.mkdir()
    url = {
        "relative": "sqlite:///rows.db",
        "shared_encoded": "file:%3Amemory%3A?cache=shared",
        "managed_memory": "sqlite:///:memory:",
    }[form]
    db = DataFlow(
        url, test_mode=False, auto_migrate=False, enable_model_persistence=False
    )
    manager = None
    try:
        connection = db._open_sqlite_connection(
            db._memory_db_uri or db._sqlite_database_url
        )
        try:
            connection.execute("CREATE TABLE sync_owner(value TEXT)")
            connection.execute("INSERT INTO sync_owner VALUES ('before')")
            connection.commit()
            monkeypatch.chdir(later)
            manager = db.transactions_sync
            with manager.begin() as tx:
                cursor = tx.execute_raw(
                    "UPDATE sync_owner SET value = ?", ["committed"]
                )
                manager._run_sync(cursor.close())
            assert connection.execute("SELECT value FROM sync_owner").fetchall() == [
                ("committed",)
            ]
            with pytest.raises(RuntimeError, match="rollback marker"):
                with manager.begin() as tx:
                    cursor = tx.execute_raw(
                        "UPDATE sync_owner SET value = ?", ["rolled back"]
                    )
                    manager._run_sync(cursor.close())
                    raise RuntimeError("rollback marker")
            assert connection.execute("SELECT value FROM sync_owner").fetchall() == [
                ("committed",)
            ]
            if form == "relative":
                assert connection.execute("PRAGMA database_list").fetchone()[2] == str(
                    tmp_path / "rows.db"
                )
                assert not (later / "rows.db").exists()
            else:
                assert connection.execute("PRAGMA database_list").fetchone()[2] == ""
        finally:
            connection.close()
    finally:
        if manager is not None:
            manager.close_sync()
        db.close()


@pytest.mark.asyncio
async def test_lightweight_pool_keeps_readonly_native_target_and_owner(
    tmp_path, monkeypatch
):
    from dataflow.core.pool_lightweight import LightweightPool

    monkeypatch.chdir(tmp_path)
    connection = sqlite3.connect("health.db")
    try:
        connection.execute("CREATE TABLE proof(value TEXT)")
        connection.execute("INSERT INTO proof VALUES ('expected')")
        connection.commit()
    finally:
        connection.close()
    pool = LightweightPool("file:health.db?mode=ro")
    later = tmp_path / "later"
    later.mkdir()
    monkeypatch.chdir(later)
    try:
        await pool.initialize()
        assert await pool.execute_raw("SELECT 1 FROM proof") == [(1,)]
        async with pool._pool.execute("PRAGMA database_list") as cursor:
            assert (await cursor.fetchone())[2] == str(tmp_path / "health.db")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            await pool._pool.execute("INSERT INTO proof VALUES ('forbidden')")
        assert not (later / "health.db").exists()
    finally:
        await pool.close()


def test_sync_transaction_native_readonly_does_not_write(tmp_path, caplog):
    path = tmp_path / "readonly.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE proof(value TEXT)")
        connection.execute("INSERT INTO proof VALUES ('kept')")
        connection.commit()
        db = DataFlow(
            f"file:{path}?mode=ro",
            test_mode=False,
            auto_migrate=False,
            enable_model_persistence=False,
        )
        manager = None
        try:
            from dataflow.migrations.schema_state_manager import MigrationHistoryManager

            MigrationHistoryManager(db)
            assert (
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE name='dataflow_migration_history'"
                ).fetchall()
                == []
            )
            assert not [record for record in caplog.records if record.levelno >= 30], [
                record.getMessage() for record in caplog.records
            ]
            manager = db.transactions_sync
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                with manager.begin() as tx:
                    tx.execute_raw("UPDATE proof SET value = 'forbidden'")
            assert connection.execute("SELECT value FROM proof").fetchall() == [
                ("kept",)
            ]
        finally:
            if manager is not None:
                manager.close_sync()
            db.close()
    finally:
        connection.close()


@pytest.mark.parametrize(
    "suffix",
    ["vfs=memdb%00x", "mode=memory%00x&cache=shared", "%6dode%00x=memory&cache=shared"],
)
def test_native_nul_options_rejected_before_allocation(suffix, tmp_path, monkeypatch):
    from kailash.utils.sqlite_url import sqlite_connection_target

    native = f"file:{tmp_path / 'nul.db'}?{suffix}"
    connection = sqlite3.connect(native, uri=True)
    try:
        # The real C parser truncates the decoded NUL and opens memory.
        assert connection.execute("PRAGMA database_list").fetchone()[2] == ""
    finally:
        connection.close()
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("driver reached before NUL validation")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    encoded = "sqlite:///" + native.replace("%", "%25")
    for url in [native, encoded, f"file:{tmp_path / 'path'}%00suffix"]:
        with pytest.raises(ValueError, match="NUL"):
            sqlite_connection_target(url)
        with pytest.raises(ValueError, match="NUL"):
            DataFlow(url, test_mode=False)
    assert calls == []


@pytest.mark.parametrize("character", ["\t", "\r", "\n"])
def test_literal_uri_controls_rejected_before_lossy_url_parsing(
    character, tmp_path, monkeypatch
):
    from kailash.utils.sqlite_url import sqlite_connection_target

    path = tmp_path / f"a{character}b.db"
    native = f"file:{path}"
    connection = sqlite3.connect(native, uri=True)
    try:
        assert connection.execute("PRAGMA database_list").fetchone()[2] == str(path)
    finally:
        connection.close()
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("driver reached before literal control validation")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    for url in [native, "sqlite:///" + native]:
        with pytest.raises(ValueError, match="percent-encode"):
            sqlite_connection_target(url)
        with pytest.raises(ValueError, match="percent-encode"):
            DataFlow(url, test_mode=False)
    assert calls == []


@pytest.mark.parametrize(
    "url", [":memory:", "sqlite://", "sqlite:///", "sqlite+pysqlite:///:memory:"]
)
def test_anonymous_read_replica_rejected_before_allocation(url, monkeypatch):
    from dataflow.exceptions import DataFlowConfigurationError

    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("allocation before replica admission")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    with pytest.raises(
        DataFlowConfigurationError, match="shared across its connections"
    ):
        DataFlow(":memory:", read_url=url, test_mode=False)
    assert calls == []


@pytest.mark.asyncio
async def test_successful_pool_borrow_with_abandoned_transaction_still_warns(
    tmp_path, caplog
):
    from dataflow.adapters.sqlite import SQLiteAdapter

    adapter = SQLiteAdapter(f"sqlite:///{tmp_path / 'abandoned.db'}")
    try:
        await adapter.connect()
        with caplog.at_level(logging.WARNING):
            async with adapter._get_connection() as connection:
                cursor = await connection.execute("BEGIN")
                await cursor.close()
        assert any(
            "Connection released with open transaction - rolling back" == r.getMessage()
            for r in caplog.records
        )
        async with adapter._get_connection() as connection:
            assert not connection.in_transaction
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
async def test_sqlite_database_size_uses_actual_physical_target(
    native, tmp_path, caplog
):
    from dataflow.adapters.sqlite import SQLiteAdapter

    path = tmp_path / "size#proof.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE proof(value TEXT)")
        connection.execute("INSERT INTO proof VALUES ('retained')")
        connection.commit()
    finally:
        connection.close()
    from urllib.parse import quote

    url = f"file:{quote(str(path), safe='/')}?mode=ro" if native else str(path)
    adapter = SQLiteAdapter(url)
    try:
        await adapter.connect()
        assert await adapter.execute_query("SELECT value FROM proof") == [
            {"value": "retained"}
        ]
        size = await adapter.get_database_size()
        assert size >= path.stat().st_size > 0
        assert not [record for record in caplog.records if record.levelno >= 30], [
            record.getMessage() for record in caplog.records
        ]
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_schema_discovery_distinguishes_memory_word_from_memory_target(tmp_path):
    path = tmp_path / "memory_archive.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE proof(id INTEGER PRIMARY KEY, value TEXT)")
        connection.commit()
    finally:
        connection.close()
    file_db = DataFlow(
        f"sqlite:///{path}",
        auto_migrate=False,
        enable_model_persistence=False,
        test_mode=False,
    )
    memory_db = DataFlow(
        "sqlite:///",
        auto_migrate=False,
        enable_model_persistence=False,
        test_mode=False,
    )
    try:
        schema = await file_db.discover_schema_async(use_real_inspection=True)
        assert "proof" in schema
        assert {column["name"] for column in schema["proof"]["columns"]} == {
            "id",
            "value",
        }
        from dataflow.exceptions import EnhancedDataFlowError

        with pytest.raises(EnhancedDataFlowError, match="schema_discovery_memory_db"):
            await memory_db.discover_schema_async(use_real_inspection=True)
    finally:
        await file_db.close_async()
        await memory_db.close_async()
