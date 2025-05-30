# State Management Implementation

This document describes the files created for the new immutable state management implementation.

## Core Files

| Filename | Description |
|----------|-------------|
| `kailash/workflow/state.py` | Core implementation of immutable state management with `StateManager` and `WorkflowStateWrapper` |
| `kailash/workflow/runner.py` | `WorkflowRunner` for connecting multiple workflows with state passing |

## Extended APIs

| Filename | Description |
|----------|-------------|
| `kailash/workflow/graph.py` (modified) | Added state management integration to `Workflow` class |

## HMI Implementation

| Filename | Description |
|----------|-------------|
| `examples/project_hmi/adapted/nodes_immutable.py` | Nodes that use immutable state management |
| `examples/project_hmi/adapted/workflow_immutable.py` | Workflow implementation with immutable state management |
| `examples/project_hmi/adapted/workflow_immutable_example.py` | Example script to demonstrate the immutable state workflow |
| `examples/project_hmi/adapted/state_management_comparison.md` | Comparison of traditional vs. immutable approaches |

## Tests

| Filename | Description |
|----------|-------------|
| `tests/test_workflow/test_state_management.py` | Unit tests for `StateManager` and `WorkflowStateWrapper` |
| `tests/test_workflow/test_workflow_state_integration.py` | Integration tests for workflow state management |
| `tests/test_workflow/test_hmi_state_management.py` | Tests for the HMI implementation with immutable state |

## Documentation

| Filename | Description |
|----------|-------------|
| `docs/adr/0015-immutable-state-management.md` | Architecture Decision Record for immutable state management |

## Usage Summary

1. **Wrap state with `WorkflowStateWrapper`**:
   ```python
   state_wrapper = WorkflowStateWrapper(state)
   ```

2. **Update state immutably**:
   ```python
   # Single update
   updated_wrapper = state_wrapper.update_in(["path", "to", "field"], new_value)
   
   # Multiple updates
   updated_wrapper = state_wrapper.batch_update([
       (["field1"], value1),
       (["nested", "field2"], value2)
   ])
   ```

3. **Execute workflow with state management**:
   ```python
   final_state, results = workflow.execute_with_state(state_model=state)
   ```

4. **Connect multiple workflows**:
   ```python
   runner = WorkflowRunner()
   runner.add_workflow("workflow1", workflow1)
   runner.add_workflow("workflow2", workflow2)
   runner.connect_workflows("workflow1", "workflow2", condition={"field": "status", "value": "completed"})
   final_state, results = runner.execute("workflow1", initial_state)
   ```

The implementation provides a clean, declarative approach to state management while ensuring immutability throughout workflow execution.