# Inspector API Extensions - Design Summary

**Date**: 2025-11-01
**Status**: Design Complete, Ready for Implementation

---

## Overview

This document summarizes the Inspector API extension design for connection analysis and parameter tracing capabilities.

**Full Design**: See [inspector-api-extensions-design.md](./inspector-api-extensions-design.md)

---

## Key Design Decisions

### 1. Three New Dataclasses

| Dataclass | Purpose | Key Fields |
|-----------|---------|------------|
| **ConnectionInfo** | Single connection representation | source_node, source_param, target_node, target_param, type_compatible, validation_errors |
| **ParameterTrace** | Complete parameter flow path | source_node, transformations, destination_nodes, total_hops, type_changes |
| **ConnectionGraph** | Workflow topology analysis | nodes, connections, entry_points, exit_points, adjacency_list, cyclic |

**Why these structures?**
- Consistent with existing Inspector dataclasses (ModelInfo, NodeInfo, etc.)
- All support `.show()` for formatted display
- Contain both data and metadata for debugging

---

### 2. Ten New Methods (Two Categories)

#### Connection Analysis (5 methods)

| Method | Returns | Use Case |
|--------|---------|----------|
| `connections(node_id, direction)` | `list[ConnectionInfo]` | List all/filtered connections |
| `connection_chain(from_node, to_node)` | `list[ConnectionInfo]` | Find path between nodes |
| `connection_graph()` | `ConnectionGraph` | Topology analysis |
| `validate_connections()` | `dict[str, Any]` | Pre-execution validation |
| `find_broken_connections()` | `list[ConnectionInfo]` | Quick health check |

#### Parameter Tracing (5 methods)

| Method | Returns | Use Case |
|--------|---------|----------|
| `trace_parameter(node_id, param)` | `ParameterTrace` | Complete flow tracking |
| `parameter_flow(from_node, param)` | `list[dict]` | Step-by-step flow |
| `find_parameter_source(node_id, param)` | `dict[str, Any]` | Find origin |
| `parameter_dependencies(node_id)` | `dict[str, list[str]]` | List dependencies |
| `parameter_consumers(node_id, param)` | `list[dict]` | List consumers |

**Why this division?**
- Clear separation of concerns (topology vs. data flow)
- Each method has a specific, focused purpose
- Composable for complex debugging scenarios

---

### 3. Backward Compatibility Strategy

**No Breaking Changes**:
- All existing Inspector methods unchanged
- Existing dataclasses unchanged
- New features are **additive only**

**Enhanced NodeInfo** (optional):
```python
@dataclass
class NodeInfo:
    # EXISTING FIELDS (unchanged)
    node_id: str
    node_type: str
    # ... existing fields ...

    # NEW FIELDS (default to empty - backward compatible)
    connection_details: list[ConnectionInfo] = field(default_factory=list)
    parameter_traces: dict[str, ParameterTrace] = field(default_factory=dict)
```

**Why this approach?**
- Existing code continues to work without modification
- New features available when needed
- Gradual migration path for users

---

### 4. Data Source Integration

**Connection information from**:
1. `WorkflowBuilder.connections` - Connection dictionaries
2. `WorkflowBuilder.nodes` - Node configuration
3. `Node.get_parameters()` - Parameter declarations

**Type inference from**:
1. Parameter declarations (`get_parameters()`)
2. Python type hints (when available)
3. DataFlow model field types
4. Runtime value inspection

**Why these sources?**
- Already available in WorkflowBuilder
- No new infrastructure required
- Leverages existing validation mechanisms

---

### 5. Algorithm Choices

| Operation | Algorithm | Reason |
|-----------|-----------|--------|
| **connection_chain()** | Breadth-First Search (BFS) | Finds shortest path, handles cycles |
| **trace_parameter()** | Forward/Backward DFS | Tracks all branches, detects transformations |
| **connection_graph()** | Topological analysis | Detects cycles, calculates depth |
| **validate_connections()** | Iterative validation | Checks all constraints systematically |

**Performance**:
- Lazy evaluation (computed on-demand)
- Memoization during inspector session
- Max depth limits (default: 10) prevent infinite loops

---

## Example Usage Patterns

### Pattern 1: Pre-Execution Validation

```python
inspector = Inspector(studio)

# Validate before execution
report = inspector.validate_connections()
if report['broken'] > 0:
    print(f"❌ Cannot execute: {report['broken']} broken connections")
    for issue in report['issues']:
        print(f"  {issue['message']}")
else:
    print(f"✅ All {report['total']} connections valid")
    results = runtime.execute(workflow.build())
```

### Pattern 2: Debug Parameter Flow

```python
# Where does 'user_id' go?
trace = inspector.trace_parameter("input_node", "user_id")
print(f"Flows to {len(trace.destination_nodes)} nodes:")
for node in trace.destination_nodes:
    print(f"  - {node}")

# Where does 'result' come from?
source = inspector.find_parameter_source("output_node", "result")
print(f"Originates from: {source['node']}.{source['parameter']}")
```

