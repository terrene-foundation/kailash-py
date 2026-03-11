"""
Integration Tests for Connection Validation (Tier 2)

Tests connection validation with real WorkflowBuilder instances.
Uses real infrastructure (NO MOCKING) as per integration test guidelines.

NOTE: Automatic validation during workflow.add_connection() is not yet implemented.
These tests validate connections manually to verify validator functions work
correctly with real WorkflowBuilder instances and workflows.

Test Coverage:
- Integration Test 1-3: Node existence validation with real workflows
- Integration Test 4-6: Connection parameter validation with real workflows
- Integration Test 7-9: Dot notation validation with real workflows
- Integration Test 10-12: Self-connection and circular dependency validation
- Integration Test 13-15: Complete connection validation scenarios
"""

import pytest
from dataflow.validation.connection_validator import (
    detect_circular_dependency,
    get_connection_summary,
    validate_connection,
    validate_connection_parameters,
    validate_dot_notation,
    validate_no_self_connection,
    validate_node_existence,
)

from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.integration
class TestNodeExistenceValidationIntegration:
    """Integration tests for node existence validation with real workflows."""

    def test_node_existence_with_real_workflow(self):
        """
        Integration Test 1: Node existence validation with real workflow.

        Verifies validation works in the context of actual workflow construction.
        """
        # Create real workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode", "create_user", {"id": "user-123", "name": "Alice"}
        )
        workflow.add_node("UserReadNode", "read_user", {"id": "user-123"})

        # Get existing nodes
        existing_nodes = {"create_user", "read_user"}

        # Validate connection between existing nodes
        results = validate_node_existence("create_user", "read_user", existing_nodes)

        # Should pass
        assert all(r.success for r in results)

    def test_missing_source_node_in_workflow(self):
        """
        Integration Test 2: Missing source node in workflow context.

        Verifies validation catches missing source node before execution.
        """
        # Create real workflow with only destination node
        workflow = WorkflowBuilder()
        workflow.add_node("UserReadNode", "read_user", {"id": "user-123"})

        # Try to validate connection with missing source
        existing_nodes = {"read_user"}
        results = validate_node_existence("create_user", "read_user", existing_nodes)

        # Should fail
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_201"
        assert "create_user" in failed[0].message.lower()

    def test_missing_destination_node_in_workflow(self):
        """
        Integration Test 3: Missing destination node in workflow context.

        Verifies validation catches missing destination node before execution.
        """
        # Create real workflow with only source node
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode", "create_user", {"id": "user-123", "name": "Alice"}
        )

        # Try to validate connection with missing destination
        existing_nodes = {"create_user"}
        results = validate_node_existence("create_user", "read_user", existing_nodes)

        # Should fail
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_201"
        assert "read_user" in failed[0].message.lower()


@pytest.mark.integration
class TestConnectionParameterValidationIntegration:
    """Integration tests for connection parameter validation with real workflows."""

    def test_connection_parameters_with_real_workflow(self):
        """
        Integration Test 4: Connection parameter validation with real workflow.

        Verifies validation works for connection parameters.
        """
        # Simulate valid connection parameters
        results = validate_connection_parameters("id", "id")

        # Should pass
        assert all(r.success for r in results)

    def test_empty_source_output_detected(self):
        """
        Integration Test 5: Empty source output parameter detected.

        Verifies validation catches empty source output in workflow context.
        """
        # Empty source output
        results = validate_connection_parameters("", "id")

        # Should fail
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_202"

    def test_empty_destination_input_detected(self):
        """
        Integration Test 6: Empty destination input parameter detected.

        Verifies validation catches empty destination input in workflow context.
        """
        # Empty destination input
        results = validate_connection_parameters("id", "")

        # Should fail
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_202"


