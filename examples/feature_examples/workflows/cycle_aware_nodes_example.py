#!/usr/bin/env python3
"""
Cycle-Aware Node Enhancement Examples
=====================================

This example demonstrates the new cycle-aware node enhancements including:
1. CycleAwareNode base class with built-in helpers
2. ConvergenceCheckerNode for declarative convergence
3. Enhanced A2A Coordinator with cycle-aware agent selection
4. Integration with SwitchNode for conditional routing

Design Philosophy:
    These examples showcase how the cycle-aware node enhancements simplify
    the creation of iterative workflows. By providing built-in helpers and
    declarative convergence checking, developers can focus on business logic
    rather than cycle management boilerplate.

Run: python workflow_cycle_aware_nodes.py
"""

import time
from typing import Any

from kailash import Workflow
from kailash.nodes import CycleAwareNode, NodeParameter
from kailash.nodes.ai.a2a import A2ACoordinatorNode, SharedMemoryPoolNode
from kailash.nodes.logic import (
    ConvergenceCheckerNode,
    MultiCriteriaConvergenceNode,
    SwitchNode,
)
from kailash.runtime.local import LocalRuntime

# ============================================================================
# Example 1: Basic CycleAwareNode Usage
# ============================================================================


class QualityImproverNode(CycleAwareNode):
    """
    Example node demonstrating CycleAwareNode helpers.

    This node shows how to use the built-in cycle-aware methods to
    track quality improvement across iterations without boilerplate.
    """

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
        """
        Process data with cycle awareness.

        Demonstrates use of CycleAwareNode helpers for iteration tracking,
        state management, and value accumulation across cycles.

        Args:
            context: Execution context with cycle information
            **kwargs: Node parameters including data, quality, improvement_rate

        Returns:
            Dict with improved quality and cycle state
        """
        # Use built-in helpers - no boilerplate!
        iteration = self.get_iteration(context)
        is_first = self.is_first_iteration(context)
        self.get_previous_state(context)

        # Get parameters
        data = kwargs.get("data", [])
        quality = kwargs.get("quality", 0.0)
        improvement_rate = kwargs.get("improvement_rate", 0.1)

        # Log progress (built-in helper)
        if is_first:
            self.log_cycle_info(context, "Starting quality improvement process")

        # Improve quality based on iteration
        improved_quality = min(1.0, quality + (improvement_rate * (1 - quality)))

        # Accumulate quality history (built-in helper)
        quality_history = self.accumulate_values(
            context, "quality_history", improved_quality, max_history=20
        )

        # Process data
        processed_data = [x * (1 + improved_quality) for x in data]

        # Log progress every 5 iterations
        if iteration % 5 == 0:
            avg_quality = (
                sum(quality_history) / len(quality_history) if quality_history else 0
            )
            self.log_cycle_info(context, f"Average quality: {avg_quality:.3f}")

        return {
            "data": processed_data,
            "quality": improved_quality,
            "quality_history": quality_history[-5:],  # Return last 5 for display
            **self.set_cycle_state(
                {
                    "quality_history": quality_history,
                    "best_quality": (
                        max(quality_history) if quality_history else improved_quality
                    ),
                }
            ),
        }


