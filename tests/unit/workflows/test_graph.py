"""Tests for workflow graph module."""

from typing import Any

import pytest
from kailash.nodes import NodeRegistry
from kailash.nodes.base import Node
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


class MockNode(Node):
    """Mock node for testing."""

    def __init__(self, node_id=None, name=None, **kwargs):
        """Initialize mock node."""
        self.node_id = node_id
        self.name = name or node_id
        self.config = kwargs

    def get_parameters(self):
        """Define input parameters for the mock node."""
        from kailash.nodes.base import NodeParameter

        return {
            "value": NodeParameter(
                name="value",
                type=float,
                required=False,
                description="Input value parameter",
                default=0.0,
            )
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Run node."""
        return {"output": "test"}

    def process(self, data: dict[str, Any]) -> dict[str, Any]:
        """Process data."""
        return {"value": data.get("value", 0) * 2}


# Store original NodeRegistry.get for cleanup
_original_get = NodeRegistry.get


def _mock_get(node_type: str):
    """Mock node registry getter."""
    if node_type == "MockNode" or node_type in [
        "DataReader",
        "DataWriter",
        "Processor",
        "Merger",
    ]:
        return MockNode
    # For other nodes, try to get from registry, but return MockNode if not found
    try:
        return _original_get(node_type)
    except:
        # If node not found, return MockNode for testing
        return MockNode


@pytest.fixture(autouse=True, scope="module")
def mock_node_registry():
    """Mock NodeRegistry.get for this module and restore it after tests."""
    NodeRegistry.get = _mock_get
    yield
    NodeRegistry.get = _original_get


@pytest.mark.requires_isolation
class TestWorkflow:
    """Test Workflow class."""

    def test_workflow_creation(self):
        """Test creating a workflow graph."""
        workflow = Workflow(workflow_id="test-workflow", name="Test Workflow")

        assert workflow.workflow_id == "test-workflow"
        assert workflow.name == "Test Workflow"
        assert workflow.description == ""
        assert workflow.version == "1.0.0"
        assert workflow.graph.number_of_nodes() == 0

    def test_workflow_with_metadata(self):
        """Test creating workflow with metadata."""
        metadata = {
            "author": "Test User",
            "tags": ["test", "example"],
            "created_date": "2024-01-01",
        }

        workflow = Workflow(
            workflow_id="test",
            name="Test",
            description="Test workflow",
            version="2.0.0",
            metadata=metadata,
        )

        assert workflow.description == "Test workflow"
        assert workflow.version == "2.0.0"
        assert workflow.metadata["author"] == "Test User"
        assert "tags" in workflow.metadata

    def test_add_node(self):
        """Test adding nodes to workflow."""
        builder = WorkflowBuilder()
        builder.add_node("MockNode", "node1")
        builder.add_node("MockNode", "node2")

        workflow = builder.build("test")

        # Mock the nodes
        workflow.graph.nodes["node1"]["node"] = MockNode(node_id="node1", name="Node 1")
        workflow.graph.nodes["node2"]["node"] = MockNode(node_id="node2", name="Node 2")

        assert workflow.graph.number_of_nodes() == 2
        assert "node1" in workflow.graph.nodes
        assert "node2" in workflow.graph.nodes

    def test_add_edge(self):
        """Test adding edges between nodes."""
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        builder.add_connection(node1_id, "output", node2_id, "input")

        workflow = builder.build("test")

        assert workflow.graph.has_edge("node1", "node2")
        assert workflow.graph.number_of_edges() == 1

    def test_add_edge_with_mapping(self):
        """Test adding edge with field mapping."""
        builder = WorkflowBuilder()
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")

        builder.add_connection(node1_id, "output_field", node2_id, "input_field")
        workflow = builder.build("test")

        edge_data = workflow.graph.edges["node1", "node2"]
        assert edge_data["from_output"] == "output_field"
        assert edge_data["to_input"] == "input_field"

    def test_get_node(self):
        """Test getting node by ID."""
        builder = WorkflowBuilder()
        builder.add_node("MockNode", "node1")
        workflow = builder.build("test")

        # Mock the node
        mock_node = MockNode(node_id="node1", name="Node 1")
        workflow.graph.nodes["node1"]["node"] = mock_node

        retrieved_node = workflow.get_node("node1")

        assert retrieved_node == mock_node
        assert retrieved_node.node_id == "node1"

    def test_get_nonexistent_node(self):
        """Test getting non-existent node."""
        workflow = Workflow(workflow_id="test", name="Test")

        assert workflow.get_node("nonexistent") is None

    def test_get_execution_order(self):
        """Test getting topological execution order."""
        builder = WorkflowBuilder()

        # Create a diamond graph
        start_id = builder.add_node("MockNode", "start")
        a_id = builder.add_node("MockNode", "a")
        b_id = builder.add_node("MockNode", "b")
        end_id = builder.add_node("MockNode", "end")

        builder.add_connection(start_id, "output", a_id, "input")
        builder.add_connection(start_id, "output", b_id, "input")
        builder.add_connection(a_id, "output", end_id, "input1")
        builder.add_connection(b_id, "output", end_id, "input2")

        workflow = builder.build("test")

        order = workflow.get_execution_order()

        assert len(order) == 4
        assert order[0] == "start"
        assert order[-1] == "end"
        assert order.index("a") > order.index("start")
        assert order.index("b") > order.index("start")

    def test_validate_workflow(self):
        """Test workflow validation."""
        builder = WorkflowBuilder()

        # Create a valid workflow
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        builder.add_connection(node1_id, "output", node2_id, "input")

        workflow = builder.build("test")

        # Should not raise exception
        workflow.validate()

    def test_validate_workflow_with_cycle(self):
        """Test validation with cyclic graph."""
        builder = WorkflowBuilder()

        # Create a cycle
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        node3_id = builder.add_node("MockNode", "node3")

        builder.add_connection(node1_id, "output", node2_id, "input")
        builder.add_connection(node2_id, "output", node3_id, "input")
        builder.add_connection(node3_id, "output", node1_id, "input")  # Creates cycle

        workflow = builder.build("test")

        # Use the generic exception to match either type
        with pytest.raises(Exception):
            workflow.validate()

    def test_get_metadata(self):
        """Test getting workflow metadata."""
        metadata = {"author": "Test", "version": "1.0"}
        workflow = Workflow(workflow_id="test", name="Test", metadata=metadata)

        assert workflow.metadata == metadata
        assert workflow.metadata["author"] == "Test"

    def test_workflow_repr(self):
        """Test workflow string representation."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")

        repr_str = repr(workflow)
        assert "Workflow" in repr_str
        assert "test" in repr_str
        assert "Test Workflow" in repr_str

    def test_workflow_str(self):
        """Test workflow string conversion."""
        workflow = Workflow(workflow_id="test", name="Test Workflow")

        str_repr = str(workflow)
        assert "test" in str_repr
        assert "Test Workflow" in str_repr


