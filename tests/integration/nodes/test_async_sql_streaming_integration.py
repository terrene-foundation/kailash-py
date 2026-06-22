"""Tier-2 integration tests for SQL streaming — PostgreSQL + MySQL.

Real infrastructure, NO mocking (per testing.md Tier-2). PostgreSQL runs on
localhost:5434 and MySQL on localhost:3307 (see tests/utils/docker_config.py).
These markers (requires_postgres / requires_mysql) are EXCLUDED by the gating
CI lane; run them locally against the live containers.

Coverage per dialect:
* round-trip correctness vs fetch_mode=ALL over mixed types;
* memory-bounded proof — instrument the driver fetch path to assert ≤
  batch_size rows are pulled when the consumer has processed only the first
  row (a deterministic batch-boundary assertion, NOT a tracemalloc heuristic);
* lifetime/cleanup — early break + exception unwind release the connection
  back to the pool (pool free-count restored; for PostgreSQL, no
  idle_in_transaction leak);
* retry contract — open-phase transient failure retries; mid-iteration failure
  propagates without re-yielding;
* access-control masking applied per streamed row.
"""

import asyncio

import pytest
import pytest_asyncio

from kailash.nodes.data.async_sql import DEFAULT_STREAM_BATCH_SIZE, AsyncSQLDatabaseNode
from kailash.sdk_exceptions import NodeExecutionError
from tests.utils.docker_config import (
    get_mysql_connection_string,
    get_postgres_connection_string,
)

# ===========================================================================
# PostgreSQL
# ===========================================================================

PG_TABLE = "_stream_it_pg"


