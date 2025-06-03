# Reference Documentation Validation Report

This report documents discrepancies found between the reference documentation in `guide/reference/` and the actual codebase implementation.

## Summary

The reference documentation contains several critical errors that would cause code generated from these references to fail. The most significant issues are:

1. **Incorrect Node Class Names**: Many data nodes do NOT have the "Node" suffix
2. **Wrong Workflow Execution Pattern**: Workflows are executed through a runtime, not directly
3. **Incorrect Connection Method Signature**: The `connect` method uses different parameters

## Critical Issues Found

### 2. Workflow Execution Method

The documentation states workflows have an `execute()` method that takes a runtime parameter:

**Documentation Claims (WRONG):**
```python
workflow.execute(runtime)  # This is INCORRECT
```

**Actual Implementation (CORRECT):**
```python
# Option 1: Execute through runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# Option 2: Direct execute (no runtime parameter)
results = workflow.execute(inputs={'key': 'value'})
```

The workflow's `execute()` method signature is:
```python
def execute(self, inputs: Optional[Dict[str, Any]] = None, task_manager: Optional[TaskManager] = None) -> Dict[str, Any]
```

### 3. Connection Method Parameters

The documentation shows incorrect parameter names for the `connect` method:

**Documentation Claims (WRONG):**
```python
workflow.connect("from", "to", from_output="port", to_input="port")
```

**Actual Implementation (CORRECT):**
```python
workflow.connect(
    source_node="from",
    target_node="to", 
    mapping={"output_field": "input_field"}  # Dict mapping, not separate params
)
```

The actual signature is:
```python
def connect(self, source_node: str, target_node: str, mapping: Optional[Dict[str, str]] = None) -> None
```

### 4. Add Node Method Signature

The documentation shows a different signature than the actual implementation:

**Documentation Claims:**
```python
workflow.add_node(node_id: str, node: Node, config: dict = None)
```

**Actual Implementation:**
```python
def add_node(self, node_id: str, node_or_type: Any, **config) -> None
```

The actual method:
- Takes `node_or_type` which can be a Node instance, Node class, or string type name
- Takes config as **kwargs, not as a dict parameter

### 5. Import Path Issues

Some import paths in the examples are incorrect:

**Documentation:**
```python
from kailash.workflow import MermaidVisualizer  # WRONG
```

**Actual:**
```python
from kailash.workflow.mermaid_visualizer import MermaidVisualizer  # CORRECT
```

### 6. Custom Node Creation Issues

The custom node example shows methods that don't match the actual base class:

**Documentation shows:**
- `get_parameters()` method
- `get_output_schema()` method

**Actual base class has:**
- Parameters defined via class attributes or constructor
- Output schema is optional and not always implemented

## Files That Need Updates

1. **`cheatsheet.md`**:
   - Fix all node class names (remove "Node" suffix where incorrect)
   - Fix workflow execution pattern
   - Fix connection method signature
   - Update import statements

2. **`validation-guide.md`**:
   - Remove the rule about ALL nodes having "Node" suffix
   - Clarify which nodes have suffix and which don't
   - Fix method signatures
   - Fix execution patterns

3. **`README.md`**:
   - Update the quick start example
   - Fix the critical rules section

4. **`api-registry.yaml`** (if it exists):
   - Verify all class names match actual implementation
   - Update method signatures

## Recommendations

1. **Create an automated validation script** that compares the reference docs against actual code
2. **Add unit tests** that verify the examples in documentation actually work
3. **Consider standardizing** node naming to always include "Node" suffix for consistency
4. **Update the register_node decorator** to handle aliasing if backward compatibility is needed
5. **Add doctest** to verify code examples in documentation

## Working Example (Corrected)

Here's a corrected version of the basic workflow example:

```python
from kailash import Workflow
from kailash.nodes.data import CSVReaderNode, CSVWriterNode  # No "Node" suffix
from kailash.runtime.local import LocalRuntime

# Create workflow
workflow = Workflow("example")

# Add nodes - using actual class names and method signature
workflow.add_node("reader", CSVReaderNode(), file_path="input.csv")
workflow.add_node("writer", CSVWriterNode(), file_path="output.csv")

# Connect nodes - using actual method signature
workflow.connect("reader", "writer", mapping={"data": "data"})

# Execute - using runtime
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)

# OR direct execution without runtime
results = workflow.execute(inputs={})
```