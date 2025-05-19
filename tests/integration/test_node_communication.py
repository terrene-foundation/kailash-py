"""Test data passing between nodes in workflows."""

import json
from pathlib import Path
from typing import Dict, Any

import pytest
import pandas as pd
import numpy as np

from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow import Workflow, WorkflowBuilder
from kailash.nodes.base import (
    Node, NodeStatus, DataFormat, InputType, OutputType,
    ValidationError, ExecutionError
)


class TestNodeCommunication:
    """Test data flow between different node types."""
    
    def test_dataframe_passing(self, temp_data_dir: Path):
        """Test passing DataFrames between nodes."""
        builder = WorkflowBuilder()
        
        # Create test data
        input_csv = temp_data_dir / "input.csv"
        input_csv.write_text("id,value\n1,10\n2,20\n3,30\n")
        
        # Add nodes that pass DataFrames
        reader_id = builder.add_node(
            "CSVFileReader",
            "reader",
            inputs={"path": InputType(value=str(input_csv))},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        transformer_id = builder.add_node(
            "DataTransformer",
            "transformer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "operation": InputType(value="multiply"),
                "factor": InputType(value=2)
            },
            outputs={"transformed_data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        aggregator_id = builder.add_node(
            "DataAggregator",
            "aggregator",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "agg_func": InputType(value="sum")
            },
            outputs={"result": OutputType(format=DataFormat.JSON)}
        )
        
        # Connect nodes
        builder.add_connection(reader_id, "data", transformer_id, "data")
        builder.add_connection(transformer_id, "transformed_data", aggregator_id, "data")
        
        workflow = builder.build("dataframe_passing_test")
        
        # Execute workflow
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        result = runner.run(workflow)
        
        # Verify data was correctly passed and transformed
        assert result.status == NodeStatus.COMPLETED
        assert result.outputs["aggregator"]["result"]["value"] == 120  # (10+20+30)*2
    
    def test_json_data_passing(self, temp_data_dir: Path):
        """Test passing JSON data between nodes."""
        builder = WorkflowBuilder()
        
        # Create test JSON data
        input_json = temp_data_dir / "input.json"
        test_data = {
            "users": [
                {"id": 1, "name": "Alice", "score": 85},
                {"id": 2, "name": "Bob", "score": 92},
                {"id": 3, "name": "Charlie", "score": 78}
            ]
        }
        input_json.write_text(json.dumps(test_data))
        
        # Add nodes that work with JSON
        reader_id = builder.add_node(
            "JSONFileReader",
            "reader",
            inputs={"path": InputType(value=str(input_json))},
            outputs={"data": OutputType(format=DataFormat.JSON)}
        )
        
        processor_id = builder.add_node(
            "JSONProcessor",
            "processor",
            inputs={
                "data": InputType(format=DataFormat.JSON),
                "filter_field": InputType(value="score"),
                "filter_value": InputType(value=80),
                "filter_op": InputType(value=">")
            },
            outputs={"filtered_data": OutputType(format=DataFormat.JSON)}
        )
        
        writer_id = builder.add_node(
            "JSONFileWriter",
            "writer",
            inputs={
                "data": InputType(format=DataFormat.JSON),
                "path": InputType(value=str(temp_data_dir / "output.json"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        # Connect nodes
        builder.add_connection(reader_id, "data", processor_id, "data")
        builder.add_connection(processor_id, "filtered_data", writer_id, "data")
        
        workflow = builder.build("json_passing_test")
        
        # Execute workflow
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        result = runner.run(workflow)
        
        # Verify JSON data was correctly passed and filtered
        assert result.status == NodeStatus.COMPLETED
        
        output_data = json.loads((temp_data_dir / "output.json").read_text())
        assert len(output_data["users"]) == 2  # Only Alice and Bob (score > 80)
        assert all(user["score"] > 80 for user in output_data["users"])
    
    def test_text_data_passing(self, temp_data_dir: Path):
        """Test passing text data between nodes."""
        builder = WorkflowBuilder()
        
        # Create test text data
        input_text = temp_data_dir / "input.txt"
        input_text.write_text("Hello World\nThis is a test\nPython SDK")
        
        # Add nodes that work with text
        reader_id = builder.add_node(
            "TextFileReader",
            "reader",
            inputs={"path": InputType(value=str(input_text))},
            outputs={"text": OutputType(format=DataFormat.TEXT)}
        )
        
        processor_id = builder.add_node(
            "TextProcessor",
            "processor",
            inputs={
                "text": InputType(format=DataFormat.TEXT),
                "operation": InputType(value="uppercase")
            },
            outputs={"processed_text": OutputType(format=DataFormat.TEXT)}
        )
        
        analyzer_id = builder.add_node(
            "TextAnalyzer",
            "analyzer",
            inputs={"text": InputType(format=DataFormat.TEXT)},
            outputs={
                "word_count": OutputType(format=DataFormat.JSON),
                "line_count": OutputType(format=DataFormat.JSON)
            }
        )
        
        # Connect nodes
        builder.add_connection(reader_id, "text", processor_id, "text")
        builder.add_connection(processor_id, "processed_text", analyzer_id, "text")
        
        workflow = builder.build("text_passing_test")
        
        # Execute workflow
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        result = runner.run(workflow)
        
        # Verify text data was correctly passed and processed
        assert result.status == NodeStatus.COMPLETED
        assert result.outputs["analyzer"]["word_count"] == 8
        assert result.outputs["analyzer"]["line_count"] == 3
    
    def test_mixed_data_types(self, temp_data_dir: Path):
        """Test passing mixed data types through a workflow."""
        builder = WorkflowBuilder()
        
        # Create test data of different types
        csv_file = temp_data_dir / "data.csv"
        csv_file.write_text("id,text\n1,hello\n2,world\n")
        
        # Node that reads CSV and outputs DataFrame
        csv_reader_id = builder.add_node(
            "CSVFileReader",
            "csv_reader",
            inputs={"path": InputType(value=str(csv_file))},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        # Node that converts DataFrame to JSON
        df_to_json_id = builder.add_node(
            "DataFrameToJSON",
            "df_to_json",
            inputs={"data": InputType(format=DataFormat.DATAFRAME)},
            outputs={"json_data": OutputType(format=DataFormat.JSON)}
        )
        
        # Node that extracts text from JSON
        json_to_text_id = builder.add_node(
            "JSONToText",
            "json_to_text",
            inputs={
                "data": InputType(format=DataFormat.JSON),
                "field": InputType(value="text")
            },
            outputs={"text": OutputType(format=DataFormat.TEXT)}
        )
        
        # Node that writes text
        text_writer_id = builder.add_node(
            "TextFileWriter",
            "text_writer",
            inputs={
                "text": InputType(format=DataFormat.TEXT),
                "path": InputType(value=str(temp_data_dir / "output.txt"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        # Connect nodes with different data types
        builder.add_connection(csv_reader_id, "data", df_to_json_id, "data")
        builder.add_connection(df_to_json_id, "json_data", json_to_text_id, "data")
        builder.add_connection(json_to_text_id, "text", text_writer_id, "text")
        
        workflow = builder.build("mixed_types_test")
        
        # Execute workflow
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        result = runner.run(workflow)
        
        # Verify data was correctly converted between types
        assert result.status == NodeStatus.COMPLETED
        
        output_text = (temp_data_dir / "output.txt").read_text()
        assert "hello" in output_text.lower()
        assert "world" in output_text.lower()
    
    def test_type_validation(self, temp_data_dir: Path):
        """Test that type mismatches are caught and reported."""
        builder = WorkflowBuilder()
        
        # Create nodes with incompatible types
        json_reader_id = builder.add_node(
            "JSONFileReader",
            "json_reader",
            inputs={"path": InputType(value=str(temp_data_dir / "test.json"))},
            outputs={"data": OutputType(format=DataFormat.JSON)}
        )
        
        # This node expects DataFrame but will receive JSON
        df_processor_id = builder.add_node(
            "DataFrameProcessor",
            "df_processor",
            inputs={"data": InputType(format=DataFormat.DATAFRAME)},
            outputs={"processed": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        # Try to connect incompatible types
        with pytest.raises(ValidationError):
            builder.add_connection(json_reader_id, "data", df_processor_id, "data")
    
    def test_multiple_outputs(self, temp_data_dir: Path):
        """Test nodes with multiple outputs connected to different nodes."""
        builder = WorkflowBuilder()
        
        # Create test data
        input_csv = temp_data_dir / "input.csv"
        input_csv.write_text("id,name,score\n1,Alice,85\n2,Bob,70\n3,Charlie,95\n")
        
        # Node that reads and processes data with multiple outputs
        reader_processor_id = builder.add_node(
            "CSVReaderProcessor",
            "reader_processor",
            inputs={"path": InputType(value=str(input_csv))},
            outputs={
                "full_data": OutputType(format=DataFormat.DATAFRAME),
                "high_scores": OutputType(format=DataFormat.DATAFRAME),
                "low_scores": OutputType(format=DataFormat.DATAFRAME),
                "statistics": OutputType(format=DataFormat.JSON)
            }
        )
        
        # Multiple downstream nodes
        high_writer_id = builder.add_node(
            "CSVFileWriter",
            "high_writer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType(value=str(temp_data_dir / "high_scores.csv"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        low_writer_id = builder.add_node(
            "CSVFileWriter",
            "low_writer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType(value=str(temp_data_dir / "low_scores.csv"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        stats_writer_id = builder.add_node(
            "JSONFileWriter",
            "stats_writer",
            inputs={
                "data": InputType(format=DataFormat.JSON),
                "path": InputType(value=str(temp_data_dir / "statistics.json"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        # Connect multiple outputs to different nodes
        builder.add_connection(reader_processor_id, "high_scores", high_writer_id, "data")
        builder.add_connection(reader_processor_id, "low_scores", low_writer_id, "data")
        builder.add_connection(reader_processor_id, "statistics", stats_writer_id, "data")
        
        workflow = builder.build("multiple_outputs_test")
        
        # Execute workflow
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        result = runner.run(workflow)
        
        # Verify all outputs were correctly routed
        assert result.status == NodeStatus.COMPLETED
        assert (temp_data_dir / "high_scores.csv").exists()
        assert (temp_data_dir / "low_scores.csv").exists()
        assert (temp_data_dir / "statistics.json").exists()
        
        # Verify data was correctly split
        high_scores = pd.read_csv(temp_data_dir / "high_scores.csv")
        low_scores = pd.read_csv(temp_data_dir / "low_scores.csv")
        
        assert all(high_scores["score"] > 80)
        assert all(low_scores["score"] <= 80)
    
    def test_multiple_inputs(self, temp_data_dir: Path):
        """Test nodes that receive inputs from multiple sources."""
        builder = WorkflowBuilder()
        
        # Create multiple input sources
        csv1 = temp_data_dir / "data1.csv"
        csv1.write_text("id,value\n1,10\n2,20\n")
        
        csv2 = temp_data_dir / "data2.csv"
        csv2.write_text("id,value\n3,30\n4,40\n")
        
        # Multiple reader nodes
        reader1_id = builder.add_node(
            "CSVFileReader",
            "reader1",
            inputs={"path": InputType(value=str(csv1))},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        reader2_id = builder.add_node(
            "CSVFileReader",
            "reader2",
            inputs={"path": InputType(value=str(csv2))},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        # Node that accepts multiple inputs
        merger_id = builder.add_node(
            "DataMerger",
            "merger",
            inputs={
                "left": InputType(format=DataFormat.DATAFRAME),
                "right": InputType(format=DataFormat.DATAFRAME),
                "how": InputType(value="concat")
            },
            outputs={"merged_data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        writer_id = builder.add_node(
            "CSVFileWriter",
            "writer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType(value=str(temp_data_dir / "merged.csv"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        # Connect multiple inputs
        builder.add_connection(reader1_id, "data", merger_id, "left")
        builder.add_connection(reader2_id, "data", merger_id, "right")
        builder.add_connection(merger_id, "merged_data", writer_id, "data")
        
        workflow = builder.build("multiple_inputs_test")
        
        # Execute workflow
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        result = runner.run(workflow)
        
        # Verify data from multiple sources was combined
        assert result.status == NodeStatus.COMPLETED
        
        merged_data = pd.read_csv(temp_data_dir / "merged.csv")
        assert len(merged_data) == 4  # All rows from both sources
        assert set(merged_data["id"]) == {1, 2, 3, 4}
    
    def test_circular_dependency_detection(self):
        """Test that circular dependencies are detected and prevented."""
        builder = WorkflowBuilder()
        
        # Create nodes that would form a cycle
        node1_id = builder.add_node(
            "DataProcessor",
            "node1",
            inputs={"data": InputType(format=DataFormat.JSON)},
            outputs={"processed": OutputType(format=DataFormat.JSON)}
        )
        
        node2_id = builder.add_node(
            "DataProcessor",
            "node2",
            inputs={"data": InputType(format=DataFormat.JSON)},
            outputs={"processed": OutputType(format=DataFormat.JSON)}
        )
        
        node3_id = builder.add_node(
            "DataProcessor",
            "node3",
            inputs={"data": InputType(format=DataFormat.JSON)},
            outputs={"processed": OutputType(format=DataFormat.JSON)}
        )
        
        # Create connections that would form a cycle
        builder.add_connection(node1_id, "processed", node2_id, "data")
        builder.add_connection(node2_id, "processed", node3_id, "data")
        
        # This should raise an error
        with pytest.raises(ValidationError):
            builder.add_connection(node3_id, "processed", node1_id, "data")
    
    def test_data_transformation_chain(self, temp_data_dir: Path):
        """Test a chain of data transformations."""
        builder = WorkflowBuilder()
        
        # Create initial data
        input_csv = temp_data_dir / "input.csv"
        input_csv.write_text("id,value\n1,1.5\n2,2.5\n3,3.5\n")
        
        # Create a chain of transformations
        reader_id = builder.add_node(
            "CSVFileReader",
            "reader",
            inputs={"path": InputType(value=str(input_csv))},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        # Transform 1: Multiply by 2
        mult_id = builder.add_node(
            "DataTransformer",
            "multiplier",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "operation": InputType(value="multiply"),
                "factor": InputType(value=2)
            },
            outputs={"transformed_data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        # Transform 2: Add 10
        add_id = builder.add_node(
            "DataTransformer",
            "adder",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "operation": InputType(value="add"),
                "value": InputType(value=10)
            },
            outputs={"transformed_data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        # Transform 3: Round values
        round_id = builder.add_node(
            "DataTransformer",
            "rounder",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "operation": InputType(value="round"),
                "decimals": InputType(value=0)
            },
            outputs={"transformed_data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        writer_id = builder.add_node(
            "CSVFileWriter",
            "writer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType(value=str(temp_data_dir / "transformed.csv"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        # Connect the transformation chain
        builder.add_connection(reader_id, "data", mult_id, "data")
        builder.add_connection(mult_id, "transformed_data", add_id, "data")
        builder.add_connection(add_id, "transformed_data", round_id, "data")
        builder.add_connection(round_id, "transformed_data", writer_id, "data")
        
        workflow = builder.build("transformation_chain_test")
        
        # Execute workflow
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        result = runner.run(workflow)
        
        # Verify transformations were applied in order
        assert result.status == NodeStatus.COMPLETED
        
        transformed_data = pd.read_csv(temp_data_dir / "transformed.csv")
        expected_values = [13, 15, 17]  # (1.5*2+10=13), (2.5*2+10=15), (3.5*2+10=17)
        assert list(transformed_data["value"]) == expected_values