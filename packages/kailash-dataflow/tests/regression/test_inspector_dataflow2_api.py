"""Regression: Inspector must reflect current DataFlow 2.0 APIs.

After the 2026-Q1 WorkflowBuilder refactor (commit 53dab715) and the
DataFlow 2.0 model-registry refactor, three bugs were introduced in the
Inspector that all manifested as silently empty outputs (not tracebacks):

1. ``connections()`` looked for ``source_node`` / ``target_node`` keys
   but WorkflowBuilder now emits ``from_node`` / ``to_node``. Every
   connection became ``("", "", "", "")`` — ``connection_graph()``,
   ``validate_connections()``, ``workflow_summary.node_count`` all
   degraded to empty / 1-node results.

2. ``connection_graph()`` derived its node list from connection endpoints
   only, so isolated nodes (and every node in a fresh workflow) vanished.

3. ``inspector.model()`` expected a SQLAlchemy ``__table__`` attribute,
   but DataFlow 2.0 registers each model as ``{"class", "fields",
   "table_name"}`` dict — ``ModelInfo.schema`` always returned ``{}``.

4. ``inspector.node()`` tokenised on ``_`` only, so the canonical
   PascalCase ``"{Model}{Op}Node"`` format (e.g. ``"ProductCreateNode"``)
   was parsed as ``model="Unknown"`` / ``op="unknown"`` with zero
   expected parameters.

This file exercises each contract through the public Inspector surface.
"""

from __future__ import annotations

import pytest

from dataflow import DataFlow
from dataflow.platform.inspector import Inspector
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.regression
def test_inspector_connections_handle_from_to_keys():
    """Regression: Inspector reads WorkflowBuilder's from_node/to_node keys."""
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)

    @db.model
    class Widget:
        id: str
        name: str

    workflow = WorkflowBuilder()
    workflow.add_node("WidgetCreateNode", "create", {"id": "w1", "name": "x"})
    workflow.add_node("WidgetReadNode", "read", {})
    workflow.add_connection("create", "id", "read", "id")

    inspector = Inspector(db, workflow)
    conns = inspector.connections()

    assert len(conns) == 1
    assert conns[0].source_node == "create"
    assert conns[0].target_node == "read"
    assert conns[0].source_parameter == "id"
    assert conns[0].target_parameter == "id"


@pytest.mark.regression
def test_inspector_connection_graph_includes_isolated_nodes():
    """Regression: connection_graph() lists every workflow node, not just
    those appearing in a connection.
    """
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)

    @db.model
    class Item:
        id: str
        label: str

    workflow = WorkflowBuilder()
    workflow.add_node("ItemCreateNode", "a", {"id": "1", "label": "first"})
    workflow.add_node("ItemCreateNode", "b", {"id": "2", "label": "second"})
    workflow.add_node("ItemCreateNode", "c", {"id": "3", "label": "third"})
    workflow.add_connection("a", "id", "b", "id")
    # c is isolated — it MUST still appear in graph.nodes.

    inspector = Inspector(db, workflow)
    graph = inspector.connection_graph()

    assert set(graph.nodes) == {"a", "b", "c"}
    # c should be both entry and exit because it has no edges.
    assert "c" in graph.entry_points
    assert "c" in graph.exit_points


@pytest.mark.regression
def test_inspector_workflow_summary_counts_all_nodes():
    """Regression: workflow_summary().node_count reflects every node,
    including isolated ones. Prior bug returned 1 for a 3-node workflow.
    """
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)

    @db.model
    class Ping:
        id: str

    workflow = WorkflowBuilder()
    for i in range(3):
        workflow.add_node("PingCreateNode", f"p{i}", {"id": str(i)})
    workflow.add_connection("p0", "id", "p1", "id")
    workflow.add_connection("p1", "id", "p2", "id")

    inspector = Inspector(db, workflow)
    summary = inspector.workflow_summary()

    assert summary.node_count == 3
    assert summary.connection_count == 2


@pytest.mark.regression
def test_inspector_model_reads_dataflow_registry_dict():
    """Regression: ModelInfo.schema is populated from DataFlow's
    {"class", "fields", "table_name"} registry entry, not a SQLAlchemy
    __table__ attribute (which DataFlow 2.0 models do not have).
    """
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)

    @db.model
    class Gadget:
        id: str
        name: str
        count: int

    inspector = Inspector(db)
    info = inspector.model("Gadget")

    assert info.name == "Gadget"
    assert info.table_name == "gadgets"
    assert set(info.schema.keys()) == {"id", "name", "count"}
    assert info.schema["id"]["primary_key"] is True
    assert info.schema["name"]["type"] == "str"
    assert info.schema["count"]["type"] == "int"
    assert info.primary_key == "id"


@pytest.mark.regression
@pytest.mark.parametrize(
    "node_id, expected_model, expected_op",
    [
        ("ProductCreateNode", "Product", "create"),
        ("UserReadByIdNode", "User", "read_by_id"),
        ("OrderBulkCreateNode", "Order", "bulk_create"),
        ("CustomerUpdateNode", "Customer", "update"),
        ("WidgetDeleteNode", "Widget", "delete"),
    ],
)
def test_inspector_node_parses_pascal_case(node_id, expected_model, expected_op):
    """Regression: NodeInfo parses the canonical {Model}{Op}Node format.

    The prior parser split on ``_`` only, so any PascalCase generated-node
    ID fell through to model="Unknown" / op="unknown" and produced an
    empty expected_params dict.
    """
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    inspector = Inspector(db)
    info = inspector.node(node_id)
    assert info.node_id == node_id
    assert info.model_name == expected_model
    assert info.node_type == expected_op
    # At least one expected param MUST be populated for the known ops.
    if expected_op in {"create", "update", "read_by_id"}:
        assert len(info.expected_params) >= 1
