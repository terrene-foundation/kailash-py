# Common Node Patterns - Copy & Paste Templates

## Data I/O
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# CSV Reading
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "data.csv",
    "delimiter": ",",
    "has_header": True
})

# JSON Writing
workflow.add_node("JSONWriterNode", "writer", {
    "file_path": "output.json",
    "indent": 2
})

# Connect them
workflow.add_connection("reader", "data", "writer", "data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## PythonCodeNode
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = [{'score': 0.9}, {'score': 0.3}, {'score': 0.85}]"
})

# Filter with wrapped output
workflow.add_node("PythonCodeNode", "filter", {
    "code": '''
filtered = [item for item in input_data if item.get('score', 0) > 0.8]
result = {'items': filtered, 'count': len(filtered)}
'''
})

# Connect with proper syntax
workflow.add_connection("data_source", "result", "filter", "input_data")

# Access nested output with dot notation
workflow.add_connection("filter", "result.items", "next_node", "processed_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## LLM Integration
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = {'text': 'This is sample data to analyze'}"
})

# Simulate LLM analysis (avoid real API calls in examples)
workflow.add_node("PythonCodeNode", "llm_analysis", {
    "code": '''
text = input_data.get('text', '')
# Simulate LLM analysis
analysis = f"Analysis of '{text}': This appears to be informational text."
result = {'analysis': analysis, 'confidence': 0.85}
'''
})

# Connect nodes
workflow.add_connection("data_source", "result", "llm_analysis", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Analysis: {results['llm_analysis']['result']['analysis']}")
```

## Data Transformation
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.transform import FilterNode

workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = [{'status': 'active', 'id': 1, 'name': 'alice'}, {'status': 'inactive', 'id': 2, 'name': 'bob'}]"
})

# Filter data
workflow.add_node("FilterNode", "filter", {
    "field": "status",
    "operator": "==",
    "value": "active"
})

# Transform filtered data
workflow.add_node("PythonCodeNode", "transform", {
    "code": '''
transformed = []
for item in input_data:
    transformed.append({'id': item['id'], 'name': item['name'].upper()})
result = transformed
'''
})

# Connect nodes
workflow.add_connection("data_source", "result", "filter", "data")
workflow.add_connection("filter", "filtered_data", "transform", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Conditional Routing
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "data_source", {
    "code": "result = {'score': 85}"
})

# Router with conditional logic
workflow.add_node("PythonCodeNode", "router", {
    "code": '''
score = input_data.get('score', 0)
if score > 80:
    category = 'high'
elif score > 50:
    category = 'medium'
else:
    category = 'low'
result = {'category': category, 'score': score}
'''
})

# Processors for each category
workflow.add_node("PythonCodeNode", "high_processor", {
    "code": "result = {'processed': f'High score processing: {input_data.get(\"score\", 0)}'}"
})

workflow.add_node("PythonCodeNode", "medium_processor", {
    "code": "result = {'processed': f'Medium score processing: {input_data.get(\"score\", 0)}'}"
})

# Connect nodes
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## HTTPRequestNode - Real API Calls
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# HTTP GET request
workflow.add_node("HTTPRequestNode", "api_get", {
    "url": "https://httpbin.org/get",
    "method": "GET",
    "headers": {"User-Agent": "Kailash-SDK/0.6.0"},
    "timeout": 30
})

# HTTP POST request
workflow.add_node("HTTPRequestNode", "api_post", {
    "url": "https://httpbin.org/post",
    "method": "POST",
    "headers": {"Content-Type": "application/json"},
    "json_data": {"key": "value", "timestamp": "2024-01-01"},
    "timeout": 30
})

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"GET Status: {results['api_get']['result']['status_code']}")
print(f"POST Status: {results['api_post']['result']['status_code']}")
```

## LLMAgentNode - AI Integration
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Data source for LLM processing
workflow.add_node("PythonCodeNode", "data_prep", {
    "code": '''
text = "The quarterly sales report shows 15% growth in revenue."
result = {"text": text, "task": "analyze"}
'''
})

# LLM Agent processing
workflow.add_node("LLMAgentNode", "llm_agent", {
    "model": "gpt-3.5-turbo",
    "system_prompt": "You are a business analyst. Analyze the given text and extract key insights.",
    "temperature": 0.1,
    "max_tokens": 200
})

# Post-process LLM output
workflow.add_node("PythonCodeNode", "post_process", {
    "code": '''
llm_response = input_data.get("response", "")
result = {
    "analysis": llm_response,
    "processed_at": "2024-01-01T10:00:00Z",
    "confidence": 0.9
}
'''
})

# Connect nodes
workflow.add_connection("data_prep", "result.text", "llm_agent", "prompt")
workflow.add_connection("llm_agent", "result", "post_process", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## API Requests (Simulated)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Simple GET (simulated)
workflow.add_node("PythonCodeNode", "api_get", {
    "code": '''
# Simulate API GET response
result = {
    'status': 200,
    'data': {'message': 'GET response simulation'},
    'headers': {'Content-Type': 'application/json'}
}
'''
})

# POST with data (simulated)
workflow.add_node("PythonCodeNode", "api_post", {
    "code": '''
# Simulate API POST response
result = {
    'status': 201,
    'data': {'message': 'POST successful', 'id': 12345},
    'headers': {'Content-Type': 'application/json'}
}
'''
})

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Cycles (Advanced)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Initial value
workflow.add_node("PythonCodeNode", "initial", {
    "code": "result = {'value': 1.0, 'iteration': 0}"
})

# Iterative processing with convergence check
workflow.add_node("PythonCodeNode", "convergence", {
    "code": '''
value = input_data.get('value', 1.0)
iteration = input_data.get('iteration', 0)
new_value = value * 0.9  # Example convergence calculation
converged = abs(new_value - value) < 0.01 or iteration > 10
result = {
    "value": new_value,
    "converged": converged,
    "iteration": iteration + 1
}
'''
})

# Connect nodes
workflow.add_connection("initial", "result", "convergence", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Final value: {results['convergence']['result']['value']}")
```

## Next Steps
- [Connection Patterns](005-connection-patterns.md) - Data flow patterns
- [Workflow Guide](../../developer/02-workflows.md) - Complete guide
- [Node Catalog](../nodes/comprehensive-node-catalog.md) - All nodes
