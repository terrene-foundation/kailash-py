"""Shared fixtures for Kailash tests."""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Generator

from kailash.nodes.base import Node, NodeMetadata
from kailash.workflow import Workflow
from kailash.tracking.models import TaskRun, TaskStatus
from kailash.tracking.manager import TaskManager
from kailash.tracking.storage.filesystem import FileSystemStorage


class MockNode(Node):
    """Mock node for testing."""
    
    def __init__(self, name: str, **kwargs):
        """Initialize mock node with metadata."""
        metadata = NodeMetadata(
            name=name,
            description="Mock node for testing",
            tags={"test", "mock"}
        )
        super().__init__(metadata=metadata, **kwargs)
    
    def get_parameters(self) -> Dict[str, Any]:
        """Define input parameters for the mock node."""
        from kailash.nodes.base import NodeParameter
        return {
            "value": NodeParameter(
                name="value",
                type=float,
                required=True,
                description="Input value to double"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic."""
        value = kwargs.get("value", 0)
        return {"result": value * 2}


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def mock_node():
    """Create a mock node instance."""
    return MockNode(name="Test Node")


@pytest.fixture
def mock_node_with_config():
    """Create a mock node with configuration."""
    node = MockNode(name="Test Node with Config")
    node.config = {
        "version": "1.0.0",
        "description": "A test node",
        "dependencies": ["test-dep"]
    }
    return node


@pytest.fixture
def sample_workflow():
    """Create a sample workflow graph."""
    workflow = Workflow(name="Test Workflow")
    
    # Add nodes
    node1 = MockNode(name="Node 1")
    node2 = MockNode(name="Node 2")
    
    workflow.add_node(node1)
    workflow.add_node(node2)
    workflow.add_edge(node1, node2)
    
    return workflow


@pytest.fixture
def sample_task():
    """Create a sample task."""
    return TaskRun(
        task_id="test-task",
        run_id="test-run",
        node_id="test-node",
        node_type="MockNode",
        status=TaskStatus.PENDING,
        metadata={"user": "test"}
    )


@pytest.fixture
def task_manager(temp_dir):
    """Create a task manager with filesystem storage."""
    storage = FileSystemStorage(temp_dir)
    return TaskManager(storage)


@pytest.fixture
def invalid_input_data():
    """Sample invalid input data."""
    return {
        "invalid_type": {"value": "not_a_number"},
        "missing_field": {},
        "extra_field": {"value": 42, "extra": "field"},
        "null_value": {"value": None}
    }


@pytest.fixture
def valid_input_data():
    """Sample valid input data."""
    return {
        "simple": {"value": 42},
        "negative": {"value": -10},
        "zero": {"value": 0},
        "float": {"value": 3.14}
    }


@pytest.fixture
def complex_workflow():
    """Create a complex workflow with multiple nodes."""
    workflow = Workflow(name="Complex Workflow")

    # Create a diamond-shaped workflow
    nodes = {
        "start": MockNode(name="Start Node"),
        "branch1": MockNode(name="Branch 1"),
        "branch2": MockNode(name="Branch 2"),
        "merge": MockNode(name="Merge Node")
    }

    for node in nodes.values():
        workflow.add_node(node)

    workflow.add_edge(nodes["start"], nodes["branch1"])
    workflow.add_edge(nodes["start"], nodes["branch2"])
    workflow.add_edge(nodes["branch1"], nodes["merge"])
    workflow.add_edge(nodes["branch2"], nodes["merge"])

    return workflow