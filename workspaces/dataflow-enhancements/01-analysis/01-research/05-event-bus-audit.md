# Event Bus Audit

## Source

- `src/kailash/middleware/communication/event_bus.py` (abstract base, ~108 lines)
- `src/kailash/middleware/communication/domain_event.py` (~114 lines)
- `src/kailash/middleware/communication/backends/memory.py` (~180 lines)

## DomainEvent Dataclass

```python
@dataclass
class DomainEvent:
    event_type: str                    # e.g., "order.created"
    payload: Dict[str, Any]            # JSON-serializable data
    correlation_id: str                # UUID, auto-generated
    timestamp: datetime                # UTC, auto-generated
    actor: Optional[str]               # Who caused the event
    schema_version: str = "1.0"        # Payload schema version
```

- Validates non-empty event_type, dict payload, non-empty correlation_id, timezone-aware timestamp.
- Has `to_dict()` / `from_dict()` (EATP SDK convention).

## EventBus ABC

Abstract base with three methods:

- `publish(event: DomainEvent) -> None`
- `subscribe(event_type: str, handler: Callable[[DomainEvent], None]) -> str`
- `unsubscribe(subscription_id: str) -> None`

Exception hierarchy: `EventBusError` -> `PublishError`, `SubscriptionError`.

## InMemoryEventBus

Thread-safe, bounded implementation:

- Uses `threading.Lock` (not RLock).
- Bounded subscriber list: `max_subscribers = 10,000`.
- Handlers invoked synchronously in subscription order.
- Handler exceptions are logged but don't stop other handlers (fail-open per handler).
- Snapshot-under-lock pattern: handlers copied under lock, invoked outside lock.

### CRITICAL FINDING: No Wildcard/Pattern Subscription

The `InMemoryEventBus` does **exact event_type matching only**. The `publish()` method looks up `self._subscribers.get(event.event_type)` -- an exact dict lookup.

The architecture document proposes:

```python
def on_model_change(self, model_name: str, handler: Callable) -> None:
    self._event_bus.subscribe(f"dataflow.{model_name}.*", handler)
```

This **will not work**. Subscribing to `"dataflow.Order.*"` will only receive events with the exact type `"dataflow.Order.*"` -- not `"dataflow.Order.create"` or `"dataflow.Order.update"`.

### Options to Fix

1. **Subscribe to each specific event type** -- `subscribe("dataflow.Order.create", handler)`, `subscribe("dataflow.Order.update", handler)`, etc. (6-8 subscriptions per source model per derived model).
2. **Add wildcard/glob matching to InMemoryEventBus** -- check subscribers against a pattern. More elegant but modifies Core SDK code.
3. **Use a pattern-aware publish** -- iterate all subscriber keys and fnmatch/glob against the event type.

Option 1 is the safest -- no Core SDK changes, works immediately. The `on_model_change()` convenience method would register multiple subscriptions internally.

## DataFlow Integration Status

Confirmed: DataFlow (the package) has ZERO references to `EventBus`, `DomainEvent`, `InMemoryEventBus`, or any event-related imports. No event emission happens anywhere in DataFlow today.

## Other EventBus Files

- `events.py` (~16K) -- Event management system with async subscribe, but this is a higher-level construct with subscriber IDs and async callbacks. Different from the base EventBus.
- `api_gateway.py` (~32K) -- API gateway event handling.
- `realtime.py` (~29K) -- Real-time event streaming.

These are more complex systems that DataFlow does NOT need. The base `EventBus` + `InMemoryEventBus` is the correct integration point.

## Import Path

```python
from kailash.middleware.communication.domain_event import DomainEvent
from kailash.middleware.communication.event_bus import EventBus
from kailash.middleware.communication.backends.memory import InMemoryEventBus
```

`kailash-dataflow` already depends on `kailash` (Core SDK), so no new package dependency.

## Risk for TSG-201

Medium risk. The event infrastructure exists and is well-implemented, but:

1. No wildcard subscription -- requires workaround in the DataFlowEventMixin
2. Synchronous handler invocation -- derived model recompute is expensive, must not block the write path. Need to dispatch to async task or background thread.
3. 8 write node classes need modification -- manageable but must be done carefully to avoid breaking existing behavior.
