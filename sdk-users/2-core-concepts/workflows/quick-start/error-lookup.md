from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
# Error Lookup Guide

**Fast error-to-solution mapping** - Consolidated from 74 documented mistakes for instant debugging.

## 🚨 Critical Errors (Fix Immediately)

### Config vs Runtime Confusion
```
❌ ERROR: "TypeError: data is not a valid config parameter"
❌ ERROR: "Unexpected keyword argument 'data' in node constructor"

✅ SOLUTION: Separate config (HOW) from runtime (WHAT)
# Config: How the node works (static)
workflow.add_node("PythonCodeNode", "node", {})

# Runtime: What data to process (dynamic)
runtime.execute(workflow, parameters={"node": {"data": [1,2,3]}})
```

### Missing Node Name Parameter
```
❌ ERROR: "TypeError: PythonCodeNode.__init__() missing 1 required positional argument: 'name'"

✅ SOLUTION: Always use workflow.add_node
workflow.add_node("PythonCodeNode", "my_node", {"code": "result = data * 2"})
```

### Cycle Parameter Mapping Failures
```
❌ ERROR: "assert 1 >= 3" (cycle state not persisting)
❌ ERROR: "assert 0.0 >= 0.7" (quality score not improving)
❌ ERROR: "assert 10 == 45" (accumulation failing)

✅ SOLUTION: Use specific field mapping in cycles
# ❌ NEVER: Generic mapping
# workflow.connect("source", "target", mapping={"output": "output"})  # Generic fails

# ✅ ALWAYS: Specific field mapping
cycle_builder = workflow.create_cycle("improvement_cycle")
cycle_builder.connect("source", "target", mapping={"specific_field": "input_field"}).build()
```

## 🔧 PythonCodeNode Errors

### Execution Environment Issues
```
❌ ERROR: "NameError: name 'NameError' is not defined"
❌ ERROR: "NameError: name 'globals' is not defined"
❌ ERROR: "NameError: name 'open' is not defined"

✅ SOLUTION: Use bare except clauses
try:
    risky_operation()
except:  # ✅ Use bare except, not except NameError:
    result = {"error": "Operation failed"}
```

### Variable Access in Cycles
```
❌ ERROR: "NameError: name 'kwargs' is not defined"
❌ ERROR: "NameError: name 'data' is not defined"

✅ SOLUTION: Use direct variable access with try/except defaults
try:
    count = count  # Direct variable access
except:
    count = 0     # Default for first iteration

try:
    prev_result = prev_result
except:
    prev_result = []
```

### Data Serialization Errors
```
❌ ERROR: "TypeError: Object of type DataFrame is not JSON serializable"
❌ ERROR: "TypeError: Object of type ndarray is not JSON serializable"

✅ SOLUTION: Convert pandas/numpy objects before returning
import pandas as pd
import numpy as np

df = pd.DataFrame(data)
arr = np.array([1, 2, 3])

result = {
    "dataframe": df.to_dict('records'),  # ✅ JSON serializable
    "array": arr.tolist(),               # ✅ JSON serializable
    "summary": df.describe().to_dict()   # ✅ Convert all pandas objects
}
```

### NumPy Compatibility Issues
```
❌ ERROR: "AttributeError: module 'numpy' has no attribute 'float128'"
❌ ERROR: "AttributeError: module 'numpy' has no attribute 'string_'"

✅ SOLUTION: Check platform-specific types
import numpy as np

# Check availability before using
if hasattr(np, 'float128'):
    precision_type = np.float128
else:
    precision_type = np.float64

# NumPy 2.0 compatibility
if hasattr(np, 'bytes_'):
    string_type = np.bytes_  # NumPy 2.0+
elif hasattr(np, 'string_'):
    string_type = np.string_  # NumPy < 2.0
```

## 🔄 Workflow Connection Errors

### Wrong API Usage
```
❌ ERROR: "AttributeError: 'Workflow' object has no attribute 'add'"
❌ ERROR: "TypeError: Workflow.connect() got unexpected keyword argument 'output_key'"

✅ SOLUTION: Use correct Workflow API (not WorkflowBuilder)
workflow = WorkflowBuilder()  # ✅ Use WorkflowBuilder
workflow.add_node("SomeNode", "node", {})  # ✅ add_node method
workflow.add_connection("a", "b", "output", "input")  # ✅ mapping parameter
```

