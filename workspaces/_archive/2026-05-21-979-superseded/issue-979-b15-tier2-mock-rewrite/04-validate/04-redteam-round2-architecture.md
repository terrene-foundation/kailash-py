# Red Team Round 2 — Architecture Plan v2

## Round-1 closure verification

| Round-1 finding                                                                      | Status in v2                                                                                                                                                                                                        | v2 paragraph                                                                                                                            |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| arch HIGH-1 (mock counts stale, cache file 27 not 1)                                 | CLOSED                                                                                                                                                                                                              | § "Verified per-file state" — verified totals 28/2/4/1/29/37/13/13/1 = 128                                                              |
| arch HIGH-2 (worktree Rule 1/5/6 prompt skeletons absent)                            | CLOSED                                                                                                                                                                                                              | § "Parallel-launch strategy" — pre-flight bash + agent prompt skeleton enumerate path-pin, cwd-verify, branch-verify, commit discipline |
| arch HIGH-3 (Shard 4 journal entry path unspecified)                                 | PARTIAL — file name now `DECISION-shard-classifications.md` (Shard 3 step 5) but the numbered prefix (e.g. `0001-`) is absent. RECOMMEND tighten to `journal/0001-DECISION-...md` per HIGH-3                        |
| arch HIGH-4 (Cluster B concurrent-acquire pattern under-specified)                   | CLOSED-BY-DROP — Shard 2 no longer ships a new Tier-2 file (DF-1 CRIT closure made the concern moot)                                                                                                                |
| arch HIGH-5 (File 4 Tier-2 PG regression min harness)                                | CLOSED-BY-DROP — v1 Cluster C deleted; regression is now SQLite-anchored move to `tests/regression/`                                                                                                                |
| arch HIGH-6 (Invariant 1b cross-tier sum)                                            | CLOSED                                                                                                                                                                                                              | Shard 1 Invariant 1 explicitly sums unit + regression collection counts; "Hand-typed counts BLOCKED" cites testing.md                   |
| dataflow CRIT (DF-1 duplicate Tier-2 coverage)                                       | CLOSED                                                                                                                                                                                                              | Shard 2 § Scope step 2 — DELETE the plural-dir file; cite singular path as migration target                                             |
| dataflow HIGH (DF-2 table name `dataflow_migration_locks`)                           | CLOSED                                                                                                                                                                                                              | Changelog row "dataflow_migration_locks (not kml_migration_locks)"                                                                      |
| dataflow HIGH (DF-3 `_execute_workflow_safe` is sync; bug class closed)              | CLOSED                                                                                                                                                                                                              | § "Why v2" point 2; Shard 1 special handling per File 4                                                                                 |
| dataflow HIGH (DF-3-supplemental `test_simulated_fastapi_lifespan` Rule-3 violation) | CLOSED                                                                                                                                                                                                              | Shard 1 Step 5 (DELETE); Invariant 7 (zero occurrences)                                                                                 |
| dataflow HIGH (DF-4 pool_size cargo-cult)                                            | CLOSED                                                                                                                                                                                                              | Changelog "pool_size=2 dropped from Shard 2"                                                                                            |
| testing HIGH-1 (regression tests misplaced)                                          | CLOSED                                                                                                                                                                                                              | Shard 1 Step 5 moves `test_original_bug_scenario` to `tests/regression/` with `@pytest.mark.regression`                                 |
| testing HIGH-2 (naming feature_scenario_result)                                      | CLOSED                                                                                                                                                                                                              | File 9 renamed to `test_tdd_mode_propagates_to_node_generator.py`                                                                       |
| testing HIGH-3 (Shard 4 strict-sequencing)                                           | CLOSED                                                                                                                                                                                                              | Shard 3 § "Sequencing reason" — strictly after Shards 1+2 merge to main                                                                 |
| testing HIGH-4 (E2E TDD-mode pipeline regression)                                    | UNCLOSED-BUT-DOCUMENTED — v2 "Out of scope" notes this is orthogonal; original disposition was "follow-up issue." Per `value-prioritization.md` MUST-2, deferral needs a value-anchor; v2 silently inherits from v1 |

## New issues surfaced by v2

