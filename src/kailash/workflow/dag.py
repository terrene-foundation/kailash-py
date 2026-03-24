# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Custom directed graph implementation replacing networkx for workflow execution.

WorkflowDAG uses dual adjacency lists (forward + reverse edges) for O(1)
neighbor lookups. Implements only the graph operations actually used by
the Kailash Core SDK, avoiding the overhead of the full networkx library.

Algorithms implemented:
- Kahn's algorithm for topological sort (iterative, O(V+E))
- Tarjan's algorithm for strongly connected components (O(V+E))
- Johnson's algorithm for simple cycle enumeration (for error messages)
- BFS for ancestors and descendants (O(V+E))

All algorithm results are cached with dirty-flag invalidation on mutation.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Iterable, Iterator, Literal, overload

logger = logging.getLogger(__name__)

__all__ = ["WorkflowDAG", "CycleDetectedError"]


class _NodeView:
    """Lightweight view over graph nodes that mimics networkx's NodeView.

    Supports:
    - Iteration: ``for node in view``
    - Membership: ``node in view``
    - Subscript: ``view[node_id]`` returns node attrs dict
    - Length: ``len(view)``
    - Callable: ``view()`` returns list of node IDs, ``view(data=True)`` returns [(id, attrs), ...]
    - ``.get(node_id, default)`` for safe dict-like access
    """

    __slots__ = ("_node_attrs",)

    def __init__(self, node_attrs: dict[str, dict[str, Any]]) -> None:
        self._node_attrs = node_attrs

    @overload
    def __call__(self, data: Literal[False] = ...) -> list[str]: ...
    @overload
    def __call__(self, data: Literal[True]) -> list[tuple[str, dict[str, Any]]]: ...

    def __call__(
        self, data: bool = False
    ) -> list[str] | list[tuple[str, dict[str, Any]]]:
        if data:
            return [(nid, dict(attrs)) for nid, attrs in self._node_attrs.items()]
        return list(self._node_attrs.keys())

    def __iter__(self) -> Iterator[str]:
        return iter(self._node_attrs)

    def __contains__(self, node: str) -> bool:
        return node in self._node_attrs

    def __len__(self) -> int:
        return len(self._node_attrs)

    def __getitem__(self, node: str) -> dict[str, Any]:
        return self._node_attrs[node]

    def __setitem__(self, node: str, value: dict[str, Any]) -> None:
        if node not in self._node_attrs:
            raise KeyError(
                f"Cannot create node '{node}' via __setitem__. Use add_node() instead."
            )
        self._node_attrs[node] = value

    def get(self, node: str, default: Any = None) -> dict[str, Any] | Any:
        return self._node_attrs.get(node, default)

    def __repr__(self) -> str:
        return f"_NodeView({list(self._node_attrs.keys())})"


class _EdgeView:
    """Lightweight view over graph edges that mimics networkx's EdgeView.

    Supports:
    - Iteration: ``for (src, dst) in view``
    - Length: ``len(view)``
    - Callable: ``view()`` returns list of (src, dst), ``view(data=True)`` returns [(src, dst, attrs), ...]
    """

    __slots__ = ("_edge_attrs",)

    def __init__(self, edge_attrs: dict[tuple[str, str], dict[str, Any]]) -> None:
        self._edge_attrs = edge_attrs

    @overload
    def __call__(self, data: Literal[False] = ...) -> list[tuple[str, str]]: ...
    @overload
    def __call__(
        self, data: Literal[True]
    ) -> list[tuple[str, str, dict[str, Any]]]: ...

    def __call__(
        self, data: bool = False
    ) -> list[tuple[str, str]] | list[tuple[str, str, dict[str, Any]]]:
        if data:
            return [(s, t, dict(attrs)) for (s, t), attrs in self._edge_attrs.items()]
        return list(self._edge_attrs.keys())

    def __iter__(self) -> Iterator[tuple[str, str]]:
        return iter(self._edge_attrs)

    def __contains__(self, edge: tuple[str, str]) -> bool:
        return edge in self._edge_attrs

    def __len__(self) -> int:
        return len(self._edge_attrs)

    def __repr__(self) -> str:
        return f"_EdgeView({list(self._edge_attrs.keys())})"


class CycleDetectedError(Exception):
    """Raised when a topological sort is requested on a graph containing cycles."""

    def __init__(
        self,
        message: str = "Graph contains a cycle",
        cycles: list[list[str]] | None = None,
    ):
        self.cycles = cycles or []
        super().__init__(message)


