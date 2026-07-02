---
type: DISCOVERY
date: 2026-04-18
author: agent
project: kailash-py
topic: #500 + #501 converge on a single fix — move startup hooks into FastAPI lifespan
phase: analyze
tags: [nexus, lifespan, startup-hooks, asyncio, cross-sdk]
---

# Both Bugs Are One Bug: Hooks On The Wrong Event Loop

**Finding**: #500 and #501 were filed as separate issues but have a
single root cause: Nexus startup hooks execute on an ephemeral event
loop that dies before uvicorn's loop starts.

- **#500**: `router.on_startup` hooks are never invoked because the
  custom `lifespan` in `src/kailash/servers/workflow_server.py:140-147`
  omits `await app.router._startup()`.
- **#501**: plugin `on_startup` async hooks ARE invoked but via
  `asyncio.run()` at `packages/kailash-nexus/src/nexus/core.py:1972`,
  which creates a fresh loop, runs the hook, then closes the loop —
  cancelling any `asyncio.create_task(...)` the hook scheduled.

Fix sites verified by reading the exact lines cited in both issues.
Both fix sites match the issue authors' citations.

## Why the convergence matters

Filing them as one fix is strictly better:

1. **One PR, one test suite.** The three new Tier 2 tests cover both
   fixes simultaneously — `test_router_on_startup_fires.py`,
   `test_plugin_on_startup_task_survives.py`,
   `test_shutdown_symmetric.py`. Splitting would duplicate the uvicorn
   harness.
2. **Shutdown symmetry is the same design question.** Whoever fixes
   startup also owns the shutdown side; `router.on_shutdown` needs
   `router._shutdown()` wired in the same lifespan.
3. **Downstream workaround removes in one PR.** impact-verse's
   `f1186b28` lifespan-wrapper workaround covers both bugs in one
   patch; the SDK fix should close both in one patch.

## Target design (confirmed from issues' suggested fix)

The `WorkflowServer.__init__` lifespan context manager gains four
additions:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(...)
    await app.router._startup()           # NEW — fixes #500
    if startup_hook is not None:          # NEW — fixes #501
        await startup_hook()
    try:
        yield
    finally:
        if shutdown_hook is not None:     # NEW — symmetric to above
            await shutdown_hook()
        try:
            await app.router._shutdown()  # NEW — symmetric to above
        except Exception:
            logger.warning(...)
        await self.shutdown_coordinator.shutdown()
```

`Nexus.__init__` passes `startup_hook=self._call_startup_hooks_async`
(new coroutine) to `WorkflowServer`, and the pre-uvicorn invocation at
`core.py:2792` is deleted.

## Cross-SDK

Per `rules/cross-sdk-inspection.md` MUST 4 checklist:

- [x] Does the other SDK have this issue? — **No**: kailash-rs uses
      tokio + axum, has no custom lifespan wrapper (issue author
      confirmed in both #500 and #501 bodies).
- [x] Bug filing required? — **No**.
- [x] Cross-reference added? — **N/A** (single-SDK bug).

## Capacity budget

Per `rules/autonomous-execution.md` § per-session capacity:

- LOC: ~80-120 load-bearing logic
- Invariants: 4 (lifespan ordering, hook idempotency, shutdown
  symmetry, task-lifetime survival)
- Call-graph hops: 1-2 (`Nexus.start` → `WorkflowServer` lifespan →
  hooks)
- Describable in 3 sentences: yes

Single shard, single session.

## For Discussion

- Counterfactual: if we fixed only #500, users would still hit #501 —
  their plugin `on_startup` tasks would die. If we fixed only #501
  (move hooks into lifespan) but didn't add `await
app.router._startup()`, the documented FastAPI pattern would still
  no-op. Both halves are required; neither is sufficient.
- The `WorkflowServer.lifespan` contract needs a decision:
  `startup_hook` and `shutdown_hook` are nullable callbacks on the
  constructor. Is that the cleanest API, or should `WorkflowServer`
  expose an explicit `register_startup(async_fn)` method so
  subclasses / composition can layer multiple hooks? The minimal
  fix is callbacks. The ergonomic API would be a registration method.
  Recommend callbacks for this fix; refactor to a registration method
  in a follow-up if a second subclass needs multiple hooks.
- The `router._startup` / `_shutdown` calls use FastAPI's
  underscore-prefixed private attrs. FastAPI has no public API for
  this. If FastAPI ever renames these, the fix breaks silently. A
  wiring test (`test_router_on_startup_fires.py`) that boots a real
  uvicorn process catches the rename at test time rather than
  production time. The test is therefore NOT optional.

## References

- GH #500: `Nexus custom FastAPI lifespan silently ignores router.on_startup handlers`
- GH #501: `Nexus._call_startup_hooks runs async hooks via asyncio.run, killing scheduled background tasks`
- Fix sites: `src/kailash/servers/workflow_server.py:139-151` +
  `packages/kailash-nexus/src/nexus/core.py:1950-1972,2792`
- Downstream workaround: impact-verse commit `f1186b28`
- Analysis doc: `workspaces/issues-500-501/01-analysis/01-root-cause-unified.md`
