"""Example demonstrating the PythonCodeNode for custom code execution.

This example shows how to create nodes from:
1. Python functions
2. Python classes 
3. Code strings
4. External Python files
"""

import pandas as pd
import numpy as np
from pathlib import Path

from kailash.workflow.graph import Workflow
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data import CSVReader, CSVWriter
from kailash.runtime import LocalRuntime


def create_function_based_node():
    """Example of creating a node from a Python function."""
    
    # Define a custom data processing function
    def calculate_metrics(data: pd.DataFrame, window_size: int = 5) -> pd.DataFrame:
        """Calculate rolling metrics for the data."""
        # Convert to DataFrame if needed
        if isinstance(data, list):
            data = pd.DataFrame(data)
        
        # Convert string columns to numeric where possible
        for col in ['value', 'quantity']:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')
        
        result = data.copy()
        
        # Calculate rolling mean
        for column in data.select_dtypes(include=[np.number]).columns:
            result[f'{column}_rolling_mean'] = data[column].rolling(window_size).mean()
            result[f'{column}_rolling_std'] = data[column].rolling(window_size).std()
        
        # Add a custom metric
        if 'value' in data.columns:
            result['value_zscore'] = (data['value'] - data['value'].mean()) / data['value'].std()
        
        # Convert DataFrame to JSON-serializable format
        return result.to_dict('records')
    
    # Create node from function
    return PythonCodeNode.from_function(
        func=calculate_metrics,
        name="metrics_calculator",
        description="Calculate rolling statistics and z-scores"
    )


def create_class_based_node():
    """Example of creating a stateful node from a Python class."""
    
    class OutlierDetector:
        """Stateful outlier detection using IQR method."""
        
        def __init__(self, sensitivity: float = 1.5):
            self.sensitivity = sensitivity
            self.q1 = None
            self.q3 = None
            self.iqr = None
            self.outlier_count = 0
        
        def process(self, data: pd.DataFrame, value_column: str = 'value') -> pd.DataFrame:
            """Process data and mark outliers."""
            # Convert to DataFrame if needed
            if isinstance(data, list):
                data = pd.DataFrame(data)
            
            # Convert string columns to numeric where possible
            for col in ['value', 'quantity']:
                if col in data.columns:
                    data[col] = pd.to_numeric(data[col], errors='coerce')
            
            result = data.copy()
            
            # Calculate IQR on first run
            if self.q1 is None:
                self.q1 = data[value_column].quantile(0.25)
                self.q3 = data[value_column].quantile(0.75)
                self.iqr = self.q3 - self.q1
            
            # Detect outliers
            lower_bound = self.q1 - self.sensitivity * self.iqr
            upper_bound = self.q3 + self.sensitivity * self.iqr
            
            result['is_outlier'] = (
                (data[value_column] < lower_bound) | 
                (data[value_column] > upper_bound)
            )
            
            # Track outlier count
            new_outliers = result['is_outlier'].sum()
            self.outlier_count += new_outliers
            result['total_outliers'] = self.outlier_count
            
            # Convert DataFrame to JSON-serializable format
            return result.to_dict('records')
    
    # Create node from class
    return PythonCodeNode.from_class(
        class_type=OutlierDetector,
        name="outlier_detector",
        description="Detect outliers using IQR method with state tracking"
    )


def create_code_string_node():
    """Example of creating a node from a code string."""
    
    # Define processing logic as a string
    code = """
# Custom data aggregation logic
# pandas is available as 'pandas' in the namespace

# Convert to DataFrame if needed
if isinstance(data, list):
    data = pandas.DataFrame(data)

# Convert string columns to numeric where possible
for col in ['value', 'quantity']:
    if col in data.columns:
        data[col] = pandas.to_numeric(data[col], errors='coerce')

# Group data by category and calculate statistics
grouped = data.groupby('category').agg({
    'value': ['mean', 'std', 'count'],
    'timestamp': ['min', 'max']
})

# Flatten column names
grouped.columns = ['_'.join(col).strip() for col in grouped.columns.values]
grouped.reset_index(inplace=True)

# Add derived metrics
grouped['cv'] = grouped['value_std'] / grouped['value_mean']  # Coefficient of variation
grouped['duration'] = pandas.to_datetime(grouped['timestamp_max']) - pandas.to_datetime(grouped['timestamp_min'])

# Store result and convert to JSON-serializable format
result = grouped.to_dict('records')
"""
    
    # Create node from code string
    return PythonCodeNode(
        name="custom_aggregator",
        code=code,
        input_types={'data': pd.DataFrame},
        output_type=pd.DataFrame,
        description="Custom aggregation with derived metrics"
    )