- **[N-1 type:HIGH] Regression filename violates `test_issue_<N>_<slug>.py` convention.** v2 names the file `test_issue_async_safe_run_no_event_loop_bridge.py` — no issue number. Every existing file in `packages/kailash-dataflow/tests/regression/` follows `test_issue_<N>_<slug>.py` (verified: 24 files, all numbered, e.g. `test_issue_352_fastapi_startup.py` is the canonical sibling). The bug class (event-loop bridging) was closed in v0.10.11; issue #992 owns the test-rewrite, NOT the bug. Recommend grep for the original GitHub issue that documented the FastAPI lifespan bug (looks adjacent to #352) and adopt that number. If no issue exists, file one for traceability per `git.md` § Discipline before Shard 1 lands.

- **[N-2 type:MED] Shard 1 invariant count is 7, but the work bundles 8 file moves + 1 regression carve-out + 1 delete + 1 rename across 2 destination tiers.** Walking the invariants: (1) cross-tier sum, (2) pytestmark presence, (3) decorator removal, (4) AST scan zero mocks, (5) clean-venv collection, (6) git-log-follow rename, (7) regression file uses mark + lifespan deleted. Plus implicit invariants the plan glosses: (8) drop dead `test_suite`/`runtime` fixtures (Step 3) AND drop unused `IntegrationTestSuite` imports (Step 4) MUST NOT break collection on Files 1, 3; (9) File 9 rename preserves test bodies. Count = 9, not 7. Per `autonomous-execution.md` MUST-1 (≤5–10 invariants), still within budget but at the upper edge. Recommend explicitly listing all 9 OR split File 4 split-out into its own shard (Shard 1a moves only; Shard 1b owns File 4 split + File 9 rename).

- **[N-3 type:MED] Cluster A count is "8 Tier-1 moves" but File 4 produces TWO destinations.** v2 § Verified per-file state classifies File 4 as "Tier-1 move (SUT obsolete; regression carve-out per §Shard 3 below)" — but Shard 1 Step 5 actually does BOTH a unit move (lines 50-145, 321-365, 562-606) AND a regression carve-out (lines 612-660). That's 1 source file → 2 destinations. Cluster A is "7 Tier-1 moves + 1 split" rather than "8 Tier-1 moves." Cosmetic mislabeling, but the per-file invariant arithmetic depends on it.

- **[N-4 type:MED] File 4 line ranges include `test_async_safe_run_in_async_context` (lines 330-339) which exercises async-context behavior. Verified line 321-365 also includes `test_execution_context_detection` and `test_execution_context_detection_async` — both pytest-asyncio (live event loop required).** These ARE pure Tier-1 tests under the new contract (no PG needed; deterministic; `asyncio.sleep(0.01)`), so the unit move is correct. BUT line 562-606 includes `test_dataflow_creation_async` + `test_dataflow_initialize_async` (verified) which construct a real `DataFlow("sqlite:///:memory:")` and call `await db.initialize()`. These exercise SUT wiring not pure helpers. Spot-check passes: SQLite is permitted in Tier 1 per `tests/CLAUDE.md` § "Allowed Dependencies by Tier" Unit Tests = "SQLite databases ... Lightweight, no external infrastructure required". No fix needed; line ranges are tier-1-compatible.

- **[N-5 type:MED] Pre-flight bash uses `git rev-parse main` (stale-base risk).** Per `worktree-isolation.md` MUST Rule 5, "the orchestrator MUST verify `git merge-base <new-branch> <target-branch>` equals the CURRENT tip of `<target-branch>` at launch time." `git rev-parse main` returns the LOCAL main tip; if local main hasn't been fetched, this branches from a stale base. The verification loop catches drift between branches and `target_head`, but does NOT catch local-main-stale. Recommend: `git fetch origin && target_head=$(git rev-parse origin/main)` to anchor on remote.

- **[N-6 type:MED] Shard 2's full-file delete needs a commit-body rationale per `git.md` § Discipline.** v2 Shard 2 Step 2 says "Deletion commit message MUST cite the singular path as the migration target" — partial compliance. `git.md` MUST: "Commit bodies MUST answer **why**, not **what**." Tighten the prescription: the commit body MUST cite (a) the singular-dir path that replaces the deleted coverage, (b) the DF-1 finding that justifies the delete, (c) the date/PR that established the duplicate-coverage state. `git log --follow` does NOT follow a pure delete (no rename), so the audit trail lives entirely in the commit body.

- **[N-7 type:LOW] `test_simulated_fastapi_lifespan` IS a Rule-3 violation as v2 claims** — verified at lines 663-684: `try: result = await db.initialize() ... except Exception as e: pass` — bare swallow-exception. v2's "delete outright" disposition is correct. (Spot-check confirms the v2 framing.)

