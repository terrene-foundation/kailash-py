"""Real SQLite savepoints retain one outer connection and lifecycle owner."""

import asyncio
import sqlite3
import threading

import pytest

from kailash.nodes.data.async_sql import (
    DatabaseConfig,
    DatabaseType,
    ProductionSQLiteAdapter,
    SQLiteAdapter,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(params=[False, True], ids=["file", "memory"])
async def adapter(request, tmp_path):
    owner = SQLiteAdapter(
        DatabaseConfig(
            type=DatabaseType.SQLITE,
            database=":memory:" if request.param else str(tmp_path / "nested.db"),
        )
    )
    await owner.connect()
    await owner.execute("CREATE TABLE proof(value INTEGER)")
    try:
        yield owner
    finally:
        await owner.disconnect()


async def values(adapter, transaction=None):
    return await adapter.execute(
        "SELECT value FROM proof ORDER BY value", transaction=transaction
    )


async def test_nested_rollback_preserves_outer_and_one_owner(adapter):
    async with adapter.transaction() as outer:
        await adapter.execute(
            "INSERT INTO proof VALUES (?)", (1,), transaction=outer.transaction
        )
        with pytest.raises(ValueError, match="inner body"):
            async with adapter.transaction() as inner:
                assert inner.connection is outer.connection
                await adapter.execute_many(
                    "INSERT INTO proof VALUES (?)",
                    [(2,), (3,)],
                    transaction=inner.transaction,
                )
                raise ValueError("inner body")
        assert await values(adapter, outer.transaction) == [{"value": 1}]
        async with adapter.transaction() as inner:
            assert inner.connection is outer.connection
            await adapter.execute(
                "INSERT INTO proof VALUES (?)", (4,), transaction=inner.transaction
            )
    assert await values(adapter) == [{"value": 1}, {"value": 4}]
    assert adapter._transaction_depth == 0
    assert adapter._transaction_connection is None
    assert adapter._transaction_owner is None
    if adapter._is_memory_db:
        async with adapter.transaction() as next_scope:
            assert next_scope.connection is outer.connection
    else:
        with pytest.raises(ValueError, match="no active connection"):
            await outer.connection.execute("SELECT 1")


async def test_outer_rollback_discards_committed_savepoints(adapter):
    with pytest.raises(ValueError, match="outer body"):
        async with adapter.transaction() as outer:
            async with adapter.transaction() as inner:
                async with adapter.transaction() as deepest:
                    assert deepest.connection is inner.connection is outer.connection
                    await adapter.execute(
                        "INSERT INTO proof VALUES (1)", transaction=deepest.transaction
                    )
            raise ValueError("outer body")
    assert await values(adapter) == []
    assert adapter._transaction_depth == 0


@pytest.mark.parametrize("finish", ["commit", "rollback"])
async def test_foreign_implicit_begin_rejected_explicit_capability_handoff_allowed(
    adapter, finish
):
    async with adapter.transaction() as outer:

        async def borrower():
            with pytest.raises(RuntimeError, match="another task"):
                await adapter.begin_transaction()
            await adapter.execute(
                "INSERT INTO proof VALUES (1)", transaction=outer.transaction
            )
            await getattr(outer, finish)()

        await asyncio.create_task(borrower())
        assert adapter._transaction_depth == 0
        assert outer._committed if finish == "commit" else outer._rolled_back
    assert await values(adapter) == ([{"value": 1}] if finish == "commit" else [])


async def test_out_of_order_and_replayed_handle_cannot_consume_scope(adapter):
    async with adapter.transaction() as outer:
        async with adapter.transaction() as inner:
            with pytest.raises(RuntimeError, match="nested"):
                await outer.commit()
            with pytest.raises(RuntimeError, match="nested"):
                await adapter.rollback_transaction(outer.connection)
            assert not outer._committed
        with pytest.raises(RuntimeError, match="not active"):
            await adapter.commit_transaction(inner.transaction)
        await adapter.execute(
            "INSERT INTO proof VALUES (1)", transaction=outer.transaction
        )
    with pytest.raises(RuntimeError, match="no longer active"):
        await adapter.rollback_transaction(outer.transaction)
    assert await values(adapter) == [{"value": 1}]


async def test_legacy_connection_terminal_clears_pinned_owner(adapter):
    txn = await adapter.begin_transaction()
    await adapter.execute("INSERT INTO proof VALUES (1)", transaction=txn[0])
    await adapter.commit_transaction(txn[0])
    assert adapter._transaction_depth == 0
    assert adapter._transaction_owner is None
    async with adapter.transaction() as scope:
        await adapter.execute(
            "INSERT INTO proof VALUES (2)", transaction=scope.transaction
        )
    assert await values(adapter) == [{"value": 1}, {"value": 2}]


async def test_real_cancel_after_savepoint_execution_retains_outer(adapter):
    entered, release = threading.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    observations = []

    async def owner():
        async with adapter.transaction() as outer:
            await adapter.execute(
                "INSERT INTO proof VALUES (1)", transaction=outer.transaction
            )

            def trace(statement):
                if statement.startswith("SAVEPOINT "):
                    entered.set()
                    assert release.wait(5)

            await outer.connection.set_trace_callback(trace)
            try:
                await adapter.begin_transaction()
            except asyncio.CancelledError:
                observations.append("cancelled")
            finally:
                await outer.connection.set_trace_callback(None)
            assert adapter._transaction_depth == 1
            assert adapter._transaction_connection is outer.connection
            assert await values(adapter, outer.transaction) == [{"value": 1}]
            async with adapter.transaction() as retry:
                assert retry.connection is outer.connection

    task = loop.create_task(owner())
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert observations == ["cancelled"]
    assert await values(adapter) == [{"value": 1}]


async def test_commit_constraint_failure_cleans_owner_and_allows_retry(adapter):
    await adapter.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
    await adapter.execute(
        "CREATE TABLE child(id INTEGER REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED)"
    )
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        async with adapter.transaction() as scope:
            await adapter.execute(
                "INSERT INTO child VALUES (1)", transaction=scope.transaction
            )
    assert adapter._transaction_depth == 0
    assert adapter._transaction_owner is None
    async with adapter.transaction() as scope:
        await adapter.execute(
            "INSERT INTO parent VALUES (1)", transaction=scope.transaction
        )
    assert await adapter.execute("SELECT * FROM child") == []


async def test_disconnect_closes_abandoned_transaction_owner(adapter):
    txn = await adapter.begin_transaction()
    await adapter.execute("INSERT INTO proof VALUES (1)", transaction=txn)
    await adapter.disconnect()
    assert adapter._transaction_depth == 0
    assert adapter._transaction_connection is None
    assert adapter._transaction_owner is None
    with pytest.raises(ValueError, match="no active connection"):
        await txn[0].execute("SELECT 1")


async def test_production_adapter_inherits_pinned_file_transactions(tmp_path):
    owner = ProductionSQLiteAdapter(
        DatabaseConfig(
            type=DatabaseType.SQLITE, database=str(tmp_path / "production.db")
        )
    )
    await owner.connect()
    try:
        await owner.execute("CREATE TABLE proof(value INTEGER)")
        async with owner.transaction() as outer:
            async with owner.transaction() as inner:
                assert inner.connection is outer.connection
                await owner.execute(
                    "INSERT INTO proof VALUES (1)", transaction=inner.transaction
                )
        assert await values(owner) == [{"value": 1}]
    finally:
        await owner.disconnect()


@pytest.mark.parametrize("adapter", [True], indirect=True)
@pytest.mark.parametrize("operation", ["execute", "many", "stream"])
async def test_unscoped_memory_operations_cannot_commit_outer(adapter, operation):
    async with adapter.transaction() as outer:
        await adapter.execute(
            "INSERT INTO proof VALUES (1)", transaction=outer.transaction
        )

        async def unscoped():
            with pytest.raises(RuntimeError, match="transaction handle"):
                if operation == "execute":
                    await adapter.execute("SELECT * FROM proof")
                elif operation == "many":
                    await adapter.execute_many("INSERT INTO proof VALUES (?)", [(2,)])
                else:
                    async with adapter.stream("SELECT * FROM proof"):
                        pytest.fail("borrowed uncommitted memory rows without a handle")

        await asyncio.create_task(unscoped())
        await outer.rollback()
    assert await values(adapter) == []


@pytest.mark.parametrize("adapter", [True], indirect=True)
async def test_memory_stream_serializes_new_transaction_and_rejects_reentry(adapter):
    admitted = asyncio.Event()

    async def owner():
        async with adapter.transaction() as scope:
            admitted.set()
            await adapter.execute(
                "INSERT INTO proof VALUES (1)", transaction=scope.transaction
            )

    async with adapter.stream("SELECT * FROM proof") as rows:
        assert [row async for row in rows] == []
        with pytest.raises(RuntimeError, match="shared-memory operation"):
            await adapter.begin_transaction()
        with pytest.raises(RuntimeError, match="shared-memory operation"):
            await adapter.disconnect()
        task = asyncio.create_task(owner())
        await asyncio.sleep(0)
        assert not admitted.is_set()
    await task
    assert admitted.is_set()
    assert await values(adapter) == [{"value": 1}]


async def test_repeated_cancellation_during_real_rollback_finishes_cleanup(adapter):
    entered, release = threading.Event(), threading.Event()

    async def owner():
        async with adapter.transaction() as scope:
            await adapter.execute(
                "INSERT INTO proof VALUES (1)", transaction=scope.transaction
            )

            def trace(statement):
                if statement == "ROLLBACK":
                    entered.set()
                    assert release.wait(5)

            await scope.connection.set_trace_callback(trace)
            raise ValueError("rollback body")

    task = asyncio.create_task(owner())
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert adapter._transaction_depth == 0
    assert adapter._transaction_owner is None
    assert adapter._transaction_connection is None
    assert await values(adapter) == []


@pytest.mark.parametrize("finish", ["commit", "rollback"])
@pytest.mark.parametrize("cancel_waiter", [False, True], ids=["reject", "cancel"])
async def test_waiting_scope_completion_does_not_consume_before_admission(
    adapter, finish, cancel_waiter
):
    loop = asyncio.get_running_loop()
    entered, waiting = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    async with adapter.transaction() as outer:
        await adapter.execute(
            "INSERT INTO proof VALUES (1)", transaction=outer.transaction
        )

        def trace(statement):
            if statement.startswith("SAVEPOINT "):
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(5)

        await outer.connection.set_trace_callback(trace)

        async def complete():
            await entered.wait()
            waiting.set()
            await getattr(outer, finish)()

        completion = asyncio.create_task(complete())

        async def unblock():
            await waiting.wait()
            # complete() reaches the held lifecycle lock before yielding.
            await asyncio.sleep(0)
            if cancel_waiter:
                completion.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await completion
            release.set()

        unblocking = asyncio.create_task(unblock())
        try:
            inner = await adapter.begin_transaction()
            await unblocking
            if not cancel_waiter:
                with pytest.raises(RuntimeError, match="nested"):
                    await completion
            assert not outer._committed and not outer._rolled_back
            assert adapter._transaction_depth == 2
            await adapter.rollback_transaction(inner)
            assert await values(adapter, outer.transaction) == [{"value": 1}]
        finally:
            release.set()
            await outer.connection.set_trace_callback(None)
            for task in (completion, unblocking):
                if not task.done():
                    task.cancel()
            await asyncio.gather(completion, unblocking, return_exceptions=True)
    assert await values(adapter) == [{"value": 1}]
    assert adapter._transaction_depth == 0
