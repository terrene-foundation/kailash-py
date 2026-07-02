# /redteam Round 1 — Reviewer — #500 + #501

Date: 2026-04-18
Commits audited: 1535f4be, 7463a5fb, 157abdf5

## HIGH findings

### H1. Idempotency flag `_shutdown_hooks_fired` has ZERO test coverage

- **Issue**: Commit body calls the flag "correctness-critical" to prevent double-firing shutdown hooks, yet no test in `tests/integration/nexus/`, `tests/regression/`, or `packages/kailash-nexus/tests/` exercises either code path (lifespan-then-stop, or stop-then-lifespan). A future refactor that drops the flag, inverts its polarity, or moves the set-site below the iteration will ship silently.
- **Affected**: `packages/kailash-nexus/src/nexus/core.py` L2024, L2030, L2077, L2079 + `L422` (init) + `L2963` (stop call site).
- **Rule**: `facade-manager-detection.md` §1 (Tier 2 must assert externally observable effect through the facade) + `orphan-detection.md` §2 (framework behavior requires integration coverage, not just unit-level).
- **Fix**: Add a Tier 2 test that (a) boots Nexus with a plugin `on_shutdown` counter, (b) triggers `server.should_exit = True`, (c) awaits server shutdown, (d) invokes `app.stop()`, (e) asserts the plugin counter == 1 (not 2). Also add a second test for the reverse path (stop before uvicorn boots) to prove flag set on sync path prevents async re-fire.

## MED findings

### M1. Lifespan logs miss structured-log contract (observability.md §§1, MUST Rule 3)

- **Issue**: The new lifespan at `src/kailash/servers/workflow_server.py:170-206` uses f-string log messages (`logger.info(f"Starting {title} v{version}")`) which observability.md MUST NOT explicitly blocks ("No unstructured `f"..."` log messages"). Also missing: entry log line for `startup_hook` invocation, exit log line for `startup_hook` success, entry/exit for `shutdown_hook`. Operators cannot tell from logs whether the injected Nexus hook actually ran inside the lifespan or whether it bailed silently.
- **Affected**: `src/kailash/servers/workflow_server.py:176,187,195-198,202-205`.
- **Rule**: `observability.md` MUST Rule §1 (entry+exit+error per integration point) and "No unstructured f-string log messages".
- **Fix**: Replace f-strings with structured kwargs and add hook-boundary logs:
  ```python
  logger.info("workflow_server.lifespan.startup", title=title, version=version)
  await app.router.startup()
  if startup_hook is not None:
      logger.info("workflow_server.startup_hook.start", hook=getattr(startup_hook, "__qualname__", repr(startup_hook)))
      await startup_hook()
      logger.info("workflow_server.startup_hook.ok")
  ```
  Same for the shutdown path.

### M2. Pre-existing `asyncio.iscoroutinefunction` deprecation sites untouched (zero-tolerance Rule 1)

- **Issue**: The commit swapped 4 `asyncio.iscoroutinefunction` → `inspect.iscoroutinefunction` call sites (hook drivers), but `packages/kailash-nexus/src/nexus/core.py` L209 (`_wrap_with_guard`) and L1611 (`use_middleware`) remain on `asyncio.iscoroutinefunction` and will emit `DeprecationWarning` as of Python 3.14 / removal 3.16. Commit message implicitly claims to have "fixed `asyncio.iscoroutinefunction` DeprecationWarnings (Python 3.14)" on "the affected code paths" — scope of that statement is ambiguous, and `zero-tolerance.md` Rule 1 states warnings are equal-weight to errors.
- **Affected**: `packages/kailash-nexus/src/nexus/core.py` L209, L1611.
- **Rule**: `zero-tolerance.md` Rule 1 (equal-weight for DeprecationWarning) + Rule 1a (scanner-surface symmetry).
- **Fix**: Swap the two remaining sites to `inspect.iscoroutinefunction` in a follow-up commit on the same branch before tagging a release.

