# W5-A Findings — core + infra + node-catalog

**Specs audited:** 7
**§ subsections enumerated:** TBD (see per-spec sections)
**Findings:** CRIT=0 HIGH=0 MED=0 LOW=0 (running tally — updated per commit)
**Audit completed:** 2026-04-26
**Branch:** `audit/w5-a-core-spec-audit`
**Base SHA:** `6142ea52`
**Working tree:** `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/w5-a-core`

## Methodology

Per `.claude/skills/spec-compliance/SKILL.md`:

1. Each spec read in full.
2. Acceptance assertions extracted (class names, method signatures, exception types, BLOCKED patterns, security threats).
3. Each assertion verified via `Grep` (class/method names) + targeted `Read` (signature confirmation) against `src/` and `packages/`.
4. Findings classified CRIT/HIGH/MED/LOW per task brief.

## Severity Definitions

- **CRIT** — Security/governance contract claimed but absent (orphan facade per `rules/orphan-detection.md` §1)
- **HIGH** — Public API claimed but absent or signature-divergent
- **MED** — Internal helper or utility claimed but absent
- **LOW** — Naming/terminology drift, doc-only assertions

---

# Spec 1: `specs/core-nodes.md`

**Subsections audited:** §1.1 (Node ABC + 6 subsections), §1.2 (NodeParameter), §1.3 (NodeMetadata), §1.4 (NodeRegistry).
**Verification source:** `src/kailash/nodes/base.py` (2,700+ lines).

| Assertion | Method | Expected | Actual | Status |
|-----------|--------|----------|--------|--------|
| `class NodeMetadata(BaseModel)` exists at `kailash.nodes.base` | grep | match | line 44 | OK |
| `class NodeParameter(BaseModel)` exists | grep | match | line 77 | OK |
| `class Node(ABC)` exists | grep | match | line 152 | OK |
| `class NodeRegistry` exists | grep | match | line 2129 | OK |
| `Node._DEFAULT_CACHE_SIZE = 128` | grep | int 128 | line 191 (`= 128`) | OK |
| `Node._SPECIAL_PARAMS = {"context", "config"}` | grep | set | line 192 | OK |
| `Node._strict_unknown_params = False` | grep | False | line 193 | OK |
| `Node._env_cache: dict[str, str \| None] = {}` | grep | empty dict | line 194 | OK |
| `Node._clear_env_cache()` classmethod | grep | classmethod | line 208 | OK |
| `Node.id` property (getter + setter) | grep | both | lines 422, 435 | OK |
| `Node.metadata` property (getter + setter, type-routed) | grep | both | lines 448, 469 | OK |
| Abstract `get_parameters` | grep | abstractmethod | line 506 | OK |
| Abstract `run` | grep | abstractmethod | line 610 | OK |
| `get_output_schema` (optional, default `{}`) | grep | match | line 553 | OK |
| `get_workflow_context` | grep | match | line 373 | OK |
| `set_workflow_context` | grep | match | line 399 | OK |
| `_validate_config` invoked in `__init__` | grep | match | line 661 | OK |
| `validate_inputs` | grep | match | line 787 | OK |
| `execute` (orchestrator) | grep | match | line 1347 | OK |
| `NodeMetadata` fields: `id`, `name`, `description`, `version`, `author`, `created_at`, `tags` | Read | all 7 | lines 65–74 | OK |
| `NodeParameter` fields: `name`, `type`, `required`, `default`, `description`, `choices`, `enum`, `default_value`, `category`, `display_name`, `icon`, `input`, `output`, `auto_map_from`, `auto_map_primary`, `workflow_alias` | Read | all 16 | lines 112–149 | OK |
| `NodeRegistry.register` | grep | match | line 2189 | OK |

**Spec 1 findings:** 0 CRIT / 0 HIGH / 0 MED / 0 LOW.

Note: All claims in `core-nodes.md` are present in `src/kailash/nodes/base.py`. Class field counts and signatures match the spec verbatim. The spec accurately documents the implementation; no drift detected.

---

# Spec 2: `specs/core-workflows.md`

