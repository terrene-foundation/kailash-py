# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1526 — actionable cross-tenant natural-key error.

A ``multi_tenant=True`` DataFlow model keeps the DEFAULT single-column primary
key ``id`` (schema-gen at ``core/engine.py``), NOT a composite ``(tenant_id,
id)``. Under the default row-level tenant strategy the ``id`` is therefore a
GLOBALLY-UNIQUE surrogate: two tenants cannot share the same natural-key ``id``.
When tenant B writes an ``id`` tenant A already owns, the database rejects it on
the PK UNIQUE constraint (``UNIQUE constraint failed: <table>.id`` on SQLite;
``<table>_pkey`` on PostgreSQL). This is fail-closed and SAFE (no cross-tenant
data leaks — verified in #1518), but the raw driver message never explains the
surrogate-id design.

Option B (owner-selected): keep the id-alone PK (no schema change) and close the
DX gap with an actionable typed error — :class:`TenantNaturalKeyCollisionError`
— that names the CALLER's own ``tenant_id`` + supplied ``id`` and points to the
schema-per-tenant / UUID alternatives.

These are Tier-2 regression tests against REAL databases (no mocking): SQLite
always, PostgreSQL when the shared Docker infra is reachable. The pure
PK-detection helper (:func:`is_pk_unique_violation`) additionally carries Tier-1
narrowness assertions — it MUST match ONLY the ``id`` PK, never a sibling UNIQUE
column, so the actionable error never over-broadens onto unrelated violations.
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from dataflow import DataFlow
from dataflow.core.exceptions import (
    TenantNaturalKeyCollisionError,
    is_pk_unique_violation,
)

# Shared SDK Docker PostgreSQL infra (port 5434), same as the #1518 suite.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


def _uid(prefix: str = "doc") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


def _sqlite_db():
    tmpdir = tempfile.mkdtemp()
    path = f"{tmpdir}/mt1526_{int(time.time() * 1_000_000)}.db"
    return DataFlow(f"sqlite:///{path}", auto_migrate=True, multi_tenant=True)


def _pg_available() -> bool:
    import socket

    host, port = "localhost", 5434
    if TEST_DATABASE_URL.startswith("postgresql://"):
        # Best-effort parse host:port out of the URL for the probe.
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


# ---------------------------------------------------------------------------
# Tier-1: is_pk_unique_violation narrowness (PK-only, never a sibling column)
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.unit
@pytest.mark.tier1
class TestIsPkUniqueViolation:
    """The PK-detection helper matches ONLY the ``id`` PK across dialects and
    NEVER a sibling UNIQUE column — the guarantee that prevents the actionable
    error from over-broadening (issue #1526)."""

    def test_sqlite_pk_violation_matches(self):
        assert is_pk_unique_violation("UNIQUE constraint failed: docs.id", "docs")

    def test_sqlite_sibling_unique_column_does_not_match(self):
        # A sibling UNIQUE column whose name has ``id`` as a prefix MUST NOT
        # match — only the exact ``docs.id`` PK column.
        assert not is_pk_unique_violation(
            "UNIQUE constraint failed: docs.idempotency_key", "docs"
        )
        assert not is_pk_unique_violation(
            "UNIQUE constraint failed: docs.email", "docs"
        )

    def test_postgres_pkey_constraint_matches(self):
        assert is_pk_unique_violation(
            'duplicate key value violates unique constraint "docs_pkey"',
            "docs",
        )

    def test_postgres_detail_key_id_matches(self):
        # Even when the constraint name is redacted/absent, the DETAIL naming
        # the ``id`` column is a positive signal (survives sanitize_db_error,
        # which preserves the column name).
        assert is_pk_unique_violation(
            "duplicate key value violates unique constraint\n"
            "DETAIL: Key (id)=([REDACTED]) already exists.",
            "docs",
        )

    def test_postgres_sibling_unique_constraint_does_not_match(self):
        assert not is_pk_unique_violation(
            'duplicate key value violates unique constraint "docs_email_key"\n'
            "DETAIL: Key (email)=([REDACTED]) already exists.",
            "docs",
        )

    def test_mysql_primary_key_matches(self):
        assert is_pk_unique_violation(
            "Duplicate entry '[REDACTED]' for key 'PRIMARY'", "docs"
        )
        # MySQL 8.0.19+ qualified form.
        assert is_pk_unique_violation(
            "Duplicate entry '[REDACTED]' for key 'docs.PRIMARY'", "docs"
        )

    def test_mysql_sibling_key_does_not_match(self):
        assert not is_pk_unique_violation(
            "Duplicate entry '[REDACTED]' for key 'docs.email_unique'", "docs"
        )

    def test_empty_and_unrelated_inputs_return_false(self):
        assert not is_pk_unique_violation("", "docs")
        assert not is_pk_unique_violation("some unrelated error", "docs")
        assert not is_pk_unique_violation("UNIQUE constraint failed: docs.id", "")


# ---------------------------------------------------------------------------
# Tier-2: end-to-end through the express write path (real DB, no mocking)
# ---------------------------------------------------------------------------


async def _run_collision_scenario(db: DataFlow) -> None:
    """Shared scenario body run against whichever real backend is passed in."""

    @db.model
    class Doc:
        id: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    db.tenant_context.register_tenant("tenant-b", "B")

    doc_id = _uid()

    # tenant-a establishes the natural key.
    with db.tenant_context.switch("tenant-a"):
        created = await db.express.create("Doc", {"id": doc_id, "title": "A"})
        assert created["id"] == doc_id

    # (a) tenant-b writing the SAME natural key → actionable typed error.
    with db.tenant_context.switch("tenant-b"):
        with pytest.raises(TenantNaturalKeyCollisionError) as excinfo:
            await db.express.create("Doc", {"id": doc_id, "title": "B"})

    err = excinfo.value
    # Structured attributes name the CALLER's own tenant + id (never the other
    # tenant's row data — tenant isolation preserved).
    assert err.tenant_id == "tenant-b"
    assert err.colliding_id == doc_id
    assert err.model_name == "Doc"

    # (c) message contains tenant_id + colliding id + surrogate-id guidance.
    msg = str(err)
    assert "tenant-b" in msg
    assert doc_id in msg
    assert "surrogate" in msg
    assert "schema-per-tenant" in msg
    assert "IsolationStrategy.SCHEMA" in msg
    # Must NOT leak the other tenant's identity.
    assert "tenant-a" not in msg

    # (b) a normal SAME-tenant duplicate keeps the ordinary path — it MUST NOT
    # be converted into the cross-tenant collision error (no over-broadening).
    with db.tenant_context.switch("tenant-a"):
        with pytest.raises(Exception) as dup_info:
            await db.express.create("Doc", {"id": doc_id, "title": "A-again"})
    assert not isinstance(dup_info.value, TenantNaturalKeyCollisionError)


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.sqlite
async def test_issue_1526_cross_tenant_collision_sqlite():
    """SQLite (always-on): cross-tenant collision raises the actionable error;
    same-tenant duplicate keeps the ordinary path."""
    db = _sqlite_db()
    try:
        await _run_collision_scenario(db)
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.tier2
@pytest.mark.postgresql
@pytest.mark.requires_postgres
async def test_issue_1526_cross_tenant_collision_postgres():
    """PostgreSQL (when the shared Docker infra is reachable): the same
    contract holds against the ``<table>_pkey`` violation shape."""
    if not _pg_available():
        pytest.skip("PostgreSQL infra (localhost:5434) not reachable")
    db = DataFlow(TEST_DATABASE_URL, auto_migrate=True, multi_tenant=True)
    try:
        await _run_collision_scenario(db)
    finally:
        db.close()
