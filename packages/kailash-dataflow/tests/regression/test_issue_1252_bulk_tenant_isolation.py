"""Regression tests for issue #1252 — DataFlow bulk + upsert cross-tenant leak.

Issue #1252 (follow-up to #1249): in multi-tenant mode, DataFlow's BULK write
paths (``bulk_create`` / ``bulk_update`` / ``bulk_delete`` / ``bulk_upsert``)
provided NO tenant isolation. The bulk subsystem (``dataflow.features.bulk``,
reached via the node dispatch at ``nodes.py`` and ``db.bulk.*``) builds its own
SQL and does NOT route through ``_apply_tenant_isolation`` / ``QueryInterceptor``
(the single-record enforcement point #1249 fixed). It HAD inline tenant handling
but read the WRONG source:

- ``tenant_context.switch(t)`` sets the ``_current_tenant`` ContextVar, read by
  ``get_current_tenant_id()`` — the source the single-record path uses.
- The bulk subsystem read ``self.dataflow._tenant_context.get("tenant_id")`` — a
  SEPARATE legacy dict only populated by the unused ``set_tenant_context()``
  API. Under ``switch()`` that dict stays empty ``{}`` → ``tenant_id`` was never
  set → every bulk write persisted ``tenant_id = NULL`` (rows invisible to all
  tenants), AND bulk_update / bulk_delete ran with NO ``tenant_id`` in the WHERE
  (latent cross-tenant write/delete).

The fix reads ``get_current_tenant_id()`` in all four bulk ops, stamps
``tenant_id`` on create/upsert records, AND-s a bound ``tenant_id`` predicate
into the WHERE for update/delete, and FAILS CLOSED (raises) when no tenant is
bound under ``multi_tenant=True`` — mirroring the #1249 ``_apply_tenant_isolation``
guard per ``tenant-isolation.md`` MUST-2 + ``zero-tolerance.md`` Rule 3.
Single-tenant DataFlow (``multi_tenant=False``) keeps current behavior.

These are permanent regression tests — NEVER delete (``rules/testing.md``
Regression). The bulk subsystem methods are async (``db.bulk.*``), the exact
path the node dispatch routes to.
"""

import sqlite3
import tempfile

import pytest

from dataflow import DataFlow

# ---------------------------------------------------------------------------
# Tier-2: end-to-end bulk isolation through the real bulk subsystem (SQLite)
# ---------------------------------------------------------------------------


@pytest.fixture
def mt_db():
    """Multi-tenant DataFlow over file-backed SQLite + Feat model.

    Yields ``(db, tmpdir)`` and closes the DataFlow on teardown so the runner
    does not accumulate ``ResourceWarning: Unclosed LocalRuntime`` per
    ``rules/testing.md`` (fixtures yield + cleanup, never return).
    """
    tmpdir = tempfile.mkdtemp()
    db = DataFlow(
        f"sqlite:///{tmpdir}/mt.db",
        auto_migrate=True,
        multi_tenant=True,
        # Hermetic read-back (rules/testing.md § State Persistence Verification):
        # these #1252 regression tests verify the BULK subsystem's tenant
        # stamping/scoping and read every write back to assert real PERSISTED
        # state. The Express query cache auto-detects a process-shared Redis
        # whose keys (pre-#1606 shape dataflow:v2:<tenant>:<model>:<op>:<hash>)
        # carried a tenant dimension but NO database-instance dimension, so a
        # sibling test's
        # rows for the same model+tenant in a DIFFERENT tmpdir DB bleed into
        # this test's read-backs (a stale cached ``list Feat`` returned an id
        # from another DB, which a later bulk_upsert then targeted — clobbering
        # a real row). The bulk enforcement path is cache-independent, so
        # disabling the Express query cache here makes read-backs hit the real
        # DB without weakening any #1252 assertion. The un-DB-scoped cache-key
        # gap itself is a separate cross-SDK-keyspace follow-up.
        cache_enabled=False,
    )

    @db.model
    class Feat:
        entity_id: str
        score: int

    db._ensure_connected()
    db.tenant_context.register_tenant("acme", "A")
    db.tenant_context.register_tenant("globex", "G")
    try:
        yield db, tmpdir
    finally:
        db.close()


