# /redteam Round 1 — Security — #500 + #501 Nexus lifespan fix

Scope: `src/kailash/servers/workflow_server.py` (lifespan rewrite) and
`packages/kailash-nexus/src/nexus/core.py` (`_call_{startup,shutdown}_hooks_async`,
`_shutdown_hooks_fired` idempotency, `stop()` path).

Reviewed against threat classes:

1. Signal-handler / thread race on `_shutdown_hooks_fired`
2. Hook exception swallowing in lifespan `try/finally`
3. Startup-hook DoS
4. Order-of-operations leak when `router.startup()` throws before the `try:`

## CRITICAL findings

_None._

## HIGH findings

### H1 — Partial startup crash LEAKS every resource registered with `ShutdownCoordinator`

**File:** `/Users/esperie/repos/loom/kailash-py/src/kailash/servers/workflow_server.py:170-206`

**Reproduction:**

```python
# In workflow_server.py the lifespan is:
async def lifespan(app: FastAPI):
    logger.info(f"Starting {title} v{version}")
    await app.router.startup()                  # <-- (A) may raise
    if startup_hook is not None:
        await startup_hook()                    # <-- (B) may raise
    try:
        yield
    finally:
        # shutdown_hook + router.shutdown + self.shutdown_coordinator.shutdown()
        ...
```

The `try` / `finally` only wraps the `yield`. If either (A) `router.startup()` or
(B) `startup_hook()` raises BEFORE control reaches `try:`, the `finally` block is
never entered. Concretely this means:

- `self.executor` (ThreadPoolExecutor) is registered as a shutdown-coordinator task
  at `WorkflowServer.__init__` (line 147) but `self.shutdown_coordinator.shutdown()`
  never runs — the pool leaks until process exit.
- Any Nexus plugin whose `on_startup` ran earlier in the hook chain but whose
  `on_shutdown` is queued on `_shutdown_hooks` is silently skipped — the
  `shutdown_hook` never fires. `_shutdown_hooks_fired` stays `False`, but the
  lifespan owns the only code path that would call the async shutdown hook, and
  FastAPI will not call the lifespan's cleanup branch after an aborted startup.
- Uvicorn reports the startup failure, the process dies, external-resource
  cleanup (DB pools, aiohttp sessions, MCP channels) never runs.

The asymmetry is the dangerous part: `_call_startup_hooks_async` runs hooks one
by one and logs+continues on each failure (core.py:2054-2061), so after N hooks
run successfully and the N+1-th raises, the first N have allocated resources
that no paired `_call_shutdown_hooks_async` will release.

**Proposed fix:** widen the `try` to cover `router.startup()` + `startup_hook()`.
On failure, run the shutdown branch (shutdown_hook → router.shutdown → coordinator)
before re-raising so partial startup state is always torn down.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {title} v{version}")
    startup_ok = False
    try:
        await app.router.startup()
        if startup_hook is not None:
            await startup_hook()
        startup_ok = True
        yield
    finally:
        # Always run shutdown path, even on aborted startup.
        if shutdown_hook is not None:
            try:
                await shutdown_hook()
            except Exception:
                logger.warning("shutdown hook failed during teardown", exc_info=True)
        try:
            await app.router.shutdown()
        except Exception:
            logger.warning("router.shutdown failed during teardown", exc_info=True)
        await self.shutdown_coordinator.shutdown()
```

### H2 — `_shutdown_hooks_fired` TOCTOU between lifespan coroutine and sync `stop()`

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/core.py:2024-2030` (sync path) and `2077-2079` (async path)

**Reproduction:**

```python
# sync _call_shutdown_hooks:
if self._shutdown_hooks_fired:
    return
self._shutdown_hooks_fired = True
for hook in reversed(self._shutdown_hooks):
    ...
```

The check-then-set on `_shutdown_hooks_fired` is not atomic. Two interleavings
produce observable bugs:

1. **Double-fire.** `Nexus.stop()` is typically called from a signal handler
   (SIGINT/SIGTERM) in the main thread. The lifespan's async shutdown runs in
   uvicorn's event loop on the same thread, but signal delivery can interrupt
   between the `if self._shutdown_hooks_fired:` read and the `= True` write in
   `_call_shutdown_hooks_async`. If `stop()` fires the sync path during that
   window, both paths enter the loop and shutdown hooks run twice. Plugins that
   hold idempotent cleanup (close a pool) survive; plugins that don't
   (increment a counter, publish a "shutdown" event, revoke a leased token
   twice) corrupt.

2. **Skip-fire.** If uvicorn's lifespan has already set the flag and is
   iterating the hook loop, a signal-driven `stop()` call to the sync path
   short-circuits on the flag and calls `_run_sync_shutdown(self._mcp_channel.stop())`
   on line 2974 — but uvicorn's loop is still running and owns the MCP state.
   The sync path races the async path for the same resource.

The fix is not thread-safety-per-se — CPython's GIL makes the individual load
and store atomic — but ordering: the flag is consulted AND set from both a
coroutine and a sync signal context without a lock or "owner" discipline.

**Proposed fix:** move the flag to a `threading.Lock()`-guarded critical
section, OR make `stop()` refuse to run the sync shutdown path whenever an
event loop is currently running on the main thread (delegate to the lifespan
and return immediately). The second is cleaner:

```python
def stop(self):
    if not self._running:
        self.close()
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        # Lifespan owns shutdown. Signal it and return.
        logger.info("Nexus.stop called while loop running; lifespan will handle shutdown")
        self._running = False
        return
    # Non-running-loop path: safe to run sync hooks.
    self._call_shutdown_hooks()
    ...
```

## MED findings

### M1 — `ResourceWarning` path (`WorkflowServer.__del__`-equivalent) absent; `ShutdownCoordinator` not invoked on GC

**File:** `/Users/esperie/repos/loom/kailash-py/src/kailash/servers/workflow_server.py` (entire class)

`WorkflowServer` holds a `ThreadPoolExecutor` (line 137) and a
`ShutdownCoordinator` (line 142) but defines no `__del__` / `close()` /
`__aexit__`. If a consumer constructs `WorkflowServer(...)` without calling
`run()` (tests, dependency-injection smoke checks, import-time probes), the
executor leaks with zero signal.

This is adjacent to `rules/patterns.md` § "Async Resource Cleanup". It is not
introduced by #500/#501 — it pre-dates the patch — but it interacts with H1:
anyone who upgrades to 2.0.9 and starts catching partial-startup failures will
hit this leak path on every caught failure.

**Proposed fix:** add a `ResourceWarning`-emitting `__del__` and a public
`close()` that invokes `shutdown_coordinator.shutdown()`. Follows the pattern
mandated by `rules/patterns.md`.

### M2 — `startup_hook` blocking call has no timeout (denial-of-service vector)

**File:** `/Users/esperie/repos/loom/kailash-py/src/kailash/servers/workflow_server.py:180-181`

```python
if startup_hook is not None:
    await startup_hook()        # unbounded wait
```

A plugin `on_startup` that hangs (awaiting a DB that is down, an HTTP
dependency that never responds) pins the lifespan coroutine forever. Uvicorn
never begins accepting connections; health probes time out; Kubernetes restarts
the pod; the restarted pod hits the same hang.

Labeled MED rather than HIGH because the bulk of uvicorn deployments sit
behind a liveness-probe that will eventually restart the pod — the DoS is
effectively self-healing with a short blast radius per pod — but a malicious
or buggy plugin can still run the pod into CrashLoopBackOff indefinitely.

**Proposed fix:** wrap `startup_hook()` in `asyncio.wait_for(...,
timeout=startup_hook_timeout_s)` with a reasonable default (30–60s) and a
typed error on timeout so operators can distinguish "plugin hung" from "plugin
raised".