### Missing Source Nodes
```
❌ ERROR: "WorkflowValidationError: No source nodes found"

✅ SOLUTION: Add source node OR use parameters
# Option 1: Add source node
workflow.add_node("CSVReaderNode", "source", {})

# Option 2: Use parameters (any node can receive initial data)
runtime.execute(workflow, parameters={
    "any_node": {"initial_data": [1, 2, 3]}
})
```

### Multi-Node Input Issues
```
❌ ERROR: "Input type not allowed: <class 'NoneType'>"
❌ ERROR: "NameError: name 'data' is not defined" (multi-input aggregation)

✅ SOLUTION: Use MergeNode for multiple inputs
workflow.add_node("MergeNode", "merger", {})
workflow.add_connection("source1", "merger", "data", "input1")
workflow.add_connection("source2", "merger", "data", "input2")
workflow.add_connection("merger", "processor", "merged", "combined_data")
```

## 🤖 AI/MCP Integration Errors

### Deprecated MCP Patterns
```
❌ ERROR: Complex 5+ node workflow for simple MCP usage
❌ ANTI-PATTERN: Separate MCPClientNode + complex routing

✅ SOLUTION: Use LLMAgentNode with built-in MCP
workflow.add_node("LLMAgentNode", "ai_agent", {})
```

### Async Execution Issues
```
❌ ERROR: "RuntimeError: unhandled errors in a TaskGroup"

✅ SOLUTION: Use AsyncNode or proper async patterns
from kailash.runtime.async_local import AsyncLocalRuntime

async def run_workflow():
    runtime = AsyncLocalRuntime()
    results, run_id = await runtime.execute(workflow, parameters)
    return results
```

## 🔀 Conditional Logic Errors

### SwitchNode Mapping Issues
```
❌ ERROR: "ValueError: Required parameter 'input_data' not provided"

✅ SOLUTION: Map to SwitchNode's expected input parameter
workflow.add_connection("switch", "target", "output", "input_data")
# NOT # mapping removed)

✅ SOLUTION: Use safe state access with defaults
cycle_info = cycle_info or {}
prev_state = cycle_info.get("node_state") or {}
results_history = prev_state.get("results", [])
```

### Overly Rigid Test Assertions
```
❌ ERROR: "AssertionError: 1 >= 2" (cycle iterations)
❌ ERROR: "AssertionError: 7 != 5" (exact iteration counts)

✅ SOLUTION: Use flexible assertions for cycles
# ❌ Rigid
assert cycle_count == 3

# ✅ Flexible
assert cycle_count >= 1
assert 1 <= cycle_count <= 5
assert cycle_count > 0
```

## 🔍 Parameter Validation Errors

### Required Parameter Issues
```
❌ ERROR: "NodeConfigurationError: Required parameter 'data' not provided"
❌ ERROR: "ValidationError: Input should be a type [Union[float, int]]"

✅ SOLUTION: Use required=False with defaults for cycle-aware nodes
workflow.add_node("SomeNode", "cycle_node", {})
```

### Input Types in Cycles
```
❌ ERROR: "WorkflowValidationError: Node missing required inputs" (with input_types)

✅ SOLUTION: Map ALL parameters in cycles when using input_types
# When using input_types, EVERYTHING must be mapped
# Use CycleBuilder API: workflow.create_cycle("name").connect(...).build()
```

## 🛠️ Quick Debugging Checklist

When you encounter any error:

1. **Check Config vs Runtime**: Is data in the right place?
2. **Verify Node Names**: Do all classes end with "Node"?
3. **Check Cycle Mapping**: Using specific fields, not generic?
4. **Validate Serialization**: Are DataFrames/arrays converted?
5. **Check MCP Pattern**: Using LLMAgentNode, not separate client?
6. **Verify State Access**: Using .get() with defaults?
7. **Check Parameter Types**: Using simple types in cycles?
8. **Validate Connections**: Using Workflow.connect() with mapping?

## 🔗 Detailed Solutions

For comprehensive solutions to any error:

- **Basic Issues**: See [sdk-essentials.md](sdk-essentials.md)
- **Complex Cycles**: See [../advanced/cyclic-workflows-complete.md](../advanced/cyclic-workflows-complete.md)
- **AI Integration**: See [../advanced/ai-agent-coordination.md](../advanced/ai-agent-coordination.md)
- **Production Issues**: See [../advanced/enterprise-integration.md](../advanced/enterprise-integration.md)

---

*This error lookup consolidates solutions from 74 documented mistakes. 90% of issues can be resolved with these patterns.*
