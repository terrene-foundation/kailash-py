"""Shared address parsing reaches the real Core SQLite producer APIs."""

import sqlite3

import pytest

from kailash.tracking.storage.database import SQLiteStorage


@pytest.mark.parametrize("form", ["two", "three", "four"])
def test_tracking_storage_standard_file_urls(form, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "tracking.db"
    url = {
        "two": "sqlite://tracking.db",
        "three": "sqlite:///tracking.db",
        "four": f"sqlite:///{target}",
    }[form]
    store = SQLiteStorage(url)
    try:
        assert store.conn.execute("PRAGMA database_list").fetchone()[2] == str(target)
        assert store.conn.execute(
            "SELECT name FROM sqlite_master WHERE name='workflow_runs'"
        ).fetchone() == ("workflow_runs",)
    finally:
        store.close()


@pytest.mark.asyncio
async def test_esa_sqlite_allocator_preserves_readonly_uri(tmp_path):
    from kailash.trust.esa.database import DatabaseESA

    path = tmp_path / "esa.db"
    with sqlite3.connect(path) as initial:
        initial.execute("CREATE TABLE proof(value TEXT)")
        initial.execute("INSERT INTO proof VALUES ('retained')")
    initial.close()
    # Exercise the connection producer independently of the trust execution
    # dispatcher; this makes no claim about authorization or query validation.
    esa = DatabaseESA.__new__(DatabaseESA)
    esa.connection_string = f"file:{path}?mode=ro"
    await esa._init_sqlite()
    try:
        async with esa._connection.execute("SELECT value FROM proof") as cursor:
            assert tuple(await cursor.fetchone()) == ("retained",)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            await esa._connection.execute("DELETE FROM proof")
    finally:
        await esa._connection.close()


@pytest.mark.parametrize("form", ["literal", "encoded_mode", "encoded_memory", "memdb"])
def test_sql_node_native_memory_works_across_distinct_live_threads(form, tmp_path):
    import threading
    from uuid import uuid4

    from sqlalchemy import event

    from kailash.nodes.data.sql import SQLDatabaseNode

    name = "thread_" + uuid4().hex
    uri = {
        "literal": f"file:{name}?mode=memory&cache=shared",
        "encoded_mode": f"file:{name}?%6dode=memory&cache=shared",
        "encoded_memory": "file:%3Amemory%3A?cache=shared",
        "memdb": f"file:{tmp_path / name}?vfs=memdb",
    }[form]
    anchor = sqlite3.connect(uri, uri=True)
    anchor.execute("CREATE TABLE thread_proof(value TEXT)")
    anchor.execute("INSERT INTO thread_proof VALUES ('retained')")
    anchor.commit()
    node = SQLDatabaseNode(connection_string=uri)
    ready, finished = threading.Event(), threading.Event()
    state, created = {}, []

    def first():
        state["first_id"] = threading.get_ident()
        try:
            engine = node._get_shared_engine()
            event.listen(
                engine, "connect", lambda connection, record: created.append(connection)
            )
            state["first"] = node.execute(query="SELECT value FROM thread_proof")
        except BaseException as error:
            state["first_error"] = error
        finally:
            ready.set()
        if not finished.wait(30):
            state["timeout"] = True
        try:
            SQLDatabaseNode.dispose_pools_for(uri)
            for connection in created:
                connection.close()
        except BaseException as error:
            state["cleanup_error"] = error

    def second():
        assert (
            ready.is_set()
        ), "Start the borrower only after the owner publishes readiness"
        state["second_id"] = threading.get_ident()
        state["first_alive"] = first_thread.is_alive()
        try:
            state["second"] = node.execute(query="SELECT value FROM thread_proof")
        except BaseException as error:
            state["second_error"] = error
        finally:
            finished.set()

    first_thread, second_thread = threading.Thread(target=first), threading.Thread(
        target=second
    )
    try:
        first_thread.start()
        # Connection setup/imports are not a five-second product deadline.
        # Admit the borrower after setup, while the owner is still alive;
        # retain finite watchdogs so a real deadlock still fails this test.
        assert ready.wait(30), "Owner did not finish SQLite setup"
        second_thread.start()
        first_thread.join(35)
        second_thread.join(35)
        assert not first_thread.is_alive() and not second_thread.is_alive()
        assert not any(
            key.endswith("error") or key == "timeout" for key in state
        ), state
        assert state["first_id"] != state["second_id"] and state["first_alive"]
        assert (
            state["first"]["data"] == state["second"]["data"] == [{"value": "retained"}]
        )
        assert state["first"]["row_count"] == state["second"]["row_count"] == 1
    finally:
        finished.set()
        first_thread.join(35)
        if second_thread.ident is not None:
            second_thread.join(35)
        anchor.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("producer", ["manager", "adapter"])
async def test_core_native_readonly_default_setup_preserves_reads(producer, tmp_path):
    from kailash.db.connection import ConnectionManager
    from kailash.nodes.data.async_sql import DatabaseConfig, DatabaseType, SQLiteAdapter

    path = tmp_path / "readonly.db"
    initial = sqlite3.connect(path)
    try:
        initial.execute("CREATE TABLE proof(value TEXT)")
        initial.execute("INSERT INTO proof VALUES ('retained')")
        initial.commit()
        assert initial.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    finally:
        initial.close()
    uri = f"file:{path}?mode=ro"
    owner = (
        ConnectionManager(uri)
        if producer == "manager"
        else SQLiteAdapter(
            DatabaseConfig(type=DatabaseType.SQLITE, connection_string=uri)
        )
    )
    try:
        if producer == "manager":
            await owner.initialize()
            rows = await owner.fetch("SELECT value FROM proof")
        else:
            await owner.connect()
            rows = await owner.execute("SELECT value FROM proof")
        assert rows == [{"value": "retained"}]
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            await owner.execute("DELETE FROM proof")
        if producer == "manager":
            assert await owner.fetch("SELECT value FROM proof") == rows
        else:
            assert await owner.execute("SELECT value FROM proof") == rows
    finally:
        if producer == "manager":
            await owner.close()
        else:
            await owner.disconnect()
    with sqlite3.connect(path) as inspect:
        assert inspect.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    inspect.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("producer", ["manager", "adapter_get", "adapter_begin"])
@pytest.mark.parametrize("memory", [False, True])
@pytest.mark.parametrize(
    "failure",
    ["error", "cancel", "close_error", "cancel_close_error", "repeated_cancel"],
)
async def test_core_sqlite_setup_failure_closes_unpublished_handle(
    producer, memory, failure, tmp_path, monkeypatch, caplog
):
    import asyncio

    import aiosqlite

    from kailash.db.connection import ConnectionManager
    from kailash.nodes.data.async_sql import DatabaseConfig, DatabaseType, SQLiteAdapter

    uri = ":memory:" if memory else f"file:{tmp_path / 'setup.db'}"
    owner = (
        ConnectionManager(uri)
        if producer == "manager"
        else SQLiteAdapter(
            DatabaseConfig(type=DatabaseType.SQLITE, connection_string=uri)
        )
    )
    setup_error = (
        asyncio.CancelledError("setup cancelled")
        if failure in {"cancel", "cancel_close_error"}
        else RuntimeError("setup failed")
    )
    close_error = RuntimeError("victim@private.example\nforged cleanup record")
    original_execute, original_close = (
        aiosqlite.Connection.execute,
        aiosqlite.Connection.close,
    )
    opened, closed = [], []
    closing, release = asyncio.Event(), asyncio.Event()

    def fail_setup(connection, sql, *args, **kwargs):
        if sql.startswith("PRAGMA"):
            opened.append(connection)
            raise setup_error
        return original_execute(connection, sql, *args, **kwargs)

    async def close(connection):
        if failure == "repeated_cancel":
            closing.set()
            await release.wait()
        await original_close(connection)
        closed.append(connection)
        if failure in {"close_error", "cancel_close_error", "repeated_cancel"}:
            raise close_error

    monkeypatch.setattr(aiosqlite.Connection, "execute", fail_setup)
    monkeypatch.setattr(aiosqlite.Connection, "close", close)

    async def run():
        if producer == "manager":
            await owner.initialize()
        else:
            await owner.connect()
            if producer == "adapter_get":
                await owner._get_connection()
            else:
                await owner.begin_transaction()

    task = asyncio.create_task(run())
    try:
        if failure == "repeated_cancel":
            await asyncio.wait_for(closing.wait(), 2)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            release.set()
        with pytest.raises(BaseException) as caught:
            await task
        if failure == "repeated_cancel":
            assert isinstance(caught.value, asyncio.CancelledError)
            assert caught.value.__cause__ is close_error
        else:
            assert caught.value is setup_error
            if failure in {"close_error", "cancel_close_error"}:
                assert caught.value.__cause__ is close_error
        assert len(opened) == 1 and closed == opened
        records = [
            record
            for record in caplog.records
            if record.name == "kailash.utils.resource_manager"
        ]
        if failure == "repeated_cancel":
            assert len(records) == 1 and "RuntimeError" in records[0].getMessage()
        for record in records:
            assert "victim@private.example" not in str(record.__dict__)
            assert "forged cleanup record" not in record.getMessage()
            assert record.exc_info is None
        assert owner._pool is None
        if producer != "manager":
            assert owner._connection is None
        with pytest.raises(ValueError, match="no active connection"):
            await original_execute(opened[0], "SELECT 1")
    finally:
        release.set()
        if not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass
        for connection in opened:
            await original_close(connection)
        if producer == "manager":
            await owner.close()
        else:
            await owner.disconnect()


@pytest.mark.asyncio
async def test_core_failed_file_begin_releases_owned_connection(tmp_path, monkeypatch):
    import aiosqlite

    from kailash.nodes.data.async_sql import DatabaseConfig, DatabaseType, SQLiteAdapter

    adapter = SQLiteAdapter(
        DatabaseConfig(type=DatabaseType.SQLITE, database=str(tmp_path / "begin.db"))
    )
    original = aiosqlite.Connection.execute
    opened = []
    failure = RuntimeError("BEGIN rejected")

    def execute(connection, sql, *args, **kwargs):
        if sql == "BEGIN IMMEDIATE":
            opened.append(connection)
            raise failure
        return original(connection, sql, *args, **kwargs)

    monkeypatch.setattr(aiosqlite.Connection, "execute", execute)
    await adapter.connect()
    try:
        with pytest.raises(RuntimeError) as caught:
            await adapter.begin_transaction()
        assert caught.value is failure
        assert len(opened) == 1 and adapter._transaction_depth == 0
        with pytest.raises(ValueError, match="no active connection"):
            await original(opened[0], "SELECT 1")
    finally:
        for connection in opened:
            await connection.close()
        await adapter.disconnect()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "form",
    [
        "anonymous",
        "url",
        "driver",
        "encoded_private",
        "encoded_shared",
        "encoded_mode",
        "memdb",
    ],
)
async def test_core_adapter_memory_address_retains_rows(form, tmp_path):
    from uuid import uuid4

    from kailash.nodes.data.async_sql import DatabaseConfig, DatabaseType, SQLiteAdapter

    uri = {
        "anonymous": ":memory:",
        "url": "sqlite:///",
        "driver": "sqlite+pysqlite:///:memory:",
        "encoded_private": "file:%3Amemory%3A",
        "encoded_shared": "file:%3Amemory%3A?cache=shared",
        "encoded_mode": f"file:{uuid4().hex}?%6dode=memory&cache=shared",
        "memdb": f"file:{tmp_path / 'logical-memory'}?vfs=memdb",
    }[form]
    adapter = SQLiteAdapter(
        DatabaseConfig(type=DatabaseType.SQLITE, connection_string=uri)
    )
    try:
        await adapter.connect()
        await adapter.execute("CREATE TABLE proof(value TEXT)")
        await adapter.execute("INSERT INTO proof VALUES ('retained')")
        assert await adapter.execute("SELECT value FROM proof") == [
            {"value": "retained"}
        ]
        assert adapter._connection is not None
    finally:
        await adapter.disconnect()
    assert adapter._connection is None


