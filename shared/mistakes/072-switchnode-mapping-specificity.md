# SwitchNode Mapping Specificity

**Mistake ID**: 072
**Category**: Cyclic Workflows
**Severity**: High
**Phase**: Session 56 - Logic Node Test Fixes

## Description

Incorrect connection mapping patterns when using SwitchNode in cyclic workflows, leading to "Required parameter 'input_data' not provided" errors and empty data transfer.

## The Mistake

### Wrong Pattern - Missing input_data Mapping
```python
# ❌ This doesn't work - SwitchNode requires input_data parameter
workflow.add_node("processor", ProcessorNode())
workflow.add_node("switch", SwitchNode())

# Wrong - no mapping
workflow.connect("processor", "switch")  # No mapping at all
# Result: ValueError: Required parameter 'input_data' not provided

# Wrong - incorrect parameter name
workflow.connect("processor", "switch",
    mapping={"result": "data"})  # Wrong parameter name
# Result: ValueError: Required parameter 'input_data' not provided
```

### Wrong Pattern - Empty Mapping in Cycles
```python
# ❌ Empty mapping transfers no data
workflow.connect("switch", "processor",
    mapping={},  # Empty mapping = no data transfer
    cycle=True,
    max_iterations=5)
# Result: Nodes receive empty data in subsequent iterations
```

## Root Cause

1. **SwitchNode API Requirements**: SwitchNode specifically expects `input_data` parameter
2. **Mapping Specificity**: Connection mappings must explicitly map to expected parameter names
3. **Empty Mappings**: `mapping={}` transfers nothing, breaking data flow in cycles

## The Solution

### Correct Pattern - Use "output" Key for Complete Transfer
```python
# ✅ Transfer complete output dictionary to SwitchNode
workflow.connect("processor", "switch",
    mapping={"output": "input_data"})  # Entire output → input_data

# SwitchNode then accesses fields within input_data
runtime.execute(workflow, parameters={
    "switch": {
        "condition_field": "needs_improvement",  # Field within input_data
        "operator": "==",
        "value": True
    }
})
```

### Correct Pattern - Specific Field Mapping
```python
# ✅ Map specific output field to input_data
workflow.connect("processor", "switch",
    mapping={"status": "input_data"})  # Specific field → input_data

# Or map multiple fields
workflow.connect("processor", "switch",
    mapping={
        "data": "input_data",
        "quality_score": "threshold"
    })
```

### Correct Pattern - Explicit Cycle Mapping
```python
# ✅ Use explicit field mappings in cycles
workflow.connect("switch", "processor",
    condition="false_output",
    mapping={
        "improved_data": "data",    # Map specific output field
        "quality_score": "threshold"
    },
    cycle=True,
    max_iterations=10)
```

## Complete Working Example
```python
# ✅ Full working pattern with source node
class DataSourceNode(CycleAwareNode):
    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return {"data": kwargs.get("data", [])}

workflow = Workflow("switch-mapping", "Switch Mapping")
workflow.add_node("data_source", DataSourceNode())
workflow.add_node("processor", QualityProcessorNode())
workflow.add_node("quality_switch", SwitchNode())

# Initial data flow
workflow.connect("data_source", "processor", mapping={"data": "data"})

# Processor to switch - complete output transfer
workflow.connect("processor", "quality_switch",
    mapping={"output": "input_data"})  # Key: "output" transfers everything

# Cycle back with specific field mapping
workflow.connect("quality_switch", "processor",
    condition="false_output",
    mapping={"improved_data": "data"},  # Specific field mapping
    cycle=True,
    max_iterations=10)

# Execute with proper configuration
runtime.execute(workflow, parameters={
    "data_source": {"data": [1, 2, 3, 60, 4, 5]},
    "quality_switch": {
        "condition_field": "needs_improvement",
        "operator": "==",
        "value": True
    }
})
```

## Detection

**Error Messages:**
- `ValueError: Required parameter 'input_data' not provided at execution time`
- Nodes receiving empty data in cycle iterations
- `KeyError` when SwitchNode tries to access condition_field

**Debug Patterns:**
```python
# Check SwitchNode debug output
# Should see: "SwitchNode received kwargs keys: ['input_data', 'condition_field', ...]"
# If missing 'input_data', check connection mapping
```

## Prevention

1. **Always map to input_data** for SwitchNode connections
2. **Use "output" key** to transfer complete output dictionary
3. **Specify explicit mappings** in cycle connections
4. **Test data flow** by checking SwitchNode receives expected parameters
5. **Avoid empty mappings** (`mapping={}`) in cycles

## Related Mistakes
- [071](071-cyclic-workflow-parameter-passing-patterns.md) - Parameter Passing Patterns
- [057](057-missing-cycle-flag.md) - Missing Cycle Flag
- [056](056-inconsistent-connection-apis-between-workflow-and-workflowbuilder.md) - Connection API Issues

## Examples in Codebase
- `tests/test_nodes/test_cycle_node_specific_logic.py::test_switch_conditional_cycle_routing`
- `tests/test_nodes/test_cycle_node_specific_logic.py::test_switch_multi_path_cycles`