### M3 — Async shutdown exception swallowing is silent on EVERY hook

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/core.py:2080-2087`

```python
for hook in reversed(self._shutdown_hooks):
    try:
        if inspect.iscoroutinefunction(hook):
            await hook()
        else:
            hook()
    except Exception:
        logger.exception("Shutdown hook failed: %s", hook)
```

The exception IS logged (good — satisfies zero-tolerance Rule 3), but the
lifespan `finally` block continues unconditionally. No failure count is
propagated back to the operator; no metric is emitted; no startup-fails-loudly
behavior. A plugin whose `on_shutdown` silently fails leaves orphaned
resources (connection pools, audit queues) that no one detects until the
replacement pod claims the same durable state.

**Proposed fix:** aggregate exceptions across all shutdown hooks and emit a
single WARN summary: `"shutdown: {n_failed}/{n_total} hooks failed"`. Add a
`shutdown_failures` Counter (if Prometheus available) for alerting.

## LOW findings

### L1 — `_call_shutdown_hooks_async` does not reset `_shutdown_hooks_fired` on re-entry across server restart

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/core.py:2077-2079`

The idempotency flag is set on first fire and never reset. If a user restarts
the Nexus instance in-process (`nx.stop(); nx.start()`), the second startup
succeeds but the second shutdown is a no-op — both async and sync paths
short-circuit. Unlikely in production but plausible in Jupyter/notebook
workflows.

**Proposed fix:** reset `_shutdown_hooks_fired = False` at the top of
`start()`.

### L2 — `_run_async_hook` swallows task exception state via done-callback, breaking caller's ability to await completion

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-nexus/src/nexus/core.py:1969-1979`

```python
task = loop.create_task(hook())
def _hook_done_callback(t):
    exc = t.exception()
    ...
task.add_done_callback(_hook_done_callback)
# function returns here; caller has no handle on task
```

When `_run_async_hook` is invoked from the SYNC `_call_startup_hooks` path
(line 2003), the task is created on a running loop and the function returns
synchronously — the hook hasn't completed yet. This only matters for callers
on the sync path (legacy tests per the docstring) but it means "startup
hooks completed" is a lie for async hooks scheduled via the sync entry point.
Since #501 now routes production through the async entry, this is observably
dead code for the fixed path, but it stays as a loaded gun for anyone who
calls `_call_startup_hooks()` manually.

**Proposed fix:** deprecate `_call_startup_hooks()` formally — add a
`DeprecationWarning` when it runs against an async hook on a running loop;
direct callers to `await nexus._call_startup_hooks_async()` instead.

## Green

- **SSRF / URL handling.** Not in scope for this fix (no network code touched).
- **Authentication / authorization.** Not in scope; lifespan fix does not
  change auth path.
- **Input validation.** `startup_hook` / `shutdown_hook` kwargs are typed
  `Optional[Callable[[], Awaitable[None]]]`; duck-typed at call site. No
  user-reachable input surface introduced.
- **SQL injection / parameter binding.** N/A.
- **Log injection.** `logger.info(f"Starting {title} v{version}")` at line 176
  interpolates `title` (constructor kwarg from app operator, not user input).
  Acceptable — this is operator-supplied config, not external input.
- **Signal safety on the async path.** `_call_shutdown_hooks_async` correctly
  uses `await hook()` for coroutines (no `asyncio.run` / throwaway-loop bug
  that motivated #501).
- **Idempotency flag (happy path).** `_shutdown_hooks_fired` correctly
  prevents double-fire when the SAME async path runs twice (e.g., pytest
  fixture teardown after lifespan). H2 is strictly about cross-path races.
- **`finally` covers hook failure on the shutdown side.** Each of the three
  teardown steps (`shutdown_hook`, `router.shutdown`, `shutdown_coordinator`)
  is wrapped in its own `try/except` and logged, so one failure does not
  block the next — correct. The only gap is H1 (coverage of the startup
  side), not the shutdown side.
