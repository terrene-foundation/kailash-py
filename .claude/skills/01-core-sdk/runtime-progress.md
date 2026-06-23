# Runtime Progress Tracking

ProgressRegistry provides structured progress reporting for long-running node
operations. Nodes emit updates via `report_progress()`, and registered callbacks
(UIs, loggers, metrics) receive them in real time.

## Architecture

```
Node.run()                     ProgressRegistry              Callbacks
    │                               │                           │
    ├─ report_progress(1, 100) ──►  emit(ProgressUpdate) ──►  on_progress(update)
    ├─ report_progress(2, 100) ──►  emit(ProgressUpdate) ──►  on_progress(update)
    │                               │                           │
    └─ (node completes)             └─ (bounded deque)          └─ (UI/log/metric)
```

- **Context variables** (`contextvars`) propagate the registry and current node ID
  implicitly through the async call stack — nodes don't need a reference to the runtime.
- **Thread-safe** — `threading.Lock` protects callback registration; bounded `deque`
  prevents OOM on long workflows.
- **Backward compatible** — `report_progress()` is a no-op when no registry is active.

## API Surface

```python
from kailash.runtime.progress import ProgressUpdate, ProgressRegistry, report_progress

# ProgressUpdate (dataclass)
update.node_id      # str — which node emitted this
update.current      # int — items processed so far
update.total        # int | None — total items (None = indeterminate)
update.message      # str — human-readable status
update.timestamp    # float — time.monotonic()
update.fraction     # float | None — current/total (property)

# ProgressRegistry
registry = ProgressRegistry()
registry.register(callback)    # Callable[[ProgressUpdate], None]
registry.unregister(callback)
registry.emit(update)          # broadcast to all callbacks
registry.clear()               # remove all callbacks

# Convenience function (called inside Node.run())
report_progress(current=50, total=100, message="Processing batch 5/10")
```

## Production Wiring (LocalRuntime)

LocalRuntime creates a `ProgressRegistry` at init and wires it into the
execution context via `_current_progress_registry` context variable:

```python
# Consumer side — register a callback before execution
def on_progress(update: ProgressUpdate):
    print(f"[{update.node_id}] {update.fraction:.0%} — {update.message}")

runtime = LocalRuntime()
runtime.progress_registry.register(on_progress)
results, run_id = runtime.execute(workflow.build())
```

## Writing Progress-Aware Nodes

Inside a custom node's `run()` method:

```python
from kailash.runtime.progress import report_progress

class BatchProcessNode(BaseNode):
    async def run(self, inputs):
        items = inputs["items"]
        for i, item in enumerate(items):
            await self.process(item)
            report_progress(current=i + 1, total=len(items), message=f"Item {item.id}")
        return {"processed": len(items)}
```

`report_progress` reads the context variable set by the runtime. If no registry
is active (e.g., running the node in isolation), the call is a silent no-op.
