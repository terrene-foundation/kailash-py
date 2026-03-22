# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PlanModification application — typed mutations with validation.

Every modification is validated against structural and envelope invariants
before application. Batch modifications are atomic (all or nothing).

Spec reference: workspaces/kaizen-l3/briefs/05-plan-dag.md Section 4.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from kaizen.composition.graph_utils import validate_graph
from kaizen.l3.plan.errors import ModificationError
from kaizen.l3.plan.types import (
    EdgeType,
    Plan,
    PlanEdge,
    PlanModification,
    PlanNode,
    PlanNodeState,
)

__all__ = ["apply_modification", "apply_modifications"]

logger = logging.getLogger(__name__)


def apply_modification(plan: Plan, modification: PlanModification) -> None:
    """Apply a single modification to the plan.

    Validates the modification against all invariants before applying.
    If validation fails, the plan is unchanged.

    Raises:
        ModificationError: If the modification would violate any invariant.
    """
    tag = modification.tag
    details = modification.details

    if tag == "AddNode":
        _apply_add_node(plan, details["node"], details["edges"])
    elif tag == "RemoveNode":
        _apply_remove_node(plan, details["node_id"])
    elif tag == "ReplaceNode":
        _apply_replace_node(plan, details["old_node_id"], details["new_node"])
    elif tag == "AddEdge":
        _apply_add_edge(plan, details["edge"])
    elif tag == "RemoveEdge":
        _apply_remove_edge(plan, details["from_node"], details["to_node"])
    elif tag == "UpdateSpec":
        _apply_update_spec(plan, details["node_id"], details["new_spec_id"])
    elif tag == "SkipNode":
        _apply_skip_node(plan, details["node_id"], details["reason"])
    else:
        raise ModificationError(
            f"Unknown modification tag: {tag!r}",
            details={"tag": tag},
        )


def apply_modifications(plan: Plan, modifications: list[PlanModification]) -> None:
    """Apply a batch of modifications atomically.

    All modifications are applied tentatively in sequence. If any fails,
    the entire batch is rolled back (INV-PLAN-14).

    Raises:
        ModificationError: If any modification in the batch would violate
            an invariant. The plan is restored to its pre-batch state.
    """
    # Snapshot for rollback
    snapshot_nodes = copy.deepcopy(plan.nodes)
    snapshot_edges = list(plan.edges)
    snapshot_state = plan.state

    try:
        for mod in modifications:
            apply_modification(plan, mod)
    except ModificationError:
        # Rollback to pre-batch state
        plan.nodes = snapshot_nodes
        plan.edges = snapshot_edges
        plan.state = snapshot_state
        raise


# ---------------------------------------------------------------------------
# Individual modification implementations
# ---------------------------------------------------------------------------


def _apply_add_node(plan: Plan, node: PlanNode, edges: list[PlanEdge]) -> None:
    """Add a new node and its edges to the plan.

    Validates: unique ID, no cycle, referential integrity.
    """
    if node.node_id in plan.nodes:
        raise ModificationError(
            f"Node '{node.node_id}' already exists in plan",
            details={"node_id": node.node_id},
        )

    # Tentatively add node and edges, then check for cycles
    plan.nodes[node.node_id] = node
    plan.edges.extend(edges)

    # Validate referential integrity of new edges
    node_ids = set(plan.nodes.keys())
    for edge in edges:
        if edge.from_node not in node_ids:
            # Rollback
            del plan.nodes[node.node_id]
            plan.edges = [e for e in plan.edges if e not in edges]
            raise ModificationError(
                f"Edge references non-existent node '{edge.from_node}'",
                details={"from_node": edge.from_node},
            )
        if edge.to_node not in node_ids:
            del plan.nodes[node.node_id]
            plan.edges = [e for e in plan.edges if e not in edges]
            raise ModificationError(
                f"Edge references non-existent node '{edge.to_node}'",
                details={"to_node": edge.to_node},
            )

    # Check for cycles after addition
    if not _check_acyclic(plan):
        # Rollback
        del plan.nodes[node.node_id]
        plan.edges = [e for e in plan.edges if e not in edges]
        raise ModificationError(
            f"Adding node '{node.node_id}' with edges would create a cycle",
            details={"node_id": node.node_id},
        )


def _apply_remove_node(plan: Plan, node_id: str) -> None:
    """Remove a node and all its edges from the plan.

    Only valid for Pending, Ready, Skipped, or Completed nodes.
    Running nodes raise ModificationError (INV-PLAN-15).
    """
    if node_id not in plan.nodes:
        raise ModificationError(
            f"Node '{node_id}' not found in plan",
            details={"node_id": node_id},
        )

    node = plan.nodes[node_id]
    if node.state == PlanNodeState.RUNNING:
        raise ModificationError(
            f"Cannot remove node '{node_id}' while it is Running "
            f"(INV-PLAN-15: running node protection)",
            details={"node_id": node_id, "state": node.state.value},
        )

    # Remove node and all edges referencing it
    del plan.nodes[node_id]
    plan.edges = [
        e for e in plan.edges if e.from_node != node_id and e.to_node != node_id
    ]


