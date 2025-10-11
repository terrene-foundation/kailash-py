# Verification Summary: PythonCodeNode Parameter Preservation

## Investigation Request

User asked to verify the ACTUAL behavior of PythonCodeNode regarding:
1. Does PythonCodeNode preserve the `code` parameter in `node.config` after `workflow.build()`?
2. What is the correct way to use PythonCodeNode with WorkflowBuilder?
3. Where is the code actually stored?

## Findings

### 1. Code Parameter Preservation

**YOUR CLAIM WAS CORRECT** ✓

```python
from kailash.nodes.code import PythonCodeNode

node = PythonCodeNode(name="test", code="result = x * 2")

# ✓ Code IS stored as attribute
assert node.code == "result = x * 2"

# ✓ Code is NOT in node.config
assert node.config == {}
assert "code" not in node.config
```

### 2. Correct Usage with WorkflowBuilder

**Two ways to pass code parameter:**

#### Option A: Via add_node config dict
```python
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node(
    "PythonCodeNode",
    "processor",
    {"code": "result = x * 2", "input_types": {"x": int}}
)
```

#### Option B: Via add_existing_node
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode

node = PythonCodeNode(name="processor", code="result = x * 2")
workflow = WorkflowBuilder()
workflow.add_existing_node(node)
```

Both work correctly!

### 3. Storage Location

**The code is stored in THREE places:**

```python
node = PythonCodeNode(name="test", code="result = x * 2")

# Location 1: Instance attribute (PRIMARY)
assert node.code == "result = x * 2"  # ✓

# Location 2: NOT in node.config
assert node.config == {}  # ✓ Empty!

# Location 3: Included in get_config() for serialization
config = node.get_config()
assert config["code"] == "result = x * 2"  # ✓
```

**After workflow.build():**

```python
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {"code": "result = x * 2"})
built = workflow.build()

# NodeInstance.config is EMPTY
node_instance = built.nodes["test"]
assert node_instance.config == {}  # ✓

# Actual node is in the graph
actual_node = built.graph.nodes["test"]["node"]
assert actual_node.code == "result = x * 2"  # ✓
```

## Test Results

### Test 1: Direct Instantiation
```
✓ node.code = 'result = x * 2'
✓ node.config = {}
✓ 'code' not in node.config
```

### Test 2: get_config() Method
```
✓ node.get_config() returns:
  {
    'name': 'test',
    'description': 'Custom Python code node',
    'version': '1.0.0',
    'tags': ['code', 'python', 'custom'],
    'code': 'result = x * 2',  ← Code IS here
    'input_types': {'x': 'int'},
    'output_type': 'int'
  }
```

### Test 3: After WorkflowBuilder.build()
```
✓ node_instance.config = {}  (empty)
✓ built.graph.nodes["test"]["node"].code = 'result = x * 2'
```

### Test 4: From Function
```
✓ func_node.function = <function multiply>
✓ func_node.code = None
✓ func_node.config = {}
```

## Implementation Details

### Source File
`./repos/projects/kailash_python_sdk/src/kailash/nodes/code/python.py`

### Constructor (lines 1187-1277)
```python
def __init__(
    self,
    name: str,
    code: str | None = None,
    function: Callable | None = None,
    class_type: type | None = None,
    # ... other params
):
    # Stored as instance attributes (NOT in config)
    self.code = code  # Line 1231
    self.function = function  # Line 1232
    self.class_type = class_type  # Line 1233

    # Base Node.__init__ sets self.config = {}
    super().__init__(**kwargs)  # Line 1277
```

### get_config() Method (lines 1678-1715)
```python
def get_config(self) -> dict[str, Any]:
    """Get node configuration for serialization."""
    config = {
        "name": self.metadata.name,
        "description": self.metadata.description,
        "version": self.metadata.version,
        "tags": list(self.metadata.tags),
    }

    # Add code-specific config
    config.update({
        "code": self.code,  # ← Explicitly added for serialization
        "input_types": {...},
        "output_type": ...,
    })

    return config
```

## Why This Design?

### Architectural Decision

PythonCodeNode distinguishes between:

1. **Execution attributes** (`code`, `function`, `class_type`)
   - Stored as instance attributes
   - Used directly by runtime
   - Accessed via `node.code`, `node.function`, etc.

2. **Configuration parameters** (other node types)
   - Stored in `node.config`
   - Used for serialization/deserialization
   - Accessed via `node.config["param"]`

3. **Serialization format** (get_config())
   - Combines both for persistence
   - Includes execution attributes
   - Used for saving/loading workflows

### Runtime Behavior

```python
# When runtime executes a node, it:
# 1. Gets the actual node from graph
actual_node = built.graph.nodes[node_id]["node"]

# 2. Calls the node's run() method
result = actual_node.run(**inputs)

# 3. Inside run(), PythonCodeNode accesses self.code directly
def run(self, **kwargs):
    if self.code:
        outputs = self.executor.execute_code(self.code, kwargs)
        # ...
```

The runtime NEVER looks at `node.config["code"]` - it uses `node.code` directly!

## Comparison with Other Nodes

### HTTPRequestNode (Standard Pattern)
```python
workflow.add_node("HTTPRequestNode", "http", {"url": "https://api.com"})
built = workflow.build()
node = built.nodes["http"]

# ✓ Config IS populated for HTTPRequestNode
assert node.config["url"] == "https://api.com"
```

### PythonCodeNode (Special Pattern)
```python
workflow.add_node("PythonCodeNode", "py", {"code": "result = x"})
built = workflow.build()
node = built.nodes["py"]

# ✗ Config is EMPTY for PythonCodeNode
assert node.config == {}

# ✓ Must access via graph
actual_node = built.graph.nodes["py"]["node"]
assert actual_node.code == "result = x"
```

**PythonCodeNode is the exception, not the rule.**

## Recommendations

### For Testing PythonCodeNode

1. **Access code attribute directly:**
   ```python
   node = PythonCodeNode(name="test", code="...")
   assert node.code == "..."
   ```

2. **After build(), access via graph:**
   ```python
   built = workflow.build()
   actual_node = built.graph.nodes["test"]["node"]
   assert actual_node.code == "..."
   ```

3. **For serialization, use get_config():**
   ```python
   config = node.get_config()
   assert config["code"] == "..."
   ```

4. **Don't expect code in node.config:**
   ```python
   # ✗ WRONG
   assert node.config["code"] == "..."

   # ✓ CORRECT
   assert node.code == "..."
   ```

### For Documentation

Update any documentation that suggests:
- `node.config["code"]` is available
- PythonCodeNode config works like other nodes
- Code can be accessed via NodeInstance.config after build()

All should clarify:
- Use `node.code` for code access
- Use `node.get_config()` for serialization
- PythonCodeNode has a unique storage pattern

## Files Created

1. **INVESTIGATION_RESULTS_PYTHONCODE.md** - Detailed findings with code examples
2. **PYTHONCODE_USAGE_PATTERNS.md** - Correct usage patterns and common mistakes
3. **VERIFICATION_SUMMARY.md** (this file) - Executive summary

## Conclusion

Your original claim was **100% CORRECT**:

> "PythonCodeNode does not preserve the `code` parameter in `node.config` after `workflow.build()`"

The code is:
- ✓ Stored as `node.code` instance attribute
- ✓ Included in `node.get_config()` return value
- ✗ **NOT** in `node.config` dictionary
- ✓ Accessible via `built.graph.nodes[id]["node"]` after build()

This is by design and works correctly for execution. The runtime accesses `node.code` directly, not `node.config["code"]`.
