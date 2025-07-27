# Quick Tips - Essential Knowledge

## Naming Conventions
- **Node classes end with "Node"**: `CSVReaderNode` ✓, `CSVReader` ✗
- **Methods use snake_case**: `add_node()` ✓, `addNode()` ✗
- **Config keys use underscores**: `file_path` ✓, `filePath` ✗
- **Workflow IDs use hyphens**: `"my-workflow-001"` ✓

## Workflow Basics
- **Use WorkflowBuilder**: `workflow = WorkflowBuilder()`
- **Use LocalRuntime**: `runtime.execute()` returns `(results, run_id)`
- **Connect nodes properly**: `workflow.add_connection(from_node, output, to_node, input)`
- **Wrap outputs in dict**: `result = {'data': processed}`
- **Always call .build()**: `runtime.execute(workflow.build())`
- **Use string-based API**: `workflow.add_node("NodeType", "id", config)`

## Common Pitfalls
- **Set attributes BEFORE super().__init__()** in custom nodes
- **NodeParameter uses basic types**: `type=list` not `List[str]`
- **Cycles need ALL parameters mapped**: Including constants
- **Middleware via create_gateway()**: Not manual FastAPI

## Performance Tips
- **Use batch operations**: Process multiple items at once
- **Enable async for I/O**: `LocalRuntime(enable_async=True)`
- **Cache expensive operations**: Use `IntelligentCacheNode`
- **Profile with monitoring**: `enable_monitoring=True`

## Security Best Practices
- **Never hardcode secrets**: Use environment variables
- **Validate file paths**: Use `validate_file_path()`
- **Enable audit logging**: Track all operations
- **Use AccessControlledRuntime**: For multi-tenant apps

## Debugging Techniques
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

# Enable verbose logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Inspect workflow structure
workflow = WorkflowBuilder()
built_workflow = workflow.build()
built_workflow.to_dict()

# Check node outputs
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
for node_id, output in results.items():
    print(f"{node_id}: {output}")

# Validate before execution
try:
workflow = WorkflowBuilder()
built_workflow = workflow.build()
built_workflow.validate()
except Exception as e:
    print(f"Validation error: {e}")

```

## Quick Patterns
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

# Read → Process → Write
# Create quick CSV-to-JSON converter
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "read", {})
workflow.add_node("PythonCodeNode", "proc", {
    "code": "result = {'converted': input_data}"
})
workflow.add_node("JSONWriterNode", "write", {})
workflow.add_connection("read", "result", "proc", "input")
workflow.add_connection("proc", "result", "write", "input")

# Quick execution
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Processed {len(results)} nodes")

```

## Next Steps
- [Common Mistakes](018-common-mistakes-to-avoid.md) - What to avoid
- [Troubleshooting](../../developer/05-troubleshooting.md) - Fix errors
- [Node Catalog](../nodes/comprehensive-node-catalog.md) - Find nodes
