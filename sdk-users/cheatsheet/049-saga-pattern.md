# Saga Pattern Cheatsheet

Quick reference for implementing distributed transactions using the Saga pattern: orchestration, compensation, and state management.

## Saga Coordinator - Quick Start

```python
from kailash.nodes.transaction import SagaCoordinatorNode

# Create saga coordinator
saga = SagaCoordinatorNode()

# Create a new saga
result = saga.execute(
    operation="create_saga",
    saga_name="order_processing",
    timeout=600.0,
    context={"user_id": "user123", "order_id": "order456"}
)
saga_id = result["saga_id"]

# Add steps with compensations
result = saga.execute(
    operation="add_step",
    name="validate_order",
    node_id="ValidationNode",
    parameters={"check_inventory": True},
    compensation_node_id="CancelValidationNode"
)

result = saga.execute(
    operation="add_step",
    name="charge_payment",
    node_id="PaymentNode",
    parameters={"amount": 100.0},
    compensation_node_id="RefundPaymentNode"
)

# Execute the saga
result = saga.execute(operation="execute_saga")
print(f"Saga completed: {result['status']}")
```

## Saga Step - Quick Start

```python
from kailash.nodes.transaction import SagaStepNode

# Create a saga step with compensation
payment_step = SagaStepNode(
    step_name="process_payment",
    idempotent=True,
    max_retries=3
)

# Execute forward action
result = payment_step.execute(
    operation="execute",
    execution_id="exec_123",
    saga_context={"order_id": "order_456"},
    action_type="charge",
    data={"amount": 100.0, "currency": "USD"}
)

# If needed, compensate
result = payment_step.execute(
    operation="compensate",
    execution_id="exec_123"
)
```

## Common Patterns

### Pattern 1: Order Processing Saga

```python
from kailash.nodes.transaction import SagaCoordinatorNode

# Create order processing saga
saga = SagaCoordinatorNode(saga_name="order_processing")

# Initialize saga
result = saga.execute(
    operation="create_saga",
    context={
        "order_id": "order_789",
        "customer_id": "cust_123",
        "items": [{"sku": "ITEM1", "qty": 2}],
        "total_amount": 150.00
    }
)

# Step 1: Validate inventory
saga.execute(
    operation="add_step",
    name="check_inventory",
    node_id="InventoryCheckNode",
    parameters={"output_key": "inventory_status"},
    compensation_node_id="ReleaseInventoryNode"
)

# Step 2: Reserve inventory
saga.execute(
    operation="add_step",
    name="reserve_inventory",
    node_id="InventoryReserveNode",
    parameters={"output_key": "reservation_id"},
    compensation_node_id="CancelReservationNode"
)

# Step 3: Process payment
saga.execute(
    operation="add_step",
    name="process_payment",
    node_id="PaymentProcessNode",
    parameters={"output_key": "payment_id"},
    compensation_node_id="RefundPaymentNode"
)

# Step 4: Create shipment
saga.execute(
    operation="add_step",
    name="create_shipment",
    node_id="ShipmentNode",
    parameters={"output_key": "tracking_number"},
    compensation_node_id="CancelShipmentNode"
)

# Execute saga
result = saga.execute(operation="execute_saga")

if result["status"] == "success":
    print(f"Order processed: {result['context']}")
else:
    print(f"Order failed at: {result['failed_step']}")
    print(f"Compensation: {result['compensation']}")
```

### Pattern 2: Custom Saga Step

