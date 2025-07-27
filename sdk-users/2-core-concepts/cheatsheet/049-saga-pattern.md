# Saga Pattern Cheatsheet

Quick reference for implementing distributed transactions using the Saga pattern: orchestration, compensation, and state management.

## Saga Coordinator - Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create saga coordinator workflow
workflow = WorkflowBuilder()
workflow.add_node("SagaCoordinatorNode", "saga", {
    "operation": "create_saga",
    "saga_name": "order_processing",
    "timeout": 600.0,
    "context": {"user_id": "user123", "order_id": "order456"}
})

# Add step configurations
workflow.add_node("PythonCodeNode", "add_steps", {
    "code": """
# Configure saga steps
steps_config = [
    {
        "name": "validate_order",
        "node_id": "ValidationNode",
        "parameters": {"check_inventory": True},
        "compensation_node_id": "CancelValidationNode"
    },
    {
        "name": "charge_payment",
        "node_id": "PaymentNode",
        "parameters": {"amount": 100.0},
        "compensation_node_id": "RefundPaymentNode"
    }
]
result = {"steps": steps_config}
"""
})

# Connect and execute
workflow.add_connection("saga", "saga_id", "add_steps", "saga_id")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(f"Saga completed: {results['saga']['status']}")
```

## Saga Step - Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create a saga step workflow
step_workflow = WorkflowBuilder()
step_workflow.add_node("SagaStepNode", "payment_step", {
    "step_name": "process_payment",
    "idempotent": True,
    "max_retries": 3,
    "operation": "execute",
    "execution_id": "exec_123",
    "saga_context": {"order_id": "order_456"},
    "action_type": "charge",
    "data": {"amount": 100.0, "currency": "USD"}
})

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(step_workflow.build())

# If needed, create compensation workflow
compensation_workflow = WorkflowBuilder()
compensation_workflow.add_node("SagaStepNode", "compensate_step", {
    "step_name": "process_payment",
    "operation": "compensate",
    "execution_id": "exec_123"
})

# Execute compensation if needed
comp_results, comp_run_id = runtime.execute(compensation_workflow.build())
```

## Common Patterns

### Pattern 1: Order Processing Saga

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create order processing saga workflow
order_workflow = WorkflowBuilder()

# Initialize saga
order_workflow.add_node("SagaCoordinatorNode", "order_saga", {
    "saga_name": "order_processing",
    "operation": "create_saga",
    "context": {
        "order_id": "order_789",
        "customer_id": "cust_123",
        "items": [{"sku": "ITEM1", "qty": 2}],
        "total_amount": 150.00
    }
})

# Add saga steps configuration
order_workflow.add_node("PythonCodeNode", "configure_steps", {
    "code": """
# Define all saga steps
steps = [
    {
        "name": "check_inventory",
        "node_id": "InventoryCheckNode",
        "parameters": {"output_key": "inventory_status"},
        "compensation_node_id": "ReleaseInventoryNode"
    },
    {
        "name": "reserve_inventory",
        "node_id": "InventoryReserveNode",
        "parameters": {"output_key": "reservation_id"},
        "compensation_node_id": "CancelReservationNode"
    },
    {
        "name": "process_payment",
        "node_id": "PaymentProcessNode",
        "parameters": {"output_key": "payment_id"},
        "compensation_node_id": "RefundPaymentNode"
    },
    {
        "name": "create_shipment",
        "node_id": "ShipmentNode",
        "parameters": {"output_key": "tracking_number"},
        "compensation_node_id": "CancelShipmentNode"
    }
]
result = {"saga_steps": steps}
"""
})

# Execute saga
order_workflow.add_node("SagaCoordinatorNode", "execute_saga", {
    "operation": "execute_saga"
})

# Connect workflow
order_workflow.add_connection("order_saga", "saga_id", "configure_steps", "saga_id")
order_workflow.add_connection("configure_steps", "saga_steps", "execute_saga", "steps")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(order_workflow.build())

if results["execute_saga"]["status"] == "success":
    print(f"Order processed: {results['execute_saga']['context']}")
else:
    print(f"Order failed at: {results['execute_saga']['failed_step']}")
    print(f"Compensation: {results['execute_saga']['compensation']}")
