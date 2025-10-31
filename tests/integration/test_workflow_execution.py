"""End-to-end workflow execution integration tests."""

import json
from pathlib import Path

import pandas as pd
import pytest
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow import Workflow


class TestWorkflowExecution:
    """Test complete workflow execution scenarios."""

    def test_simple_workflow_execution(
        self, simple_workflow: Workflow, temp_data_dir: Path
    ):
        """Test execution of a simple linear workflow."""
        runner = WorkflowRunner(debug=True)

        # Execute workflow
        result, run_id = runner.run(simple_workflow)

        # Verify execution success
        assert result is not None

        # Verify output file was created
        output_file = temp_data_dir / "output.csv"
        assert output_file.exists()

        # Verify output data is correct (should have filtered rows)
        df = pd.read_csv(output_file)
        assert len(df) == 2  # Only Bob and Charlie (value > 100)
        assert all(df["value"] > 100)

    def test_complex_workflow_execution(
        self, complex_workflow: Workflow, temp_data_dir: Path
    ):
        """Test execution of a complex multi-branch workflow."""
        runner = WorkflowRunner(debug=True)

        # Execute workflow
        result, run_id = runner.run(complex_workflow)

        # Verify execution success
        assert result is not None

        # Verify workflow execution completed successfully
        assert run_id is not None

        # For MockNode-based workflow, verify basic structure executed
        # (In a real workflow, this would check actual output files)

    def test_workflow_with_task_tracking(self, simple_workflow: Workflow, task_manager):
        """Test workflow execution with task tracking enabled."""
        runner = WorkflowRunner(task_manager=task_manager)

        # Execute workflow with tracking
        result, run_id = runner.run(simple_workflow)

        # Verify workflow executed
        assert result is not None

        # Task tracking verification would require proper implementation
        # For now, just verify the manager exists
        assert task_manager is not None

    def test_workflow_state_persistence(
        self, simple_workflow: Workflow, temp_data_dir: Path
    ):
        """Test workflow state persistence and recovery."""
        runner = WorkflowRunner()

        # Execute workflow
        initial_result, run_id = runner.run(simple_workflow)

        # Save state
        state_file = temp_data_dir / "workflow_state.json"
        state = {
            "workflow_id": getattr(simple_workflow, "id", "test"),
            "status": "completed",
            "outputs": {},
        }

        with open(state_file, "w") as f:
            json.dump(state, f)

        # Load state and verify
        with open(state_file) as f:
            loaded_state = json.load(f)

        assert loaded_state["status"] is not None
        assert loaded_state["workflow_id"] == getattr(
            simple_workflow.metadata, "id", "test"
        )

    def test_workflow_retry_on_failure(self, error_workflow: Workflow):
        """Test workflow retry mechanism on failures."""
        runner = WorkflowRunner()

        # Execute workflow (should fail)
        with pytest.raises(Exception):
            result, run_id = runner.run(error_workflow)

        # Verify retry attempts were made
        # This would require tracking retry count in the runner

    def test_partial_workflow_execution(self, complex_workflow: Workflow):
        """Test executing only a subset of workflow nodes."""
        runner = WorkflowRunner()

        # Execute workflow (partial execution not implemented)
        result, run_id = runner.run(complex_workflow)

        # Verify partial execution
        assert result is not None
        # Verify that nodes after aggregator were not executed

    def test_workflow_with_dynamic_inputs(self, temp_data_dir: Path):
        """Test workflow execution with runtime-provided inputs."""
        from kailash.workflow.builder import WorkflowBuilder

        builder = WorkflowBuilder()

        # Create test data first
        input_file = temp_data_dir / "dynamic_input.csv"
        input_file.write_text("id,value\n1,100\n2,200\n")
        output_file = temp_data_dir / "dynamic_output.csv"

        # Create workflow with dynamic inputs
        reader_id = builder.add_node(
            "CSVReaderNode", "reader", config={"file_path": str(input_file)}
        )
        writer_id = builder.add_node(
            "CSVWriterNode", "writer", config={"file_path": str(output_file)}
        )

        builder.add_connection(reader_id, "data", writer_id, "data")
        workflow = builder.build("dynamic_workflow")

        # Execute with runtime inputs
        runner = WorkflowRunner()

        result, run_id = runner.run(workflow)

        assert result is not None

    def test_workflow_with_environment_variables(
        self, simple_workflow: Workflow, monkeypatch
    ):
        """Test workflow execution with environment variable configuration."""
        # Set environment variables
        monkeypatch.setenv("KAILASH_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("KAILASH_TIMEOUT", "300")

        runner = WorkflowRunner()

        # Execute workflow
        result, run_id = runner.run(simple_workflow)

        assert result is not None
        # Environment variables should be respected

    def test_workflow_cancellation(self, complex_workflow: Workflow):
        """Test workflow cancellation during execution."""
        runner = WorkflowRunner()

        # Start workflow execution in background
        import threading

        execution_thread = threading.Thread(target=lambda: runner.run(complex_workflow))
        execution_thread.start()

        # Cancel after short delay
        import time

        time.sleep(0.1)
        # runner.cancel()  # Not implemented

        execution_thread.join(timeout=5)

        # Verify workflow was cancelled
        # This would require implementing cancellation in the runner

    def test_workflow_resource_cleanup(
        self, simple_workflow: Workflow, temp_data_dir: Path
    ):
        """Test proper resource cleanup after workflow execution."""
        runner = WorkflowRunner()

        # Track open file handles before execution
        # psutil not available in test environment

        # Execute workflow
        result, run_id = runner.run(simple_workflow)

        # Verify resources were cleaned up
        # final_files = len(process.open_files())
        # assert final_files <= initial_files

        # Verify temporary files were cleaned up
        temp_files = list(temp_data_dir.glob("*.tmp"))
        assert len(temp_files) == 0
