"""
Unit tests for core cycle execution in the Kailash SDK.

Tests fundamental cyclic workflow execution patterns including:
- Basic cycle execution mechanics
- Convergence patterns and detection
- Nested cycle scenarios
- Parameter propagation through cycles
- State management across iterations
"""

import pytest

from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.logic import SwitchNode
from kailash.runtime.local import LocalRuntime


class TestCoreCycleExecution:
    """Test core cycle execution functionality."""

    def test_basic_cycle_execution(self):
        """Test basic cycle execution mechanics."""
        workflow = Workflow("basic_cycle", "Basic Cycle Test")

        # Simple counter node
        def counter(count=0, increment=1):
            """Increment counter."""
            return {"count": count + increment, "increment": increment}

        counter_node = PythonCodeNode.from_function(
            func=counter,
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
        workflow.add_node("counter", counter_node)

        # Create basic cycle
        workflow.create_cycle("basic_cycle").connect(
            "counter",
            "counter",
            {"result.count": "count", "result.increment": "increment"},
        ).max_iterations(5).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow, parameters={"counter": {"count": 0, "increment": 2}}
        )

        # Verify execution
        assert results["counter"]["result"]["count"] == 10  # 0 + (2 * 5)

    def test_convergence_detection(self):
        """Test convergence pattern detection in cycles."""
        workflow = Workflow("convergence_test", "Convergence Test")

        # Node that converges to a value
        def converge_value(value=0.0, target=1.0, rate=0.1):
            """Converge towards target value."""
            diff = target - value
            step = diff * rate
            new_value = value + step
            converged = abs(new_value - target) < 0.01

            return {
                "value": new_value,
                "target": target,
                "converged": converged,
                "difference": abs(new_value - target),
            }

        converge_node = PythonCodeNode.from_function(
            func=converge_value,
            name="converger",
            input_schema={
                "value": NodeParameter(
                    name="value", type=float, required=False, default=0.0
                ),
                "target": NodeParameter(
                    name="target", type=float, required=False, default=1.0
                ),
                "rate": NodeParameter(
                    name="rate", type=float, required=False, default=0.1
                ),
            },
        )
        workflow.add_node("converger", converge_node)

        # Create convergence cycle
        workflow.create_cycle("convergence_cycle").connect(
            "converger",
            "converger",
            {"result.value": "value", "result.target": "target"},
        ).max_iterations(50).converge_when("difference < 0.01").build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow,
            parameters={"converger": {"value": 0.0, "target": 10.0, "rate": 0.2}},
        )

        # Verify convergence
        result = results["converger"]["result"]
        assert abs(result["value"] - result["target"]) < 0.1  # Close to target

    def test_parameter_propagation_through_cycles(self):
        """Test parameter propagation through cycle iterations."""
        workflow = Workflow("param_propagation", "Parameter Propagation Test")

        # Node that modifies multiple parameters
        def process_params(a=1, b=2, c=3):
            """Process multiple parameters."""
            return {"a": a + 1, "b": b * 2, "c": c - 1, "sum": a + b + c}

        processor = PythonCodeNode.from_function(
            func=process_params,
            name="processor",
            input_schema={
                "a": NodeParameter(name="a", type=int, required=False, default=1),
                "b": NodeParameter(name="b", type=int, required=False, default=2),
                "c": NodeParameter(name="c", type=int, required=False, default=3),
            },
        )
        workflow.add_node("processor", processor)

        # Create cycle with multiple parameter mappings
        workflow.create_cycle("param_cycle").connect(
            "processor",
            "processor",
            {"result.a": "a", "result.b": "b", "result.c": "c"},
        ).max_iterations(3).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Verify parameter evolution
        result = results["processor"]["result"]
        assert result["a"] == 4  # 1 + 1 + 1 + 1
        assert result["b"] == 16  # 2 * 2 * 2 * 2
        assert result["c"] == 0  # 3 - 1 - 1 - 1

    def test_nested_cycle_execution(self):
        """Test nested cycle scenarios."""
        workflow = Workflow("nested_cycles", "Nested Cycles Test")

        # Outer loop node
        def outer_process(outer_count=0, inner_result=0):
            """Outer loop processing."""
            return {
                "outer_count": outer_count + 1,
                "inner_input": outer_count * 10,
                "accumulated": inner_result,
            }

        outer_node = PythonCodeNode.from_function(
            func=outer_process,
            name="outer",
            input_schema={
                "outer_count": NodeParameter(
                    name="outer_count", type=int, required=False, default=0
                ),
                "inner_result": NodeParameter(
                    name="inner_result", type=int, required=False, default=0
                ),
            },
        )
        workflow.add_node("outer", outer_node)

        # Inner loop node
        def inner_process(inner_count=0, base_value=0):
            """Inner loop processing."""
            return {"inner_count": inner_count + 1, "result": base_value + inner_count}

        inner_node = PythonCodeNode.from_function(
            func=inner_process,
            name="inner",
            input_schema={
                "inner_count": NodeParameter(
                    name="inner_count", type=int, required=False, default=0
                ),
                "base_value": NodeParameter(
                    name="base_value", type=int, required=False, default=0
                ),
            },
        )
        workflow.add_node("inner", inner_node)

        # Connect outer to inner
        workflow.connect("outer", "inner", mapping={"result.inner_input": "base_value"})

        # Create inner cycle
        workflow.create_cycle("inner_cycle").connect(
            "inner", "inner", {"result.inner_count": "inner_count"}
        ).max_iterations(2).build()

        # Create outer cycle
        workflow.create_cycle("outer_cycle").connect(
            "inner", "outer", {"result.result": "inner_result"}
        ).max_iterations(3).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Verify nested execution
        assert "outer" in results
        assert "inner" in results

    def test_state_accumulation_pattern(self):
        """Test state accumulation across cycle iterations."""
        workflow = Workflow("accumulation", "Accumulation Test")

        # Accumulator node
        def accumulate(total=0, value=1, operation="add"):
            """Accumulate values with different operations."""
            if operation == "add":
                new_total = total + value
            elif operation == "multiply":
                new_total = total * value if total != 0 else value
            elif operation == "max":
                new_total = max(total, value)
            else:
                new_total = total

            return {"total": new_total, "value": value, "operation": operation}

        accumulator = PythonCodeNode.from_function(
            func=accumulate,
            name="accumulator",
            input_schema={
                "total": NodeParameter(
                    name="total", type=float, required=False, default=0
                ),
                "value": NodeParameter(
                    name="value", type=float, required=False, default=1
                ),
                "operation": NodeParameter(
                    name="operation", type=str, required=False, default="add"
                ),
            },
        )
        workflow.add_node("accumulator", accumulator)

        # Create accumulation cycle
        workflow.create_cycle("accumulate_cycle").connect(
            "accumulator",
            "accumulator",
            {
                "result.total": "total",
                "result.value": "value",
                "result.operation": "operation",
            },
        ).max_iterations(5).build()

        # Test addition
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow,
            parameters={"accumulator": {"total": 0, "value": 2, "operation": "add"}},
        )
        # The cycle starts with 0, then adds 2 for max_iterations (5 times)
        # But note that "value" stays constant at 2 throughout
        # 0 -> 2 -> 4 -> 6 -> 8 -> 10
        # Actually checking the function - it adds "value" each time, not 2*iterations
        # So: 0 + 2 + 2 + 2 + 2 + 2 = 10
        assert results["accumulator"]["result"]["total"] == 10

        # Test multiplication
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "accumulator": {"total": 1, "value": 2, "operation": "multiply"}
            },
        )
        assert results["accumulator"]["result"]["total"] == 32  # 1 * 2^5

    def test_cycle_with_conditional_flow(self):
        """Test cycles with simple threshold check."""
        workflow = Workflow("conditional_cycle", "Conditional Cycle Test")

        # Processing node that increments value
        def process_value(value=0, threshold=10):
            """Process value with threshold."""
            new_value = value + 3

            return {
                "value": new_value,
                "threshold": threshold,
                "done": new_value >= threshold,
            }

        processor = PythonCodeNode.from_function(
            func=process_value,
            name="processor",
            input_schema={
                "value": NodeParameter(
                    name="value", type=int, required=False, default=0
                ),
                "threshold": NodeParameter(
                    name="threshold", type=int, required=False, default=10
                ),
            },
        )
        workflow.add_node("processor", processor)

        # Create simple cycle without conditional routing
        workflow.create_cycle("value_cycle").connect(
            "processor",
            "processor",
            {"result.value": "value", "result.threshold": "threshold"},
        ).max_iterations(10).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow, parameters={"processor": {"value": 0, "threshold": 10}}
        )

        # Verify execution - should reach at least threshold
        assert results["processor"]["result"]["value"] >= 10
        assert results["processor"]["result"]["done"] is True

    def test_cycle_iteration_limits(self):
        """Test cycle iteration limit enforcement."""
        workflow = Workflow("iteration_limits", "Iteration Limits Test")

        # Simple incrementor
        def increment(value=0):
            """Increment value."""
            return {"value": value + 1}

        incrementor = PythonCodeNode.from_function(
            func=increment,
            name="incrementor",
            input_schema={
                "value": NodeParameter(
                    name="value", type=int, required=False, default=0
                )
            },
        )
        workflow.add_node("inc", incrementor)

        # Create cycle with specific limit
        workflow.create_cycle("limit_test").connect(
            "inc", "inc", {"result.value": "value"}
        ).max_iterations(7).build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Verify exact iteration count
        assert results["inc"]["result"]["value"] == 7
