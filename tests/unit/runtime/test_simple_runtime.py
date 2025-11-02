"""Simple tests for basic runtime functionality."""

from typing import Any

import pytest
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.tracking import TaskManager
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.workflow import Workflow


class TestBasicRuntime:
    """Test basic runtime functionality with correct imports."""

    def test_create_runtime(self):
        """Test creating a LocalRuntime instance."""
        runtime = LocalRuntime()
        assert runtime is not None
        assert runtime.debug is False

        runtime_debug = LocalRuntime(debug=True)
        assert runtime_debug.debug is True

    def test_create_workflow(self):
        """Test creating a workflow."""
        workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")
        assert workflow.name == "Test Workflow"
        assert len(workflow._node_instances) == 0
        assert len(workflow.graph.edges()) == 0

    def test_add_node(self):
        """Test adding a node to workflow."""
        workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")

        def test_func(x: int, y: int) -> dict[str, Any]:
            return {"result": x + y}

        node = PythonCodeNode.from_function(test_func, name="adder")
        workflow.add_node("adder", node)

        assert "adder" in workflow._node_instances
        assert workflow._node_instances["adder"].__class__.__name__ == "PythonCodeNode"

    def test_simple_execution(self, tmp_path):
        """Test simple workflow execution."""
        workflow = Workflow(workflow_id="test_workflow", name="Test Workflow")

        def double(x: int) -> dict[str, Any]:
            return {"result": x * 2}

        node = PythonCodeNode.from_function(double, name="doubler")
        # Set the config with x value
        node.config = {"x": 5}
        workflow.add_node("doubler", node)

        # Create task manager with storage
        storage = FileSystemStorage(str(tmp_path))
        task_manager = TaskManager(storage)

        # Execute without parameters since we set config
        with LocalRuntime() as runtime:
            results, run_id = runtime.execute(workflow, task_manager=task_manager)

        assert len(results) == 1
        assert "doubler" in results
        assert results["doubler"]["result"] == 10

    def test_data_nodes(self):
        """Test data reader/writer nodes exist."""
        # Just test that these can be imported and instantiated
        reader = CSVReaderNode(name="CSVReaderNode", file_path="test.csv")
        assert reader.metadata.name == "CSVReaderNode"

        writer = CSVWriterNode(name="CSVWriterNode", file_path="output.csv")
        assert writer.metadata.name == "CSVWriterNode"

    def test_task_manager(self, tmp_path):
        """Test task manager creation."""
        storage = FileSystemStorage(str(tmp_path))
        task_manager = TaskManager(storage)
        assert task_manager is not None

        run_id = task_manager.create_run(workflow_name="test_workflow")
        assert run_id is not None

        task_manager.update_run_status(run_id, "running")
        task_manager.update_run_status(run_id, "completed")

        runs = task_manager.list_runs()
        assert len(runs) > 0
