"""
Unit Tests for Connection Validation (Tier 1)

Tests connection validation logic in isolation without real workflows.
Follows 3-tier testing strategy with mocking allowed for unit tests.

Test Coverage:
- Unit Test 1-5: Node existence validation
- Unit Test 6-10: Connection parameter validation
- Unit Test 11-18: Dot notation validation
- Unit Test 19-21: Self-connection validation
- Unit Test 22-26: Circular dependency detection
- Unit Test 27-30: Complete connection validation
"""

import pytest
from dataflow.validation.connection_validator import (
    ConnectionValidationResult,
    detect_circular_dependency,
    get_connection_summary,
    validate_connection,
    validate_connection_parameters,
    validate_dot_notation,
    validate_no_self_connection,
    validate_node_existence,
)


class TestNodeExistenceValidation:
    """Unit tests for node existence validation (STRICT_CONN_201)."""

    def test_both_nodes_exist(self):
        """
        Unit Test 1: Both source and destination nodes exist.

        Verifies validation passes when both nodes are in workflow.
        """
        existing_nodes = {"node1", "node2", "node3"}
        results = validate_node_existence("node1", "node2", existing_nodes)

        assert all(r.success for r in results)

    def test_source_node_missing(self):
        """
        Unit Test 2: Source node does not exist.

        Verifies validation catches missing source node.
        """
        existing_nodes = {"node2", "node3"}
        results = validate_node_existence("node1", "node2", existing_nodes)

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_201"
        assert "node1" in failed[0].message.lower()
        assert "source" in failed[0].message.lower()

    def test_destination_node_missing(self):
        """
        Unit Test 3: Destination node does not exist.

        Verifies validation catches missing destination node.
        """
        existing_nodes = {"node1", "node3"}
        results = validate_node_existence("node1", "node2", existing_nodes)

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_201"
        assert "node2" in failed[0].message.lower()
        assert "destination" in failed[0].message.lower()

    def test_both_nodes_missing(self):
        """
        Unit Test 4: Both source and destination nodes missing.

        Verifies validation catches both missing nodes.
        """
        existing_nodes = {"node3"}
        results = validate_node_existence("node1", "node2", existing_nodes)

        failed = [r for r in results if not r.success]
        assert len(failed) == 2
        assert all(r.error_code == "STRICT_CONN_201" for r in failed)

    def test_empty_node_set(self):
        """
        Unit Test 5: No nodes exist in workflow.

        Verifies validation catches missing nodes when workflow is empty.
        """
        existing_nodes = set()
        results = validate_node_existence("node1", "node2", existing_nodes)

        failed = [r for r in results if not r.success]
        assert len(failed) == 2


class TestConnectionParameterValidation:
    """Unit tests for connection parameter validation (STRICT_CONN_202-203)."""

    def test_valid_parameters(self):
        """
        Unit Test 6: Valid source and destination parameters.

        Verifies validation passes with valid parameters.
        """
        results = validate_connection_parameters("output_field", "input_field")

        assert all(r.success for r in results)

    def test_empty_source_output(self):
        """
        Unit Test 7: Empty source_output parameter.

        Verifies validation catches empty source_output.
        """
        results = validate_connection_parameters("", "input_field")

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_202"
        assert "source output" in failed[0].message.lower()

    def test_empty_destination_input(self):
        """
        Unit Test 8: Empty destination_input parameter.

        Verifies validation catches empty destination_input.
        """
        results = validate_connection_parameters("output_field", "")

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_202"
        assert "destination input" in failed[0].message.lower()

    def test_both_parameters_empty(self):
        """
        Unit Test 9: Both parameters empty.

        Verifies validation catches both empty parameters.
        """
        results = validate_connection_parameters("", "")

        failed = [r for r in results if not r.success]
        assert len(failed) == 2
        assert all(r.error_code == "STRICT_CONN_202" for r in failed)

    def test_none_parameters(self):
        """
        Unit Test 10: None parameters.

        Verifies validation catches None parameters.
        """
        results = validate_connection_parameters(None, "input_field")

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_202"


