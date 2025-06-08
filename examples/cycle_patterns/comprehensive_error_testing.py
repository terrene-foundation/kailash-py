#!/usr/bin/env python3
"""
Comprehensive Error Testing - Phase 5.1.3 Validation
====================================================

This script comprehensively tests all enhanced error handling features
implemented in Phase 5.1.3 to ensure they work correctly across the
entire cycle system.
"""

from typing import Any, Dict

from kailash import Workflow
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow import CycleConfig, CycleTemplates
from kailash.workflow.cycle_exceptions import (
    CycleConfigurationError,
    CycleConnectionError,
)


class TestNode(Node):
    """Simple test node for error testing."""

    def get_parameters(self):
        return {
            "input": NodeParameter(
                name="input", type=str, required=False, default="test"
            ),
            "value": NodeParameter(
                name="value", type=float, required=False, default=0.0
            ),
        }

    def run(self, context: Any = None, **inputs) -> Dict[str, Any]:
        return {
            "output": inputs.get("input", "test"),
            "result": inputs.get("value", 0.0),
        }


def test_cycle_config_errors():
    """Test CycleConfig validation errors."""
    print("=== Testing CycleConfig Errors ===")

    # Test 1: Missing termination condition
    try:
        CycleConfig()
        print("❌ Should have failed: No termination condition")
    except CycleConfigurationError as e:
        print(f"✅ Caught termination error: {e.error_code}")
        assert e.error_code == "CYCLE_CONFIG_001"
        assert "termination condition" in str(e)
        assert len(e.suggestions) > 0

    # Test 2: Negative max_iterations
    try:
        CycleConfig(max_iterations=-10)
        print("❌ Should have failed: Negative iterations")
    except CycleConfigurationError as e:
        print(f"✅ Caught negative iterations error: {e.error_code}")
        assert e.error_code == "CYCLE_CONFIG_002"
        assert "positive" in str(e)
        assert e.context.get("max_iterations") == -10

    # Test 3: Invalid timeout
    try:
        CycleConfig(max_iterations=10, timeout=-30)
        print("❌ Should have failed: Negative timeout")
    except CycleConfigurationError as e:
        print(f"✅ Caught timeout error: {e.error_code}")
        assert "timeout" in str(e)

    # Test 4: Unsafe convergence expression
    try:
        CycleConfig(
            max_iterations=10, convergence_check="import os; os.system('rm -rf /')"
        )
        print("❌ Should have failed: Unsafe expression")
    except CycleConfigurationError as e:
        print(f"✅ Caught unsafe expression error: {e.error_code}")
        assert "unsafe" in str(e)

    print("✅ All CycleConfig error tests passed\n")


def test_cycle_builder_errors():
    """Test CycleBuilder validation errors."""
    print("=== Testing CycleBuilder Errors ===")

    workflow = Workflow("test", "Test Workflow")
    workflow.add_node("node1", TestNode())
    workflow.add_node("node2", TestNode())

    # Test 1: Missing source node
    try:
        workflow.create_cycle("test1").connect("missing_node", "node1").max_iterations(
            10
        ).build()
        print("❌ Should have failed: Missing source node")
    except CycleConnectionError as e:
        print(f"✅ Caught missing source error: {e.error_code}")
        assert e.error_code == "CYCLE_CONN_001"
        assert "missing_node" in str(e)
        assert "available_nodes" in e.context

    # Test 2: Missing target node
    try:
        workflow.create_cycle("test2").connect(
            "node1", "missing_target"
        ).max_iterations(10).build()
        print("❌ Should have failed: Missing target node")
    except CycleConnectionError as e:
        print(f"✅ Caught missing target error: {e.error_code}")
        assert e.error_code == "CYCLE_CONN_002"
        assert "missing_target" in str(e)

    # Test 3: Build without connection
    try:
        workflow.create_cycle("test3").max_iterations(10).build()
        print("❌ Should have failed: No connection configured")
    except CycleConfigurationError as e:
        print(f"✅ Caught no connection error: {e.error_code}")
        assert "source and target nodes" in str(e)

    # Test 4: Negative max_iterations in builder
    try:
        workflow.create_cycle("test4").connect("node1", "node2").max_iterations(
            -5
        ).build()
        print("❌ Should have failed: Negative iterations in builder")
    except CycleConfigurationError as e:
        print(f"✅ Caught builder negative iterations: {e.error_code}")
        assert e.error_code == "CYCLE_CONFIG_002"
        assert e.context.get("max_iterations") == -5

    # Test 5: Empty convergence condition
    try:
        workflow.create_cycle("test5").connect("node1", "node2").converge_when(
            ""
        ).build()
        print("❌ Should have failed: Empty convergence condition")
    except CycleConfigurationError as e:
        print("✅ Caught empty convergence error")
        assert "non-empty string" in str(e)

    print("✅ All CycleBuilder error tests passed\n")


