#!/usr/bin/env python3
"""
Type-Safe Cycle Configuration Example - Phase 5.1.2 Implementation
=================================================================

This example demonstrates the type-safe CycleConfig system introduced in
Phase 5.1.2 of the cyclic workflow development. The CycleConfig provides
structured, validated configuration objects for cycle creation with full
IDE support and runtime validation.

Key Features Demonstrated:
- Type-safe cycle configuration with dataclasses
- Comprehensive validation with actionable error messages
- Configuration templates for common patterns
- Configuration merging and inheritance
- Integration with CycleBuilder API
- Serialization and deserialization support
"""

from typing import Any, Dict

from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.workflow import CycleBuilder, CycleConfig, CycleTemplates


class OptimizationNode(Node):
    """Node for optimization demonstration."""

    def get_parameters(self):
        return {
            "value": NodeParameter(
                name="value", type=float, required=False, default=0.0
            ),
            "target": NodeParameter(
                name="target", type=float, required=False, default=100.0
            ),
            "iteration": NodeParameter(
                name="iteration", type=int, required=False, default=0
            ),
            "quality": NodeParameter(
                name="quality", type=float, required=False, default=0.0
            ),
        }

    def run(self, context: Any = None, **inputs) -> Dict[str, Any]:
        """Run optimization step."""
        value = inputs.get("value", 0.0)
        target = inputs.get("target", 100.0)
        iteration = inputs.get("iteration", 0)

        # Simulate optimization progress
        improvement = (target - value) * 0.2
        new_value = min(value + improvement, target)
        quality = new_value / target if target > 0 else 0.0

        return {
            "value": new_value,
            "target": target,
            "iteration": iteration + 1,
            "quality": quality,
            "improvement": improvement,
        }


def demonstrate_cycle_config_basics():
    """Demonstrate basic CycleConfig usage."""
    print("=== CycleConfig Basics ===")

    # Create basic configuration
    config = CycleConfig(
        max_iterations=50,
        convergence_check="quality > 0.95",
        timeout=120.0,
        cycle_id="optimization_cycle",
        description="Basic optimization cycle",
    )

    print(f"Created config: {config}")
    print(f"Config dict: {config.to_dict()}")
    print(f"Effective max iterations: {config.get_effective_max_iterations()}")

    return config


def demonstrate_cycle_templates():
    """Demonstrate pre-built configuration templates."""
    print("\n=== CycleConfig Templates ===")

    # Optimization template
    opt_config = CycleTemplates.optimization_loop(
        max_iterations=100, convergence_threshold=0.01
    )
    print(f"Optimization template: {opt_config}")

    # Retry template
    retry_config = CycleTemplates.retry_cycle(max_retries=5)
    print(f"Retry template: {retry_config}")

    # Data quality template
    quality_config = CycleTemplates.data_quality_cycle(quality_threshold=0.98)
    print(f"Data quality template: {quality_config}")

    # Training loop template
    training_config = CycleTemplates.training_loop(max_epochs=200)
    print(f"Training template: {training_config}")

    return opt_config, retry_config, quality_config, training_config


