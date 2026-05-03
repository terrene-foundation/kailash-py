# Orphan Subsystems Audit

Scope: `packages/kailash-dataflow/src/dataflow/` subsystems that the other
auditors do NOT own — `platform/`, `web/`, `semantic/`, `debug/`, `cli/`,
`compatibility/`, `performance/`, `features/` (non-bulk/express/multi-tenant/
transaction files), `trust/`, `utils/`, `tenancy/` (wiring angle), and
`core/event_stores/`.

This file is analysis-only — no code changed.

## Executive summary

The orphan subsystems collectively contain **~15,500 lines of LOC** that are
never instantiated anywhere in the `dataflow` production path, PLUS another
**~1,800 lines of live code that is pure stub pretending to be real** (five
connector/service classes returning canned `{"success": True}` dicts in place
of any database work). The audit found:

- **2 subsystems are 100% orphan** — `dataflow.trust/` (2,407 LOC) and
  `dataflow.web/` (1,958 LOC) have zero production importers. They are only
  referenced from their own tests.
- **1 subsystem is a near-complete orphan with one weak attachment** —
  `dataflow.semantic/` (1,239 LOC). Only `dataflow/nodes/semantic_memory.py`
  imports it, and `semantic_memory.py` is NOT re-exported from
  `dataflow/nodes/__init__.py`. Dead-on-arrival.
- **1 subsystem is a "coming soon" shell** — `dataflow.cli/` (2,004 LOC). The
  declared entry point (`pyproject.toml [project.scripts] dataflow =
dataflow.cli:main`) exposes `init`, `schema`, `migrate create/apply/rollback/
status` — every one of which literally prints `"coming soon..."` or
  `"Placeholder for actual implementation"`. Running `dataflow init` against a
  production database is a silent no-op.
- **1 subsystem is lies-in-code** — `dataflow.compatibility/` (1,327 LOC)
  defines a `class DataFlowConfig` built on `unittest.mock.Mock` in production
  code (`legacy_support.py:75-82`). Zero downstream importers beyond tests.
- **1 subsystem is dead-test-code** — `dataflow.performance/` (1,700 LOC)
  defines `MigrationFastPath`, `OptimizedSchemaComparator`, and
  `MigrationConnectionManager` that are ONLY imported by their own unit tests.
  `MigrationConnectionManager` is a **duplicate class name** to the live
  `dataflow/migrations/migration_connection_manager.py::MigrationConnectionManager`
  that real code actually uses.
- **1 subsystem is wired-but-stubbed** — `dataflow.utils.connection.py::
ConnectionManager` (158 LOC) is assigned as `self._connection_manager` on
  every DataFlow instance and exposed as `db.connection`, but EVERY method is a
  stub. `initialize_pool()` returns a canned dict with a `# In real
implementation, would create SQLAlchemy engine and pool` comment;
  `health_check()` returns `database_reachable=True` regardless of actual
  state; `test_connection()` does not connect.
- **3 sibling features files in `features/` are also stubs** —
  `features/multi_tenant.py::MultiTenantManager` (95 LOC) stores tenants in a
  dict with a hardcoded `"2024-01-01T00:00:00Z"` `created_at` value.
  `features/transactions.py::TransactionManager` (77 LOC) pretends to run
  transactions by flipping a dict status from `active` to `committed` without
  ever touching the database. Both are instantiated on every DataFlow instance
  and exposed as `db.tenants` and `db.transactions`. The core auditor claims
  scope over these files but this audit notes them here because they are
  structurally the same orphan-stub-as-live-service pattern as
  `utils/connection.py`.
- **1 subsystem is unsafe pseudo-live** — `dataflow.tenancy/` is only wired via
  a lazy import in `core/nodes.py:479`. The interceptor uses regex SQL rewrite
  with f-string WHERE injection (`interceptor.py:698, 715, 719, 776, 785, 807,
816`) — dialect-unsafe and fragile, but not an orphan.
- **1 subsystem is heavy but functional — with one CRITICAL security bug**.
  `dataflow.semantic/search.py:134` uses `eval()` on a value read from a DB
  column to convert an embedding string to a Python object. Combined with the
  orphan status, the code path is dead-but-dangerous — if anyone ever wires it
  up, they inherit an `eval()` on stored data.
- **1 subsystem is heavy and partially orphan** — `dataflow.debug/` (5,028
  LOC). `Inspector` (in `platform/inspector.py`) is reached via the debug
  agent CLI, but the entire `DebugAgent` class graph is effectively the agent
  equivalent of a regex-first-classifier, which violates `rules/agent-
reasoning.md`. The CLI entry `dataflow.cli.debug_agent_cli` hardcodes
  `model="gpt-4o-mini"` — `rules/env-models.md` violation.
- **1 subsystem is the "suppress the observer" landmine** —
  `dataflow.utils.suppress_warnings.py::suppress_core_sdk_warnings()` is
  called automatically at `dataflow/__init__.py:92`. It permanently downgrades
  the `kailash.nodes.base` and `kailash.resources.registry` loggers from
  WARNING to ERROR for every process that imports DataFlow. This is a direct
  violation of `rules/observability.md` MUST Rule "No silent log-level
  downgrades" — the rule calls this out as a Zero-Tolerance Rule 1 violation
  in disguise.
- **1 subsystem is mostly live** — `core/event_stores/` and the core-level
  `core/event_store.py` are instantiated by the `DataFlow.__init__` audit
  backend path (`core/engine.py:1172` for Postgres, `:1198` for SQLite). The
  `__init__.py` only re-exports `SQLiteEventStore`, leaving `PostgreSQLEventStore`
  off the public `__all__` — minor packaging defect.

Aggregate numbers (LOC counted from `wc -l` on production `.py` files only):

