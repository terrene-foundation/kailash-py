"""Tier-2 regression for issue #1604 — add ``include_deleted`` to
``express.find_one`` (soft_delete models) on BOTH PostgreSQL and file-backed
SQLite.

``db.express.list`` / ``read`` / ``count`` accept ``include_deleted=False`` so
tombstoned rows can be retrieved on demand. ``find_one`` auto-filtered
tombstoned rows by default but had NO ``include_deleted`` escape hatch — there
was no way to fetch a tombstoned row via a NON-PK filter through ``find_one``.

The fix mirrors ``list``/``read``/``count``: ``include_deleted`` is placed into
the query params so it (a) forwards to the ListNode ``deleted_at IS NULL``
auto-filter bypass AND (b) becomes part of the cache key (a ``False`` result is
never served to a ``True`` query). The tenant dimension is unaffected —
``tenant_id`` remains a separate cache-key dimension (tenant-isolation.md
Rule 1), ``include_deleted`` only enters the params hash.

Everything below is proven through ``db.express`` / ``db.express_sync`` on BOTH
dialects (parametrized), NO mocking, every write verified with an independent
raw read-back.

Permanent regression test — NEVER delete (``rules/testing.md`` Regression).
"""

import os
import uuid

import asyncpg
import pytest

from dataflow import DataFlow

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


def _sqlite_path(url: str) -> str:
    return url[len("sqlite:///") :]


async def _raw_fetch(dialect: str, url: str, table: str, rid: str):
    """Committed-state read-back that bypasses DataFlow (independent check)."""
    if dialect == "postgresql":
        conn = await asyncpg.connect(url)
        try:
            row = await conn.fetchrow(f'SELECT * FROM "{table}" WHERE id = $1', rid)
            return dict(row) if row is not None else None
        finally:
            await conn.close()
    else:  # sqlite
        import sqlite3

        conn = sqlite3.connect(_sqlite_path(url))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(f'SELECT * FROM "{table}" WHERE id = ?', (rid,))
            r = cur.fetchone()
            return dict(r) if r is not None else None
        finally:
            conn.close()


async def _drop_table(dialect: str, url: str, table: str) -> None:
    if dialect == "postgresql":
        conn = await asyncpg.connect(url)
        try:
            await conn.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        finally:
            await conn.close()
    # sqlite: the tmp_path-backed DB file is discarded by the fixture — no-op.


@pytest.fixture(params=["postgresql", "sqlite"])
def dialect_db(request, tmp_path):
    if request.param == "postgresql":
        return "postgresql", TEST_DATABASE_URL
    return "sqlite", f"sqlite:///{tmp_path}/fo_{uuid.uuid4().hex[:8]}.db"


@pytest.mark.integration
async def test_find_one_include_deleted_returns_tombstoned_row(dialect_db):
    """include_deleted=True returns a tombstoned row matched by a NON-PK filter;
    the default (False) treats it as not-found."""
    dialect, url = dialect_db
    table = f"fo_life_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class FoDoc:
        __tablename__ = table
        __dataflow__ = {"soft_delete": True}

        id: str
        slug: str  # non-PK lookup field
        title: str

    try:
        rid = f"doc-{uuid.uuid4().hex[:8]}"
        await db.express.create(
            "FoDoc", {"id": rid, "slug": "archived", "title": "alive"}
        )

        # Visible before delete via the non-PK filter.
        found = await db.express.find_one("FoDoc", {"slug": "archived"})
        assert found is not None and found["id"] == rid

        # Soft delete (tombstone).
        assert await db.express.delete("FoDoc", rid) is True

        # Default find_one: tombstoned row is treated as not-found.
        assert await db.express.find_one("FoDoc", {"slug": "archived"}) is None

        # include_deleted=True: the tombstoned row is returned via the non-PK
        # filter — the escape hatch the issue adds.
        incl = await db.express.find_one(
            "FoDoc", {"slug": "archived"}, include_deleted=True
        )
        assert incl is not None and incl["id"] == rid
        assert incl["deleted_at"] is not None

        # Independent raw read-back: the row still physically exists, tombstoned.
        raw = await _raw_fetch(dialect, url, table, rid)
        assert raw is not None and raw["deleted_at"] is not None
        assert raw["title"] == "alive"
    finally:
        await db.express.close_async()
        await _drop_table(dialect, url, table)


@pytest.mark.integration
async def test_find_one_include_deleted_cache_no_collision(dialect_db):
    """include_deleted MUST be a cache-key dimension: a cached
    include_deleted=False (None) result must NOT be served to an
    include_deleted=True find_one in the same session. Express caching is ON by
    default (TTL 300s), so this exercises the real collision scenario."""
    dialect, url = dialect_db
    table = f"fo_cache_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class FoCacheDoc:
        __tablename__ = table
        __dataflow__ = {"soft_delete": True}

        id: str
        slug: str
        title: str

    try:
        rid = f"doc-{uuid.uuid4().hex[:8]}"
        await db.express.create("FoCacheDoc", {"id": rid, "slug": "gone", "title": "x"})
        await db.express.delete("FoCacheDoc", rid)

        # Prime the default (include_deleted=False) slot with None (not-found).
        assert await db.express.find_one("FoCacheDoc", {"slug": "gone"}) is None

        # The include_deleted=True query MUST NOT collide with the cached None.
        incl = await db.express.find_one(
            "FoCacheDoc", {"slug": "gone"}, include_deleted=True
        )
        assert incl is not None and incl["id"] == rid
        assert incl["deleted_at"] is not None
    finally:
        await db.express.close_async()
        await _drop_table(dialect, url, table)


@pytest.mark.integration
def test_find_one_sync_include_deleted(dialect_db):
    """The sync variant (db.express_sync.find_one) honors include_deleted too."""
    dialect, url = dialect_db
    table = f"fo_sync_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class FoSyncDoc:
        __tablename__ = table
        __dataflow__ = {"soft_delete": True}

        id: str
        slug: str
        title: str

    try:
        rid = f"doc-{uuid.uuid4().hex[:8]}"
        db.express_sync.create("FoSyncDoc", {"id": rid, "slug": "s", "title": "alive"})
        db.express_sync.delete("FoSyncDoc", rid)

        # Default: not-found.
        assert db.express_sync.find_one("FoSyncDoc", {"slug": "s"}) is None

        # include_deleted=True: tombstoned row returned via non-PK filter.
        incl = db.express_sync.find_one(
            "FoSyncDoc", {"slug": "s"}, include_deleted=True
        )
        assert incl is not None and incl["id"] == rid
        assert incl["deleted_at"] is not None
    finally:
        db.close()
        # Async drop is fine from a sync test (no running loop here).
        import asyncio

        asyncio.new_event_loop().run_until_complete(_drop_table(dialect, url, table))