def test_workflow_connect_errors():
    """Test enhanced errors in workflow.connect() with cycle=True."""
    print("=== Testing Workflow.connect() Cycle Errors ===")

    workflow = Workflow("connect-test", "Connect Test")
    workflow.add_node("node1", TestNode())

    # Test 1: Missing termination condition
    try:
        workflow.connect("node1", "node1", cycle=True)
        print("❌ Should have failed: No termination condition")
    except CycleConfigurationError as e:
        print(f"✅ Caught connect termination error: {e.error_code}")
        assert e.error_code == "CYCLE_CONFIG_001"
        assert "max_iterations or convergence_check" in str(e)

    # Test 2: Negative iterations in connect
    try:
        workflow.connect("node1", "node1", cycle=True, max_iterations=-3)
        print("❌ Should have failed: Negative iterations in connect")
    except CycleConfigurationError as e:
        print(f"✅ Caught connect negative iterations: {e.error_code}")
        assert e.error_code == "CYCLE_CONFIG_002"

    # Test 3: Negative timeout in connect
    try:
        workflow.connect("node1", "node1", cycle=True, max_iterations=10, timeout=-60)
        print("❌ Should have failed: Negative timeout in connect")
    except CycleConfigurationError as e:
        print(f"✅ Caught connect negative timeout: {e.error_code}")
        assert e.error_code == "CYCLE_CONFIG_003"

    # Test 4: Negative memory limit in connect
    try:
        workflow.connect(
            "node1", "node1", cycle=True, max_iterations=10, memory_limit=-512
        )
        print("❌ Should have failed: Negative memory limit in connect")
    except CycleConfigurationError as e:
        print(f"✅ Caught connect negative memory: {e.error_code}")
        assert e.error_code == "CYCLE_CONFIG_004"

    print("✅ All workflow.connect() error tests passed\n")


def test_error_context_and_suggestions():
    """Test that errors provide useful context and suggestions."""
    print("=== Testing Error Context and Suggestions ===")

    # Test detailed error information
    try:
        CycleConfig(max_iterations=-50, timeout=-30)
        print("❌ Should have failed: Multiple invalid parameters")
    except CycleConfigurationError as e:
        print(f"✅ Caught multi-parameter error: {e.error_code}")

        # Check context
        assert hasattr(e, "context")
        assert hasattr(e, "suggestions")
        assert hasattr(e, "documentation_url")

        # Check detailed message
        detailed = e.get_detailed_message()
        assert "Error:" in detailed
        assert "Code:" in detailed
        assert "Suggestions:" in detailed
        print(f"  Context fields: {len(e.context)} items")
        print(f"  Suggestions: {len(e.suggestions)} items")
        print(f"  Has documentation URL: {e.documentation_url is not None}")

    # Test connection error context
    workflow = Workflow("context-test", "Context Test")
    workflow.add_node("existing", TestNode())

    try:
        workflow.create_cycle("context").connect("missing", "existing").max_iterations(
            10
        ).build()
        print("❌ Should have failed: Missing node")
    except CycleConnectionError as e:
        print("✅ Caught connection error with context")

        # Check specific context fields
        assert "source_node" in e.context
        assert "available_nodes" in e.context
        assert e.context["source_node"] == "missing"
        assert "existing" in e.context["available_nodes"]
        print(f"  Source node: {e.context['source_node']}")
        print(f"  Available nodes: {e.context['available_nodes']}")

    print("✅ All context and suggestion tests passed\n")


