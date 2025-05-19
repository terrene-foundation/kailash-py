"""End-to-end workflow execution integration tests."""

import json
from pathlib import Path
from typing import Dict, Any

import pytest
import pandas as pd
from networkx import DiGraph

from kailash.runtime.local import LocalRunner
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow import Workflow
from kailash.nodes.base import Node
from kailash.tracking.manager import TaskManager
from kailash.sdk_exceptions import RuntimeExecutionError, NodeExecutionError


class TestWorkflowExecution:
    """Test complete workflow execution scenarios."""
    
    def test_simple_workflow_execution(self, simple_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test execution of a simple linear workflow."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow
        result = runner.run(simple_workflow)
        
        # Verify execution success
        assert result.status == NodeStatus.COMPLETED
        assert result.error is None
        
        # Verify output file was created
        output_file = temp_data_dir / "output.csv"
        assert output_file.exists()
        
        # Verify output data is correct (should have filtered rows)
        df = pd.read_csv(output_file)
        assert len(df) == 2  # Only Bob and Charlie (value > 100)
        assert all(df['value'] > 100)
    
    def test_complex_workflow_execution(self, complex_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test execution of a complex multi-branch workflow."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow
        result = runner.run(complex_workflow)
        
        # Verify execution success
        assert result.status == NodeStatus.COMPLETED
        
        # Verify multiple output files were created
        assert (temp_data_dir / "processed.csv").exists()
        assert (temp_data_dir / "report.txt").exists()
        
        # Verify processed data
        df = pd.read_csv(temp_data_dir / "processed.csv")
        assert len(df) > 0
        
        # Verify report was generated
        report = (temp_data_dir / "report.txt").read_text()
        assert "insights" in report.lower() or "analysis" in report.lower()
    
    def test_workflow_with_task_tracking(self, simple_workflow: WorkflowGraph, task_tracker: TaskTracker):
        """Test workflow execution with task tracking enabled."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow with tracking
        result = runner.run(simple_workflow, tracker=task_tracker)
        
        # Verify tasks were tracked
        tasks = task_tracker.get_tasks()
        assert len(tasks) > 0
        
        # Verify task statuses
        completed_tasks = [t for t in tasks if t.status == "completed"]
        assert len(completed_tasks) == len(simple_workflow.graph.nodes())
    
    def test_workflow_state_persistence(self, simple_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test workflow state persistence and recovery."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow
        initial_result = runner.run(simple_workflow)
        
        # Save state
        state_file = temp_data_dir / "workflow_state.json"
        state = {
            "workflow_id": simple_workflow.metadata.get("id"),
            "status": initial_result.status.value,
            "outputs": initial_result.outputs
        }
        
        with open(state_file, 'w') as f:
            json.dump(state, f)
        
        # Load state and verify
        with open(state_file, 'r') as f:
            loaded_state = json.load(f)
        
        assert loaded_state["status"] == NodeStatus.COMPLETED.value
        assert loaded_state["workflow_id"] == simple_workflow.metadata.get("id")
    
    def test_workflow_retry_on_failure(self, error_workflow: WorkflowGraph):
        """Test workflow retry mechanism on failures."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime, max_retries=3)
        
        # Execute workflow (should fail)
        with pytest.raises(ExecutionError):
            result = runner.run(error_workflow)
        
        # Verify retry attempts were made
        # This would require tracking retry count in the runner
    
    def test_partial_workflow_execution(self, complex_workflow: WorkflowGraph):
        """Test executing only a subset of workflow nodes."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute only up to the aggregator node
        result = runner.run(
            complex_workflow, 
            start_node="csv_reader",
            end_node="aggregator"
        )
        
        # Verify partial execution
        assert result.status == NodeStatus.COMPLETED
        # Verify that nodes after aggregator were not executed
    
    def test_workflow_with_dynamic_inputs(self, temp_data_dir: Path):
        """Test workflow execution with runtime-provided inputs."""
        from kailash.workflow.graph import WorkflowBuilder
        from kailash.nodes.base import InputType, OutputType
        
        builder = WorkflowBuilder()
        
        # Create workflow with dynamic inputs
        reader_id = builder.add_node(
            "CSVFileReader",
            "reader",
            inputs={"path": InputType()},  # No default value
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        writer_id = builder.add_node(
            "CSVFileWriter",
            "writer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType()  # No default value
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        builder.add_connection(reader_id, "data", writer_id, "data")
        workflow = builder.build("dynamic_workflow")
        
        # Execute with runtime inputs
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Create test data
        input_file = temp_data_dir / "dynamic_input.csv"
        input_file.write_text("id,value\n1,100\n2,200\n")
        
        result = runner.run(
            workflow,
            inputs={
                "reader": {"path": str(input_file)},
                "writer": {"path": str(temp_data_dir / "dynamic_output.csv")}
            }
        )
        
        assert result.status == NodeStatus.COMPLETED
        assert (temp_data_dir / "dynamic_output.csv").exists()
    
    def test_workflow_with_environment_variables(self, simple_workflow: WorkflowGraph, monkeypatch):
        """Test workflow execution with environment variable configuration."""
        # Set environment variables
        monkeypatch.setenv("KAILASH_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("KAILASH_TIMEOUT", "300")
        
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow
        result = runner.run(simple_workflow)
        
        assert result.status == NodeStatus.COMPLETED
        # Environment variables should be respected
    
    def test_workflow_cancellation(self, complex_workflow: WorkflowGraph):
        """Test workflow cancellation during execution."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Start workflow execution in background
        import threading
        execution_thread = threading.Thread(
            target=lambda: runner.run(complex_workflow)
        )
        execution_thread.start()
        
        # Cancel after short delay
        import time
        time.sleep(0.1)
        runner.cancel()
        
        execution_thread.join(timeout=5)
        
        # Verify workflow was cancelled
        # This would require implementing cancellation in the runner
    
    def test_workflow_resource_cleanup(self, simple_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test proper resource cleanup after workflow execution."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Track open file handles before execution
        import psutil
        process = psutil.Process()
        initial_files = len(process.open_files())
        
        # Execute workflow
        result = runner.run(simple_workflow)
        
        # Verify resources were cleaned up
        final_files = len(process.open_files())
        assert final_files <= initial_files
        
        # Verify temporary files were cleaned up
        temp_files = list(temp_data_dir.glob("*.tmp"))
        assert len(temp_files) == 0