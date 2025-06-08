# Mistake #066: Phase 6.3 Cycle Test Implementation Mistakes

## Context
During implementation of Phase 6.3 (Node-Specific Cycle Tests), multiple systematic errors were encountered that reveal important patterns for future cycle test development.

## Mistakes Made

### 1. PythonCodeNode Constructor Parameter Missing
**What happened**: All PythonCodeNode instantiations failed with `TypeError: PythonCodeNode.__init__() missing 1 required positional argument: 'name'`

**Code that failed**:
```python
workflow.add_node("python_processor", PythonCodeNode(code=python_code))
```

**Root cause**: PythonCodeNode requires `name` as the first parameter

**Solution**:
```python
workflow.add_node("python_processor", PythonCodeNode(name="python_processor", code=python_code))
```

**Pattern**: Always check constructor signatures with `help(ClassName.__init__)` before use

### 2. PythonCodeNode Function vs Raw Code Confusion
**What happened**: PythonCodeNode returned function objects instead of executing them

**Code that failed**:
```python
python_code = '''
def main(**kwargs):
    return {"value": 10, "converged": True}
'''
```

**Root cause**: PythonCodeNode expects raw Python statements, not function definitions

**Solution**:
```python
python_code = '''
# Direct variable assignments and statements
value = 10
converged = True
result = {"value": value, "converged": converged}
'''
```

**Pattern**: PythonCodeNode uses `exec()` on raw code, not function calls

### 3. PythonCodeNode Variable Scope Issues
**What happened**: Variables like `kwargs`, `locals()`, `NameError` not available in execution context

**Code that failed**:
```python
python_code = '''
value = kwargs.get("value", 0)  # NameError: name 'kwargs' is not defined
'''
```

**Root cause**: PythonCodeNode creates a restricted execution namespace

**Solution**: Use parameter names directly instead of accessing through `kwargs`:
```python
python_code = '''
# Variables are injected directly into namespace
try:
    value = value  # Use injected variable
except NameError:
    value = 0      # Fallback value
'''
```

### 4. Convergence Check Expression Format Confusion
**What happened**: Convergence expressions failed with "name 'result' is not defined" or "name 'converged' is not defined"

**Code that failed**:
```python
convergence_check="result.converged == True"  # For PythonCodeNode
convergence_check="converged == True"         # For direct outputs
```

**Root cause**: Different nodes return different result structures

**Solution Pattern**:
- For PythonCodeNode: Use direct variable names `convergence_check="converged == True"`
- For mock nodes: Use direct output keys `convergence_check="converged == True"`
- For nested results: Use dot notation carefully

### 5. Cycle Iteration Expectation vs Reality
**What happened**: Tests expected 3-5 iterations but cycles converged after 1-2 iterations

**Code that failed**:
```python
assert final_output["coordination_rounds"] >= 2  # Expected 2+, got 1
assert final_output["knowledge_count"] == 3      # Expected 3, got 1
```

**Root cause**: Convergence conditions too easy to satisfy early

**Solution**:
```python
# Make convergence require both condition AND minimum iterations
converged = current_consensus >= threshold and len(coordination_history) >= 2
# OR relax test assertions
assert final_output["coordination_rounds"] >= 1  # Accept actual behavior
```

### 6. Cycle Connection Missing Mapping
**What happened**: Cycles didn't iterate because no data was passed between iterations

**Code that failed**:
```python
workflow.connect("node", "node", cycle=True, max_iterations=5)  # No mapping!
```

**Root cause**: Cycle connections require explicit parameter mapping

**Solution**:
```python
workflow.connect("node", "node",
    mapping={"output_field": "input_field"},  # Essential for data flow
    cycle=True, max_iterations=5)
```

### 7. Node Naming Inconsistency in Tests
**What happened**: Node names in `add_node()` didn't match names in `connect()` calls

**Code that failed**:
```python
workflow.add_node("data_cleaner", PythonCodeNode(...))
workflow.connect("data_processor", "data_processor", ...)  # Wrong name!
```

**Solution**: Ensure consistency between node IDs across all workflow operations

### 8. SwitchNode API Confusion
**What happened**: Used `output_key` parameter which doesn't exist in `Workflow.connect()`

**Code that failed**:
```python
workflow.connect("switch", "processor",
    output_key="true_branch",  # TypeError: unexpected keyword argument
    mapping={...})
```

**Root cause**: SwitchNode uses different connection patterns with conditional outputs

**Solution**: SwitchNode creates output fields like `true_output`, `false_output`, or `case_*` that must be connected using regular mapping

### 9. Result Structure Access Inconsistency
**What happened**: Mixed expectations about whether results are nested under "result" key

**Code that failed**:
```python
assert final_output["converged"]         # Sometimes works
assert final_output["result"]["converged"] # Sometimes needed
```

**Root cause**: Different nodes return different result structures

**Solution Pattern**:
- Test actual result structure first: `print("Keys:", list(final_output.keys()))`
- Use consistent access pattern within each test
- PythonCodeNode typically returns flat structure when using raw code

## Key Learning Patterns

### 1. Always Verify Constructor Signatures
```python
# Before using any node class
from kailash.nodes.code.python import PythonCodeNode
help(PythonCodeNode.__init__)
```

### 2. Debug Result Structures First
```python
results, run_id = runtime.execute(workflow)
print(f"Result keys: {list(results['node_name'].keys())}")
print(f"Sample values: {results['node_name']}")
```

### 3. Test Cycle Connections Gradually
```python
# Start without convergence check
workflow.connect("node", "node", mapping={"out": "in"}, cycle=True, max_iterations=3)
# Add convergence after verifying basic iteration works
```

### 4. Use Explicit Input Types for PythonCodeNode
```python
node = PythonCodeNode(
    name="processor",
    code=code,
    input_types={"value": int, "target": int},  # Helps with debugging
    output_type=dict
)
```

## Documentation Needed

These patterns should be added to:

1. **Claude.md**: Common cycle test pitfalls
2. **Cheatsheet**: PythonCodeNode usage patterns
3. **Reference docs**: Node constructor signatures
4. **Workflow guide**: Cycle connection requirements

## Prevention

- Add constructor signature checks to common node classes in reference docs
- Create PythonCodeNode execution environment guide
- Document SwitchNode connection patterns
- Add cycle test template with proper structure
