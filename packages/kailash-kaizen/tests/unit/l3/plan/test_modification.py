# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for PlanModification application.

Covers:
- AddNode: unique ID, cycle check, adds edges
- RemoveNode: only Pending/Ready/Skipped; Running raises error
- ReplaceNode: edge transfer
- AddEdge: cycle check
- RemoveEdge: removes existing, errors on missing
- UpdateSpec: Pending/Ready only
- SkipNode: transitions to Skipped
- Batch atomicity: all-or-nothing
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(
    node_id, agent_spec_id="spec_1", input_mapping=None, optional=False, state=None
):
    from kaizen.l3.plan.types import PlanNode, PlanNodeState

    return PlanNode(
        node_id=node_id,
        agent_spec_id=agent_spec_id,
        input_mapping=input_mapping or {},
        state=state or PlanNodeState.PENDING,
        instance_id=None,
        optional=optional,
        retry_count=0,
        output=None,
        error=None,
    )


def _make_edge(from_node, to_node, edge_type=None):
    from kaizen.l3.plan.types import EdgeType, PlanEdge

    return PlanEdge(
        from_node=from_node,
        to_node=to_node,
        edge_type=edge_type or EdgeType.DATA_DEPENDENCY,
    )


def _make_plan(nodes, edges, envelope=None, state=None):
    from kaizen.l3.plan.types import Plan, PlanState

    return Plan(
        plan_id="test_plan",
        name="Test Plan",
        envelope=envelope or {"financial": {"max_cost": 100.0}},
        gradient={},
        nodes={n.node_id: n for n in nodes},
        edges=edges,
        state=state or PlanState.DRAFT,
    )


# ---------------------------------------------------------------------------
# AddNode tests
# ---------------------------------------------------------------------------


class TestAddNode:
    """apply_modification with AddNode."""

    def test_add_node_success(self):
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification

        n1 = _make_node("n1")
        plan = _make_plan([n1], [])

        new_node = _make_node("n2")
        new_edge = _make_edge("n1", "n2")
        mod = PlanModification.add_node(node=new_node, edges=[new_edge])

        apply_modification(plan, mod)
        assert "n2" in plan.nodes
        assert any(e.to_node == "n2" for e in plan.edges)

    def test_add_node_duplicate_id_raises(self):
        from kaizen.l3.plan.errors import ModificationError
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification

        n1 = _make_node("n1")
        plan = _make_plan([n1], [])

        duplicate = _make_node("n1")
        mod = PlanModification.add_node(node=duplicate, edges=[])

        with pytest.raises(ModificationError, match="already exists"):
            apply_modification(plan, mod)

    def test_add_node_creates_cycle_raises(self):
        from kaizen.l3.plan.errors import ModificationError
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [_make_edge("n1", "n2")])

        new_node = _make_node("n3")
        # n2 -> n3 -> n1 would create a cycle
        edges = [_make_edge("n2", "n3"), _make_edge("n3", "n1")]
        mod = PlanModification.add_node(node=new_node, edges=edges)

        with pytest.raises(ModificationError, match="[Cc]ycle"):
            apply_modification(plan, mod)


# ---------------------------------------------------------------------------
# RemoveNode tests
# ---------------------------------------------------------------------------


class TestRemoveNode:
    """apply_modification with RemoveNode."""

    def test_remove_pending_node(self):
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [_make_edge("n1", "n2")])

        mod = PlanModification.remove_node(node_id="n2")
        apply_modification(plan, mod)
        assert "n2" not in plan.nodes
        assert not any(e.to_node == "n2" or e.from_node == "n2" for e in plan.edges)

    def test_remove_running_node_raises(self):
        from kaizen.l3.plan.errors import ModificationError
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification, PlanNodeState

        n1 = _make_node("n1", state=PlanNodeState.RUNNING)
        plan = _make_plan([n1], [])

        mod = PlanModification.remove_node(node_id="n1")
        with pytest.raises(ModificationError, match="[Rr]unning"):
            apply_modification(plan, mod)

    def test_remove_nonexistent_node_raises(self):
        from kaizen.l3.plan.errors import ModificationError
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification

        plan = _make_plan([_make_node("n1")], [])

        mod = PlanModification.remove_node(node_id="n_ghost")
        with pytest.raises(ModificationError, match="not found"):
            apply_modification(plan, mod)


# ---------------------------------------------------------------------------
# ReplaceNode tests
# ---------------------------------------------------------------------------


class TestReplaceNode:
    """apply_modification with ReplaceNode."""

    def test_replace_node_transfers_edges(self):
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        n3 = _make_node("n3")
        plan = _make_plan(
            [n1, n2, n3],
            [_make_edge("n1", "n2"), _make_edge("n2", "n3")],
        )

        replacement = _make_node("n2_v2")
        mod = PlanModification.replace_node(old_node_id="n2", new_node=replacement)
        apply_modification(plan, mod)

        assert "n2" not in plan.nodes
        assert "n2_v2" in plan.nodes
        # Edges should reference new node
        assert any(e.to_node == "n2_v2" and e.from_node == "n1" for e in plan.edges)
        assert any(e.from_node == "n2_v2" and e.to_node == "n3" for e in plan.edges)

    def test_replace_running_node_raises(self):
        from kaizen.l3.plan.errors import ModificationError
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification, PlanNodeState

        n1 = _make_node("n1", state=PlanNodeState.RUNNING)
        plan = _make_plan([n1], [])

        replacement = _make_node("n1_v2")
        mod = PlanModification.replace_node(old_node_id="n1", new_node=replacement)
        with pytest.raises(ModificationError, match="[Rr]unning"):
            apply_modification(plan, mod)