class TestDotNotationValidation:
    """Unit tests for dot notation validation (STRICT_CONN_204-205)."""

    def test_simple_field_no_dot_notation(self):
        """
        Unit Test 11: Simple field without dot notation.

        Verifies validation passes for simple field names.
        """
        results = validate_dot_notation("output_field", "source_output")

        assert all(r.success for r in results)

    def test_valid_dot_notation(self):
        """
        Unit Test 12: Valid dot notation.

        Verifies validation passes for valid dot notation.
        """
        results = validate_dot_notation("data.field", "source_output")

        assert all(r.success for r in results)

    def test_nested_dot_notation(self):
        """
        Unit Test 13: Nested dot notation.

        Verifies validation passes for nested dot notation.
        """
        results = validate_dot_notation("data.nested.field", "source_output")

        assert all(r.success for r in results)

    def test_leading_dot(self):
        """
        Unit Test 14: Dot notation with leading dot.

        Verifies validation catches leading dot.
        """
        results = validate_dot_notation(".data.field", "source_output")

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_204"
        assert "leading" in failed[0].message.lower()

    def test_trailing_dot(self):
        """
        Unit Test 15: Dot notation with trailing dot.

        Verifies validation catches trailing dot.
        """
        results = validate_dot_notation("data.field.", "source_output")

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_204"
        assert "trailing" in failed[0].message.lower()

    def test_consecutive_dots(self):
        """
        Unit Test 16: Dot notation with consecutive dots.

        Verifies validation catches consecutive dots.
        """
        results = validate_dot_notation("data..field", "source_output")

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_204"
        assert "consecutive" in failed[0].message.lower()

    def test_reserved_field_in_dot_notation(self):
        """
        Unit Test 17: Reserved field in dot notation.

        Verifies validation catches reserved field names.
        """
        results = validate_dot_notation("data.error.field", "source_output")

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_205"
        assert "reserved" in failed[0].message.lower()
        assert "error" in failed[0].message.lower()

    def test_reserved_field_first_part(self):
        """
        Unit Test 18: Reserved field as first part of dot notation.

        Verifies validation catches reserved field at start.
        """
        results = validate_dot_notation("error.data", "source_output")

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_205"


class TestSelfConnectionValidation:
    """Unit tests for self-connection validation (STRICT_CONN_206)."""

    def test_different_nodes(self):
        """
        Unit Test 19: Source and destination are different nodes.

        Verifies validation passes when nodes are different.
        """
        results = validate_no_self_connection("node1", "node2")

        assert all(r.success for r in results)

    def test_self_connection(self):
        """
        Unit Test 20: Source and destination are same node.

        Verifies validation catches self-connection.
        """
        results = validate_no_self_connection("node1", "node1")

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_206"
        assert "self-connection" in failed[0].message.lower()
        assert "node1" in failed[0].message.lower()

    def test_self_connection_with_whitespace(self):
        """
        Unit Test 21: Self-connection with exact string match.

        Verifies validation uses exact string comparison.
        """
        results = validate_no_self_connection("node1", "node1")

        assert any(not r.success for r in results)


class TestCircularDependencyDetection:
    """Unit tests for circular dependency detection (STRICT_CONN_207)."""

    def test_no_existing_connections(self):
        """
        Unit Test 22: No existing connections in workflow.

        Verifies validation passes when workflow has no connections.
        """
        results = detect_circular_dependency("node1", "node2", [])

        assert all(r.success for r in results)

    def test_linear_connections(self):
        """
        Unit Test 23: Linear connection chain (no cycle).

        Verifies validation passes for linear chains.
        """
        existing = [("node1", "node2"), ("node2", "node3")]
        results = detect_circular_dependency("node3", "node4", existing)

        assert all(r.success for r in results)

    def test_simple_cycle_detection(self):
        """
        Unit Test 24: Simple cycle detection (A -> B, B -> A).

        Verifies validation catches simple 2-node cycle.
        """
        existing = [("node1", "node2")]
        results = detect_circular_dependency("node2", "node1", existing)

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_207"
        assert "circular" in failed[0].message.lower()

    def test_complex_cycle_detection(self):
        """
        Unit Test 25: Complex cycle detection (A -> B -> C -> A).

        Verifies validation catches multi-node cycles.
        """
        existing = [("node1", "node2"), ("node2", "node3")]
        results = detect_circular_dependency("node3", "node1", existing)

        assert any(not r.success for r in results)
        failed = [r for r in results if not r.success]
        assert failed[0].error_code == "STRICT_CONN_207"

    def test_branching_no_cycle(self):
        """
        Unit Test 26: Branching connections without cycle.

        Verifies validation passes for branching DAG structures.
        """
        existing = [
            ("node1", "node2"),
            ("node1", "node3"),
            ("node2", "node4"),
            ("node3", "node4"),
        ]
        results = detect_circular_dependency("node4", "node5", existing)

        assert all(r.success for r in results)


