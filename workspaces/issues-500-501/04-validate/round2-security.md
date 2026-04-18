# Round 2 Security — #500 + #501 Nexus lifespan + shutdown idempotency

Scope reviewed at main SHA `fc77bdd3`:

- `src/kailash/servers/workflow_server.py` (lifespan rewrite — H1 widen,
  M2 bound + re-raise)
- `packages/kailash-nexus/src/nexus/core.py` (H2 lock around
  `_shutdown_hooks_fired`, sync + async paths, `stop()` signal path)

Evidence:

- `src/kailash/servers/workflow_server.py:179-254` (widened lifespan)
- `src/kailash/servers/workflow_server.py:115`, `204-220` (startup_hook_timeout)
- `packages/kailash-nexus/src/nexus/core.py:435-436` (flag + lock init)
- `packages/kailash-nexus/src/nexus/core.py:2035-2052` (sync path under lock)
- `packages/kailash-nexus/src/nexus/core.py:2091-2103` (async path under lock)
- `tests/integration/nexus/test_partial_startup_teardown.py` (H1 regression)
- `tests/integration/nexus/test_startup_hook_timeout.py` (M2 regression)

## Round 1 verification

| Finding                                               | Status       | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| sec H1 (partial-startup leak)                         | FIXED        | `workflow_server.py:199-254` — `try:` now begins BEFORE `router.startup()` and BEFORE `startup_hook()`; the `finally:` block runs `shutdown_hook` + `router.shutdown` + `self.shutdown_coordinator.shutdown()` on BOTH normal shutdown AND aborted startup. Each teardown step has its own `try/except` so one failure does not block the next. Tier 2 regression `test_partial_startup_teardown.py` asserts shutdown_hook + coordinator both fire after a startup_hook raise. |
| sec H2 (TOCTOU on `_shutdown_hooks_fired`)            | FIXED        | `core.py:436` adds `self._shutdown_hooks_fired_lock: threading.Lock`. `_call_shutdown_hooks` (sync, 2037-2044) and `_call_shutdown_hooks_async` (async, 2092-2095) both wrap the check-and-set in `with self._shutdown_hooks_fired_lock:` before releasing the lock and iterating hooks outside the critical section (correct — minimises hold time, avoids re-entry if a hook calls back into the same code path).                                                            |
| sec M1 (missing `__del__` / `close()`)                | OUT OF SCOPE | Deferred per instructions. No regression introduced by round-2; the `__init__` still registers `self.executor` with `ShutdownCoordinator` at line 156, so partial-startup no longer leaks it (H1 covers).                                                                                                                                                                                                                                                                      |
| sec M2 (startup_hook DoS)                             | FIXED        | `workflow_server.py:115` adds `startup_hook_timeout: Optional[float] = None` kwarg. `204-220` wraps the hook in `asyncio.wait_for(startup_hook(), timeout=startup_hook_timeout)` when set; on `asyncio.TimeoutError` it logs `workflow_server.startup_hook.timeout` at ERROR and re-raises, which then drops into the widened `finally:` from H1 so the coordinator still runs. Tier 2 regression `test_startup_hook_timeout.py` asserts timeout + teardown together.          |
| sec M3 (per-hook shutdown errors no aggregate signal) | OUT OF SCOPE | Deferred per instructions. No regression introduced.                                                                                                                                                                                                                                                                                                                                                                                                                           |

## Round 2 NEW — fresh attack surface introduced by the round-2 code

### CRITICAL

_None._

### HIGH

_None._

### MED

#### M-N1 — `_shutdown_hooks_fired_lock` never resets across `stop(); start()` cycles

**File:** `packages/kailash-nexus/src/nexus/core.py:435-436`, `2866-2887`, `2970-3011`

`self._shutdown_hooks_fired` is initialised to `False` in `__init__` and is set to `True` on the first shutdown fire. Nothing in `start()` (line 2866) resets it back to `False`. A caller that does `nx.stop(); nx.start()` (Jupyter/notebook workflows, test harnesses, reload patterns) will start a second lifecycle where the first shutdown-hook invocation is silently a no-op — the sync path at 2038 and the async path at 2093 both short-circuit on the already-`True` flag.

This is a cleaner, testable restatement of round-1 L1; it survived round-2 because the lock scope only addresses TOCTOU, not flag-reset discipline. Proposed fix: reset `self._shutdown_hooks_fired = False` (under the lock) at the top of `start()`. MED rather than HIGH because the common production path (one lifecycle per process) is unaffected; the in-process restart path is the notebook/test surface.

#### M-N2 — `asyncio.wait_for` cancellation does not propagate to partially-allocated resources inside `startup_hook`

**File:** `src/kailash/servers/workflow_server.py:209-220`

