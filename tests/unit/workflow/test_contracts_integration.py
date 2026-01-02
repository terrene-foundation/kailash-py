"""
Unit tests for connection contract integration in WorkflowBuilder.

Tests Task 2.2: Integrate Contracts into WorkflowBuilder
- add_typed_connection() method
- Contract storage in workflow
- Backward compatibility with add_connection()
- Contract validation and error handling
"""

from unittest.mock import Mock, patch

import pytest
from kailash.sdk_exceptions import ConnectionError, WorkflowValidationError
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.contracts import (
    ConnectionContract,
    SecurityPolicy,
    get_contract_registry,
)


class TestContractIntegration:
    """Test connection contract integration with WorkflowBuilder."""

    def test_add_typed_connection_with_predefined_contract(self):
        """Test adding typed connection with predefined contract."""
        builder = WorkflowBuilder()

        # Add nodes first
        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Add typed connection with predefined contract
        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        # Verify connection was added
        assert len(builder.connections) == 1
        conn = builder.connections[0]
        assert conn["from_node"] == "source"
        assert conn["from_output"] == "result"
        assert conn["to_node"] == "target"
        assert conn["to_input"] == "data"

        # Verify contract was stored
        connection_id = "source.result → target.data"
        assert connection_id in builder.connection_contracts
        contract = builder.connection_contracts[connection_id]
        assert contract.name == "string_data"

    def test_add_typed_connection_with_custom_contract(self):
        """Test adding typed connection with custom contract."""
        builder = WorkflowBuilder()

        # Add nodes
        builder.add_node("CSVReaderNode", "reader", {"file_path": "test.csv"})
        builder.add_node("PythonCodeNode", "processor", {"code": "result = data"})

        # Create custom contract
        custom_contract = ConnectionContract(
            name="csv_data_flow",
            description="CSV data with security",
            source_schema={"type": "array"},
            target_schema={"type": "array"},
            security_policies=[SecurityPolicy.NO_SQL],
            audit_level="detailed",
        )

        # Add typed connection
        builder.add_typed_connection(
            "reader", "data", "processor", "input", contract=custom_contract
        )

        # Verify contract was stored
        connection_id = "reader.data → processor.input"
        stored_contract = builder.connection_contracts[connection_id]
        assert stored_contract.name == "csv_data_flow"
        assert stored_contract.description == "CSV data with security"
        assert SecurityPolicy.NO_SQL in stored_contract.security_policies
        assert stored_contract.audit_level == "detailed"

    def test_add_typed_connection_unknown_contract(self):
        """Test error when using unknown contract name."""
        builder = WorkflowBuilder()

        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        with pytest.raises(
            WorkflowValidationError, match="Contract 'unknown_contract' not found"
        ):
            builder.add_typed_connection(
                "source", "result", "target", "data", contract="unknown_contract"
            )

    def test_add_typed_connection_immediate_validation(self):
        """Test immediate validation of contract schemas."""
        builder = WorkflowBuilder()

        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Create contract with invalid schema (bypass __post_init__ validation)
        invalid_contract = ConnectionContract(
            name="invalid_schema",
            source_schema={"type": "string"},  # Valid schema for creation
            target_schema={"type": "string"},
        )

        # Manually set invalid schema after creation
        invalid_contract.source_schema = {"type": "invalid_type"}

        with pytest.raises(WorkflowValidationError, match="Invalid contract schema"):
            builder.add_typed_connection(
                "source",
                "result",
                "target",
                "data",
                contract=invalid_contract,
                validate_immediately=True,
            )

    def test_add_typed_connection_missing_nodes(self):
        """Test error when nodes don't exist."""
        builder = WorkflowBuilder()

        # Try to connect non-existent nodes
        with pytest.raises(
            WorkflowValidationError, match="Source node 'missing' not found"
        ):
            builder.add_typed_connection(
                "missing", "result", "target", "data", contract="string_data"
            )

    def test_get_connection_contract(self):
        """Test retrieving connection contract."""
        builder = WorkflowBuilder()

        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        builder.add_typed_connection(
            "source", "result", "target", "data", contract="numeric_data"
        )

        # Get existing contract
        connection_id = "source.result → target.data"
        contract = builder.get_connection_contract(connection_id)
        assert contract is not None
        assert contract.name == "numeric_data"

        # Get non-existent contract
        contract = builder.get_connection_contract("nonexistent")
        assert contract is None

    def test_list_connection_contracts(self):
        """Test listing all connection contracts."""
        builder = WorkflowBuilder()

        # Add nodes
        builder.add_node("PythonCodeNode", "node1", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "node2", {"code": "result = data"})
        builder.add_node("PythonCodeNode", "node3", {"code": "result = data"})

        # Add typed connections
        builder.add_typed_connection(
            "node1", "result", "node2", "data", contract="string_data"
        )
        builder.add_typed_connection(
            "node2", "result", "node3", "data", contract="numeric_data"
        )

        contracts = builder.list_connection_contracts()

        assert len(contracts) == 2
        assert "node1.result → node2.data" in contracts
        assert "node2.result → node3.data" in contracts
        assert contracts["node1.result → node2.data"] == "string_data"
        assert contracts["node2.result → node3.data"] == "numeric_data"

    def test_validate_all_contracts(self):
        """Test validating all contracts in workflow."""
        builder = WorkflowBuilder()

        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Add connection with valid contract
        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        # Validate - should pass
        is_valid, errors = builder.validate_all_contracts()
        assert is_valid
        assert len(errors) == 0

    def test_validate_all_contracts_with_errors(self):
        """Test validation with invalid contracts."""
        builder = WorkflowBuilder()

        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Create valid contract first, then corrupt it
        invalid_contract = ConnectionContract(
            name="invalid_test", source_schema={"type": "string"}  # Valid initially
        )

        # Manually corrupt the schema after creation
        invalid_contract.source_schema = {"type": "invalid_type"}

        builder.add_connection("source", "result", "target", "data")
        connection_id = "source.result → target.data"
        builder.connection_contracts[connection_id] = invalid_contract

        # Validate - should fail
        is_valid, errors = builder.validate_all_contracts()
        assert not is_valid
        assert len(errors) > 0
        assert "invalid_test" in errors[0]

    def test_backward_compatibility_with_add_connection(self):
        """Test that regular add_connection() still works."""
        builder = WorkflowBuilder()

        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Use regular add_connection (no contract)
        builder.add_connection("source", "result", "target", "data")

        # Verify connection was added but no contract
        assert len(builder.connections) == 1
        assert len(builder.connection_contracts) == 0

        # Should still be able to build workflow
        workflow = builder.build()
        assert len(workflow.connections) == 1

    def test_mixed_connections_with_and_without_contracts(self):
        """Test workflow with both typed and regular connections."""
        builder = WorkflowBuilder()

        # Add nodes
        builder.add_node("PythonCodeNode", "node1", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "node2", {"code": "result = data"})
        builder.add_node("PythonCodeNode", "node3", {"code": "result = data"})
        builder.add_node("PythonCodeNode", "node4", {"code": "result = data"})

        # Add regular connection
        builder.add_connection("node1", "result", "node2", "data")

        # Add typed connection
        builder.add_typed_connection(
            "node2", "result", "node3", "data", contract="string_data"
        )

        # Add another regular connection
        builder.add_connection("node3", "result", "node4", "data")

        # Verify state
        assert len(builder.connections) == 3
        assert len(builder.connection_contracts) == 1

        contracts = builder.list_connection_contracts()
        assert len(contracts) == 1
        assert "node2.result → node3.data" in contracts

    def test_clear_resets_contracts(self):
        """Test that clear() resets connection contracts."""
        builder = WorkflowBuilder()

        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        # Verify contracts exist
        assert len(builder.connection_contracts) == 1

        # Clear and verify contracts are gone
        builder.clear()
        assert len(builder.connection_contracts) == 0
        assert len(builder.connections) == 0

    def test_workflow_build_stores_contracts_in_metadata(self):
        """Test that built workflow contains contract metadata."""
        builder = WorkflowBuilder()

        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Add typed connection
        builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        # Build workflow
        workflow = builder.build()

        # Verify contracts are stored in metadata
        assert "connection_contracts" in workflow.metadata
        contracts_dict = workflow.metadata["connection_contracts"]

        connection_id = "source.result → target.data"
        assert connection_id in contracts_dict

        # Verify contract was serialized properly
        contract_data = contracts_dict[connection_id]
        assert contract_data["name"] == "string_data"
        assert contract_data["source_schema"] == {"type": "string"}
        assert contract_data["target_schema"] == {"type": "string"}