def create_external_file_node():
    """Example of creating a node from an external Python file."""
    
    # First, create a Python file with custom logic
    external_file = Path("custom_processor.py")
    external_file.write_text("""
import pandas as pd
import numpy as np

def advanced_processing(data: pd.DataFrame, threshold: float = 0.5) -> pd.DataFrame:
    '''Apply advanced processing with configurable threshold.'''
    # Convert to DataFrame if needed
    if isinstance(data, list):
        data = pd.DataFrame(data)
    
    # Convert string columns to numeric where possible
    for col in ['value', 'quantity']:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors='coerce')
    
    result = data.copy()
    
    # Apply transformations
    for col in data.select_dtypes(include=[np.number]).columns:
        # Normalize values
        result[f'{col}_normalized'] = (data[col] - data[col].mean()) / data[col].std()
        
        # Apply threshold
        result[f'{col}_above_threshold'] = data[col] > (data[col].mean() + threshold * data[col].std())
    
    # Add composite score
    numeric_cols = result.select_dtypes(include=[np.number]).columns
    result['composite_score'] = result[numeric_cols].mean(axis=1)
    
    # Convert DataFrame to JSON-serializable format
    return result.to_dict('records')

class DataProcessor:
    '''Stateful data processor with memory.'''
    
    def __init__(self):
        self.history = []
        
    def process(self, data: pd.DataFrame) -> pd.DataFrame:
        # Convert to DataFrame if needed
        if isinstance(data, list):
            data = pd.DataFrame(data)
        
        # Convert string columns to numeric where possible
        for col in ['value', 'quantity']:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')
        
        self.history.append(len(data))
        
        result = data.copy()
        result['record_count'] = len(data)
        result['total_processed'] = sum(self.history)
        result['batch_number'] = len(self.history)
        
        # Convert DataFrame to JSON-serializable format
        return result.to_dict('records')
""")
    
    # Create node from file (function)
    function_node = PythonCodeNode.from_file(
        file_path=external_file,
        function_name="advanced_processing",
        name="file_based_processor",
        description="Advanced processing from external file"
    )
    
    # Create node from file (class)
    class_node = PythonCodeNode.from_file(
        file_path=external_file,
        class_name="DataProcessor",
        name="file_based_class",
        description="Stateful processor from external file"
    )
    
    return function_node, class_node


def main():
    """Demonstrate PythonCodeNode usage in a workflow."""
    
    # Create sample data
    sample_data = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=100, freq='h'),
        'category': np.random.choice(['A', 'B', 'C'], 100),
        'value': np.random.normal(100, 15, 100),
        'quantity': np.random.randint(1, 20, 100)
    })
    sample_data.to_csv('data/sample_metrics.csv', index=False)
    
    # Create workflow
    workflow = Workflow(workflow_id="python_code_demo", name="python_code_demo")
    
    # Add data reader
    reader = CSVReader(file_path="data/sample_metrics.csv", name="data_reader")
    workflow.add_node("data_reader", reader)
    
    # Create and add custom nodes
    function_node = create_function_based_node()
    class_node = create_class_based_node()
    # code_node = create_code_string_node()  # Commented out due to security restrictions
    file_node, _ = create_external_file_node()
    
    workflow.add_node("function_node", function_node)
    workflow.add_node("class_node", class_node)
    # workflow.add_node("code_node", code_node)  # Commented out
    workflow.add_node("file_node", file_node)
    
    # Add data writer
    writer = CSVWriter(file_path="data/results.csv", name="result_writer")
    workflow.add_node("result_writer", writer)
    
    # Connect nodes in pipeline
    workflow.connect("data_reader", "function_node", {"data": "data"})
    workflow.connect("function_node", "class_node", {"result": "data"})
    workflow.connect("class_node", "file_node", {"result": "data"})
    workflow.connect("file_node", "result_writer", {"result": "data"})
    
    # Comment out code node due to security restrictions in this demo
    # workflow.connect("data_reader", "code_node", {"data": "data"})
    # aggregation_writer = CSVWriter(file_path="data/aggregated_metrics.csv", name="aggregation_writer")
    # workflow.add_node("aggregation_writer", aggregation_writer)
    # workflow.connect("code_node", "aggregation_writer", {"result": "data"})
    
    # Configure nodes
    reader.config = {'file_path': 'data/sample_metrics.csv'}
    writer.config = {'file_path': 'data/processed_metrics.csv'}
    # aggregation_writer.config = {'file_path': 'data/aggregated_metrics.csv'}
    
    # Add custom parameters
    function_node.config = {'window_size': 10}
    class_node.config = {'value_column': 'value'}
    file_node.config = {'threshold': 0.8}
    
    # Visualize workflow
    try:
        import matplotlib.pyplot as plt
        workflow.visualize()
        plt.savefig('data/python_code_workflow.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("Workflow visualization saved to 'data/python_code_workflow.png'")
    except ImportError:
        print("Matplotlib not available for visualization")
    
    # Execute workflow
    print("\\nExecuting workflow...")
    runner = LocalRuntime(debug=True)
    results, run_id = runner.execute(workflow)
    
    print(f"\\nWorkflow completed successfully!")
    print(f"Results: {results}")
    
    # Show sample of processed data
    processed_df = pd.read_csv('data/processed_metrics.csv')
    print(f"\\nProcessed data shape: {processed_df.shape}")
    print(f"New columns: {[col for col in processed_df.columns if col not in sample_data.columns]}")
    
    # Show aggregated data (commented out for this demo)
    # aggregated_df = pd.read_csv('data/aggregated_metrics.csv')
    # print(f"\\nAggregated data shape: {aggregated_df.shape}")
    # print(aggregated_df.head())
    
    # Clean up
    Path("custom_processor.py").unlink(missing_ok=True)


if __name__ == "__main__":
    # Create data directory
    Path("data").mkdir(exist_ok=True)
    
    main()