def _raw(tmpdir):
    con = sqlite3.connect(f"{tmpdir}/mt.db")
    try:
        return con.execute(
            "SELECT entity_id, score, tenant_id FROM feats ORDER BY tenant_id, score"
        ).fetchall()
    finally:
        con.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
async def test_bulk_create_isolation_no_cross_tenant_leak(mt_db):
    """Two tenants bulk_create rows; each reads back ONLY its own rows.

    This is the core #1252 leak: pre-fix every bulk_create row stored
    ``tenant_id = NULL`` so each tenant's filtered read returned nothing.
    """
    db, tmpdir = mt_db

    with db.tenant_context.switch("acme"):
        await db.bulk.bulk_create(
            "Feat", [{"entity_id": "a1", "score": 1}, {"entity_id": "a2", "score": 2}]
        )
    with db.tenant_context.switch("globex"):
        await db.bulk.bulk_create(
            "Feat",
            [{"entity_id": "g1", "score": 100}, {"entity_id": "g2", "score": 200}],
        )

    with db.tenant_context.switch("acme"):
        acme_scores = sorted(r.get("score") for r in db.express_sync.list("Feat", {}))
    with db.tenant_context.switch("globex"):
        globex_scores = sorted(r.get("score") for r in db.express_sync.list("Feat", {}))

    assert acme_scores == [1, 2], f"cross-tenant leak: acme saw {acme_scores}"
    assert globex_scores == [100, 200], f"cross-tenant leak: globex saw {globex_scores}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
async def test_bulk_create_persists_non_null_tenant_id(mt_db):
    """Every multi-tenant bulk_create row MUST persist a non-NULL tenant_id.

    Pre-fix the stale-dict read left tenant_id=None on every bulk_create row.
    """
    db, tmpdir = mt_db

    with db.tenant_context.switch("acme"):
        await db.bulk.bulk_create("Feat", [{"entity_id": "a", "score": 1}])
    with db.tenant_context.switch("globex"):
        await db.bulk.bulk_create("Feat", [{"entity_id": "g", "score": 2}])

    rows = _raw(tmpdir)
    assert all(r[2] is not None for r in rows), f"tenant_id stored as NULL: {rows}"
    assert {r[2] for r in rows} == {"acme", "globex"}, f"wrong tenant_id values: {rows}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
async def test_bulk_update_is_tenant_scoped(mt_db):
    """A filter-based bulk_update MUST only touch the bound tenant's rows.

    acme runs ``bulk_update`` with an EMPTY filter (update-all). Pre-fix this
    ran ``UPDATE feats SET score = 0`` with NO tenant predicate and would have
    zeroed globex's rows too (latent cross-tenant write).
    """
    db, tmpdir = mt_db

    with db.tenant_context.switch("acme"):
        await db.bulk.bulk_create(
            "Feat", [{"entity_id": "a1", "score": 10}, {"entity_id": "a2", "score": 20}]
        )
    with db.tenant_context.switch("globex"):
        await db.bulk.bulk_create(
            "Feat",
            [{"entity_id": "g1", "score": 100}, {"entity_id": "g2", "score": 200}],
        )

    # acme attempts to set ALL rows score=0 (empty filter, confirmed).
    with db.tenant_context.switch("acme"):
        await db.bulk.bulk_update(
            "Feat", filter_criteria={}, update_values={"score": 0}, confirmed=True
        )

    rows = _raw(tmpdir)
    acme_scores = sorted(r[1] for r in rows if r[2] == "acme")
    globex_scores = sorted(r[1] for r in rows if r[2] == "globex")
    assert acme_scores == [0, 0], f"same-tenant bulk_update failed: {rows}"
    assert globex_scores == [
        100,
        200,
    ], f"cross-tenant bulk_update leaked into globex: {rows}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
