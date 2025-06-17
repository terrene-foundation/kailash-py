# Quick Workflow Creation - Direct Pattern

## Basic Workflow Pattern
```python
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.code import PythonCodeNode

# 1. Create workflow
workflow = Workflow("wf-001", name="my_pipeline")

# 2. Add nodes with config parameters
workflow.add_node("reader", CSVReaderNode(), file_path="input.csv")
workflow.add_node("process", PythonCodeNode(
    name="process",
    code="result = {'count': len(data), 'items': data}",
    input_types={"data": list}
))
workflow.add_node("writer", CSVWriterNode(), file_path="output.csv")

# 3. Connect nodes
workflow.connect("reader", "process")
workflow.connect("process", "writer", mapping={"result.items": "data"})

# 4. Execute with runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

```

## Common Patterns

### Data Processing Pipeline
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode, JSONReaderNode, JSONWriterNode
from kailash.nodes.transform import DataTransformerNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("etl-001", name="ETL Pipeline")

# Extract
workflow.add_node("extract", CSVReaderNode(),
    file_path="sales.csv")

# Transform
workflow.add_node("transform", DataTransformerNode(),
    operations=[
        {"type": "filter", "condition": "amount > 100"},
        {"type": "map", "expression": "{'id': id, 'total': amount * 1.1}"}
    ])

# Load
workflow.add_node("load", JSONWriterNode(),
    file_path="processed.json")

# Connect nodes
workflow.connect("extract", "transform")
workflow.connect("transform", "load", mapping={"result": "data"})

```

### AI Integration Pipeline
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode, JSONReaderNode, JSONWriterNode
from kailash.nodes.transform import DataTransformerNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

workflow = Workflow("ai-001", name="AI Analysis")

# Read data
workflow.add_node("reader", JSONReaderNode(),
    file_path="reviews.json")

# Analyze with LLM
workflow.add_node("analyze", LLMAgentNode(),
    provider="openai",
    model="gpt-4",
    prompt="Analyze sentiment: {text}")

# Save results
workflow.add_node("save", JSONWriterNode(),
    file_path="sentiment.json")

# Connect nodes
workflow.connect("reader", "analyze", mapping={"data": "text"})
workflow.connect("analyze", "save", mapping={"result": "data"})

```

## Key Points
- Always use `LocalRuntime()` for execution
- Configuration params in `add_node()`, data flows through `connect()`
- Use dot notation for nested access: `"result.data"`
- PythonCodeNode needs `name` as first parameter

## Next Steps
- [Common Node Patterns](004-common-node-patterns.md) - Node examples
- [Connection Patterns](005-connection-patterns.md) - Data flow
- [Developer Guide](../../developer/02-workflows.md) - Complete guide