def demonstrate_config_validation():
    """Demonstrate configuration validation and error handling."""
    print("\n=== CycleConfig Validation ===")

    # Test valid configuration
    try:
        valid_config = CycleConfig(max_iterations=100, timeout=60.0)
        print(f"✅ Valid config created: {valid_config}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

    # Test invalid configurations with detailed error messages
    test_cases = [
        ("Negative iterations", {"max_iterations": -10}),
        ("Empty convergence", {"convergence_check": ""}),
        ("No termination", {}),
        (
            "Unsafe expression",
            {"convergence_check": "import os; os.system('rm -rf /')"},
        ),
        ("Invalid timeout", {"timeout": -30}),
        ("Invalid memory limit", {"memory_limit": -512}),
    ]

    for description, invalid_params in test_cases:
        print(f"\nTesting: {description}")
        try:
            invalid_config = CycleConfig(**invalid_params)
            print(f"❌ Expected error but config was created: {invalid_config}")
        except Exception as e:
            print(f"✅ Caught expected error: {e}")


def demonstrate_config_merging():
    """Demonstrate configuration merging and inheritance."""
    print("\n=== CycleConfig Merging ===")

    # Base configuration
    base_config = CycleConfig(max_iterations=100, timeout=300.0, cycle_id="base_cycle")

    # Override configuration
    override_config = CycleConfig(
        convergence_check="quality > 0.9",
        memory_limit=1024,
        cycle_id="customized_cycle",
    )

    # Merge configurations
    merged_config = base_config.merge(override_config)

    print(f"Base config: {base_config}")
    print(f"Override config: {override_config}")
    print(f"Merged config: {merged_config}")

    # Show that merged has all parameters
    print(f"Merged has max_iterations: {merged_config.max_iterations}")
    print(f"Merged has convergence_check: {merged_config.convergence_check}")
    print(f"Merged has memory_limit: {merged_config.memory_limit}")
    print(f"Merged cycle_id: {merged_config.cycle_id}")

    return merged_config


def demonstrate_config_serialization():
    """Demonstrate configuration serialization and templates."""
    print("\n=== CycleConfig Serialization ===")

    # Create configuration
    config = CycleConfig(
        max_iterations=75,
        convergence_check="error < 0.001",
        timeout=180.0,
        memory_limit=2048,
        description="High-precision optimization cycle",
    )

    # Serialize to dictionary
    config_dict = config.to_dict()
    print(f"Serialized config: {config_dict}")

    # Deserialize from dictionary
    restored_config = CycleConfig.from_dict(config_dict)
    print(f"Restored config: {restored_config}")

    # Create reusable template
    template = config.create_template("high_precision_optimization")
    print(f"Created template: {template['template_name']}")
    print(f"Template description: {template['description']}")

    return restored_config, template


def demonstrate_cycle_builder_integration():
    """Demonstrate CycleConfig integration with CycleBuilder."""
    print("\n=== CycleBuilder + CycleConfig Integration ===")

    # Create workflow
    workflow = Workflow("config-integration", "CycleConfig Integration")
    workflow.add_node("optimizer", OptimizationNode())

    # Method 1: Using CycleBuilder.from_config()
    print("Method 1: CycleBuilder.from_config()")
    config1 = CycleTemplates.optimization_loop(max_iterations=30)

    builder1 = CycleBuilder.from_config(workflow, config1)
    builder1.connect(
        "optimizer",
        "optimizer",
        {
            "value": "value",
            "target": "target",
            "iteration": "iteration",
            "quality": "quality",
        },
    ).build()

    print("✅ Cycle created using from_config()")

    # Method 2: Using apply_config()
    print("\nMethod 2: Builder with apply_config()")
    config2 = CycleConfig(max_iterations=25, timeout=90.0)

    workflow.create_cycle("custom_optimization").connect(
        "optimizer",
        "optimizer",
        {
            "value": "value",
            "target": "target",
            "iteration": "iteration",
            "quality": "quality",
        },
    ).apply_config(config2).converge_when("quality > 0.85").build()

    print("✅ Cycle created using apply_config()")

    return workflow


def demonstrate_workflow_execution():
    """Demonstrate executing workflow with type-safe configuration."""
    print("\n=== Workflow Execution with CycleConfig ===")

    # Create workflow with optimized configuration
    workflow = Workflow("optimized-execution", "Optimized Execution")
    workflow.add_node("optimizer", OptimizationNode())

    # Use optimization template with custom parameters
    config = CycleTemplates.optimization_loop(
        max_iterations=20, convergence_threshold=0.05  # 5% improvement threshold
    )

    # Create cycle using configuration
    CycleBuilder.from_config(workflow, config).connect(
        "optimizer",
        "optimizer",
        {
            "value": "value",
            "target": "target",
            "iteration": "iteration",
            "quality": "quality",
        },
    ).build()

    # Execute workflow
    runtime = LocalRuntime()
    print("Executing optimized workflow...")

    results, run_id = runtime.execute(
        workflow,
        parameters={"value": 10.0, "target": 100.0, "iteration": 0, "quality": 0.0},
    )

    final_result = results["optimizer"]
    print(
        f"Final result: value={final_result['value']:.2f}, quality={final_result['quality']:.3f}"
    )
    print(f"Iterations: {final_result['iteration']}")

    return results


if __name__ == "__main__":
    print("Type-Safe Cycle Configuration Example - Phase 5.1.2")
    print("=" * 60)

    # Demonstrate basic usage
    basic_config = demonstrate_cycle_config_basics()

    # Demonstrate templates
    templates = demonstrate_cycle_templates()

    # Demonstrate validation
    demonstrate_config_validation()

    # Demonstrate merging
    merged_config = demonstrate_config_merging()

    # Demonstrate serialization
    restored_config, template = demonstrate_config_serialization()

    # Demonstrate integration with CycleBuilder
    integrated_workflow = demonstrate_cycle_builder_integration()

    # Demonstrate execution
    execution_results = demonstrate_workflow_execution()

    print("\n" + "=" * 60)
    print("✅ All CycleConfig demonstrations completed!")
    print("\nKey Benefits of Phase 5.1.2:")
    print("• Type-safe configuration with full IDE support")
    print("• Comprehensive validation with actionable error messages")
    print("• Reusable templates for common cycle patterns")
    print("• Configuration merging and inheritance capabilities")
    print("• Seamless integration with CycleBuilder API")
    print("• Serialization support for configuration persistence")
