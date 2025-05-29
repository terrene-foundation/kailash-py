"""Simple example demonstrating CSV reader connected to custom Python node."""
from typing import Any, Dict
import pandas as pd
from pathlib import Path

from kailash.workflow import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.data import CSVReader, CSVWriter
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime import LocalRuntime


def main():
    """Simple workflow: CSV -> Python Processing -> CSV"""
    
    # Setup paths
    sample_directory = Path('tests/sample_data')
    output_directory = Path('output')
    output_directory.mkdir(exist_ok=True)
    
    # 1. Create a workflow
    workflow = Workflow(name="Simple Data Processing")
    
    # 2. Create CSV reader node
    csv_reader = CSVReader(
        file_path=sample_directory / 'customer_value.csv',
        headers=True,
        delimiter=','
    )
    
    # 3. Create custom Python node for filtering
    def filter_high_value_customers(data: list, column_name: str, threshold: float) -> Dict[str, Any]:
        """Filter customers based on a threshold value."""
        df = pd.DataFrame(data)
        filtered_df = df[df[column_name] > threshold]
        
        return {
            'filtered_data': filtered_df.to_dict(orient='records'),
            'count': len(filtered_df),
            'total_value': filtered_df[column_name].sum()
        }
    
    # Define schemas for the Python node
    filter_node = PythonCodeNode.from_function(
        func=filter_high_value_customers,
        name="high_value_filter",
        description="Filter customers with high claim amounts",
        input_schema={
            'data': NodeParameter(name='data', type=list, required=True),
            'column_name': NodeParameter(name='column_name', type=str, required=True),
            'threshold': NodeParameter(name='threshold', type=float, required=True)
        },
        output_schema={
            'filtered_data': NodeParameter(name='filtered_data', type=list, required=True),
            'count': NodeParameter(name='count', type=int, required=True),
            'total_value': NodeParameter(name='total_value', type=float, required=True)
        }
    )
    
    # Configure the filter node
    filter_node.configure({
        'column_name': 'Total Claim Amount',
        'threshold': 1000.0
    })
    
    # 4. Create CSV writer node for results
    csv_writer = CSVWriter(
        file_path=str(output_directory / 'high_value_customers.csv'),
        headers=True
    )
    
    # 5. Add nodes to workflow
    workflow.add_node(csv_reader)
    workflow.add_node(filter_node)
    workflow.add_node(csv_writer)
    
    # 6. Connect the nodes
    # CSV reader output 'data' -> Filter input 'data'
    workflow.connect(csv_reader.id, 'data', filter_node.id, 'data')
    
    # Filter output 'filtered_data' -> CSV writer input 'data'
    workflow.connect(filter_node.id, 'filtered_data', csv_writer.id, 'data')
    
    # 7. Execute the workflow
    runner = LocalRuntime(debug=True)
    result = runner.run(workflow)
    
    # 8. Display results
    filter_output = runner.get_node_output(filter_node.id)
    print(f"Found {filter_output['count']} high-value customers")
    print(f"Total value: ${filter_output['total_value']:,.2f}")
    print(f"Results saved to: {output_directory / 'high_value_customers.csv'}")
    
    # 9. Alternative: Direct execution without workflow
    print("\n=== Direct Execution Example ===")
    
    # Execute nodes directly
    csv_data = csv_reader.execute()
    filter_result = filter_node.execute(
        data=csv_data['data'],
        column_name='Total Claim Amount',
        threshold=1500.0  # Different threshold
    )
    
    print(f"Direct execution: {filter_result['count']} customers with claims > $1500")
    
    # Create another Python node on the fly
    def calculate_statistics(data: list, value_column: str) -> Dict[str, Any]:
        """Calculate basic statistics."""
        df = pd.DataFrame(data)
        values = df[value_column]
        
        return {
            'mean': values.mean(),
            'median': values.median(),
            'std': values.std(),
            'min': values.min(),
            'max': values.max()
        }
    
    stats_node = PythonCodeNode.from_function(
        func=calculate_statistics,
        name="statistics_calculator"
    )
    
    stats_result = stats_node.execute(
        data=csv_data['data'],
        value_column='Total Claim Amount'
    )
    
    print("\nStatistics for all customers:")
    for stat, value in stats_result.items():
        print(f"  {stat}: ${value:,.2f}")


if __name__ == "__main__":
    # Create sample data
    sample_dir = Path('tests/sample_data')
    sample_dir.mkdir(parents=True, exist_ok=True)
    
    if not (sample_dir / 'customer_value.csv').exists():
        # Create sample data
        data = pd.DataFrame({
            'Customer': ['Alice', 'Bob', 'Charlie', 'David', 'Eve', 'Frank'],
            'Total Claim Amount': [1500, 800, 2500, 600, 1200, 3000],
            'Status': ['Active', 'Active', 'Inactive', 'Active', 'Active', 'Active']
        })
        data.to_csv(sample_dir / 'customer_value.csv', index=False)
        print("Created sample data")
    
    main()