| Subsystem                               | Production LOC | Orphan LOC | Stub LOC | Status                                                                                      |
| --------------------------------------- | -------------- | ---------- | -------- | ------------------------------------------------------------------------------------------- |
| `platform/`                             | 9,483          | ~6,400     | ~150     | PARTIAL (studio/validation/autofix/resilience/metrics/health orphan; inspector+errors live) |
| `web/`                                  | 1,958          | 1,958      | 0        | ORPHAN                                                                                      |
| `semantic/`                             | 1,239          | 1,239      | 0        | ORPHAN (+ eval() landmine)                                                                  |
| `debug/`                                | 5,028          | ~2,500     | 0        | PARTIAL (regex-classifier agent stack, two DebugAgent classes)                              |
| `cli/`                                  | 2,004          | 0          | ~1,000   | LIVE ENTRY POINT, STUBBED COMMANDS                                                          |
| `compatibility/`                        | 1,327          | 1,327      | 75       | ORPHAN (Mock in production code)                                                            |
| `performance/`                          | 1,700          | 1,700      | 0        | ORPHAN (test-only, duplicate class name)                                                    |
| `features/derived.py`                   | 585            | 0          | 0        | LIVE                                                                                        |
| `features/retention.py`                 | 322            | 0          | 45       | LIVE but `_partition` raises NotImplemented-equivalent                                      |
| `features/multi_tenant.py`              | 94             | 0          | 94       | LIVE ENTRY, STUBBED                                                                         |
| `features/transactions.py`              | 77             | 0          | 77       | LIVE ENTRY, STUBBED                                                                         |
| `trust/`                                | 2,407          | 2,407      | 0        | ORPHAN                                                                                      |
| `utils/connection.py`                   | 158            | 0          | 158      | LIVE ENTRY, STUBBED                                                                         |
| `utils/connection_adapter.py`           | 478            | 0          | 0        | LIVE (used by migrations)                                                                   |
| `utils/suppress_warnings.py`            | 399            | 0          | 0        | LIVE, OBSERVABILITY VIOLATION                                                               |
| `tenancy/`                              | 1,566          | ~500       | 0        | PARTIAL (interceptor used via lazy import; security.py orphan)                              |
| `core/event_stores/` + `event_store.py` | 706            | 0          | 0        | LIVE                                                                                        |

There is no `features/audit.py` — the audit-integration code lives in
`core/audit_integration.py` and is out of scope for this auditor.

## Orphan module table

| Module                                         | LOC   | Instantiations (production)                                            | Production referrers                         | Verdict                                                 |
| ---------------------------------------------- | ----- | ---------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------- |
| `dataflow/web/migration_api.py`                | 1,885 | 0 (tests only)                                                         | 0                                            | **ORPHAN**                                              |
| `dataflow/web/exceptions.py`                   | 45    | 0                                                                      | `web/migration_api.py` self-ref              | **ORPHAN** (whole `web/` not imported)                  |
| `dataflow/semantic/search.py`                  | 474   | 0 (tests only, plus `nodes/semantic_memory.py`)                        | `nodes/semantic_memory.py` (NOT re-exported) | **ORPHAN**                                              |
| `dataflow/semantic/memory.py`                  | 483   | 0                                                                      | `nodes/semantic_memory.py` only              | **ORPHAN**                                              |
| `dataflow/semantic/embeddings.py`              | 262   | 0                                                                      | `nodes/semantic_memory.py` only              | **ORPHAN**                                              |
| `dataflow/trust/audit.py`                      | 675   | 0                                                                      | `trust/__init__.py` self-ref                 | **ORPHAN**                                              |
| `dataflow/trust/multi_tenant.py`               | 582   | 0                                                                      | self-ref                                     | **ORPHAN**                                              |
| `dataflow/trust/query_wrapper.py`              | 1,033 | 0                                                                      | self-ref                                     | **ORPHAN**                                              |
| `dataflow/compatibility/legacy_support.py`     | 873   | 0                                                                      | self-ref                                     | **ORPHAN** (contains production `Mock`)                 |
| `dataflow/compatibility/migration_path.py`     | 454   | 0                                                                      | `legacy_support.py` only                     | **ORPHAN**                                              |
| `dataflow/performance/migration_optimizer.py`  | 925   | 0 (tests only)                                                         | 0                                            | **ORPHAN** (+duplicate class name)                      |
| `dataflow/performance/sqlite_monitor.py`       | 775   | 0 (tests only)                                                         | 0                                            | **ORPHAN**                                              |
| `dataflow/platform/studio.py`                  | 528   | 0                                                                      | `platform/__init__.py`                       | **ORPHAN**                                              |
| `dataflow/platform/autofix.py`                 | 517   | 0                                                                      | `platform/__init__.py`, `studio.py`          | **ORPHAN**                                              |
| `dataflow/platform/validation.py`              | 494   | 0                                                                      | `platform/__init__.py`, `studio.py`          | **ORPHAN**                                              |
| `dataflow/platform/resilience.py`              | 504   | 0 (only self `circuit_breaker = CircuitBreaker(...)` example)          | 0                                            | **ORPHAN** (3rd duplicate CircuitBreaker)               |
| `dataflow/platform/health.py`                  | 389   | 0 in prod, `studio.py` only                                            | `studio.py`                                  | **ORPHAN**                                              |
| `dataflow/platform/metrics.py`                 | 241   | 0 (nodes/monitoring_integration refers to a DIFFERENT MetricsExporter) | 0                                            | **ORPHAN**                                              |
| `dataflow/tenancy/security.py`                 | 529   | 0 (tests only)                                                         | 0                                            | **ORPHAN**                                              |
| `dataflow/debug/debug_agent.py` (legacy class) | 250   | 1 (`debug/cli.py:157`)                                                 | `debug/cli.py`                               | **PARTIAL** — duplicate of `debug/agent.py::DebugAgent` |
| `dataflow/debug/cli.py` (legacy)               | 192   | 0                                                                      | 0                                            | **ORPHAN** (replaced by `cli/debug_agent_cli.py`)       |
| `dataflow/debug/solution_generator.py`         | 812   | 1 (in debug_agent.py — orphan itself)                                  | `debug_agent.py` only                        | **ORPHAN-TRANSITIVE**                                   |

## Orphan class table

