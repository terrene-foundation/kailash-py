# Connection Patterns - Data Flow Mapping

## Basic Patterns

### Auto-mapping (matching names)
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

# When output and input names match, mapping is automatic
workflow = Workflow("example", name="Example")
workflow.connect("reader", "processor")  # data -> data

```

### Explicit mapping
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

# Map specific outputs to inputs
workflow = Workflow("example", name="Example")
workflow.connect("source", "target", mapping={"output_field": "input_field"})

```

### Dot notation for nested data
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

# Access nested fields in node outputs
workflow = Workflow("example", name="Example")
workflow.connect("analyzer", "reporter", mapping={"result.summary": "summary_data"})

```

## Multi-Output Patterns

### SwitchNode routing
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

# Each condition creates a separate output
workflow = Workflow("example", name="Example")
workflow.add_node("router", SwitchNode(),
    conditions=[
        {"output": "high", "expression": "value > 100"},
        {"output": "low", "expression": "value <= 100"}
    ]
)

# Connect each output separately
workflow.connect("router", "high_handler", output_port="high")
workflow.connect("router", "low_handler", output_port="low")

```

### Multiple data streams
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

# Node with multiple outputs
workflow = Workflow("example", name="Example")
workflow.add_node("splitter", PythonCodeNode(
    name="splitter",
    code='''
valid = [item for item in data if item.get('valid')]
invalid = [item for item in data if not item.get('valid')]
result = {'valid': valid, 'invalid': invalid}
''',
    input_types={"data": list}
))

# Route each stream
workflow.connect("splitter", "valid_processor", mapping={"result.valid": "data"})
workflow.connect("splitter", "invalid_processor", mapping={"result.invalid": "data"})

```

## Multi-Input Patterns

### MergeNode
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

# Combine multiple data sources
workflow = Workflow("example", name="Example")
workflow.add_node("merge", MergeNode())

# Connect multiple sources
workflow.connect("source1", "merge", mapping={"data": "input1"})
workflow.connect("source2", "merge", mapping={"data": "input2"})
workflow.connect("source3", "merge", mapping={"data": "input3"})

```

### PythonCodeNode with multiple inputs
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

workflow.add_node("combiner", PythonCodeNode(
    name="combiner",
    code="result = {'combined': list(data1) + list(data2)}",
    input_types={"data1": list, "data2": list}
))

# Map each input
workflow.connect("source1", "combiner", mapping={"result": "data1"})
workflow.connect("source2", "combiner", mapping={"result": "data2"})

```

## Advanced Patterns

### Partial mapping
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

# Map only specific fields
workflow = Workflow("example", name="Example")
workflow.connect("analyzer", "reporter", mapping={
    "result.metrics.accuracy": "accuracy",
    "result.summary": "summary"
})

```

### Fan-out pattern
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

# One output to multiple nodes
for handler in ["log", "store", "notify"]:
    workflow.connect("processor", handler, mapping={"result": "data"})

```

## Next Steps
- [Quick Creation](003-quick-workflow-creation.md) - Build workflows
- [Error Handling](007-error-handling.md) - Handle failures
- [Developer Guide](../../developer/02-workflows.md) - Deep dive
