"""
Template: Basic ETL Pipeline
Purpose: Extract data from CSV, transform it, and load into JSON
Use Case: Simple data processing workflows

Customization Points:
- INPUT_FILE: Path to your input CSV file
- OUTPUT_FILE: Path for output JSON file
- transform_data(): Your transformation logic
- VALIDATION_RULES: Data validation criteria
"""

from kailash.workflow.graph import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import JSONWriterNode
from typing import Dict, Any, List
import os

# Configuration (customize these)
INPUT_FILE = "data/input.csv"
OUTPUT_FILE = "outputs/processed_data.json"
VALIDATION_RULES = {
    "required_fields": ["id", "name", "value"],
    "min_value": 0,
    "max_value": 1000
}

def validate_data(data: List[Dict], rules: Dict) -> Dict[str, Any]:
    """Validate input data according to rules"""
    errors = []
    valid_records = []
    
    for i, record in enumerate(data):
        # Check required fields
        missing_fields = [field for field in rules["required_fields"] 
                         if field not in record]
        if missing_fields:
            errors.append(f"Row {i}: Missing fields {missing_fields}")
            continue
        
        # Validate numeric ranges
        if "value" in record:
            value = float(record.get("value", 0))
            if value < rules["min_value"] or value > rules["max_value"]:
                errors.append(f"Row {i}: Value {value} out of range")
                continue
        
        valid_records.append(record)
    
    return {
        "valid_data": valid_records,
        "errors": errors,
        "validation_summary": {
            "total_records": len(data),
            "valid_records": len(valid_records),
            "invalid_records": len(errors)
        }
    }

def transform_data(data: List[Dict]) -> Dict[str, Any]:
    """Transform the validated data (customize this function)"""
    transformed = []
    
    for record in data:
        # Example transformations
        transformed_record = {
            "id": record["id"],
            "name": record["name"].upper(),  # Convert to uppercase
            "value": float(record["value"]),
            "value_squared": float(record["value"]) ** 2,  # Calculate square
            "category": "high" if float(record["value"]) > 500 else "low"
        }
        transformed.append(transformed_record)
    
    # Calculate summary statistics
    total_value = sum(r["value"] for r in transformed)
    avg_value = total_value / len(transformed) if transformed else 0
    
    return {
        "transformed_data": transformed,
        "summary": {
            "total_records": len(transformed),
            "total_value": total_value,
            "average_value": avg_value
        }
    }

def create_etl_workflow():
    """Create the ETL workflow"""
    workflow = Workflow()
    
    # 1. Extract: Read CSV data
    csv_reader = CSVReaderNode(
        config={"file_path": INPUT_FILE}
    )
    workflow.add_node("extract", csv_reader)
    
    # 2. Validate: Check data quality
    validator = PythonCodeNode.from_function(
        func=validate_data,
        name="data_validator",
        description="Validate input data"
    )
    workflow.add_node("validate", validator)
    
    # 3. Transform: Process valid data
    transformer = PythonCodeNode.from_function(
        func=transform_data,
        name="data_transformer",
        description="Transform validated data"
    )
    workflow.add_node("transform", transformer)
    
    # 4. Load: Write to JSON
    json_writer = JSONWriterNode(
        config={
            "file_path": OUTPUT_FILE,
            "indent": 2
        }
    )
    workflow.add_node("load", json_writer)
    
    # Connect the pipeline
    workflow.connect("extract", "validate", mapping={"data": "data"})
    workflow.connect("validate", "transform", mapping={"valid_data": "data"})
    workflow.connect("transform", "load", mapping={"transformed_data": "data"})
    
    return workflow

def main():
    """Execute the ETL workflow"""
    # Ensure output directory exists
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # Create and validate workflow
    workflow = create_etl_workflow()
    workflow.validate()
    
    # Execute workflow
    runtime = LocalRuntime()
    try:
        # Pass validation rules as runtime parameter
        results = runtime.execute(
            workflow,
            inputs={"validate": {"rules": VALIDATION_RULES}}
        )
        
        print("ETL Pipeline completed successfully!")
        print(f"Results saved to: {OUTPUT_FILE}")
        
        # Print summary
        if "transform" in results:
            summary = results["transform"].get("summary", {})
            print(f"\nSummary:")
            print(f"- Total records processed: {summary.get('total_records', 0)}")
            print(f"- Average value: {summary.get('average_value', 0):.2f}")
        
        # Print any validation errors
        if "validate" in results:
            errors = results["validate"].get("errors", [])
            if errors:
                print(f"\nValidation errors found:")
                for error in errors[:5]:  # Show first 5 errors
                    print(f"  - {error}")
                if len(errors) > 5:
                    print(f"  ... and {len(errors) - 5} more errors")
        
        return 0
        
    except Exception as e:
        print(f"Error executing workflow: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())