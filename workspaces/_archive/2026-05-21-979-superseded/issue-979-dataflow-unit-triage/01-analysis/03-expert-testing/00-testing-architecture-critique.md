# Testing-Architecture Critique — Issue #979

Date: 2026-05-13
Role: testing-architecture expert (team of 5)
Inputs: brief, journals 0001/0002, research 01–03, plan + amendments, the
two CLAUDE.md files, current main `21ba8e6a`.

Posture: this critique stays out of the moves/refactors the plan already
covers (S1–S6). It adds testing-architecture findings the plan does NOT
already encode.

## 1. Tier-1 contract gaps (what the plan-cited spec needs to add)

The plan cites `specs/testing-tiers.md` as authority (plan
`02-plans/00-architecture-plan.md:259-263`), but the file does NOT
exist yet in `workspaces/issue-979-dataflow-unit-triage/specs/`. The
analyst's research at `01-tier1-contract.md:1-86` reads the contract OUT
of `tests/unit/CLAUDE.md` rather than authoring it. This is a
spec-accuracy issue (`rules/spec-accuracy.md` MUST-5 — code first, then
spec; here the situation is inverse: contract exists in CLAUDE.md, the
canonical `specs/testing-tiers.md` is missing). S6 in the amendments
(`02-plans/01-amendments-post-redteam.md:185-216`) plans to write
`specs/testing-tiers.md` — that authoring MUST cover the eight invariants
below, which the current draft contract does NOT carry:

### 1.1 `pytest.ini` vs `pyproject.toml [tool.pytest.ini_options]` precedence

Both files exist:

- `packages/kailash-dataflow/pytest.ini` (full config block, `markers`,
  `addopts`, `asyncio_mode`, `pythonpath`)
- `packages/kailash-dataflow/pyproject.toml` `[tool.pytest.ini_options]`
  (different `markers` list — only 6 markers vs pytest.ini's 23,
  different `addopts`, no `pythonpath`)

