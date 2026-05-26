# 0001 DISCOVERY — Brief Verification (Parallel Deep-Dive)

Date: 2026-05-13
Phase: /analyze
Issue: #979

## Why this entry

Per `rules/agents.md` MUST "Parallel Brief-Claim Verification When Issue
Count ≥ 3", I launched 5 parallel general-purpose agents to verify
each failure-layer claim in `briefs/00-brief.md` against current main
(`21ba8e6a`). This entry records the verdicts and the brief
corrections that resulted, BEFORE `/todos`.

## Per-layer verdicts vs current main

### Layer 1 — pytest-timeout / pytest-forked missing

**Verdict:** PARTIALLY TRUE — needs reframing.

- `pytest-timeout>=2.3.0` IS declared at root `pyproject.toml:166`.
- `pytest-timeout` is NOT declared in
  `packages/kailash-dataflow/pyproject.toml` `[dev]` extras
  (lines 124-137).
- `pytest-forked` is NOT pinned in either manifest — it is installed
  transitively in the dev venv (`xdist-3.8.0 + forked-1.6.0` in
  the collection banner) but unavailable in a clean CI install.
- `timeout = 120` is NOT in `packages/kailash-dataflow/pytest.ini`
  nor in `pyproject.toml [tool.pytest.ini_options]`. PR #976's
  defensive timeout fix never landed on main (see #976 status
  below).
- `.github/workflows/unified-ci.yml` has ZERO dataflow test
  remnants (no `test-dataflow` job, no dataflow path filter).

### Layer 2 — `test_example_gallery.py` fork+asyncio

**Verdict:** TRUE on the structural shape; FALSE on PR #976 helpers.

- File exists at 1094 lines, 10 async test methods in 5 classes
  (Stripe, SendGrid, OpenAI, S3, JWT/OAuth2).
- Imports `AsyncLocalRuntime` (line 22) and `WorkflowBuilder`
  (line 23) — 10 + 15 instantiations respectively.
- `DataFlow(DB_URL)` instantiated with no kwargs in all 10 tests,
  so `auto_migrate=True` default (per `engine.py:151`) fires real
  DDL per test against a module-scoped `tempfile.mktemp()` SQLite
  file shared across the suite (line 28-30).
- `_fresh_db_url()` helpers from PR #976 are ABSENT from current
  main — verifies PR #976 never landed.
- `memory_dataflow` fixture EXISTS at
  `packages/kailash-dataflow/tests/unit/conftest.py:75` —
  PR #977's recovery plan #4 has a real refactor target.

### Layer 3 — fabric/ imports without `[fabric]`

**Verdict:** TRUE.

- `packages/kailash-dataflow/tests/unit/fabric/` has 21 test
  files + `__init__.py`.
- 17 of 21 top-import `from dataflow.fabric.*` at module scope
  (test_config.py:14, test_context.py:11, etc.) — the remaining 4
  import only `dataflow.adapters.*` or stdlib.
- `dataflow.fabric` is in-tree at
  `packages/kailash-dataflow/src/dataflow/fabric/` — runtime
  failure mode is its sub-modules' deps:
  `httpx>=0.27, watchdog>=4.0, msgpack>=1.0, prometheus-client>=0.20`
  declared as the `[fabric]` extra at `pyproject.toml:95-100`.
- ZERO `importorskip` gating in any unit/fabric file.
- `tests/integration/fabric/` does NOT exist (22 sibling integration
  subdirs but no fabric twin).

### Layer 4 — PostgreSQL-requiring "unit" tests

**Verdict:** TRUE and BROADER than #979 lists.

- Direct integration-class: `tests/unit/migration/test_impact_reporter_unit.py:67`
  uses `tests.infrastructure.test_harness.IntegrationTestSuite` —
  requires PG:5434.
- Bare top-import: `tests/unit/testing/test_tdd_support.py:16`
  `import asyncpg` at module scope, no `importorskip`.
- PG:5434 URLs (likely real connection attempts):
  `tests/unit/migrations/test_migration_test_framework.py:48,82`,
  `tests/unit/test_dataflow_bug_011_012_fixes.py:230,273`,
  `tests/unit/test_tdd_node_generation_integration.py:148,182,267`.
- PG:5432 URLs (may be patched but still real-shaped):
  `test_bug_006_safety_parameters.py` (10 sites),
  `test_actual_api_validation.py` (10 sites),
  `test_real_tdd_integration.py` (5 sites),
  `test_count_node.py:21`, `test_bulk_upsert_delegation.py:28`,
  `test_architecture_validation.py:197`.
