# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the issue #1526 BULK follow-up — actionable cross-tenant
natural-key collision diagnostic on the ``bulk_create`` / ``bulk_upsert`` paths.

PR #1646 (issue #1526, Option B) added an actionable
:class:`TenantNaturalKeyCollisionError` raised on the SINGLE-record
create/upsert path when a ``multi_tenant`` natural-key collision occurs. The
bulk paths, however, use partial-failure-dict semantics (they RETURN a failure
dict, they do NOT raise), and were NOT wired for the same actionable
diagnostic — a bulk-path natural-key collision surfaced only the raw
(sanitized) driver message.

This follow-up wires the SAME actionable, tenant-scoped, no-cross-tenant-leak
diagnostic into the bulk partial-failure dict WITHOUT converting the bulk
contract to raise-on-first-error. The bulk collision entry:

  * names ONLY the caller's own ``tenant_id`` + the caller's own supplied ids
    (never another tenant's id or row data — tenant isolation preserved);
  * uses a TENANT-SCOPED read (``cache_ttl=0``) to distinguish a same-tenant
    duplicate (keep the raw error — no over-broadening) from a genuine
    cross-tenant collision;
  * is built by the SAME shared message builder the single-path exception
    uses, so the two surfaces never drift.

Tier-2 regression tests against REAL databases (no mocking): SQLite always,
PostgreSQL when the shared Docker infra is reachable. Every write is verified
against a real backend and the returned failure dict is asserted for both the
actionable diagnostic AND the cross-tenant-no-leak property.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time

import pytest

from dataflow import DataFlow

# Shared SDK Docker PostgreSQL infra (port 5434), same as the #1518/#1526 suites.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)

# A title unique to tenant-a used to assert the cross-tenant-no-leak property:
# it must NEVER appear anywhere in tenant-b's failure dict.
TENANT_A_SECRET_TITLE = "TENANT-A-SECRET-TITLE-DO-NOT-LEAK"


def _uid(prefix: str = "doc") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


def _sqlite_db():
    tmpdir = tempfile.mkdtemp()
    path = f"{tmpdir}/mt1526bulk_{int(time.time() * 1_000_000)}.db"
    return DataFlow(f"sqlite:///{path}", auto_migrate=True, multi_tenant=True)


def _pg_available() -> bool:
    import socket

    host, port = "localhost", 5434
    if TEST_DATABASE_URL.startswith("postgresql://"):
        try:
            after_at = TEST_DATABASE_URL.split("@", 1)[1]
            hostport = after_at.split("/", 1)[0]
            host = hostport.split(":", 1)[0]
            port = int(hostport.split(":", 1)[1]) if ":" in hostport else 5432
        except Exception:
            pass
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _assert_actionable_collision(result, *, caller_tenant: str, colliding_id: str):
    """Assert ``result`` is a bulk failure DICT (never raised) carrying the
    actionable, tenant-scoped collision diagnostic naming ONLY ``caller_tenant``
    + the caller's own ``colliding_id`` — and never tenant-a's identity/data."""
    # Partial-failure-dict semantics preserved: a dict, not a raise.
    assert isinstance(result, dict)
    assert result.get("success") is False

    collision = result.get("collision")
    assert collision is not None, f"no collision diagnostic in {result!r}"
    assert collision["error_type"] == "TenantNaturalKeyCollisionError"
    assert collision["tenant_id"] == caller_tenant
    assert colliding_id in [str(x) for x in collision["colliding_ids"]]

    # The failure dict's error is the SAME actionable message the single-path
    # exception raises (built by the shared builder).
    msg = str(result.get("error"))
    assert caller_tenant in msg
    assert "surrogate" in msg
    assert "schema-per-tenant" in msg
    assert "IsolationStrategy.SCHEMA" in msg

    # Cross-tenant-no-leak: tenant-b's failure dict MUST NOT reveal tenant-a's
    # identity or row data anywhere in the returned structure.
    blob = repr(result)
    assert "tenant-a" not in blob
    assert TENANT_A_SECRET_TITLE not in blob


# ---------------------------------------------------------------------------
# Tier-2: bulk_create through the express partial-failure-dict path (real DB)
# ---------------------------------------------------------------------------


async def _run_bulk_create_scenario(db: DataFlow) -> None:
    @db.model
    class Doc:
        id: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    db.tenant_context.register_tenant("tenant-b", "B")

    shared_id = _uid("doc")
    new_id = _uid("doc-new")

    # tenant-a establishes the natural key with a SECRET title.
    with db.tenant_context.switch("tenant-a"):
        created = await db.express.create(
            "Doc", {"id": shared_id, "title": TENANT_A_SECRET_TITLE}
        )
        assert created["id"] == shared_id

    # tenant-b bulk_creates the SAME natural key (+ a genuinely new id) →
    # partial-failure dict carrying the actionable collision diagnostic.
    with db.tenant_context.switch("tenant-b"):
        result = await db.express.bulk_create(
            "Doc",
            [{"id": shared_id, "title": "B"}, {"id": new_id, "title": "B2"}],
        )

    _assert_actionable_collision(
        result, caller_tenant="tenant-b", colliding_id=shared_id
    )
    # The caller's OWN new id may appear as a candidate (at-least-one framing);
    # that is the caller's own supplied value, never a cross-tenant leak.
    assert new_id in [str(x) for x in result["collision"]["colliding_ids"]]


async def _run_bulk_create_same_tenant_duplicate(db: DataFlow) -> None:
    """A same-tenant bulk duplicate MUST keep the ordinary raw-error path — it
    MUST NOT be converted into a cross-tenant collision claim (no
    over-broadening), mirroring the single-record discipline."""

    @db.model
    class Doc:
        id: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")

    dup_id = _uid("doc")
    with db.tenant_context.switch("tenant-a"):
        await db.express.create("Doc", {"id": dup_id, "title": "A"})
        # tenant-a re-inserting its OWN id (+ a new id) → same-tenant duplicate.
        result = await db.express.bulk_create(
            "Doc",
            [{"id": dup_id, "title": "A2"}, {"id": _uid("doc-new"), "title": "A3"}],
        )

    assert isinstance(result, dict)
    assert result.get("success") is False
    # No cross-tenant claim — the current tenant OWNS the duplicated id.
    assert "collision" not in result
    assert "surrogate" not in str(result.get("error"))


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.sqlite
async def test_issue_1526_bulk_create_cross_tenant_collision_sqlite(caplog):
    """SQLite (always-on): a cross-tenant bulk_create collision surfaces the
    actionable diagnostic in the failure dict + emits a WARN partial-failure
    log (observability.md Rule 7); it does NOT raise and does NOT leak."""
    db = _sqlite_db()
    try:
        with caplog.at_level(logging.WARNING):
            await _run_bulk_create_scenario(db)
        assert any(
            "bulk_create.partial_failure" in rec.message
            or rec.getMessage() == "bulk_create.partial_failure"
            for rec in caplog.records
        ), "expected a bulk_create.partial_failure WARN"
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.sqlite
async def test_issue_1526_bulk_create_same_tenant_duplicate_sqlite():
    """SQLite (always-on): a same-tenant bulk duplicate keeps the raw error
    path — no over-broadening into a cross-tenant collision claim."""
    db = _sqlite_db()
    try:
        await _run_bulk_create_same_tenant_duplicate(db)
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.postgresql
@pytest.mark.requires_postgres
async def test_issue_1526_bulk_create_cross_tenant_collision_postgres():
    """PostgreSQL (when the shared Docker infra is reachable): the same
    contract holds against the ``<table>_pkey`` violation shape."""
    if not _pg_available():
        pytest.skip("PostgreSQL infra (localhost:5434) not reachable")
    db = DataFlow(TEST_DATABASE_URL, auto_migrate=True, multi_tenant=True)
    try:
        await _run_bulk_create_scenario(db)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tier-2: bulk_upsert through the express partial-failure-dict path (real DB)
# ---------------------------------------------------------------------------


async def _run_bulk_upsert_scenario(db: DataFlow) -> None:
    """A bulk_upsert whose conflict target is a UNIQUE column (``code``) with a
    NEW value, while the ``id`` PK collides cross-tenant → the INSERT fails on
    the PK (not the conflict target) → whole-batch failure dict carrying the
    actionable collision diagnostic."""

    @db.model
    class Account:
        id: str
        code: str
        title: str
        # A real UNIQUE index makes ``code`` a valid conflict target; the id PK
        # is what collides cross-tenant.
        __dataflow__ = {"indexes": [{"fields": ["code"], "unique": True}]}

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    db.tenant_context.register_tenant("tenant-b", "B")

    shared_id = _uid("acct")
    with db.tenant_context.switch("tenant-a"):
        await db.express.create(
            "Account",
            {"id": shared_id, "code": _uid("code-a"), "title": TENANT_A_SECRET_TITLE},
        )

    # tenant-b upserts the SAME id with a NEW (non-conflicting) code → the
    # conflict target does not match, the INSERT hits the cross-tenant id PK.
    with db.tenant_context.switch("tenant-b"):
        result = await db.express.bulk_upsert(
            "Account",
            [{"id": shared_id, "code": _uid("code-b"), "title": "B"}],
            conflict_on=["code"],
        )

    _assert_actionable_collision(
        result, caller_tenant="tenant-b", colliding_id=shared_id
    )


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.sqlite
async def test_issue_1526_bulk_upsert_cross_tenant_collision_sqlite(caplog):
    """SQLite (always-on): a cross-tenant bulk_upsert PK collision surfaces the
    actionable diagnostic in the failure dict + emits a WARN partial-failure
    log; it does NOT raise and does NOT leak tenant-a's data."""
    db = _sqlite_db()
    try:
        with caplog.at_level(logging.WARNING):
            await _run_bulk_upsert_scenario(db)
        assert any(
            "bulk_upsert.partial_failure" in rec.getMessage() for rec in caplog.records
        ), "expected a bulk_upsert.partial_failure WARN"
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.postgresql
@pytest.mark.requires_postgres
async def test_issue_1526_bulk_upsert_cross_tenant_collision_postgres():
    """PostgreSQL (when the shared Docker infra is reachable): the same
    bulk_upsert contract holds against the ``<table>_pkey`` violation shape."""
    if not _pg_available():
        pytest.skip("PostgreSQL infra (localhost:5434) not reachable")
    db = DataFlow(TEST_DATABASE_URL, auto_migrate=True, multi_tenant=True)
    try:
        await _run_bulk_upsert_scenario(db)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tier-2: shared helper — no-leak + no-over-broadening directly against a REAL
# database (real tenant-scoped reads, real QueryInterceptor — no mocking). This
# is the exact disambiguation BOTH bulk paths invoke.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.sqlite
async def test_issue_1526_bulk_collision_helper_no_leak_and_no_over_broadening():
    """The shared ``_maybe_bulk_tenant_natural_key_collision`` helper, exercised
    against a REAL SQLite multi_tenant DataFlow, (a) produces the diagnostic for
    a genuine cross-tenant case naming ONLY the caller's own tenant + ids with
    no cross-tenant leak, (b) declines for a same-tenant-owned id (no
    over-broadening), and (c) declines for an intra-batch duplicate id (a
    caller-side duplicate, not a cross-tenant collision)."""
    db = _sqlite_db()
    try:

        @db.model
        class Doc:
            id: str
            title: str

        db._ensure_connected()
        db.tenant_context.register_tenant("tenant-a", "A")
        db.tenant_context.register_tenant("tenant-b", "B")

        shared_id = _uid("doc")
        new_id = _uid("doc-new")
        with db.tenant_context.switch("tenant-a"):
            await db.express.create(
                "Doc", {"id": shared_id, "title": TENANT_A_SECRET_TITLE}
            )

        pk_err = "UNIQUE constraint failed: docs.id"

        # (a) cross-tenant: tenant-b owns neither id → diagnostic, no leak.
        with db.tenant_context.switch("tenant-b"):
            diag = await db.express._maybe_bulk_tenant_natural_key_collision(
                "Doc",
                [{"id": shared_id, "title": "B"}, {"id": new_id, "title": "B2"}],
                pk_err,
            )
        assert diag is not None
        assert diag["tenant_id"] == "tenant-b"
        assert shared_id in [str(x) for x in diag["colliding_ids"]]
        assert "tenant-a" not in repr(diag)
        assert TENANT_A_SECRET_TITLE not in repr(diag)

        # (b) same-tenant: tenant-a OWNS shared_id → decline (no over-broadening).
        with db.tenant_context.switch("tenant-a"):
            diag_same = await db.express._maybe_bulk_tenant_natural_key_collision(
                "Doc",
                [
                    {"id": shared_id, "title": "A2"},
                    {"id": _uid("doc-x"), "title": "A3"},
                ],
                pk_err,
            )
        assert diag_same is None

        # (c) intra-batch duplicate id (same tenant) → decline (caller-side dup,
        # not a cross-tenant collision — no false positive).
        dup = _uid("doc-dup")
        with db.tenant_context.switch("tenant-b"):
            diag_dup = await db.express._maybe_bulk_tenant_natural_key_collision(
                "Doc",
                [{"id": dup, "title": "B"}, {"id": dup, "title": "B-again"}],
                pk_err,
            )
        assert diag_dup is None
    finally:
        db.close()


# ===========================================================================
# CROSS-TENANT WRITE BREACH (conflict_on=["id"]) — the confirmed data-theft
# path. Tenant B ``bulk_upsert([{id:X}], conflict_on=["id"])`` (or single-record
# ``upsert``) MUST NOT overwrite / re-own tenant A's row. Assertions read the
# RAW table across ALL tenants (NOT db.express.read, which is tenant-scoped and
# masks the theft). See rules/tenant-isolation.md.
# ===========================================================================


async def _raw_read_all(db: DataFlow, table: str) -> list:
    """Read the RAW table across ALL tenants (bypasses tenant-scoped reads).

    NOT a mock: a real SELECT against the same backend db.express writes to.
    db.express.read is tenant-scoped (QueryInterceptor), so it CANNOT observe a
    cross-tenant theft — only a tenant-blind raw read can.
    """
    dbt = db._detect_database_type()
    node = db._get_or_create_async_sql_node(dbt)
    res = await node.async_run(
        query=f"SELECT id, tenant_id, title FROM {table}",
        params=[],
        fetch_mode="all",
        validate_queries=False,
        transaction_mode="auto",
    )
    return res.get("result", {}).get("data", []) or []


async def _assert_tenant_a_row_intact(db: DataFlow, table: str, shared_id: str):
    """Tenant A's row is UNCHANGED and tenant B did NOT gain the row."""
    rows = await _raw_read_all(db, table)
    matches = [r for r in rows if str(r["id"]) == shared_id]
    assert len(matches) == 1, f"expected exactly one row for id={shared_id}: {rows!r}"
    row = matches[0]
    # Secret intact, ownership NOT flipped, title NOT overwritten.
    assert row["tenant_id"] == "tenant-a", f"tenant_id was flipped: {row!r}"
    assert row["title"] == TENANT_A_SECRET_TITLE, f"title was overwritten: {row!r}"


async def _run_bulk_id_conflict_scenario(db: DataFlow) -> None:
    @db.model
    class Doc:
        id: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    db.tenant_context.register_tenant("tenant-b", "B")

    shared_id = _uid("doc")
    with db.tenant_context.switch("tenant-a"):
        await db.express.create(
            "Doc", {"id": shared_id, "title": TENANT_A_SECRET_TITLE}
        )

    # THE BREACH: tenant B upserts the SAME id on the id PK conflict target.
    with db.tenant_context.switch("tenant-b"):
        result = await db.express.bulk_upsert(
            "Doc", [{"id": shared_id, "title": "B-STOLEN"}], conflict_on=["id"]
        )

    # Fail-closed: actionable, tenant-scoped collision diagnostic, no leak.
    _assert_actionable_collision(
        result, caller_tenant="tenant-b", colliding_id=shared_id
    )
    # And — the load-bearing assertion — tenant A's row was NOT stolen.
    await _assert_tenant_a_row_intact(db, "docs", shared_id)


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.sqlite
async def test_issue_bulk_upsert_id_conflict_no_cross_tenant_theft_sqlite(caplog):
    """SQLite: tenant B bulk_upsert(conflict_on=['id']) on tenant A's id does NOT
    overwrite/steal A's row; surfaces the actionable collision diagnostic +
    a WARN partial-failure log."""
    db = _sqlite_db()
    try:
        with caplog.at_level(logging.WARNING):
            await _run_bulk_id_conflict_scenario(db)
        assert any(
            "bulk_upsert.partial_failure" in rec.getMessage() for rec in caplog.records
        ), "expected a bulk_upsert.partial_failure WARN"
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.postgresql
@pytest.mark.requires_postgres
async def test_issue_bulk_upsert_id_conflict_no_cross_tenant_theft_postgres():
    """PostgreSQL: same fail-closed contract against the native ON CONFLICT path
    (the real-DB-verified breach shape)."""
    if not _pg_available():
        pytest.skip("PostgreSQL infra (localhost:5434) not reachable")
    db = DataFlow(TEST_DATABASE_URL, auto_migrate=True, multi_tenant=True)
    try:
        await _run_bulk_id_conflict_scenario(db)
    finally:
        db.close()


async def _run_single_id_conflict_scenario(db: DataFlow) -> None:
    from dataflow.core.exceptions import TenantNaturalKeyCollisionError

    @db.model
    class Doc:
        id: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    db.tenant_context.register_tenant("tenant-b", "B")

    shared_id = _uid("doc")
    with db.tenant_context.switch("tenant-a"):
        await db.express.create(
            "Doc", {"id": shared_id, "title": TENANT_A_SECRET_TITLE}
        )

    # Single-record sibling: tenant B upsert on tenant A's id MUST fail closed.
    with db.tenant_context.switch("tenant-b"):
        with pytest.raises(Exception) as exc_info:
            await db.express.upsert(
                "Doc", {"id": shared_id, "title": "B-STOLEN"}, conflict_on=["id"]
            )
    # A caller-actionable raise (never a silent success). On the PG native
    # ON CONFLICT path this is the typed TenantNaturalKeyCollisionError; the
    # SQLite tenant-scoped WHERE-precheck raises a PK-unique NodeExecutionError.
    raised = exc_info.value
    assert isinstance(raised, (TenantNaturalKeyCollisionError, Exception))
    assert not isinstance(raised, AssertionError)
    # The row is intact regardless of which fail-closed raise fired.
    await _assert_tenant_a_row_intact(db, "docs", shared_id)


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.sqlite
async def test_issue_single_upsert_id_conflict_no_cross_tenant_theft_sqlite():
    """SQLite: single-record upsert(conflict_on=['id']) fails closed (no theft)."""
    db = _sqlite_db()
    try:
        await _run_single_id_conflict_scenario(db)
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.postgresql
@pytest.mark.requires_postgres
async def test_issue_single_upsert_id_conflict_no_cross_tenant_theft_postgres():
    """PostgreSQL: single-record upsert raises TenantNaturalKeyCollisionError on
    the native ON CONFLICT path — the previously-breached data-corruption case."""
    if not _pg_available():
        pytest.skip("PostgreSQL infra (localhost:5434) not reachable")
    from dataflow.core.exceptions import TenantNaturalKeyCollisionError

    db = DataFlow(TEST_DATABASE_URL, auto_migrate=True, multi_tenant=True)
    try:

        @db.model
        class Doc:
            id: str
            title: str

        db._ensure_connected()
        db.tenant_context.register_tenant("tenant-a", "A")
        db.tenant_context.register_tenant("tenant-b", "B")
        shared_id = _uid("doc")
        with db.tenant_context.switch("tenant-a"):
            await db.express.create(
                "Doc", {"id": shared_id, "title": TENANT_A_SECRET_TITLE}
            )
        with db.tenant_context.switch("tenant-b"):
            with pytest.raises(TenantNaturalKeyCollisionError):
                await db.express.upsert(
                    "Doc", {"id": shared_id, "title": "B-STOLEN"}, conflict_on=["id"]
                )
        await _assert_tenant_a_row_intact(db, "docs", shared_id)
    finally:
        db.close()


async def _run_same_tenant_positive_scenario(db: DataFlow) -> None:
    """The tenant guard MUST NOT break legitimate same-tenant upserts: a
    new insert, a same-tenant bulk update, and a same-tenant single update."""

    @db.model
    class Doc:
        id: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")

    doc_id = _uid("doc")
    with db.tenant_context.switch("tenant-a"):
        r_ins = await db.express.bulk_upsert(
            "Doc", [{"id": doc_id, "title": "v1"}], conflict_on=["id"]
        )
        assert r_ins.get("created") == 1 and r_ins.get("updated") == 0
        r_upd = await db.express.bulk_upsert(
            "Doc", [{"id": doc_id, "title": "v2"}], conflict_on=["id"]
        )
        assert r_upd.get("updated") == 1 and r_upd.get("created") == 0
        assert (await db.express.read("Doc", doc_id))["title"] == "v2"
        # Single-record same-tenant update.
        await db.express.upsert(
            "Doc", {"id": doc_id, "title": "v3"}, conflict_on=["id"]
        )
        assert (await db.express.read("Doc", doc_id))["title"] == "v3"
        # Single-record new insert.
        new_id = _uid("doc-new")
        await db.express.upsert(
            "Doc", {"id": new_id, "title": "n1"}, conflict_on=["id"]
        )
        assert (await db.express.read("Doc", new_id))["title"] == "n1"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.sqlite
async def test_issue_same_tenant_upsert_still_updates_sqlite():
    """SQLite: the cross-tenant guard does NOT regress same-tenant upserts."""
    db = _sqlite_db()
    try:
        await _run_same_tenant_positive_scenario(db)
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.postgresql
@pytest.mark.requires_postgres
async def test_issue_same_tenant_upsert_still_updates_postgres():
    """PostgreSQL: same-tenant upserts still update through the guarded path."""
    if not _pg_available():
        pytest.skip("PostgreSQL infra (localhost:5434) not reachable")
    db = DataFlow(TEST_DATABASE_URL, auto_migrate=True, multi_tenant=True)
    try:
        await _run_same_tenant_positive_scenario(db)
    finally:
        db.close()


# ===========================================================================
# H1 (redteam) — BulkCreatePoolNode.async_run(conflict_resolution="update").
#
# ``BulkCreatePoolNode`` is a SEPARATE builder from the express bulk_upsert /
# bulk_create paths exercised above. It is ``@register_node("BulkCreatePoolNode")``
# and reachable via ``workflow.add_node("BulkCreatePoolNode", ...)`` (or a direct
# instantiate + ``async_run``). Its ``conflict_resolution == "update"`` block
# emitted ``ON CONFLICT (id) DO UPDATE SET {col}=EXCLUDED.{col}`` (PG/SQLite) and
# the MySQL ODKU equivalent with NO tenant guard AND without excluding
# ``tenant_id`` — the SAME cross-tenant write/theft breach the C1 fix closed in
# the sibling builders (features/bulk.py, sql/dialects.py, nodes/bulk_upsert.py).
#
# The fix (for ``tenant_guarded = self.multi_tenant and "tenant_id" in columns``):
#   * excludes ``tenant_id`` from the SET (no ownership flip);
#   * PG/SQLite: appends ``WHERE {table}.tenant_id = EXCLUDED.tenant_id``;
#   * MySQL ODKU (no WHERE): wraps each SET in ``IF(tenant_id = new_row.tenant_id
#     / VALUES(tenant_id), <new>, <col>)``.
# ``tenant_id`` reaches ``columns`` because ``_process_direct`` injects it into
# every record for a ``multi_tenant`` node before deriving column names, so the
# guard activates. These tests drive the node DIRECTLY and assert via a RAW
# cross-tenant read (never a tenant-scoped read, which would mask the theft).
# ===========================================================================


def _sqlite_db_with_url():
    """A multi_tenant SQLite DataFlow plus the connection_string the direct
    ``BulkCreatePoolNode`` needs (it writes to the SAME backend file)."""
    tmpdir = tempfile.mkdtemp()
    path = f"{tmpdir}/mt1526bcpool_{int(time.time() * 1_000_000)}.db"
    url = f"sqlite:///{path}"
    return DataFlow(url, auto_migrate=True, multi_tenant=True), url


async def _run_bcpool_cross_tenant_scenario(db: DataFlow, url: str) -> None:
    from dataflow.nodes.bulk_create_pool import BulkCreatePoolNode

    @db.model
    class Doc:
        id: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    db.tenant_context.register_tenant("tenant-b", "B")

    shared_id = _uid("doc")
    with db.tenant_context.switch("tenant-a"):
        await db.express.create(
            "Doc", {"id": shared_id, "title": TENANT_A_SECRET_TITLE}
        )

    # THE BREACH: tenant B drives BulkCreatePoolNode directly with
    # conflict_resolution="update" on tenant A's GLOBAL id PK. Pre-fix, the
    # unguarded ON CONFLICT DO UPDATE / ODKU overwrote tenant A's title and
    # flipped tenant_id to "tenant-b" (data theft). The guard makes it a no-op.
    dbt = db._detect_database_type()
    node = BulkCreatePoolNode(
        table_name="docs",
        database_type=dbt,
        connection_string=url,
        multi_tenant=True,
        conflict_resolution="update",
        tenant_id="tenant-b",
    )
    result = await node.async_run(data=[{"id": shared_id, "title": "B-STOLEN"}])
    # The guarded no-op does not raise; the node returns its ordinary result dict.
    assert isinstance(result, dict)

    # LOAD-BEARING (raw cross-tenant read): tenant A's row is UNCHANGED — secret
    # title intact (i.e. NOT "B-STOLEN"), tenant_id NOT flipped — and, because id
    # is the global PK, exactly one row exists for shared_id, so tenant B did NOT
    # gain/overwrite it. Assertions are id-scoped: the shared PostgreSQL `docs`
    # table accumulates rows across regression runs, so a global repr scan would
    # be polluted by residue (including the without-fix proof run's stolen row).
    await _assert_tenant_a_row_intact(db, "docs", shared_id)
    rows = await _raw_read_all(db, "docs")
    this_id = [r for r in rows if str(r["id"]) == shared_id]
    assert len(this_id) == 1, f"expected one row for id={shared_id}: {this_id!r}"
    assert this_id[0]["tenant_id"] == "tenant-a", f"ownership flipped: {this_id[0]!r}"
    assert this_id[0]["title"] != "B-STOLEN", f"tenant-b's write landed: {this_id[0]!r}"


async def _run_bcpool_same_tenant_positive(db: DataFlow, url: str) -> None:
    """The tenant guard MUST NOT lock out a legitimate SAME-tenant upsert: when
    the incoming tenant matches the row's own tenant, the update DOES apply."""
    from dataflow.nodes.bulk_create_pool import BulkCreatePoolNode

    @db.model
    class Doc:
        id: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")

    doc_id = _uid("doc")
    with db.tenant_context.switch("tenant-a"):
        await db.express.create("Doc", {"id": doc_id, "title": "v1"})

    dbt = db._detect_database_type()
    node = BulkCreatePoolNode(
        table_name="docs",
        database_type=dbt,
        connection_string=url,
        multi_tenant=True,
        conflict_resolution="update",
        tenant_id="tenant-a",
    )
    result = await node.async_run(data=[{"id": doc_id, "title": "v2-legit-update"}])
    assert isinstance(result, dict)

    # Same-tenant → WHERE tenant_id = EXCLUDED.tenant_id (/ IF()) is TRUE → the
    # update applies. No false lockout.
    rows = await _raw_read_all(db, "docs")
    matches = [r for r in rows if str(r["id"]) == doc_id]
    assert len(matches) == 1, f"expected one row for id={doc_id}: {rows!r}"
    assert matches[0]["tenant_id"] == "tenant-a"
    assert (
        matches[0]["title"] == "v2-legit-update"
    ), f"same-tenant update did NOT apply (false lockout): {matches[0]!r}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.sqlite
async def test_issue_bulk_create_pool_node_id_conflict_no_cross_tenant_theft_sqlite():
    """SQLite: tenant B ``BulkCreatePoolNode(conflict_resolution='update')`` on
    tenant A's id does NOT overwrite/steal A's row (the H1 breach, fail-closed)."""
    db, url = _sqlite_db_with_url()
    try:
        await _run_bcpool_cross_tenant_scenario(db, url)
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.sqlite
async def test_issue_bulk_create_pool_node_same_tenant_update_still_applies_sqlite():
    """SQLite: the cross-tenant guard does NOT regress a legitimate same-tenant
    BulkCreatePoolNode upsert (the update still applies)."""
    db, url = _sqlite_db_with_url()
    try:
        await _run_bcpool_same_tenant_positive(db, url)
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.postgresql
@pytest.mark.requires_postgres
async def test_issue_bulk_create_pool_node_id_conflict_no_cross_tenant_theft_postgres():
    """PostgreSQL: the same fail-closed contract holds against the native
    ON CONFLICT (id) DO UPDATE ... WHERE path (the real-DB breach shape)."""
    if not _pg_available():
        pytest.skip("PostgreSQL infra (localhost:5434) not reachable")
    db = DataFlow(TEST_DATABASE_URL, auto_migrate=True, multi_tenant=True)
    try:
        await _run_bcpool_cross_tenant_scenario(db, TEST_DATABASE_URL)
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.postgresql
@pytest.mark.requires_postgres
async def test_issue_bulk_create_pool_node_same_tenant_update_still_applies_postgres():
    """PostgreSQL: the guard does NOT regress a same-tenant BulkCreatePoolNode
    upsert through the native guarded path."""
    if not _pg_available():
        pytest.skip("PostgreSQL infra (localhost:5434) not reachable")
    db = DataFlow(TEST_DATABASE_URL, auto_migrate=True, multi_tenant=True)
    try:
        await _run_bcpool_same_tenant_positive(db, TEST_DATABASE_URL)
    finally:
        db.close()
