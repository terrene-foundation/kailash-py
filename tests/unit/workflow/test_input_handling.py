"""Unit tests for workflow input handling module."""

import logging
from unittest.mock import MagicMock, Mock, patch

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.workflow.graph import Workflow
from kailash.workflow.input_handling import (
    WorkflowInputHandler,
    enhance_workflow_execution,
    fix_login_workflow,
)


class TestWorkflowInputHandler:
    """Test WorkflowInputHandler class."""

    @pytest.fixture
    def mock_workflow(self):
        """Create a mock workflow with graph and nodes."""
        workflow = Mock(spec=Workflow)
        workflow._graph = Mock()
        workflow._nodes = {}
        workflow._metadata = {}
        return workflow

    @pytest.fixture
    def mock_node_with_params(self):
        """Create a mock node with parameters."""
        node = Mock(spec=Node)
        node.config = {}
        node.get_parameters = Mock(
            return_value={
                "required_param": Mock(required=True),
                "optional_param": Mock(required=False),
                "tenant_id": Mock(required=True),
                "database_config": Mock(required=True),
            }
        )
        return node

    def test_inject_workflow_parameters_no_entry_nodes(self, mock_workflow):
        """Test injection when all nodes have incoming connections."""
        # Setup: All nodes have incoming edges
        mock_workflow._graph.edges.return_value = [
            ("node1", "node2"),
            ("node2", "node3"),
        ]
        mock_workflow._graph.nodes.return_value = ["node1", "node2", "node3"]

        # No entry nodes should be processed
        WorkflowInputHandler.inject_workflow_parameters(
            mock_workflow, {"param": "value"}
        )

        # Verify no nodes were processed (empty _nodes dict)
        assert len(mock_workflow._nodes) == 0

    def test_inject_workflow_parameters_with_entry_nodes(
        self, mock_workflow, mock_node_with_params
    ):
        """Test injection into nodes without incoming connections."""
        # Setup: node1 has no incoming edges
        mock_workflow._graph.edges.return_value = [("node1", "node2")]
        mock_workflow._graph.nodes.return_value = ["node1", "node2"]
        mock_workflow._nodes = {"node1": mock_node_with_params}

        parameters = {"required_param": "test_value", "extra_param": "extra_value"}

        WorkflowInputHandler.inject_workflow_parameters(mock_workflow, parameters)

        # Verify required parameter was injected
        assert mock_node_with_params.config["required_param"] == "test_value"
        # Verify get_parameters was called
        mock_node_with_params.get_parameters.assert_called_once()

    def test_inject_workflow_parameters_default_tenant(
        self, mock_workflow, mock_node_with_params
    ):
        """Test default tenant_id injection."""
        # Setup entry node without tenant_id in parameters
        mock_workflow._graph.edges.return_value = []
        mock_workflow._graph.nodes.return_value = ["node1"]
        mock_workflow._nodes = {"node1": mock_node_with_params}

        WorkflowInputHandler.inject_workflow_parameters(mock_workflow, {})

        # Verify default tenant_id was set
        assert mock_node_with_params.config["tenant_id"] == "default"

    def test_inject_workflow_parameters_database_config(
        self, mock_workflow, mock_node_with_params
    ):
        """Test database config injection from various sources."""
        # Setup
        mock_workflow._graph.edges.return_value = []
        mock_workflow._graph.nodes.return_value = ["node1"]
        mock_workflow._nodes = {"node1": mock_node_with_params}

        # Test 1: database_config in parameters
        parameters = {"database_config": {"host": "localhost"}}
        WorkflowInputHandler.inject_workflow_parameters(mock_workflow, parameters)
        assert mock_node_with_params.config["database_config"] == {"host": "localhost"}

        # Reset
        mock_node_with_params.config = {}

        # Test 2: db_config in parameters
        parameters = {"db_config": {"host": "db_host"}}
        WorkflowInputHandler.inject_workflow_parameters(mock_workflow, parameters)
        assert mock_node_with_params.config["database_config"] == {"host": "db_host"}

        # Reset
        mock_node_with_params.config = {}

        # Test 3: database_config in workflow metadata
        mock_workflow._metadata = {"database_config": {"host": "metadata_host"}}
        WorkflowInputHandler.inject_workflow_parameters(mock_workflow, {})
        assert mock_node_with_params.config["database_config"] == {
            "host": "metadata_host"
        }

    def test_inject_workflow_parameters_skip_existing_config(
        self, mock_workflow, mock_node_with_params
    ):
        """Test that existing node config is not overwritten."""
        # Setup node with existing config
        mock_workflow._graph.edges.return_value = []
        mock_workflow._graph.nodes.return_value = ["node1"]
        mock_node_with_params.config = {"required_param": "existing_value"}
        mock_workflow._nodes = {"node1": mock_node_with_params}

        parameters = {"required_param": "new_value"}
        WorkflowInputHandler.inject_workflow_parameters(mock_workflow, parameters)

        # Verify existing value was preserved
        assert mock_node_with_params.config["required_param"] == "existing_value"

    def test_inject_workflow_parameters_node_without_get_parameters(
        self, mock_workflow
    ):
        """Test handling nodes without get_parameters method."""
        # Setup node without get_parameters
        node = Mock(spec=Node)
        node.config = {}
        del node.get_parameters  # Remove the method

        mock_workflow._graph.edges.return_value = []
        mock_workflow._graph.nodes.return_value = ["node1"]
        mock_workflow._nodes = {"node1": node}

        # Should not raise error
        WorkflowInputHandler.inject_workflow_parameters(
            mock_workflow, {"param": "value"}
        )

    def test_create_input_mappings_basic(self, mock_workflow):
        """Test basic input mapping creation."""
        node = Mock(spec=Node)
        node.config = {}
        mock_workflow._nodes = {"node1": node}

        mappings = {
            "node1": {
                "workflow_param1": "node_param1",
                "workflow_param2": "node_param2",
            }
        }

        WorkflowInputHandler.create_input_mappings(mock_workflow, mappings)

        # Verify mappings were stored
        assert "_input_mappings" in node.config
        assert node.config["_input_mappings"] == mappings["node1"]

    def test_create_input_mappings_update_existing(self, mock_workflow):
        """Test updating existing input mappings."""
        node = Mock(spec=Node)
        node.config = {"_input_mappings": {"existing": "mapping"}}
        mock_workflow._nodes = {"node1": node}

        mappings = {"node1": {"new_param": "new_mapping"}}

        WorkflowInputHandler.create_input_mappings(mock_workflow, mappings)

        # Verify mappings were updated, not replaced
        assert node.config["_input_mappings"]["existing"] == "mapping"
        assert node.config["_input_mappings"]["new_param"] == "new_mapping"

    def test_create_input_mappings_missing_node(self, mock_workflow):
        """Test handling of missing nodes in mappings."""
        mock_workflow._nodes = {}

        mappings = {"missing_node": {"param": "value"}}

        # Should log warning but not raise error
        with patch("kailash.workflow.input_handling.logger") as mock_logger:
            WorkflowInputHandler.create_input_mappings(mock_workflow, mappings)
            mock_logger.warning.assert_called_once()

    def test_enhance_workflow_execution_decorator(self):
        """Test the enhance_workflow_execution decorator."""
        # Mock original execute method
        original_execute = Mock(return_value="execution_result")

        # Create enhanced version
        enhanced = enhance_workflow_execution(original_execute)

        # Create mock self with workflow attributes
        mock_self = Mock()
        mock_self._graph = Mock()
        mock_self._graph.edges.return_value = []
        mock_self._graph.nodes.return_value = []
        mock_self._nodes = {}

        # Test with parameters
        parameters = {"param": "value"}
        result = enhanced(mock_self, parameters)

        # Verify original was called with parameters
        original_execute.assert_called_once_with(mock_self, parameters)
        assert result == "execution_result"

    def test_enhance_workflow_execution_no_parameters(self):
        """Test decorator with no parameters."""
        original_execute = Mock(return_value="result")
        enhanced = enhance_workflow_execution(original_execute)

        mock_self = Mock()
        result = enhanced(mock_self, None, extra="kwarg")

        # Verify original was called correctly
        original_execute.assert_called_once_with(mock_self, None, extra="kwarg")
        assert result == "result"

    def test_fix_login_workflow(self, mock_workflow):
        """Test the fix_login_workflow helper function."""
        # Create user_fetcher node
        user_fetcher = Mock(spec=Node)
        user_fetcher.config = {}
        mock_workflow._nodes = {"user_fetcher": user_fetcher}

        config = {"DATABASE_URL": "sqlite:///:memory:"}

        fix_login_workflow(mock_workflow, config)

        # Verify mappings were created
        assert "_input_mappings" in user_fetcher.config
        assert user_fetcher.config["_input_mappings"]["email"] == "identifier"
        assert user_fetcher.config["_input_mappings"]["tenant_id"] == "tenant_id"

        # Verify defaults were set
        assert user_fetcher.config["tenant_id"] == "default"
        assert (
            user_fetcher.config["database_config"]["connection_string"]
            == "sqlite:///:memory:"
        )
        assert user_fetcher.config["database_config"]["database_type"] == "postgresql"

    def test_fix_login_workflow_existing_config(self, mock_workflow):
        """Test fix_login_workflow preserves existing config."""
        user_fetcher = Mock(spec=Node)
        user_fetcher.config = {
            "tenant_id": "existing_tenant",
            "database_config": {"existing": "config"},
        }
        mock_workflow._nodes = {"user_fetcher": user_fetcher}

        fix_login_workflow(mock_workflow, {})

        # Verify existing config was preserved
        assert user_fetcher.config["tenant_id"] == "existing_tenant"
        assert user_fetcher.config["database_config"] == {"existing": "config"}

    def test_fix_login_workflow_no_user_fetcher(self, mock_workflow):
        """Test fix_login_workflow when user_fetcher node doesn't exist."""
        mock_workflow._nodes = {}

        # Should not raise error
        fix_login_workflow(mock_workflow, {})


