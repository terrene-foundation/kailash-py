# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PlanValidator — deterministic structural and envelope validation.

All checks are deterministic. No LLM required.
Reuses graph_utils from kaizen.composition.graph_utils for cycle detection.

Spec reference: workspaces/kaizen-l3/briefs/05-plan-dag.md Section 4.
"""

from __future__ import annotations

import logging
from typing import Any

from kaizen.composition.graph_utils import validate_graph
from kaizen.l3.plan.types import EdgeType, Plan, PlanState

__all__ = ["PlanValidator"]

logger = logging.getLogger(__name__)


class PlanValidator:
    """Validates a Plan DAG for structural correctness and envelope feasibility.

    All methods are static/classmethod — no instance state required.
    """

    @staticmethod
    def validate_structure(plan: Plan) -> list[str]:
        """Validate structural invariants of the plan DAG.

        Checks:
        1. Node count >= 1 (INV-PLAN-05)
        2. No self-edges
        3. Referential integrity (edges reference existing nodes)
        4. Cycle detection via graph_utils (INV-PLAN-01)
        5. Input mapping consistency (source node exists, edge exists)
        6. Root existence (INV-PLAN-03)
        7. Leaf existence (INV-PLAN-04)

        Returns all errors found (not just the first).
        """
        errors: list[str] = []

        # 1. Non-empty plan (INV-PLAN-05)
        if not plan.nodes:
            errors.append("Plan must have at least one node (empty plan rejected)")

        # 2. Self-edges
        for edge in plan.edges:
            if edge.from_node == edge.to_node:
                errors.append(
                    f"Self-edge detected: node '{edge.from_node}' has an edge to itself"
                )

        # 3. Referential integrity
        node_ids = set(plan.nodes.keys())
        for edge in plan.edges:
            if edge.from_node not in node_ids:
                errors.append(
                    f"Edge references non-existent source node '{edge.from_node}'"
                )
            if edge.to_node not in node_ids:
                errors.append(
                    f"Edge references non-existent target node '{edge.to_node}'"
                )

        # 4. Cycle detection (only DATA_DEPENDENCY and COMPLETION_DEPENDENCY edges
        #    affect ordering; CO_START is advisory)
        ordering_edges = [
            e
            for e in plan.edges
            if e.edge_type in (EdgeType.DATA_DEPENDENCY, EdgeType.COMPLETION_DEPENDENCY)
            and e.from_node in node_ids
            and e.to_node in node_ids
        ]

        # Build adjacency for graph_utils: node -> list of predecessors (dependencies)
        # graph_utils expects adjacency[node] = [nodes that node depends on]
        # But our edges go from_node -> to_node meaning to_node depends on from_node.
        # graph_utils uses adjacency[node] = list of nodes it points to (successors)
        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for edge in ordering_edges:
            adjacency.setdefault(edge.from_node, []).append(edge.to_node)

        if node_ids:
            result = validate_graph(adjacency)
            if not result.is_acyclic:
                for cycle in result.cycles:
                    cycle_str = " -> ".join(cycle)
                    errors.append(f"Cycle detected in plan: {cycle_str}")

        # 5. Input mapping consistency
        for node_id, node in plan.nodes.items():
            for mapping_key, pno in node.input_mapping.items():
                # Source node must exist
                if pno.source_node not in node_ids:
                    errors.append(
                        f"Node '{node_id}' input_mapping['{mapping_key}'] references "
                        f"non-existent source node '{pno.source_node}'"
                    )
                else:
                    # A DATA_DEPENDENCY or COMPLETION_DEPENDENCY edge must exist
                    # from the source to this node
                    has_edge = any(
                        e.from_node == pno.source_node
                        and e.to_node == node_id
                        and e.edge_type
                        in (EdgeType.DATA_DEPENDENCY, EdgeType.COMPLETION_DEPENDENCY)
                        for e in plan.edges
                    )
                    if not has_edge:
                        errors.append(
                            f"Node '{node_id}' input_mapping['{mapping_key}'] references "
                            f"source '{pno.source_node}' but no DATA_DEPENDENCY or "
                            f"COMPLETION_DEPENDENCY edge exists from '{pno.source_node}' "
                            f"to '{node_id}'"
                        )

        # 6. Root existence (INV-PLAN-03)
        # Root = node with no incoming DATA_DEPENDENCY or COMPLETION_DEPENDENCY
        if plan.nodes:
            nodes_with_incoming: set[str] = set()
            for edge in plan.edges:
                if edge.edge_type in (
                    EdgeType.DATA_DEPENDENCY,
                    EdgeType.COMPLETION_DEPENDENCY,
                ):
                    nodes_with_incoming.add(edge.to_node)
            roots = node_ids - nodes_with_incoming
            if not roots:
                errors.append(
                    "Plan has no root node (every node has incoming "
                    "DATA_DEPENDENCY or COMPLETION_DEPENDENCY edges)"
                )

        # 7. Leaf existence (INV-PLAN-04)
        if plan.nodes:
            nodes_with_outgoing: set[str] = set()
            for edge in plan.edges:
                if edge.edge_type in (
                    EdgeType.DATA_DEPENDENCY,
                    EdgeType.COMPLETION_DEPENDENCY,
                ):
                    nodes_with_outgoing.add(edge.from_node)
            leaves = node_ids - nodes_with_outgoing
            if not leaves:
                errors.append(
                    "Plan has no leaf node (every node has outgoing "
                    "DATA_DEPENDENCY or COMPLETION_DEPENDENCY edges)"
                )

        return errors

    @staticmethod
    def validate_envelopes(plan: Plan) -> list[str]:
        """Validate envelope invariants.

        Checks:
        1. Budget summation (INV-PLAN-06): sum of node financial <= plan financial.
        2. Per-node tightening (INV-PLAN-07): each node financial <= plan financial.

        Returns all errors found.
        """
        errors: list[str] = []

        # Extract plan-level financial max_cost
        plan_financial = _extract_financial_max(plan.envelope)
        if plan_financial is None:
            # No financial constraint on plan -- nothing to validate
            return errors

        # Per-node tightening check
        total_node_cost = 0.0
        for node_id, node in plan.nodes.items():
            node_financial = _extract_financial_max(node.envelope)
            if node_financial is not None:
                total_node_cost += node_financial
                if node_financial > plan_financial:
                    errors.append(
                        f"Node '{node_id}' financial max_cost ({node_financial}) "
                        f"exceeds plan financial max_cost ({plan_financial}). "
                        f"Per-node tightening invariant violated."
                    )

        # Budget summation check
        if total_node_cost > plan_financial:
            errors.append(
                f"Budget summation violated: sum of node financial max_cost "
                f"({total_node_cost}) exceeds plan financial max_cost ({plan_financial})"
            )

        return errors

    @staticmethod
    def validate(plan: Plan) -> list[str]:
        """Run all validations (structure + envelopes).

        Returns the union of all errors. If no errors, transitions
        plan.state from Draft to Validated.
        """
        errors: list[str] = []
        errors.extend(PlanValidator.validate_structure(plan))
        errors.extend(PlanValidator.validate_envelopes(plan))

        if not errors:
            if plan.state == PlanState.DRAFT:
                plan.transition_to(PlanState.VALIDATED)
            elif plan.state == PlanState.VALIDATED:
                pass  # Already validated, idempotent
            else:
                logger.warning(
                    "Plan '%s' is in state %s, cannot transition to VALIDATED",
                    plan.plan_id,
                    plan.state.value,
                )

        return errors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_financial_max(envelope: dict[str, Any]) -> float | None:
    """Extract max_cost from a nested envelope dict.

    Supports both flat and nested structures:
    - {"financial": {"max_cost": 100.0}}
    - {"financial": 100.0}  (shorthand)
    """
    financial = envelope.get("financial")
    if financial is None:
        return None
    if isinstance(financial, dict):
        return financial.get("max_cost")
    if isinstance(financial, (int, float)):
        return float(financial)
    return None
