# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Delegation Graph Validator (CARE-003).

Provides graph-based cycle detection for delegation chains
using DFS (Depth-First Search) algorithm.

This module is a critical security component that prevents:
- Infinite loops in delegation chain traversal
- DoS attacks via cyclic delegation graphs
- Resource exhaustion from unbounded chain following
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Set

if TYPE_CHECKING:
    from eatp.chain import DelegationRecord


@dataclass
class DelegationGraph:
    """
    Graph representation of delegation relationships.

    Used for cycle detection and delegation chain analysis.
    The graph is built from delegation records where:
    - Nodes are agent IDs (delegator_id and delegatee_id)
    - Edges represent delegation relationships (delegator -> delegatee)
    """

    nodes: Set[str] = field(default_factory=set)
    edges: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def from_delegations(
        cls, delegations: List["DelegationRecord"]
    ) -> "DelegationGraph":
        """
        Build graph from delegation records.

        Args:
            delegations: List of DelegationRecord objects

        Returns:
            DelegationGraph with nodes and edges populated
        """
        nodes: Set[str] = set()
        edges: Dict[str, List[str]] = {}

        for delegation in delegations:
            delegator = delegation.delegator_id
            delegatee = delegation.delegatee_id

            nodes.add(delegator)
            nodes.add(delegatee)

            if delegator not in edges:
                edges[delegator] = []
            edges[delegator].append(delegatee)

        return cls(nodes=nodes, edges=edges)


class DelegationGraphValidator:
    """
    Graph-based validator for delegation chain properties.

    Uses DFS (Depth-First Search) for cycle detection and path analysis.
    This is a critical security component (CARE-003) that prevents
    infinite loops and DoS attacks in delegation chains.
    """

    def __init__(self, graph: DelegationGraph):
        """
        Initialize validator with a delegation graph.

        Args:
            graph: DelegationGraph to validate
        """
        self.graph = graph

    def detect_cycle(self) -> Optional[List[str]]:
        """
        Detect cycles using DFS with recursion stack.

        Uses three-color marking to track node states:
        - Not visited: node not yet seen
        - In recursion stack: node is part of current DFS path
        - Visited: node fully processed

        Returns:
            Cycle path as list of node IDs if found, None otherwise
        """
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(node: str, path: List[str]) -> Optional[List[str]]:
            """
            Recursive DFS traversal with cycle detection.

            Args:
                node: Current node being visited
                path: Path from root to current node

            Returns:
                Cycle path if found, None otherwise
            """
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self.graph.edges.get(node, []):
                if neighbor not in visited:
                    cycle = dfs(neighbor, path.copy())
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    # Found a cycle - return the path including the back edge
                    return path + [neighbor]

            rec_stack.remove(node)
            return None

        # Check all nodes to handle disconnected components
        for node in self.graph.nodes:
            if node not in visited:
                cycle = dfs(node, [])
                if cycle:
                    return cycle

        return None

    def validate_new_delegation(
        self,
        delegator_id: str,
        delegatee_id: str,
    ) -> bool:
        """
        Check if adding a new delegation would create a cycle.

        This method is used to validate delegations BEFORE they are
        created, preventing cycles from being introduced.

        IMPORTANT: This method does not permanently modify the graph.
        It temporarily adds the edge, checks for cycles, then restores
        the original graph state.

        Args:
            delegator_id: Who is delegating (source node)
            delegatee_id: Who is receiving delegation (target node)

        Returns:
            True if safe to add (no cycle would be created),
            False if adding would create a cycle
        """
        # Self-delegation is always a cycle
        if delegator_id == delegatee_id:
            return False

        # Save original state for restoration
        original_edges = {k: list(v) for k, v in self.graph.edges.items()}
        original_nodes = set(self.graph.nodes)

        try:
            # Temporarily add the proposed edge
            if delegator_id not in self.graph.edges:
                self.graph.edges[delegator_id] = []
            self.graph.edges[delegator_id].append(delegatee_id)
            self.graph.nodes.add(delegator_id)
            self.graph.nodes.add(delegatee_id)

            # Check for cycles with the new edge
            cycle = self.detect_cycle()

            # Return True if no cycle found (safe to add)
            return cycle is None
        finally:
            # Always restore original state
            self.graph.edges = original_edges
            self.graph.nodes = original_nodes
