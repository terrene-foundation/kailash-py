"""Tests based on cyclic workflow examples."""

from typing import Any

import pytest

from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor


class IncrementNode(Node):
    """Simple node that increments a value."""

    def get_parameters(self):
        return {
            "value": NodeParameter(
                name="value",
                type=int,
                required=False,
                default=0,
                description="Value to increment",
            ),
            "step": NodeParameter(
                name="step",
                type=int,
                required=False,
                default=1,
                description="Increment step",
            ),
        }

    def run(self, context: dict[str, Any], **kwargs):
        value = kwargs.get("value", 0)
        step = kwargs.get("step", 1)

        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        new_value = value + step

        return {
            "value": new_value,
            "iteration": iteration,
            "converged": new_value >= 10,
        }


class QualityImproverNode(Node):
    """Node that improves quality over iterations."""

    def get_parameters(self):
        return {
            "quality": NodeParameter(
                name="quality",
                type=float,
                required=False,
                default=0.0,
                description="Current quality",
            ),
            "data": NodeParameter(
                name="data",
                type=dict,
                required=False,
                default={},
                description="Data to process",
            ),
        }

    def run(self, context: dict[str, Any], **kwargs):
        quality = kwargs.get("quality", 0.0)
        data = kwargs.get("data", {})

        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Improve quality by 20% each iteration
        new_quality = min(1.0, quality + 0.2)

        # Track improvements
        prev_state = cycle_info.get("node_state") or {}
        improvements = prev_state.get("improvements", [])
        improvements.append(
            {"iteration": iteration, "before": quality, "after": new_quality}
        )

        return {
            "quality": new_quality,
            "data": {**data, "processed": True},
            "improvements_made": len(improvements),
            "_cycle_state": {"improvements": improvements},
        }


