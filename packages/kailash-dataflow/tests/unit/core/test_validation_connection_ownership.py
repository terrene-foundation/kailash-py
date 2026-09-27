"""Temporary engine connections close without taking ownership of TDD handles."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
import pytest

from dataflow import DataFlow
from dataflow.core import engine
from dataflow.testing import tdd_support


@pytest.fixture
async def db(monkeypatch, request):
    monkeypatch.delenv("DATAFLOW_TDD_MODE", raising=False)
    database = DataFlow(
        getattr(request, "param", "sqlite:///:memory:"),
        auto_migrate=False,
        test_mode=False,
    )
    try:
        yield database
    finally:
        await database.close_async()


@pytest.mark.parametrize("borrowed", [False, True])
@pytest.mark.parametrize("failure", [False, True])
async def test_scope_closes_only_owned_real_connection(
    db, monkeypatch, borrowed, failure
):
    connection = await aiosqlite.connect(":memory:")
    if borrowed:
        monkeypatch.setenv("DATAFLOW_TDD_MODE", "true")
        monkeypatch.setattr(
            tdd_support, "_current_test_context", SimpleNamespace(connection=connection)
        )
    else:
        monkeypatch.setattr(aiosqlite, "connect", AsyncMock(return_value=connection))
    error = RuntimeError("scope body failed")
    try:
        if failure:
            with pytest.raises(RuntimeError) as raised:
                async with db._async_database_connection_scope() as acquired:
                    assert acquired is connection
                    raise error
            assert raised.value is error
        else:
            async with db._async_database_connection_scope() as acquired:
                assert acquired is connection
                async with acquired.execute("SELECT 1") as cursor:
                    assert await cursor.fetchone() == (1,)
        if borrowed:
            async with connection.execute("SELECT 2") as cursor:
                assert await cursor.fetchone() == (2,)
        else:
            with pytest.raises(ValueError, match="no active connection"):
                await connection.execute("SELECT 2")
    finally:
        await connection.close()


@pytest.mark.parametrize("lazy", [False, True])
@pytest.mark.parametrize(
    "db", ["postgresql://ownership@localhost:5432/ownership"], indirect=True
)
async def test_validation_keeps_tdd_manager_connection(db, monkeypatch, lazy):
    connection = await aiosqlite.connect(":memory:")
    context = SimpleNamespace(connection=None if lazy else connection)
    manager = SimpleNamespace(get_test_connection=AsyncMock(return_value=connection))
    monkeypatch.setenv("DATAFLOW_TDD_MODE", "true")
    monkeypatch.setattr(tdd_support, "_current_test_context", context)
    monkeypatch.setattr(tdd_support, "get_database_manager", lambda: manager)
    try:
        assert await db._validate_database_connection() is True
        async with connection.execute("SELECT 3") as cursor:
            assert await cursor.fetchone() == (3,)
        assert manager.get_test_connection.await_count == int(lazy)
    finally:
        await connection.close()


@pytest.mark.parametrize(
    "db", ["postgresql://ownership@localhost:5432/ownership"], indirect=True
)
async def test_validation_closes_new_postgresql_handle(db, monkeypatch):
    connection = SimpleNamespace(close=AsyncMock())
    opener = AsyncMock(return_value=connection)
    monkeypatch.setattr(engine, "open_credentialed_connection", opener)
    assert await db._validate_database_connection() is True
    opener.assert_awaited_once()
    connection.close.assert_awaited_once()


@pytest.mark.parametrize("borrowed", [False, True])
@pytest.mark.parametrize("cancelled", [False, True])
async def test_table_cleanup_preserves_cancel_and_connection_owner(
    db, monkeypatch, borrowed, cancelled
):
    error = asyncio.CancelledError("cleanup cancelled")
    connection = SimpleNamespace(
        fetch=AsyncMock(side_effect=error if cancelled else None, return_value=[]),
        close=AsyncMock(),
    )
    monkeypatch.setattr(
        db,
        "_acquire_async_database_connection",
        AsyncMock(return_value=(connection, borrowed)),
    )
    monkeypatch.setattr(
        db, "_get_async_database_connection", AsyncMock(return_value=connection)
    )
    if cancelled:
        with pytest.raises(asyncio.CancelledError) as raised:
            await db.cleanup_test_tables()
        assert raised.value is error
        connection.fetch.assert_awaited_once()
    else:
        await db.cleanup_test_tables()
        assert connection.fetch.await_count == 6
    assert connection.close.await_count == int(not borrowed)


async def test_repeated_cancellation_finishes_owned_close(db, monkeypatch):
    started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def close():
        started.set()
        await release.wait()
        finished.set()

    connection = SimpleNamespace(close=close)
    monkeypatch.setattr(
        db,
        "_acquire_async_database_connection",
        AsyncMock(return_value=(connection, False)),
    )

    async def drive():
        async with db._async_database_connection_scope():
            pass

    task = asyncio.create_task(drive())
    await started.wait()
    try:
        task.cancel("first")
        await asyncio.sleep(0)
        task.cancel("second")
        await asyncio.sleep(0)
        assert not task.done()
        assert not finished.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_scope_propagates_owned_close_failure(db, monkeypatch):
    error = RuntimeError("close failed")
    connection = SimpleNamespace(close=AsyncMock(side_effect=error))
    monkeypatch.setattr(
        db,
        "_acquire_async_database_connection",
        AsyncMock(return_value=(connection, False)),
    )
    with pytest.raises(RuntimeError) as raised:
        async with db._async_database_connection_scope():
            pass
    assert raised.value is error
    connection.close.assert_awaited_once()


async def test_connection_only_wrapper_leaves_lifecycle_to_caller(db, monkeypatch):
    connection = await aiosqlite.connect(":memory:")
    monkeypatch.setattr(aiosqlite, "connect", AsyncMock(return_value=connection))
    try:
        acquired = await db._get_async_database_connection()
        assert acquired is connection
        async with acquired.execute("SELECT 4") as cursor:
            assert await cursor.fetchone() == (4,)
    finally:
        await connection.close()


@pytest.mark.parametrize(
    "body_cancel, new_cancels, entrypoint",
    [
        (True, 0, "scope"),
        (True, 2, "scope"),
        (False, 1, "scope"),
        (False, 2, "scope"),
        (False, 1, "validation"),
        (False, 2, "validation"),
    ],
)
@pytest.mark.parametrize(
    "db", ["postgresql://ownership@localhost:5432/ownership"], indirect=True
)
async def test_cancel_wins_over_owned_close_failure(
    db, monkeypatch, body_cancel, new_cancels, entrypoint
):
    connection = await aiosqlite.connect(":memory:")
    original_close = connection.close
    started, release = asyncio.Event(), asyncio.Event()
    close_error = RuntimeError("owned close failed after disposal")
    body_error = asyncio.CancelledError("body cancelled")

    async def close():
        started.set()
        await release.wait()
        await original_close()
        raise close_error

    monkeypatch.setattr(connection, "close", close)
    monkeypatch.setattr(
        db,
        "_acquire_async_database_connection",
        AsyncMock(return_value=(connection, False)),
    )

    async def drive():
        if entrypoint == "validation":
            return await db._validate_database_connection()
        async with db._async_database_connection_scope():
            if body_cancel:
                raise body_error

    task = asyncio.create_task(drive())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        for _ in range(new_cancels):
            task.cancel("caller cancelled")
            await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError) as raised:
            await task
        assert task.cancelled()
        assert raised.value.__cause__ is close_error
        if body_cancel and not new_cancels:
            assert raised.value is body_error
        with pytest.raises(ValueError, match="no active connection"):
            await connection.execute("SELECT 1")
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await original_close()