def example1_basic_cycle_aware():
    """
    Demonstrates basic CycleAwareNode usage.

    Design Pattern:
        QualityImprover → ConvergenceChecker ↻
        ↓ (when converged)
        [Output]

    Flow:
    1. QualityImprover starts with initial data and quality=0
    2. Each iteration improves quality by improvement_rate
    3. ConvergenceChecker monitors quality value
    4. When quality >= threshold (0.85), cycle exits
    5. Final improved data flows to output

    This pattern shows how CycleAwareNode helpers eliminate boilerplate
    for iteration tracking, state management, and value accumulation.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 1: Basic CycleAwareNode Usage")
    print("=" * 60)

    workflow = Workflow("cycle-aware-basic", "Basic CycleAwareNode Example")

    # Add nodes
    workflow.add_node("improver", QualityImproverNode())
    workflow.add_node("convergence", ConvergenceCheckerNode())

    # Connect with cycle
    workflow.connect("improver", "convergence", mapping={"quality": "value"})
    workflow.connect(
        "convergence",
        "improver",
        mapping={"quality": "quality"},
        cycle=True,
        max_iterations=15,
        convergence_check="converged == True",
    )

    # Execute
    runtime = LocalRuntime()
    results, _ = runtime.execute(
        workflow,
        parameters={
            "improver": {"data": [1, 2, 3, 4, 5], "improvement_rate": 0.15},
            "convergence": {"threshold": 0.85, "mode": "threshold"},
        },
    )

    # Display results
    final_result = results.get("convergence", {})
    print(f"\n✅ Converged: {final_result.get('converged', False)}")
    print(f"Final quality: {final_result.get('value', 0):.3f}")
    print(f"Iterations: {final_result.get('iteration', 0)}")
    print(f"Reason: {final_result.get('reason', 'Unknown')}")


# ============================================================================
# Example 2: Advanced Convergence Patterns
# ============================================================================


class DataOptimizerNode(CycleAwareNode):
    """Optimizes data with multiple convergence criteria."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "optimization_target": NodeParameter(
                name="optimization_target", type=float, default=100.0
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Optimize data towards target."""
        self.get_iteration(context)
        prev_state = self.get_previous_state(context)

        data = kwargs.get("data", [])
        target = kwargs.get("optimization_target", 100.0)

        # Get previous results
        prev_error = prev_state.get("error", float("inf"))
        learning_rate = prev_state.get("learning_rate", 0.5)

        # Calculate current state
        current_sum = sum(data)
        error = abs(target - current_sum)
        error_reduction = (
            (prev_error - error) / prev_error if prev_error != float("inf") else 1.0
        )

        # Adaptive learning rate
        if error_reduction < 0.01:  # Slow progress
            learning_rate *= 0.9  # Reduce learning rate

        # Optimize data
        scale_factor = (
            1 + (learning_rate * (target - current_sum) / current_sum)
            if current_sum > 0
            else 1
        )
        optimized_data = [x * scale_factor for x in data]

        # Track metrics
        error_history = self.accumulate_values(context, "error_history", error)

        # Detect convergence trend
        is_converging = self.detect_convergence_trend(
            context, "error_history", threshold=0.1, window=5
        )

        return {
            "data": optimized_data,
            "metrics": {
                "error": error,
                "sum": sum(optimized_data),
                "target": target,
                "learning_rate": learning_rate,
                "error_reduction": error_reduction,
                "is_converging": is_converging,
            },
            **self.set_cycle_state(
                {
                    "error_history": error_history,
                    "error": error,
                    "learning_rate": learning_rate,
                }
            ),
        }


def example2_advanced_convergence():
    """
    Demonstrates advanced convergence patterns.

    Design Pattern:
        DataOptimizer → ConvergenceChecker ↻
        ↓ (when converged)
        [Output]

    Flow:
    1. DataOptimizer adjusts data values toward optimization_target
    2. Tracks error (distance from target) across iterations
    3. Uses adaptive learning rate based on progress
    4. ConvergenceChecker supports multiple modes:
        - Threshold: error < threshold
        - Stability: variance in recent values < min_variance
        - Improvement: rate of change < min_improvement
    5. Different convergence criteria lead to different optimization behaviors

    This demonstrates how ConvergenceCheckerNode replaces custom
    convergence logic with declarative configuration.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Advanced Convergence Patterns")
    print("=" * 60)

    workflow = Workflow("advanced-convergence", "Multi-criteria Convergence Example")

    # Add nodes
    workflow.add_node("optimizer", DataOptimizerNode())
    workflow.add_node("convergence", ConvergenceCheckerNode())

    # Connect with multiple convergence criteria
    workflow.connect(
        "optimizer", "convergence", mapping={"metrics.error": "value", "data": "data"}
    )
    workflow.connect(
        "convergence",
        "optimizer",
        mapping={"data": "data"},
        cycle=True,
        max_iterations=50,
    )

    # Execute with different convergence modes
    runtime = LocalRuntime()

    # Test 1: Threshold convergence
    print("\nTest 1: Threshold convergence (error < 1.0)")
    results, _ = runtime.execute(
        workflow,
        parameters={
            "optimizer": {"data": [10, 20, 30], "optimization_target": 100.0},
            "convergence": {"threshold": 1.0, "mode": "threshold"},
        },
    )

    conv_result = results.get("convergence", {})
    print(
        f"Converged: {conv_result.get('converged')} at iteration {conv_result.get('iteration')}"
    )
    print(f"Final error: {conv_result.get('value', 0):.3f}")

    # Test 2: Stability convergence
    print("\nTest 2: Stability convergence (low variance)")
    results, _ = runtime.execute(
        workflow,
        parameters={
            "optimizer": {"data": [10, 20, 30], "optimization_target": 100.0},
            "convergence": {
                "mode": "stability",
                "stability_window": 5,
                "min_variance": 0.5,
            },
        },
    )

    conv_result = results.get("convergence", {})
    print(
        f"Converged: {conv_result.get('converged')} at iteration {conv_result.get('iteration')}"
    )
    print(f"Reason: {conv_result.get('reason')}")

    # Test 3: Improvement rate convergence
    print("\nTest 3: Improvement rate convergence")
    results, _ = runtime.execute(
        workflow,
        parameters={
            "optimizer": {"data": [10, 20, 30], "optimization_target": 100.0},
            "convergence": {
                "mode": "improvement",
                "min_improvement": 0.01,
                "improvement_window": 5,
            },
        },
    )

    conv_result = results.get("convergence", {})
    metrics = conv_result.get("convergence_metrics", {})
    print(
        f"Converged: {conv_result.get('converged')} at iteration {conv_result.get('iteration')}"
    )
    print(f"Final improvement rate: {metrics.get('improvement_rate', 0):.4f}")