@pytest.mark.requires_isolation
class TestWorkflowBuilder:
    """Test WorkflowBuilder class."""

    def test_builder_creation(self):
        """Test creating workflow builder."""
        builder = WorkflowBuilder()

        assert builder.nodes == {}
        assert builder.connections == []

    def test_add_node(self):
        """Test adding node to builder."""
        builder = WorkflowBuilder()

        node_id = builder.add_node(
            node_type="MockNode", node_id="node1", config={"param1": "value1"}
        )

        assert node_id == "node1"
        assert "node1" in builder.nodes
        assert builder.nodes["node1"]["type"] == "MockNode"
        assert builder.nodes["node1"]["config"]["param1"] == "value1"

    def test_add_node_auto_id(self):
        """Test adding node with auto-generated ID."""
        builder = WorkflowBuilder()

        node_id = builder.add_node(node_type="MockNode")

        assert node_id is not None
        assert node_id in builder.nodes

    def test_add_connection(self):
        """Test adding connection between nodes."""
        builder = WorkflowBuilder()

        builder.add_node("MockNode", "node1")
        builder.add_node("MockNode", "node2")

        builder.add_connection(
            from_node="node1", from_output="output", to_node="node2", to_input="input"
        )

        assert len(builder.connections) == 1
        conn = builder.connections[0]
        assert conn["from_node"] == "node1"
        assert conn["from_output"] == "output"
        assert conn["to_node"] == "node2"
        assert conn["to_input"] == "input"

    def test_build_workflow(self):
        """Test building workflow from builder."""
        builder = WorkflowBuilder()

        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        builder.add_connection(node1_id, "output", node2_id, "input")

        workflow = builder.build("test-workflow", name="Test Workflow")

        assert workflow.workflow_id == "test-workflow"
        assert workflow.name == "Test Workflow"
        assert workflow.graph.number_of_nodes() == 2
        assert workflow.graph.number_of_edges() == 1

    def test_build_complex_workflow(self):
        """Test building complex workflow."""
        builder = WorkflowBuilder()

        # Create multiple nodes
        input_id = builder.add_node("DataReader", "input")
        process1_id = builder.add_node("Processor", "process1")
        process2_id = builder.add_node("Processor", "process2")
        merge_id = builder.add_node("Merger", "merge")
        output_id = builder.add_node("DataWriter", "output")

        # Create connections
        builder.add_connection(input_id, "data", process1_id, "input")
        builder.add_connection(input_id, "data", process2_id, "input")
        builder.add_connection(process1_id, "result", merge_id, "input1")
        builder.add_connection(process2_id, "result", merge_id, "input2")
        builder.add_connection(merge_id, "output", output_id, "data")

        workflow = builder.build("complex")

        assert workflow.graph.number_of_nodes() == 5
        assert workflow.graph.number_of_edges() == 5

    def test_clear_builder(self):
        """Test clearing builder state."""
        builder = WorkflowBuilder()

        # Add some nodes and connections
        node1_id = builder.add_node("MockNode", "node1")
        node2_id = builder.add_node("MockNode", "node2")
        builder.add_connection(node1_id, "output", node2_id, "input")

        # Clear the builder
        builder.clear()

        assert builder.nodes == {}
        assert builder.connections == []

    def test_from_dict(self):
        """Test creating workflow from dictionary."""
        config = {
            "workflow_id": "test",
            "name": "Test Workflow",
            "nodes": [
                {"type": "MockNode", "id": "node1", "config": {"value": 1.0}},
                {"type": "MockNode", "id": "node2", "config": {"value": 2.0}},
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
        workflow = builder.build("test")

        assert workflow.workflow_id == "test"
        assert workflow.name == "Test Workflow"
        assert workflow.graph.number_of_nodes() == 2
        assert workflow.graph.number_of_edges() == 1
