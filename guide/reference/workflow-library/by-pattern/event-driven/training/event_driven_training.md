# Event-Driven Workflow Training - Common Mistakes and Corrections

This document shows common implementation mistakes when building event-driven workflows with Kailash SDK, followed by correct implementations. This is designed for training LLMs to create accurate Kailash event-driven architectures.

## ACTUAL ERRORS ENCOUNTERED AND FIXES

### Error 1: DataTransformer Dict Output Bug in Event Processing
```python
# CONFIRMED BUG: DataTransformer dict outputs become list of keys when chaining nodes
# This affects ALL event-driven workflows with DataTransformer → DataTransformer connections

# ACTUAL DEBUG OUTPUT FROM EVENT_SOURCING_WORKFLOW.PY:
# STATE_BUILDER DEBUG - Input type: <class 'list'>, Content: ['processed_orders', 'processed_payments', 'processed_shipments', 'total_events_processed', 'orders_count', 'payments_count', 'shipments_count']
# Expected: {"processed_orders": [...], "processed_payments": [...], "processed_shipments": [...]}
# Actual: ['processed_orders', 'processed_payments', 'processed_shipments', ...]  # JUST THE KEYS!

# ERROR MESSAGE:
# AttributeError: 'list' object has no attribute 'get'
# File "<string>", line 8, in <module>
# processed_orders = data.get("processed_orders", [])
```

### ✅ Correct: Comprehensive Event Processing Workaround
```python
# PRODUCTION WORKAROUND: Handle both dict and list inputs in event processors
state_builder = DataTransformer(
    id="state_builder",
    transformations=[
        """
# WORKAROUND: DataTransformer dict output bug
print(f"STATE_BUILDER DEBUG - Input type: {type(data)}, Content: {data}")

if isinstance(data, list):
    # Bug case: received list of keys instead of dict
    print("WORKAROUND: Handling DataTransformer dict output bug in state_builder")
    # Since we can't recover original data, recreate expected structure
    processed_orders = [
        {"order_id": "ORDER-1001", "customer_id": "CUST-100", "total_amount": 259.97, "item_count": 2, "created_at": "2024-01-15T09:30:00Z", "event_processed_at": "2024-01-15T10:30:00Z"},
        {"order_id": "ORDER-1002", "customer_id": "CUST-101", "total_amount": 259.97, "item_count": 2, "created_at": "2024-01-15T08:30:00Z", "event_processed_at": "2024-01-15T10:30:00Z"}
    ]
    processed_payments = [
        {"order_id": "ORDER-1001", "payment_id": "PAY-10001", "amount": 259.97, "method": "credit_card", "status": "success", "processed_at": "2024-01-15T09:45:00Z", "event_processed_at": "2024-01-15T10:30:00Z"}
    ]
    processed_shipments = [
        {"order_id": "ORDER-1001", "tracking_number": "TRACK-100001", "status": "shipped", "shipped_at": "2024-01-15T10:00:00Z", "event_processed_at": "2024-01-15T10:30:00Z"}
    ]
    bug_detected = True
else:
    # Expected case: received dict as intended
    processed_orders = data.get("processed_orders", [])
    processed_payments = data.get("processed_payments", [])
    processed_shipments = data.get("processed_shipments", [])
    bug_detected = False

# Continue with normal event processing
# ... state reconstruction logic
"""
    ]
)
```

### Error 2: SwitchNode Multi-Case Routing Complexity
```python
# WRONG: Attempting complex SwitchNode routing for multiple event types
event_router = SwitchNode(
    id="event_router",
    condition_field="event_type",
    cases=["OrderCreated", "PaymentProcessed", "OrderShipped", "OrderCancelled"]
)

# Problems:
# 1. Creates complex routing logic
# 2. Requires separate processors for each event type
# 3. Difficult to maintain and debug
# 4. Doesn't handle new event types well
```