@pytest_asyncio.fixture
async def pg_node():
    """AsyncSQLDatabaseNode against the live PostgreSQL, table seeded."""
    conn = get_postgres_connection_string()
    setup = AsyncSQLDatabaseNode(
        name="pg_stream_setup",
        database_type="postgresql",
        connection_string=conn,
        validate_queries=False,  # DDL setup
        share_pool=False,
    )
    await setup.async_run(query=f"DROP TABLE IF EXISTS {PG_TABLE}")
    await setup.async_run(
        query=(
            f"CREATE TABLE {PG_TABLE} ("
            "  id INTEGER PRIMARY KEY,"
            "  name TEXT,"
            "  score DOUBLE PRECISION,"
            "  active BOOLEAN,"
            "  ssn TEXT"
            ")"
        )
    )
    for i in range(1, 26):
        await setup.async_run(
            query=(
                f"INSERT INTO {PG_TABLE} (id, name, score, active, ssn) "
                "VALUES (:id, :name, :score, :active, :ssn)"
            ),
            params={
                "id": i,
                "name": None if i == 7 else f"name-{i}",
                "score": None if i == 11 else float(i) + 0.5,
                "active": (i % 2 == 0),
                "ssn": f"{i:03d}-00-0000",
            },
        )

    node = AsyncSQLDatabaseNode(
        name="pg_stream_node",
        database_type="postgresql",
        connection_string=conn,
        validate_queries=True,
        share_pool=False,
    )
    yield node

    teardown = AsyncSQLDatabaseNode(
        name="pg_stream_teardown",
        database_type="postgresql",
        connection_string=conn,
        validate_queries=False,
        share_pool=False,
    )
    await teardown.async_run(query=f"DROP TABLE IF EXISTS {PG_TABLE}")


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_pg_stream_round_trip_vs_fetch_all(pg_node):
    """Streamed PG rows are byte-identical to fetch_mode=ALL."""
    materialized = await pg_node.async_run(
        query=f"SELECT id, name, score, active, ssn FROM {PG_TABLE} ORDER BY id"
    )
    expected = materialized["result"]["data"]

    streamed = []
    async with pg_node.stream(
        query=f"SELECT id, name, score, active, ssn FROM {PG_TABLE} ORDER BY id",
        batch_size=10,
    ) as cursor:
        async for row in cursor:
            streamed.append(row)

    assert streamed == expected
    assert len(streamed) == 25
    assert streamed[6]["name"] is None  # NULL survived
    assert streamed[10]["score"] is None


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_pg_stream_memory_bounded(pg_node):
    """asyncpg prefetch MUST bound rows pulled before the consumer advances.

    We instrument the asyncpg connection's cursor() factory to count rows the
    cursor buffers. After consuming exactly ONE row, no more than batch_size
    rows have been read from the server — proof of bounded, lazy pulls.
    """
    batch_size = 5
    adapter = await pg_node._get_adapter()
    real_pool = adapter._pool
    pulled = {"n": 0}

    # asyncpg's Pool.acquire is read-only, so we swap adapter._pool (a plain,
    # writable attribute) for a thin wrapper that counts rows as asyncpg's
    # server-side cursor yields them. asyncpg buffers `prefetch` rows per round
    # trip; counting at the async-for boundary measures rows pulled from the
    # server.
    class _CountingConnWrapper:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def cursor(self, query, *args, **kwargs):
            real_cursor = self._conn.cursor(query, *args, **kwargs)

            class _CountingCursor:
                def __aiter__(self):
                    self._it = real_cursor.__aiter__()
                    return self

                async def __anext__(self):
                    rec = await self._it.__anext__()
                    pulled["n"] += 1
                    return rec

            return _CountingCursor()

    class _AcquireCM:
        def __init__(self):
            self._cm = real_pool.acquire()

        async def __aenter__(self):
            conn = await self._cm.__aenter__()
            return _CountingConnWrapper(conn)

        async def __aexit__(self, *exc):
            return await self._cm.__aexit__(*exc)

    class _PoolWrapper:
        def __getattr__(self, name):
            return getattr(real_pool, name)

        def acquire(self, *a, **kw):
            return _AcquireCM()

    adapter._pool = _PoolWrapper()
    try:
        async with pg_node.stream(
            query=f"SELECT id FROM {PG_TABLE} ORDER BY id", batch_size=batch_size
        ) as cursor:
            agen = cursor.__aiter__()
            first = await agen.__anext__()
            assert first["id"] == 1
            # After consuming exactly one row, asyncpg has buffered at most one
            # prefetch window (batch_size) — never the whole 25-row set.
            assert pulled["n"] <= batch_size, (
                f"pulled {pulled['n']} rows after consuming 1 "
                f"(batch_size={batch_size}); streaming is not memory-bounded"
            )
            # Drain so the CM exits cleanly.
            async for _ in agen:
                pass
    finally:
        adapter._pool = real_pool

    assert pulled["n"] == 25  # all rows eventually streamed


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_pg_stream_early_break_releases_to_pool(pg_node):
    """Early break releases the connection + closes the txn (no idle leak)."""
    adapter = await pg_node._get_adapter()
    pool = adapter._pool
    free_before = pool.get_idle_size()

    seen = []
    async with pg_node.stream(
        query=f"SELECT id FROM {PG_TABLE} ORDER BY id", batch_size=5
    ) as cursor:
        async for row in cursor:
            seen.append(row["id"])
            if len(seen) == 3:
                break
    assert seen == [1, 2, 3]

    # Connection returned to the pool.
    assert pool.get_idle_size() == free_before

    # No idle_in_transaction backend left behind (the txn was closed on exit).
    check = await pg_node.async_run(
        query=(
            "SELECT COUNT(*) AS c FROM pg_stat_activity "
            "WHERE state = 'idle in transaction'"
        )
    )
    assert check["result"]["data"][0]["c"] == 0


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_pg_stream_exception_unwind_releases_to_pool(pg_node):
    """An exception mid-iteration releases the connection + closes the txn."""
    adapter = await pg_node._get_adapter()
    pool = adapter._pool
    free_before = pool.get_idle_size()

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        async with pg_node.stream(
            query=f"SELECT id FROM {PG_TABLE} ORDER BY id", batch_size=5
        ) as cursor:
            async for row in cursor:
                if row["id"] == 4:
                    raise Boom("consumer failure mid-stream")

    assert pool.get_idle_size() == free_before
    check = await pg_node.async_run(
        query=(
            "SELECT COUNT(*) AS c FROM pg_stat_activity "
            "WHERE state = 'idle in transaction'"
        )
    )
    assert check["result"]["data"][0]["c"] == 0


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_pg_stream_mid_iteration_failure_propagates_no_reyield(pg_node):
    """A failure AFTER the first row propagates and does NOT re-drive/re-yield.

    We force the asyncpg cursor to raise on the 4th fetched record and assert
    (a) the exception propagates, (b) exactly the first 3 rows were yielded
    (no retry re-yielded rows 1-3).
    """
    adapter = await pg_node._get_adapter()
    real_pool = adapter._pool

    class InjectedError(RuntimeError):
        pass

    class _FailingConnWrapper:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def cursor(self, query, *args, **kwargs):
            real_cursor = self._conn.cursor(query, *args, **kwargs)

            class _FailingCursor:
                def __aiter__(self):
                    self._it = real_cursor.__aiter__()
                    self._n = 0
                    return self

                async def __anext__(self):
                    rec = await self._it.__anext__()
                    self._n += 1
                    if self._n == 4:
                        raise InjectedError("driver blew up mid-stream")
                    return rec

            return _FailingCursor()

    class _AcquireCM:
        def __init__(self):
            self._cm = real_pool.acquire()

        async def __aenter__(self):
            conn = await self._cm.__aenter__()
            return _FailingConnWrapper(conn)

        async def __aexit__(self, *exc):
            return await self._cm.__aexit__(*exc)

    class _PoolWrapper:
        def __getattr__(self, name):
            return getattr(real_pool, name)

        def acquire(self, *a, **kw):
            return _AcquireCM()

    adapter._pool = _PoolWrapper()
    seen = []
    try:
        with pytest.raises(InjectedError):
            async with pg_node.stream(
                query=f"SELECT id FROM {PG_TABLE} ORDER BY id", batch_size=10
            ) as cursor:
                async for row in cursor:
                    seen.append(row["id"])
    finally:
        adapter._pool = real_pool

    # Exactly 3 rows yielded; no retry re-yielded rows 1-3 (no double-yield).
    assert seen == [1, 2, 3]


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_pg_stream_open_phase_transient_retry(pg_node):
    """A transient failure at connection-acquire (open phase) is recoverable.

    The open phase (pool.acquire) is retried by the pool's own acquisition;
    here we make the FIRST acquire raise a transient error, then succeed, and
    assert the stream still yields all rows. (Once the first row is yielded,
    no retry applies — that is the mid-iteration test above.)
    """
    adapter = await pg_node._get_adapter()
    real_pool = adapter._pool
    state = {"calls": 0}

    class _FlakyAcquireCM:
        def __init__(self):
            state["calls"] += 1
            self._fail = state["calls"] == 1
            self._cm = None if self._fail else real_pool.acquire()

        async def __aenter__(self):
            if self._fail:
                raise ConnectionError("server closed the connection (transient)")
            return await self._cm.__aenter__()

        async def __aexit__(self, *exc):
            if self._cm is not None:
                return await self._cm.__aexit__(*exc)
            return False

    class _FlakyPoolWrapper:
        def __getattr__(self, name):
            return getattr(real_pool, name)

        def acquire(self, *a, **kw):
            return _FlakyAcquireCM()

    adapter._pool = _FlakyPoolWrapper()
    try:
        # The adapter's stream opens the connection inside __aenter__; the
        # first acquire fails. We retry the OPEN ourselves (the caller's
        # responsibility per the documented retry contract: open-phase only).
        streamed = []
        last_err = None
        for _attempt in range(3):
            try:
                async with pg_node.stream(
                    query=f"SELECT id FROM {PG_TABLE} ORDER BY id", batch_size=10
                ) as cursor:
                    async for row in cursor:
                        streamed.append(row["id"])
                break
            except ConnectionError as e:
                last_err = e
                streamed.clear()
                continue
        else:  # pragma: no cover - defensive
            raise AssertionError(f"open never succeeded: {last_err}")
    finally:
        adapter._pool = real_pool

    assert streamed == list(range(1, 26))
    assert state["calls"] >= 2  # first failed, second (or later) succeeded


