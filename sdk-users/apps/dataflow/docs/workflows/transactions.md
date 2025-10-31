# DataFlow Transaction Management

Comprehensive guide to managing database transactions in DataFlow workflows.

## Overview

DataFlow provides two transaction patterns: **separate connections (default)** and **shared transaction context (explicit)**. Understanding which pattern you're using is critical for data consistency.

## ⚠️ Critical Understanding: Connection Isolation

**By default, DataFlow nodes do NOT share a transaction context.** Each node gets its own connection from the connection pool, which means:

- ❌ No automatic ACID guarantees across multiple nodes
- ❌ No automatic rollback if a later node fails
- ✅ Better concurrency (connections returned to pool quickly)
- ✅ No connection blocking on long workflows

**See**: [Connection Isolation Guide](../../../../.claude/skills/02-dataflow/dataflow-connection-isolation.md) for complete details.

## Transaction Patterns

### Pattern 1: Separate Connections (Default)

**Each DataFlow node gets its own connection from the pool:**

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Each node uses SEPARATE connection
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com"
})

workflow.add_node("AccountCreateNode", "create_account", {
    "user_id": ":user_id",
    "balance": 100.00
})

# Connect nodes
workflow.add_connection("create_user", "create_account", "id", "user_id")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# ❌ NO ACID GUARANTEES:
# - If create_account fails, create_user is NOT rolled back
# - Each operation commits independently
# - Partial data may persist if workflow fails midway
```

**When to use:** Independent operations, bulk imports where partial success is acceptable, high-concurrency scenarios.

### Pattern 2: Shared Transaction (Explicit)

**Use TransactionScopeNode for ACID guarantees across multiple nodes:**

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Start explicit transaction
workflow.add_node("TransactionScopeNode", "tx", {
    "isolation_level": "READ_COMMITTED",
    "timeout": 30,
    "rollback_on_error": True
})

# All nodes share SAME connection
workflow.add_node("UserCreateNode", "create_user", {
    "name": "John Doe",
    "email": "john@example.com"
})

workflow.add_node("AccountCreateNode", "create_account", {
    "user_id": ":user_id",
    "balance": 100.00
})

# Commit transaction
workflow.add_node("TransactionCommitNode", "commit", {})

# Connect nodes
workflow.add_connection("tx", "result", "create_user", "input")
workflow.add_connection("create_user", "create_account", "id", "user_id")
workflow.add_connection("create_account", "result", "commit", "input")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# ✅ ACID GUARANTEES:
# - If create_account fails, create_user IS rolled back
# - All operations in single transaction
# - No partial data commits
```

**When to use:** Financial operations, multi-step operations requiring atomicity, data consistency requirements, audit trail needs.

## Explicit Transaction Control

### Basic Transaction Management

```python
workflow = WorkflowBuilder()

# Start explicit transaction
workflow.add_node("TransactionScopeNode", "start_transaction", {
    "isolation_level": "READ_COMMITTED",  # Optional
    "timeout": 30,  # 30 seconds timeout
    "rollback_on_error": True  # Automatically rollback on error
})

# Database operations
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Jane Doe",
    "email": "jane@example.com"
})

workflow.add_node("ProfileCreateNode", "create_profile", {
    "user_id": ":user_id",
    "bio": "Software developer"
})

# Commit transaction
workflow.add_node("TransactionCommitNode", "commit_transaction", {
    # No parameters required - commits active transaction
})

# Connect nodes
workflow.add_connection("start_transaction", "result", "create_user", "input")
workflow.add_connection("create_user", "create_profile", "id", "user_id")
workflow.add_connection("create_profile", "result", "commit_transaction", "input")
```

### Transaction Rollback

