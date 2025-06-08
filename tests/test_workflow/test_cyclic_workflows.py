"""Tests for cyclic workflow functionality."""

from typing import Any, Dict

import pytest

from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.sdk_exceptions import WorkflowValidationError
from kailash.workflow.convergence import (
    ExpressionCondition,
    MaxIterationsCondition,
    create_convergence_condition,
)
from kailash.workflow.cycle_state import CycleState, CycleStateManager
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor


class CounterNode(Node):
    """Simple counter node for testing cycles."""

    def get_parameters(self):
        return {
            "count": NodeParameter(
                name="count",
                type=int,
                required=False,
                default=0,
                description="Current count",
            ),
            "increment": NodeParameter(
                name="increment",
                type=int,
                required=False,
                default=1,
                description="Increment value",
            ),
        }

    def run(self, context: Dict[str, Any], **kwargs):
        count = kwargs.get("count", 0)
        increment = kwargs.get("increment", 1)

        # Get iteration from context
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        new_count = count + increment

        return {"count": new_count, "iteration": iteration, "converged": new_count >= 5}


class TestCyclicWorkflowBasics:
    """Test basic cyclic workflow functionality."""

    def test_simple_cycle_with_max_iterations(self):
        """Test a simple cycle with max iterations limit."""
        # Create workflow
        workflow = Workflow("test-cycle", "test_simple_cycle")

        # Add a counter node with increment in config
        workflow.add_node("counter", CounterNode(), increment=2)

        # Create self-loop with max iterations
        workflow.connect(
            "counter",
            "counter",
            mapping={"count": "count"},
            cycle=True,
            max_iterations=3,
            cycle_id="count_loop",
        )

        # Execute
        executor = CyclicWorkflowExecutor()
        results, run_id = executor.execute(
            workflow, parameters={"counter": {"count": 0}}
        )

        # Check results
        assert "counter" in results
        # The node's iteration reflects the cycle_state iteration at execution time
        # But we need to check what iteration value the node saw
        assert results["counter"]["count"] == 6  # 0 + 2*3
        # The last execution happens when cycle iteration is 2 (before it's incremented to 3)
        assert results["counter"]["iteration"] == 2

    def test_cycle_with_expression_convergence(self):
        """Test cycle with expression-based convergence."""
        # Create workflow
        workflow = Workflow("test-convergence", "test_expression_convergence")

        # Add a counter node with increment in config
        workflow.add_node("counter", CounterNode(), increment=2)

        # Create self-loop with convergence expression
        workflow.connect(
            "counter",
            "counter",
            mapping={"count": "count"},
            cycle=True,
            max_iterations=10,
            convergence_check="count >= 5",
            cycle_id="convergence_loop",
        )

        # Execute
        executor = CyclicWorkflowExecutor()
        results, run_id = executor.execute(
            workflow, parameters={"counter": {"count": 0}}
        )

        # Check results - should stop when count >= 5
        assert results["counter"]["count"] == 6  # 0 + 2 + 2 + 2
        assert results["counter"]["iteration"] < 10  # Should stop before max

    def test_cycle_detection_and_validation(self):
        """Test cycle detection methods."""
        # Create workflow with cycle
        workflow = Workflow("test-detection", "test_cycle_detection")

        workflow.add_node("a", CounterNode())
        workflow.add_node("b", CounterNode())

        # Regular connection
        workflow.connect("a", "b", mapping={"count": "count"})

        # Cycle connection
        workflow.connect(
            "b",
            "a",
            mapping={"count": "count"},
            cycle=True,
            max_iterations=5,
            cycle_id="ab_cycle",
        )

        # Test detection methods
        assert workflow.has_cycles() is True

        dag_edges, cycle_edges = workflow.separate_dag_and_cycle_edges()
        assert len(dag_edges) == 1  # a->b
        assert len(cycle_edges) == 1  # b->a

        cycle_groups = workflow.get_cycle_groups()
        assert "ab_cycle" in cycle_groups
        # Enhanced cycle detection now includes synthetic edges for complete cycle groups
        # For A -> B -> A cycle with only B -> A marked as cycle:
        # - Original: B -> A (cycle=True)
        # - Synthetic: A -> B (cycle=True, synthetic=True)
        assert len(cycle_groups["ab_cycle"]) == 2

        # Verify we have both original and synthetic edges
        edges = cycle_groups["ab_cycle"]
        original_edges = [
            (s, t, d) for s, t, d in edges if not d.get("synthetic", False)
        ]
        synthetic_edges = [(s, t, d) for s, t, d in edges if d.get("synthetic", False)]
        assert len(original_edges) == 1  # B -> A
        assert len(synthetic_edges) == 1  # A -> B (synthetic)

    def test_unmarked_cycle_rejection(self):
        """Test that unmarked cycles are rejected."""
        workflow = Workflow("test-unmarked", "test_unmarked_cycle")

        workflow.add_node("a", CounterNode())
        workflow.add_node("b", CounterNode())

        # Create unmarked cycle
        workflow.connect("a", "b", mapping={"count": "count"})
        workflow.connect("b", "a", mapping={"count": "count"})  # No cycle=True

        # Should fail validation
        with pytest.raises(WorkflowValidationError) as excinfo:
            workflow.validate()

        assert "unmarked cycles" in str(excinfo.value)

    def test_cycle_state_preservation(self):
        """Test that cycle state is preserved across iterations."""

        # Create a node that uses cycle state
        class StateNode(Node):
            def get_parameters(self):
                return {
                    "value": NodeParameter(
                        name="value", type=int, required=False, default=0
                    ),
                }

            def run(self, context: Dict[str, Any], **kwargs):
                value = kwargs.get("value", 0)

                # Get previous state
                cycle_info = context.get("cycle", {})
                node_state = cycle_info.get("node_state") or {}
                history = node_state.get("history", [])

                # Add to history
                history.append(value)

                return {
                    "value": value + 1,
                    "history": history,
                    "_cycle_state": {"history": history},
                }

        workflow = Workflow("test-state", "test_state_preservation")
        workflow.add_node("state_node", StateNode())

        workflow.connect(
            "state_node",
            "state_node",
            mapping={"value": "value"},
            cycle=True,
            max_iterations=3,
            cycle_id="state_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(
            workflow, parameters={"state_node": {"value": 10}}
        )

        # Check that history was preserved
        assert "history" in results["state_node"]
        assert len(results["state_node"]["history"]) == 3
        assert results["state_node"]["history"] == [10, 11, 12]

    def test_cycle_safety_limits(self):
        """Test cycle safety limits (timeout, memory)."""
        # This is a basic test - full safety testing would require mocking
        workflow = Workflow("test-safety", "test_safety_limits")
        workflow.add_node("counter", CounterNode())

        workflow.connect(
            "counter",
            "counter",
            mapping={"count": "count"},
            cycle=True,
            max_iterations=100,
            timeout=1.0,  # 1 second timeout
            memory_limit=100,  # 100MB limit
            cycle_id="safety_loop",
        )

        # Should execute successfully within limits
        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(
            workflow, parameters={"counter": {"count": 0, "increment": 1}}
        )

        # Should have stopped due to timeout or iterations
        assert results["counter"]["count"] <= 100