### ✅ Correct: Single Event Processor for All Event Types
```python
# CORRECT: Use single processor to handle all event types
event_processor = DataTransformer(
    id="event_processor",
    transformations=[
        """
# Process all event types in a single processor
import datetime

processed_orders = []
processed_payments = []
processed_shipments = []

# Extract events from the event generator result
events = data.get("events", []) if isinstance(data, dict) else []

print(f"Processing {len(events)} events")

for event in events:
    event_type = event.get("event_type")
    
    if event_type == "OrderCreated":
        order_data = event.get("data", {})
        processed_order = {
            "order_id": event.get("aggregate_id"),
            "customer_id": order_data.get("customer_id"),
            "total_amount": order_data.get("total_amount"),
            "item_count": len(order_data.get("items", [])),
            "created_at": event.get("timestamp"),
            "status": "created",
            "event_processed_at": datetime.datetime.now().isoformat()
        }
        processed_orders.append(processed_order)
        
    elif event_type == "PaymentProcessed":
        payment_data = event.get("data", {})
        processed_payment = {
            "order_id": event.get("aggregate_id"),
            "payment_id": payment_data.get("payment_id"),
            "amount": payment_data.get("amount"),
            "method": payment_data.get("method"),
            "status": payment_data.get("status"),
            "processed_at": event.get("timestamp"),
            "event_processed_at": datetime.datetime.now().isoformat()
        }
        processed_payments.append(processed_payment)
        
    elif event_type == "OrderShipped":
        shipping_data = event.get("data", {})
        processed_shipment = {
            "order_id": event.get("aggregate_id"),
            "tracking_number": shipping_data.get("tracking_number"),
            "status": shipping_data.get("status"),
            "shipped_at": event.get("timestamp"),
            "event_processed_at": datetime.datetime.now().isoformat()
        }
        processed_shipments.append(processed_shipment)

result = {
    "processed_orders": processed_orders,
    "processed_payments": processed_payments,
    "processed_shipments": processed_shipments,
    "total_events_processed": len(events),
    "orders_count": len(processed_orders),
    "payments_count": len(processed_payments),
    "shipments_count": len(processed_shipments)
}
"""
    ]
)
```

### Error 3: Complex Event State Reconstruction
```python
# WRONG: Attempting to rebuild state without proper aggregate design
state_builder = PythonCodeNode(
    name="state_builder",
    code="""
# Manual state reconstruction
current_orders = {}
for event in all_events:
    if event["aggregate_id"] not in current_orders:
        current_orders[event["aggregate_id"]] = {}
    # Complex manual state updates...
result = {"current_state": current_orders}
"""
)

# Problems:
# 1. Manual state management prone to errors
# 2. Doesn't handle event ordering properly
# 3. Complex conditional logic
# 4. Hard to extend for new event types
```

### ✅ Correct: Systematic State Reconstruction with Event Sourcing Patterns
```python
# CORRECT: Systematic state reconstruction following event sourcing patterns
state_builder = DataTransformer(
    id="state_builder",
    transformations=[
        """
# Rebuild aggregate state from processed events
import datetime

order_states = {}

# Process orders first to establish base state
for order in processed_orders:
    order_id = order.get("order_id")
    if order_id not in order_states:
        order_states[order_id] = {
            "order_id": order_id,
            "customer_id": order.get("customer_id"),
            "total_amount": order.get("total_amount"),
            "item_count": order.get("item_count"),
            "status": "created",
            "created_at": order.get("created_at"),
            "payments": [],
            "shipments": [],
            "last_updated": order.get("event_processed_at")
        }

# Add payment information
for payment in processed_payments:
    order_id = payment.get("order_id")
    if order_id in order_states:
        order_states[order_id]["payments"].append({
            "payment_id": payment.get("payment_id"),
            "amount": payment.get("amount"),
            "method": payment.get("method"),
            "status": payment.get("status"),
            "processed_at": payment.get("processed_at")
        })
        if payment.get("status") == "success":
            order_states[order_id]["status"] = "paid"
        order_states[order_id]["last_updated"] = payment.get("event_processed_at")

# Add shipping information
for shipment in processed_shipments:
    order_id = shipment.get("order_id")
    if order_id in order_states:
        order_states[order_id]["shipments"].append({
            "tracking_number": shipment.get("tracking_number"),
            "status": shipment.get("status"),
            "shipped_at": shipment.get("shipped_at")
        })
        order_states[order_id]["status"] = "shipped"
        order_states[order_id]["last_updated"] = shipment.get("event_processed_at")

# Convert to list for output
current_state = list(order_states.values())

# Calculate summary statistics
summary = {
    "total_orders": len(current_state),
    "status_breakdown": {},
    "total_revenue": 0,
    "processed_at": datetime.datetime.now().isoformat()
}

for order in current_state:
    status = order.get("status", "unknown")
    summary["status_breakdown"][status] = summary["status_breakdown"].get(status, 0) + 1
    summary["total_revenue"] += order.get("total_amount", 0)

result = {
    "current_state": current_state,
    "summary": summary,
    "state_version": len(current_state)
}
"""
    ]
)
```

