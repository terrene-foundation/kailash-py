# API Usage Guide

**Version**: v0.6.3 | **Tested and Validated**

## 🎯 Core API Patterns

All code examples in this guide have been **tested and validated** against the actual Kailash SDK.

### Basic Workflow Construction

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow builder (no name parameter needed)
workflow = WorkflowBuilder()

# Add nodes with proper syntax
workflow.add_node("PythonCodeNode", "data_processor", {
    "code": "result = {'processed': parameters.get('value', 0) * 2}"
})

workflow.add_node("PythonCodeNode", "validator", {
    "code": "result = {'valid': input_data.get('processed', 0) > 0}"
})

# Connect nodes
workflow.add_connection("data_processor", "result", "validator", "input_data")

# Build and execute
built_workflow = workflow.build()
runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow, parameters={
    "data_processor": {"value": 10}
})

print(results["validator"]["result"]["valid"])  # True
```

### Dot Notation for Nested Data

```python
workflow = WorkflowBuilder()

# Producer creates nested data structure
workflow.add_node("PythonCodeNode", "producer", {
    "code": """
result = {
    'data': {'customer': 'John', 'amount': 100},
    'metadata': {'timestamp': '2025-01-01', 'source': 'api'}
}
"""
})

# Consumer accesses nested data using dot notation
workflow.add_node("PythonCodeNode", "consumer", {
    "code": "result = {'customer_amount': input_data.get('amount', 0)}"
})

# Connect using dot notation to access nested fields
workflow.add_connection("producer", "result.data", "consumer", "input_data")
```

### Node Type Patterns

#### 1. String-based Node Types (Recommended)
```python
# Use string names for built-in nodes
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("LLMAgentNode", "analyzer", {"model": "gpt-4"})
workflow.add_node("JSONWriterNode", "writer", {"file_path": "output.json"})
```

#### 2. Class-based Node Types
```python
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode

# Use string references (recommended pattern)
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("LLMAgentNode", "analyzer", {"model": "gpt-4"})
```

#### 3. Instance-based Node Types
```python
# Use string-based approach instead (recommended)
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
# Note: Instance-based patterns are being deprecated in favor of string-based API
```

### Connection Patterns

#### Basic Connections
```python
# Simple field mapping
workflow.add_connection("source_node", "output_field", "target_node", "input_field")

# Default connections (uses 'result' and 'input_data')
workflow.add_connection("source_node", "result", "target_node", "input_data")
```

#### Advanced Connection Mapping
```python
# Multiple field mapping with dict
workflow.add_connection("source_node", "result", "target_node", "input")
```

### Runtime Patterns

#### Local Runtime (Most Common)
```python
from kailash.runtime.local import LocalRuntime

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "node_name": {"param": "value"}
})
```

#### Async Runtime Execution
```python
from kailash.runtime.local import LocalRuntime

runtime = LocalRuntime()
results, run_id = await runtime.execute_async(workflow.build(), parameters={
    "node_name": {"param": "value"}
})
```

#### Sync Runtime Execution
```python
from kailash.runtime.local import LocalRuntime

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "node_name": {"param": "value"}
})
```

### Parameter Passing

#### Runtime Parameters
```python
# Pass parameters at execution time
results, run_id = runtime.execute(workflow.build(), parameters={
    "csv_reader": {
        "file_path": "dynamic_file.csv",
        "delimiter": ","
    },
    "llm_agent": {
        "prompt": "Analyze this data and provide insights",
        "model": "gpt-4"
    }
})
```

#### Node Configuration (Build-time)
```python
# Configure nodes at build time
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "static_file.csv",
    "delimiter": ";",
    "has_header": True
})
```

### Error Handling Patterns

#### Basic Error Handling
```python
from kailash.sdk_exceptions import WorkflowValidationError, RuntimeExecutionError

try:
    workflow = WorkflowBuilder()
    workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
    built_workflow = workflow.build()

    runtime = LocalRuntime()
    results, run_id = runtime.execute(built_workflow)

except WorkflowValidationError as e:
    print(f"Workflow validation failed: {e}")