**Subsections audited:** §2.1 (WorkflowBuilder + 8 method subsections), §2.2 (Workflow + 5 subsections), §3.1 (Connection), §3.2 (CyclicConnection), §3.3 (NodeInstance), §3.4 (ConnectionContract), §3.5 (Data Flow Semantics), §8.1–§8.3 (Validation).
**Verification source:** `src/kailash/workflow/{builder,graph,contracts,validation,cycle_builder}.py`.

| Assertion | Method | Expected | Actual | Status |
|-----------|--------|----------|--------|--------|
| `class WorkflowBuilder` at `kailash.workflow.builder` | grep | match | builder.py:20 | OK |
| `WorkflowBuilder.add_node(*args, **kwargs) -> str` | grep | match | builder.py:200 | OK |
| `WorkflowBuilder.add_connection(from_node, from_output, to_node, to_input)` | grep | match | builder.py:536 | OK |
| `WorkflowBuilder.connect(from_node, to_node, mapping=...)` | grep | match | builder.py:656 | OK |
| `WorkflowBuilder.add_typed_connection(..., contract, validate_immediately=False)` | grep | match | builder.py:711 | OK |
| `WorkflowBuilder.set_metadata(**kwargs) -> WorkflowBuilder` | grep | match | builder.py:698 | OK |
| `WorkflowBuilder.validate_parameter_declarations(warn_on_issues=True)` | grep | match | builder.py:106 | OK |
| `WorkflowBuilder.build(workflow_id=None, **kwargs) -> Workflow` | grep | match | builder.py:901 | OK |
| `WorkflowValidationError`, `ConnectionError` imports from `kailash.sdk_exceptions` | grep | match | builder.py:8 | OK |
| `class Workflow` at `kailash.workflow.graph` | grep | match | graph.py:106 | OK |
| `Workflow.add_node(node_id, node_or_type, **config)` | grep | match | graph.py:233 | OK |
| `Workflow.connect(source_node, target_node, mapping, cycle, max_iterations, ...)` | grep | match | graph.py:331 | OK |
| `Workflow.get_node(node_id) -> Node \| None` | grep | match | graph.py:713 | OK |
| `Workflow.separate_dag_and_cycle_edges()` | grep | match | graph.py:733 | OK |
| `Workflow.get_cycle_groups() -> dict[str, list[tuple]]` | grep | match | graph.py:760 | OK |
| `Workflow.create_cycle(cycle_id=None)` | grep | match | graph.py:615 | OK |
| `class Connection(BaseModel)` at `kailash.workflow.graph` | grep | match | graph.py:72 | OK |
| `class CyclicConnection(Connection)` | grep | match | graph.py:81 | OK |
| `class NodeInstance(BaseModel)` | grep | match | graph.py:38 | OK |
| `NodeInstance._SENSITIVE_KEYS` (frozenset, includes api_key, password, token, secret, etc.) | grep | match | graph.py:42 | OK |
| `class ConnectionContract` at `kailash.workflow.contracts` | grep | match | contracts.py:51 | OK |
| `class SecurityPolicy(Enum)` at `kailash.workflow.contracts` | grep | match | contracts.py:28 | OK |
| `class ValidationIssue` at `kailash.workflow.validation` | grep | match | validation.py:135 | OK |
| `class IssueSeverity(Enum)` at `kailash.workflow.validation` | grep | match | validation.py:126 | OK |
| `class CycleBuilder` at `kailash.workflow.cycle_builder` | grep | match | cycle_builder.py:58 | OK |
| `class WorkflowDAG` at `kailash.workflow.dag` | grep | match | dag.py:141 | OK |

**Spec 2 findings:** 0 CRIT / 0 HIGH / 0 MED / 0 LOW.

Note: All workflow construction classes, connection types, contract types, and validation primitives are present at the spec-claimed module paths with the spec-claimed signatures.

---

# Spec 3: `specs/core-runtime.md`

