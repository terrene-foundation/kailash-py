# Transaction Context Propagation in DataFlow

## ⚠️ Critical: Transaction Context is Opt-In

**IMPORTANT**: By default, DataFlow nodes do NOT share a transaction context. Each node gets its own connection from the pool.

### Default Behavior (No Shared Transaction)

```python
# ❌ NO shared transaction - each node gets separate connection
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_node("OrderCreateNode", "create_order", {...})
# If create_order fails, create_user is NOT automatically rolled back!
```

### Explicit Transaction Context (Shared Connection)

```python
# ✅ Shared transaction - all nodes use same connection
workflow.add_node("TransactionScopeNode", "tx", {})
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_node("OrderCreateNode", "create_order", {...})
workflow.add_node("TransactionCommitNode", "commit", {})
# If create_order fails, create_user IS rolled back automatically!
```

**See**: [Connection Isolation Guide](../../../../.claude/skills/02-dataflow/dataflow-connection-isolation.md) for complete explanation.

---

## Overview

DataFlow supports transaction context propagation, enabling ACID guarantees across multiple nodes within a single workflow execution. This feature allows you to maintain database transaction state throughout a workflow, ensuring data consistency and atomicity.

**To use this feature, you MUST explicitly use TransactionScopeNode** - it is not automatic.

## Key Features

- **Shared Transaction Context**: Multiple nodes can share the same database transaction
- **Connection Reuse**: Active database connections are shared between nodes in a transaction
- **ACID Guarantees**: Full transaction support with commit/rollback capabilities
- **Isolation Levels**: Support for all PostgreSQL isolation levels
- **Savepoints**: Nested transaction support with savepoint management
- **Error Handling**: Automatic rollback on errors with configurable behavior

## Transaction Nodes

### TransactionScopeNode

Initiates a new database transaction and stores the connection in workflow context.

```python
workflow.add_node("TransactionScopeNode", "begin_tx", {
    "isolation_level": "READ_COMMITTED",  # READ_UNCOMMITTED, READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE
    "timeout": 30,                        # Transaction timeout in seconds
    "rollback_on_error": True            # Automatically rollback on errors
})
```

**Parameters:**
- `isolation_level` (str): PostgreSQL isolation level (default: "READ_COMMITTED")
- `timeout` (int): Transaction timeout in seconds (default: 30)
- `rollback_on_error` (bool): Auto-rollback on error (default: True)

**Returns:**
- `status`: "started"
- `transaction_id`: Unique transaction identifier
- `isolation_level`: Active isolation level
- `timeout`: Transaction timeout
- `rollback_on_error`: Rollback configuration

### TransactionCommitNode

Commits the active transaction and closes the connection.

```python
workflow.add_node("TransactionCommitNode", "commit_tx", {})
```

**Returns:**
- `status`: "committed"
- `result`: Success message

### TransactionRollbackNode

Rolls back the active transaction and closes the connection.

```python
workflow.add_node("TransactionRollbackNode", "rollback_tx", {
    "reason": "Manual rollback"  # Optional reason for rollback
})
```

**Parameters:**
- `reason` (str): Reason for rollback (default: "Manual rollback")

**Returns:**
- `status`: "rolled_back"
- `reason`: Rollback reason
- `result`: Success message

### TransactionSavepointNode

Creates a savepoint within the current transaction.

```python
workflow.add_node("TransactionSavepointNode", "savepoint", {
    "name": "before_risky_operation"
})
```

**Parameters:**
- `name` (str): Savepoint name (required)

**Returns:**
- `status`: "created"
- `savepoint`: Savepoint name
- `result`: Success message

### TransactionRollbackToSavepointNode

Rolls back to a specific savepoint without ending the transaction.

```python
workflow.add_node("TransactionRollbackToSavepointNode", "rollback_sp", {
    "savepoint": "before_risky_operation"
})
```

**Parameters:**
- `savepoint` (str): Savepoint name to rollback to (required)

**Returns:**
- `status`: "rolled_back_to_savepoint"
- `savepoint`: Savepoint name
- `result`: Success message

## Usage Patterns

### Basic Transaction Workflow

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from dataflow import DataFlow

# Initialize DataFlow
db = DataFlow()

@db.model
class User:
    name: str
    email: str
    balance: float = 0.0

# Create workflow with transaction
workflow = WorkflowBuilder()

# Start transaction
workflow.add_node("TransactionScopeNode", "begin_tx", {
    "isolation_level": "READ_COMMITTED",
    "rollback_on_error": True
})

# Create user within transaction
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice",
    "email": "alice@example.com",
    "balance": 100.0
})

