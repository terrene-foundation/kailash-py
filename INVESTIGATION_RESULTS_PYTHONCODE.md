# Investigation Results: PythonCodeNode Parameter Preservation

## Summary

**YOU WERE CORRECT** - The `code` parameter is NOT stored in `node.config` after `workflow.build()`.

## Key Findings

### 1. PythonCodeNode Storage Pattern

```python
from kailash.nodes.code import PythonCodeNode

node = PythonCodeNode(
    name="test",
    code="result = x * 2",
    input_types={"x": int},
    output_type=int
)

# The code is stored as an instance attribute
assert node.code == "result = x * 2"  # ✓ Available

# But NOT in node.config
assert node.config == {}  # ✓ Empty dict
assert 'code' not in node.config  # ✓ Confirmed
```

### 2. However, get_config() DOES Include Code

```python
config = node.get_config()
# Returns: {
#   'name': 'test',
#   'description': 'Custom Python code node',
#   'version': '1.0.0',
#   'tags': ['code', 'python', 'custom'],
#   'code': 'result = x * 2',  # ✓ Code IS here
#   'input_types': {'x': 'int'},
#   'output_type': 'int'
# }
```

### 3. After WorkflowBuilder.build()

```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node(
    "PythonCodeNode",
    "test",
    {"code": "result = x * 2"}
)

built = workflow.build()

# NodeInstance has empty config
node_instance = built.nodes["test"]
assert node_instance.config == {}  # ✓ Empty

# But the actual node is stored in the NetworkX graph
actual_node = built.graph.nodes["test"]["node"]
assert actual_node.code == "result = x * 2"  # ✓ Code preserved
assert actual_node.config == {}  # ✓ Still empty
```

## Code Implementation Reference

From `./repos/projects/kailash_python_sdk/src/kailash/nodes/code/python.py`:

### Constructor (lines 1187-1277)

The `code` parameter is stored as `self.code` (line 1231):

```python
def __init__(
    self,
    name: str,
    code: str | None = None,
    # ... other params
):
    # ...
    self.code = code  # Line 1231 - stored as instance attribute
    # ...
    super().__init__(**kwargs)  # Line 1277 - inherits from Node
```

### Base Node Class Config

PythonCodeNode inherits from `Node`, which has:
- `self.config` = empty dict by default (from Node base class)
- `self.code` = stored as PythonCodeNode-specific attribute

### get_config() Method (lines 1678-1715)

This method DOES include the code:

```python
def get_config(self) -> dict[str, Any]:
    """Get node configuration for serialization."""
    # Get base config from parent class
    config = {
        "name": self.metadata.name,
        "description": self.metadata.description,
        "version": self.metadata.version,
        "tags": list(self.metadata.tags) if self.metadata.tags else [],
    }

    # Add code-specific config
    config.update(
        {
            "code": self.code,  # ✓ Code IS included here
            "input_types": {...},
            "output_type": ...,
        }
    )
    return config
```

## Why Execution Still Works

The runtime accesses the actual node object stored in the graph:

```python
# Runtime looks up the node from the graph
actual_node = workflow.graph.nodes[node_id]["node"]

# Then executes using the node's attributes
actual_node.run(**inputs)  # This accesses actual_node.code
```

## Implications for Testing

### Current Test Pattern (WRONG for PythonCodeNode)

```python
# ✗ This will FAIL for code-based PythonCodeNode
built = workflow.build()
node = built.nodes["test"]
assert node.config["code"] == "result = x * 2"  # KeyError!
```

### Correct Test Pattern

```python
# ✓ Option 1: Access via graph
built = workflow.build()
actual_node = built.graph.nodes["test"]["node"]
assert actual_node.code == "result = x * 2"

# ✓ Option 2: Test before build()
node = PythonCodeNode(name="test", code="result = x * 2")
assert node.code == "result = x * 2"

# ✓ Option 3: Use get_config()
config = node.get_config()
assert config["code"] == "result = x * 2"
```

## Comparison with Other Nodes

Most other nodes (like HTTPRequestNode, SQLDatabaseNode) store their config in `node.config`:

```python
workflow.add_node("HTTPRequestNode", "http", {"url": "https://api.example.com"})
built = workflow.build()
node = built.nodes["http"]
assert node.config["url"] == "https://api.example.com"  # ✓ Works for HTTP
```

**PythonCodeNode is special** - it stores execution-related attributes (`code`, `function`, `class_type`) as instance attributes, NOT in `config`.

## Recommended Action

When writing tests that verify PythonCodeNode code preservation:

1. **Access the actual node from the graph**: `built.graph.nodes[node_id]["node"]`
2. **Use get_config() for serialization tests**: `node.get_config()["code"]`
3. **Test before build() for direct access**: Create node, check `node.code` directly

## Files to Review

Based on this finding, these test files may need updates:

```bash
grep -r "node\.config\[.code" tests/
```

Any test expecting `code` in `node.config` will fail and should be updated to use one of the correct patterns above.
