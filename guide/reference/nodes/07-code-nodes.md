# Code Execution Nodes

**Module**: `kailash.nodes.code`
**Last Updated**: 2025-01-06

This document covers code execution nodes including Python code execution and MCP tool integration.

## Table of Contents
- [Python Code Execution](#python-code-execution)
- [PythonCodeNode Usage Guide](#pythoncodenode-usage-guide)
- [MCP Tool Nodes](#mcp-tool-nodes)

## Python Code Execution

### PythonCodeNode
- **Module**: `kailash.nodes.code.python`
- **Purpose**: Execute arbitrary Python code
- **Parameters**:
  - `code`: Python code to execute
  - `imports`: Required imports
  - `timeout`: Execution timeout
- **Security**: Sandboxed execution environment
- **Example**:
  ```python
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
from kailash import Workflow
from kailash.nodes.code.python import PythonCodeNode
from kailash.runtime.local import LocalRuntime

workflow = Workflow("cycle-example", "Cycle Example")

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

workflow.add_node("improver", PythonCodeNode(name="improver", code=python_code))

# ✅ ESSENTIAL: Include mapping for data flow between iterations
workflow.connect("improver", "improver",
    mapping={"current_value": "current_value"},  # Pass data between iterations
    cycle=True,
    max_iterations=10,
    convergence_check="converged == True")       # Direct field name

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "current_value": 10,
    "target": 50
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
# ✅ CORRECT: Use direct field names from result
workflow.connect("node", "node",
    convergence_check="converged == True")      # Direct access

# ❌ WRONG: Nested path access
workflow.connect("node", "node",
    convergence_check="result.converged == True")  # Will fail
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
# ❌ ERROR: Cycle runs only once, no data flow
workflow.connect("node", "node", cycle=True, max_iterations=5)

# ✅ FIX: Include mapping for data flow
workflow.connect("node", "node",
    mapping={"output_field": "input_field"},
    cycle=True, max_iterations=5)
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
# Always debug the actual result structure first
results, run_id = runtime.execute(workflow)
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
  mcp_tool = MCPToolNode()
  result = mcp_tool.run(
      mcp_server="ai_tools",
      tool_name="analyze",
      parameters={"method": "regression", "data": input_data}
  )
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
