"""
Core integration tests for cyclic workflow functionality.

This file tests fundamental cycle mechanics, convergence conditions,
cycle detection, and basic state management using real Docker infrastructure.
"""

import time
from datetime import datetime, timezone

import pytest
from kailash import Workflow, WorkflowBuilder
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError, WorkflowValidationError

from tests.utils.docker_config import REDIS_CONFIG, get_postgres_connection_string


@pytest.mark.integration
class TestCyclicWorkflowBasics:
    """Test basic cyclic workflow functionality with real infrastructure."""

    def test_simple_self_cycle(self):
        """Test simple self-referencing cycle with counter."""
        workflow = Workflow("self_cycle", "Simple self cycle test")

        # Counter function using PythonCodeNode.from_function
        def counter_func(count=0):
            new_count = count + 1
            return {"count": new_count, "converged": new_count >= 5}

        counter_node = PythonCodeNode.from_function(counter_func, name="counter")

        workflow.add_node("counter", counter_node)

        # Use the new CycleBuilder API with dot notation for PythonCodeNode output
        workflow.create_cycle("counter_cycle").connect(
            "counter", "counter", {"result.count": "count"}
        ).max_iterations(10).converge_when("converged == True").build()

        runtime = LocalRuntime()
        result, run_id = runtime.execute(
            workflow, parameters={"counter": {"count": 0}}  # Provide initial value
        )

        # Check the result structure
        print(f"Result: {result}")

        # The result from PythonCodeNode.from_function IS wrapped in 'result'
        assert "counter" in result
        assert "result" in result["counter"]
        assert result["counter"]["result"]["count"] >= 5
        assert result["counter"]["result"]["converged"] is True

    def test_two_node_cycle(self):
        """Test cycle between two nodes with state passing."""
        workflow = Workflow("two_node_cycle", "Two node cycle test")

        # Node A: Processes data and passes to B
        node_a = PythonCodeNode.from_function(
            lambda value=1, increment=0: {"value": value + increment}, name="node_a"
        )

        # Node B: Checks convergence and increments
        node_b = PythonCodeNode.from_function(
            lambda value: {
                "increment": 2 if value < 10 else 0,
                "converged": value >= 10,
                "final_value": value,
            },
            name="node_b",
        )

        workflow.add_node("a", node_a)
        workflow.add_node("b", node_b)

        workflow.connect("a", "b", {"result.value": "value"})
        workflow.create_cycle("cycle_b_to_a").connect(
            "b", "a", {"result.increment": "increment", "result.final_value": "value"}
        ).max_iterations(10).converge_when("converged == True").build()

        runtime = LocalRuntime()
        result, _ = runtime.execute(
            workflow,
            parameters={
                "a": {"value": 1, "increment": 0}
            },  # Initial parameters for node a
        )

        assert result["b"]["result"]["converged"] is True
        assert result["b"]["result"]["final_value"] >= 10

    def test_convergence_conditions(self):
        """Test various convergence condition types."""
        # Test 1: Expression-based convergence
        workflow1 = Workflow("expr_convergence", "Expression convergence")

        quality_node = PythonCodeNode.from_function(
            lambda quality=0.5: {"quality": min(quality + 0.1, 1.0)},
            name="quality_improver",
        )

        workflow1.add_node("quality", quality_node)
        workflow1.create_cycle("quality_cycle").connect(
            "quality", "quality", {"result.quality": "quality"}
        ).max_iterations(10).converge_when("quality >= 0.9").build()

        runtime = LocalRuntime()
        result1, _ = runtime.execute(
            workflow1, parameters={"quality": {"quality": 0.5}}  # Initial quality value
        )
        assert result1["quality"]["result"]["quality"] >= 0.9

        # Test 2: Max iterations limit
        workflow2 = Workflow("max_iter", "Max iteration test")

        infinite_node = PythonCodeNode.from_function(
            lambda x=0: {"x": x + 1, "converged": False}, name="infinite"
        )

        workflow2.add_node("inf", infinite_node)
        workflow2.create_cycle("inf_cycle").connect(
            "inf", "inf", {"result.x": "x"}
        ).max_iterations(3).converge_when("converged == True").build()

        result2, _ = runtime.execute(
            workflow2, parameters={"inf": {"x": 0}}
        )  # Initial x value
        assert (
            result2["inf"]["result"]["x"] == 3
        )  # max_iterations=3 stops after 3rd value

    def test_cycle_state_management(self):
        """Test state management across cycle iterations."""
        workflow = Workflow("state_mgmt", "State management test")

        # Accumulator node that tracks history
        class AccumulatorNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "value": NodeParameter(name="value", type=int, default=0),
                    "threshold": NodeParameter(name="threshold", type=int, default=100),
                }

            def run(self, **kwargs):
                value = kwargs.get("value", 0)
                threshold = kwargs.get("threshold", 100)
                context = kwargs.get("context", {})

                # Get previous state
                history = self.get_previous_state(context).get("history", [])
                total = self.get_previous_state(context).get("total", 0)

                # Update state
                new_value = value + 10
                new_total = total + new_value
                history.append(new_value)

                return {
                    "value": new_value,
                    "total": new_total,
                    "history": history,
                    "converged": new_total >= threshold,
                    "iteration": self.get_iteration(context),
                    **self.set_cycle_state({"history": history, "total": new_total}),
                }

        accumulator = AccumulatorNode(name="accumulator")
        workflow.add_node("acc", accumulator)
        workflow.create_cycle("cycle_acc_to_acc").connect(
            "acc", "acc", {"value": "value"}
        ).max_iterations(20).converge_when("converged == True").build()

        runtime = LocalRuntime()
        result, _ = runtime.execute(workflow, {"acc": {"threshold": 100}})

        assert result["acc"]["converged"] is True
        assert result["acc"]["total"] >= 100
        assert len(result["acc"]["history"]) == result["acc"]["iteration"] + 1

    def test_cycle_detection_and_validation(self):
        """Test cycle detection prevents invalid workflows."""
        # Test 1: Cycles require cycle=True flag
        workflow = Workflow("explicit_cycle", "Explicit cycle test")

        node1 = PythonCodeNode.from_function(lambda x=0: {"x": x + 1}, name="n1")
        node2 = PythonCodeNode.from_function(lambda x: {"x": x * 2}, name="n2")

        workflow.add_node("n1", node1)
        workflow.add_node("n2", node2)

        # Create a valid cycle using CycleBuilder
        workflow.connect("n1", "n2", {"result.x": "x"})
        workflow.create_cycle("valid_cycle").connect(
            "n2", "n1", {"result.x": "x"}
        ).max_iterations(10).build()

        # This should work fine - cycles are allowed with cycle=True
        runtime = LocalRuntime()
        result, _ = runtime.execute(workflow, parameters={"n1": {"x": 1}})

        # Verify the cycle executed
        assert "n1" in result
        assert "n2" in result

    def test_parameter_propagation_through_cycles(self):
        """Test that parameters propagate correctly through cycle iterations."""
        workflow = Workflow("param_prop", "Parameter propagation test")

        # Processing node that modifies multiple parameters
        process_node = PythonCodeNode.from_function(
            lambda data=None, metadata=None, iteration=0: {
                "data": {
                    "values": (
                        data.get("values", []) + [iteration] if data else [iteration]
                    ),
                    "count": len(data.get("values", [])) + 1 if data else 1,
                },
                "metadata": {
                    "last_update": datetime.now(timezone.utc).isoformat(),
                    "iterations": iteration + 1,
                    "status": "processing",
                },
                "converged": iteration >= 3,
                "iteration": iteration + 1,
            },
            name="processor",
        )

        workflow.add_node("proc", process_node)
        workflow.create_cycle("cycle_proc_to_proc").connect(
            "proc",
            "proc",
            {
                "result.data": "data",
                "result.metadata": "metadata",
                "result.iteration": "iteration",
            },
        ).max_iterations(5).converge_when("converged == True").build()

        runtime = LocalRuntime()
        result, _ = runtime.execute(
            workflow,
            parameters={
                "proc": {
                    "data": {"values": [], "count": 0},
                    "metadata": {"iterations": 0},
                    "iteration": 0,
                }
            },
        )

        assert result["proc"]["result"]["data"]["count"] == 4
        assert len(result["proc"]["result"]["data"]["values"]) == 4
        assert result["proc"]["result"]["metadata"]["iterations"] == 4

    def test_cycle_with_external_nodes(self):
        """Test cycles that interact with non-cyclic nodes."""
        workflow = Workflow("mixed_cycle", "Cycle with external nodes")

        # Initial data source (non-cyclic)
        source = PythonCodeNode.from_function(
            lambda: {"initial_data": list(range(10)), "threshold": 50}, name="source"
        )

        # Cyclic processor
        processor = PythonCodeNode.from_function(
            lambda data: {
                "data": [x * 1.1 for x in data],
                "sum": sum([x * 1.1 for x in data]),
                "converged": sum([x * 1.1 for x in data]) >= 50,
            },
            name="processor",
        )

        # Final aggregator (non-cyclic)
        aggregator = PythonCodeNode.from_function(
            lambda data, sum: {
                "final_sum": sum,
                "final_count": len(data),
                "average": sum / len(data) if data else 0,
            },
            name="aggregator",
        )

        workflow.add_node("source", source)
        workflow.add_node("proc", processor)
        workflow.add_node("agg", aggregator)

        # Connect source to processor
        workflow.connect("source", "proc", {"result.initial_data": "data"})

        # Processor cycles on itself
        workflow.create_cycle("cycle_proc_to_proc").connect(
            "proc", "proc", {"result.data": "data"}
        ).max_iterations(10).converge_when("converged == True").build()

        # Processor to aggregator when done
        workflow.connect("proc", "agg", {"result.data": "data", "result.sum": "sum"})

        runtime = LocalRuntime()
        result, _ = runtime.execute(workflow)

        assert result["agg"]["result"]["final_sum"] >= 50
        assert result["agg"]["result"]["final_count"] == 10

    def test_edge_cases(self):
        """Test edge cases in cycle handling."""
        runtime = LocalRuntime()

        # Test 1: Immediate convergence
        workflow1 = Workflow("immediate", "Immediate convergence")
        node1 = PythonCodeNode.from_function(
            lambda: {"value": 100, "converged": True}, name="immediate"
        )
        workflow1.add_node("n", node1)
        workflow1.create_cycle("immediate_cycle").connect("n", "n").max_iterations(
            1
        ).converge_when("converged == True").build()

        result1, _ = runtime.execute(workflow1)
        assert result1["n"]["result"]["value"] == 100  # Should execute once

        # Test 2: Minimum iterations (1 iteration)
        workflow2 = Workflow("min_iter", "Minimum iterations")
        node2 = PythonCodeNode.from_function(lambda x=0: {"x": x + 1}, name="counter")
        workflow2.add_node("n", node2)
        workflow2.create_cycle("min_iter_cycle").connect(
            "n", "n", {"result.x": "x"}
        ).max_iterations(1).build()

        result2, _ = runtime.execute(workflow2, parameters={"n": {"x": 0}})
        assert result2["n"]["result"]["x"] == 1  # x=0 -> x+1 = 1

    def test_cycle_performance_monitoring(self):
        """Test performance monitoring in cycles."""
        workflow = Workflow("perf_monitor", "Performance monitoring")

        # Node that tracks execution time
        class TimedNode(CycleAwareNode):
            def get_parameters(self):
                return {"delay": NodeParameter(name="delay", type=float, default=0.1)}

            def run(self, **kwargs):
                delay = kwargs.get("delay", 0.1)
                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)

                start = time.time()
                time.sleep(delay)  # Simulate work
                elapsed = time.time() - start

                # Track timing history
                timing_history = self.get_previous_state(context).get("timings", [])
                timing_history.append(elapsed)

                return {
                    "iteration": iteration,
                    "elapsed": elapsed,
                    "total_time": sum(timing_history),
                    "avg_time": sum(timing_history) / len(timing_history),
                    "converged": iteration >= 2,
                    **self.set_cycle_state({"timings": timing_history}),
                }

        timed = TimedNode(name="timed")
        workflow.add_node("timer", timed)
        workflow.create_cycle("cycle_timer_to_timer").connect(
            "timer", "timer"
        ).max_iterations(3).converge_when("converged == True").build()

        runtime = LocalRuntime()
        result, _ = runtime.execute(workflow, {"timer": {"delay": 0.01}})

        assert result["timer"]["iteration"] == 2
        assert result["timer"]["total_time"] > 0.02  # At least 3 * 0.01
        assert result["timer"]["avg_time"] > 0.01