class TestContractRegistryIntegration:
    """Test integration with contract registry."""

    def test_builder_uses_global_registry(self):
        """Test that builder uses global contract registry."""
        builder = WorkflowBuilder()

        # Verify builder has access to predefined contracts
        available_contracts = builder._contract_registry.list_contracts()
        assert "string_data" in available_contracts
        assert "numeric_data" in available_contracts
        assert "file_path" in available_contracts

    def test_custom_contract_registration(self):
        """Test registering custom contract and using it."""
        builder = WorkflowBuilder()

        # Create and register custom contract
        custom_contract = ConnectionContract(
            name="test_custom",
            description="Test custom contract",
            source_schema={"type": "object"},
            target_schema={"type": "object"},
        )

        builder._contract_registry.register(custom_contract)

        # Use the custom contract
        builder.add_node("PythonCodeNode", "source", {"code": "result = {}"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        builder.add_typed_connection(
            "source", "result", "target", "data", contract="test_custom"
        )

        # Verify it worked
        connection_id = "source.result → target.data"
        stored_contract = builder.connection_contracts[connection_id]
        assert stored_contract.name == "test_custom"
        assert stored_contract.description == "Test custom contract"


class TestContractValidationMethods:
    """Test contract validation helper methods."""

    def test_connection_id_format(self):
        """Test connection ID format consistency."""
        builder = WorkflowBuilder()

        builder.add_node("PythonCodeNode", "source_node", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target_node", {"code": "result = data"})

        builder.add_typed_connection(
            "source_node",
            "output_port",
            "target_node",
            "input_port",
            contract="string_data",
        )

        # Verify connection ID format
        expected_id = "source_node.output_port → target_node.input_port"
        assert expected_id in builder.connection_contracts

        # Verify get_connection_contract uses same format
        contract = builder.get_connection_contract(expected_id)
        assert contract is not None
        assert contract.name == "string_data"

    def test_fluent_api_chaining_with_contracts(self):
        """Test that add_typed_connection supports method chaining."""
        builder = WorkflowBuilder()

        # Add nodes first (add_node returns node_id, not self)
        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        # Test chaining with add_typed_connection
        result = builder.add_typed_connection(
            "source", "result", "target", "data", contract="string_data"
        )

        # Should return self for chaining
        assert result is builder

        # Verify connection was added
        assert len(builder.connection_contracts) == 1

    def test_error_messages_include_available_contracts(self):
        """Test that error messages are helpful."""
        builder = WorkflowBuilder()

        builder.add_node("PythonCodeNode", "source", {"code": "result = 'test'"})
        builder.add_node("PythonCodeNode", "target", {"code": "result = data"})

        try:
            builder.add_typed_connection(
                "source", "result", "target", "data", contract="nonexistent_contract"
            )
            assert False, "Should have raised WorkflowValidationError"
        except WorkflowValidationError as e:
            # Error message should include available contracts
            error_msg = str(e)
            assert "Available contracts:" in error_msg
            assert "string_data" in error_msg
            assert "numeric_data" in error_msg
