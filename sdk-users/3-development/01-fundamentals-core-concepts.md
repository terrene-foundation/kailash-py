# Core Concepts - Workflows and Nodes

*Essential workflow and node concepts*

## 🎯 Prerequisites
- Python 3.8+
- Kailash SDK installed (`pip install kailash`)
- Basic understanding of data processing workflows

## 📋 Core Concepts

### Workflows and Nodes
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# WorkflowBuilder creates workflows with correct API
workflow = WorkflowBuilder()

# Nodes are processing units that perform specific tasks
# All node classes end with "Node"
```

### Node Creation Patterns
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# CSV Reading
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "/data/input.csv",
    "has_header": True,
    "delimiter": ","
})

# Data Processing
workflow.add_node("PythonCodeNode", "processor", {
    "code": '''
# Process the input data
processed = [item for item in input_data if item.get('amount', 0) > 100]
result = {'processed_items': processed, 'count': len(processed)}
'''
})

# Connect nodes
workflow.add_connection("reader", "result", "processor", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## 🔧 Node Types

### Data Input/Output
- `CSVReaderNode`, `JSONReaderNode` - File reading
- `CSVWriterNode`, `JSONWriterNode` - File writing
- `SQLDatabaseNode` - Database operations

### Processing
- `PythonCodeNode` - Custom Python logic
- `FilterNode`, `Map`, `Sort` - Data transformations
- `LLMAgentNode` - AI processing

### Logic & Control
- `SwitchNode`, `MergeNode` - Conditional routing
- `WorkflowNode` - Sub-workflows

## ✅ Key Rules
- Use `WorkflowBuilder()` not `Workflow()`
- Connection syntax: `add_connection(from_node, from_output, to_node, to_input)`
- PythonCodeNode wraps outputs in `result` key
- Access nested data with dot notation: `"result.data"`

## 🔗 Next Steps
- [Parameter Passing](01-fundamentals-parameters.md) - Data flow patterns
- [Node Connections](01-fundamentals-connections.md) - Advanced routing
- [Best Practices](01-fundamentals-best-practices.md) - Code patterns
