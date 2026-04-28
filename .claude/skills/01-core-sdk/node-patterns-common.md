---
name: node-patterns-common
description: "Common node usage patterns with copy-paste templates for CSV, JSON, PythonCode, LLM, HTTP, and data transformation. Use when asking 'node examples', 'how to use nodes', 'CSVReader', 'PythonCodeNode', 'LLMAgent', 'HTTPRequest', 'data transformation', 'common patterns', 'node templates', or 'workflow examples'."
---

# Common Node Patterns

Copy-paste ready templates for the most frequently used Kailash SDK nodes with working examples.

> **Skill Metadata**
> Category: `core-sdk`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **PythonCodeNode**: Custom Python logic, most flexible
- **CSVReaderNode**: Read CSV files
- **JSONWriterNode**: Write JSON output
- **HTTPRequestNode**: API calls (GET/POST)
- **PythonCodeNode**: Custom Python logic (including LLM API calls)
- **SwitchNode**: Conditional routing

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# PythonCodeNode - most common pattern
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Process data
processed = [item for item in data if item['score'] > 0.8]
result = {'filtered': processed, 'count': len(processed)}
"""
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Common Use Cases

- **Data I/O**: Read/write CSV, JSON, Excel files
- **Data Processing**: Filter, transform, aggregate data
- **API Integration**: HTTP requests to external services
- **AI/LLM**: Process data with AI models
- **Conditional Logic**: Route data based on conditions

## Node Patterns

### Pattern 1: CSV Reading and Writing

```python
workflow = WorkflowBuilder()

# Read CSV file
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "input.csv",
    "delimiter": ",",
    "has_header": True
})

# Process data
workflow.add_node("PythonCodeNode", "process", {
    "code": """
import pandas as pd  # requires: pip install pandas
df = pd.DataFrame(data)
df['total'] = df['quantity'] * df['price']
result = df.to_dict('records')
"""
})

# Write results
workflow.add_node("CSVWriterNode", "writer", {
    "file_path": "output.csv"
})

workflow.add_connection("reader", "data", "process", "data")
workflow.add_connection("process", "result", "writer", "data")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Pattern 2: PythonCodeNode with Filtering

```python
workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "source", {
    "code": """
result = [
    {'name': 'Alice', 'score': 0.9},
    {'name': 'Bob', 'score': 0.3},
    {'name': 'Charlie', 'score': 0.85}
]
"""
})

# Filter high scores
workflow.add_node("PythonCodeNode", "filter", {
    "code": """
filtered = [item for item in data if item.get('score', 0) > 0.8]
result = {'items': filtered, 'count': len(filtered)}
"""
})

workflow.add_connection("source", "result", "filter", "data")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Filtered {results['filter']['result']['count']} items")
```

### Pattern 3: HTTP API Requests

```python
workflow = WorkflowBuilder()

# GET request
workflow.add_node("HTTPRequestNode", "api_get", {
    "url": "https://api.example.com/data",
    "method": "GET",
    "headers": {"Authorization": "Bearer TOKEN"},
    "timeout": 30
})

# Process response
workflow.add_node("PythonCodeNode", "process", {
    "code": """
import json
data = json.loads(response) if isinstance(response, str) else response
result = {
    'items': data.get('items', []),
    'count': len(data.get('items', []))
}
"""
})

workflow.add_connection("api_get", "response", "process", "response")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Pattern 4: LLM Agent Integration

```python
workflow = WorkflowBuilder()

# Prepare data for LLM
workflow.add_node("PythonCodeNode", "prep", {
    "code": """
text = "Quarterly revenue increased by 15%."
result = {'text': text, 'task': 'analyze'}
"""
})

# LLM processing (use Kaizen agents for production; PythonCodeNode for quick prototyping)
workflow.add_node("PythonCodeNode", "llm", {
    "code": "import os; from openai import OpenAI; client = OpenAI(); resp = client.chat.completions.create(model=os.environ['LLM_MODEL'], messages=[{'role': 'system', 'content': 'You are a business analyst. Analyze the given text.'}, {'role': 'user', 'content': text}], temperature=0.1, max_tokens=200); result = {'response': resp.choices[0].message.content}",
    "input_variables": ["text"]
})

# Post-process
workflow.add_node("PythonCodeNode", "post", {
    "code": """