**Subsections audited:** §4.1 (LocalRuntime + 3 method subsections), §4.2 (AsyncLocalRuntime + 4 subsections), §4.3 (DistributedRuntime + Worker + TaskQueue), §4.4 (get_runtime factory), §4.5 (Return Structure Contract), §5.1 (CycleBuilder + methods), §5.2 (Convergence ABC + 3 implementations), §5.3 (CyclicWorkflowExecutor), §6.1 (RetryPolicy, RetryStrategy, CircuitBreakerConfig, configure_retry, configure_circuit_breaker, add_fallback, PersistentDLQ, DLQItem, exception allowlist), §7.1 (Exception hierarchy, 30+ classes), §7.3 (ContentAwareExecutionError + content-aware detection), §13 (Key Invariants).
**Verification source:** `src/kailash/{runtime,workflow,sdk_exceptions}.py`.

| Assertion | Method | Expected | Actual | Status |
|-----------|--------|----------|--------|--------|
| `class LocalRuntime` at `kailash.runtime.local` | grep | match | local.py:280 | OK |
| `class AsyncLocalRuntime(LocalRuntime)` at `kailash.runtime.async_local` | grep | match | async_local.py:430 | OK |
| `class DistributedRuntime(BaseRuntime)` at `kailash.runtime.distributed` | grep | match | distributed.py:449 | OK |
| `class BaseRuntime(ABC)` at `kailash.runtime.base` | grep | match | base.py:88 | OK |
| `class TaskQueue` at `kailash.runtime.distributed` | grep | match | distributed.py:151 | OK |
| `class Worker` at `kailash.runtime.distributed` | grep | match | distributed.py:582 | OK |
| `class ExecutionContext` at `kailash.runtime.async_local` | grep | match | async_local.py:87 | OK |
| `class ExecutionPlan` | grep | match | async_local.py:48 | OK |
| `class ExecutionLevel` | grep | match | async_local.py:39 | OK |
| `class ExecutionMetrics` | grep | match | async_local.py:76 | OK |
| `class ExecutionTracker` at `kailash.runtime.execution_tracker` | grep | match | execution_tracker.py:19 | OK |
| `class CancellationToken` at `kailash.runtime.cancellation` | grep | match | cancellation.py:31 | OK |
| `class CycleExecutionMixin` | grep | match | mixins/cycle_execution.py:33 | OK |
| `class ValidationMixin` | grep | match | mixins/validation.py:31 | OK |
| `class ConditionalExecutionMixin` | grep | match | mixins/conditional_execution.py:51 | OK |
| `def get_runtime(context=None, **kwargs)` factory | grep | match | runtime/__init__.py:45 | OK |
| `class CycleBuilder` at `kailash.workflow.cycle_builder` | grep | match | cycle_builder.py:58 | OK |
| `class CyclicWorkflowExecutor` | grep | match | cyclic_runner.py:136 | OK |
| `class CycleConnectionError` | grep | match | cycle_exceptions.py:194 | OK |
| `class ConvergenceCondition(ABC)` at `kailash.workflow.convergence` | grep | match | convergence.py:14 | OK |
| `class ExpressionCondition(ConvergenceCondition)` | grep | match | convergence.py:35 | OK |
| `class CallbackCondition(ConvergenceCondition)` | grep | match | convergence.py:116 | OK |
| `class MaxIterationsCondition(ConvergenceCondition)` | grep | match | convergence.py:147 | OK |
| `class RetryStrategy(Enum)` at `kailash.workflow.resilience` | grep | match | resilience.py:19 | OK |
| `class RetryPolicy` (dataclass) | grep | match | resilience.py:29 | OK |
| `class CircuitBreakerConfig` (dataclass) | grep | match | resilience.py:69 | OK |
| `class WorkflowResilience` mixin | grep | match | resilience.py:129 | OK |
| `class PersistentDLQ` at `kailash.workflow.dlq` | grep | match | dlq.py:66 | OK |
| `class DLQItem` | grep | match | dlq.py:33 | OK |
| `MAX_DLQ_ITEMS = 10_000` | grep | constant | dlq.py:23 | OK |
| `DEFAULT_BASE_DELAY = 60.0` | grep | float 60.0 | dlq.py:26 | OK |
| `class KailashException(Exception)` | grep | match | sdk_exceptions.py:77 | OK |
| `class NodeException(KailashException)` | grep | match | sdk_exceptions.py:82 | OK |
| `class NodeValidationError`, `NodeExecutionError`, `NodeConfigurationError`, `SafetyViolationError`, `CodeExecutionError` | grep | all 5 | sdk_exceptions.py:86, 96, 106, 116, 377 | OK |
| `class WorkflowException`, `WorkflowValidationError`, `WorkflowExecutionError`, `WorkflowCancelledError`, `CyclicDependencyError`, `ConnectionError`, `CycleConfigurationError`, `KailashWorkflowException` | grep | all 8 | sdk_exceptions.py:127, 131, 141, 406, 151, 159, 169, 399 | OK |
| `class RuntimeException`, `RuntimeExecutionError`, `ResourceLimitExceededError`, `CircuitBreakerOpenError`, `RetryExhaustedException` | grep | all 5 | sdk_exceptions.py:185, 189, 199, 210, 220 | OK |
| `class TaskException`, `TaskStateError` | grep | both | sdk_exceptions.py:260, 264 | OK |
| `class StorageException`, `KailashStorageError` | grep | both | sdk_exceptions.py:275, 279 | OK |
| `class ExportException`, `ImportException`, `ConfigurationException`, `KailashConfigError`, `ManifestError`, `CLIException`, `VisualizationError`, `TemplateError`, `KailashNotFoundException` | grep | all 9 | sdk_exceptions.py:291, 301, 312, 322, 330, 341, 352, 363, 388 | OK |
| `class ContentAwareExecutionError` | grep | match | local.py:148 | OK (see F-A-01) |
| `WorkflowCancelledError(WorkflowExecutionError)` | grep | inherits WorkflowExecutionError | sdk_exceptions.py:406 | OK |
| Default `LocalRuntime.connection_validation = "warn"` | Read | "warn" | constructor signature | OK |
| Default `LocalRuntime.conditional_execution = "route_data"` | Read | "route_data" | constructor signature | OK |

