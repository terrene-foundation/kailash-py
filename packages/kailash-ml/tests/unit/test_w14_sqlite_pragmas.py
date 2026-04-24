# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W14 Tier-1 unit tests — SQLite PRAGMA stack + shared-cache ``:memory:``.

Per ``specs/ml-tracking.md`` §6.1 + ``rules/patterns.md`` "SQLite
Connection Management", every :class:`SqliteTrackerStore` connection
MUST apply the full PRAGMA set at connect time:

- ``journal_mode=WAL`` (file-based only; ``:memory:`` has no journal)
- ``busy_timeout=30000`` (30 s)
- ``synchronous=NORMAL``
- ``cache_size=-20000`` (20 MB)
- ``foreign_keys=ON``

AND in-memory stores MUST use the URI shared-cache form so two store
instances pointing at ``:memory:`` see the same database (the plain
``:memory:`` string gives every connection a private DB, which
silently breaks cross-instance test fixtures).

W14b routes SQLite through :class:`kailash.core.pool.AsyncSQLitePool`;
the PRAGMA stack is applied by the pool's ``ConnectionFactory`` at
connect time, so these tests probe a live writer connection via
``pool.acquire_write()``.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from kailash_ml.tracking import SqliteTrackerStore

# ---------------------------------------------------------------------------
# File-based PRAGMA stack (spec §6.1, rules/patterns.md)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_backend_applies_full_pragma_stack(tmp_path: Path) -> None:
    """File-based SQLite MUST apply all five PRAGMAs at connect time."""
    db_path = tmp_path / "w14_pragma.db"
    backend = SqliteTrackerStore(db_path)
    try:
        # Trigger writer-connection creation so we can probe it.
        await backend.initialize()
        async with backend._pool.acquire_write() as conn:
            cur = await conn.execute("PRAGMA journal_mode")
            (journal_mode,) = await cur.fetchone()
            assert journal_mode.lower() == "wal", (
                f"journal_mode={journal_mode!r}, expected 'wal' — WAL is "
                f"mandatory for multi-process SQLite per rules/patterns.md"
            )

            cur = await conn.execute("PRAGMA busy_timeout")
            (busy_timeout,) = await cur.fetchone()
            assert busy_timeout == 30000, (
                f"busy_timeout={busy_timeout}, expected 30000 (30s) — "
                f"shorter windows surface SQLITE_BUSY under test-suite "
                f"parallelism"
            )

            cur = await conn.execute("PRAGMA synchronous")
            (synchronous,) = await cur.fetchone()
            # 1 == NORMAL, 2 == FULL, 3 == EXTRA — the enum, not the
            # name, is what PRAGMA returns when queried.
            assert synchronous == 1, (
                f"synchronous={synchronous}, expected 1 (NORMAL) — FULL "
                f"imposes ~10× write overhead without durability gain in WAL"
            )

            cur = await conn.execute("PRAGMA cache_size")
            (cache_size,) = await cur.fetchone()
            assert cache_size == -20000, (
                f"cache_size={cache_size}, expected -20000 (20MB). "
                f"Positive values mean pages; negative means KB."
            )

            cur = await conn.execute("PRAGMA foreign_keys")
            (foreign_keys,) = await cur.fetchone()
            assert foreign_keys == 1, (
                f"foreign_keys={foreign_keys}, expected 1 (ON) — FK "
                f"enforcement is required for W14+ schema unification"
            )
    finally:
        await backend.close()


# ---------------------------------------------------------------------------
# :memory: variant — shared-cache URI (rules/patterns.md "URI shared-cache")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_backend_uses_shared_cache_uri() -> None:
    """``:memory:`` MUST route through the URI shared-cache form so
    two store instances see the same database.

    Without shared-cache, each ``sqlite3.connect(":memory:")`` returns
    a private in-memory DB; fixtures that open two handles (writer +
    reader, e.g. a test harness) silently see empty reads and tests
    fall over with "table doesn't exist" late in the cycle.
    """
    backend_a = SqliteTrackerStore(":memory:")
    backend_b = SqliteTrackerStore(":memory:")
    try:
        await backend_a.initialize()
        # backend_b should see backend_a's schema because both share
        # the named memory cache.
        async with backend_b._pool.acquire_write() as conn:
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            rows = await cur.fetchall()
        table_names = {row[0] for row in rows}
        assert "experiment_runs" in table_names, (
            "shared-cache URI not applied — backend_b sees a private "
            "in-memory DB instead of backend_a's schema"
        )
    finally:
        await backend_a.close()
        await backend_b.close()


@pytest.mark.asyncio
async def test_memory_backend_applies_non_wal_pragmas() -> None:
    """``:memory:`` skips WAL (no journal) but MUST still apply the
    other four PRAGMAs."""
    backend = SqliteTrackerStore(":memory:")
    try:
        await backend.initialize()
        async with backend._pool.acquire_write() as conn:
            cur = await conn.execute("PRAGMA busy_timeout")
            (busy_timeout,) = await cur.fetchone()
            assert busy_timeout == 30000

            cur = await conn.execute("PRAGMA synchronous")
            (synchronous,) = await cur.fetchone()
            assert synchronous == 1

            cur = await conn.execute("PRAGMA cache_size")
            (cache_size,) = await cur.fetchone()
            assert cache_size == -20000

            cur = await conn.execute("PRAGMA foreign_keys")
            (foreign_keys,) = await cur.fetchone()
            assert foreign_keys == 1
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_memory_backend_connect_uri_does_not_leak_into_db_path() -> None:
    """Spec hygiene — the shared-cache URI rewrite is internal. The
    public ``_db_path`` attribute MUST remain the user-supplied
    ``":memory:"`` so callers (artifact root resolver, error messages)
    see the logical address, not the physical URI."""
    backend = SqliteTrackerStore(":memory:")
    try:
        assert backend._db_path == ":memory:"
    finally:
        await backend.close()
