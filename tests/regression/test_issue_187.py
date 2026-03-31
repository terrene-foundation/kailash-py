# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: #187 -- Sync Express API wrapper for non-async contexts.

The problem: all Express CRUD methods are async-only. Users in sync contexts
(CLI scripts, sync FastAPI handlers, pytest without asyncio) had no way to
use the Express API without manually managing event loops.

Fix: SyncExpress class wraps every async Express method with a sync equivalent,
accessible via db.express_sync property.
"""

import pytest


@pytest.mark.regression
def test_issue_187_express_sync_create_read_list_count(tmp_path) -> None:
    """express_sync provides working sync CRUD: create, read, list, count."""
    from dataflow import DataFlow
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    db_file = str(tmp_path / "test_187.db")
    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)

    # Register model dynamically
    Model = type(
        "Widget187",
        (),
        {
            "__annotations__": {
                "id": str,
                "name": str,
            },
            "__tablename__": "widgets_187",
            "name": "",
        },
    )
    db.model(Model)

    # Create table manually
    wf = WorkflowBuilder()
    wf.add_node(
        "SQLDatabaseNode",
        "create_table",
        {
            "query": """CREATE TABLE IF NOT EXISTS widgets_187 (
                id TEXT PRIMARY KEY,
                name TEXT DEFAULT ''
            )""",
            "connection_string": f"sqlite:///{db_file}",
        },
    )
    runtime = LocalRuntime()
    runtime.execute(wf.build())

    # -- create --
    created = db.express_sync.create("Widget187", {"id": "w-001", "name": "Sprocket"})
    assert created is not None, "express_sync.create returned None"

    # -- read (verify persistence) --
    read_back = db.express_sync.read("Widget187", "w-001")
    assert read_back is not None, "express_sync.read returned None for existing record"
    assert read_back["name"] == "Sprocket", f"Unexpected name: {read_back['name']}"

    # -- create a second record --
    db.express_sync.create("Widget187", {"id": "w-002", "name": "Gear"})

    # -- list --
    all_records = db.express_sync.list("Widget187")
    assert isinstance(all_records, list), f"list() returned {type(all_records)}"
    assert len(all_records) == 2, f"Expected 2 records, got {len(all_records)}"

    # -- count --
    total = db.express_sync.count("Widget187")
    assert total == 2, f"Expected count=2, got {total}"

    # -- delete --
    deleted = db.express_sync.delete("Widget187", "w-001")
    assert deleted, "express_sync.delete returned False"

    # Verify deletion persisted
    after_delete = db.express_sync.read("Widget187", "w-001")
    assert after_delete is None, f"Record should be deleted but got: {after_delete}"

    remaining = db.express_sync.count("Widget187")
    assert remaining == 1, f"Expected count=1 after delete, got {remaining}"


@pytest.mark.regression
def test_issue_187_express_sync_update(tmp_path) -> None:
    """express_sync.update modifies a record and persists the change."""
    from dataflow import DataFlow
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    db_file = str(tmp_path / "test_187_update.db")
    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)

    Model = type(
        "Part187",
        (),
        {
            "__annotations__": {
                "id": str,
                "label": str,
            },
            "__tablename__": "parts_187",
            "label": "",
        },
    )
    db.model(Model)

    wf = WorkflowBuilder()
    wf.add_node(
        "SQLDatabaseNode",
        "create_table",
        {
            "query": """CREATE TABLE IF NOT EXISTS parts_187 (
                id TEXT PRIMARY KEY,
                label TEXT DEFAULT ''
            )""",
            "connection_string": f"sqlite:///{db_file}",
        },
    )
    runtime = LocalRuntime()
    runtime.execute(wf.build())

    db.express_sync.create("Part187", {"id": "p-001", "label": "Original"})

    db.express_sync.update("Part187", "p-001", {"label": "Updated"})

    read_back = db.express_sync.read("Part187", "p-001")
    assert read_back is not None, "Record missing after update"
    assert read_back["label"] == "Updated", f"Update not persisted: {read_back}"


@pytest.mark.regression
def test_issue_187_express_sync_find_one(tmp_path) -> None:
    """express_sync.find_one returns a single record by non-PK filter."""
    from dataflow import DataFlow
    from kailash.runtime import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    db_file = str(tmp_path / "test_187_find.db")
    db = DataFlow(f"sqlite:///{db_file}", auto_migrate=False, cache_enabled=False)

    Model = type(
        "Gadget187",
        (),
        {
            "__annotations__": {
                "id": str,
                "color": str,
            },
            "__tablename__": "gadgets_187",
            "color": "",
        },
    )
    db.model(Model)

    wf = WorkflowBuilder()
    wf.add_node(
        "SQLDatabaseNode",
        "create_table",
        {
            "query": """CREATE TABLE IF NOT EXISTS gadgets_187 (
                id TEXT PRIMARY KEY,
                color TEXT DEFAULT ''
            )""",
            "connection_string": f"sqlite:///{db_file}",
        },
    )
    runtime = LocalRuntime()
    runtime.execute(wf.build())

    db.express_sync.create("Gadget187", {"id": "g-001", "color": "red"})
    db.express_sync.create("Gadget187", {"id": "g-002", "color": "blue"})

    result = db.express_sync.find_one("Gadget187", {"color": "blue"})
    assert result is not None, "find_one returned None for existing record"
    assert result["id"] == "g-002", f"Wrong record: {result}"

    missing = db.express_sync.find_one("Gadget187", {"color": "green"})
    assert missing is None, f"find_one should return None for missing record: {missing}"


@pytest.mark.regression
def test_issue_187_express_sync_accessible_from_import() -> None:
    """SyncExpress is importable from the dataflow package."""
    from dataflow import SyncExpress

    assert SyncExpress is not None
