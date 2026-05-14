# S4 — Category C audit decisions

Date: 2026-05-14
Branch: `feat/issue-979-s4-pg-audit`
Commits: `891d6a91` (Cat B gate), `1581992f` (Cat A 12 moves)

## Context

The Shard S4 plan called for a per-file audit of 8 tier-1 files that have a
"Layer D" smell (PG-port URL strings, AsyncLocalRuntime import, real-DataFlow
construction). For each file the decision is MOVE-to-integration vs
SQLite-sentinel refactor vs KEEP-AS-IS based on whether the test actually
opens a PG connection. Layer B (workflow-runtime) imports are out of S4's
scope per the brief — S4 closes the Layer-D-only failure mode.

The 3 explicitly named files are documented below plus 5 nearby tier-1 files
that surfaced in the same `grep` sweep.

## File-by-file decisions

| File | PG URLs | asyncpg | AsyncLocalRuntime | Mock count | Real DataFlow construction | Decision |
|---|---|---|---|---|---|---|
| `core/test_lazy_connection.py` | 7 | 0 | 0 | 0 | Yes (TEST-NET-1 192.0.2.1) | KEEP |
| `nodes/test_count_node.py` | 1 | 0 | 1 (import only) | 0 | Yes (`auto_migrate=False`) | KEEP |
| `core/test_architecture_validation.py` | 4 | 0 | 0 | 0 | Yes (config-only) | KEEP |
| `migrations/test_bug_006_safety_parameters.py` | 10 | 0 | 0 | 1 | Yes (patched ConnectionManager) | KEEP |
| `test_dataflow_bug_011_012_fixes.py` | 5 | 0 | 0 | 12 | No (fully mocked) | KEEP |
| `test_health_monitoring.py` | 2 | 0 | 0 | 19 | No (memory_dataflow fixture) | KEEP |
| `test_strict_mode_connection_validation.py` | 0 | 0 | 0 | 0 | No | KEEP |
| `core/test_model_registry_runtime_injection.py` | 0 | 0 | 4 (isinstance target) | 5 | No | KEEP |

## Rationale for each KEEP

**`test_lazy_connection.py`** — explicitly tests the lazy-connection contract.
The URL `postgresql://nonexistent:password@192.0.2.1:5432/fake_db` is TEST-NET-1
(RFC 5737) — guaranteed unreachable. Tests never call `await db.*` or
`runtime.execute`; they only construct `DataFlow(...)` and assert the
`_connected is False` / `_pending_table_creations == []` config state. Removing
this test from tier-1 would defeat the purpose of the lazy-connection contract
test, which IS a unit test of __init__ behavior.

**`test_count_node.py`** — imports `AsyncLocalRuntime` at module top but never
invokes it. Tests only call `workflow.build()` and assert node names in the
built graph. Construction uses `auto_migrate=False`, so DataFlow stores the URL
as config string and does not connect. The PG URL is purely for adapter-dialect
selection. Layer B import is out of S4 scope. Layer D: no real connection.

**`core/test_architecture_validation.py`** — pure config-shape tests. PG URLs
appear only as values in `DatabaseConfig(url="postgresql://...")` to validate
that the config dataclass accepts them. No DataFlow.connect, no runtime.execute,
no asyncpg import.

**`migrations/test_bug_006_safety_parameters.py`** — patches
`dataflow.core.engine.ConnectionManager` at module scope and constructs
DataFlow inside that patch. Real PG URL is config-only.

**`test_dataflow_bug_011_012_fixes.py`** — 12 mocks; fully isolated.

**`test_health_monitoring.py`** — uses the `memory_dataflow` SQLite fixture
per `tests/unit/CLAUDE.md`; PG URL strings are assigned to
`memory_dataflow.connection_url` purely to test the URL-parser path of the
health monitor. No real connection.

**`test_strict_mode_connection_validation.py`** — zero mocks, zero PG URLs,
zero asyncpg. Pure dataclass/validation tests.

**`core/test_model_registry_runtime_injection.py`** — uses `AsyncLocalRuntime`
only as the type argument to `isinstance()` to verify a constructor accepts
the right runtime type. No execution. Layer B import is out of S4 scope.

## Verification

After the moves in `1581992f`, the only remaining unguarded module-top
asyncpg/psycopg/motor import in `tests/unit/` was
`testing/test_tdd_support.py:16` — fixed in `891d6a91`. Re-running the
detection commands from the shard plan returns zero hits:

```bash
grep -rn 'import asyncpg\|import psycopg\|import motor' \
  packages/kailash-dataflow/tests/unit/ | grep -v importorskip
# → 0 hits

grep -rln 'IntegrationTestSuite\|from tests\.infrastructure' \
  packages/kailash-dataflow/tests/unit/
# → 0 hits (excluding CLAUDE.md prose)

grep -rln '^import asyncpg' packages/kailash-dataflow/tests/unit/
# → 0 hits
```

## Out of scope (Layer B follow-up)

`test_count_node.py` and `test_model_registry_runtime_injection.py` keep
their `AsyncLocalRuntime` imports. These are Layer B (workflow-runtime
import) concerns — they would only fail at collection if the kailash core
package itself were absent, which is impossible on any installable
configuration. A future Layer B shard could remove the unused
`AsyncLocalRuntime` import from `test_count_node.py` for hygiene, but it
is not an S4 (Layer D) blocker.

## Outcome

- Brief AC#4 satisfied: `TestImpactReporterIntegration` moved to
  `tests/integration/migrations/test_impact_reporter.py` (line 561 class)
  and `tests/integration/migration/test_impact_reporter_unit.py` (line 67).
- Brief AC#5 satisfied: zero remaining tier-1 tests that import `motor`,
  `psycopg`, or other DB drivers without an `importorskip` guard.
- `tests/unit/templates/test_saas_tenancy.py` STAYS in tier-1 as
  specified — verified 100% mocked.

## Receipt

This is the durable receipt per `rules/verify-resource-existence.md`
MUST-4 for the Category C audit decision. The audit produced zero moves
because Layer D evidence (open PG connection at runtime) was absent in
each of the 8 inspected files.