@pytest.mark.asyncio
async def test_owned_sqlite_close_failure_diagnostic_omits_payload(
    tmp_path, monkeypatch, caplog
):
    import io
    import logging

    import aiosqlite

    from kailash.nodes.data.async_sql import DatabaseConfig, DatabaseType, SQLiteAdapter

    adapter = SQLiteAdapter(
        DatabaseConfig(
            type=DatabaseType.SQLITE, database=str(tmp_path / "diagnostic.db")
        )
    )
    await adapter.connect()
    connection = await adapter._get_connection()
    original_close = connection.close
    error = RuntimeError("victim@private.example\nforged cleanup record")

    async def close_then_fail():
        await original_close()
        raise error

    monkeypatch.setattr(connection, "close", close_then_fail)
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    logger = logging.getLogger("kailash.nodes.data.async_sql")
    logger.addHandler(handler)
    try:
        await adapter._close_quietly(connection)
        assert output.getvalue() == "async_sql.sqlite.close_failed: RuntimeError\n"
        records = [record for record in caplog.records if record.name == logger.name]
        assert len(records) == 1 and records[0].exc_info is None
        assert "victim@private.example" not in str(records[0].__dict__)
        with pytest.raises(ValueError, match="no active connection"):
            await connection.execute("SELECT 1")
    finally:
        logger.removeHandler(handler)
        handler.close()
        await original_close()
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_core_concurrent_cold_memory_queries_have_one_owned_handle(monkeypatch):
    import asyncio

    import aiosqlite

    from kailash.nodes.data.async_sql import DatabaseConfig, DatabaseType, SQLiteAdapter

    original = aiosqlite.connect
    opened = []

    def observe(*args, **kwargs):
        connection = original(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(aiosqlite, "connect", observe)
    adapter = SQLiteAdapter(
        DatabaseConfig(type=DatabaseType.SQLITE, database=":memory:")
    )
    await adapter.connect()
    try:
        results = await asyncio.gather(
            adapter.execute("SELECT 1 AS value"), adapter.execute("SELECT 2 AS value")
        )
        assert results == [[{"value": 1}], [{"value": 2}]]
        assert len(opened) == 1
        await adapter.disconnect()
        for connection in opened:
            with pytest.raises(ValueError, match="no active connection"):
                await connection.execute("SELECT 1")
    finally:
        for connection in opened:
            await connection.close()
        await adapter.disconnect()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["error", "cancel"])
