"""Tier-1 unit tests for SQL streaming (server-side cursor) — SQLite lane.

SQLite needs no Docker, so this lane is the BLOCKING Tier-1 CI gate for the
streaming API. It covers, against a real on-disk SQLite database:

* round-trip correctness — streamed rows are byte-identical to a
  ``fetch_mode=ALL`` materialization over mixed types (NULL / int / str /
  float / bool);
* the context-manager lifetime contract — early ``break`` AND exception
  unwind both release the connection;
* batch-boundary behaviour — rows are pulled in ``batch_size`` chunks via
  ``fetchmany``, not all up front.

The PostgreSQL + MySQL lanes (server-side cursors / SSCursor, memory-bounded
proofs, retry contract, masking) live under ``tests/integration/nodes/`` and
run against the live containers.
"""

import asyncio
import os
import tempfile

import pytest

from kailash.nodes.data.async_sql import (
    DEFAULT_STREAM_BATCH_SIZE,
    DatabaseConfig,
    DatabaseType,
    FetchMode,
    SQLiteAdapter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_db_path():
    """A real on-disk SQLite database file (NOT :memory:).

    Using a file DB exercises the inline-connection ``stream`` path where the
    context-manager owns the connection and MUST close it on every exit.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        yield path
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        # aiosqlite WAL sidecar files
        for sidecar in (f"{path}-wal", f"{path}-shm"):
            try:
                os.remove(sidecar)
            except FileNotFoundError:
                pass


@pytest.fixture
async def seeded_adapter(sqlite_db_path):
    """SQLiteAdapter connected to a file DB seeded with mixed-type rows."""
    config = DatabaseConfig(
        type=DatabaseType.SQLITE,
        database=sqlite_db_path,
    )
    adapter = SQLiteAdapter(config)
    await adapter.connect()

    # Mixed types incl. NULL/int/str/float/bool. SQLite stores bool as int.
    await adapter.execute(
        "CREATE TABLE items ("
        "  id INTEGER PRIMARY KEY,"
        "  name TEXT,"
        "  score REAL,"
        "  active INTEGER,"
        "  note TEXT"
        ")"
    )
    rows = [
        (1, "alpha", 1.5, 1, "first"),
        (2, "beta", 2.0, 0, None),  # NULL note
        (3, None, 3.25, 1, "third"),  # NULL name
        (4, "delta", None, 0, "fourth"),  # NULL score
        (5, "epsilon", 5.0, 1, "fifth"),
    ]
    for r in rows:
        await adapter.execute(
            "INSERT INTO items (id, name, score, active, note) "
            "VALUES (?, ?, ?, ?, ?)",
            r,
        )

    try:
        yield adapter
    finally:
        await adapter.disconnect()


# ---------------------------------------------------------------------------
# Round-trip correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_rows_byte_identical_to_fetch_all(seeded_adapter):
    """Streamed rows MUST equal the materialized (fetch_mode=ALL) rows."""
    materialized = await seeded_adapter.execute(
        "SELECT id, name, score, active, note FROM items ORDER BY id",
        fetch_mode=FetchMode.ALL,
    )

    streamed = []
    async with seeded_adapter.stream(
        "SELECT id, name, score, active, note FROM items ORDER BY id"
    ) as cursor:
        async for row in cursor:
            streamed.append(row)

    assert streamed == materialized
    # Sanity: NULLs survived as None, not as a sentinel.
    assert streamed[1]["note"] is None
    assert streamed[2]["name"] is None
    assert streamed[3]["score"] is None
    # Each row is a plain dict.
    assert all(isinstance(r, dict) for r in streamed)


@pytest.mark.asyncio
async def test_stream_with_positional_params(seeded_adapter):
    """Parameterized streaming returns only matching rows, converted."""
    streamed = []
    async with seeded_adapter.stream(
        "SELECT id, name FROM items WHERE active = ? ORDER BY id", (1,)
    ) as cursor:
        async for row in cursor:
            streamed.append(row)

    assert [r["id"] for r in streamed] == [1, 3, 5]


@pytest.mark.asyncio
async def test_stream_empty_result_set(seeded_adapter):
    """An empty result set yields zero rows and still releases cleanly."""
    streamed = []
    async with seeded_adapter.stream("SELECT id FROM items WHERE id > 9999") as cursor:
        async for row in cursor:
            streamed.append(row)
    assert streamed == []


# ---------------------------------------------------------------------------
# Context-manager lifetime: early break + exception unwind release the conn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_early_break_releases_connection(seeded_adapter):
    """Breaking out of iteration MUST exit the CM and release the connection.

    After an early break, the SAME adapter must be able to run a fresh query —
    proof the connection/cursor were released, not leaked open.
    """
    seen = []
    async with seeded_adapter.stream("SELECT id FROM items ORDER BY id") as cursor:
        async for row in cursor:
            seen.append(row["id"])
            if len(seen) == 2:
                break  # early exit mid-stream

    assert seen == [1, 2]

    # The connection is released — a follow-up query succeeds.
    after = await seeded_adapter.execute(
        "SELECT COUNT(*) AS c FROM items", fetch_mode=FetchMode.ONE
    )
    assert after["c"] == 5


@pytest.mark.asyncio
async def test_stream_exception_unwind_releases_connection(seeded_adapter):
    """An exception raised inside the iteration body MUST still release.

    The exception propagates (not swallowed), AND the adapter is reusable
    afterward — proof __aexit__ ran the cleanup on the exception path.
    """

    class Boom(RuntimeError):
        pass

    seen = []
    with pytest.raises(Boom):
        async with seeded_adapter.stream("SELECT id FROM items ORDER BY id") as cursor:
            async for row in cursor:
                seen.append(row["id"])
                if row["id"] == 3:
                    raise Boom("consumer blew up mid-stream")

    assert seen == [1, 2, 3]

    # Connection released despite the exception — follow-up query works.
    after = await seeded_adapter.execute(
        "SELECT COUNT(*) AS c FROM items", fetch_mode=FetchMode.ONE
    )
    assert after["c"] == 5


# ---------------------------------------------------------------------------
# Batch boundary: fetchmany pulls in batch_size chunks, not all up front
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_pulls_in_batch_size_chunks(seeded_adapter, monkeypatch):
    """With batch_size=2, fetchmany MUST be called with size 2 each round.

    We instrument the cursor's fetchmany to record the requested chunk size
    and the number of round trips — a deterministic batch-boundary assertion
    rather than a memory heuristic.
    """
    recorded_sizes = []
    real_get_conn = seeded_adapter._get_connection

    async def instrumented_get_conn():
        db = await real_get_conn()
        real_execute = db.execute

        async def execute_wrapping_cursor(sql, params=None):
            cursor = await real_execute(sql, params)
            real_fetchmany = cursor.fetchmany

            async def recording_fetchmany(size):
                recorded_sizes.append(size)
                return await real_fetchmany(size)

            cursor.fetchmany = recording_fetchmany
            return cursor

        db.execute = execute_wrapping_cursor
        return db

    # File-DB stream path uses aiosqlite.connect inline, so patch that to
    # wrap the cursor's fetchmany. We monkeypatch the adapter's aiosqlite
    # connect to return a connection whose execute wraps fetchmany.
    import aiosqlite

    real_connect = aiosqlite.connect

    class _ConnectWrapper:
        def __init__(self, *args, **kwargs):
            self._cm = real_connect(*args, **kwargs)

        async def __aenter__(self):
            db = await self._cm.__aenter__()
            real_execute = db.execute

            async def execute_wrapping_cursor(sql, params=None):
                cursor = await real_execute(sql, params)
                real_fetchmany = cursor.fetchmany

                async def recording_fetchmany(size):
                    recorded_sizes.append(size)
                    return await real_fetchmany(size)

                cursor.fetchmany = recording_fetchmany
                return cursor

            db.execute = execute_wrapping_cursor
            return db

        async def __aexit__(self, *exc):
            return await self._cm.__aexit__(*exc)

    monkeypatch.setattr(seeded_adapter._aiosqlite, "connect", _ConnectWrapper)

    streamed = []
    async with seeded_adapter.stream(
        "SELECT id FROM items ORDER BY id", batch_size=2
    ) as cursor:
        async for row in streamed_consume(cursor, streamed):
            pass

    assert [r["id"] for r in streamed] == [1, 2, 3, 4, 5]
    # Every fetchmany call requested exactly batch_size=2.
    assert recorded_sizes, "fetchmany was never called"
    assert all(size == 2 for size in recorded_sizes), recorded_sizes
    # 5 rows / chunk of 2 => 3 chunks with data + 1 empty terminator.
    assert len(recorded_sizes) == 4, recorded_sizes


async def streamed_consume(cursor, sink):
    """Helper: drain a stream cursor into ``sink`` and yield each row."""
    async for row in cursor:
        sink.append(row)
        yield row


@pytest.mark.asyncio
async def test_stream_does_not_pull_remaining_rows_before_consumed(
    seeded_adapter,
):
    """Before the consumer has processed past the first batch, only the first
    batch_size rows have been pulled — proof of lazy, bounded pulls.

    With batch_size=2, after pulling exactly ONE row from the iterator (which
    triggers the first fetchmany of 2), at most 2 rows have been read from the
    driver — never all 5.
    """
    fetched_total = 0

    import aiosqlite

    real_connect = aiosqlite.connect

    class _ConnectWrapper:
        def __init__(self, *args, **kwargs):
            self._cm = real_connect(*args, **kwargs)

        async def __aenter__(self):
            db = await self._cm.__aenter__()
            real_execute = db.execute

            async def execute_wrapping(sql, params=None):
                cursor = await real_execute(sql, params)
                real_fetchmany = cursor.fetchmany

                async def counting_fetchmany(size):
                    nonlocal fetched_total
                    batch = await real_fetchmany(size)
                    fetched_total += len(batch)
                    return batch

                cursor.fetchmany = counting_fetchmany
                return cursor

            db.execute = execute_wrapping
            return db

        async def __aexit__(self, *exc):
            return await self._cm.__aexit__(*exc)

    seeded_adapter._aiosqlite.connect = _ConnectWrapper
    try:
        async with seeded_adapter.stream(
            "SELECT id FROM items ORDER BY id", batch_size=2
        ) as cursor:
            agen = cursor.__aiter__()
            first = await agen.__anext__()
            assert first["id"] == 1
            # Only the first batch (2 rows) should have been pulled so far.
            assert fetched_total <= 2, (
                f"pulled {fetched_total} rows after consuming 1; "
                "streaming is not bounded"
            )
            # Drain the rest so the CM exits cleanly.
            async for _ in agen:
                pass
    finally:
        seeded_adapter._aiosqlite.connect = real_connect

    assert fetched_total == 5


# ---------------------------------------------------------------------------
# Module-level constant + API surface
# ---------------------------------------------------------------------------


def test_default_stream_batch_size_constant():
    """The documented default batch size is exposed as a module constant."""
    assert DEFAULT_STREAM_BATCH_SIZE == 1000


def test_stream_uses_default_batch_size_signature():
    """adapter.stream defaults batch_size to DEFAULT_STREAM_BATCH_SIZE."""
    import inspect

    sig = inspect.signature(SQLiteAdapter.stream)
    assert sig.parameters["batch_size"].default == DEFAULT_STREAM_BATCH_SIZE