class TestConvergenceConditions:
    """Test convergence condition functionality."""

    def test_expression_condition(self):
        """Test expression-based convergence."""
        condition = ExpressionCondition("score > 0.9")

        # Test with passing result
        results = {"validator": {"score": 0.95}}
        cycle_state = CycleState()
        assert condition.evaluate(results, cycle_state) is True

        # Test with failing result
        results = {"validator": {"score": 0.85}}
        assert condition.evaluate(results, cycle_state) is False

    def test_max_iterations_condition(self):
        """Test max iterations convergence."""
        condition = MaxIterationsCondition(5)

        cycle_state = CycleState()
        results = {}

        # Should not converge before max
        for i in range(4):
            cycle_state.update(results, i)
            assert condition.evaluate(results, cycle_state) is False

        # Should converge at max
        cycle_state.update(results, 5)
        assert condition.evaluate(results, cycle_state) is True

    def test_create_convergence_condition(self):
        """Test convergence condition factory."""
        # String creates expression condition
        cond = create_convergence_condition("value > 10")
        assert isinstance(cond, ExpressionCondition)

        # Int creates max iterations condition
        cond = create_convergence_condition(5)
        assert isinstance(cond, MaxIterationsCondition)

        # Callable creates callback condition
        def my_convergence(results, state):
            return results.get("done", False)

        cond = create_convergence_condition(my_convergence)
        assert cond.evaluate({"done": True}, CycleState()) is True