async def test_bulk_delete_is_tenant_scoped(mt_db):
    """A filter-based bulk_delete MUST only delete the bound tenant's rows.

    acme runs ``bulk_delete`` with an EMPTY filter (delete-all). Pre-fix this
    ran ``DELETE FROM feats`` with NO tenant predicate and would have deleted
    globex's rows too (latent cross-tenant delete).
    """
    db, tmpdir = mt_db

    with db.tenant_context.switch("acme"):
        await db.bulk.bulk_create(
            "Feat", [{"entity_id": "a1", "score": 10}, {"entity_id": "a2", "score": 20}]
        )
    with db.tenant_context.switch("globex"):
        await db.bulk.bulk_create(
            "Feat",
            [{"entity_id": "g1", "score": 100}, {"entity_id": "g2", "score": 200}],
        )

    # acme attempts to delete ALL rows (empty filter, confirmed).
    with db.tenant_context.switch("acme"):
        await db.bulk.bulk_delete("Feat", filter_criteria={}, confirmed=True)

    rows = _raw(tmpdir)
    assert not any(r[2] == "acme" for r in rows), f"acme rows not deleted: {rows}"
    globex_scores = sorted(r[1] for r in rows if r[2] == "globex")
    assert globex_scores == [
        100,
        200,
    ], f"cross-tenant bulk_delete removed globex's rows: {rows}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
async def test_bulk_upsert_round_trips_under_tenant_and_isolates(mt_db):
    """bulk_upsert round-trips under a tenant (conflict on the id PK) AND
    cannot touch another tenant's rows.

    Pre-fix the stale-dict read left tenant_id=NULL on every upserted row. The
    ON CONFLICT (id) target stays valid because ``id`` is the PK and
    ``tenant_id`` rides in the column list as just another INSERT/EXCLUDED
    column. acme updates its own row by id and inserts a fresh one; globex's
    rows are untouched.
    """
    db, tmpdir = mt_db

    with db.tenant_context.switch("acme"):
        await db.bulk.bulk_create("Feat", [{"entity_id": "a1", "score": 1}])
        acme_id = db.express_sync.list("Feat", {})[0]["id"]
    with db.tenant_context.switch("globex"):
        await db.bulk.bulk_create("Feat", [{"entity_id": "g1", "score": 100}])

    # acme upserts: update its existing row (by id) + insert a new one.
    with db.tenant_context.switch("acme"):
        result = await db.bulk.bulk_upsert(
            "Feat",
            [
                {"id": acme_id, "entity_id": "a1", "score": 999},
                {"id": acme_id + 1000, "entity_id": "a2", "score": 5},
            ],
            conflict_resolution="update",
        )
    assert result.get("success") is True, f"bulk_upsert failed: {result}"

    rows = _raw(tmpdir)
    # acme's row updated to 999, tenant intact.
    acme_rows = {r[0]: (r[1], r[2]) for r in rows if r[2] == "acme"}
    assert acme_rows.get("a1") == (999, "acme"), f"upsert round-trip failed: {rows}"
    assert acme_rows.get("a2") == (5, "acme"), f"upsert insert failed: {rows}"
    # globex untouched.
    globex_scores = sorted(r[1] for r in rows if r[2] == "globex")
    assert globex_scores == [100], f"bulk_upsert leaked into globex: {rows}"
    # No NULL tenant rows.
    assert all(
        r[2] is not None for r in rows
    ), f"bulk_upsert stored NULL tenant: {rows}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
async def test_bulk_create_without_bound_tenant_fails_closed(mt_db):
    """bulk_create under multi_tenant=True with NO bound tenant MUST raise AND
    MUST NOT persist a tenant_id=NULL row.

    Mirrors the #1249 fail-closed guard at the bulk subsystem layer per
    tenant-isolation.md MUST-2 + zero-tolerance.md Rule 3.
    """
    db, tmpdir = mt_db

    with pytest.raises(RuntimeError, match="no tenant is bound"):
        await db.bulk.bulk_create("Feat", [{"entity_id": "orphan", "score": 1}])

    rows = _raw(tmpdir)
    assert rows == [], f"fail-open: a row was persisted with no bound tenant: {rows}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
