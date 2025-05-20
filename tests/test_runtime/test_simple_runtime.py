"""Simple tests for basic runtime functionality."""

import pytest
from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReader, CSVWriter
from kailash.tracking import TaskManager, TaskStatus


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
        workflow = Workflow(name="test_workflow")
        assert workflow.metadata.name == "test_workflow"
        assert len(workflow.nodes) == 0
        assert len(workflow.connections) == 0
    
    def test_add_node(self):
        """Test adding a node to workflow."""
        workflow = Workflow(name="test_workflow")
        
        def test_func(x: int, y: int) -> int:
            return x + y
        
        node = PythonCodeNode.from_function(test_func, name="adder")
        workflow.add_node(node_id="adder", node_or_type=node)
        
        assert "adder" in workflow.nodes
        assert workflow.nodes["adder"].node_type == "PythonCodeNode"
    
    def test_simple_execution(self):
        """Test simple workflow execution."""
        workflow = Workflow(name="test_workflow")
        
        def double(x: int) -> int:
            return x * 2
        
        node = PythonCodeNode.from_function(double, name="doubler")
        workflow.add_node(node_id="doubler", node_or_type=node, config={"x": 5})
        
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)
        
        assert len(results) == 1
        assert "doubler" in results
        assert results["doubler"]["result"] == 10
    
    def test_data_nodes(self):
        """Test data reader/writer nodes exist."""
        # Just test that these can be imported and instantiated
        reader = CSVReader(file_path="test.csv")
        assert reader.metadata.name == "CSVReader"
        
        writer = CSVWriter(file_path="output.csv")
        assert writer.metadata.name == "CSVWriter"
    
    def test_task_manager(self):
        """Test task manager creation."""
        task_manager = TaskManager()
        assert task_manager is not None
        
        run_id = task_manager.create_run(workflow_name="test_workflow")
        assert run_id is not None
        
        task_manager.update_run_status(run_id, TaskStatus.RUNNING)
        task_manager.update_run_status(run_id, TaskStatus.COMPLETED)
        
        runs = task_manager.list_runs()
        assert len(runs) > 0


if __name__ == "__main__":
    # Run tests directly
    test = TestBasicRuntime()
    test.test_create_runtime()
    test.test_create_workflow() 
    test.test_add_node()
    test.test_simple_execution()
    test.test_data_nodes()
    test.test_task_manager()
    print("All tests passed!")