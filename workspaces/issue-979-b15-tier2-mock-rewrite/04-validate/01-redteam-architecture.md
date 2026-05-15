# Red Team Round 1 — Architecture Plan for #992

## Verdict

APPROVE-WITH-FIXES

The plan is structurally sound — three independent shards close the spec
violation, the cluster decomposition matches the classification audit, the
shard budget is respected, and the Cluster B split correctly transmutes a
deletion into a `facade-manager-detection.md` Rule 1 win. However, six gaps
must be closed in the plan before `/todos`:

1. The cache test file's mock has already been removed on `main` (the
   classification audit is stale by one file/site).
2. Concrete worktree-isolation prompt-skeleton mandates (Rules 1, 5, 6) are
   alluded to but not enumerated.
3. Shard 4 (verification) is described but its journal-entry deliverable is
   not given a path on disk.
4. The Cluster B concurrent-acquire test pattern is named ("real concurrent
   acquire") without specifying the two-event-loops vs two-asyncpg-connections
   strategy.
5. File 4's Tier-2 PG regression for `_execute_workflow_safe` lacks a
   minimum-viable harness specification (FastAPI ASGI vs `asyncio.get_running_loop()`
   sentinel).
6. Test-count preservation invariant (Shard 1 Invariant 1) doesn't gate
   against the case where a dropped `test_suite` fixture silently un-registers
   class-scoped tests.

None of the six are CRITICAL. All six are HIGH (must fix before `/todos`).

## Critical findings (must fix before /todos)

None.

## High findings (should fix)

- **[HIGH-1] Cache file classification is one-mock-site stale.**
  Brief says `cache/test_cache_invalidation.py` has 1 mock site. Live `grep`
  (`Mock\(\)|AsyncMock\(\)|MagicMock\(\)` in
  `packages/kailash-dataflow/tests/integration/cache/test_cache_invalidation.py`)
  reports **27 occurrences** of `Mock()` and a `from unittest.mock import
AsyncMock, Mock, patch` at line 21. The classification audit's "~30 `Mock()`"
  number in `01-per-file-classification.md` is correct; the brief number 1 is
  wrong. The plan inherits the audit number (correct), so the shard plan is
  unaffected, but Shard 4's verification grep (`grep -rcE`) WILL surface 27
  matches in this file if it runs against `tests/integration/cache/` BEFORE
  Shard 1 has moved the file out. **Fix**: state explicitly in Shard 4 that
  the grep MUST run AFTER all 3 shards merge AND that the grep target is
  the `tests/integration/{cache,core,migration,migrations,package,performance}/`
  tree on `main` post-merge — NOT on a feature branch with partial state.

- **[HIGH-2] Worktree-isolation Rule 1, 5, 6 prompt-skeletons absent.**
  Plan § "Parallel-launch strategy" cites `rules/worktree-isolation.md` Rule 4
  (waves of ≤3) and Rule 5 (merge-base check) but provides ZERO concrete
  prompt skeleton showing:
  - Rule 1 — absolute worktree path pinned in prompt with `git -C <path>
status` verification at agent start.
  - Rule 5 — pre-flight `target_head=$(git rev-parse main)` + `merge_base ==
target_head` assertion BEFORE `git worktree add -b ... "$target_head"`.
  - Rule 6 — `-b <declared-branch>` explicit on `git worktree add`, agent
    prompt verifies `git rev-parse --abbrev-ref HEAD == <declared-branch>`.
  - § "Commit incremental progress per Rule 6" — actually that's
    worktree-isolation Rule 6 about branch names, NOT Rule 6 about incremental
    commits. The plan conflates two Rule-6 clauses.
  - `rules/agents.md` § "Worktree Agents Commit Incremental Progress" — the
    explicit instruction to `git commit` after each milestone must be in EACH
    of Shard 1's, Shard 2's, Shard 3's prompts. The plan says "commits
    incrementally per Rule 6" but does not actually mandate the per-shard
    inclusion of that line in the prompt text the orchestrator emits.
    **Fix**: insert a worked example prompt skeleton at the bottom of the plan
    showing one of the three shards' full prompt content, including all 4
    guardrails (path-pin + cwd-verify + branch-name verify + commit-discipline
    instruction).

- **[HIGH-3] Shard 4 journal entry lacks a path on disk.**
  Plan Shard 4 step 4 says "Update `workspaces/issue-979-b15-tier2-mock-rewrite/journal/`
  with a `DECISION-shard-classifications.md` entry per AC bullet 2." The
  brief AC #2 says "Per-file decisions documented in a journal `DECISION-`
  entry." The plan mandates ONE journal entry covering all 9 files. The
  classification audit already documents per-file decisions — the journal
  entry is one synthesis pointing to that audit. Per `rules/git.md` §
  "Issue closure", `gh issue close 992` must cite PR SHAs. The plan does
  cite that, but the journal entry's EXACT path is unspecified — the workspace
  is fresh and has NO `journal/` directory today (verify:
  `ls workspaces/issue-979-b15-tier2-mock-rewrite/journal/` — empty/absent).
  **Fix**: specify the journal entry filename, e.g.
  `journal/0001-DECISION-tier2-mock-rewrite-per-file-classifications.md`, and
  what content it MUST contain (the table from `01-per-file-classification.md`
  - the 3 PR links + the cluster→shard mapping).

- **[HIGH-4] Cluster B concurrent-acquire test pattern under-specified.**
  Shard 2 Invariant 4 says "`MigrationLockManager.acquire_migration_lock`
  covered by ≥1 direct-call real-PG test". The plan's Risk note says
  "two `async with migration_lock` blocks must not deadlock". This is
  ambiguous: PostgreSQL row-level locks on `_kml_migration_locks` (UNIQUE
  on `schema_name`) require two SEPARATE connections — same-connection-two-awaits
  serializes and never tests concurrency. The harness contract at
  `02-harness-contract.md` § 4.4 explicitly cites `pool_size=2, max_overflow=2`
  as canonical for multi-DataFlow-instance tests, but the LOCK test needs
  TWO `DataFlow` instances (each with its own pool) OR one DataFlow with TWO
  explicit `asyncpg.Connection` objects (acquired via
  `test_suite.get_connection()` twice). **Fix**: specify the pattern. Recommend:
  - Two DataFlow instances sharing `test_suite.config.url`, each
    `pool_size=2, max_overflow=2`.
  - Lock manager A acquires; assert success.
  - Lock manager B (separate DataFlow, separate connection pool) tries to
    acquire same `schema_name`; assert returns False within a bounded timeout
    (≤2s, NOT the default 30s `lock_timeout`).
  - Lock manager A releases; lock manager B retries; assert success.
  - Both instances closed via `try/finally: await db.close_async()` per
    harness contract § 4.6.
  - `@pytest.mark.timeout(15)` to bound any deadlock failure.

- **[HIGH-5] File 4 Tier-2 PG regression: minimum viable harness unspecified.**
  Plan Shard 3 Invariant 2 says new Tier-2 file proves the fix "at the
  platform where the bug was originally reported (FastAPI lifespan, real
  event loop, real PG connection pool)". The original file 4 contains
  `test_simulated_fastapi_lifespan` (lines 662-684), which uses
  `sqlite:///:memory:` and `db.initialize()` inside an already-running
  asyncio loop (via `pytest-asyncio`). The plan should clarify that
  reproducing the FastAPI-lifespan failure mode in pytest does NOT require
  a real ASGI server — `pytest-asyncio` already provides the running event
  loop (this is the same loop FastAPI's lifespan provides). The minimum
  viable harness is:
  - `@pytest.mark.asyncio` + `pytest.mark.integration` markers.
  - Acquire the running loop via `asyncio.get_running_loop()` and assert
    `loop.is_running()` BEFORE the SUT call (preserves the original test's
    intent).
  - Use `test_suite.config.url` (real PG, port 5434) for the DataFlow URL.
  - Verify the workflow execution completes without
    `"Task got Future attached to a different loop"` — same assertion
    keyword as the SQLite version.
  - Verify the read-back of the seeded row (per `rules/testing.md` §
    "State Persistence Verification").
    **Fix**: include this 5-bullet minimum-harness spec in Shard 3's Scope §,
    not just "rewrite … against real PG".

- **[HIGH-6] Test-count-preservation invariant has a hole for class-scoped
  decorator drops.**
  Shard 1 Invariant 1 ("per-file pytest collection count identical pre/post")
  uses `pytest --collect-only -q`. This catches function-level test drops
  but NOT the case where a class-level `@pytest.mark.integration` decorator
  drop changes the test's collected-tier (e.g., dropping `@pytest.mark.integration`
  means the test no longer matches the integration-tier filter and instead
  appears in the unit-tier collection — net same COUNT but different LOCATION).
  The plan also drops dead `test_suite` fixtures (Files 1, 3) — if any test
  in those classes consumed the fixture and is now class-scoped without it,
  pytest collection error. **Fix**: Invariant 1 is sufficient AS A COLLECTION
  GATE. Add Invariant 1b: `pytest tests/unit/ -m unit --collect-only -q`
  reports a count ≥ pre-move count + 7-files-worth of tests. The SUM across
  unit AND integration directories MUST equal the pre-move integration
  collection count. This catches the silent-orphan-via-fixture-drop case.

## Medium findings (consider)

- **[MED-1] Out-of-scope item: `tests/integration/test_dataflow_ml_feature_source_wiring.py`
  and `fabric/test_fabric_integrity.py` import from `unittest.mock`.**
  Live grep finds 14 files total under `tests/integration/` with mock-related
  imports. Brief enumerates only 9 (the 9 from PR #988's `git mv`). The other
  3 sites:
  - `test_dataflow_ml_feature_source_wiring.py` — references "MagicMock" in
    a docstring/comment only (no actual mock use; false positive).
  - `fabric/test_fabric_integrity.py` — imports `unittest.mock.ANY` only
    (whitelisted by `tests/integration/conftest.py:57-65` per harness audit
    § 4.1).
  - `tests/integration/conftest.py` and `test_conftest_no_mocking_hook.py` —
    legitimate: the scanner itself, plus its tests.
    So the brief's 9-file scope IS complete. Recommend the plan call this
    out explicitly in § "Out of scope" so a future reader doesn't double-count
    the 14-file grep hit.

- **[MED-2] Cross-SDK sibling sweep not flagged at all.**
  Per `rules/cross-sdk-inspection.md` Rule 1, "When an issue is found or
  fixed in ONE BUILD repo, you MUST inspect the OTHER BUILD repo for the
  same or equivalent issue." The plan correctly excludes kailash-rs work
  per `rules/repo-scope-discipline.md`, but `cross-sdk-inspection.md` Rule 5
  ("Inspection Checklist") still requires the agent closing issue #992 to
  state whether the OTHER SDK has the same issue. This is a CLOSURE-time
  checklist item, not an `/implement` scope item. The plan does not mention
  it. **Fix**: add to Shard 4's scope: "verify the kailash-rs equivalent
  (real-PG mock rewrite for the Rust DataFlow integration tier) by reading
  `gh issue list --repo esperie/kailash-rs --search 'mock integration tier'`
  AND record disposition in the journal entry." Reading is allowed under
  `rules/repo-scope-discipline.md` (no writes, no comments on the other repo);
  only acting on findings would cross the line.

- **[MED-3] File 9 rename: `git log --follow` audit-trail-via-name.**
  File 9 renames `test_real_tdd_integration.py` →
  `test_tdd_mode_init_wiring.py`. Git follows the rename for `--follow`
  by default, so blame/log work. However, journal entries, GH issue
  comments, and PR descriptions referencing the OLD filename will not be
  rewritten. **Fix**: Shard 4 journal entry MUST include a "Renames"
  section mapping old → new filenames so search-by-old-name resolves
  to the new path.

- **[MED-4] Sibling-spec re-derivation per `specs-authority.md` Rule 5b.**
  Shards 2+3 introduce NEW Tier-2 files
  (`test_migration_lock_manager_wiring.py`,
  `test_async_safe_run_postgres.py`). Per `specs-authority.md` Rule 5b,
  "Every spec edit MUST trigger a re-derivation sweep against the FULL
  sibling-spec set". The plan does NOT modify `specs/testing-tiers.md` —
  it ASSERTS the spec contract. Verified live: `specs/testing-tiers.md`
  contains no example list of Tier-2 files; the spec is contract-only,
  not enumeration. So Rule 5b does not bind. Recommend: add a one-line
  note to the plan stating "no spec edits required; Tier-2 contract is
  enumeration-free." That kills a future `/redteam` question.

- **[MED-5] `_INTEGRATION_DIR` path discipline in Cluster B and C.**
  Harness audit § 4.1 says the AST scan triggers when the file is under
  `tests/integration/`. The new files under `tests/integration/migrations/`
  ARE under the scanned tree. The new file under `tests/unit/migrations/`
  is OUTSIDE the scanned tree. Verified live: `conftest.py:136` checks
  `_INTEGRATION_DIR not in resolved.parents`. **The plan's Cluster B+C
  Invariant claims (e.g., Shard 2 Invariant 5, "AST collection scan passes
  on the new Tier-2 file") are CORRECT.** No fix needed — flagged as
  confirmed.

## Low findings (nice-to-have)

- **[LOW-1] LOC estimate vs plan delta — slight under-scoping.**
  Issue body says "~3 sessions of work (~900 LOC)." Plan delta totals:
  - Shard 1: ~-80 LOC (deletes only) + 7 file moves
  - Shard 2: +120 LOC new + ~-160 LOC deleted (full file 6 = 466 lines per
    audit, minus the param-conversion preserved ~205 lines = ~260 LOC removed)
  - Shard 3: +80 LOC new + ~-680 LOC deleted (file 4 currently ~700 lines,
    minus helper-existence preserved ~150 = ~550 LOC removed)
  - Total net: +200 LOC new, ~-890 LOC deleted = NET -690 LOC delta.
    Issue body's "~900 LOC" was an OVERSTATEMENT of new work, not an UNDERESTIMATE.
    Plan's actual new-write surface is ~200 LOC, well within one parallel wave.

- **[LOW-2] Plan does not mention `pip check` post-merge.**
  Per `rules/dependencies.md` § "Verification step", `/redteam` and `/deploy`
  MUST run `pip check`. Shard 4 doesn't mention it. The shards delete tests
  but don't change `pyproject.toml` deps, so `pip check` should pass —
  but the gate should be invoked. **Fix**: add to Shard 4 step list:
  `.venv/bin/python -m pip check` → exit 0 required.

- **[LOW-3] Read-back assertion per `rules/testing.md`.**
  The new Cluster B real-PG test acquires a lock, but `rules/testing.md`
  § "State Persistence Verification" requires "every write MUST be verified
  with a read-back." The lock acquire IS a write to `_kml_migration_locks`;
  the read-back is `check_lock_status()`. Plan covers this via Shard 2
  scenario "acquire → check_status returns row with correct columns" —
  confirmed compliant. No fix needed.

- **[LOW-4] Mechanical reviewer sweep per `rules/agents.md` § "Reviewer
  Prompts Include Mechanical AST/Grep Sweep".**
  The plan's Shard 4 verification gate IS already a mechanical sweep. The
  plan does NOT explicitly delegate to `reviewer` + `security-reviewer` per
  the `/implement` MUST gate. Recommend stating at the top of the shard
  plan: "After each shard PR is reviewed, reviewer and security-reviewer
  run as parallel background agents per `rules/agents.md` § 'Quality Gates'."

## Verification command outputs

```bash
# Cache file mock-import check (HIGH-1 evidence)
$ grep -c 'Mock()\|AsyncMock()\|MagicMock()' \
  packages/kailash-dataflow/tests/integration/cache/test_cache_invalidation.py
27

$ grep -n '^from unittest\|^import.*mock' \
  packages/kailash-dataflow/tests/integration/cache/test_cache_invalidation.py
21:from unittest.mock import AsyncMock, Mock, patch

# Total mock-using files under tests/integration/ (MED-1 evidence)
$ grep -l 'from unittest\|@patch\|MagicMock\|AsyncMock\|Mock()' \
  packages/kailash-dataflow/tests/integration/**/*.py
# 14 files (9 brief-scope + 3 legitimate + 2 non-scope-but-clean = OK)

# fabric/test_fabric_integrity.py — only imports ANY (whitelisted)
$ grep -n 'from unittest' \
  packages/kailash-dataflow/tests/integration/fabric/test_fabric_integrity.py
22:from unittest.mock import ANY

# AST scanner location (corroborates harness audit § 4.1)
$ grep -n 'pytest_collectstart\|_module_imports_unittest_mock' \
  packages/kailash-dataflow/tests/integration/conftest.py
120:def pytest_collectstart(collector):
138:    if _module_imports_unittest_mock(resolved):

# Shared test_suite fixture confirmed at expected line range
$ grep -n '^async def test_suite' \
  packages/kailash-dataflow/tests/integration/conftest.py
303:async def test_suite():
# (off-by-one from plan's "304-318" — the function header is line 303;
#  body is 304-318. Plan's citation is non-blocking but minor.)

# File 6 TestMigrationLockManagerIntegration class exists at expected range
$ grep -n '^class TestMigrationLockManagerIntegration' \
  packages/kailash-dataflow/tests/integration/migrations/test_migration_lock_manager_integration.py
230:class TestMigrationLockManagerIntegration:

# File 4 test_original_bug_scenario + test_simulated_fastapi_lifespan
$ grep -n 'test_original_bug_scenario\|test_simulated_fastapi_lifespan' \
  packages/kailash-dataflow/tests/integration/migrations/test_async_safe_run_integration.py
612:    async def test_original_bug_scenario(self):
662:    async def test_simulated_fastapi_lifespan(self):

# Workspace journal/ directory existence (HIGH-3 evidence)
$ ls workspaces/issue-979-b15-tier2-mock-rewrite/journal/
# (absent — must be created by Shard 4)
```

## Summary disposition

- **Strengths**: shard count (3 + 1 verification) matches AC bullet 4
  ("~3 sessions, shard by file or directory group"); cluster split correctly
  identifies File 6 + File 4 as `(c) Split` candidates rather than blanket
  deletions; Cluster B closes `facade-manager-detection.md` Rule 1 by
  rewriting the MOCKED wiring test to REAL-PG wiring instead of deleting it;
  shard budget compliance (≤500 LOC, ≤6 invariants each) verified by hand.
- **Six HIGH fixes**: enumerate worktree prompt skeletons (1, 5, 6, commit
  discipline) inline; specify journal entry path + content; specify Cluster
  B concurrent-acquire pattern (two DataFlow instances); specify Cluster C
  FastAPI-lifespan minimum harness; add Invariant 1b for cross-tier collection
  count preservation; update Shard 4 grep target = post-merge `main`.
- **Five MED**: 14-file false-positive note in Out-of-scope; cross-SDK
  inspection checklist for Shard 4; rename audit trail in journal entry;
  one-line spec-untouched note; reviewer + security-reviewer delegation
  note.
- **Four LOW**: LOC scoping is generous; add `pip check`; read-back
  confirmed compliant; mechanical-reviewer-sweep note.

After these fixes, the plan converges. Cluster B's `MigrationLockManager`
real-PG concurrent-acquire test is the highest-risk single shard. Cluster C
is straightforward (existing tests cite the bug scenario in-file).

Recommend orchestrator amend the plan inline (per `specs-authority.md`
Rule 5c amend-at-launch discipline) before opening `/todos`.
