# IntegrationTestSuite Harness Contract — Migration Reference

**Scope:** kailash-dataflow tier-2 mock → real-infra rewrite (issue #992 / issue #979 B15)
**Source of truth:** `packages/kailash-dataflow/tests/infrastructure/test_harness.py` (521 lines)
**Companion docs:** `packages/kailash-dataflow/tests/CLAUDE.md` (test-suite policy), `packages/kailash-dataflow/tests/integration/conftest.py` (autouse fixtures + NO MOCKING gate), `packages/kailash-dataflow/pytest.ini` (markers + addopts + asyncio config)

This document captures the **public API surface** of the harness as test authors will encounter it when rewriting mock-based tier-2 tests against real PostgreSQL. Every symbol cited is grounded in `file:line` from the harness source unless explicitly marked as policy from CLAUDE.md.

---

## 1. API surface

### 1.1 Classes exported

All classes live in `tests/infrastructure/test_harness.py` and are imported by test files via `from tests.infrastructure.test_harness import IntegrationTestSuite` (the canonical entry point — see `tests/CLAUDE.md` § "CRITICAL: For Claude Code — Always Use IntegrationTestSuite").

| Class                               | Lines       | Role                                                                                                    |
| ----------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------- |
| `DatabaseConfig` (`@dataclass`)     | 33-68       | Centralized DB config; `from_environment()` builds from env vars                                        |
| `DatabaseInfrastructure`            | 71-131      | Owns the asyncpg connection pool; verifies connectivity at init                                         |
| `TableFactory`                      | 134-270     | Creates standardized test tables with deterministic schemas + auto-cleanup                              |
| `NotNullTestHarness`                | 273-350     | Specialized harness for NOT NULL column-addition tests                                                  |
| `StandardConnectionManager`         | 353-369     | Single-connection wrapper compatible with `NotNullColumnHandler`                                        |
| `DataFlowTestHarness`               | 372-410     | Creates `DataFlow` instances against the shared test DB and tracks them for pool cleanup                |
| **`IntegrationTestSuite`**          | **413-449** | **The canonical fixture cited in `specs/testing-tiers.md` § Tier-2 Rule 2. Composes all of the above.** |
| `PerformanceMetrics` (`@dataclass`) | 455-468     | Records `operation`, `duration`, `rows_affected`, `throughput`                                          |
| `PerformanceMeasurement` (static)   | 471-500     | `assert_performance_bounds` + `assert_throughput_minimum` helpers                                       |

Module-level decorators:

| Decorator                                               | Lines   | Effect                                                                                                                       |
| ------------------------------------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `requires_postgres(test_func)`                          | 506-510 | Currently aliases `pytest.mark.integration` (note: the name is descriptive but the implementation simply tags `integration`) |
| `performance_test(timeout_seconds=30, max_rows=100000)` | 513-520 | Stacks `pytest.mark.timeout(...)` + `pytest.mark.performance`                                                                |

### 1.2 Public methods + signatures

#### `IntegrationTestSuite` (the load-bearing class)

```python
class IntegrationTestSuite:
    def __init__(self, config: Optional[DatabaseConfig] = None)               # line 416
    async def initialize(self) -> None                                         # line 422
    async def cleanup(self) -> None                                            # line 427
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[IntegrationTestSuite, None]      # line 434
    def get_connection(self) -> AsyncContextManager[asyncpg.Connection]        # line 443
```

Composed attributes (all set in `__init__`):

- `self.config: DatabaseConfig` — DB URL + connection params (line 417)
- `self.infrastructure: DatabaseInfrastructure` — pool owner (line 418)
- `self.not_null_harness: NotNullTestHarness` — NOT NULL specialization (line 419)
- `self.dataflow_harness: DataFlowTestHarness` — DataFlow factory + tracker (line 420)

**Critical:** `IntegrationTestSuite` does **not** expose a top-level `clean_database()` method despite the `tests/CLAUDE.md` example referring to one — that method is documented as part of "Standard Fixtures" (CLAUDE.md § 5) but is NOT in the harness source. Tests that need DB reset use per-test table-name UUIDs + the per-test connection-pool cleanup autouse fixture in `tests/conftest.py:985-1083` instead.

#### `DatabaseInfrastructure`

```python
class DatabaseInfrastructure:
    def __init__(self, config: DatabaseConfig)                                 # line 74
    async def initialize(self) -> None                                          # line 79
    async def get_connection(self) -> asyncpg.Connection                       # line 112
    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[asyncpg.Connection, None]     # line 118
    async def cleanup(self) -> None                                            # line 126
```

Pool sizing (set in `initialize()`, lines 99-105):

- `min_size=1`, `max_size=5` — intentionally conservative for test isolation
- `command_timeout=30s`
- `max_inactive_connection_lifetime=3.0s` (aggressive recycling)

#### `TableFactory`

```python
class TableFactory:
    def __init__(self, infrastructure: DatabaseInfrastructure)                 # line 137
    def generate_unique_name(self, prefix: str = "test") -> str                # line 141 — microsecond-suffixed
    async def create_basic_table(self, name: Optional[str] = None) -> str     # line 145
    async def create_constrained_table(self) -> Dict[str, str]                # line 174 — returns {"main_table", "category_table"}
    async def create_large_table(self, rows: int = 10000) -> str              # line 225
    async def cleanup_all(self) -> None                                        # line 255 — drops in reverse order
```

#### `DataFlowTestHarness`

```python
class DataFlowTestHarness:
    def __init__(self, infrastructure: DatabaseInfrastructure)                 # line 375
    def create_dataflow(self, **kwargs) -> DataFlow                            # line 380
    async def cleanup(self) -> None                                            # line 391
```

`create_dataflow` defaults (line 382-386): `auto_migrate=False`, `existing_schema_mode=True`. Passing kwargs overrides either. Every DataFlow instance is tracked and closed at `cleanup()` via `close_all_pools()` / `cleanup()` on the connection manager.

### 1.3 Fixtures (scoping)

Fixtures live in `packages/kailash-dataflow/tests/integration/conftest.py`. The harness module itself does NOT define pytest fixtures — it provides the classes that fixtures wrap.

| Fixture                         | Scope                 | Source                                  | Yields                                                                                                                        |
| ------------------------------- | --------------------- | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `test_suite`                    | function              | `tests/integration/conftest.py:304-318` | `IntegrationTestSuite` already inside `async with suite.session()`                                                            |
| `memory_test_suite`             | function              | `conftest.py:322-337`                   | SQLite-memory variant (`UnitTestSuite` from `tests/fixtures/unit_test_harness.py`) — for error-shape tests that don't need PG |
| `memory_dataflow`               | function              | `conftest.py:340-351`                   | `DataFlow` against `memory_test_suite` (sqlite memory); explicit `close_async()` on teardown                                  |
| `test_database_config`          | session               | `conftest.py:170-192`                   | `dict` with `url`, `type`, `host`, `port`, `user`, `password`, `database`                                                     |
| `db_url`                        | session               | `conftest.py:195-198`                   | DB URL string                                                                                                                 |
| `shared_connection_pool`        | function              | `conftest.py:201-227`                   | `asyncpg.Pool` (size 1-5) — used by `postgres_connection`                                                                     |
| `postgres_connection`           | function              | `conftest.py:230-234`                   | A single `asyncpg.Connection` borrowed from the pool                                                                          |
| `connection_manager`            | function              | `conftest.py:256-261`                   | `DatabaseConnectionManager` for NOT NULL tests                                                                                |
| `unique_table_name`             | function              | `conftest.py:264-267`                   | microsecond-suffixed string                                                                                                   |
| `clean_test_table`              | function              | `conftest.py:270-300`                   | Creates basic 4-column table + 3 seed rows, drops after                                                                       |
| `test_table_with_constraints`   | function              | `conftest.py:354-406`                   | `{"main_table", "category_table"}` with FK + check constraints                                                                |
| `large_test_table`              | function              | `conftest.py:409-439`                   | 10K-row table for performance tests                                                                                           |
| `no_mocking_policy_integration` | function, **autouse** | `conftest.py:148-167`                   | Tier-2 NO MOCKING runtime guard                                                                                               |

The root conftest (`packages/kailash-dataflow/tests/conftest.py`) adds two **function-scoped autouse fixtures** that apply to every test (unit + integration + e2e):

- `event_loop` (lines 181-203) — fresh event loop per test, cancels pending tasks on teardown
- `cleanup_dataflow_connection_pools` (lines 985-1083) — **critical** fix for `SDK-CORE-2025-001`: terminates every `AsyncSQLDatabaseNode._shared_pools` entry after each test so the next test's fresh event loop does not reuse a pool bound to the closed loop

### 1.4 Cleanup contract (yield + teardown)

`IntegrationTestSuite.session()` (lines 434-441) is the canonical lifecycle:

```python
@asynccontextmanager
async def session(self):
    await self.initialize()
    try:
        yield self
    finally:
        await self.cleanup()
```

`cleanup()` (lines 427-432) runs in dependency order:

1. `not_null_harness.cleanup()` — closes lazily-opened connections + drops NOT NULL test tables
2. `dataflow_harness.cleanup()` — closes every tracked `DataFlow` instance's pool + drops the harness's tables
3. `infrastructure.cleanup()` — closes the asyncpg pool

Guarantees the migration author can rely on:

- Every table created via `TableFactory.create_*` is dropped after the test (`cleanup_all`, lines 255-270, drops in reverse insertion order with `CASCADE`).
- Every `DataFlow` constructed via `DataFlowTestHarness.create_dataflow(...)` has its connection pool closed (`close_all_pools` / `cleanup` on the connection manager, lines 394-408).
- The asyncpg pool itself is closed in `DatabaseInfrastructure.cleanup()` (lines 128-131).
- The session-level autouse `cleanup_dataflow_connection_pools` (root conftest 985-1083) sweeps any stragglers from `AsyncSQLDatabaseNode._shared_pools` even if a test forgets explicit cleanup — this is the safety net for the event-loop mismatch bug.

What is NOT guaranteed:

- The harness does NOT truncate / drop application-level tables created by `DataFlow.auto_migrate=True` outside `TableFactory`. Tests that enable `auto_migrate` must either use unique table names per test (UUID suffix pattern in `test_classification_mutation_return.py:64-67`) or explicitly drop in their own `finally` blocks (see `test_issue_480_express_pg_identifier_quoting.py:42-73`).

---

## 2. Required environment

### 2.1 Env vars (read by `DatabaseConfig.from_environment()`, lines 46-68)

| Var                 | Default         | Effect                                             |
| ------------------- | --------------- | -------------------------------------------------- |
| `TEST_DATABASE_URL` | unset           | If set, overrides everything else; `type="custom"` |
| `DB_HOST`           | `localhost`     | PostgreSQL host                                    |
| `DB_PORT`           | `5434`          | **SDK-standard shared test port**                  |
| `DB_USER`           | `test_user`     |                                                    |
| `DB_PASSWORD`       | `test_password` |                                                    |
| `DB_NAME`           | `kailash_test`  |                                                    |

The composed URL is `postgresql://{user}:{password}@{host}:{port}/{database}` (line 58). The `type="postgresql"` field on the resulting `DatabaseConfig` is the canonical signal that real PostgreSQL is in scope.

### 2.2 Docker / container expectations

`tests/CLAUDE.md` § 3 mandates: "All tests use the shared PostgreSQL on port **5434** via IntegrationTestSuite". This is the kailash-py monorepo shared SDK Docker infrastructure (port 5434 is the port used across `kailash-dataflow`, `kailash-nexus`, `kailash-kaizen` integration tests).

There is no docker-compose file referenced by the harness itself — the port + credentials are coded as defaults, and the assumption is that `docker compose up` for the SDK test infrastructure is already running before `pytest tests/integration/` is invoked.

### 2.3 Skip behavior when infrastructure is absent

`DatabaseInfrastructure.initialize()` (lines 85-95) calls `await asyncpg.connect(...)` and on any exception raises `ConnectionError("Cannot connect to test database: {e}. Ensure PostgreSQL is running on port {self.config.port}")`. The harness itself does NOT `pytest.skip` — it raises and the test errors out.

Skip handling is in the **conftest layer**, not the harness layer:

- `shared_connection_pool` (`conftest.py:201-227`) wraps the same connection probe in `try / except` and calls `pytest.skip(f"Cannot connect to test database: {e}. Ensure PostgreSQL is running on port {test_database_config.get('port', 5434)}")` when the pool cannot be created.
- The `test_suite` fixture does NOT have its own skip wrapper — if Postgres is down, `await suite.session().__aenter__()` raises `ConnectionError` and the test fails (not skips). Migration authors who want graceful skip behavior on missing infra should follow the `shared_connection_pool` pattern OR rely on `pytest.ini`'s `addopts = -m "not (requires_postgres or requires_mysql or requires_redis or requires_docker)"` to filter out the tier-2 tests when running locally without Docker.

### 2.4 Marker filtering interaction

`pytest.ini` at `packages/kailash-dataflow/pytest.ini:44-48` declares:

```ini
addopts =
    -v
    --strict-markers
    --tb=short
    -m "not (requires_postgres or requires_mysql or requires_redis or requires_docker)"
```

This means: by default, `pytest` in this package SKIPS any test tagged `@pytest.mark.requires_postgres` etc. Tier-2 tests using `IntegrationTestSuite` are typically marked `@pytest.mark.integration` (which IS collected by default) and only opt into `requires_postgres` if the migration author wants the test gated behind explicit invocation. **Recommendation for migration:** mark new tier-2 tests with `@pytest.mark.integration` so they run by default; reserve `requires_postgres` for tests that should ONLY run in environments where the marker is explicitly enabled (CI matrix jobs, etc.).

---

## 3. Idiomatic usage

The canonical pattern from `tests/CLAUDE.md` § "Standard Fixtures" + reproduced in every integration test file:

### Pattern A — Local `test_suite` fixture per test file

This is the most common form in the repo (~30 files). Each test file defines its own `test_suite` fixture, but with the **shared conftest fixture at `tests/integration/conftest.py:304-318` already providing it globally**, new tests in `tests/integration/` can drop the local definition.

```python
# packages/kailash-dataflow/tests/integration/test_issue_480_express_pg_identifier_quoting.py
# lines 31-39, 76-119
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create the standard integration test suite against real PostgreSQL."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.integration
@pytest.mark.regression
@pytest.mark.timeout(30)
class TestIssue480ExpressPostgresIdentifierQuoting:
    async def test_issue_480_exact_reproduction_from_issue_body(
        self, test_suite, _clean_tables
    ):
        db = DataFlow(test_suite.config.url, auto_migrate=True, pool_size=2)

        @db.model
        class Issue480Item:
            __tablename__ = "issue480_items"
            id: str
            name: str

        await db.initialize()

        rid = f"x-{uuid.uuid4().hex[:8]}"
        created = await db.express.create("Issue480Item", {"id": rid, "name": "test"})
        assert created["id"] == rid
        assert created["name"] == "test"

        # State-persistence read-back — mandatory by rules/testing.md.
        fetched = await db.express.read("Issue480Item", rid)
        assert fetched is not None
        assert fetched["id"] == rid
```

Key idioms in this example:

1. Test class is decorated `@pytest.mark.integration` + `@pytest.mark.timeout(30)` — required by `testing.md` and `pytest.ini` budget.
2. `DataFlow(test_suite.config.url, ...)` — the URL is the ONLY thing pulled from the suite.
3. Per-test unique table name via `auto_migrate=True` + uniquely-named `__tablename__` (or UUID-derived row IDs to avoid collisions even with shared tables).
4. **Read-back assertion** after every write (`testing.md` § "State Persistence Verification").

### Pattern B — Classified field / clearance redaction test

```python
# packages/kailash-dataflow/tests/integration/security/test_classification_mutation_return.py
# lines 45-138 (abridged to load-bearing parts)
from tests.infrastructure.test_harness import IntegrationTestSuite

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def test_suite():
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def unique_model_name() -> str:
    return f"Doc{uuid.uuid4().hex[:10]}"


def _make_db_with_named_pii_model(db_url: str, model_name: str) -> DataFlow:
    db = DataFlow(db_url, auto_migrate=True, pool_size=2, max_overflow=2)
    cls = type(model_name, (), {
        "__annotations__": {"id": int, "title": str, "body": str},
        "id": 0, "title": "", "body": "",
    })
    cls = classify("body", DataClassification.PII, masking=MaskingStrategy.REDACT)(cls)
    db.model(cls)
    return db


async def test_create_redacts_classified_field_for_public_caller(
    test_suite, unique_model_name
):
    db = _make_db_with_named_pii_model(test_suite.config.url, unique_model_name)
    try:
        await db.initialize()
        returned = await db.express.create(
            unique_model_name, {"title": "public-title", "body": "leak-me"},
        )
        assert returned["body"] == "[REDACTED]"
    finally:
        db.close()
```

Key idioms:

1. `pytestmark = [pytest.mark.integration, pytest.mark.asyncio]` at module level — both markers apply to every test.
2. **Per-test `unique_model_name` UUID** so the 9 tests in the file each get an isolated model registration (avoids registry collisions when multiple `DataFlow` instances share one test DB).
3. **Small pool sizes** (`pool_size=2, max_overflow=2`) — the file comment at line 79 explicitly cites the reason: with 9 independent `DataFlow` instances, default pool sizes would saturate the test PostgreSQL's `max_connections` budget.
4. Explicit `try / finally: db.close()` — the harness's `dataflow_harness.cleanup()` only tracks instances built via `harness.create_dataflow(...)`, NOT instances built directly from `DataFlow(test_suite.config.url, ...)`. Authors who construct DataFlow directly own the close.

### Pattern C — BP-049 wiring test (real classified PK + cache + audit)

`packages/kailash-dataflow/tests/integration/security/test_bp_049_classification_leaks_wiring.py` (lines 35-44) cites:

> Each test:
>
> 1. Constructs a real `DataFlow` against PostgreSQL via the shared `IntegrationTestSuite` fixture.
> 2. Registers a model with a classified PK (`DataClassification.PII` on `id`).
> 3. Exercises the production hot path.
> 4. Asserts the externally-observable surface (event payload, cache key, validation error) does NOT contain the raw PK value.

This is the **canonical Tier-2 redaction-pattern shape** for migration: real DB + real DataFlow + real classification policy + assertion against the externally-observable surface (NOT against an internal mock call count).

---

## 4. Anti-patterns / gotchas

### 4.1 NO MOCKING gate at collection time

`tests/integration/conftest.py:120-145` (`pytest_collectstart`) parses every test module via `ast.parse()` and **fails collection** if it sees any of:

- `from unittest.mock import Mock | MagicMock | AsyncMock | patch | PropertyMock | seal | create_autospec | NonCallableMock | NonCallableMagicMock | patch.object | patch.dict | patch.multiple` — the "mocking primitives" set (lines 35-50).
- `from unittest import mock` — bare-module rebind also blocked (lines 106-109).
- `import unittest.mock` / `import unittest.mock as m` — same reason (lines 110-116).

**Whitelisted non-primitive helpers** (lines 57-65) — these DO NOT trigger the gate: `ANY`, `sentinel`, `DEFAULT`, `call`, `mock_open`. They are stdlib equality-matcher helpers, not test-double constructors.

**Migration gotcha:** if the original mock-based test used `@patch("...")` or `MagicMock()`, the rewrite MUST remove those imports entirely. Leaving even one `from unittest.mock import patch` line in the rewritten file fails collection with `NO MOCKING POLICY VIOLATION (Tier 2): ... imports unittest.mock`.

### 4.2 Async lifecycle ordering — `initialize()` must precede `express.*`

`DataFlow.__init__` does NOT open the connection pool. The pool is created in `await db.initialize()`. Calling `await db.express.create(...)` before `initialize()` raises an opaque pool-not-ready error.

```python
# DO
db = DataFlow(test_suite.config.url, auto_migrate=True)
await db.initialize()
await db.express.create("Model", {...})

# DO NOT
db = DataFlow(test_suite.config.url, auto_migrate=True)
await db.express.create("Model", {...})  # raises — pool not initialized
```

### 4.3 Schema setup ordering — `auto_migrate=True` is post-`@db.model`

The `@db.model` decorator only registers a model with the framework. Schema DDL is emitted on `initialize()` IF `auto_migrate=True`. Order matters:

```python
# DO
db = DataFlow(url, auto_migrate=True)
@db.model
class Item: ...
await db.initialize()  # NOW migrations + table creation run

# DO NOT
db = DataFlow(url, auto_migrate=True)
await db.initialize()  # no tables yet
@db.model
class Item: ...  # table never created
```

### 4.4 Multiple `DataFlow` instances in one test — connection-pool exhaustion

The test PostgreSQL on port 5434 has a finite `max_connections`. The harness's pool (`max_size=5`) plus N user-created `DataFlow` instances each with default `pool_size=10` saturates fast.

**Mitigation pattern** (from `test_classification_mutation_return.py:81-86`):

```python
db = DataFlow(
    test_suite.config.url,
    auto_migrate=True,
    pool_size=2,        # was: default 10
    max_overflow=2,     # was: default 5
)
```

### 4.5 Model registry collisions across tests

If two tests register a class named `Document` against the same DataFlow framework registry, the second registration may overwrite or error. The repo standard is **per-test UUID-suffixed model names** built via `type(model_name, (), {...})` (see `_make_db_with_named_pii_model` in `test_classification_mutation_return.py:69-107`).

### 4.6 Direct `DataFlow(...)` construction bypasses harness tracking

`DataFlowTestHarness.create_dataflow()` tracks instances in `self._dataflow_instances` for batch cleanup. `DataFlow(test_suite.config.url, ...)` directly does NOT. Migration tests that construct DataFlow directly own the `db.close()` call in a `finally` block.

### 4.7 Event loop reuse across tests

Without the autouse `cleanup_dataflow_connection_pools` fixture (`tests/conftest.py:985-1083`), pools cached at `AsyncSQLDatabaseNode._shared_pools` (class-level) leak from test to test and bind to the closed event loop. The fixture closes and clears them after each test. Migration authors do NOT need to invoke this manually — it is autouse — but should be aware that ignoring `asyncpg.pool` warnings during cleanup is intentional.

### 4.8 Multi-DB isolation

The harness supports PostgreSQL only. The SQLite-memory variant (`memory_test_suite` / `memory_dataflow`) lives in `tests/fixtures/unit_test_harness.py` and is **unit-tier** semantically — it is exposed at the integration tier as a convenience for error-shape tests, not as a real-infra substitute. Migration tests in scope for real-infra MUST use `test_suite`, not `memory_test_suite`.

### 4.9 `clean_database()` does not exist on the suite

The `tests/CLAUDE.md` example at line 11 references `test_suite.clean_database()`. This method is **NOT** in the harness source (verified by reading lines 413-449 of `test_harness.py`). The repo standard is per-test table-name UUIDs + autouse pool-cleanup, NOT a suite-level clean call. Migration authors quoting that example need to substitute either:

- Per-test `unique_table_name` fixture (`conftest.py:264-267`), OR
- Explicit `_clean_tables` fixture pattern (`test_issue_480_*.py:42-73`).

---

## 5. Markers

### 5.1 Markers used by tier-2 tests

Declared in `packages/kailash-dataflow/pytest.ini:14-36`:

| Marker              | Tier-2 use                                                                                                                                                                                                 |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `integration`       | **Primary tier-2 marker.** Applied to every test class / module using `IntegrationTestSuite`. Not filtered by `addopts`.                                                                                   |
| `tier2`             | Equivalent alias for `integration`.                                                                                                                                                                        |
| `requires_postgres` | Test requires PostgreSQL. **Filtered out by default** via `pytest.ini` `addopts` (line 48).                                                                                                                |
| `requires_docker`   | Test requires Docker services. **Filtered out by default.**                                                                                                                                                |
| `regression`        | Bug regression test (never deleted per `rules/testing.md`).                                                                                                                                                |
| `bug_reproduction`  | Minimal failing example.                                                                                                                                                                                   |
| `bug_investigation` | Hypothesis-validation test.                                                                                                                                                                                |
| `timeout(N)`        | Per-test timeout. Default for the file is `pytest.ini` `timeout = 120` (line 54). Many tier-2 tests override with `@pytest.mark.timeout(30)`.                                                              |
| `asyncio`           | Async support. `pytest.ini` sets `asyncio_mode = auto` (line 58) so most tests don't need an explicit marker, but `pytestmark = [pytest.mark.integration, pytest.mark.asyncio]` is a common explicit form. |

### 5.2 The default-skip interaction

`pytest.ini:44-48` declares:

```ini
addopts =
    ...
    -m "not (requires_postgres or requires_mysql or requires_redis or requires_docker)"
```

This means: by default, `pytest tests/integration/` SKIPS any test tagged with any of those four "requires\_\*" markers. Tier-2 tests using `IntegrationTestSuite` typically get tagged `@pytest.mark.integration` (which IS collected by default) and AVOID the `requires_postgres` marker so they run on every developer's machine where Docker port 5434 is up.

**Recommendation for migration:**

1. Mark every rewritten tier-2 test with `@pytest.mark.integration` — required.
2. Add `@pytest.mark.timeout(30)` at module / class level to enforce a tighter budget than the global 120s.
3. **Do NOT** add `@pytest.mark.requires_postgres` unless the test should ONLY run in CI matrix jobs that explicitly opt into PG. The infrastructure dependency is already implicit via `IntegrationTestSuite` — the marker is redundant and triggers the default-filter exclusion.
4. If the rewritten test is a bug regression, add `@pytest.mark.regression` (and place the file under `tests/regression/test_issue_*.py` if it traces to a specific GitHub issue).
5. Module-level `pytestmark = [pytest.mark.integration, pytest.mark.asyncio]` is the most concise form when every test in the file shares the same markers (see `test_classification_mutation_return.py:47`).

### 5.3 Strict markers

`pytest.ini:46` declares `--strict-markers`. Any marker used but not declared in `pytest.ini:14-36` fails collection with `PytestUnknownMarkWarning` upgraded to error. Migration authors introducing new markers MUST register them in `pytest.ini` in the same PR (cross-reference: `testing.md` § "MUST: Pytest Plugin + Marker Declaration Pair").

---

## Appendix: file:line citation summary

All citations are absolute paths from kailash-py repo root.

- Harness source: `packages/kailash-dataflow/tests/infrastructure/test_harness.py` (521 lines)
- Integration conftest (autouse + shared fixtures): `packages/kailash-dataflow/tests/integration/conftest.py` (461 lines)
- Root conftest (event loop + pool cleanup): `packages/kailash-dataflow/tests/conftest.py` (1083 lines)
- Test-suite policy: `packages/kailash-dataflow/tests/CLAUDE.md`
- Marker + addopts config: `packages/kailash-dataflow/pytest.ini` (80 lines)
- Pattern A example: `packages/kailash-dataflow/tests/integration/test_issue_480_express_pg_identifier_quoting.py:31-119`
- Pattern B example: `packages/kailash-dataflow/tests/integration/security/test_classification_mutation_return.py:45-200`
- Pattern C example: `packages/kailash-dataflow/tests/integration/security/test_bp_049_classification_leaks_wiring.py:1-60`
