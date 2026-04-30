# Implementation Plan — issues #712 / #713 / #714

This is the high-level plan; detailed shard-by-shard todos go in `todos/active/`
during `/todos`.

## Goal

Land all three fixes such that the downstream `mediscribe-v2/backend/app/main.py:417-486`
workaround can be deleted entirely. Per brief constraint:

```
WITHOUT #712: consumer cannot register startup hook                    → blocked
WITHOUT #713: consumer wraps lifespan, calls db.create_tables_async()  → AttributeError
WITHOUT #714: consumer falls back to sync, hits pgbouncer cap          → MaxClientsInSessionMode
```

Partial fixes leave at least one workaround in place.

## Approach

**Shard structure** (detailed in `01-analysis/01-architecture.md` § Sharding):

```
S1 #712 helper       — NEW src/kailash/utils/lifespan.py + workflow_server refactor
S2 #712 siblings     — patch 3 sibling FastAPI lifespan sites + audit kaizen/pact
S3 #712 public API   — Nexus.add_startup_handler/add_shutdown_handler
S4 #713 core         — lazy runtime @property + setter + runtime= kwarg
S5 #713 subsystems   — 6 subsystem captures → lazy lookups
S6 #714              — DDL bypass AsyncSQLDatabaseNode → single connection from manager
S7 specs + docs      — dataflow-core, nexus-core, sibling re-derive
```

**PR strategy** — split per fix surface to keep reviews focused:

- PR-A: #712 work (S1+S2+S3 bundled — they share helper code and can land together)
- PR-B: #713 work (S4+S5)
- PR-C: #714 work (S6)
- PR-D: specs + docs (S7) — can land after the code PRs once final state is known

All four PRs target same release window. PR-A unblocks Mediscribe's startup
registration; PR-B unblocks the async DDL call; PR-C unblocks pgbouncer
deployment. Mediscribe needs all three to drop their workaround.

## Wave plan (per worktree-isolation.md Rule 4 — waves of ≤3)

Per `rules/worktree-isolation.md` Rule 4, each wave caps at 3 concurrent
Opus worktree agents.

```
Wave 1: {S1, S4, S6}   — independent files, parallel
        → wait for completion
Wave 2: {S2, S3, S5}   — S2 needs S1 helper; S3 reads S1's surface; S5 reads S4's property
        → wait for completion
Wave 3: {S7}           — specs after code lands
```

Each wave sets a worktree branch from current `feat/*` HEAD per `rules/worktree-isolation.md` Rule 5 (merge-base check).

## Acceptance criteria

Per the brief (already detailed there). Summary:

- #712: `Nexus.add_startup_handler(func)` exists and works; `@app.on_event` continues to work via router iteration; sibling FastAPI sites all iterate router; downstream `lifespan_context`-wrap workaround unnecessary
- #713: `db = DataFlow(...)` at module scope + `await db.create_tables_async()` inside event loop succeeds; `db.runtime = X` mutation pattern still works; subsystems follow runtime swap; downstream `db.runtime = AsyncLocalRuntime()` mutation unnecessary
- #714: `create_tables()` and `create_tables_async()` use single connection across all DDL, no per-statement node construction; passes Tier-3 pgbouncer test with low session-mode cap; downstream "stick with async path forced choice" eliminated

## Test plan

Each fix ships with a Tier-2 or Tier-3 regression test that fails on main and
passes on the fix branch:

- `tests/regression/test_issue_712_consumer_startup_patterns.py` — Tier-2: spawns Nexus, registers via new public API + via `@app.on_event`, asserts both fire
- `tests/regression/test_issue_712_sibling_fastapi_sites.py` — Tier-2: each of `KailashAPIGateway`, `WorkflowAPIGateway`, `WorkflowAPI` fires startup hooks
- `tests/regression/test_issue_713_module_import_then_async_ddl.py` — Tier-3: PostgreSQL container; module-level DataFlow + async DDL succeeds; subsystems follow swap
- `tests/regression/test_issue_714_create_tables_pgbouncer.py` — Tier-3: pgbouncer container in session-mode with cap≤5; create_tables() and create_tables_async() both succeed against 10+ models

Per `rules/testing.md` § "End-to-End Pipeline Regression", also add:

- `tests/regression/test_mediscribe_pattern_end_to_end.py` — Tier-3: replicates the exact Mediscribe bring-up sequence (Nexus + DataFlow at module scope, register hook for create_tables_async via new public API, no workarounds) and asserts the full path works.

## Cross-SDK parity

Per `rules/cross-cli-parity.md` and the analysis:

- Nexus axum/tokio side: no equivalent custom-lifespan footgun; **no companion issue needed**
- DataFlow runtime-at-construction: no Tokio-runtime-presence-check at construction in kailash-rs; **no companion issue needed**
- Pgbouncer pool exhaustion: kailash-rs DataFlow may have similar DDL-connection-thrash; **file companion issue at /implement gate** for kailash-rs to audit `_execute_ddl*` equivalent
- File companion issue for #714 against esperie/kailash-rs as part of S6.

## Risks and mitigations

| Risk                                                                                                                           | Mitigation                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mediscribe is on stale Nexus and #712 is just upgrade-guidance, not real bug                                                   | Confirm at S3 implementation — write the test against current Nexus head; if it passes, file an upgrade-guidance issue and skip the public API. If it fails, the public API is justified. |
| Converting `self.runtime` to property breaks pickle / copy / deepcopy of DataFlow                                              | S4 acceptance test must include pickle round-trip of DataFlow and assert it survives. If pickle fails, fall back to keeping plain attribute + lazy resolver method.                       |
| `monkeypatch.setattr(db, "runtime", x)` test patterns bypass the setter                                                        | S4 setter MUST also accept `__set__` from descriptor protocol; `monkeypatch.setattr` uses `setattr()` which goes through descriptors. Verify with a Tier-1 test.                          |
| Removing `AsyncSQLDatabaseNode` from DDL path loses observability / metrics that the node provides                             | S6 acceptance: log every DDL statement at INFO with timing; emit DDL counter metric. Same observability as before, just without the node wrapper.                                         |
| Sibling FastAPI sites (`KailashAPIGateway` etc.) may not be widely consumed and the fix introduces unintended startup ordering | S2 acceptance: run existing tests for each class and assert no regression. If any test depends on startup hooks NOT firing, that test is itself the bug — fix it in the same PR.          |

## Open questions for human approval at /todos gate

1. **PR strategy** — do we land 4 separate PRs, or 1 mega-PR? Default: 4 separate, but if reviewer prefers bundled, can adjust.
2. **Public API name** — `Nexus.add_startup_handler(func)` vs `Nexus.on_startup(func)` vs `Nexus.lifespan(startup, shutdown)`. Recommendation: `add_startup_handler` (parallels `add_plugin`, doesn't shadow `on_event`).
3. **Cross-SDK companion** — file kailash-rs#NNN at /implement, or only after #714 lands cleanly? Default: file when #714 PR opens, link both ways.
4. **Spec sibling re-derivation** — the spec edit for `dataflow-core.md` §1.5 will trigger Rule 5b sibling sweep. The four `dataflow-*.md` files total ~1500 lines — re-derivation is a real cost. Confirm this is acceptable or if we should split S7 into S7a (just dataflow-core) and S7b (sibling sweep) for parallel review.