- **[N-8 type:LOW] v2 doesn't audit for new BLOCKED rationalizations.** Scan for "scaffold for now" / "Phase-1 / Phase-2" / "deferred" / "we'll catch in /redteam" — `grep -i 'scaffold\|phase-?[12]\|deferred\|catch in.*redteam' 01-architecture-plan-v2.md` returns ZERO matches. v2 is clean of split-state framings per `spec-accuracy.md`.

- **[N-9 type:LOW] Shard 3 "verification gate" issues `gh issue close 992` without confirming cross-SDK inspection per `cross-sdk-inspection.md` Rule 5.** Shard 3 step 6 cites `git.md` § Issue closure (PR SHA req) but doesn't include the cross-SDK checklist. Recommend appending step 5b: read kailash-rs issue list for mock-integration-tier work; record disposition in journal entry. Reading-only is permitted per `repo-scope-discipline.md`; only acting would cross the line.

## Verdict

APPROVE-WITH-FIXES

v2 closes 13 of 14 Round-1 HIGH/CRIT findings cleanly (one — testing HIGH-4 E2E TDD-mode gap — remains UNCLOSED, but is structurally out of scope per the brief and per `value-prioritization.md` requires a follow-up issue with value-anchor, not a same-shard fix). The new structure (Shard 1 + Shard 2 + Verification Gate) is materially better than v1: Shard 2 has shrunk from "build new Tier-2 file" to "delete duplicate" — a much smaller blast radius. The plan is internally consistent against `specs/testing-tiers.md`, `rules/zero-tolerance.md` Rule 3, `rules/testing.md` § Regression, and `rules/worktree-isolation.md`.

Fixes required before `/todos`:

1. **N-1 (HIGH)**: regression filename — adopt `test_issue_<N>_<slug>.py`; if no existing issue documents the FastAPI-lifespan event-loop bug class, file one (the original "v0.10.11 ARCHITECTURE FIX" cited in v2 § Why v2) before Shard 1 lands.
2. **N-2 / N-3 (MED)**: re-count Shard 1 invariants (9, not 7) and reclassify Cluster A as "7 moves + 1 split."
3. **N-5 (MED)**: use `git fetch origin && git rev-parse origin/main` in pre-flight bash.
4. **N-6 (MED)**: tighten Shard 2 commit-body prescription per `git.md` § Discipline.
5. **N-9 (LOW)**: add cross-SDK inspection step to Shard 3 verification gate.

testing HIGH-4 (E2E TDD-mode pipeline regression) stays UNCLOSED as flagged in the closure table. Per `value-prioritization.md` MUST-2, file as a separate workspace todo with explicit value-anchor citing the brief, NOT as a v2 deferral.

## Verification command outputs

```bash
# N-1 — regression filename convention verified empirically
$ ls packages/kailash-dataflow/tests/regression/test_issue_*.py | wc -l
24
$ ls packages/kailash-dataflow/tests/regression/ | grep -v '^test_issue_' | grep -v __pycache__ | head -5
# (only conftest.py and non-issue-pattern regression files remain)

# N-7 — Rule-3 violation in test_simulated_fastapi_lifespan
$ sed -n '662,684p' packages/kailash-dataflow/tests/integration/migrations/test_async_safe_run_integration.py
# (verified: try: ...; except Exception as e: pass — bare swallow-exception)

# N-8 — BLOCKED rationalization scan on v2 plan
$ grep -ciE 'scaffold|phase-?[12]|deferred|catch in.*redteam' \
    workspaces/issue-979-b15-tier2-mock-rewrite/02-plans/01-architecture-plan-v2.md
0

# N-3 — File 4 line ranges produce 2 destinations
$ grep -n 'unit/migrations/test_async_safe_run\|regression/test_issue_async_safe_run' \
    workspaces/issue-979-b15-tier2-mock-rewrite/02-plans/01-architecture-plan-v2.md
# (2 distinct destination paths from one source file)

# DF-1 closure verification — singular-dir real-PG coverage exists
$ grep -c 'IntegrationTestSuite\|asyncpg.connect\|@patch\|MagicMock' \
    packages/kailash-dataflow/tests/integration/migration/test_migration_lock_manager_integration.py
# (IntegrationTestSuite + asyncpg present; @patch/MagicMock absent — real-PG, zero mocks)
```
