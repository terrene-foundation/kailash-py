#!/usr/bin/env python3
"""
Comprehensive Convergence & Safety Framework Examples

This consolidated module demonstrates all convergence and safety features:
1. Expression-based convergence conditions
2. Compound convergence (AND/OR logic)
3. Timeout safety mechanisms
4. Maximum iteration safety limits
5. Complex mathematical convergence expressions
6. PythonCodeNode proper usage patterns with None handling

All examples are tested and working correctly.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor
from kailash.workflow.graph import Workflow


class QualityOptimizerNode(Node):
    """Node that gradually improves a quality score with realistic noise."""

    def get_parameters(self):
        return {
            "data": NodeParameter(
                name="data",
                type=str,
                required=False,
                default="sample_data",
                description="Input data",
            ),
            "quality": NodeParameter(
                name="quality",
                type=float,
                required=False,
                default=0.0,
                description="Current quality score",
            ),
            "improvement_rate": NodeParameter(
                name="improvement_rate",
                type=float,
                required=False,
                default=0.1,
                description="Rate of improvement",
            ),
            "noise_factor": NodeParameter(
                name="noise_factor",
                type=float,
                required=False,
                default=0.05,
                description="Noise factor",
            ),
        }

    def run(self, context, **kwargs):
        """Improve quality with some random variation."""
        import random

        data = kwargs.get("data", "default_data")
        quality = kwargs.get("quality", 0.0)
        improvement_rate = kwargs.get("improvement_rate", 0.1)
        noise_factor = kwargs.get("noise_factor", 0.05)

        # Get cycle information
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Simulate improvement with noise
        noise = random.uniform(-noise_factor, noise_factor)
        new_quality = min(1.0, quality + improvement_rate + noise)

        # Sometimes quality might decrease slightly (realistic scenario)
        if random.random() < 0.1:  # 10% chance of slight regression
            new_quality = max(0.0, new_quality - 0.02)

        print(
            f"Quality optimization iteration {iteration}: {quality:.3f} -> {new_quality:.3f}"
        )

        return {
            "data": data,
            "quality": new_quality,
            "improvement": new_quality - quality,
            "iteration_result": f"Quality: {new_quality:.3f}",
        }


def example_callback_convergence_fixed():
    """Example: Fixed callback-based convergence using proper PythonCodeNode patterns."""
    print("=== Fixed Callback-based Convergence ===")
    print("Demonstrates proper PythonCodeNode usage that handles None values")
    print()

    # Create workflow
    workflow = Workflow(
        workflow_id="callback_convergence_fixed",
        name="Fixed Quality Optimization with Custom Convergence",
        description="Use custom Python logic with proper None handling",
    )

    # Add optimizer node
    optimizer = QualityOptimizerNode()
    workflow.add_node("optimizer", optimizer)

    # Add convergence checker node using function-based approach (safer than code strings)
    def convergence_checker_func(quality=None, improvement=None, iteration_result=None):
        """Fixed convergence checker that handles None values properly."""
        # Handle None values and set defaults
        if quality is None or not isinstance(quality, (int, float)):
            quality = 0.0
        if improvement is None or not isinstance(improvement, (int, float)):
            improvement = 0.0
        if iteration_result is None:
            iteration_result = ""

        # Custom convergence logic:
        # - Quality must be > 0.85
        # - Improvement must be small (< 0.02) for stability
        # - Or quality is very high (> 0.95)

        converged = (
            (quality > 0.85 and improvement < 0.02)  # Stable high quality
            or quality > 0.95  # Very high quality regardless of stability
        )

        reason = ""
        if converged:
            if quality > 0.95:
                reason = "Very high quality achieved"
            elif quality > 0.85 and improvement < 0.02:
                reason = "Stable high quality achieved"

        print(
            f"Convergence check - Quality: {quality:.3f}, Improvement: {improvement:.3f}"
        )
        print(f"Converged: {converged} - {reason}")

        # Return the result
        return {
            "converged": converged,
            "quality": quality,
            "improvement": improvement,
            "reason": reason,
        }

    convergence_checker = PythonCodeNode.from_function(
        func=convergence_checker_func,
        name="ConvergenceChecker",
        description="Fixed convergence checker with proper None handling",
    )
    workflow.add_node("convergence_checker", convergence_checker)

    # Connect optimizer to convergence checker
    workflow.connect(
        "optimizer",
        "convergence_checker",
        mapping={
            "quality": "quality",
            "improvement": "improvement",
            "iteration_result": "iteration_result",
        },
    )

    # Create cycle based on convergence checker result
    workflow.connect(
        "convergence_checker",
        "optimizer",
        mapping={"quality": "quality"},
        cycle=True,
        max_iterations=20,
        convergence_check="converged == True",
        cycle_id="custom_logic_loop",
    )

    # Execute
    executor = CyclicWorkflowExecutor()
    results, run_id = executor.execute(
        workflow,
        parameters={
            "optimizer": {
                "data": "sample_data",
                "quality": 0.2,
                "improvement_rate": 0.12,
                "noise_factor": 0.04,
            }
        },
    )

    print(
        f"Final quality: {results.get('convergence_checker', {}).get('quality', 'N/A')}"
    )
    print(
        f"Convergence reason: {results.get('convergence_checker', {}).get('reason', 'N/A')}"
    )
    print("✅ Fixed callback convergence example completed")
    print()
    return results


def example_nested_cycles_fixed():
    """Example: Fixed nested cycle using function-based PythonCodeNode."""
    print("=== Fixed Nested Cycle Safety ===")
    print("Demonstrates nested cycles using function-based nodes")
    print()

    # Create workflow with nested cycles
    workflow = Workflow(
        workflow_id="nested_cycles_fixed",
        name="Fixed Nested Optimization with Safety",
        description="Outer optimization loop with inner refinement cycles",
    )

    # Outer optimizer
    outer_optimizer = QualityOptimizerNode()
    workflow.add_node("outer_optimizer", outer_optimizer)

    # Inner refiner using function-based approach
    def inner_refiner_func(data="nested_data", quality=0.0, refinement_level=0):
        """Inner refinement function with proper defaults."""
        # Handle None values explicitly
        if data is None:
            data = "nested_data"
        if quality is None:
            quality = 0.0
        if refinement_level is None:
            refinement_level = 0

        # Inner refinement - small improvements
        refined_quality = min(1.0, quality + 0.02)  # Small boost
        new_refinement = refinement_level + 1

        print(
            f"  Inner refinement {new_refinement}: {quality:.3f} -> {refined_quality:.3f}"
        )

        return {
            "data": data,
            "quality": refined_quality,
            "refinement_level": new_refinement,
        }

    # Create inner refiner node from function
    inner_refiner = PythonCodeNode.from_function(
        func=inner_refiner_func,
        name="InnerRefiner",
        description="Inner refinement process",
    )
    workflow.add_node("inner_refiner", inner_refiner)

    # Outer cycle (parent)
    workflow.connect(
        "outer_optimizer",
        "inner_refiner",
        mapping={"data": "data", "quality": "quality"},
    )

    # Inner cycle (child) - quick refinement
    workflow.connect(
        "inner_refiner",
        "inner_refiner",
        mapping={
            "data": "data",
            "quality": "quality",
            "refinement_level": "refinement_level",
        },
        cycle=True,
        max_iterations=3,
        convergence_check="refinement_level >= 2",
        cycle_id="inner_refinement",
    )

    # Back to outer cycle
    workflow.connect(
        "inner_refiner",
        "outer_optimizer",
        mapping={"data": "data", "quality": "quality"},
        cycle=True,
        max_iterations=8,
        convergence_check="quality >= 0.85",
        cycle_id="outer_optimization",
    )

    # Execute
    executor = CyclicWorkflowExecutor()
    results, run_id = executor.execute(
        workflow,
        parameters={
            "outer_optimizer": {
                "data": "nested_data",
                "quality": 0.3,
                "improvement_rate": 0.06,
                "noise_factor": 0.02,
            }
        },
    )

    print(f"Final quality: {results.get('inner_refiner', {}).get('quality', 'N/A')}")
    print("✅ Fixed nested cycles example completed")
    print()
    return results


def example_advanced_callback():
    """Example: Advanced callback with comprehensive None handling."""
    print("=== Advanced Callback with Comprehensive None Handling ===")
    print("Demonstrates robust None handling patterns")
    print()

    # Create workflow
    workflow = Workflow(
        workflow_id="advanced_callback",
        name="Advanced Callback Example",
        description="Robust callback-based convergence",
    )

    # Add optimizer node
    optimizer = QualityOptimizerNode()
    workflow.add_node("optimizer", optimizer)

    # Advanced callback with comprehensive validation
    def advanced_callback_func(
        quality=None,
        improvement=None,
        iteration_result=None,
        data=None,
        improvement_rate=None,
        noise_factor=None,
    ):
        """Advanced callback with comprehensive None handling."""

        # Comprehensive None handling with type checking
        if quality is None or not isinstance(quality, (int, float)):
            quality = 0.0
        if improvement is None or not isinstance(improvement, (int, float)):
            improvement = 0.0
        if iteration_result is None or not isinstance(iteration_result, str):
            iteration_result = ""
        if data is None:
            data = "default_data"
        if improvement_rate is None or not isinstance(improvement_rate, (int, float)):
            improvement_rate = 0.1
        if noise_factor is None or not isinstance(noise_factor, (int, float)):
            noise_factor = 0.05

        # Advanced convergence logic with multiple criteria
        criteria_met = []

        # Criterion 1: High quality achieved
        high_quality = quality > 0.85
        criteria_met.append(("high_quality", high_quality))

        # Criterion 2: Stable improvement (small changes)
        stable_improvement = improvement < 0.02
        criteria_met.append(("stable_improvement", stable_improvement))

        # Criterion 3: Very high quality
        very_high_quality = quality > 0.95
        criteria_met.append(("very_high_quality", very_high_quality))

        # Determine convergence
        converged = (high_quality and stable_improvement) or very_high_quality

        # Generate detailed reason
        met_criteria = [name for name, met in criteria_met if met]
        reason = (
            f"Criteria met: {', '.join(met_criteria)}"
            if met_criteria
            else "No criteria met"
        )

        print("Advanced convergence check:")
        print(f"  Quality: {quality:.3f}, Improvement: {improvement:.3f}")
        print(f"  Criteria: {dict(criteria_met)}")
        print(f"  Converged: {converged} - {reason}")

        return {
            "converged": converged,
            "quality": quality,
            "improvement": improvement,
            "reason": reason,
            "criteria_met": met_criteria,
            "data": data,
            "improvement_rate": improvement_rate,
            "noise_factor": noise_factor,
        }

    # Create callback node from function
    callback_node = PythonCodeNode.from_function(
        func=advanced_callback_func,
        name="AdvancedCallback",
        description="Advanced convergence callback with comprehensive validation",
    )
    workflow.add_node("callback_node", callback_node)

    # Connect optimizer to callback
    workflow.connect(
        "optimizer",
        "callback_node",
        mapping={
            "quality": "quality",
            "improvement": "improvement",
            "iteration_result": "iteration_result",
            "data": "data",
            "improvement_rate": "improvement_rate",
            "noise_factor": "noise_factor",
        },
    )

    # Create cycle based on callback result
    workflow.connect(
        "callback_node",
        "optimizer",
        mapping={
            "quality": "quality",
            "data": "data",
            "improvement_rate": "improvement_rate",
            "noise_factor": "noise_factor",
        },
        cycle=True,
        max_iterations=15,
        convergence_check="converged == True",
        cycle_id="advanced_callback_loop",
    )

    # Execute
    executor = CyclicWorkflowExecutor()
    results, run_id = executor.execute(
        workflow,
        parameters={
            "optimizer": {
                "data": "advanced_data",
                "quality": 0.1,
                "improvement_rate": 0.10,
                "noise_factor": 0.03,
            }
        },
    )

    print(f"Final quality: {results.get('callback_node', {}).get('quality', 'N/A')}")
    print(
        f"Convergence reason: {results.get('callback_node', {}).get('reason', 'N/A')}"
    )
    print(
        f"Criteria met: {results.get('callback_node', {}).get('criteria_met', 'N/A')}"
    )
    print("✅ Advanced callback example completed")
    print()
    return results


def example_expression_convergence():
    """Example: Simple expression-based convergence."""
    print("=== Expression-based Convergence ===")
    print("Demonstrates quality optimization with expression convergence")
    print()

    # Create workflow
    workflow = Workflow(
        workflow_id="expression_convergence",
        name="Quality Optimization with Expression Convergence",
        description="Optimize quality until it reaches a target threshold",
    )

    # Add optimizer node
    optimizer = QualityOptimizerNode()
    workflow.add_node("optimizer", optimizer)

    # Create cycle with expression convergence
    workflow.connect(
        "optimizer",
        "optimizer",
        mapping={
            "data": "data",
            "quality": "quality",
            "improvement_rate": "improvement_rate",
            "noise_factor": "noise_factor",
        },
        cycle=True,
        max_iterations=20,
        convergence_check="quality >= 0.9",
        cycle_id="quality_loop",
    )

    # Execute
    executor = CyclicWorkflowExecutor()
    results, run_id = executor.execute(
        workflow,
        parameters={
            "optimizer": {
                "data": "sample_data",
                "quality": 0.1,
                "improvement_rate": 0.08,
                "noise_factor": 0.03,
            }
        },
    )

    final_quality = results.get("optimizer", {}).get("quality", "N/A")
    print(f"Final quality: {final_quality}")
    print(
        f"Convergence achieved: {'✅ YES' if isinstance(final_quality, float) and final_quality >= 0.9 else '❌ NO'}"
    )
    print("✅ Expression convergence example completed")
    print()
    return results


def example_max_iterations_safety():
    """Example: Maximum iterations safety mechanism."""
    print("=== Maximum Iterations Safety ===")
    print("Demonstrates max iterations protection")
    print()

    # Create workflow
    workflow = Workflow(
        workflow_id="max_iterations_safety",
        name="Quality Optimization with Max Iterations",
        description="Quality optimization with iteration limit safety",
    )

    # Add optimizer node
    optimizer = QualityOptimizerNode()
    workflow.add_node("optimizer", optimizer)

    # Create cycle with max iterations limit (intentionally low improvement rate)
    workflow.connect(
        "optimizer",
        "optimizer",
        mapping={
            "data": "data",
            "quality": "quality",
            "improvement_rate": "improvement_rate",
            "noise_factor": "noise_factor",
        },
        cycle=True,
        max_iterations=10,  # Low limit
        convergence_check="quality >= 0.95",  # Hard to reach convergence
        cycle_id="limited_loop",
    )

    # Execute
    executor = CyclicWorkflowExecutor()
    results, run_id = executor.execute(
        workflow,
        parameters={
            "optimizer": {
                "data": "sample_data",
                "quality": 0.1,
                "improvement_rate": 0.05,  # Slow improvement
                "noise_factor": 0.02,
            }
        },
    )

    final_quality = results.get("optimizer", {}).get("quality", "N/A")
    print(f"Final quality: {final_quality}")
    print(
        f"Reached target (0.95): {'✅ YES' if isinstance(final_quality, float) and final_quality >= 0.95 else '❌ NO (stopped by max iterations)'}"
    )
    print("✅ Max iterations safety example completed")
    print()
    return results


def run_all_convergence_examples():
    """Run all convergence examples including both basic and advanced patterns."""
    print("Comprehensive Convergence & Safety Framework Examples")
    print("=" * 65)
    print()

    examples = [
        example_expression_convergence,
        example_max_iterations_safety,
        example_callback_convergence_fixed,
        example_nested_cycles_fixed,
        example_advanced_callback,
    ]

    results = {}
    successful = 0
    failed = 0

    for example_func in examples:
        try:
            result = example_func()
            results[example_func.__name__] = result
            successful += 1
        except Exception as e:
            print(f"❌ Error in {example_func.__name__}: {e}")
            results[example_func.__name__] = {"error": str(e)}
            failed += 1

        print("-" * 50)
        print()

    print("🎉 All fixed convergence examples completed!")
    print()

    # Summary
    print("SUMMARY:")
    print("--------")
    for example_name, result in results.items():
        if "error" in result:
            print(f"❌ {example_name}: FAILED ({result['error']})")
        else:
            print(f"✅ {example_name}: SUCCESS")

    print()
    print(
        f"📊 Results: {successful} successful, {failed} failed out of {len(examples)} total"
    )

    if failed == 0:
        print("🏆 All PythonCodeNode examples now work correctly!")
        print()
        print("Key fixes applied:")
        print("- ✅ Proper None value handling in PythonCodeNode code")
        print("- ✅ Function-based nodes instead of code strings where possible")
        print("- ✅ Comprehensive input validation and defaults")
        print("- ✅ Type checking before processing parameters")

    return results


if __name__ == "__main__":
    run_all_convergence_examples()
