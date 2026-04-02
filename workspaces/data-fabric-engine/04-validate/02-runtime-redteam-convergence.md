# Runtime Red Team Convergence

## 8 findings from runtime transformation review. All resolved.

### RT-1 (CRITICAL): TaskGroup kills all tasks on single failure

**Problem**: `asyncio.TaskGroup` cancels ALL sibling tasks when one raises. Fabric tasks run forever — one crash = full outage.

**Resolution**: Replace with supervised task list. Each task restarts on failure independently.

```python
class FabricRuntime:
    def __init__(self):
        self._tasks: list[asyncio.Task] = []

    async def _supervised(self, name: str, coro_fn):
        """Run a background task forever. Restart on failure."""
        while not self._shutting_down:
            try:
                await coro_fn()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(f"Fabric task '{name}' crashed, restarting in 5s")
                await asyncio.sleep(5)

    async def start(self):
        self._tasks.append(asyncio.create_task(
            self._supervised("leader", self._leader_heartbeat)
        ))
        for name, source in self._sources.items():
            self._tasks.append(asyncio.create_task(
                self._supervised(f"poll:{name}", lambda: self._poll_loop(name, source))
            ))

    async def stop(self):
        self._shutting_down = True
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
```

### RT-2 (MAJOR): Leader gap loses webhooks

**Resolution**: Webhook endpoints registered on ALL workers (not just leader). Non-leader workers write webhook events to a Redis list. Leader consumes from list and triggers pipelines. Leadership gap only delays pipeline execution, never loses webhook events.

### RT-3 (MAJOR): Parameterized inline execution unbounded

**Resolution**: Configurable strategy per product, default TIMEOUT (2s):

```python
@db.product("users", mode="parameterized",
    cache_miss="timeout",          # "inline" | "timeout" | "async_202"
    cache_miss_timeout=2.0,        # seconds
)
```

- `timeout` (default): Execute inline, return 504 if exceeds timeout
- `async_202`: Return 202 immediately, execute in background
- `inline`: Execute inline, no timeout (only for fast products)

Concurrent inline executions guarded by separate semaphore (default: 10).

### RT-4 (MAJOR): Redis MULTI partial write

**Resolution**: Use Lua script for atomic cache update:

```lua
redis.call('SET', KEYS[1], ARGV[1])  -- data
redis.call('SET', KEYS[2], ARGV[2])  -- hash
redis.call('SET', KEYS[3], ARGV[3])  -- metadata
return 1
```

Lua scripts execute atomically on Redis server. No partial state possible.

### RT-5 (MAJOR): REST APIs without ETag

**Resolution**: Auto-detect conditional support on first request. If API returns neither ETag nor Last-Modified, fall back to content-hash comparison:

```python
async def detect_change(self) -> bool:
    if self._supports_conditional is None:
        # First request — probe for support
        resp = await self._client.head(self._detect_url)
        self._supports_conditional = bool(
            resp.headers.get("ETag") or resp.headers.get("Last-Modified")
        )

    if self._supports_conditional:
        return await self._detect_via_conditional()
    else:
        return await self._detect_via_content_hash()
```

Content-hash fallback: full fetch + SHA-256. Works for any API. More expensive, but correct.

### RT-6 (MAJOR): Unbounded product result size

**Resolution**: Default max 10MB per product. Configurable. Enforced before serialization:

```python
MAX_PRODUCT_SIZE = 10 * 1024 * 1024  # 10MB

serialized = json.dumps(result, default=str, sort_keys=True)
if len(serialized) > max_size:
    trace.status = "failed"
    trace.error = f"Result {len(serialized)} bytes exceeds {max_size} limit"
    return  # Cache keeps old data
```

### RT-7 (MAJOR): Watchdog thread → async bridge

**Resolution**: Pass event loop reference to file adapter. Use `run_coroutine_threadsafe`:

```python
def _on_file_changed(self, event):
    future = asyncio.run_coroutine_threadsafe(
        self._notify_change(), self._loop
    )
    future.add_done_callback(lambda f:
        f.exception() and logger.error(f"File callback error: {f.exception()}")
    )
```

### RT-8 (MAJOR): Express lacks centralized \_execute_write

**Resolution**: Use DataFlow's existing `DataFlowEventMixin` event bus. The fabric subscribes to write events via the existing event system rather than adding hooks to individual Express methods:

```python
# Fabric subscribes to existing event bus
self._dataflow.on("model.created", self._on_model_write)
self._dataflow.on("model.updated", self._on_model_write)
self._dataflow.on("model.deleted", self._on_model_write)
self._dataflow.on("model.bulk_created", self._on_model_write)
self._dataflow.on("model.bulk_deleted", self._on_model_write)
```

No Express refactoring needed. Fabric hooks into the existing event system.

### Minor Fixes

| Finding                         | Fix                                            |
| ------------------------------- | ---------------------------------------------- |
| `datetime.utcnow()` deprecated  | Use `datetime.now(timezone.utc)` throughout    |
| Unbounded pipeline queue        | `asyncio.Queue(maxsize=100)`, coalesce on full |
| `ensure_future` in `call_later` | Use `create_task` with error callback          |

---

## Updated Spec Coverage After Runtime Red Team

All 8 findings resolved. No new PARTIAL items introduced. The runtime transformation document (doc 12) is now implementation-ready with these corrections applied.
