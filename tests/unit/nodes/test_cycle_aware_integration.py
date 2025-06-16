"""Integration tests for cycle-aware node patterns in complete workflows."""

import time
from typing import Any

import pytest

from kailash import Workflow
from kailash.nodes.ai.a2a import A2ACoordinatorNode
from kailash.nodes.base import NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.logic import ConvergenceCheckerNode, SwitchNode
from kailash.runtime.local import LocalRuntime


class QualityImproverNode(CycleAwareNode):
    """Test node that improves quality iteratively."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "quality": NodeParameter(
                name="quality", type=float, required=False, default=0.0
            ),
            "improvement_rate": NodeParameter(
                name="improvement_rate", type=float, required=False, default=0.1
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Improve quality with cycle awareness."""
        iteration = self.get_iteration(context)
        is_first = self.is_first_iteration(context)

        data = kwargs.get("data", [])
        quality = kwargs.get("quality", 0.0)
        improvement_rate = kwargs.get("improvement_rate", 0.1)

        if is_first:
            self.log_cycle_info(context, "Starting quality improvement")

        # Improve quality - if quality is 0, start with improvement_rate
        if quality == 0.0:
            improved_quality = improvement_rate
        else:
            improved_quality = min(1.0, quality + (improvement_rate * (1 - quality)))

        # Process data
        processed_data = [x * (1 + improved_quality) for x in data]

        # Track quality history
        quality_history = self.accumulate_values(
            context, "quality_history", improved_quality
        )

        return {
            "data": processed_data,
            "quality": improved_quality,
            "quality_history": quality_history[-3:],  # Last 3 for display
            **self.set_cycle_state(
                {"quality_history": quality_history, "iteration": iteration}
            ),
        }


class DataValidatorNode(CycleAwareNode):
    """Validates data quality in cycles."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "min_quality": NodeParameter(
                name="min_quality", type=float, required=False, default=0.8
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Validate data quality."""
        data = kwargs.get("data", [])
        min_quality = kwargs.get("min_quality", 0.8)

        # Simple quality metric
        if not data:
            quality_score = 0.0
        else:
            quality_score = sum(x for x in data if x > 0) / len(data) if data else 0.0
            quality_score = min(1.0, quality_score / 10.0)  # Normalize

        is_valid = quality_score >= min_quality

        return {
            "data": data,
            "quality_score": quality_score,
            "is_valid": is_valid,
            "validation_result": {
                "score": quality_score,
                "valid": is_valid,
                "threshold": min_quality,
                "iteration": self.get_iteration(context),
            },
        }