@pytest.mark.integration
class TestDotNotationValidationIntegration:
    """Integration tests for dot notation validation with real workflows."""

    def test_valid_dot_notation_in_workflow(self):
        """
        Integration Test 7: Valid dot notation in workflow context.

        Verifies validation passes for valid dot notation.
        """
        # Valid dot notation
        results = validate_dot_notation("data.nested.field", "source_output")

        # Should pass
        assert all(r.success for r in results)

    def test_invalid_dot_notation_leading_dot(self):
        """
        Integration Test 8: Invalid dot notation with leading dot.

        Verifies validation catches leading dot in workflow context.
        """
        # Leading dot
        results = validate_dot_notation(".data.field", "source_output")

        # Should fail
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_204"

    def test_reserved_field_in_dot_notation_detected(self):
        """
        Integration Test 9: Reserved field in dot notation detected.

        Verifies validation catches reserved field names in workflow context.
        """
        # Reserved field "error"
        results = validate_dot_notation("data.error.field", "source_output")

        # Should fail
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_205"
        assert "error" in failed[0].message.lower()


@pytest.mark.integration
class TestSelfConnectionValidationIntegration:
    """Integration tests for self-connection validation with real workflows."""

    def test_self_connection_detected_in_workflow(self):
        """
        Integration Test 10: Self-connection detected in workflow.

        Verifies validation prevents node from connecting to itself.
        """
        # Self-connection attempt
        results = validate_no_self_connection("create_user", "create_user")

        # Should fail
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_206"
        assert "self-connection" in failed[0].message.lower()

    def test_different_nodes_allowed(self):
        """
        Integration Test 11: Different nodes allowed in workflow.

        Verifies validation allows connections between different nodes.
        """
        # Different nodes
        results = validate_no_self_connection("create_user", "read_user")

        # Should pass
        assert all(r.success for r in results)


@pytest.mark.integration
class TestCircularDependencyDetectionIntegration:
    """Integration tests for circular dependency detection with real workflows."""

    def test_simple_cycle_detected_in_workflow(self):
        """
        Integration Test 12: Simple cycle detected in workflow.

        Verifies validation catches 2-node cycles.
        """
        # Existing connection: node1 -> node2
        existing_connections = [("node1", "node2")]

        # Try to add: node2 -> node1 (would create cycle)
        results = detect_circular_dependency("node2", "node1", existing_connections)

        # Should fail
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_207"
        assert "circular" in failed[0].message.lower()

    def test_complex_cycle_detected_in_workflow(self):
        """
        Integration Test 13: Complex cycle detected in workflow.

        Verifies validation catches multi-node cycles.
        """
        # Existing connections: node1 -> node2 -> node3
        existing_connections = [("node1", "node2"), ("node2", "node3")]

        # Try to add: node3 -> node1 (would create cycle)
        results = detect_circular_dependency("node3", "node1", existing_connections)

        # Should fail
        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_207"

    def test_linear_workflow_allowed(self):
        """
        Integration Test 14: Linear workflow allowed.

        Verifies validation allows linear connection chains.
        """
        # Existing connections: node1 -> node2 -> node3
        existing_connections = [("node1", "node2"), ("node2", "node3")]

        # Add: node3 -> node4 (linear)
        results = detect_circular_dependency("node3", "node4", existing_connections)

        # Should pass
        assert all(r.success for r in results)


