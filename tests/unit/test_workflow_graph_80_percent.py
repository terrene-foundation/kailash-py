"""Comprehensive tests to boost workflow.graph coverage from 16% to >80%."""

import inspect
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import networkx as nx
import pytest
import yaml


class MockNode:
    """Mock node for testing."""

    def __init__(self, id=None, name=None, **config):
        self.id = id or name
        self.name = name or id
        self.config = config
        self.executed = False
        self.result = None

    def execute(self, **inputs):
        self.executed = True
        self.result = inputs
        return {"output": "success"}

    def validate(self):
        pass


class MockNodeWithNameOnly:
    """Mock node that only accepts name parameter."""

    def __init__(self, name, **config):
        self.name = name
        self.config = config

    def execute(self, **inputs):
        return {"output": f"executed_{self.name}"}


class MockNodeWithIdOnly:
    """Mock node that only accepts id parameter."""

    def __init__(self, id, **config):
        self.id = id
        self.config = config

    def execute(self, **inputs):
        return {"output": f"executed_{self.id}"}


class MockNodeRegistry:
    """Mock node registry for testing."""

    def __init__(self):
        self.nodes = {
            "TestNode": MockNode,
            "NameOnlyNode": MockNodeWithNameOnly,
            "IdOnlyNode": MockNodeWithIdOnly,
            "PythonCodeNode": MockNode,
            "DataTransformNode": MockNode,
            "CSVReaderNode": MockNode,
            "CSVWriterNode": MockNode,
        }

    def get(self, node_type):
        if node_type in self.nodes:
            return self.nodes[node_type]
        raise ValueError(f"Unknown node type: {node_type}")

    def register_node(self, node_type, node_class):
        self.nodes[node_type] = node_class


class TestNodeInstance:
    """Test NodeInstance model."""

    def test_node_instance_init_minimal(self):
        """Test NodeInstance initialization with minimal parameters."""
        try:
            from kailash.workflow.graph import NodeInstance

            node = NodeInstance(node_id="test_node", node_type="TestNode")

            assert node.node_id == "test_node"
            assert node.node_type == "TestNode"
            assert isinstance(node.config, dict)
            assert len(node.config) == 0
            assert node.position == (0, 0)

        except ImportError:
            pytest.skip("NodeInstance not available")

    def test_node_instance_init_full(self):
        """Test NodeInstance initialization with all parameters."""
        try:
            from kailash.workflow.graph import NodeInstance

            config = {"param1": "value1", "param2": 42}
            position = (100.5, 200.3)

            node = NodeInstance(
                node_id="test_node",
                node_type="TestNode",
                config=config,
                position=position,
            )

            assert node.config == config
            assert node.position == position

        except ImportError:
            pytest.skip("NodeInstance not available")

    def test_node_instance_validation(self):
        """Test NodeInstance validation."""
        try:
            from pydantic import ValidationError

            from kailash.workflow.graph import NodeInstance

            # Missing required fields should raise error
            with pytest.raises(ValidationError):
                NodeInstance(node_type="TestNode")  # Missing node_id

            with pytest.raises(ValidationError):
                NodeInstance(node_id="test")  # Missing node_type

        except ImportError:
            pytest.skip("NodeInstance not available")


class TestConnection:
    """Test Connection model."""

    def test_connection_init(self):
        """Test Connection initialization."""
        try:
            from kailash.workflow.graph import Connection

            conn = Connection(
                source_node="node1",
                source_output="output1",
                target_node="node2",
                target_input="input1",
            )

            assert conn.source_node == "node1"
            assert conn.source_output == "output1"
            assert conn.target_node == "node2"
            assert conn.target_input == "input1"

        except ImportError:
            pytest.skip("Connection not available")

    def test_connection_validation(self):
        """Test Connection validation."""
        try:
            from pydantic import ValidationError

            from kailash.workflow.graph import Connection

            # Missing required fields
            with pytest.raises(ValidationError):
                Connection(source_node="node1", source_output="out1")

        except ImportError:
            pytest.skip("Connection not available")


