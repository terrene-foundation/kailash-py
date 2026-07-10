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