```python
workflow = WorkflowBuilder()

# Start transaction
workflow.add_node("TransactionScopeNode", "start_tx", {
    "rollback_on_error": True
})

# Operations
workflow.add_node("UserCreateNode", "create_user", {...})

# Validation check
workflow.add_node("PythonCodeNode", "validate_user", {
    "code": """
user = get_input_data("create_user")["data"]
if not user["email"].endswith("@company.com"):
    result = {"valid": False, "error": "Invalid email domain"}
else:
    result = {"valid": True}
"""
})

# Conditional commit or rollback
workflow.add_node("SwitchNode", "tx_decision", {
    "input": ":valid",
    "cases": {
        "true": "commit_tx",
        "false": "rollback_tx"
    }
})

workflow.add_node("TransactionCommitNode", "commit_tx", {})
workflow.add_node("TransactionRollbackNode", "rollback_tx", {
    # No parameters required - rolls back active transaction
})

# Connect flow
workflow.add_connection("start_tx", "result", "create_user", "input")
workflow.add_connection("create_user", "result", "validate_user", "input")
workflow.add_connection("source", "result", "target", "input")  # Fixed complex pattern
workflow.add_connection("validate_user", "rollback_tx", "error")
```

## Transaction Isolation Levels

### Available Isolation Levels

```python
# READ_UNCOMMITTED - Lowest isolation, highest performance
workflow.add_node("TransactionScopeNode", "tx_read_uncommitted", {
    "isolation_level": "READ_UNCOMMITTED",
    "rollback_on_error": True
})

# READ_COMMITTED - Default for most databases
workflow.add_node("TransactionScopeNode", "tx_read_committed", {
    "isolation_level": "READ_COMMITTED",
    "rollback_on_error": True
})

# REPEATABLE_READ - Prevents non-repeatable reads
workflow.add_node("TransactionScopeNode", "tx_repeatable_read", {
    "isolation_level": "REPEATABLE_READ",
    "rollback_on_error": True
})

# SERIALIZABLE - Highest isolation, lowest concurrency
workflow.add_node("TransactionScopeNode", "tx_serializable", {
    "isolation_level": "SERIALIZABLE",
    "rollback_on_error": True
})
```

### Choosing Isolation Levels

```python
# For financial transactions - use SERIALIZABLE
workflow.add_node("TransactionScopeNode", "financial_tx", {
    "isolation_level": "SERIALIZABLE",
    "timeout": 60,  # Longer timeout for complex transactions
    "rollback_on_error": True
})

workflow.add_node("AccountUpdateNode", "debit_account", {
    "id": source_account_id,
    "balance": "balance - :amount"
})

workflow.add_node("AccountUpdateNode", "credit_account", {
    "id": target_account_id,
    "balance": "balance + :amount"
})

# For reporting - READ_COMMITTED is usually sufficient
workflow.add_node("TransactionScopeNode", "report_tx", {
    "isolation_level": "READ_COMMITTED",
    "rollback_on_error": True
    # Note: read_only optimization can be handled at database level
})
```

## Nested Transactions (Savepoints)

### Basic Savepoints

```python
workflow = WorkflowBuilder()

# Main transaction
workflow.add_node("TransactionScopeNode", "main_tx", {
    "rollback_on_error": True
})

# Create user (will be kept)
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Test User",
    "email": "test@example.com"
})

# Create savepoint
workflow.add_node("TransactionSavepointNode", "savepoint_1", {
    "name": "before_risky_operations"
})

# Risky operations
workflow.add_node("ExternalAPINode", "call_payment_api", {
    "endpoint": "https://payment.api/charge",
    "data": {"amount": 100.00}
})

# Rollback to savepoint on error
workflow.add_node("TransactionRollbackToSavepointNode", "rollback_on_error", {
    "savepoint": "before_risky_operations",
    "condition": ":api_failed"
})

# Commit main transaction
workflow.add_node("TransactionCommitNode", "commit_main", {})
```

### Multiple Savepoints

```python
# Complex workflow with multiple savepoints
workflow = WorkflowBuilder()

workflow.add_node("TransactionScopeNode", "main_tx", {
    "rollback_on_error": True
})

# Phase 1: User creation
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_node("TransactionSavepointNode", "sp_after_user", {
    "name": "user_created"
})

# Phase 2: Profile setup (optional)
workflow.add_node("ProfileCreateNode", "create_profile", {...})
workflow.add_node("TransactionSavepointNode", "sp_after_profile", {
    "name": "profile_created"
})

# Phase 3: Notifications (can fail)
workflow.add_node("NotificationNode", "send_notifications", {...})

# Handle notification failure
workflow.add_node("TransactionRollbackToSavepointNode", "handle_notification_error", {
    "savepoint": "profile_created",
    "on_error": True
})

workflow.add_node("TransactionCommitNode", "commit_all", {})
```