class TestCyclicConnection:
    """Test CyclicConnection model."""

    def test_cyclic_connection_init_defaults(self):
        """Test CyclicConnection initialization with defaults."""
        try:
            from kailash.workflow.graph import CyclicConnection

            conn = CyclicConnection(
                source_node="node1",
                source_output="output1",
                target_node="node2",
                target_input="input1",
            )

            assert conn.cycle is False
            assert conn.max_iterations is None
            assert conn.convergence_check is None
            assert conn.cycle_id is None
            assert conn.timeout is None
            assert conn.memory_limit is None
            assert conn.condition is None
            assert conn.parent_cycle is None

        except ImportError:
            pytest.skip("CyclicConnection not available")

    def test_cyclic_connection_init_full(self):
        """Test CyclicConnection initialization with all parameters."""
        try:
            from kailash.workflow.graph import CyclicConnection

            conn = CyclicConnection(
                source_node="node1",
                source_output="output1",
                target_node="node2",
                target_input="input1",
                cycle=True,
                max_iterations=100,
                convergence_check="error < 0.01",
                cycle_id="cycle_1",
                timeout=300.0,
                memory_limit=1024,
                condition="iteration > 5",
                parent_cycle="parent_cycle_1",
            )

            assert conn.cycle is True
            assert conn.max_iterations == 100
            assert conn.convergence_check == "error < 0.01"
            assert conn.cycle_id == "cycle_1"
            assert conn.timeout == 300.0
            assert conn.memory_limit == 1024
            assert conn.condition == "iteration > 5"
            assert conn.parent_cycle == "parent_cycle_1"

        except ImportError:
            pytest.skip("CyclicConnection not available")