class WorkflowDAG:
    """Directed graph optimized for workflow DAG operations.

    Drop-in replacement for networkx.DiGraph() for the subset of operations
    used by the Kailash Core SDK. Uses dual adjacency lists for O(1) neighbor
    lookups and caches algorithm results with dirty-flag invalidation.

    Data structures:
        _successors:   dict[str, set[str]]  — forward adjacency list
        _predecessors: dict[str, set[str]]  — reverse adjacency list
        _node_attrs:   dict[str, dict]      — node attributes
        _edge_attrs:   dict[tuple, dict]    — edge attributes: {(src, dst): attrs}

    Caches (invalidated on any mutation):
        _topo_cache:   list[str] | None     — topological sort result
        _scc_cache:    list[set[str]] | None — strongly connected components
    """

    __slots__ = (
        "_successors",
        "_predecessors",
        "_node_attrs",
        "_edge_attrs",
        "_topo_cache",
        "_scc_cache",
    )

    def __init__(self) -> None:
        self._successors: dict[str, set[str]] = {}
        self._predecessors: dict[str, set[str]] = {}
        self._node_attrs: dict[str, dict[str, Any]] = {}
        self._edge_attrs: dict[tuple[str, str], dict[str, Any]] = {}
        self._topo_cache: list[str] | None = None
        self._scc_cache: list[set[str]] | None = None

    # -------------------------------------------------------------------
    # Cache management
    # -------------------------------------------------------------------

    def _invalidate_caches(self) -> None:
        """Invalidate all algorithm caches. Called on every mutation."""
        self._topo_cache = None
        self._scc_cache = None

    # -------------------------------------------------------------------
    # Construction
    # -------------------------------------------------------------------

    def add_node(self, node_id: str, **attrs: Any) -> None:
        """Add a node with optional attributes.

        If the node already exists, its attributes are updated (merged).

        Args:
            node_id: Unique node identifier.
            **attrs: Arbitrary key-value attributes for the node.
        """
        if node_id not in self._successors:
            self._successors[node_id] = set()
            self._predecessors[node_id] = set()
            self._node_attrs[node_id] = {}
            self._invalidate_caches()
        if attrs:
            self._node_attrs[node_id].update(attrs)

    def add_edge(self, source: str, target: str, **attrs: Any) -> None:
        """Add a directed edge from source to target with optional attributes.

        Auto-creates nodes if they do not exist. If the edge already exists,
        its attributes are replaced (matching networkx behavior).

        Args:
            source: Source node ID.
            target: Target node ID.
            **attrs: Arbitrary key-value attributes for the edge.
        """
        # Auto-create nodes (without triggering extra invalidations)
        if source not in self._successors:
            self._successors[source] = set()
            self._predecessors[source] = set()
            self._node_attrs[source] = {}
        if target not in self._successors:
            self._successors[target] = set()
            self._predecessors[target] = set()
            self._node_attrs[target] = {}

        self._successors[source].add(target)
        self._predecessors[target].add(source)
        self._edge_attrs[(source, target)] = attrs
        self._invalidate_caches()

    def add_nodes_from(self, nodes_with_data: Iterable) -> None:
        """Add multiple nodes from an iterable.

        Accepts either:
        - An iterable of node IDs: ``["a", "b", "c"]``
        - An iterable of (node_id, attrs) tuples: ``[("a", {"x": 1}), ("b", {"y": 2})]``

        Matches networkx's ``add_nodes_from`` behavior.

        Args:
            nodes_with_data: Iterable of node IDs or (node_id, attribute_dict) tuples.
        """
        for item in nodes_with_data:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], dict):
                node_id, attrs = item
                self.add_node(node_id, **attrs)
            else:
                # item is a plain node ID
                self.add_node(str(item))

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all its incident edges.

        Args:
            node_id: The node to remove.

        Raises:
            KeyError: If node_id does not exist.
        """
        if node_id not in self._successors:
            raise KeyError(f"Node '{node_id}' not in graph")

        # Remove all outgoing edges
        for target in list(self._successors[node_id]):
            self._predecessors[target].discard(node_id)
            self._edge_attrs.pop((node_id, target), None)

        # Remove all incoming edges
        for source in list(self._predecessors[node_id]):
            self._successors[source].discard(node_id)
            self._edge_attrs.pop((source, node_id), None)

        del self._successors[node_id]
        del self._predecessors[node_id]
        del self._node_attrs[node_id]
        self._invalidate_caches()

    def remove_edge(self, source: str, target: str) -> None:
        """Remove a directed edge.

        Args:
            source: Source node ID.
            target: Target node ID.

        Raises:
            KeyError: If the edge does not exist.
        """
        if (source, target) not in self._edge_attrs:
            raise KeyError(f"Edge ({source!r}, {target!r}) not in graph")

        self._successors[source].discard(target)
        self._predecessors[target].discard(source)
        del self._edge_attrs[(source, target)]
        self._invalidate_caches()

    # -------------------------------------------------------------------
    # Query
    # -------------------------------------------------------------------

    @property
    def nodes(self) -> _NodeView:
        """Return a view over all nodes (networkx-compatible).

        Supports:
        - ``graph.nodes`` — iterable, supports ``in``, ``len()``, ``[]``
        - ``graph.nodes()`` — returns list of node IDs
        - ``graph.nodes(data=True)`` — returns [(id, attrs), ...]
        - ``graph.nodes[node_id]`` — returns node attrs dict
        - ``node_id in graph.nodes`` — membership test
        """
        return _NodeView(self._node_attrs)

    @property
    def edges(self) -> _EdgeView:
        """Return a view over all edges (networkx-compatible).

        Supports:
        - ``graph.edges`` — iterable, supports ``in``, ``len()``
        - ``graph.edges()`` — returns list of (src, dst) tuples
        - ``graph.edges(data=True)`` — returns [(src, dst, attrs), ...]
        """
        return _EdgeView(self._edge_attrs)

    def predecessors(self, node: str) -> Iterator[str]:
        """Return an iterator over direct predecessors of a node.

        Args:
            node: The node ID.

        Raises:
            KeyError: If node does not exist.
        """
        if node not in self._predecessors:
            raise KeyError(f"Node '{node}' not in graph")
        return iter(self._predecessors[node])

    def successors(self, node: str) -> Iterator[str]:
        """Return an iterator over direct successors of a node.

        Args:
            node: The node ID.

        Raises:
            KeyError: If node does not exist.
        """
        if node not in self._successors:
            raise KeyError(f"Node '{node}' not in graph")
        return iter(self._successors[node])

    @overload
    def in_edges(
        self, node: str, data: Literal[False] = ...
    ) -> list[tuple[str, str]]: ...
    @overload
    def in_edges(
        self, node: str, data: Literal[True]
    ) -> list[tuple[str, str, dict[str, Any]]]: ...

    def in_edges(
        self, node: str, data: bool = False
    ) -> list[tuple[str, str]] | list[tuple[str, str, dict[str, Any]]]:
        """Return incoming edges for a node.

        Args:
            node: The target node ID.
            data: If True, return (source, node, attrs) tuples.

        Raises:
            KeyError: If node does not exist.
        """
        if node not in self._predecessors:
            raise KeyError(f"Node '{node}' not in graph")
        if data:
            return [
                (src, node, dict(self._edge_attrs[(src, node)]))
                for src in self._predecessors[node]
            ]
        return [(src, node) for src in self._predecessors[node]]

    @overload
    def out_edges(
        self, node: str, data: Literal[False] = ...
    ) -> list[tuple[str, str]]: ...
    @overload
    def out_edges(
        self, node: str, data: Literal[True]
    ) -> list[tuple[str, str, dict[str, Any]]]: ...

    def out_edges(
        self, node: str, data: bool = False
    ) -> list[tuple[str, str]] | list[tuple[str, str, dict[str, Any]]]:
        """Return outgoing edges for a node.

        Args:
            node: The source node ID.
            data: If True, return (node, target, attrs) tuples.

        Raises:
            KeyError: If node does not exist.
        """
        if node not in self._successors:
            raise KeyError(f"Node '{node}' not in graph")
        if data:
            return [
                (node, dst, dict(self._edge_attrs[(node, dst)]))
                for dst in self._successors[node]
            ]
        return [(node, dst) for dst in self._successors[node]]

    def has_node(self, node: str) -> bool:
        """Check if a node exists in the graph."""
        return node in self._node_attrs

    def has_edge(self, source: str, target: str) -> bool:
        """Check if an edge exists in the graph."""
        return (source, target) in self._edge_attrs

    def get_edge_data(self, source: str, target: str) -> dict[str, Any] | None:
        """Return edge attributes for the given edge, or None if edge doesn't exist.

        Returns a copy of the attributes dict (matching networkx behavior where
        the dict is mutable but changes don't propagate without explicit set).
        """
        attrs = self._edge_attrs.get((source, target))
        if attrs is None:
            return None
        return dict(attrs)

    def in_degree(self, node: str) -> int:
        """Return the number of incoming edges for a node.

        Args:
            node: The node ID.

        Raises:
            KeyError: If node does not exist.
        """
        if node not in self._predecessors:
            raise KeyError(f"Node '{node}' not in graph")
        return len(self._predecessors[node])

    def out_degree(self, node: str) -> int:
        """Return the number of outgoing edges for a node.

        Args:
            node: The node ID.

        Raises:
            KeyError: If node does not exist.
        """
        if node not in self._successors:
            raise KeyError(f"Node '{node}' not in graph")
        return len(self._successors[node])

    def subgraph(self, nodes: Iterable[str]) -> WorkflowDAG:
        """Return a new WorkflowDAG containing only the specified nodes and their internal edges.

        Args:
            nodes: Collection of node IDs to include.

        Returns:
            A new WorkflowDAG instance with the specified nodes and edges between them.
        """
        node_set = set(nodes)
        sub = WorkflowDAG()
        for nid in node_set:
            if nid in self._node_attrs:
                sub.add_node(nid, **self._node_attrs[nid])
        for (src, dst), attrs in self._edge_attrs.items():
            if src in node_set and dst in node_set:
                sub.add_edge(src, dst, **attrs)
        return sub

    def copy(self) -> WorkflowDAG:
        """Return a deep copy of this graph.

        Returns:
            A new independent WorkflowDAG instance with the same nodes and edges.
        """
        new_dag = WorkflowDAG()
        for nid, attrs in self._node_attrs.items():
            new_dag.add_node(nid, **attrs)
        for (src, dst), attrs in self._edge_attrs.items():
            new_dag.add_edge(src, dst, **attrs)
        return new_dag

    def __len__(self) -> int:
        """Return the number of nodes in the graph."""
        return len(self._node_attrs)

    def __contains__(self, node: str) -> bool:
        """Check if a node exists in the graph (supports 'in' operator)."""
        return node in self._node_attrs

    def __getitem__(self, node: str) -> dict[str, dict[str, Any]]:
        """Return adjacency dict for a node (networkx compatibility).

        ``graph[node]`` returns a dict mapping each successor to its edge attrs.
        ``graph[u][v]`` returns the edge data dict for edge (u, v).

        Raises:
            KeyError: If node does not exist.
        """
        if node not in self._successors:
            raise KeyError(f"Node '{node}' not in graph")
        return {
            succ: self._edge_attrs.get((node, succ), {})
            for succ in self._successors[node]
        }

    # -------------------------------------------------------------------
    # Algorithms (cached)
    # -------------------------------------------------------------------

    def topological_sort(self) -> list[str]:
        """Return nodes in topological order using Kahn's algorithm.

        Returns a list of node IDs such that for every edge (u, v),
        u appears before v in the list.

        Results are cached until the graph is mutated.

        Returns:
            Topologically ordered list of node IDs.

        Raises:
            CycleDetectedError: If the graph contains a cycle.
        """
        if self._topo_cache is not None:
            return self._topo_cache

        if not self._node_attrs:
            self._topo_cache = []
            return self._topo_cache

        # Kahn's algorithm: iterative topological sort
        # 1. Compute in-degree for all nodes
        in_degree: dict[str, int] = {
            node: len(preds) for node, preds in self._predecessors.items()
        }

        # 2. Initialize queue with all zero in-degree nodes
        # Use sorted() for deterministic ordering (matches networkx behavior)
        queue: deque[str] = deque(
            sorted(node for node, deg in in_degree.items() if deg == 0)
        )

        result: list[str] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            # Process successors in sorted order for deterministic output
            for successor in sorted(self._successors[node]):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(result) != len(self._node_attrs):
            # Not all nodes were processed — cycle exists
            cycles = self.simple_cycles()
            cycle_desc = ", ".join(str(c) for c in cycles[:3])
            raise CycleDetectedError(
                f"Graph contains {len(cycles)} cycle(s): {cycle_desc}",
                cycles=cycles,
            )

        self._topo_cache = result
        return self._topo_cache

    def strongly_connected_components(self) -> list[set[str]]:
        """Find all strongly connected components using Tarjan's algorithm.

        Returns a list of sets, where each set contains the node IDs of one
        strongly connected component.

        Results are cached until the graph is mutated.

        Returns:
            List of sets of node IDs, one set per SCC.
        """
        if self._scc_cache is not None:
            return self._scc_cache

        if not self._node_attrs:
            self._scc_cache = []
            return self._scc_cache

        # Tarjan's algorithm (iterative to avoid stack overflow on large graphs)
        index_counter = [0]
        stack: list[str] = []
        on_stack: set[str] = set()
        index: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        result: list[set[str]] = []

        def strongconnect(v: str) -> None:
            # Use an explicit call stack to avoid Python recursion limit
            call_stack: list[tuple[str, Iterator[str]]] = []
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)
            call_stack.append((v, iter(sorted(self._successors[v]))))

            while call_stack:
                v, successors_iter = call_stack[-1]
                pushed = False
                for w in successors_iter:
                    if w not in index:
                        # w has not been visited; recurse
                        index[w] = index_counter[0]
                        lowlink[w] = index_counter[0]
                        index_counter[0] += 1
                        stack.append(w)
                        on_stack.add(w)
                        call_stack.append((w, iter(sorted(self._successors[w]))))
                        pushed = True
                        break
                    elif w in on_stack:
                        lowlink[v] = min(lowlink[v], index[w])

                if not pushed:
                    # All successors processed
                    if lowlink[v] == index[v]:
                        # v is root of an SCC
                        scc: set[str] = set()
                        while True:
                            w = stack.pop()
                            on_stack.discard(w)
                            scc.add(w)
                            if w == v:
                                break
                        result.append(scc)

                    call_stack.pop()
                    if call_stack:
                        # Update parent's lowlink
                        parent = call_stack[-1][0]
                        lowlink[parent] = min(lowlink[parent], lowlink[v])

        for node in sorted(self._node_attrs.keys()):
            if node not in index:
                strongconnect(node)

        self._scc_cache = result
        return self._scc_cache

    def simple_cycles(self) -> list[list[str]]:
        """Find all simple cycles in the graph using Johnson's algorithm.

        This is primarily used for generating error messages when cycles are
        detected. For large graphs with many cycles, this can be expensive.

        Returns:
            List of cycles, where each cycle is a list of node IDs forming
            the cycle path (not including the closing edge back to start).
        """
        if not self._node_attrs:
            return []

        # Johnson's algorithm for finding all simple cycles
        # Reference: Donald B. Johnson, "Finding All the Elementary Circuits of a Directed Graph"
        # SIAM J. Comput., 4(1), 77-84, 1975.

        cycles: list[list[str]] = []
        # Work with sorted nodes for deterministic output
        all_nodes = sorted(self._node_attrs.keys())

        def _unblock(
            node: str, blocked: set[str], blocked_map: dict[str, set[str]]
        ) -> None:
            """Unblock a node and recursively unblock all nodes blocked by it."""
            unblock_stack = [node]
            while unblock_stack:
                u = unblock_stack.pop()
                if u in blocked:
                    blocked.discard(u)
                    if u in blocked_map:
                        for w in blocked_map[u]:
                            unblock_stack.append(w)
                        del blocked_map[u]

        for start_idx, start_node in enumerate(all_nodes):
            # Build subgraph induced by nodes from start_idx onward
            subgraph_nodes = set(all_nodes[start_idx:])
            if not subgraph_nodes:
                continue

            # Build adjacency for the subgraph
            adj: dict[str, list[str]] = {}
            for node in subgraph_nodes:
                adj[node] = sorted(
                    s for s in self._successors.get(node, set()) if s in subgraph_nodes
                )

            # Find SCCs in the subgraph that contain start_node
            # Use a simplified SCC detection for this subgraph
            scc_containing_start = _find_scc_containing(start_node, adj, subgraph_nodes)
            if (
                scc_containing_start is None
                or len(scc_containing_start) < 2
                and start_node not in self._successors.get(start_node, set())
            ):
                # Check self-loop separately
                if start_node in self._successors.get(start_node, set()):
                    cycles.append([start_node])
                continue

            # Johnson's circuit finding within this SCC
            blocked: set[str] = set()
            blocked_map: dict[str, set[str]] = {}
            path: list[str] = [start_node]
            blocked.add(start_node)

            # Restrict adjacency to the SCC
            scc_adj: dict[str, list[str]] = {}
            for node in scc_containing_start:
                scc_adj[node] = sorted(
                    s for s in adj.get(node, []) if s in scc_containing_start
                )

            # DFS-based circuit finding (iterative)
            call_stack: list[tuple[str, int]] = [(start_node, 0)]
            found_cycle_at_level: set[int] = set()

            while call_stack:
                v, next_idx = call_stack[-1]
                neighbors = scc_adj.get(v, [])

                if next_idx < len(neighbors):
                    w = neighbors[next_idx]
                    call_stack[-1] = (v, next_idx + 1)

                    if w == start_node:
                        # Found a cycle
                        cycles.append(list(path))
                        found_cycle_at_level.add(len(call_stack) - 1)
                    elif w not in blocked:
                        path.append(w)
                        blocked.add(w)
                        call_stack.append((w, 0))
                else:
                    # Backtrack
                    level = len(call_stack) - 1
                    if level in found_cycle_at_level:
                        _unblock(v, blocked, blocked_map)
                        found_cycle_at_level.discard(level)
                    else:
                        for w in scc_adj.get(v, []):
                            if w not in blocked_map:
                                blocked_map[w] = set()
                            blocked_map[w].add(v)

                    call_stack.pop()
                    if path and path[-1] == v:
                        path.pop()

        return cycles

    def is_dag(self) -> bool:
        """Check if the graph is a directed acyclic graph.

        Returns True if the graph has no cycles, False otherwise.
        Uses SCC detection: a DAG has only singleton SCCs (no self-loops).

        Returns:
            True if the graph is a DAG, False otherwise.
        """
        if not self._node_attrs:
            return True

        sccs = self.strongly_connected_components()
        for scc in sccs:
            if len(scc) > 1:
                return False
            # Check for self-loops (single-node SCC with self-edge)
            node = next(iter(scc))
            if node in self._successors.get(node, set()):
                return False
        return True

    def ancestors(self, node: str) -> set[str]:
        """Find all ancestors of a node (all nodes that have a path TO node).

        Uses BFS traversal on the reverse graph (predecessors).

        Args:
            node: The node to find ancestors for.

        Returns:
            Set of all ancestor node IDs (does not include node itself).

        Raises:
            KeyError: If node does not exist.
        """
        if node not in self._predecessors:
            raise KeyError(f"Node '{node}' not in graph")

        visited: set[str] = set()
        queue: deque[str] = deque(self._predecessors[node])
        visited.update(self._predecessors[node])

        while queue:
            current = queue.popleft()
            for pred in self._predecessors[current]:
                if pred not in visited:
                    visited.add(pred)
                    queue.append(pred)

        return visited

    def descendants(self, node: str) -> set[str]:
        """Find all descendants of a node (all nodes reachable FROM node).

        Uses BFS traversal on the forward graph (successors).

        Args:
            node: The node to find descendants for.

        Returns:
            Set of all descendant node IDs (does not include node itself).

        Raises:
            KeyError: If node does not exist.
        """
        if node not in self._successors:
            raise KeyError(f"Node '{node}' not in graph")

        visited: set[str] = set()
        queue: deque[str] = deque(self._successors[node])
        visited.update(self._successors[node])

        while queue:
            current = queue.popleft()
            for succ in self._successors[current]:
                if succ not in visited:
                    visited.add(succ)
                    queue.append(succ)

        return visited

    # -------------------------------------------------------------------
    # String representation
    # -------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"WorkflowDAG(nodes={len(self._node_attrs)}, edges={len(self._edge_attrs)})"
        )


def _find_scc_containing(
    start: str, adj: dict[str, list[str]], nodes: set[str]
) -> set[str] | None:
    """Find the SCC containing start in the given subgraph.

    Uses Tarjan's algorithm restricted to the provided adjacency and node set.

    Returns the SCC set containing start, or None if start is not
    reachable from itself (singleton without self-loop).
    """
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}

    result_scc: set[str] | None = None

    def strongconnect(v: str) -> None:
        nonlocal result_scc
        call_stack: list[tuple[str, Iterator[str]]] = []

        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        call_stack.append((v, iter(adj.get(v, []))))

        while call_stack:
            v_cur, successors_iter = call_stack[-1]
            pushed = False
            for w in successors_iter:
                if w not in nodes:
                    continue
                if w not in index:
                    index[w] = index_counter[0]
                    lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    call_stack.append((w, iter(adj.get(w, []))))
                    pushed = True
                    break
                elif w in on_stack:
                    lowlink[v_cur] = min(lowlink[v_cur], index[w])

            if not pushed:
                if lowlink[v_cur] == index[v_cur]:
                    scc: set[str] = set()
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        scc.add(w)
                        if w == v_cur:
                            break
                    if start in scc:
                        result_scc = scc

                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[v_cur])

    # Only need to traverse from start to find its SCC
    if start in nodes and start not in index:
        strongconnect(start)

    return result_scc
