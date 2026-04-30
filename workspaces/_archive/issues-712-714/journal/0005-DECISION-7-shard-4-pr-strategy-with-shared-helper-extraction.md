---
type: DECISION
created: 2026-04-29
issue: 712,713,714
phase: 02-todos
---

# DECISION — 7 shards across 4 PRs, helper-first extraction for #712

## Decisions captured at /todos

### 1. 7 shards, not fewer (capacity budget)

Per `rules/autonomous-execution.md` § Per-Session Capacity Budget,
each shard MUST stay within ≤500 LOC load-bearing logic / ≤5-10 invariants /
≤3-4 call-graph hops. The work decomposed naturally into:

| Shard  | Issue     | Why a separate shard                                                                                                                                            |
| ------ | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1 | #712      | Helper extraction is independent (no consumer depends on it yet); blocks S2/S3                                                                                  |
| S2 | #712      | Sibling-site patches need the helper; coordinate-different file from S1 to allow parallel work later                                                            |
| S3 | #712      | Public API + spec is a discrete change; touches different files than S1/S2; can land in same PR                                                                 |
| S4 | #713      | Property + setter + kwarg + per-loop cache + pickle compat is ~265 LOC of load-bearing logic                                                                    |
| S5 | #713      | Subsystem captures across 6 files is mechanical but spans multiple files; budgeted as separate shard so an agent isn't holding S4's invariants AND S5's at once |
| S6 | #714      | DDL refactor + pgbouncer test infrastructure is a clean separable surface                                                                                       |
| S7 | spec/docs | Spec re-derivation per Rule 5b is non-trivial; doing it after all code lands lets it observe actual final surface                                               |

### 2. 4 PRs, not 7 (review efficiency)

Bundle by issue, not by shard. Reviewer benefits from seeing the helper +
sibling sweep + public API together for #712 (single PR-A). Conversely, S4
and S5 are tightly coupled (S5 reads S4's property) and bundle into PR-B.
S6 is independent enough to ship as its own PR-C. S7 specs land last in PR-D.

Alternative considered: one mega-PR. Rejected — too big for review; per
`rules/git.md`, atomic commits per logical change, separate PRs per fix.

Alternative considered: 7 micro-PRs. Rejected — adds reviewer ceremony for
no benefit; S1+S2+S3 share concepts and tests, splitting them costs review
time without clarity gain.

### 3. Naming: `add_startup_handler` (chose), not `on_startup` or `lifespan`

`Nexus.add_startup_handler(func)` chosen because:

- Parallels existing `Nexus.add_plugin(plugin)` — same verb-noun pattern
- Doesn't shadow FastAPI's `@app.on_event("startup")` decorator (avoids confusion when both exist)
- "Handler" matches `_startup_hooks` internal naming and the plugin protocol's `on_startup` method signature

Alternatives considered:

- `Nexus.on_startup(func)` — shorter but conflicts with the FastAPI decorator semantically
- `Nexus.lifespan(startup, shutdown)` — context-manager style, but consumers want one-shot registration not context management
- `Nexus.register_startup(func)` — verbose, breaks parallel with `add_plugin`

Decision deferred to /todos human-approval gate per the brief constraint.
Recommend `add_startup_handler` but accept reviewer override.

### 4. pgbouncer container in test infrastructure (not mocked)

Per `rules/testing.md` § "Tier 3 (E2E): Real everything; every write
verified with read-back" + § "End-to-End Pipeline Regression": the #714
failure mode (`MaxClientsInSessionMode` from pgbouncer) ONLY surfaces
against real pgbouncer in session mode. Mocking pgbouncer's connection
cap defeats the regression test.

Alternative considered: assert via static analysis that the DDL path uses
single-connection. Rejected — fragile, breaks on refactor; behavioral test
preferred per `rules/testing.md` § "Behavioral Regression Tests Over Source-Grep".

Alternative considered: skip the Tier-3 test, rely on Tier-2 connection-count
assertions against PostgreSQL directly. Rejected — pgbouncer is the
specific production failure surface; covering it is the regression
test's job.

### 5. DDL bypass `AsyncSQLDatabaseNode` (not "reuse db.runtime pool")

The brief recommended "reuse the runtime's existing connection pool." But
deep-dive verified `AsyncLocalRuntime` does NOT expose a connection pool —
it's a workflow runtime. There's no "runtime pool" to reuse.

The correct fix is to bypass `AsyncSQLDatabaseNode` for DDL and acquire ONE
connection directly from `self._connection_manager`. Routing DDL through a
node-with-pool is overkill: DDL is single-connection work that doesn't
need pool/transaction-mode/fetch-mode plumbing.

This is also the cleanest path forward for testing — single-connection
behavior is observable via `pg_stat_activity` count.

### 6. Wave plan: ≤3 worktree agents per wave (rules/worktree-isolation.md Rule 4)

Wave 1: {S1, S4, S6} parallel (3 agents, exactly at the cap). Independent
files, no merge contention.

Wave 2: {S2, S3, S5} after wave 1 (3 agents). S2 depends on S1; S3 doesn't
strictly depend on S1 but reads its API surface; S5 depends on S4. All
target different files within a single sub-package.

Wave 3: {S7} solo after all code lands.

Critical-path latency: 3 worktree-agent durations sequentially. For
~1400 LOC across 7 shards, autonomous estimate: 2-3 sessions including
review cycles.

### 7. Cross-SDK companion only for #714

Per the analyze findings:

- #712 has no kailash-rs analog (axum + tokio architecture)
- #713 has no kailash-rs analog (Tokio runtime always present)
- #714 may have kailash-rs analog (DDL connection thrash)

File one companion issue at PR-C open against esperie/kailash-rs.

## Open questions for human-approval gate

1. **Public API name** — `add_startup_handler` (chosen) vs alternatives. Default to chosen unless reviewer prefers different.
2. **PR bundling** — 4 PRs (A: #712, B: #713, C: #714, D: specs) vs 1 mega-PR. Default to 4.
3. **S7 splitting** — keep as one shard, or split into S7a (dataflow) + S7b (nexus) for parallel review? Default: keep as one; spec re-derivation is small enough.
4. **kailash-rs companion timing** — file at PR-C open, or after #714 lands cleanly? Default: at PR-C open with note.

## Dependencies on prior decisions

- Helper-first extraction (S1) was decided in `01-analysis/01-architecture.md` after the deep-dive agent confirmed 3 unmitigated sibling sites. Without the sibling finding, the canonical inline iteration in `workflow_server.py` would have been sufficient.
- Property + setter (S4) was chosen over alternatives "just lazy method" or "explicit kwarg only" after deep-dive showed 1 existing test relies on `db.runtime = X` mutation pattern (`test_string_id_type_coercion_integration.py:35`) — preserving that pattern requires a setter.
- DDL bypass (S6) was chosen over "reuse runtime pool" after deep-dive established the runtime is a workflow runtime, not a connection runtime.

All three decisions are evidence-driven from the parallel deep-dive sweep
mandated by `rules/agents.md` for ≥3-issue briefs.
