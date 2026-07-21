# WorkflowDAG — Custom Graph Engine

## What It Is

`WorkflowDAG` (`kailash.workflow.dag`) is a custom directed graph implementation that replaces networkx for all core workflow execution. It uses dual adjacency lists for O(1) neighbor lookups and implements only the 17 features actually used from networkx's hundreds.

## When to Use

- **Always** for workflow graph operations — it IS the graph engine
- Topological sorting, cycle detection, SCC analysis
- Node/edge queries during runtime execution

## Key APIs

```python
from kailash.workflow.dag import WorkflowDAG, CycleDetectedError

dag = WorkflowDAG()
dag.add_node("a", type="ProcessNode")
dag.add_node("b", type="TransformNode")
dag.add_edge("a", "b", label="output→input")

# Topological sort (Kahn's algorithm, cached)
order = dag.topological_sort()  # ["a", "b"]

# Cycle detection (Tarjan's SCC)
sccs = dag.strongly_connected_components()

# Queries
dag.predecessors("b")  # {"a"}
dag.successors("a")    # {"b"}
dag.ancestors("b")     # {"a"}
dag.descendants("a")   # {"b"}
```

## Cache Invalidation

All mutations (`add_node`, `add_edge`, `remove_node`, `remove_edge`) automatically invalidate the topo sort and SCC caches. Returned lists are copies — callers cannot corrupt the cache.

## Reference

- Source: `kailash/workflow/dag.py` (~890 lines)
- Tests: `tests/unit/workflow/test_workflow_dag.py` (70 tests)
- Replaces: networkx (now optional, viz only)
