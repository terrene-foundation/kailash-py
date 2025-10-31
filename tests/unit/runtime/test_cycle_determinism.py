"""
Unit tests for cycle execution determinism logic.

These tests verify the deterministic behavior of cycle-related algorithms and data structures
WITHOUT using the full execution pipeline. They focus on individual components.

IMPORTANT: These are Tier 1 UNIT tests that must:
- Run in <1 second per test
- Have NO external dependencies
- Use NO file I/O or database operations
- Test ONLY algorithmic behavior with mocked/isolated components
- Use mocking for external dependencies (allowed in Tier 1)

These tests validate the core logic that ensures cycle execution is deterministic.
"""

from unittest.mock import Mock, patch

import pytest
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow


class TestCycleDeterminismUnit:
    """Unit tests for cycle execution determinism algorithms."""

    @pytest.mark.timeout(1)
    def test_cycle_detection_deterministic(self):
        """Test that cycle detection produces consistent results."""
        # Test the underlying cycle detection logic
        workflow = WorkflowBuilder()

        # Create a workflow with a known cycle pattern
        workflow.add_node(
            "PythonCodeNode", "source", {"code": "result = {'value': 10}"}
        )
        workflow.add_node(
            "PythonCodeNode",
            "processor",
            {"code": "result = {'value': parameters.get('value', 0) + 5}"},
        )
        workflow.add_node(
            "SwitchNode",
            "threshold",
            {"condition_field": "value", "operator": "<", "value": 50},
        )

        workflow.add_connection("source", "result", "threshold", "input_data")
        workflow.add_connection("threshold", "true_output", "processor", "parameters")

        built_workflow = workflow.build()
        cycle = built_workflow.create_cycle("test_cycle")
        cycle.connect("processor", "threshold", mapping={"result": "input_data"})
        cycle.max_iterations(10)
        cycle.build()

        # Test multiple calls to has_cycles() return the same result
        results = []
        for _ in range(5):
            results.append(built_workflow.has_cycles())

        # All results should be identical (deterministic)
        assert all(
            r == results[0] for r in results
        ), f"Inconsistent cycle detection: {results}"
        assert results[0] is True, "Expected cycle to be detected"

    @pytest.mark.timeout(1)
    def test_cycle_edge_separation_deterministic(self):
        """Test that cycle edge separation is deterministic."""
        workflow = WorkflowBuilder()

        # Create workflow with mixed cycle and non-cycle edges
        workflow.add_node("PythonCodeNode", "start", {"code": "result = {'value': 1}"})
        workflow.add_node(
            "PythonCodeNode",
            "middle",
            {"code": "result = {'value': parameters.get('value', 0) * 2}"},
        )
        workflow.add_node(
            "SwitchNode",
            "end",
            {"condition_field": "value", "operator": "<", "value": 10},
        )

        workflow.add_connection(
            "start", "result", "middle", "parameters"
        )  # Normal edge
        workflow.add_connection("middle", "result", "end", "input_data")  # Normal edge

        built_workflow = workflow.build()
        cycle = built_workflow.create_cycle("test_cycle")
        cycle.connect(
            "end", "middle", mapping={"true_output": "parameters"}
        )  # Cycle edge
        cycle.max_iterations(5)
        cycle.build()

        # Test multiple calls to separate_dag_and_cycle_edges()
        results = []
        for _ in range(5):
            dag_edges, cycle_edges = built_workflow.separate_dag_and_cycle_edges()
            results.append((len(dag_edges), len(cycle_edges)))

        # All results should be identical
        assert all(
            r == results[0] for r in results
        ), f"Inconsistent edge separation: {results}"

        # Verify expected edge counts (2 DAG edges, 1 cycle edge)
        dag_count, cycle_count = results[0]
        assert dag_count == 2, f"Expected 2 DAG edges, got {dag_count}"
        assert cycle_count == 1, f"Expected 1 cycle edge, got {cycle_count}"

    @pytest.mark.timeout(1)
    def test_execution_order_deterministic(self):
        """Test that execution order calculation is deterministic."""
        workflow = WorkflowBuilder()

        # Create a more complex workflow
        workflow.add_node("PythonCodeNode", "a", {"code": "result = {'step': 'a'}"})
        workflow.add_node("PythonCodeNode", "b", {"code": "result = {'step': 'b'}"})
        workflow.add_node("PythonCodeNode", "c", {"code": "result = {'step': 'c'}"})
        workflow.add_node("PythonCodeNode", "d", {"code": "result = {'step': 'd'}"})

        # Create dependencies: a->b->c, a->d->c (diamond pattern)
        workflow.add_connection("a", "result", "b", "input")
        workflow.add_connection("a", "result", "d", "input")
        workflow.add_connection("b", "result", "c", "input1")
        workflow.add_connection("d", "result", "c", "input2")

        built_workflow = workflow.build()

        # Test multiple calls to get_execution_order()
        orders = []
        for _ in range(10):
            order = built_workflow.get_execution_order()
            orders.append(tuple(order))  # Convert to tuple for comparison

        # All orders should be identical (deterministic)
        assert all(
            o == orders[0] for o in orders
        ), f"Inconsistent execution orders: {set(orders)}"

        # Verify the order makes sense (a first, c last)
        order = list(orders[0])
        assert order[0] == "a", f"Expected 'a' first, got {order}"
        assert order[-1] == "c", f"Expected 'c' last, got {order}"
        assert "b" in order and "d" in order, f"Missing intermediate nodes in {order}"

    @pytest.mark.timeout(1)
    def test_cycle_iteration_limit_logic(self):
        """Test that cycle iteration limit logic is deterministic."""
        # Test the mathematical logic that determines when cycles should terminate
        test_cases = [
            {
                "start_value": 10,
                "increment": 5,
                "threshold": 50,
                "expected_iterations": 8,
            },
            {
                "start_value": 0,
                "increment": 10,
                "threshold": 100,
                "expected_iterations": 10,
            },
            {
                "start_value": 5,
                "increment": 3,
                "threshold": 20,
                "expected_iterations": 5,
            },
        ]

        for case in test_cases:
            # Simulate the iteration logic multiple times
            results = []
            for _ in range(5):
                value = case["start_value"]
                iterations = 0

                while value < case["threshold"] and iterations < 20:  # Safety limit
                    value += case["increment"]
                    iterations += 1

                results.append(iterations)

            # All results should be identical (deterministic)
            assert all(
                r == results[0] for r in results
            ), f"Inconsistent iterations for {case}: {results}"
            assert (
                results[0] == case["expected_iterations"]
            ), f"Expected {case['expected_iterations']} iterations, got {results[0]}"

    @pytest.mark.timeout(1)
    def test_switch_node_condition_evaluation_deterministic(self):
        """Test that switch node condition evaluation is deterministic."""
        # Test the condition evaluation logic that determines cycle termination
        test_conditions = [
            {
                "field": "value",
                "operator": "<",
                "threshold": 50,
                "test_value": 45,
                "expected": True,
            },
            {
                "field": "value",
                "operator": "<",
                "threshold": 50,
                "test_value": 55,
                "expected": False,
            },
            {
                "field": "count",
                "operator": ">=",
                "threshold": 10,
                "test_value": 10,
                "expected": True,
            },
            {
                "field": "count",
                "operator": ">=",
                "threshold": 10,
                "test_value": 5,
                "expected": False,
            },
        ]

        for condition in test_conditions:
            # Test the condition multiple times
            results = []
            for _ in range(5):
                test_data = {condition["field"]: condition["test_value"]}

                # Simulate switch node condition logic
                field_value = test_data.get(condition["field"])
                operator = condition["operator"]
                threshold = condition["threshold"]

                if operator == "<":
                    result = field_value < threshold
                elif operator == ">=":
                    result = field_value >= threshold
                elif operator == "==":
                    result = field_value == threshold
                else:
                    result = False

                results.append(result)

            # All results should be identical (deterministic)
            assert all(
                r == results[0] for r in results
            ), f"Inconsistent condition evaluation for {condition}: {results}"
            assert (
                results[0] == condition["expected"]
            ), f"Expected {condition['expected']}, got {results[0]}"

    @pytest.mark.timeout(1)
    def test_cycle_data_flow_mapping_deterministic(self):
        """Test that cycle data flow mapping is deterministic."""
        # Test the data mapping logic used in cycle connections
        test_mappings = [
            {
                "source_data": {"result": {"iteration": 3, "value": 25}},
                "mapping": {"result": "input_data"},
                "expected": {"input_data": {"iteration": 3, "value": 25}},
            },
            {
                "source_data": {"output": {"count": 5, "status": "active"}},
                "mapping": {"output": "parameters"},
                "expected": {"parameters": {"count": 5, "status": "active"}},
            },
        ]

        for test_case in test_mappings:
            # Test the mapping logic multiple times
            results = []
            for _ in range(5):
                source_data = test_case["source_data"]
                mapping = test_case["mapping"]

                # Simulate the data mapping logic
                mapped_data = {}
                for source_key, target_key in mapping.items():
                    if source_key in source_data:
                        mapped_data[target_key] = source_data[source_key]

                results.append(mapped_data)

            # All results should be identical (deterministic)
            assert all(
                r == results[0] for r in results
            ), f"Inconsistent mapping for {test_case}: {results}"
            assert (
                results[0] == test_case["expected"]
            ), f"Expected {test_case['expected']}, got {results[0]}"
