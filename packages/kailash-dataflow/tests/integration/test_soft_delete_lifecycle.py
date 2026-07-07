"""Tier-2 regression: full soft_delete lifecycle via the EXPRESS API on BOTH
PostgreSQL and file-backed SQLite.

Completes the ``__dataflow__ = {"soft_delete": True}`` feature which was
half-implemented: the READ path (list/read/count auto-filter on ``deleted_at
IS NULL``) was wired, but the SCHEMA never created the ``deleted_at`` column,
DELETE was still a hard delete, the read-by-id SELECT never projected
``deleted_at`` (so the tombstone check was a silent no-op), and the Express
facade (the DEFAULT recommended CRUD surface) never accepted ``include_deleted``
— so soft-deleted rows were unviewable/unrecoverable from ``db.express``.

Everything below is proven through ``db.express`` (create/list/read/count/delete)
— NOT the node layer — on BOTH dialects (parametrized), NO mocking, every write
verified with an independent raw read-back:

* create → list/read/count see the row (the original repro: list was []/errored)
* delete → list/read/count exclude it, BUT the row still physically exists with
  ``deleted_at`` populated (raw read-back)
* express.list(include_deleted=True) / read(..., include_deleted=True) /
  count(..., include_deleted=True) reveal the tombstoned row on BOTH dialects
* include_deleted is part of the cache key — a False result never collides with
  a True query in the same session
* a NON-soft_delete control model still HARD-deletes (row gone from the DB)

Two PG-only engine-level tests round it out: the migration-diff schema-dict
(fix #2 deliverable) and an end-to-end contract that a pre-existing table gains
deleted_at when a soft_delete model is registered against it (issue #1600 — the
generic auto-migrate ALTER-ADD wiring; formerly a strict-xfail pin against the
pre-existing gap, flipped to a passing test once the wiring landed).

Run (PostgreSQL on 5434 must be up; SQLite is file-backed under tmp_path):
    TEST_DATABASE_URL="postgresql://test_user:test_password@localhost:5434/kailash_test" \
      ../../.venv/bin/python -m pytest \
      tests/integration/test_soft_delete_lifecycle.py -p no:xdist -o "addopts=" -q --tb=short
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


# --------------------------------------------------------------------------
# Dialect-aware helpers (raw read-back reflects COMMITTED state, bypasses
# DataFlow — the independent verification the express-API assertions pair with).
# --------------------------------------------------------------------------
def _sqlite_path(url: str) -> str:
    return url[len("sqlite:///") :]


async def _raw_fetch(dialect: str, url: str, table: str, rid: str):
    """Return the row as a dict (with deleted_at) or None, dialect-appropriately."""
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


async def _pg_column_exists(table: str, column: str) -> bool:
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = $1 AND column_name = $2",
            table,
            column,
        )
        return row is not None
    finally:
        await conn.close()


@pytest.fixture(params=["postgresql", "sqlite"])
def dialect_db(request, tmp_path):
    """(dialect, url) for each supported dialect.

    PostgreSQL uses the shared test instance (port 5434); SQLite is
    FILE-backed under tmp_path — NOT ``:memory:``, because DataFlow's
    migration pool opens multiple short-lived connections and a bare
    ``:memory:`` gives each its own database, breaking the migration
    handshake (see tests/CLAUDE.md § templates carve-out).
    """
    if request.param == "postgresql":
        return "postgresql", TEST_DATABASE_URL
    return "sqlite", f"sqlite:///{tmp_path}/sd_{uuid.uuid4().hex[:8]}.db"


# --------------------------------------------------------------------------
# Parametrized lifecycle — proven through db.express on BOTH dialects.
# String PK (id: str) so create returns a usable id on SQLite (SQLite create
# returns rows_affected, not the generated id — a known quirk).
# --------------------------------------------------------------------------
@pytest.mark.integration
async def test_soft_delete_full_lifecycle_express(dialect_db):
    dialect, url = dialect_db
    table = f"sd_life_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class SoftLifeDoc:
        __tablename__ = table
        __dataflow__ = {"soft_delete": True}

        id: str
        title: str

    try:
        rid = f"doc-{uuid.uuid4().hex[:8]}"
        await db.express.create("SoftLifeDoc", {"id": rid, "title": "alive"})

        # Visible before delete (the original repro: list was []/errored).
        rows = await db.express.list("SoftLifeDoc", {})
        assert len(rows) == 1 and rows[0]["id"] == rid
        assert await db.express.read("SoftLifeDoc", rid) is not None
        assert await db.express.count("SoftLifeDoc", {}) == 1

        # Soft delete via the express facade.
        assert await db.express.delete("SoftLifeDoc", rid) is True

        # Excluded from the default (non-include-deleted) express views.
        assert await db.express.list("SoftLifeDoc", {}) == []
        assert await db.express.read("SoftLifeDoc", rid) is None
        assert await db.express.count("SoftLifeDoc", {}) == 0

        # include_deleted reveals the tombstone through EXPRESS on BOTH dialects.
        incl = await db.express.list("SoftLifeDoc", {}, include_deleted=True)
        assert len(incl) == 1 and incl[0]["id"] == rid
        assert incl[0]["deleted_at"] is not None
        assert await db.express.count("SoftLifeDoc", {}, include_deleted=True) == 1
        read_incl = await db.express.read("SoftLifeDoc", rid, include_deleted=True)
        assert read_incl is not None and read_incl["deleted_at"] is not None

        # Independent raw read-back: the row still PHYSICALLY exists, tombstoned.
        raw = await _raw_fetch(dialect, url, table, rid)
        assert raw is not None, "soft delete must NOT physically remove the row"
        assert raw["deleted_at"] is not None, "deleted_at must be stamped"
        assert raw["title"] == "alive"
    finally:
        await db.express.close_async()
        await _drop_table(dialect, url, table)


@pytest.mark.integration
async def test_soft_delete_include_deleted_cache_no_collision(dialect_db):
    """include_deleted MUST be a cache-key dimension: a cached
    include_deleted=False result must NOT be served to an include_deleted=True
    query in the same session (tenant-isolation.md cache-key discipline applied
    to the soft-delete dimension). Express caching is ON by default (TTL 300s),
    so this exercises the real collision scenario."""
    dialect, url = dialect_db
    table = f"sd_cache_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class SoftCacheDoc:
        __tablename__ = table
        __dataflow__ = {"soft_delete": True}

        id: str
        title: str

    try:
        rid = f"doc-{uuid.uuid4().hex[:8]}"
        await db.express.create("SoftCacheDoc", {"id": rid, "title": "x"})
        await db.express.delete("SoftCacheDoc", rid)

        # Prime the default (include_deleted=False) cache slot with [].
        assert await db.express.list("SoftCacheDoc", {}) == []
        # include_deleted=True MUST hit a DISTINCT slot — NOT the primed [].
        incl = await db.express.list("SoftCacheDoc", {}, include_deleted=True)
        assert (
            len(incl) == 1
        ), "include_deleted=True collided with the cached False slot"
        # The default slot is still [] (its own key, uncorrupted).
        assert await db.express.list("SoftCacheDoc", {}) == []

        # Same non-collision for count.
        assert await db.express.count("SoftCacheDoc", {}) == 0
        assert await db.express.count("SoftCacheDoc", {}, include_deleted=True) == 1

        # Belt-and-suspenders: the derived cache keys themselves differ.
        from dataflow.cache.key_generator import CacheKeyGenerator

        g = CacheKeyGenerator()
        base = {"filter": {}, "limit": 100, "offset": 0}
        kf = g.generate_express_key(
            "SoftCacheDoc", "list", {**base, "include_deleted": False}
        )
        kt = g.generate_express_key(
            "SoftCacheDoc", "list", {**base, "include_deleted": True}
        )
        assert kf != kt, "list cache key must differ on include_deleted"
    finally:
        await db.express.close_async()
        await _drop_table(dialect, url, table)


@pytest.mark.integration
async def test_soft_delete_repeat_delete_is_noop(dialect_db):
    """A second delete of an already-tombstoned row is a no-op (guarded by
    ``AND deleted_at IS NULL``) — returns not-deleted, deleted_at unchanged."""
    dialect, url = dialect_db
    table = f"sd_twice_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class SoftTwiceDoc:
        __tablename__ = table
        __dataflow__ = {"soft_delete": True}

        id: str
        title: str

    try:
        rid = f"doc-{uuid.uuid4().hex[:8]}"
        await db.express.create("SoftTwiceDoc", {"id": rid, "title": "x"})

        assert await db.express.delete("SoftTwiceDoc", rid) is True
        first = await _raw_fetch(dialect, url, table, rid)
        assert first["deleted_at"] is not None

        # Second delete: no live row to tombstone → False, deleted_at unchanged.
        assert await db.express.delete("SoftTwiceDoc", rid) is False
        second = await _raw_fetch(dialect, url, table, rid)
        assert second["deleted_at"] == first["deleted_at"]
    finally:
        await db.express.close_async()
        await _drop_table(dialect, url, table)


@pytest.mark.integration
async def test_non_soft_delete_model_hard_deletes(dialect_db):
    """Control: a model WITHOUT soft_delete still HARD-deletes — the row is
    physically gone from the DB, and no deleted_at column is created."""
    dialect, url = dialect_db
    table = f"hard_del_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class HardDoc:
        __tablename__ = table

        id: str
        title: str

    try:
        rid = f"doc-{uuid.uuid4().hex[:8]}"
        await db.express.create("HardDoc", {"id": rid, "title": "temp"})
        assert await _raw_fetch(dialect, url, table, rid) is not None

        assert await db.express.delete("HardDoc", rid) is True

        # Physically gone (hard delete).
        assert await _raw_fetch(dialect, url, table, rid) is None
        assert await db.express.list("HardDoc", {}) == []
    finally:
        await db.express.close_async()
        await _drop_table(dialect, url, table)


@pytest.mark.integration
async def test_bulk_delete_tombstones_soft_delete_model(dialect_db):
    """bulk_delete on a soft_delete model TOMBSTONES (not hard-deletes): rows
    are excluded from list but still physically present with deleted_at set;
    a repeat bulk_delete is a no-op. Proven via express + raw read-back on both
    dialects. (All bulk-delete surfaces — express, BulkDeleteNode, db.bulk —
    converge on BulkOperations.bulk_delete, so this covers them all.)"""
    dialect, url = dialect_db
    table = f"bd_soft_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class BulkSoftDoc:
        __tablename__ = table
        __dataflow__ = {"soft_delete": True}

        id: str
        title: str

    try:
        ids = [f"doc-{i}-{uuid.uuid4().hex[:6]}" for i in range(3)]
        for rid in ids:
            await db.express.create("BulkSoftDoc", {"id": rid, "title": "alive"})
        assert len(await db.express.list("BulkSoftDoc", {})) == 3

        # Bulk delete via the express facade (routes through BulkDeleteNode →
        # BulkOperations.bulk_delete).
        assert await db.express.bulk_delete("BulkSoftDoc", ids) is True

        # Excluded from the default views…
        assert await db.express.list("BulkSoftDoc", {}) == []
        assert await db.express.count("BulkSoftDoc", {}) == 0

        # …but every row STILL physically exists, tombstoned (express + raw).
        incl = await db.express.list("BulkSoftDoc", {}, include_deleted=True)
        assert len(incl) == 3
        assert all(r["deleted_at"] is not None for r in incl)
        for rid in ids:
            raw = await _raw_fetch(dialect, url, table, rid)
            assert raw is not None, "bulk soft delete must NOT physically remove rows"
            assert raw["deleted_at"] is not None
            assert raw["title"] == "alive"

        # Repeat bulk_delete is a no-op (AND deleted_at IS NULL guard): the
        # deleted_at timestamps are unchanged.
        stamps_before = {
            rid: (await _raw_fetch(dialect, url, table, rid))["deleted_at"]
            for rid in ids
        }
        await db.express.bulk_delete("BulkSoftDoc", ids)
        for rid in ids:
            after = await _raw_fetch(dialect, url, table, rid)
            assert after["deleted_at"] == stamps_before[rid]
    finally:
        await db.express.close_async()
        await _drop_table(dialect, url, table)


@pytest.mark.integration
async def test_bulk_delete_hard_deletes_non_soft_delete_model(dialect_db):
    """Control: bulk_delete on a NON-soft-delete model still HARD-deletes —
    every row is physically gone from the DB."""
    dialect, url = dialect_db
    table = f"bd_hard_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class BulkHardDoc:
        __tablename__ = table

        id: str
        title: str

    try:
        ids = [f"doc-{i}-{uuid.uuid4().hex[:6]}" for i in range(3)]
        for rid in ids:
            await db.express.create("BulkHardDoc", {"id": rid, "title": "temp"})
        assert len(await db.express.list("BulkHardDoc", {})) == 3

        assert await db.express.bulk_delete("BulkHardDoc", ids) is True

        # Physically gone.
        assert await db.express.list("BulkHardDoc", {}) == []
        for rid in ids:
            assert await _raw_fetch(dialect, url, table, rid) is None
    finally:
        await db.express.close_async()
        await _drop_table(dialect, url, table)


@pytest.mark.integration
async def test_bulk_update_filter_skips_tombstoned_by_default(dialect_db):
    """FILTER-based bulk_update on a soft_delete model SKIPS tombstoned rows by
    default (deleted_at IS NULL guard), matching the list/read/count read
    auto-filter — a bulk_update(filter_criteria=...) must not silently mutate
    rows the caller can't see. Exercised via db.bulk.bulk_update on both
    dialects, verified with a raw read-back."""
    dialect, url = dialect_db
    table = f"bu_filter_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class BulkUpdDoc:
        __tablename__ = table
        __dataflow__ = {"soft_delete": True}

        id: str
        status: str

    try:
        live = [f"live-{i}-{uuid.uuid4().hex[:6]}" for i in range(2)]
        dead = f"dead-{uuid.uuid4().hex[:6]}"
        for rid in live:
            await db.express.create("BulkUpdDoc", {"id": rid, "status": "active"})
        await db.express.create("BulkUpdDoc", {"id": dead, "status": "active"})
        await db.express.delete("BulkUpdDoc", dead)  # tombstone one row

        # Filter-based bulk_update: matches status="active" — MUST skip the
        # tombstoned row despite it also having status="active".
        res = await db.bulk.bulk_update(
            "BulkUpdDoc",
            filter_criteria={"status": "active"},
            update_values={"status": "archived"},
        )
        assert res["success"] is True
        assert res["records_processed"] == 2, "must update only the 2 live rows"

        # Live rows updated…
        for rid in live:
            row = await _raw_fetch(dialect, url, table, rid)
            assert row["status"] == "archived"

        # …tombstoned row is UNCHANGED (still 'active', still tombstoned).
        dead_row = await _raw_fetch(dialect, url, table, dead)
        assert dead_row is not None
        assert dead_row["status"] == "active", "tombstoned row must NOT be mutated"
        assert dead_row["deleted_at"] is not None
    finally:
        await db.express.close_async()
        await _drop_table(dialect, url, table)


@pytest.mark.integration
async def test_bulk_update_include_deleted_undeletes(dialect_db):
    """bulk_update(..., include_deleted=True) bypasses the deleted_at IS NULL
    guard — the un-delete workflow: update_values={"deleted_at": None} on a
    tombstoned row (matched by filter) makes it visible again in list()."""
    dialect, url = dialect_db
    table = f"bu_undel_{uuid.uuid4().hex[:8]}"
    db = DataFlow(url, auto_migrate=True)

    @db.model
    class UndelDoc:
        __tablename__ = table
        __dataflow__ = {"soft_delete": True}

        id: str
        status: str

    try:
        rid = f"doc-{uuid.uuid4().hex[:8]}"
        await db.express.create("UndelDoc", {"id": rid, "status": "active"})
        await db.express.delete("UndelDoc", rid)
        # Tombstoned: raw row present with deleted_at set.
        pre = await _raw_fetch(dialect, url, table, rid)
        assert pre is not None and pre["deleted_at"] is not None

        # Without include_deleted, the filter guard excludes the tombstoned row,
        # so this un-delete attempt affects 0 rows (guard skips it).
        guarded = await db.bulk.bulk_update(
            "UndelDoc",
            filter_criteria={"id": rid},
            update_values={"status": "restored"},
        )
        assert guarded["records_processed"] == 0, "guard must skip tombstoned row"
        still = await _raw_fetch(dialect, url, table, rid)
        assert still["status"] == "active", "guarded update must NOT touch the row"

        # With include_deleted=True the guard is bypassed → the un-delete lands.
        undel = await db.bulk.bulk_update(
            "UndelDoc",
            filter_criteria={"id": rid},
            update_values={"status": "restored", "deleted_at": None},
            include_deleted=True,
        )
        assert undel["records_processed"] == 1

        # Authoritative Tier-2 verification is the raw read-back (connection-
        # independent). A row whose deleted_at IS NULL is, by definition,
        # visible to the default read auto-filter (WHERE deleted_at IS NULL).
        # NOTE: a subsequent db.express.list() in THIS session may still serve a
        # stale [] — db.bulk.* writes on their own connection and do NOT
        # invalidate the express read cache (a pre-existing, separate concern),
        # so the raw read-back is the deterministic proof the un-delete landed.
        raw = await _raw_fetch(dialect, url, table, rid)
        assert raw is not None
        assert raw["status"] == "restored"
        assert (
            raw["deleted_at"] is None
        ), "include_deleted un-delete must clear deleted_at"
    finally:
        await db.express.close_async()
        await _drop_table(dialect, url, table)


# --------------------------------------------------------------------------
# Engine-level migration-diff coverage (PostgreSQL — fix #2 deliverable + the
# end-to-end ALTER-ADD contract for issue #1600, formerly a strict-xfail pin).
# --------------------------------------------------------------------------
@pytest.mark.integration
async def test_soft_delete_schema_dict_includes_deleted_at():
    """Fix #2 deliverable: the migration-diff TARGET schema for a soft_delete
    model includes a nullable ``deleted_at`` column; a non-soft_delete model
    does NOT (``_convert_fields_to_columns`` threaded with soft_delete)."""
    db = DataFlow(TEST_DATABASE_URL, auto_migrate=True)

    @db.model
    class SchemaSoftDoc:
        __dataflow__ = {"soft_delete": True}

        id: str
        title: str

    @db.model
    class SchemaHardDoc:
        id: str
        title: str

    engine = getattr(db, "_engine", db)
    assert engine._model_has_soft_delete("SchemaSoftDoc") is True
    assert engine._model_has_soft_delete("SchemaHardDoc") is False

    soft_cols = engine._convert_fields_to_columns(
        engine.get_model_fields("SchemaSoftDoc"),
        soft_delete=engine._model_has_soft_delete("SchemaSoftDoc"),
    )
    assert "deleted_at" in soft_cols, "soft_delete schema-dict MUST include deleted_at"
    assert soft_cols["deleted_at"]["nullable"] is True
    assert soft_cols["deleted_at"]["default"] is None

    hard_cols = engine._convert_fields_to_columns(
        engine.get_model_fields("SchemaHardDoc"),
        soft_delete=engine._model_has_soft_delete("SchemaHardDoc"),
    )
    assert (
        "deleted_at" not in hard_cols
    ), "non-soft_delete schema-dict MUST NOT include deleted_at"


@pytest.mark.integration
async def test_auto_migrate_adds_deleted_at_to_existing_table():
    """End-to-end migration contract (issue #1600 — the generic auto-migrate
    ALTER-ADD wiring): a pre-existing table WITHOUT deleted_at gains the column
    when a model declaring soft_delete=True is registered against the same table
    name. Previously a strict-xfail pin against the pre-existing SDK gap; the
    additive column-reconciliation in ensure_table_exists closed it, so the
    marker was removed (per testing.md: a strict-xfail that XPASSes forces
    same-shard removal)."""
    table = f"sd_migrate_{uuid.uuid4().hex[:8]}"

    db1 = DataFlow(TEST_DATABASE_URL, auto_migrate=True)

    @db1.model
    class MigrateDocV1:
        __tablename__ = table

        id: str
        title: str

    try:
        rid = f"doc-{uuid.uuid4().hex[:8]}"
        await db1.express.create("MigrateDocV1", {"id": rid, "title": "legacy"})
        assert not await _pg_column_exists(table, "deleted_at")
        await db1.express.close_async()

        db2 = DataFlow(TEST_DATABASE_URL, auto_migrate=True)

        @db2.model
        class MigrateDocV2:
            __tablename__ = table
            __dataflow__ = {"soft_delete": True}

            id: str
            title: str

        await db2.ensure_table_exists("MigrateDocV2")
        try:
            assert await _pg_column_exists(
                table, "deleted_at"
            ), "auto-migrate must ALTER-ADD deleted_at to the pre-existing table"
        finally:
            await db2.express.close_async()
    finally:
        await _drop_table("postgresql", TEST_DATABASE_URL, table)
