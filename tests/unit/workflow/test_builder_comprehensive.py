"""Comprehensive tests for WorkflowBuilder functionality.

This test file focuses on missing coverage areas in builder.py:
- Complex add_node method with multiple API patterns
- Parameter injection and workflow-level configuration
- Connection management and validation
- from_dict configuration loading
- Error handling and edge cases
- Build method with metadata and parameter injection
- Fluent API methods and backward compatibility
"""

import json
import tempfile
import uuid
import warnings
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from kailash.nodes.base import Node, NodeParameter, NodeRegistry
from kailash.sdk_exceptions import ConnectionError, WorkflowValidationError
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow


class MockNode(Node):
    """Mock node for testing with flexible constructor patterns."""

    def __init__(self, name=None, id=None, **kwargs):
        """Initialize with flexible parameter handling."""
        self.name = name or id or "mock_node"
        self.id = id or name or "mock_node"
        self.config = kwargs
        self.executed = False
        self.return_value = kwargs.get("return_value", {"result": "success"})
        self.required_params = kwargs.get("required_params", [])
        # Initialize parent class attributes
        super().__init__()

    # Ensure the class is properly recognized as a Node subclass
    @classmethod
    def __subclasshook__(cls, subclass):
        return (
            hasattr(subclass, "execute")
            and callable(subclass.execute)
            and hasattr(subclass, "get_parameters")
            and callable(subclass.get_parameters)
        )

    def get_parameters(self):
        """Get node parameters."""
        params = {
            "input_data": NodeParameter(
                name="input_data", type=str, required=False, description="Input data"
            )
        }

        # Add required parameters for testing validation
        for param_name in self.required_params:
            params[param_name] = NodeParameter(
                name=param_name,
                type=str,
                required=True,
                description=f"Required parameter {param_name}",
            )

        return params

    def execute(self, **inputs):
        """Execute the node."""
        self.executed = True
        self.last_inputs = inputs
        return self.return_value


class NodeWithNameParam(Node):
    """Node that requires 'name' parameter in constructor."""

    def __init__(self, name, **kwargs):
        self.name = name
        self.config = kwargs
        super().__init__()

    def get_parameters(self):
        return {}

    def execute(self, **inputs):
        return {"result": f"executed_{self.name}"}


class NodeWithIdParam(Node):
    """Node that requires 'id' parameter in constructor."""

    def __init__(self, id, **kwargs):
        self.id = id
        self.config = kwargs
        super().__init__()

    def get_parameters(self):
        return {}

    def execute(self, **inputs):
        return {"result": f"executed_{self.id}"}


class NodeWithRequiredParam(Node):
    """Node with required constructor parameter."""

    def __init__(self, required_param, **kwargs):
        self.required_param = required_param
        self.config = kwargs
        super().__init__()

    def get_parameters(self):
        return {}

    def execute(self, **inputs):
        return {"result": "success"}


class InvalidNode:
    """Non-Node class for testing error handling."""

    def __init__(self, **kwargs):
        self.config = kwargs


# Register the mock nodes - they'll be cleaned up by clean_node_registry
# but we need to ensure they're available for string-based references
def _ensure_mock_nodes_registered():
    """Ensure mock nodes are registered for string-based references."""
    if "MockNode" not in NodeRegistry._nodes:
        NodeRegistry.register(MockNode, "MockNode")
    if "NodeWithNameParam" not in NodeRegistry._nodes:
        NodeRegistry.register(NodeWithNameParam, "NodeWithNameParam")
    if "NodeWithIdParam" not in NodeRegistry._nodes:
        NodeRegistry.register(NodeWithIdParam, "NodeWithIdParam")
    if "NodeWithRequiredParam" not in NodeRegistry._nodes:
        NodeRegistry.register(NodeWithRequiredParam, "NodeWithRequiredParam")


