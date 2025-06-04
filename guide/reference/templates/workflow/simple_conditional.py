"""
Template: Simple Conditional Routing
Purpose: Route data based on conditions using SwitchNode
Use Case: Process data differently based on status or category

Based on actual working examples from the SDK.
"""

from kailash.workflow.graph import Workflow
from kailash.nodes.data.readers import JSONReaderNode
from kailash.nodes.data.writers import JSONWriterNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.nodes.code.python import PythonCodeNode
from typing import Dict, Any, List
import os
import json

# Configuration
INPUT_FILE = "data/items.json"
OUTPUT_DIR = "outputs"

def process_high_value(data: List[Dict]) -> Dict[str, Any]:
    """Process high value items"""
    processed = []
    for item in data:
        item_copy = item.copy()
        item_copy['discount'] = 0.10  # 10% discount
        item_copy['priority'] = 'high'
        processed.append(item_copy)
    return {"data": processed}

def process_low_value(data: List[Dict]) -> Dict[str, Any]:
    """Process low value items"""
    processed = []
    for item in data:
        item_copy = item.copy()
        item_copy['discount'] = 0.05  # 5% discount
        item_copy['priority'] = 'normal'
        processed.append(item_copy)
    return {"data": processed}

def create_sample_data():
    """Create sample data if it doesn't exist"""
    if not os.path.exists(INPUT_FILE):
        os.makedirs(os.path.dirname(INPUT_FILE), exist_ok=True)
        sample_data = [
            {"id": 1, "name": "Product A", "value": 150, "category": "high"},
            {"id": 2, "name": "Product B", "value": 50, "category": "low"},
            {"id": 3, "name": "Product C", "value": 200, "category": "high"},
            {"id": 4, "name": "Product D", "value": 75, "category": "low"},
        ]
        with open(INPUT_FILE, 'w') as f:
            json.dump(sample_data, f, indent=2)

def main():
    """Create and run conditional workflow"""
    # Ensure we have data
    create_sample_data()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Create workflow
    workflow = Workflow()
    
    # Read data
    reader = JSONReaderNode(file_path=INPUT_FILE)
    workflow.add_node("reader", reader)
    
    # Switch based on category
    switch = SwitchNode(
        condition_field="category",
        cases=["high", "low"]
    )
    workflow.add_node("switch", switch)
    
    # Process high value items
    high_processor = PythonCodeNode.from_function(
        func=process_high_value,
        name="high_processor"
    )
    workflow.add_node("process_high", high_processor)
    
    # Process low value items
    low_processor = PythonCodeNode.from_function(
        func=process_low_value,
        name="low_processor"
    )
    workflow.add_node("process_low", low_processor)
    
    # Write outputs
    high_writer = JSONWriterNode(file_path=f"{OUTPUT_DIR}/high_value.json")
    workflow.add_node("write_high", high_writer)
    
    low_writer = JSONWriterNode(file_path=f"{OUTPUT_DIR}/low_value.json")
    workflow.add_node("write_low", low_writer)
    
    # Connect workflow
    workflow.connect("reader", "switch", {"data": "input_data"})
    
    # Connect switch outputs to processors
    workflow.connect("switch", "process_high", {"case_high": "data"})
    workflow.connect("switch", "process_low", {"case_low": "data"})
    
    # Connect processors to writers
    workflow.connect("process_high", "write_high", {"data": "data"})
    workflow.connect("process_low", "write_low", {"data": "data"})
    
    # Run workflow
    try:
        results, run_id = workflow.run()
        print(f"Workflow completed! Run ID: {run_id}")
        print(f"High value items: {OUTPUT_DIR}/high_value.json")
        print(f"Low value items: {OUTPUT_DIR}/low_value.json")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())