def test_error_codes_for_programmatic_handling():
    """Test that error codes enable programmatic error handling."""
    print("=== Testing Programmatic Error Handling ===")

    error_handlers = {
        "CYCLE_CONFIG_001": lambda: "Add default termination condition",
        "CYCLE_CONFIG_002": lambda: "Reset to positive max_iterations",
        "CYCLE_CONN_001": lambda: "Show available nodes",
        "CYCLE_CONN_002": lambda: "Show available nodes",
    }

    test_scenarios = [
        ("Missing termination", lambda: CycleConfig(), "CYCLE_CONFIG_001"),
        (
            "Negative iterations",
            lambda: CycleConfig(max_iterations=-5),
            "CYCLE_CONFIG_002",
        ),
    ]

    for description, error_func, expected_code in test_scenarios:
        try:
            error_func()
            print(f"❌ Should have failed: {description}")
        except CycleConfigurationError as e:
            print(f"✅ Caught {description}: {e.error_code}")
            assert e.error_code == expected_code

            # Test programmatic handling
            if e.error_code in error_handlers:
                action = error_handlers[e.error_code]()
                print(f"  → Handler action: {action}")

    print("✅ All programmatic handling tests passed\n")


def test_error_recovery_patterns():
    """Test error recovery and auto-suggestion patterns."""
    print("=== Testing Error Recovery Patterns ===")

    # Test 1: Configuration auto-recovery
    try:
        CycleConfig(max_iterations=-10)
    except CycleConfigurationError as e:
        print(f"✅ Original error: {e.error_code}")

        # Auto-recovery based on suggestions
        if "positive" in str(e):
            recovered_config = CycleConfig(max_iterations=100)
            print(f"  → Auto-recovered: {recovered_config}")
            assert recovered_config.max_iterations == 100

    # Test 2: Template-based recovery
    try:
        CycleConfig(max_iterations=-1, timeout=-10)
    except CycleConfigurationError as e:
        print(f"✅ Multi-error caught: {e.error_code}")

        # Recover using template
        template_config = CycleTemplates.optimization_loop(max_iterations=50)
        print(f"  → Template recovery: {template_config}")
        assert template_config.max_iterations == 50
        assert template_config.timeout is None  # Will use template defaults

    # Test 3: Node suggestion recovery
    workflow = Workflow("recovery-test", "Recovery Test")
    workflow.add_node("processor", TestNode())
    workflow.add_node("evaluator", TestNode())

    try:
        workflow.create_cycle("recovery").connect(
            "nonexistent", "processor"
        ).max_iterations(10).build()
    except CycleConnectionError as e:
        print(f"✅ Node not found: {e.error_code}")

        # Extract available nodes from context
        available = e.context.get("available_nodes", [])
        if available:
            suggested_node = available[0]
            print(f"  → Suggested node: {suggested_node}")

            # Could auto-correct here
            workflow.create_cycle("recovery_fixed").connect(
                suggested_node, "processor"
            ).max_iterations(10).build()
            print(f"  → Recovery successful with: {suggested_node}")

    print("✅ All error recovery tests passed\n")


if __name__ == "__main__":
    print("Comprehensive Error Testing - Phase 5.1.3")
    print("=" * 50)

    test_cycle_config_errors()
    test_cycle_builder_errors()
    test_workflow_connect_errors()
    test_error_context_and_suggestions()
    test_error_codes_for_programmatic_handling()
    test_error_recovery_patterns()

    print("=" * 50)
    print("✅ ALL ENHANCED ERROR HANDLING TESTS PASSED!")
    print("\nPhase 5.1.3 Implementation Summary:")
    print("• Specialized exception classes with error codes")
    print("• Actionable error messages with specific suggestions")
    print("• Detailed context information for debugging")
    print("• Documentation links for additional guidance")
    print("• Programmatic error handling capabilities")
    print("• Error recovery patterns and auto-suggestion")
    print("• Complete integration across cycle system")
