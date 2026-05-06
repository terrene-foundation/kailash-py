# Specs Index — DataFlow Engine Pyright Cleanup

This directory holds the domain-truth specifications for the cleanup workspace's deliverables. Per `rules/specs-authority.md` Rule 4, phase commands MUST read this index before reading any individual spec file.

Per `rules/spec-accuracy.md` Rule 5, every spec section in this directory describes behavior shipped on `main` post-cleanup-merge (T1–T8 of the dataflow-engine-pyright-cleanup workspace, 2026-05-04). Cleanup intent and historical state are NOT spec content — they live in `02-plans/` (architecture + sharding) and `journal/` (decisions + discoveries). Spec files here are amended ONLY when the underlying behavior on main changes.

## Files

| File                           | Domain                              | Description                                                                                 |
| ------------------------------ | ----------------------------------- | ------------------------------------------------------------------------------------------- |
| `static-analysis-baseline.md`  | Static analysis (pyright)           | Pre-cleanup pyright baseline (5 errors + 56 warnings) on `main @ a28caf0d` — historical     |
| `production-test-isolation.md` | Import discipline (production code) | Production source MUST NOT import from `tests.*`; verifying grep + acceptable patterns      |
| `regression-gate-contract.md`  | Test infrastructure (regression)    | Contract enforced by `tests/regression/test_engine_pyright_invariant.py`; pinned thresholds |

All three specs describe behavior on `main` post-cleanup-merge. No contracts-in-waiting remain.

## Brief traceability

| Brief acceptance criterion                         | Authorizing artifact                                                                                      |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| #1 — All 5 errors resolved at root cause           | `production-test-isolation.md` (E1) + `02-plans/01-cleanup-architecture.md` § "Sharding" T1+T2+T3 (E2-E5) |
| #2 — Warning triage with grounded comments         | `regression-gate-contract.md` § "Pass condition" + `01-analysis/01-research/02-warning-categorization.md` |
| #3 — Zero NEW pyright diagnostics                  | `regression-gate-contract.md` § "Drift detection"                                                         |
| #4 — Exit 0 errors, ≤10 warnings                   | `regression-gate-contract.md` § "Pass condition"                                                          |
| #5 — No public API changes (deviations documented) | `static-analysis-baseline.md` § "Public surface invariant"                                                |
| #6 — Regression test in CI default path            | `regression-gate-contract.md` § "Test placement + collection"                                             |