When `asyncio.wait_for(startup_hook(), timeout=N)` fires, Python raises `CancelledError` inside the hook coroutine. The hook then gets **one chance** to clean up in its own `finally:` block before `wait_for` converts the CancelledError into `asyncio.TimeoutError` and re-raises. Any resource the hook allocated (a DB connection pool that completed `__aenter__` but hadn't reached `register-for-shutdown` yet, an aiohttp session, a Redis client) that is NOT caught by the hook's own `finally:` leaks.

The widened lifespan `finally:` block at line 224 runs `shutdown_hook` + `router.shutdown` + `ShutdownCoordinator.shutdown()` — but only resources that were successfully registered with one of those paths before the timeout fired will be cleaned up. This is intrinsic to the `wait_for` model and documenting it in the hook contract is the right disposition; there is no library-level fix short of making every hook run under a `with-contextmanager` scope, which is a larger API change.

MED because the fix on the library side is a doc change; operators writing startup_hooks MUST know that `wait_for` cancellation requires the hook to own its own cleanup, and the MUST is enforceable only via the hook docstring.

#### M-N3 — `router.startup()` exception drives `shutdown_hook()` on a framework whose startup never completed

**File:** `src/kailash/servers/workflow_server.py:199-231`

The widened try-block (H1) means that if `app.router.startup()` raises at line 200, the `finally:` at line 224 still invokes `shutdown_hook()` at line 229-231. At that point Starlette's `router._startup` list has only partially run — any `on_startup` handler registered by a downstream consumer (FastAPI dependency-injection hooks, middleware `startup` methods, database-pool acquirers) that failed has NOT been balanced by its corresponding `on_shutdown` handler. Calling `shutdown_hook()` on half-initialised framework state is a contract change from the pre-fix behaviour ("shutdown_hook only fires after a successful startup").

The fix is correct for the H1 threat (ShutdownCoordinator resources MUST be torn down), but downstream authors of `shutdown_hook=` callbacks that assume "my setup_complete flag is True" will now see their shutdown code run against `setup_complete == False`. This is a real change in contract, not a bug; it should be documented in the `shutdown_hook` kwarg docstring at line 131-135. The docstring today says "Exceptions are swallowed and logged at WARN" — it does not state that the hook MUST be robust to partial-startup state.

MED; the fix is a doc update. No runtime change needed.

### LOW

#### L-N1 — Lifespan signal-handler race on `await` point inside the lock

**File:** `packages/kailash-nexus/src/nexus/core.py:2092-2095`

`threading.Lock` guards the check-and-set of `_shutdown_hooks_fired`. CPython signal handlers run on the MAIN thread and can interrupt the interpreter between bytecodes but NOT while the GIL is held by a non-main thread. The async path at 2092-2095 runs in uvicorn's event loop on the main thread; the lock is acquired and released synchronously before the `for hook in ...:` loop — there is no `await` point inside the critical section, so a signal delivered during this window cannot re-enter the critical section (a signal handler's Python-level code runs only after the current bytecode completes, and the lock release bytecode will run before any `await` yields). This is correct.

The sync path at 2037-2044 is likewise fully synchronous inside the critical section. LOW because the rationalisation is subtle and a future refactor that moves an `await` inside the lock would silently re-open the race; a code comment pinning "no await inside the lock" would harden it.

#### L-N2 — Stuck `threading.Lock` across gunicorn worker recycling

**File:** `packages/kailash-nexus/src/nexus/core.py:435-436`

`threading.Lock` is per-process. Gunicorn worker recycling re-executes the worker process with a fresh memory image, so `self._shutdown_hooks_fired_lock` is re-created on every worker boot — no cross-process stuck-lock condition. The question about "the lock re-created if the app restarts without process exit" is a non-issue: Python `Nexus()` construction re-runs `__init__`, which re-creates the lock.

The edge case is a caller who calls `nexus.stop()` then re-uses the same `Nexus` instance (in-process restart) — addressed by M-N1 above.

LOW; no change needed, documented here for completeness.

#### L-N3 — `_run_async_hook` sync entry point (round-1 L2) still present

**File:** `packages/kailash-nexus/src/nexus/core.py:1975-1997`, `2013-2020` docstring

The sync `_call_startup_hooks` at line 1999 still delegates async hooks to `_run_async_hook` via fire-and-forget task scheduling. The round-2 docstring at line 2004-2011 documents that production no longer traverses this path, but the method is still exposed. A downstream caller who invokes `nexus._call_startup_hooks()` manually against a running loop gets the "task hasn't completed yet" behavior. Not fixed; not introduced by round-2. Carried over from round-1.

## Green

- **Round-1 H1 regression.** `test_partial_startup_teardown.py` drives the
  lifespan directly, raises from `startup_hook`, asserts `shutdown_hook`
  AND `ShutdownCoordinator.shutdown()` both fired, asserts the original
  `_BoomStartupError` surfaced through the cause chain.
- **Round-1 H2 regression.** The lock pattern is auditable: grep for
  `_shutdown_hooks_fired_lock` returns both call sites (sync + async),
  and both wrap the atomic check-and-set. `CPython GIL` comment at 432-434
  pins the rationale.
- **Round-1 M2 regression.** `test_startup_hook_timeout_aborts_hung_hook_and_runs_teardown`
  uses `asyncio.Event().wait()` (a real hung hook — no mocking),
  asserts `asyncio.TimeoutError` surfaces AND `shutdown_hook` still fires.
- **ERROR log on timeout.** `workflow_server.py:214-219` logs
  `workflow_server.startup_hook.timeout` at ERROR with
  `timeout_seconds`, before re-raising. Meets `observability.md` Rule 3.
- **Exception taxonomy.** `asyncio.TimeoutError` is re-raised from the
  `except` branch unchanged so uvicorn's lifespan observes a real
  `TimeoutError`, not a wrapped custom type — test consumers can
  `except asyncio.TimeoutError:` directly.

## CONVERGED: yes

All round-1 HIGH (H1, H2) and in-scope MED (M2) are FIXED with
externally-observable Tier 2 regressions that exercise the real
FastAPI lifespan + real asyncio (no mocking). M1 and M3 are
explicitly out of scope per the round-2 brief. Round-2 NEW findings
are MED/LOW — docstring improvements and a known-in-scope flag-reset
case (M-N1). No new HIGH surface introduced.