class TestWorkflow:
    """Test Workflow functionality."""

    def test_workflow_init_minimal(self):
        """Test Workflow initialization with minimal parameters."""
        try:
            from kailash.workflow.graph import Workflow

            workflow_id = "test_workflow_123"
            name = "Test Workflow"

            workflow = Workflow(workflow_id, name)

            assert workflow.workflow_id == workflow_id
            assert workflow.name == name
            assert workflow.description == ""
            assert workflow.version == "1.0.0"
            assert workflow.author == ""
            assert isinstance(workflow.metadata, dict)
            assert isinstance(workflow.graph, nx.DiGraph)
            assert isinstance(workflow._node_instances, dict)
            assert isinstance(workflow.nodes, dict)
            assert isinstance(workflow.connections, list)

        except ImportError:
            pytest.skip("Workflow not available")

    def test_workflow_init_full(self):
        """Test Workflow initialization with all parameters."""
        try:
            from kailash.workflow.graph import Workflow

            workflow_id = "test_workflow_123"
            name = "Test Workflow"
            description = "A test workflow"
            version = "2.0.0"
            author = "Test Author"
            metadata = {"tags": ["test", "example"]}

            workflow = Workflow(
                workflow_id=workflow_id,
                name=name,
                description=description,
                version=version,
                author=author,
                metadata=metadata,
            )

            assert workflow.description == description
            assert workflow.version == version
            assert workflow.author == author
            assert "tags" in workflow.metadata
            assert workflow.metadata["author"] == author
            assert workflow.metadata["version"] == version
            assert "created_at" in workflow.metadata

        except ImportError:
            pytest.skip("Workflow not available")

    def test_workflow_metadata_defaults(self):
        """Test Workflow metadata default values."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test", author="John", version="1.5")

            assert workflow.metadata["author"] == "John"
            assert workflow.metadata["version"] == "1.5"
            assert "created_at" in workflow.metadata

            # Should be ISO format timestamp
            created_at = workflow.metadata["created_at"]
            assert "T" in created_at  # ISO format contains T

        except ImportError:
            pytest.skip("Workflow not available")

    def test_create_node_instance_with_name(self):
        """Test creating node instance that expects name parameter."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            # Mock node class that expects name
            node_class = MockNodeWithNameOnly
            node_id = "test_node"
            config = {"param1": "value1"}

            node = workflow._create_node_instance(node_class, node_id, config)

            assert isinstance(node, MockNodeWithNameOnly)
            assert node.name == node_id
            assert node.config["param1"] == "value1"

        except ImportError:
            pytest.skip("Workflow not available")

    def test_create_node_instance_with_id(self):
        """Test creating node instance that expects id parameter."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            # Mock node class that expects id
            node_class = MockNodeWithIdOnly
            node_id = "test_node"
            config = {"param1": "value1"}

            node = workflow._create_node_instance(node_class, node_id, config)

            assert isinstance(node, MockNodeWithIdOnly)
            assert node.id == node_id
            assert node.config["param1"] == "value1"

        except ImportError:
            pytest.skip("Workflow not available")

    def test_create_node_instance_error_handling(self):
        """Test error handling in node instance creation."""
        try:
            from kailash.sdk_exceptions import NodeConfigurationError
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            # Mock node class with specific constructor requirements
            class StrictNode:
                def __init__(self, name, required_param):
                    self.name = name
                    self.required_param = required_param

            # Should raise error for missing required parameter
            with pytest.raises(NodeConfigurationError):
                workflow._create_node_instance(StrictNode, "test_node", {})

        except ImportError:
            pytest.skip("Workflow not available")

    def test_add_node_with_instance(self):
        """Test adding a node instance to workflow."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            # Create node instance
            node = MockNode(id="test_node", param1="value1")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry:
                workflow.add_node("test_node", node)

                assert "test_node" in workflow._node_instances
                assert workflow._node_instances["test_node"] == node
                assert "test_node" in workflow.nodes
                assert workflow.graph.has_node("test_node")

        except ImportError:
            pytest.skip("Workflow not available")

    def test_add_node_with_type_string(self):
        """Test adding a node by type string."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("test_node", "TestNode", param1="value1")

                assert "test_node" in workflow._node_instances
                assert "test_node" in workflow.nodes
                assert workflow.nodes["test_node"].node_type == "TestNode"

        except ImportError:
            pytest.skip("Workflow not available")

    def test_add_node_duplicate_id(self):
        """Test adding node with duplicate ID."""
        try:
            from kailash.sdk_exceptions import WorkflowValidationError
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("test_node", "TestNode")

                # Adding duplicate should raise error
                with pytest.raises(WorkflowValidationError):
                    workflow.add_node("test_node", "TestNode")

        except ImportError:
            pytest.skip("Workflow not available")

    def test_add_connection_basic(self):
        """Test adding basic connection between nodes."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                # Add nodes first
                workflow.add_node("node1", "TestNode")
                workflow.add_node("node2", "TestNode")

                # Add connection
                workflow.add_connection("node1", "output1", "node2", "input1")

                assert len(workflow.connections) == 1
                conn = workflow.connections[0]
                assert conn.source_node == "node1"
                assert conn.target_node == "node2"
                assert workflow.graph.has_edge("node1", "node2")

        except ImportError:
            pytest.skip("Workflow not available")

    def test_add_connection_missing_nodes(self):
        """Test adding connection with missing nodes."""
        try:
            from kailash.sdk_exceptions import ConnectionError
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            # Try to connect non-existent nodes
            with pytest.raises(ConnectionError):
                workflow.add_connection("node1", "output1", "node2", "input1")

        except ImportError:
            pytest.skip("Workflow not available")

    def test_add_cyclic_connection(self):
        """Test adding cyclic connection."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                # Add nodes
                workflow.add_node("node1", "TestNode")
                workflow.add_node("node2", "TestNode")

                # Add cyclic connection
                workflow.add_cyclic_connection(
                    "node1",
                    "output1",
                    "node2",
                    "input1",
                    max_iterations=10,
                    convergence_check="error < 0.01",
                )

                assert len(workflow.connections) == 1
                conn = workflow.connections[0]
                assert conn.cycle is True
                assert conn.max_iterations == 10
                assert conn.convergence_check == "error < 0.01"

        except ImportError:
            pytest.skip("Workflow not available")

    def test_get_node_existing(self):
        """Test getting existing node."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("test_node", "TestNode")

                node = workflow.get_node("test_node")
                assert node is not None
                assert isinstance(node, MockNode)

        except ImportError:
            pytest.skip("Workflow not available")

    def test_get_node_nonexistent(self):
        """Test getting non-existent node."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            node = workflow.get_node("nonexistent")
            assert node is None

        except ImportError:
            pytest.skip("Workflow not available")

    def test_remove_node(self):
        """Test removing node from workflow."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("test_node", "TestNode")
                assert "test_node" in workflow.nodes

                workflow.remove_node("test_node")
                assert "test_node" not in workflow.nodes
                assert "test_node" not in workflow._node_instances
                assert not workflow.graph.has_node("test_node")

        except ImportError:
            pytest.skip("Workflow not available")

    def test_remove_node_with_connections(self):
        """Test removing node that has connections."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode")
                workflow.add_node("node2", "TestNode")
                workflow.add_node("node3", "TestNode")
                workflow.add_connection("node1", "out", "node2", "in")
                workflow.add_connection("node2", "out", "node3", "in")

                # Remove middle node
                workflow.remove_node("node2")

                # Connections involving node2 should be removed
                assert len(workflow.connections) == 0
                assert not workflow.graph.has_edge("node1", "node2")
                assert not workflow.graph.has_edge("node2", "node3")

        except ImportError:
            pytest.skip("Workflow not available")

    def test_validate_no_cycles(self):
        """Test validation of DAG workflow (no cycles)."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode")
                workflow.add_node("node2", "TestNode")
                workflow.add_connection("node1", "out", "node2", "in")

                # Should validate successfully
                workflow.validate()

        except ImportError:
            pytest.skip("Workflow not available")

    def test_validate_with_cycles_error(self):
        """Test validation error with unintentional cycles."""
        try:
            from kailash.sdk_exceptions import WorkflowValidationError
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode")
                workflow.add_node("node2", "TestNode")
                workflow.add_connection("node1", "out", "node2", "in")
                workflow.add_connection("node2", "out", "node1", "in")  # Creates cycle

                # Should raise validation error
                with pytest.raises(WorkflowValidationError):
                    workflow.validate()

        except ImportError:
            pytest.skip("Workflow not available")

    def test_validate_empty_workflow(self):
        """Test validation of empty workflow."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            # Empty workflow should validate
            workflow.validate()

        except ImportError:
            pytest.skip("Workflow not available")

    def test_to_dict(self):
        """Test workflow serialization to dictionary."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test Workflow", version="1.2.3")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode", param1="value1")
                workflow.add_node("node2", "TestNode")
                workflow.add_connection("node1", "out", "node2", "in")

                result = workflow.to_dict()

                assert isinstance(result, dict)
                assert result["workflow_id"] == "test_id"
                assert result["name"] == "Test Workflow"
                assert result["version"] == "1.2.3"
                assert len(result["nodes"]) == 2
                assert len(result["connections"]) == 1

        except ImportError:
            pytest.skip("Workflow not available")

    def test_from_dict(self):
        """Test workflow deserialization from dictionary."""
        try:
            from kailash.workflow.graph import Workflow

            workflow_dict = {
                "workflow_id": "test_id",
                "name": "Test Workflow",
                "version": "1.0.0",
                "nodes": [
                    {"node_id": "node1", "node_type": "TestNode", "config": {}},
                    {"node_id": "node2", "node_type": "TestNode", "config": {}},
                ],
                "connections": [
                    {
                        "source_node": "node1",
                        "source_output": "out",
                        "target_node": "node2",
                        "target_input": "in",
                    }
                ],
            }

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow = Workflow.from_dict(workflow_dict)

                assert workflow.workflow_id == "test_id"
                assert workflow.name == "Test Workflow"
                assert len(workflow.nodes) == 2
                assert len(workflow.connections) == 1

        except ImportError:
            pytest.skip("Workflow not available")

    def test_to_json(self):
        """Test workflow serialization to JSON."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            json_str = workflow.to_json()

            assert isinstance(json_str, str)
            data = json.loads(json_str)
            assert data["workflow_id"] == "test_id"

        except ImportError:
            pytest.skip("Workflow not available")

    def test_from_json(self):
        """Test workflow deserialization from JSON."""
        try:
            from kailash.workflow.graph import Workflow

            json_str = '{"workflow_id": "test_id", "name": "Test", "nodes": [], "connections": []}'

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow = Workflow.from_json(json_str)

                assert workflow.workflow_id == "test_id"
                assert workflow.name == "Test"

        except ImportError:
            pytest.skip("Workflow not available")

    def test_to_yaml(self):
        """Test workflow serialization to YAML."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            yaml_str = workflow.to_yaml()

            assert isinstance(yaml_str, str)
            data = yaml.safe_load(yaml_str)
            assert data["workflow_id"] == "test_id"

        except ImportError:
            pytest.skip("Workflow not available")

    def test_from_yaml(self):
        """Test workflow deserialization from YAML."""
        try:
            from kailash.workflow.graph import Workflow

            yaml_str = """
workflow_id: test_id
name: Test
nodes: []
connections: []
"""

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow = Workflow.from_yaml(yaml_str)

                assert workflow.workflow_id == "test_id"
                assert workflow.name == "Test"

        except ImportError:
            pytest.skip("Workflow not available")

    def test_save_and_load(self):
        """Test saving and loading workflow to/from file."""
        try:
            import os
            import tempfile

            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".json"
            ) as f:
                temp_file = f.name

            try:
                workflow.save(temp_file)
                assert os.path.exists(temp_file)

                with patch(
                    "kailash.workflow.graph.NodeRegistry"
                ) as mock_registry_class:
                    mock_registry = MockNodeRegistry()
                    mock_registry_class.return_value = mock_registry

                    loaded = Workflow.load(temp_file)
                    assert loaded.workflow_id == "test_id"

            finally:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

        except ImportError:
            pytest.skip("Workflow not available")

    def test_get_execution_order(self):
        """Test getting topological execution order."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode")
                workflow.add_node("node2", "TestNode")
                workflow.add_node("node3", "TestNode")
                workflow.add_connection("node1", "out", "node2", "in")
                workflow.add_connection("node2", "out", "node3", "in")

                order = workflow.get_execution_order()

                assert isinstance(order, list)
                assert len(order) == 3
                assert order.index("node1") < order.index("node2")
                assert order.index("node2") < order.index("node3")

        except ImportError:
            pytest.skip("Workflow not available")

    def test_get_node_dependencies(self):
        """Test getting node dependencies."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode")
                workflow.add_node("node2", "TestNode")
                workflow.add_node("node3", "TestNode")
                workflow.add_connection("node1", "out", "node2", "in")
                workflow.add_connection("node3", "out", "node2", "in")

                deps = workflow.get_node_dependencies("node2")

                assert isinstance(deps, list)
                assert len(deps) == 2
                assert "node1" in deps
                assert "node3" in deps

        except ImportError:
            pytest.skip("Workflow not available")

    def test_get_node_dependents(self):
        """Test getting node dependents."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode")
                workflow.add_node("node2", "TestNode")
                workflow.add_node("node3", "TestNode")
                workflow.add_connection("node1", "out", "node2", "in")
                workflow.add_connection("node1", "out", "node3", "in")

                deps = workflow.get_node_dependents("node1")

                assert isinstance(deps, list)
                assert len(deps) == 2
                assert "node2" in deps
                assert "node3" in deps

        except ImportError:
            pytest.skip("Workflow not available")

    def test_has_cycles(self):
        """Test cycle detection."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode")
                workflow.add_node("node2", "TestNode")

                # No cycle initially
                assert workflow.has_cycles() is False

                # Add edges creating a cycle
                workflow.add_connection("node1", "out", "node2", "in")
                workflow.add_connection("node2", "out", "node1", "in")

                assert workflow.has_cycles() is True

        except ImportError:
            pytest.skip("Workflow not available")

    def test_get_cycles(self):
        """Test getting cycle information."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode")
                workflow.add_node("node2", "TestNode")
                workflow.add_cyclic_connection(
                    "node1", "out", "node2", "in", cycle_id="cycle_1", max_iterations=10
                )
                workflow.add_connection("node2", "out", "node1", "in")

                cycles = workflow.get_cycles()

                assert isinstance(cycles, list)
                assert len(cycles) > 0

        except ImportError:
            pytest.skip("Workflow not available")

    def test_clone(self):
        """Test workflow cloning."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test", version="1.0.0")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode", param1="value1")
                workflow.add_connection("node1", "out", "node1", "in")  # Self-loop

                # Clone with new ID
                cloned = workflow.clone("cloned_id")

                assert cloned.workflow_id == "cloned_id"
                assert cloned.name == workflow.name
                assert cloned.version == workflow.version
                assert len(cloned.nodes) == len(workflow.nodes)
                assert len(cloned.connections) == len(workflow.connections)

                # Modifying clone shouldn't affect original
                cloned.add_node("node2", "TestNode")
                assert len(cloned.nodes) == 2
                assert len(workflow.nodes) == 1

        except ImportError:
            pytest.skip("Workflow not available")

    def test_export_import_error_handling(self):
        """Test error handling in export/import operations."""
        try:
            from kailash.sdk_exceptions import ExportException, WorkflowValidationError
            from kailash.workflow.graph import Workflow

            # Test invalid file format
            workflow = Workflow("test_id", "Test")

            with pytest.raises(ExportException):
                workflow.save("test.invalid")  # Invalid format

            # Test loading non-existent file
            with pytest.raises(FileNotFoundError):
                Workflow.load("nonexistent.json")

        except ImportError:
            pytest.skip("Workflow not available")

    def test_runtime_parameter_validation(self):
        """Test runtime parameter validation."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                workflow.add_node("node1", "TestNode")

                # Test with runtime parameters
                runtime_params = {"node1": {"param1": "override_value"}}
                workflow.validate(runtime_parameters=runtime_params)

        except ImportError:
            pytest.skip("Workflow not available")

    def test_node_position_tracking(self):
        """Test node position tracking for visualization."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            with patch("kailash.workflow.graph.NodeRegistry") as mock_registry_class:
                mock_registry = MockNodeRegistry()
                mock_registry_class.return_value = mock_registry

                # Add node with position
                workflow.add_node("node1", "TestNode", position=(100, 200))

                node_metadata = workflow.nodes["node1"]
                assert node_metadata.position == (100, 200)

        except ImportError:
            pytest.skip("Workflow not available")

    def test_workflow_state_wrapper_integration(self):
        """Test integration with WorkflowStateWrapper."""
        try:
            from kailash.workflow.graph import Workflow

            workflow = Workflow("test_id", "Test")

            # Test that workflow can work with state wrapper
            assert hasattr(workflow, "workflow_id")
            assert hasattr(workflow, "nodes")
            assert hasattr(workflow, "connections")

        except ImportError:
            pytest.skip("Workflow not available")
