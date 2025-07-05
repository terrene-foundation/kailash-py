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
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

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
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Create workflow
workflow = Workflow(name="Data Pipeline")

# Create nodes (writer doesn't need data yet)
reader = CSVReaderNode(file_path='input.csv')
writer = CSVWriterNode(file_path='output.csv')  # No data parameter

# Add nodes to workflow
workflow = Workflow("example", name="Example")
workflow.workflow.add_node(reader, node_id='reader')
workflow = Workflow("example", name="Example")
workflow.workflow.add_node(writer, node_id='writer')

# Connect nodes - data flows from reader to writer
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# Execute workflow
runtime = LocalRuntime()
runtime = LocalRuntime()
workflow.execute(workflow)

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
- Use `config` parameter in `add_node()` for runtime parameters
- These override node defaults but can still receive connection data

### 4. Connections
- Map source node outputs to target node inputs
- Data flows automatically during execution

## Complete Example

```python
from kailash.workflow import Workflow
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = Workflow(name="Customer Processing")

# Create nodes
reader = CSVReaderNode(file_path='customers.csv')

# Create custom filter node
def filter_customers(data: list, threshold: float) -> dict:
    filtered = [d for d in data if d['amount'] > threshold]
    return {'filtered_data': filtered, 'count': len(filtered)}

filter_node = PythonCodeNode.from_function(
    func=filter_customers,
    name="customer_filter"
)

writer = CSVWriterNode(file_path='filtered_customers.csv')

# Add nodes with configuration
workflow.add_node(reader, node_id='reader')
workflow.add_node(filter_node, node_id='filter', config={
    'threshold': 1000.0  # Configuration parameter
})
workflow.add_node(writer, node_id='writer')

# Connect nodes
workflow.connect('reader', 'filter', mapping={'data': 'data'})
workflow.connect('filter', 'writer', mapping={'filtered_data': 'data'})

# Execute
runtime = LocalRuntime(debug=True)
results, run_id = runtime.execute(workflow)

print(f"Filtered {results['filter']['count']} customers")

```

## Common Patterns

### 1. Fork Pattern
One node output feeds multiple downstream nodes:
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### 2. Join Pattern
Multiple nodes feed into one downstream node:
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### 3. Sequential Pipeline
Data flows through multiple processing steps:
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature
workflow = Workflow("example", name="Example")
workflow.  # Method signature

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
