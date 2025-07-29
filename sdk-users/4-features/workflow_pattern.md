# Workflow Pattern Guide

This guide explains the correct pattern for creating and executing workflows in the Kailash SDK.

## Overview

The Kailash SDK supports two execution modes:
1. **Direct Node Execution**: Nodes run immediately with all parameters provided upfront
2. **Workflow Execution**: Nodes are connected in a graph and data flows through connections

## Direct Node Execution

In direct execution, you create nodes with all parameters and call `execute()` immediately.

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create reader with file path
reader = CSVReaderNode(file_path='input.csv')
result = reader.execute()

# Create writer with data already available
writer = CSVWriterNode(
    file_path='output.csv',
    data=result['data']  # Data provided at creation
)
writer_result = writer.execute()

```

### When to Use Direct Execution
- Simple operations
- Testing individual nodes
- Quick data transformations
- Prototyping

## Workflow Execution

In workflow execution, nodes are connected and data flows through the graph.

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Create workflow with string-based API
workflow = WorkflowBuilder()

# Add nodes using string-based API
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "input.csv"
})
workflow.add_node("CSVWriterNode", "writer", {
    "file_path": "output.csv"
})

# Connect nodes - data flows from reader to writer
workflow.add_connection("reader", "data", "writer", "data")

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

```

### When to Use Workflow Execution
- Complex data pipelines
- Multi-step processing
- Data flows between nodes
- Production systems
- Need execution tracking

## Key Concepts

### 1. Node Creation
- Direct: Create with all parameters
- Workflow: Create with only static parameters

### 2. Parameter Passing
- Direct: All parameters provided at creation
- Workflow: Dynamic parameters come through connections

### 3. Configuration
- Use configuration dict in `add_node()` for node parameters
- These provide node defaults but can be overridden by connection data

### 4. Connections
- Map source node outputs to target node inputs
- Data flows automatically during execution

## Complete Example

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Create custom filter function
def filter_customers(data: list, threshold: float) -> dict:
    filtered = [d for d in data if d['amount'] > threshold]
    return {'filtered_data': filtered, 'count': len(filtered)}

# Add nodes using string-based API
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "customers.csv"
})

# Add filter node using from_function
workflow.add_node("filter", PythonCodeNode.from_function(
    func=filter_customers,
    name="customer_filter"
))

workflow.add_node("CSVWriterNode", "writer", {
    "file_path": "filtered_customers.csv"
})

# Connect nodes
workflow.add_connection("reader", "data", "filter", "data")
workflow.add_connection("filter", "result", "writer", "data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

print(f"Filtered {results['filter']['count']} customers")

```

## Common Patterns

### 1. Fork Pattern
One node output feeds multiple downstream nodes:
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Add source node
workflow.add_node("CSVReaderNode", "source", {
    "file_path": "input.csv"
})

# Add multiple processing nodes
workflow.add_node("PythonCodeNode", "process_a", {
    "code": "result = {'type': 'A', 'data': input_data}"
})
workflow.add_node("PythonCodeNode", "process_b", {
    "code": "result = {'type': 'B', 'data': input_data}"
})

# Fork the data flow
workflow.add_connection("source", "data", "process_a", "input_data")
workflow.add_connection("source", "data", "process_b", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### 2. Join Pattern
Multiple nodes feed into one downstream node:
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Add source nodes
workflow.add_node("CSVReaderNode", "source_a", {
    "file_path": "data_a.csv"
})
workflow.add_node("CSVReaderNode", "source_b", {
    "file_path": "data_b.csv"
})

# Add merge node
workflow.add_node("MergeNode", "merger", {
    "strategy": "concatenate"
})

# Join the data flows
workflow.add_connection("source_a", "data", "merger", "input_a")
workflow.add_connection("source_b", "data", "merger", "input_b")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### 3. Sequential Pipeline
Data flows through multiple processing steps:
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = WorkflowBuilder()

# Add sequential processing steps
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "raw_data.csv"
})
workflow.add_node("PythonCodeNode", "cleaner", {
    "code": """
# Clean and validate data
cleaned = [row for row in input_data if row.get('value') is not None]
result = {'cleaned_data': cleaned, 'count': len(cleaned)}
"""
})
workflow.add_node("LLMAgentNode", "analyzer", {
    "model": "gpt-4",
    "prompt": "Analyze this data and provide insights"
})
workflow.add_node("CSVWriterNode", "writer", {
    "file_path": "analyzed_data.csv"
})

# Chain the processing steps
workflow.add_connection("reader", "data", "cleaner", "input_data")
workflow.add_connection("cleaner", "result", "analyzer", "data")
workflow.add_connection("analyzer", "result", "writer", "data")

# Execute pipeline
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Best Practices

1. **Use descriptive node IDs**: Make them meaningful for debugging
2. **Keep nodes focused**: Each node should do one thing well
3. **Handle errors gracefully**: Use try-catch in custom nodes
4. **Document connections**: Use clear mapping names
5. **Test nodes individually**: Before adding to workflows

## Common Pitfalls

1. **Providing data parameters to writer nodes**: Let data flow through connections
2. **Missing connections**: Ensure all required inputs are connected
3. **Circular dependencies**: Avoid nodes depending on each other
4. **Type mismatches**: Ensure output types match input requirements

## FAQ

**Q: Can I mix direct and workflow execution?**
A: Yes, you can test nodes directly before adding them to workflows.

**Q: How do I debug workflows?**
A: Use `LocalRuntime(debug=True)` for detailed logging.

**Q: Can I save and reload workflows?**
A: Yes, use `workflow.save()` and `Workflow.load()`.

**Q: How do I pass parameters to nodes in workflows?**
A: Use the `config` parameter in `add_node()` or through connections.

**Q: What happens if a node fails?**
A: The workflow stops and returns an error. Use error handling in custom nodes.

## See Also

- [Node Development Guide](node_development.md)
- [PythonCodeNode Guide](python_code_node.md)
- [Data Nodes Guide](data_nodes.md)
