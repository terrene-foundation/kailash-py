# Quick Workflow Creation - Direct Pattern

## 🆕 Enhanced API Patterns (v0.6.6+)

### Auto ID Generation (New!)
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Auto-generate node IDs for rapid prototyping
reader_id = workflow.add_node("CSVReaderNode", {"file_path": "data.csv"})
processor_id = workflow.add_node("PythonCodeNode", {"code": "result = len(input_data)"})

# Use returned IDs for connections
workflow.add_connection(reader_id, "result", processor_id, "input_data")
```

### Flexible API Patterns
```python
# All these patterns work and are equivalent:

# 1. Current/Preferred Pattern
workflow.add_node("PythonCodeNode", "processor", {"code": "..."})

# 2. Keyword-Only Pattern
workflow.add_node(node_type="PythonCodeNode", node_id="processor", config={"code": "..."})

# 3. Mixed Pattern (common in existing code)
workflow.add_node("PythonCodeNode", node_id="processor", config={"code": "..."})

# 4. Auto ID (returns generated ID)
processor_id = workflow.add_node("PythonCodeNode", {"code": "..."})
```

## Basic Workflow Pattern
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# 1. Create workflow
workflow = WorkflowBuilder()

# 2. Add nodes with modern syntax
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = {'data': [{'name': 'item1'}, {'name': 'item2'}]}"
})

workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'count': len(input_data.get('data', [])), 'items': input_data.get('data', [])}"
})

workflow.add_node("PythonCodeNode", "output", {
    "code": "result = {'processed': f'Found {input_data.get(\"count\", 0)} items'}"
})

# 3. Connect nodes
workflow.add_connection("data_source", "result", "processor", "input_data")
workflow.add_connection("processor", "result", "output", "input_data")

# 4. Execute with runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Result: {results['output']['result']['processed']}")  # PythonCodeNode wraps outputs in 'result' key
```

## Common Patterns

### Data Processing Pipeline
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Extract (simulate data source)
workflow.add_node("PythonCodeNode", "extract", {
    "code": "result = {'data': [{'amount': 150}, {'amount': 50}, {'amount': 200}]}"
})

# Transform (filter and process data)
workflow.add_node("PythonCodeNode", "transform", {
    "code": """
# Filter and transform data
data = input_data.get('data', [])
filtered = [item for item in data if item.get('amount', 0) > 100]
transformed = [{'id': i, 'total': item['amount'] * 1.1} for i, item in enumerate(filtered)]
result = transformed
"""
})

# Load (save results)
workflow.add_node("PythonCodeNode", "load", {
    "code": "result = {'saved': len(input_data), 'status': 'complete'}"
})

# Connect nodes
workflow.add_connection("extract", "result", "transform", "input_data")
workflow.add_connection("transform", "result", "load", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Processed {results['load']['result']['saved']} items")  # Access via nested 'result' key
```

### AI Integration Pipeline
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Read data (simulate with PythonCodeNode)
workflow.add_node("PythonCodeNode", "reader", {
    "code": "result = {'reviews': [{'text': 'Great product!'}, {'text': 'Poor quality'}]}"
})

# Analyze with simulated LLM (avoid real API calls in examples)
workflow.add_node("PythonCodeNode", "analyze", {
    "code": """
reviews = input_data.get('reviews', [])
analyzed = []
for review in reviews:
    sentiment = 'positive' if 'great' in review.get('text', '').lower() else 'negative'
    analyzed.append({'text': review['text'], 'sentiment': sentiment})
result = {'analyzed_reviews': analyzed}
"""
})

# Save results (simulate)
workflow.add_node("PythonCodeNode", "save", {
    "code": "result = {'saved_count': len(input_data.get('analyzed_reviews', [])), 'status': 'saved'}"
})

# Connect nodes
workflow.add_connection("reader", "result", "analyze", "input_data")
workflow.add_connection("analyze", "result", "save", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Analyzed {results['save']['result']['saved_count']} reviews")  # PythonCodeNode outputs wrapped in 'result'
```

## Key Points
- Always use `LocalRuntime()` for execution
- Configuration params in `add_node()`, data flows through `add_connection()`
- Use dot notation for nested access: `"result.data"`
- PythonCodeNode wraps outputs in `result` key

## Next Steps
- [Common Node Patterns](004-common-node-patterns.md) - Node examples
- [Connection Patterns](005-connection-patterns.md) - Data flow
- [Developer Guide](../../developer/02-workflows.md) - Complete guide