class TestCompleteConnectionValidation:
    """Unit tests for complete connection validation."""

    def test_valid_connection_all_checks_pass(self):
        """
        Unit Test 27: Valid connection passes all validation rules.

        Verifies all validation rules pass for valid connection.
        """
        existing_nodes = {"node1", "node2", "node3"}
        existing_connections = [("node1", "node3")]

        results = validate_connection(
            "node1", "output", "node2", "input", existing_nodes, existing_connections
        )

        # Should have exactly one success result
        assert any(r.success for r in results)
        assert not any(not r.success for r in results)

    def test_connection_with_dot_notation(self):
        """
        Unit Test 28: Valid connection with dot notation.

        Verifies validation passes for connections with dot notation.
        """
        existing_nodes = {"node1", "node2"}
        existing_connections = []

        results = validate_connection(
            "node1",
            "data.nested.field",
            "node2",
            "input",
            existing_nodes,
            existing_connections,
        )

        assert all(r.success for r in results)

    def test_connection_with_multiple_errors(self):
        """
        Unit Test 29: Connection with multiple validation errors.

        Verifies all errors are detected when multiple rules fail.
        """
        existing_nodes = {"node3"}  # node1 and node2 missing
        existing_connections = []

        results = validate_connection(
            "node1",
            "",  # Empty source_output
            "node2",
            ".field",  # Leading dot
            existing_nodes,
            existing_connections,
        )

        failed = [r for r in results if not r.success]
        assert len(failed) >= 3  # At least 3 errors

        # Check error codes present
        error_codes = [r.error_code for r in failed]
        assert "STRICT_CONN_201" in error_codes  # Missing nodes
        assert "STRICT_CONN_202" in error_codes  # Empty parameter
        assert "STRICT_CONN_204" in error_codes  # Leading dot

    def test_connection_without_circular_check(self):
        """
        Unit Test 30: Connection validation without circular dependency check.

        Verifies validation works when existing_connections not provided.
        """
        existing_nodes = {"node1", "node2"}

        results = validate_connection(
            "node1",
            "output",
            "node2",
            "input",
            existing_nodes,
            existing_connections=None,  # No circular check
        )

        assert all(r.success for r in results)


class TestConnectionSummaryHelper:
    """Unit tests for connection validation summary helper."""

    def test_summary_all_valid(self):
        """
        Unit Test 31: Summary for all valid connections.

        Verifies summary correctly reports valid connections.
        """
        results = [ConnectionValidationResult(success=True)]
        summary = get_connection_summary(results)

        assert summary["valid"] is True
        assert summary["error_count"] == 0
        assert len(summary["errors"]) == 0

    def test_summary_with_errors(self):
        """
        Unit Test 32: Summary with validation errors.

        Verifies summary correctly aggregates errors.
        """
        results = [
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_201",
                message="Source node not found",
                solution={"description": "Add source node"},
            ),
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_202",
                message="Empty parameter",
                solution={"description": "Provide valid parameter"},
            ),
        ]
        summary = get_connection_summary(results)

        assert summary["valid"] is False
        assert summary["error_count"] == 2
        assert len(summary["errors"]) == 2
        assert summary["errors"][0]["code"] == "STRICT_CONN_201"
        assert summary["errors"][1]["code"] == "STRICT_CONN_202"

    def test_summary_mixed_results(self):
        """
        Unit Test 33: Summary with mixed success and failure results.

        Verifies summary correctly handles mixed results.
        """
        results = [
            ConnectionValidationResult(success=True),
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_204",
                message="Invalid dot notation",
                solution={"description": "Fix dot notation"},
            ),
            ConnectionValidationResult(success=True),
        ]
        summary = get_connection_summary(results)

        assert summary["valid"] is False  # Has at least one error
        assert summary["error_count"] == 1
        assert len(summary["errors"]) == 1
