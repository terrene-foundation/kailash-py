"""Integration tests for PythonCodeNode in workflows."""

import numpy as np
import pandas as pd
import pytest
from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode, JSONReaderNode
from kailash.runtime.local import LocalRuntime


class TestPythonCodeNodeIntegration:
    """Test PythonCodeNode integration with other components."""

    @pytest.fixture
    def sample_data(self, tmp_path):
        """Create sample data files."""
        # Create CSV data
        csv_file = tmp_path / "data.csv"
        df = pd.DataFrame(
            {
                "id": range(1, 11),
                "value": np.random.normal(100, 10, 10),
                "category": ["A", "B", "C"] * 3 + ["A"],
            }
        )
        df.to_csv(csv_file, index=False)

        # Create JSON data
        json_file = tmp_path / "config.json"
        json_data = {"threshold": 95, "multiplier": 1.5, "categories": ["A", "B", "C"]}
        import json

        json_file.write_text(json.dumps(json_data))

        return csv_file, json_file

    def test_function_node_in_workflow(self, sample_data, tmp_path):
        """Test function-based PythonCodeNode in a workflow."""
        csv_file, json_file = sample_data

        # Create function node
        def process_with_config(data: list, config: dict) -> list:
            """Apply threshold and multiply values."""
            threshold = config.get("threshold", 0)
            multiplier = config.get("multiplier", 1)

            # Convert to DataFrame for processing
            df = pd.DataFrame(data)
            # Convert value column to numeric
            df["value"] = pd.to_numeric(df["value"])

            mask = df["value"] > threshold
            df.loc[mask, "value"] *= multiplier
            df["above_threshold"] = mask

            # Return as list - the framework will wrap it in {"result": ...}
            return df.to_dict("records")

        # Create workflow
        workflow = Workflow(workflow_id="function_workflow", name="function_workflow")

        # Add nodes with config
        output_file = tmp_path / "output.csv"

        csv_reader = CSVReaderNode(name="csv_reader", file_path=str(csv_file))
        json_reader = JSONReaderNode(name="json_reader", file_path=str(json_file))
        processor = PythonCodeNode.from_function(
            func=process_with_config, name="processor"
        )
        writer = CSVWriterNode(name="writer", file_path=str(output_file))

        workflow.add_node("csv_reader", csv_reader)
        workflow.add_node("json_reader", json_reader)
        workflow.add_node("processor", processor)
        workflow.add_node("writer", writer)

        # Connect nodes
        workflow.connect("csv_reader", "processor", {"data": "data"})
        workflow.connect("json_reader", "processor", {"data": "config"})
        workflow.connect("processor", "writer", {"result": "data"})

        # Execute workflow
        runner = LocalRuntime()
        results, run_id = runner.execute(workflow)

        # Verify results
        assert output_file.exists()
        result_df = pd.read_csv(output_file)
        assert "above_threshold" in result_df.columns

        # Check that values above threshold were multiplied
        original_df = pd.read_csv(csv_file)
        for idx, row in result_df.iterrows():
            if row["above_threshold"]:
                expected = original_df.iloc[idx]["value"] * 1.5
                assert abs(row["value"] - expected) < 0.01

    def test_class_node_with_state(self, sample_data, tmp_path):
        """Test stateful class-based PythonCodeNode."""
        csv_file, _ = sample_data

        # Create stateful node
        class RunningStats:
            def __init__(self):
                self.count = 0
                self.sum = 0
                self.sum_sq = 0

            def process(self, data: pd.DataFrame) -> pd.DataFrame:
                """Calculate running statistics."""
                # Handle both DataFrame and list of dicts from CSV reader
                if isinstance(data, list):
                    data = pd.DataFrame(data)
                # Convert to numeric first (CSV reader returns strings)
                data["value"] = pd.to_numeric(data["value"])
                values = data["value"].values
                self.count += len(values)
                self.sum += values.sum()
                self.sum_sq += (values**2).sum()

                mean = self.sum / self.count
                var = (self.sum_sq / self.count) - mean**2
                std = np.sqrt(var)

                result = data.copy()
                result["running_mean"] = mean
                result["running_std"] = std
                result["z_score"] = (data["value"] - mean) / std

                # Convert DataFrame to list of dicts for JSON serialization
                return result.to_dict("records")

        # Create workflow
        workflow = Workflow(workflow_id="stateful_workflow", name="stateful_workflow")

        output_file = tmp_path / "stats_output.csv"

        reader = CSVReaderNode(name="reader", file_path=str(csv_file))
        stats_node = PythonCodeNode.from_class(class_type=RunningStats, name="stats")
        writer = CSVWriterNode(name="writer", file_path=str(output_file))

        workflow.add_node("reader", reader)
        workflow.add_node("stats", stats_node)
        workflow.add_node("writer", writer)

        workflow.connect("reader", "stats", {"data": "data"})
        workflow.connect("stats", "writer", {"result": "data"})

        # Execute workflow
        runner = LocalRuntime()
        results, run_id = runner.execute(workflow)

        # Verify results
        result_df = pd.read_csv(output_file)
        assert "running_mean" in result_df.columns
        assert "running_std" in result_df.columns
        assert "z_score" in result_df.columns

        # All rows should have the same running stats (single batch)
        assert result_df["running_mean"].nunique() == 1
        assert result_df["running_std"].nunique() == 1

    def test_code_string_node(self, sample_data, tmp_path):
        """Test code string-based PythonCodeNode."""
        csv_file, _ = sample_data

        # Create code string node
        code = """
# pandas is already available in the namespace
# Convert data to DataFrame and numeric types
df = pandas.DataFrame(data)
df['value'] = pandas.to_numeric(df['value'])
df['id'] = pandas.to_numeric(df['id'])

# Group by category and aggregate
grouped = df.groupby('category').agg({
    'value': ['mean', 'std', 'count'],
    'id': 'count'
})

# Flatten columns
grouped.columns = ['_'.join(col).strip() for col in grouped.columns.values]
grouped.reset_index(inplace=True)

# Calculate coefficient of variation
grouped['cv'] = grouped['value_std'] / grouped['value_mean']

# Convert to list of dicts for JSON serialization
result = grouped.to_dict('records')
"""

        # Create workflow
        workflow = Workflow(workflow_id="code_workflow", name="code_workflow")

        output_file = tmp_path / "aggregated.csv"

        reader = CSVReaderNode(name="reader", file_path=str(csv_file))
        aggregator = PythonCodeNode(
            name="aggregator",
            code=code,
            input_types={"data": pd.DataFrame},
            output_type=pd.DataFrame,
        )
        writer = CSVWriterNode(name="writer", file_path=str(output_file))

        workflow.add_node("reader", reader)
        workflow.add_node("aggregator", aggregator)
        workflow.add_node("writer", writer)

        workflow.connect("reader", "aggregator", {"data": "data"})
        workflow.connect("aggregator", "writer", {"result": "data"})

        # Execute workflow
        runner = LocalRuntime()
        results, run_id = runner.execute(workflow)

        # Verify results
        result_df = pd.read_csv(output_file)
        assert "category" in result_df.columns
        assert "value_mean" in result_df.columns
        assert "cv" in result_df.columns
        assert len(result_df) == 3  # Three categories

    def test_multiple_code_nodes(self, sample_data, tmp_path):
        """Test multiple PythonCodeNodes in a pipeline."""
        csv_file, _ = sample_data

        # Create multiple processing nodes
        def normalize(data: list) -> list:
            """Normalize numeric columns."""
            # Convert list of dicts to DataFrame
            df = pd.DataFrame(data)
            # Convert numeric columns
            df["id"] = pd.to_numeric(df["id"])
            df["value"] = pd.to_numeric(df["value"])

            for col in df.select_dtypes(include=[np.number]).columns:
                if col != "id":
                    df[col] = (df[col] - df[col].mean()) / df[col].std()
            # Return as list of dicts
            return df.to_dict("records")

        def add_features(data: list) -> list:
            """Add engineered features."""
            df = pd.DataFrame(data)
            # Ensure numeric types
            if "value" in df.columns:
                df["value"] = pd.to_numeric(df["value"])

            df["value_squared"] = df["value"] ** 2
            df["value_abs"] = df["value"].abs()
            df["category_encoded"] = df["category"].map({"A": 1, "B": 2, "C": 3})
            return df.to_dict("records")

        # Create workflow with pipeline
        workflow = Workflow(workflow_id="pipeline_workflow", name="pipeline_workflow")

        output_file = tmp_path / "pipeline_output.csv"

        reader = CSVReaderNode(name="reader", file_path=str(csv_file))
        normalizer = PythonCodeNode.from_function(normalize, name="normalizer")
        feature_eng = PythonCodeNode.from_function(add_features, name="features")
        writer = CSVWriterNode(name="writer", file_path=str(output_file))

        workflow.add_node("reader", reader)
        workflow.add_node("normalizer", normalizer)
        workflow.add_node("features", feature_eng)
        workflow.add_node("writer", writer)

        workflow.connect("reader", "normalizer", {"data": "data"})
        workflow.connect("normalizer", "features", {"result": "data"})
        workflow.connect("features", "writer", {"result": "data"})

        # Execute workflow
        runner = LocalRuntime()
        results, run_id = runner.execute(workflow)

        # Verify results
        result_df = pd.read_csv(output_file)

        # Check normalization (should have mean ~0, std ~1)
        assert abs(result_df["value"].mean()) < 0.1
        assert abs(result_df["value"].std() - 1) < 0.1

        # Check feature engineering
        assert "value_squared" in result_df.columns
        assert "value_abs" in result_df.columns
        assert "category_encoded" in result_df.columns

    def test_error_handling_in_workflow(self, sample_data, tmp_path):
        """Test error handling when PythonCodeNode fails."""
        csv_file, _ = sample_data

        # Create node that will fail
        def failing_processor(data: pd.DataFrame) -> pd.DataFrame:
            if len(data) > 5:
                raise ValueError("Too many rows!")
            return data

        # Create workflow
        workflow = Workflow(workflow_id="failing_workflow", name="failing_workflow")

        output_file = tmp_path / "should_not_exist.csv"

        reader = CSVReaderNode(name="reader", file_path=str(csv_file))
        processor = PythonCodeNode.from_function(
            failing_processor, name="failing_processor"
        )
        writer = CSVWriterNode(name="writer", file_path=str(output_file))

        workflow.add_node("reader", reader)
        workflow.add_node("processor", processor)
        workflow.add_node("writer", writer)

        workflow.connect("reader", "processor", {"data": "data"})
        workflow.connect("processor", "writer", {"result": "data"})

        # Execute workflow and expect failure
        runner = LocalRuntime()
        with pytest.raises(Exception, match="Too many rows"):
            runner.execute(workflow)

        # Output file should not exist
        assert not output_file.exists()