- ZERO `requires_postgres / requires_mysql / requires_redis /
requires_docker` markers in any unit test (markers ARE
  declared in `pytest.ini:18-21`).
- `addopts` is `-v --strict-markers --tb=short` — no marker
  exclusion at the unit tier.

### Layer 5 — OOM + `test_dataflow_events.py` failures

**Verdict:** OOM claim plausible; "4+ events failures" UNCLEAR.

- `tests/unit/features/test_dataflow_events.py` (182 lines, 11
  tests) is PURE-PYTHON: imports only `dataflow.core.events`,
  uses `class FakeDataFlow(DataFlowEventMixin)` — no DB, no
  runtime, no asyncpg. `pytest --collect-only` returns
  `collected 11 items` cleanly with zero errors. PR #976's
  "4+ failures" framing is NOT reproducing locally on main.
- Total unit collection: **3849 tests in 1.60s**, no collection
  errors (the local venv has `[fabric]` deps so the 17 fabric
  files import cleanly — the failure mode requires a clean
  `[dev]`-only install to surface).
- AST assertion rewriting is ENABLED (default); no
  `--assert=plain` in either pytest config.
- pytest-xdist pinned at root; pytest-forked transitive only.

## Critical brief corrections (gate before /todos)

1. **PR #976 was NEVER MERGED** (`gh pr view 976 --json mergedAt`
   returns `null`; branch `fix/dataflow-unit-ci-hang-after-968`).
   Its commit `65009cc8` is reachable via `--all` but NOT on main.
   The brief at `briefs/00-brief.md` and #979's body both
   reference PR #976 as if its fixes landed; they did NOT. This
   means the layered fixes (`_fresh_db_url`, `timeout=120`,
   `importorskip` for aiomysql/redis) all need to be re-derived
   from scratch as part of this workstream, not assumed in place.

2. **#979 Acceptance Criterion 2 may already be satisfied** —
   `test_dataflow_events.py` is pure-Python and collects clean on
   current main. The "4+ failures" cited from PR #976's debug log
   may have been transient (env-specific, ordering-specific) or
   was unrelated to the current file's contents. Recommended:
   downgrade AC#2 from "diagnose and fix 4+ failures" to "verify
   no failures in a clean `[dev]`-only environment; document as
   resolved if green."

3. **Layer 4 (PG-requiring tests) is broader than the brief
   listed.** #979 names only `TestImpactReporterIntegration`. The
   actual surface is at least 11 files carrying real-shaped PG
   URLs plus `test_tdd_support.py`'s bare `import asyncpg`. The
   acceptance criterion needs to be widened to "audit ALL files
   with real DB URLs / direct DB-driver imports under `tests/unit/`."

4. **Local fabric tests pass collection only because the dev venv
   has `[fabric]` installed.** A clean CI install with
   `pip install -e ".[dev]"` (no `[fabric]`) is the canonical
   tier-1 environment — that's where the 17 import-fails happen.
   Verification command: `python -m venv /tmp/clean && /tmp/clean/bin/pip install -e packages/kailash-dataflow[dev] && /tmp/clean/bin/pytest packages/kailash-dataflow/tests/unit --collect-only`.

5. **The `timeout = 120` / `pytest-timeout` plumbing is a
   precondition, not a fix.** Without it landed FIRST, any
   subsequent failure (e.g., an undetected hang in
   `test_example_gallery.py` after refactor) surfaces as a
   silent 6-hour CI timeout instead of a clean per-test failure.
   This becomes Shard 1 in the plan.

6. **`tests/unit/migration/` (singular) and `tests/unit/migrations/`
   (plural) ARE DIFFERENT DIRECTORIES** — both exist. Layer 4's
   `test_impact_reporter_unit.py` is in `migration/`, while
   `tests/unit/migrations/test_impact_reporter.py` (mock-based,
   different file) is in `migrations/`. The plan must use full
   paths everywhere — `migration/` vs `migrations/` ambiguity is
   high-risk.

## Implications for /todos

- The plan MUST have a precondition shard (plugin pinning +
  timeout config) BEFORE any test-classification work.
- The plan MUST verify in a clean `[dev]`-only venv, not the
  dev workstation venv that already has `[fabric]`.
- The plan MUST adopt one of two consistent strategies per
  failure layer (move-to-integration OR importorskip-gate) and
  apply it uniformly — mixing both per-file invites drift.
- The plan MUST end with re-applying PR #968 as the final
  acceptance shard, because that IS the user-anchored value:
  every DataFlow PR currently rediscovers this failure mode.
