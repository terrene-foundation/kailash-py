#!/usr/bin/env python3
"""
Enhanced Error Messages Example - Phase 5.1.3 Implementation
===========================================================

This example demonstrates the enhanced error messaging system introduced in
Phase 5.1.3 of the cyclic workflow development. The new exception classes
provide actionable error messages with specific suggestions, context information,
and debugging guidance.

Key Features Demonstrated:
- Specialized exception classes with detailed context
- Actionable error messages with specific suggestions
- Error codes for programmatic error handling
- Enhanced debugging information and documentation links
- Comprehensive validation with detailed feedback
"""

from typing import Any

from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow import CycleConfig, CycleTemplates
from kailash.workflow.cycle_exceptions import (
    CycleConfigurationError,
    CycleConnectionError,
    create_configuration_error,
    create_connection_error,
)


class SimpleNode(Node):
    """Simple node for error demonstration."""

    def get_parameters(self):
        return {
            "input_value": NodeParameter(
                name="input_value", type=int, required=False, default=0
            )
        }

    def run(self, context: Any = None, **inputs) -> dict[str, Any]:
        return {"output": inputs.get("input_value", 0) * 2}


def demonstrate_configuration_errors():
    """Demonstrate enhanced configuration error messages."""
    print("=== Configuration Error Examples ===")

    # Test 1: Missing termination condition
    print("1. Missing termination condition:")
    try:
        CycleConfig()  # No termination condition
    except CycleConfigurationError as e:
        print(f"Error Code: {e.error_code}")
        print(f"Context: {e.context}")
        print(f"Suggestions: {len(e.suggestions)} provided")
        print(f"Message: {e.args[0]}")
        print()

    # Test 2: Negative iterations with enhanced error
    print("2. Negative max_iterations:")
    try:
        CycleConfig(max_iterations=-10)
    except CycleConfigurationError as e:
        print(f"Error Code: {e.error_code}")
        print(f"Context: {e.context}")
        print("Suggestions:")
        for suggestion in e.suggestions:
            print(f"  • {suggestion}")
        print()

    # Test 3: Unsafe convergence expression
    print("3. Unsafe convergence expression:")
    try:
        CycleConfig(
            max_iterations=10, convergence_check="import os; os.system('rm -rf /')"
        )
    except CycleConfigurationError as e:
        print(f"Error Code: {e.error_code}")
        print(f"Context: {e.context}")
        print(f"Documentation: {e.documentation_url}")
        print()

    # Test 4: Custom configuration error
    print("4. Custom configuration error with context:")
    try:
        error = create_configuration_error(
            "Custom validation failed",
            cycle_id="test_cycle",
            invalid_param1="bad_value",
            invalid_param2=42,
        )
        raise error
    except CycleConfigurationError as e:
        print(f"Detailed message:\n{e.get_detailed_message()}")
        print()


def demonstrate_connection_errors():
    """Demonstrate enhanced connection error messages."""
    print("=== Connection Error Examples ===")

    # Create a workflow with limited nodes
    workflow = Workflow("error-demo", "Error Demo")
    workflow.add_node("node1", SimpleNode())
    workflow.add_node("node2", SimpleNode())

    # Test 1: Missing source node
    print("1. Missing source node:")
    try:
        workflow.create_cycle("test").connect("missing_source", "node1").max_iterations(
            10
        ).build()
    except CycleConnectionError as e:
        print(f"Error Code: {e.error_code}")
        print(f"Context: {e.context}")
        print("Suggestions:")
        for suggestion in e.suggestions:
            print(f"  • {suggestion}")
        print()

    # Test 2: Missing target node
    print("2. Missing target node:")
    try:
        workflow.create_cycle("test2").connect(
            "node1", "missing_target"
        ).max_iterations(10).build()
    except CycleConnectionError as e:
        print(f"Error Code: {e.error_code}")
        print(f"Available nodes: {e.context.get('available_nodes')}")
        print()

    # Test 3: Custom connection error
    print("3. Custom connection error:")
    try:
        error = create_connection_error(
            "Parameter mapping validation failed",
            source_node="processor",
            target_node="validator",
            available_nodes=["reader", "writer", "processor"],
        )
        raise error
    except CycleConnectionError as e:
        print(f"Detailed message:\n{e.get_detailed_message()}")
        print()


def demonstrate_builder_errors():
    """Demonstrate CycleBuilder enhanced error handling."""
    print("=== CycleBuilder Error Examples ===")

    workflow = Workflow("builder-errors", "Builder Errors")
    workflow.add_node("processor", SimpleNode())

    # Test 1: Build without connection
    print("1. Build without connection:")
    try:
        workflow.create_cycle("incomplete").max_iterations(10).build()
    except CycleConfigurationError as e:
        print(f"Error: {e.args[0]}")
        print(f"Suggestions: {e.suggestions}")
        print()

    # Test 2: Invalid max_iterations with enhanced error
    print("2. Invalid max_iterations:")
    try:
        workflow.create_cycle("invalid_iterations").connect(
            "processor", "processor"
        ).max_iterations(-5).build()
    except CycleConfigurationError as e:
        print(f"Error Code: {e.error_code}")
        print(f"Context: {e.context}")
        print("Suggestions:")
        for suggestion in e.suggestions:
            print(f"  • {suggestion}")
        print()

    # Test 3: Empty convergence condition
    print("3. Empty convergence condition:")
    try:
        workflow.create_cycle("empty_convergence").connect(
            "processor", "processor"
        ).converge_when("").build()
    except CycleConfigurationError as e:
        print(f"Error: {e.args[0]}")
        print()