### M3. Pre-existing `AsyncLocalRuntime` ref_count=1 leak surfaced by the new tests

- **Issue**: Running the 5 target tests emits `ResourceWarning: Unclosed AsyncLocalRuntime (ref_count=1)`. Root cause is pre-existing: `Nexus.close()` (core.py:2915) releases only `self.runtime` but never calls `EnterpriseWorkflowServer.close()` (enterprise_workflow_server.py:168) which owns its own acquired runtime ref via `_async_runtime = self._injected_runtime.acquire()`. The new tests surface this because they construct Nexus and cleanly close it without running the full `start()`/`stop()` dance that prior tests went through.
- **Affected**: `packages/kailash-nexus/src/nexus/core.py::Nexus.close` vs `src/kailash/servers/enterprise_workflow_server.py::EnterpriseWorkflowServer.close`.
- **Rule**: `zero-tolerance.md` Rule 1 (found-in-session ResourceWarning) + `testing.md` § "Test Resource Cleanup Discipline".
- **Fix**: Either (a) have `Nexus.close()` call `self._http_transport.gateway.close()` when the gateway is an `EnterpriseWorkflowServer`, or (b) register the gateway's runtime-release into `ShutdownCoordinator` so the lifespan tears it down. Option (a) is less-layered; option (b) matches the existing shutdown architecture.

### M4. `create_gateway` signature widened but docstring `Args:` not updated (documentation hygiene)

- **Issue**: `src/kailash/servers/gateway.py:36-40` adds `startup_hook` and `shutdown_hook` kwargs, but the docstring's `Args:` block (L49-61) documents neither. The only mention is the inline comment `# Lifespan hooks (run inside FastAPI lifespan / uvicorn loop)`. Downstream users who read the docstring (IDE hover, Sphinx docs) will not learn the new surface exists.
- **Affected**: `src/kailash/servers/gateway.py:42-88`.
- **Rule**: `documentation.md` + `cc-artifacts.md` (public-API surfaces need aligned docstring entries).
- **Fix**: Add `startup_hook` and `shutdown_hook` to the `Args:` block with the same contract description as `WorkflowServer.__init__`'s docstring (L125-133).

## LOW findings

### L1. `_shutdown_hooks_fired` is not thread-safe (observational, not load-bearing)

- **Issue**: Plain `bool`, no lock. The check-then-set (L2024/L2030 and L2077/L2079) has a TOCTOU window. In the current invocation graph — lifespan teardown runs in uvicorn's loop thread, `Nexus.stop()` invoked from the same main thread's `KeyboardInterrupt` branch — the paths are serial, so no race fires today. But if a future signal handler or external operator invokes `stop()` from a different thread while the lifespan is mid-teardown, both paths could read False and both iterate hooks.
- **Rule**: Defense-in-depth; not a current-rule violation.
- **Fix (optional)**: Use a `threading.Lock` around the check/set, or an atomic `compare_and_set` via `threading.Event`. Document the single-thread assumption if left as-is.

### L2. Regression tests boot real uvicorn — good, but slow-test opportunity

- **Issue**: Each of the 5 tests spins up a real uvicorn server on a fresh ephemeral port. Test suite cost is ~3.8s for the 5 tests, acceptable today; if this pattern multiplies across other regression targets the CI wall-time grows quickly.
- **Rule**: Not a rule violation; testing.md explicitly endorses real-infra Tier 2.
- **Fix (optional)**: Share a single uvicorn server across the suite via a session-scoped fixture where the invariant permits (tests mutate router state, so probably not shareable — accept as-is).

### L3. Cross-SDK verified: kailash-rs NexusPlugin trait has no async startup hooks

