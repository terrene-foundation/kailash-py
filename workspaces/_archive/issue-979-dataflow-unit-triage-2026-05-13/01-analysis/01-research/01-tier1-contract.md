# Tier-1 (Unit) Test Contract — Canonical Source

Source: `packages/kailash-dataflow/tests/unit/CLAUDE.md`
(institutional, authored alongside the unit suite)

## What MUST hold for every `tests/unit/` file

1. **No external infrastructure at import or run time.**
   - SQLite (`:memory:` or file-based) allowed
   - Mocks / stubs for external services allowed
   - PostgreSQL connections BLOCKED (move to `tests/integration/`)
   - MySQL / Redis / Mongo BLOCKED at module top

2. **Standardized fixtures, never ad-hoc connections.**
   - Use `memory_dataflow` for DataFlow-instance tests
   - Use `memory_test_suite` for direct SQLite connections
   - Use `file_dataflow` / `file_test_suite` only when persistence
     across operations within ONE test is required
   - NEVER `tempfile.NamedTemporaryFile` / `tempfile.mktemp()`
     for DB paths
   - NEVER hardcode connection strings

3. **Mocking discipline.**
   - Mock external services (HTTP, APIs, external systems)
   - Do NOT mock SQLite (use real SQLite)
   - Use provided mocks (`mock_migration_executor`,
     `mock_connection_manager`, etc.)

4. **Test isolation.**
   - Each test independent, no shared state
   - Trust fixtures for cleanup
   - No order-dependent assertions

5. **Marker auto-application.**
   - All `tests/unit/` files implicitly carry `@pytest.mark.unit`
   - Fixture use auto-applies `sqlite_memory` / `sqlite_file` /
     `mocking` markers

6. **Performance budget.**
   - Tier-1 contract is conventionally **<10s per test** and
     the **whole suite in <2 min** on a clean `[dev]`-only
     install. (PR #977 cited 3000+ tests OOMing the
     ubuntu-latest 7GB at 22s — that violates the suite-level
     budget too.)

## Available fixtures (from `tests/unit/conftest.py`)

| Fixture                    | Yields                                    | Use when                                      |
| -------------------------- | ----------------------------------------- | --------------------------------------------- |
| `memory_dataflow`          | DataFlow w/ in-memory SQLite              | DataFlow API tests (most common)              |
| `file_dataflow`            | DataFlow w/ file SQLite                   | Tests requiring persistence across operations |
| `auto_migrate_dataflow`    | DataFlow with `auto_migrate=True`         | Tests of migration triggering only            |
| `memory_test_suite`        | Suite handle (raw SQLite conn)            | Direct-SQL operations without DataFlow facade |
| `file_test_suite`          | Suite handle (raw SQLite, file)           | Direct-SQL with persistence                   |
| `sqlite_memory_connection` | aiosqlite conn directly                   | Lowest-level SQLite                           |
| `basic_test_table`         | Table name (pre-seeded Alice/Bob/Charlie) | Tests needing canned starter data             |
| `mock_connection_manager`  | Mock                                      | External-pool-shape behaviour tests           |
| `mock_migration_executor`  | Mock                                      | Migration logic without real DDL              |
| `mock_dataflow_engine`     | Mock                                      | Engine-shape behaviour tests                  |

## Why `memory_dataflow` matters here

The `tests/unit/conftest.py:75` docstring is unusually explicit:

> Yields+closes per rules/testing.md § "Fixtures Yield + Cleanup,
> Never Return". Without explicit close() the DataFlow is released
> to GC, whose finalizer would previously run async_safe_run()
> inside `__del__` and interleave with subsequent fixture setup —
> the deadlock that hung the unit suite (see engine.py **del**
> commit).

This is the EXACT bug class PR #968's gate kept rediscovering:
ad-hoc DataFlow instantiation (`DataFlow(DB_URL)`) without a
yield+close fixture caused the `__del__` deadlock that produced
15-minute hangs. The fix is institutional — the `memory_dataflow`
fixture solves it once for all tests.

## Implication for #979

The fix is NOT mostly "tighten markers" or "skip a few PG tests."
The fix is **align every unit-tier DataFlow instantiation with the
documented fixture pattern AND audit the suite for direct
external-infra imports**. Files that need real PG / fabric deps /
real `AsyncLocalRuntime` are misclassified — they belong in
`tests/integration/`, not `tests/unit/`. The CLAUDE.md contract
calls this out explicitly; the suite has drifted from its own spec.
