# Mistake 063: Cyclic Workflow Parameter Propagation - Multi-Issue Fix

## Problem
Parameter propagation in cyclic workflows was completely broken due to two separate issues:
1. NetworkX edge data being overwritten when multiple mappings were specified
2. Initial parameters being treated as outputs, causing DAG nodes to be skipped

## Root Cause
1. **Graph Edge Issue**: The `connect()` method was calling `add_edge()` multiple times in a loop, with each call overwriting the previous edge data. NetworkX doesn't merge edge attributes - it replaces them.

2. **Initial Parameters Issue**: The CyclicWorkflowExecutor was storing initial parameters in `state.node_outputs`, which made the executor think those nodes had already been executed.

## Discovery
- Debugging showed only the last mapping pair was preserved (e.g., only "c": "c" from {"a": "a", "b": "b", "c": "c"})
- DAG nodes that should feed into cycles were being skipped entirely
- Multi-field cycles failed while single-field cycles worked

## Solution
Two fixes were required:

1. **Fixed graph.py `connect()` method**:
```python
# Store complete mapping in single edge
edge_data = {
    "from_output": list(mapping.keys()),
    "to_input": list(mapping.values()),
    "mapping": mapping,  # Complete dictionary
}
self.graph.add_edge(source_node, target_node, **edge_data)
```

2. **Fixed CyclicWorkflowExecutor parameter handling**:
```python
# Store initial parameters separately
state.initial_parameters = parameters or {}
# Use them as inputs, not outputs
```

## Impact
- All cyclic workflow parameter propagation now works correctly
- DAG nodes properly feed data into cycles
- Multi-field mappings are preserved
- Phase 2 of cyclic graph implementation can proceed

## Prevention
- Always verify NetworkX edge behavior when storing complex data
- Keep initial parameters separate from execution outputs
- Test both single and multi-field parameter propagation
- Test DAG → cycle workflows, not just pure cycles

## Related Issues
- Mistake 058: Node Configuration vs Runtime Parameters Confusion
- Mistake 060: Incorrect Cycle State Access Patterns
- Mistake 062: Cyclic Workflow Parameter Propagation Failure
