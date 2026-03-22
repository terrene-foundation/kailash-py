# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Generic graph algorithms for DAG validation and topological ordering.

Extracted from dag_validator.py (P5) to be reusable by PlanValidator (M5).
Uses iterative DFS-based 3-color marking (WHITE/GRAY/BLACK) for cycle
detection and computes topological order via reverse post-order.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "CycleDetected",
    "GraphValidationResult",
    "detect_cycles",
    "topological_order",
    "validate_graph",
]


class CycleDetected(Exception):
    """Raised when a cycle is detected in a graph."""

    def __init__(self, cycles: list[list[str]]) -> None:
        self.cycles = cycles
        cycle_strs = [" -> ".join(c) for c in cycles]
        super().__init__(f"Cycles detected: {'; '.join(cycle_strs)}")


class GraphValidationResult:
    """Result of graph validation.

    Attributes:
        is_acyclic: True if the graph has no cycles.
        topological_order: Nodes in dependency order (predecessors first).
            Empty if cycles exist.
        cycles: List of detected cycles (each cycle is a list of node IDs).
    """

    __slots__ = ("is_acyclic", "topological_order", "cycles")

    def __init__(
        self,
        is_acyclic: bool,
        topological_order: list[str],
        cycles: list[list[str]],
    ) -> None:
        self.is_acyclic = is_acyclic
        self.topological_order = topological_order
        self.cycles = cycles


class _Color(Enum):
    WHITE = 0  # Unvisited
    GRAY = 1  # In current DFS path
    BLACK = 2  # Fully processed


def _reconstruct_cycle(
    current: str, back_target: str, parent_map: dict[str, str | None]
) -> list[str]:
    """Reconstruct a cycle from parent pointers."""
    cycle = [back_target, current]
    node = parent_map.get(current)
    visited_in_trace: set[str] = {back_target, current}
    while node is not None and node != back_target:
        if node in visited_in_trace:
            break
        visited_in_trace.add(node)
        cycle.append(node)
        node = parent_map.get(node)
    cycle.reverse()
    return cycle


def validate_graph(adjacency: dict[str, list[str]]) -> GraphValidationResult:
    """Validate a directed graph for cycles and compute topological order.

    Uses iterative DFS with 3-color marking. Handles disconnected components.

    Args:
        adjacency: Map of node_id -> list of predecessor node_ids (dependencies).
            Every node that appears as a value must also appear as a key.

    Returns:
        GraphValidationResult with is_acyclic, topological_order, and cycles.
    """
    if not adjacency:
        return GraphValidationResult(is_acyclic=True, topological_order=[], cycles=[])

    nodes = sorted(adjacency.keys())  # Deterministic traversal order
    color: dict[str, _Color] = {n: _Color.WHITE for n in nodes}
    parent: dict[str, str | None] = {n: None for n in nodes}
    cycles: list[list[str]] = []
    post_order: list[str] = []

    for start in nodes:
        if color[start] != _Color.WHITE:
            continue
        color[start] = _Color.GRAY
        stack: list[tuple[str, Any]] = [(start, iter(adjacency.get(start, [])))]
        while stack:
            node, children = stack[-1]
            try:
                dep = next(children)
                if dep not in color:
                    # Unknown node — skip (caller should validate referential integrity)
                    continue
                if color[dep] == _Color.GRAY:
                    cycle = _reconstruct_cycle(node, dep, parent)
                    cycles.append(cycle)
                elif color[dep] == _Color.WHITE:
                    parent[dep] = node
                    color[dep] = _Color.GRAY
                    stack.append((dep, iter(adjacency.get(dep, []))))
            except StopIteration:
                color[node] = _Color.BLACK
                post_order.append(node)
                stack.pop()

    if cycles:
        return GraphValidationResult(
            is_acyclic=False, topological_order=[], cycles=cycles
        )

    return GraphValidationResult(
        is_acyclic=True, topological_order=list(post_order), cycles=[]
    )


def detect_cycles(adjacency: dict[str, list[str]]) -> list[list[str]]:
    """Detect cycles in a directed graph.

    Args:
        adjacency: Map of node_id -> list of predecessor node_ids.

    Returns:
        List of cycles found. Empty list if the graph is acyclic.
    """
    return validate_graph(adjacency).cycles


def topological_order(adjacency: dict[str, list[str]]) -> list[str]:
    """Compute topological order of a directed acyclic graph.

    Args:
        adjacency: Map of node_id -> list of predecessor node_ids.

    Returns:
        Nodes in topological order (dependencies first).

    Raises:
        CycleDetected: If the graph contains cycles.
    """
    result = validate_graph(adjacency)
    if not result.is_acyclic:
        raise CycleDetected(result.cycles)
    return result.topological_order
