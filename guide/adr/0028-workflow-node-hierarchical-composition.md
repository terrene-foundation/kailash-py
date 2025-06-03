# ADR-0028: WorkflowNode for Hierarchical Workflow Composition

## Status
Accepted

## Context
The Kailash SDK needed a way to enable workflow reusability and hierarchical composition. Users were creating complex workflows that contained common patterns, but there was no way to package these patterns as reusable components. This led to:

1. **Duplication**: Common workflow patterns repeated across different workflows
2. **Maintenance burden**: Updates to patterns required changes in multiple places
3. **Limited abstraction**: No way to hide complexity behind simpler interfaces
4. **Testing challenges**: Difficult to test workflow components in isolation

## Decision
We implemented a `WorkflowNode` class that wraps entire workflows and exposes them as single nodes. This enables hierarchical composition where workflows can contain other workflows, creating a powerful abstraction mechanism.

### Key Design Features

1. **Dynamic Parameter Discovery**
   - Automatically detects input requirements from workflow entry nodes
   - Maps workflow outputs from exit nodes
   - All parameters made optional to support runtime configuration

2. **Multiple Loading Methods**
   - Direct workflow instance: `WorkflowNode(workflow=my_workflow)`
   - From file: `WorkflowNode(workflow_path="path/to/workflow.yaml")`
   - From dictionary: `WorkflowNode(workflow_dict={...})`

3. **Custom Input/Output Mapping**
   ```python
   WorkflowNode(
       workflow=inner_workflow,
       input_mapping={
           "rows": {"node": "reader", "parameter": "num_rows", "type": int}
       },
       output_mapping={
           "count": {"node": "writer", "output": "row_count", "type": int}
       }
   )
   ```

4. **Lazy Runtime Loading**
   - Runtime created only when needed to avoid circular imports
   - Uses LocalRuntime internally for workflow execution

## Implementation Details

### Parameter Mapping
- Entry nodes (no incoming connections) define workflow inputs
- Exit nodes (no outgoing connections) define workflow outputs
- Parameters prefixed with node_id: `reader_file_path`, `writer_output`
- Generic `inputs` parameter for additional overrides

### Execution Flow
1. WorkflowNode receives parameters
2. Maps parameters to inner workflow nodes
3. Executes workflow using LocalRuntime
4. Maps outputs back to WorkflowNode outputs
5. Returns consolidated results

### Configuration Validation
- Overrides `_validate_config()` to skip strict validation
- Parameters are dynamic based on wrapped workflow
- Validation happens at runtime during execution

## Consequences

### Positive
1. **Reusability**: Complex workflows become building blocks
2. **Abstraction**: Implementation details hidden from users
3. **Modularity**: Test workflows in isolation before composition
4. **Maintainability**: Update inner workflows without changing outer ones
5. **Scalability**: Build complex systems from simpler components

### Negative
1. **Debugging complexity**: Errors in nested workflows harder to trace
2. **Parameter naming**: Potential conflicts with node_id prefixing
3. **Performance overhead**: Additional execution layer
4. **File loading limitations**: YAML/JSON export format constraints

### Neutral
1. All workflow features available to wrapped workflows
2. Compatible with existing runtime and tracking systems
3. Standard node interface maintained

## Examples

### Basic Usage
```python
# Create reusable workflow
data_workflow = Workflow("processor")
# ... add nodes ...

# Wrap as node
processor_node = WorkflowNode(workflow=data_workflow)

# Use in another workflow
main_workflow = Workflow("main")
main_workflow.add_node("processor", processor_node)
```

### Hierarchical Composition
```python
# Level 1: Basic processing
level1 = create_processing_workflow()

# Level 2: Enhanced processing
level2 = Workflow("enhanced")
level2.add_node("basic", WorkflowNode(workflow=level1))
level2.add_node("extra", additional_processing)

# Level 3: Complete pipeline
level3 = Workflow("complete")
level3.add_node("pipeline", WorkflowNode(workflow=level2))
```

## References
- Issue: User request for workflow reusability
- Implementation: `src/kailash/nodes/logic/workflow.py`
- Tests: `tests/test_nodes/test_workflow_node.py`
- Examples: `examples/workflow_examples/workflow_nested_composition.py`

## Notes
Future enhancements could include:
- Workflow versioning for wrapped workflows
- Parameter type inference from workflow analysis
- Visual representation of nested workflows
- Optimization for deeply nested workflows