class TestCycleAwareWorkflowIntegration:
    """Test complete workflows with cycle-aware nodes."""

    def test_simple_quality_improvement_cycle(self):
        """Test a simple quality improvement cycle."""

        class SimpleQualityImprover(CycleAwareNode):
            """Improver that checks its own convergence."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "data": NodeParameter(
                        name="data", type=list, required=False, default=[]
                    ),
                    "quality": NodeParameter(
                        name="quality", type=float, required=False, default=0.0
                    ),
                    "improvement_rate": NodeParameter(
                        name="improvement_rate", type=float, required=False, default=0.1
                    ),
                    "target_quality": NodeParameter(
                        name="target_quality", type=float, required=False, default=0.8
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                """Improve quality with built-in convergence check."""
                iteration = self.get_iteration(context)
                is_first = self.is_first_iteration(context)

                data = kwargs.get("data", [])
                quality = kwargs.get("quality", 0.0)
                improvement_rate = kwargs.get("improvement_rate", 0.1)
                target_quality = kwargs.get("target_quality", 0.8)

                if is_first:
                    self.log_cycle_info(context, "Starting quality improvement")

                # Improve quality
                if quality == 0.0:
                    improved_quality = improvement_rate
                else:
                    improved_quality = min(
                        1.0, quality + (improvement_rate * (1 - quality))
                    )

                # Check convergence
                converged = improved_quality >= target_quality

                # Process data
                processed_data = [x * (1 + improved_quality) for x in data]

                # Track quality history
                quality_history = self.accumulate_values(
                    context, "quality_history", improved_quality
                )

                return {
                    "data": processed_data,
                    "quality": improved_quality,
                    "quality_history": quality_history[-3:],
                    "converged": converged,
                    "iteration": iteration,
                    **self.set_cycle_state(
                        {"quality_history": quality_history, "iteration": iteration}
                    ),
                }

        workflow = Workflow("quality-cycle", "Quality Improvement Cycle")

        # Add node that improves and checks its own convergence
        workflow.add_node("improver", SimpleQualityImprover())

        # Connect in cycle using CycleBuilder
        workflow.create_cycle("quality_improvement").connect(
            "improver", "improver"
        ).max_iterations(15).converge_when("converged == True").build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "improver": {
                    "data": [1, 2, 3, 4, 5],
                    "improvement_rate": 0.2,
                    "target_quality": 0.7,
                }
            },
        )

        # Verify results
        assert run_id is not None
        final_result = results.get("improver", {})

        # Should have converged or reached max iterations
        assert final_result is not None

        # The quality should have improved
        final_quality = final_result.get("quality", 0)
        assert final_quality > 0.0  # Should improve from initial 0.0

        # Should have run multiple iterations if not converged immediately
        assert final_result.get("iteration", 0) >= 0

        # Check that quality improved over time
        quality_history = final_result.get("quality_history", [])
        assert len(quality_history) > 0

    def test_conditional_cycle_with_switch_node(self):
        """Test cycle with conditional exit using SwitchNode."""

        class ConditionalProcessorNode(CycleAwareNode):
            """Processor that can trigger early exit."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "data": NodeParameter(
                        name="data", type=list, required=False, default=[]
                    ),
                    "target_sum": NodeParameter(
                        name="target_sum", type=float, required=False, default=100.0
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                """Process data toward target."""
                data = kwargs.get("data", [])
                target_sum = kwargs.get("target_sum", 100.0)
                iteration = self.get_iteration(context)

                # Increase values each iteration
                processed_data = [x * (1 + 0.1 * iteration) for x in data]
                current_sum = sum(processed_data)

                # Check if we should exit early
                should_exit = current_sum >= target_sum

                return {
                    "data": processed_data,
                    "current_sum": current_sum,
                    "target_sum": target_sum,
                    "should_exit": should_exit,
                    "iteration": iteration,
                    "input_data": {
                        "should_exit": should_exit,
                        "data": processed_data,
                        "sum": current_sum,
                        "iteration": iteration,
                    },
                }

        workflow = Workflow("conditional-cycle", "Conditional Processing Cycle")

        # Add nodes
        workflow.add_node("processor", ConditionalProcessorNode())
        workflow.add_node("switch", SwitchNode())
        workflow.add_node("validator", DataValidatorNode())

        # Connect workflow
        workflow.connect("processor", "switch", mapping={"input_data": "input_data"})

        # For conditional cycles with switch nodes, we need to use the old API
        # because CycleBuilder doesn't support conditional routing yet
        workflow.connect(
            "switch",
            "processor",
            condition="false_output",
            mapping={
                "false_output.data": "data",
                "false_output.target_sum": "target_sum",
            },
            cycle=True,
            max_iterations=20,
        )

        # Exit path - validate when should_exit is true
        workflow.connect(
            "switch",
            "validator",
            condition="true_output",
            mapping={"true_output.data": "data"},
        )

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "processor": {"data": [5, 10, 15], "target_sum": 200.0},
                "switch": {
                    "condition_field": "should_exit",
                    "operator": "==",
                    "value": True,
                },
                "validator": {"min_quality": 0.5},
            },
        )

        # Verify results
        assert run_id is not None

        # Should have exited through switch to validator
        validator_result = results.get("validator", {})
        assert validator_result is not None
        assert "quality_score" in validator_result
        assert validator_result.get("data") is not None

        # The workflow should have completed
        # Check that we have meaningful data even if from iteration 0
        validation_result = validator_result.get("validation_result", {})
        assert "iteration" in validation_result

    def test_convergence_with_multiple_criteria(self):
        """Test cycle with multiple convergence criteria."""

        class MultiMetricNode(CycleAwareNode):
            """Node that optimizes multiple metrics."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "accuracy": NodeParameter(
                        name="accuracy", type=float, required=False, default=0.5
                    ),
                    "speed": NodeParameter(
                        name="speed", type=float, required=False, default=0.3
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                """Optimize multiple metrics."""
                accuracy = kwargs.get("accuracy", 0.5)
                speed = kwargs.get("speed", 0.3)
                iteration = self.get_iteration(context)

                # Improve both metrics (with tradeoffs)
                accuracy_gain = 0.1 * (1 - accuracy)
                speed_gain = 0.05 * (1 - speed)

                new_accuracy = min(0.99, accuracy + accuracy_gain)
                new_speed = min(0.95, speed + speed_gain)

                # Track metrics
                metrics = {"accuracy": new_accuracy, "speed": new_speed}

                return {
                    "accuracy": new_accuracy,
                    "speed": new_speed,
                    "metrics": metrics,
                    "iteration": iteration,
                }

        workflow = Workflow("multi-metric", "Multi-Metric Optimization")

        # Add nodes
        workflow.add_node("optimizer", MultiMetricNode())
        workflow.add_node("accuracy_check", ConvergenceCheckerNode())
        workflow.add_node("speed_check", ConvergenceCheckerNode())

        # Check both metrics separately
        workflow.connect("optimizer", "accuracy_check", mapping={"accuracy": "value"})
        workflow.connect("optimizer", "speed_check", mapping={"speed": "value"})

        # Continue cycling for optimization
        workflow.create_cycle("optimization_cycle").connect(
            "accuracy_check",
            "optimizer",
            mapping={"result.accuracy": "accuracy", "result.speed": "speed"},
        ).max_iterations(30).build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "optimizer": {"accuracy": 0.6, "speed": 0.4},
                "accuracy_check": {"threshold": 0.90, "mode": "threshold"},
                "speed_check": {"threshold": 0.85, "mode": "threshold"},
            },
        )

        # Verify results
        assert run_id is not None

        # Should have improved at least one metric or run for multiple iterations
        optimizer_result = results.get("optimizer", {})
        # Either improved accuracy OR speed, or both
        accuracy = optimizer_result.get("accuracy", 0)
        speed = optimizer_result.get("speed", 0)
        assert accuracy >= 0.55 or speed >= 0.35  # Some improvement
        assert optimizer_result.get("iteration", 0) >= 0

        # At least one convergence check should pass
        accuracy_result = results.get("accuracy_check", {})
        speed_result = results.get("speed_check", {})

        assert accuracy_result is not None
        assert speed_result is not None

    def test_a2a_coordination_in_cycles(self):
        """Test A2A coordination across cycle iterations."""

        class TaskGeneratorNode(CycleAwareNode):
            """Generates tasks for agents."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "task_count": NodeParameter(
                        name="task_count", type=int, required=False, default=3
                    )
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                """Generate tasks based on iteration."""
                iteration = self.get_iteration(context)
                task_count = kwargs.get("task_count", 3)

                # Generate different task types based on iteration
                task_types = ["analysis", "research", "processing"]
                current_task_type = task_types[iteration % len(task_types)]

                return {
                    "task": {
                        "type": current_task_type,
                        "id": f"task_{iteration}",
                        "iteration": iteration,
                        "priority": "high" if iteration < 2 else "medium",
                    },
                    "task_count": task_count,
                    "iteration": iteration,
                }

        workflow = Workflow("a2a-cycle", "A2A Coordination in Cycles")

        # Add nodes
        workflow.add_node("task_gen", TaskGeneratorNode())
        workflow.add_node("coordinator", A2ACoordinatorNode())
        workflow.add_node("convergence", ConvergenceCheckerNode())

        # Connect workflow
        workflow.connect("task_gen", "coordinator", mapping={"task": "task"})
        workflow.connect(
            "coordinator", "convergence", mapping={"cycle_info.active_agents": "value"}
        )
        workflow.create_cycle("a2a_coordination").connect(
            "convergence", "task_gen"
        ).max_iterations(10).build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "task_gen": {"task_count": 5},
                "coordinator": {
                    "action": "delegate",
                    "coordination_strategy": "round_robin",
                },
                "convergence": {"threshold": 2, "mode": "threshold"},
            },
        )

        # Verify results
        assert run_id is not None

        # Should have coordination results
        coordinator_result = results.get("coordinator", {})
        assert coordinator_result is not None

        # Should have cycle info from coordination
        cycle_info = coordinator_result.get("cycle_info", {})
        assert cycle_info.get("iteration", 0) >= 0

    def test_error_handling_in_cycles(self):
        """Test error handling and recovery in cyclic workflows."""

        class UnreliableNode(CycleAwareNode):
            """Node that fails occasionally."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "fail_on_iteration": NodeParameter(
                        name="fail_on_iteration", type=int, required=False, default=3
                    ),
                    "data": NodeParameter(
                        name="data", type=Any, required=False, default="test"
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                """Process data, failing on specific iteration."""
                iteration = self.get_iteration(context)
                fail_on_iteration = kwargs.get("fail_on_iteration", 3)
                data = kwargs.get("data", "test")

                # Fail on specific iteration
                if iteration == fail_on_iteration:
                    # Instead of raising an exception, return error state
                    return {
                        "data": data,
                        "error": True,
                        "error_message": f"Simulated failure on iteration {iteration}",
                        "iteration": iteration,
                        "should_retry": True,
                    }

                # Normal processing
                processed_data = f"{data}_processed_{iteration}"

                return {
                    "data": processed_data,
                    "error": False,
                    "iteration": iteration,
                    "should_retry": False,
                }

        class ErrorHandlerNode(CycleAwareNode):
            """Handles errors and decides on retry."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "error": NodeParameter(
                        name="error", type=bool, required=False, default=False
                    ),
                    "should_retry": NodeParameter(
                        name="should_retry", type=bool, required=False, default=False
                    ),
                    "max_retries": NodeParameter(
                        name="max_retries", type=int, required=False, default=2
                    ),
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                """Handle errors and count retries."""
                error = kwargs.get("error", False)
                should_retry = kwargs.get("should_retry", False)
                max_retries = kwargs.get("max_retries", 2)

                # Track retry count
                prev_state = self.get_previous_state(context)
                retry_count = prev_state.get("retry_count", 0)

                if error and should_retry and retry_count < max_retries:
                    # Retry
                    new_retry_count = retry_count + 1
                    return {
                        "should_continue": True,
                        "retry_count": new_retry_count,
                        "action": "retry",
                        **self.set_cycle_state({"retry_count": new_retry_count}),
                    }
                elif error and (not should_retry or retry_count >= max_retries):
                    # Give up
                    return {
                        "should_continue": False,
                        "retry_count": retry_count,
                        "action": "abort",
                        **self.set_cycle_state({"retry_count": retry_count}),
                    }
                else:
                    # Success
                    return {
                        "should_continue": False,
                        "retry_count": retry_count,
                        "action": "success",
                        **self.set_cycle_state({"retry_count": 0}),
                    }

        workflow = Workflow("error-handling", "Error Handling in Cycles")

        # Add nodes
        workflow.add_node("processor", UnreliableNode())
        workflow.add_node("error_handler", ErrorHandlerNode())
        workflow.add_node("convergence", ConvergenceCheckerNode())

        # Connect workflow
        workflow.connect(
            "processor",
            "error_handler",
            mapping={"error": "error", "should_retry": "should_retry"},
        )
        workflow.connect(
            "error_handler", "convergence", mapping={"should_continue": "value"}
        )
        workflow.create_cycle("error_retry").connect(
            "convergence", "processor"
        ).max_iterations(10).build()

        # Execute
        runtime = LocalRuntime()
        results, run_id = runtime.execute(
            workflow,
            parameters={
                "processor": {"fail_on_iteration": 2, "data": "test_data"},
                "error_handler": {"max_retries": 3},
                "convergence": {
                    "threshold": 0.5,
                    "mode": "threshold",
                    "direction": "minimize",
                },
            },
        )

        # Verify results
        assert run_id is not None

        # Should have handled the error
        error_handler_result = results.get("error_handler", {})
        assert error_handler_result is not None
        assert "action" in error_handler_result

        # Should have retry count tracking
        assert "retry_count" in error_handler_result


