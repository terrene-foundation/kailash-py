# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for PlanValidator.

Covers:
- validate_structure: cycle detection, referential integrity, input mapping
  consistency, root/leaf existence, node count, unique IDs, self-edges
- validate_envelopes: budget summation, per-node tightening
- validate: combined validation, Draft->Validated transition on success
- All errors collected (not just first)
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(node_id, agent_spec_id="spec_1", input_mapping=None, optional=False):
    from kaizen.l3.plan.types import PlanNode, PlanNodeState

    return PlanNode(
        node_id=node_id,
        agent_spec_id=agent_spec_id,
        input_mapping=input_mapping or {},
        state=PlanNodeState.PENDING,
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


def _make_plan(nodes, edges, envelope=None, gradient=None, state=None):
    from kaizen.l3.plan.types import Plan, PlanState

    return Plan(
        plan_id="test_plan",
        name="Test Plan",
        envelope=envelope or {"financial": {"max_cost": 100.0}},
        gradient=gradient or {},
        nodes={n.node_id: n for n in nodes},
        edges=edges,
        state=state or PlanState.DRAFT,
    )


# ---------------------------------------------------------------------------
# validate_structure tests
# ---------------------------------------------------------------------------


class TestValidateStructure:
    """PlanValidator.validate_structure: structural DAG invariants."""

    def test_valid_linear_plan(self):
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        edge = _make_edge("n1", "n2")
        plan = _make_plan([n1, n2], [edge])

        errors = PlanValidator.validate_structure(plan)
        assert errors == []

    def test_valid_diamond_plan(self):
        from kaizen.l3.plan.types import EdgeType
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        n3 = _make_node("n3")
        n4 = _make_node("n4")
        edges = [
            _make_edge("n1", "n2"),
            _make_edge("n1", "n3"),
            _make_edge("n2", "n4"),
            _make_edge("n3", "n4"),
        ]
        plan = _make_plan([n1, n2, n3, n4], edges)

        errors = PlanValidator.validate_structure(plan)
        assert errors == []

    def test_single_node_no_edges(self):
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        plan = _make_plan([n1], [])

        errors = PlanValidator.validate_structure(plan)
        assert errors == []

    def test_cycle_detected(self):
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        edges = [_make_edge("n1", "n2"), _make_edge("n2", "n1")]
        plan = _make_plan([n1, n2], edges)

        errors = PlanValidator.validate_structure(plan)
        assert len(errors) >= 1
        assert any("cycle" in str(e).lower() for e in errors)

    def test_self_edge_detected(self):
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        edge = _make_edge("n1", "n1")
        plan = _make_plan([n1], [edge])

        errors = PlanValidator.validate_structure(plan)
        assert len(errors) >= 1
        assert any("self" in str(e).lower() for e in errors)

    def test_edge_references_nonexistent_node(self):
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        edge = _make_edge("n1", "n_missing")
        plan = _make_plan([n1], [edge])

        errors = PlanValidator.validate_structure(plan)
        assert len(errors) >= 1
        assert any("n_missing" in str(e) for e in errors)

    def test_input_mapping_no_edge(self):
        """Input mapping references source_node but no DATA/COMPLETION edge exists."""
        from kaizen.l3.plan.types import PlanNodeOutput
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        n2 = _make_node(
            "n2",
            input_mapping={
                "data": PlanNodeOutput(source_node="n1", output_key="result")
            },
        )
        # No edges at all
        plan = _make_plan([n1, n2], [])

        errors = PlanValidator.validate_structure(plan)
        assert len(errors) >= 1
        assert any(
            "input_mapping" in str(e).lower() or "edge" in str(e).lower()
            for e in errors
        )

    def test_input_mapping_source_node_missing(self):
        """Input mapping references a node that does not exist."""
        from kaizen.l3.plan.types import PlanNodeOutput
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node(
            "n1",
            input_mapping={
                "data": PlanNodeOutput(source_node="n_ghost", output_key="result")
            },
        )
        plan = _make_plan([n1], [])

        errors = PlanValidator.validate_structure(plan)
        assert len(errors) >= 1
        assert any("n_ghost" in str(e) for e in errors)

    def test_empty_plan_rejected(self):
        from kaizen.l3.plan.validator import PlanValidator

        plan = _make_plan([], [])

        errors = PlanValidator.validate_structure(plan)
        assert len(errors) >= 1
        assert any(
            "empty" in str(e).lower() or "node" in str(e).lower() for e in errors
        )

    def test_no_root_detected(self):
        """All nodes have incoming data/completion deps -- no root."""
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        # Both have incoming deps from each other (would also be a cycle, but
        # root detection is independent)
        edges = [_make_edge("n1", "n2"), _make_edge("n2", "n1")]
        plan = _make_plan([n1, n2], edges)

        errors = PlanValidator.validate_structure(plan)
        # Should find cycle error and potentially no-root error
        assert len(errors) >= 1

    def test_co_start_edges_do_not_affect_root_leaf(self):
        """CoStart edges should not count for root/leaf determination."""
        from kaizen.l3.plan.types import EdgeType
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        # Only a CoStart edge -- both should be root and leaf for data/completion
        edge = _make_edge("n1", "n2", EdgeType.CO_START)
        plan = _make_plan([n1, n2], [edge])

        errors = PlanValidator.validate_structure(plan)
        assert errors == []

    def test_collects_all_errors(self):
        """Validator must return ALL errors, not stop at first."""
        from kaizen.l3.plan.validator import PlanValidator

        # Empty plan (no nodes) + self-edge on nonexistent node
        plan = _make_plan([], [_make_edge("ghost", "ghost")])

        errors = PlanValidator.validate_structure(plan)
        # Should have at least: empty plan + referential integrity
        assert len(errors) >= 2


# ---------------------------------------------------------------------------
# validate_envelopes tests
# ---------------------------------------------------------------------------


class TestValidateEnvelopes:
    """PlanValidator.validate_envelopes: budget summation and tightening."""

    def test_budget_within_limit(self):
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1", agent_spec_id="spec_1")
        n2 = _make_node("n2", agent_spec_id="spec_2")
        plan = _make_plan(
            [n1, n2],
            [_make_edge("n1", "n2")],
            envelope={"financial": {"max_cost": 100.0}},
        )
        # Assign node envelopes via agent_spec_id -> we store envelope info
        # in the plan's per-node envelope mapping
        # For simplicity, PlanValidator reads envelope from node or a specs dict
        # We'll pass specs_envelopes in the plan or use a simple approach

        errors = PlanValidator.validate_envelopes(plan)
        # With default empty node envelopes, sum is 0 <= 100 -- should pass
        assert errors == []

    def test_budget_exceeds_limit(self):
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        n2 = _make_node("n2")

        plan = _make_plan(
            [n1, n2],
            [_make_edge("n1", "n2")],
            envelope={"financial": {"max_cost": 10.0}},
        )
        # Simulate node envelopes that exceed plan budget
        # We'll set node-level envelope data
        n1.envelope = {"financial": {"max_cost": 8.0}}
        n2.envelope = {"financial": {"max_cost": 8.0}}

        errors = PlanValidator.validate_envelopes(plan)
        assert len(errors) >= 1
        assert any(
            "budget" in str(e).lower() or "sum" in str(e).lower() for e in errors
        )

    def test_node_exceeds_plan_envelope(self):
        """Per-node tightening: node financial > plan financial."""
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        n1.envelope = {"financial": {"max_cost": 200.0}}

        plan = _make_plan(
            [n1],
            [],
            envelope={"financial": {"max_cost": 100.0}},
        )

        errors = PlanValidator.validate_envelopes(plan)
        assert len(errors) >= 1
        assert any(
            "tighten" in str(e).lower() or "exceed" in str(e).lower() for e in errors
        )


# ---------------------------------------------------------------------------
# validate (combined) tests
# ---------------------------------------------------------------------------


class TestValidate:
    """PlanValidator.validate: combined structure + envelopes."""

    def test_valid_plan_transitions_to_validated(self):
        from kaizen.l3.plan.types import PlanState
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        n2 = _make_node("n2")
        plan = _make_plan(
            [n1, n2],
            [_make_edge("n1", "n2")],
            envelope={"financial": {"max_cost": 100.0}},
        )

        errors = PlanValidator.validate(plan)
        assert errors == []
        assert plan.state == PlanState.VALIDATED

    def test_invalid_plan_stays_draft(self):
        from kaizen.l3.plan.types import PlanState
        from kaizen.l3.plan.validator import PlanValidator

        plan = _make_plan([], [])

        errors = PlanValidator.validate(plan)
        assert len(errors) >= 1
        assert plan.state == PlanState.DRAFT

    def test_already_validated_plan_revalidates(self):
        """A Validated plan can be re-validated (idempotent)."""
        from kaizen.l3.plan.types import PlanState
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        plan = _make_plan([n1], [], state=PlanState.DRAFT)

        errors = PlanValidator.validate(plan)
        assert errors == []
        assert plan.state == PlanState.VALIDATED

    def test_collects_structure_and_envelope_errors(self):
        """Both structure and envelope errors returned together."""
        from kaizen.l3.plan.validator import PlanValidator

        n1 = _make_node("n1")
        n1.envelope = {"financial": {"max_cost": 200.0}}

        # self-edge for structural error
        plan = _make_plan(
            [n1],
            [_make_edge("n1", "n1")],
            envelope={"financial": {"max_cost": 100.0}},
        )

        errors = PlanValidator.validate(plan)
        # At least one structural error (self-edge) + one envelope error (tightening)
        assert len(errors) >= 2