## F-A-01 — `core-runtime.md` § 7.1 / 7.3 — `ContentAwareExecutionError` parent-class drift

**Severity:** LOW
**Spec claim:** §7.3 says `ContentAwareExecutionError` is raised with `node_id` and `failure_data` attached, but the §7.1 exception hierarchy diagram does NOT include `ContentAwareExecutionError`. Spec implies (by structural placement under "RuntimeException" siblings) it should inherit from a `Kailash*` ancestor.
**Actual state:** `src/kailash/runtime/local.py:148` defines `class ContentAwareExecutionError(Exception)` — inherits from bare `Exception`, NOT `KailashException` or `RuntimeException`. The class is also not exported from `kailash.sdk_exceptions`.
**Remediation hint:** Either (a) add `ContentAwareExecutionError` to §7.1 hierarchy diagram with explicit `Exception` parent + note, or (b) re-parent the class to `RuntimeException` (or `KailashException`) and re-export from `kailash.sdk_exceptions` so callers can catch via the framework hierarchy.

**Spec 3 findings:** 0 CRIT / 0 HIGH / 0 MED / 1 LOW.

Note: Every spec-claimed runtime class, mixin, exception, and resilience primitive is present at the named module path. `get_runtime` factory present. Cycle and convergence primitives all present. The single LOW finding is documentation drift on `ContentAwareExecutionError`'s parent class.

---

# Spec 4: `specs/core-servers.md`

**Subsections audited:** §9.1 (WorkflowServer), §9.2 (DurableWorkflowServer), §9.3 (EnterpriseWorkflowServer), §9.4 (Server Hierarchy), §10.1 (create_gateway), §10.2 (Convenience Aliases), §11 (Deprecated and Removed APIs).
**Verification source:** `src/kailash/servers/{workflow_server,durable_workflow_server,enterprise_workflow_server,gateway,__init__}.py`.

