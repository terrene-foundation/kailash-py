# Testing Tiers — Domain Spec

Authoritative contract for the three-tier testing model that
applies to every package in this repository (Core SDK, DataFlow,
Nexus, Kaizen, MCP, PACT, ML, Align). Developer guides at
`tests/unit/CLAUDE.md`, `tests/integration/CLAUDE.md`, and
package-specific `packages/*/tests/CLAUDE.md` describe HOW;
this spec defines WHAT MUST hold.

When code and spec disagree, fix the code or update the spec —
never leave them divergent (per `rules/specs-authority.md`).

## Three tiers

| Tier | Directory            | Infra surface                            | Budget                         |
| ---- | -------------------- | ---------------------------------------- | ------------------------------ |
| 1    | `tests/unit/`        | SQLite (memory + file), in-process mocks | <10s per test, <2 min suite    |
| 2    | `tests/integration/` | Real PostgreSQL, Redis, MongoDB, Docker  | <60s per test, <15 min suite   |
| 3    | `tests/e2e/`         | Full production stack, multi-service     | <5 min per test, <30 min suite |

Tier number is the maximum infrastructure cost; lower tiers MUST
NOT exceed their tier's surface.

## Tier-1 (Unit) Contract — MUST Rules

### 1. No external infrastructure at import or run time

The following MUST NOT appear in any `tests/unit/` file unless
gated by `pytest.importorskip(...)` at module top:

- `import asyncpg` / `import psycopg` / `import psycopg2` / `import pymysql`
- `import aiomysql` / `import motor` / `import redis`
- `from kailash.runtime import AsyncLocalRuntime` (real workflow runtime)
- `from kailash.workflow.builder import WorkflowBuilder` (real workflow builder)
- `from tests.infrastructure.test_harness import IntegrationTestSuite`
  (the PG integration harness)

Bare top-imports of these modules BLOCK collection in a clean
`[dev]`-only install. The `importorskip` gate converts
ImportError into a clean skip.

### 2. Use standardized fixtures, never ad-hoc connections

`tests/unit/` files MUST consume the fixtures from
`tests/unit/conftest.py` for DataFlow instances and SQLite
connections. The following patterns are BLOCKED:

- `tempfile.NamedTemporaryFile(suffix=".db", ...)` for DB paths
- `tempfile.mktemp(suffix=".db", ...)` at module or function scope
- `DataFlow(f"sqlite:///{tmp.name}")` ad-hoc instantiation
- `DataFlow("postgresql://...")` in unit tests (any port)

Canonical fixtures:

| Fixture                   | Yields                              | Use case                                       |
| ------------------------- | ----------------------------------- | ---------------------------------------------- |
| `memory_dataflow`         | DataFlow w/ in-memory SQLite        | Fast DataFlow API tests (most common)          |
| `file_dataflow`           | DataFlow w/ file SQLite             | Tests requiring persistence across operations  |
| `auto_migrate_dataflow`   | DataFlow w/ `auto_migrate=True`     | Tests of migration triggering only             |
| `unit_test_suite`         | Suite handle (StandardUnitFixtures) | Default unit-test suite handle (memory-backed) |
| `memory_test_suite`       | Suite handle (raw SQLite conn)      | Direct-SQL without DataFlow facade             |
| `file_test_suite`         | Suite handle (file SQLite)          | Direct-SQL w/ persistence                      |
| `mock_connection_manager` | Mock                                | External-pool-shape behavior tests             |
| `mock_migration_executor` | Mock                                | Migration logic w/o real DDL                   |

Each fixture yields+closes per `rules/testing.md` §
"Fixtures Yield + Cleanup, Never Return", which for DataFlow
means an explicit `await dataflow.close_async()` in the
fixture's `finally` block. The canonical shape is at
`packages/kailash-dataflow/tests/unit/conftest.py:80-108`
(`memory_dataflow` / `file_dataflow` / `auto_migrate_dataflow`).

