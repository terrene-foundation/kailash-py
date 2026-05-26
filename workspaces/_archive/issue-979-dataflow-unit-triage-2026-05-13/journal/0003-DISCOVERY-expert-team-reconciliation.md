# 0003 DISCOVERY — Expert Team Reconciliation (Pre-Redteam)

Date: 2026-05-13
Phase: /analyze (expanded, per user directive "expert team + pentest")
Issue: #979

## What ran

Five experts in parallel:

| Agent                  | Output                                                 | Lines |
| ---------------------- | ------------------------------------------------------ | ----- |
| testing-specialist     | `01-analysis/03-expert-testing/00-...md`               | 282   |
| security-reviewer (×2) | `01-analysis/02-pentest/{00,01}-...md`                 | ~700  |
| dataflow-specialist    | `01-analysis/04-expert-dataflow/00-...md`              | ~500  |
| release-specialist     | `01-analysis/05-expert-release/00-...md`               | ~320  |
| general-purpose        | `01-analysis/02-pentest/02-security-test-inventory.md` | 230   |

Combined: ~2,030 lines of expert analysis. Reconciled below by
severity. This journal is the receipts anchor for /redteam Round 1.

## Findings reconciled by severity

### CRIT (plan-blocking — must amend before /todos)

**CRIT-A — `pytest-forked` is archived upstream.** No release since
2021; repo read-only. Pinning a dead package violates
`rules/dependencies.md` "Own the Stack." Disposition: DROP from
S1. `test_example_gallery.py` (the test needing process isolation)
moves to integration in S2a anyway.
Source: release-specialist Finding 1.

