# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for M0-08: Generic cycle detection (P5)."""

import pytest

from kaizen.composition.graph_utils import (
    CycleDetected,
    detect_cycles,
    topological_order,
    validate_graph,
)


class TestValidateGraph:
    def test_empty_graph(self):
        result = validate_graph({})
        assert result.is_acyclic
        assert result.topological_order == []
        assert result.cycles == []

    def test_single_node(self):
        result = validate_graph({"A": []})
        assert result.is_acyclic
        assert result.topological_order == ["A"]

    def test_linear_chain(self):
        """A -> B -> C (A depends on nothing, B depends on A, C depends on B)."""
        result = validate_graph({"A": [], "B": ["A"], "C": ["B"]})
        assert result.is_acyclic
        order = result.topological_order
        assert order.index("A") < order.index("B") < order.index("C")

    def test_diamond(self):
        """A -> B, A -> C, B -> D, C -> D."""
        result = validate_graph(
            {
                "A": [],
                "B": ["A"],
                "C": ["A"],
                "D": ["B", "C"],
            }
        )
        assert result.is_acyclic
        order = result.topological_order
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_simple_cycle(self):
        """A -> B -> A."""
        result = validate_graph({"A": ["B"], "B": ["A"]})
        assert not result.is_acyclic
        assert len(result.cycles) >= 1
        assert result.topological_order == []

    def test_self_loop(self):
        """A -> A."""
        result = validate_graph({"A": ["A"]})
        assert not result.is_acyclic
        assert len(result.cycles) >= 1

    def test_longer_cycle(self):
        """A -> B -> C -> A."""
        result = validate_graph({"A": ["C"], "B": ["A"], "C": ["B"]})
        assert not result.is_acyclic

    def test_disconnected_components(self):
        """Two separate chains: A->B and C->D."""
        result = validate_graph(
            {
                "A": [],
                "B": ["A"],
                "C": [],
                "D": ["C"],
            }
        )
        assert result.is_acyclic
        assert len(result.topological_order) == 4

    def test_parallel_fan_out(self):
        """A -> B, A -> C, A -> D (all independent)."""
        result = validate_graph(
            {
                "A": [],
                "B": ["A"],
                "C": ["A"],
                "D": ["A"],
            }
        )
        assert result.is_acyclic
        assert result.topological_order[0] == "A"


class TestDetectCycles:
    def test_no_cycles(self):
        assert detect_cycles({"A": [], "B": ["A"]}) == []

    def test_has_cycle(self):
        cycles = detect_cycles({"A": ["B"], "B": ["A"]})
        assert len(cycles) >= 1


class TestTopologicalOrder:
    def test_linear(self):
        order = topological_order({"A": [], "B": ["A"], "C": ["B"]})
        assert order.index("A") < order.index("B") < order.index("C")

    def test_raises_on_cycle(self):
        with pytest.raises(CycleDetected) as exc_info:
            topological_order({"A": ["B"], "B": ["A"]})
        assert len(exc_info.value.cycles) >= 1

    def test_empty(self):
        assert topological_order({}) == []
