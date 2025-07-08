# Distributed Transactions - Copy-Paste Patterns

**Enterprise-grade distributed transaction patterns with automatic selection.**

## 🎯 Quick Pattern Selection

### Automatic Pattern Selection (Recommended)
```python
from kailash.nodes.transaction import DistributedTransactionManagerNode

# DTM automatically selects optimal pattern
manager = DistributedTransactionManagerNode(
    transaction_name="business_process",
    state_storage="redis",
    storage_config={
        "redis_client": redis_client,
        "key_prefix": "transactions:"
    }
)

# Create transaction with requirements
result = manager.execute(
    operation="create_transaction",
    requirements={
        "consistency": "eventual",  # eventual, strong, immediate
        "availability": "high",     # high, medium, low
        "timeout": 300
    },
    context={"order_id": "123", "customer_id": "456"}
)

# Add participants with capabilities
participants = [
    {
        "participant_id": "payment_service",
        "endpoint": "http://payment:8080/api",
        "supports_2pc": True,
        "supports_saga": True,
        "compensation_action": "refund_payment"
    },
    {
        "participant_id": "inventory_service",
        "endpoint": "http://inventory:8080/api",
        "supports_2pc": False,  # Legacy system
        "supports_saga": True,
        "compensation_action": "release_inventory"
    }
]

for participant in participants:
    manager.execute(operation="add_participant", **participant)

# Execute - DTM selects Saga due to mixed capabilities
result = manager.execute(operation="execute_transaction")
print(f"Selected pattern: {result['selected_pattern']}")
```

### Force Specific Pattern
```python
# Force Two-Phase Commit for strong consistency
result = manager.execute(
    operation="execute_transaction",
    pattern="two_phase_commit"  # Explicit override
)

# Force Saga for high availability
result = manager.execute(
    operation="execute_transaction",
    pattern="saga"  # Explicit override
)
```

## 🔄 Saga Pattern (High Availability)

### Basic Saga Setup
```python
from kailash.nodes.transaction import SagaCoordinatorNode

# Create saga coordinator
coordinator = SagaCoordinatorNode(
    saga_name="order_processing",
    state_storage="database",
    storage_config={
        "db_pool": db_pool,
        "table_name": "saga_states"
    }
)

# Start saga
result = coordinator.execute(
    operation="create_saga",
    context={
        "order_id": "order_123",
        "customer_id": "customer_456",
        "total_amount": 299.99
    }
)
```

### Add Saga Steps with Compensation
```python
from kailash.nodes.transaction import SagaStepNode

# Define saga steps
steps = [
    {
        "name": "payment_step",
        "action": "process_payment",
        "compensation": "refund_payment",
        "timeout": 30,
        "retry_count": 3
    },
    {
        "name": "inventory_step",
        "action": "reserve_inventory",
        "compensation": "release_inventory",
        "timeout": 20,
        "retry_count": 2
    },
    {
        "name": "shipping_step",
        "action": "schedule_shipment",
        "compensation": "cancel_shipment",
        "timeout": 45,
        "retry_count": 1
    }
]

# Add steps to saga
for step in steps:
    coordinator.execute(
        operation="add_step",
        name=step["name"],
        node_id=f"StepNode_{step['name']}",
        parameters={"action": step["action"], "timeout": step["timeout"]},
        compensation_node_id=f"CompensationNode_{step['name']}",
        compensation_parameters={"action": step["compensation"]}
    )

# Execute saga
result = coordinator.execute(operation="execute_saga")
```

### Saga Recovery
```python
# Recover failed saga
result = coordinator.execute(
    operation="load_saga",
    saga_id="saga_123"
)

# Resume from failure point
if result["status"] == "success":
    resume_result = coordinator.execute(operation="resume")
    print(f"Saga resumed: {resume_result['state']}")
```

## ⚡ Two-Phase Commit (Strong Consistency)

