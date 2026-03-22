# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Comprehensive test suite for WorkflowDAG — the custom graph class replacing networkx.

Tests are organized into 7 categories:
1. Construction (add/remove nodes/edges)
2. Query (nodes, edges, predecessors, successors, etc.)
3. Topological Sort (Kahn's algorithm with caching)
4. Cycle Detection (Tarjan's SCC, simple cycles, is_dag)
5. Ancestors and Descendants (BFS traversal)
6. Edge Cases (empty graph, disconnected, large graph, self-loops)
7. networkx Equivalence (verify results match networkx)
"""

from __future__ import annotations

import time

import pytest

from kailash.workflow.dag import CycleDetectedError, WorkflowDAG


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_dag():
    """Empty graph with no nodes or edges."""
    return WorkflowDAG()


@pytest.fixture
def single_node_dag():
    """Graph with a single node 'A' and no edges."""
    dag = WorkflowDAG()
    dag.add_node("A", label="alpha")
    return dag


@pytest.fixture
def linear_dag():
    """A -> B -> C -> D"""
    dag = WorkflowDAG()
    for node in ["A", "B", "C", "D"]:
        dag.add_node(node)
    dag.add_edge("A", "B")
    dag.add_edge("B", "C")
    dag.add_edge("C", "D")
    return dag


@pytest.fixture
def diamond_dag():
    """A -> B, A -> C, B -> D, C -> D"""
    dag = WorkflowDAG()
    for node in ["A", "B", "C", "D"]:
        dag.add_node(node)
    dag.add_edge("A", "B")
    dag.add_edge("A", "C")
    dag.add_edge("B", "D")
    dag.add_edge("C", "D")
    return dag


@pytest.fixture
def cycle_graph():
    """A -> B -> C -> A (3-node cycle)"""
    dag = WorkflowDAG()
    for node in ["A", "B", "C"]:
        dag.add_node(node)
    dag.add_edge("A", "B")
    dag.add_edge("B", "C")
    dag.add_edge("C", "A")
    return dag


@pytest.fixture
def mixed_graph():
    """X -> A -> B -> C -> A, X -> D (cycle + DAG tail)"""
    dag = WorkflowDAG()
    for node in ["X", "A", "B", "C", "D"]:
        dag.add_node(node)
    dag.add_edge("X", "A")
    dag.add_edge("A", "B")
    dag.add_edge("B", "C")
    dag.add_edge("C", "A")  # cycle: A->B->C->A
    dag.add_edge("X", "D")
    return dag


@pytest.fixture
def disconnected_dag():
    """Two disconnected components: A->B and C->D"""
    dag = WorkflowDAG()
    for node in ["A", "B", "C", "D"]:
        dag.add_node(node)
    dag.add_edge("A", "B")
    dag.add_edge("C", "D")
    return dag


@pytest.fixture
def complex_dag():
    """10-node DAG with multiple paths.

    1 -> 2 -> 4 -> 7
    1 -> 3 -> 5 -> 7
         3 -> 6 -> 8
    9 -> 10 (disconnected)
    """
    dag = WorkflowDAG()
    for i in range(1, 11):
        dag.add_node(str(i))
    dag.add_edge("1", "2")
    dag.add_edge("1", "3")
    dag.add_edge("2", "4")
    dag.add_edge("3", "5")
    dag.add_edge("3", "6")
    dag.add_edge("4", "7")
    dag.add_edge("5", "7")
    dag.add_edge("6", "8")
    dag.add_edge("9", "10")
    return dag


# ===========================================================================
# Category 1: Construction (8 tests)
# ===========================================================================


class TestConstruction:
    def test_add_node_single(self, empty_dag):
        """Add one node, verify it exists in graph."""
        empty_dag.add_node("node1")
        assert empty_dag.has_node("node1")
        assert len(empty_dag) == 1

    def test_add_node_with_attrs(self, empty_dag):
        """Add node with attributes, verify attributes retrievable."""
        empty_dag.add_node("node1", color="red", weight=5)
        nodes_with_data = empty_dag.nodes(data=True)
        node_dict = {nid: attrs for nid, attrs in nodes_with_data}
        assert node_dict["node1"]["color"] == "red"
        assert node_dict["node1"]["weight"] == 5

    def test_add_edge_creates_nodes(self, empty_dag):
        """Adding edge auto-creates both nodes if they don't exist."""
        empty_dag.add_edge("A", "B")
        assert empty_dag.has_node("A")
        assert empty_dag.has_node("B")
        assert len(empty_dag) == 2

    def test_add_edge_with_attrs(self, empty_dag):
        """Add edge with attributes, verify via get_edge_data()."""
        empty_dag.add_edge("A", "B", mapping={"output": "input"}, weight=3)
        data = empty_dag.get_edge_data("A", "B")
        assert data is not None
        assert data["mapping"] == {"output": "input"}
        assert data["weight"] == 3

    def test_add_nodes_from_list(self, empty_dag):
        """add_nodes_from with (id, attrs) tuples works correctly."""
        empty_dag.add_nodes_from(
            [
                ("n1", {"label": "first"}),
                ("n2", {"label": "second"}),
                ("n3", {"label": "third"}),
            ]
        )
        assert len(empty_dag) == 3
        assert empty_dag.has_node("n1")
        assert empty_dag.has_node("n2")
        assert empty_dag.has_node("n3")

    def test_remove_node(self, linear_dag):
        """Remove node, verify it's gone and incident edges are removed."""
        linear_dag.remove_node("B")
        assert not linear_dag.has_node("B")
        assert len(linear_dag) == 3
        # A->B edge should be gone
        assert empty_dag_edge_check(linear_dag, "A", "B") is False
        # B->C edge should be gone
        assert empty_dag_edge_check(linear_dag, "B", "C") is False
        # A and C still exist
        assert linear_dag.has_node("A")
        assert linear_dag.has_node("C")

    def test_remove_edge(self, linear_dag):
        """Remove edge, verify it's gone but nodes still present."""
        linear_dag.remove_edge("A", "B")
        assert not linear_dag.has_edge("A", "B")
        assert linear_dag.has_node("A")
        assert linear_dag.has_node("B")
        # Other edges unaffected
        assert linear_dag.has_edge("B", "C")

    def test_len(self, diamond_dag):
        """len(dag) returns node count."""
        assert len(diamond_dag) == 4


def empty_dag_edge_check(dag, src, dst):
    """Helper to check if edge exists using has_edge."""
    return dag.has_edge(src, dst)


# ===========================================================================
# Category 2: Query (12 tests)
# ===========================================================================


class TestQuery:
    def test_nodes_returns_all(self, linear_dag):
        """nodes() returns all node IDs."""
        node_ids = linear_dag.nodes()
        assert set(node_ids) == {"A", "B", "C", "D"}

    def test_nodes_with_data(self, empty_dag):
        """nodes(data=True) returns [(id, attrs), ...]."""
        empty_dag.add_node("A", color="red")
        empty_dag.add_node("B", color="blue")
        result = empty_dag.nodes(data=True)
        # result is list of (id, attrs) tuples
        result_dict = {nid: attrs for nid, attrs in result}
        assert result_dict["A"]["color"] == "red"
        assert result_dict["B"]["color"] == "blue"

    def test_edges_returns_all(self, diamond_dag):
        """edges() returns all (src, dst) pairs."""
        edge_set = set(diamond_dag.edges())
        assert edge_set == {("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")}

    def test_edges_with_data(self, empty_dag):
        """edges(data=True) returns [(src, dst, attrs), ...]."""
        empty_dag.add_edge("A", "B", weight=10)
        empty_dag.add_edge("B", "C", weight=20)
        result = empty_dag.edges(data=True)
        edge_dict = {(s, d): attrs for s, d, attrs in result}
        assert edge_dict[("A", "B")]["weight"] == 10
        assert edge_dict[("B", "C")]["weight"] == 20

    def test_predecessors(self, diamond_dag):
        """predecessors(n) returns direct predecessors only."""
        preds = list(diamond_dag.predecessors("D"))
        assert set(preds) == {"B", "C"}

    def test_successors(self, diamond_dag):
        """successors(n) returns direct successors only."""
        succs = list(diamond_dag.successors("A"))
        assert set(succs) == {"B", "C"}

    def test_in_edges(self, diamond_dag):
        """in_edges(n) returns [(src, n), ...]."""
        result = diamond_dag.in_edges("D")
        edge_set = set(result)
        assert edge_set == {("B", "D"), ("C", "D")}

    def test_in_edges_with_data(self, empty_dag):
        """in_edges(n, data=True) returns [(src, n, attrs), ...]."""
        empty_dag.add_edge("A", "C", weight=1)
        empty_dag.add_edge("B", "C", weight=2)
        result = empty_dag.in_edges("C", data=True)
        edge_dict = {s: attrs for s, _, attrs in result}
        assert edge_dict["A"]["weight"] == 1
        assert edge_dict["B"]["weight"] == 2

    def test_has_node_true(self, linear_dag):
        """Known node returns True."""
        assert linear_dag.has_node("A") is True

    def test_has_node_false(self, linear_dag):
        """Unknown node returns False."""
        assert linear_dag.has_node("Z") is False

    def test_get_edge_data_existing(self, empty_dag):
        """Returns edge attrs dict for existing edge."""
        empty_dag.add_edge("A", "B", color="red")
        data = empty_dag.get_edge_data("A", "B")
        assert isinstance(data, dict)
        assert data["color"] == "red"

    def test_get_edge_data_missing(self, empty_dag):
        """Returns None for non-existent edge."""
        empty_dag.add_node("A")
        empty_dag.add_node("B")
        assert empty_dag.get_edge_data("A", "B") is None

    def test_contains_operator(self, linear_dag):
        """'node in dag' works via __contains__."""
        assert "A" in linear_dag
        assert "Z" not in linear_dag

    def test_has_edge(self, linear_dag):
        """has_edge returns True for existing edges, False otherwise."""
        assert linear_dag.has_edge("A", "B") is True
        assert linear_dag.has_edge("A", "C") is False

    def test_in_degree(self, diamond_dag):
        """in_degree returns the number of incoming edges."""
        assert diamond_dag.in_degree("A") == 0
        assert diamond_dag.in_degree("D") == 2

    def test_out_degree(self, diamond_dag):
        """out_degree returns the number of outgoing edges."""
        assert diamond_dag.out_degree("A") == 2
        assert diamond_dag.out_degree("D") == 0


# ===========================================================================
# Category 3: Topological Sort (8 tests)
# ===========================================================================


class TestTopologicalSort:
    def test_topo_sort_linear(self, linear_dag):
        """A->B->C->D returns [A, B, C, D]."""
        result = linear_dag.topological_sort()
        assert result == ["A", "B", "C", "D"]

    def test_topo_sort_diamond(self, diamond_dag):
        """Diamond: D must come after both B and C, A must be first."""
        result = diamond_dag.topological_sort()
        assert result[0] == "A"
        assert result[-1] == "D"
        # B and C can be in any order, but both before D
        assert result.index("B") < result.index("D")
        assert result.index("C") < result.index("D")

    def test_topo_sort_complex(self, complex_dag):
        """Multi-root DAG with correct ordering constraints."""
        result = complex_dag.topological_sort()
        # Verify all ordering constraints
        assert result.index("1") < result.index("2")
        assert result.index("1") < result.index("3")
        assert result.index("2") < result.index("4")
        assert result.index("3") < result.index("5")
        assert result.index("3") < result.index("6")
        assert result.index("4") < result.index("7")
        assert result.index("5") < result.index("7")
        assert result.index("6") < result.index("8")
        assert result.index("9") < result.index("10")

    def test_topo_sort_single_node(self, single_node_dag):
        """Single node returns [node]."""
        result = single_node_dag.topological_sort()
        assert result == ["A"]

    def test_topo_sort_empty(self, empty_dag):
        """Empty graph returns []."""
        result = empty_dag.topological_sort()
        assert result == []

    def test_topo_sort_cache_hit(self, linear_dag):
        """Second call returns same list object (is identity)."""
        first = linear_dag.topological_sort()
        second = linear_dag.topological_sort()
        assert first is second

    def test_topo_sort_cache_invalidated_on_add_node(self, linear_dag):
        """After add_node(), recomputes (not same object)."""
        first = linear_dag.topological_sort()
        linear_dag.add_node("E")
        second = linear_dag.topological_sort()
        assert first is not second
        assert "E" in second

    def test_topo_sort_cache_invalidated_on_add_edge(self, linear_dag):
        """After add_edge(), recomputes."""
        first = linear_dag.topological_sort()
        linear_dag.add_node("E")
        linear_dag.add_edge("D", "E")
        second = linear_dag.topological_sort()
        assert first is not second
        assert second[-1] == "E"

    def test_topo_sort_raises_on_cycle(self, cycle_graph):
        """CycleDetectedError raised when graph has cycle."""
        with pytest.raises(CycleDetectedError):
            cycle_graph.topological_sort()


# ===========================================================================
# Category 4: Cycle Detection (8 tests)
# ===========================================================================


class TestCycleDetection:
    def test_is_dag_true(self, linear_dag):
        """Acyclic graph returns True."""
        assert linear_dag.is_dag() is True

    def test_is_dag_false(self, cycle_graph):
        """Graph with cycle returns False."""
        assert cycle_graph.is_dag() is False

    def test_scc_acyclic(self, linear_dag):
        """Each node is its own SCC in DAG."""
        sccs = linear_dag.strongly_connected_components()
        # In a DAG, all SCCs are singletons
        for scc in sccs:
            assert len(scc) == 1

    def test_scc_cycle(self, cycle_graph):
        """Nodes in cycle form one SCC."""
        sccs = cycle_graph.strongly_connected_components()
        # Should have one SCC with all 3 nodes
        multi_node_sccs = [scc for scc in sccs if len(scc) > 1]
        assert len(multi_node_sccs) == 1
        assert multi_node_sccs[0] == {"A", "B", "C"}

    def test_scc_mixed(self, mixed_graph):
        """Graph with cycle + acyclic nodes -- correct SCC grouping."""
        sccs = mixed_graph.strongly_connected_components()
        scc_map = {}
        for scc in sccs:
            for node in scc:
                scc_map[node] = scc
        # A, B, C are in the same SCC (cycle)
        assert scc_map["A"] == scc_map["B"] == scc_map["C"]
        assert len(scc_map["A"]) == 3
        # X and D are singletons
        assert len(scc_map["X"]) == 1
        assert len(scc_map["D"]) == 1

    def test_simple_cycles_none(self, linear_dag):
        """DAG has no simple cycles."""
        cycles = linear_dag.simple_cycles()
        assert cycles == []

    def test_simple_cycles_one(self, cycle_graph):
        """Single cycle correctly identified."""
        cycles = cycle_graph.simple_cycles()
        assert len(cycles) == 1
        assert set(cycles[0]) == {"A", "B", "C"}

    def test_simple_cycles_two(self):
        """Two independent cycles both found."""
        dag = WorkflowDAG()
        # Cycle 1: A->B->C->A
        dag.add_edge("A", "B")
        dag.add_edge("B", "C")
        dag.add_edge("C", "A")
        # Cycle 2: D->E->D
        dag.add_edge("D", "E")
        dag.add_edge("E", "D")
        cycles = dag.simple_cycles()
        assert len(cycles) == 2
        cycle_sets = [set(c) for c in cycles]
        assert {"A", "B", "C"} in cycle_sets
        assert {"D", "E"} in cycle_sets


# ===========================================================================
# Category 5: Ancestors and Descendants (6 tests)
# ===========================================================================


class TestAncestorsDescendants:
    def test_ancestors_direct(self, linear_dag):
        """Direct predecessor is in ancestors."""
        ancestors = linear_dag.ancestors("B")
        assert "A" in ancestors

    def test_ancestors_transitive(self, linear_dag):
        """Transitive predecessors included."""
        ancestors = linear_dag.ancestors("D")
        assert ancestors == {"A", "B", "C"}

    def test_ancestors_empty(self, linear_dag):
        """Root node has empty ancestors."""
        ancestors = linear_dag.ancestors("A")
        assert ancestors == set()

    def test_descendants_direct(self, linear_dag):
        """Direct successor is in descendants."""
        descendants = linear_dag.descendants("C")
        assert "D" in descendants

    def test_descendants_transitive(self, linear_dag):
        """Transitive successors included."""
        descendants = linear_dag.descendants("A")
        assert descendants == {"B", "C", "D"}

    def test_descendants_empty(self, linear_dag):
        """Leaf node has empty descendants."""
        descendants = linear_dag.descendants("D")
        assert descendants == set()


# ===========================================================================
# Category 6: Edge Cases (10 tests)
# ===========================================================================


class TestEdgeCases:
    def test_empty_graph_operations(self, empty_dag):
        """All queries on empty graph work without error."""
        assert empty_dag.nodes() == []
        assert empty_dag.edges() == []
        assert len(empty_dag) == 0
        assert empty_dag.topological_sort() == []
        assert empty_dag.is_dag() is True
        assert empty_dag.strongly_connected_components() == []
        assert empty_dag.simple_cycles() == []

    def test_single_node_no_edges(self, single_node_dag):
        """Single node, all queries return correct empty/single results."""
        assert single_node_dag.nodes() == ["A"]
        assert single_node_dag.edges() == []
        assert list(single_node_dag.predecessors("A")) == []
        assert list(single_node_dag.successors("A")) == []
        assert single_node_dag.in_degree("A") == 0
        assert single_node_dag.out_degree("A") == 0
        assert single_node_dag.topological_sort() == ["A"]
        assert single_node_dag.ancestors("A") == set()
        assert single_node_dag.descendants("A") == set()

    def test_disconnected_components(self, disconnected_dag):
        """Graph with 2 disconnected parts -- both components queryable."""
        assert len(disconnected_dag) == 4
        topo = disconnected_dag.topological_sort()
        assert set(topo) == {"A", "B", "C", "D"}
        assert topo.index("A") < topo.index("B")
        assert topo.index("C") < topo.index("D")

    def test_self_loop_detected(self, empty_dag):
        """Self-loop makes is_dag() False."""
        empty_dag.add_node("A")
        empty_dag.add_edge("A", "A")
        assert empty_dag.is_dag() is False

    def test_parallel_edges_overwrite(self, empty_dag):
        """Second add_edge(A, B) overwrites first edge attrs."""
        empty_dag.add_edge("A", "B", weight=1)
        empty_dag.add_edge("A", "B", weight=2)
        data = empty_dag.get_edge_data("A", "B")
        assert data["weight"] == 2

    def test_remove_nonexistent_node_raises(self, empty_dag):
        """Removing nonexistent node raises KeyError."""
        with pytest.raises(KeyError):
            empty_dag.remove_node("Z")

    def test_remove_nonexistent_edge_raises(self, linear_dag):
        """Removing nonexistent edge raises KeyError."""
        with pytest.raises(KeyError):
            linear_dag.remove_edge("A", "D")

    def test_large_graph(self):
        """1000-node chain -- topological sort completes in <100ms."""
        dag = WorkflowDAG()
        n = 1000
        for i in range(n):
            dag.add_node(str(i))
        for i in range(n - 1):
            dag.add_edge(str(i), str(i + 1))

        start = time.monotonic()
        result = dag.topological_sort()
        elapsed = time.monotonic() - start

        assert len(result) == n
        assert result == [str(i) for i in range(n)]
        assert elapsed < 0.1, f"topological_sort took {elapsed:.3f}s, expected <0.1s"

    def test_mutation_after_query(self, linear_dag):
        """Add/remove after computing sort -- no stale results."""
        first_sort = linear_dag.topological_sort()
        assert first_sort == ["A", "B", "C", "D"]

        linear_dag.add_node("E")
        linear_dag.add_edge("D", "E")
        second_sort = linear_dag.topological_sort()
        assert second_sort == ["A", "B", "C", "D", "E"]
        assert first_sort is not second_sort

    def test_subgraph(self, diamond_dag):
        """subgraph() returns a new WorkflowDAG with only specified nodes and their internal edges."""
        sub = diamond_dag.subgraph(["A", "B", "D"])
        assert len(sub) == 3
        assert sub.has_node("A")
        assert sub.has_node("B")
        assert sub.has_node("D")
        assert not sub.has_node("C")
        # A->B edge should be present, but C->D should not
        assert sub.has_edge("A", "B")
        assert sub.has_edge("B", "D")
        assert not sub.has_edge("A", "C")

    def test_copy(self, linear_dag):
        """copy() creates an independent copy of the graph."""
        copied = linear_dag.copy()
        assert len(copied) == len(linear_dag)
        assert set(copied.nodes()) == set(linear_dag.nodes())
        assert set(copied.edges()) == set(linear_dag.edges())
        # Mutation of copy does not affect original
        copied.add_node("Z")
        assert not linear_dag.has_node("Z")

    def test_predecessors_nonexistent_node_raises(self, empty_dag):
        """Calling predecessors on a nonexistent node raises KeyError."""
        with pytest.raises(KeyError):
            list(empty_dag.predecessors("Z"))

    def test_successors_nonexistent_node_raises(self, empty_dag):
        """Calling successors on a nonexistent node raises KeyError."""
        with pytest.raises(KeyError):
            list(empty_dag.successors("Z"))


# ===========================================================================
# Category 7: networkx Equivalence (10 tests)
# ===========================================================================


class TestNetworkxEquivalence:
    """Verify WorkflowDAG results match networkx for the same inputs.

    These tests require networkx to be installed.
    """

    @pytest.fixture(autouse=True)
    def _import_networkx(self):
        self.nx = pytest.importorskip("networkx")

    def _build_both(self, edges, node_attrs=None):
        """Build identical graphs in both WorkflowDAG and nx.DiGraph."""
        dag = WorkflowDAG()
        nx_graph = self.nx.DiGraph()
        # Collect all nodes from edges
        all_nodes = set()
        for src, dst in edges:
            all_nodes.add(src)
            all_nodes.add(dst)
        for node in sorted(all_nodes):
            attrs = (node_attrs or {}).get(node, {})
            dag.add_node(node, **attrs)
            nx_graph.add_node(node, **attrs)
        for src, dst in edges:
            dag.add_edge(src, dst)
            nx_graph.add_edge(src, dst)
        return dag, nx_graph

    def test_equiv_topological_sort_linear(self):
        """Linear chain: topological orders must be equal."""
        edges = [("A", "B"), ("B", "C"), ("C", "D")]
        dag, nx_graph = self._build_both(edges)
        dag_result = dag.topological_sort()
        nx_result = list(self.nx.topological_sort(nx_graph))
        # Both should produce A, B, C, D
        assert dag_result == nx_result

    def test_equiv_topological_sort_diamond(self):
        """Diamond: verify topological invariants match."""
        edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
        dag, nx_graph = self._build_both(edges)
        dag_result = dag.topological_sort()
        nx_result = list(self.nx.topological_sort(nx_graph))
        # Both must have A first, D last
        assert dag_result[0] == nx_result[0] == "A"
        assert dag_result[-1] == nx_result[-1] == "D"

    def test_equiv_topological_sort_complex(self):
        """10-node complex DAG: verify ordering constraints match."""
        edges = [
            ("1", "2"),
            ("1", "3"),
            ("2", "4"),
            ("3", "5"),
            ("3", "6"),
            ("4", "7"),
            ("5", "7"),
            ("6", "8"),
            ("9", "10"),
        ]
        dag, nx_graph = self._build_both(edges)
        dag_result = dag.topological_sort()
        # Verify topological constraints (all predecessors before node)
        for src, dst in edges:
            assert dag_result.index(src) < dag_result.index(dst)

    def test_equiv_scc_cycle(self):
        """3-node cycle: SCC must contain all 3 nodes."""
        edges = [("A", "B"), ("B", "C"), ("C", "A")]
        dag, nx_graph = self._build_both(edges)
        dag_sccs = dag.strongly_connected_components()
        nx_sccs = list(self.nx.strongly_connected_components(nx_graph))
        # Compare as sets of frozensets
        dag_scc_sets = {frozenset(s) for s in dag_sccs}
        nx_scc_sets = {frozenset(s) for s in nx_sccs}
        assert dag_scc_sets == nx_scc_sets

    def test_equiv_scc_mixed(self):
        """Mixed acyclic + cyclic: SCC grouping must match."""
        edges = [("X", "A"), ("A", "B"), ("B", "C"), ("C", "A"), ("X", "D")]
        dag, nx_graph = self._build_both(edges)
        dag_sccs = dag.strongly_connected_components()
        nx_sccs = list(self.nx.strongly_connected_components(nx_graph))
        dag_scc_sets = {frozenset(s) for s in dag_sccs}
        nx_scc_sets = {frozenset(s) for s in nx_sccs}
        assert dag_scc_sets == nx_scc_sets

    def test_equiv_ancestors_middle_node(self):
        """Node in middle of chain: ancestors must match."""
        edges = [("A", "B"), ("B", "C"), ("C", "D"), ("C", "E")]
        dag, nx_graph = self._build_both(edges)
        dag_ancestors = dag.ancestors("C")
        nx_ancestors = self.nx.ancestors(nx_graph, "C")
        assert dag_ancestors == nx_ancestors

    def test_equiv_descendants_middle_node(self):
        """Node in middle of chain: descendants must match."""
        edges = [("A", "B"), ("B", "C"), ("C", "D"), ("C", "E")]
        dag, nx_graph = self._build_both(edges)
        dag_descendants = dag.descendants("C")
        nx_descendants = self.nx.descendants(nx_graph, "C")
        assert dag_descendants == nx_descendants

    def test_equiv_is_dag_true(self):
        """Acyclic graph: is_dag matches nx."""
        edges = [("A", "B"), ("B", "C")]
        dag, nx_graph = self._build_both(edges)
        assert dag.is_dag() == self.nx.is_directed_acyclic_graph(nx_graph)

    def test_equiv_is_dag_false(self):
        """Graph with cycle: is_dag matches nx."""
        edges = [("A", "B"), ("B", "C"), ("C", "A")]
        dag, nx_graph = self._build_both(edges)
        assert dag.is_dag() == self.nx.is_directed_acyclic_graph(nx_graph)

    def test_equiv_edge_data(self):
        """Edge attributes round-trip correctly."""
        dag = WorkflowDAG()
        nx_graph = self.nx.DiGraph()
        attrs = {
            "mapping": {"output": "input"},
            "from_output": "output",
            "to_input": "input",
        }
        dag.add_edge("A", "B", **attrs)
        nx_graph.add_edge("A", "B", **attrs)

        dag_data = dag.get_edge_data("A", "B")
        nx_data = nx_graph.get_edge_data("A", "B")
        assert dag_data == nx_data
