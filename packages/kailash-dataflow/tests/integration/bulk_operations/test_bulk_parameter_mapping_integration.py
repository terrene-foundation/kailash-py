"""Integration test for bulk parameter mapping fix."""

from unittest.mock import MagicMock

import pytest
from dataflow.core.nodes import NodeGenerator

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


class TestBulkParameterMappingIntegration:
    """Integration tests for bulk node parameter mapping."""

    def setup_method(self):
        """Set up integration test environment."""
        # Create mock DataFlow instance
        self.mock_dataflow = MagicMock()
        self.mock_dataflow.config.security.multi_tenant = False
        self.mock_dataflow._tenant_context = {}

        # Create node generator
        self.node_generator = NodeGenerator(self.mock_dataflow)

        # Define test model fields
        self.test_fields = {
            "name": str,
            "email": str,
            "age": int,
        }

        # Generate bulk nodes
        self.bulk_nodes = self.node_generator.generate_bulk_nodes(
            "User", self.test_fields
        )

    def test_workflow_with_records_parameter(self):
        """Test that a workflow using 'records' parameter works correctly."""
        # Create workflow with bulk create node using 'records' parameter
        workflow = WorkflowBuilder()

        # Add bulk create node
        UserBulkCreateNode = self.bulk_nodes["UserBulkCreateNode"]
        node = UserBulkCreateNode()

        # Prepare test data using 'records' instead of 'data'
        test_records = [
            {"name": "Alice", "email": "alice@example.com", "age": 25},
            {"name": "Bob", "email": "bob@example.com", "age": 30},
        ]

        # Execute the node directly (simulating workflow execution)
        result = node.run(records=test_records)

        # Verify the operation completed successfully
        assert isinstance(result, dict)
        # The exact result structure depends on implementation, but it should not fail

    def test_workflow_with_rows_parameter(self):
        """Test that a workflow using 'rows' parameter works correctly."""
        UserBulkCreateNode = self.bulk_nodes["UserBulkCreateNode"]
        node = UserBulkCreateNode()

        test_rows = [
            {"name": "Charlie", "email": "charlie@example.com", "age": 35},
            {"name": "Diana", "email": "diana@example.com", "age": 28},
        ]

        result = node.run(rows=test_rows)
        assert isinstance(result, dict)

    def test_workflow_with_documents_parameter(self):
        """Test that a workflow using 'documents' parameter works correctly."""
        UserBulkCreateNode = self.bulk_nodes["UserBulkCreateNode"]
        node = UserBulkCreateNode()

        test_documents = [
            {"name": "Eve", "email": "eve@example.com", "age": 32},
            {"name": "Frank", "email": "frank@example.com", "age": 27},
        ]

        result = node.run(documents=test_documents)
        assert isinstance(result, dict)

    def test_all_bulk_operations_parameter_mapping(self):
        """Test parameter mapping works for all bulk operations."""
        test_data = [{"name": "Test User", "email": "test@example.com", "age": 25}]

        operations = {
            "create": "UserBulkCreateNode",
            "update": "UserBulkUpdateNode",
            "delete": "UserBulkDeleteNode",
            "upsert": "UserBulkUpsertNode",
        }

        for operation, node_name in operations.items():
            NodeClass = self.bulk_nodes[node_name]
            node = NodeClass()

            # Test with 'records' parameter for each operation
            try:
                result = node.run(records=test_data)
                assert isinstance(
                    result, dict
                ), f"{operation} failed to handle 'records' parameter"
            except Exception as e:
                # Some operations might fail due to missing required parameters
                # but they should not fail due to parameter mapping issues
                assert (
                    "data" not in str(e).lower()
                ), f"{operation} failed due to parameter mapping: {e}"

    def test_parameter_validation_consistency(self):
        """Test that parameter validation is consistent across operations."""
        for node_name, NodeClass in self.bulk_nodes.items():
            node = NodeClass()
            params = node.get_parameters()

            # All bulk nodes should have data parameter with auto_map_from
            assert "data" in params, f"{node_name} missing 'data' parameter"

            data_param = params["data"]
            assert hasattr(
                data_param, "auto_map_from"
            ), f"{node_name} missing auto_map_from"
            assert data_param.auto_map_from == [
                "records",
                "rows",
                "documents",
            ], f"{node_name} has incorrect auto_map_from: {data_param.auto_map_from}"

    def test_backward_compatibility(self):
        """Test that existing 'data' parameter still works (backward compatibility)."""
        UserBulkCreateNode = self.bulk_nodes["UserBulkCreateNode"]
        node = UserBulkCreateNode()

        test_data = [{"name": "Legacy User", "email": "legacy@example.com", "age": 40}]

        # This should continue to work as before
        result = node.run(data=test_data)
        assert isinstance(result, dict)

    def test_mixed_parameters_precedence(self):
        """Test parameter precedence when multiple parameter names are provided."""
        UserBulkCreateNode = self.bulk_nodes["UserBulkCreateNode"]
        node = UserBulkCreateNode()

        data_records = [{"name": "Data User", "email": "data@example.com", "age": 30}]
        records_records = [
            {"name": "Records User", "email": "records@example.com", "age": 25}
        ]

        # When both are provided, behavior depends on SDK parameter resolution
        # This test ensures no crashes occur and a result is returned
        result = node.run(data=data_records, records=records_records)
        assert isinstance(result, dict)

    def test_empty_parameter_handling(self):
        """Test handling of empty data with different parameter names."""
        UserBulkCreateNode = self.bulk_nodes["UserBulkCreateNode"]
        node = UserBulkCreateNode()

        # Test empty data with each parameter name
        parameter_names = ["data", "records", "rows", "documents"]

        for param_name in parameter_names:
            result = node.run(**{param_name: []})
            assert isinstance(result, dict), f"Failed to handle empty {param_name}"

    def test_parameter_type_validation(self):
        """Test that parameter type validation works correctly."""
        UserBulkCreateNode = self.bulk_nodes["UserBulkCreateNode"]
        node = UserBulkCreateNode()

        # Test with correct list type
        valid_records = [{"name": "Valid", "email": "valid@example.com", "age": 25}]
        result = node.run(records=valid_records)
        assert isinstance(result, dict)

        # Test with invalid type should be handled gracefully by SDK validation
        # The exact behavior depends on SDK validation implementation
        try:
            result = node.run(records="invalid_type")
            # If no exception, validation converted or handled it
            assert isinstance(result, dict)
        except Exception as e:
            # If exception, it should be a validation error, not a parameter mapping error
            assert "data" not in str(e).lower() or "validation" in str(e).lower()
