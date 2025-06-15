"""
Test WorkflowBuilder.from_dict() parameter mapping improvements.

This test validates the core SDK improvement that standardizes node constructor
patterns and fixes the parameter mapping inconsistency between 'name' and 'id'.
"""

import pytest

from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.transform import DataTransformer
from kailash.sdk_exceptions import NodeConfigurationError, WorkflowValidationError
from kailash.workflow.builder import WorkflowBuilder


class TestNodeConstructorMapping:
    """Test node constructor parameter mapping in WorkflowBuilder.from_dict()."""

    def test_python_code_node_parameter_mapping(self):
        """Test PythonCodeNode works with WorkflowBuilder.from_dict()."""
        workflow_config = {
            "name": "test_workflow",
            "nodes": [
                {
                    "id": "python_node",
                    "type": "PythonCodeNode",
                    "config": {
                        "code": "result = {'status': 'processed'}"
                        # Note: 'name' is not explicitly provided - should be auto-mapped
                    },
                }
            ],
            "connections": [],
        }

        # Should not raise NodeConfigurationError
        builder = WorkflowBuilder.from_dict(workflow_config)
        workflow = builder.build()

        # Verify node was created correctly
        assert "python_node" in workflow.nodes
        node_instance = workflow._node_instances["python_node"]
        assert isinstance(node_instance, PythonCodeNode)
        assert node_instance.metadata.name == "python_node"  # auto-mapped from id

    def test_explicit_name_parameter_preserved(self):
        """Test that explicitly provided 'name' parameter is preserved."""
        workflow_config = {
            "name": "test_workflow",
            "nodes": [
                {
                    "id": "python_node",
                    "type": "PythonCodeNode",
                    "config": {
                        "name": "custom_processor_name",
                        "code": "result = {'status': 'processed'}",
                    },
                }
            ],
            "connections": [],
        }

        builder = WorkflowBuilder.from_dict(workflow_config)
        workflow = builder.build()

        # Verify explicit name is preserved
        node_instance = workflow._node_instances["python_node"]
        assert node_instance.metadata.name == "custom_processor_name"

    def test_csv_reader_node_traditional_pattern(self):
        """Test CSVReaderNode (traditional id-based constructor) still works."""
        workflow_config = {
            "name": "test_workflow",
            "nodes": [
                {
                    "id": "csv_reader",
                    "type": "CSVReaderNode",
                    "config": {"file_path": "/tmp/test.csv"},
                }
            ],
            "connections": [],
        }

        # Should work with traditional id-based pattern
        builder = WorkflowBuilder.from_dict(workflow_config)
        workflow = builder.build()

        assert "csv_reader" in workflow.nodes
        node_instance = workflow._node_instances["csv_reader"]
        assert isinstance(node_instance, CSVReaderNode)

    def test_multiple_node_types_in_workflow(self):
        """Test workflow with mixed node constructor patterns."""
        workflow_config = {
            "name": "mixed_workflow",
            "nodes": [
                {
                    "id": "python_processor",
                    "type": "PythonCodeNode",
                    "config": {"code": "result = input_data"},
                },
                {
                    "id": "csv_reader",
                    "type": "CSVReaderNode",
                    "config": {"file_path": "/tmp/data.csv"},
                },
            ],
            "connections": [
                {
                    "from_node": "csv_reader",
                    "from_output": "data",
                    "to_node": "python_processor",
                    "to_input": "input_data",
                }
            ],
        }

        # Should handle both constructor patterns correctly
        builder = WorkflowBuilder.from_dict(workflow_config)
        workflow = builder.build()

        # Verify both nodes created
        assert "python_processor" in workflow.nodes
        assert "csv_reader" in workflow.nodes

        python_node = workflow._node_instances["python_processor"]
        csv_node = workflow._node_instances["csv_reader"]

        assert isinstance(python_node, PythonCodeNode)
        assert isinstance(csv_node, CSVReaderNode)
        assert python_node.metadata.name == "python_processor"

    def test_invalid_node_config_error_message(self):
        """Test improved error messages for invalid node configurations."""
        workflow_config = {
            "name": "test_workflow",
            "nodes": [
                {
                    "id": "invalid_node",
                    "type": "PythonCodeNode",
                    "config": {
                        # Missing required code parameter
                        "invalid_param": "value"
                    },
                }
            ],
            "connections": [],
        }

        # Should provide clear error message about missing parameters
        with pytest.raises(WorkflowValidationError) as exc_info:
            builder = WorkflowBuilder.from_dict(workflow_config)
            builder.build()

        error_msg = str(exc_info.value)
        # Error should mention the specific node and issue
        assert "invalid_node" in error_msg
        assert "Must provide either code string, function, or class" in error_msg

    @pytest.mark.parametrize(
        "node_type,config",
        [
            ("PythonCodeNode", {"code": "result = 42"}),
            ("CSVReaderNode", {"file_path": "/tmp/test.csv"}),
            ("DataTransformer", {"transformations": []}),
        ],
    )
    def test_common_node_types_parameter_mapping(self, node_type, config):
        """Test parameter mapping works for common node types."""
        workflow_config = {
            "name": "test_workflow",
            "nodes": [{"id": "test_node", "type": node_type, "config": config}],
            "connections": [],
        }

        # Should not raise NodeConfigurationError for any common node type
        builder = WorkflowBuilder.from_dict(workflow_config)
        workflow = builder.build()

        assert "test_node" in workflow.nodes
        assert workflow._node_instances["test_node"] is not None

    def test_class_based_workflow_integration(self):
        """Test that the improvement works with class-based workflows."""

        class ProcessingWorkflow:
            """Reusable workflow template for data processing."""

            @staticmethod
            def get_config():
                return {
                    "name": "processing_template",
                    "nodes": [
                        {
                            "id": "processor",
                            "type": "PythonCodeNode",
                            "config": {
                                "code": "result = {'processed': True, 'count': len(input_data)}"
                            },
                        }
                    ],
                    "connections": [],
                }

        # Class-based workflow should work with parameter mapping
        workflow_config = ProcessingWorkflow.get_config()
        builder = WorkflowBuilder.from_dict(workflow_config)
        workflow = builder.build()

        assert "processor" in workflow.nodes
        processor_node = workflow._node_instances["processor"]
        assert isinstance(processor_node, PythonCodeNode)
        assert processor_node.metadata.name == "processor"