llm_response = llm_result.get('response', '')
result = {
    'analysis': llm_response,
    'confidence': 0.9
}
"""
})

workflow.add_connection("prep", "result.text", "llm", "prompt")
workflow.add_connection("llm", "result", "post", "llm_result")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Pattern 5: Conditional Routing with SwitchNode

```python
workflow = WorkflowBuilder()

# Data source
workflow.add_node("PythonCodeNode", "source", {
    "code": "result = {'score': 85, 'type': 'test'}"
})

# Router
workflow.add_node("SwitchNode", "router", {
    "condition_field": "score",
    "operator": ">",
    "value": 80
})

# High score handler
workflow.add_node("PythonCodeNode", "high_handler", {
    "code": "result = {'status': 'high_score', 'score': score}"
})

# Low score handler
workflow.add_node("PythonCodeNode", "low_handler", {
    "code": "result = {'status': 'low_score', 'score': score}"
})

workflow.add_connection("source", "result", "router", "data")
workflow.add_connection("router", "true_output", "high_handler", "score")
workflow.add_connection("router", "false_output", "low_handler", "score")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Pattern 6: Data Transformation

```python
workflow = WorkflowBuilder()

# Source data
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "users.csv"
})

# Transform
workflow.add_node("PythonCodeNode", "transform", {
    "code": """
import pandas as pd  # requires: pip install pandas
df = pd.DataFrame(data)
# Add calculated columns
df['full_name'] = df['first_name'] + ' ' + df['last_name']
df['age'] = 2024 - df['birth_year']
# Filter and sort
df = df[df['age'] >= 18].sort_values('age', ascending=False)
result = df.to_dict('records')
"""
})

# Output
workflow.add_node("JSONWriterNode", "output", {
    "file_path": "transformed.json",
    "indent": 2
})

workflow.add_connection("reader", "data", "transform", "data")
workflow.add_connection("transform", "result", "output", "data")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Common Mistakes

### ❌ Mistake 1: Wrong Result Access for PythonCodeNode

```python
# Wrong - Missing 'result' nesting
value = results['processor']['count']  # KeyError
```

### ✅ Fix: Use Correct Nesting

```python
# Correct - PythonCodeNode wraps output in 'result'
value = results['processor']['result']['count']  # ✓
```

### ❌ Mistake 2: Not Handling First Iteration in Cycles

```python
# Wrong - Assuming parameters exist
workflow.add_node("PythonCodeNode", "proc", {
    "code": "value = input_value + 1; result = {'value': value}"
})
```

### ✅ Fix: Use try/except for Cycles

```python
# Correct - Handle first iteration
workflow.add_node("PythonCodeNode", "proc", {
    "code": """
try:
    value = input_value
except NameError:
    value = 0  # First iteration default
result = {'value': value + 1}
"""
})
```

### ❌ Mistake 3: Incorrect Port Names in Connections

```python
# Wrong - Using wrong output port name
workflow.add_connection("csv_reader", "output", "processor", "input")
```

### ✅ Fix: Use Correct Port Names

```python
# Correct - CSVReaderNode outputs to 'data' port
workflow.add_connection("csv_reader", "data", "processor", "data")
```

## Related Patterns

- **For connections**: See [`connection-patterns`](#)
- **For parameter passing**: See [`param-passing-quick`](#)
- **For error handling**: See [`error-handling-patterns`](#)
- **For node selection**: See [`decide-node-for-task`](#)
- **Complete node catalog**: See [`nodes-quick-index`](#)

## When to Escalate to Subagent

Use `sdk-navigator` subagent when:

- Finding specific nodes for your use case
- Exploring all 110+ available nodes
- Understanding node capabilities

Use `pattern-expert` subagent when:

- Designing complex multi-node workflows
- Optimizing workflow patterns
- Creating reusable workflow components

## Documentation References

### Primary Sources

### Related Documentation

## Quick Tips

- 💡 **PythonCodeNode is your friend**: Use it for quick transformations and logic
- 💡 **Always wrap in 'result'**: PythonCodeNode expects `result = {...}`
- 💡 **Check port names**: Each node has specific input/output ports
- 💡 **Use pandas for data**: Install pandas (`pip install pandas`) and import in PythonCodeNode for data manipulation
- 💡 **Test incrementally**: Build workflows node by node, test each connection

## Version Notes

- **v0.9.25+**: AsyncLocalRuntime default for Docker/async
- **v0.9.20+**: String-based nodes recommended (all examples use this pattern)

## Keywords for Auto-Trigger

<!-- Trigger Keywords: node examples, how to use nodes, CSVReader, PythonCodeNode, LLMAgent, HTTPRequest, data transformation, common patterns, node templates, workflow examples, CSV patterns, JSON patterns, API patterns, LLM patterns, node usage -->