```

### Pattern 2: Custom Saga Step

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.base import Node, NodeParameter

class PaymentSagaStepNode(Node):
    """Custom payment processing node with compensation."""

    amount = NodeParameter(type=float, required=True)
    customer_id = NodeParameter(type=str, required=True)
    operation = NodeParameter(type=str, default="execute")

    def run(self, **kwargs):
        """Process payment or compensation."""
        if self.operation == "execute":
            # Process payment forward action
            payment_result = {
                "payment_id": f"pay_{self.customer_id}_{self.amount}",
                "status": "charged",
                "amount": self.amount,
                "timestamp": "2024-01-01T00:00:00Z"
            }
            return {"result": payment_result}
        elif self.operation == "compensate":
            # Refund payment compensation
            refund_result = {
                "refund_id": f"ref_pay_{self.customer_id}_{self.amount}",
                "status": "refunded",
                "amount": self.amount,
                "original_payment": f"pay_{self.customer_id}_{self.amount}"
            }
            return {"result": refund_result}

# Use custom step in workflow
payment_workflow = WorkflowBuilder()
payment_workflow.add_node("PaymentSagaStepNode", "payment_step", {
    "operation": "execute",
    "customer_id": "cust_123",
    "amount": 99.99
})

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(payment_workflow.build())
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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create resumable saga workflow
resumable_workflow = WorkflowBuilder()

# Configure saga with Redis storage
resumable_workflow.add_node("SagaCoordinatorNode", "resumable_saga", {
    "state_storage": "redis",
    "storage_config": {
        "host": "localhost",
        "port": 6379,
        "key_prefix": "saga:prod:"
    },
    "saga_id": "resumable_saga_123",
    "operation": "load_saga"
})

# Check if saga exists and resume or create
resumable_workflow.add_node("SwitchNode", "check_status", {
    "condition": "result.status == 'success'"
})

# Resume path
resumable_workflow.add_node("SagaCoordinatorNode", "resume_saga", {
    "operation": "resume"
})

# Create new path
resumable_workflow.add_node("SagaCoordinatorNode", "create_saga", {
    "operation": "create_saga",
    "saga_name": "new_resumable_saga"
})

# Connect workflow
resumable_workflow.add_connection("resumable_saga", "result", "check_status", "result")
resumable_workflow.add_connection("check_status", "true_output", "resume_saga", "saga_context")
resumable_workflow.add_connection("check_status", "false_output", "create_saga", "saga_context")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(resumable_workflow.build())
```

### Pattern 5: Saga State Management

```python
# List all running sagas
manager_workflow = WorkflowBuilder()
manager_workflow.add_node("SagaCoordinatorNode", "list_sagas", {
    "operation": "list_sagas",
    "filter": {"state": "running"}
})

# Process each saga
manager_workflow.add_node("PythonCodeNode", "process_sagas", {
    "code": """
import time

# Process saga list
saga_list = parameters.get('saga_list', {})
stuck_sagas = []

for saga_id in saga_list.get('saga_ids', []):
    # Would check saga status in real implementation
    # Here we simulate checking for stuck sagas
    stuck_sagas.append({
        "saga_id": saga_id,
        "action": "cancel",
        "reason": "exceeded_timeout"
    })

result = {
    "count": saga_list.get('count', 0),
    "stuck_sagas": stuck_sagas
}
"""
})

# Connect workflow
manager_workflow.add_connection("list_sagas", "result", "process_sagas", "saga_list")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(manager_workflow.build())

print(f"Found {results['process_sagas']['result']['count']} running sagas")
for stuck in results['process_sagas']['result']['stuck_sagas']:
    print(f"Saga {stuck['saga_id']} stuck, triggering {stuck['action']}")
```

## Configuration Reference

### Saga Coordinator Settings

```python
# Saga configuration in workflow
config_workflow = WorkflowBuilder()
config_workflow.add_node("SagaCoordinatorNode", "business_saga", {
    "saga_name": "business_process",
    "timeout": 3600.0,              # 1 hour timeout
    "retry_policy": {
        "max_attempts": 3,
        "delay": 1.0
    },
    "state_storage": "memory",      # or "redis", "database"
    "storage_config": {             # Storage-specific configuration
        # For Redis:
        "host": "localhost",
        "port": 6379,
        "key_prefix": "saga:",
        # For Database:
        "connection_string": "postgresql://user:pass@localhost:5432/saga_db",
        "table_name": "saga_states"
    },
    "enable_monitoring": True
})
```

### Saga Step Settings