class TestCycleState:
    """Test cycle state management."""

    def test_dag_to_cycle_parameter_propagation(self):
        """Test that DAG nodes properly feed data into cycles."""

        class DataSourceNode(Node):
            """Generates initial data."""

            def get_parameters(self):
                return {
                    "size": NodeParameter(
                        name="size", type=int, required=False, default=5
                    )
                }

            def run(self, context, **kwargs):
                size = kwargs.get("size", 5)
                return {"data": list(range(size)), "quality": 0.3}

        class DataProcessorNode(Node):
            """Processes data in a cycle."""

            def get_parameters(self):
                return {
                    "data": NodeParameter(
                        name="data", type=list, required=False, default=[]
                    ),
                    "quality": NodeParameter(
                        name="quality", type=float, required=False, default=0.0
                    ),
                    "increment": NodeParameter(
                        name="increment", type=float, required=False, default=0.2
                    ),
                }

            def run(self, context, **kwargs):
                data = kwargs.get("data", [])
                quality = kwargs.get("quality", 0.0)
                increment = kwargs.get("increment", 0.2)

                return {
                    "data": data,
                    "quality": quality + increment,
                    "done": quality + increment >= 0.9,
                }

        # Create workflow
        workflow = Workflow("dag-cycle-test", "test")
        workflow.add_node("source", DataSourceNode())
        workflow.add_node("processor", DataProcessorNode())

        # Connect source to processor
        workflow.connect(
            "source", "processor", mapping={"data": "data", "quality": "quality"}
        )

        # Create cycle on processor
        workflow.connect(
            "processor",
            "processor",
            mapping={"data": "data", "quality": "quality"},
            cycle=True,
            max_iterations=5,
            convergence_check="done == True",
            cycle_id="process_loop",
        )

        # Execute
        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(workflow, parameters={"source": {"size": 3}})

        # Verify results
        assert "source" in results
        assert "processor" in results

        # Check source was executed
        assert results["source"]["data"] == [0, 1, 2]
        assert results["source"]["quality"] == 0.3

        # Check processor received and maintained data through cycles
        assert results["processor"]["data"] == [0, 1, 2]
        assert results["processor"]["quality"] >= 0.9
        assert results["processor"]["done"] is True

    def test_cycle_state_tracking(self):
        """Test basic cycle state tracking."""
        state = CycleState("test-cycle")

        assert state.cycle_id == "test-cycle"
        assert state.iteration == 0
        assert len(state.history) == 0

        # Update state
        results = {"node1": {"value": 10}}
        state.update(results)

        assert state.iteration == 1
        assert len(state.history) == 1
        assert state.history[0]["results"] == results

    def test_cycle_state_trends(self):
        """Test trend calculation in cycle state."""
        state = CycleState("test-cycle")

        # Add some iterations with numeric values
        for i in range(3):
            results = {"optimizer": {"loss": 1.0 - i * 0.3, "accuracy": 0.7 + i * 0.1}}
            state.update(results)

        # Check trend calculation
        trends = state.calculate_trend()
        assert "numeric_trends" in trends
        assert "optimizer.loss" in trends["numeric_trends"]
        assert "optimizer.accuracy" in trends["numeric_trends"]

        # Loss should be decreasing
        loss_trend = trends["numeric_trends"]["optimizer.loss"]
        assert loss_trend["change"] < 0

        # Accuracy should be increasing
        acc_trend = trends["numeric_trends"]["optimizer.accuracy"]
        assert acc_trend["change"] > 0

    def test_cycle_state_manager(self):
        """Test cycle state manager for nested cycles."""
        manager = CycleStateManager()

        # Get or create states
        state1 = manager.get_or_create_state("cycle1")
        state2 = manager.get_or_create_state("cycle2")

        assert state1.cycle_id == "cycle1"
        assert state2.cycle_id == "cycle2"
        assert len(manager.states) == 2

        # Test nested cycle tracking
        manager.push_cycle("cycle1")
        assert manager.get_active_cycle() == "cycle1"

        manager.push_cycle("cycle2")
        assert manager.get_active_cycle() == "cycle2"

        popped = manager.pop_cycle()
        assert popped == "cycle2"
        assert manager.get_active_cycle() == "cycle1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