def _apply_replace_node(plan: Plan, old_node_id: str, new_node: PlanNode) -> None:
    """Replace an existing node, transferring all edges.

    Old node must be in Pending, Ready, Failed, or Skipped state.
    Running nodes raise ModificationError (INV-PLAN-15).
    """
    if old_node_id not in plan.nodes:
        raise ModificationError(
            f"Node '{old_node_id}' not found in plan",
            details={"old_node_id": old_node_id},
        )

    old_node = plan.nodes[old_node_id]
    if old_node.state == PlanNodeState.RUNNING:
        raise ModificationError(
            f"Cannot replace node '{old_node_id}' while it is Running "
            f"(INV-PLAN-15: running node protection)",
            details={"old_node_id": old_node_id, "state": old_node.state.value},
        )

    # Transfer edges: replace old_node_id with new_node.node_id
    new_edges: list[PlanEdge] = []
    for edge in plan.edges:
        from_node = edge.from_node
        to_node = edge.to_node
        if from_node == old_node_id:
            from_node = new_node.node_id
        if to_node == old_node_id:
            to_node = new_node.node_id
        new_edges.append(
            PlanEdge(
                from_node=from_node,
                to_node=to_node,
                edge_type=edge.edge_type,
            )
        )

    # Remove old, add new
    del plan.nodes[old_node_id]
    plan.nodes[new_node.node_id] = new_node
    plan.edges = new_edges

    # Cycle check after replacement
    if not _check_acyclic(plan):
        # Rollback: restore old node and edges
        del plan.nodes[new_node.node_id]
        plan.nodes[old_node_id] = old_node
        # Re-transfer edges back (revert)
        reverted_edges: list[PlanEdge] = []
        for edge in new_edges:
            from_node = edge.from_node
            to_node = edge.to_node
            if from_node == new_node.node_id:
                from_node = old_node_id
            if to_node == new_node.node_id:
                to_node = old_node_id
            reverted_edges.append(
                PlanEdge(
                    from_node=from_node,
                    to_node=to_node,
                    edge_type=edge.edge_type,
                )
            )
        plan.edges = reverted_edges
        raise ModificationError(
            f"Replacing node '{old_node_id}' with '{new_node.node_id}' "
            f"would create a cycle",
            details={
                "old_node_id": old_node_id,
                "new_node_id": new_node.node_id,
            },
        )


def _apply_add_edge(plan: Plan, edge: PlanEdge) -> None:
    """Add a new edge between existing nodes.

    Must not create a cycle.
    """
    node_ids = set(plan.nodes.keys())
    if edge.from_node not in node_ids:
        raise ModificationError(
            f"Edge source node '{edge.from_node}' not found in plan",
            details={"from_node": edge.from_node},
        )
    if edge.to_node not in node_ids:
        raise ModificationError(
            f"Edge target node '{edge.to_node}' not found in plan",
            details={"to_node": edge.to_node},
        )

    # Tentatively add edge, check for cycles
    plan.edges.append(edge)
    if not _check_acyclic(plan):
        plan.edges.pop()
        raise ModificationError(
            f"Adding edge {edge.from_node} -> {edge.to_node} would create a cycle",
            details={"from_node": edge.from_node, "to_node": edge.to_node},
        )


def _apply_remove_edge(plan: Plan, from_node: str, to_node: str) -> None:
    """Remove an edge from the plan.

    Raises ModificationError if no such edge exists.
    """
    for i, edge in enumerate(plan.edges):
        if edge.from_node == from_node and edge.to_node == to_node:
            plan.edges.pop(i)
            return

    raise ModificationError(
        f"Edge {from_node} -> {to_node} not found in plan",
        details={"from_node": from_node, "to_node": to_node},
    )


def _apply_update_spec(plan: Plan, node_id: str, new_spec_id: str) -> None:
    """Update the agent_spec_id of a node.

    Only valid for Pending or Ready nodes.
    """
    if node_id not in plan.nodes:
        raise ModificationError(
            f"Node '{node_id}' not found in plan",
            details={"node_id": node_id},
        )

    node = plan.nodes[node_id]
    if node.state not in (PlanNodeState.PENDING, PlanNodeState.READY):
        raise ModificationError(
            f"Cannot update spec for node '{node_id}' in state {node.state.value}. "
            f"Only Pending or Ready nodes can be updated. "
            f"Running nodes have already been spawned from their original spec.",
            details={"node_id": node_id, "state": node.state.value},
        )

    node.agent_spec_id = new_spec_id


def _apply_skip_node(plan: Plan, node_id: str, reason: str) -> None:
    """Transition a node to Skipped state.

    Valid for Pending and Ready nodes. Running nodes raise error (INV-PLAN-15).
    """
    if node_id not in plan.nodes:
        raise ModificationError(
            f"Node '{node_id}' not found in plan",
            details={"node_id": node_id},
        )

    node = plan.nodes[node_id]
    if node.state == PlanNodeState.RUNNING:
        raise ModificationError(
            f"Cannot skip node '{node_id}' while it is Running "
            f"(INV-PLAN-15: running node protection)",
            details={"node_id": node_id, "state": node.state.value},
        )

    if node.state not in (PlanNodeState.PENDING, PlanNodeState.READY):
        raise ModificationError(
            f"Cannot skip node '{node_id}' in state {node.state.value}. "
            f"Only Pending or Ready nodes can be skipped via modification.",
            details={"node_id": node_id, "state": node.state.value},
        )

    node.transition_to(PlanNodeState.SKIPPED)
    node.error = f"Skipped: {reason}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_acyclic(plan: Plan) -> bool:
    """Check if the plan's ordering edges form a DAG.

    Only DATA_DEPENDENCY and COMPLETION_DEPENDENCY edges affect ordering.
    """
    node_ids = set(plan.nodes.keys())
    ordering_edges = [
        e
        for e in plan.edges
        if e.edge_type in (EdgeType.DATA_DEPENDENCY, EdgeType.COMPLETION_DEPENDENCY)
        and e.from_node in node_ids
        and e.to_node in node_ids
    ]

    adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for edge in ordering_edges:
        adjacency[edge.from_node].append(edge.to_node)

    result = validate_graph(adjacency)
    return result.is_acyclic
