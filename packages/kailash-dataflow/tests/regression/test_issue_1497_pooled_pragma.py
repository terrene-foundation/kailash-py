"""Regression: SQLite pooled connections apply only the LAST PRAGMA (#1497).

Root cause: ``SQLiteAdapter._initialize_connection_pool`` dedented the
``await conn.execute("PRAGMA ...")`` OUTSIDE the ``for pragma, value in
self.pragmas.items()`` loop, so only the final pragma (``optimize``) was ever
applied to each initially-pooled connection. ``foreign_keys`` is the *first*
pragma in the default dict, so FK enforcement was silently OFF on every
initial pooled connection while overflow connections (created inside
``_get_connection``, where the execute is correctly in-loop) had it ON — an
internally-inconsistent pool. An empty ``pragmas`` dict additionally raised
``NameError`` on the unbound ``safe_name`` at the dedented execute.

Tier-2 — NO MOCKING. Real ``SQLiteAdapter``, real ``aiosqlite``, real
file-backed SQLite, real ``PRAGMA`` reads. Structural behavioral assertions
(actual pragma values read back off pooled connections), not lexical source
scanning.

The coupled aiosqlite Connection-leak acceptance criterion (#1497 AC-2) is
pinned by ``test_issue_1051_memory_connection_leak.py`` — the pragma re-indent
keeps that suite green in the full ``-k sqlite`` slice.
"""

import pytest

from dataflow.adapters.sqlite import SQLiteAdapter


async def _read_pragma(conn, name: str):
    cursor = await conn.execute(f"PRAGMA {name}")
    row = await cursor.fetchone()
    await cursor.close()
    return row[0] if row else None


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1497_initial_pooled_conn_applies_every_pragma(sqlite_file_url):
    """Every configured pragma reaches each initially-pooled connection.

    The dedent bug applied ONLY ``optimize`` (the last pragma); foreign_keys
    stayed at SQLite's default 0 and synchronous at the default 2 (FULL).
    """
    adapter = SQLiteAdapter(sqlite_file_url)
    await adapter.connect()
    try:
        async with adapter._pool_lock:
            assert adapter._connection_pool, "pool should be pre-populated"
            conn = adapter._connection_pool[0]

        # foreign_keys is the FIRST pragma in the default dict — the canonical
        # victim of the dedent (only the LAST pragma survived).
        assert await _read_pragma(conn, "foreign_keys") == 1, (
            "foreign_keys OFF on an initial pooled connection — the pragma "
            "loop's execute was dedented and only the last pragma applied"
        )
        # synchronous is configured NORMAL (1); the bug left it at default 2.
        assert (
            await _read_pragma(conn, "synchronous") == 1
        ), "synchronous not set to configured NORMAL on a pooled connection"
    finally:
        await adapter.disconnect()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1497_initial_and_overflow_conns_have_identical_pragmas(
    sqlite_file_url,
):
    """Initial-pool and overflow connections apply an identical pragma set.

    Overflow connections are created in ``_get_connection`` (execute already
    in-loop); initial connections in ``_initialize_connection_pool`` (the
    fixed site). Before the fix the two diverged (initial: FK off; overflow:
    FK on).
    """
    adapter = SQLiteAdapter(sqlite_file_url)
    await adapter.connect()
    try:
        # An initial pooled connection.
        async with adapter._pool_lock:
            initial_conn = adapter._connection_pool[0]
        initial_fk = await _read_pragma(initial_conn, "foreign_keys")
        initial_sync = await _read_pragma(initial_conn, "synchronous")

        # Force an overflow connection: drain the pool, then acquire one more.
        async with adapter._pool_lock:
            drained = list(adapter._connection_pool)
            adapter._connection_pool.clear()
        async with adapter._get_connection() as overflow_conn:
            overflow_fk = await _read_pragma(overflow_conn, "foreign_keys")
            overflow_sync = await _read_pragma(overflow_conn, "synchronous")
        # Restore drained connections so disconnect closes them all.
        async with adapter._pool_lock:
            adapter._connection_pool.extend(drained)

        assert (
            initial_fk == overflow_fk == 1
        ), f"foreign_keys divergence: initial={initial_fk} overflow={overflow_fk}"
        assert (
            initial_sync == overflow_sync == 1
        ), f"synchronous divergence: initial={initial_sync} overflow={overflow_sync}"
    finally:
        await adapter.disconnect()


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1497_empty_pragmas_does_not_nameerror(sqlite_file_url):
    """An empty ``pragmas`` dict must not NameError on the (formerly unbound)
    ``safe_name`` at the dedented execute."""
    adapter = SQLiteAdapter(sqlite_file_url, pragmas={})
    # connect() -> _initialize_connection_pool() must not raise NameError.
    await adapter.connect()
    try:
        async with adapter._pool_lock:
            assert adapter._connection_pool, "pool should populate with empty pragmas"
    finally:
        await adapter.disconnect()
