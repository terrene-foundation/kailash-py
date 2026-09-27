"""AsyncNode owns and drains transient loops; caller loops remain borrowed."""

import asyncio
import concurrent.futures
import logging
import threading

import pytest

from kailash.nodes.base_async import AsyncNode
from kailash.nodes.data import async_sql
from kailash.utils import loop_pool_registry


class ResourceNode(AsyncNode):
    def get_parameters(self):
        return {}

    async def execute_async(self, **inputs):
        self.calls += 1
        self.loop = asyncio.get_running_loop()

        async def background():
            try:
                await asyncio.Event().wait()
            finally:
                self.events.append("task_finished")

        async def stream():
            try:
                yield 1
            finally:
                self.events.append("generator_finished")

        self.task = asyncio.create_task(background())
        self.generator = stream()
        assert await anext(self.generator) == 1
        await asyncio.sleep(0)

        def work():
            assert self.release_worker.wait(3)
            self.events.append("executor_finished")

        self.future = self.loop.run_in_executor(None, work)

        async def broken_drain():
            self.events.append("broken_drain")
            raise ValueError("deliberate cleanup failure")

        async def drain():
            assert asyncio.get_running_loop() is self.loop
            assert not self.loop.is_closed()
            self.events.append("drained")
            self.release_worker.set()

        loop_pool_registry.register_pool_drain_on_current_loop(broken_drain)
        loop_pool_registry.register_pool_drain_on_current_loop(drain)
        if self.failure is not None:
            raise self.failure
        return {"result": "completed"}


def _resource_node(fails):
    node = ResourceNode()
    node.calls = 0
    node.events = []
    node.release_worker = threading.Event()
    node.failure = RuntimeError("original node failure") if fails else None
    return node


def _invoke(node, context):
    if context == "main":
        return node.execute()
    if context == "worker":
        with concurrent.futures.ThreadPoolExecutor() as executor:
            return executor.submit(node.execute).result()

    async def caller():
        loop = asyncio.get_running_loop()
        survivor = asyncio.create_task(asyncio.sleep(0, result="caller alive"))
        try:
            return node.execute()
        finally:
            assert not loop.is_closed()
            assert await survivor == "caller alive"
            assert asyncio.get_running_loop() is loop

    return asyncio.run(caller())


@pytest.mark.parametrize("context", ["main", "worker", "running_loop"])
@pytest.mark.parametrize("fails", [False, True])
def test_owned_loop_drains_every_resource_and_preserves_original_error(
    context, fails, caplog
):
    node = _resource_node(fails)
    if fails:
        with pytest.raises(RuntimeError) as error:
            _invoke(node, context)
        assert error.value is node.failure
    else:
        assert _invoke(node, context) == {"result": "completed"}
    assert node.calls == 1
    assert node.loop.is_closed()
    assert node.task.done()
    assert sorted(node.events) == [
        "broken_drain",
        "drained",
        "executor_finished",
        "generator_finished",
        "task_finished",
    ]
    assert id(node.loop) not in loop_pool_registry._registry
    assert not [
        record for record in caplog.records if record.levelno >= logging.WARNING
    ]


@pytest.mark.parametrize("context", ["main", "worker", "running_loop"])
def test_real_sqlite_owned_pool_is_drained_before_loop_close(context, tmp_path, caplog):
    node = async_sql.AsyncSQLDatabaseNode(
        database_type="sqlite",
        connection_string=str(tmp_path / "owned.db"),
        query="SELECT 7 AS value",
    )
    try:
        result = _invoke(node, context)
        assert result["result"]["data"] == [{"value": 7}]
        assert node._pool_loop.is_closed()
        assert node._adapter._enterprise_pool is None
        assert node._adapter not in async_sql._PROCESS_POOL_REGISTRY.values()
        assert not asyncio.all_tasks(node._pool_loop)
        assert id(node._pool_loop) not in loop_pool_registry._registry
        assert not [
            record for record in caplog.records if record.levelno >= logging.WARNING
        ]
    finally:
        asyncio.run(node.cleanup())


