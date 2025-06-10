# Cyclic Workflow Parameter Passing Patterns

**Mistake ID**: 071
**Category**: Cyclic Workflows
**Severity**: High
**Phase**: Session 56 - Logic Node Test Fixes

## Description

Incorrect parameter passing in cyclic workflows, leading to nodes not receiving initial data and cycles failing to execute properly.

## The Mistake

### Wrong Pattern - Workflow-Level Parameters
```python
# ❌ This doesn't work in cycles
workflow = Workflow("cycle-test", "Cycle Test")
workflow.add_node("processor", ProcessorNode())
workflow.add_node("switch", SwitchNode())
workflow.connect("processor", "switch", mapping={"output": "input_data"})
workflow.connect("switch", "processor", cycle=True, max_iterations=5)

runtime = LocalRuntime()
results = runtime.execute(workflow, parameters={
    "data": [1, 2, 3, 4]  # Wrong - this doesn't reach cycle nodes
})
```

### Result
```
ValueError: Required parameter 'input_data' not provided at execution time
```

## Root Cause

1. **No Entry Point**: Cycle nodes (processor, switch) have no non-cycle connections providing initial data
2. **Wrong Parameter Format**: Workflow-level parameters don't map to specific nodes in cycles
3. **Execution Order**: Cycle nodes only execute during cycle execution, not DAG execution

## The Solution

### Correct Pattern - Node-Specific Parameters with Source Nodes
```python
# ✅ Add a source node for initial data entry
class DataSourceNode(CycleAwareNode):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(name="data", type=list, required=False, default=[])
        }

    def run(self, context: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return {"data": kwargs.get("data", [])}

workflow = Workflow("cycle-test", "Cycle Test")
workflow.add_node("data_source", DataSourceNode())  # Entry point
workflow.add_node("processor", ProcessorNode())
workflow.add_node("switch", SwitchNode())

# Connect source to cycle
workflow.connect("data_source", "processor", mapping={"data": "data"})
workflow.connect("processor", "switch", mapping={"output": "input_data"})
workflow.connect("switch", "processor", cycle=True, max_iterations=5)

runtime = LocalRuntime()
results = runtime.execute(workflow, parameters={
    "data_source": {  # Node-specific parameters
        "data": [1, 2, 3, 4]
    }
})
```

## Alternative: Direct Parameter Mapping (Simple Cycles)
```python
# ✅ For simple self-loops, use direct parameter passing
workflow.add_node("processor", PythonCodeNode(name="processor", code=code))
workflow.connect("processor", "processor", cycle=True, max_iterations=5)

runtime.execute(workflow, parameters={
    "value": 10,      # Direct parameter for simple cycles
    "target": 100
})
```

## Detection

**Error Messages:**
- `ValueError: Required parameter 'input_data' not provided at execution time`
- `ValueError: Required parameter 'data' not provided at execution time`
- Nodes receiving empty data in cycles

**Test Pattern:**
```python
# If you see this in debug output:
# Node iteration 0: data=[], kwargs=['data']
# Node iteration 1: data=[], kwargs=['data']
# This indicates the parameter passing issue
```

## Prevention

1. **Always add source nodes** for multi-node cycles
2. **Use node-specific parameters** format: `{"node_id": {"param": value}}`
3. **Test initial data flow** before adding cycle connections
4. **Verify entry points** - ensure cycles have non-cycle connections providing initial data

## Related Mistakes
- [049](049-missing-data-source-nodes-in-workflow-design.md) - Missing Data Source Nodes
- [053](053-confusion-between-configuration-and-runtime-parameters.md) - Config vs Runtime Parameters
- [057](057-missing-cycle-flag.md) - Missing Cycle Flag

## Examples in Codebase
- `tests/test_nodes/test_cycle_node_specific_logic.py::test_switch_conditional_cycle_routing`
- `tests/test_nodes/test_cycle_node_specific_logic.py::test_merge_cycle_output_combination`