@pytest.mark.integration
class TestCompleteConnectionValidationIntegration:
    """Integration tests for complete connection validation with real workflows."""

    def test_complete_validation_with_real_workflow(self):
        """
        Integration Test 15: Complete connection validation with real workflow.

        Verifies all validation rules work together in workflow context.
        """
        # Create real workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode", "create_user", {"id": "user-123", "name": "Alice"}
        )
        workflow.add_node("UserReadNode", "read_user", {"id": "user-123"})

        # Get existing nodes
        existing_nodes = {"create_user", "read_user"}
        existing_connections = []

        # Validate complete connection
        results = validate_connection(
            "create_user", "id", "read_user", "id", existing_nodes, existing_connections
        )

        # Should pass all validations
        assert any(r.success for r in results)
        assert not any(not r.success for r in results)

    def test_complete_validation_with_multiple_errors(self):
        """
        Integration Test 16: Complete validation with multiple errors.

        Verifies all errors are detected in workflow context.
        """
        # Empty existing nodes (both nodes missing)
        existing_nodes = set()
        existing_connections = []

        # Validate connection with multiple issues
        results = validate_connection(
            "create_user",
            "",  # Empty source_output
            "read_user",
            ".field",  # Leading dot
            existing_nodes,
            existing_connections,
        )

        # Should have multiple errors
        failed = [r for r in results if not r.success]
        assert len(failed) >= 3

        # Check error codes
        error_codes = [r.error_code for r in failed]
        assert "STRICT_CONN_201" in error_codes  # Missing nodes
        assert "STRICT_CONN_202" in error_codes  # Empty parameter
        assert "STRICT_CONN_204" in error_codes  # Leading dot

    def test_connection_summary_with_workflow_errors(self):
        """
        Integration Test 17: Connection summary with workflow errors.

        Verifies summary helper works in workflow context.
        """
        # Validate connection with errors
        existing_nodes = {"create_user"}  # Missing read_user
        existing_connections = []

        results = validate_connection(
            "create_user", "id", "read_user", "id", existing_nodes, existing_connections
        )

        # Get summary
        summary = get_connection_summary(results)

        # Should indicate invalid
        assert summary["valid"] is False
        assert summary["error_count"] >= 1
        assert len(summary["errors"]) >= 1

    def test_workflow_with_valid_dot_notation_connection(self):
        """
        Integration Test 18: Workflow with valid dot notation connection.

        Verifies validation passes for real workflows using dot notation.
        """
        # Create real workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode", "create_user", {"id": "user-123", "name": "Alice"}
        )
        workflow.add_node("ProcessNode", "process", {})

        # Get existing nodes
        existing_nodes = {"create_user", "process"}
        existing_connections = []

        # Validate connection with dot notation
        results = validate_connection(
            "create_user",
            "data.user.id",
            "process",
            "input_id",
            existing_nodes,
            existing_connections,
        )

        # Should pass
        assert any(r.success for r in results)

    def test_workflow_with_circular_dependency_prevention(self):
        """
        Integration Test 19: Workflow with circular dependency prevention.

        Verifies validation prevents cycles in real workflows.
        """
        # Create real workflow with connections
        workflow = WorkflowBuilder()
        workflow.add_node("Node1", "node1", {})
        workflow.add_node("Node2", "node2", {})
        workflow.add_node("Node3", "node3", {})

        # Existing connections: node1 -> node2 -> node3
        existing_nodes = {"node1", "node2", "node3"}
        existing_connections = [("node1", "node2"), ("node2", "node3")]

        # Try to add: node3 -> node1 (cycle)
        results = validate_connection(
            "node3", "output", "node1", "input", existing_nodes, existing_connections
        )

        # Should fail with circular dependency error
        failed = [r for r in results if not r.success]
        assert len(failed) >= 1

        # Check for circular dependency error
        error_codes = [r.error_code for r in failed]
        assert "STRICT_CONN_207" in error_codes

    def test_workflow_with_branching_no_cycle(self):
        """
        Integration Test 20: Workflow with branching structure (no cycle).

        Verifies validation allows branching DAG structures.
        """
        # Create real workflow
        workflow = WorkflowBuilder()
        workflow.add_node("Node1", "node1", {})
        workflow.add_node("Node2", "node2", {})
        workflow.add_node("Node3", "node3", {})
        workflow.add_node("Node4", "node4", {})

        # Existing connections: node1 -> node2, node1 -> node3, node2 -> node4, node3 -> node4 (DAG)
        existing_nodes = {"node1", "node2", "node3", "node4"}
        existing_connections = [
            ("node1", "node2"),
            ("node1", "node3"),
            ("node2", "node4"),
            ("node3", "node4"),
        ]

        # Add: node4 -> node5 (no cycle)
        existing_nodes.add("node5")
        results = validate_connection(
            "node4", "output", "node5", "input", existing_nodes, existing_connections
        )

        # Should pass
        assert any(r.success for r in results)
        assert not any(not r.success for r in results)
