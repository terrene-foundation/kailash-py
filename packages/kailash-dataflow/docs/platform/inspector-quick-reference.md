# Inspector Quick Reference Card

**Quick reference for Inspector connection analysis methods.**

---

## Setup

```python
from src.dataflow.platform.inspector import Inspector
inspector = Inspector(db, workflow=my_workflow)
```

---

## 5 Core Methods

### 1. connections(node_id=None)
**List all connections or filter by node**

```python
# All connections
all_conns = inspector.connections()

# Specific node
node_conns = inspector.connections("create_user")
```

### 2. connection_chain(from_node, to_node)
**Find shortest path between nodes (BFS)**

```python
path = inspector.connection_chain("input", "output")
if path:
    for conn in path:
        print(conn.show())
```

### 3. connection_graph()
**Get full workflow topology**

```python
graph = inspector.connection_graph()
print(graph.show())

# Access properties
print(f"Entry points: {graph.entry_points}")
print(f"Exit points: {graph.exit_points}")
print(f"Cycles: {len(graph.cycles)}")
```

### 4. validate_connections()
**Check connection validity**

```python
invalid = inspector.validate_connections()
if invalid:
    print(f"⚠️ {len(invalid)} invalid connections")
    for conn in invalid:
        print(conn.validation_message)
```

### 5. find_broken_connections()
**Find all issues (invalid, cycles, isolated)**

```python
broken = inspector.find_broken_connections()
if not broken:
    print("✓ Workflow is healthy")
```

---

## Common Patterns

### Pre-Execution Validation
```python
if not inspector.validate_connections():
    runtime.execute(workflow.build())
```

### Cycle Detection
```python
graph = inspector.connection_graph()
if graph.cycles:
    print(f"⚠️ {len(graph.cycles)} cycles detected!")
```

### Find Disconnected Nodes
```python
broken = inspector.find_broken_connections()
isolated = [b for b in broken if "isolated" in b.validation_message]
if isolated:
    print(f"⚠️ {len(isolated)} isolated nodes")
```

### Trace Data Flow
```python
path = inspector.connection_chain("source", "target")
print(f"Data flows through {len(path)} connections")
```

---

## ConnectionInfo Properties

```python
conn = connections[0]
conn.source_node       # "create_user"
conn.source_parameter  # "id"
conn.target_node       # "read_user"
conn.target_parameter  # "user_id"
conn.is_valid          # True/False
conn.validation_message # "Parameter not found"
conn.show()            # Rich formatted output
```

---

## ConnectionGraph Properties

```python
graph = inspector.connection_graph()
graph.nodes            # List[str]
graph.connections      # List[ConnectionInfo]
graph.entry_points     # List[str]
graph.exit_points      # List[str]
graph.cycles           # List[List[str]]
graph.show()           # Rich formatted output
```

---

## Error Handling

```python
try:
    connections = inspector.connections()
except AttributeError:
    print("Workflow not set - use Inspector(db, workflow=...)")
```

---

## One-Liner Health Check

```python
healthy = not inspector.find_broken_connections()
```

---

## Interactive Mode

```python
inspector.interactive()

# Inside interactive session:
>>> inspector.connections()
>>> inspector.connection_graph()
>>> inspector.validate_connections()
```

---

## Typical Workflow

```python
# 1. Create inspector
inspector = Inspector(db, workflow=workflow)

# 2. Validate connections
invalid = inspector.validate_connections()
if invalid:
    raise ValueError("Invalid connections found")

# 3. Check for cycles
graph = inspector.connection_graph()
if graph.cycles:
    raise ValueError("Circular dependencies detected")

# 4. Execute workflow
runtime.execute(workflow.build())
```

---

## Tips

- **Cache inspector**: Reuse for multiple calls
- **Validate early**: Before execution
- **Use filters**: `connections(node_id)` for specific nodes
- **Check cycles**: In production workflows
- **Interactive mode**: For debugging

---

## Full Documentation

- Implementation Guide: `docs/platform/inspector-connection-analysis.md`
- Usage Examples: `docs/platform/inspector-usage-examples.md`
- Source Code: `src/dataflow/platform/inspector.py` (lines 201-1059)
