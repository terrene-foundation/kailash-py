# How Kailash Implements Cyclic Workflows

## 🔄 True Cyclic Edges, Not SwitchNodes

Despite historical design intentions to use SwitchNodes for cycles (to maintain DAG constraints), Kailash actually implements **true cyclic edges** with a sophisticated execution strategy.

## 🏗️ Architecture Overview

### 1. Graph Structure
The workflow graph can contain actual cycles, marked with special metadata:

```python
# When you create a cycle
cycle.connect("processor", "evaluator", mapping={"result": "input"})

# This adds an edge with cycle=True
self.graph.add_edge("processor", "evaluator", cycle=True, cycle_id="optimization", ...)
```

### 2. Dual Edge Types
```python
# The workflow separates edges into two categories
dag_edges, cycle_edges = workflow.separate_dag_and_cycle_edges()

# DAG edges: Normal workflow connections
# Cycle edges: Marked with cycle=True attribute
```

### 3. Execution Strategy

The `CyclicWorkflowExecutor` uses a **staged execution approach**:

```text
Stage 1: Pre-cycle DAG nodes (topological order)
Stage 2: Cycle group (iterative execution)
Stage 3: Post-cycle DAG nodes (dynamic scheduling)
```

## 🎯 How It Overcomes DAG Constraints

### 1. **Graph Separation**
While the NetworkX graph contains cycles, execution planning separates them:

```python
# Create DAG-only graph for topological analysis
dag_graph = nx.DiGraph()
dag_graph.add_nodes_from(workflow.graph.nodes(data=True))
for source, target, data in dag_edges:
    if not data.get("cycle", False):
        dag_graph.add_edge(source, target, **data)

# Now we can use topological sort on DAG portion
topo_order = list(nx.topological_sort(dag_graph))
```

### 2. **Cycle Groups**
Cycles are identified and grouped:

```python
def get_cycle_groups(self) -> dict[str, list[tuple]]:
    """Group cycle edges by cycle_id."""
    # Groups like: {"optimization": [(A, B), (B, C), (C, A)]}
```

### 3. **Staged Execution**
The executor builds stages that alternate between DAG and cycle execution:

```python
# Execution stages look like:
Stage 1: [source, preprocessor]        # DAG nodes
Stage 2: CycleGroup("optimization")    # Cycle execution
Stage 3: [postprocessor, sink]         # More DAG nodes
```

### 4. **Dynamic Post-Cycle Scheduling**
After cycles complete, downstream nodes are dynamically scheduled:

```python
# When cycle terminates
downstream_nodes = cycle_group.get_downstream_nodes(workflow)
# These nodes are then executed with cycle results
```

## 📝 Example: How It Works

```python
# Define workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "source", {"code": "result = {'value': 0}"})
workflow.add_node("PythonCodeNode", "processor", {"code": "result = {'value': value + 1}"})
workflow.add_node("SwitchNode", "check", {"condition_field": "value", "operator": ">=", "value": 10})
workflow.add_node("PythonCodeNode", "sink", {"code": "result = {'final': value}"})

# Connect nodes
workflow.add_connection("source", "result", "processor", "input")
workflow.add_connection("processor", "result", "check", "input")
workflow.add_connection("check", "true_output", "sink", "input")

# Create cycle
built = workflow.build()
cycle = built.create_cycle("increment")
cycle.connect("check", "processor", {"false_output": "input"})  # Back edge
cycle.max_iterations(20)
cycle.build()

# Execution flow:
# 1. source executes (Stage 1 - DAG)
# 2. Cycle group executes (Stage 2):
#    - processor → check → processor (repeat)
#    - Until check returns true
# 3. sink executes (Stage 3 - post-cycle)
```

## 🔍 Key Differences from SwitchNode Approach

### True Cyclic Edges
- **Direct cycle specification**: No complex switch routing needed
- **Clear intent**: Cycles are explicit in the graph
- **Better performance**: No conditional evaluation overhead

### SwitchNode (Historical Intent)
- Would have used switches to route back
- Maintained pure DAG structure
- More complex configuration

## 🛡️ Safety Mechanisms

Even with true cycles, the system is safe:

1. **Max Iterations**: Hard limit on cycle execution
2. **Convergence Conditions**: Early termination when goal achieved
3. **Timeout Protection**: Time-based limits
4. **Memory Limits**: Prevent resource exhaustion
5. **State Tracking**: Monitor cycle progress

## 📚 API Remains Intuitive

Despite the implementation complexity, the API is simple:

```python
# Create cycle with fluent API
cycle = workflow.create_cycle("optimization")
cycle.connect("processor", "evaluator", {"result": "input"})
cycle.max_iterations(100)
cycle.converge_when("quality > 0.95")
cycle.build()
```

## 🎯 Key Takeaways

1. **Kailash uses true cyclic edges**, not SwitchNodes for cycles
2. **Graph separation strategy** enables DAG algorithms on non-cycle portions
3. **Staged execution** handles cycles specially while maintaining order
4. **Dynamic scheduling** ensures post-cycle nodes execute correctly
5. **The API hides this complexity** - you just define cycles naturally

## 🔗 Related Documentation

- [Cyclic Workflow Patterns](by-pattern/control-flow/cyclic-workflows.md)
- Architecture Decision Record (ADR-0070)
- [CycleBuilder API Reference](../../cheatsheet/021-cyclebuilder-api.md)