| Assertion | Method | Expected | Actual | Status |
|-----------|--------|----------|--------|--------|
| `class WorkflowServer` at `kailash.servers.workflow_server` | grep | match | workflow_server.py:84 | OK |
| `class DurableWorkflowServer(WorkflowServer)` at `kailash.servers.durable_workflow_server` | grep | match | durable_workflow_server.py:37 | OK |
| `class EnterpriseWorkflowServer(DurableWorkflowServer)` | grep | match | enterprise_workflow_server.py:86 | OK |
| `def create_gateway(...)` factory | grep | match | gateway.py:19 | OK |
| `def create_enterprise_gateway(**kwargs)` | grep | match | gateway.py:150 | OK |
| `def create_durable_gateway(**kwargs)` | grep | match | gateway.py:161 | OK |
| `def create_basic_gateway(**kwargs)` | grep | match | gateway.py:172 | OK |
| `WorkflowServer.register_workflow(name, workflow)` | grep | match | workflow_server.py:580 | OK |
| `WorkflowServer.run(port=8000)` | grep | exists | workflow_server.py:752 — actual signature `run(host="127.0.0.1", port=8000, **kwargs)` | OK (see F-A-02) |
| `WorkflowGraph` deprecation alias | grep | DeprecationWarning | `kailash/__init__.py:30` raises DeprecationWarning naming v3.0.0 | OK |

## F-A-02 — `core-servers.md` § 9.1 — `WorkflowServer.run` missing `host` parameter in spec

**Severity:** LOW
**Spec claim:** §9.1 lists key method `run(port=8000)`.
**Actual state:** `src/kailash/servers/workflow_server.py:752` signature is `def run(self, host: str = "127.0.0.1", port: int = 8000, **kwargs)`. The `host` parameter is part of the public API but not documented.
**Remediation hint:** Update spec §9.1 to document `run(host="127.0.0.1", port=8000, **kwargs)` so users know how to override the bind host (production deployments typically bind to `0.0.0.0`).

**Spec 4 findings:** 0 CRIT / 0 HIGH / 0 MED / 1 LOW.

Note: All three server classes present with correct inheritance. All four gateway factory functions present. WorkflowGraph deprecation alias present. The single LOW finding is documentation incompleteness on `WorkflowServer.run`.

---

# Spec 5: `specs/infra-sql.md`

**Subsections audited:** Database Type Enum, Dialect System (Canonical Placeholder, Identifier Safety, JSON Path Validation, QueryDialect ABC, PostgresDialect, MySQLDialect, SQLiteDialect, detect_dialect), Connection Management (ConnectionManager + lifecycle + query + transactions + index creation), URL Resolution (resolve_database_url, resolve_queue_url), Credential Handling (preencode_password_special_chars, decode_userinfo_or_raise), Schema Migration (SCHEMA_VERSION, check/stamp), Database Execution Pipeline (5 stages + ExecutionContext + ExecutionResult + DatabaseExecutionPipeline), Migration Tooling (6 components), Concurrency Invariants, Error Handling.
**Verification source:** `src/kailash/{db,database,utils/url_credentials,migration}/`.