## Distributed Transactions

### Two-Phase Commit

```python
# Coordinating transactions across multiple databases
workflow = WorkflowBuilder()

# Phase 1: Prepare
workflow.add_node("TransactionPrepareNode", "prepare_main_db", {
    "database": "main",
    "transaction_id": ":global_tx_id"
})

workflow.add_node("TransactionPrepareNode", "prepare_analytics_db", {
    "database": "analytics",
    "transaction_id": ":global_tx_id"
})

# Check if all prepared successfully
workflow.add_node("TransactionCoordinatorNode", "check_prepared", {
    "participants": ["main", "analytics"],
    "transaction_id": ":global_tx_id"
})

# Phase 2: Commit or Abort
workflow.add_node("SwitchNode", "decide_commit", {
    "input": ":all_prepared",
    "cases": {
        "true": "commit_all",
        "false": "abort_all"
    }
})

# Commit path
workflow.add_node("TransactionCommitPreparedNode", "commit_main", {
    "database": "main",
    "transaction_id": ":global_tx_id"
})

workflow.add_node("TransactionCommitPreparedNode", "commit_analytics", {
    "database": "analytics",
    "transaction_id": ":global_tx_id"
})

# Abort path
workflow.add_node("TransactionAbortPreparedNode", "abort_main", {
    "database": "main",
    "transaction_id": ":global_tx_id"
})

workflow.add_node("TransactionAbortPreparedNode", "abort_analytics", {
    "database": "analytics",
    "transaction_id": ":global_tx_id"
})
```

## Transaction Patterns

### Saga Pattern

For long-running transactions that span multiple services:

```python
# Order processing saga
workflow = WorkflowBuilder()

# Step 1: Reserve inventory
workflow.add_node("InventoryReserveNode", "reserve_inventory", {
    "product_id": product_id,
    "quantity": quantity
})

# Step 2: Process payment
workflow.add_node("PaymentProcessNode", "process_payment", {
    "amount": total_amount,
    "payment_method": payment_method
})

# Step 3: Create shipment
workflow.add_node("ShipmentCreateNode", "create_shipment", {
    "order_id": ":order_id",
    "address": shipping_address
})

# Compensating transactions for rollback
workflow.add_node("InventoryReleaseNode", "release_inventory", {
    "reservation_id": ":reservation_id",
    "on_error": True
})

workflow.add_node("PaymentRefundNode", "refund_payment", {
    "payment_id": ":payment_id",
    "on_error": True
})

# Connect with error handling
workflow.add_connection("reserve_inventory", "result", "process_payment", "input")
workflow.add_connection("process_payment", "result", "create_shipment", "input")

# Compensation flow
workflow.add_connection("process_payment", "release_inventory",
                       on_error=True)
workflow.add_connection("create_shipment", "refund_payment",
                       on_error=True)
workflow.add_connection("create_shipment", "release_inventory",
                       on_error=True)
```

### Optimistic Locking

```python
# Update with version check
workflow = WorkflowBuilder()

# Read current version
workflow.add_node("ProductReadNode", "get_product", {
    "id": product_id,
    "lock": False  # Don't lock for read
})

# Update with version check
workflow.add_node("ProductUpdateNode", "update_product", {
    "id": product_id,
    "price": new_price,
    "version": ":current_version + 1",
    "where": {
        "version": ":current_version"  # Only update if version matches
    }
})

# Check if update succeeded
workflow.add_node("PythonCodeNode", "check_update", {
    "code": """
update_result = get_input_data("update_product")
if update_result["affected_rows"] == 0:
    result = {"success": False, "error": "Version conflict"}
else:
    result = {"success": True}
"""
})

# Retry logic for conflicts
workflow.add_node("RetryNode", "retry_on_conflict", {
    "target_node": "get_product",
    "condition": ":conflict_detected",
    "max_retries": 3,
    "backoff": "exponential"
})
```