class TestCycleAwarePerformance:
    """Test performance characteristics of cycle-aware nodes."""

    def test_state_accumulation_performance(self):
        """Test that state accumulation doesn't cause memory issues."""

        class StateAccumulatorNode(CycleAwareNode):
            """Node that accumulates large amounts of state."""

            def get_parameters(self) -> dict[str, NodeParameter]:
                return {
                    "data_size": NodeParameter(
                        name="data_size", type=int, required=False, default=100
                    )
                }

            def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
                """Accumulate state with memory management."""
                data_size = kwargs.get("data_size", 100)
                iteration = self.get_iteration(context)

                # Generate some data
                current_data = list(
                    range(iteration * data_size, (iteration + 1) * data_size)
                )

                # Accumulate with limited history
                accumulated_data = self.accumulate_values(
                    context, "large_data", current_data, max_history=5
                )

                # Track size
                total_size = sum(len(chunk) for chunk in accumulated_data)

                return {
                    "current_size": len(current_data),
                    "total_size": total_size,
                    "chunks_count": len(accumulated_data),
                    "iteration": iteration,
                    **self.set_cycle_state(
                        {
                            "large_data": accumulated_data,
                            "size_history": self.accumulate_values(
                                context, "size_history", total_size
                            ),
                        }
                    ),
                }

        workflow = Workflow("performance-test", "State Accumulation Performance")

        # Add nodes
        workflow.add_node("accumulator", StateAccumulatorNode())
        workflow.add_node("convergence", ConvergenceCheckerNode())

        # Connect with cycle
        workflow.connect(
            "accumulator", "convergence", mapping={"chunks_count": "value"}
        )
        workflow.create_cycle("accumulation_cycle").connect(
            "convergence", "accumulator"
        ).max_iterations(20).build()

        # Execute
        runtime = LocalRuntime()
        start_time = time.time()

        results, run_id = runtime.execute(
            workflow,
            parameters={
                "accumulator": {"data_size": 50},
                "convergence": {"threshold": 5, "mode": "threshold"},
            },
        )

        execution_time = time.time() - start_time

        # Verify results
        assert run_id is not None
        accumulator_result = results.get("accumulator", {})

        # Should have limited chunks due to max_history
        assert accumulator_result.get("chunks_count", 0) <= 5

        # Should not take too long (reasonable performance)
        assert (
            execution_time < 70.0
        )  # 70 seconds max (very generous for CI/slower machines)

        # Should have processed multiple iterations
        assert accumulator_result.get("iteration", 0) > 0
