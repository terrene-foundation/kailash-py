# Root Cause Analysis — #500 + #501

Both issues have a single root cause: **Nexus startup hooks execute on
an ephemeral event loop that dies before uvicorn's loop starts.**

## #500 call chain (router.on_startup ignored)

```
user code: app.fastapi_app.router.on_startup.append(my_startup)
            │
            ▼
src/kailash/servers/workflow_server.py:139-151
            │
            ▼
FastAPI(lifespan=lifespan)  ← custom lifespan supplied
            │
            ▼
lifespan body:
    logger.info("Starting ...")
    yield                     ← ** MISSING: await app.router._startup()
    logger.info("Shutting down ...")
    await self.shutdown_coordinator.shutdown()
                              ← ** MISSING: await app.router._shutdown()
```

Per Starlette `Router.__init__`: when a custom `lifespan` is supplied,
the default `_DefaultLifespan` (which would have iterated
`router.on_startup`) is REPLACED, not wrapped. `router.on_startup`
hooks therefore never fire.

## #501 call chain (plugin hooks cancel tasks)

```
Nexus.start()  @ packages/kailash-nexus/src/nexus/core.py:2792
            │
            ▼
self._call_startup_hooks()  (pre-uvicorn, line 2792)
            │
            ▼
for hook in self._startup_hooks:  @ line 1981
    self._run_async_hook(hook)    @ line 1984 (async path)
            │
            ▼
_run_async_hook:
    loop = asyncio.get_running_loop()  ← RuntimeError (no loop)
    loop = None
    ...
    asyncio.run(hook())           @ line 1972
            │                       ↓
            │                   creates fresh loop
            │                   runs hook(), which does
            │                   asyncio.create_task(periodic_bg)
            │                   hook returns → asyncio.run closes loop
            │                   → periodic_bg task CANCELLED
            ▼
self._http_transport.run_blocking(host="0.0.0.0")  @ line 2800
    ↓
uvicorn starts its OWN loop, where the cancelled tasks are gone
```

## Why they converge on one fix

The unifying fact: **any code that wants to own a task for the server's
lifetime MUST run inside uvicorn's loop**. Both bugs violate this:

- #500 violates it by having hooks that are never invoked at all
  (the invocation path is missing from the lifespan).
- #501 violates it by having hooks that ARE invoked, but on a
  throwaway loop created by `asyncio.run()`.

The fix is the same: move ALL startup-hook invocation into the
FastAPI `lifespan` context manager, which runs inside uvicorn's loop.

## Target design

```python
# src/kailash/servers/workflow_server.py — accept an optional hook callback
class WorkflowServer:
    def __init__(self, ..., startup_hook=None, shutdown_hook=None):
        ...
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            logger.info(f"Starting {title} v{version}")
            # Honor documented FastAPI pattern (#500)
            await app.router._startup()
            # Run Nexus plugin startup hooks inside uvicorn's loop (#501)
            if startup_hook is not None:
                await startup_hook()
            try:
                yield
            finally:
                if shutdown_hook is not None:
                    try:
                        await shutdown_hook()
                    except Exception:
                        logger.warning("shutdown_hook failed", exc_info=True)
                try:
                    await app.router._shutdown()
                except Exception:
                    logger.warning("router._shutdown failed", exc_info=True)
                await self.shutdown_coordinator.shutdown()

        self.app = FastAPI(..., lifespan=lifespan)
```

And in Nexus:

```python
# packages/kailash-nexus/src/nexus/core.py
# Pass an async callback that awaits _call_startup_hooks to the
# WorkflowServer (or subclass) constructor. Remove the pre-uvicorn
# invocation at line 2792 — hooks now run inside the lifespan.
async def _call_startup_hooks_async(self) -> None:
    for hook in self._startup_hooks:
        try:
            if asyncio.iscoroutinefunction(hook):
                await hook()
            else:
                hook()
        except Exception as e:
            logger.error("Startup hook failed", exc_info=True)
```

## Test plan

- **Tier 2** `tests/integration/nexus/test_router_on_startup_fires.py` —
  `Nexus().fastapi_app.router.on_startup.append(fn)` + boot against a
  real uvicorn instance (httpx `AsyncClient` to a live port), assert
  fn ran
- **Tier 2** `tests/integration/nexus/test_plugin_on_startup_task_survives.py`
  — plugin on_startup creates `asyncio.create_task(periodic)`, assert
  the task is still running 1s after boot
- **Tier 2** `tests/integration/nexus/test_shutdown_symmetric.py` —
  both `router.on_shutdown` AND plugin `on_shutdown` fire at shutdown,
  plus `ShutdownCoordinator` still runs
- **Regression** `tests/regression/test_issue_500_router_on_startup.py`
  - `test_issue_501_hook_task_lifetime.py` — minimal reproductions from
    the issue bodies, `@pytest.mark.regression`, never deleted

## Cross-SDK

Both issues explicitly state kailash-rs is NOT affected (axum + tokio,
no custom lifespan wrapper, sync `on_register` + tokio global runtime).
Per `rules/cross-sdk-inspection.md` MUST 4 checklist: confirmed, no
cross-SDK issue needs filing.

## Capacity budget

Per `rules/autonomous-execution.md` § per-session capacity: ~80-120 LOC
load-bearing logic, 3-4 invariants (lifespan ordering, hook
idempotency, shutdown symmetry, task-lifetime survival), 1-2
call-graph hops, single shard. Well within single-session budget.

## Downstream dependency

impact-verse currently ships a lifespan workaround at commit
`f1186b28` — reporter wants to remove it once the SDK fix lands. After
merge, coordinate with downstream maintainer to confirm removal is
safe.
