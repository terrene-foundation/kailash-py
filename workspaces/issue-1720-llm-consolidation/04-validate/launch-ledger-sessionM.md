# Launch Ledger — session M (2026-08-10)

Durable orchestration record per `rules/orchestration-launch-ledger.md` MUST-1.
Consult BEFORE every spawn (MUST-2); match every completion against it (MUST-3).

Branch: `fix/issue-1720-forest-drain` · PR **#2016 OPEN** · base `main`.

## Wave 1 — CI red-to-green (3 independent shards, disjoint file scopes)

Entry state: CI **33 pass / 3 fail** on head `fix/issue-1720-forest-drain`.
All three agents run in the MAIN checkout (NOT worktrees) — deliberate, see § Isolation note.

| track       | agent | scope (disjoint)                                | branch                      | status    |
| ----------- | ----- | ----------------------------------------------- | --------------------------- | --------- |
| W1-dataflow | W1-df | `packages/kailash-dataflow/**` (adapters+tests) | fix/issue-1720-forest-drain | in-flight |
| W1-ml       | W1-ml | `packages/kailash-ml/**`                        | fix/issue-1720-forest-drain | in-flight |
| W1-codeql   | W1-cq | read-only diagnosis, `.github/workflows/**`     | fix/issue-1720-forest-drain | in-flight |

### Failure inventory (measured, not inferred)

**A — `Test DataFlow Unit Suite (Tier 1)`** run 31323588202, step "DataFlow infra-free regression
gates": `4 failed, 678 passed, 6 skipped, 176 deselected in 47.42s`. All four in
`tests/regression/test_issue_1502_sqlite_memory_shared_cache.py`:

- `test_memory_shared_cache_ddl_and_crud_reach_same_db` — `AdapterError: Unsupported database
scheme: file. Supported schemes: mariadb, mongodb, mysql, pgsql, postgres, postgresql, sqlite`
- `test_two_memory_instances_are_isolated` — same
- `test_model_registry_sync_path_reaches_shared_memory_db` — `assert False is True`
- `test_close_disposes_registry_pool_no_id_reuse_aliasing` — `registry StaticPool should exist for
this instance's URI before close()`

Suspect commit `d8b29d038` (per-dialect identifier budgets, fail-closed) — it is one of only two
commits touching `packages/kailash-dataflow/src/dataflow/adapters/` on this branch, and `git log -S
"Unsupported database scheme"` names it. **Hypothesis, not established** — the agent proves it.

**B — `Base (Python 3.12)` / Coverage** run 31323588102: `18 failed, 2437 passed, 36 skipped in
507.10s`. Coverage gate itself PASSED (75.88% ≥ 60%) — the job fails on test failures, NOT coverage.
All 18 in `packages/kailash-ml/tests/integration/`:
`test_feature_materialiser_wiring.py` (9), `test_feature_store_erase_tenant_wiring.py` (7),
`test_online_store_and_reopen_wiring.py` (2). Every one:
`FeatureStoreError(reason='materialize failed: TypeError', tenant_fingerprint='sha256:...')`.
The real `TypeError` is swallowed into `reason=` — the agent must recover the underlying traceback.

**C — `CodeQL`** check-run 93271127308, `fail` in **11s**, while the actual analysis job
"Analyze Python" (run 31323588135) **passed in 7m46s**. `gh run view --log-failed` on that run
returns EMPTY ⇒ the red is NOT an Actions job failure. Session-L notes claim the open alerts are
pre-existing quality findings (`py/unused-import`, `py/cyclic-import`, `py/repeated-import`,
`py/catch-base-exception`) with no security severity — **that claim is UNVERIFIED and is exactly
what shard C establishes or refutes.**

### Isolation note (deliberate deviation from worktree default)

`worktree-isolation.md` Rule 1 prefers sibling worktrees for parallel agents. NOT used here, for two
recorded reasons: (1) session-L trap — the venv's editable installs resolve `kailash*` to the MAIN
repo, so a worktree agent's probe silently measures unmutated main code; (2) the three scopes are
genuinely disjoint packages, and agents are instructed NOT to `git commit` (orchestrator commits
centrally), which removes the index race that motivates isolation for same-tree parallel work.

## Wave 1b — `#2005` re-triage + fix (launched alongside Wave 1)

| track     | agent     | scope                                                             | status    |
| --------- | --------- | ----------------------------------------------------------------- | --------- |
| W1-tenant | W1-tenant | `packages/kailash-kaizen/src/kaizen/memory/enterprise.py` + tests | in-flight |

`#2005` re-triaged INCREMENTAL → BUG (`deferred-quality` removed, `bug`+`security` added;
rationale posted as issue comment). Grounds: (1) the issue's OWN text calls it "the same
structural shape as a defect fixed on `fix/issue-1720-forest-drain` — a falsy identity widening
scope through a truthiness `or`-chain", which fires `autonomous-execution.md` MUST-4's
fix-while-warm mandate and BLOCKS a sixth defer; (2) `product-completion-first.md` MUST-1 is
fail-closed and a tenant-isolation shape resolves ON-LIST. **Scope verified disjoint** —
`memory/enterprise.py` is NOT in this branch's diff (`git diff --name-only origin/main..HEAD`).

## Wave 2 — after CI green (planned, not launched)

1. Merge #2016 — pinned-head READ, then MERGE as a **separate command** per `git.md`
   § "CI-check and merge are SEPARATE steps".
2. `/release` in dependency order. **Deltas measured against pypi.org, not assumed:**

   | package          | local  | PyPI   | release owed           |
   | ---------------- | ------ | ------ | ---------------------- |
   | kailash          | 2.63.0 | 2.62.0 | **YES — FIRST (root)** |
   | kailash-kaizen   | 2.46.0 | 2.45.0 | YES                    |
   | kailash-nexus    | 2.16.0 | 2.15.0 | YES                    |
   | kailash-dataflow | 2.20.0 | 2.19.1 | YES                    |
   | kailash-ml       | 2.2.3  | 2.2.2  | YES                    |
   | kailash-mcp      | 0.5.1  | 0.5.1  | already published      |
   | kailash-align    | 0.7.4  | 0.7.4  | no                     |
   | kailash-pact     | 0.18.0 | 0.18.0 | no                     |

   **Corrects a stale session-L/earlier claim that "no kailash-ml release is owed"** — there IS a
   2.2.2→2.2.3 delta, and W1-ml is changing ml source this session, so re-verify at release time.
   kaizen 2.46.0 carries a `### Changed (BREAKING)` entry (`matches_requirement` async→sync).

3. Decision B: kailash-mcp 0.5.0/0.5.1 were published from an UNMERGED branch. After merge, cut
   `mcp-v0.5.1` from main so the tag matches the published artifact.
4. Decision C: residuals P2/P3 could not be filed — no substantive content survives. Filing would
   mean inventing findings. Accept the loss; do NOT fabricate.