**CRIT-B — Double-filter trap.** S1 puts marker-exclusion in
`pytest.ini::addopts`. If S6 also passes `-m` in the workflow run
command (as PR #968 did), the two filters intersect AND integration
jobs that pass `-m requires_postgres` would silently suppress those
tests. S6 MUST have ZERO `-m` flags; pytest.ini is the sole
canonical location.
Source: release-specialist Finding 2 + redteam HIGH-3 from journal 0002.

**CRIT-C — `pyproject.toml [tool.pytest.ini_options]` is dead
config.** `packages/kailash-dataflow/` has BOTH `pytest.ini` AND
`pyproject.toml`'s `[tool.pytest.ini_options]` with the 6-marker
block. Pytest precedence rule: `pytest.ini` wins; pyproject's
config is silently inert. S1 must consolidate.
Source: testing-specialist gap #1.

### HIGH (must address before /todos)

**HIGH-A — Security coverage REGRESSION on PR-gate.** The proposed
moves take 3-5 security-purposeful tests out of tier-1:

- `test_saas_starter_jwt.py` (S2c MOVE) — JWT auth
- `test_saas_starter_auth.py` (S2c MOVE) — auth pipeline
- `test_saas_tenancy.py` (S2c MOVE) — **cross-tenant access block**
- `test_write_protection_comprehensive.py` (S4 audit) — write protection
- `test_protection_system_critical_gaps.py` (S4 audit) — protection gaps

Net change: -3 to -5 tier-1 security tests (16.7%-27.8% reduction).
Per-PR security feedback weakens.
Source: general-purpose security inventory; security-reviewer
coverage audit.

**HIGH-B — Fabric S3 move silently removes 2 tier-1 security
signals.** `test_ssrf.py` (SSRF validation) and
`test_fabric_integrity.py` (middleware tamper detection) move to
integration as part of the directory move. Both close to zero
per-PR signal. Tier-1 OR tier-2 coverage of these threats today
is zero outside these files.
Source: security-reviewer COVERAGE-LOSS-1 + 2.

**HIGH-C — Pre-existing sanitizer-contract gap.** `rules/security.md`
§ Sanitizer 1 (token-replace not quote-escape) and § Sanitizer 2
(type-confusion `ValueError`) have ZERO grep-able tier-1 OR
tier-2 test assertions. The DataFlow sanitizer is documented
defense-in-depth; absence of tests means a regression to
quote-escape would not be caught.
Source: security-reviewer GAP-1, GAP-2; security-test-inventory
finding #5.

**HIGH-D — DNS-rebinding bypass.** Fabric SSRF validator does
NOT resolve DNS; attacker-controlled DNS that resolves to internal
on attack time bypasses the validator. Pre-existing.
Source: security-reviewer GAP-A.

**HIGH-E — `test_workflow_binding.py:109-115` MUST NOT move.**
Only tier-1 file mechanically verifying `_resolve_node_type` for
all 11 DataFlow node ops (`Create`, `Read`, `Update`, `Delete`,
`List`, `Count`, `BulkCreate`, `BulkUpdate`, `BulkDelete`,
`BulkUpsert`, `Update`). Uses `memory_dataflow` (73 references),
imports `WorkflowBuilder` but never executes a real workflow
(LocalRuntime is mocked). S2d's blanket MOVE would lose this
coverage. Disposition: STAY in tier-1, importorskip the one
runtime-touching test.
Source: dataflow-specialist Finding 3 (load-bearing).

**HIGH-F — Engine API invisible to tier-1.** `DataFlowEngine.builder`
/ `DataFlowEngine(...)` has zero matches in `tests/unit/`. The
framework-first.md-recommended default Engine layer has no tier-1
smoke coverage today AND after every move.
Source: dataflow-specialist Finding 1.

**HIGH-G — `db.express` async surface → ZERO tier-1 coverage
after S3.** Only async Express tests live under `tests/unit/fabric/`
(S3 → integration). Surviving tier-1 Express coverage is 3
`express_sync.list` invocations in `test_derived_model.py` — none
of `read`, `count`, `async-form`, or `bulk`.
Source: dataflow-specialist Finding 2 (load-bearing).

**HIGH-H — Zero regression tests in current plan.** Per
`rules/testing.md` § Regression, every fix needs a behavioral
regression test. The plan ships 6 (now 10) shards with no
`tests/regression/test_issue_979_*.py` files. After this work, a
future refactor can silently re-introduce `tempfile.mktemp` or
bare `import asyncpg`.
Source: testing-specialist gap #5.

### MED (should address, document if deferred)

**MED-A — Fixture-port problem.** When `test_X.py` uses
`memory_dataflow` (defined in `tests/unit/conftest.py`) and S2a-S2d
move the file to `tests/integration/`, the fixture is unavailable
unless duplicated to the integration conftest. The plan must
either (a) move the fixture too, (b) duplicate it, or (c) refactor
moved tests to use `tests/integration/conftest.py`'s
`IntegrationTestSuite`.
Source: testing-specialist gap #3.

**MED-B — Cross-shard file overlap on 5 files.** Files matching
multiple violation classes:

- `test_count_node.py` (S2d ∩ S4)
- `test_lazy_connection.py` (S2d ∩ S4)
- `test_logging_config.py` (S2d ∩ S4)
- `test_logging_levels.py` (S2d ∩ S4)
- `test_inspector_workflow_analysis.py` (S2b ∩ S5b)

Requires Wave A / Wave B serialization OR explicit per-file
ownership.
Source: testing-specialist gap #3.

**MED-C — Performance-test files belong in tier-2.** 5 of 7
`test_*_performance_*` files have wall-clock asserts that violate
the <1s tier-1 budget and cause shared-CI flake. The plan moves
some via S2/S5 but not all explicitly.
Source: testing-specialist gap #6.

**MED-D — DataFlow Engine smoke test needed in S6.** New file
`tests/unit/engine/test_engine_smoke.py` exercising
`DataFlowEngine.builder()` chain — closes HIGH-F.
Source: dataflow-specialist net recommendation.

**MED-E — Express smoke test needed in S6.** New file
`tests/unit/express/test_express_smoke.py` exercising `read`,
`count`, async forms — closes HIGH-G.
Source: dataflow-specialist net recommendation.

**MED-F — `--assert=plain` evaluation.** Testing-specialist
recommends evaluating `--assert=plain` for the unit suite as part
of S1 (would reduce AST-rewrite cache memory; addresses the OOM
class).
Source: testing-specialist gap #2.

**MED-G — `pytest.mark.security` is unused.** Zero matches across
the package. A marker-based per-PR gate doesn't exist; the only
way to run "all security tests" today is directory enumeration.
S6 should declare + apply this marker.
Source: general-purpose security inventory finding #2.

### LOW (cosmetic / followup)

- LOW-1: `pythonpath = src` cwd dependency in `pytest.ini`.
- LOW-2: Auto-applied markers (`sqlite_memory`, `sqlite_file`,
  `mocking`) named in CLAUDE.md but not declared in pytest.ini
  (drift-3 from journal 0002).
- LOW-3: Surviving `tempfile.NamedTemporaryFile` in
  `tests/unit/testing/test_performance_regression_suite.py` is
  for `.json` (not DB) — keep, document.
- LOW-4: `tests/integration/trust/` does not exist (separate issue;
  facade-manager-detection.md Rule 1 violation; flag for separate
  workspace).

## Total CRIT + HIGH count

3 CRIT + 8 HIGH = 11 plan-affecting findings. The amended plan
(`02-plans/01-amendments-post-redteam.md`) covered some via S2/S4
splits but DID NOT address:

- CRIT-A (pytest-forked archived)
- CRIT-C (dead pyproject config)
- HIGH-A (security coverage regression)
- HIGH-B (fabric tier-1 security loss)
- HIGH-C, HIGH-D (sanitizer + DNS-rebinding pre-existing gaps)
- HIGH-E (test_workflow_binding.py must stay)
- HIGH-F (engine API tier-1 coverage)
- HIGH-G (express async tier-1 coverage)
- HIGH-H (zero regression tests)

A second-pass amendment is required. The pattern is consistent —
each expert lens surfaces gaps invisible to the prior lens. This
validates the user's directive to expand the analysis.

## Receipt for /redteam Round 1

When /redteam runs adversarial agents, they will independently
verify these findings AND look for gaps the experts missed. The
convergence target is two consecutive rounds with zero new CRIT/HIGH.

Round 1 reads:

1. All briefs / journals / research / plan / amendments
2. The 5 expert artifacts (~138 KB)
3. The spec (`specs/testing-tiers.md`)
4. Cross-reference against `rules/security.md`, `rules/testing.md`,
   `rules/zero-tolerance.md`, `rules/spec-accuracy.md`

Round 1 mission: surface anything the experts missed, falsify
any finding the experts ASSERTED, and identify cross-finding
contradictions.