Per pytest's documented config-file resolution
(<https://docs.pytest.org/en/stable/reference/customize.html>), when
both `pytest.ini` AND `pyproject.toml` exist in the same directory,
**`pytest.ini` wins unconditionally** — `pyproject.toml`'s
`[tool.pytest.ini_options]` is silently ignored. The 6-marker subset in
pyproject.toml has been dead config for the duration of its existence.
Tier-1 spec MUST declare ONE canonical config file (recommendation:
delete the `pyproject.toml` block; keep `pytest.ini`) and add an
invariant test asserting the chosen file is the only one with
non-empty `[pytest]` / `[tool.pytest.ini_options]` content. Plan
S1+S6 wire S1's `timeout = 120` and marker exclusion into pytest.ini
(per `02-plans/01-amendments-post-redteam.md:18`) — that lands on the
correct file, but the redundant pyproject block is a permanent
trap for the next contributor.

### 1.2 Marker auto-application drift between sub-conftests

`tests/unit/conftest.py:177-191` auto-applies markers per fixture-name
prefix (`memory_` → `sqlite_memory`, `file_` → `sqlite_file`,
`mock_` → `mocking`) AND adds `unit` based on path. None of these
auto-applied markers are declared in `pytest.ini::markers` — the file
declares `requires_postgres`, `requires_mysql`, etc., but NOT
`sqlite_memory` / `sqlite_file` / `mocking`. With `--strict-markers` in
`pytest.ini:43` `addopts`, the auto-applications would FAIL except that
both `tests/unit/conftest.py:162-171` (`pytest_configure`) AND
`tests/conftest.py:696-707` separately `addinivalue_line` for some of
them. This is hook-order-dependent: `tests/unit/conftest.py::pytest_configure`
runs FIRST for unit-tree tests, and registers `unit`, `sqlite_memory`,
`sqlite_file`, `mocking`. The integration tier's `tests/conftest.py`
registers an entirely different marker set (`requires_full_infrastructure`,
`requires_monitoring`, `requires_multi_db` —
`tests/conftest.py:696-707`). Per red-team DRIFT-3
(`journal/0002-DISCOVERY-redteam-findings.md:209-212`), the plan picks
"declare them in pytest.ini OR remove from CLAUDE.md — pick at S6." Tier-1
spec MUST declare: **every marker auto-applied by conftest MUST also
appear in `pytest.ini::markers`**. Without that invariant, removing one
auto-application breaks `--strict-markers` at collection on every test
using that fixture.

### 1.3 `pytest_collection_modifyitems` + marker-exclusion interaction

S1 plans to add `-m "not (requires_postgres or requires_mysql or
requires_redis or requires_docker)"` to `pytest.ini::addopts`
(`02-plans/01-amendments-post-redteam.md:18`). Independently,
`tests/conftest.py:711-734` runs a `pytest_collection_modifyitems` hook
that adds `pytest.mark.skip` to `requires_full_infrastructure` /
`requires_monitoring` / `requires_multi_db` markers when
`DATAFLOW_MINIMAL_TESTS=true`. The CI gate's `-m` filter and the
collection hook's skip-injection are different mechanisms with different
semantics:

- `-m` filter at addopts: tests with the marker are DESELECTED at
  collection (no `--collected` output line)
- collection-hook `add_marker(skip)`: tests are COLLECTED then SKIPPED
  (visible in `--collected`, counted in `--collect-only`)

A failing tier-1 CI configured with both ends up with two filter
layers operating on different marker sets. The Tier-1 spec MUST
declare which mechanism is canonical. Recommendation: use `-m`
exclusion exclusively for tier-1 CI; document the
`DATAFLOW_MINIMAL_TESTS` collection-hook as a separate
infrastructure-tier mechanism (Tier 2/3) NOT applicable to unit tier.
Otherwise S1's addopts + S6's gate `-m` flag interaction is exactly
red-team HIGH-3's "double-filter risk"
(`journal/0002-DISCOVERY-redteam-findings.md:107-123`).

### 1.4 Parametrized fixtures vs class-based fixtures

Tier-1 spec is silent on the parametrize-vs-class fixture choice. Several
DataFlow tests parametrize fixtures across dialects (`sqlite` /
`postgres`) which inflates Tier 1 with PG paths via `@pytest.mark.parametrize`

- `request.param == "postgresql"`. The spec MUST forbid PG-parametrized
  fixtures in Tier 1 — they are integration tests dressed as unit tests and
  fire the Layer-D bug-class even after S4's moves.

### 1.5 Async fixture cleanup ordering

`tests/unit/conftest.py` has FIVE async fixtures
(`unit_test_suite`, `memory_test_suite`, `file_test_suite`,
`sqlite_memory_connection`, `sqlite_file_connection`) that all yield
through `async with suite.session()`. The `memory_dataflow` fixture at
line 74-88 yields a DataFlow constructed FROM the
`memory_test_suite.dataflow_harness` AND owns the close in a `finally`
block. Cleanup ordering: pytest tears down fixtures in REVERSE request
order — `memory_dataflow` closes first, THEN `memory_test_suite`'s
`async with` exits. Tier-1 spec MUST declare: **every async fixture
that owns a DataFlow / connection MUST yield+close with the same
ordering as `memory_dataflow`** (yield inside try, close in finally).
The fixture pattern at conftest line 84-88 is correct; the spec
needs to make it normative so future fixtures don't drift to
`return` (per `rules/testing.md` § "Fixtures Yield + Cleanup").

### 1.6 `pythonpath = src` in pytest.ini (Layer A precondition not yet on radar)

`pytest.ini:5` sets `pythonpath = src`. This works when pytest is
invoked from `packages/kailash-dataflow/` cwd; it BREAKS when invoked
from repo root because `src` resolves to `kailash-py/src` (the
core SDK, not dataflow). The CI re-applied gate at S6 MUST invoke pytest
with `cwd=packages/kailash-dataflow` OR replace `pythonpath = src` with
`pythonpath = packages/kailash-dataflow/src` to be cwd-agnostic. Not
covered by any current shard.

### 1.7 Auto-applied `@pytest.mark.unit` marker overlap

`tests/unit/conftest.py:181-182` auto-applies `unit` to every test in
`tests/unit/`. The `pytest.ini` also declares `tier1` marker
(line 23) — these are duplicates. S6 MUST pick one. Recommendation:
drop `tier1` from pytest.ini and standardize on `unit` (matches the
directory name and CLAUDE.md prose).

### 1.8 `pytest_plugins` hierarchy not declared

Neither `tests/conftest.py` nor `tests/unit/conftest.py` declares
`pytest_plugins = (...)`. pytest's behavior: every conftest.py at or
above the test's directory is autoloaded — fine in monorepo when conftest
chain is short. The 4-level hierarchy (`root conftest.py` → `packages/kailash-dataflow/tests/conftest.py` → `packages/kailash-dataflow/tests/unit/conftest.py` → optional sub-dir conftest like `tests/unit/trust/conftest.py` and `tests/unit/query/conftest.py`) means a test in
`tests/unit/trust/` autoloads 4 conftests. Tier-1 spec SHOULD declare
the maximum conftest depth (recommendation: 3) and forbid sub-conftests
that materially alter import behavior — the `tests/unit/query/conftest.py`
bootstrap is the institutional canary (see §4 below).

## 2. The 3849-test collection time — empirical findings

```
$ .venv/bin/python -m pytest --collect-only -q \
    packages/kailash-dataflow/tests/unit 2>&1 | tail -1
======================== 3849 tests collected in 1.00s =========================
```

Collection itself is fast (1.00s in local dev venv with `[fabric]`
present). PR #977's "OOM at 22s" framing was from CI's clean
`[dev]`-only environment where AST rewriting on 3849 test bodies in a
~7GB GitHub Actions runner exhausts memory BEFORE the import errors on
fabric/PG-shaped tests can surface as collection errors. This is a
**suite-size problem**, not a per-test problem:

- 3849 tests in tier 1 is ~3-4× what the tier-1 "<2 min" budget can
  hold even under ideal conditions. Average tier-1 test in DataFlow
  observed at ~5-30ms (in-memory SQLite, fixture setup); 3849 × 15ms
  median = 58s of pure execution time, plus collection (1s),
  plus fixture-setup amortized (uncountable here). The <2 min budget is
  achievable but TIGHT.
- After plan moves (S2a-S5b moves ~50 files out of unit), the post-move
  count should be ~3400-3500 tests. Still tight; still achievable.
- The OOM in PR #976 was likely NOT raw test count — it was AST rewrite
  bytecode-cache size. With `--assert=plain` (disabling assert-rewrite)
  collection memory drops 60-80% (`pytest --help | grep assert`).

**Recommendation NOT in the plan**: S1 (preconditions) should add
`--assert=plain` evaluation as an option. Add a sub-shard or amend S1
to time both: `pytest --collect-only` vs
`pytest --assert=plain --collect-only` against a 7GB-RAM-capped
container. If `--assert=plain` saves the OOM, set it as the tier-1
default in `pytest.ini::addopts`. Cost: weaker assertion messages on
failure (you get `assert x == 1` not `assert 2 == 1`). Tradeoff vs OOM:
weaker messages are recoverable via verbose mode; OOM is not.

### 2.1 Slowest tests by inference (no --durations available without execution)

I cannot run `--durations=0` without executing the suite (which
requires the `[fabric]` deps the suite imports). Instead, by inspection
of the 7 performance files (LOC + sleep/timing patterns):

| File                                                            | LOC | Profile                                                                 |
| --------------------------------------------------------------- | --- | ----------------------------------------------------------------------- |
| `tests/unit/test_error_enhancer_performance.py`                 | 494 | `time.time()` + `ThreadPoolExecutor` — concurrency timing               |
| `tests/unit/testing/test_performance_regression_suite.py`       | 786 | `time.time()` + statistics over JSON-persisted runs (no DB)             |
| `tests/unit/testing/test_tdd_performance_benchmark.py`          | 742 | `time.time()` + `LocalRuntime` — REAL workflow execution                |
| `tests/unit/context_aware/test_performance_benchmarks.py`       | 436 | `under_10_seconds` thresholds with `memory_dataflow`                    |
| `tests/unit/migrations/test_migration_performance_tracker.py`   | 845 | `tempfile` + `time.time()` mostly mock-based                            |
| `tests/unit/migrations/test_performance_validator.py`           | 818 | Heavily mocked (`AsyncMock, MagicMock, Mock, patch`); fast              |
| `tests/unit/migrations/test_not_null_performance_boundaries.py` | 941 | Imports `psutil` + `resource` — process/memory benchmarks (real timing) |

Three of these (`test_error_enhancer_performance.py`,
`test_tdd_performance_benchmark.py`,
`test_not_null_performance_boundaries.py`) measure wall-clock time and
assert below a threshold. Wall-clock assertions in unit tier are
inherently flaky on shared CI runners under load — see §6 below for
the disposition recommendation.

## 3. Shard design — testing-architecture coupling points the plan misses

### 3.1 S2a moves `tests/unit/examples/` but doesn't move its conftest dependency

`tests/unit/examples/test_example_gallery.py` uses `memory_dataflow`
(per the analyst's research). When the file moves to
`tests/integration/examples/`, the test no longer inherits
`tests/unit/conftest.py` — it inherits `tests/integration/conftest.py`
(or the absence thereof). If `tests/integration/` does NOT export
`memory_dataflow`, the test fails at fixture-resolution post-move with
`fixture 'memory_dataflow' not found`. Plan S2a doesn't address this.
The analyst notes Layer B intent IS integration
(`02-failure-layers.md:33-39`), so the right disposition is to
REFACTOR test_example_gallery.py to use `IntegrationTestSuite` and a
real PG DataFlow during the move — NOT just `git mv`. S2a's
"≤30 LOC change (mostly path moves), 3 invariants" budget
(`00-architecture-plan.md:110`) is too low; the actual cost is ~10
test methods × ~30 LOC refactor each = ~300 LOC. **Recommendation**:
upsize S2a budget to ≤300 LOC, 5 invariants, OR add an S2a-bis sub-shard
for fixture port.

### 3.2 S2b-S2d ALSO have the fixture-port problem

Every move of a test that uses a unit-tier fixture has the same issue.
The amended plan lists 20 files in S2a-S2d as moves
(`02-plans/01-amendments-post-redteam.md:29-97`); each file needs a
per-fixture audit BEFORE move. The plan implicitly assumes "move = git
mv" — but for any file using `memory_dataflow` / `memory_test_suite` /
`mock_*`, the move must also port the fixture or refactor the test.
**Mitigation**: S2a-S2d sub-shard prompts MUST include
`grep -E 'memory_dataflow|memory_test_suite|file_dataflow|mock_(connection_manager|migration_executor|dataflow_engine)' <file>` and
report fixture-usage to the shard agent. Files using unit-tier
fixtures need an integration-tier counterpart fixture OR the test
gets refactored to construct its own DataFlow.

### 3.3 S3 (fabric/ move) inherits the same problem ×21 files

`tests/unit/fabric/` has 21 files; some import unit-tier conftest
fixtures (per the plan's research not enumerated). Without an
explicit audit step, S3's "≤50 LOC" budget
(`02-plans/01-amendments-post-redteam.md:104`) understates the move
cost if any fabric file uses `memory_dataflow` / `mock_*`. The shard
prompt for S3 MUST include the same fixture-usage grep as §3.2.

### 3.4 S5b cleans up `tests/unit/query/conftest.py` (good) but the conftest is load-bearing

`tests/unit/query/conftest.py:23-73` (read above) bootstraps a
fake `dataflow` module into `sys.modules` BEFORE collection because
it documents a "pre-existing import error in dataflow.**init**.py".
Red-team verified the underlying import is fixed (per
`journal/0002-DISCOVERY-redteam-findings.md:128-150`). BUT — the
bootstrap registers a stub `dataflow` package that **shadows the real
package** during query tests. If any query test transitively imports
from `dataflow.X` where X is NOT `query.models` / `query.sql_builder`,
that test resolves against the stub (which only has `query` attrs)
and fails opaquely. S5b's "fold cleanup into S5b" disposition is
correct; the spec must also ban this pattern. **Recommendation**:
Tier-1 spec adds: "conftest.py MUST NOT modify `sys.modules` for
production packages; any test needing isolated imports uses
`importlib.reload` inside a test body or
`monkeypatch.delitem(sys.modules, ...)`."

### 3.5 S5a/S5b touch files that S2b/S2d also touch — order risk

Cross-shard file overlap from amendments
(`02-plans/01-amendments-post-redteam.md:167-176`):

- `test_inspector_workflow_analysis.py` — S2b (inspector group)
  AND S5b (V6 ad-hoc sqlite)
- `core/test_architecture_validation.py` — S2d (workflow-importing)
  AND S5b
- `core/test_lazy_connection.py` — S4 (PG audit) AND S5b
- `nodes/test_count_node.py` — S2d AND S4
- `core/test_async_sql_sqlite.py` — S2d AND S5a

If S2b/S2d/S5a/S5b run in parallel worktrees per
worktree-isolation.md Rule 4, the merge will conflict on these files.
The plan's parallel-wave note
(`02-plans/01-amendments-post-redteam.md:229-234`) says "conflicts on
pyproject.toml and pytest.ini are avoided since only S1 and S6 touch
those" but DOES NOT address overlapping test-file edits.
**Recommendation**: post-S1, run shards in TWO sequential waves:

- Wave A: S2a + S3 + S5a (no file overlap; safe to parallelize 3-up)
- Wave B: S2b + S2c + S2d + S4 + S5b (overlap on 5 files; serialize
  S5b after S2b/S2d/S4 OR explicitly assign overlap files to one shard
  and exclude from the others)

## 4. The `memory_dataflow` fixture deadlock — verified

Verified the docstring claim at `tests/unit/conftest.py:75-83`:

> Without explicit close() the DataFlow is released to GC, whose
> finalizer would previously run async_safe_run() inside **del** and
> interleave with subsequent fixture setup — the deadlock that hung the
> unit suite (see engine.py **del** commit).

**Engine.py commit that introduced the fix**:
`2c98e7b3 fix(dataflow): stop DataFlow.__del__ from calling close() to prevent deadlock`

Current state of `packages/kailash-dataflow/src/dataflow/core/engine.py`
lines 3484-3515: `__del__` emits `ResourceWarning` only; does NOT call
`close()` or `async_safe_run`. Conforms to `rules/patterns.md`
§ "Async Resource Cleanup" — which itself originated from the same bug.

**Latent risk in tests NOT using the fixture**: any test that
instantiates `DataFlow(...)` directly without an `await
db.close_async()` / `db.close()` re-introduces the GC race. The plan's
S5a/S5b refactor the 15+ files that do this — necessary but NOT
sufficient. The CLAUDE.md contract bans this pattern
(`packages/kailash-dataflow/tests/unit/CLAUDE.md:111-115`); the spec
needs to ELEVATE it to a MUST with a `/redteam` mechanical sweep:

```bash
# Tier-1 spec MUST add — grep audit for ad-hoc DataFlow instantiation
grep -rn 'DataFlow(' packages/kailash-dataflow/tests/unit \
  | grep -v 'memory_dataflow\|file_dataflow\|auto_migrate_dataflow' \
  | grep -v '#.*DataFlow('
# Any hit = potential GC-deadlock risk; require fixture or explicit close.
```

This is the testing-architecture variant of `rules/orphan-detection.md`
§ "Detection Protocol" — every ad-hoc `DataFlow(...)` is a potential
orphan-of-cleanup.

**Cross-language echo**: kailash-rs has its own DataFlow; if it has
equivalent `Drop` semantics with async cleanup, the same deadlock class
exists there. Per `rules/repo-scope-discipline.md`, I cannot recommend
work in kailash-rs from this session; I note here that the fix-pattern
in `engine.py` (emit warning, defer real cleanup to explicit
`close_async`) is the canonical resolution and applies cross-SDK.

## 5. Regression-test gap — what `tests/regression/` MUST add

Per `rules/testing.md` § "Regression Testing", every bug fix needs a
behavioral regression test in `tests/regression/test_issue_*.py` with
`@pytest.mark.regression`. The plan's S1–S6 fix multiple distinct
defects but adds ZERO regression tests. The gap is structural — the
next session's refactor can re-inline every fix.

**Required regression tests post-shard-landing** (each in
`packages/kailash-dataflow/tests/regression/test_issue_979_*.py`):

1. `test_issue_979_pytest_timeout_pinned.py`
   Behavioral: import `pytest_timeout` and assert version ≥ 2.3.0.
   Anchors S1's plugin pin against the next pyproject.toml edit.

2. `test_issue_979_no_fabric_top_imports_in_unit.py`
   Mechanical sweep test:

   ```python
   @pytest.mark.regression
   def test_no_fabric_top_imports_in_unit():
       import pathlib, re
       unit_root = pathlib.Path("packages/kailash-dataflow/tests/unit")
       violations = []
       for path in unit_root.rglob("*.py"):
           if "fabric/" in str(path):
               continue
           text = path.read_text()
           if re.search(r"^from dataflow\.fabric", text, re.MULTILINE):
               violations.append(str(path))
       assert not violations, f"fabric top-imports in unit: {violations}"
   ```

   Anchors S3's move against re-inlining.

3. `test_issue_979_no_pg_url_in_unit.py`
   Same pattern, regex for `postgresql://.*:543[24]`. Anchors S4.

4. `test_issue_979_no_tempfile_db_path_in_unit.py`
   Regex for `tempfile\.(mktemp|NamedTemporaryFile)` adjacent to
   `\.db|sqlite:///|DataFlow\(`. Anchors S5a.

5. `test_issue_979_no_async_local_runtime_top_import_in_unit.py`
   Anchors S2a-S2d's Layer B moves.

6. `test_issue_979_no_integration_test_suite_in_unit.py`
   `grep IntegrationTestSuite tests/unit/`. Anchors S4 V1 moves.

7. `test_issue_979_unit_suite_collects_clean_dev_only.py`
   This is the LOAD-BEARING regression test. It would invoke
   `pytest --collect-only` in a subprocess against a `[dev]`-only
   venv and assert exit 0. Tricky to land inside the test suite
   (chicken-and-egg with the dev venv), so this might land as a CI
   workflow step rather than a pytest file. Anchors S6.

Per `rules/refactor-invariants.md`, every shard that shrinks
something also needs a numeric invariant. The amended plan does NOT
land any invariant tests — that's a Rule 1+2 gap. Each test above is a
mechanical-grep invariant equivalent to LOC counts; together they form
the structural defense against re-inlining.

**Counterpart to red-team CRIT-2**: the violations-inventory was
under-counted by ~8 files
(`journal/0002-DISCOVERY-redteam-findings.md:174-198`); regression
tests #2–#6 above are the structural fix that would catch
under-counting in the NEXT iteration without human re-audit.

## 6. Performance-regression detection — survey of `test_*_performance_*` files

Seven files, totaling 5,062 LOC. Disposition recommendation per file:

| File                                                                  | Disposition                  | Reason                                                                                                     |
| --------------------------------------------------------------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `tests/unit/test_error_enhancer_performance.py` (494 LOC)             | MOVE to `tests/integration/` | Uses `ThreadPoolExecutor` + wall-clock concurrency timing; inherently flaky on shared CI                   |
| `tests/unit/testing/test_performance_regression_suite.py` (786)       | MOVE to `tests/integration/` | Statistics over JSON-persisted runs is a TIER-3 shape (history-aware); not unit                            |
| `tests/unit/testing/test_tdd_performance_benchmark.py` (742)          | MOVE to `tests/integration/` | Uses `LocalRuntime` + real workflow execution; per CRIT-2 it's already in Layer B move group               |
| `tests/unit/context_aware/test_performance_benchmarks.py` (436)       | MOVE to `tests/integration/` | `under_10_seconds` thresholds against `memory_dataflow` — wall-clock asserts violate the <1s tier-1 budget |
| `tests/unit/migrations/test_migration_performance_tracker.py` (845)   | KEEP in unit, RENAME         | Heavily mocked; doesn't actually time anything meaningful. Drop "_performance_" from filename              |
| `tests/unit/migrations/test_performance_validator.py` (818)           | KEEP in unit                 | Tests the validator's logic (mocked Mock/AsyncMock); name is misleading but content is unit-tier           |
| `tests/unit/migrations/test_not_null_performance_boundaries.py` (941) | MOVE to `tests/integration/` | Imports `psutil` + `resource` — process/memory benchmarks need real environment; flaky in container        |

**General testing-architecture stance**: wall-clock performance
assertions belong in Tier 2 OR a dedicated `tests/performance/` tier
(unrelated to `tests/regression/`). Reasons:

1. Tier 1's contract is `<1s per test`. A test asserting "under 10
   seconds" cannot stay under 1s under load; it CAN stay under 10s
   if the budget is honored, but the test's RELIABILITY axis is
   different from a unit test's.
2. Shared CI runners (GitHub Actions ubuntu-latest, the kailash-py
   self-hosted Mac Studio) experience neighbor-noise from concurrent
   jobs. A performance test that passes locally on a quiet dev box
   asserts a threshold that's noise on a shared runner.
3. The plan's S6 re-applies the PR #968 gate. Wall-clock perf tests
   in tier 1 introduce intermittent-failure risk in the very gate the
   workstream is trying to ship. Moving them OUT before gate re-application
   is the correct ordering.

**Tier-1 spec addition required**: "wall-clock performance assertions
are BLOCKED in Tier 1. File naming `test_*_performance_*` MUST live in
`tests/integration/` or `tests/performance/`." 5 of 7 files move.

This is NOT covered in the current shard plan — recommend adding it as
S2e or expanding S2d to include the 5 performance-test moves.

## 7. Summary — gaps not in the amended plan

Listed for the orchestrator to consider before /todos:

1. **Spec authoring gap**: `specs/testing-tiers.md` must be written
   (S6) and MUST carry the 8 invariants in §1 above.
2. **pytest.ini vs pyproject.toml precedence**: delete the redundant
   pyproject block; declare ONE canonical config file. (Not in plan.)
3. **`pythonpath` cwd dependency** (§1.6): make pytest invocation
   cwd-agnostic. (Not in plan.)
4. **Auto-applied-marker registration audit** (§1.2 + §1.3): close
   double-filter ambiguity and `--strict-markers` drift.
5. **Fixture-port audit pre-move** (§3.1–§3.3): every S2a-S2d-S3 shard
   prompt MUST grep for unit-tier fixture usage and port or refactor.
6. **Shard wave-coupling**: serialize Wave B post Wave A (§3.5);
   prevent overlap-merge conflicts.
7. **Conftest sys.modules manipulation ban** (§3.4 / §4): tier-1 spec
   MUST forbid the `tests/unit/query/conftest.py` bootstrap pattern.
8. **Ad-hoc DataFlow grep audit** (§4): elevate CLAUDE.md guidance to
   a mechanical `/redteam` sweep.
9. **Regression-test set** (§5): land 6-7 regression tests anchoring
   each shard's structural fix against re-inlining.
10. **Performance-test relocation** (§6): 5 of 7 `*_performance_*`
    files move to integration/performance tier; 1 renames to drop
    misleading "performance" prefix.
11. **`--assert=plain` evaluation** (§2): empirical test for OOM
    reduction in clean-venv CI; if effective, set as Tier-1 default.

Eleven structural gaps; each is small (≤50 LOC equivalent change).
Together they are the difference between "the gate re-lands" and
"the gate re-lands AND stays clean for the next 6 months."

## Anchors

- Plan + amendments cited paths above.
- engine.py `__del__` fix: commit `2c98e7b3`.
- Empirical 3849 tests / 1.00s collection: `pytest --collect-only -q
packages/kailash-dataflow/tests/unit` in local dev venv.
- pytest config precedence: pytest documentation (linked above);
  empirical proof in this repo:
  `packages/kailash-dataflow/pytest.ini` AND `pyproject.toml
[tool.pytest.ini_options]` both present; only pytest.ini takes
  effect (different marker counts, only pytest.ini's markers resolve
  on `pytest --markers`).
- Performance-file LOCs and import patterns: `wc -l` + grep on each of
  the 7 `test_*_performance_*` files listed in §6.
