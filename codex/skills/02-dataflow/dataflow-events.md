---
name: dataflow-events
description: "DataFlow write event emission and Core SDK EventBus integration. Use when asking about 'DataFlow events', 'on_model_change', 'write events', 'EventBus', 'event-driven DataFlow', 'WRITE_OPERATIONS', or 'DataFlowEventMixin'."
---

# DataFlow Events

Automatic write event emission via Core SDK EventBus, enabling event-driven architectures with DataFlow models.

## Quick Reference

| Feature      | Details                                                                                                |
| ------------ | ------------------------------------------------------------------------------------------------------ |
| Event bus    | `db.event_bus` (Core SDK `InMemoryEventBus`)                                                           |
| Subscribe    | `db.on_model_change("User", handler)`                                                                  |
| Event format | `dataflow.{Model}.{operation}`                                                                         |
| Operations   | 8 WRITE_OPERATIONS: create, update, delete, upsert, bulk_create, bulk_update, bulk_delete, bulk_upsert |
| Overhead     | Negligible when no subscribers (single dict lookup + early return)                                     |
| Emission     | Fire-and-forget (never blocks write path)                                                              |

## Subscribing to Write Events

```python
db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: str
    name: str

await db.initialize()

# Subscribe to all write events for User
def on_user_change(event):
    print(f"User changed: {event.event_type}")
    print(f"  Operation: {event.payload['operation']}")
    print(f"  Record ID: {event.payload['record_id']}")

sub_ids = db.on_model_change("User", on_user_change)
# Returns 8 subscription IDs (one per WRITE_OPERATIONS)

# Now writes emit events
await db.express.create("User", {"name": "Alice"})
# Prints: User changed: dataflow.User.create
#         Operation: create
#         Record ID: <id>
```

## Event Types

Events follow the pattern `dataflow.{ModelName}.{operation}`:

| Event Type                  | Trigger                               |
| --------------------------- | ------------------------------------- |
| `dataflow.User.create`      | `db.express.create("User", ...)`      |
| `dataflow.User.update`      | `db.express.update("User", ...)`      |
| `dataflow.User.delete`      | `db.express.delete("User", ...)`      |
| `dataflow.User.upsert`      | `db.express.upsert("User", ...)`      |
| `dataflow.User.bulk_create` | `db.express.bulk_create("User", ...)` |
| `dataflow.User.bulk_update` | `db.express.bulk_update("User", ...)` |
| `dataflow.User.bulk_delete` | `db.express.bulk_delete("User", ...)` |
| `dataflow.User.bulk_upsert` | `db.express.bulk_upsert("User", ...)` |

## Event Payload

```python
{
    "model": "User",
    "operation": "create",
    "record_id": "user-001",  # or None for bulk operations
}
```

## Direct EventBus Access

```python
# Subscribe to specific event types directly
db.event_bus.subscribe("dataflow.User.create", handler)
db.event_bus.subscribe("dataflow.Order.delete", handler)
```

## Integration with Nexus

DataFlow events bridge to Nexus EventBus via `app.integrate_dataflow(db)`:

```python
from nexus import Nexus

app = Nexus()
app.integrate_dataflow(db)

@app.on_event("dataflow.User.create")
async def on_user_created(event):
    await send_welcome_email(event.payload["record_id"])
```

See `nexus-eventbus-phase2.md` for details.

## Integration with DerivedModelEngine

The `on_source_change` refresh mode subscribes to all 8 WRITE_OPERATIONS for each source model. See `dataflow-derived-models.md` for details.

## Design Notes

- Events are emitted **after** successful write operations (not before)
- Emission is fire-and-forget -- failures in event handlers never break the write path
- No wildcard subscriptions (R1-1 compliance) -- explicit event types only
- The `WRITE_OPERATIONS` constant is the single source of truth for operation names

## Source Code

- the dataflow package (`src/dataflow/core/events.py`) -- DataFlowEventMixin, WRITE_OPERATIONS
- the dataflow package (`tests/unit/features/test_dataflow_events.py`) -- Unit tests
