#!/usr/bin/env python3
"""
Cyclic Workflow Examples - Phase 1 Demonstration
==============================================

This consolidated example demonstrates cyclic workflows in Kailash SDK.
All parameter propagation issues have been fixed!

Examples included:
1. Simple Counter (✅) - Basic self-loop cycle
2. Data Quality Improvement (✅) - Single-node cycle with convergence
3. Multi-Node Cycle (✅) - Data preservation through cycle iterations

Key Features:
- Parameter propagation through cycle iterations
- Expression-based convergence conditions
- Maximum iteration safety limits
- Cycle state tracking and preservation
"""


from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor

# ============================================================================
# EXAMPLE 1: Simple Counter (WORKING ✅)
# ============================================================================


class CounterNode(Node):
    """Simple counter that increments until target is reached."""

    def get_parameters(self):
        return {
            "count": NodeParameter(
                name="count",
                type=int,
                required=False,
                default=0,
                description="Current count value",
            ),
            "target": NodeParameter(
                name="target",
                type=int,
                required=False,
                default=10,
                description="Target count to reach",
            ),
        }

    def run(self, context, **kwargs):
        count = kwargs.get("count", 0)
        target = kwargs.get("target", 10)

        # Get cycle information
        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Simple increment
        new_count = count + 1

        print(
            f"Counter iteration {iteration}: {count} → {new_count} (target: {target})"
        )

        return {
            "count": new_count,
            "reached_target": new_count >= target,
            "iteration": iteration,
        }


def example1_simple_counter():
    """Demonstrates a working self-loop cycle."""
    print("\n" + "=" * 60)
    print("EXAMPLE 1: Simple Counter (Self-Loop)")
    print("=" * 60)

    workflow = Workflow("simple-counter", "example1")

    # Single node with self-loop
    workflow.add_node("counter", CounterNode())

    # Create self-loop cycle
    workflow.connect(
        "counter",
        "counter",
        mapping={"count": "count"},
        cycle=True,
        max_iterations=15,
        convergence_check="count >= 5",  # Stop at 5
        cycle_id="counting_loop",
    )

    # Execute
    executor = CyclicWorkflowExecutor()
    results, run_id = executor.execute(
        workflow, parameters={"counter": {"count": 0, "target": 5}}
    )

    print(f"\nResults: Final count = {results['counter']['count']}")
    print(
        f"Status: {'✅ WORKING' if results['counter']['count'] == 5 else '❌ FAILED'}"
    )


# ============================================================================
# EXAMPLE 2: Data Quality Improvement (WORKING ✅)
# ============================================================================


class QualityCheckerNode(Node):
    """Checks data quality and decides if improvement is needed."""

    def get_parameters(self):
        return {
            "quality": NodeParameter(
                name="quality", type=float, required=False, default=0.0
            ),
            "threshold": NodeParameter(
                name="threshold", type=float, required=False, default=0.8
            ),
        }

    def run(self, context, **kwargs):
        quality = kwargs.get("quality", 0.0)
        threshold = kwargs.get("threshold", 0.8)

        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        # Simulate quality improvement (20% per iteration)
        if iteration > 0:  # Only improve after first check
            quality = min(1.0, quality + 0.2)

        print(f"Quality check {iteration}: {quality:.2f} (threshold: {threshold})")

        return {
            "quality": quality,
            "needs_improvement": quality < threshold,
            "iteration": iteration,
        }