# Update user within same transaction
workflow.add_node("UserUpdateNode", "update_user", {
    "id": "${create_user.id}",
    "balance": 150.0
})

# Commit transaction
workflow.add_node("TransactionCommitNode", "commit_tx", {})

# Connect nodes
workflow.add_connection("begin_tx", "result", "create_user", "input")
workflow.add_connection("create_user", "result", "update_user", "input")
workflow.add_connection("update_user", "result", "commit_tx", "input")

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "workflow_context": {"dataflow_instance": db}
})
```

### Error Handling with Rollback

```python
# Create workflow with error handling
workflow = WorkflowBuilder()

# Start transaction
workflow.add_node("TransactionScopeNode", "begin_tx", {
    "isolation_level": "SERIALIZABLE",
    "rollback_on_error": True
})

# Business logic that might fail
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Bob",
    "email": "bob@example.com"
})

# Validation that might trigger rollback
workflow.add_node("PythonCodeNode", "validate_user", {
    "code": """
user = get_input_data("create_user")
if user["email"] == "invalid@example.com":
    raise ValueError("Invalid email address")
result = {"valid": True}
"""
})

# Rollback on error
workflow.add_node("TransactionRollbackNode", "rollback_tx", {
    "reason": "Validation failed"
})

# Commit on success
workflow.add_node("TransactionCommitNode", "commit_tx", {})

# Connect with error handling
workflow.add_connection("begin_tx", "result", "create_user", "input")
workflow.add_connection("create_user", "result", "validate_user", "input")
workflow.add_connection("validate_user", "result", "commit_tx", "input")
workflow.add_connection("source", "result", "target", "input")  # Fixed complex pattern
```

### Savepoints for Nested Operations

```python
# Complex workflow with savepoints
workflow = WorkflowBuilder()

# Main transaction
workflow.add_node("TransactionScopeNode", "main_tx", {
    "isolation_level": "READ_COMMITTED"
})

# Safe operation
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Charlie",
    "email": "charlie@example.com"
})

# Create savepoint before risky operation
workflow.add_node("TransactionSavepointNode", "savepoint", {
    "name": "before_update"
})

# Risky operation
workflow.add_node("PythonCodeNode", "risky_update", {
    "code": """
import random
if random.random() > 0.7:  # 30% chance of failure
    raise Exception("Random failure occurred")
result = {"success": True}
"""
})

# On success, continue
workflow.add_node("UserUpdateNode", "update_user", {
    "id": "${create_user.id}",
    "balance": 200.0
})

# On failure, rollback to savepoint
workflow.add_node("TransactionRollbackToSavepointNode", "rollback_sp", {
    "savepoint": "before_update"
})

# Always commit main transaction
workflow.add_node("TransactionCommitNode", "commit_tx", {})

# Connect with error handling
workflow.add_connection("main_tx", "result", "create_user", "input")
workflow.add_connection("create_user", "result", "savepoint", "input")
workflow.add_connection("savepoint", "result", "risky_update", "input")
workflow.add_connection("risky_update", "result", "update_user", "input")
workflow.add_connection("risky_update", "rollback_sp", on_error=True)
workflow.add_connection("update_user", "result", "commit_tx", "input")
workflow.add_connection("rollback_sp", "result", "commit_tx", "input")
```

### E-commerce Order Processing

```python
# Complete e-commerce transaction workflow
workflow = WorkflowBuilder()

# Start transaction with highest isolation
workflow.add_node("TransactionScopeNode", "order_tx", {
    "isolation_level": "SERIALIZABLE",  # Prevent phantom reads
    "timeout": 60,
    "rollback_on_error": True
})

# Create customer
workflow.add_node("CustomerCreateNode", "create_customer", {
    "name": "Enterprise Customer",
    "email": "customer@enterprise.com",
    "credit_limit": 10000.0
})

# Create order
workflow.add_node("OrderCreateNode", "create_order", {
    "customer_id": "${create_customer.id}",
    "status": "pending"
})

# Add items to order (multiple operations)
workflow.add_node("OrderItemCreateNode", "add_item1", {
    "order_id": "${create_order.id}",
    "product_id": 1,
    "quantity": 2,
    "price": 100.0
})

workflow.add_node("OrderItemCreateNode", "add_item2", {
    "order_id": "${create_order.id}",
    "product_id": 2,
    "quantity": 1,
    "price": 50.0
})

# Calculate total
workflow.add_node("PythonCodeNode", "calculate_total", {
    "code": """
total = 2 * 100.0 + 1 * 50.0  # $250
result = {"total": total}
"""
})