class TestCyclicExamples:
    """Test cyclic workflows based on examples."""

    def test_basic_increment_cycle(self):
        """Test basic increment cycle similar to counter example."""
        workflow = Workflow("test-increment", "test_increment")

        # Single node with self-loop
        workflow.add_node("incrementer", IncrementNode())

        # Create cycle
        workflow.connect(
            "incrementer",
            "incrementer",
            mapping={"value": "value"},
            cycle=True,
            max_iterations=15,
            convergence_check="value >= 10",
            cycle_id="increment_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(
            workflow, parameters={"incrementer": {"value": 0, "step": 2}}
        )

        # Should stop at value 10 (0, 2, 4, 6, 8, 10)
        assert results["incrementer"]["value"] == 10
        # Iteration count depends on when convergence is checked

    def test_quality_improvement_cycle(self):
        """Test quality improvement cycle."""
        workflow = Workflow("test-quality", "test_quality")

        # Quality improver node
        workflow.add_node("improver", QualityImproverNode())

        # Self-loop until quality threshold
        workflow.connect(
            "improver",
            "improver",
            mapping={"quality": "quality", "data": "data"},
            cycle=True,
            max_iterations=10,
            convergence_check="quality >= 0.9",
            cycle_id="quality_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(
            workflow, parameters={"improver": {"quality": 0.1, "data": {"raw": True}}}
        )

        # Quality should have improved from 0.1
        assert results["improver"]["quality"] > 0.1
        assert results["improver"]["improvements_made"] > 0
        assert results["improver"]["data"]["processed"] is True

        # Check if actually converged (quality >= 0.9) or hit max iterations
        if results["improver"]["quality"] >= 0.9:
            # Should reach quality 0.9 after 4-5 iterations depending on execution
            # 0.1 -> 0.3 -> 0.5 -> 0.7 -> 0.9 (or with extra iteration at start)
            assert results["improver"]["improvements_made"] in [4, 5]

    def test_multi_node_cycle(self):
        """Test cycle with multiple nodes."""
        workflow = Workflow("test-multi", "test_multi_node")

        # Create two nodes that work together
        workflow.add_node("processor", IncrementNode())

        class ValidatorNode(Node):
            def get_parameters(self):
                return {
                    "value": NodeParameter(
                        name="value", type=int, required=False, default=0
                    ),
                }

            def run(self, context, **kwargs):
                value = kwargs.get("value", 0)
                return {
                    "value": value,
                    "valid": value < 10,
                    "message": f"Value {value} is {'valid' if value < 10 else 'complete'}",
                }

        workflow.add_node("validator", ValidatorNode())

        # Connect nodes
        workflow.connect("processor", "validator", mapping={"value": "value"})

        # Cycle back from validator to processor
        workflow.connect(
            "validator",
            "processor",
            mapping={"value": "value"},
            cycle=True,
            max_iterations=20,
            convergence_check="value >= 10",
            cycle_id="process_validate_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(
            workflow, parameters={"processor": {"value": 0, "step": 3}}
        )

        # Should stop at value >= 10
        assert results["validator"]["value"] >= 10
        assert results["validator"]["valid"] is False
        assert "complete" in results["validator"]["message"]

    def test_cycle_with_timeout(self):
        """Test cycle timeout safety."""
        workflow = Workflow("test-timeout", "test_timeout")

        # Node that never converges
        class SlowNode(Node):
            def get_parameters(self):
                return {
                    "value": NodeParameter(
                        name="value", type=int, required=False, default=0
                    ),
                }

            def run(self, context, **kwargs):
                import time

                time.sleep(0.1)  # Simulate slow processing
                value = kwargs.get("value", 0)
                return {"value": value + 1}

        workflow.add_node("slow", SlowNode())

        # Create cycle with short timeout
        workflow.connect(
            "slow",
            "slow",
            mapping={"value": "value"},
            cycle=True,
            max_iterations=100,
            convergence_check="value >= 1000",  # Never reached
            cycle_id="slow_loop",
            timeout=0.5,
        )  # 0.5 second timeout

        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(workflow, parameters={"slow": {"value": 0}})

        # Should stop due to timeout after ~5 iterations
        assert results["slow"]["value"] < 10

    def test_cycle_state_persistence(self):
        """Test that cycle state persists across iterations."""
        workflow = Workflow("test-state", "test_state")

        class StatefulNode(Node):
            def get_parameters(self):
                return {
                    "value": NodeParameter(
                        name="value", type=int, required=False, default=0
                    ),
                }

            def run(self, context, **kwargs):
                value = kwargs.get("value", 0)

                cycle_info = context.get("cycle", {})
                prev_state = cycle_info.get("node_state") or {}

                # Accumulate values
                accumulated = prev_state.get("accumulated", [])
                accumulated.append(value)

                return {
                    "value": value + 1,
                    "accumulated_count": len(accumulated),
                    "accumulated_sum": sum(accumulated),
                    "_cycle_state": {"accumulated": accumulated},
                }

        workflow.add_node("stateful", StatefulNode())

        workflow.connect(
            "stateful",
            "stateful",
            mapping={"value": "value"},
            cycle=True,
            max_iterations=5,
            cycle_id="state_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(workflow, parameters={"stateful": {"value": 1}})

        # Should accumulate [1, 2, 3, 4, 5]
        assert results["stateful"]["value"] == 6
        assert results["stateful"]["accumulated_count"] == 5
        assert results["stateful"]["accumulated_sum"] == 15  # 1+2+3+4+5

    def test_nested_workflow_cycles(self):
        """Test workflows with multiple independent cycles."""
        workflow = Workflow("test-nested", "test_nested")

        # First cycle: counter
        workflow.add_node("counter1", IncrementNode())
        workflow.connect(
            "counter1",
            "counter1",
            mapping={"value": "value"},
            cycle=True,
            max_iterations=5,
            convergence_check="value >= 5",
            cycle_id="counter1_loop",
        )

        # Second cycle: counter
        workflow.add_node("counter2", IncrementNode())
        workflow.connect(
            "counter2",
            "counter2",
            mapping={"value": "value"},
            cycle=True,
            max_iterations=5,
            convergence_check="value >= 10",
            cycle_id="counter2_loop",
        )

        # Connect cycles
        workflow.connect("counter1", "counter2", mapping={"value": "value"})

        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(
            workflow,
            parameters={"counter1": {"value": 0, "step": 1}, "counter2": {"step": 2}},
        )

        # First counter reaches 5
        assert results["counter1"]["value"] >= 5
        # Second counter should have a value > 5 (started from counter1's output)
        assert results["counter2"]["value"] > 5


class TestCyclicWorkflowEdgeCases:
    """Test edge cases and error conditions."""

    def test_cycle_without_convergence(self):
        """Test cycle that only stops at max iterations."""
        workflow = Workflow("test-no-converge", "test_no_convergence")

        workflow.add_node("counter", IncrementNode())
        workflow.connect(
            "counter",
            "counter",
            mapping={"value": "value"},
            cycle=True,
            max_iterations=3,
            cycle_id="no_converge_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(workflow, parameters={"counter": {"value": 0}})

        # Should stop at max iterations
        assert results["counter"]["value"] == 3
        assert results["counter"]["iteration"] == 2  # 0, 1, 2

    def test_immediate_convergence(self):
        """Test cycle that converges immediately."""
        workflow = Workflow("test-immediate", "test_immediate")

        workflow.add_node("counter", IncrementNode())
        workflow.connect(
            "counter",
            "counter",
            mapping={"value": "value"},
            cycle=True,
            max_iterations=10,
            convergence_check="value >= 5",
            cycle_id="immediate_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(
            workflow, parameters={"counter": {"value": 10}}  # Already above threshold
        )

        # Should run once and converge
        assert results["counter"]["value"] == 11
        assert results["counter"]["iteration"] == 0

    def test_one_max_iteration(self):
        """Test cycle with max_iterations=1."""
        workflow = Workflow("test-one", "test_one_iter")

        workflow.add_node("counter", IncrementNode())
        workflow.connect(
            "counter",
            "counter",
            mapping={"value": "value"},
            cycle=True,
            max_iterations=1,
            cycle_id="one_iter_loop",
        )

        executor = CyclicWorkflowExecutor()
        results, _ = executor.execute(workflow, parameters={"counter": {"value": 0}})

        # Should iterate exactly once
        assert "counter" in results
        assert results["counter"]["value"] == 1
        assert results["counter"]["iteration"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