### Basic 2PC Setup
```python
from kailash.nodes.transaction import TwoPhaseCommitCoordinatorNode

# Create 2PC coordinator
coordinator = TwoPhaseCommitCoordinatorNode(
    transaction_name="financial_transfer",
    state_storage="redis",
    storage_config={
        "redis_client": redis_client,
        "key_prefix": "2pc:"
    }
)

# Begin transaction
result = coordinator.execute(
    operation="begin_transaction",
    context={
        "transfer_id": "transfer_789",
        "from_account": "ACC001",
        "to_account": "ACC002",
        "amount": 10000.00,
        "currency": "USD"
    }
)
```

### Add 2PC Participants
```python
# Add participants that support 2PC
participants = [
    "source_bank_service",
    "target_bank_service",
    "compliance_service",
    "audit_service"
]

for participant_id in participants:
    coordinator.execute(
        operation="add_participant",
        participant_id=participant_id,
        endpoint=f"http://{participant_id}:8080/2pc"
    )

# Execute 2PC protocol
result = coordinator.execute(operation="execute_transaction")
print(f"Transaction state: {result['state']}")
```

### 2PC Recovery
```python
# Recover after coordinator failure
result = coordinator.execute(
    operation="recover_transaction",
    transaction_id="tx_789"
)

# Check recovery status
if result["status"] == "success":
    print(f"Recovered transaction in state: {result['state']}")
```

## 📊 Pattern Selection Examples

### E-commerce Order (Saga)
```python
# High availability, eventual consistency
manager = DistributedTransactionManagerNode()
manager.execute(
    operation="create_transaction",
    requirements={
        "consistency": "eventual",
        "availability": "high"
    }
)

# Mixed participant capabilities
services = [
    {"id": "payment", "2pc": True, "saga": True},
    {"id": "inventory", "2pc": False, "saga": True},  # Legacy
    {"id": "shipping", "2pc": False, "saga": True}   # External
]

for service in services:
    manager.execute(
        operation="add_participant",
        participant_id=service["id"],
        supports_2pc=service["2pc"],
        supports_saga=service["saga"]
    )

# Automatically selects Saga
result = manager.execute(operation="execute_transaction")
assert result["selected_pattern"] == "saga"
```

### Financial Transfer (2PC)
```python
# Strong consistency, ACID properties
manager = DistributedTransactionManagerNode()
manager.execute(
    operation="create_transaction",
    requirements={
        "consistency": "immediate",  # Forces 2PC
        "availability": "medium"
    }
)

# All participants support 2PC
financial_services = [
    "core_banking",
    "fraud_detection",
    "compliance_check",
    "audit_logging"
]

for service in financial_services:
    manager.execute(
        operation="add_participant",
        participant_id=service,
        supports_2pc=True,
        supports_saga=True
    )

# Automatically selects 2PC
result = manager.execute(operation="execute_transaction")
assert result["selected_pattern"] == "two_phase_commit"
```

## 🛡️ Enterprise Patterns

### Multi-Storage Configuration
```python
# Production-ready storage configuration
storage_configs = {
    "redis_ha": {
        "storage": "redis",
        "redis_client": redis_cluster,
        "key_prefix": "prod:tx:",
        "ttl": 604800  # 7 days
    },
    "postgres_ha": {
        "storage": "database",
        "db_pool": postgres_pool,
        "table_name": "transaction_states",
        "schema": "transactions"
    }
}

# Use different storage for different transaction types
saga_coordinator = SagaCoordinatorNode(
    state_storage="redis",
    storage_config=storage_configs["redis_ha"]
)

tpc_coordinator = TwoPhaseCommitCoordinatorNode(
    state_storage="database",
    storage_config=storage_configs["postgres_ha"]
)
```

