"""Unit tests for basic workflow functionality."""

import csv
import tempfile
from pathlib import Path

import pytest

from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.runtime.local import LocalRuntime

# NOTE: Some tests may have CI-specific teardown issues but work fine locally


class TestBasicWorkflow:
    """Test basic workflow construction and execution."""

    def teardown_method(self):
        """Clean up after each test method."""
        # Ensure any lingering state is cleaned up
        import gc

        gc.collect()

    @pytest.fixture
    def sample_csv_file(self, tmp_path):
        """Create a sample CSV file for testing."""
        csv_file = tmp_path / "test_data.csv"
        data = [
            {"id": "1", "name": "Alice", "value": "100"},
            {"id": "2", "name": "Bob", "value": "200"},
            {"id": "3", "name": "Charlie", "value": "150"},
        ]

        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "name", "value"])
            writer.writeheader()
            writer.writerows(data)

        return csv_file

    @pytest.mark.skip(reason="CI-specific teardown issue - works locally")
    def test_csv_reader_node(self, sample_csv_file):
        """Test CSVReaderNode reads data correctly."""
        # Create workflow
        workflow = Workflow(workflow_id="test_csv_reader", name="test_csv_reader")

        # Add CSV reader node
        reader = CSVReaderNode(file_path=str(sample_csv_file), headers=True)
        workflow.add_node("reader", reader)

        # Execute workflow
        runtime = LocalRuntime()
        result, run_id = runtime.execute(workflow)

        # Verify results
        assert "reader" in result
        assert "data" in result["reader"]
        assert len(result["reader"]["data"]) == 3
        assert result["reader"]["data"][0]["name"] == "Alice"

    def test_python_code_node_integration(self, sample_csv_file, tmp_path):
        """Test PythonCodeNode processes data from CSVReaderNode."""
        # Create workflow
        workflow = Workflow(
            workflow_id="test_python_integration", name="test_python_integration"
        )

        # Add CSV reader
        reader = CSVReaderNode(file_path=str(sample_csv_file), headers=True)
        workflow.add_node("reader", reader)

        # Create Python node for data transformation
        def transform_data(data: list) -> dict:
            """Transform data by calculating total."""
            total = sum(int(row["value"]) for row in data)
            return {
                "total": total,
                "count": len(data),
            }  # PythonCodeNode wraps in result

        transformer = PythonCodeNode.from_function(
            func=transform_data,
            name="data_transformer",
            description="Calculate total value",
        )
        workflow.add_node("transformer", transformer)

        # Connect nodes
        workflow.connect(
            source_node="reader", target_node="transformer", mapping={"data": "data"}
        )

        # Execute workflow
        runtime = LocalRuntime()
        result, run_id = runtime.execute(workflow)

        # Verify results
        assert "transformer" in result
        assert "result" in result["transformer"]
        assert result["transformer"]["result"]["total"] == 450
        assert result["transformer"]["result"]["count"] == 3

    def test_csv_writer_node(self, sample_csv_file, tmp_path):
        """Test complete CSV read-transform-write workflow."""
        # Create workflow
        workflow = Workflow(workflow_id="test_csv_pipeline", name="test_csv_pipeline")

        # Add CSV reader
        reader = CSVReaderNode(file_path=str(sample_csv_file), headers=True)
        workflow.add_node("reader", reader)

        # Add transformer that filters data
        def filter_data(data: list, min_value: int) -> list:
            """Filter rows by minimum value."""
            filtered = [row for row in data if int(row["value"]) >= min_value]
            return filtered  # PythonCodeNode will wrap this in {"result": filtered}

        filter_node = PythonCodeNode.from_function(
            func=filter_data,
            name="value_filter",
            description="Filter by minimum value",
            input_schema={
                "data": NodeParameter(name="data", type=list, required=True),
                "min_value": NodeParameter(name="min_value", type=int, required=True),
            },
        )
        workflow.add_node("filter", filter_node)

        # Add CSV writer
        output_file = tmp_path / "filtered_output.csv"
        writer = CSVWriterNode(file_path=str(output_file))
        workflow.add_node("writer", writer)

        # Connect nodes
        workflow.connect("reader", "filter", mapping={"data": "data"})
        workflow.connect("filter", "writer", mapping={"result": "data"})

        # Execute with parameters
        runtime = LocalRuntime()
        parameters = {"filter": {"min_value": 150}}
        result, run_id = runtime.execute(workflow, parameters=parameters)

        # Verify output file was created
        assert output_file.exists()

        # Read and verify output
        with open(output_file, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2  # Only Bob (200) and Charlie (150)
            assert all(int(row["value"]) >= 150 for row in rows)

    def test_workflow_disconnected_nodes(self):
        """Test workflow with disconnected nodes raises proper error."""
        workflow = Workflow(workflow_id="test_disconnected", name="test_disconnected")

        # Create nodes that require connections
        def transform(data: list) -> list:
            return data

        transformer = PythonCodeNode.from_function(
            func=transform, name="transformer", description="Requires data input"
        )
        workflow.add_node("transformer", transformer)

        # This should raise an error because transformer needs input
        runtime = LocalRuntime()
        with pytest.raises(Exception) as exc_info:
            runtime.execute(workflow)

        # Verify the error message mentions missing inputs
        assert "missing required inputs" in str(exc_info.value)

    def test_runtime_parameters(self, sample_csv_file):
        """Test runtime parameter passing to nodes."""
        workflow = Workflow(workflow_id="test_parameters", name="test_parameters")

        # Add a simple Python node that accepts runtime parameters
        def process_config(config: dict) -> dict:
            """Process configuration."""
            return config  # PythonCodeNode wraps in result

        config_node = PythonCodeNode.from_function(
            func=process_config,
            name="config_processor",
            description="Process configuration",
        )
        workflow.add_node("config", config_node)

        # Execute with runtime parameters
        runtime = LocalRuntime()
        parameters = {"config": {"config": {"runtime": "override"}}}
        result, run_id = runtime.execute(workflow, parameters=parameters)

        # Verify runtime parameter was used
        assert result["config"]["result"]["runtime"] == "override"

    def test_workflow_with_multiple_outputs(self, tmp_path):
        """Test workflow with nodes producing multiple outputs."""
        workflow = Workflow(
            workflow_id="test_multiple_outputs", name="test_multiple_outputs"
        )

        # Create a node that produces multiple outputs
        def split_data(data: list) -> dict:
            """Split data into even and odd indices."""
            even = [data[i] for i in range(0, len(data), 2)]
            odd = [data[i] for i in range(1, len(data), 2)]
            return {
                "even_items": even,
                "odd_items": odd,
                "total_count": len(data),
            }  # PythonCodeNode wraps in result

        # Add a Python node that provides test data
        def provide_data() -> list:
            """Provide test data."""
            return [1, 2, 3, 4, 5, 6]  # PythonCodeNode wraps in result

        data_source = PythonCodeNode.from_function(
            func=provide_data, name="data_provider", description="Provide test data"
        )
        workflow.add_node("data_source", data_source)

        # Add splitter node
        splitter = PythonCodeNode.from_function(
            func=split_data, name="data_splitter", description="Split data by index"
        )
        workflow.add_node("splitter", splitter)

        # Connect nodes
        workflow.connect("data_source", "splitter", mapping={"result": "data"})

        # Execute
        runtime = LocalRuntime()
        result, run_id = runtime.execute(workflow)

        # Verify outputs
        assert result["splitter"]["result"]["even_items"] == [1, 3, 5]
        assert result["splitter"]["result"]["odd_items"] == [2, 4, 6]
        assert result["splitter"]["result"]["total_count"] == 6
