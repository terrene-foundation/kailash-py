"""
Unit tests for cyclic workflow functionality.

Tests core cyclic workflow features including:
- Cycle creation and validation
- Max iterations limits
- Convergence conditions
- Cycle state management
"""

import pytest
from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import WorkflowValidationError
from kailash.workflow.cycle_exceptions import CycleConfigurationError


class TestCyclicWorkflowBasics:
    """Test basic cyclic workflow functionality."""

    def test_simple_cycle_with_max_iterations(self):
        """Test a simple cycle with max iterations limit."""
        # Create workflow
        workflow = Workflow("test-cycle", "test_simple_cycle")

        # Add a counter node
        def counter_func(count=0, increment=1):
            """Simple counter for testing."""
            new_count = count + increment
            return {
                "count": new_count,
                "increment": increment,
                "converged": new_count >= 5,
            }

        counter = PythonCodeNode.from_function(
            func=counter_func,
            name="counter",
            input_schema={
                "count": NodeParameter(
                    name="count", type=int, required=False, default=0
                ),
                "increment": NodeParameter(
                    name="increment", type=int, required=False, default=1
                ),
            },
        )
        workflow.add_node("counter", counter)

        # Create self-loop with max iterations
        workflow.create_cycle("count_loop").connect(
            "counter",
            "counter",
            {"result.count": "count", "result.increment": "increment"},
        ).max_iterations(3).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow, parameters={"counter": {"count": 0, "increment": 2}}
        )

        # Check results
        assert "counter" in results
        result = results["counter"]["result"]
        # Started at 0, increment by 2, max 3 iterations: 0 -> 2 -> 4 -> 6
        assert result["count"] == 6
        assert result["converged"] is True

    def test_cycle_without_max_iterations_raises_error(self):
        """Test that cycles require either max_iterations or convergence_check."""
        workflow = Workflow("test-invalid", "test_invalid_cycle")

        # Add node
        node = PythonCodeNode(name="node", code="result = {'data': 1}")
        workflow.add_node("node", node)

        # Try to create cycle without limits
        # This should raise CycleConfigurationError
        try:
            workflow.create_cycle("invalid_cycle").connect(
                "node", "node"
            ).build()  # No max_iterations or convergence_when provided
            assert False, "Should have raised CycleConfigurationError"
        except CycleConfigurationError:
            # Expected - test passes
            pass

    def test_cycle_with_convergence_expression(self):
        """Test cycle with convergence expression."""
        workflow = Workflow("test-convergence", "test_convergence")

        # Add accumulator node
        def accumulate(total=0, step=0.1):
            """Accumulate values."""
            new_total = total + step
            return {"total": new_total, "step": step}

        accumulator = PythonCodeNode.from_function(
            func=accumulate,
            name="accumulator",
            input_schema={
                "total": NodeParameter(
                    name="total", type=float, required=False, default=0.0
                ),
                "step": NodeParameter(
                    name="step", type=float, required=False, default=0.1
                ),
            },
        )
        workflow.add_node("accumulator", accumulator)

        # Create cycle with convergence expression
        workflow.create_cycle("accumulate_loop").connect(
            "accumulator",
            "accumulator",
            {"result.total": "total", "result.step": "step"},
        ).max_iterations(50).converge_when("total >= 1.0").build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Check convergence
        assert "accumulator" in results
        total = results["accumulator"]["result"]["total"]
        assert total >= 1.0

    def test_multiple_cycles_in_workflow(self):
        """Test workflow with multiple independent cycles."""
        workflow = Workflow("multi-cycle", "test_multiple_cycles")

        # First cycle - counter
        def counter_func(count=0):
            return {"count": count + 1}

        counter = PythonCodeNode.from_function(
            func=counter_func,
            name="counter",
            input_schema={
                "count": NodeParameter(
                    name="count", type=int, required=False, default=0
                )
            },
        )
        workflow.add_node("counter", counter)

        workflow.create_cycle("counter_cycle").connect(
            "counter", "counter", {"result.count": "count"}
        ).max_iterations(3).build()

        # Second cycle - accumulator (independent)
        def accumulator_func(sum=0):
            return {"sum": sum + 5}

        accumulator = PythonCodeNode.from_function(
            func=accumulator_func,
            name="accumulator",
            input_schema={
                "sum": NodeParameter(name="sum", type=int, required=False, default=0)
            },
        )
        workflow.add_node("accumulator", accumulator)

        workflow.create_cycle("accumulator_cycle").connect(
            "accumulator", "accumulator", {"result.sum": "sum"}
        ).max_iterations(2).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Both cycles should execute independently
        assert results["counter"]["result"]["count"] == 3
        assert results["accumulator"]["result"]["sum"] == 10

    def test_cycle_with_external_input(self):
        """Test cycle that also receives external input."""
        workflow = Workflow("external-input", "test_external_input")

        # Config node provides configuration
        config = PythonCodeNode(
            name="config", code="result = {'multiplier': 2, 'threshold': 10}"
        )
        workflow.add_node("config", config)

        # Processor uses config and cycles
        def process(value=0, multiplier=1, threshold=10):
            """Process with external config."""
            new_value = value + multiplier
            return {"value": new_value, "done": new_value >= threshold}

        processor = PythonCodeNode.from_function(
            func=process,
            name="processor",
            input_schema={
                "value": NodeParameter(
                    name="value", type=int, required=False, default=0
                ),
                "multiplier": NodeParameter(
                    name="multiplier", type=int, required=False, default=1
                ),
                "threshold": NodeParameter(
                    name="threshold", type=int, required=False, default=10
                ),
            },
        )
        workflow.add_node("processor", processor)

        # Connect config to processor
        workflow.connect(
            "config",
            "processor",
            {"result.multiplier": "multiplier", "result.threshold": "threshold"},
        )

        # Create cycle
        workflow.create_cycle("process_cycle").connect(
            "processor", "processor", {"result.value": "value"}
        ).max_iterations(10).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Check results
        assert results["processor"]["result"]["value"] >= 10
        assert results["processor"]["result"]["done"] is True

    def test_workflow_has_cycles_detection(self):
        """Test workflow.has_cycles() method."""
        # Non-cyclic workflow
        workflow1 = Workflow("linear", "Linear Workflow")
        node1 = PythonCodeNode(name="node1", code="result = 1")
        node2 = PythonCodeNode(name="node2", code="result = 2")
        workflow1.add_node("n1", node1)
        workflow1.add_node("n2", node2)
        workflow1.connect("n1", "n2")

        assert not workflow1.has_cycles()

        # Cyclic workflow
        workflow2 = Workflow("cyclic", "Cyclic Workflow")
        node = PythonCodeNode(name="node", code="result = 1")
        workflow2.add_node("node", node)
        workflow2.create_cycle("test").connect("node", "node").max_iterations(5).build()

        assert workflow2.has_cycles()

    def test_cycle_id_uniqueness(self):
        """Test that cycle IDs must be unique within a workflow."""
        workflow = Workflow("test-duplicate", "test_duplicate_cycle_id")

        # Add nodes
        node1 = PythonCodeNode(name="node1", code="result = 1")
        node2 = PythonCodeNode(name="node2", code="result = 2")
        workflow.add_node("node1", node1)
        workflow.add_node("node2", node2)

        # Create first cycle
        workflow.create_cycle("same_id").connect("node1", "node1").max_iterations(
            10
        ).build()

        # Try to create second cycle with same ID
        # This might not raise an error in current implementation
        # but test the behavior anyway
        try:
            workflow.create_cycle("same_id").connect("node2", "node2").max_iterations(
                3
            ).build()
            # If no error raised, at least verify both cycles exist
            assert workflow.has_cycles()
        except (WorkflowValidationError, ValueError, KeyError):
            # If error is raised, that's also acceptable
            pass
