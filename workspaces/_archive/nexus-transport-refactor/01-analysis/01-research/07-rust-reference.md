# Rust Reference Architecture — kailash-rs Nexus

## Availability

The Rust Nexus crate is available at `~/repos/loom/kailash-rs/crates/kailash-nexus/src/`.

## Directory Structure

```
kailash-nexus/src/
    nexus.rs            # Main Nexus struct
    handler.rs          # HandlerDef, HandlerParam, HandlerParamType, HandlerFn
    server.rs           # Server implementation
    engine.rs           # NexusEngine (builder pattern)
    config.rs           # Configuration
    error.rs            # NexusError
    lib.rs              # Crate root
    prelude.rs          # Common imports
    openapi.rs          # OpenAPI generation
    events/
        mod.rs          # NexusEvent enum
        bus.rs          # EventBus (tokio::sync::broadcast)
    registry/
        mod.rs          # WorkflowRegistry
    health/             # Health check
    middleware/         # Middleware
    mcp/               # MCP integration
    plugin/            # Plugin system
    auth/              # Authentication
    cli/               # CLI
    api/               # API
    agentui/           # Agent UI
```

## HandlerDef (handler.rs)

The Rust implementation matches the Python architecture proposal exactly:

```rust
pub enum HandlerParamType {
    String, Integer, Float, Bool, Object, Array, Optional(Box<HandlerParamType>), Any
}

pub struct HandlerParam {
    pub name: String,
    pub param_type: HandlerParamType,
    pub required: bool,
    pub default: Option<Value>,
    pub description: String,
}

pub struct HandlerDef {
    pub name: String,
    pub func: Arc<dyn HandlerFn>,
    pub params: Vec<HandlerParam>,
    pub description: String,
    pub tags: Vec<String>,
    pub metadata: ValueMap,
}
```

This confirms the proposed Python `HandlerDef` and `HandlerParam` dataclasses align with the Rust architecture.

## EventBus (events/bus.rs)

```rust
pub struct EventBus {
    sender: broadcast::Sender<NexusEvent>,
}

impl EventBus {
    pub fn new(capacity: usize) -> Self { ... }
    pub fn publish(&self, event: NexusEvent) { ... }
    pub fn subscribe(&self) -> broadcast::Receiver<NexusEvent> { ... }
    pub fn subscribe_filtered(&self, filter_fn) -> FilteredSubscriber { ... }
    pub fn subscriber_count(&self) -> usize { ... }
}
```

Key observations:

- Uses `tokio::sync::broadcast` — inherently `Send + Sync`
- Bounded buffer with configurable capacity
- Lagging subscribers lose oldest events
- `subscribe_filtered()` returns a `FilteredSubscriber` wrapper

The proposed Python `EventBus` with `janus.Queue` mirrors this API exactly:

- `publish()` -> non-blocking fire-and-forget
- `subscribe()` -> returns a receiver/queue
- `subscribe_filtered()` -> returns filtered receiver
- Bounded with oldest-drop overflow

## NexusEvent (events/mod.rs)

```rust
pub enum NexusEvent {
    HandlerRegistered { name, timestamp },
    HandlerCalled { name, request_id, timestamp },
    HandlerCompleted { name, request_id, duration, timestamp },
    HandlerError { name, request_id, error, timestamp },
    HealthCheck { status, timestamp },
    Custom { event_type, payload },
}
```

The proposed Python `NexusEventType` enum matches:

- `HANDLER_REGISTERED`, `HANDLER_CALLED`, `HANDLER_COMPLETED`, `HANDLER_ERROR`, `HEALTH_CHECK`, `CUSTOM`

## WorkflowRegistry (registry/mod.rs)

```rust
pub struct WorkflowRegistry {
    workflows: HashMap<String, RegisteredWorkflow>,
}

impl WorkflowRegistry {
    pub fn new() -> Self { ... }
    pub fn register(&mut self, name, workflow) -> Result<()> { ... }
    pub fn get(&self, name) -> Option<&RegisteredWorkflow> { ... }
    pub fn list(&self) -> Vec<&RegisteredWorkflow> { ... }
    pub fn remove(&mut self, name) -> Option<RegisteredWorkflow> { ... }
    pub fn replace(&mut self, name, workflow) -> Result<Option<...>> { ... }
    pub fn contains(&self, name) -> bool { ... }
    pub fn count(&self) -> usize { ... }
    pub fn execute(&self, name, inputs, runtime) -> Result<ExecutionResult> { ... }
}
```

Note: The Rust `WorkflowRegistry` stores workflows only, not handlers. The handler registry is separate (in `nexus.rs` or the handler module). The Python `HandlerRegistry` proposal combines both — this is a reasonable simplification for Python.

## Cross-SDK Alignment Assessment

| Concept          | Rust                                  | Python (Proposed)                              | Aligned?                                                 |
| ---------------- | ------------------------------------- | ---------------------------------------------- | -------------------------------------------------------- |
| HandlerDef       | `HandlerDef` struct                   | `HandlerDef` dataclass                         | YES                                                      |
| HandlerParam     | `HandlerParam` struct                 | `HandlerParam` dataclass                       | YES                                                      |
| HandlerParamType | `HandlerParamType` enum               | `param_type: str`                              | PARTIAL (Rust uses enum, Python uses string)             |
| NexusEvent       | `NexusEvent` enum                     | `NexusEvent` dataclass + `NexusEventType` enum | YES (different encoding, same semantics)                 |
| EventBus         | `tokio::sync::broadcast`              | `janus.Queue`                                  | YES (same semantics: bounded, lagging-drop, thread-safe) |
| WorkflowRegistry | `WorkflowRegistry`                    | Part of `HandlerRegistry`                      | PARTIAL (Python combines workflows + handlers)           |
| Transport ABC    | Not a Rust trait (uses axum directly) | `Transport` ABC                                | N/A (Rust has no equivalent abstraction)                 |

The cross-SDK alignment is strong. The Python architecture mirrors Rust semantics while using Python idioms. The main divergence is that Python's `HandlerRegistry` combines workflow and handler storage, whereas Rust separates them. This is acceptable — the external API semantics match.
