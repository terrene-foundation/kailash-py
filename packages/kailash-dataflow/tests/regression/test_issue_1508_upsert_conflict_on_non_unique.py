# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1508 — SQLite upsert ``conflict_on`` on a field
with no UNIQUE constraint.

Before #1508, a single-record upsert with ``conflict_on=["email"]`` on a model
whose ``email`` field was not declared unique failed with::

    Database query failed: ON CONFLICT clause does not match any PRIMARY KEY
    or UNIQUE constraint

The single-record SQLite upsert path already runs a WHERE-based existence
pre-check (SQLite lacks PostgreSQL's ``xmax``, so INSERT-vs-UPDATE is detected
by a ``SELECT COUNT(*)``). It then needlessly emitted ``INSERT ... ON CONFLICT
(email) ...``, which SQLite rejects unless ``email`` is backed by a UNIQUE
constraint. The fix uses the pre-check result to emit a plain INSERT (row
absent) or UPDATE ... WHERE (row present) via
``SQLiteDialect.build_precheck_upsert_query`` — no ``ON CONFLICT``, so no
reliance on a unique constraint. This matches the documented SQLite pre-check
design intent and is independent of connection type (surfaced, not caused, by
the #1502 ``:memory:`` shared-cache fix which made the table exist so the
ON CONFLICT was finally reached).

These are Tier-2 regression tests exercising REAL SQLite (no mocking), with
read-backs asserting persisted state per ``rules/testing.md`` § State
Persistence Verification.
"""

from __future__ import annotations

import time

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from dataflow.sql.dialects import SQLDialectFactory


def _uid(prefix: str = "u") -> str:
    return f"{prefix}-{int(time.time() * 1_000_000)}"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_conflict_on_non_unique_field_inserts_then_updates(tmp_path):
    """R1: conflict_on on a non-unique field upserts (INSERT then UPDATE) on
    file-backed SQLite — the exact #1508 repro, independent of ``:memory:``."""
    db = DataFlow(f"sqlite:///{tmp_path / 'issue_1508.db'}")

    @db.model
    class User:
        id: str
        email: str  # deliberately NOT unique — this is the bug's precondition
        name: str

    runtime = AsyncLocalRuntime()
    email = f"{_uid('alice')}@example.com"
    uid = _uid("user")

    # First upsert → INSERT (email absent). Previously raised "ON CONFLICT ...".
    wf1 = WorkflowBuilder()
    wf1.add_node(
        "UserUpsertNode",
        "upsert1",
        {
            "where": {"email": email},
            "conflict_on": ["email"],
            "update": {"name": "Alice Updated"},
            "create": {"id": uid, "email": email, "name": "Alice New"},
        },
    )
    res1, _ = await runtime.execute_workflow_async(wf1.build(), inputs={})
    assert res1["upsert1"]["created"] is True
    assert res1["upsert1"]["record"]["email"] == email
    assert res1["upsert1"]["record"]["name"] == "Alice New"

    # Second upsert on the same email → UPDATE (row present).
    wf2 = WorkflowBuilder()
    wf2.add_node(
        "UserUpsertNode",
        "upsert2",
        {
            "where": {"email": email},
            "conflict_on": ["email"],
            "update": {"name": "Alice Updated Again"},
            "create": {"id": _uid("other"), "email": email, "name": "ignored"},
        },
    )
    res2, _ = await runtime.execute_workflow_async(wf2.build(), inputs={})
    assert res2["upsert2"]["created"] is False
    assert res2["upsert2"]["record"]["name"] == "Alice Updated Again"

    # Read-back: exactly one row, carrying the UPDATE payload (state persisted).
    users = await db.express.list("User", {"email": email})
    assert len(users) == 1
    assert users[0]["name"] == "Alice Updated Again"
    assert users[0]["id"] == uid  # UPDATE kept the original id, ignored the 2nd create


@pytest.mark.regression
@pytest.mark.asyncio
async def test_conflict_on_composite_non_unique_fields(tmp_path):
    """R2: composite conflict_on on non-unique fields upserts correctly."""
    db = DataFlow(f"sqlite:///{tmp_path / 'issue_1508_composite.db'}")

    @db.model
    class OrderItem:
        id: str
        order_id: str
        product_id: str
        quantity: int

    runtime = AsyncLocalRuntime()
    order_id, product_id = _uid("order"), _uid("product")

    wf1 = WorkflowBuilder()
    wf1.add_node(
        "OrderItemUpsertNode",
        "u1",
        {
            "where": {"order_id": order_id, "product_id": product_id},
            "conflict_on": ["order_id", "product_id"],
            "update": {"quantity": 10},
            "create": {
                "id": _uid("item"),
                "order_id": order_id,
                "product_id": product_id,
                "quantity": 5,
            },
        },
    )
    res1, _ = await runtime.execute_workflow_async(wf1.build(), inputs={})
    assert res1["u1"]["created"] is True
    assert res1["u1"]["record"]["quantity"] == 5

    wf2 = WorkflowBuilder()
    wf2.add_node(
        "OrderItemUpsertNode",
        "u2",
        {
            "where": {"order_id": order_id, "product_id": product_id},
            "conflict_on": ["order_id", "product_id"],
            "update": {"quantity": 10},
            "create": {
                "id": _uid("item2"),
                "order_id": order_id,
                "product_id": product_id,
                "quantity": 5,
            },
        },
    )
    res2, _ = await runtime.execute_workflow_async(wf2.build(), inputs={})
    assert res2["u2"]["created"] is False
    assert res2["u2"]["record"]["quantity"] == 10

    items = await db.express.list("OrderItem", {"order_id": order_id})
    assert len(items) == 1
    assert items[0]["quantity"] == 10


@pytest.mark.regression
def test_precheck_upsert_query_emits_no_on_conflict():
    """R3: unit-level structural pin — the SQLite pre-check builder emits a plain
    INSERT / UPDATE and never ``ON CONFLICT`` (the clause that required a UNIQUE
    constraint). Guards against a refactor re-introducing the constraint
    dependency on the single-record SQLite path."""
    dialect = SQLDialectFactory.get_dialect("sqlite")

    insert_q = dialect.build_precheck_upsert_query(
        table_name="users",
        insert_data={"id": "u1", "email": "a@b.co", "name": "A"},
        update_data={"name": "A2"},
        where={"email": "a@b.co"},
        row_exists=False,
    )
    assert "ON CONFLICT" not in insert_q.query.upper()
    assert insert_q.query.upper().startswith("INSERT INTO")
    assert "RETURNING *" in insert_q.query.upper()

    update_q = dialect.build_precheck_upsert_query(
        table_name="users",
        insert_data={"id": "u1", "email": "a@b.co", "name": "A"},
        update_data={"name": "A2"},
        where={"email": "a@b.co"},
        row_exists=True,
        has_updated_at=True,
    )
    assert "ON CONFLICT" not in update_q.query.upper()
    assert update_q.query.upper().startswith("UPDATE ")
    assert "WHERE EMAIL = :" in update_q.query.upper()
    assert "UPDATED_AT = CURRENT_TIMESTAMP" in update_q.query.upper()
    # The identity column is never in the SET clause (would move the row).
    assert "SET NAME" in update_q.query.upper()