### Monitoring and Alerting
```python
# Enterprise monitoring setup
manager = DistributedTransactionManagerNode(
    monitoring_enabled=True,
    audit_logging=True,
    retry_policy={
        "max_attempts": 3,
        "backoff": "exponential",
        "base_delay": 1.0,
        "max_delay": 30.0
    }
)

# Get comprehensive status
status = manager.execute(operation="get_status")
metrics = {
    "transaction_id": status["transaction_id"],
    "selected_pattern": status["selected_pattern"],
    "participants": len(status["participants"]),
    "state": status["transaction_status"],
    "duration": status.get("execution_time", 0)
}
```

### Error Handling Patterns
```python
# Robust error handling
try:
    result = manager.execute(operation="execute_transaction")

    if result["status"] == "success":
        # Success path
        transaction_id = result["transaction_id"]
        pattern = result["selected_pattern"]
        logger.info(f"Transaction {transaction_id} completed with {pattern}")

    elif result["status"] == "failed":
        # Handle failure
        error = result["error"]
        logger.error(f"Transaction failed: {error}")

        # Attempt recovery or compensation
        if "2pc" in result.get("selected_pattern", ""):
            # 2PC failure - check for partial commits
            status = manager.execute(operation="get_status")
            if status.get("coordinator_status"):
                # Decide on recovery action
                pass
        else:
            # Saga failure - compensation should be automatic
            pass

    elif result["status"] == "aborted":
        # Handle abort
        reason = result.get("reason", "Unknown")
        logger.warning(f"Transaction aborted: {reason}")

except Exception as e:
    logger.error(f"Transaction system error: {e}")
    # Implement fallback or manual intervention
```

## 🎯 Common Use Cases

### Microservices Order Processing
```python
# Typical microservices saga
def create_order_saga(order_data):
    coordinator = SagaCoordinatorNode(saga_name="order_processing")
    coordinator.execute(operation="create_saga", context=order_data)

    # Add microservice steps
    steps = [
        ("validate_order", "ValidationService"),
        ("process_payment", "PaymentService"),
        ("reserve_inventory", "InventoryService"),
        ("schedule_shipping", "ShippingService"),
        ("send_confirmation", "NotificationService")
    ]

    for step_name, service in steps:
        coordinator.execute(
            operation="add_step",
            name=step_name,
            node_id=f"{service}Node",
            compensation_node_id=f"{service}CompensationNode"
        )

    return coordinator.execute(operation="execute_saga")
```

### Cross-System Integration
```python
# DTM handles different system capabilities
def integrate_systems(integration_data):
    manager = DistributedTransactionManagerNode()
    manager.execute(operation="create_transaction", context=integration_data)

    # Different systems with different capabilities
    systems = [
        {"name": "erp_system", "2pc": True, "saga": True},
        {"name": "crm_system", "2pc": False, "saga": True},
        {"name": "legacy_mainframe", "2pc": False, "saga": True},
        {"name": "cloud_service", "2pc": True, "saga": True}
    ]

    for system in systems:
        manager.execute(
            operation="add_participant",
            participant_id=system["name"],
            supports_2pc=system["2pc"],
            supports_saga=system["saga"]
        )

    # Let DTM choose optimal pattern
    return manager.execute(operation="execute_transaction")
```

## 📚 Quick Reference

### Pattern Selection Rules
1. **immediate consistency** → Forces 2PC (if all participants support it)
2. **high availability** → Prefers Saga pattern
3. **strong consistency + 2PC support** → Uses 2PC
4. **mixed capabilities** → Uses Saga pattern
5. **default** → Saga (most flexible)

### Storage Options
- **Memory**: Development/testing
- **Redis**: Production, high performance
- **Database**: Production, durability, complex queries

### Common Operations
- `create_transaction` / `create_saga` / `begin_transaction`
- `add_participant` / `add_step`
- `execute_transaction` / `execute_saga`
- `get_status`
- `abort_transaction`
- `recover_transaction` / `load_saga`

Copy and adapt these patterns for your distributed transaction needs!