```python
from kailash.nodes.transaction import SagaStepNode

class PaymentSagaStep(SagaStepNode):
    """Custom payment processing step with compensation."""

    def __init__(self, **kwargs):
        super().__init__(
            step_name="payment_processing",
            idempotent=True,
            max_retries=3,
            **kwargs
        )

        # Override action handlers
        self.forward_action = self._process_payment
        self.compensation_action = self._refund_payment

    def _process_payment(self, inputs, saga_context):
        """Process payment forward action."""
        amount = inputs["data"]["amount"]
        customer_id = saga_context["customer_id"]

        # Simulate payment processing
        payment_result = {
            "payment_id": f"pay_{customer_id}_{amount}",
            "status": "charged",
            "amount": amount,
            "timestamp": datetime.now(UTC).isoformat()
        }

        return payment_result

    def _refund_payment(self, inputs, saga_context, execution_state):
        """Refund payment compensation."""
        payment_result = execution_state["result"]

        # Simulate refund
        refund_result = {
            "refund_id": f"ref_{payment_result['payment_id']}",
            "status": "refunded",
            "amount": payment_result["amount"],
            "original_payment": payment_result["payment_id"]
        }

        return refund_result

# Use custom step
payment_step = PaymentSagaStep()
result = payment_step.execute(
    operation="execute",
    saga_context={"customer_id": "cust_123"},
    data={"amount": 99.99}
)
```

### Pattern 3: Saga with Monitoring

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Build saga workflow with monitoring
workflow = WorkflowBuilder()

# Add transaction monitoring
workflow.add_node("TransactionMetricsNode", "metrics", {
    "operation": "start_transaction",
    "transaction_id": "saga_001",
    "operation_type": "distributed_saga"
})

# Add saga coordinator
workflow.add_node("SagaCoordinatorNode", "saga", {
    "saga_name": "monitored_workflow"
})

# Connect monitoring to saga
workflow.add_connection("metrics", "status", "saga", "monitoring_enabled")

# Execute with monitoring
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Pattern 4: Resumable Saga with Persistence

```python
# Redis storage configuration
import redis
from kailash.nodes.transaction import SagaCoordinatorNode

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

saga = SagaCoordinatorNode(
    state_storage="redis",
    storage_config={
        "redis_client": redis_client,
        "key_prefix": "saga:prod:"
    },
    saga_id="resumable_saga_123"
)

# Or database storage
import asyncpg

db_pool = await asyncpg.create_pool(
    host='localhost',
    database='myapp',
    user='saga_user'
)

saga = SagaCoordinatorNode(
    state_storage="database",
    storage_config={
        "db_pool": db_pool,
        "table_name": "saga_states"
    }
)

# Load existing saga
result = saga.execute(
    operation="load_saga",
    saga_id="resumable_saga_123"
)

if result["status"] == "success":
    # Resume execution
    result = saga.execute(operation="resume")
elif result["status"] == "not_found":
    # Create new saga
    result = saga.execute(operation="create_saga")
```

### Pattern 5: Saga State Management

```python
# List all running sagas
saga_manager = SagaCoordinatorNode()
result = saga_manager.execute(
    operation="list_sagas",
    filter={"state": "running"}
)

print(f"Found {result['count']} running sagas")
for saga_id in result['saga_ids']:
    # Load and check each saga
    saga = SagaCoordinatorNode()
    saga.execute(operation="load_saga", saga_id=saga_id)
    status = saga.execute(operation="get_status")

    # Check for stuck sagas
    if status['state'] == 'running':
        duration = time.time() - status['start_time']
        if duration > 3600:  # 1 hour
            print(f"Saga {saga_id} stuck, triggering compensation")
            saga.execute(operation="cancel")
```

## Configuration Reference

### Saga Coordinator Settings

```python
# Saga configuration
SagaCoordinatorNode(
    saga_name="business_process",
    timeout=3600.0,              # 1 hour timeout
    retry_policy={
        "max_attempts": 3,
        "delay": 1.0
    },
    state_storage="memory",      # or "redis", "database"
    storage_config={             # Storage-specific configuration
        # For Redis:
        "redis_client": redis_client,
        "key_prefix": "saga:",
        # For Database:
        "db_pool": db_pool,
        "table_name": "saga_states"
    },
    enable_monitoring=True
)
```

### Saga Step Settings

```python
# Step configuration
SagaStepNode(
    step_name="critical_operation",
    idempotent=True,             # Prevent duplicate execution
    retry_on_failure=True,
    max_retries=3,
    retry_delay=1.0,             # Exponential backoff
    timeout=300.0,               # 5 minutes
    compensation_timeout=600.0,   # 10 minutes for compensation
    compensation_retries=5
)
```

## Error Handling

### Handling Step Failures

