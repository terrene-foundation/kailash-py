"""
Template: Simple ETL Pipeline
Purpose: Basic Extract-Transform-Load workflow
Use Case: Simple data processing from CSV to JSON

This is a minimal template to get started quickly.
"""

from kailash.workflow.graph import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import JSONWriterNode
from typing import Dict, Any, List

# Configuration
INPUT_FILE = "data/input.csv"
OUTPUT_FILE = "outputs/output.json"


def transform_data(data: List[Dict]) -> Dict[str, Any]:
    """Transform your data here"""
    transformed = []

    for record in data:
        # Example: Convert names to uppercase
        new_record = record.copy()
        if "name" in new_record:
            new_record["name"] = new_record["name"].upper()
        transformed.append(new_record)

    return {"data": transformed}


def main():
    """Create and run the ETL workflow"""
    # Create workflow
    workflow = Workflow()

    # Add nodes
    reader = CSVReaderNode(file_path=INPUT_FILE)
    workflow.add_node("reader", reader)

    transformer = PythonCodeNode.from_function(func=transform_data, name="transformer")
    workflow.add_node("transformer", transformer)

    writer = JSONWriterNode(file_path=OUTPUT_FILE)
    workflow.add_node("writer", writer)

    # Connect nodes
    workflow.connect("reader", "transformer", {"data": "data"})
    workflow.connect("transformer", "writer", {"data": "data"})

    # Run workflow
    try:
        results, run_id = workflow.run()
        print(f"Workflow completed! Run ID: {run_id}")
        print(f"Output saved to: {OUTPUT_FILE}")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
