# 🚀 Quickstart - Start Here!

Welcome to Kailash SDK! This is your starting point for building workflow automation.

## 📋 Getting Started in 3 Steps

### 1. Installation

```bash
pip install kailash
```

### 2. Your First Workflow

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create a simple workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "hello", {
    "code": "result = {'message': 'Hello, Kailash!'}"
})

# Execute it
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(results["hello"]["result"]["message"])  # "Hello, Kailash!"
```

### 3. Common Patterns

#### Data Processing Pipeline

```python
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "read", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "process", {"code": "result = len(data)"})
workflow.add_node("CSVWriterNode", "write", {"file_path": "output.csv"})

workflow.add_connection("read", "data", "process", "data")
workflow.add_connection("process", "result", "write", "data")
```

#### AI Analysis

```python
import os

workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "analyzer", {
    "model": os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o"),
    "prompt": "Analyze this data: {data}"
})
```

## 📚 Next Steps

- **Learn Concepts**: Head to [2-core-concepts/](../2-core-concepts/) to understand nodes and workflows
- **Build Apps**: Check [3-development/](../3-development/) for complete development guides
- **See Examples**: Browse [examples/](../examples/) for real-world workflows

## ⚠️ Common Mistakes to Avoid

1. **Wrong API**: Use string-based node creation, not instances

   ```python
   # ❌ DON'T
   workflow.add_node("CSVReaderNode", "reader", {}))

   # ✅ DO
   workflow.add_node("CSVReaderNode", "reader", {})
   ```

2. **Wrong Connections**: Use 4-parameter syntax

   ```python
   # ❌ DON'T
   workflow.add_connection("source", "result", "target", "input")

   # ✅ DO
   workflow.add_connection("source", "output", "target", "input")
   ```

3. **Missing Build**: Always build before execution

   ```python
   # ❌ DON'T
   runtime.execute(workflow.build())

   # ✅ DO
   runtime.execute(workflow.build())
   ```

## 🔗 Quick Links

- [Installation Guide](installation.md)
- [First Workflow Tutorial](first-workflow.md)
- [Common Patterns](common-patterns.md)
- [Node Selection Guide](../2-core-concepts/nodes/node-selection-guide.md)
- [Troubleshooting](../3-development/troubleshooting.md)
