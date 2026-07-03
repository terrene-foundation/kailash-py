# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1518 — multi_tenant upsert mis-maps ``tenant_id``.

On a ``multi_tenant=True`` DataFlow, a single-record upsert persisted the WRONG
value in the ``tenant_id`` column: it received another column's value (the
row's ``id``) instead of the active tenant. Tenant scoping on the write path was
therefore built against a bogus ``tenant_id`` — a cross-tenant leak class.

Root cause (traced end-to-end): the SQLite precheck-upsert builder
(``build_precheck_upsert_query``, issue #1508) emits *named* ``:pN``
placeholders. The tenant ``QueryInterceptor`` appends ``tenant_id`` when the
INSERT column list omits it (``insert_data = {**where, **create}`` never carries
``tenant_id``), but ``_detect_placeholder_style`` did not recognise the ``:pN``
style and defaulted to ``qmark`` — appending a lone ``?`` into a ``:pN`` query.
Downstream ``_convert_to_named_parameters`` renumbered that ``?`` to ``:p0``
(its counter restarts at 0), colliding with the existing ``:p0`` so ``tenant_id``
bound to the first value. The fix teaches the interceptor the ``:pN`` (``colon``)
style so the injected query is pure ``:pN`` — structurally identical to the
already-correct non-tenant upsert.

These are Tier-2 regression tests exercising REAL SQLite (no mocking) with raw
``sqlite3`` read-backs asserting the persisted ``tenant_id`` value — the mis-map
is about the stored value, so the ground-truth read is raw, not framework-read.
"""

from __future__ import annotations

import sqlite3
import tempfile
import time

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from dataflow.tenancy.interceptor import QueryInterceptor


def _uid(prefix: str = "doc") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


def _raw_rows(db_path: str, table: str):
    """Ground-truth read straight from the file — bypasses every framework
    read-path transform so the persisted ``tenant_id`` value is asserted as
    stored on disk."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(
            f"SELECT id, tenant_id, email, title FROM {table} ORDER BY id, tenant_id"
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        con.close()


async def _upsert(runtime, doc_id, title, email):
    wf = WorkflowBuilder()
    wf.add_node(
        "TenantDocUpsertNode",
        "u",
        {
            "where": {"id": doc_id},
            "conflict_on": ["id"],
            "update": {"title": title},
            # deliberately omit tenant_id from create — the exact #1518 path where
            # the interceptor must APPEND it (insert_data never carries tenant_id).
            "create": {"id": doc_id, "email": email, "title": title},
        },
    )
    return await runtime.execute_workflow_async(wf.build(), inputs={})


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
@pytest.mark.asyncio
async def test_issue_1518_new_row_upsert_persists_active_tenant():
    """R1 (the reported bug): a new-row multi_tenant upsert persists
    ``tenant_id == active tenant`` — NOT the row's ``id`` value."""
    tmpdir = tempfile.mkdtemp()
    path = f"{tmpdir}/mt1518.db"
    db = DataFlow(f"sqlite:///{path}", auto_migrate=True, multi_tenant=True)

    @db.model
    class TenantDoc:
        id: str
        tenant_id: str
        email: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    runtime = AsyncLocalRuntime()
    try:
        doc_id = _uid()
        with db.tenant_context.switch("tenant-a"):
            await _upsert(runtime, doc_id, "A1", "a@example.com")

        rows = _raw_rows(path, "tenant_docs")
        assert len(rows) == 1, rows
        row = rows[0]
        # Pre-fix this was ``row["id"]`` (the mis-map): tenant_id == doc_id.
        assert row["tenant_id"] == "tenant-a", (
            f"tenant_id mis-map: stored {row['tenant_id']!r}, expected 'tenant-a' "
            f"(row={row})"
        )
        # Payload columns must be intact (the mixed-placeholder bug also risked
        # binding payload columns to the wrong values).
        assert row["id"] == doc_id and row["email"] == "a@example.com"
        assert row["title"] == "A1"
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
@pytest.mark.asyncio
async def test_issue_1518_tenant_id_correct_regardless_of_create_column_order():
    """R1b (AC: 'regardless of the payload column order'): reordering the
    ``create`` dict must not change which column ``tenant_id`` binds to."""
    tmpdir = tempfile.mkdtemp()
    path = f"{tmpdir}/mt1518_order.db"
    db = DataFlow(f"sqlite:///{path}", auto_migrate=True, multi_tenant=True)

    @db.model
    class TenantDoc:
        id: str
        tenant_id: str
        email: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    runtime = AsyncLocalRuntime()
    try:
        doc_id = _uid()
        # create dict with columns in a non-schema order
        wf = WorkflowBuilder()
        wf.add_node(
            "TenantDocUpsertNode",
            "u",
            {
                "where": {"id": doc_id},
                "conflict_on": ["id"],
                "update": {"title": "Z9"},
                "create": {"title": "Z9", "email": "z@example.com", "id": doc_id},
            },
        )
        with db.tenant_context.switch("tenant-a"):
            await runtime.execute_workflow_async(wf.build(), inputs={})

        row = _raw_rows(path, "tenant_docs")[0]
        assert row["tenant_id"] == "tenant-a", row
        assert row["title"] == "Z9" and row["email"] == "z@example.com"
        assert row["id"] == doc_id
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
@pytest.mark.asyncio
async def test_issue_1518_existing_row_upsert_update_stays_tenant_scoped():
    """R2: the existing-row UPDATE branch of the upsert (also ``:pN``, injected
    via ``_inject_where_predicate``) keeps ``tenant_id`` correct and applies the
    update to the right row."""
    tmpdir = tempfile.mkdtemp()
    path = f"{tmpdir}/mt1518_update.db"
    db = DataFlow(f"sqlite:///{path}", auto_migrate=True, multi_tenant=True)

    @db.model
    class TenantDoc:
        id: str
        tenant_id: str
        email: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    runtime = AsyncLocalRuntime()
    try:
        doc_id = _uid()
        with db.tenant_context.switch("tenant-a"):
            await _upsert(runtime, doc_id, "A1", "a@example.com")  # INSERT
            await _upsert(runtime, doc_id, "A2", "a@example.com")  # UPDATE

        rows = _raw_rows(path, "tenant_docs")
        assert len(rows) == 1, rows
        row = rows[0]
        assert row["tenant_id"] == "tenant-a", row
        assert row["title"] == "A2", f"UPDATE did not apply: {row}"
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
@pytest.mark.asyncio
async def test_issue_1518_cross_tenant_upsert_cannot_corrupt_other_tenant_row():
    """R3 (the security invariant): a second tenant upserting another tenant's
    natural key MUST NOT modify the first tenant's row. Two tenants each keep a
    correctly-scoped row; one tenant's write never touches the other's."""
    tmpdir = tempfile.mkdtemp()
    path = f"{tmpdir}/mt1518_iso.db"
    db = DataFlow(f"sqlite:///{path}", auto_migrate=True, multi_tenant=True)

    @db.model
    class TenantDoc:
        id: str
        tenant_id: str
        email: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    db.tenant_context.register_tenant("tenant-b", "B")
    runtime = AsyncLocalRuntime()
    try:
        with db.tenant_context.switch("tenant-a"):
            await _upsert(runtime, "doc-a", "A1", "a@example.com")
        with db.tenant_context.switch("tenant-b"):
            await _upsert(runtime, "doc-b", "B1", "b@example.com")

        before = {r["id"]: dict(r) for r in _raw_rows(path, "tenant_docs")}
        assert before["doc-a"]["tenant_id"] == "tenant-a"
        assert before["doc-b"]["tenant_id"] == "tenant-b"

        # tenant-b attempts to write tenant-a's key. It MUST fail closed (the
        # single-tenant PK on ``id`` rejects the second row) and MUST NOT mutate
        # tenant-a's existing row.
        with db.tenant_context.switch("tenant-b"):
            # Pinned to the PK-collision fail-closed path — a future regression
            # that threw for an unrelated reason must not keep this green.
            with pytest.raises(Exception, match="(?i)UNIQUE constraint"):
                await _upsert(runtime, "doc-a", "HACKED", "hack@example.com")

        after = {
            (r["tenant_id"], r["id"]): dict(r) for r in _raw_rows(path, "tenant_docs")
        }
        a_row = after[("tenant-a", "doc-a")]
        assert a_row == before["doc-a"], (
            f"cross-tenant write leak: tenant-a's row changed: {a_row} != "
            f"{before['doc-a']}"
        )
        # tenant-b never planted a row under doc-a with tenant-a's data.
        assert ("tenant-b", "doc-a") not in after
    finally:
        db.close()


# --- Structural unit tests: lock the root-cause fix (no DB) --------------------


def test_issue_1518_detect_placeholder_style_recognizes_colon():
    """The ``:pN`` named style emitted by ``build_precheck_upsert_query`` MUST be
    detected as ``colon`` — the classification the whole fix hinges on."""
    q = "INSERT INTO t (id, email) VALUES (:p0, :p1) RETURNING *"
    assert QueryInterceptor._detect_placeholder_style(q) == "colon"
    # regressions of the other styles must still classify correctly
    assert QueryInterceptor._detect_placeholder_style("... $1 ...") == "dollar"
    assert QueryInterceptor._detect_placeholder_style("... %s ...") == "percent"
    assert QueryInterceptor._detect_placeholder_style("... ? ...") == "qmark"


def test_issue_1518_insert_injection_emits_pure_colon_no_qmark():
    """The INSERT append-branch on a ``:pN`` query MUST emit a ``:p{N}`` tenant
    placeholder (pure named), never a ``?`` — a mixed statement collides at
    ``:p0`` downstream."""
    interceptor = QueryInterceptor(
        tenant_id="tenant-a",
        tenant_tables=["tenant_docs"],
        tenant_column="tenant_id",
    )
    query = (
        "INSERT INTO tenant_docs (id, email, title)\n"
        "            VALUES (:p0, :p1, :p2)\n"
        "            RETURNING *"
    )
    params = ["doc-a", "a@example.com", "A1"]
    out_q, out_p = interceptor.inject_tenant_conditions(query, params)

    assert "tenant_id" in out_q
    assert "?" not in out_q, f"mixed placeholder regressed: {out_q!r}"
    # tenant value appended at index 3 → placeholder must be :p3
    assert ":p3" in out_q, out_q
    assert out_p[-1] == "tenant-a"
    # the tenant value's :pN index must equal its position in the params list
    assert out_p.index("tenant-a") == 3


def test_issue_1518_update_where_predicate_colon_emits_indexed_placeholder():
    """Symmetric structural lock for the UPDATE/WHERE colon branch: the injected
    tenant predicate on a ``:pN`` UPDATE must be ``:p{len}`` (pure named), never
    a ``?``, with the value's index == its params position."""
    interceptor = QueryInterceptor(
        tenant_id="tenant-a",
        tenant_tables=["tenant_docs"],
        tenant_column="tenant_id",
    )
    query = (
        "UPDATE tenant_docs SET title = :p0\n"
        "            WHERE id = :p1\n"
        "            RETURNING *"
    )
    params = ["A2", "doc-a"]
    out_q, out_p = interceptor.inject_tenant_conditions(query, params)

    assert "tenant_id = :p2" in out_q, out_q
    assert "?" not in out_q, f"mixed placeholder regressed: {out_q!r}"
    assert out_p[-1] == "tenant-a"
    assert out_p.index("tenant-a") == 2


def test_issue_1518_select_colon_injection_is_defense_in_depth_pure_colon():
    """Defense-in-depth: a (currently-unemitted) ``:pN`` SELECT injected by the
    interceptor must also be pure ``:pN`` — the read-path symmetry that stops a
    future named-param SELECT builder silently reopening the #1518 leak."""
    interceptor = QueryInterceptor(
        tenant_id="tenant-a",
        tenant_tables=["tenant_docs"],
        tenant_column="tenant_id",
    )
    query = "SELECT id, tenant_id, title FROM tenant_docs WHERE id = :p0"
    params = ["doc-a"]
    out_q, out_p = interceptor.inject_tenant_conditions(query, params)

    assert "tenant_id = :p1" in out_q, out_q
    assert "?" not in out_q, f"mixed placeholder on SELECT read path: {out_q!r}"
    assert out_p[-1] == "tenant-a"
    assert out_p.index("tenant-a") == 1


def test_issue_1518_tenant_placeholder_for_style_rejects_colon():
    """``_tenant_placeholder_for_style`` must FAIL LOUD on colon rather than
    silently return ``?`` (a ``?`` in a ``:pN`` query is the #1518 defect). This
    locks the fail-closed guard against a future caller forgetting the inline
    colon branch."""
    with pytest.raises(ValueError, match="(?i)colon"):
        QueryInterceptor._tenant_placeholder_for_style("colon")


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.sqlite
@pytest.mark.asyncio
async def test_issue_1518_tenant_id_in_create_is_overwritten_to_active_tenant():
    """The 'tenant column already present' interceptor branch: when ``create``
    supplies a WRONG ``tenant_id``, the interceptor MUST overwrite it with the
    active tenant (never persist the caller-supplied value). Locks the
    style-agnostic overwrite branch for colon-style upserts."""
    tmpdir = tempfile.mkdtemp()
    path = f"{tmpdir}/mt1518_present.db"
    db = DataFlow(f"sqlite:///{path}", auto_migrate=True, multi_tenant=True)

    @db.model
    class TenantDoc:
        id: str
        tenant_id: str
        email: str
        title: str

    db._ensure_connected()
    db.tenant_context.register_tenant("tenant-a", "A")
    runtime = AsyncLocalRuntime()
    try:
        doc_id = _uid()
        wf = WorkflowBuilder()
        wf.add_node(
            "TenantDocUpsertNode",
            "u",
            {
                "where": {"id": doc_id},
                "conflict_on": ["id"],
                "update": {"title": "A1"},
                # caller supplies a spoofed tenant_id — must be overwritten.
                "create": {
                    "id": doc_id,
                    "tenant_id": "tenant-EVIL",
                    "email": "a@example.com",
                    "title": "A1",
                },
            },
        )
        with db.tenant_context.switch("tenant-a"):
            await runtime.execute_workflow_async(wf.build(), inputs={})

        row = _raw_rows(path, "tenant_docs")[0]
        assert (
            row["tenant_id"] == "tenant-a"
        ), f"spoofed tenant_id not overwritten: stored {row['tenant_id']!r}"
    finally:
        db.close()
