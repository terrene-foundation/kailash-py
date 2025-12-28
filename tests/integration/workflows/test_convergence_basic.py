"""
Unit tests for workflow convergence functionality.

Tests cyclic workflow features including:
1. Expression-based convergence conditions
2. Maximum iteration safety limits
3. Custom convergence logic
4. Nested cycles

Note: These tests validate that cyclic workflows can be created and executed,
but the convergence expression evaluation has limitations in the current SDK.
"""

import pytest
from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime


class TestConvergence:
    """Test convergence functionality in cyclic workflows."""

    def test_max_iterations_safety(self):
        """Test maximum iterations safety limit prevents infinite loops."""
        # Create workflow
        workflow = Workflow(
            workflow_id="max_iterations_safety",
            name="Max Iterations Safety Test",
        )

        # Add slow incrementor node
        def slow_increment(value=0):
            """Increment very slowly."""
            return {"value": value + 0.01}

        incrementor = PythonCodeNode.from_function(
            func=slow_increment,
            name="incrementor",
            input_schema={
                "value": NodeParameter(
                    name="value", type=float, required=False, default=0.0
                ),
            },
        )
        workflow.add_node("incrementor", incrementor)

        # Create cycle with max iterations limit (intentionally low)
        workflow.create_cycle("limited_loop").connect(
            "incrementor", "incrementor", {"result.value": "value"}
        ).max_iterations(5).converge_when("value >= 0.95").build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "incrementor": {
                    "value": 0.1,
                }
            },
        )

        # Verify max iterations safety worked
        assert "incrementor" in results
        final_value = results["incrementor"]["result"].get("value", 0)
        # Should NOT reach 0.95 due to max iterations limit (0.1 + 5*0.01 = 0.15)
        assert final_value < 0.95
        # But should have made some progress
        assert final_value > 0.1

    def test_simple_cycle_execution(self):
        """Test that a simple cycle executes and produces results."""
        # Create workflow
        workflow = Workflow(
            workflow_id="simple_cycle",
            name="Simple Cycle Test",
        )

        # Add counter node
        def count(n=0):
            """Simple counter."""
            return {"count": n + 1}

        counter = PythonCodeNode.from_function(
            func=count,
            name="counter",
            input_schema={
                "n": NodeParameter(name="n", type=int, required=False, default=0),
            },
        )
        workflow.add_node("counter", counter)

        # Create simple cycle
        workflow.create_cycle("count_loop").connect(
            "counter", "counter", {"result.count": "n"}
        ).max_iterations(3).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Verify cycle executed
        assert "counter" in results
        # Should have counted up to max_iterations
        count_value = results["counter"]["result"].get("count", 0)
        assert count_value > 0
        assert count_value <= 3

    def test_cycle_with_initial_parameters(self):
        """Test cycle with initial parameters."""
        # Create workflow
        workflow = Workflow(
            workflow_id="cycle_with_params",
            name="Cycle with Parameters Test",
        )

        # Add accumulator node
        def accumulate(total=0, step=1):
            """Accumulate by step amount."""
            return {"total": total + step, "step": step}

        accumulator = PythonCodeNode.from_function(
            func=accumulate,
            name="accumulator",
            input_schema={
                "total": NodeParameter(
                    name="total", type=float, required=False, default=0.0
                ),
                "step": NodeParameter(
                    name="step", type=float, required=False, default=1.0
                ),
            },
        )
        workflow.add_node("accumulator", accumulator)

        # Create cycle
        workflow.create_cycle("accumulate_loop").connect(
            "accumulator",
            "accumulator",
            {
                "result.total": "total",
                "result.step": "step",
            },
        ).max_iterations(5).build()

        # Execute with initial parameters
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "accumulator": {
                    "total": 10.0,
                    "step": 2.0,
                }
            },
        )

        # Verify accumulation worked
        assert "accumulator" in results
        final_total = results["accumulator"]["result"].get("total", 0)
        # Started at 10, added 2.0 per iteration
        assert final_total > 10.0
        # Max 5 iterations: 10 + (5 * 2) = 20
        assert final_total <= 20.0

    def test_none_handling_in_cycle(self):
        """Test that None values are properly handled in cycles."""
        # Create workflow
        workflow = Workflow(workflow_id="none_handling", name="None Handling Test")

        # Create a node that handles None
        def handle_none(value=None):
            """Function that handles None values."""
            if value is None:
                return {"value": 1}
            return {"value": value + 1}

        node = PythonCodeNode.from_function(
            func=handle_none,
            name="none_handler",
            input_schema={
                "value": NodeParameter(name="value", type=int, required=False)
            },
        )
        workflow.add_node("handler", node)

        # Create cycle
        workflow.create_cycle("none_loop").connect(
            "handler", "handler", {"result.value": "value"}
        ).max_iterations(3).build()

        # Execute with no parameters (None initial value)
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow, parameters={})

        # Should handle None and produce values
        assert "handler" in results
        final_value = results["handler"]["result"]["value"]
        assert final_value > 0  # Started from None (1), then incremented

    def test_multi_node_cycle(self):
        """Test cycle with multiple nodes in the loop."""
        # Create workflow
        workflow = Workflow(
            workflow_id="multi_node_cycle",
            name="Multi-Node Cycle Test",
        )

        # Node 1: Generate data
        def generate(iteration=0):
            """Generate data based on iteration."""
            return {
                "data": f"data_{iteration}",
                "iteration": iteration,
            }

        generator = PythonCodeNode.from_function(
            func=generate,
            name="generator",
            input_schema={
                "iteration": NodeParameter(
                    name="iteration", type=int, required=False, default=0
                ),
            },
        )
        workflow.add_node("generator", generator)

        # Node 2: Process data
        def process(data, iteration):
            """Process data and increment iteration."""
            processed = f"processed_{data}"
            new_iteration = iteration + 1
            return {
                "processed_data": processed,
                "iteration": new_iteration,
            }

        processor = PythonCodeNode.from_function(
            func=process,
            name="processor",
            input_schema={
                "data": NodeParameter(name="data", type=str, required=True),
                "iteration": NodeParameter(name="iteration", type=int, required=True),
            },
        )
        workflow.add_node("processor", processor)

        # Connect nodes
        workflow.connect(
            "generator",
            "processor",
            mapping={
                "result.data": "data",
                "result.iteration": "iteration",
            },
        )

        # Create cycle from processor back to generator
        workflow.create_cycle("multi_node_loop").connect(
            "processor", "generator", {"result.iteration": "iteration"}
        ).max_iterations(3).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Verify cycle executed properly
        assert "processor" in results
        processor_result = results["processor"]["result"]
        # Should have incremented iteration
        assert processor_result["iteration"] > 0
        assert processor_result["iteration"] <= 3
        assert "processed_" in processor_result["processed_data"]
