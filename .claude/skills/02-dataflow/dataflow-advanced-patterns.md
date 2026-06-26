# DataFlow Advanced Patterns

## Transaction Context Propagation

By default, DataFlow nodes do NOT share a transaction. Each node gets its own connection.

### Enabling Shared Transactions

```python
# Without transaction: create_user and create_order are independent
# With transaction: all-or-nothing ACID guarantee

workflow.add_node("TransactionScopeNode", "begin_tx", {
    "isolation_level": "READ_COMMITTED",  # or SERIALIZABLE for financial
    "timeout": 30,
    "rollback_on_error": True
})
workflow.add_node("UserCreateNode", "create_user", {"name": "Alice", "email": "a@b.com"})
workflow.add_node("OrderCreateNode", "create_order", {"customer_id": "${create_user.id}"})
workflow.add_node("TransactionCommitNode", "commit_tx", {})

workflow.add_connection("begin_tx", "result", "create_user", "input")
workflow.add_connection("create_user", "result", "create_order", "input")
workflow.add_connection("create_order", "result", "commit_tx", "input")

results, run_id = runtime.execute(workflow.build(), parameters={
    "workflow_context": {"dataflow_instance": db}
})
```

### Transaction Nodes

| Node                                 | Purpose                                                         |
| ------------------------------------ | --------------------------------------------------------------- |
| `TransactionScopeNode`               | Begin transaction (isolation_level, timeout, rollback_on_error) |
| `TransactionCommitNode`              | Commit and close connection                                     |
| `TransactionRollbackNode`            | Rollback with optional reason                                   |
| `TransactionSavepointNode`           | Create named savepoint for partial rollback                     |
| `TransactionRollbackToSavepointNode` | Rollback to savepoint without ending transaction                |

### Isolation Level Guide

- `SERIALIZABLE`: Financial transactions (prevents all anomalies)
- `READ_COMMITTED`: General CRUD (balance of performance and consistency)
- `REPEATABLE_READ`: Concurrent order processing
- `READ_UNCOMMITTED`: Only if dirty reads are acceptable

### Multi-Workflow Isolation

Each workflow execution gets its own transaction context. Concurrent workflows are isolated at the connection level via PostgreSQL MVCC.

---

## DataFlow + Nexus Integration 

`auto_migrate=True` (default) works correctly everywhere including Docker and Nexus. No startup tradeoffs.

```python
import os
from nexus import Nexus
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

# Step 1: DataFlow with defaults (fast startup, full features)
db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    enable_caching=True,
    enable_metrics=True,
    connection_pool_size=50,
)

# Step 2: Register models
@db.model
class User:
    id: str
    email: str
    full_name: str = None
    active: bool = True

# Step 3: Create Nexus
app = Nexus(api_port=8000, mcp_port=3001, auto_discovery=False)

# Step 4: Register workflows
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"email": "{{email}}", "full_name": "{{full_name}}"})
app.register("create_user", workflow.build())
```

### Startup Times 

| Models | Time | Notes                       |
| ------ | ---- | --------------------------- |
| 1-3    | <2s  | Synchronous DDL handling |
| 5      | <3s  | Scales well                 |
| 10     | <5s  | Still fast                  |

### Read-Only Mode

For existing databases: `DataFlow(database_url=url, auto_migrate=False)`

---

## Connection Pool Configuration

```python
import os
from dataflow import DataFlow

db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    connection_pool_size=20,  # Max connections in pool
    enable_caching=True,
)
```

### Per-Environment Sizing

| Environment | pool_size | Notes                          |
| ----------- | --------- | ------------------------------ |
| Development | 5         | Low concurrency                |
| Staging     | 15        | Simulates production load      |
| Production  | 30-50     | Based on expected concurrency  |
| Analytics   | 10        | Long-running queries, separate |
