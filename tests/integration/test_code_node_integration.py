"""Integration tests for PythonCodeNode in workflows."""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from kailash import Workflow
from kailash.nodes import PythonCodeNode
from kailash.nodes.data import CSVReader, CSVWriter, JSONReader, JSONWriter
from kailash.runtime import LocalRunner


class TestPythonCodeNodeIntegration:
    """Test PythonCodeNode integration with other components."""
    
    @pytest.fixture
    def sample_data(self, tmp_path):
        """Create sample data files."""
        # Create CSV data
        csv_file = tmp_path / "data.csv"
        df = pd.DataFrame({
            'id': range(1, 11),
            'value': np.random.normal(100, 10, 10),
            'category': ['A', 'B', 'C'] * 3 + ['A']
        })
        df.to_csv(csv_file, index=False)
        
        # Create JSON data
        json_file = tmp_path / "config.json"
        json_data = {
            'threshold': 95,
            'multiplier': 1.5,
            'categories': ['A', 'B', 'C']
        }
        import json
        json_file.write_text(json.dumps(json_data))
        
        return csv_file, json_file
    
    def test_function_node_in_workflow(self, sample_data, tmp_path):
        """Test function-based PythonCodeNode in a workflow."""
        csv_file, json_file = sample_data
        
        # Create function node
        def process_with_config(data: pd.DataFrame, config: dict) -> pd.DataFrame:
            """Apply threshold and multiply values."""
            threshold = config.get('threshold', 0)
            multiplier = config.get('multiplier', 1)
            
            result = data.copy()
            mask = result['value'] > threshold
            result.loc[mask, 'value'] *= multiplier
            result['above_threshold'] = mask
            
            return result
        
        # Create workflow
        workflow = Workflow(name="function_workflow")
        
        # Add nodes
        csv_reader = CSVReader(name="csv_reader")
        json_reader = JSONReader(name="json_reader")
        processor = PythonCodeNode.from_function(
            func=process_with_config,
            name="processor"
        )
        writer = CSVWriter(name="writer")
        
        workflow.add_node(csv_reader)
        workflow.add_node(json_reader)
        workflow.add_node(processor)
        workflow.add_node(writer)
        
        # Connect nodes
        workflow.add_edge(csv_reader, processor, output_key="data")
        workflow.add_edge(json_reader, processor, output_key="config")
        workflow.add_edge(processor, writer)
        
        # Configure nodes
        csv_reader.config = {'file_path': str(csv_file)}
        json_reader.config = {'file_path': str(json_file)}
        output_file = tmp_path / "output.csv"
        writer.config = {'file_path': str(output_file)}
        
        # Execute workflow
        runner = LocalRunner()
        results = runner.run(workflow)
        
        # Verify results
        assert output_file.exists()
        result_df = pd.read_csv(output_file)
        assert 'above_threshold' in result_df.columns
        
        # Check that values above threshold were multiplied
        original_df = pd.read_csv(csv_file)
        for idx, row in result_df.iterrows():
            if row['above_threshold']:
                expected = original_df.iloc[idx]['value'] * 1.5
                assert abs(row['value'] - expected) < 0.01
    
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
                values = data['value'].values
                self.count += len(values)
                self.sum += values.sum()
                self.sum_sq += (values ** 2).sum()
                
                mean = self.sum / self.count
                var = (self.sum_sq / self.count) - mean ** 2
                std = np.sqrt(var)
                
                result = data.copy()
                result['running_mean'] = mean
                result['running_std'] = std
                result['z_score'] = (data['value'] - mean) / std
                
                return result
        
        # Create workflow
        workflow = Workflow(name="stateful_workflow")
        
        reader = CSVReader(name="reader")
        stats_node = PythonCodeNode.from_class(
            class_type=RunningStats,
            name="stats"
        )
        writer = CSVWriter(name="writer")
        
        workflow.add_node(reader)
        workflow.add_node(stats_node)
        workflow.add_node(writer)
        
        workflow.add_edge(reader, stats_node)
        workflow.add_edge(stats_node, writer)
        
        # Configure nodes
        reader.config = {'file_path': str(csv_file)}
        output_file = tmp_path / "stats_output.csv"
        writer.config = {'file_path': str(output_file)}
        
        # Execute workflow
        runner = LocalRunner()
        results = runner.run(workflow)
        
        # Verify results
        result_df = pd.read_csv(output_file)
        assert 'running_mean' in result_df.columns
        assert 'running_std' in result_df.columns
        assert 'z_score' in result_df.columns
        
        # All rows should have the same running stats (single batch)
        assert result_df['running_mean'].nunique() == 1
        assert result_df['running_std'].nunique() == 1
    
    def test_code_string_node(self, sample_data, tmp_path):
        """Test code string-based PythonCodeNode."""
        csv_file, _ = sample_data
        
        # Create code string node
        code = """
import pandas as pd

# Group by category and aggregate
grouped = data.groupby('category').agg({
    'value': ['mean', 'std', 'count'],
    'id': 'count'
})

# Flatten columns
grouped.columns = ['_'.join(col).strip() for col in grouped.columns.values]
grouped.reset_index(inplace=True)

# Calculate coefficient of variation
grouped['cv'] = grouped['value_std'] / grouped['value_mean']

result = grouped
"""
        
        # Create workflow
        workflow = Workflow(name="code_workflow")
        
        reader = CSVReader(name="reader")
        aggregator = PythonCodeNode(
            name="aggregator",
            code=code,
            input_types={'data': pd.DataFrame},
            output_type=pd.DataFrame
        )
        writer = CSVWriter(name="writer")
        
        workflow.add_node(reader)
        workflow.add_node(aggregator)
        workflow.add_node(writer)
        
        workflow.add_edge(reader, aggregator)
        workflow.add_edge(aggregator, writer)
        
        # Configure nodes
        reader.config = {'file_path': str(csv_file)}
        output_file = tmp_path / "aggregated.csv"
        writer.config = {'file_path': str(output_file)}
        
        # Execute workflow
        runner = LocalRunner()
        results = runner.run(workflow)
        
        # Verify results
        result_df = pd.read_csv(output_file)
        assert 'category' in result_df.columns
        assert 'value_mean' in result_df.columns
        assert 'cv' in result_df.columns
        assert len(result_df) == 3  # Three categories
    
    def test_multiple_code_nodes(self, sample_data, tmp_path):
        """Test multiple PythonCodeNodes in a pipeline."""
        csv_file, _ = sample_data
        
        # Create multiple processing nodes
        def normalize(data: pd.DataFrame) -> pd.DataFrame:
            """Normalize numeric columns."""
            result = data.copy()
            for col in result.select_dtypes(include=[np.number]).columns:
                if col != 'id':
                    result[col] = (result[col] - result[col].mean()) / result[col].std()
            return result
        
        def add_features(data: pd.DataFrame) -> pd.DataFrame:
            """Add engineered features."""
            result = data.copy()
            result['value_squared'] = result['value'] ** 2
            result['value_abs'] = result['value'].abs()
            result['category_encoded'] = result['category'].map({'A': 1, 'B': 2, 'C': 3})
            return result
        
        # Create workflow with pipeline
        workflow = Workflow(name="pipeline_workflow")
        
        reader = CSVReader(name="reader")
        normalizer = PythonCodeNode.from_function(normalize, name="normalizer")
        feature_eng = PythonCodeNode.from_function(add_features, name="features")
        writer = CSVWriter(name="writer")
        
        workflow.add_node(reader)
        workflow.add_node(normalizer)
        workflow.add_node(feature_eng)
        workflow.add_node(writer)
        
        workflow.add_edge(reader, normalizer)
        workflow.add_edge(normalizer, feature_eng)
        workflow.add_edge(feature_eng, writer)
        
        # Configure nodes
        reader.config = {'file_path': str(csv_file)}
        output_file = tmp_path / "pipeline_output.csv"
        writer.config = {'file_path': str(output_file)}
        
        # Execute workflow
        runner = LocalRunner()
        results = runner.run(workflow)
        
        # Verify results
        result_df = pd.read_csv(output_file)
        
        # Check normalization (should have mean ~0, std ~1)
        assert abs(result_df['value'].mean()) < 0.1
        assert abs(result_df['value'].std() - 1) < 0.1
        
        # Check feature engineering
        assert 'value_squared' in result_df.columns
        assert 'value_abs' in result_df.columns
        assert 'category_encoded' in result_df.columns
    
    def test_error_handling_in_workflow(self, sample_data, tmp_path):
        """Test error handling when PythonCodeNode fails."""
        csv_file, _ = sample_data
        
        # Create node that will fail
        def failing_processor(data: pd.DataFrame) -> pd.DataFrame:
            if len(data) > 5:
                raise ValueError("Too many rows!")
            return data
        
        # Create workflow
        workflow = Workflow(name="failing_workflow")
        
        reader = CSVReader(name="reader")
        processor = PythonCodeNode.from_function(
            failing_processor,
            name="failing_processor"
        )
        writer = CSVWriter(name="writer")
        
        workflow.add_node(reader)
        workflow.add_node(processor)
        workflow.add_node(writer)
        
        workflow.add_edge(reader, processor)
        workflow.add_edge(processor, writer)
        
        # Configure nodes
        reader.config = {'file_path': str(csv_file)}
        output_file = tmp_path / "should_not_exist.csv"
        writer.config = {'file_path': str(output_file)}
        
        # Execute workflow and expect failure
        runner = LocalRunner()
        with pytest.raises(Exception, match="Too many rows"):
            runner.run(workflow)
        
        # Output file should not exist
        assert not output_file.exists()