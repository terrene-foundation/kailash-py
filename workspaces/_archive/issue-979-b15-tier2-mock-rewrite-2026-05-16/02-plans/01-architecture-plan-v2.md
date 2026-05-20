# Architecture Plan v2 — #992 B-1.5 Tier-2 Mock Rewrite

Supersedes: `00-architecture-plan.md` (v1 — REJECTED by Round-1 red team).
Round-1 findings: `04-validate/01-redteam-architecture.md` (6 HIGH),
`04-validate/02-redteam-dataflow.md` (1 CRIT + 3 HIGH — REJECT),
`04-validate/03-redteam-testing.md` (4 HIGH).

## Why v2

Round 1 surfaced three load-bearing corrections, all verified directly:

1. **`tests/integration/migration/test_migration_lock_manager_integration.py`
   (singular dir) already provides real-PG `IntegrationTestSuite`-based
   coverage for `MigrationLockManager`.** v1 Shard 2 would have shipped
   duplicate Tier-2 coverage. v2 Shard 2 collapses to "extract Tier-1
   param-conversion + DELETE the rest."

2. **`_execute_workflow_safe` is now SYNC** (uses `SyncDDLExecutor` per
   `auto_migration_system.py:40-114`, "ARCHITECTURE FIX (v0.10.11)"). The
   event-loop bug class File 4's regression tests target is **closed in
   production code**. v1 Shard 3's PG-regression rationale is stale.

3. **Issue body mock counts are wildly understated.** Verified totals:
   28/2/4/1/29/37/13/13/1 = **128 mock sites** across 9 files (issue
   body claims 74). Plan must cite verified numbers, not issue body.

## Value-anchor (verbatim — UNCHANGED)

> `specs/testing-tiers.md` § Tier-2 Contract Rule 1:
> "Per `rules/testing.md` § 'No Mocking in Tier 2/3', integration tests MUST
> exercise real infrastructure: Real PostgreSQL via `IntegrationTestSuite`;
> Real Redis / Mongo / MySQL when subject under test requires them; Real
> `AsyncLocalRuntime` / `LocalRuntime`; Real network calls (mockable at the
> response layer only via VCR-style cassettes)."

## Verified per-file state (mock counts from `grep -cE`)

| #   | File (`packages/kailash-dataflow/tests/integration/`)       | Mock count | Classification                                                                                                                                           |
| --- | ----------------------------------------------------------- | ---------: | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `cache/test_cache_invalidation.py`                          |     **28** | Tier-1 move                                                                                                                                              |
| 2   | `core/test_dataflow_engine_lock_integration.py`             |      **2** | Tier-1 move                                                                                                                                              |
| 3   | `migration/test_impact_reporter_unit.py`                    |      **4** | Tier-1 move                                                                                                                                              |
| 4   | `migrations/test_async_safe_run_integration.py`             |      **1** | Tier-1 move (SUT obsolete; regression carve-out per §Shard 3 below)                                                                                      |
| 5   | `migrations/test_auto_migration_system_lock_integration.py` |     **29** | Tier-1 move                                                                                                                                              |
| 6   | `migrations/test_migration_lock_manager_integration.py`     |     **37** | Tier-1 split + delete mocked block (real-PG coverage already lives at `tests/integration/migration/test_migration_lock_manager_integration.py` singular) |
| 7   | `migrations/test_migration_test_framework.py`               |     **13** | Tier-1 move                                                                                                                                              |
| 8   | `package/test_package_installation_unit.py`                 |     **13** | Tier-1 move                                                                                                                                              |
| 9   | `test_real_tdd_integration.py`                              |      **1** | Tier-1 move + rename                                                                                                                                     |

