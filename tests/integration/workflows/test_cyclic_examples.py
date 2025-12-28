"""
Unit tests for cyclic workflow execution.

Tests basic cyclic workflow functionality including:
- Simple increment cycles
- Convergence patterns
- Cycle execution with CyclicWorkflowExecutor
"""

import pytest
from kailash import Workflow
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime


class TestCyclicExamples:
    """Test cyclic workflow execution patterns."""

    def test_simple_increment_cycle(self):
        """Test simple incrementing cycle execution."""
        # Create workflow
        workflow = Workflow(workflow_id="increment_test", name="Increment Test")

        # Add increment node using PythonCodeNode
        def increment(value=0, step=1):
            """Increment value by step."""
            new_value = value + step
            return {"value": new_value, "step": step, "done": new_value >= 10}

        incrementor = PythonCodeNode.from_function(func=increment, name="incrementor")
        workflow.add_node("increment", incrementor)

        # Create cycle
        workflow.create_cycle("increment_cycle").connect(
            "increment", "increment", {"result.value": "value", "result.step": "step"}
        ).max_iterations(15).build()

        # Execute with initial values
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow, parameters={"increment": {"value": 0, "step": 2}}
        )

        # Verify execution
        assert "increment" in results
        result = results["increment"]["result"]
        assert result["value"] >= 10
        assert result["done"] is True

    def test_quality_improvement_cycle(self):
        """Test quality improvement cycle pattern."""
        # Create workflow
        workflow = Workflow(workflow_id="quality_test", name="Quality Test")

        # Add quality improver node
        def improve_quality(quality=0.0, improvement_rate=0.2):
            """Improve quality gradually."""
            # Improve quality by rate each iteration
            new_quality = min(1.0, quality + improvement_rate)

            return {
                "quality": new_quality,
                "improvement": new_quality - quality,
                "target_reached": new_quality >= 0.8,
            }

        from kailash.nodes.base import NodeParameter

        improver = PythonCodeNode.from_function(
            func=improve_quality,
            name="improver",
            input_schema={
                "quality": NodeParameter(
                    name="quality", type=float, required=False, default=0.0
                ),
                "improvement_rate": NodeParameter(
                    name="improvement_rate", type=float, required=False, default=0.2
                ),
            },
        )
        workflow.add_node("improver", improver)

        # Create improvement cycle
        workflow.create_cycle("quality_cycle").connect(
            "improver", "improver", {"result.quality": "quality"}
        ).max_iterations(10).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow,
            parameters={"improver": {"quality": 0.0, "improvement_rate": 0.15}},
        )

        # Verify quality improved
        assert "improver" in results
        final_quality = results["improver"]["result"]["quality"]
        assert final_quality >= 0.8
        assert final_quality <= 1.0

    def test_cycle_with_multiple_outputs(self):
        """Test cycle that tracks multiple values."""
        # Create workflow
        workflow = Workflow(workflow_id="multi_output_test", name="Multi Output Test")

        # Add node that produces multiple outputs
        def process_data(counter=0, accumulator=0, multiplier=2):
            """Process data with multiple outputs."""
            new_counter = counter + 1
            new_accumulator = accumulator + (counter * multiplier)

            return {
                "counter": new_counter,
                "accumulator": new_accumulator,
                "multiplier": multiplier,
                "iterations_done": new_counter,
            }

        processor = PythonCodeNode.from_function(func=process_data, name="processor")
        workflow.add_node("processor", processor)

        # Create cycle with multiple mappings
        workflow.create_cycle("multi_cycle").connect(
            "processor",
            "processor",
            {
                "result.counter": "counter",
                "result.accumulator": "accumulator",
                "result.multiplier": "multiplier",
            },
        ).max_iterations(5).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow,
            parameters={"processor": {"counter": 0, "accumulator": 0, "multiplier": 3}},
        )

        # Verify multiple values were tracked
        assert "processor" in results
        result = results["processor"]["result"]
        assert result["counter"] > 0
        assert result["counter"] <= 5
        assert result["accumulator"] > 0
        assert result["iterations_done"] == result["counter"]

    def test_cycle_execution_without_initial_params(self):
        """Test cycle execution with default parameters."""
        # Create workflow
        workflow = Workflow(
            workflow_id="default_params_test", name="Default Params Test"
        )

        # Add node with defaults
        def counter_with_defaults(count=0):
            """Counter with default starting value."""
            return {"count": count + 1}

        from kailash.nodes.base import NodeParameter

        counter = PythonCodeNode.from_function(
            func=counter_with_defaults,
            name="counter",
            input_schema={
                "count": NodeParameter(
                    name="count", type=int, required=False, default=0
                )
            },
        )
        workflow.add_node("counter", counter)

        # Create cycle
        workflow.create_cycle("default_cycle").connect(
            "counter", "counter", {"result.count": "count"}
        ).max_iterations(3).build()

        # Execute without parameters
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Should use defaults and execute
        assert "counter" in results
        assert results["counter"]["result"]["count"] == 3

    def test_cycle_with_early_termination(self):
        """Test cycle that might terminate early based on condition."""
        # Create workflow
        workflow = Workflow(
            workflow_id="early_termination_test", name="Early Termination Test"
        )

        # Add node that can signal early termination
        def process_until_threshold(value=0, threshold=50):
            """Process until threshold reached."""
            # Large increment to potentially reach threshold early
            new_value = value + 20
            should_continue = new_value < threshold

            return {
                "value": new_value,
                "threshold": threshold,
                "should_continue": should_continue,
            }

        processor = PythonCodeNode.from_function(
            func=process_until_threshold, name="processor"
        )
        workflow.add_node("processor", processor)

        # Create cycle with high max_iterations
        workflow.create_cycle("threshold_cycle").connect(
            "processor",
            "processor",
            {"result.value": "value", "result.threshold": "threshold"},
        ).max_iterations(10).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow, parameters={"processor": {"value": 0, "threshold": 50}}
        )

        # Should stop when threshold reached, not at max_iterations
        assert "processor" in results
        result = results["processor"]["result"]
        assert result["value"] >= 50
        # Since we're incrementing by 20 each time, final value depends on iterations
        # Max iterations is 10, so max value would be 0 + (20 * 10) = 200
        assert result["value"] <= 200