| Class                                        | File:line                                | LOC       | Instantiations                                                     | Verdict                                                           |
| -------------------------------------------- | ---------------------------------------- | --------- | ------------------------------------------------------------------ | ----------------------------------------------------------------- |
| `DataFlowStudio`                             | `platform/studio.py:95`                  | ~300      | 0 prod                                                             | ORPHAN                                                            |
| `ConfigProfile`                              | `platform/studio.py:47`                  | ~40       | 0 prod                                                             | ORPHAN                                                            |
| `BuildValidator`                             | `platform/validation.py:~60`             | ~400      | 1 (`studio.py:239`)                                                | ORPHAN-transitive                                                 |
| `AutoFix`                                    | `platform/autofix.py:~40`                | ~400      | 1 (`studio.py:523`)                                                | ORPHAN-transitive                                                 |
| `HealthMonitor`                              | `platform/health.py:77`                  | ~200      | 0 prod (only `studio.py` + error catalog doc)                      | ORPHAN                                                            |
| `CircuitBreaker`                             | `platform/resilience.py:318`             | ~200      | 0 prod (self-example only)                                         | ORPHAN (3rd duplicate of same concept)                            |
| `MetricsExporter`                            | `platform/metrics.py:23`                 | ~200      | 0 prod                                                             | ORPHAN                                                            |
| `DataFlowError`                              | `platform/errors.py:89`                  | N/A       | self-ref only                                                      | ORPHAN (shadowed by `exceptions.py:121::DataFlowError`)           |
| `WebMigrationAPI`                            | `web/migration_api.py:48`                | ~1,750    | 0 prod                                                             | ORPHAN                                                            |
| `SemanticMemory`                             | `semantic/memory.py`                     | ~400      | `nodes/semantic_memory.py` (not registered in `nodes/__init__.py`) | ORPHAN                                                            |
| `VectorStore`                                | `semantic/memory.py`                     | ~150      | same as above                                                      | ORPHAN                                                            |
| `SemanticSearchEngine`                       | `semantic/search.py`                     | ~200      | same                                                               | ORPHAN                                                            |
| `HybridSearchEngine`                         | `semantic/search.py`                     | ~200      | same                                                               | ORPHAN                                                            |
| `OllamaEmbeddings`                           | `semantic/embeddings.py:177`             | ~80       | same                                                               | ORPHAN                                                            |
| `OpenAIEmbeddings`                           | `semantic/embeddings.py:83`              | ~80       | same                                                               | ORPHAN (+ hardcoded model name violates `env-models.md`)          |
| `TrustAwareQueryExecutor`                    | `trust/query_wrapper.py`                 | ~500      | 0 prod                                                             | ORPHAN                                                            |
| `ConstraintEnvelopeWrapper`                  | `trust/query_wrapper.py`                 | ~200      | self-ref only                                                      | ORPHAN                                                            |
| `DataFlowAuditStore`                         | `trust/audit.py`                         | ~350      | 0 prod                                                             | ORPHAN                                                            |
| `SignedAuditRecord`                          | `trust/audit.py`                         | ~150      | self-ref only                                                      | ORPHAN                                                            |
| `TenantTrustManager`                         | `trust/multi_tenant.py:256`              | ~300      | 0 prod                                                             | ORPHAN                                                            |
| `CrossTenantDelegation`                      | `trust/multi_tenant.py`                  | ~100      | self-ref only                                                      | ORPHAN                                                            |
| `LegacyAPICompatibility`                     | `compatibility/legacy_support.py:85`     | ~600      | 0 prod                                                             | ORPHAN                                                            |
| `MigrationPathTester`                        | `compatibility/migration_path.py`        | ~300      | 0 prod                                                             | ORPHAN                                                            |
| `DataFlowConfig` (compatibility Mock)        | `compatibility/legacy_support.py:75`     | ~10       | self-ref only                                                      | **ORPHAN AND PRODUCTION MOCK**                                    |
| `MigrationFastPath`                          | `performance/migration_optimizer.py:108` | ~280      | 0 prod                                                             | ORPHAN                                                            |
| `OptimizedSchemaComparator`                  | `performance/migration_optimizer.py:391` | ~290      | 0 prod                                                             | ORPHAN                                                            |
| `MigrationConnectionManager`                 | `performance/migration_optimizer.py:685` | ~240      | 0 prod                                                             | ORPHAN + **DUPLICATE CLASS NAME**                                 |
| `SqliteMonitor` / `SQLitePerformanceMonitor` | `performance/sqlite_monitor.py`          | 775 total | 0 prod                                                             | ORPHAN                                                            |
| `TenantSecurityManager`                      | `tenancy/security.py:73`                 | ~450      | 0 prod                                                             | ORPHAN                                                            |
| `SecurityPolicy`                             | `tenancy/security.py:32`                 | ~20       | self-ref                                                           | ORPHAN                                                            |
| `SecurityAuditLog`                           | `tenancy/security.py:57`                 | ~15       | self-ref                                                           | ORPHAN                                                            |
| `DebugAgent` (legacy)                        | `debug/debug_agent.py:19`                | ~250      | `debug/cli.py:157` only                                            | ORPHAN-TRANSITIVE + **DUPLICATE of `debug/agent.py::DebugAgent`** |
| `ErrorCategorizer`                           | `debug/error_categorizer.py:33`          | ~450      | `debug_agent.py` only                                              | ORPHAN-TRANSITIVE (+ regex classifier in agent)                   |
| `SolutionGenerator`                          | `debug/solution_generator.py`            | ~800      | `debug_agent.py` only                                              | ORPHAN-TRANSITIVE                                                 |
| `KnowledgeBase`                              | `debug/knowledge_base.py`                | ~230      | `debug_agent.py` + tests                                           | ORPHAN-TRANSITIVE                                                 |
| `PatternRecognitionEngine`                   | `debug/pattern_recognition.py:34`        | ~340      | `debug/agent.py` only                                              | PARTIAL-ORPHAN (one user)                                         |
| `DerivedModelRefreshScheduler`               | `features/derived.py:504`                | ~85       | 1 (`features/derived.py:360`)                                      | LIVE                                                              |

## CRITICAL findings (security-critical orphans, stub-in-live-path)

### C1 — `utils/connection.py::ConnectionManager` is a live-service stub

`core/engine.py:454` assigns `self._connection_manager = ConnectionManager(self)`
and `core/engine.py:2830` exposes it as the `db.connection` property. Every
method is a fake:

- `initialize_pool()` returns `{"pool_initialized": True, "success": True}`
  with the source-code comment `# In real implementation, would create
SQLAlchemy engine and pool` (`utils/connection.py:77`).
- `health_check()` always returns `database_reachable=True` with the comment
  `# In real implementation, would test actual database connection`
  (`utils/connection.py:93`).
- `test_connection()` does not connect — same `# In real implementation`
  comment (`utils/connection.py:131`).
- `close_all_connections()` just zeroes an in-memory counter.

This is `zero-tolerance.md` Rule 2 (no stubs) + Rule 6 (implement fully) and
the `dataflow-pool.md` Rule "Validate Pool Config AND Reachability at Startup"
all at once. Users calling `db.connection.health_check()` get a lie.

### C2 — `features/transactions.py::TransactionManager` never touches a database

`core/engine.py:453` assigns `self._transaction_manager`. The `transaction()`
context manager (line 18) yields a dict, flips `status` from `"active"` to
`"committed"` in memory on success or `"rolled_back"` on exception, and never
issues `BEGIN`, `COMMIT`, or `ROLLBACK`. Users who write

```python
with db.transactions.transaction():
    await db.express.create("Order", {...})
    await db.express.create("OrderLine", {...})
```

believe they have an atomic write. They have two independent autocommitted
writes. This is a **data-integrity CRITICAL** — not a security bug, a
correctness bug that guarantees silent partial writes under exception.

### C3 — `features/multi_tenant.py::MultiTenantManager` hardcoded timestamp + no DB

`features/multi_tenant.py:28` creates tenants with a literal
`"created_at": "2024-01-01T00:00:00Z"` — every tenant on every install gets
the same fake creation date. `delete_tenant()` has the comment `# In real
implementation, would also delete all tenant data` but only pops a dict entry
(`features/multi_tenant.py:85`). This is the "live service that is a lie"
pattern again. Note: the **wired** multi-tenancy flows go through
`core/multi_tenancy.py::TenantContext`, NOT through this feature file. Remove
or rewrite.

### C4 — `semantic/search.py:134` uses `eval()` on a DB column value

Already flagged by the security auditor. Verbatim:

```python
embedding = np.array(
    row["embedding"]
    if isinstance(row["embedding"], list)
    else eval(row["embedding"])  # ← CRITICAL: arbitrary-code execution
)
```

Combined with the finding that `semantic/` is an orphan, the current risk is
zero in the running process (nothing reaches line 134). The reason it is still
CRITICAL: the surrounding docstring promises a "production-ready semantic
search", other skills reference `SemanticMemory`, and any consumer that ever
follows that documentation will import the landmine. Delete or rewrite with
`json.loads` / `ast.literal_eval` before allowing any downstream rewire.

### C5 — `dataflow.cli/main.py` is a production entry point that stubs every command

`pyproject.toml:88-89` declares `[project.scripts] dataflow =
"dataflow.cli:main"`. Running `dataflow init`, `dataflow schema`, `dataflow
migrate create`, `dataflow migrate apply`, `dataflow migrate rollback`, and
`dataflow migrate status` all print **success messages that describe actions
never performed** (`cli/main.py:42, 83, 113, 125, 137, 146`). The `init`
handler literally instantiates a `DataFlow` object with the comment
`# Mock the DataFlow instantiation for testing` (line 37) and then prints
`"Database initialization functionality coming soon..."` (line 42). This is
the worst kind of user-facing stub: it exits 0 and prints "success" while
doing nothing. **Inspector CLI is the only CLI subcommand that works.**

### C6 — `utils/suppress_warnings.py::suppress_core_sdk_warnings()` runs on import

`dataflow/__init__.py:92` calls `suppress_core_sdk_warnings()` unconditionally.
That function (`utils/suppress_warnings.py:55-59`) downgrades
`kailash.nodes.base` and `kailash.resources.registry` from WARNING to ERROR
for the lifetime of the process. This is `rules/observability.md` MUST "No
silent log-level downgrades" — "Fix the root cause or document the
suppression in the rule itself. Downgrading log levels to silence noise is a
Zero-Tolerance Rule 1 violation in disguise". The root cause is that DataFlow
re-registers nodes during `@db.model` decoration; the correct fix is in the
SDK node registry (support re-registration silently) — `zero-tolerance.md`
Rule 4 — not a blanket logger mute.

## HIGH findings (large orphan implementations blocking framework-first)

### H1 — `dataflow.trust/` is entirely orphaned (2,407 LOC)

Three subsystems claiming CARE-019, CARE-020, CARE-021 features live in
`dataflow.trust/` and have **zero production importers anywhere in the
codebase**. The only referrers are their own tests. Every class advertised in
`trust/__init__.py` (`TrustAwareQueryExecutor`, `ConstraintEnvelopeWrapper`,
`QueryAccessResult`, `QueryExecutionResult`, `SignedAuditRecord`,
`DataFlowAuditStore`, `CrossTenantDelegation`, `TenantTrustManager`) is
orphaned. The docstring promises "trust-aware query execution for DataFlow"
but nothing in the DataFlow query path calls any of it. This should either be
removed or bolted into `core/engine.py`'s `_ensure_connected()` pipeline.

### H2 — `dataflow.web.WebMigrationAPI` is an orphaned 1,885-LOC class

`web/migration_api.py` wraps `VisualMigrationBuilder` and `AutoMigrationSystem`
to provide "schema inspection, migration preview, validation, execution and
rollback" via a session-based API. No Nexus endpoint mounts it, no CLI routes
to it, no gateway surfaces it. The only code that imports it is its own tests
and two hand-written `scripts/fix_final_*_test_failures.py` helper scripts.
If migration-over-HTTP is required, wire it through a Nexus handler. If not,
delete.

### H3 — `dataflow.compatibility/` uses `unittest.mock.Mock` in production

`compatibility/legacy_support.py:75` defines a "production" `DataFlowConfig`
class whose `__init__` sets attributes via `unittest.mock.Mock()`. This is
not a test helper — it is the production code that `LegacyAPICompatibility`
calls into. The subsystem has zero external importers. Delete the whole
subdirectory — backward compat if needed lives in the deprecation warnings
on the real `DataFlowConfig`, not a separate mock-backed copy.

### H4 — `dataflow.performance/` is a test-only parallel migration stack

