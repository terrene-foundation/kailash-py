---
type: CONVERGENCE
status: final
created: 2026-04-18
issues: [500, 501]
rounds: [1, 2, 3, 5]
verdict: CONVERGED
---

# Round 5 Close — #500 + #501 CONVERGED

Both Nexus startup/shutdown hook bugs filed by the impact-verse downstream team are closed. The unified fix routed all startup hooks through FastAPI's `lifespan` context, converged through 2 parallel /redteam rounds + a round-3 cleanup sweep + a round-5 cancel-cleanup amendment.

## Commits (chronological)

| Commit     | Scope                                                                                   |
| ---------- | --------------------------------------------------------------------------------------- |
| `1535f4be` | Root fix: route startup/shutdown hooks through FastAPI lifespan                         |
| `7463a5fb` | Tier 2 wiring tests (router.on_startup fires, plugin tasks survive, teardown runs)      |
| `157abdf5` | CHANGELOG entry                                                                         |
| `1ac214b3` | Round-2: widen lifespan teardown + bound startup_hook DoS via `startup_hook_timeout`    |
| `dea8c195` | Round-2: atomic shutdown idempotency + deprecation cleanup                              |
| `fc77bdd3` | Merge: round-2 redteam fixes                                                            |
| `c00f21c4` | Round-3: fingerprint parity (4→8 hex), JWT/Azure SAS scrub, shutdown-flag reset         |
| (R5)       | Round-5: M-N2 cancel-cleanup contract + 2 Tier 2 tests + third iscoroutinefunction site |

## Round-5 cleanup additions

Two deferred items from round-2 security-reviewer (both re-categorized to LOW by reviewer, but addressed in the pristine-first sweep):

1. **M-N2 cancel-cleanup contract** — `asyncio.wait_for(startup_hook, timeout)` cancellation leaves partial plugin state. Added a three-clause contract to the `startup_hook_timeout` docstring (shutdown_hook must be partial-init-safe, hooks must handle CancelledError, must not swallow). Added `tests/integration/nexus/test_startup_hook_cancel_cleanup.py` with two Tier 2 tests: partial-init cleanup via shutdown_hook + spawned-task cancellation.

2. **Third `asyncio.iscoroutinefunction` residual** — fixed in `packages/kailash-nexus/src/nexus/auth/audit/backends/custom.py:32`. The session notes predicted a different file (`_run_async_hook:1977`) but surface audit found the actual remaining site here. Replaced with `inspect.iscoroutinefunction` (Python 3.14 forward-compatible).

## Test coverage (verified 2026-04-18)

- **Tier 2 lifespan suite (10 tests):**
  - `test_router_on_startup_fires.py` (1): router.on_startup invoked inside uvicorn
  - `test_plugin_on_startup_task_survives.py` (1): spawned tasks survive server uptime
  - `test_partial_startup_teardown.py` (1): crash before yield still runs shutdown
  - `test_startup_hook_timeout.py` (2): hung hook bounded + None-timeout preserves unbounded wait
  - `test_shutdown_idempotency.py` (3): atomic check-and-set under lock across sync+async paths
  - `test_startup_hook_cancel_cleanup.py` (2): partial-init cleanup + spawned-task cancel (round 5)

- **Kaizen custom audit backend (1 test, part of 64-test suite):** iscoroutinefunction dispatch works post-fix.

## Downstream impact (impact-verse)

The impact-verse workaround at `f1186b28` (private `_fastapi.router.lifespan_context` surgery) can be retired once Nexus 1.x ships with this fix. Coordinate with the downstream maintainer.

## GitHub issue closures

- **#500** — CLOSED with reference to commits `1535f4be`, `7463a5fb`, + R5 cancel-cleanup.
- **#501** — CLOSED with reference to commits `dea8c195`, `1ac214b3`, + R5 cancel-cleanup.

## No remaining gaps

All MED + HIGH findings from rounds 1–2 addressed. Round-2 LOWs either fixed in round 3 or round 5. No deferred items for future sessions on this issue pair.
