# Architecture Plan — #992 B-1.5 Tier-2 Mock Rewrite

Workspace: `issue-979-b15-tier2-mock-rewrite`.
Brief: `briefs/00-brief.md` (verbatim from `gh issue view 992`).
Classification audit: `01-analysis/01-research/01-per-file-classification.md`.
Harness reference: `01-analysis/01-research/02-harness-contract.md`.

## Value-anchor (verbatim)

> `specs/testing-tiers.md` § Tier-2 Contract Rule 1:
> "Per `rules/testing.md` § 'No Mocking in Tier 2/3', integration tests MUST
> exercise real infrastructure: Real PostgreSQL via `IntegrationTestSuite`;
> Real Redis / Mongo / MySQL when subject under test requires them; Real
> `AsyncLocalRuntime` / `LocalRuntime`; Real network calls (mockable at the
> response layer only via VCR-style cassettes)."

The 9 files in scope currently violate this contract — 74 mock sites across
`tests/integration/` after S4's mechanical `git mv` left mock-based tests
in a directory whose contract is "no mocking."

## Forest-vs-trees rank (per `rules/value-prioritization.md` MUST-1)

1. **Tier-2 contract restoration (HIGH)** — Anchor: spec verbatim above.
   Without this rewrite, every tier-2 enforcement gate added later (a CodeQL
   rule, a CI assertion, or a `/redteam` mechanical sweep per `rules/testing.md`
   § Audit Mode) flips red on the 9 files. Today the cost is silent; the moment
   we add the gate, the cost is "release-blocking PR until mocks are gone."

2. **Facade-manager Tier-2 coverage restoration (HIGH, structurally tied to 1)**
   — Anchor: `rules/facade-manager-detection.md` Rule 1 (manager-shape classes
   exposed via facade MUST have Tier-2 wiring tests). `MigrationLockManager`
   currently has only mocked tests — by downgrading File 6 wholesale we'd
   REMOVE its sole Tier-2 marker without replacing the coverage. The split
   approach (Cluster B below) keeps the wiring intent and rewrites it to real
   PG, fulfilling both contracts in one shard.

3. **Test-suite collection hygiene (MED)** — Anchor: `tests/integration/conftest.py:120-145`
   has a collection-time AST scan that fails on any leftover `unittest.mock`
   import. Today the scan is silent because the mocks live IN integration tests
   and the scan ignores them. Once we move-or-rewrite, the cleanup must be total
   or collection itself breaks — surfaces the cost of any half-finished migration.

Tiebreaker: Item 1 and Item 2 collapse to one workstream via the split-shards
plan; Item 3 is the verification gate. All three deliver in this workspace.

## Shard plan

Three implementation shards + one verification gate. All three implementation
shards are independent (touch disjoint files); eligible for parallel worktree
launch per `rules/worktree-isolation.md` Rule 4 (waves of ≤3 — exactly 3).

|   # | Shard                                          | Files touched                 |       LOC delta | Invariants | Parallel?        |
| --: | ---------------------------------------------- | ----------------------------- | --------------: | ---------: | ---------------- |
|   1 | Cluster A — 7 Tier-1 moves                     | 7 (Files 1, 2, 3, 5, 7, 8, 9) |            ~-80 |          6 | yes              |
|   2 | Cluster B — File 6 split (Tier-1 + new Tier-2) | 1 → 2                         | +120 / preserve |          5 | yes              |
|   3 | Cluster C — File 4 split (Tier-1 + new Tier-2) | 1 → 2                         |        +80 / -3 |          4 | yes              |
|   4 | Verification gate                              | post-merge sweep              |               0 |          3 | no (after 1+2+3) |

Each shard fits the per-session capacity budget per `rules/autonomous-execution.md`
§ MUST Rule 1 (≤500 LOC load-bearing, ≤5–10 invariants, ≤3–4 call-graph hops).

### Shard 1 — Cluster A: 7 Tier-1 moves (mechanical)

**Value-anchor (per `rules/value-prioritization.md` MUST-2):** restores the tier-1
contract from `specs/testing-tiers.md` § Tier-1 — these 7 files self-declare
Tier-1 intent (`pytestmark = pytest.mark.unit`, filenames ending `_unit.py`,
docstrings explicit) but were mechanically moved to `tests/integration/` by S4
without re-classification. The move is a no-op-semantic operation that closes
the misclassification.

**Scope:**

For each of Files 1, 2, 3, 5, 7, 8, 9:

