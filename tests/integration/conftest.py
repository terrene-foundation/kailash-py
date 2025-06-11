"""Integration test fixtures for Kailash SDK."""

import json
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml

from kailash.manifest import KailashManifest
from kailash.tracking.manager import TaskManager
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_csv_file(temp_data_dir: Path) -> Path:
    """Create a sample CSV file for testing."""
    csv_path = temp_data_dir / "sample.csv"
    csv_path.write_text("id,name,value\n1,Alice,100\n2,Bob,200\n3,Charlie,300\n")
    return csv_path


@pytest.fixture
def sample_json_file(temp_data_dir: Path) -> Path:
    """Create a sample JSON file for testing."""
    json_path = temp_data_dir / "sample.json"
    data = {
        "items": [
            {"id": 1, "name": "Alice", "value": 100},
            {"id": 2, "name": "Bob", "value": 200},
            {"id": 3, "name": "Charlie", "value": 300},
        ]
    }
    json_path.write_text(json.dumps(data, indent=2))
    return json_path


@pytest.fixture
def mock_api_data() -> dict:
    """Create mock API response data."""
    return {
        "status": "success",
        "data": [
            {"id": 1, "metric": 42.5},
            {"id": 2, "metric": 37.8},
            {"id": 3, "metric": 55.1},
        ],
    }


@pytest.fixture
def simple_workflow(sample_csv_file: Path, temp_data_dir: Path) -> Workflow:
    """Create a simple workflow for testing."""
    builder = WorkflowBuilder()

    # Add nodes
    reader_id = builder.add_node(
        "CSVReaderNode", "reader", config={"file_path": str(sample_csv_file)}
    )

    filter_id = builder.add_node(
        "FilterNode", "filter", config={"field": "value", "operator": ">", "value": 100}
    )

    writer_id = builder.add_node(
        "CSVWriterNode",
        "writer",
        config={"file_path": str(temp_data_dir / "output.csv")},
    )

    # Connect nodes
    builder.add_connection(reader_id, "data", filter_id, "data")
    builder.add_connection(filter_id, "filtered_data", writer_id, "data")

    return builder.build("simple_test_workflow")


@pytest.fixture
def complex_workflow(
    sample_csv_file: Path, sample_json_file: Path, temp_data_dir: Path
) -> Workflow:
    """Create a complex multi-branch workflow for testing."""
    builder = WorkflowBuilder()

    # Add CSV reader
    csv_reader_id = builder.add_node(
        "CSVReaderNode", "csv_reader", config={"file_path": str(sample_csv_file)}
    )

    # Add filter
    filter_id = builder.add_node(
        "FilterNode", "filter", config={"field": "value", "operator": ">", "value": 150}
    )

    # Add AI processor
    ai_processor_id = builder.add_node(
        "TextSummarizer",
        "ai_processor",
        config={"texts": ["Analyze this data and provide insights"], "max_length": 100},
    )

    # Add outputs
    csv_writer_id = builder.add_node(
        "CSVWriterNode",
        "csv_writer",
        config={"file_path": str(temp_data_dir / "processed.csv")},
    )

    json_writer_id = builder.add_node(
        "JSONWriterNode",
        "json_writer",
        config={"file_path": str(temp_data_dir / "processed.json")},
    )

    report_writer_id = builder.add_node(
        "TextWriterNode",
        "report_writer",
        config={
            "file_path": str(temp_data_dir / "report.txt"),
            "text": "Data analysis complete",
        },
    )

    # Connect nodes
    builder.add_connection(csv_reader_id, "data", filter_id, "data")
    builder.add_connection(filter_id, "filtered_data", csv_writer_id, "data")
    builder.add_connection(filter_id, "filtered_data", json_writer_id, "data")
    # AI processor can run independently
    builder.add_connection(ai_processor_id, "summaries", report_writer_id, "data")

    return builder.build("complex_test_workflow")


@pytest.fixture
def sample_manifest(simple_workflow: Workflow) -> KailashManifest:
    """Create a sample manifest for testing."""
    return KailashManifest(
        metadata={
            "id": "test-manifest",
            "name": "Test Manifest",
            "version": "1.0.0",
            "author": "Test Author",
            "description": "Test manifest for integration tests",
        },
        workflow=simple_workflow,
    )


@pytest.fixture
def task_manager(temp_data_dir: Path) -> TaskManager:
    """Create a task manager for testing."""
    from kailash.tracking.storage.filesystem import FileSystemStorage

    storage = FileSystemStorage(base_path=str(temp_data_dir / "tasks"))
    return TaskManager(storage_backend=storage)