def example2_quality_improvement():
    """Demonstrates a working single-node quality improvement cycle."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Quality Improvement (Single Node)")
    print("=" * 60)

    workflow = Workflow("quality-improvement", "example2")

    # Single node that both checks and improves
    workflow.add_node("checker", QualityCheckerNode())

    # Self-loop until quality threshold met
    workflow.connect(
        "checker",
        "checker",
        mapping={"quality": "quality"},
        cycle=True,
        max_iterations=10,
        convergence_check="quality >= 0.8",
        cycle_id="quality_loop",
    )

    # Execute
    executor = CyclicWorkflowExecutor()
    results, run_id = executor.execute(
        workflow, parameters={"checker": {"quality": 0.3, "threshold": 0.8}}
    )

    print(f"\nResults: Final quality = {results['checker']['quality']:.2f}")
    print(
        f"Status: {'✅ WORKING' if results['checker']['quality'] >= 0.8 else '❌ FAILED'}"
    )


# ============================================================================
# EXAMPLE 3: Multi-Node Cycle with Data Preservation (✅ FIXED)
# ============================================================================


class DataGeneratorNode(Node):
    """Generates data with initial quality."""

    def get_parameters(self):
        return {
            "size": NodeParameter(name="size", type=int, required=False, default=10),
        }

    def run(self, context, **kwargs):
        size = kwargs.get("size", 10)

        print(f"Generated {size} data points with quality 0.3")

        return {"data": list(range(size)), "quality": 0.3, "size": size}


class ProcessorNode(Node):
    """Processes data and improves quality through iterations."""

    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[]),
            "quality": NodeParameter(
                name="quality", type=float, required=False, default=0.0
            ),
            "increment": NodeParameter(
                name="increment", type=float, required=False, default=0.1
            ),
        }

    def run(self, context, **kwargs):
        # Get parameters - now properly propagated through cycles!
        data = kwargs.get("data", [])
        quality = kwargs.get("quality", 0.0)
        increment = kwargs.get("increment", 0.1)

        cycle_info = context.get("cycle", {})
        iteration = cycle_info.get("iteration", 0)

        print(f"\nProcessor iteration {iteration}:")
        print(f"  Received quality: {quality} (should increase each iteration)")
        print(f"  Data length: {len(data)} (should stay constant)")

        # Try to improve quality
        new_quality = quality + increment

        return {"data": data, "quality": new_quality, "improved": True}


def example3_multi_node_cycle():
    """Demonstrates multi-node cycle with data preservation (now fixed!)."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Multi-Node Cycle with Data Preservation")
    print("=" * 60)

    workflow = Workflow("known-issues", "example3")

    # Multi-node setup
    workflow.add_node("generator", DataGeneratorNode())
    workflow.add_node("processor", ProcessorNode(), increment=0.2)

    # Initial flow
    workflow.connect(
        "generator", "processor", mapping={"data": "data", "quality": "quality"}
    )

    # Cycle back to processor
    workflow.connect(
        "processor",
        "processor",
        mapping={"data": "data", "quality": "quality"},
        cycle=True,
        max_iterations=3,
        convergence_check="quality >= 0.9",
        cycle_id="process_loop",
    )

    # Execute
    executor = CyclicWorkflowExecutor()

    print("\nExpected: Quality should increase from 0.3 → 0.5 → 0.7 → 0.9")
    print("Actual: Watch the parameters propagate correctly through iterations!\n")

    results, run_id = executor.execute(workflow, parameters={"generator": {"size": 5}})

    final_quality = results.get("processor", {}).get("quality", 0.0)
    final_data = results.get("processor", {}).get("data", [])

    print(
        f"\nResults: Final quality = {final_quality:.1f}, Data preserved = {len(final_data) == 5}"
    )

    # Check if the fix worked (with floating point tolerance)
    if abs(final_quality - 0.9) < 0.01 and len(final_data) == 5:
        print("Status: ✅ FIXED - Parameters now propagating correctly!")
    else:
        print(
            f"Status: ❌ FAILED - Quality: {final_quality:.3f}, Data length: {len(final_data)}"
        )


# ============================================================================
# Summary and Next Steps
# ============================================================================


def print_summary():
    """Print summary of cyclic workflow status."""
    print("\n" + "=" * 60)
    print("CYCLIC WORKFLOWS - PHASE 1 STATUS SUMMARY")
    print("=" * 60)

    print("\n✅ WHAT WORKS (ALL FIXED!):")
    print("- Self-loop cycles with single nodes")
    print("- Multi-node cycles with data preservation")
    print("- Parameter propagation through cycle iterations")
    print("- Expression-based convergence conditions")
    print("- Maximum iteration safety limits")
    print("- Cycle detection and validation")
    print("- DAG nodes feeding into cycles")

    print("\n✅ ISSUES FIXED:")
    print("- NetworkX edge data preservation (multiple mappings)")
    print("- Initial parameters no longer skip node execution")
    print("- Runtime values properly propagate between iterations")

    print("\n📋 NEXT STEPS:")
    print("1. Phase 2.4: Create convergence & safety examples")
    print("2. Phase 2.5: Add comprehensive Phase 2 tests")
    print("3. Phase 3: Enhanced runtime integration")
    print("4. Update documentation with working examples")

    print("\n📚 REFERENCES:")
    print("- Mistake 058: Node Configuration vs Runtime Parameters")
    print("- Mistake 060: Incorrect Cycle State Access Patterns")
    print("- guide/features/cyclic_phase1_findings.md")


def main():
    """Run all examples."""
    print("CYCLIC WORKFLOW EXAMPLES - CONSOLIDATED")
    print("======================================")

    # Run working examples
    example1_simple_counter()
    example2_quality_improvement()

    # Demonstrate multi-node cycle (now fixed!)
    example3_multi_node_cycle()

    # Print summary
    print_summary()


if __name__ == "__main__":
    main()