| Assertion | Method | Expected | Actual | Status |
|-----------|--------|----------|--------|--------|
| `class DatabaseType(Enum)` at `kailash.db.dialect` | grep | match | dialect.py:187 | OK |
| `class QueryDialect(ABC)` | grep | match | dialect.py:198 | OK |
| `class PostgresDialect(QueryDialect)` | grep | match | dialect.py:378 | OK |
| `class MySQLDialect(QueryDialect)` | grep | match | dialect.py:455 | OK |
| `class SQLiteDialect(QueryDialect)` | grep | match | dialect.py:550 | OK |
| `class IdentifierError(ValueError)` | grep | match | dialect.py:38 | OK |
| `def detect_dialect(url: str) -> QueryDialect` | grep | match | dialect.py:620 | OK |
| `def _validate_identifier(name, *, max_length=128)` | grep | match | dialect.py:72 | OK |
| `def _validate_json_path(path)` | grep | match | dialect.py:168 | OK |
| `class ConnectionManager` at `kailash.db.connection` | grep | match | connection.py:29 | OK |
| `def resolve_database_url() -> Optional[str]` at `kailash.db.registry` | grep | match | registry.py:31 | OK |
| `def resolve_queue_url() -> Optional[str]` | grep | match | registry.py:50 | OK |
| `def preencode_password_special_chars(connection_string)` at `kailash.utils.url_credentials` | grep | match | url_credentials.py:79 | OK |
| `def decode_userinfo_or_raise(parsed, *, default_user="root")` | grep | match | url_credentials.py:158 | OK |
| `SCHEMA_VERSION = 1` at `kailash.db.migration` | grep | int 1 | migration.py:32 | OK |
| `async def check_schema_version(conn)` (NOTE: spec elides `async`) | grep | exists | migration.py:35 | OK (see F-A-03) |
| `async def stamp_schema_version(conn, version=SCHEMA_VERSION)` | grep | exists | migration.py:62 | OK (see F-A-03) |
| `class ExecutionContext` at `kailash.database.execution_pipeline` | grep | match | execution_pipeline.py:21 | OK |
| `class ExecutionResult` at same module | grep | match | execution_pipeline.py:33 | OK |
| `class PermissionCheckStage(PipelineStage)` | grep | match | execution_pipeline.py:67 | OK |
| `class QueryValidationStage(PipelineStage)` | grep | match | execution_pipeline.py:111 | OK |
| `class QueryExecutionStage(PipelineStage)` | grep | match | execution_pipeline.py:176 | OK |
| `class DataMaskingStage(PipelineStage)` | grep | match | execution_pipeline.py:243 | OK |
| `class DatabaseExecutionPipeline` | grep | match | execution_pipeline.py:303 | OK |
| `class MigrationAssistant` at `kailash.migration` | grep | match | migration_assistant.py:63 | OK |
| `class CompatibilityChecker` | grep | match | compatibility_checker.py:69 | OK |
| `class PerformanceComparator` | grep | match | performance_comparator.py:83 | OK |
| `class ConfigurationValidator` | grep | match | configuration_validator.py:65 | OK |
| `class MigrationDocGenerator` | grep | match | documentation_generator.py:52 | OK |
| `class RegressionDetector` | grep | match | regression_detector.py:90 | OK |

## F-A-03 — `infra-sql.md` § Schema Migration — `check_schema_version` / `stamp_schema_version` are async, spec implies sync

**Severity:** LOW
**Spec claim:** §"Schema Migration" reads `check_schema_version(conn) -> Optional[int]` and `stamp_schema_version(conn, version=SCHEMA_VERSION)` with no `async` qualifier. A reader implementing against spec would expect a sync function returning `Optional[int]` directly.
**Actual state:** `src/kailash/db/migration.py:35` — `async def check_schema_version(conn: Any) -> Optional[int]`. Line 62 — `async def stamp_schema_version(conn: Any, version: int = SCHEMA_VERSION) -> None`.
**Remediation hint:** Add `async` to both signatures in spec text, since calling them without `await` returns a coroutine, not a value.

## F-A-04 — `infra-sql.md` § Schema Migration — `SCHEMA_VERSION` constant duplicated outside `db.migration`

**Severity:** LOW
**Spec claim:** Spec §"Schema Migration" identifies `SCHEMA_VERSION = 1` at `kailash.db.migration` as canonical. Spec implies single ownership.
**Actual state:** `SCHEMA_VERSION = 1` is also defined at `src/kailash/infrastructure/factory.py:39`, `src/kailash/trust/plane/store/postgres.py:65`, and `src/kailash/trust/plane/store/sqlite.py:53`. Multiple co-existing constants of the same name with the same value risk drift if any one is bumped.
**Remediation hint:** Decide whether infrastructure/trust modules should re-export from `kailash.db.migration` or maintain independent versioning. If independent, document each in the spec; if shared, refactor to import.

**Spec 5 findings:** 0 CRIT / 0 HIGH / 0 MED / 2 LOW.