- **Issue**: Analysis doc claims kailash-rs is not affected. Verified: `crates/kailash-nexus/src/plugin/mod.rs` defines `NexusPlugin` with `on_register`/`on_unload`/`on_reload`/`health_check` — no `on_startup`/`on_shutdown` and no async task-spawning lifecycle methods. #501 is structurally inapplicable. For #500 the Rust SDK uses axum's native router lifecycle (no custom lifespan wrapper) so the "custom lifespan replaces `_DefaultLifespan`" pattern does not exist. No cross-SDK issue to file.
- **Disposition**: Verified clean — no action needed.

## Downstream impact verified

- **impact-verse** — confirmed at `~/repos/tpc/impact-verse/src/impact_verse/rest_api.py:218-253`, commit `f1186b28` (2026-04-18). The workaround captures `_fastapi.router.lifespan_context`, replaces it with a wrapper that awaits `router._startup()` / `router._shutdown()` via private `type: ignore[attr-defined]` access. **The new `startup_hook` kwarg path fully satisfies this use case**: impact-verse can retire the workaround and simply use `app.fastapi_app.router.on_startup.append(fn)` (the documented public API), because the fix now invokes `app.router.startup()` (public Starlette coroutine) inside the lifespan. Filing a follow-up issue on impact-verse to retire the workaround is recommended but not required for this PR.

## Green (protocol items that passed)

- `pytest --collect-only` on `tests/integration/nexus/` + `tests/regression/` returns exit 0 (279 tests collected, no ImportError/ModuleNotFoundError).
- All 5 target tests pass against real uvicorn + real httpx (no mocks): `5 passed, 2 warnings in 3.84s`.
- Tier 2 tests (`test_router_on_startup_fires`, `test_plugin_on_startup_task_survives`, `test_shutdown_symmetric`) all boot real `uvicorn.Server` instances against ephemeral ports with `lifespan = "on"`; no `@patch`/`MagicMock`/`unittest.mock` imports. (testing.md § Tier 2 clean.)
- Regression tests (`test_issue_500_router_on_startup`, `test_issue_501_hook_task_lifetime`) reproduce the bug behaviorally — each asserts the minimal user-visible invariant (`flag == [1]`, `task.done() is False` after 1s of uptime) against a real uvicorn boot. Not source-grep.
- `startup_hook` / `shutdown_hook` kwargs have production call sites: `src/kailash/servers/gateway.py:99-100` forwards them into `WorkflowServer` via `common_config`; `packages/kailash-nexus/src/nexus/core.py:740-741` passes `_call_startup_hooks_async` / `_call_shutdown_hooks_async` through `create_gateway()`. Orphan-detection §1 satisfied in the same PR.
- No new `*Manager` / `*Executor` / `*Store` facade attributes — facade-manager-detection.md not triggered.
- `Nexus.start()` pre-uvicorn call to `_call_startup_hooks()` was removed (L2873-2881 comment documents the removal); sync entry point retained for backward compat with explicit `NOTE (#501)` dead-path docstring.
- CHANGELOG entry at `packages/kailash-nexus/CHANGELOG.md:5-15` documents root cause, fix, and new public surface. Under `[Unreleased]` — correct for staged release.
- Capacity budget: ~300 LOC production (workflow_server.py lifespan rewrite, nexus/core.py async hook drivers, gateway.py kwarg forward, shutdown.py inspect swap) + ~660 LOC tests. Load-bearing logic is ~100 LOC (the lifespan body + async hook drivers + flag logic). Within single-shard budget per `autonomous-execution.md` § capacity.
- Warning triage (observability.md MUST Rule 5): 3 unique WARN+ entries surfaced:
  1. `websockets.legacy` DeprecationWarning (uvicorn transitive) — **Upstream**, pinned via uvicorn.
  2. `websockets.server.WebSocketServerProtocol` DeprecationWarning (uvicorn transitive) — **Upstream**, same origin.
  3. `ResourceWarning: Unclosed AsyncLocalRuntime (ref_count=1)` — pre-existing leak, captured as M3 finding.
