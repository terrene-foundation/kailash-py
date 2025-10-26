# Workflow Creation Patterns

*Modern workflow building with WorkflowBuilder*

## 🎯 Prerequisites
- Completed [Fundamentals Overview](01-fundamentals-overview.md)
- Understanding of nodes and connections

## 🏗️ Basic Workflow Structure

### Simple Workflow
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

# Create workflow with modern API
workflow = WorkflowBuilder()

# Add nodes with configuration
workflow.add_node("CSVReaderNode", "data_reader", {
    "file_path": "/data/input.csv",
    "has_header": True,
    "delimiter": ","
})

workflow.add_node("PythonCodeNode", "processor", {
    "code": '''
# Process the data - parameters are injected directly
# NOTE: In PythonCodeNode, input_data comes from the connected node
processed = [item for item in input_data if item.get('amount', 0) > 100]
result = {'processed_items': processed, 'count': len(processed)}
'''
})

# Connect nodes with 4-parameter syntax
workflow.add_connection("data_reader", "result", "processor", "input_data")

# Execute - ALWAYS call .build() before execution
runtime = LocalRuntime()  # For CLI/scripts (synchronous)
results, run_id = runtime.execute(workflow.build())

# For Docker/FastAPI (asynchronous)
# from kailash.runtime import AsyncLocalRuntime
# runtime = AsyncLocalRuntime()
# results = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

### Progressive Workflow Building
```python
def build_data_pipeline():
    """Build a complete data processing pipeline"""
    workflow = WorkflowBuilder()

    # 1. Data Input Layer
    workflow.add_node("CSVReaderNode", "customer_reader", {
        "file_path": "/data/customers.csv",
        "has_header": True,
        "delimiter": ","
    })

    workflow.add_node("JSONReaderNode", "config_reader", {
        "file_path": "/config/processing_rules.json"
    })

    # 2. Data Processing Layer
    workflow.add_node("PythonCodeNode", "validator", {
        "code": '''
# Validate customer data
customer_data = input_data if isinstance(input_data, list) else []
valid_customers = []
invalid_customers = []

for customer in customer_data:
    if (customer.get("email") and "@" in customer["email"] and
        customer.get("age", 0) >= 18):
        valid_customers.append(customer)
    else:
        invalid_customers.append(customer)

result = {
    "valid": valid_customers,
    "invalid": invalid_customers,
    "validation_summary": {
        "total": len(customer_data),
        "valid_count": len(valid_customers),
        "invalid_count": len(invalid_customers),
        "success_rate": len(valid_customers) / len(customer_data) if customer_data else 0
    }
}
'''
    })

    workflow.add_node("PythonCodeNode", "enricher", {
        "code": '''
# Enrich valid customer data with processing rules
valid_customers = input_data.get('valid', [])
rules = processing_rules if 'processing_rules' in globals() else {}

enriched_customers = []
for customer in valid_customers:
    enriched = customer.copy()
    enriched['processed_date'] = '2024-01-01'  # Example enrichment
    enriched['status'] = 'processed'
    enriched_customers.append(enriched)

result = {
    'enriched_customers': enriched_customers,
    'enrichment_count': len(enriched_customers)
}
'''
    })

    # 3. Output Layer
    workflow.add_node("JSONWriterNode", "output_writer", {
        "file_path": "/output/processed_customers.json",
        "indent": 2
    })

    # Connect pipeline
    workflow.add_connection("customer_reader", "result", "validator", "input_data")
    workflow.add_connection("validator", "result", "enricher", "input_data")
    workflow.add_connection("enricher", "result", "output_writer", "data")

    return workflow

# Execute the pipeline - ALWAYS call .build() before execution
pipeline = build_data_pipeline()
runtime = LocalRuntime()  # For CLI/scripts (synchronous)
results, run_id = runtime.execute(pipeline.build())
```

## 🔧 Workflow Factory Pattern

### Reusable Workflow Templates
```python
class WorkflowFactory:
    """Factory for creating common workflow patterns"""

    @staticmethod
    def create_etl_workflow(input_file, output_file, transform_code):
        """Create ETL workflow with custom transformation"""
        workflow = WorkflowBuilder()

        # Extract
        workflow.add_node("CSVReaderNode", "extractor", {
            "file_path": input_file,
            "has_header": True
        })

        # Transform
        workflow.add_node("PythonCodeNode", "transformer", {
            "code": transform_code
        })

        # Load
        workflow.add_node("JSONWriterNode", "loader", {
            "file_path": output_file,
            "indent": 2
        })

        # Connections
        workflow.add_connection("extractor", "result", "transformer", "input_data")
        workflow.add_connection("transformer", "result", "loader", "data")

        return workflow

    @staticmethod
    def create_validation_workflow(data_source, validation_rules):
        """Create data validation workflow"""
        workflow = WorkflowBuilder()

        # Data source
        workflow.add_node("PythonCodeNode", "data_source", {
            "code": f"result = {data_source}"
        })

        # Validator
        workflow.add_node("PythonCodeNode", "validator", {
            "code": f'''
rules = {validation_rules}
validated_items = []
failed_items = []

for item in input_data:
    valid = True
    for field, rule in rules.items():
        if field not in item or not rule(item[field]):
            valid = False
            break

    if valid:
        validated_items.append(item)
    else:
        failed_items.append(item)

result = {{
    'valid': validated_items,
    'failed': failed_items,
    'validation_rate': len(validated_items) / len(input_data) if input_data else 0
}}
'''
        })

        workflow.add_connection("data_source", "result", "validator", "input_data")
        return workflow

# Usage examples
etl_workflow = WorkflowFactory.create_etl_workflow(
    "input.csv",
    "output.json",
    "result = [{{**item, 'processed': True}} for item in input_data]"
)

validation_workflow = WorkflowFactory.create_validation_workflow(
    [{"name": "Alice", "age": 25}, {"name": "Bob", "age": 17}],
    {"name": lambda x: len(x) > 0, "age": lambda x: x >= 18}
)
```

## ✅ Modern Patterns

### Dynamic Node Addition
```python
def create_multi_source_workflow(data_sources):
    """Create workflow with dynamic number of data sources"""
    workflow = WorkflowBuilder()

    # Add data sources dynamically
    for i, source_config in enumerate(data_sources):
        node_name = f"source_{i}"
        workflow.add_node("PythonCodeNode", node_name, {
            "code": f"result = {source_config['data']}"
        })

    # Add combiner
    workflow.add_node("PythonCodeNode", "combiner", {
        "code": '''
# Combine all inputs (input names will be source_0, source_1, etc.)
combined_data = []
for key, value in globals().items():
    if key.startswith('source_') and isinstance(value, list):
        combined_data.extend(value)

result = {'combined': combined_data, 'total_count': len(combined_data)}
'''
    })

    # Connect all sources to combiner
    for i in range(len(data_sources)):
        workflow.add_connection("source", "result", "target", "input")  # Fixed f-string pattern

    return workflow

# Usage
sources = [
    {"data": [1, 2, 3]},
    {"data": [4, 5, 6]},
    {"data": [7, 8, 9]}
]
multi_workflow = create_multi_source_workflow(sources)
```

## 🔗 Next Steps
- [Workflow Connections](02-workflows-connections.md) - Advanced data flow
- [PythonCodeNode Patterns](02-workflows-python-code.md) - Custom processing
- [Workflow Execution](02-workflows-execution.md) - Runtime patterns
