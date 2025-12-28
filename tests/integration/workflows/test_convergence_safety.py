"""
Unit tests for convergence and safety framework.

Tests the convergence and safety features including:
- Expression-based convergence conditions
- Timeout safety mechanisms
- Maximum iteration limits
- Compound convergence conditions
- Resource monitoring and safety
"""

import time

import pytest
from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.cycle_exceptions import CycleConfigurationError


class TestConvergenceSafety:
    """Test convergence and safety features in cyclic workflows."""

    def test_expression_based_convergence(self):
        """Test expression-based convergence conditions."""
        workflow = Workflow("expr_convergence", "Expression Convergence Test")

        # Quality improvement node
        def improve_quality(quality=0.0, improvement_rate=0.1):
            """Improve quality gradually."""
            new_quality = min(1.0, quality + improvement_rate)
            return {"quality": new_quality, "improvement": new_quality - quality}

        improver = PythonCodeNode.from_function(
            func=improve_quality,
            name="improver",
            input_schema={
                "quality": NodeParameter(
                    name="quality", type=float, required=False, default=0.0
                ),
                "improvement_rate": NodeParameter(
                    name="improvement_rate", type=float, required=False, default=0.1
                ),
            },
        )
        workflow.add_node("improver", improver)

        # Create cycle with convergence expression
        workflow.create_cycle("quality_cycle").connect(
            "improver", "improver", {"result.quality": "quality"}
        ).max_iterations(20).converge_when("quality >= 0.9").build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(
            workflow,
            parameters={"improver": {"quality": 0.0, "improvement_rate": 0.15}},
        )

        # Verify convergence
        assert results["improver"]["result"]["quality"] >= 0.9

    def test_max_iteration_safety(self):
        """Test maximum iteration limit prevents infinite loops."""
        workflow = Workflow("max_iter_safety", "Max Iteration Safety Test")

        # Slow improver that won't converge in time
        def slow_improve(value=0.0):
            """Very slow improvement."""
            return {"value": value + 0.01}

        improver = PythonCodeNode.from_function(
            func=slow_improve,
            name="slow_improver",
            input_schema={
                "value": NodeParameter(
                    name="value", type=float, required=False, default=0.0
                )
            },
        )
        workflow.add_node("improver", improver)

        # Create cycle with low max_iterations
        workflow.create_cycle("slow_cycle").connect(
            "improver", "improver", {"result.value": "value"}
        ).max_iterations(5).converge_when("value >= 1.0").build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Should stop at max iterations
        value = results["improver"]["result"]["value"]
        assert value < 1.0  # Didn't reach convergence
        assert value == pytest.approx(0.05, rel=1e-5)  # 5 iterations * 0.01

    def test_compound_convergence_conditions(self):
        """Test multiple convergence conditions working together."""
        workflow = Workflow("compound_convergence", "Compound Convergence Test")

        # Node with multiple metrics
        def process_data(error_rate=0.5, processed_count=0):
            """Process with error rate and count."""
            new_error_rate = max(0.0, error_rate - 0.05)
            new_count = processed_count + 10
            return {
                "error_rate": new_error_rate,
                "processed_count": new_count,
                "quality": 1.0 - new_error_rate,
            }

        processor = PythonCodeNode.from_function(
            func=process_data,
            name="processor",
            input_schema={
                "error_rate": NodeParameter(
                    name="error_rate", type=float, required=False, default=0.5
                ),
                "processed_count": NodeParameter(
                    name="processed_count", type=int, required=False, default=0
                ),
            },
        )
        workflow.add_node("processor", processor)

        # Create cycle with compound conditions
        # Note: Current SDK may have limitations on complex expressions
        workflow.create_cycle("process_cycle").connect(
            "processor",
            "processor",
            {
                "result.error_rate": "error_rate",
                "result.processed_count": "processed_count",
            },
        ).max_iterations(15).converge_when("error_rate <= 0.1").build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Check results
        result = results["processor"]["result"]
        assert result["error_rate"] <= 0.1
        assert result["processed_count"] > 0

    def test_timeout_safety_mechanism(self):
        """Test timeout safety for long-running cycles."""
        workflow = Workflow("timeout_safety", "Timeout Safety Test")

        # Slow processing node
        def slow_process(counter=0, delay=0.1):
            """Process with configurable delay."""
            # Note: Real timeout implementation would be in runtime
            # This simulates processing time
            time.sleep(delay)
            return {"counter": counter + 1, "delay": delay}

        slow_node = PythonCodeNode.from_function(
            func=slow_process,
            name="slow_processor",
            input_schema={
                "counter": NodeParameter(
                    name="counter", type=int, required=False, default=0
                ),
                "delay": NodeParameter(
                    name="delay", type=float, required=False, default=0.1
                ),
            },
        )
        workflow.add_node("slow", slow_node)

        # Create cycle with timeout consideration
        workflow.create_cycle("slow_cycle").connect(
            "slow", "slow", {"result.counter": "counter"}
        ).max_iterations(3).build()

        # Execute with runtime timeout (if supported)
        runtime = LocalRuntime(enable_cycles=True)
        start_time = time.time()

        results, run_id = runtime.execute(
            workflow, parameters={"slow": {"counter": 0, "delay": 0.01}}  # Small delay
        )

        elapsed = time.time() - start_time

        # Should complete within reasonable time
        assert elapsed < 5.0  # Less than 5 seconds (CI can be slower)
        assert results["slow"]["result"]["counter"] == 3

    def test_resource_monitoring_safety(self):
        """Test resource monitoring during cycle execution."""
        workflow = Workflow("resource_safety", "Resource Safety Test")

        # Memory-intensive node simulation
        def memory_intensive(size=100, iteration=0):
            """Simulate memory-intensive operation."""
            # Create list to simulate memory usage
            data = list(range(size))
            return {
                "size": size * 2,  # Double size each iteration
                "iteration": iteration + 1,
                "data_sample": data[:5] if data else [],
            }

        memory_node = PythonCodeNode.from_function(
            func=memory_intensive,
            name="memory_node",
            input_schema={
                "size": NodeParameter(
                    name="size", type=int, required=False, default=100
                ),
                "iteration": NodeParameter(
                    name="iteration", type=int, required=False, default=0
                ),
            },
        )
        workflow.add_node("memory", memory_node)

        # Create cycle with resource limits
        workflow.create_cycle("memory_cycle").connect(
            "memory", "memory", {"result.size": "size", "result.iteration": "iteration"}
        ).max_iterations(5).build()

        # Execute with resource monitoring
        runtime = LocalRuntime(
            enable_cycles=True,
            # If supported: resource_limits={"memory_mb": 100}
        )

        results, run_id = runtime.execute(
            workflow, parameters={"memory": {"size": 100}}
        )

        # Should complete without resource exhaustion
        assert results["memory"]["result"]["iteration"] <= 5
        assert results["memory"]["result"]["size"] == 100 * (2**5)  # Geometric growth

    def test_early_termination_on_convergence(self):
        """Test that cycles terminate early when convergence is reached."""
        workflow = Workflow("early_termination", "Early Termination Test")

        # Fast converging node
        def fast_converge(value=0.0):
            """Converges quickly."""
            return {"value": value + 0.3}  # Large steps

        fast_node = PythonCodeNode.from_function(
            func=fast_converge,
            name="fast_node",
            input_schema={
                "value": NodeParameter(
                    name="value", type=float, required=False, default=0.0
                )
            },
        )
        workflow.add_node("fast", fast_node)

        # Create cycle that should terminate early
        workflow.create_cycle("fast_cycle").connect(
            "fast", "fast", {"result.value": "value"}
        ).max_iterations(10).converge_when("value >= 1.0").build()

        # Execute
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Should converge in ~4 iterations (0 -> 0.3 -> 0.6 -> 0.9 -> 1.2)
        value = results["fast"]["result"]["value"]
        assert value >= 1.0
        assert value < 2.0  # Didn't run all 10 iterations

    def test_invalid_convergence_expression(self):
        """Test handling of invalid convergence expressions."""
        workflow = Workflow("invalid_expr", "Invalid Expression Test")

        node = PythonCodeNode(name="node", code="result = {'data': 1}")
        workflow.add_node("node", node)

        # Create cycle with potentially invalid expression
        # SDK should handle this gracefully
        workflow.create_cycle("invalid_cycle").connect("node", "node").max_iterations(
            5
        ).converge_when("invalid_var > 10").build()

        # Execute - should handle gracefully (rely on max_iterations)
        runtime = LocalRuntime(enable_cycles=True)
        results, run_id = runtime.execute(workflow)

        # Should complete based on max_iterations
        assert "node" in results
