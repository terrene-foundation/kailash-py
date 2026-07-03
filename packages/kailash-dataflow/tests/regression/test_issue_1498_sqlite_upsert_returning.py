"""Regression tests for issue #1498 — SQLite upsert result-shape product bugs.

Two distinct product bugs fixed together:

1. The core Kailash SQLite adapter (``src/kailash/nodes/data/async_sql.py``)
   short-circuited every ``INSERT``/``UPDATE``/``DELETE`` to
   ``[{"rows_affected": N}]`` on a keyword-only check, discarding the
   ``RETURNING`` result set. SQLite upsert therefore returned
   ``{"record": {"rows_affected": 0}}`` instead of the upserted row. Fixed by
   adding a ``"RETURNING" not in query`` guard (parity with the PostgreSQL
   adapter) so RETURNING queries fall through to the fetch.

2. The DataFlow upsert dialect (``src/dataflow/sql/dialects.py``) built the
   ``ON CONFLICT DO UPDATE SET`` clause as ``col = EXCLUDED.col`` — but
   ``EXCLUDED`` is the value proposed for INSERT (the ``create`` payload), NOT
   the separate ``update`` payload. On conflict the row was set to the CREATE
   values, ignoring the caller's ``update`` values. Fixed by binding the
   ``update`` values as parameters.

NO MOCKING — real file-backed SQLite (Tier 2 discipline).
"""

import pytest

from dataflow import DataFlow
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1498_sqlite_upsert_returns_row_not_dml_summary(tmp_path):
    """Bug 1: SQLite upsert MUST return the upserted row (RETURNING), not a
    ``{"rows_affected": N}`` DML summary."""
    db = DataFlow(f"sqlite:///{tmp_path / 'upsert_returning.db'}")

    @db.model
    class Product:
        id: str
        sku: str
        name: str
        price: float

    runtime = AsyncLocalRuntime()

    workflow = WorkflowBuilder()
    workflow.add_node(
        "ProductUpsertNode",
        "upsert",
        {
            "where": {"id": "p1"},
            "update": {"name": "N", "price": 1.0, "sku": "S1"},
            "create": {"id": "p1", "sku": "S1", "name": "N", "price": 1.0},
        },
    )
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

    record = results["upsert"]["record"]
    # The record MUST be the upserted row, carrying the model's columns — NOT a
    # bare {"rows_affected": 0} summary (the pre-fix failure mode).
    assert "rows_affected" not in record, f"got DML summary, not row: {record}"
    assert record["id"] == "p1"
    assert record["price"] == 1.0
    assert results["upsert"]["created"] is True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1498_sqlite_upsert_applies_update_values_on_conflict(tmp_path):
    """Bug 2: on conflict, the upsert MUST apply the ``update`` payload values,
    not the ``create``/EXCLUDED values."""
    db = DataFlow(f"sqlite:///{tmp_path / 'upsert_update_values.db'}")

    @db.model
    class Product:
        id: str
        sku: str
        name: str
        price: float

    runtime = AsyncLocalRuntime()

    # First upsert INSERTs with the create values (price 49.99).
    wf_insert = WorkflowBuilder()
    wf_insert.add_node(
        "ProductUpsertNode",
        "ins",
        {
            "where": {"id": "p1"},
            "update": {"name": "Updated", "price": 99.99, "sku": "SKU-UPD"},
            "create": {"id": "p1", "sku": "SKU-NEW", "name": "New", "price": 49.99},
        },
    )
    r_ins, _ = await runtime.execute_workflow_async(wf_insert.build(), inputs={})
    assert r_ins["ins"]["created"] is True
    assert r_ins["ins"]["record"]["price"] == 49.99  # create value on INSERT

    # Second upsert hits the conflict → MUST apply the UPDATE values (99.99),
    # NOT the create/EXCLUDED values (49.99).
    wf_update = WorkflowBuilder()
    wf_update.add_node(
        "ProductUpsertNode",
        "upd",
        {
            "where": {"id": "p1"},
            "update": {"name": "Updated", "price": 99.99, "sku": "SKU-UPD"},
            "create": {"id": "p1", "sku": "SKU-NEW", "name": "New", "price": 49.99},
        },
    )
    r_upd, _ = await runtime.execute_workflow_async(wf_update.build(), inputs={})
    assert r_upd["upd"]["created"] is False
    record = r_upd["upd"]["record"]
    assert (
        record["price"] == 99.99
    ), f"update value not applied (EXCLUDED bug): {record}"
    assert record["name"] == "Updated"
    assert record["sku"] == "SKU-UPD"
    assert record["id"] == "p1"  # conflict key preserved