Note: All dialect, connection management, credential handling, schema migration, execution pipeline, and migration tooling primitives present at spec-named module paths. Two LOW findings: `async` qualifier missing from spec for `check/stamp_schema_version`, and `SCHEMA_VERSION` constant duplication.

---

# Spec 6: `specs/infra-stores.md`

**Subsections audited:** Store Abstractions (CheckpointStore, EventStore, ExecutionStore + InMemory variant, IdempotencyStore, IdempotentExecutor, DLQ), Task Queue System (SQLTaskMessage, SQLTaskQueue), Worker Registry (SQLWorkerRegistry), Queue Factory (create_task_queue), Store Factory (StoreFactory + Level 0 backends).
**Verification source:** `src/kailash/infrastructure/`, `src/kailash/middleware/gateway/`.

| Assertion | Method | Expected | Actual | Status |
|-----------|--------|----------|--------|--------|
| `class DBCheckpointStore` at `kailash.infrastructure.checkpoint_store` | grep | match | checkpoint_store.py:37 | OK |
| `class DBEventStoreBackend` at `kailash.infrastructure.event_store` | grep | match | event_store.py:40 | OK |
| `EventStoreBackend = DBEventStoreBackend` alias | grep | match | event_store.py:263 | OK (see F-A-05) |
| `class DBExecutionStore` at `kailash.infrastructure.execution_store` | grep | match | execution_store.py:50 | OK |
| `class InMemoryExecutionStore` | grep | match | execution_store.py:280 | OK |
| `class DBIdempotencyStore` at `kailash.infrastructure.idempotency_store` | grep | match | idempotency_store.py:46 | OK |
| `class IdempotentExecutor` at `kailash.infrastructure.idempotency` | grep | match | idempotency.py:20 | OK |
| `class DBDeadLetterQueue` at `kailash.infrastructure.dlq` | grep | match | dlq.py:49 | OK |
| `class SQLTaskMessage` at `kailash.infrastructure.task_queue` | grep | match | task_queue.py:36 | OK |
| `class SQLTaskQueue` | grep | match | task_queue.py:92 | OK |
| `class SQLWorkerRegistry` at `kailash.infrastructure.worker_registry` | grep | match | worker_registry.py:33 | OK |
| `def create_task_queue(queue_url=None)` at `kailash.infrastructure.queue_factory` | grep | match | queue_factory.py | OK |
| `class StoreFactory` at `kailash.infrastructure.factory` | grep | match | factory.py:42 | OK |
| `class SqliteEventStoreBackend` (Level 0 backend, lazy import) | grep | match | middleware/gateway/event_store_sqlite.py:33 | OK |
| `class DiskStorage` (Level 0 checkpoint) | grep | match | middleware/gateway/checkpoint_manager.py:96 | OK |
| `SCHEMA_VERSION = 1` at `kailash.infrastructure.factory` | grep | int 1 | factory.py:39 | OK |

## F-A-05 — `infra-stores.md` § EventStore — `EventStoreBackend` name shadows a Protocol class

**Severity:** LOW
**Spec claim:** §EventStore declares `class DBEventStoreBackend (aliased as EventStoreBackend)` at `kailash.infrastructure.event_store`.
**Actual state:** `infrastructure/event_store.py:263` defines `EventStoreBackend = DBEventStoreBackend`. HOWEVER, `middleware/gateway/event_store_backend.py:20` also defines `class EventStoreBackend(Protocol)` — a typing protocol. The two co-exist with the same name, different semantics: one is the implementation alias, one is the structural-typing contract that `DBEventStoreBackend` satisfies. A reader importing `EventStoreBackend` may resolve either path depending on import order.
**Remediation hint:** Either (a) rename the Protocol to `EventStoreBackendProtocol` (PEP 544 convention), or (b) document the dual-symbol relationship in spec text and `event_store.py`'s module docstring so the relationship is explicit.

**Spec 6 findings:** 0 CRIT / 0 HIGH / 0 MED / 1 LOW.

Note: All store classes, task queue, worker registry, and factory primitives present at spec-named module paths. Single LOW finding: `EventStoreBackend` symbol-name collision between concrete-class alias and Protocol.

---
