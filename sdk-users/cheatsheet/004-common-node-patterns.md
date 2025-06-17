# Common Node Patterns - Copy & Paste Templates

## Data I/O
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# CSV Reading
workflow = Workflow("example", name="Example")
workflow.add_node("reader", CSVReaderNode(),
    file_path="data.csv",
    delimiter=",",
    has_header=True
)

# JSON Writing
from kailash.nodes.data import JSONWriterNode
workflow = Workflow("example", name="Example")
workflow.add_node("writer", JSONWriterNode(),
    file_path="output.json",
    indent=2
)

# With data paths utility
from examples.utils.data_paths import get_input_data_path
workflow = Workflow("example", name="Example")
workflow.add_node("reader", CSVReaderNode(),
    file_path=str(get_input_data_path("data.csv"))
)

```

## PythonCodeNode
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# ✅ CORRECT: Direct statements, wrap output
workflow = Workflow("example", name="Example")
workflow.add_node("filter", PythonCodeNode(
    name="filter",
    code='''
filtered = [item for item in data if item.get('score', 0) > 0.8]
result = {'items': filtered, 'count': len(filtered)}
''',
    input_types={"data": list}
))

# Access nested output with dot notation
workflow = Workflow("example", name="Example")
workflow.connect("filter", "next_node", mapping={"result.items": "processed_data"})

```

## LLM Integration
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Basic LLM
workflow = Workflow("example", name="Example")
workflow.add_node("llm", LLMAgentNode(),
    provider="openai",
    model="gpt-4",
    temperature=0.7,
    prompt="Analyze this data: {data}"
)

# With system prompt
workflow = Workflow("example", name="Example")
workflow.add_node("analyst", LLMAgentNode(),
    provider="openai",
    model="gpt-4",
    system_prompt="You are a data analyst. Be concise.",
    prompt="Summarize trends in: {metrics}"
)

```

## Data Transformation
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

from kailash.nodes.transform import DataTransformerNode
workflow = Workflow("example", name="Example")
workflow.add_node("transform", DataTransformerNode(),
    operations=[
        {"type": "filter", "condition": "status == 'active'"},
        {"type": "map", "expression": "{'id': id, 'name': name.upper()}"},
        {"type": "sort", "key": "created_at", "reverse": True}
    ]
)

```

## Conditional Routing
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Switch node with conditions
workflow = Workflow("example", name="Example")
workflow.add_node("router", SwitchNode(),
    conditions=[
        {"output": "high", "expression": "score > 80"},
        {"output": "medium", "expression": "score > 50"},
        {"output": "low", "expression": "score <= 50"}
    ]
)

# Connect each output
workflow.connect("router", "high_processor", output_port="high")
workflow.connect("router", "medium_processor", output_port="medium")
workflow.connect("router", "low_processor", output_port="low")

```

## API Requests
```python
# Simple GET
workflow.add_node("api", HTTPRequestNode(),
    url="https://api.example.com/data",
    method="GET",
    headers={"Authorization": "Bearer token"}
)

# POST with data
workflow.add_node("post", HTTPRequestNode(),
    url="https://api.example.com/submit",
    method="POST",
    headers={"Content-Type": "application/json"},
    body={"key": "value"}
)

```

## Cycles (Advanced)
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Iterative processing with convergence
workflow = Workflow("example", name="Example")
workflow.add_node("convergence", PythonCodeNode(
    name="convergence",
    code='''
new_value = value * 0.9  # Example convergence calculation
converged = abs(new_value - value) < 0.01
result = {"value": new_value, "converged": converged}
''',
    input_types={"value": float}
))

# Create cycle
workflow.connect("convergence", "convergence", mapping={"result.value": "value"})

```

## Next Steps
- [Connection Patterns](005-connection-patterns.md) - Data flow patterns
- [Workflow Guide](../../developer/02-workflows.md) - Complete guide
- [Node Catalog](../nodes/comprehensive-node-catalog.md) - All nodes