# ============================================================================
# Example 3: Cycle-Aware A2A Coordination
# ============================================================================


class AgentSimulatorNode(CycleAwareNode):
    """Simulates agent responses for A2A coordination."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "task": NodeParameter(name="task", type=dict, required=False, default={}),
            "agent_id": NodeParameter(
                name="agent_id", type=str, required=False, default="unknown"
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Simulate agent processing a task."""
        task = kwargs.get("task", {})
        agent_id = kwargs.get("agent_id", "unknown")

        # Simulate work
        time.sleep(0.1)  # Simulate processing time

        # Simulate success rate based on iteration (agents improve over time)
        iteration = self.get_iteration(context)
        base_success_rate = 0.7
        improvement = min(0.25, iteration * 0.02)  # Max 25% improvement
        success_rate = base_success_rate + improvement

        # Determine success
        import random

        success = random.random() < success_rate

        return {
            "agent_id": agent_id,
            "task": task,
            "success": success,
            "iteration": iteration,
            "effective_success_rate": success_rate,
            "result": f"Task '{task.get('type', 'unknown')}' {'completed' if success else 'failed'} by {agent_id}",
        }


def example3_cycle_aware_coordination():
    """
    Demonstrates cycle-aware A2A coordination.

    Design Pattern:
        A2ACoordinator → ConvergenceChecker ↻
        ↓ (delegate tasks)
        [Agents execute tasks]
        ↑ (report results)

    Flow:
    1. A2ACoordinator starts with registered agents
    2. Each iteration:
        - Delegates tasks based on agent skills/performance
        - Tracks agent performance across cycles
        - Learns which agents perform best
    3. ConvergenceChecker monitors active agents
    4. Converges when all agents are actively engaged
    5. Demonstrates cycle-aware agent selection improving over time

    Shows how A2ACoordinatorNode inherits CycleAwareNode to track
    agent performance history and optimize task delegation.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Cycle-Aware A2A Coordination")
    print("=" * 60)

    workflow = Workflow("a2a-coordination", "Cycle-Aware Agent Coordination")

    # Add nodes
    workflow.add_node("memory", SharedMemoryPoolNode())
    workflow.add_node("coordinator", A2ACoordinatorNode())
    workflow.add_node("agent_sim", AgentSimulatorNode())
    workflow.add_node("convergence", ConvergenceCheckerNode())

    # Register agents first
    runtime = LocalRuntime()

    # Pre-register agents
    coordinator = A2ACoordinatorNode()
    coordinator.execute(
        {"cycle": {"iteration": 0}},
        action="register",
        agent_info={
            "id": "analyst_001",
            "skills": ["analysis", "data"],
            "role": "analyst",
        },
    )
    coordinator.execute(
        {"cycle": {"iteration": 0}},
        action="register",
        agent_info={
            "id": "researcher_001",
            "skills": ["research", "investigation"],
            "role": "researcher",
        },
    )
    coordinator.execute(
        {"cycle": {"iteration": 0}},
        action="register",
        agent_info={
            "id": "processor_001",
            "skills": ["data", "processing"],
            "role": "processor",
        },
    )

    # Now build the cyclic workflow
    workflow = Workflow("a2a-cyclic", "Cyclic A2A Coordination")
    workflow.add_node("coordinator", coordinator)
    workflow.add_node("evaluator", ConvergenceCheckerNode())

    # Cycle: coordinator delegates tasks and learns from performance
    workflow.connect(
        "coordinator", "evaluator", mapping={"cycle_info.active_agents": "value"}
    )
    workflow.connect("evaluator", "coordinator", cycle=True, max_iterations=10)

    # Execute cyclic coordination
    print("\nRunning cyclic A2A coordination with learning...")
    results, _ = runtime.execute(
        workflow,
        parameters={
            "coordinator": {
                "action": "delegate",
                "task": {
                    "type": "analysis",
                    "description": "Analyze data patterns",
                    "required_skills": ["analysis", "data"],
                    "priority": "high",
                },
                "coordination_strategy": "best_match",
            },
            "evaluator": {"threshold": 3, "mode": "threshold"},  # All agents active
        },
    )

    # Show coordination history
    final_result = results.get("coordinator", {})
    cycle_info = final_result.get("cycle_info", {})

    print("\n✅ Coordination Results:")
    print(f"Total iterations: {cycle_info.get('iteration', 0)}")
    print(f"Coordination events: {cycle_info.get('coordination_history_length', 0)}")
    print(f"Active agents: {cycle_info.get('active_agents', 0)}")
    print(
        f"Performance tracked agents: {cycle_info.get('performance_tracked_agents', 0)}"
    )


# ============================================================================
# Example 4: Complete Cycle-Aware Pattern with SwitchNode
# ============================================================================


class DataQualityAnalyzerNode(CycleAwareNode):
    """Analyzes data quality with cycle awareness."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Analyze data quality metrics."""
        data = kwargs.get("data", [])

        # Handle empty data
        if not data:
            data = []

        # Quality metrics
        completeness = (
            len([x for x in data if x is not None]) / len(data) if data else 0
        )
        validity = (
            len([x for x in data if isinstance(x, (int, float)) and x > 0]) / len(data)
            if data
            else 0
        )
        consistency = (
            1.0 - (len(set(data)) / len(data)) if data else 0
        )  # Less variety = more consistent

        overall_quality = (completeness + validity + consistency) / 3

        # Track quality history
        quality_history = self.accumulate_values(
            context, "quality_scores", overall_quality
        )

        # Detect improvement trend
        is_improving = (
            len(quality_history) > 3 and quality_history[-1] > quality_history[-4]
        )

        self.log_cycle_info(
            context,
            f"Quality: {overall_quality:.3f} ({'improving' if is_improving else 'stable'})",
        )

        return {
            "data": data,
            "quality_metrics": {
                "completeness": completeness,
                "validity": validity,
                "consistency": consistency,
                "overall": overall_quality,
            },
            "is_improving": is_improving,
            **self.set_cycle_state({"quality_scores": quality_history}),
        }