```python
# Step configuration in workflow
step_config_workflow = WorkflowBuilder()
step_config_workflow.add_node("SagaStepNode", "critical_operation", {
    "step_name": "critical_operation",
    "idempotent": True,             # Prevent duplicate execution
    "retry_on_failure": True,
    "max_retries": 3,
    "retry_delay": 1.0,             # Exponential backoff
    "timeout": 300.0,               # 5 minutes
    "compensation_timeout": 600.0,   # 10 minutes for compensation
    "compensation_retries": 5
})
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
    # Create test saga workflow
    test_workflow = WorkflowBuilder()

    # Create and configure saga
    test_workflow.add_node("SagaCoordinatorNode", "test_saga", {
        "operation": "create_saga",
        "saga_name": "test_saga"
    })

    # Add test steps
    test_workflow.add_node("PythonCodeNode", "add_test_step", {
        "code": """
result = {
    "step_config": {
        "name": "step1",
        "node_id": "TestNode1",
        "compensation_node_id": "CompNode1"
    }
}
"""
    })

    # Execute saga
    test_workflow.add_node("SagaCoordinatorNode", "execute_test", {
        "operation": "execute_saga"
    })

    # Connect workflow
    test_workflow.add_connection("test_saga", "saga_id", "add_test_step", "saga_id")
    test_workflow.add_connection("add_test_step", "step_config", "execute_test", "step")

    # Execute
    runtime = LocalRuntime()
    results, run_id = runtime.execute(test_workflow.build())
    assert results["execute_test"]["status"] == "success"
```

### Test Compensation

```python
def test_saga_compensation():
    # Create compensation test workflow
    comp_workflow = WorkflowBuilder()

    # Setup saga with failing step
    comp_workflow.add_node("SagaCoordinatorNode", "create_comp_saga", {
        "operation": "create_saga"
    })

    # Configure steps where second will fail
    comp_workflow.add_node("PythonCodeNode", "configure_failing_steps", {
        "code": """
result = {
    "steps": [
        {"name": "success_step", "node_id": "Node1"},
        {"name": "fail_step", "node_id": "FailNode"}
    ]
}
"""
    })

    # Execute and verify compensation
    comp_workflow.add_node("SagaCoordinatorNode", "execute_with_failure", {
        "operation": "execute_saga"
    })

    # Connect workflow
    comp_workflow.add_connection("create_comp_saga", "saga_id", "configure_failing_steps", "saga_id")
    comp_workflow.add_connection("configure_failing_steps", "steps", "execute_with_failure", "steps")

    # Execute
    runtime = LocalRuntime()
    results, run_id = runtime.execute(comp_workflow.build())
    assert results["execute_with_failure"]["status"] == "failed"
    assert results["execute_with_failure"]["compensation"]["status"] in ["compensated", "partial_compensation"]
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
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create database saga step workflow
db_saga_workflow = WorkflowBuilder()

# Forward action - insert order
db_saga_workflow.add_node("SQLDatabaseNode", "insert_order", {
    "connection_string": "postgresql://user:pass@localhost:5432/orders_db",
    "query": "INSERT INTO orders (id, customer_id, total) VALUES (:order_id, :customer_id, :amount)",
    "parameters": {
        "order_id": "order_123",
        "customer_id": "cust_456",
        "amount": 100.0
    }
})

# Compensation action - delete order
db_saga_workflow.add_node("SQLDatabaseNode", "delete_order", {
    "connection_string": "postgresql://user:pass@localhost:5432/orders_db",
    "query": "DELETE FROM orders WHERE id = :order_id",
    "parameters": {
        "order_id": "order_123"
    }
})

# Conditional execution based on saga state
db_saga_workflow.add_node("SwitchNode", "check_compensation", {
    "condition": "parameters.get('compensate', False)"
})

# Connect workflow
db_saga_workflow.add_connection("check_compensation", "false_output", "insert_order", "input")
db_saga_workflow.add_connection("check_compensation", "true_output", "delete_order", "input")
```

### With External APIs

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# API saga step workflow
api_saga_workflow = WorkflowBuilder()

# Forward action - create resource
api_saga_workflow.add_node("HTTPRequestNode", "create_resource", {
    "url": "https://api.example.com/resources",
    "method": "POST",
    "headers": {"Content-Type": "application/json"},
    "json_data": {
        "name": "New Resource",
        "type": "saga_managed"
    }
})

# Extract resource ID
api_saga_workflow.add_node("PythonCodeNode", "extract_id", {
    "code": """
response = parameters.get('api_response', {})
resource_id = response.get('data', {}).get('id', 'unknown')
result = {'resource_id': resource_id}
"""
})

# Compensation action - delete resource
api_saga_workflow.add_node("HTTPRequestNode", "delete_resource", {
    "url": "https://api.example.com/resources/{resource_id}",
    "method": "DELETE",
    "headers": {"Authorization": "Bearer token"}
})

# Connect workflow
api_saga_workflow.add_connection("create_resource", "result", "extract_id", "api_response")
api_saga_workflow.add_connection("extract_id", "resource_id", "delete_resource", "resource_id")
```

## See Also

- [Transaction Monitoring](048-transaction-monitoring.md)
- [Enterprise Resilience Patterns](046-resilience-patterns.md)
- [Workflow Patterns](../workflows/)
- [Production Patterns](../enterprise/production-patterns.md)