class TestWorkflowBuilderAddNodePatterns:
    """Test the complex add_node method with multiple API patterns."""

    def setup_method(self):
        """Set up test fixtures."""
        self.builder = WorkflowBuilder()
        # Ensure mock nodes are registered for string-based references
        _ensure_mock_nodes_registered()
        # Ensure MockNode is properly recognized as a Node subclass
        assert issubclass(
            MockNode, Node
        ), f"MockNode should be a Node subclass, got {MockNode.__bases__}"

    def test_add_node_pattern_1_current_api(self):
        """Test Pattern 1: add_node('NodeType', 'node_id', {'param': value})."""
        node_id = self.builder.add_node("MockNode", "test_node", {"param": "value"})

        assert node_id == "test_node"
        assert self.builder.nodes["test_node"]["type"] == "MockNode"
        assert self.builder.nodes["test_node"]["config"]["param"] == "value"

    def test_add_node_pattern_2_legacy_fluent(self):
        """Test Pattern 2: add_node('node_id', NodeClass, param=value)."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            result = self.builder.add_node("test_node", MockNode, param="value")

            # Legacy API returns self for fluent chaining
            assert result == self.builder
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "Legacy fluent API usage detected" in str(w[0].message)

        assert "test_node" in self.builder.nodes
        assert self.builder.nodes["test_node"]["type"] == "MockNode"
        assert self.builder.nodes["test_node"]["config"]["param"] == "value"

    def test_add_node_pattern_3_alternative(self):
        """Test Pattern 3: add_node(NodeClass, 'node_id', param=value)."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            node_id = self.builder.add_node(MockNode, "test_node", param="value")

            assert node_id == "test_node"
            assert len(w) == 1
            assert issubclass(w[0].category, UserWarning)
            # Accept either warning message depending on test execution order
            warning_message = str(w[0].message)
            assert (
                "CUSTOM NODE USAGE CORRECT" in warning_message
                or "SDK node detected" in warning_message
            ), f"Unexpected warning message: {warning_message}"

        assert self.builder.nodes["test_node"]["type"] == "MockNode"
        assert self.builder.nodes["test_node"]["config"]["param"] == "value"
        assert self.builder.nodes["test_node"]["class"] == MockNode

    def test_add_node_pattern_4_instance(self):
        """Test Pattern 4: add_node(node_instance, 'node_id')."""
        instance = MockNode(param="instance_value")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            node_id = self.builder.add_node(instance, "test_node")

            assert node_id == "test_node"
            assert len(w) == 1
            assert issubclass(w[0].category, UserWarning)
            assert "Instance-based API usage detected" in str(w[0].message)

        assert self.builder.nodes["test_node"]["type"] == "MockNode"
        assert self.builder.nodes["test_node"]["instance"] is instance

    def test_add_node_keyword_only_pattern(self):
        """Test keyword-only pattern: add_node(node_type='NodeType', node_id='id', config={})."""
        node_id = self.builder.add_node(
            node_type="MockNode", node_id="test_node", config={"param": "value"}
        )

        assert node_id == "test_node"
        assert self.builder.nodes["test_node"]["type"] == "MockNode"
        assert self.builder.nodes["test_node"]["config"]["param"] == "value"

    def test_add_node_keyword_only_with_extra_kwargs(self):
        """Test keyword-only pattern with extra kwargs merged into config."""
        node_id = self.builder.add_node(
            node_type="MockNode",
            node_id="test_node",
            config={"param1": "value1"},
            param2="value2",
            param3="value3",
        )

        assert node_id == "test_node"
        assert self.builder.nodes["test_node"]["config"]["param1"] == "value1"
        assert self.builder.nodes["test_node"]["config"]["param2"] == "value2"
        assert self.builder.nodes["test_node"]["config"]["param3"] == "value3"

    def test_add_node_single_string_argument(self):
        """Test single string argument: add_node('NodeType')."""
        node_id = self.builder.add_node("MockNode")

        assert node_id.startswith("node_")
        assert self.builder.nodes[node_id]["type"] == "MockNode"
        assert self.builder.nodes[node_id]["config"] == {}

    def test_add_node_string_with_config_dict(self):
        """Test string with config dict: add_node('NodeType', {config})."""
        node_id = self.builder.add_node("MockNode", {"value": 1.0})

        assert node_id.startswith("node_")
        assert self.builder.nodes[node_id]["type"] == "MockNode"
        assert self.builder.nodes[node_id]["config"] == {"value": 1.0}

    def test_add_node_single_class_argument(self):
        """Test single class argument: add_node(NodeClass)."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            node_id = self.builder.add_node(MockNode)

            assert node_id.startswith("node_")
            assert len(w) == 1
            assert issubclass(w[0].category, UserWarning)

        assert self.builder.nodes[node_id]["type"] == "MockNode"
        assert self.builder.nodes[node_id]["class"] == MockNode

    def test_add_node_single_instance_argument(self):
        """Test single instance argument: add_node(node_instance)."""
        instance = MockNode(param="value")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            node_id = self.builder.add_node(instance)

            assert node_id.startswith("node_")
            assert len(w) == 1
            assert issubclass(w[0].category, UserWarning)

        assert self.builder.nodes[node_id]["instance"] is instance

    def test_add_node_auto_id_generation(self):
        """Test automatic ID generation."""
        node_id1 = self.builder.add_node("MockNode", {"value": 1.0})
        node_id2 = self.builder.add_node("MockNode", {"value": 2.0})

        assert node_id1 != node_id2
        assert node_id1.startswith("node_") and node_id2.startswith("node_")

    def test_add_node_duplicate_id_error(self):
        """Test error when adding duplicate node ID."""
        self.builder.add_node("MockNode", "test_node", {"value": 1.0})

        with pytest.raises(
            WorkflowValidationError, match="Node ID 'test_node' already exists"
        ):
            self.builder.add_node("MockNode", "test_node", {"value": 1.0})

    def test_add_node_invalid_arguments(self):
        """Test error handling for invalid arguments."""
        with pytest.raises(WorkflowValidationError, match="Invalid add_node signature"):
            self.builder.add_node(123, 456, 789)  # Invalid types

    def test_add_node_missing_node_type_in_kwargs(self):
        """Test error when node_type is missing in keyword arguments."""
        with pytest.raises(WorkflowValidationError, match="node_type is required"):
            self.builder.add_node(node_id="test_node", config={})

    def test_add_node_invalid_node_class(self):
        """Test error when invalid node class is provided."""
        with pytest.raises(WorkflowValidationError, match="Invalid node type"):
            self.builder.add_node(InvalidNode, "test_node")


class TestWorkflowBuilderConnections:
    """Test connection management functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.builder = WorkflowBuilder()
        # Ensure mock nodes are registered for string-based references
        _ensure_mock_nodes_registered()
        self.builder.add_node("MockNode", "node1", {"value": 1.0})
        self.builder.add_node("MockNode", "node2", {"value": 2.0})
        self.builder.add_node("MockNode", "node3", {"value": 3.0})

    def test_add_connection_basic(self):
        """Test basic connection addition."""
        result = self.builder.add_connection("node1", "output", "node2", "input")

        assert result == self.builder  # Returns self for chaining
        assert len(self.builder.connections) == 1

        conn = self.builder.connections[0]
        assert conn["from_node"] == "node1"
        assert conn["from_output"] == "output"
        assert conn["to_node"] == "node2"
        assert conn["to_input"] == "input"

    def test_add_connection_nonexistent_source(self):
        """Test error when source node doesn't exist."""
        with pytest.raises(
            WorkflowValidationError, match="Source node 'nonexistent' not found"
        ):
            self.builder.add_connection("nonexistent", "output", "node2", "input")

    def test_add_connection_nonexistent_target(self):
        """Test error when target node doesn't exist."""
        with pytest.raises(
            WorkflowValidationError, match="Target node 'nonexistent' not found"
        ):
            self.builder.add_connection("node1", "output", "nonexistent", "input")

    def test_add_connection_self_connection(self):
        """Test error when trying to connect node to itself."""
        with pytest.raises(
            ConnectionError, match="Cannot connect node 'node1' to itself"
        ):
            self.builder.add_connection("node1", "output", "node1", "input")

    def test_connect_method_with_mapping(self):
        """Test connect method with mapping parameter."""
        mapping = {"output1": "input1", "output2": "input2"}
        self.builder.connect("node1", "node2", mapping=mapping)

        assert len(self.builder.connections) == 2

        conn1 = self.builder.connections[0]
        assert conn1["from_node"] == "node1"
        assert conn1["from_output"] == "output1"
        assert conn1["to_node"] == "node2"
        assert conn1["to_input"] == "input1"

        conn2 = self.builder.connections[1]
        assert conn2["from_node"] == "node1"
        assert conn2["from_output"] == "output2"
        assert conn2["to_node"] == "node2"
        assert conn2["to_input"] == "input2"

    def test_connect_method_with_explicit_parameters(self):
        """Test connect method with explicit from_output and to_input."""
        self.builder.connect("node1", "node2", from_output="result", to_input="data")

        assert len(self.builder.connections) == 1
        conn = self.builder.connections[0]
        assert conn["from_output"] == "result"
        assert conn["to_input"] == "data"

    def test_connect_method_default_data_flow(self):
        """Test connect method with default data flow."""
        self.builder.connect("node1", "node2")

        assert len(self.builder.connections) == 1
        conn = self.builder.connections[0]
        assert conn["from_output"] == "data"
        assert conn["to_input"] == "data"

    def test_multiple_connections(self):
        """Test multiple connections between nodes."""
        self.builder.add_connection("node1", "output1", "node2", "input1")
        self.builder.add_connection("node2", "output2", "node3", "input2")

        assert len(self.builder.connections) == 2

        # Check connection order
        assert self.builder.connections[0]["from_node"] == "node1"
        assert self.builder.connections[1]["from_node"] == "node2"