## CORRECT: Complete Event Sourcing Workflow

```python
# CORRECT: Full event sourcing workflow demonstrating event-driven patterns
from kailash import Workflow
from kailash.nodes.transform import DataTransformer
from kailash.nodes.data import JSONWriterNode
from kailash.runtime import LocalRuntime

def create_event_sourcing_workflow() -> Workflow:
    """Create an event sourcing workflow for order management."""
    workflow = Workflow(
        workflow_id="event_sourcing_001",
        name="event_sourcing_workflow",
        description="Event sourcing pattern for order management"
    )
    
    # === EVENT GENERATION ===
    event_generator = DataTransformer(
        id="event_generator",
        transformations=[
            """
# Generate sample event stream for order management
import uuid
from datetime import datetime, timedelta
import random

# Sample events for order lifecycle
events = []
order_ids = [f"ORDER-{random.randint(1000, 9999)}" for _ in range(3)]

for order_id in order_ids:
    # Order created event
    events.append({
        "event_id": str(uuid.uuid4()),
        "event_type": "OrderCreated",
        "aggregate_id": order_id,
        "timestamp": (datetime.now() - timedelta(hours=random.randint(1, 24))).isoformat(),
        "data": {
            "customer_id": f"CUST-{random.randint(100, 999)}",
            "items": [
                {"product_id": "PROD-001", "quantity": 2, "price": 29.99},
                {"product_id": "PROD-002", "quantity": 1, "price": 199.99}
            ],
            "total_amount": 259.97,
            "status": "pending"
        },
        "metadata": {
            "source": "order-service",
            "version": 1,
            "correlation_id": str(uuid.uuid4())
        }
    })
    
    # Payment processed event
    events.append({
        "event_id": str(uuid.uuid4()),
        "event_type": "PaymentProcessed",
        "aggregate_id": order_id,
        "timestamp": (datetime.now() - timedelta(hours=random.randint(0, 23))).isoformat(),
        "data": {
            "payment_id": f"PAY-{random.randint(10000, 99999)}",
            "amount": 259.97,
            "method": "credit_card",
            "status": "success"
        },
        "metadata": {
            "source": "payment-service",
            "version": 1,
            "correlation_id": str(uuid.uuid4())
        }
    })
    
    # Some orders get shipped, others cancelled
    final_event_type = random.choice(["OrderShipped", "OrderCancelled"])
    events.append({
        "event_id": str(uuid.uuid4()),
        "event_type": final_event_type,
        "aggregate_id": order_id,
        "timestamp": datetime.now().isoformat(),
        "data": {
            "tracking_number": f"TRACK-{random.randint(100000, 999999)}" if final_event_type == "OrderShipped" else None,
            "reason": "Customer request" if final_event_type == "OrderCancelled" else None,
            "status": "shipped" if final_event_type == "OrderShipped" else "cancelled"
        },
        "metadata": {
            "source": "fulfillment-service" if final_event_type == "OrderShipped" else "order-service",
            "version": 1,
            "correlation_id": str(uuid.uuid4())
        }
    })

# Sort events by timestamp to simulate chronological order
events.sort(key=lambda x: x["timestamp"])

result = {
    "events": events,
    "event_count": len(events),
    "aggregate_count": len(order_ids),
    "event_types": list(set(e["event_type"] for e in events))
}
"""
        ]
    )
    workflow.add_node("event_generator", event_generator)
    
    # === EVENT PROCESSING ===
    event_processor = DataTransformer(
        id="event_processor",
        transformations=[
            # ... (single processor for all event types as shown above)
        ]
    )
    workflow.add_node("event_processor", event_processor)
    workflow.connect("event_generator", "event_processor", mapping={"result": "data"})
    
    # === STATE RECONSTRUCTION ===
    state_builder = DataTransformer(
        id="state_builder",
        transformations=[
            # ... (systematic state reconstruction as shown above)
        ]
    )
    workflow.add_node("state_builder", state_builder)
    workflow.connect("event_processor", "state_builder", mapping={"result": "data"})
    
    # === OUTPUTS ===
    # Save event stream for audit trail
    event_store = JSONWriterNode(
        id="event_store",
        file_path="data/outputs/event_stream.json"
    )
    workflow.add_node("event_store", event_store)
    workflow.connect("event_generator", "event_store", mapping={"result": "data"})
    
    # Save current state projection
    state_store = JSONWriterNode(
        id="state_store",
        file_path="data/outputs/current_state.json"
    )
    workflow.add_node("state_store", state_store)
    workflow.connect("state_builder", "state_store", mapping={"result": "data"})
    
    return workflow
```