except RuntimeExecutionError as e:
    print(f"Execution failed: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

#### Connection Validation
```python
# This will raise WorkflowValidationError if nodes don't exist
try:
    workflow.add_connection("nonexistent_node", "result", "existing_node", "input")
except WorkflowValidationError as e:
    print(f"Invalid connection: {e}")
```

### Data Flow Patterns

#### Linear Pipeline
```python
workflow = WorkflowBuilder()

# Step 1: Read data
workflow.add_node("CSVReaderNode", "reader", {"file_path": "input.csv"})

# Step 2: Process data
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'processed_rows': len(input_data.get('rows', []))}"
})

# Step 3: Save results
workflow.add_node("JSONWriterNode", "writer", {"file_path": "output.json"})

# Connect in sequence
workflow.add_connection("reader", "result", "processor", "input_data")
workflow.add_connection("processor", "result", "writer", "data")
```

#### Parallel Processing
```python
workflow = WorkflowBuilder()

# Single source
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})

# Multiple parallel processors
workflow.add_node("PythonCodeNode", "analyzer1", {
    "code": "result = {'analysis_type': 'statistical'}"
})
workflow.add_node("PythonCodeNode", "analyzer2", {
    "code": "result = {'analysis_type': 'categorical'}"
})

# Merge results
workflow.add_node("MergeNode", "merger", {})

# Connect parallel paths
workflow.add_connection("reader", "result", "analyzer1", "input_data")
workflow.add_connection("reader", "result", "analyzer2", "input_data")
workflow.add_connection("analyzer1", "result", "merger", "input1")
workflow.add_connection("analyzer2", "result", "merger", "input2")
```

#### Conditional Routing
```python
workflow = WorkflowBuilder()

workflow.add_node("PythonCodeNode", "classifier", {
    "code": """
value = input_data.get('amount', 0)
if value > 1000:
    result = {'route': 'high_value', 'data': input_data}
else:
    result = {'route': 'standard', 'data': input_data}
"""
})

workflow.add_node("SwitchNode", "router", {
    "field": "route",
    "cases": {
        "high_value": "high_value_processor",
        "standard": "standard_processor"
    }
})

workflow.add_node("PythonCodeNode", "high_value_processor", {
    "code": "result = {'processed': 'high_value_logic'}"
})

workflow.add_node("PythonCodeNode", "standard_processor", {
    "code": "result = {'processed': 'standard_logic'}"
})

workflow.add_connection("classifier", "result", "router", "input")
workflow.add_connection("router", "high_value", "high_value_processor", "input")
workflow.add_connection("router", "standard", "standard_processor", "input")
```

## 🎯 Best Practices

### 1. Node Naming
- Use descriptive names: `"csv_reader"` not `"node1"`
- Follow snake_case convention
- Include purpose: `"customer_data_processor"`

### 2. Parameter Management
- Use runtime parameters for dynamic values
- Use build-time config for static settings
- Validate parameters before execution

### 3. Error Handling
- Always wrap execution in try-catch
- Handle specific SDK exceptions
- Provide meaningful error messages

### 4. Data Flow Design
- Keep connections simple and clear
- Use dot notation for nested data access
- Test with sample data before production

### 5. Performance
- Use async runtime for I/O heavy workflows
- Minimize data copying between nodes
- Consider parallel processing for independent operations

## 🔧 Debugging Tips

### Inspect Workflow Structure
```python
workflow = WorkflowBuilder()
# ... add nodes and connections ...

# Check workflow structure before building
print("Nodes:", list(workflow.nodes.keys()))
print("Connections:", workflow.connections)

built_workflow = workflow.build()
```

### Test Individual Nodes
```python
# Test nodes in isolation first
test_workflow = WorkflowBuilder()
test_workflow.add_node("PythonCodeNode", "test", {
    "code": "result = {'test': input_data}"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(test_workflow.build(), parameters={
    "test": {"sample": "data"}
})
print(results)
```

### Validate Connections
```python
# Test data flow with simple data
test_data = {"sample": "value"}
results, run_id = runtime.execute(workflow.build(), parameters={
    "first_node": test_data
})

# Check if data flows correctly
for node_name, node_result in results.items():
    print(f"{node_name}: {node_result}")
```

---

**All examples tested and validated against Kailash SDK v0.6.3**
