# Event Systems Audit

## Brief Claim: "Two separate EventBus systems"

**Verified: YES.** There are two completely independent event systems.

## System 1: Core SDK EventBus

**Location**: `src/kailash/middleware/communication/`

### Files

- `event_bus.py` — Abstract `EventBus` ABC with `publish()`, `subscribe()`, `unsubscribe()`
- `domain_event.py` — `DomainEvent` dataclass
- `backends/memory.py` — `InMemoryEventBus` concrete implementation
- `backends/__init__.py` — exports

### Key Characteristics

- **Event type**: `DomainEvent` (custom dataclass)
- **Backend**: `InMemoryEventBus` (default), pluggable (Redis, Kafka mentioned in docstrings)
- **Thread safety**: Docstring says "implementations must be thread-safe"
- **Subscriber model**: `subscribe(event_type: str, handler: Callable)` — callback-based
- **Bounded**: `maxlen=10_000` subscriber limit documented
- **Scope**: Core SDK infrastructure. Used by DataFlow for model write events

### Interface

```python
class EventBus(ABC):
    def publish(self, event: DomainEvent) -> None: ...
    def subscribe(self, event_type: str, handler: Callable) -> str: ...
    def unsubscribe(self, subscription_id: str) -> None: ...
    def subscribe_all(self, handler: Callable) -> str: ...  # in InMemoryEventBus
```

## System 2: Nexus EventBus (Proposed — Does Not Exist Yet)

**Location**: Will be `packages/kailash-nexus/src/nexus/events.py`

### Current State in core.py

The `Nexus` class has a rudimentary event system via `broadcast_event()` (line 2254) and `get_events()` (line 2305). This is **NOT** an EventBus — it is a simple list-based event log:

```python
# Line 2294-2296
if not hasattr(self, "_event_log"):
    self._event_log = []
self._event_log.append(event)
```

There is no pub/sub, no subscribers, no filtering, no thread safety. It is purely a debug/logging feature marked "v1.1" for real broadcasting.

### Proposed Design (from architecture.md)

- **Event type**: `NexusEvent` dataclass with `NexusEventType` enum
- **Backend**: `janus.Queue` for cross-thread safety
- **Thread safety**: YES — janus provides sync_q (MCP thread) + async_q (event loop)
- **Subscriber model**: `subscribe()` returns a `janus.AsyncQueue`, consumer pulls events
- **Bounded**: Capacity=256, drops oldest on overflow
- **Scope**: Nexus lifecycle events, handler events, custom events

## Comparison

| Feature         | Core SDK EventBus                    | Nexus EventBus (proposed)                 |
| --------------- | ------------------------------------ | ----------------------------------------- |
| Event type      | `DomainEvent`                        | `NexusEvent`                              |
| Subscribe model | Callback-based (`handler: Callable`) | Queue-based (`subscribe() -> AsyncQueue`) |
| Thread safety   | Required by contract                 | `janus.Queue` (sync + async sides)        |
| Backend         | `InMemoryEventBus` / pluggable       | `janus.Queue` (fixed)                     |
| Bounded         | 10,000 subscribers                   | 256 events per subscriber queue           |
| Wildcard        | `subscribe_all()`                    | `subscribe_filtered(filter_fn)`           |
| Scope           | DataFlow model events                | Nexus lifecycle + custom events           |

## Bridge Design (architecture.md Section 8)

The `DataFlowEventBridge` connects the two systems:

1. Subscribes to Core SDK EventBus via `dataflow.event_bus.subscribe_all()`
2. Translates `DomainEvent` -> `NexusEvent`
3. Publishes to Nexus EventBus via `nexus_event_bus.publish()`

This is a one-way bridge (DataFlow -> Nexus). Nexus events do NOT flow back to DataFlow.

## Risks

### Risk 1: janus Not a Current Dependency

`janus` is NOT currently in any `pyproject.toml` in the codebase. It must be added to `packages/kailash-nexus/pyproject.toml` during B0a. This is a new third-party dependency introduction.

### Risk 2: janus.Queue Lifecycle

`janus.Queue` requires an active asyncio event loop at creation time. If `EventBus.__init__()` is called before the event loop starts (which happens in `Nexus.__init__()` before `start()`), `janus.Queue` creation will fail unless lazy initialization is used.

**Mitigation**: Use lazy subscriber queue creation — `subscribe()` creates the `janus.Queue` when first called, not at EventBus construction time. Or use `janus.Queue(maxsize=capacity)` which does NOT require a running event loop (it creates the queue pair lazily).

### Risk 3: Existing broadcast_event() API

The existing `broadcast_event()` and `get_events()` methods on `Nexus` (lines 2254-2349) form a quasi-public API. After adding the real EventBus, these methods should be wired to use it. The migration is straightforward but must be done in B0a to avoid two event systems coexisting confusingly.