def test_persistent_caller_pool_is_not_registered_or_drained(tmp_path):
    async def caller():
        node = async_sql.AsyncSQLDatabaseNode(
            database_type="sqlite",
            connection_string=str(tmp_path / "caller.db"),
            query="SELECT 3 AS value",
        )
        try:
            result = await node.execute_async()
            assert result["result"]["data"] == [{"value": 3}]
            pool = node._adapter._enterprise_pool
            assert pool is not None
            loop = asyncio.get_running_loop()
            assert id(loop) not in loop_pool_registry._registry
            assert _invoke(_resource_node(False), "main") == {"result": "completed"}
            assert node._adapter._enterprise_pool is pool
            assert not loop.is_closed()
            assert (await node.execute_async())["result"]["data"] == [{"value": 3}]
        finally:
            await node.cleanup()

    asyncio.run(caller())


@pytest.mark.parametrize("dialect", ["postgresql", "mysql"])
def test_existing_driver_drain_and_owned_registration_are_idempotent(
    dialect, monkeypatch
):
    # Tier 1 driver protocol stand-ins; real adapter connect/disconnect and
    # registry methods execute. This does not claim live PG/MySQL coverage.
    import sys
    import types

    class DriverPool:
        calls = 0

        async def pg_close(self):
            self.calls += 1

        def mysql_close(self):
            self.calls += 1

        async def wait_closed(self):
            return None

    pool = DriverPool()
    pool.close = pool.pg_close if dialect == "postgresql" else pool.mysql_close

    async def create_pool(*args, **kwargs):
        return pool

    monkeypatch.setitem(
        sys.modules,
        "asyncpg" if dialect == "postgresql" else "aiomysql",
        types.SimpleNamespace(create_pool=create_pool),
    )
    adapter_class = (
        async_sql.PostgreSQLAdapter
        if dialect == "postgresql"
        else async_sql.MySQLAdapter
    )
    adapter = adapter_class(
        async_sql.DatabaseConfig(
            type=async_sql.DatabaseType(dialect),
            host="localhost",
            database="owner_test",
        )
    )

    class AdapterNode(AsyncNode):
        def get_parameters(self):
            return {}

        async def execute_async(self):
            await adapter.connect()
            async_sql._register_pool("owner-test-" + dialect, adapter)
            assert (
                len(loop_pool_registry._registry[id(asyncio.get_running_loop())]) == 2
            )
            return {"connected": True}

    assert AdapterNode().execute() == {"connected": True}
    assert pool.calls == 1
    assert adapter not in async_sql._PROCESS_POOL_REGISTRY.values()


def test_external_sqlite_connection_is_borrowed_across_transient_bridge(tmp_path):
    import aiosqlite

    async def caller():
        async with aiosqlite.connect(tmp_path / "external.db") as connection:
            sql_node = async_sql.AsyncSQLDatabaseNode(
                database_type="sqlite",
                external_pool=connection,
                query="SELECT 9 AS value",
            )

            class Borrower(AsyncNode):
                def get_parameters(self):
                    return {}

                async def execute_async(self):
                    adapter = await sql_node._get_adapter()
                    assert adapter._pool is connection
                    assert adapter not in async_sql._PROCESS_POOL_REGISTRY.values()
                    assert (
                        id(asyncio.get_running_loop())
                        not in loop_pool_registry._registry
                    )
                    return {"borrowed": True}

            try:
                assert Borrower().execute() == {"borrowed": True}
                async with connection.execute("SELECT 9 AS value") as cursor:
                    assert await cursor.fetchall() == [(9,)]
            finally:
                await sql_node.cleanup()
            async with connection.execute("SELECT 11 AS value") as cursor:
                assert await cursor.fetchall() == [(11,)]

    asyncio.run(caller())