# Update order total
workflow.add_node("OrderUpdateNode", "update_order", {
    "id": "${create_order.id}",
    "total": "${calculate_total.total}",
    "status": "confirmed"
})

# Process payment
workflow.add_node("PaymentCreateNode", "process_payment", {
    "order_id": "${create_order.id}",
    "amount": "${calculate_total.total}",
    "status": "completed"
})

# Update inventory (could fail if insufficient stock)
workflow.add_node("ProductUpdateNode", "update_inventory1", {
    "id": 1,
    "stock": "${current_stock - 2}"
})

workflow.add_node("ProductUpdateNode", "update_inventory2", {
    "id": 2,
    "stock": "${current_stock - 1}"
})

# Commit entire transaction
workflow.add_node("TransactionCommitNode", "commit_order", {})

# Connect all operations
connections = [
    ("order_tx", "create_customer"),
    ("create_customer", "create_order"),
    ("create_order", "add_item1"),
    ("add_item1", "add_item2"),
    ("add_item2", "calculate_total"),
    ("calculate_total", "update_order"),
    ("update_order", "process_payment"),
    ("process_payment", "update_inventory1"),
    ("update_inventory1", "update_inventory2"),
    ("update_inventory2", "commit_order")
]

for source, target in connections:
    workflow.add_connection(source, "result", target, "input")
```

## Multi-Workflow Transaction Isolation

DataFlow's transaction architecture ensures proper isolation between concurrent workflows:

### Isolation Guarantees

1. **Per-Workflow Context**: Each workflow execution gets its own transaction context
2. **Connection Isolation**: Transactions are isolated at the database connection level
3. **MVCC Support**: Leverages PostgreSQL's Multi-Version Concurrency Control
4. **Lock Management**: Proper lock acquisition and release per transaction

### Concurrent Access Example

```python
# Workflow A - Processing order for Customer 1
workflow_a = WorkflowBuilder()
workflow_a.add_node("TransactionScopeNode", "tx_a", {
    "isolation_level": "REPEATABLE_READ"
})
# ... order processing logic ...
workflow_a.add_node("TransactionCommitNode", "commit_a", {})

# Workflow B - Processing order for Customer 2
workflow_b = WorkflowBuilder()
workflow_b.add_node("TransactionScopeNode", "tx_b", {
    "isolation_level": "REPEATABLE_READ"
})
# ... order processing logic ...
workflow_b.add_node("TransactionCommitNode", "commit_b", {})

# Execute concurrently
import threading

def execute_workflow(workflow, context):
    runtime = LocalRuntime()
    return runtime.execute(workflow.build(), parameters={
        "workflow_context": context
    })

# Each gets isolated transaction
thread_a = threading.Thread(
    target=execute_workflow,
    args=(workflow_a, {"dataflow_instance": db, "customer": "A"})
)
thread_b = threading.Thread(
    target=execute_workflow,
    args=(workflow_b, {"dataflow_instance": db, "customer": "B"})
)

thread_a.start()
thread_b.start()

thread_a.join()
thread_b.join()
```

## Best Practices

### 1. Use Appropriate Isolation Levels

```python
# For financial transactions - prevent all anomalies
workflow.add_node("TransactionScopeNode", "financial_tx", {
    "isolation_level": "SERIALIZABLE"
})

# For general CRUD operations - balance performance and consistency
workflow.add_node("TransactionScopeNode", "general_tx", {
    "isolation_level": "READ_COMMITTED"
})

# For read-heavy operations - prevent dirty reads
workflow.add_node("TransactionScopeNode", "read_tx", {
    "isolation_level": "READ_UNCOMMITTED"  # Only if dirty reads acceptable
})
```

### 2. Implement Proper Error Handling

```python
# Always include error paths
workflow.add_connection("risky_operation", "result", "commit_tx", "input")
workflow.add_connection("risky_operation", "rollback_tx", on_error=True)

# Use savepoints for partial rollbacks
workflow.add_node("TransactionSavepointNode", "checkpoint", {"name": "safe_point"})
workflow.add_node("TransactionRollbackToSavepointNode", "partial_rollback", {
    "savepoint": "safe_point"
})
```

### 3. Set Reasonable Timeouts

```python
# Short transactions for simple operations
workflow.add_node("TransactionScopeNode", "quick_tx", {"timeout": 10})