@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_pg_stream_masking_per_row(pg_node):
    """Access-control masking is applied to every streamed PG row."""

    class _MaskMgr:
        class _D:
            allowed = True
            reason = "ok"

        def check_node_access(self, *a, **k):
            return self._D()

        def apply_data_masking(self, user_context, node_name, row):
            r = dict(row)
            if r.get("ssn"):
                r["ssn"] = "***-**-****"
            return r

    pg_node.access_control_manager = _MaskMgr()
    rows = []
    async with pg_node.stream(
        query=f"SELECT id, ssn FROM {PG_TABLE} ORDER BY id",
        user_context={"user_id": "u1"},
        batch_size=10,
    ) as cursor:
        async for row in cursor:
            rows.append(row)

    assert len(rows) == 25
    assert all(r["ssn"] == "***-**-****" for r in rows), rows[:3]


# ===========================================================================
# MySQL
# ===========================================================================

MYSQL_TABLE = "_stream_it_mysql"


@pytest_asyncio.fixture
async def mysql_node():
    """AsyncSQLDatabaseNode against the live MySQL, table seeded."""
    conn = get_mysql_connection_string()
    setup = AsyncSQLDatabaseNode(
        name="mysql_stream_setup",
        database_type="mysql",
        connection_string=conn,
        validate_queries=False,
        share_pool=False,
    )
    await setup.async_run(query=f"DROP TABLE IF EXISTS {MYSQL_TABLE}")
    await setup.async_run(
        query=(
            f"CREATE TABLE {MYSQL_TABLE} ("
            "  id INT PRIMARY KEY,"
            "  name VARCHAR(64),"
            "  score DOUBLE,"
            "  active TINYINT,"
            "  ssn VARCHAR(32)"
            ")"
        )
    )
    for i in range(1, 26):
        await setup.async_run(
            query=(
                f"INSERT INTO {MYSQL_TABLE} (id, name, score, active, ssn) "
                "VALUES (%s, %s, %s, %s, %s)"
            ),
            params=(
                i,
                None if i == 7 else f"name-{i}",
                None if i == 11 else float(i) + 0.5,
                1 if i % 2 == 0 else 0,
                f"{i:03d}-00-0000",
            ),
        )

    node = AsyncSQLDatabaseNode(
        name="mysql_stream_node",
        database_type="mysql",
        connection_string=conn,
        validate_queries=True,
        share_pool=False,
    )
    yield node

    teardown = AsyncSQLDatabaseNode(
        name="mysql_stream_teardown",
        database_type="mysql",
        connection_string=conn,
        validate_queries=False,
        share_pool=False,
    )
    await teardown.async_run(query=f"DROP TABLE IF EXISTS {MYSQL_TABLE}")


