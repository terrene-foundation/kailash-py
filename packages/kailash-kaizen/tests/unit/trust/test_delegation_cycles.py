"""
Unit tests for CARE-003: Cycle Detection in Delegation Chains.

Tests cover:
- Cycle detection in get_delegation_chain()
- Self-delegation rejection
- Graph-based cycle detection (DFS)
- Performance on large graphs
"""

from datetime import datetime, timezone

import pytest
from kaizen.trust.chain import (
    AuthorityType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
)
from kaizen.trust.exceptions import DelegationCycleError
from kaizen.trust.graph_validator import DelegationGraph, DelegationGraphValidator


def _make_genesis(agent_id: str = "agent-A") -> GenesisRecord:
    """Create a test genesis record."""
    return GenesisRecord(
        id=f"gen-{agent_id}",
        agent_id=agent_id,
        authority_id="org-test",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime.now(timezone.utc),
        signature="test-sig",
    )


def _make_delegation(
    delegator_id: str,
    delegatee_id: str,
    del_id: str = None,
    parent_delegation_id: str = None,
) -> DelegationRecord:
    """Create a test delegation record."""
    if del_id is None:
        del_id = f"del-{delegator_id}-{delegatee_id}"
    return DelegationRecord(
        id=del_id,
        delegator_id=delegator_id,
        delegatee_id=delegatee_id,
        task_id=f"task-{del_id}",
        capabilities_delegated=["read"],
        constraint_subset=[],
        delegated_at=datetime.now(timezone.utc),
        signature="test-sig",
        parent_delegation_id=parent_delegation_id,
    )


class TestDelegationCycleError:
    """Tests for DelegationCycleError exception."""

    def test_error_message_contains_cycle_path(self):
        """Error message must show the cycle path."""
        err = DelegationCycleError(["A", "B", "C", "A"])
        assert "A" in str(err)
        assert "B" in str(err)
        assert "C" in str(err)
        assert "cycle" in str(err).lower()

    def test_cycle_path_stored(self):
        """cycle_path attribute stores the full path."""
        err = DelegationCycleError(["A", "B", "A"])
        assert err.cycle_path == ["A", "B", "A"]


class TestGetDelegationChainCycleDetection:
    """Tests for cycle detection in TrustLineageChain.get_delegation_chain()."""

    def test_valid_chain_no_cycle(self):
        """Valid linear chain A->B->C should work."""
        del_ab = _make_delegation("A", "B", "del-1")
        del_bc = _make_delegation("B", "C", "del-2", parent_delegation_id="del-1")

        chain = TrustLineageChain(
            genesis=_make_genesis("A"),
            delegations=[del_ab, del_bc],
        )

        result = chain.get_delegation_chain()
        assert len(result) == 2

    def test_cycle_detected_raises_error(self):
        """Circular delegation must raise DelegationCycleError."""
        # Create circular chain via parent_delegation_id links:
        # del-1 (no parent) -> del-2 (parent=del-1) -> del-3 (parent=del-2)
        # But del-1 also points to del-3 as parent -> CYCLE
        del_1 = _make_delegation("A", "B", "del-1", parent_delegation_id="del-3")
        del_2 = _make_delegation("B", "C", "del-2", parent_delegation_id="del-1")
        del_3 = _make_delegation("C", "A", "del-3", parent_delegation_id="del-2")

        chain = TrustLineageChain(
            genesis=_make_genesis("A"),
            delegations=[del_1, del_2, del_3],
        )

        with pytest.raises(DelegationCycleError):
            chain.get_delegation_chain()

    def test_single_delegation_no_cycle(self):
        """Single delegation should not trigger cycle detection."""
        del_1 = _make_delegation("A", "B", "del-1")

        chain = TrustLineageChain(
            genesis=_make_genesis("A"),
            delegations=[del_1],
        )

        result = chain.get_delegation_chain()
        assert len(result) == 1

    def test_empty_delegations_no_error(self):
        """Chain with no delegations returns empty list."""
        chain = TrustLineageChain(genesis=_make_genesis("A"))

        result = chain.get_delegation_chain()
        assert result == []

    def test_max_depth_exceeded(self):
        """Chain exceeding max_depth should raise ValueError."""
        # Create a long chain
        delegations = []
        for i in range(15):
            parent_id = f"del-{i-1}" if i > 0 else None
            delegations.append(
                _make_delegation(f"agent-{i}", f"agent-{i+1}", f"del-{i}", parent_id)
            )

        chain = TrustLineageChain(
            genesis=_make_genesis("agent-0"),
            delegations=delegations,
        )

        with pytest.raises(ValueError, match="exceeds maximum depth"):
            chain.get_delegation_chain(max_depth=10)