class DataEnhancerNode(CycleAwareNode):
    """Enhances data quality iteratively."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "quality_metrics": NodeParameter(
                name="quality_metrics", type=dict, required=False, default={}
            ),
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Enhance data based on quality metrics."""
        data = kwargs.get("data", [])

        # Debug logging
        iteration = self.get_iteration(context)
        if iteration == 0:
            self.log_cycle_info(context, f"Initial data: {data}")

        metrics = kwargs.get("quality_metrics", {})

        # Enhancement strategies based on metrics
        enhanced_data = data.copy()

        # Fix completeness issues
        if metrics.get("completeness", 1) < 0.9:
            enhanced_data = [x if x is not None else 0 for x in enhanced_data]

        # Fix validity issues
        if metrics.get("validity", 1) < 0.9:
            enhanced_data = [
                abs(x) if isinstance(x, (int, float)) else 1 for x in enhanced_data
            ]

        # Add some variation if too consistent
        if metrics.get("consistency", 0) > 0.9 and iteration < 5:

            idx = random.randint(0, len(enhanced_data) - 1)
            enhanced_data[idx] = enhanced_data[idx] * 1.1

        return {
            "data": enhanced_data,
            "enhancement_applied": True,
            "iteration": iteration,
        }


def example4_complete_pattern():
    """
    Demonstrates complete cycle-aware pattern with SwitchNode.

    Design Pattern:
        DataEnhancer → DataQualityAnalyzer → ConvergenceChecker → ConvergencePackagerNode → SwitchNode
                ↑                                                                            ↓ (false_output)
                ←━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                                                                                             ↓ (true_output)
                                                                                          OutputNode

    Flow:
    1. DataEnhancer improves data quality each iteration
    2. DataQualityAnalyzer calculates quality metrics (completeness, validity, consistency)
    3. ConvergenceChecker evaluates if quality meets criteria (combined mode)
    4. ConvergencePackagerNode formats convergence output for SwitchNode
    5. SwitchNode routes based on 'converged' field:
        - false_output → cycle back to DataEnhancer
        - true_output → exit to OutputNode
    6. Cycle continues until convergence criteria met

    Critical pattern for implementing iterative refinement with conditional exit.
    Shows real-world usage of SwitchNode in cyclic workflows.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Complete Cycle-Aware Pattern")
    print("=" * 60)
    print(
        "Pattern: Input → Enhance → Analyze → Converge → Switch → (Enhance if retry | Output if done)"
    )

    workflow = Workflow("complete-pattern", "Complete Cycle-Aware Pattern")

    # Add all nodes
    workflow.add_node("enhancer", DataEnhancerNode())  # B - Enhances data
    workflow.add_node("analyzer", DataQualityAnalyzerNode())  # C - Analyzes quality
    workflow.add_node("convergence", ConvergenceCheckerNode())  # D - Checks convergence

    # Create a wrapper to package convergence output for SwitchNode
    class ConvergencePackagerNode(CycleAwareNode):
        def get_parameters(self) -> dict[str, NodeParameter]:
            return {
                "input": NodeParameter(name="input", type=dict, required=False),
                "converged": NodeParameter(name="converged", type=bool, required=False),
                "data": NodeParameter(name="data", type=Any, required=False),
                "value": NodeParameter(name="value", type=float, required=False),
                "iteration": NodeParameter(name="iteration", type=int, required=False),
                "convergence_metrics": NodeParameter(
                    name="convergence_metrics", type=dict, required=False
                ),
                "_cycle_state": NodeParameter(
                    name="_cycle_state", type=dict, required=False
                ),
            }

        def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
            # Package all convergence output as input_data for SwitchNode
            self.log_cycle_info(context, f"Packager received: {list(kwargs.keys())}")

            # Handle the case where everything comes as 'input'
            if "input" in kwargs and len(kwargs) == 1:
                input_data = kwargs["input"]
            else:
                input_data = kwargs

            self.log_cycle_info(
                context,
                f"Packager sending to switch: converged={input_data.get('converged')}",
            )
            return {"input_data": input_data}

    workflow.add_node("packager", ConvergencePackagerNode())

    # Use the real SwitchNode with proper configuration
    workflow.add_node(
        "switch", SwitchNode(condition_field="converged", operator="==", value=True)
    )

    # Create a simple output node
    class OutputNode(CycleAwareNode):
        def get_parameters(self) -> dict[str, NodeParameter]:
            return {
                "data1": NodeParameter(name="data1", type=Any, required=False),
                "data2": NodeParameter(name="data2", type=Any, required=False),
            }

        def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
            return {"merged_data": [kwargs.get("data1"), kwargs.get("data2")]}

    workflow.add_node("output", OutputNode())  # E - Final output

    # Connect the pattern
    workflow.connect("enhancer", "analyzer")
    workflow.connect(
        "analyzer",
        "convergence",
        mapping={"quality_metrics.overall": "value", "data": "data"},
    )
    # Package convergence output for SwitchNode
    workflow.connect("convergence", "packager")
    # Map packager's input_data output to switch's input_data parameter
    workflow.connect("packager", "switch", mapping={"input_data": "input_data"})

    # Conditional routing based on convergence
    workflow.connect(
        "switch",
        "enhancer",  # Back to enhancement when false_output
        condition="false_output",
        mapping={"false_output.data": "data"},
        cycle=True,
        max_iterations=20,
        convergence_check="converged == True",
    )

    workflow.connect(
        "switch",
        "output",  # To output when true_output
        condition="true_output",
        mapping={"true_output": "data1"},
    )

    # Execute with problematic data
    runtime = LocalRuntime()
    results, _ = runtime.execute(
        workflow,
        parameters={
            "enhancer": {"data": [1, -2, None, 4, -5, None, 7, 8, 9, 10]},
            "convergence": {
                "threshold": 0.85,
                "mode": "combined",  # Both threshold and stability
                "stability_window": 3,
                "min_variance": 0.02,
            },
        },
    )

    # Display results - the converged data should come through true_output
    if "output" in results:
        output = results.get("output", {})
        merged = output.get("merged_data", [])
        if merged and merged[0]:
            # Extract the converged data from the switch output
            conv_result = merged[0]
            print("\n✅ CYCLE COMPLETED")
            print(f"Converged at iteration: {conv_result.get('iteration', 0)}")
            print(f"Final quality: {conv_result.get('value', 0):.3f}")
            print(f"Convergence reason: {conv_result.get('reason', 'Unknown')}")
            if "data" in conv_result:
                print(
                    f"Final processed data: {conv_result['data'][:5]}... (showing first 5)"
                )
        else:
            print("\n❌ Workflow did not converge properly")
    else:
        print("\n❌ Workflow did not complete properly")


# ============================================================================
# Example 5: Multi-Criteria Convergence
# ============================================================================


class MultiMetricOptimizerNode(CycleAwareNode):
    """Optimizes multiple metrics simultaneously."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=dict, required=False, default={})
        }

    def run(self, context: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Optimize multiple metrics."""
        data = kwargs.get("data", {})

        # Log received data for debugging
        iteration = self.get_iteration(context)
        if iteration < 3:  # Only log first few iterations
            self.log_cycle_info(context, f"Optimizer received data: {data}")

        # Current metrics
        accuracy = data.get("accuracy", 0.5)
        latency = data.get("latency", 100)
        cost = data.get("cost", 1000)

        # Improve each metric
        iteration = self.get_iteration(context)
        improvement_factor = 1 - (
            0.05 * (1 - iteration / 20)
        )  # Diminishing improvements

        # Optimize
        new_accuracy = min(0.99, accuracy + (1 - accuracy) * 0.1 * improvement_factor)
        new_latency = max(10.0, latency * 0.9 * improvement_factor)
        new_cost = max(100.0, cost * 0.85 * improvement_factor)

        return {
            "metrics": {
                "accuracy": new_accuracy,
                "latency": new_latency,
                "cost": new_cost,
            }
        }


def example5_multi_criteria():
    """
    Demonstrates multi-criteria convergence checking.

    Design Pattern:
        MultiMetricOptimizer → MultiCriteriaConvergenceChecker ↻
        ↓ (when all criteria met)
        [Output]

    Flow:
    1. MultiMetricOptimizer manages multiple metrics simultaneously:
        - accuracy (maximize toward 0.99)
        - latency (minimize toward 10ms)
        - cost (minimize toward $100)
    2. Each metric improves at different rates
    3. MultiCriteriaConvergenceChecker monitors all metrics:
        - accuracy >= 0.95 (threshold mode)
        - latency <= 20 (threshold mode, minimize)
        - cost <= 200 (threshold mode, minimize)
    4. require_all=True means ALL criteria must be met
    5. Provides detailed per-metric convergence status

    Demonstrates handling complex multi-dimensional optimization
    scenarios common in ML training and system tuning.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Multi-Criteria Convergence")
    print("=" * 60)

    # MultiCriteriaConvergenceNode is already imported at the top

    workflow = Workflow("multi-criteria", "Multi-Criteria Convergence")

    # Add nodes
    workflow.add_node("optimizer", MultiMetricOptimizerNode())
    workflow.add_node("convergence", MultiCriteriaConvergenceNode())

    # Connect with multi-criteria convergence
    workflow.connect("optimizer", "convergence", mapping={"metrics": "metrics"})
    workflow.connect(
        "convergence",
        "optimizer",
        mapping={"metrics": "data"},
        cycle=True,
        max_iterations=30,
    )

    # Execute
    runtime = LocalRuntime()
    results, _ = runtime.execute(
        workflow,
        parameters={
            "optimizer": {"data": {"accuracy": 0.6, "latency": 100, "cost": 1000}},
            "convergence": {
                "criteria": {
                    "accuracy": {"threshold": 0.95, "mode": "threshold"},
                    "latency": {
                        "threshold": 20,
                        "mode": "threshold",
                        "direction": "minimize",
                    },
                    "cost": {
                        "threshold": 200,
                        "mode": "threshold",
                        "direction": "minimize",
                    },
                },
                "require_all": True,  # All criteria must be met
            },
        },
    )

    # Display results
    conv_result = results.get("convergence", {})
    print("\n✅ Multi-Criteria Convergence Results:")
    print(f"Converged: {conv_result.get('converged')}")
    print(f"Iterations: {conv_result.get('iteration')}")
    print(f"Met criteria: {conv_result.get('met_criteria', [])}")
    print(f"Failed criteria: {conv_result.get('failed_criteria', [])}")

    # Show detailed results
    detailed = conv_result.get("detailed_results", {})
    for metric, result in detailed.items():
        print(f"\n{metric}:")
        print(f"  - Value: {result.get('value', 0):.3f}")
        print(f"  - Converged: {result.get('converged')}")
        print(f"  - Reason: {result.get('reason')}")


# ============================================================================
# Main Execution
# ============================================================================


def main():
    """Run all cycle-aware node examples."""
    print("🚀 Cycle-Aware Node Enhancement Examples")
    print("=" * 60)
    print()
    print("This example demonstrates:")
    print("• CycleAwareNode base class with built-in helpers")
    print("• ConvergenceCheckerNode for declarative convergence")
    print("• Enhanced A2A Coordinator with cycle-aware features")
    print("• Integration with SwitchNode for conditional routing")
    print("• Multi-criteria convergence patterns")
    print()

    try:
        # Run all examples
        example1_basic_cycle_aware()
        example2_advanced_convergence()
        example3_cycle_aware_coordination()
        example4_complete_pattern()
        example5_multi_criteria()

        print("\n" + "=" * 60)
        print("✅ All cycle-aware examples completed successfully!")
        print()
        print("💡 Key Benefits Demonstrated:")
        print("• Eliminated boilerplate with CycleAwareNode helpers")
        print("• Declarative convergence instead of custom logic")
        print("• Cycle-aware agent coordination with learning")
        print("• Clean integration with SwitchNode patterns")
        print("• Multi-dimensional convergence checking")
        print()
        print("🔧 Usage Tips:")
        print("• Inherit from CycleAwareNode to eliminate boilerplate")
        print("• Use ConvergenceCheckerNode instead of custom convergence logic")
        print("• A2ACoordinatorNode now tracks agent performance across cycles")
        print("• Combine with SwitchNode for powerful conditional patterns")

    except Exception as e:
        print(f"❌ Examples failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