Total: **128 mock sites** across 9 files (NOT 74 as issue #992 body claims).
Update body verification: `grep -cE "@patch|MagicMock|AsyncMock|unittest\.mock|Mock\(\)" packages/kailash-dataflow/tests/integration/<path>`.

## Shard plan (v2 — 2 shards + verification gate)

|   # | Shard                                                          | Files |  LOC delta | Invariants | Parallel?           |
| --: | -------------------------------------------------------------- | ----- | ---------: | ---------: | ------------------- |
|   1 | Cluster A — 8 Tier-1 moves (Files 1, 2, 3, 4, 5, 7, 8, 9)      | 8     |      ~-200 |          7 | yes                 |
|   2 | Cluster B — File 6 split: Tier-1 extract + DELETE mocked block | 1 → 1 | -300 / +50 |          4 | yes                 |
|   3 | Verification gate                                              | 0     |          0 |          4 | sequenced AFTER 1+2 |

v1's Cluster C (File 4 split with PG-regression carve-out) is **dropped**.
File 4 becomes a pure Tier-1 move (in Cluster A) with the bug-fix-already-shipped
context noted in the move commit. The `test_simulated_fastapi_lifespan` test
violates `rules/zero-tolerance.md` Rule 3 (swallow exceptions for "smoke test"
pattern — dataflow-specialist DF-3-supplemental) and is **deleted in Shard 1**.
The `test_original_bug_scenario` test is renamed and moved to
`packages/kailash-dataflow/tests/regression/test_issue_async_safe_run_no_event_loop_bridge.py`
per `rules/testing.md` § Regression (regression tests are permanent and live
in `tests/regression/`).

### Shard 1 — Cluster A: 8 Tier-1 moves (mechanical + regression carve-out)

**Value-anchor (per `rules/value-prioritization.md` MUST-2):** restores the
Tier-1 contract from `specs/testing-tiers.md` § Tier-1 for 8 files
self-declared Tier-1 (pytestmark, filename, docstring) but mechanically moved
by S4 (PR #988) to `tests/integration/`.

**Scope:**

For Files 1, 2, 3, 4, 5, 7, 8, 9:

1. `git mv` to `tests/unit/<appropriate-subdir>/`.
2. Drop `@pytest.mark.integration` class decorators.
3. Drop dead `test_suite` / `runtime` fixtures (Files 1, 3).
4. Drop unused `from tests.infrastructure.test_harness import IntegrationTestSuite`
   imports (Files 1, 3).
5. **File 4 special handling:**
   - Move helper-existence + sync-context tests (lines 50-145, 321-365, 562-606) to
     `tests/unit/migrations/test_async_safe_run.py`. The helper still exists at
     `packages/kailash-dataflow/src/dataflow/core/async_utils.py:80,121`
     (`get_execution_context`, `async_safe_run`) — verified.
   - **Move** `test_original_bug_scenario` (lines 612-660) to
     `packages/kailash-dataflow/tests/regression/test_issue_async_safe_run_no_event_loop_bridge.py`
     with `@pytest.mark.regression`. Keep the SQLite-based assertion verbatim — it's
     the documented historical regression and per `rules/testing.md` § Regression,
     regression tests are PERMANENT even after the bug class moves.
   - **Delete** `test_simulated_fastapi_lifespan` (lines 662-684) — it's a
     `try: ...; except Exception: ...` smoke-test pattern (Rule 3 violation).
6. **File 9 rename:** `test_real_tdd_integration.py` → `test_tdd_mode_propagates_to_node_generator.py`
   per `rules/testing.md` § Rules `test_[feature]_[scenario]_[expected_result].py`.
   "Real_integration" in the original name is actively misleading (every test patches
   7 init phases).

**Invariants (7):**

1. **Test count preservation per file (cross-tier sum)**: `pytest --collect-only -q
packages/kailash-dataflow/tests/unit/<file>` + `pytest --collect-only -q
packages/kailash-dataflow/tests/regression/<file>` total = pre-move
   collection count for each of Files 1-9. Hand-typed counts BLOCKED per
   `rules/testing.md` § MUST: Verified Numerical Claims.
2. `pytestmark = pytest.mark.unit` present on each moved file (already present
   on Files 1, 2, 3, 8 per audit; add where missing).
3. No `@pytest.mark.integration` class decorator survives in any moved file.
4. `tests/integration/conftest.py:120-145` AST scan reports zero mock imports
   in the 8 moved files' new paths (they're no longer in `tests/integration/`).
5. Each moved file collects cleanly in a clean
   `pip install -e packages/kailash-dataflow[dev]` venv.
6. File 9 rename: `git log --follow tests/unit/core/test_tdd_mode_propagates_to_node_generator.py`
   traces back to the old name; internal docstring + module comment updated.
7. File 4 split: regression file uses `@pytest.mark.regression` AND
   `test_simulated_fastapi_lifespan` is GONE (zero occurrences in
   `tests/regression/` and `tests/unit/`).

### Shard 2 — Cluster B: File 6 split (Tier-1 extract + DELETE mocked block)

**Value-anchor (per `rules/value-prioritization.md` MUST-2):** removes the
duplicate-mocked tier-2 file. Real `MigrationLockManager` Tier-2 coverage
already lives at `tests/integration/migration/test_migration_lock_manager_integration.py`
(singular dir) — VERIFIED 2026-05-15: zero mocks, real `IntegrationTestSuite`,
real `asyncpg`, real concurrent acquire / release / status / ctx-mgr tests.
Per `facade-manager-detection.md` Rule 1, the manager-shape class IS covered.

**Scope:**

1. **Extract Tier-1 param-conversion suite to** `tests/unit/migrations/test_connection_adapter_param_conversion.py`:
   - `TestConnectionManagerAdapter` (lines 24-227 of File 6) — `%s` → `$1`
     string-algorithm tests.
   - `TestParameterConversionEdgeCases` (lines 392-466) — edge cases.
   - Preserve every test method body verbatim. Drop only the mock setup
     since the `ConnectionManagerAdapter._convert_parameters` SUT is pure
     string transformation (does not require an adapter instance or a
     mocked `execute_query`).
2. **Delete** `packages/kailash-dataflow/tests/integration/migrations/test_migration_lock_manager_integration.py`
   in full. The mocked `TestMigrationLockManagerIntegration` block (lines
   230-389) is replaced by the existing real-PG suite at
   `tests/integration/migration/test_migration_lock_manager_integration.py`
   (singular). Deletion commit message MUST cite the singular path as the
   migration target.

**Invariants (4):**

1. Tier-1 file: param-conversion test count = `TestConnectionManagerAdapter` +
   `TestParameterConversionEdgeCases` test counts from the deleted file
   (verified via `pytest --collect-only -q`).
2. `tests/unit/migrations/test_connection_adapter_param_conversion.py` collects
   cleanly without any mock imports.
3. `packages/kailash-dataflow/tests/integration/migrations/test_migration_lock_manager_integration.py`
   no longer exists.
4. `tests/integration/migration/test_migration_lock_manager_integration.py`
   (singular) is **UNTOUCHED** and continues to provide real-PG coverage.

### Shard 3 — Verification gate (sequenced after Shards 1+2 merge to main)

**Sequencing reason (per testing-specialist HIGH-3):** the
`tests/integration/conftest.py:68-117` AST scan has NO file-level exemption;
the only reason the 9 mocked files passed today is that `pytest.ini::addopts`
filters out the integration tier by default. Once Shards 1+2 land and the
9 mock-laden paths are gone, the AST scan validates the integration tier
end-to-end. Running Shard 3 mid-merge would surface false positives from
partially-landed shards.

**Scope:**

1. **Mock sweep**: `grep -rcE '@patch|MagicMock|AsyncMock|unittest\.mock|Mock\(\)'
packages/kailash-dataflow/tests/integration/` MUST report zero matches in
   the 9 originally-listed paths.
2. **AST scan**: `pytest packages/kailash-dataflow/tests/integration --collect-only -q`
   MUST succeed (proving `conftest.py:68-117` AST scan passes).
3. **Tier-1 collection**: `pytest packages/kailash-dataflow/tests/unit --collect-only -q`
   MUST succeed; new test count > old test count by the 8 moved files'
   collection sum.
4. **Regression file**: `pytest packages/kailash-dataflow/tests/regression -m regression --collect-only -q`
   MUST collect `test_issue_async_safe_run_no_event_loop_bridge.py`.
5. **Journal `DECISION-shard-classifications.md`** written to
   `workspaces/issue-979-b15-tier2-mock-rewrite/journal/` documenting per-file
   classification decisions (satisfies issue #992 AC bullet 2).
6. **Close issue #992** with `gh issue close 992` citing PR SHAs per
   `rules/git.md` § Issue closure.

**Invariants (4):**

1. Zero `unittest.mock` imports across the 9 original integration paths
   (mechanical grep).
2. AST scan passes (collection succeeds).
3. Tier-1 + regression test counts increased by the expected per-file amounts.
4. Journal entry exists and documents per-file classifications.

## Parallel-launch strategy (per `rules/worktree-isolation.md` Rules 1+4+5+6)

Shards 1 + 2 launch as a worktree wave of 2 (well under Rule 4's cap of 3).

| Shard | Worktree path                                    | Branch                              |
| ----- | ------------------------------------------------ | ----------------------------------- |
| 1     | `.claude/worktrees/issue-992-shard1-tier1-moves` | `feat/issue-992-shard1-tier1-moves` |
| 2     | `.claude/worktrees/issue-992-shard2-file6-split` | `feat/issue-992-shard2-file6-split` |

**Pre-flight discipline (per Rules 1+5+6):**

```bash
# Pin base SHA at launch
target_head=$(git rev-parse main)

# Create each worktree with explicit -b flag (Rule 6 — no harness default names)
git worktree add -b feat/issue-992-shard1-tier1-moves \
  /Users/esperie/repos/loom/kailash-py/.claude/worktrees/issue-992-shard1-tier1-moves \
  "$target_head"

git worktree add -b feat/issue-992-shard2-file6-split \
  /Users/esperie/repos/loom/kailash-py/.claude/worktrees/issue-992-shard2-file6-split \
  "$target_head"

# Verify merge-base equals current main HEAD at launch (Rule 5)
for branch in feat/issue-992-shard1-tier1-moves feat/issue-992-shard2-file6-split; do
  mb=$(git merge-base "$branch" main)
  [ "$mb" = "$target_head" ] || { echo "$branch: merge-base drift — ABORT"; exit 1; }
done
```

**Agent prompt skeleton (per Rule 1 — pin path AND verify cwd at start):**

```
Working directory (absolute, MUST be your cwd for every file edit):
  <absolute worktree path>

STEP 0 — Verify cwd before any file edit:
  git -C <worktree> rev-parse --show-toplevel
  → MUST equal <worktree>; if not, STOP and report "worktree drift detected".

STEP 0b — Verify branch:
  git -C <worktree> rev-parse --abbrev-ref HEAD
  → MUST equal <expected branch name>.

Commit discipline (Rule 6):
  After EACH file move / extraction / deletion, commit incrementally with
  conventional commit format: "test(dataflow): <shard-N> <what>".
  Exit-without-commit auto-cleans the worktree.

All file paths in your edits MUST be absolute and begin with <worktree>/.
```

**Parent verifies deliverables (per Rule 3):** after each shard agent exits,
the orchestrator runs `ls <expected file path>` and `git -C <worktree>
log --oneline` to confirm files exist and commits landed.

## Sequencing summary

```
Shard 1 (Cluster A — 8 Tier-1 moves) ──┐
Shard 2 (Cluster B — File 6 split)   ──┴──→ both PRs merge to main ──→ Shard 3 (verification gate)
```

Shards 1 and 2 are independent (disjoint file sets). Shard 3 runs strictly
sequenced after both PRs merge.

## Open questions for human gate

None — Round-1 red team's questions all resolved structurally above. The plan
is internally consistent against:

- `specs/testing-tiers.md` § Tier-1/Tier-2 contracts (verbatim citations)
- `rules/zero-tolerance.md` Rule 3 (deletes `test_simulated_fastapi_lifespan`
  smoke-test instead of porting it)
- `rules/testing.md` § Regression (moves `test_original_bug_scenario` to
  `tests/regression/` with `@pytest.mark.regression`)
- `rules/testing.md` § Naming (renames File 9 to feature_scenario_result form;
  keeps Shard 2's file names compliant)
- `rules/worktree-isolation.md` Rules 1+4+5+6 (explicit paths, pre-flight,
  commit discipline, branch names)
- `rules/facade-manager-detection.md` Rule 1 (`MigrationLockManager` Tier-2
  coverage VERIFIED to exist at singular-`migration/` path)
- `rules/value-prioritization.md` MUST-2 (value-anchors per shard)
- `rules/repo-scope-discipline.md` (stays in kailash-py)

## Out of scope (UNCHANGED from v1)

- The other 5 Workstream-B issues of #979 (#995, #996, #997, #998, #999) —
  separate workstreams.
- Cross-SDK kailash-rs sibling mock-rewrite work — separate kailash-rs session.
- Adding new tests beyond the regression carve-out and param-conversion
  extract.
- Modifying production code in `packages/kailash-dataflow/src/`. The
  classification audit and red team identified that `_execute_workflow_safe`
  is sync (correct), `MigrationLockManager` semantics are row-level INSERT
  ON CONFLICT (not advisory locks), `dataflow_migration_locks` is the table
  name (not `kml_migration_locks`). These are domain notes only — production
  code is correct, this rewrite only moves/deletes tests.

## Changelog vs v1

| Change                                                                                                 | Reason                                                                                                  | Source              |
| ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- | ------------------- |
| Drop v1 Cluster B (new Tier-2 wiring file)                                                             | Real-PG coverage already exists at singular `migration/` path                                           | DF-1 CRIT           |
| Drop v1 Cluster C (File 4 split with PG-regression carve-out)                                          | `_execute_workflow_safe` is now sync; event-loop bug class closed                                       | DF-3 HIGH           |
| File 4 split: `test_simulated_fastapi_lifespan` DELETED (was: ported to tier-2)                        | Rule 3 violation (swallow-exception smoke test)                                                         | DF-3 supplemental   |
| File 4 split: `test_original_bug_scenario` moved to `tests/regression/` with `@pytest.mark.regression` | Regression test discipline                                                                              | testing HIGH-1      |
| File 9 rename: `test_tdd_mode_init_wiring` → `test_tdd_mode_propagates_to_node_generator`              | Feature-scenario-result naming                                                                          | testing HIGH-2      |
| Updated mock counts (74 → 128)                                                                         | Verified via `grep -cE` per file                                                                        | architecture HIGH-1 |
| Added worktree-isolation prompt skeleton                                                               | Plan needs to enumerate Rule 1+5+6 in text                                                              | architecture HIGH-2 |
| Shard 3 strictly sequenced after merges                                                                | AST scan has no file-level exemption                                                                    | testing HIGH-3      |
| `pool_size=2, max_overflow=2` dropped from Shard 2                                                     | SUT pattern uses `ConnectionManagerAdapter(MockDataFlowForTesting)` directly, not a `DataFlow` instance | DF-4 HIGH           |
| `dataflow_migration_locks` (not `kml_migration_locks`) cited as the lock table                         | Verified in `concurrent_access_manager.py:183-298`                                                      | DF-2 HIGH           |
