---
name: nexus-eventbus-phase2
description: "Nexus EventBus (janus.Queue), Phase 2 APIs (@app.on_event, @app.scheduled, app.emit), DataFlow event bridge, NexusFile, and BackgroundService. Use when asking about 'EventBus', 'on_event', 'scheduled handler', 'NexusFile', 'event bridge', 'integrate_dataflow', 'BackgroundService', or 'janus queue'."
---

# Nexus EventBus and Phase 2 APIs

Event-driven architecture with janus.Queue bridging sync/async boundaries, plus scheduled tasks, file handling, and DataFlow integration.

## Quick Reference

| Feature         | API                                                                |
| --------------- | ------------------------------------------------------------------ |
| Event handler   | `@app.on_event("event.type")`                                      |
| Scheduled task  | `@app.scheduled("5m")` or `@app.scheduled("", cron="0 */6 * * *")` |
| Emit event      | `app.emit("event.type", payload)`                                  |
| File handling   | `NexusFile` (auto-adapts to transport)                             |
| DataFlow bridge | `app.integrate_dataflow(db)`                                       |
| Event history   | `app.get_events(session_id="...")` (bounded 256)                   |

## EventBus Architecture

The EventBus uses `janus.Queue` (bounded 256) to bridge sync publishers (MCP thread) and async subscribers (Nexus HTTP transport event loop):

```
Sync Thread (MCP)     janus.Queue      Async Loop (Nexus HTTP)
   publish() -------> [bounded 256] ----> dispatch_loop()
                                             |
                                      fan-out to subscribers
```

### subscribe_filtered

```python
# Subscribe to events matching a predicate — returns an asyncio.Queue
q = bus.subscribe_filtered(
    predicate=lambda e: e.event_type.startswith("dataflow.")
)
# Consume matching events from the queue
event = await q.get()
```

## Phase 2 APIs

### @app.on_event()

React to events (both custom and DataFlow-bridged):

```python
from nexus import Nexus

app = Nexus()

@app.on_event("user.created")
async def on_user_created(event):
    await send_welcome_email(event.payload["user_id"])

@app.on_event("order.completed")
async def on_order_completed(event):
    await update_inventory(event.payload)
```

### @app.scheduled()

Register periodic tasks:

```python
@app.scheduled("5m")  # Every 5 minutes
async def cleanup_sessions():
    await session_store.purge_expired()

@app.scheduled("", cron="0 2 * * *")  # Daily at 2am
async def generate_reports():
    await report_engine.run()
```

Scheduled handlers run via `SchedulerBackgroundService`.

### app.emit()

Fire custom events:

```python
@app.handler("create_order")
async def create_order(customer_id: str, items: list) -> dict:
    order = await db.express.create("Order", {"customer_id": customer_id})
    app.emit("order.created", {"order_id": order["id"], "customer_id": customer_id})
    return order
```

## DataFlow Event Bridge

Connect DataFlow write events to Nexus handlers:

```python
from dataflow import DataFlow
from nexus import Nexus

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: str
    name: str
    email: str

app = Nexus()
app.integrate_dataflow(db)

# Now DataFlow write events appear as Nexus events
@app.on_event("dataflow.User.create")
async def on_user_created(event):
    user_id = event.payload["record_id"]
    await send_welcome_email(user_id)

@app.on_event("dataflow.User.delete")
async def on_user_deleted(event):
    await cleanup_user_data(event.payload["record_id"])
```

`integrate_dataflow()` bridges all 8 WRITE_OPERATIONS per model from the DataFlow EventBus to the Nexus EventBus.

## NexusFile

Cross-transport file abstraction. Handlers receive `NexusFile` regardless of how the file was sent:

```python
from nexus import Nexus, NexusFile

@app.handler("upload_document")
async def upload_document(file: NexusFile, title: str = "Untitled") -> dict:
    return {
        "filename": file.filename,
        "size": file.size,
        "content_type": file.content_type,
    }
```

### Transport Adaptation

| Transport | Input            | Conversion                                |
| --------- | ---------------- | ----------------------------------------- |
| HTTP      | Multipart upload | `NexusFile.from_upload_file(upload_file)` |
| CLI       | File path        | `NexusFile.from_path("/path/to/file")`    |
| MCP       | Base64 string    | `NexusFile.from_base64(data, filename)`   |
| WebSocket | Binary frame     | `NexusFile(data=bytes)`                   |

## BackgroundService ABC

Base class for internal Nexus services (not client-facing transports):

```python
from nexus.background import BackgroundService

class BackgroundService(ABC):
    """Internal services: scheduler, metrics, cleanup."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this background service."""
        ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    def is_healthy(self) -> bool: ...
```

Built-in services include `SchedulerBackgroundService` for `@app.scheduled()` handlers.

## Event History

Events are stored in a bounded history (256 most recent):

```python
# Get recent events
events = app.get_events()

# Filter by session
session_events = app.get_events(session_id="session_123")
```

## Source Code

- `packages/kailash-nexus/src/nexus/events.py` -- EventBus (janus.Queue, subscribe_filtered)
- `packages/kailash-nexus/src/nexus/core.py` -- Phase 2 APIs (on_event, scheduled, emit)
- `packages/kailash-nexus/src/nexus/bridges/dataflow.py` -- DataFlow event bridge
- `packages/kailash-nexus/src/nexus/files.py` -- NexusFile
- `packages/kailash-nexus/src/nexus/background.py` -- BackgroundService ABC