`performance/migration_optimizer.py` defines `MigrationFastPath`,
`OptimizedSchemaComparator`, and `MigrationConnectionManager`. Zero production
references. `migrations/migration_connection_manager.py` contains its own
**differently-implemented `MigrationConnectionManager`** that IS used
(`core/engine.py`-adjacent migration code and `migration_test_framework.py`
both import the live one). Duplicate class names in two subdirectories are a
framework-first Rule 4 violation and a confusion vector at import time.
`performance/sqlite_monitor.py` (775 LOC) is similarly orphaned.

### H5 — `dataflow.semantic/` duplicates Kaizen's semantic memory

`kaizen/nodes/ai/semantic_memory.py` and `kaizen/retrieval/vector_store.py`
are the live, referenced semantic memory stack used by RAG examples. The
DataFlow `semantic/` subdirectory reimplements `SemanticMemory`, `VectorStore`,
`HybridSearchEngine`, `SemanticSearchEngine`, `OllamaEmbeddings`, and
`OpenAIEmbeddings` with the `OpenAIEmbeddings` default model hardcoded to
`"text-embedding-3-small"` (`semantic/embeddings.py:89`) — a direct
`env-models.md` violation. Combined with the orphan status and the `eval()`
landmine this is the biggest "delete this" candidate in the audit.

### H6 — `dataflow.debug/` has two `DebugAgent` classes and regex-classifier agents

Two classes named `DebugAgent` exist: `debug/debug_agent.py:19` and
`debug/agent.py:41`. The latter is a `KaizenNode`; the former is not. Both are
documented publicly. `debug/cli.py:157` instantiates the legacy one;
`cli/debug_agent_cli.py:314` instantiates the Kaizen one. Users importing
`DebugAgent` from the two different paths get different behavior. Pick one and
delete the other.

