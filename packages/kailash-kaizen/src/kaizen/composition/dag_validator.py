from __future__ import annotations

# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
DAG validator for composite agent pipelines.

Uses DFS-based 3-color marking (WHITE/GRAY/BLACK) for cycle detection
and computes topological order via reverse post-order.
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Set

from kaizen.composition.models import CompositionError, ValidationResult

logger = logging.getLogger(__name__)

__all__ = ["validate_dag"]


class _Color(Enum):
    """DFS node coloring for cycle detection."""

    WHITE = 0  # Unvisited
    GRAY = 1  # In current DFS path (back-edge to GRAY = cycle)
    BLACK = 2  # Fully processed


def validate_dag(
    agents: List[Dict[str, Any]],
    max_agents: int = 1000,
) -> ValidationResult:
    """Validate a composite agent DAG for cycles.

    Args:
        agents: List of agent descriptors, each with "name" (str) and
                "inputs_from" (list of dependency names).
        max_agents: Maximum composition size for DoS prevention.

    Returns:
        ValidationResult with is_valid, topological_order, cycles, warnings.

    Raises:
        CompositionError: If duplicate names are found or max_agents is exceeded.
    """
    if not agents:
        logger.debug("validate_dag called with empty agent list")
        return ValidationResult(is_valid=True)

    # --- Guard: max agents (DoS prevention) ---
    if len(agents) > max_agents:
        raise CompositionError(
            f"Composition exceeds maximum of {max_agents} agents "
            f"(got {len(agents)})",
            details={"agent_count": len(agents), "max_agents": max_agents},
        )

    # --- Guard: duplicate names ---
    names: List[str] = [a["name"] for a in agents]
    seen: Set[str] = set()
    duplicates: List[str] = []
    for name in names:
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        raise CompositionError(
            f"Duplicate agent names: {duplicates}",
            details={"duplicates": duplicates},
        )

    # --- Build adjacency list ---
    # adjacency[node] = list of nodes that node depends on (predecessors)
    name_set: Set[str] = set(names)
    adjacency: Dict[str, List[str]] = {name: [] for name in names}
    warnings: List[str] = []

    for agent in agents:
        name = agent["name"]
        inputs_from = agent.get("inputs_from", [])
        for dep in inputs_from:
            if dep not in name_set:
                warnings.append(
                    f"Agent '{name}' depends on '{dep}' which is not in the "
                    f"agent list"
                )
                logger.warning(
                    "Missing dependency: agent '%s' depends on '%s' "
                    "which is not declared",
                    name,
                    dep,
                )
            else:
                adjacency[name].append(dep)

    # --- Iterative DFS-based cycle detection with 3-color marking ---
    # (Recursive DFS would overflow Python's stack on deep chains up to max_agents)
    color: Dict[str, _Color] = {name: _Color.WHITE for name in names}
    parent: Dict[str, str | None] = {name: None for name in names}
    cycles: List[List[str]] = []
    post_order: List[str] = []

    def _reconstruct_cycle(
        current: str, back_target: str, parent_map: Dict[str, str | None]
    ) -> List[str]:
        """Reconstruct a cycle from parent pointers."""
        cycle = [back_target, current]
        node = parent_map.get(current)
        visited_in_trace: Set[str] = {back_target, current}
        while node is not None and node != back_target:
            if node in visited_in_trace:
                break
            visited_in_trace.add(node)
            cycle.append(node)
            node = parent_map.get(node)
        cycle.reverse()
        return cycle

    # Process all nodes (handles disconnected components)
    # Sort names for deterministic traversal order
    for start in sorted(names):
        if color[start] != _Color.WHITE:
            continue
        color[start] = _Color.GRAY
        stack = [(start, iter(adjacency.get(start, [])))]
        while stack:
            node, children = stack[-1]
            try:
                dep = next(children)
                if color[dep] == _Color.GRAY:
                    # Back-edge found: reconstruct cycle
                    cycle = _reconstruct_cycle(node, dep, parent)
                    cycles.append(cycle)
                    logger.info(
                        "Cycle detected in DAG: %s",
                        " -> ".join(cycle),
                    )
                elif color[dep] == _Color.WHITE:
                    parent[dep] = node
                    color[dep] = _Color.GRAY
                    stack.append((dep, iter(adjacency.get(dep, []))))
            except StopIteration:
                color[node] = _Color.BLACK
                post_order.append(node)
                stack.pop()

    if cycles:
        return ValidationResult(
            is_valid=False,
            topological_order=[],
            cycles=cycles,
            warnings=warnings,
        )

    # Reverse post-order = valid topological order
    # (dependencies come before dependents)
    topological_order = list(post_order)

    logger.debug(
        "DAG validation passed: %d agents, topological order: %s",
        len(agents),
        topological_order,
    )

    return ValidationResult(
        is_valid=True,
        topological_order=topological_order,
        cycles=[],
        warnings=warnings,
    )
