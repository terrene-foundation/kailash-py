# Product Brief — Mediscribe Downstream Incident Cluster (#712/#713/#714)

## Source

A single downstream consumer (vflores-io/mediscribe-v2) hit three independent bugs while wiring DataFlow into a Nexus-based FastAPI backend. The bugs were discovered sequentially while attempting to make `db.create_tables_async()` run at startup. The chain was:

1. **#712** — Tried `@nexus.app.on_event("startup")` to call `db.create_tables_async()`. Hook silently never fired because `WorkflowServer.__init__` constructs the FastAPI app with `lifespan=…` set, which per FastAPI/Starlette semantics disables `@on_event` decorators registered later.

2. **#713** — Worked around #712 by wrapping `app.router.lifespan_context` (Starlette private state). Inside the wrapper, called `db.create_tables_async()` and got `AttributeError: 'LocalRuntime' object has no attribute 'execute_workflow_async'`. Cause: `DataFlow.__init__` selects runtime based on `asyncio.get_running_loop()` at construction time. Module-import construction (the natural FastAPI/Nexus pattern) binds permanently to `LocalRuntime`.

3. **#714** — Worked around #713 by falling back to sync `db.create_tables()`. Hit `MaxClientsInSessionMode` against Supabase's pgbouncer (session-mode default cap ~15 clients) because the sync DDL loop allocates a fresh `AsyncSQLDatabaseNode` connection pool per registered model. With 19 models, exhausts the cap.

The downstream consumer's recovery path (mediscribe-v2 commit `d5b3bd15`) currently:

- Wraps `app.router.lifespan_context` with custom asynccontextmanager (fragile — Starlette private state)
- Mutates `db.runtime = AsyncLocalRuntime()` post-construction (singleton mutation outside construction path)
- Sticks with the async DDL path because sync hits the pgbouncer cap

All three issues are filed as `type/bug` and represent active production blockers for at least one consumer building on Nexus + DataFlow.

## Objectives

The three fixes ship together as one workstream because:

- They share a root failure pattern: Nexus/DataFlow async-lifecycle interaction is under-specified at the consumer surface
- Fixing only one leaves the consumer still blocked on the others
- The dependency chain in the consumer's recovery means partial fixes don't reduce workaround complexity

Per-issue acceptance:

**#712 Nexus FastAPI lifespan footgun**

- Consumers MUST be able to register startup/shutdown hooks against Nexus without silently failing
- Fix surface: choose between (a) public `Nexus.add_lifespan_handler(startup, shutdown)` API; (b) loud refusal of `nexus.app.on_event` calls; (c) documented runtime warning. Decision deferred to /analyze phase.
- The downstream `app.router.lifespan_context` wrapper MUST become unnecessary

**#713 DataFlow runtime binding at construction**

- `db = DataFlow(...)` evaluated at module-import (sync context) MUST NOT permanently bind to `LocalRuntime`
- `db.create_tables_async()` from inside an async context MUST NOT raise `AttributeError`
- Fix surface: lazy runtime selection at first-use (preferred per issue body), explicit `runtime=` kwarg, or per-call-site auto-detection. Decision deferred to /analyze phase.
- The downstream `db.runtime = AsyncLocalRuntime()` mutation MUST become unnecessary

**#714 Sync `create_tables()` connection pool exhaustion**

- DDL loop in `create_tables()` MUST NOT allocate a per-model connection pool
- Realistic model counts (Mediscribe: 19) MUST work against pgbouncer session-mode caps
- Fix surface: reuse the framework's existing `db.runtime` pool across all models in the create_tables loop
- The downstream "stick with async path" forced choice MUST become a free choice

## Tech Stack

- Backend: Kailash Core SDK + DataFlow + Nexus (the SDK itself; this is BUILD repo work)
- Database: PostgreSQL (Supabase pgbouncer in session mode is the failure surface for #714; PostgreSQL 14+ for tests)
- AI: N/A
- Test infra: real pytest tier 2 + tier 3 (NO mocking per `rules/testing.md`); pgbouncer container required for #714 regression

## Constraints

- **No workarounds** (`rules/zero-tolerance.md` Rule 4): this is the SDK; fix at root, don't paper over.
- **Fixes MUST land such that the downstream `mediscribe-v2/backend/app/main.py:417-486` workaround can be deleted entirely.** Partial fixes that leave any of the three workarounds necessary fail the spec.
- **Cross-SDK parity**: kailash-rs has equivalent runtime-binding question (Tokio vs non-Tokio); file companion issues OR justify Python-specific.
- **Tier 2/3 regression tests**: `rules/testing.md` § "End-to-End Pipeline Regression". Each fix MUST come with a regression test that fails on main and passes on the fix branch.
- **Backwards compatibility**: `rules/zero-tolerance.md` Rule 6a — public-API removal requires a deprecation cycle. New public APIs (`Nexus.add_lifespan_handler`) ship cleanly; existing public APIs that change behavior need a deprecation note.
- **PR-per-issue or bundled**: decide at /todos. Mediscribe needs all three to drop the workaround, but reviewability favours separate PRs. Default: separate PRs that can land on the same release.
- **BUILD repo discipline** (memory `feedback_build_repo_release.md`): proceed through /release after merge.

## Users

- **Downstream SDK consumers building Nexus + DataFlow apps** — the primary audience. Mediscribe is one; the patterns they hit are common enough that any FastAPI-style consumer would hit them.
- **Kailash SDK contributors** — fixes need to be discoverable patterns for future Nexus/DataFlow work.

## Out of scope (explicit)

- **#711 (`db.transactions_sync.begin()`)** — separate enhancement, separate workstream. Filed today as follow-up to #707; not part of this Mediscribe incident cluster.
- **W7 cross-SDK trace gap (#677, #678)** — separate cleanup, low coupling to this work.
- **`git.md` overflow** — separate hygiene task.
- **`ModelNotFoundError` two-class divergence** — separate decision-journal task.

## Cross-references

- Originating consumer: https://github.com/vflores-io/mediscribe-v2/commit/d5b3bd15
- Issue bodies: `gh issue view 712 713 714 -R terrene-foundation/kailash-py`
- Cross-SDK companion: esperie/kailash-rs#688 (referenced from #711, applies in spirit to #713's runtime-binding question for Tokio)
- Related shipping: PR #707 (`db.transactions.begin()` async surface) — same release window candidate