# Longer timeouts for complex operations
workflow.add_node("TransactionScopeNode", "complex_tx", {"timeout": 300})
```

### 4. Monitor Transaction Performance

```python
# Enable monitoring for transaction workflows
runtime = LocalRuntime(
    enable_monitoring=True,
    enable_audit=True
)
```

## Architecture Details

### Workflow Context Storage

Transaction state is stored in the workflow context:

```python
workflow_context = {
    "dataflow_instance": db,                    # DataFlow instance
    "transaction_connection": connection,       # Active database connection
    "active_transaction": transaction,          # asyncpg transaction object
    "transaction_config": {                     # Transaction configuration
        "isolation_level": "READ_COMMITTED",
        "timeout": 30,
        "rollback_on_error": True
    },
    "savepoints": {                            # Active savepoints
        "checkpoint_1": True,
        "checkpoint_2": True
    }
}
```

### Node Integration

DataFlow-generated nodes automatically check for transaction context:

```python
# Pseudo-code for generated DataFlow nodes
def run(self, **kwargs):
    # Check for active transaction
    connection = self.get_workflow_context("transaction_connection")

    if connection:
        # Use shared transaction connection
        result = await connection.execute(query, params)
    else:
        # Create new connection (legacy behavior)
        connection = await create_connection()
        result = await connection.execute(query, params)
        await connection.close()

    return result
```

### Connection Management

- **With Transaction**: Single connection shared across all nodes
- **Without Transaction**: Each node creates its own connection
- **Cleanup**: Connections are automatically closed on commit/rollback
- **Error Handling**: Connections are closed even if transaction fails

## Performance Considerations

### Benefits

- **Reduced Overhead**: Single connection vs. multiple connections per workflow
- **Better Performance**: No connection creation/destruction per node
- **Consistency**: ACID guarantees without manual connection management
- **Scalability**: Connection pooling handled at DataFlow level

### Monitoring

Transaction workflows automatically include performance metrics:

```python
# Results include transaction metrics
results, run_id = runtime.execute(workflow.build())

# Access transaction timing
transaction_start = results["begin_tx"]["timestamp"]
transaction_end = results["commit_tx"]["timestamp"]
transaction_duration = transaction_end - transaction_start
```

## Troubleshooting

### Common Issues

1. **Connection Not Found**: Ensure `dataflow_instance` is passed in workflow context
2. **Transaction Timeout**: Increase timeout or optimize workflow performance
3. **Deadlocks**: Use consistent ordering of operations and appropriate isolation levels
4. **Rollback Failures**: Check that transaction is still active and not already committed

### Debug Mode

Enable debug logging to track transaction lifecycle:

```python
runtime = LocalRuntime(debug=True)
```

### Error Messages

- `DataFlow instance not found in workflow context`: Pass DataFlow instance in parameters
- `No active transaction found`: Ensure TransactionScopeNode executed successfully
- `Failed to start transaction`: Check database connectivity and permissions
- `Transaction timeout exceeded`: Increase timeout or optimize workflow

## Migration Guide

### From Direct Node Execution

```python
# OLD: Direct node execution
user_node = db._nodes["UserCreateNode"]()
result = user_node.execute(name="Alice", email="alice@example.com")

# NEW: Transaction-aware workflow
workflow = WorkflowBuilder()
workflow.add_node("TransactionScopeNode", "tx", {})
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})
workflow.add_node("TransactionCommitNode", "commit", {})

workflow.add_connection("tx", "result", "create", "input")
workflow.add_connection("create", "result", "commit", "input")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "workflow_context": {"dataflow_instance": db}
})
```

### From Manual Transaction Management

```python
# OLD: Manual transaction management
async with db.get_connection() as conn:
    async with conn.transaction():
        # Manual operations
        await conn.execute("INSERT INTO users ...")
        await conn.execute("UPDATE accounts ...")

# NEW: Workflow-based transaction management
workflow = WorkflowBuilder()
workflow.add_node("TransactionScopeNode", "tx", {})
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_node("AccountUpdateNode", "update_account", {...})
workflow.add_node("TransactionCommitNode", "commit", {})
# Automatic connection and transaction management
```

## Security Considerations

- **SQL Injection Protection**: All generated nodes include SQL injection validation
- **Access Control**: Transaction context respects DataFlow access controls
- **Audit Logging**: Transaction operations are automatically logged when audit is enabled
- **Connection Security**: Database connections use configured security settings

## Summary

Transaction context propagation in DataFlow provides:

✅ **ACID Guarantees**: Full transaction support across workflow nodes
✅ **Performance**: Shared connections reduce overhead
✅ **Flexibility**: Multiple isolation levels and savepoint support
✅ **Reliability**: Automatic error handling and rollback capabilities
✅ **Scalability**: Proper isolation between concurrent workflows
✅ **Ease of Use**: Simple node-based transaction management

This feature enables DataFlow applications to handle complex, multi-step operations with full database consistency guarantees while maintaining the simplicity of the workflow paradigm.