### Pessimistic Locking

```python
# Lock records during read
workflow = WorkflowBuilder()

workflow.add_node("TransactionScopeNode", "start_tx", {
    "rollback_on_error": True
})

# Lock account for update
workflow.add_node("AccountReadNode", "lock_account", {
    "id": account_id,
    "lock": "FOR UPDATE",  # Exclusive lock
    "timeout": 5.0  # Wait up to 5 seconds
})

# Perform operations on locked record
workflow.add_node("AccountUpdateNode", "update_balance", {
    "id": account_id,
    "balance": ":new_balance"
})

workflow.add_node("TransactionCommitNode", "commit_tx", {})
```

## Best Practices

### 1. Keep Transactions Short

```python
# Good: Short transaction
workflow.add_node("TransactionScopeNode", "tx", {
    "rollback_on_error": True
})
workflow.add_node("UserCreateNode", "create_user", {...})
workflow.add_node("TransactionCommitNode", "commit", {})

# Then do slow operations outside transaction
workflow.add_node("EmailNode", "send_welcome_email", {...})

# Bad: Long transaction including slow operations
# workflow.add_node("TransactionScopeNode", "tx", {
    "rollback_on_error": True
})
# workflow.add_node("UserCreateNode", "create_user", {...})
# workflow.add_node("EmailNode", "send_email", {...})  # Slow!
# workflow.add_node("TransactionCommitNode", "commit", {})
```

### 2. Handle Deadlocks

```python
workflow.add_node("TransactionScopeNode", "tx", {
    "timeout": 10,
    "rollback_on_error": True
    # Note: deadlock retry can be handled at runtime level
})

# Always access resources in same order
workflow.add_node("UserUpdateNode", "update_user", {"id": 1})
workflow.add_node("AccountUpdateNode", "update_account", {"id": 1})
# Not: account then user in another transaction
```

### 3. Use Appropriate Isolation

```python
# Financial operations: SERIALIZABLE
workflow.add_node("TransactionScopeNode", "financial_tx", {
    "isolation_level": "SERIALIZABLE"
})

# Reporting: READ_COMMITTED with read-only
workflow.add_node("TransactionScopeNode", "report_tx", {
    "isolation_level": "READ_COMMITTED",
    "read_only": True
})

# Bulk operations: Consider READ_UNCOMMITTED
workflow.add_node("TransactionScopeNode", "bulk_tx", {
    "isolation_level": "READ_UNCOMMITTED",
    "rollback_on_error": True
})
```

### 4. Monitor Transaction Performance

```python
workflow.add_node("TransactionScopeNode", "monitored_tx", {
    "timeout": 30,
    "rollback_on_error": True
    # Note: monitoring can be configured at runtime level
})
```

## Error Handling

### Transaction Error Types

```python
# Handle different transaction errors
workflow.add_node("PythonCodeNode", "handle_tx_error", {
    "code": """
error = get_input_data("transaction_error")
error_type = error.get("type")

if error_type == "deadlock":
    result = {"action": "retry", "delay": 1.0}
elif error_type == "timeout":
    result = {"action": "abort", "reason": "Transaction timeout"}
elif error_type == "serialization_failure":
    result = {"action": "retry", "delay": 0.5}
else:
    result = {"action": "fail", "reason": str(error)}
"""
})
```

### Cleanup on Error

```python
workflow.add_node("TransactionScopeNode", "tx", {
    "rollback_on_error": True
    # Note: error handlers can be configured at workflow level
})

workflow.add_node("PythonCodeNode", "handle_cleanup", {
    "code": """
# Release any locks or resources
# Log transaction failure
# Notify monitoring system
"""
})
```

## Next Steps

- **Error Handling**: [Error Handling Guide](error-handling.md)
- **Performance**: [Performance Optimization](../production/performance.md)
- **Distributed Systems**: [Distributed Transactions](../advanced/distributed-transactions.md)

Proper transaction management is crucial for data integrity. Choose the right isolation level and transaction boundaries for your use case.