def demonstrate_error_codes_and_handling():
    """Demonstrate programmatic error handling with error codes."""
    print("=== Programmatic Error Handling ===")

    error_scenarios = [
        ("CYCLE_CONFIG_001", lambda: CycleConfig()),
        ("CYCLE_CONFIG_002", lambda: CycleConfig(max_iterations=-1)),
        (
            "CYCLE_CONN_001",
            lambda: create_connection_error(
                "Node not found", source_node="missing", available_nodes=["node1"]
            ),
        ),
    ]

    for expected_code, error_generator in error_scenarios:
        try:
            if callable(error_generator):
                if expected_code.startswith("CYCLE_CONN"):
                    raise error_generator()
                else:
                    error_generator()  # This should raise an exception
        except (CycleConfigurationError, CycleConnectionError) as e:
            print(f"Caught error code: {e.error_code}")
            print(f"Expected: {expected_code}")
            print(f"Match: {e.error_code == expected_code}")

            # Demonstrate programmatic handling
            if e.error_code == "CYCLE_CONFIG_001":
                print("→ Handler: Add default termination condition")
            elif e.error_code == "CYCLE_CONFIG_002":
                print("→ Handler: Reset to default max_iterations=100")
            elif e.error_code == "CYCLE_CONN_001":
                print("→ Handler: Show available nodes for selection")

            print()


def demonstrate_detailed_error_messages():
    """Demonstrate the detailed error message system."""
    print("=== Detailed Error Messages ===")

    # Create a complex error with full context
    try:
        raise CycleConfigurationError(
            "Complex cycle configuration validation failed",
            cycle_id="optimization_cycle",
            invalid_params={"max_iterations": -50, "timeout": -30, "memory_limit": 0},
            error_code="CYCLE_CONFIG_999",
            suggestions=[
                "Set max_iterations to a positive value (recommended: 10-100)",
                "Set timeout to a positive value in seconds (recommended: 30-300)",
                "Set memory_limit to a positive value in MB (recommended: 100-1000)",
                "Review cycle configuration documentation for valid parameter ranges",
            ],
            context={"workflow_id": "test_workflow", "node_count": 5},
        )
    except CycleConfigurationError as e:
        print("Standard message:")
        print(e.args[0])
        print("\nDetailed message:")
        print(e.get_detailed_message())
        print("\nContext data:")
        for key, value in e.context.items():
            print(f"  {key}: {value}")
        print()


def demonstrate_error_recovery_patterns():
    """Demonstrate error recovery patterns with enhanced errors."""
    print("=== Error Recovery Patterns ===")

    workflow = Workflow("recovery-demo", "Recovery Demo")
    workflow.add_node("processor", SimpleNode())

    # Recovery pattern 1: Configuration validation and auto-fix
    print("1. Configuration auto-recovery:")
    try:
        # This will fail
        CycleConfig(max_iterations=-10)
    except CycleConfigurationError as e:
        print(f"Original error: {e.args[0]}")

        # Auto-recovery based on suggestions
        if "positive" in e.args[0].lower():
            recovered_config = CycleConfig(max_iterations=100)
            print("Auto-recovered with: max_iterations=100")
            print(f"Recovery successful: {recovered_config}")
        print()

    # Recovery pattern 2: Connection validation and suggestion
    print("2. Connection error with suggestions:")
    try:
        workflow.create_cycle("test").connect(
            "nonexistent", "processor"
        ).max_iterations(10).build()
    except CycleConnectionError as e:
        print(f"Connection failed: {e.args[0]}")
        available = e.context.get("available_nodes", [])
        if available:
            print(f"Available alternatives: {', '.join(available)}")
            # Could auto-suggest the first available node
            suggested_node = available[0]
            print(f"Suggestion: Use '{suggested_node}' instead")
        print()

    # Recovery pattern 3: Template-based recovery
    print("3. Template-based error recovery:")
    try:
        # Create invalid configuration
        CycleConfig(max_iterations=-1, timeout=-10)
    except CycleConfigurationError as e:
        print(f"Invalid configuration: {e.args[0]}")

        # Recover using template
        template_config = CycleTemplates.optimization_loop(max_iterations=50)
        print(f"Recovered using template: {template_config}")
        print()


if __name__ == "__main__":
    print("Enhanced Error Messages Example - Phase 5.1.3")
    print("=" * 55)

    # Demonstrate different error types
    demonstrate_configuration_errors()
    demonstrate_connection_errors()
    demonstrate_builder_errors()

    # Demonstrate programmatic handling
    demonstrate_error_codes_and_handling()

    # Demonstrate detailed messages
    demonstrate_detailed_error_messages()

    # Demonstrate recovery patterns
    demonstrate_error_recovery_patterns()

    print("=" * 55)
    print("✅ All enhanced error message demonstrations completed!")
    print("\nKey Benefits of Phase 5.1.3:")
    print("• Actionable error messages with specific suggestions")
    print("• Error codes for programmatic error handling")
    print("• Detailed context information for debugging")
    print("• Documentation links for additional guidance")
    print("• Comprehensive validation with clear feedback")
    print("• Error recovery patterns and auto-suggestion capabilities")