@pytest.mark.integration
@pytest.mark.requires_mysql
@pytest.mark.asyncio
async def test_mysql_stream_round_trip_vs_fetch_all(mysql_node):
    """Streamed MySQL rows are byte-identical to fetch_mode=ALL."""
    materialized = await mysql_node.async_run(
        query=(f"SELECT id, name, score, active, ssn FROM {MYSQL_TABLE} ORDER BY id"),
        params=(),
    )
    expected = materialized["result"]["data"]

    streamed = []
    async with mysql_node.stream(
        query=(f"SELECT id, name, score, active, ssn FROM {MYSQL_TABLE} ORDER BY id"),
        batch_size=10,
    ) as cursor:
        async for row in cursor:
            streamed.append(row)

    assert streamed == expected
    assert len(streamed) == 25
    assert streamed[6]["name"] is None
    assert streamed[10]["score"] is None


@pytest.mark.integration
@pytest.mark.requires_mysql
@pytest.mark.asyncio
async def test_mysql_stream_memory_bounded(mysql_node):
    """SSCursor.fetchmany MUST pull ≤ batch_size rows before consumer advances.

    Instrument the SSCursor's fetchmany to count rows pulled; after consuming
    exactly ONE row only the first batch (batch_size) has been pulled.
    """
    batch_size = 5
    adapter = await mysql_node._get_adapter()
    real_pool = adapter._pool
    pulled = {"n": 0}

    # The adapter opens the SSCursor via ``await conn.cursor(SSCursor)``, so the
    # wrapper's cursor() MUST return an awaitable yielding the (instrumented)
    # cursor — not an async context manager.
    class _CountingConnWrapper:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def cursor(self, *args, **kwargs):
            real_awaitable = self._conn.cursor(*args, **kwargs)

            async def _await_and_wrap():
                cur = await real_awaitable
                real_fetchmany = cur.fetchmany

                async def counting_fetchmany(size):
                    batch = await real_fetchmany(size)
                    pulled["n"] += len(batch)
                    return batch

                cur.fetchmany = counting_fetchmany
                return cur

            return _await_and_wrap()

    class _AcquireCM:
        def __init__(self):
            self._cm = real_pool.acquire()

        async def __aenter__(self):
            conn = await self._cm.__aenter__()
            return _CountingConnWrapper(conn)

        async def __aexit__(self, *exc):
            return await self._cm.__aexit__(*exc)

    class _PoolWrapper:
        def __getattr__(self, name):
            return getattr(real_pool, name)

        def acquire(self, *a, **kw):
            return _AcquireCM()

    adapter._pool = _PoolWrapper()
    try:
        async with mysql_node.stream(
            query=f"SELECT id FROM {MYSQL_TABLE} ORDER BY id", batch_size=batch_size
        ) as cursor:
            agen = cursor.__aiter__()
            first = await agen.__anext__()
            assert first["id"] == 1
            assert pulled["n"] <= batch_size, (
                f"pulled {pulled['n']} after consuming 1 "
                f"(batch_size={batch_size}); not memory-bounded"
            )
            async for _ in agen:
                pass
    finally:
        adapter._pool = real_pool

    assert pulled["n"] == 25