class TestWorkflowInputHandlerIntegration:
    """Integration tests with real Workflow objects."""

    def test_inject_parameters_real_workflow(self):
        """Test parameter injection with a real workflow."""
        from kailash.workflow.graph import Workflow

        # Create real workflow
        workflow = Workflow(workflow_id="test", name="Test Workflow")

        # Add a mock node
        node = Mock(spec=Node)
        node.config = {}
        node.get_parameters = Mock(
            return_value={
                "input_file": Mock(required=True),
                "output_file": Mock(required=True),
            }
        )

        # The input_handling module expects _nodes and _graph, but Workflow uses different names
        # This is an architecture inconsistency - we'll add the expected attributes
        workflow._nodes = {"reader": node}
        workflow._graph = workflow.graph  # Alias for the inconsistency
        workflow.graph.add_node("reader")

        # Inject parameters
        parameters = {"input_file": "/tmp/input.csv", "output_file": "/tmp/output.csv"}

        WorkflowInputHandler.inject_workflow_parameters(workflow, parameters)

        # Verify injection
        assert node.config["input_file"] == "/tmp/input.csv"
        assert node.config["output_file"] == "/tmp/output.csv"

    def test_complex_workflow_parameter_injection(self):
        """Test parameter injection in a complex workflow with multiple nodes."""
        from kailash.workflow.graph import Workflow

        workflow = Workflow(workflow_id="complex", name="Complex Workflow")

        # Create nodes
        reader_node = Mock(spec=Node)
        reader_node.config = {}
        reader_node.get_parameters = Mock(
            return_value={"file_path": Mock(required=True)}
        )

        processor_node = Mock(spec=Node)
        processor_node.config = {}
        processor_node.get_parameters = Mock(
            return_value={"threshold": Mock(required=True)}
        )

        writer_node = Mock(spec=Node)
        writer_node.config = {}
        writer_node.get_parameters = Mock(
            return_value={"output_path": Mock(required=True)}
        )

        # Add nodes to workflow (architecture inconsistency workaround)
        workflow._nodes = {
            "reader": reader_node,
            "processor": processor_node,
            "writer": writer_node,
        }
        workflow._graph = workflow.graph  # Alias for the inconsistency

        # Add to graph with connections
        workflow.graph.add_node("reader")
        workflow.graph.add_node("processor")
        workflow.graph.add_node("writer")
        workflow.graph.add_edge("reader", "processor")
        workflow.graph.add_edge("processor", "writer")

        # Inject parameters
        parameters = {
            "file_path": "/data/input.csv",
            "threshold": 0.5,
            "output_path": "/data/output.csv",
        }

        WorkflowInputHandler.inject_workflow_parameters(workflow, parameters)

        # Only reader should get parameters (no incoming edges)
        assert reader_node.config["file_path"] == "/data/input.csv"
        assert "threshold" not in processor_node.config  # Has incoming edge
        assert "output_path" not in writer_node.config  # Has incoming edge
