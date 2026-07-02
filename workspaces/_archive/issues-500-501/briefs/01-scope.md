# Workspace: issues-500-501 — Nexus startup hook bugs

Created: 2026-04-18 (round 4, session wrap-up)
Source: GH issues #500 + #501 (both filed by impact-verse downstream team)

## Goal

Fix the Nexus startup-hook surface so user-registered async code runs
correctly. Today neither documented path works for async tasks that
need to live for the server's lifetime.

## Issues

### #500 — `router.on_startup` silently ignored

`Nexus.fastapi_app.router.on_startup.append(fn)` is a silent no-op.
Custom lifespan in `src/kailash/servers/workflow_server.py:139-151`
replaces (not wraps) Starlette's default lifespan that would have
iterated `router.on_startup`.

**Root cause**: the custom `lifespan` context manager in `WorkflowServer`
does `yield` without first calling `app.router._startup()` (and does
not call `app.router._shutdown()` on exit).

### #501 — `_call_startup_hooks` runs async hooks via `asyncio.run()`, killing scheduled tasks

`packages/kailash-nexus/src/nexus/core.py:1950-1972` — when no event
loop is running, `_run_async_hook` calls `asyncio.run(hook())` which
creates a loop, runs the hook, then CLOSES the loop. Any
`asyncio.create_task(...)` scheduled inside the hook is cancelled at
loop close. Uvicorn starts its own loop afterwards, so the scheduled
task is already gone.

**Root cause**: `_call_startup_hooks()` is invoked from `Nexus.start()`
BEFORE `self._http_transport.run_blocking(...)` starts uvicorn. The
shared-loop assumption is violated by the architectural sequence.

## Combined impact

**No working async startup path** for Nexus users who need background
tasks:

- `router.on_startup` silently does nothing (#500).
- Plugin `on_startup` creates tasks on a dying loop (#501).
- Downstream (impact-verse) shipped a workaround at commit `f1186b28`
  that wraps `router.lifespan_context` after Nexus construction.

Reporter asks to remove the downstream workaround once the SDK fix
lands.

## Target fix (preferred)

Single unified fix (option 1 in #501):

1. Move `_call_startup_hooks()` invocation INTO the FastAPI lifespan
   context manager.
2. In the same lifespan, call `await app.router._startup()` to honor
   the documented FastAPI `router.on_startup` pattern.
3. Symmetric on the shutdown side: `await app.router._shutdown()`
   before `self.shutdown_coordinator.shutdown()`.

This solves both bugs simultaneously:

- User-registered `router.on_startup` hooks execute via the
  `_startup()` call → closes #500.
- Plugin async hooks execute inside the long-lived uvicorn loop, so
  `asyncio.create_task(...)` attaches to a persistent loop → closes
  #501.

## Acceptance criteria

- [ ] `Nexus.fastapi_app.router.on_startup.append(fn)` fires on
      startup (Tier 2 test against a real uvicorn instance)
- [ ] `Nexus.add_plugin(p)` where `p.on_startup` schedules a background
      task via `asyncio.create_task(...)` — the task survives past the
      hook return and is accessible from request handlers
- [ ] Symmetric shutdown: `router.on_shutdown` hooks and plugin
      `on_shutdown` hooks both fire, plus `ShutdownCoordinator` still
      runs at the end
- [ ] Regression test reproducing the exact failure mode in #500 +
      #501 minimal reproductions above
- [ ] Downstream workaround at `impact-verse f1186b28` no longer
      needed (cross-SDK verification in a follow-up note)

## Out of scope

- kailash-rs (not affected per cross-SDK check in both issues; tokio +
  axum architecture is structurally different)
- Deprecating `router.on_startup` in favor of `Nexus.on_startup()` —
  may be a future enhancement but issue #500's suggested alternative
  fix is explicitly not preferred by the reporter

## References

- GH #500: Nexus custom FastAPI lifespan silently ignores `router.on_startup`
- GH #501: `_call_startup_hooks` runs async hooks via `asyncio.run()`
- Downstream workaround: `impact-verse@f1186b28`
- Fix site: `src/kailash/servers/workflow_server.py:139-151` +
  `packages/kailash-nexus/src/nexus/core.py:1950-1972`
