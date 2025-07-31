# Execution Options

## Standard Execution Pattern
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

# Always use runtime for workflow execution
runtime = LocalRuntime()

# Basic execution (no parameter overrides)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Execution with parameter overrides
runtime = LocalRuntime()
results, run_id = runtime.execute(
    workflow,
    parameters={
        "reader": {"file_path": "custom.csv"},  # Override node config
        "filter": {"threshold": 100}            # Runtime parameter
    }
)

```

## Runtime Configuration Options

### Content-Aware Success Detection (v0.9.4+)

LocalRuntime now includes intelligent failure detection that analyzes node return values:

```python
# Default behavior - content-aware detection enabled
runtime = LocalRuntime()  # content_aware_success_detection=True by default

# Explicit configuration
runtime = LocalRuntime(content_aware_success_detection=True)

# Disable content-aware detection (legacy behavior)
runtime = LocalRuntime(content_aware_success_detection=False)
```

**How it works:**
- Analyzes node return values for failure patterns
- Detects `{"success": False, "error": "..."}` patterns
- Stops execution early when content failures are detected
- Maintains backward compatibility with exception-only detection

**Example failure detection:**
```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "failing_node", {
    "code": """
# This will be detected as a failure
result = {"success": False, "error": "Database connection failed"}
"""
})

runtime = LocalRuntime(content_aware_success_detection=True)
try:
    results, run_id = runtime.execute(workflow.build())
except Exception as e:
    print(f"Runtime detected content failure: {e}")
    # Will include detailed error information from the node result
```

**Benefits:**
- Earlier failure detection
- Better error reporting
- No breaking changes to existing code
- Compatible with DataFlow error patterns

## Parameters Structure
```python
# The 'parameters' dict maps node IDs to their parameter overrides
parameters = {
    "node_id_1": {
        "param1": "value1",
        "param2": 123
    },
    "node_id_2": {
        "param": "override_value"
    }
}

```

## Passing Initial Data to Workflows
```python
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.transform import DataTransformerNode

# Option 1: Source nodes (self-contained)
workflow.add_node("CSVReaderNode", "reader", {}))
# No external input needed

# Option 2: External data injection (flexible)
workflow.add_node("DataTransformerNode", "processor", {}))
runtime.execute(workflow, parameters={
    "processor": {"data": [1, 2, 3], "config": {...}}
})

# Option 3: Hybrid (source + override)
workflow.add_node("CSVReaderNode", "reader", {}), file_path="default.csv")
runtime.execute(workflow, parameters={
    "reader": {"file_path": "custom.csv"}  # Override at runtime
})

```

## Common Execution Mistakes
```python
# ❌ WRONG - Using wrong parameter name
runtime.execute(workflow, parameters={"data": [1, 2, 3]})  # Should be 'parameters', not 'inputs'

# ❌ WRONG - Passing as positional argument
runtime.execute(workflow, {"node": {"param": "value"}})  # Must use parameters=...

# ❌ WRONG - Wrong return value handling
results = runtime.execute(workflow.build())  # Returns tuple (results, run_id)
results, run_id = runtime.execute(workflow.build(), parameters={})  # Returns only results

```

## Access Results
```python
# Get output from specific node
node_output = results.get("node_id", {}).get("output_name")

# Get final results (from nodes with no outgoing connections)
final_results = results.get("_final_outputs", {})

```