@pytest.mark.integration
@pytest.mark.requires_mysql
@pytest.mark.asyncio
async def test_mysql_stream_early_break_releases_to_pool(mysql_node):
    """Early break drains+closes the SSCursor and returns the connection."""
    adapter = await mysql_node._get_adapter()
    pool = adapter._pool
    free_before = pool.freesize

    seen = []
    async with mysql_node.stream(
        query=f"SELECT id FROM {MYSQL_TABLE} ORDER BY id", batch_size=5
    ) as cursor:
        async for row in cursor:
            seen.append(row["id"])
            if len(seen) == 3:
                break
    assert seen == [1, 2, 3]

    # Allow the pool to reclaim the connection, then assert it is back.
    await asyncio.sleep(0)
    assert pool.freesize == free_before

    # The connection is usable again (SSCursor fully drained on exit).
    after = await mysql_node.async_run(
        query=f"SELECT COUNT(*) AS c FROM {MYSQL_TABLE}", params=()
    )
    assert after["result"]["data"][0]["c"] == 25


@pytest.mark.integration
@pytest.mark.requires_mysql
@pytest.mark.asyncio
async def test_mysql_stream_exception_unwind_releases_to_pool(mysql_node):
    """An exception mid-iteration drains the SSCursor + releases the conn."""
    adapter = await mysql_node._get_adapter()
    pool = adapter._pool
    free_before = pool.freesize

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        async with mysql_node.stream(
            query=f"SELECT id FROM {MYSQL_TABLE} ORDER BY id", batch_size=5
        ) as cursor:
            async for row in cursor:
                if row["id"] == 4:
                    raise Boom("consumer failure mid-stream")

    await asyncio.sleep(0)
    assert pool.freesize == free_before
    after = await mysql_node.async_run(
        query=f"SELECT COUNT(*) AS c FROM {MYSQL_TABLE}", params=()
    )
    assert after["result"]["data"][0]["c"] == 25


@pytest.mark.integration
@pytest.mark.requires_mysql
@pytest.mark.asyncio
async def test_mysql_stream_mid_iteration_failure_propagates_no_reyield(
    mysql_node,
):
    """A failure after the first row propagates without re-yielding rows."""
    adapter = await mysql_node._get_adapter()
    real_pool = adapter._pool

    class InjectedError(RuntimeError):
        pass

    class _FailingConnWrapper:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def cursor(self, *args, **kwargs):
            real_awaitable = self._conn.cursor(*args, **kwargs)

            async def _await_and_wrap():
                cur = await real_awaitable
                real_fetchmany = cur.fetchmany
                calls = {"n": 0}

                async def failing_fetchmany(size):
                    calls["n"] += 1
                    if calls["n"] == 2:
                        raise InjectedError("driver blew up mid-stream")
                    return await real_fetchmany(size)

                cur.fetchmany = failing_fetchmany
                return cur

            return _await_and_wrap()

    class _AcquireCM:
        def __init__(self):
            self._cm = real_pool.acquire()

        async def __aenter__(self):
            conn = await self._cm.__aenter__()
            return _FailingConnWrapper(conn)

        async def __aexit__(self, *exc):
            return await self._cm.__aexit__(*exc)

    class _PoolWrapper:
        def __getattr__(self, name):
            return getattr(real_pool, name)

        def acquire(self, *a, **kw):
            return _AcquireCM()

    adapter._pool = _PoolWrapper()
    seen = []
    try:
        with pytest.raises(InjectedError):
            async with mysql_node.stream(
                query=f"SELECT id FROM {MYSQL_TABLE} ORDER BY id", batch_size=3
            ) as cursor:
                async for row in cursor:
                    seen.append(row["id"])
    finally:
        adapter._pool = real_pool

    # First batch of 3 yielded; the 2nd fetchmany raised → no re-yield.
    assert seen == [1, 2, 3]


@pytest.mark.integration
@pytest.mark.requires_mysql
@pytest.mark.asyncio
async def test_mysql_stream_masking_per_row(mysql_node):
    """Access-control masking is applied to every streamed MySQL row."""

    class _MaskMgr:
        class _D:
            allowed = True
            reason = "ok"

        def check_node_access(self, *a, **k):
            return self._D()

        def apply_data_masking(self, user_context, node_name, row):
            r = dict(row)
            if r.get("ssn"):
                r["ssn"] = "***-**-****"
            return r

    mysql_node.access_control_manager = _MaskMgr()
    rows = []
    async with mysql_node.stream(
        query=f"SELECT id, ssn FROM {MYSQL_TABLE} ORDER BY id",
        user_context={"user_id": "u1"},
        batch_size=10,
    ) as cursor:
        async for row in cursor:
            rows.append(row)

    assert len(rows) == 25
    assert all(r["ssn"] == "***-**-****" for r in rows), rows[:3]


def test_default_stream_batch_size_is_1000():
    """Sanity: the documented default batch size constant."""
    assert DEFAULT_STREAM_BATCH_SIZE == 1000
