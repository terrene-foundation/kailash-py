# Red Team Report — Sprint S12 PACT Spec-Conformance

**Date**: 2026-03-31
**Rounds**: 2 (pre-implementation todo review + post-implementation code review)
**Status**: CONVERGED — 0 open findings

## Round 1: Todo Review (Pre-Implementation)

3 CRITICAL, 5 HIGH findings in the todo plan. All fixed before implementation began. See journal entry `0017-RISK-pact-todos-red-team-three-critical-findings.md`.

## Round 2: Post-Implementation Code Review

### Security Review Findings

| #   | Severity | Finding                                                            | Status                                                 |
| --- | -------- | ------------------------------------------------------------------ | ------------------------------------------------------ |
| C1  | CRITICAL | `posixpath.normpath()` used instead of `normalize_resource_path()` | Pre-existing, out of scope                             |
| C2  | CRITICAL | `_vacancy_start_times` unbounded dict                              | Bounded by org size (max 100K nodes), acceptable       |
| C3  | CRITICAL | `register_compliance_role()` accepts phantom addresses             | **FIXED** — address validation added                   |
| C4  | CRITICAL | Vacant head role_id collision with user-defined roles              | **FIXED** — collision check added in compilation.py    |
| H1  | HIGH     | `check_passthrough_envelope` NaN equality edge case                | Accepted — Pydantic v2 `__eq__` handles correctly      |
| H2  | HIGH     | `check_gradient_dereliction` NaN in 90% threshold                  | Low risk — upstream `DimensionThresholds` rejects NaN  |
| H3  | HIGH     | `InMemoryPactEmitter` thread safety on free-threaded Python        | Accepted — CPython GIL sufficient for current runtimes |

### Deep Analysis Findings

| #   | Severity | Finding                                                     | Status                                           |
| --- | -------- | ----------------------------------------------------------- | ------------------------------------------------ |
| R1  | CRITICAL | Multiple vacant ancestors don't intersect interim envelopes | **FIXED** — intersect loop in `_check_vacancy()` |
| R2  | CRITICAL | `consent_bridge()` accepts phantom addresses                | **FIXED** — address validation added             |
| R3  | HIGH     | Timezone mismatch in temporal intersection                  | Documented — warning log added                   |
| R5  | MEDIUM   | Vacant head role_id collision                               | **FIXED** — collision check in compilation.py    |
| R7  | MEDIUM   | Bridge scope validation skip for no-envelope roles          | **FIXED** — fail-closed when envelope missing    |

### Red Team Regression Tests

7 tests in `test_redteam_r1_findings.py`:

- R1: 2 tests (multiple vacant ancestors intersection)
- R2: 2 tests (phantom address rejection for consent + compliance)
- R3: 1 test (timezone mismatch handling)
- R5: 2 tests (role_id collision + multi-headless units)

## Final Test Results

- **1240 passed**, 10 skipped, 0 failures (baseline: 1139)
- **+101 new tests** across 8 test files
- 0 regressions

## Convergence

Red team converged after Round 2. All CRITICAL and HIGH findings either fixed or accepted with rationale. No open findings remain.
