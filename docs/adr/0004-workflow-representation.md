# Workflow Representation

## Status
Accepted

## Context
The Kailash Python SDK needs to represent workflows as DAGs (Directed Acyclic Graphs) that can be:
- Easily created and modified by ABCs
- Validated for correctness
- Executed locally for testing
- Exported to Kailash-compatible format
- Visualized for understanding

## Decision
We will implement a `Workflow` class that:

1. **Uses NetworkX** for DAG representation and operations
2. **Stores nodes** as `NodeInstance` objects with configuration
3. **Defines connections** as explicit mapping between outputs and inputs
4. **Validates** workflow integrity (cycles, missing connections)
5. **Supports serialization** to/from various formats

Key design elements:
- Separate node instances from node types
- Explicit data mapping between nodes
- Position tracking for visualization
- Metadata support for workflow properties

```python
workflow = Workflow(name="data_processing")
workflow.add_node("reader", CSVReader(), file_path="data.csv")
workflow.add_node("filter", Filter(), field="value", operator=">", value=100)
workflow.connect("reader", "filter", {"data": "data"})
```

## Consequences

### Positive
- Intuitive API for workflow construction
- Strong validation prevents common errors
- NetworkX provides proven graph algorithms
- Easy to visualize and debug
- Clean separation between definition and execution
- Supports complex data routing

### Negative
- NetworkX adds a dependency
- More complex than simple function chaining
- Requires understanding of DAG concepts
- Connection mapping can be verbose

### Implementation Notes
The workflow system integrates with:
- Node registry for type discovery
- Task tracking for execution monitoring
- Export system for Kailash compatibility
- Visualization utilities for debugging

This design balances ease of use for ABCs with the structural requirements of the Kailash architecture.