async def test_core_memory_waiter_recovers_after_creator_setup_fails(
    failure, monkeypatch
):
    import asyncio

    import aiosqlite

    from kailash.nodes.data.async_sql import DatabaseConfig, DatabaseType, SQLiteAdapter

    original = aiosqlite.connect
    opened = []

    def observe(*args, **kwargs):
        connection = original(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(aiosqlite, "connect", observe)
    adapter = SQLiteAdapter(
        DatabaseConfig(type=DatabaseType.SQLITE, database=":memory:")
    )
    await adapter.connect()
    configure = adapter._configure_connection
    entered, release = asyncio.Event(), asyncio.Event()
    error = RuntimeError("first setup rejected")
    attempts = 0

    async def first_fails(connection):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            entered.set()
            await release.wait()
            raise error
        await configure(connection)

    monkeypatch.setattr(adapter, "_configure_connection", first_fails)
    first = asyncio.create_task(adapter.execute("SELECT 1 AS value"))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(adapter.execute("SELECT 2 AS value"))
        await asyncio.sleep(0)
        assert not second.done() and len(opened) == 1
        if failure == "cancel":
            first.cancel()
        else:
            release.set()
        with pytest.raises(BaseException) as caught:
            await first
        assert (
            isinstance(caught.value, asyncio.CancelledError)
            if failure == "cancel"
            else caught.value is error
        )
        assert await second == [{"value": 2}]
        assert len(opened) == 2
        with pytest.raises(ValueError, match="no active connection"):
            await opened[0].execute("SELECT 1")
        await adapter.disconnect()
        with pytest.raises(ValueError, match="no active connection"):
            await opened[1].execute("SELECT 1")
    finally:
        release.set()
        for task in [first, second]:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
        for connection in opened:
            await connection.close()
        await adapter.disconnect()


@pytest.mark.asyncio
async def test_cancelled_disconnect_finishes_waiting_for_memory_creator(monkeypatch):
    import asyncio

    from kailash.nodes.data.async_sql import DatabaseConfig, DatabaseType, SQLiteAdapter

    adapter = SQLiteAdapter(
        DatabaseConfig(type=DatabaseType.SQLITE, database=":memory:")
    )
    await adapter.connect()
    entered, release = asyncio.Event(), asyncio.Event()
    configure = adapter._configure_connection
    opened = []

    async def delayed(connection):
        opened.append(connection)
        entered.set()
        await release.wait()
        await configure(connection)

    monkeypatch.setattr(adapter, "_configure_connection", delayed)
    creator = asyncio.create_task(adapter._get_connection())
    closer = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        closer = asyncio.create_task(adapter.disconnect())
        await asyncio.sleep(0)
        assert not closer.done()
        closer.cancel()
        await asyncio.sleep(0)
        closer.cancel()
        await asyncio.sleep(0)
        release.set()
        assert await creator is opened[0]
        with pytest.raises(asyncio.CancelledError):
            await closer
        assert adapter._connection is None and len(opened) == 1
        with pytest.raises(ValueError, match="no active connection"):
            await opened[0].execute("SELECT 1")
    finally:
        release.set()
        for task in [creator, closer]:
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in [creator, closer] if task is not None),
            return_exceptions=True,
        )
        await adapter.disconnect()
        for connection in opened:
            await connection.close()