@pytest.mark.parametrize("context", ["main", "worker", "running_loop"])
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
def test_cancelled_drain_preserves_original_error_and_later_cleanup(context, failure):
    events = []

    class CancelledDrainNode(AsyncNode):
        def get_parameters(self):
            return {}

        async def execute_async(self):
            self.loop = asyncio.get_running_loop()

            async def cancelled():
                events.append("cancelled")
                asyncio.current_task().cancel("callback cancellation")
                await asyncio.sleep(0)

            async def later():
                events.append("later")

            loop_pool_registry.register_pool_drain_on_current_loop(cancelled)
            loop_pool_registry.register_pool_drain_on_current_loop(later)
            try:
                if failure is asyncio.CancelledError:
                    asyncio.current_task().cancel("original caller cancellation")
                    await asyncio.sleep(0)
                raise RuntimeError("original node failure")
            except BaseException as error:
                self.original = error
                self.cancel_count = asyncio.current_task().cancelling()
                raise

    node = CancelledDrainNode()
    with pytest.raises(failure) as caught:
        _invoke(node, context)
    assert caught.value is node.original
    assert node.cancel_count == (1 if failure is asyncio.CancelledError else 0)
    assert events == ["cancelled", "later"]
    assert node.loop.is_closed()
    assert not asyncio.all_tasks(node.loop)
    assert id(node.loop) not in loop_pool_registry._registry


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_before_start", [False, True])
async def test_caller_cancellation_waits_for_owned_drains_and_still_propagates(
    cancel_before_start,
):
    events = []
    started = asyncio.Event()
    release = asyncio.Event()
    owned_tasks = []

    async def blocked():
        owned_tasks.append(asyncio.current_task())
        started.set()
        await release.wait()
        events.append("blocked finished")

    async def later():
        events.append("later")

    async def owner():
        loop = asyncio.get_running_loop()
        # This test owns only these registry entries, not the pytest loop.
        with loop_pool_registry._registry_lock:
            assert id(loop) not in loop_pool_registry._registry
            loop_pool_registry._registry[id(loop)] = [blocked, later]
        if cancel_before_start:
            asyncio.current_task().cancel("caller cancellation")
        await loop_pool_registry.drain_loop_pools(loop)
        raise AssertionError("caller cancellation was swallowed")

    task = asyncio.create_task(owner())
    try:
        await asyncio.wait_for(started.wait(), 2)
        if not cancel_before_start:
            task.cancel("caller cancellation")
        await asyncio.sleep(0)
        assert not task.done()
        assert not owned_tasks[0].cancelled()
        release.set()
        with pytest.raises(asyncio.CancelledError, match="caller cancellation"):
            await task
        assert events == ["blocked finished", "later"]
        assert all(item.done() for item in owned_tasks)
        assert id(asyncio.get_running_loop()) not in loop_pool_registry._registry
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_hostile_drain_exception_type_cannot_forge_log_records(monkeypatch):
    import io
    import json

    stream = io.StringIO()
    records = []
    events = []
    hostile = type("Injected\nERROR counterfeit", (Exception,), {})

    class Capture(logging.StreamHandler):
        def emit(self, record):
            if record.msg == "loop_pool_registry.drain.error":
                records.append(dict(record.__dict__))
                super().emit(record)

    async def failed():
        events.append("failed")
        raise hostile("drain-person@example.invalid")

    async def later():
        events.append("later")

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, loop_pool_registry.BRIDGE_LOOP_ATTR, True, raising=False)
    logger = loop_pool_registry.logger
    handler = Capture(stream)
    handler.setFormatter(logging.Formatter("%(message)s %(error_type)s"))
    previous = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        loop_pool_registry.register_pool_drain_on_current_loop(failed)
        loop_pool_registry.register_pool_drain_on_current_loop(later)
        await loop_pool_registry.drain_loop_pools(loop)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
    assert events == ["failed", "later"]
    assert id(loop) not in loop_pool_registry._registry
    assert len(records) == 1
    assert records[0]["error_type"] == "Injected?ERROR?counterfeit"
    assert records[0]["exc_info"] is None
    assert len(stream.getvalue().splitlines()) == 1
    assert "drain-person@example.invalid" not in json.dumps(records, default=str)
    assert "drain-person@example.invalid" not in stream.getvalue()
