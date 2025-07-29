# Connection Patterns - Data Flow Mapping

*Essential patterns for connecting workflow nodes with the modern WorkflowBuilder API*

## ⚡ Quick Reference

### 4-Parameter Connection Syntax (Required)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Modern WorkflowBuilder API - ALWAYS use 4 parameters
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = len(data)"})

# ✅ CORRECT: 4-parameter syntax
workflow.add_connection("reader", "data", "processor", "data")
#                      ^source ^source_port ^target ^target_port

# ❌ WRONG: 2-parameter syntax (deprecated)
# workflow.add_connection("reader", "result", "processor", "input")
```

### Connection Pattern Types
1. **Direct mapping**: `source_port` = `target_port`
2. **Explicit mapping**: Different port names
3. **Dot notation**: Access nested data structures
4. **Multi-output**: One source to multiple targets
5. **Multi-input**: Multiple sources to one target

## 📋 Basic Connection Patterns

### Pattern 1: Direct Data Flow
```python
# Same port names - most common pattern
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "input.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = len(data)"})
workflow.add_node("JSONWriterNode", "writer", {"file_path": "output.json"})

# Connect in sequence
workflow.add_connection("reader", "data", "processor", "data")
workflow.add_connection("processor", "result", "writer", "data")
```

### Pattern 2: Port Name Mapping
```python
# Different port names - explicit mapping
workflow = WorkflowBuilder()
workflow.add_node("HTTPRequestNode", "api", {"url": "https://api.example.com"})
workflow.add_node("LLMAgentNode", "analyzer", {"model": "gpt-4"})

# Map 'response' output to 'input_data' input
workflow.add_connection("api", "response", "analyzer", "input_data")
```

### Pattern 3: Dot Notation for Nested Data
```python
# Access nested fields in complex outputs
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "analyzer", {
    "model": "gpt-4",
    "prompt": "Analyze this data: {data}"
})
workflow.add_node("PythonCodeNode", "reporter", {
    "code": "result = f'Summary: {summary_data}'"
})

# Extract nested field from analyzer result
workflow.add_connection("analyzer", "result.summary", "reporter", "summary_data")
#                                 ^nested_field      ^target_port

# More complex nesting
workflow.add_connection("analyzer", "result.metrics.accuracy", "validator", "threshold")
```

## 🔀 Multi-Output Patterns

### Pattern 4: Conditional Routing with SwitchNode
```python
# Route data based on conditions
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("SwitchNode", "router", {
    "condition_field": "value",
    "operator": ">",
    "value": 100
})
workflow.add_node("PythonCodeNode", "high_handler", {"code": "result = f'High value: {data}'"})
workflow.add_node("PythonCodeNode", "low_handler", {"code": "result = f'Low value: {data}'"})

# Connect input to router
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

# Connect each output port
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
```

### Pattern 5: Fan-Out (One-to-Many)
```python
# Split data into multiple streams
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "splitter", {
    "code": """
# Split data into valid and invalid items
valid = [item for item in data if item.get('valid', True)]
invalid = [item for item in data if not item.get('valid', True)]
result = {'valid': valid, 'invalid': invalid}
"""
})
workflow.add_node("PythonCodeNode", "valid_processor", {"code": "result = f'Valid: {len(data)} items'"})
workflow.add_node("PythonCodeNode", "invalid_processor", {"code": "result = f'Invalid: {len(data)} items'"})

# Input connection
workflow.add_connection("reader", "data", "splitter", "data")

# Fan-out with dot notation
workflow.add_connection("splitter", "result.valid", "valid_processor", "data")
workflow.add_connection("splitter", "result.invalid", "invalid_processor", "data")
```

## 🔄 Multi-Input Patterns

### Pattern 6: Fan-In with MergeNode
```python
# Combine multiple data sources
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "source1", {"file_path": "data1.csv"})
workflow.add_node("JSONReaderNode", "source2", {"file_path": "data2.json"})
workflow.add_node("HTTPRequestNode", "source3", {"url": "https://api.example.com"})
workflow.add_node("MergeNode", "merger", {})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = f'Combined {len(data)} items'"})

# Connect all sources to merger
workflow.add_connection("source1", "data", "merger", "input1")
workflow.add_connection("source2", "data", "merger", "input2")
workflow.add_connection("source3", "response", "merger", "input3")