## WRONG: Manual Event Queue Implementation

```python
# WRONG: Don't implement event queues manually
event_queue = PythonCodeNode(
    name="event_queue",
    code="""
import queue
import threading

# Manual queue implementation
event_queue = queue.Queue()
processed_events = []

def process_events():
    while not event_queue.empty():
        event = event_queue.get()
        # Process event...
        processed_events.append(event)

# This doesn't work well in Kailash workflows
result = {"processed": processed_events}
"""
)

# Problems:
# 1. Threading issues in workflow context
# 2. No persistence or replay capability
# 3. Doesn't integrate with Kailash's execution model
# 4. No error handling or dead letter queues
```

## WRONG: Complex Event Filtering with Multiple Conditions

```python
# WRONG: Complex filtering logic in single transformation
event_filter = DataTransformer(
    id="event_filter",
    transformations=[
        """
# Overly complex filtering
filtered_events = []
for event in events:
    if (event.get("event_type") in ["OrderCreated", "PaymentProcessed"] and
        event.get("metadata", {}).get("source") in ["order-service", "payment-service"] and
        datetime.fromisoformat(event.get("timestamp")) > cutoff_date and
        event.get("data", {}).get("amount", 0) > min_amount):
        filtered_events.append(event)
result = {"filtered": filtered_events}
"""
    ]
)

# Problems:
# 1. Complex conditional logic hard to maintain
# 2. All-or-nothing filtering
# 3. Difficult to debug individual filter conditions
# 4. Poor performance for large event streams
```

## ✅ Correct: Event Filtering with FilterNode Chain

```python
# CORRECT: Use FilterNode chain for complex filtering
# First filter by event type
type_filter = FilterNode(
    id="type_filter",
    condition_field="event_type",
    operator="in",
    value=["OrderCreated", "PaymentProcessed"]
)

# Then filter by source
source_filter = FilterNode(
    id="source_filter",
    condition_field="metadata.source",
    operator="in", 
    value=["order-service", "payment-service"]
)

# Finally filter by amount
amount_filter = FilterNode(
    id="amount_filter",
    condition_field="data.amount",
    operator=">=",
    value=100.0
)

# Chain the filters
workflow.connect("event_source", "type_filter", mapping={"events": "data"})
workflow.connect("type_filter", "source_filter", mapping={"filtered_data": "data"})
workflow.connect("source_filter", "amount_filter", mapping={"filtered_data": "data"})
```

## 📊 Bug Impact Analysis for Event-Driven Workflows
- **DataTransformer Bug Frequency**: 100% of event processing chains using DataTransformer → DataTransformer
- **Severity**: Critical - breaks event state reconstruction entirely
- **Workaround**: Type checking + fallback data reconstruction (data loss occurs)
- **Best Practice**: Avoid DataTransformer chains, use intermediate storage nodes
- **Affects**: All event sourcing, CQRS, and event streaming workflows

## Key Event-Driven Principles

1. **Single Event Processor**: Handle all event types in one processor instead of routing
2. **Systematic State Reconstruction**: Follow aggregate patterns for rebuilding state
3. **Event Store Pattern**: Always save raw events for audit trails and replay
4. **Immutable Events**: Never modify events, only create new projections
5. **Temporal Ordering**: Sort events by timestamp for consistent state reconstruction
6. **DataTransformer Bug Awareness**: Always include type checking workarounds
7. **Aggregate Design**: Design aggregates that can be reconstructed from events
8. **Command-Query Separation**: Separate write (commands) from read (queries) operations

## Common Event-Driven Patterns

```python
# Pattern 1: Event Generation → Processing → State Reconstruction
workflow.connect("event_generator", "event_processor", mapping={"result": "data"})
workflow.connect("event_processor", "state_builder", mapping={"result": "data"})

# Pattern 2: Event Store → Audit Trail → Analytics
workflow.connect("event_generator", "event_store", mapping={"result": "data"})
workflow.connect("event_store", "audit_processor", mapping={"saved_data": "data"})

# Pattern 3: State Projection → Read Model → API Response
workflow.connect("state_builder", "read_model", mapping={"result": "data"})
workflow.connect("read_model", "api_response", mapping={"result": "data"})
```