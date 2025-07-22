# Transaction Nodes - Distributed Transaction Management

**Enterprise-grade distributed transaction patterns with automatic pattern selection.**

## 🎯 Quick Reference

| Node | Use Case | Pattern | Consistency | Availability |
|------|----------|---------|-------------|--------------|
| **DistributedTransactionManagerNode** | Automatic pattern selection | Auto-select Saga/2PC | Configurable | High |
| **SagaCoordinatorNode** | Long-running transactions | Saga | Eventual | High |
| **SagaStepNode** | Individual saga steps | Saga | Eventual | High |
| **TwoPhaseCommitCoordinatorNode** | ACID transactions | 2PC | Strong/Immediate | Medium |

## 🚀 Core Patterns

### Automatic Pattern Selection
```python
from kailash.nodes.transaction import DistributedTransactionManagerNode

# DTM automatically selects optimal pattern
manager = DistributedTransactionManagerNode()
result = manager.execute(
    operation="create_transaction",
    transaction_name="order_processing",
    requirements={
        "consistency": "eventual",  # or "strong", "immediate"
        "availability": "high",     # or "medium", "low"
        "timeout": 300
    }
)
```

### Saga Pattern (High Availability)
```python
from kailash.nodes.transaction import SagaCoordinatorNode

# Long-running business transactions
coordinator = SagaCoordinatorNode(saga_name="order_processing")
result = coordinator.execute(
    operation="create_saga",
    context={"order_id": "123", "customer_id": "456"}
)
```

### Two-Phase Commit (Strong Consistency)
```python
from kailash.nodes.transaction import TwoPhaseCommitCoordinatorNode

# ACID transactions requiring atomicity
coordinator = TwoPhaseCommitCoordinatorNode(
    transaction_name="financial_transfer"
)
result = coordinator.execute(
    operation="begin_transaction",
    context={"amount": 10000.00, "currency": "USD"}
)
```

## 🎯 Pattern Selection Guide

### When to Use Each Pattern

