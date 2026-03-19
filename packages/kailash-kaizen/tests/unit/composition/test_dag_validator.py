# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Tier 1 (Unit) tests for DAG validator.

Tests validate_dag() for cycle detection, topological ordering,
duplicate names, max agent limits, and missing dependencies.

Self-contained: imports ONLY from kaizen.composition, never from kaizen.core.
"""

from __future__ import annotations

import pytest

from kaizen.composition.dag_validator import validate_dag
from kaizen.composition.models import CompositionError, ValidationResult


class TestValidLinearDAG:
    """A -> B -> C linear pipeline is valid."""

    def test_valid_linear_dag(self) -> None:
        agents = [
            {"name": "A", "inputs_from": []},
            {"name": "B", "inputs_from": ["A"]},
            {"name": "C", "inputs_from": ["B"]},
        ]
        result = validate_dag(agents)

        assert result.is_valid is True
        assert len(result.cycles) == 0
        assert len(result.topological_order) == 3
        # A must come before B, B must come before C
        order = result.topological_order
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")


class TestSimpleCycle:
    """A -> B -> A is a cycle."""

    def test_simple_cycle(self) -> None:
        agents = [
            {"name": "A", "inputs_from": ["B"]},
            {"name": "B", "inputs_from": ["A"]},
        ]
        result = validate_dag(agents)

        assert result.is_valid is False
        assert len(result.cycles) > 0


class TestSelfLoop:
    """A -> A is a self-loop cycle."""

    def test_self_loop(self) -> None:
        agents = [
            {"name": "A", "inputs_from": ["A"]},
        ]
        result = validate_dag(agents)

        assert result.is_valid is False
        assert len(result.cycles) > 0


class TestDiamondDAG:
    """A -> B, A -> C, B -> D, C -> D is a valid diamond."""

    def test_diamond_dag(self) -> None:
        agents = [
            {"name": "A", "inputs_from": []},
            {"name": "B", "inputs_from": ["A"]},
            {"name": "C", "inputs_from": ["A"]},
            {"name": "D", "inputs_from": ["B", "C"]},
        ]
        result = validate_dag(agents)

        assert result.is_valid is True
        assert len(result.cycles) == 0
        order = result.topological_order
        # A must precede B and C; B and C must precede D
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")


class TestBackEdgeComplex:
    """A -> B -> C -> D -> B has a back-edge cycle."""

    def test_back_edge_complex(self) -> None:
        agents = [
            {"name": "A", "inputs_from": []},
            {"name": "B", "inputs_from": ["A", "D"]},
            {"name": "C", "inputs_from": ["B"]},
            {"name": "D", "inputs_from": ["C"]},
        ]
        result = validate_dag(agents)

        assert result.is_valid is False
        assert len(result.cycles) > 0


class TestDisconnectedComponents:
    """Two disconnected subgraphs: A->B, C->D, both valid."""

    def test_disconnected_components(self) -> None:
        agents = [
            {"name": "A", "inputs_from": []},
            {"name": "B", "inputs_from": ["A"]},
            {"name": "C", "inputs_from": []},
            {"name": "D", "inputs_from": ["C"]},
        ]
        result = validate_dag(agents)

        assert result.is_valid is True
        assert len(result.cycles) == 0
        assert len(result.topological_order) == 4
        order = result.topological_order
        assert order.index("A") < order.index("B")
        assert order.index("C") < order.index("D")


class TestSingleNode:
    """Single node with no dependencies is valid."""

    def test_single_node(self) -> None:
        agents = [{"name": "A", "inputs_from": []}]
        result = validate_dag(agents)

        assert result.is_valid is True
        assert result.topological_order == ["A"]
        assert len(result.cycles) == 0


class TestEmptyList:
    """Empty agent list is valid (vacuously)."""

    def test_empty_list(self) -> None:
        result = validate_dag([])

        assert result.is_valid is True
        assert result.topological_order == []
        assert len(result.cycles) == 0


class TestDuplicateNamesRejected:
    """Two agents with the same name must be rejected."""

    def test_duplicate_names_rejected(self) -> None:
        agents = [
            {"name": "A", "inputs_from": []},
            {"name": "A", "inputs_from": []},
        ]
        with pytest.raises(CompositionError, match="[Dd]uplicate"):
            validate_dag(agents)


class TestExceedsMaxAgents:
    """More than max_agents should be rejected."""

    def test_exceeds_max_agents(self) -> None:
        agents = [{"name": f"agent_{i}", "inputs_from": []} for i in range(1001)]
        with pytest.raises(CompositionError, match="[Ee]xceed|[Mm]ax"):
            validate_dag(agents, max_agents=1000)


class TestMissingDependencyWarning:
    """A depends on B, but B is not in the agent list -- should warn."""

    def test_missing_dependency_warning(self) -> None:
        agents = [
            {"name": "A", "inputs_from": ["B"]},
        ]
        result = validate_dag(agents)

        # Missing dependency is a warning, not a cycle
        assert len(result.warnings) > 0
        assert any("B" in w for w in result.warnings)


class TestTopologicalOrderDeterminism:
    """Repeated calls with the same input produce the same topological order."""

    def test_topological_order_determinism(self) -> None:
        agents = [
            {"name": "A", "inputs_from": []},
            {"name": "B", "inputs_from": ["A"]},
            {"name": "C", "inputs_from": ["A"]},
            {"name": "D", "inputs_from": ["B", "C"]},
        ]
        results = [validate_dag(agents) for _ in range(5)]
        orders = [r.topological_order for r in results]
        # All orders should be identical
        for order in orders[1:]:
            assert order == orders[0]


class TestValidationResultSerialization:
    """ValidationResult to_dict/from_dict round-trip."""

    def test_round_trip(self) -> None:
        original = ValidationResult(
            is_valid=True,
            topological_order=["A", "B", "C"],
            cycles=[],
            warnings=["test warning"],
        )
        data = original.to_dict()
        restored = ValidationResult.from_dict(data)

        assert restored.is_valid == original.is_valid
        assert restored.topological_order == original.topological_order
        assert restored.cycles == original.cycles
        assert restored.warnings == original.warnings