Direct `DataFlow(...)` instantiation in a test body bypasses
this cleanup. After PR #1001 (commit `5cae13c0`), `DataFlow.__del__`
only emits a `ResourceWarning` per `rules/patterns.md` §
"Async Resource Cleanup" — it does NOT close the underlying
aiosqlite connection pool. Un-closed instances leave non-daemon
aiosqlite background threads alive past pytest's success summary,
blocking `_Py_Finalize → wait_for_thread_shutdown` indefinitely
(reproduces today: see issue #1002).

DataFlow exposes a sync context manager (`with DataFlow(...) as
db:` calling `close()` on `__exit__`) but NO async context
manager. Async tests MUST use the `try / finally: await
dataflow.close_async()` shape, not `async with`.

### 3. Marker discipline

Every `tests/unit/` test is implicitly `@pytest.mark.unit`.

When a borderline test cannot be cleanly moved, marker-gating
applies:

- `@pytest.mark.requires_postgres` — needs PG at :5432 / :5434
- `@pytest.mark.requires_mysql` — needs MySQL
- `@pytest.mark.requires_redis` — needs Redis
- `@pytest.mark.requires_docker` — needs Docker

The unit-tier `pytest.ini` `addopts` MUST include
`-m "not (requires_postgres or requires_mysql or
requires_redis or requires_docker)"` to exclude marked
tests from the tier-1 run by default. CI integration jobs
override the marker filter.

### 4. Mocking discipline

- Mock external services (HTTP clients, external APIs, external systems)
- Do NOT mock SQLite — use real SQLite for DB operations
- Use the provided mock fixtures (`mock_*` family) rather than ad-hoc `unittest.mock` patches when behavior overlap exists
- Patches to driver modules (`patch("asyncpg.connect", ...)`) are acceptable for testing connection-error paths; bare top-imports of the patched module are not

### 5. Test isolation

- Each test independent; no shared state across tests
- Trust fixtures for cleanup; no manual teardown
- No order-dependent assertions

### 6. Required CI plugins (clean `[dev]` install)

Every package's `[project.optional-dependencies] dev` MUST
include:

- `pytest>=7.0.0`
- `pytest-asyncio>=0.23.0`
- `pytest-timeout>=2.3.0` — per-test timeout enforcement
- `pytest-cov>=4.0.0`

`pytest-forked` is OPTIONAL — pin it ONLY when the package has
real consumers of the plugin's `--forked` flag or
`@pytest.mark.forked` decorator. Pinning a no-consumer plugin
violates `rules/dependencies.md` "Own the Stack."

In addition, each package MUST pin every Tier-1 infra driver
its canonical fixtures import at module scope. SQLite is the
Tier-1 infra surface (see Three tiers table above), so any
package whose Tier-1 fixtures use async-SQLite MUST include
`aiosqlite>=0.19.0` in `[dev]`. The general rule: a bare
top-level import in any `tests/unit/conftest.py` or
`tests/fixtures/*.py` consumed by `conftest.py` MUST be
satisfiable by `pip install -e packages/<pkg>[dev]` alone.

The package's `pytest.ini` MUST declare:

- `timeout = 120` (or lower for the package's budget)
- `timeout_method = thread` (default; or `signal` where supported)

These MUST be redundantly pinned in each package, not relied
upon transitively from the root, so a clean
`pip install -e packages/<pkg>[dev]` install reproduces CI.

## Tier-2 (Integration) Contract — MUST Rules

### 1. NO MOCKING

Per `rules/testing.md` § "No Mocking in Tier 2/3", integration
tests MUST exercise real infrastructure:

- Real PostgreSQL via `IntegrationTestSuite`
- Real Redis / Mongo / MySQL when subject under test requires them
- Real `AsyncLocalRuntime` / `LocalRuntime`
- Real network calls (mockable at the response layer only via VCR-style cassettes)

### 2. Standardized infrastructure harness

`tests/integration/` MUST use `IntegrationTestSuite` from
`tests/infrastructure/test_harness` for DB connections.
Hardcoded URLs BLOCKED.

### 3. Marker overrides

CI integration jobs run with `-m "requires_postgres or
requires_mysql or requires_redis or requires_docker"` (the
OPPOSITE of tier 1's filter).

## Tier-3 (E2E) Contract — MUST Rules

### 1. Production scenario coverage

E2E tests exercise full user journeys across multiple services.
They MAY use Playwright for UI, real auth providers, real
storage backends.

### 2. NO MOCKING (same as tier 2)

### 3. Performance budget

Suite MUST complete in <30 min on a healthy environment.
Individual tests <5 min.

## CI Gate Strategy (per package)

Each package SHOULD have three CI gates, layered:

1. **Unit gate (tier 1)** — fires on every PR touching the
   package. <2 min. Clean `[dev]`-only venv. No marker overrides.
   This is the gate #898 / PR #968 / #979 establish for DataFlow.
2. **Integration gate (tier 2)** — fires on PRs touching the
   package AND on every push to main. Real infra. <15 min.
3. **E2E gate (tier 3)** — fires on push to main and on
   release branches. Full stack. <30 min.

The unit gate MUST pass before the integration gate runs (CI
dependency). The integration gate MUST pass before the E2E gate.

## Spec drift detection

Files that violate this spec are detectable via mechanical sweep:

```bash
# Bare top-imports of integration deps in tier 1
grep -rn 'import asyncpg\|import psycopg\|import motor' tests/unit/ \
  | grep -v 'importorskip'

# Ad-hoc DataFlow instantiation in tier 1
grep -rn 'DataFlow(.*sqlite:///' tests/unit/  # should be near-zero
grep -rn 'DataFlow(.*postgresql://' tests/unit/  # MUST be zero

# IntegrationTestSuite in tier 1 (always wrong)
grep -rn 'IntegrationTestSuite\|from tests.infrastructure' tests/unit/

# tempfile DB paths in tier 1
grep -rn 'tempfile\.mktemp\|tempfile\.NamedTemporaryFile.*\.db' tests/unit/
```

The `spec-drift-gate.md` infrastructure runs these sweeps as a
pre-commit + CI check. New violations BLOCK merge.

## Brief traceability (per `rules/specs-authority.md` MUST Rule 7)

Per `workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md`,
every brief requirement maps to a clause here:

- Layer A (plugins / timeout) → § Tier-1 Contract Rule 6
- Layer B (`test_example_gallery` deadlock) → § Tier-1 Contract Rule 2
- Layer C (`fabric/` imports) → § Tier-1 Contract Rule 1
- Layer D (PG-requiring tests) → § Tier-1 Contract Rule 1 + Rule 3
- Layer E (OOM / events) → § Tier-1 Contract Rule 5 + Rule 6
- AC#7 (re-apply gate) → § CI Gate Strategy

## Open spec areas (for future /codify)

- Performance benchmark suite (currently spread across `testing/test_*_performance*.py`) needs its own tier? Likely tier 2 — they shouldn't run on every unit-tier PR. Add to a `testing-performance.md` spec or expand this file.
- Cross-package smoke tests (currently in `tests/cross_sdk/`) need tier definition. Likely tier 3.
