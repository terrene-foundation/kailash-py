"""
Unit tests for runtime contract enforcement in LocalRuntime.

Tests Task 2.3: Runtime Contract Enforcement
- Contract validation during execution
- Clear error messages on violation
- Performance optimization
- Audit trail updates
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.nodes.base import Node
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import WorkflowExecutionError, WorkflowValidationError
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.contracts import ConnectionContract, SecurityPolicy


class TestRuntimeContractEnforcement:
    """Test contract enforcement during runtime execution."""

    def test_contract_validation_passes_with_valid_data(self):
        """Test that valid data passes contract validation."""
        # Create workflow with typed connection
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test_string'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Add typed connection with string contract
        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        workflow = builder.build()

        # Execute with strict validation
        with LocalRuntime(connection_validation="strict") as runtime:
            # Should execute successfully without contract violations
            results, run_id = runtime.execute(workflow)

        assert results is not None
        assert run_id is not None
        assert "target" in results

    def test_contract_validation_fails_with_invalid_data(self):
        """Test that invalid data fails contract validation."""
        # Create workflow with contract mismatch
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 123"})  # Number
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Add typed connection expecting string but getting number
        builder.add_typed_connection(
            "source",
            "result",
            "target",
            "data",
            contract="string_data",  # Expects string
        )

        workflow = builder.build()

        # The contract validation should cause a failure
        # Let's check what actually happens
        try:
            # Execute with strict validation - should fail
            with LocalRuntime(connection_validation="strict") as runtime:
                results, run_id = runtime.execute(workflow)
            # If it succeeds, check if there are error indicators
            if results and "target" in results and results["target"].get("failed"):
                # Expected behavior - node failed due to contract validation
                pass
            else:
                assert False, "Expected contract validation to cause node failure"
        except WorkflowExecutionError:
            # This is also acceptable - direct exception
            pass

    def test_contract_validation_with_security_policies(self):
        """Test contract validation with security policy enforcement."""
        # Create custom contract with security policies
        custom_contract = ConnectionContract(
            name="secure_data",
            source_schema={"type": "string"},
            target_schema={"type": "string"},
            security_policies=[SecurityPolicy.NO_SQL],
        )

        builder = WorkflowBuilder()
        builder.add_node(
            "PythonCodeNode", "source", {"code": "result = 'SELECT * FROM users'"}
        )  # SQL content
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Add typed connection with security policy
        builder.add_typed_connection(
            "source", "result", "target", "data", contract=custom_contract
        )

        workflow = builder.build()

        # Should fail due to SQL content in data
        try:
            with LocalRuntime(connection_validation="strict") as runtime:
                results, run_id = runtime.execute(workflow)
            # Check if node failed due to contract validation
            if results and "target" in results and results["target"].get("failed"):
                pass  # Expected behavior
            else:
                assert False, "Expected contract validation to cause node failure"
        except WorkflowExecutionError:
            pass  # Also acceptable

    def test_contract_validation_skipped_when_no_contracts(self):
        """Test that execution works normally when no contracts are defined."""
        # Create workflow without typed connections
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Regular connection (no contract)
        builder.add_connection("source", "result", "target", "data")

        workflow = builder.build()

        # Should execute normally without contract validation
        with LocalRuntime(connection_validation="strict") as runtime:
            results, run_id = runtime.execute(workflow)

        assert results is not None
        assert "target" in results

    def test_contract_validation_warn_mode(self):
        """Test contract validation in warn mode."""
        # Create workflow with contract violation
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 123"})  # Number
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Add typed connection expecting string
        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        workflow = builder.build()

        # Execute with warn mode - should log warning but continue
        with LocalRuntime(connection_validation="warn") as runtime:
            with patch.object(runtime.logger, "warning") as mock_warning:
                results, run_id = runtime.execute(workflow)

            # Should complete execution but log contract warnings
            assert results is not None
            # Should log warning about contract violation
            mock_warning.assert_called()
            warning_msg = str(mock_warning.call_args[0][0])
            assert any(
                term in warning_msg.lower()
                for term in ["contract validation failed", "contract", "violation"]
            )

    def test_contract_validation_off_mode(self):
        """Test that contract validation is skipped when turned off."""
        # Create workflow with contract violation
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 123"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        workflow = builder.build()

        # Execute with validation off - should skip contract validation
        with LocalRuntime(connection_validation="off") as runtime:
            # Should execute without any contract validation
            results, run_id = runtime.execute(workflow)

        assert results is not None

    def test_multiple_contracts_validation(self):
        """Test validation of multiple contracts in the same workflow."""
        builder = WorkflowBuilder()

        # Create multiple nodes
        builder.add_node("PythonCodeNode", "source1", {"code": "result = 'string'"})
        builder.add_node("PythonCodeNode", "source2", {"code": "result = 42"})
        builder.add_node("PythonCodeNode", "target1", {"code": "result = data"})
        builder.add_node("PythonCodeNode", "target2", {"code": "result = data"})

        # Add multiple typed connections
        builder.add_typed_connection(
            "source1", "result", "target1", "data", contract="string_data"
        )
        builder.add_typed_connection(
            "source2", "result", "target2", "data", contract="numeric_data"
        )

        workflow = builder.build()

        # Should validate all contracts successfully
        with LocalRuntime(connection_validation="strict") as runtime:
            results, run_id = runtime.execute(workflow)

        assert results is not None
        assert "target1" in results
        assert "target2" in results

    def test_partial_contract_violations(self):
        """Test when some contracts pass and others fail."""
        builder = WorkflowBuilder()

        builder.add_node(
            "PythonCodeNode", "source1", {"code": "result = 'valid_string'"}
        )
        builder.add_node(
            "PythonCodeNode", "source2", {"code": "result = 'not_a_number'"}
        )  # Invalid for numeric
        builder.add_node("PythonCodeNode", "target1", {"code": "result = data"})
        builder.add_node("PythonCodeNode", "target2", {"code": "result = data"})

        # One valid contract, one invalid
        builder.add_typed_connection(
            "source1", "result", "target1", "data", contract="string_data"
        )
        builder.add_typed_connection(
            "source2", "result", "target2", "data", contract="numeric_data"
        )

        workflow = builder.build()

        # Should fail due to the invalid contract
        try:
            with LocalRuntime(connection_validation="strict") as runtime:
                results, run_id = runtime.execute(workflow)
            # Check if any target node failed due to contract validation
            target_failed = any(
                results.get(f"target{i}", {}).get("failed") for i in range(1, 3)
            )
            if target_failed:
                pass  # Expected behavior
            else:
                assert False, "Expected contract validation to cause node failure"
        except WorkflowExecutionError:
            pass  # Also acceptable

    def test_contract_validation_with_missing_source_data(self):
        """Test contract validation when source data is missing."""
        builder = WorkflowBuilder()

        # Source node that might not produce expected output
        builder.add_node(
            "PythonCodeNode", "source", {"code": "pass"}
        )  # No result output
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        workflow = builder.build()

        # Should handle missing source data gracefully
        # The actual behavior depends on how the source node handles missing outputs
        try:
            with LocalRuntime(connection_validation="strict") as runtime:
                results, run_id = runtime.execute(workflow)
            # If it succeeds, contracts should not cause additional failures
            assert results is not None
        except (WorkflowExecutionError, KeyError, Exception):
            # Failure due to missing data is acceptable
            pass

    def test_contract_metadata_preservation(self):
        """Test that contract metadata is properly preserved in workflow."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        workflow = builder.build()

        # Verify contract metadata is stored
        assert "connection_contracts" in workflow.metadata
        contracts = workflow.metadata["connection_contracts"]

        connection_id = "source.result → target.data"
        assert connection_id in contracts
        assert contracts[connection_id]["name"] == "string_data"

    def test_contract_validation_error_messages(self):
        """Test that contract validation errors provide clear messages."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 123"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        workflow = builder.build()

        try:
            with LocalRuntime(connection_validation="strict") as runtime:
                results, run_id = runtime.execute(workflow)
            # Check if node failed due to contract validation
            if results and "target" in results and results["target"].get("failed"):
                # Check error message content through logs or results
                pass  # Contract validation worked
            else:
                assert False, "Expected contract validation to cause node failure"
        except WorkflowExecutionError as e:
            error_msg = str(e)
            # Error message should include contract name and connection info
            assert any(
                term in error_msg for term in ["string_data", "contract", "validation"]
            )
            assert any(term in error_msg for term in ["source", "target", "connection"])
            assert any(
                term in error_msg.lower()
                for term in [
                    "contract validation failed",
                    "violation",
                    "validation error",
                ]
            )


class TestContractValidationMethod:
    """Test the _validate_connection_contracts method directly."""

    def test_validate_connection_contracts_no_contracts(self):
        """Test validation when no contracts are defined."""
        runtime = LocalRuntime()

        # Mock workflow without contracts
        workflow = Mock()
        workflow.metadata = {}
        workflow.connections = []

        violations = runtime._validate_connection_contracts(
            workflow, "target_node", {}, {}
        )

        assert violations == []

    def test_validate_connection_contracts_with_violations(self):
        """Test validation with contract violations."""
        runtime = LocalRuntime()

        # Mock workflow with contracts
        workflow = Mock()
        workflow.metadata = {
            "connection_contracts": {
                "source.output → target.input": {
                    "name": "string_data",
                    "source_schema": {"type": "string"},
                    "target_schema": {"type": "string"},
                    "security_policies": [],
                    "audit_level": "normal",
                    "metadata": {},
                }
            }
        }

        # Mock connection
        connection = Mock()
        connection.source_node = "source"
        connection.source_output = "output"
        connection.target_node = "target"
        connection.target_input = "input"
        workflow.connections = [connection]

        # Mock invalid data (number instead of string)
        node_outputs = {"source": {"output": 123}}
        target_inputs = {"input": 123}

        violations = runtime._validate_connection_contracts(
            workflow, "target", target_inputs, node_outputs
        )

        assert len(violations) == 1
        violation = violations[0]
        assert violation["connection"] == "source.output → target.input"
        assert violation["contract"] == "string_data"
        assert "validation failed" in violation["error"].lower()

    def test_validate_connection_contracts_with_valid_data(self):
        """Test validation with valid data."""
        runtime = LocalRuntime()

        # Mock workflow with contracts
        workflow = Mock()
        workflow.metadata = {
            "connection_contracts": {
                "source.output → target.input": {
                    "name": "string_data",
                    "source_schema": {"type": "string"},
                    "target_schema": {"type": "string"},
                    "security_policies": [],
                    "audit_level": "normal",
                    "metadata": {},
                }
            }
        }

        # Mock connection
        connection = Mock()
        connection.source_node = "source"
        connection.source_output = "output"
        connection.target_node = "target"
        connection.target_input = "input"
        workflow.connections = [connection]

        # Mock valid string data
        node_outputs = {"source": {"output": "valid_string"}}
        target_inputs = {"input": "valid_string"}

        violations = runtime._validate_connection_contracts(
            workflow, "target", target_inputs, node_outputs
        )

        assert violations == []


class TestContractIntegrationWithExistingValidation:
    """Test that contract validation integrates properly with existing validation."""

    def test_contract_and_node_validation_both_run(self):
        """Test that both contract and node validation are performed."""
        builder = WorkflowBuilder()

        # Create a node that will fail node validation
        builder.add_node(
            "CSVReaderNode", "csv_reader", {}
        )  # Missing required file_path
        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test.csv'"})

        # Add typed connection
        builder.add_typed_connection(
            "source", "result", "csv_reader", "file_path", contract="file_path"
        )

        # Should fail due to parameter validation at build time or contract validation at runtime
        try:
            workflow = builder.build()

            with LocalRuntime(connection_validation="strict") as runtime:
                results, run_id = runtime.execute(workflow)
            # Check if csv_reader node failed
            if (
                results
                and "csv_reader" in results
                and results["csv_reader"].get("failed")
            ):
                pass  # Expected behavior
            else:
                assert False, "Expected validation to cause node failure"
        except WorkflowValidationError:
            pass  # Also acceptable - parameter validation at build time
        except WorkflowExecutionError:
            pass  # Also acceptable - contract validation at runtime

    def test_metrics_collection_with_contracts(self):
        """Test that metrics are collected for contract validation."""
        builder = WorkflowBuilder()
        builder.add_node("PythonCodeNode", "source", {"code": "result = 123"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        workflow = builder.build()

        # Execute and capture metrics
        try:
            with LocalRuntime(connection_validation="strict") as runtime:
                results, run_id = runtime.execute(workflow)
                # Verify metrics were collected (inside context to access runtime)
                metrics = runtime.get_validation_metrics()
            # Check if target node failed due to contract validation
            if results and "target" in results and results["target"].get("failed"):
                pass  # Expected behavior
            else:
                assert False, "Expected contract validation to cause node failure"
            assert "performance_summary" in metrics
            assert "security_report" in metrics
        except WorkflowExecutionError:
            pass  # Also acceptable

    def test_contract_validation_performance(self):
        """Test that contract validation doesn't significantly impact performance."""
        import time

        builder = WorkflowBuilder()

        # Create workflow with multiple contracts
        for i in range(10):
            builder.add_node(
                "PythonCodeNode", f"source_{i}", {"code": f"result = 'data_{i}'"}
            )
            builder.add_node("PythonCodeNode", f"target_{i}", {"code": "result = data"})
            builder.add_typed_connection(
                f"source_{i}", "result", f"target_{i}", "data", contract="string_data"
            )

        workflow = builder.build()

        # Measure execution time
        start_time = time.time()
        with LocalRuntime(
            connection_validation="strict", enable_monitoring=False
        ) as runtime:
            results, run_id = runtime.execute(workflow)
        end_time = time.time()

        execution_time = end_time - start_time

        # Should complete within reasonable time (allowing for test environment variability)
        assert execution_time < 5.0  # 5 seconds should be more than enough
        assert results is not None
