# Code Execution Nodes

**Module**: `kailash.nodes.code`
**Last Updated**: 2025-01-06

This document covers code execution nodes including Python code execution and MCP tool integration.

## Table of Contents
- [Python Code Execution](#python-code-execution)
- [PythonCodeNode Usage Guide](#pythoncodenode-usage-guide)
- [MCP Tool Nodes](#mcp-tool-nodes)

## Python Code Execution

### PythonCodeNode Dual Execution Model

PythonCodeNode supports **two distinct execution models** designed for different security and usability needs:

#### 1. **Sandboxed String Execution** (Security-First)
- **Purpose**: Execute arbitrary Python code strings in a controlled environment
- **Security**: Restricted imports, controlled environment, timeout enforcement
- **Use Case**: User-provided code, dynamic code generation, simple operations
- **Module Restrictions**: Only whitelisted modules (`math`, `json`, `datetime`, `pandas`, `numpy`, `hashlib`, etc.)

```python
# Sandboxed execution - restricted but safe
node = PythonCodeNode(
    node_id="secure_calc",
    name="Secure Calculator",
    code="result = sum(data) * 1.1",  # String code
    timeout=30  # Automatic timeout
)
```

#### 2. **Trusted Function Execution** (Developer-Friendly)
- **Purpose**: Execute pre-defined Python functions with full capabilities
- **Security**: Full Python environment access, developer-controlled
- **Use Case**: Complex business logic, IDE development, multi-line code
- **Module Access**: Full Python environment (developer responsibility)

```python
# Trusted execution - full capabilities
def complex_processor(data, threshold=0.5):
    """Complex business logic with full Python access."""
    import requests  # Any module available
    filtered = [x for x in data if x > threshold]
    return {"processed": filtered, "count": len(filtered)}

node = PythonCodeNode.from_function(complex_processor)
```

### Security Rationale

**Why Two Models?**
1. **String code = Untrusted**: Assumes code comes from users, APIs, or dynamic sources
2. **Function code = Trusted**: Assumes code is written by developers and reviewed
3. **Graduated Security**: Different security postures for different trust levels
4. **Developer Experience**: Full IDE support for trusted code, restrictions for untrusted

### PythonCodeNode
- **Module**: `kailash.nodes.code.python`
- **Purpose**: Execute Python code with dual security model
- **Parameters**:
  - `code`: Python code string (sandboxed execution)
  - `imports`: Required imports (for sandboxed mode)
  - `timeout`: Execution timeout (both modes)
- **Security**: Dual model - sandboxed strings vs trusted functions
- **Example**:
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

  node = PythonCodeNode(
      config={
          "code": "result = sum(data)",
          "imports": []
      }
  )

  ```

## PythonCodeNode Usage Guide

### Overview

PythonCodeNode allows execution of custom Python code within Kailash workflows. This guide covers correct usage patterns and common pitfalls.

### Constructor Patterns

#### Basic Constructor
```python
from kailash.nodes.code.python import PythonCodeNode

# ✅ CORRECT: Always include name parameter first
node = PythonCodeNode(
    name="processor",           # Required first parameter
    code="result = value * 2"   # Raw Python code
)

# ❌ WRONG: Missing name parameter
node = PythonCodeNode(code="result = value * 2")  # TypeError!

```

#### With Type Hints
```python
node = PythonCodeNode(
    name="calculator",
    code="result = a + b",
    input_types={"a": int, "b": int},  # Helps with validation
    output_type=int
)

```

### Code Format Patterns

#### ✅ Correct: Raw Python Statements
```python
python_code = '''
# Direct variable assignments
value = input_value * 2
quality = len(data) / total_items if total_items > 0 else 0
converged = quality >= 0.8

# Create result dictionary
result = {
    "processed_value": value,
    "quality_score": quality,
    "converged": converged
}
'''

node = PythonCodeNode(name="processor", code=python_code)

```

#### ❌ Wrong: Function Definitions
```python
# This will NOT work - returns function object, doesn't execute
python_code = '''
def main(**kwargs):
    return {"result": kwargs.get("value", 0) * 2}
'''

```

### Variable Access Patterns

#### ✅ Correct: Direct Variable Access
```python
python_code = '''
# Variables are injected directly into execution namespace
try:
    value = value  # Use parameter if provided
except NameError:
    value = 0      # Default value

result = {"doubled": value * 2}
'''

```

#### ❌ Wrong: kwargs Access
```python
# This will NOT work - kwargs not available
python_code = '''
value = kwargs.get("value", 0)  # NameError: name 'kwargs' is not defined
'''

```

### Cycle Usage Patterns

#### Basic Cycle with PythonCodeNode
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Iterative improvement code
python_code = '''
# Handle missing variables gracefully
try:
    current_value = current_value
except NameError:
    current_value = 0

try:
    target = target
except NameError:
    target = 100

# Improve towards target
if current_value < target:
    new_value = current_value + (target - current_value) * 0.2
else:
    new_value = current_value

# Check convergence
converged = abs(new_value - target) < 1.0

result = {
    "current_value": new_value,
    "target": target,
    "converged": converged
}
'''

workflow.add_node("PythonCodeNode", "improver", {"code": python_code})

# Build workflow FIRST, then create cycle
built_workflow = workflow.build()

# ✅ CRITICAL: Include mapping for data flow between iterations with "result." prefix
cycle_builder = built_workflow.create_cycle("improvement_cycle")
cycle_builder.connect("improver", "improver", mapping={
    "result.current_value": "current_value",
    "result.target": "target",
    "result.converged": "converged"
}).max_iterations(10).converge_when("converged == True").build()

runtime = LocalRuntime()
results, run_id = runtime.execute(built_workflow, parameters={
    "improver": {"current_value": 10, "target": 50}
})

```

#### Complex State Management
```python
python_code = '''
# Access previous iteration state
try:
    history = history
except NameError:
    history = []

try:
    data = data
except NameError:
    data = []

# Process current data
processed = [x * 2 for x in data]

# Update history
new_history = history + [len(processed)]
if len(new_history) > 5:  # Keep only recent history
    new_history = new_history[-5:]

# Check stability
converged = len(new_history) >= 3 and all(
    abs(new_history[-1] - h) < 0.1 for h in new_history[-3:]
)

result = {
    "processed_data": processed,
    "history": new_history,
    "converged": converged
}
'''

```

### Result Structure Patterns

#### PythonCodeNode Return Format
```python
# When using raw code, the `result` variable becomes the output
python_code = '''
result = {"value": 42, "status": "complete"}
'''

# Output will be: {"value": 42, "status": "complete"}
# Access as: final_output["value"], final_output["status"]

```

#### Convergence Check Format
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

# ✅ CORRECT: Use direct field names from result
workflow = WorkflowBuilder()
workflow.add_connection("source", "converged", "target", "input")  # Direct field name

# ❌ WRONG: Nested path access
workflow = WorkflowBuilder()
workflow.add_connection("source", "result.converged", "target", "input")  # Will fail

```

### Common Mistakes and Solutions

#### 1. Constructor Error
```python
# ❌ ERROR: TypeError: missing required positional argument 'name'
node = PythonCodeNode(code="result = 42")

# ✅ FIX: Include name parameter
node = PythonCodeNode(name="calculator", code="result = 42")

```

#### 2. Variable Scope Error
```python
# ❌ ERROR: NameError: name 'kwargs' is not defined
python_code = '''
value = kwargs.get("input", 0)
'''

# ✅ FIX: Use direct variable access with try/except
python_code = '''
try:
    value = input
except NameError:
    value = 0
'''

```

#### 3. Cycle Not Iterating
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

# ❌ ERROR: Cycle runs only once, no data flow
workflow = WorkflowBuilder()
# Workflow setup goes here  # Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# ✅ FIX: Include mapping for data flow
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

#### 4. Convergence Check Failure
```python
# ❌ ERROR: Expression evaluation failed: name 'converged' is not defined
convergence_check="result.converged == True"

# ✅ FIX: Use direct field names
convergence_check="converged == True"

```

### Testing Patterns

#### Debug Result Structure
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

# Always debug the actual result structure first
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Result keys: {list(results['node_name'].keys())}")
print(f"Sample values: {results['node_name']}")

```

#### Relaxed Cycle Assertions
```python
# ✅ GOOD: Allow for early convergence
assert final_output["iteration_count"] >= 1

# ❌ RIGID: May fail if cycle converges early
assert final_output["iteration_count"] == 5

```

### Best Practices

1. **Always include name parameter** in constructor
2. **Use raw Python statements**, not function definitions
3. **Handle missing variables** with try/except blocks
4. **Include mapping parameter** for cycle connections
5. **Use direct field names** in convergence checks
6. **Debug result structure** before writing assertions
7. **Use relaxed assertions** for iteration counts in tests

### Related Documentation

- [Cyclic Workflows Basics](../cheatsheet/019-cyclic-workflows-basics.md)
- [Cycle Debugging](../cheatsheet/022-cycle-debugging-troubleshooting.md)
- [Common Node Patterns](../cheatsheet/004-common-node-patterns.md)

## MCP Tool Nodes

### MCPToolNode
- **Module**: `kailash.nodes.mcp`
- **Purpose**: Execute MCP (Model Context Protocol) tools in workflows
- **Parameters**:
  - `mcp_server`: Name of MCP server
  - `tool_name`: Name of tool to execute
  - `parameters`: Tool parameters
- **Example**:
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

  workflow.add_node("MCPToolNode", "mcp_tool", {
      "mcp_server": "ai_tools",
      "tool_name": "analyze",
      "parameters": {"method": "regression", "data": "input_data"}
  })

  ```

### MCPClientNode
- **Module**: `kailash.nodes.mcp.client`
- **Purpose**: Connect to and interact with MCP servers
- **Features**: Tool discovery, parameter validation, result handling

### MCPServerNode
- **Module**: `kailash.nodes.mcp.server`
- **Purpose**: Create MCP server endpoints within workflows
- **Features**: Tool registration, request handling, response formatting

### MCPResourceNode
- **Module**: `kailash.nodes.mcp.resource`
- **Purpose**: Access MCP resources (files, data, etc.)
- **Features**: Resource discovery, access control, caching

## See Also
- [AI Nodes](02-ai-nodes.md) - AI and ML capabilities
- [API Nodes](04-api-nodes.md) - API integration
- [API Reference](../api/08-nodes-api.yaml) - Detailed API documentation