Both paths violate `rules/agent-reasoning.md` Rule 2 ("No keyword/regex
matching on agent inputs"). `debug/error_categorizer.py:33::ErrorCategorizer`
is a regex-based pattern matcher over error messages that decides which
solution group to surface — pure deterministic classification in the agent
decision path. `debug/pattern_recognition.py:34::PatternRecognitionEngine`
computes "match scores" using hardcoded thresholds ("Exact error code match:
1.0, Same category: 0.7…") to route between cached solutions. The LLM is
never asked which solution applies. Rewire via Kaizen `Signature` fields or
delete.

Additionally, `debug/agent.py:69` hardcodes `model: str = "gpt-4o-mini"` —
`env-models.md` violation. `cli/debug_agent_cli.py:314` passes it through.

### H7 — `platform/` developer-experience stack is a disconnected half-framework

`platform/__init__.py` advertises `DataFlowStudio`, `BuildValidator`,
`ValidationReport`, `ValidationLevel`, `ConfigProfile`, `AutoFix`, `FixResult`
— none of which are imported anywhere in the rest of the codebase. Only
`platform.inspector.Inspector` and `platform.errors.ErrorEnhancer` are live:
`core/engine.py:51` and `core/nodes.py:52` import the `ErrorEnhancer` as
`PlatformErrorEnhancer` inside a try/except fallback; `debug/*` and `cli/*`
import `Inspector`. The rest — `autofix.py` (517 LOC), `validation.py` (494
LOC), `studio.py` (528 LOC), `resilience.py` (504 LOC), `health.py` (389
LOC), `metrics.py` (241 LOC) — is orphan. `platform/errors.py::DataFlowError`
is a duplicate of `dataflow/exceptions.py:121::DataFlowError`. `platform/
health.py::HealthStatus` is a duplicate of `dataflow/engine.py:89::HealthStatus`.

### H8 — `features/retention.py::_partition` raises NotImplemented-equivalent

`features/retention.py:297-300` — the `_partition` branch of `RetentionEngine`
raises `DataFlowConfigError("Partition retention policy is not yet
implemented. Use 'archive' or 'delete' policy instead.")`. The module
docstring (line 10) promises three policies: archive, delete, **partition**.
Two of three are real. `zero-tolerance.md` Rule 2: no "will implement later"
comments or paths. Remove the partition branch entirely or implement it.

### H9 — `dataflow.tenancy/` is wired by lazy import inside a hot path

`core/nodes.py:479` imports `QueryInterceptor` lazily on every read/write
from a tenant-enabled model, via `from ..tenancy.interceptor import
QueryInterceptor`. Lazy imports in the hot path are a micro-perf issue but
the bigger concern is that the interceptor rewrites SQL via regex and
f-strings (`interceptor.py:698, 715, 719, 776, 785, 807, 816`). Example:

```python
tenant_condition = f"{table_alias}.{self.tenant_column} = ?"
modified_query = re.sub(
    r"WHERE\s+",
    f"WHERE {tenant_condition} AND ",
    modified_query,
    ...
)
```

`tenant_column` is controlled by configuration, not user input, but if the
configuration ever accepts a tenant_column with a regex metacharacter (`.`
in `customer.tenant_id`) the `re.sub` replacement string will expand
backrefs. More importantly, this is raw SQL-string manipulation outside the
Kailash dialect layer — `framework-first.md` violation. Use SQLGlot or the
existing dialect helpers. `tenancy/security.py::TenantSecurityManager` is
orphan and should be deleted or wired into the same interceptor path.

### H10 — `performance/migration_optimizer.py` has a duplicate class name

`MigrationConnectionManager` appears at `migrations/migration_connection_
manager.py:85` (live) AND `performance/migration_optimizer.py:685` (orphan).
Two classes, same name, different semantics. Whichever one an IDE's "go to
definition" picks is the one the reader sees. Delete the orphan copy.

### H11 — `platform.resilience.CircuitBreaker` is a third duplicate

Three independent `CircuitBreaker` implementations:

1. `platform/resilience.py:318::CircuitBreaker` (orphan)
2. `adapters/source_adapter.py:69::CircuitBreaker` (live, used by fabric)
3. `fabric/config.py:158::CircuitBreakerConfig` (live config for #2)

This is the same anti-pattern the other auditors found with cache and
migrations. Pick one, delete the other two.

### H12 — Inspector is user-facing but has a `TODO: Reconstruct workflow from JSON`

`cli/inspector_cli.py:38-39`:

```python
# TODO: Reconstruct workflow from JSON
# For now, this is a placeholder
```

Inspector is the ONE CLI command that is supposed to work end-to-end. It has
a live stub branch.

## MEDIUM findings (small orphans, duplicate functionality, hygiene)

### M1 — `features/__init__.py` re-exports `RetentionPolicy` that collides with classification enum

`features/retention.py::RetentionPolicy` is a `@dataclass` with fields
`model_name`, `table_name`, `policy`, `after_days`, ...
`classification/types.py::RetentionPolicy` is a `str`-backed `Enum` with
values `INDEFINITE`, `DAYS_30`, `DAYS_90`, .... The top-level
`dataflow/__init__.py` re-exports the **enum** one as `RetentionPolicy`, but
`features/__init__.py` would export the **dataclass** one if anyone ever
imports from `dataflow.features`. Two different meanings for the same public
name. Rename one.

### M2 — `features/retention.py` reads a `policy.cutoff_field` via f-string into SQL

`features/retention.py:309-314` builds a `DELETE` query via
`f"SELECT COUNT(*) as cnt FROM {policy.table_name} WHERE
{policy.cutoff_field} < ?"`. `_validate_table_name` exists for `table_name`
at line 38, but `cutoff_field` has no validation. Add the same identifier
check.

### M3 — `debug/agent.py` hardcodes `confidence_threshold=0.7`

This is not routing — it's a filter — so it's out of scope for
agent-reasoning Rule 1 under the "safety guard" exception. But it's a magic
number with no configuration path. Plumb from config.

### M4 — `event_stores/__init__.py` exports `SQLiteEventStore` but not `PostgreSQLEventStore`

`event_stores/__init__.py:1-7` only re-exports the SQLite backend.
`core/engine.py:1172` uses `PostgreSQLEventStore` directly via a deep import.
Either export both in `__all__` or remove the init altogether.

### M5 — `platform/errors.py::DataFlowError` shadows `exceptions.py::DataFlowError`

Two exception classes with the same name in two modules means `isinstance`
checks silently diverge depending on which import path reached them. Pick
one canonical location (the top-level `exceptions.py` is already imported by
more callers) and have the other re-export, or delete the duplicate.

### M6 — `platform/health.py::HealthStatus` shadows `engine.py:89::HealthStatus`

Same pattern as M5 but for the health enum. `engine.py::HealthStatus` is
re-exported from `dataflow/__init__.py`; `platform/health.py::HealthStatus`
is not. Delete the shadow.

### M7 — `DerivedModelRefreshScheduler` started but no shutdown hook

`features/derived.py:504` defines the scheduler; `features/derived.py:360-361`
creates it and calls `.start()` during validate. The scheduler creates one
`asyncio.Task` per scheduled derived model. `stop()` exists but is not called
from any `DataFlow.close()` path — I did not see a caller of
`_derived_engine._scheduler.stop()`. Scheduler tasks leak on shutdown.

### M8 — `utils/suppress_warnings.py` duplicates `LoggingConfig` handling

Two logging configs exist: `core/config.py::LoggingConfig` and
`core/logging_config.py::LoggingConfig` (re-exported as
`AdvancedLoggingConfig` in `__init__.py:48`). This file bridges them. The
duplication should be resolved before adding more entry points.

### M9 — `cli/commands.py` is a 25-line stub module

`cli/commands.py` contains no real commands. The live CLI commands live in
`cli/main.py`, `cli/debug.py`, `cli/generate.py`, etc. This file should
either be deleted or consolidate the registrations.

### M10 — `compatibility/` imports `unittest.mock.Mock` at module level

Beyond the `DataFlowConfig` Mock class, `compatibility/legacy_support.py:22`
imports `from unittest.mock import Mock` at the top of the module. Production
modules should not depend on `unittest`.

### M11 — `tenancy/exceptions.py` is 35 lines for three exception classes

Acceptable size but `CrossTenantAccessError`, `QueryParsingError`,
`TenantIsolationError` all inherit from `Exception` — not from a shared
`TenantError` base. Downstream cannot catch "any tenancy error" cleanly.

## LOW findings (comment/naming/hygiene)

### L1 — `platform/__init__.py` advertises `__version__ = "0.1.0"` inside the package

`platform/__init__.py:64`. Two version numbers exist in the package:
`dataflow/__init__.py::__version__ = "1.7.1"` and this. Delete the
sub-package version.

### L2 — `DataFlowStudio` docstring says "1-minute setup" but nothing calls it

Aspirational docstrings are worse than no docstrings because they suggest the
framework has a quick-start path that it actually doesn't.

### L3 — `platform/resilience.py` example code in module docstring references

`circuit_breaker = CircuitBreaker(circuit_config)` — inside a docstring, not
a wired test. The only place the class is "used" is its own documentation.

### L4 — `cli/commands.py` + `cli/analyze.py` + `cli/debug.py` + `cli/validate.py`

Four separate CLI files each reimplement argparse/click setup. Consolidate
under a single command registry.

### L5 — `debug/patterns.yaml` + `debug/solutions.yaml` + `platform/error_catalog.yaml`

Three YAML files describing error patterns. `error_catalog.yaml` is 2,500+
lines. `patterns.yaml` and `solutions.yaml` are consumed only by
`KnowledgeBase`. Merge or delete duplicates.

### L6 — `suppress_warnings.py` exports `suppress_core_sdk_warnings` AND

`restore_core_sdk_warnings` AND a context manager. Only the suppress function
is actually called from production. Trim the surface.

### L7 — `platform/inspector.py` is 3,540 lines in a single file

Not an orphan finding per se but a maintainability concern. The other auditors
may want to factor into `inspector/models.py`, `inspector/workflows.py`, etc.

## Deletion candidates

Outright deletion recommended (no functionality lost, no user-facing API
broken because nothing outside tests imports these):

1. `dataflow/web/` (entire directory, 1,958 LOC)
2. `dataflow/semantic/` (entire directory, 1,239 LOC + `eval()` landmine)
3. `dataflow/nodes/semantic_memory.py` (SemanticMemoryNode; not registered)
4. `dataflow/trust/` (entire directory, 2,407 LOC) — or rewire per R1 below
5. `dataflow/compatibility/` (entire directory, 1,327 LOC, contains Mock in
   production code)
6. `dataflow/performance/` (entire directory, 1,700 LOC, duplicate class names)
7. `dataflow/platform/studio.py`
8. `dataflow/platform/autofix.py`
9. `dataflow/platform/validation.py` (orphan BuildValidator)
10. `dataflow/platform/resilience.py` (duplicate CircuitBreaker)
11. `dataflow/platform/health.py` (duplicate HealthStatus)
12. `dataflow/platform/metrics.py`
13. `dataflow/platform/errors.py::DataFlowError` (keep ErrorCode + ErrorEnhancer,
    drop the duplicate exception class)
14. `dataflow/tenancy/security.py` (orphan TenantSecurityManager)
15. `dataflow/debug/debug_agent.py` (legacy DebugAgent, duplicate of
    `debug/agent.py`)
16. `dataflow/debug/cli.py` (legacy debug CLI, replaced by
    `cli/debug_agent_cli.py`)
17. `dataflow/debug/solution_generator.py`, `solution_ranking.py`,
    `error_categorizer.py`, `pattern_recognition.py`, `knowledge_base.py`,
    `patterns.yaml`, `solutions.yaml` (all transitively orphaned once the
    legacy `DebugAgent` is removed AND the agent is rewired to LLM-first —
    see R2).
18. `dataflow/features/multi_tenant.py::MultiTenantManager` (stub; replace
    `db.tenants` with `core/multi_tenancy.py::TenantContext`)
19. `dataflow/features/transactions.py::TransactionManager` (stub; replace
    `db.transactions` with real `TransactionScopeNode`)
20. `dataflow/utils/connection.py::ConnectionManager` (stub; replace
    `db.connection` with actual pool access)
21. `dataflow/cli/commands.py` (empty)
22. `dataflow/cli/main.py::init` and `main.py::schema` stubs; replace with
    real initialization using the live path.

Total deletion candidate LOC: **~17,500**.

## Re-wire candidates

Items that should NOT be deleted but need to actually connect to the live path:

### R1 — Wire `dataflow.trust/` into DataFlow query path

`TrustAwareQueryExecutor` needs to wrap `db.express.*` and `db.nodes.*` read
paths so that CARE-019 constraint envelopes actually filter queries.
`DataFlowAuditStore` needs to back `core/audit_integration.py::AuditIntegration`
so that audit records are cryptographically signed per CARE-020.
`TenantTrustManager` needs to be called from `core/tenant_context.py` when a
cross-tenant delegation is activated. If none of those integrations can be
defended in the next sprint, delete the entire subsystem per `rules/zero-
tolerance.md` Rule 2 — "not yet wired" is the same class of sin as "not yet
implemented".

### R2 — Replace `debug/` agent with a Kaizen-native LLM-first agent

Per `rules/agent-reasoning.md`, the `ErrorCategorizer` + `PatternRecognitionEngine`

- `SolutionGenerator` pipeline must be collapsed into a single Kaizen
  `Signature` with fields: `error_text`, `stack_trace`, `workflow_context`,
  `node_type`, `environment`, and outputs: `category`, `likely_cause`,
  `suggested_fix`, `confidence`. The LLM does the classification; the YAML
  patterns become part of the system prompt or a retrieval corpus, not a
  deterministic scoring function. Delete `error_categorizer.py`,
  `pattern_recognition.py`, `solution_ranking.py`. Keep `Inspector` (which IS
  live).

### R3 — Replace `utils/connection.py::ConnectionManager` with a thin wrapper

around the real pool
The `db.connection` API is useful if it actually exposes pool statistics.
Rewrite `ConnectionManager` so `get_connection_stats()`, `health_check()`,
and `close_all_connections()` call through to the live pool in
`core/engine.py` (which is built from `migrations/migration_connection_
manager.py` and the adapter layer). Delete the stub methods.

### R4 — Replace `features/transactions.py` with `TransactionScopeNode`

The live transaction layer already exists (`nodes/transaction_nodes.py::
TransactionScopeNode`). `db.transactions.transaction()` should be a thin
wrapper that builds a one-node workflow and executes it — not a dict-flipper.

### R5 — Replace `features/multi_tenant.py` with `core/multi_tenancy.py`

`core/multi_tenancy.py::TenantContext` and `core/tenant_context.py::
TenantContextSwitch` are the real multi-tenancy primitives. The
`MultiTenantManager` facade should call them instead of storing tenants in a
Python dict. Or just delete the facade and document `TenantContext` as the
public API.

### R6 — Fix `suppress_core_sdk_warnings` by fixing node re-registration in the core SDK

`zero-tolerance.md` Rule 4: the workaround is banned. The real fix is in
`kailash.nodes.base` — support idempotent re-registration silently (log at
DEBUG, not WARNING). Once the SDK is fixed, delete
`suppress_core_sdk_warnings` and its caller at `dataflow/__init__.py:92`.

### R7 — Wire `dataflow.cli` to real commands

`dataflow init`, `dataflow schema`, `dataflow migrate *` should all call the
live APIs they claim to call. This is mostly removing `"coming soon"` strings
and plumbing to `DataFlow`, `core/database_registry.py`,
`migrations/auto_migration_system.py`, and `core/schema.py`.

### R8 — Decide on `dataflow.web`: Nexus handler or delete

If migration-over-HTTP is a real requirement, wire `WebMigrationAPI` through
a Nexus handler. Otherwise delete.

## Cross-subsystem couplings

- `platform/` ↔ `debug/` ↔ `cli/` — `Inspector` is the shared spine. Any
  change to `Inspector`'s 3,540-line file (`platform/inspector.py`) will
  ripple into all three subsystems. Tests and docs reference it from at
  least 56 different files.
- `core/engine.py` ↔ `utils/connection.py`, `features/transactions.py`,
  `features/multi_tenant.py` — these three stubs are all instantiated in
  `DataFlow.__init__` (lines 453-454) and exposed as top-level `db.*`
  properties. Removing them WILL break every downstream user who has ever
  touched `db.transactions`, `db.tenants`, or `db.connection`. The migration
  path needs to be coordinated with the core auditor.
- `features/derived.py` ↔ `core/engine.py` — `DerivedModelEngine` is live and
  wired through `db.derived_model()`, `db.refresh_derived()`,
  `db.derived_model_status()`. Scheduler lifecycle is NOT hooked into
  `DataFlow.close()` — see M7.
- `features/retention.py` ↔ `core/engine.py` — `RetentionEngine` is live
  through `db.retention`. `_partition()` is a stub raising
  `DataFlowConfigError` (H8).
- `tenancy/interceptor.py` ↔ `core/nodes.py` — single lazy-import attachment
  via `nodes.py:479`. All tenancy goes through that one import and a second
  hidden path through `core/multi_tenancy.py`. Confusion risk.
- `trust/` ↔ nothing — the trust subsystem's only "coupling" is to itself.
  This is the smoking gun for the audit. 2,407 LOC that the rest of DataFlow
  cannot see.
- `semantic/` ↔ `nodes/semantic_memory.py` (not registered) — a one-hop
  dead-end. No live workflow can ever produce a `SemanticMemoryNode`.
- `performance/` ↔ `migrations/` — two `MigrationConnectionManager` classes
  with the same name, one live and one orphan. Delete the orphan.

## Framework-first summary

Per `rules/framework-first.md`, Kailash has exactly one canonical path for
each work domain. The orphan subsystems violate this principle:

- **HTTP**: `web/migration_api.py` should be a Nexus handler, not a
  standalone web API class.
- **Agent reasoning**: `debug/` should be a Kaizen `Signature`, not a
  regex-based classification pipeline.
- **Transactions**: `features/transactions.py` should route through the
  existing `TransactionScopeNode`, not fake one with a dict.
- **Connection pool**: `utils/connection.py` should proxy the real pool, not
  fabricate `{"database_reachable": True}`.
- **Semantic search**: `semantic/` should be a thin adapter that calls
  Kaizen's `SemanticMemory` — or be deleted.
- **Trust**: `trust/` should compose with `kailash.trust/` and be invoked by
  `core/audit_integration.py`. Or be deleted.

Every one of the orphan subsystems is a parallel implementation of a
framework-first-mandated subsystem. Together they represent the single
largest lever for "DataFlow perfection" in terms of LOC.

## Cross-SDK inspection (per `rules/cross-sdk-inspection.md`)

Almost every orphan finding has a cross-SDK angle:

- **Trust**: Rust `crates/kailash-dataflow` has an analogous `trust/`
  module? If yes, is it wired? If no, is the Python orphan code ahead of the
  Rust side or behind it? File a `cross-sdk` issue either way.
- **Semantic memory**: Kaizen-Rust may or may not reimplement this. The
  Python orphan's `eval()` is the kind of bug that MUST be filed as `cross-
sdk` so the Rust side avoids the same deserialization pattern.
- **CLI**: `kailash-dataflow-cli` in Rust — does it have the same
  `init`/`schema`/`migrate` stubs? If yes, they are both "coming soon". If
  no, the Rust side is already ahead.
- **Connection manager**: Rust's pool layer is structurally different
  (`kailash-infrastructure`). The Python `ConnectionManager` stub is a
  Python-only sin.
- **DataFlowStudio / platform/**: Rust has no equivalent. This is a
  Python-only experiment that should be deleted, not ported.

The parent auditor should file `cross-sdk` issues for: Trust wiring, Semantic
`eval()`, CLI stubs, `CircuitBreaker` duplication.

## What this audit did NOT do

- Did not modify any code (analysis phase constraint).
- Did not run tests against the orphan subsystems — orphans have no runtime
  pressure, so test pass/fail is meaningless to the question "is it wired?".
- Did not measure actual `eval()`-based embedding production — the orphan
  status makes the runtime risk zero today; the finding is about future risk.
- Did not trace every Inspector call site (the scope overlap with the
  core-and-config auditor is intentional — Inspector is live; my finding is
  that the rest of `platform/` around it is not).
- Did not measure duplication between the DataFlow logging stack
  (`utils/suppress_warnings.py`, `core/logging_config.py`, `core/config.py::
LoggingConfig`). That duplication is noted but the detailed audit is in
  the core-and-config scope.

## File-by-file verdict index (for the master fix plan)

DELETE (no replacement needed): `web/`, `semantic/`, `compatibility/`,
`performance/`, `platform/studio.py`, `platform/autofix.py`,
`platform/validation.py`, `platform/resilience.py`, `platform/metrics.py`,
`tenancy/security.py`, `debug/debug_agent.py`, `debug/cli.py`,
`cli/commands.py`.

DELETE WITH REWIRE (stub, not orphan): `features/multi_tenant.py`,
`features/transactions.py`, `utils/connection.py::ConnectionManager`,
`cli/main.py::init+schema+migrate*`, `features/retention.py::_partition`,
`utils/suppress_warnings.py` (kill the auto-call, fix upstream SDK).

REWIRE OR DELETE: `trust/` (either wire into query path / audit store or
delete in full), `debug/error_categorizer.py` + `pattern_recognition.py` +
`solution_generator.py` + `solution_ranking.py` (rewrite as Kaizen Signature
or delete).

FIX: `semantic/search.py:134` (delete `eval()`), `debug/agent.py:69` (remove
hardcoded model), `cli/debug_agent_cli.py:314` (remove hardcoded model),
`tenancy/interceptor.py` (replace f-string SQL rewrite with dialect helpers),
`features/retention.py:309-314` (validate `cutoff_field`),
`event_stores/__init__.py` (export `PostgreSQLEventStore`).

KEEP AS-IS: `features/derived.py`, `features/retention.py` (sans `_partition`),
`utils/connection_adapter.py`, `core/event_store.py`, `core/event_stores/
sqlite.py`, `core/event_stores/postgresql.py`, `platform/inspector.py`
(factor separately; scope is core auditor), `platform/errors.py::ErrorEnhancer`
(live), `tenancy/interceptor.py::QueryInterceptor` (live, but see Fix list
for safety hardening).

Total orphan LOC identified in this audit: **~15,500 LOC**
Total stub-in-live-path LOC: **~1,800 LOC**
Total deletion/rewrite candidates: **~17,300 LOC** across 11 subsystems.
