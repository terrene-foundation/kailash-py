"""Unit tests for simplified workflow patterns."""

import tempfile
from pathlib import Path

import pytest

from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime


@pytest.mark.requires_isolation
class TestSimplifiedWorkflow:
    """Test simplified workflow patterns with basic nodes."""

    def test_minimal_workflow(self):
        """Test the simplest possible workflow."""
        # Create workflow
        workflow = Workflow(workflow_id="minimal_workflow", name="minimal_workflow")

        # Add a simple data generation node
        def generate_data() -> dict:
            """Generate test data."""
            return {"items": [f"Item {i}" for i in range(1, 6)], "count": 5}

        generator = PythonCodeNode.from_function(
            func=generate_data, name="data_generator", description="Generate test data"
        )
        workflow.add_node("generator", generator)

        # Execute workflow
        runtime = LocalRuntime()
        result, run_id = runtime.execute(workflow)

        # Verify results
        assert "generator" in result
        assert result["generator"]["result"]["count"] == 5
        assert len(result["generator"]["result"]["items"]) == 5

    def test_simple_transformation_pipeline(self):
        """Test a simple data transformation pipeline."""
        # Create workflow
        workflow = Workflow(workflow_id="transform_pipeline", name="transform_pipeline")

        # Data source node
        def create_data() -> list:
            """Create sample data."""
            return [{"id": i, "value": i * 10} for i in range(1, 11)]

        source = PythonCodeNode.from_function(
            func=create_data, name="data_source", description="Create sample data"
        )
        workflow.add_node("source", source)

        # Transformation node
        def transform_data(data: list) -> dict:
            """Transform data by adding processed field."""
            transformed = []
            for item in data:
                transformed.append(
                    {
                        **item,
                        "processed_value": item["value"] * 1.1,
                        "status": "processed",
                    }
                )
            return {"transformed_data": transformed, "record_count": len(transformed)}

        transformer = PythonCodeNode.from_function(
            func=transform_data, name="data_transformer", description="Transform data"
        )
        workflow.add_node("transformer", transformer)

        # Connect nodes
        workflow.connect("source", "transformer", mapping={"result": "data"})

        # Execute workflow
        runtime = LocalRuntime()
        result, run_id = runtime.execute(workflow)

        # Verify transformation
        assert "transformer" in result
        assert result["transformer"]["result"]["record_count"] == 10
        transformed = result["transformer"]["result"]["transformed_data"]
        assert all(item["status"] == "processed" for item in transformed)
        assert transformed[0]["processed_value"] == 11.0  # 10 * 1.1

    def test_workflow_with_multiple_steps(self):
        """Test workflow with multiple processing steps."""
        # Create workflow
        workflow = Workflow(workflow_id="multi_step", name="multi_step")

        # Step 1: Generate data
        def generate() -> list:
            """Generate initial data."""
            return [
                {"id": i, "name": f"Item {i}", "value": i * 5}
                for i in range(1, 6)  # Values: 5, 10, 15, 20, 25
            ]

        generator = PythonCodeNode.from_function(func=generate, name="generator")
        workflow.add_node("step1", generator)

        # Step 2: Filter data
        def filter_data(data: list, threshold: int) -> list:
            """Filter items by value threshold."""
            return [item for item in data if item["value"] >= threshold]

        filter_node = PythonCodeNode.from_function(
            func=filter_data,
            name="filter",
            input_schema={
                "data": NodeParameter(name="data", type=list, required=True),
                "threshold": NodeParameter(name="threshold", type=int, required=True),
            },
        )
        workflow.add_node("step2", filter_node)

        # Step 3: Summarize
        def summarize(data: list) -> dict:
            """Create summary statistics."""
            if not data:
                return {"total": 0, "count": 0, "average": 0}

            total = sum(item["value"] for item in data)
            count = len(data)
            return {
                "total": total,
                "count": count,
                "average": total / count if count > 0 else 0,
            }

        summarizer = PythonCodeNode.from_function(func=summarize, name="summarizer")
        workflow.add_node("step3", summarizer)

        # Connect steps
        workflow.connect("step1", "step2", mapping={"result": "data"})
        workflow.connect("step2", "step3", mapping={"result": "data"})

        # Execute with parameters
        runtime = LocalRuntime()
        parameters = {"step2": {"threshold": 10}}
        result, run_id = runtime.execute(workflow, parameters=parameters)

        # Verify results
        assert "step3" in result
        summary = result["step3"]["result"]
        assert (
            summary["count"] == 4
        )  # Items 2, 3, 4, 5 have values >= 10 (10, 15, 20, 25)
        assert summary["total"] == 70  # 10 + 15 + 20 + 25
        assert summary["average"] == 17.5

    def test_empty_workflow_execution(self):
        """Test that empty workflows can be executed without error."""
        # Create empty workflow
        workflow = Workflow(workflow_id="empty_workflow", name="empty_workflow")

        # Execute empty workflow
        runtime = LocalRuntime()
        result, run_id = runtime.execute(workflow)

        # Verify execution completed with empty results
        assert isinstance(result, dict)
        assert len(result) == 0
        assert run_id is not None

    def test_single_node_no_inputs(self):
        """Test single node with no external inputs."""
        # Create workflow
        workflow = Workflow(workflow_id="single_node", name="single_node")

        # Add self-contained node
        def compute() -> dict:
            """Compute without inputs."""
            return {"result": "computed", "status": "success"}

        computer = PythonCodeNode.from_function(func=compute, name="computer")
        workflow.add_node("compute", computer)

        # Execute
        runtime = LocalRuntime()
        result, run_id = runtime.execute(workflow)

        # Verify
        assert "compute" in result
        assert result["compute"]["result"]["status"] == "success"