# ---------------------------------------------------------------------------
# AddEdge tests
# ---------------------------------------------------------------------------


class TestAddEdge:
    """apply_modification with AddEdge."""

    def test_add_edge_success(self):
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import EdgeType, PlanEdge, PlanModification

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [])

        edge = PlanEdge(
            from_node="n1", to_node="n2", edge_type=EdgeType.COMPLETION_DEPENDENCY
        )
        mod = PlanModification.add_edge(edge=edge)
        apply_modification(plan, mod)
        assert any(e.from_node == "n1" and e.to_node == "n2" for e in plan.edges)

    def test_add_edge_creates_cycle_raises(self):
        from kaizen.l3.plan.errors import ModificationError
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import EdgeType, PlanEdge, PlanModification

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [_make_edge("n1", "n2")])

        # Adding n2 -> n1 creates cycle
        edge = PlanEdge(
            from_node="n2", to_node="n1", edge_type=EdgeType.DATA_DEPENDENCY
        )
        mod = PlanModification.add_edge(edge=edge)
        with pytest.raises(ModificationError, match="[Cc]ycle"):
            apply_modification(plan, mod)


# ---------------------------------------------------------------------------
# RemoveEdge tests
# ---------------------------------------------------------------------------


class TestRemoveEdge:
    """apply_modification with RemoveEdge."""

    def test_remove_edge_success(self):
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [_make_edge("n1", "n2")])

        mod = PlanModification.remove_edge(from_node="n1", to_node="n2")
        apply_modification(plan, mod)
        assert not any(e.from_node == "n1" and e.to_node == "n2" for e in plan.edges)

    def test_remove_nonexistent_edge_raises(self):
        from kaizen.l3.plan.errors import ModificationError
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan([n1, n2], [])

        mod = PlanModification.remove_edge(from_node="n1", to_node="n2")
        with pytest.raises(ModificationError, match="not found"):
            apply_modification(plan, mod)


# ---------------------------------------------------------------------------
# UpdateSpec tests
# ---------------------------------------------------------------------------


class TestUpdateSpec:
    """apply_modification with UpdateSpec."""

    def test_update_spec_pending_node(self):
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification

        n1 = _make_node("n1", agent_spec_id="spec_v1")
        plan = _make_plan([n1], [])

        mod = PlanModification.update_spec(node_id="n1", new_spec_id="spec_v2")
        apply_modification(plan, mod)
        assert plan.nodes["n1"].agent_spec_id == "spec_v2"

    def test_update_spec_running_node_raises(self):
        from kaizen.l3.plan.errors import ModificationError
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification, PlanNodeState

        n1 = _make_node("n1", state=PlanNodeState.RUNNING)
        plan = _make_plan([n1], [])

        mod = PlanModification.update_spec(node_id="n1", new_spec_id="spec_v2")
        with pytest.raises(ModificationError, match="[Rr]unning"):
            apply_modification(plan, mod)


# ---------------------------------------------------------------------------
# SkipNode tests
# ---------------------------------------------------------------------------


class TestSkipNode:
    """apply_modification with SkipNode."""

    def test_skip_pending_node(self):
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification, PlanNodeState

        n1 = _make_node("n1")
        plan = _make_plan([n1], [])

        mod = PlanModification.skip_node(node_id="n1", reason="not needed")
        apply_modification(plan, mod)
        assert plan.nodes["n1"].state == PlanNodeState.SKIPPED

    def test_skip_running_node_raises(self):
        from kaizen.l3.plan.errors import ModificationError
        from kaizen.l3.plan.modification import apply_modification
        from kaizen.l3.plan.types import PlanModification, PlanNodeState

        n1 = _make_node("n1", state=PlanNodeState.RUNNING)
        plan = _make_plan([n1], [])

        mod = PlanModification.skip_node(node_id="n1", reason="want to skip")
        with pytest.raises(ModificationError, match="[Rr]unning"):
            apply_modification(plan, mod)


# ---------------------------------------------------------------------------
# Batch atomicity tests
# ---------------------------------------------------------------------------


class TestBatchAtomicity:
    """apply_modifications: all-or-nothing batch semantics."""

    def test_batch_success(self):
        from kaizen.l3.plan.modification import apply_modifications
        from kaizen.l3.plan.types import PlanModification

        n1 = _make_node("n1")
        plan = _make_plan([n1], [])

        new_n2 = _make_node("n2")
        new_n3 = _make_node("n3")
        mods = [
            PlanModification.add_node(node=new_n2, edges=[]),
            PlanModification.add_node(node=new_n3, edges=[_make_edge("n2", "n3")]),
        ]
        apply_modifications(plan, mods)
        assert "n2" in plan.nodes
        assert "n3" in plan.nodes

    def test_batch_rollback_on_failure(self):
        """If second modification fails, first is rolled back."""
        from kaizen.l3.plan.errors import ModificationError
        from kaizen.l3.plan.modification import apply_modifications
        from kaizen.l3.plan.types import PlanModification

        n1 = _make_node("n1")
        plan = _make_plan([n1], [])

        new_n2 = _make_node("n2")
        mods = [
            PlanModification.add_node(node=new_n2, edges=[]),
            # This will fail -- n1 already exists
            PlanModification.add_node(node=_make_node("n1"), edges=[]),
        ]
        with pytest.raises(ModificationError):
            apply_modifications(plan, mods)

        # n2 should NOT have been added (batch rollback)
        assert "n2" not in plan.nodes
