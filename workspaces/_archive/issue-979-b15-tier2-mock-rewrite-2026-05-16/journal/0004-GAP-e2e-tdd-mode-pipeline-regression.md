# GAP — No E2E Tier-2 regression covers `DataFlow(tdd_mode=True)` docs pipeline

**Date**: 2026-05-15
**Phase**: /analyze Round-1 red team
**Source**: testing-specialist HIGH-4 (`04-validate/03-redteam-testing.md`)

## What's missing

`rules/testing.md` § MUST: End-to-End Pipeline Regression: "Every canonical
pipeline the docs teach (README Quick Start, tutorial, 3-line example) MUST
have a Tier-2+ regression test executing DOCS-EXACT code against real infra."

The `DataFlow(tdd_mode=True)` API is a docs-taught canonical pipeline. No
file in `packages/kailash-dataflow/tests/regression/` covers it end-to-end.
File 9 (`test_real_tdd_integration.py`) was the closest existing test, but
it patches 7 internal init phases — it tests constructor metadata, not the
TDD pipeline end-to-end. After Shard 1 moves it to `tests/unit/core/`, the
gap remains.

## Value-anchor (per `rules/value-prioritization.md` MUST-2)

Closes the SDK contract that every docs-taught canonical pipeline has a
regression test. Source: `rules/testing.md` § MUST: End-to-End Pipeline
Regression (verbatim).

## Disposition

**Out of scope for #992.** #992's brief is mock-rewrite scope — the
pipeline-coverage gap pre-dates #992 and is orthogonal.

**Follow-up disposition** (per `rules/value-prioritization.md` MUST-2):
file as NEW kailash-py issue **after** #992 closes:

```
Title: feat(dataflow-tests): TDD-mode docs-pipeline Tier-2 regression test
Body:
## Affected SDK API surface
DataFlow(tdd_mode=True) constructor + @db.model + WorkflowBuilder pipeline

## Expected vs actual
Expected: tests/regression/test_readme_tdd_mode_quickstart.py exercises
the README's TDD-mode quick-start end-to-end against real PG.
Actual: no such test exists. File 9 (test_real_tdd_integration.py) is a
mocked unit test of constructor metadata, not pipeline coverage.

## Severity
LOW — TDD-mode is a developer-experience feature, not a production data
path. No active incident.

## Acceptance criteria
- [ ] tests/regression/test_readme_tdd_mode_quickstart.py exists with
      @pytest.mark.regression
- [ ] Test exercises DataFlow(tdd_mode=True) + @db.model + WorkflowBuilder
      + execute end-to-end against IntegrationTestSuite
- [ ] Final user-visible outcome asserted (per rules/testing.md §
      End-to-End Pipeline Regression)
```

The follow-up is filed AFTER #992 closes to keep #992 scope crisp. Captured
in v2 § Out of scope (per amendment A7).

## Cross-rule relevance

- `rules/value-prioritization.md` MUST-2: deferred shards carry value-anchors.
- `rules/testing.md` § MUST: End-to-End Pipeline Regression.
- `rules/value-prioritization.md` MUST-4: closure-of-value-bearing-work
  requires user gate — this GAP entry IS the institutional memory the next
  session uses to confirm value still applies before closure.