@pytest.fixture
def mock_llm_response() -> str:
    """Create a mock LLM response for testing."""
    return """Based on the data analysis:

    1. Total records: 3
    2. Average value: 200
    3. Key insights:
       - Bob has the median value
       - Charlie has the highest value at 300
       - Alice has the lowest value at 100

    Recommendations:
    - Focus on understanding Charlie's high performance
    - Investigate why Alice's value is lower
    """


@pytest.fixture
def error_workflow(temp_data_dir: Path) -> Workflow:
    """Create a workflow that will produce errors for testing."""
    builder = WorkflowBuilder()

    # Add a reader that will fail
    reader_id = builder.add_node(
        "CSVReaderNode",
        "bad_reader",
        config={"file_path": str(temp_data_dir / "nonexistent.csv")},
    )

    # Add a processor that will fail
    processor_id = builder.add_node(
        "FilterNode",
        "bad_filter",
        config={"field": "value", "operator": "invalid_op", "value": 100},
    )

    writer_id = builder.add_node(
        "CSVWriterNode",
        "writer",
        config={"file_path": str(temp_data_dir / "output.csv")},
    )

    builder.add_connection(reader_id, "data", processor_id, "data")
    builder.add_connection(processor_id, "filtered_data", writer_id, "data")

    return builder.build("error_test_workflow")


@pytest.fixture
def large_dataset(temp_data_dir: Path) -> Path:
    """Create a large dataset for performance testing."""
    csv_path = temp_data_dir / "large_dataset.csv"

    # Create a CSV with 10,000 rows
    with open(csv_path, "w") as f:
        f.write("id,name,value,category\n")
        for i in range(10000):
            name = f"User_{i}"
            value = i * 10 % 1000
            category = f"Cat_{i % 10}"
            f.write(f"{i},{name},{value},{category}\n")

    return csv_path


@pytest.fixture
def parallel_workflow(temp_data_dir: Path) -> Workflow:
    """Create a workflow with parallel execution paths."""
    builder = WorkflowBuilder()

    # Single input
    reader_id = builder.add_node(
        "CSVReaderNode",
        "reader",
        config={"file_path": str(temp_data_dir / "input.csv")},
    )

    # Parallel processing branches
    filter1_id = builder.add_node(
        "FilterNode",
        "filter_high",
        config={"field": "value", "operator": ">", "value": 500},
    )

    filter2_id = builder.add_node(
        "FilterNode",
        "filter_low",
        config={"field": "value", "operator": "<=", "value": 500},
    )

    # Parallel outputs
    writer1_id = builder.add_node(
        "CSVWriterNode",
        "writer_high",
        config={"file_path": str(temp_data_dir / "high_values.csv")},
    )

    writer2_id = builder.add_node(
        "CSVWriterNode",
        "writer_low",
        config={"file_path": str(temp_data_dir / "low_values.csv")},
    )

    # Connect parallel branches
    builder.add_connection(reader_id, "data", filter1_id, "data")
    builder.add_connection(reader_id, "data", filter2_id, "data")
    builder.add_connection(filter1_id, "filtered_data", writer1_id, "data")
    builder.add_connection(filter2_id, "filtered_data", writer2_id, "data")

    return builder.build("parallel_test_workflow")


@pytest.fixture
def yaml_workflow_config(temp_data_dir: Path) -> Path:
    """Create a YAML workflow configuration for testing."""
    config = {
        "workflow": {
            "name": "yaml_test_workflow",
            "description": "Workflow loaded from YAML",
            "nodes": [
                {
                    "id": "reader",
                    "type": "CSVReaderNode",
                    "inputs": {"file_path": str(temp_data_dir / "input.csv")},
                },
                {
                    "id": "processor",
                    "type": "FilterNode",
                    "inputs": {"field": "value", "operator": ">", "value": 100},
                },
                {
                    "id": "writer",
                    "type": "CSVWriterNode",
                    "inputs": {"file_path": str(temp_data_dir / "output.csv")},
                },
            ],
            "connections": [
                {
                    "from": "reader",
                    "from_output": "data",
                    "to": "processor",
                    "to_input": "data",
                },
                {
                    "from": "processor",
                    "from_output": "filtered_data",
                    "to": "writer",
                    "to_input": "data",
                },
            ],
        }
    }

    yaml_path = temp_data_dir / "workflow.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(config, f)

    return yaml_path