async def test_bulk_update_without_bound_tenant_fails_closed(mt_db):
    """bulk_update under multi_tenant=True with NO bound tenant MUST raise AND
    MUST NOT run an unscoped UPDATE.
    """
    db, tmpdir = mt_db
    with db.tenant_context.switch("acme"):
        await db.bulk.bulk_create("Feat", [{"entity_id": "a", "score": 10}])

    with pytest.raises(RuntimeError, match="no tenant is bound"):
        await db.bulk.bulk_update(
            "Feat", filter_criteria={}, update_values={"score": 0}, confirmed=True
        )

    # The bound acme row is untouched (no unscoped UPDATE ran).
    rows = _raw(tmpdir)
    assert [r[1] for r in rows] == [10], f"unscoped UPDATE ran: {rows}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
async def test_bulk_delete_without_bound_tenant_fails_closed(mt_db):
    """bulk_delete under multi_tenant=True with NO bound tenant MUST raise AND
    MUST NOT run an unscoped DELETE.
    """
    db, tmpdir = mt_db
    with db.tenant_context.switch("acme"):
        await db.bulk.bulk_create("Feat", [{"entity_id": "a", "score": 10}])

    with pytest.raises(RuntimeError, match="no tenant is bound"):
        await db.bulk.bulk_delete("Feat", filter_criteria={}, confirmed=True)

    rows = _raw(tmpdir)
    assert len(rows) == 1, f"unscoped DELETE ran: {rows}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
async def test_bulk_upsert_without_bound_tenant_fails_closed(mt_db):
    """bulk_upsert under multi_tenant=True with NO bound tenant MUST raise AND
    MUST NOT persist a tenant_id=NULL row.
    """
    db, tmpdir = mt_db

    with pytest.raises(RuntimeError, match="no tenant is bound"):
        await db.bulk.bulk_upsert("Feat", [{"id": 1, "entity_id": "x", "score": 5}])

    rows = _raw(tmpdir)
    assert rows == [], f"fail-open: a row was persisted with no bound tenant: {rows}"


# ---------------------------------------------------------------------------
# Single-tenant (multi_tenant=False) keeps current behavior — no stamping,
# no fail-closed, no tenant_id column.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
async def test_single_tenant_bulk_ops_unchanged():
    """A single-tenant DataFlow performs every bulk op without a bound tenant
    and without a tenant_id column — the fix MUST NOT change this behavior.
    """
    tmpdir = tempfile.mkdtemp()
    db = DataFlow(f"sqlite:///{tmpdir}/st.db", auto_migrate=True)  # single-tenant

    @db.model
    class Item:
        name: str
        qty: int

    db._ensure_connected()
    try:
        con = sqlite3.connect(f"{tmpdir}/st.db")
        cols = [c[1] for c in con.execute("PRAGMA table_info(items)").fetchall()]
        con.close()
        assert "tenant_id" not in cols, f"single-tenant model grew tenant_id: {cols}"

        r = await db.bulk.bulk_create(
            "Item", [{"name": "a", "qty": 1}, {"name": "b", "qty": 2}]
        )
        assert r.get("success") is True
        r2 = await db.bulk.bulk_update(
            "Item", filter_criteria={"name": "a"}, update_values={"qty": 99}
        )
        assert r2.get("success") is True
        r3 = await db.bulk.bulk_delete("Item", filter_criteria={"name": "b"})
        assert r3.get("success") is True

        rows = sorted((x["name"], x["qty"]) for x in db.express_sync.list("Item", {}))
        assert rows == [("a", 99)], f"single-tenant bulk ops misbehaved: {rows}"
    finally:
        db.close()