class TestDelegationGraph:
    """Tests for DelegationGraph construction."""

    def test_from_delegations_builds_graph(self):
        """Graph should be built from delegation records."""
        delegations = [
            _make_delegation("A", "B"),
            _make_delegation("B", "C"),
        ]
        graph = DelegationGraph.from_delegations(delegations)

        assert "A" in graph.nodes
        assert "B" in graph.nodes
        assert "C" in graph.nodes
        assert "B" in graph.edges.get("A", [])
        assert "C" in graph.edges.get("B", [])

    def test_empty_delegations(self):
        """Empty delegation list creates empty graph."""
        graph = DelegationGraph.from_delegations([])
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0


class TestDelegationGraphValidator:
    """Tests for graph-based cycle detection."""

    def test_no_cycle_in_linear_graph(self):
        """Linear graph A->B->C has no cycle."""
        delegations = [
            _make_delegation("A", "B"),
            _make_delegation("B", "C"),
        ]
        graph = DelegationGraph.from_delegations(delegations)
        validator = DelegationGraphValidator(graph)

        assert validator.detect_cycle() is None

    def test_direct_cycle_detected(self):
        """Direct cycle A->B->A is detected."""
        delegations = [
            _make_delegation("A", "B"),
            _make_delegation("B", "A"),
        ]
        graph = DelegationGraph.from_delegations(delegations)
        validator = DelegationGraphValidator(graph)

        cycle = validator.detect_cycle()
        assert cycle is not None
        assert "A" in cycle
        assert "B" in cycle

    def test_indirect_cycle_detected(self):
        """Indirect cycle A->B->C->A is detected."""
        delegations = [
            _make_delegation("A", "B"),
            _make_delegation("B", "C"),
            _make_delegation("C", "A"),
        ]
        graph = DelegationGraph.from_delegations(delegations)
        validator = DelegationGraphValidator(graph)

        cycle = validator.detect_cycle()
        assert cycle is not None

    def test_deep_cycle_detected(self):
        """Cycle deep in graph A->B->C->D->E->C is detected."""
        delegations = [
            _make_delegation("A", "B"),
            _make_delegation("B", "C"),
            _make_delegation("C", "D"),
            _make_delegation("D", "E"),
            _make_delegation("E", "C"),  # Back to C
        ]
        graph = DelegationGraph.from_delegations(delegations)
        validator = DelegationGraphValidator(graph)

        cycle = validator.detect_cycle()
        assert cycle is not None
        assert "C" in cycle and "E" in cycle

    def test_validate_new_delegation_safe(self):
        """Adding safe delegation returns True."""
        delegations = [_make_delegation("A", "B")]
        graph = DelegationGraph.from_delegations(delegations)
        validator = DelegationGraphValidator(graph)

        assert validator.validate_new_delegation("B", "C") is True

    def test_validate_new_delegation_would_create_cycle(self):
        """Adding delegation that creates cycle returns False."""
        delegations = [
            _make_delegation("A", "B"),
            _make_delegation("B", "C"),
        ]
        graph = DelegationGraph.from_delegations(delegations)
        validator = DelegationGraphValidator(graph)

        # C -> A would create cycle
        assert validator.validate_new_delegation("C", "A") is False

    def test_self_delegation_rejected(self):
        """Self-delegation (A -> A) is always rejected."""
        graph = DelegationGraph.from_delegations([])
        validator = DelegationGraphValidator(graph)

        assert validator.validate_new_delegation("A", "A") is False

    def test_validate_does_not_modify_graph(self):
        """validate_new_delegation should not permanently modify the graph."""
        delegations = [_make_delegation("A", "B")]
        graph = DelegationGraph.from_delegations(delegations)
        validator = DelegationGraphValidator(graph)

        original_edges = dict(graph.edges)
        original_nodes = set(graph.nodes)

        validator.validate_new_delegation("B", "C")

        assert graph.edges == original_edges
        assert graph.nodes == original_nodes

    def test_performance_large_graph(self):
        """Cycle detection should complete quickly for large graphs."""
        import time

        # Create large linear graph (500 nodes)
        delegations = []
        for i in range(500):
            delegations.append(_make_delegation(f"agent-{i}", f"agent-{i+1}"))

        graph = DelegationGraph.from_delegations(delegations)
        validator = DelegationGraphValidator(graph)

        start = time.time()
        cycle = validator.detect_cycle()
        duration = time.time() - start

        assert cycle is None
        assert duration < 1.0, f"Cycle detection too slow: {duration}s for 500 nodes"

    def test_disconnected_graph_with_cycle(self):
        """Cycle in disconnected component is still detected."""
        delegations = [
            # Component 1: A -> B (no cycle)
            _make_delegation("A", "B"),
            # Component 2: C -> D -> C (cycle)
            _make_delegation("C", "D"),
            _make_delegation("D", "C"),
        ]
        graph = DelegationGraph.from_delegations(delegations)
        validator = DelegationGraphValidator(graph)

        cycle = validator.detect_cycle()
        assert cycle is not None
        assert "C" in cycle and "D" in cycle
