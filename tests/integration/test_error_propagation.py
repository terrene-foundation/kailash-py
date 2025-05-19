"""Test error handling and propagation across workflows."""

import json
from pathlib import Path
from typing import Dict, Any

import pytest
import pandas as pd

from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow.graph import WorkflowBuilder, WorkflowGraph
from kailash.nodes.base import (
    Node, NodeStatus, DataFormat, InputType, OutputType,
    ValidationError, ExecutionError
)
from kailash.sdk_exceptions import (
    KailashError, NodeError, WorkflowError,
    DataValidationError, ConnectionError as KailashConnectionError
)
from kailash.tracking.manager import TaskTracker


class TestErrorPropagation:
    """Test error handling and propagation in workflows."""
    
    def test_node_validation_error(self, temp_data_dir: Path):
        """Test that validation errors are properly caught and reported."""
        builder = WorkflowBuilder()
        
        # Create node with invalid configuration
        with pytest.raises(ValidationError) as exc_info:
            node_id = builder.add_node(
                "DataFilter",
                "filter",
                inputs={
                    # Missing required 'data' input
                    "condition": InputType(value="value > 100")
                },
                outputs={"filtered_data": OutputType(format=DataFormat.DATAFRAME)}
            )
        
        assert "required input" in str(exc_info.value).lower()
    
    def test_execution_error_propagation(self, temp_data_dir: Path):
        """Test that execution errors propagate correctly through the workflow."""
        builder = WorkflowBuilder()
        
        # Create workflow with an error
        reader_id = builder.add_node(
            "CSVFileReader",
            "reader",
            inputs={"path": InputType(value=str(temp_data_dir / "nonexistent.csv"))},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        processor_id = builder.add_node(
            "DataProcessor",
            "processor",
            inputs={"data": InputType(format=DataFormat.DATAFRAME)},
            outputs={"processed": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        builder.add_connection(reader_id, "data", processor_id, "data")
        workflow = builder.build("error_propagation_test")
        
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow - should fail with proper error
        with pytest.raises(NodeError) as exc_info:
            result = runner.run(workflow)
        
        error = exc_info.value
        assert error.node_id == "reader"
        assert "file not found" in str(error).lower() or "no such file" in str(error).lower()
    
    def test_downstream_node_failure(self, temp_data_dir: Path):
        """Test handling when a downstream node fails."""
        builder = WorkflowBuilder()
        
        # Create valid input file
        input_csv = temp_data_dir / "input.csv"
        input_csv.write_text("id,value\n1,100\n2,200\n")
        
        # Create workflow where second node will fail
        reader_id = builder.add_node(
            "CSVFileReader",
            "reader",
            inputs={"path": InputType(value=str(input_csv))},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        # This node will fail due to invalid condition syntax
        filter_id = builder.add_node(
            "DataFilter",
            "filter",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "condition": InputType(value="invalid python syntax!!!")
            },
            outputs={"filtered_data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        writer_id = builder.add_node(
            "CSVFileWriter",
            "writer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType(value=str(temp_data_dir / "output.csv"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        builder.add_connection(reader_id, "data", filter_id, "data")
        builder.add_connection(filter_id, "filtered_data", writer_id, "data")
        
        workflow = builder.build("downstream_failure_test")
        
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow
        with pytest.raises(NodeError) as exc_info:
            result = runner.run(workflow)
        
        error = exc_info.value
        assert error.node_id == "filter"
        assert "syntax" in str(error).lower() or "invalid" in str(error).lower()
        
        # First node should have succeeded, but output file should not exist
        assert not (temp_data_dir / "output.csv").exists()
    
    def test_error_in_parallel_branches(self, temp_data_dir: Path):
        """Test error handling when one of parallel branches fails."""
        builder = WorkflowBuilder()
        
        # Create input file
        input_csv = temp_data_dir / "input.csv"
        input_csv.write_text("id,value\n1,100\n2,200\n")
        
        # Create workflow with parallel branches
        reader_id = builder.add_node(
            "CSVFileReader",
            "reader",
            inputs={"path": InputType(value=str(input_csv))},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        # Branch 1: Will succeed
        valid_filter_id = builder.add_node(
            "DataFilter",
            "valid_filter",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "condition": InputType(value="value > 50")
            },
            outputs={"filtered_data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        valid_writer_id = builder.add_node(
            "CSVFileWriter",
            "valid_writer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType(value=str(temp_data_dir / "valid_output.csv"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        # Branch 2: Will fail
        invalid_filter_id = builder.add_node(
            "DataFilter",
            "invalid_filter",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "condition": InputType(value="INVALID SYNTAX")
            },
            outputs={"filtered_data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        invalid_writer_id = builder.add_node(
            "CSVFileWriter",
            "invalid_writer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType(value=str(temp_data_dir / "invalid_output.csv"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        # Connect branches
        builder.add_connection(reader_id, "data", valid_filter_id, "data")
        builder.add_connection(valid_filter_id, "filtered_data", valid_writer_id, "data")
        
        builder.add_connection(reader_id, "data", invalid_filter_id, "data")
        builder.add_connection(invalid_filter_id, "filtered_data", invalid_writer_id, "data")
        
        workflow = builder.build("parallel_error_test")
        
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow
        with pytest.raises(NodeError) as exc_info:
            result = runner.run(workflow)
        
        error = exc_info.value
        assert error.node_id == "invalid_filter"
        
        # Check that valid branch may have completed
        # (depends on execution strategy - could be stopped early)
    
    def test_error_recovery_with_fallback(self, temp_data_dir: Path):
        """Test error recovery using fallback nodes."""
        builder = WorkflowBuilder()
        
        # Create workflow with fallback path
        primary_reader_id = builder.add_node(
            "APIDataReader",
            "primary_reader",
            inputs={"endpoint": InputType(value="http://invalid.endpoint")},
            outputs={"data": OutputType(format=DataFormat.JSON)}
        )
        
        # Fallback node
        fallback_reader_id = builder.add_node(
            "JSONFileReader",
            "fallback_reader",
            inputs={"path": InputType(value=str(temp_data_dir / "fallback.json"))},
            outputs={"data": OutputType(format=DataFormat.JSON)}
        )
        
        # Create fallback data file
        fallback_data = {"data": [{"id": 1, "value": 100}]}
        (temp_data_dir / "fallback.json").write_text(json.dumps(fallback_data))
        
        # Error handler node that routes to fallback
        error_handler_id = builder.add_node(
            "ErrorHandler",
            "error_handler",
            inputs={
                "error": InputType(format=DataFormat.JSON),
                "fallback_enabled": InputType(value=True)
            },
            outputs={
                "should_fallback": OutputType(format=DataFormat.BOOLEAN),
                "error_message": OutputType(format=DataFormat.TEXT)
            }
        )
        
        # Final processor
        processor_id = builder.add_node(
            "DataProcessor",
            "processor",
            inputs={"data": InputType(format=DataFormat.JSON)},
            outputs={"processed": OutputType(format=DataFormat.JSON)}
        )
        
        # Connect with error handling
        # This would require conditional routing based on error status
        workflow = builder.build("error_recovery_test")
        
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime, enable_fallbacks=True)
        
        # Execute workflow - should use fallback
        result = runner.run(workflow)
        
        # Verify fallback was used
        assert result.status == NodeStatus.COMPLETED
        assert result.outputs["processor"]["processed"] is not None
    
    def test_error_context_preservation(self, error_workflow: WorkflowGraph, task_tracker: TaskTracker):
        """Test that error context is preserved and accessible."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow with tracking
        with pytest.raises(NodeError) as exc_info:
            result = runner.run(error_workflow, tracker=task_tracker)
        
        error = exc_info.value
        
        # Check error context
        assert error.node_id is not None
        assert error.workflow_id == error_workflow.metadata.get("id")
        assert error.timestamp is not None
        
        # Get failed task from tracker
        tasks = task_tracker.get_tasks()
        failed_tasks = [t for t in tasks if t.status == "failed"]
        
        assert len(failed_tasks) > 0
        failed_task = failed_tasks[0]
        
        # Verify error details in task
        assert failed_task.error is not None
        assert failed_task.error_details is not None
        assert "traceback" in failed_task.error_details
    
    def test_validation_error_messages(self, temp_data_dir: Path):
        """Test that validation errors provide helpful messages."""
        builder = WorkflowBuilder()
        
        # Test various validation errors
        
        # 1. Missing required input
        with pytest.raises(ValidationError) as exc_info:
            node_id = builder.add_node(
                "DataFilter",
                "filter",
                inputs={
                    # Missing 'data' input
                    "condition": InputType(value="test")
                },
                outputs={"filtered": OutputType(format=DataFormat.DATAFRAME)}
            )
        assert "required input" in str(exc_info.value).lower()
        assert "data" in str(exc_info.value)
        
        # 2. Invalid input type
        with pytest.raises(ValidationError) as exc_info:
            node_id = builder.add_node(
                "DataFilter",
                "filter",
                inputs={
                    "data": InputType(format=DataFormat.TEXT),  # Should be DATAFRAME
                    "condition": InputType(value="test")
                },
                outputs={"filtered": OutputType(format=DataFormat.DATAFRAME)}
            )
        assert "invalid format" in str(exc_info.value).lower()
        
        # 3. Invalid connection
        node1_id = builder.add_node(
            "TextProcessor",
            "text_node",
            inputs={"text": InputType(format=DataFormat.TEXT)},
            outputs={"processed": OutputType(format=DataFormat.TEXT)}
        )
        
        node2_id = builder.add_node(
            "DataFrameProcessor",
            "df_node",
            inputs={"data": InputType(format=DataFormat.DATAFRAME)},
            outputs={"processed": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        with pytest.raises(ValidationError) as exc_info:
            builder.add_connection(
                node1_id, "processed",  # TEXT output
                node2_id, "data"        # DATAFRAME input
            )
        assert "incompatible" in str(exc_info.value).lower()
    
    def test_workflow_timeout_error(self, temp_data_dir: Path):
        """Test workflow timeout error handling."""
        builder = WorkflowBuilder()
        
        # Create node that takes too long
        slow_node_id = builder.add_node(
            "SlowProcessor",
            "slow_processor",
            inputs={
                "data": InputType(value={"sleep_seconds": 10}),
                "timeout": InputType(value=1)  # 1 second timeout
            },
            outputs={"result": OutputType(format=DataFormat.JSON)}
        )
        
        workflow = builder.build("timeout_test")
        
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime, timeout=2)  # 2 second workflow timeout
        
        # Execute workflow - should timeout
        with pytest.raises(WorkflowError) as exc_info:
            result = runner.run(workflow)
        
        error = exc_info.value
        assert "timeout" in str(error).lower()
    
    def test_error_aggregation_in_complex_workflow(self, complex_workflow: WorkflowGraph):
        """Test error aggregation when multiple nodes fail."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime, fail_fast=False)
        
        # Modify workflow to have multiple failure points
        # (This would require injecting errors into specific nodes)
        
        # Execute workflow
        with pytest.raises(WorkflowError) as exc_info:
            result = runner.run(complex_workflow)
        
        error = exc_info.value
        
        # Check that multiple errors are aggregated
        if hasattr(error, 'errors'):
            assert len(error.errors) > 1
            
            # Each sub-error should have details
            for sub_error in error.errors:
                assert sub_error.node_id is not None
                assert sub_error.message is not None
    
    def test_custom_error_handlers(self, simple_workflow: WorkflowGraph):
        """Test custom error handlers in workflow execution."""
        runtime = LocalRuntime()
        
        # Define custom error handler
        def custom_error_handler(error: NodeError) -> bool:
            """Custom error handler that logs and decides whether to continue."""
            print(f"Custom handler caught error in node {error.node_id}: {error}")
            
            # Return True to continue, False to stop
            return error.node_id == "reader"  # Continue if reader fails
        
        runner = WorkflowRunner(
            runtime=runtime,
            error_handler=custom_error_handler
        )
        
        # Execute workflow
        try:
            result = runner.run(simple_workflow)
        except WorkflowError as e:
            # Error was handled but workflow still failed
            assert e.handled is True
    
    def test_error_serialization(self, error_workflow: WorkflowGraph, temp_data_dir: Path):
        """Test that errors can be serialized and deserialized."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflow and capture error
        error = None
        try:
            result = runner.run(error_workflow)
        except NodeError as e:
            error = e
        
        assert error is not None
        
        # Serialize error
        error_dict = {
            "type": type(error).__name__,
            "message": str(error),
            "node_id": error.node_id,
            "workflow_id": error.workflow_id,
            "timestamp": error.timestamp.isoformat() if error.timestamp else None,
            "details": error.details
        }
        
        error_file = temp_data_dir / "error.json"
        with open(error_file, 'w') as f:
            json.dump(error_dict, f)
        
        # Deserialize error
        with open(error_file, 'r') as f:
            loaded_error = json.load(f)
        
        assert loaded_error["type"] == "NodeError"
        assert loaded_error["node_id"] == error.node_id
        assert loaded_error["message"] == str(error)
    
    def test_nested_workflow_error_propagation(self, simple_workflow: WorkflowGraph):
        """Test error propagation in nested workflows."""
        builder = WorkflowBuilder()
        
        # Create parent workflow that contains child workflow
        sub_workflow_id = builder.add_node(
            "SubWorkflow",
            "sub_workflow",
            inputs={
                "workflow": InputType(value=simple_workflow),
                "inputs": InputType(value={})
            },
            outputs={"result": OutputType(format=DataFormat.JSON)}
        )
        
        processor_id = builder.add_node(
            "DataProcessor",
            "processor",
            inputs={"data": InputType(format=DataFormat.JSON)},
            outputs={"processed": OutputType(format=DataFormat.JSON)}
        )
        
        builder.add_connection(sub_workflow_id, "result", processor_id, "data")
        
        parent_workflow = builder.build("parent_workflow")
        
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # If sub-workflow fails, parent should get proper error
        with pytest.raises(NodeError) as exc_info:
            result = runner.run(parent_workflow)
        
        error = exc_info.value
        assert error.node_id == "sub_workflow"
        # Should contain information about the nested failure
        assert "nested" in str(error).lower() or "sub" in str(error).lower()