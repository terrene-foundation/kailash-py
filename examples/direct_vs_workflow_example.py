"""Example demonstrating the difference between direct node execution and workflow execution."""
from pathlib import Path
import pandas as pd

from kailash.workflow import Workflow
from kailash.nodes.data.readers import CSVReader
from kailash.nodes.data.writers import CSVWriter
from kailash.runtime.local import LocalRuntime


def direct_execution_example():
    """Demonstrate direct node execution."""
    print("=== Direct Node Execution ===")
    print("In direct execution, nodes run immediately with all parameters provided upfront.\n")
    
    # Create and configure nodes with all parameters
    reader = CSVReader(
        file_path='tests/sample_data/customer_value.csv',
        headers=True
    )
    
    # Execute the reader directly
    result = reader.execute()
    print(f"Direct execution: Read {len(result['data'])} rows")
    
    # Create writer with data available upfront
    writer = CSVWriter(
        file_path='output/direct_output.csv',
        data=result['data'],  # Data provided at creation time
        # Don't provide headers=True for dict data - let it auto-detect
    )
    
    # Execute the writer directly
    writer_result = writer.execute()
    print(f"Direct execution: Wrote {writer_result['rows_written']} rows")
    
    return result['data']


def workflow_execution_example():
    """Demonstrate workflow execution."""
    print("\n=== Workflow Execution ===")
    print("In workflow execution, nodes are connected and data flows through the graph.\n")
    
    # Create workflow
    workflow = Workflow(name="CSV Processing")
    
    # Create nodes - writer doesn't need data at creation time
    reader = CSVReader(
        file_path='tests/sample_data/customer_value.csv',
        headers=True
    )
    
    writer = CSVWriter(
        file_path='output/workflow_output.csv',
        # Note: No data parameter - it will come from the connection
        # Don't provide headers=True for dict data - let it auto-detect
    )
    
    # Add nodes to workflow
    workflow.add_node(reader, node_id='reader')
    workflow.add_node(writer, node_id='writer')
    
    # Connect nodes - data flows from reader to writer
    workflow.connect(
        source_node='reader',
        target_node='writer',
        mapping={'data': 'data'}  # Map reader's 'data' output to writer's 'data' input
    )
    
    # Execute workflow
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow)
    
    print(f"Workflow execution: Read {len(results['reader']['data'])} rows")
    print(f"Workflow execution: Wrote {results['writer']['rows_written']} rows")
    
    return results


def main():
    """Run both examples to show the difference."""
    # Ensure output directory exists
    Path('output').mkdir(exist_ok=True)
    
    # Create sample data if it doesn't exist
    sample_directory = Path('tests/sample_data')
    sample_directory.mkdir(parents=True, exist_ok=True)
    
    if not (sample_directory / 'customer_value.csv').exists():
        # Create simple sample data
        sample_data = pd.DataFrame({
            'Customer': ['Alice', 'Bob', 'Charlie'],
            'Total Claim Amount': [1500, 800, 2500],
            'Status': ['Active', 'Active', 'Inactive']
        })
        
        sample_data.to_csv(
            sample_directory / 'customer_value.csv',
            index=False
        )
        print("Sample data created.\n")
    
    # Run both examples
    print("This example shows the difference between direct node execution and workflow execution.\n")
    
    # Direct execution
    direct_data = direct_execution_example()
    
    # Workflow execution
    workflow_results = workflow_execution_example()
    
    print("\n=== Key Differences ===")
    print("1. Direct execution:")
    print("   - Nodes run immediately when execute() is called")
    print("   - All parameters must be provided upfront")
    print("   - Good for simple operations or testing")
    
    print("\n2. Workflow execution:")
    print("   - Nodes are connected in a graph")
    print("   - Data flows through connections")
    print("   - Parameters can be provided by upstream nodes")
    print("   - Better for complex data pipelines")
    print("   - Provides execution tracking and management")
    
    print("\nBoth files should contain the same data:")
    print("- output/direct_output.csv")
    print("- output/workflow_output.csv")


if __name__ == "__main__":
    main()