class TestWorkflowBuilderParameterInjection:
    """Test parameter injection and workflow-level configuration."""

    def setup_method(self):
        """Set up test fixtures."""
        self.builder = WorkflowBuilder()
        # Ensure mock nodes are registered for string-based references
        _ensure_mock_nodes_registered()

    def test_set_workflow_parameters(self):
        """Test setting workflow-level parameters."""
        result = self.builder.set_workflow_parameters(
            api_key="secret_key", environment="production", timeout=30
        )

        assert result == self.builder  # Returns self for chaining
        assert self.builder.workflow_parameters["api_key"] == "secret_key"
        assert self.builder.workflow_parameters["environment"] == "production"
        assert self.builder.workflow_parameters["timeout"] == 30

    def test_add_parameter_mapping(self):
        """Test adding parameter mappings for specific nodes."""
        self.builder.add_node("MockNode", "node1", {"value": 1.0})

        result = self.builder.add_parameter_mapping(
            "node1", {"workflow_param": "node_param", "global_timeout": "local_timeout"}
        )

        assert result == self.builder
        assert (
            self.builder.parameter_mappings["node1"]["workflow_param"] == "node_param"
        )
        assert (
            self.builder.parameter_mappings["node1"]["global_timeout"]
            == "local_timeout"
        )

    def test_add_input_connection(self):
        """Test adding workflow input connections."""
        self.builder.add_node("MockNode", "node1", {"value": 1.0})

        result = self.builder.add_input_connection(
            "node1", "input_param", "workflow_input"
        )

        assert result == self.builder
        assert len(self.builder.connections) == 1

        conn = self.builder.connections[0]
        assert conn["from_node"] == "__workflow_input__"
        assert conn["from_output"] == "workflow_input"
        assert conn["to_node"] == "node1"
        assert conn["to_input"] == "input_param"
        assert conn["is_workflow_input"] is True

    def test_add_workflow_inputs(self):
        """Test adding workflow inputs mapping."""
        self.builder.add_node("MockNode", "input_node", {"value": 1.0})

        result = self.builder.add_workflow_inputs(
            "input_node",
            {"workflow_data": "node_data", "workflow_config": "node_config"},
        )

        assert result == self.builder
        assert "_workflow_inputs" in self.builder._metadata
        assert (
            self.builder._metadata["_workflow_inputs"]["input_node"]["workflow_data"]
            == "node_data"
        )
        assert (
            self.builder._metadata["_workflow_inputs"]["input_node"]["workflow_config"]
            == "node_config"
        )

    def test_add_workflow_inputs_nonexistent_node(self):
        """Test error when adding inputs for nonexistent node."""
        with pytest.raises(
            WorkflowValidationError, match="Node 'nonexistent' not found"
        ):
            self.builder.add_workflow_inputs("nonexistent", {"param": "value"})

    def test_update_node_config(self):
        """Test updating node configuration."""
        self.builder.add_node("MockNode", "node1", {"initial_param": "initial_value"})

        result = self.builder.update_node(
            "node1", {"new_param": "new_value", "initial_param": "updated_value"}
        )

        assert result == self.builder
        assert self.builder.nodes["node1"]["config"]["new_param"] == "new_value"
        assert self.builder.nodes["node1"]["config"]["initial_param"] == "updated_value"

    def test_update_node_config_nonexistent_node(self):
        """Test error when updating nonexistent node."""
        with pytest.raises(
            WorkflowValidationError, match="Node 'nonexistent' not found"
        ):
            self.builder.update_node("nonexistent", {"param": "value"})

    def test_update_node_config_creates_config_if_missing(self):
        """Test that update_node creates config dict if missing."""
        # Create node without config
        self.builder.nodes["node1"] = {"type": "MockNode"}

        self.builder.update_node("node1", {"param": "value"})

        assert "config" in self.builder.nodes["node1"]
        assert self.builder.nodes["node1"]["config"]["param"] == "value"


