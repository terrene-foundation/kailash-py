# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: #184 — Express create() missing auto-generated timestamps on SQLite.

The bug: SQLite INSERT returned {id, **kwargs} without created_at/updated_at because
SQLite doesn't support RETURNING clause. PostgreSQL returned them correctly.
Fix: read-back SELECT after SQLite INSERT to fetch auto-generated fields.
"""
from datetime import datetime
from typing import Optional

import pytest


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_184_express_create_returns_timestamps_on_sqlite(
    tmp_path,
) -> None:
    """Express create() on SQLite must return created_at and updated_at."""
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    from dataflow import DataFlow

    db_file = str(tmp_path / "test_184.db")
    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)

    Model = type(
        "Item184",
        (),
        {
            "__annotations__": {
                "id": int,
                "title": str,
                "created_at": Optional[datetime],
                "updated_at": Optional[datetime],
            },
            "__tablename__": "items_184",
            "title": "",
        },
    )
    db.model(Model)

    # Create table manually using DataFlow's internal connection
    wf = WorkflowBuilder()
    wf.add_node(
        "SQLDatabaseNode",
        "create_table",
        {
            "query": """CREATE TABLE IF NOT EXISTS items_184 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
            "connection_string": f"sqlite:///{db_file}",
        },
    )
    with LocalRuntime() as runtime:
        runtime.execute(wf.build())

    result = await db.express.create("Item184", {"title": "test item"})

    assert result is not None, "express.create returned None"
    assert (
        "success" not in result or result.get("success") is not False
    ), f"express.create failed: {result}"
    # These must be present — the core assertion for issue #184
    assert (
        "created_at" in result
    ), f"created_at missing from SQLite create() response: {result}"
    assert (
        "updated_at" in result
    ), f"updated_at missing from SQLite create() response: {result}"
    assert result["created_at"] is not None, "created_at is None"
    assert result["updated_at"] is not None, "updated_at is None"