**Use Distributed Transaction Manager When:**
- You need automatic pattern selection
- Mixed participant capabilities (some support 2PC, others don't)
- Requirements may change over time
- You want a unified interface

**Use Saga Pattern When:**
- Long-running business processes
- High availability is priority
- Participants don't support 2PC
- Eventual consistency is acceptable
- Need compensation logic

**Use Two-Phase Commit When:**
- Strong consistency required
- ACID properties needed
- All participants support 2PC
- Financial/critical transactions
- Immediate consistency required

## 📊 Pattern Comparison

| Aspect | Saga | Two-Phase Commit | DTM (Auto) |
|--------|------|------------------|------------|
| **Consistency** | Eventual | Strong/Immediate | Configurable |
| **Availability** | High | Medium | Configurable |
| **Participant Requirements** | Saga support | 2PC support | Mixed OK |
| **Compensation** | Manual | Automatic rollback | Pattern-dependent |
| **Performance** | High | Medium | Optimal |
| **Complexity** | Medium | High | Low |

## 🔧 Advanced Usage

### Pattern Selection Logic
```python
# DTM selection algorithm:
# 1. immediate consistency → Force 2PC (if supported)
# 2. high availability → Prefer Saga
# 3. strong consistency + 2PC support → Use 2PC
# 4. mixed capabilities → Use Saga
# 5. default → Saga (for flexibility)

manager = DistributedTransactionManagerNode()

# Add participants with capabilities
result = manager.execute(
    operation="add_participant",
    participant_id="payment_service",
    endpoint="http://payment:8080",
    supports_2pc=True,     # Can participate in 2PC
    supports_saga=True,    # Can participate in Saga
    compensation_action="refund_payment"
)
```

### State Persistence
```python
# Multiple storage backends supported
storage_configs = {
    "memory": {"storage": "memory"},
    "redis": {
        "storage": "redis",
        "redis_client": redis_client,
        "key_prefix": "transactions:"
    },
    "database": {
        "storage": "database",
        "db_pool": db_pool,
        "table_name": "transaction_states"
    }
}

coordinator = SagaCoordinatorNode(
    state_storage="redis",
    storage_config=storage_configs["redis"]
)
```

### Recovery and Monitoring
```python
# Automatic recovery from failures
result = manager.execute(
    operation="recover_transaction",
    transaction_id="tx_123"
)

# Comprehensive status monitoring
status = coordinator.execute(operation="get_status")
# Returns: state, participants, timestamps, error info
```

## 🛡️ Enterprise Features

### Participant Management
```python
# Rich participant capabilities
participant = {
    "participant_id": "inventory_service",
    "endpoint": "http://inventory:8080/api/v1",
    "supports_2pc": False,        # Legacy system
    "supports_saga": True,        # Supports compensation
    "compensation_action": "release_inventory",
    "timeout": 30,
    "retry_count": 3,
    "priority": 2                 # Execution order
}
```

### Transaction Requirements
```python
# Flexible requirements specification
requirements = {
    "consistency": "strong",           # eventual, strong, immediate
    "availability": "high",            # high, medium, low
    "timeout": 600,                   # Total timeout
    "isolation_level": "serializable", # Database isolation
    "durability": True,               # Persistence required
    "allow_partial_failure": False   # All-or-nothing
}
```

### Monitoring and Alerting
```python
# Built-in monitoring capabilities
coordinator = DistributedTransactionManagerNode(
    monitoring_enabled=True,
    audit_logging=True,
    retry_policy={
        "max_attempts": 3,
        "backoff": "exponential",
        "base_delay": 1.0
    }
)
```

## 🎯 Best Practices

### Pattern Selection
1. **Start with DTM** - Let automatic selection choose optimal pattern
2. **Immediate consistency** - Use 2PC with compatible participants
3. **High availability** - Use Saga pattern with compensation
4. **Mixed environments** - Use DTM for unified management

### Error Handling
```python
try:
    result = manager.execute(operation="execute_transaction")
    if result["status"] == "success":
        # Handle success
        pattern = result["selected_pattern"]
        participants = result["participants"]
    else:
        # Handle failure
        error = result["error"]
        # Implement retry or compensation
except Exception as e:
    # Handle system errors
    logger.error(f"Transaction failed: {e}")
```

### Performance Optimization
1. **Use appropriate timeouts** - Balance responsiveness and reliability
2. **Configure retry policies** - Exponential backoff for transient failures
3. **Monitor transaction metrics** - Track success rates and latencies
4. **Optimize participant order** - Priority-based execution

## 🔗 Related Documentation

- **Implementation Guide**: [developer/06-comprehensive-rag-guide.md](../developer/06-comprehensive-rag-guide.md)
- **Enterprise Patterns**: [enterprise/resilience-patterns.md](../enterprise/resilience-patterns.md)
- **Cheat Sheet**: [cheatsheet/049-distributed-transactions.md](../cheatsheet/049-distributed-transactions.md)
- **Testing Strategy**: [testing/test-organization-policy.md](../testing/test-organization-policy.md)

## 📚 Quick Examples

### E-commerce Order Processing
```python
# Saga pattern for order processing
coordinator = SagaCoordinatorNode(saga_name="order_processing")
coordinator.execute(operation="create_saga", context={"order_id": "123"})

# Steps: payment → inventory → shipping → notification
steps = [
    {"name": "payment", "compensation": "refund"},
    {"name": "inventory", "compensation": "release_stock"},
    {"name": "shipping", "compensation": "cancel_shipment"},
    {"name": "notification", "compensation": "send_cancellation"}
]
```

### Financial Transfer
```python
# 2PC pattern for financial transactions
coordinator = TwoPhaseCommitCoordinatorNode(
    transaction_name="wire_transfer"
)
coordinator.execute(
    operation="begin_transaction",
    context={"amount": 50000.00, "currency": "USD"}
)

# Participants: source_bank, target_bank, compliance, audit
# All must commit atomically or transaction fails
```

### Mixed Environment
```python
# DTM handles mixed participant capabilities
manager = DistributedTransactionManagerNode()
manager.execute(operation="create_transaction")

# Modern service supports 2PC
manager.execute(
    operation="add_participant",
    participant_id="modern_service",
    supports_2pc=True,
    supports_saga=True
)

# Legacy service only supports Saga
manager.execute(
    operation="add_participant",
    participant_id="legacy_service",
    supports_2pc=False,
    supports_saga=True
)

# DTM automatically selects Saga pattern
result = manager.execute(operation="execute_transaction")
# result["selected_pattern"] == "saga"
```

This comprehensive guide covers all transaction nodes with practical examples and best practices for enterprise distributed transaction management.