# Process merged data
workflow.add_connection("merger", "result", "processor", "data")
```

### Pattern 7: Custom Multi-Input Processing
```python
# Process multiple inputs with custom logic
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "source1", {"file_path": "customers.csv"})
workflow.add_node("CSVReaderNode", "source2", {"file_path": "orders.csv"})
workflow.add_node("PythonCodeNode", "combiner", {
    "code": """
# Custom multi-input processing
customers = data1 if data1 else []
orders = data2 if data2 else []

# Join data
result = {
    'customers': len(customers),
    'orders': len(orders),
    'combined': customers + orders
}
"""
})
workflow.add_node("JSONWriterNode", "output", {"file_path": "combined.json"})

# Connect multiple inputs to same node
workflow.add_connection("source1", "data", "combiner", "data1")
workflow.add_connection("source2", "data", "combiner", "data2")
workflow.add_connection("combiner", "result", "output", "data")
```

## 🎯 Advanced Connection Patterns

### Pattern 8: Complex Nested Data Extraction
```python
# Extract multiple nested fields
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "analyzer", {
    "model": "gpt-4",
    "prompt": "Analyze this data and provide metrics: {data}"
})
workflow.add_node("PythonCodeNode", "reporter", {
    "code": """
# Process extracted metrics
report = {
    'accuracy': accuracy,
    'summary': summary,
    'confidence': confidence,
    'timestamp': import_time().time()
}
result = report
"""
})

# Multiple nested field connections
workflow.add_connection("analyzer", "result.metrics.accuracy", "reporter", "accuracy")
workflow.add_connection("analyzer", "result.summary", "reporter", "summary")
workflow.add_connection("analyzer", "result.confidence", "reporter", "confidence")
```

### Pattern 9: Parallel Processing (Broadcast)
```python
# Send same data to multiple processors
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = {'processed': len(data), 'data': data}"})

# Multiple parallel handlers
workflow.add_node("PythonCodeNode", "logger", {"code": "result = f'Logged {len(data)} items'"})
workflow.add_node("JSONWriterNode", "storer", {"file_path": "stored.json"})
workflow.add_node("HTTPRequestNode", "notifier", {
    "url": "https://api.example.com/notify",
    "method": "POST"
})

# Initial processing
workflow.add_connection("reader", "data", "processor", "data")

# Broadcast to all handlers
workflow.add_connection("processor", "result", "logger", "data")
workflow.add_connection("processor", "result", "storer", "data")
workflow.add_connection("processor", "result", "notifier", "data")
```

## 🚨 Common Connection Mistakes

### ❌ Wrong: 2-Parameter Connections
```python
# DEPRECATED - Will fail
workflow.add_connection("source", "result", "target", "input")
workflow.add_connection("reader", "result", "processor", "input")
```

### ✅ Correct: 4-Parameter Connections
```python
# REQUIRED - Always use 4 parameters
workflow.add_connection("source", "data", "target", "input")
workflow.add_connection("reader", "data", "processor", "data")
```

### ❌ Wrong: Missing Port Names
```python
# Will cause runtime errors
workflow.add_connection("source", "", "target", "input")  # Empty port
workflow.add_connection("source", "nonexistent", "target", "input")  # Wrong port
```

### ✅ Correct: Valid Port Names
```python
# Check node documentation for valid ports
workflow.add_connection("csv_reader", "data", "processor", "data")
workflow.add_connection("http_request", "response", "analyzer", "input_data")
```

## 🎯 Best Practices

1. **Always use 4-parameter syntax**: `add_connection(source, source_port, target, target_port)`
2. **Check port names**: Verify input/output ports exist on nodes
3. **Use dot notation for nested data**: `"result.metrics.accuracy"`
4. **Plan data flow**: Map out connections before coding
5. **Test connections**: Validate data flows correctly between nodes

## 📚 Related Patterns

- **[Workflow Creation](003-quick-workflow-creation.md)** - Build workflows
- **[Error Handling](007-error-handling.md)** - Handle failures
- **[Parameter Passing](../developer/11-parameter-passing-guide.md)** - Advanced parameter flow
- **[Developer Guide](../../developer/02-workflows.md)** - Deep dive workflows