```python
# Execute saga with error handling
result = saga.execute(operation="execute_saga")

if result["status"] == "failed":
    failed_step = result["failed_step"]
    error_msg = result["error"]

    # Check compensation status
    compensation = result["compensation"]
    if compensation["status"] == "compensated":
        print("All steps successfully compensated")
    elif compensation["status"] == "partial_compensation":
        print(f"Compensation errors: {compensation['compensation_errors']}")
```

### Manual Compensation

```python
# Trigger manual compensation
result = saga.execute(operation="compensate")

for error in result.get("compensation_errors", []):
    print(f"Failed to compensate {error['step']}: {error['error']}")
    # Handle manual cleanup
```

## Testing Patterns

### Test Saga Execution

```python
def test_saga_happy_path():
    saga = SagaCoordinatorNode()

    # Create and configure saga
    saga.execute(operation="create_saga", saga_name="test_saga")

    # Add test steps
    saga.execute(
        operation="add_step",
        name="step1",
        node_id="TestNode1",
        compensation_node_id="CompNode1"
    )

    # Execute
    result = saga.execute(operation="execute_saga")
    assert result["status"] == "success"
```

### Test Compensation

```python
def test_saga_compensation():
    saga = SagaCoordinatorNode()

    # Setup saga with failing step
    saga.execute(operation="create_saga")

    # Add steps where second will fail
    saga.execute(operation="add_step", name="success_step", node_id="Node1")
    saga.execute(operation="add_step", name="fail_step", node_id="FailNode")

    # Execute and verify compensation
    result = saga.execute(operation="execute_saga")
    assert result["status"] == "failed"
    assert result["compensation"]["status"] in ["compensated", "partial_compensation"]
```

## Best Practices

1. **Always define compensations** - Every step should have a compensation action
2. **Make steps idempotent** - Prevent issues from retries or resume operations
3. **Keep steps atomic** - Each step should be a single, coherent operation
4. **Log step execution** - Enable monitoring for production debugging
5. **Test compensation paths** - Ensure compensations work correctly
6. **Handle partial failures** - Plan for compensation failures
7. **Use appropriate timeouts** - Set realistic timeouts for steps and compensations

## Integration Examples

### With Database Operations

```python
from kailash.nodes.data import SQLDatabaseNode

# Create database step with compensation
class DatabaseSagaStep(SagaStepNode):
    def __init__(self, connection_string, **kwargs):
        super().__init__(**kwargs)
        self.db = SQLDatabaseNode(connection_string=connection_string)

    def _process_forward(self, inputs, context):
        # Insert order
        result = self.db.execute(
            query="INSERT INTO orders (id, customer_id, total) VALUES (?, ?, ?)",
            params=[context["order_id"], context["customer_id"], inputs["data"]["amount"]]
        )
        return {"rows_affected": result["rows_affected"]}

    def _compensate_action(self, inputs, context, execution_state):
        # Delete order
        result = self.db.execute(
            query="DELETE FROM orders WHERE id = ?",
            params=[context["order_id"]]
        )
        return {"rows_deleted": result["rows_affected"]}
```

### With External APIs

```python
from kailash.nodes.api import HTTPRequestNode

# API call with compensation
class APICallSagaStep(SagaStepNode):
    def __init__(self, base_url, **kwargs):
        super().__init__(**kwargs)
        self.api = HTTPRequestNode(base_url=base_url)

    def _process_forward(self, inputs, context):
        # Create resource
        response = self.api.execute(
            method="POST",
            endpoint="/resources",
            json_data=inputs["data"]
        )
        return {"resource_id": response["data"]["id"]}

    def _compensate_action(self, inputs, context, execution_state):
        # Delete resource
        resource_id = execution_state["result"]["resource_id"]
        response = self.api.execute(
            method="DELETE",
            endpoint=f"/resources/{resource_id}"
        )
        return {"deleted": True}
```

## See Also

- [Transaction Monitoring](048-transaction-monitoring.md)
- [Enterprise Resilience Patterns](046-resilience-patterns.md)
- [Workflow Patterns](../workflows/)
- [Production Patterns](../enterprise/production-patterns.md)