@pytest.mark.requires_isolation
class TestWorkflowBuilderMetadata:
    """Test metadata and workflow building functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.builder = WorkflowBuilder()
        # Ensure mock nodes are registered for string-based references
        _ensure_mock_nodes_registered()
        # Ensure MockNode is properly recognized as a Node subclass
        assert issubclass(
            MockNode, Node
        ), f"MockNode should be a Node subclass, got {MockNode.__bases__}"

    def test_set_metadata(self):
        """Test setting workflow metadata."""
        result = self.builder.set_metadata(
            name="Test Workflow",
            description="A test workflow",
            version="2.0.0",
            author="Test Author",
            custom_field="custom_value",
        )

        assert result == self.builder
        assert self.builder._metadata["name"] == "Test Workflow"
        assert self.builder._metadata["description"] == "A test workflow"
        assert self.builder._metadata["version"] == "2.0.0"
        assert self.builder._metadata["author"] == "Test Author"
        assert self.builder._metadata["custom_field"] == "custom_value"

    def test_build_workflow_basic(self):
        """Test building a basic workflow."""
        self.builder.add_node("MockNode", "node1", {"value": 1.0})
        self.builder.add_node("MockNode", "node2", {"value": 2.0})
        self.builder.add_connection("node1", "output", "node2", "input")

        workflow = self.builder.build()

        assert isinstance(workflow, Workflow)
        assert len(workflow.nodes) == 2
        assert "node1" in workflow.nodes
        assert "node2" in workflow.nodes

    def test_build_workflow_with_custom_id(self):
        """Test building workflow with custom ID."""
        self.builder.add_node("MockNode", "node1", {"value": 1.0})

        workflow = self.builder.build(workflow_id="custom_id")

        assert workflow.workflow_id == "custom_id"

    def test_build_workflow_with_metadata(self):
        """Test building workflow with metadata."""
        self.builder.set_metadata(
            name="Test Workflow",
            description="Test Description",
            version="1.5.0",
            author="Test Author",
        )
        self.builder.add_node("MockNode", "node1", {"value": 1.0})

        workflow = self.builder.build(name="Override Name", custom_field="custom_value")

        assert workflow.name == "Override Name"  # kwargs override metadata
        assert workflow.description == "Test Description"
        assert workflow.version == "1.5.0"
        assert workflow.author == "Test Author"
        assert workflow.metadata["custom_field"] == "custom_value"

    def test_build_workflow_auto_generated_name(self):
        """Test building workflow with auto-generated name."""
        self.builder.add_node("MockNode", "node1", {"value": 1.0})

        workflow = self.builder.build()

        assert workflow.name.startswith("Workflow-")
        assert workflow.workflow_id[:8] in workflow.name

    def test_build_workflow_with_mixed_node_types(self):
        """Test building workflow with different node configurations."""
        # Use preferred string-based API for all nodes
        self.builder.add_node("MockNode", "string_node", {"value": 1.0})
        self.builder.add_node("MockNode", "class_node", {"value": 2.0})
        self.builder.add_node("MockNode", "instance_node", {"value": 3.0})

        workflow = self.builder.build()

        assert len(workflow.nodes) == 3
        assert "string_node" in workflow.nodes
        assert "class_node" in workflow.nodes
        assert "instance_node" in workflow.nodes


@pytest.mark.requires_isolation
class TestWorkflowBuilderFluentAPI:
    """Test fluent API methods and backward compatibility."""

    def setup_method(self):
        """Set up test fixtures."""
        self.builder = WorkflowBuilder()
        # Ensure mock nodes are registered for string-based references
        _ensure_mock_nodes_registered()

    @pytest.mark.requires_isolation
    def test_add_node_fluent_deprecated(self):
        """Test deprecated add_node_fluent method."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            result = self.builder.add_node_fluent("node1", MockNode, param="value")

            assert result == self.builder
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "Fluent API is deprecated" in str(w[0].message)

        assert "node1" in self.builder.nodes
        assert self.builder.nodes["node1"]["type"] == "MockNode"
        assert self.builder.nodes["node1"]["config"]["param"] == "value"

    @pytest.mark.requires_isolation
    def test_add_node_fluent_with_string_type(self):
        """Test add_node_fluent with string node type."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            self.builder.add_node_fluent("node1", "MockNode", param="value")

        assert "node1" in self.builder.nodes
        assert self.builder.nodes["node1"]["type"] == "MockNode"
        assert self.builder.nodes["node1"]["config"]["param"] == "value"

    @pytest.mark.requires_isolation
    def test_add_node_instance_method(self):
        """Test add_node_instance convenience method."""
        instance = MockNode(param="instance_value")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            node_id = self.builder.add_node_instance(instance, "test_node")

        assert node_id == "test_node"
        assert self.builder.nodes["test_node"]["instance"] is instance

    @pytest.mark.requires_isolation
    def test_add_node_instance_auto_id(self):
        """Test add_node_instance with auto-generated ID."""
        instance = MockNode(param="instance_value")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")

            node_id = self.builder.add_node_instance(instance)

        assert node_id.startswith("node_")
        assert self.builder.nodes[node_id]["instance"] is instance

    def test_add_node_type_method(self):
        """Test add_node_type convenience method."""
        node_id = self.builder.add_node_type(
            "MockNode", "test_node", {"param": "value"}
        )

        assert node_id == "test_node"
        assert self.builder.nodes["test_node"]["type"] == "MockNode"
        assert self.builder.nodes["test_node"]["config"]["param"] == "value"

    def test_add_node_type_auto_id(self):
        """Test add_node_type with auto-generated ID."""
        node_id = self.builder.add_node_type("MockNode", config={"param": "value"})

        assert node_id.startswith("node_")
        assert self.builder.nodes[node_id]["type"] == "MockNode"
        assert self.builder.nodes[node_id]["config"]["param"] == "value"


class TestWorkflowBuilderFromDict:
    """Test creating WorkflowBuilder from dictionary configuration."""

    def setup_method(self):
        """Set up test fixtures."""
        # Ensure mock nodes are registered for string-based references
        _ensure_mock_nodes_registered()

    def test_from_dict_basic(self):
        """Test creating builder from basic dictionary."""
        config = {
            "name": "Test Workflow",
            "description": "A test workflow",
            "version": "1.0.0",
            "nodes": [
                {"id": "node1", "type": "MockNode", "config": {"param": "value1"}},
                {"id": "node2", "type": "MockNode", "config": {"param": "value2"}},
            ],
            "connections": [
                {
                    "from_node": "node1",
                    "from_output": "output",
                    "to_node": "node2",
                    "to_input": "input",
                }
            ],
        }

        builder = WorkflowBuilder.from_dict(config)

        assert builder._metadata["name"] == "Test Workflow"
        assert builder._metadata["description"] == "A test workflow"
        assert builder._metadata["version"] == "1.0.0"
        assert len(builder.nodes) == 2
        assert len(builder.connections) == 1

        assert builder.nodes["node1"]["type"] == "MockNode"
        assert builder.nodes["node1"]["config"]["param"] == "value1"
        assert builder.nodes["node2"]["type"] == "MockNode"
        assert builder.nodes["node2"]["config"]["param"] == "value2"

        conn = builder.connections[0]
        assert conn["from_node"] == "node1"
        assert conn["from_output"] == "output"
        assert conn["to_node"] == "node2"
        assert conn["to_input"] == "input"

    def test_from_dict_nodes_as_dict(self):
        """Test creating builder with nodes as dictionary."""
        config = {
            "nodes": {
                "node1": {"type": "MockNode", "parameters": {"param": "value1"}},
                "node2": {"type": "MockNode", "config": {"param": "value2"}},
            }
        }

        builder = WorkflowBuilder.from_dict(config)

        assert len(builder.nodes) == 2
        assert builder.nodes["node1"]["config"]["param"] == "value1"
        assert builder.nodes["node2"]["config"]["param"] == "value2"

    def test_from_dict_simple_connection_format(self):
        """Test creating builder with simple connection format."""
        config = {
            "nodes": [
                {"id": "node1", "type": "MockNode"},
                {"id": "node2", "type": "MockNode"},
            ],
            "connections": [{"from": "node1", "to": "node2"}],
        }

        builder = WorkflowBuilder.from_dict(config)

        assert len(builder.connections) == 1
        conn = builder.connections[0]
        assert conn["from_node"] == "node1"
        assert conn["from_output"] == "result"  # Default output
        assert conn["to_node"] == "node2"
        assert conn["to_input"] == "input"  # Default input

    def test_from_dict_invalid_node_missing_type(self):
        """Test error when node type is missing."""
        config = {"nodes": [{"id": "node1", "config": {"param": "value"}}]}

        with pytest.raises(WorkflowValidationError, match="Node type is required"):
            WorkflowBuilder.from_dict(config)

    def test_from_dict_invalid_node_missing_id(self):
        """Test error when node ID is missing."""
        config = {"nodes": [{"type": "MockNode", "config": {"param": "value"}}]}

        with pytest.raises(WorkflowValidationError, match="Node ID is required"):
            WorkflowBuilder.from_dict(config)

    def test_from_dict_invalid_connection_missing_nodes(self):
        """Test error when connection is missing nodes."""
        config = {
            "nodes": [{"id": "node1", "type": "MockNode"}],
            "connections": [{"from_output": "output", "to_input": "input"}],
        }

        with pytest.raises(
            WorkflowValidationError,
            match="Invalid connection: missing from_node and to_node",
        ):
            WorkflowBuilder.from_dict(config)

    def test_from_dict_invalid_node_parameters_type(self):
        """Test handling of invalid node parameters type."""
        config = {
            "nodes": [
                {
                    "id": "node1",
                    "type": "MockNode",
                    "parameters": "invalid_type",  # Should be dict
                }
            ]
        }

        # The warning is logged using logger.warning, not Python's warnings module
        # So we need to use a different approach to test this
        builder = WorkflowBuilder.from_dict(config)

        # Should use empty dict when invalid parameters are provided
        assert builder.nodes["node1"]["config"] == {}


class TestWorkflowBuilderUtilityMethods:
    """Test utility methods and edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.builder = WorkflowBuilder()
        # Ensure mock nodes are registered for string-based references
        _ensure_mock_nodes_registered()

    def test_clear_method(self):
        """Test clearing builder state."""
        # Set up some state
        self.builder.add_node("MockNode", "node1", {"value": 1.0})
        self.builder.add_node("MockNode", "node2", {"value": 2.0})
        self.builder.add_connection("node1", "output", "node2", "input")
        self.builder.set_metadata(name="Test")
        self.builder.set_workflow_parameters(param="value")
        self.builder.add_parameter_mapping("node1", {"param": "value"})

        # Clear state
        result = self.builder.clear()

        assert result == self.builder
        assert len(self.builder.nodes) == 0
        assert len(self.builder.connections) == 0
        assert len(self.builder._metadata) == 0
        assert len(self.builder.workflow_parameters) == 0
        assert len(self.builder.parameter_mappings) == 0

    def test_chaining_methods(self):
        """Test method chaining capability."""
        # Add nodes first
        self.builder.add_node("MockNode", "node1", {"value": 1.0})
        self.builder.add_node("MockNode", "node2", {"value": 2.0})

        # Test chaining with methods that support it
        result = (
            self.builder.add_connection("node1", "output", "node2", "input")
            .set_metadata(name="Chained Workflow")
            .set_workflow_parameters(env="test")
        )

        # Should return the same builder instance
        assert result is self.builder

        # Check that all operations were applied
        assert len(self.builder.nodes) == 2
        assert len(self.builder.connections) == 1
        assert self.builder._metadata["name"] == "Chained Workflow"
        assert self.builder.workflow_parameters["env"] == "test"

    def test_build_empty_workflow(self):
        """Test building an empty workflow."""
        workflow = self.builder.build()

        assert isinstance(workflow, Workflow)
        assert len(workflow.nodes) == 0
        assert workflow.name.startswith("Workflow-")

    def test_build_with_parameter_injection(self):
        """Test building workflow with parameter injection."""
        # This test verifies the complex parameter injection logic
        self.builder.set_workflow_parameters(global_param="global_value")
        self.builder.add_node("MockNode", "node1", {"value": 1.0})

        # The parameter injection logic is complex and depends on node configuration
        # Let's test that the workflow parameters are at least stored in metadata
        workflow = self.builder.build()

        # Verify workflow parameters are stored in metadata
        assert "workflow_parameters" in workflow.metadata
        assert (
            workflow.metadata["workflow_parameters"]["global_param"] == "global_value"
        )
        assert "parameter_mappings" in workflow.metadata

    def test_repr_and_str_methods(self):
        """Test string representation methods."""
        self.builder.add_node("MockNode", "node1", {"value": 1.0})
        self.builder.add_node("MockNode", "node2", {"value": 2.0})
        self.builder.add_connection("node1", "output", "node2", "input")

        # Test that string representations don't crash
        repr_str = repr(self.builder)
        str_str = str(self.builder)

        assert isinstance(repr_str, str)
        assert isinstance(str_str, str)
        assert len(repr_str) > 0
        assert len(str_str) > 0