### Pattern 3: Topology Analysis

```python
# Analyze workflow structure
graph = inspector.connection_graph()
print(f"Entry points: {graph.entry_points}")
print(f"Exit points: {graph.exit_points}")
print(f"Max depth: {graph.max_depth}")
print(f"Cyclic: {graph.cyclic}")

# Check for isolated nodes
if graph.isolated_nodes:
    print(f"⚠️  Isolated: {graph.isolated_nodes}")
```

### Pattern 4: Impact Analysis

```python
# Before modifying a node's output
consumers = inspector.parameter_consumers("processor", "result")
print(f"Changing 'result' will affect {len(consumers)} nodes:")
for consumer in consumers:
    print(f"  - {consumer['node']}.{consumer['parameter']}")
```

---

## Implementation Roadmap

### Task 1.2: Implementation (4 hours)

**Phase 1: Dataclasses** (1 hour)
- [ ] Implement `ConnectionInfo` with `.show()`
- [ ] Implement `ParameterTrace` with `.show()`
- [ ] Implement `ConnectionGraph` with `.show()`
- [ ] Add type hints and docstrings

**Phase 2: Connection Methods** (1.5 hours)
- [ ] Implement `connections()`
- [ ] Implement `connection_chain()` (BFS)
- [ ] Implement `connection_graph()` (topology)
- [ ] Implement `validate_connections()`
- [ ] Implement `find_broken_connections()`

**Phase 3: Parameter Methods** (1.5 hours)
- [ ] Implement `trace_parameter()` (DFS)
- [ ] Implement `parameter_flow()`
- [ ] Implement `find_parameter_source()`
- [ ] Implement `parameter_dependencies()`
- [ ] Implement `parameter_consumers()`

---

### Task 1.3: Testing (3 hours)

**Unit Tests** (1.5 hours)
- [ ] Dataclass creation and serialization
- [ ] Method signatures and type hints
- [ ] Edge cases (empty workflows, cycles, etc.)

**Integration Tests** (1.5 hours)
- [ ] Real DataFlow workflows
- [ ] Backward compatibility
- [ ] Error handling

---

### Task 1.4: Documentation (2 hours)

- [ ] Complete API reference (docstrings)
- [ ] User guide with examples
- [ ] Troubleshooting guide
- [ ] Update main Inspector README

---

## Technical Considerations

### Type Safety

All methods use modern Python type hints:
```python
def connections(
    self,
    node_id: Optional[str] = None,
    direction: Optional[str] = None
) -> list[ConnectionInfo]:
    ...
```

### Error Handling

Graceful degradation when information unavailable:
- Missing type info → `type=None` (not error)
- No path found → return empty list (not exception)
- Invalid node → return validation errors in dataclass

### Performance

- **Lazy evaluation**: No upfront graph building
- **Memoization**: Cache results during inspector session
- **Depth limits**: Prevent infinite loops in cycles
- **BFS for shortest paths**: O(V + E) complexity

---

## Success Criteria

1. **Backward Compatibility**: All existing Inspector tests pass unchanged
2. **Completeness**: All 10 new methods implemented with docstrings
3. **Type Safety**: No mypy errors, all type hints correct
4. **Test Coverage**: 90%+ coverage for new code
5. **Documentation**: Complete user guide with examples
6. **Performance**: <100ms for typical workflows (<50 nodes)

---

## Known Limitations

1. **Type inference**: Limited to declared types, not runtime values
2. **Cycle detection**: May not detect all subtle cycles (max_depth mitigation)
3. **Performance**: Large workflows (>100 nodes) may be slow for graph operations
4. **Memory**: Connection graphs held in memory (not suitable for massive workflows)

**Mitigation**:
- Document limitations in user guide
- Add performance warnings for large workflows
- Provide max_depth parameter for user control

---

## Next Actions

1. **Review Design** ✅ (Complete)
   - Design document created
   - API signatures finalized
   - Dataclasses specified

2. **Implement Methods** (Task 1.2)
   - Start with dataclasses (simplest)
   - Then connection methods
   - Finally parameter methods

3. **Write Tests** (Task 1.3)
   - Unit tests for each method
   - Integration tests with workflows
   - Backward compatibility tests

4. **Document** (Task 1.4)
   - Complete docstrings
   - User guide
   - Examples

---

## Questions for Review

1. **API Design**: Are method names clear and intuitive?
2. **Return Types**: Are dataclasses the right choice vs. plain dicts?
3. **Performance**: Are max_depth defaults appropriate?
4. **Completeness**: Are there missing use cases not covered?

---

**End of Summary**

**Full Design**: [inspector-api-extensions-design.md](./inspector-api-extensions-design.md)