1. `git mv` to `tests/unit/<appropriate-subdir>/`.
2. Drop `@pytest.mark.integration` class decorators (where present).
3. Drop dead `test_suite` / `runtime` fixtures (Files 1, 3).
4. Drop unused `from tests.infrastructure.test_harness import IntegrationTestSuite`
   imports (Files 1, 3).
5. File 9: rename to `test_tdd_mode_init_wiring.py` AND update internal docstring.

**Invariants** (≤6):

1. Per-file pytest collection count identical pre/post (`pytest --collect-only -q`).
2. `tests/integration/conftest.py:120-145` AST scan reports zero mock imports
   in the 7 moved files (they're no longer in `tests/integration/`).
3. `pytestmark = pytest.mark.unit` preserved or added on each file.
4. No `@pytest.mark.integration` class decorator survives in the 7 moved files.
5. `tests/unit/` collects cleanly in `pip install -e packages/kailash-dataflow[dev]` venv.
6. File 9 rename: every internal docstring + module-level comment references
   the new name; `git log --follow` traces the rename.

**Out of scope for Shard 1:**

- Any behavioral test edit (mocks stay where they are; only directory moves).
- Touching Files 4 or 6 (those go to Shards 2 + 3).

### Shard 2 — Cluster B: File 6 split (Tier-1 param-conversion + new Tier-2 wiring)

**Value-anchor:** restores `facade-manager-detection.md` Rule 1 compliance for
`MigrationLockManager` (a `*Manager`-shape class exposed via `DataFlow`).
Today `MigrationLockManager.acquire_migration_lock` / `release_migration_lock`
/ `check_lock_status` / `migration_lock` ctx mgr are tested ONLY via mocks —
the orphan-detection failure mode `facade-manager-detection.md` Rule 1 was
written to prevent.

**Scope:**

1. **Create `tests/unit/migrations/test_connection_adapter_param_conversion.py`**
   — extract `TestConnectionManagerAdapter` (lines 24-227 of File 6) +
   `TestParameterConversionEdgeCases` (lines 392-466). Pure `%s` → `$1`
   string-algorithm tests. Preserve every existing test verbatim.
2. **Create `tests/integration/migrations/test_migration_lock_manager_wiring.py`**
   — rewrite `TestMigrationLockManagerIntegration` (lines 230-389) against
   real PG via `IntegrationTestSuite`:
   - Use shared `test_suite` fixture from `tests/integration/conftest.py:304-318`.
   - Real `DataFlow(test_suite.config.url, pool_size=2, max_overflow=2)` per
     harness contract.
   - Cover the 4 originally-mocked scenarios with real-PG equivalents:
     - acquire → release → re-acquire (lock cycle).
     - acquire → second-acquire-blocks (UNIQUE violation surfaces as real
       PG error from `kml_migration_locks` table).
     - acquire → check_status returns row with correct columns.
     - `async with migration_lock(name):` ctx mgr acquires + releases.
3. **Delete `tests/integration/migrations/test_migration_lock_manager_integration.py`**
   (the original File 6, now fully covered by the two new files).
4. Per `rules/testing.md` § MUST: Behavioral Regression Tests — every test
   asserts observable behavior, not source-grep.

**Invariants** (≤5):

1. Param-conversion test count in new Tier-1 file equals original count in
   File 6's two extracted classes.
2. New Tier-2 file: `pytest tests/integration/migrations/test_migration_lock_manager_wiring.py`
   passes against real PG (locally + in CI).
3. New Tier-2 file: `grep -E '@patch|MagicMock|AsyncMock|unittest\.mock'`
   reports ZERO matches.
4. `MigrationLockManager.acquire_migration_lock` covered by ≥1 direct-call
   real-PG test (closes orphan-detection gap).
5. `tests/integration/conftest.py:120-145` AST collection scan passes on
   the new Tier-2 file.

**Risk**: Real-PG concurrent acquire test requires careful event-loop
isolation (two `async with migration_lock` blocks must not deadlock). Use
the canonical pattern from existing PG-concurrent tests; harness reference
doc § "Idiomatic usage" cites two well-used examples.

### Shard 3 — Cluster C: File 4 split (Tier-1 helper-existence + new Tier-2 PG regression)

**Value-anchor:** closes File 4's self-documented PG coverage gap. The file
already says (lines 30, 154, 218, 449, 622-624) that the helper's purpose is
"work inside event loop on PostgreSQL where SQLite's threading limit doesn't
apply" — yet has zero PG tests. The regression scenarios `test_original_bug_scenario`
and `test_simulated_fastapi_lifespan` document the bug class but never validate
against the platform where it actually manifests.

**Scope:**

1. **Create `tests/unit/migrations/test_async_safe_run.py`** — extract helper-
   existence tests (lines 50-72), sync-context execution (100-145),
   `test_async_safe_run_in_*` (321-365), `test_dataflow_creation_*` (562-606).
   Preserve `sqlite:///:memory:` usage — it's the helper's intentional Tier-1
   surface.
2. **Create `tests/integration/migrations/test_async_safe_run_postgres.py`**
   — rewrite `test_original_bug_scenario` (lines 612-660) +
   `test_simulated_fastapi_lifespan` (lines 662-684) against real PG via
   `IntegrationTestSuite`. The bug was an asyncio thread-pool issue that
   only manifests in production-shape async stacks (FastAPI lifespan, real
   event loop, real PG connection pool).
3. **Delete `tests/integration/migrations/test_async_safe_run_integration.py`**
   (the original File 4, now fully covered by the two new files).

**Invariants** (≤4):

1. New Tier-1 file: helper-existence + sync-context tests preserved verbatim;
   SQLite-intentional-fail assertions preserved.
2. New Tier-2 file: `test_original_bug_scenario` + `test_simulated_fastapi_lifespan`
   pass against real PG, prove the fix at the platform where the bug was
   originally reported.
3. New Tier-2 file: `grep` reports ZERO `unittest.mock` imports.
4. AST collection scan passes on the new Tier-2 file.

### Shard 4 — Post-merge verification gate

**Scope:**

1. Run `grep -rcE '@patch|MagicMock|AsyncMock|unittest\.mock'
packages/kailash-dataflow/tests/integration/{cache,core,migration,migrations,package,performance}/`
   — MUST report zero across all 9 originally-listed files.
2. Run `pytest packages/kailash-dataflow/tests/integration --collect-only -q`
   — MUST succeed (AST scan passes).
3. Run `pytest packages/kailash-dataflow/tests/integration -m integration`
   against real PG locally — MUST report all new Tier-2 tests passing.
4. Update `workspaces/issue-979-b15-tier2-mock-rewrite/journal/`
   with a `DECISION-shard-classifications.md` entry per AC bullet 2.
5. `gh issue close 992` with PR SHAs cited per `rules/git.md` § Issue closure.

**Invariants** (3):

1. Zero mock imports across the 9 original integration paths.
2. All new Tier-2 tests pass against real PG.
3. Journal entry exists and documents per-file classification.

## Parallel-launch strategy (per `rules/worktree-isolation.md` Rule 4)

Shards 1, 2, 3 launch as a single worktree wave of 3:

| Shard | Worktree                                                  | Branch                                       |
| ----- | --------------------------------------------------------- | -------------------------------------------- |
| 1     | `.claude/worktrees/issue-992-shard1-tier1-moves`          | `feat/issue-992-shard1-tier1-moves`          |
| 2     | `.claude/worktrees/issue-992-shard2-lock-manager-split`   | `feat/issue-992-shard2-lock-manager-split`   |
| 3     | `.claude/worktrees/issue-992-shard3-async-safe-run-split` | `feat/issue-992-shard3-async-safe-run-split` |

Pre-flight (per `rules/worktree-isolation.md` Rule 5):

- Pin base SHA to current `main` HEAD at launch.
- Verify `git merge-base <branch> main` equals current main HEAD.
- Each agent receives absolute worktree path AND verifies cwd at start (Rule 1+2).
- Each agent commits incrementally per Rule 6 (commit after each file move /
  each new test class).

Shard 4 (verification gate) runs sequentially after all three PRs merge to
main.

## Open questions for human gate (per `/todos` workflow)

None at architecture-plan time — all six open questions surfaced by the
classification audit were resolved structurally (see classification audit
§ "Open questions resolved by Cluster B + C"). The shard plan is internally
consistent.

## Out of scope (boundary clarifications)

- The other 5 Workstream-B issues of #979 (#995, #996, #997, #998, #999) —
  separate workstreams.
- Cross-SDK kailash-rs sibling mock-rewrite work — separate kailash-rs
  session per `rules/repo-scope-discipline.md`.
- Adding any NEW test beyond the Tier-2 carve-outs in Shards 2 + 3 (those
  carve-outs deliver rewrites of EXISTING tests, not new test scope).
- Modifying production code in `packages/kailash-dataflow/src/`. If a real-PG
  Tier-2 rewrite surfaces a production bug, that's a new issue.
- Refactoring `tests/regression/` (separate concern).
