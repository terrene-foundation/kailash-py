# PythonCodeNode: Correct Usage Patterns

## TL;DR

**PythonCodeNode does NOT store `code` in `node.config`.** The code is stored as `node.code` attribute and accessed via the graph during execution.

## Correct Patterns

### Pattern 1: Direct Instantiation and Testing

```python
from kailash.nodes.code import PythonCodeNode

# Create node
node = PythonCodeNode(
    name="processor",
    code="result = x * 2",
    input_types={"x": int},
    output_type=int
)

# ✓ CORRECT: Access via attribute
assert node.code == "result = x * 2"

# ✗ WRONG: Don't look in config
assert "code" not in node.config  # config is empty {}
```

### Pattern 2: WorkflowBuilder with Code String

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node(
    "PythonCodeNode",
    "processor",
    {"code": "result = x * 2", "input_types": {"x": int}}
)

built = workflow.build()

# ✓ CORRECT: Access actual node from graph
actual_node = built.graph.nodes["processor"]["node"]
assert actual_node.code == "result = x * 2"

# ✗ WRONG: NodeInstance.config is empty
node_instance = built.nodes["processor"]
assert "code" not in node_instance.config  # Empty {}
```

### Pattern 3: Using from_function

```python
from kailash.nodes.code import PythonCodeNode

def multiply(x: int) -> int:
    """Multiply by 2."""
    return x * 2

# Create from function
node = PythonCodeNode.from_function(multiply, name="multiplier")

# ✓ CORRECT: Access function attribute
assert node.function == multiply
assert node.code is None  # No code string when using function

# ✗ WRONG: Don't look in config
assert "function" not in node.config  # config is empty {}
```

### Pattern 4: Serialization with get_config()

```python
from kailash.nodes.code import PythonCodeNode

node = PythonCodeNode(
    name="processor",
    code="result = x * 2",
    input_types={"x": int},
    output_type=int
)

# ✓ CORRECT: Use get_config() for serialization
config = node.get_config()
assert config["code"] == "result = x * 2"
assert config["name"] == "processor"
assert config["input_types"] == {"x": "int"}
assert config["output_type"] == "int"

# ✗ WRONG: node.config doesn't have this info
assert node.config == {}  # Empty!
```

### Pattern 5: Testing Execution

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node(
    "PythonCodeNode",
    "processor",
    {"code": "result = x * 2"}
)

built = workflow.build()
runtime = LocalRuntime()

# ✓ CORRECT: Execute with inputs
results, run_id = runtime.execute(built, {"x": 5})
assert results["processor"]["result"] == 10

# The runtime internally does:
# actual_node = built.graph.nodes["processor"]["node"]
# actual_node.run(x=5)  # Uses actual_node.code
```

## Why This Design?

### Node Base Class Pattern

```python
class Node:
    def __init__(self, **kwargs):
        self.config = {}  # Base config (usually empty)
        # Subclasses add their own attributes
```

### PythonCodeNode Specialization

```python
class PythonCodeNode(Node):
    def __init__(self, code=None, function=None, class_type=None, **kwargs):
        # Store execution-related attributes on instance
        self.code = code  # Instance attribute
        self.function = function  # Instance attribute
        self.class_type = class_type  # Instance attribute

        super().__init__(**kwargs)  # Inherits config = {}
```

### Why Not in config?

1. **Execution attributes vs configuration**: `code`, `function`, and `class_type` are execution logic, not configuration
2. **Separation of concerns**: Runtime execution accesses node attributes directly
3. **Serialization**: `get_config()` includes everything needed for persistence

## Common Mistakes

### Mistake 1: Expecting code in NodeInstance.config

```python
# ✗ WRONG
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {"code": "result = x"})
built = workflow.build()
node = built.nodes["test"]
code = node.config["code"]  # KeyError! config is {}
```

```python
# ✓ CORRECT
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {"code": "result = x"})
built = workflow.build()
actual_node = built.graph.nodes["test"]["node"]
code = actual_node.code  # Works!
```

### Mistake 2: Using config for serialization

```python
# ✗ WRONG
node = PythonCodeNode(name="test", code="result = x")
serialized = node.config  # Empty dict!
```

```python
# ✓ CORRECT
node = PythonCodeNode(name="test", code="result = x")
serialized = node.get_config()  # Full config with code
```

### Mistake 3: Comparing PythonCodeNode to other nodes

```python
# HTTPRequestNode (and most other nodes)
workflow.add_node("HTTPRequestNode", "http", {"url": "https://api.com"})
built = workflow.build()
node = built.nodes["http"]
url = node.config["url"]  # ✓ Works for HTTPRequestNode

# PythonCodeNode (special case)
workflow.add_node("PythonCodeNode", "py", {"code": "result = x"})
built = workflow.build()
node = built.nodes["py"]
code = node.config["code"]  # ✗ FAILS - PythonCodeNode is different!
```

## Testing Checklist

When writing tests for PythonCodeNode:

- [ ] Use `node.code` to access code attribute (not `node.config["code"]`)
- [ ] Use `node.function` to access function attribute (not `node.config["function"]`)
- [ ] Use `node.get_config()` for serialization tests
- [ ] Access actual node via `built.graph.nodes[node_id]["node"]` after build()
- [ ] Remember `NodeInstance.config` is empty for PythonCodeNode
- [ ] Test execution with `runtime.execute()` to verify code runs

## Quick Reference

| What you want | How to get it |
|---------------|---------------|
| Code string | `node.code` (attribute) |
| Function object | `node.function` (attribute) |
| Class type | `node.class_type` (attribute) |
| Full config for serialization | `node.get_config()` (method) |
| Node after build() | `built.graph.nodes[id]["node"]` |
| Test execution | `runtime.execute(built, inputs)` |

## Examples from Real Code

### From test_python_code_node.py (lines 75-87)

```python
def test_python_code_node():
    """Test PythonCodeNode directly."""
    # Test with code string
    code_node = PythonCodeNode(
        name="adder",
        code="result = a + b",
        input_types={"a": int, "b": int},
        output_type=int,
    )

    result = code_node.execute(a=10, b=20)
    assert result["result"] == 30
```

Note: This test correctly uses `code_node.execute()` which internally accesses `code_node.code`.

### Workflow Integration

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "step1", {"code": "result = x * 2"})
workflow.add_node("PythonCodeNode", "step2", {"code": "result = result + 1"})
workflow.add_edge("step1", "step2", {"result": "result"})

# Execute
built = workflow.build()
runtime = LocalRuntime()
results, run_id = runtime.execute(built, {"x": 5})

# Verify
assert results["step1"]["result"] == 10  # 5 * 2
assert results["step2"]["result"] == 11  # 10 + 1
```

The runtime handles everything internally - you don't need to access `node.code` in normal usage!
