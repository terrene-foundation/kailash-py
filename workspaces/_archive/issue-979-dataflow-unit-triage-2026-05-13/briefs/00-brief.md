# Brief: DataFlow Unit Suite Triage (Issue #979)

## User goal

Make `packages/kailash-dataflow/tests/unit/` tier-1-clean so PR #968's
CI gate (issue #898) can re-land safely. Until this holds, every
DataFlow PR rediscovers the 5-layer failure surfaced in PR #976.

## Value-anchor

Tier-1 contract per project testing model: `tests/unit/` MUST run in
<10s on a clean install with no external infrastructure (no
PostgreSQL, no `[fabric]` extra, no real workflows). The current
DataFlow unit suite violates this on five distinct axes. Until fixed,
the #898 CI gate cannot land — it would convert every DataFlow PR
into a tier-2-environment-required run.

Source: issue #979 (filed 2026-05-13 prior session) + PR #976 closure
comment (5-iteration debug record) + PR #977 (revert of the gate).

## Failure layers (from PR #976 — verify each)

1. **pytest-timeout missing** — `--timeout` flag required the
   pytest-timeout plugin that wasn't installed in the workflow.
2. **OOM under pytest's AST rewriter** — collection memory exhausted
   on certain test modules.
3. **fork + asyncio incompatibility** — child processes inherited an
   event loop they couldn't cleanly use.
4. **`[fabric]` extra not installed** — `tests/unit/fabric/*` imports
   fail without the optional dependency.
5. **PostgreSQL-requiring "unit" tests** — `TestImpactReporterIntegration`
   and similar are integration-shaped but classified tier-1.

Each layer needs an independent verification agent (parallel
brief-claim verification per agents.md MUST: issue count ≥ 3).

## Acceptance criteria (verbatim from #979)

- [ ] `tests/unit/examples/test_example_gallery.py` moved to
      `tests/integration/` (real workflows, ~12s/test).
- [ ] `tests/unit/features/test_dataflow_events.py` — 4+ test failures
      from PR #976 investigation diagnosed and fixed.
- [ ] `tests/unit/fabric/*` either moved to `tests/integration/fabric/`
      (with `[fabric]` extra documented) OR gated behind
      `pytest.importorskip("fabric_dep_name")` at module top.
- [ ] `TestImpactReporterIntegration` moved to `tests/integration/`
      (requires PostgreSQL).
- [ ] Any remaining tier-1 test that imports `motor`, `psycopg`, or
      other DB drivers is either gated behind `importorskip` OR moved
      to `tests/integration/`.
- [ ] After moves: `pytest packages/kailash-dataflow/tests/unit -x`
      exits 0 in ≤2 min without `[fabric]` / PostgreSQL.
- [ ] PR #968 can then be re-applied (re-enable the CI gate).

## Scope boundaries

- IN: `packages/kailash-dataflow/tests/unit/**` reclassification and
  fixes.
- IN: documentation of `[fabric]` extra requirements for the
  integration tier.
- IN: re-application of the PR #968 CI gate as a final shard once
  tier-1 is clean.
- OUT: changes to non-DataFlow test tiers.
- OUT: production code changes outside `tests/`, unless a failing test
  reveals a real bug (deep-dive per zero-tolerance Rule 4 — fix
  not workaround).

## Related artifacts

- Issue #898 — original gate proposal
- PR #967 / #968 — initial gate work (gate reverted)
- PR #976 — 5-iteration debug (closed, has the failure-layer details)
- PR #977 — revert of #968
