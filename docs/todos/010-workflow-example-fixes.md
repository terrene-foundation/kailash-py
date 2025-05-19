# Workflow Example Fixes

## Summary

Fixed multiple issues in workflow_example.py to demonstrate the correct way to create and execute workflows in the Kailash SDK.

## Issues Fixed

### 1. Incorrect add_node() Usage
**Problem**: The original code was passing class references to add_node() instead of node instances
```python
# Wrong
workflow.add_node(CSVReader)
```

**Solution**: Pass actual node instances
```python
# Correct
csv_reader = CSVReader(file_path='data.csv')
workflow.add_node(csv_reader, node_id='csv_reader')
```

### 2. Non-existent configure() Method
**Problem**: The code tried to call `node.configure()` which doesn't exist in our implementation
```python
# Wrong
filter_node.configure({'threshold': 1000})
```

**Solution**: Pass configuration during add_node()
```python
# Correct
workflow.add_node(filter_node, node_id='filter', config={
    'column_name': 'Total Claim Amount',
    'threshold': 1000.0
})
```

### 3. Workflow vs Direct Execution Pattern
**Problem**: The example didn't clearly show the difference between direct node execution and workflow execution

**Solution**: Created separate examples showing:
- Direct execution: All parameters provided upfront, execute() called immediately
- Workflow execution: Nodes connected in a graph, data flows through connections

### 4. Missing Node IDs and Connection Mappings
**Problem**: The original workflow connections were incomplete
```python
# Wrong
workflow.connect(csv_reader.id, 'data', filter_node.id, 'data')
```

**Solution**: Use proper connection syntax with mapping
```python
# Correct
workflow.connect(
    source_node='csv_reader',
    target_node='filter',
    mapping={'data': 'data'}
)
```

### 5. Runtime Import
**Problem**: Using non-existent WorkflowRunner class

**Solution**: Use correct LocalRuntime class
```python
from kailash.runtime.local import LocalRuntime
runtime = LocalRuntime(debug=True)
results, run_id = runtime.execute(workflow)
```

## Key Concepts Clarified

### Direct Node Execution
- Nodes run immediately when execute() is called
- All parameters must be provided upfront
- Good for simple operations or testing

### Workflow Execution
- Nodes are connected in a graph
- Data flows through connections
- Parameters can be provided by upstream nodes
- Better for complex data pipelines
- Provides execution tracking and management

## Files Created

1. **workflow_example.py** (updated) - Fixed version of the original example
2. **workflow_example_fixed.py** - Alternative implementation with detailed comments
3. **direct_vs_workflow_example.py** - Clear comparison of execution patterns

## Usage Pattern

```python
# 1. Create nodes
reader = CSVReader(file_path='input.csv')
writer = CSVWriter(file_path='output.csv')  # No data parameter

# 2. Add to workflow
workflow.add_node(reader, node_id='reader')
workflow.add_node(writer, node_id='writer')

# 3. Connect nodes
workflow.connect(
    source_node='reader',
    target_node='writer',
    mapping={'data': 'data'}  # Map reader's output to writer's input
)

# 4. Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
```

## Status

✅ **Completed** - All workflow example issues have been fixed and documented