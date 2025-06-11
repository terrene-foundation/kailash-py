#!/usr/bin/env python3
"""
Basic Cycle Builder Example - Phase 5.1.1 Implementation
========================================================

This example demonstrates the new CycleBuilder API introduced in Phase 5
of the cyclic workflow development. The CycleBuilder provides a fluent,
chainable interface for creating cycles with enhanced developer experience.

Key Features Demonstrated:
- Fluent builder pattern for cycle creation
- Method chaining for intuitive configuration
- Type-safe cycle configuration
- Enhanced error messages with actionable guidance
- Backward compatibility with existing connect() API (with deprecation warning)
"""

from typing import Any

from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime


class ProcessorNode(Node):
    """Simple processor node for cycle demonstration."""

    def get_parameters(self):
        return {
            "value": NodeParameter(
                name="value",
                type=float,
                required=False,
                default=0.0,
                description="Current value",
            ),
            "target": NodeParameter(
                name="target",
                type=float,
                required=False,
                default=10.0,
                description="Target value to reach",
            ),
            "iteration": NodeParameter(
                name="iteration",
                type=int,
                required=False,
                default=0,
                description="Current iteration count",
            ),
        }

    def run(self, context: Any = None, **inputs) -> dict[str, Any]:
        """Run method required by Node base class."""
        return self.execute(**inputs)

    def execute(
        self, value: float = 0.0, target: float = 10.0, iteration: int = 0
    ) -> dict[str, Any]:
        """Process value towards target."""
        # Simple improvement logic
        if value < target:
            improvement = (target - value) * 0.3  # 30% improvement per iteration
            new_value = min(value + improvement, target)
        else:
            new_value = value

        # Check convergence
        converged = abs(new_value - target) < 0.1

        return {
            "value": new_value,
            "target": target,
            "iteration": iteration + 1,
            "converged": converged,
            "improvement": new_value - value,
        }


def demonstrate_new_cycle_builder_api():
    """Demonstrate the new CycleBuilder API."""
    print("=== New CycleBuilder API (Phase 5.1.1) ===")

    # Create workflow
    workflow = Workflow("cycle-builder-demo", "Cycle Builder Demo")

    # Add nodes
    workflow.add_node("processor", ProcessorNode())

    # Create cycle using new fluent API
    print("Creating cycle using new CycleBuilder API...")
    workflow.create_cycle("optimization_loop").connect(
        "processor",
        "processor",
        {"value": "value", "target": "target", "iteration": "iteration"},
    ).max_iterations(10).converge_when("converged == True").timeout(30).build()

    print("✅ Cycle created successfully using CycleBuilder!")

    # Execute workflow
    runtime = LocalRuntime()
    print("\nExecuting workflow...")
    results, run_id = runtime.execute(
        workflow, parameters={"value": 1.0, "target": 10.0, "iteration": 0}
    )

    print(f"Results structure: {results}")
    final_result = results["processor"]
    print(
        f"Final result: value={final_result['value']:.2f}, iterations={final_result['iteration']}"
    )
    print(f"Converged: {final_result['converged']}")

    return workflow, results


def demonstrate_old_api_with_deprecation_warning():
    """Demonstrate the old API showing deprecation warning."""
    print("\n=== Old connect() API (shows deprecation warning) ===")

    # Create workflow
    workflow = Workflow("old-api-demo", "Old API Demo")

    # Add nodes
    workflow.add_node("processor", ProcessorNode())

    # Use old API - this will show deprecation warning
    print("Creating cycle using old connect() API (will show deprecation warning)...")

    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")  # Capture all warnings

        workflow.connect(
            "processor",
            "processor",
            mapping={"value": "value", "target": "target", "iteration": "iteration"},
            cycle=True,
            max_iterations=10,
            convergence_check="converged == True",
        )

        # Show captured deprecation warning
        if w:
            print(f"⚠️  Deprecation Warning: {w[0].message}")
        else:
            print("⚠️  Expected deprecation warning but none was captured")

    print("✅ Cycle created (but with deprecation warning)")

    return workflow


def demonstrate_builder_error_handling():
    """Demonstrate enhanced error handling in CycleBuilder."""
    print("\n=== CycleBuilder Error Handling ===")

    workflow = Workflow("error-demo", "Error Handling Demo")
    workflow.add_node("processor", ProcessorNode())

    # Test 1: Missing connection before build
    print("Testing error: build() without connect()...")
    try:
        workflow.create_cycle("incomplete").max_iterations(10).build()
    except Exception as e:
        print(f"✅ Caught expected error: {e}")

    # Test 2: Invalid max_iterations
    print("\nTesting error: negative max_iterations...")
    try:
        workflow.create_cycle("invalid").connect(
            "processor", "processor"
        ).max_iterations(-5).build()
    except Exception as e:
        print(f"✅ Caught expected error: {e}")

    # Test 3: Empty convergence condition
    print("\nTesting error: empty convergence condition...")
    try:
        workflow.create_cycle("empty").connect("processor", "processor").converge_when(
            ""
        ).build()
    except Exception as e:
        print(f"✅ Caught expected error: {e}")

    # Test 4: Missing termination condition
    print("\nTesting error: no termination condition...")
    try:
        workflow.create_cycle("no_termination").connect(
            "processor", "processor"
        ).build()
    except Exception as e:
        print(f"✅ Caught expected error: {e}")


def demonstrate_advanced_builder_features():
    """Demonstrate advanced CycleBuilder features."""
    print("\n=== Advanced CycleBuilder Features ===")

    workflow = Workflow("advanced-demo", "Advanced Builder Demo")
    workflow.add_node("processor", ProcessorNode())

    # Advanced cycle with multiple features
    print("Creating advanced cycle with timeout, memory limit, and conditions...")
    workflow.create_cycle("advanced_optimization").connect(
        "processor", "processor"
    ).max_iterations(50).converge_when("converged == True").timeout(60.0).memory_limit(
        512
    ).when(
        "iteration < 100"
    ).build()

    print("✅ Advanced cycle created successfully!")

    # Show builder representation
    builder = (
        workflow.create_cycle("representation_demo")
        .connect("processor", "processor")
        .max_iterations(25)
    )

    print(f"Builder representation: {builder}")


if __name__ == "__main__":
    print("Cycle Builder API Example - Phase 5.1.1")
    print("=" * 50)

    # Demonstrate new API
    workflow1, results1 = demonstrate_new_cycle_builder_api()

    # Demonstrate old API with deprecation warning
    workflow2 = demonstrate_old_api_with_deprecation_warning()

    # Demonstrate error handling
    demonstrate_builder_error_handling()

    # Demonstrate advanced features
    demonstrate_advanced_builder_features()

    print("\n" + "=" * 50)
    print("✅ All CycleBuilder API demonstrations completed!")
    print("\nKey Benefits of Phase 5.1.1:")
    print("• Fluent, chainable API for intuitive cycle creation")
    print("• Enhanced error messages with actionable guidance")
    print("• Type safety and IDE auto-completion support")
    print("• Backward compatibility with deprecation warnings")
    print("• Comprehensive validation and safety features")
