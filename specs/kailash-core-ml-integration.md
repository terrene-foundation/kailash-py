# Kailash Core × kailash-ml Integration — Protocols Expansion, MLError Hierarchy, Tracking Migrations, Workflow Nodes, Observability

Version: 1.0.0 (draft)
Package: `kailash`
Target release: **kailash 2.9.0** (shipping in the kailash-ml 1.0.0 wave)
Status: DRAFT at `workspaces/kailash-ml-audit/supporting-specs-draft/kailash-core-ml-integration-draft.md`. Promotes to `specs/kailash-core-ml-integration.md` after round-3 convergence.
Supersedes: none — this is a net-new kailash-core surface that kailash-ml 1.0.0 and the other wave packages consume.
Parent domain: Kailash Core SDK.
Sibling specs: `specs/core-runtime.md`, `specs/core-nodes.md`, `specs/core-workflows.md`, `specs/diagnostics-catalog.md`.

Origin: kailash 2.9.0 is the foundation of the wave release. The `src/kailash/diagnostics/protocols.py` module is the cross-SDK authored contract for `Diagnostic`, `TraceEvent`, `TraceEventFingerprint`, and (new in 2.9.0) `RLDiagnostic`-specific methods. `src/kailash/ml/errors.py` centralises the 11-family `MLError` hierarchy that every `kailash-ml` engine throws and every sibling wave-package catches. Migration helpers at `src/kailash/tracking/migrations/` land the 0.17.0 → 1.0.0 table renames. Closes round-1 themes T5 (two registries) and T6 (spec-to-code drift — the typed-exception gap) structurally by moving the error hierarchy OUT of `kailash-ml` into `kailash` so every downstream package shares it.

---

## 1. Scope + Non-Goals

### 1.1 In Scope

Five net-new core surfaces shipped in kailash 2.9.0:

1. **`src/kailash/diagnostics/protocols.py` expansion** — add `RLDiagnostic` Protocol with `record_episode`, `record_eval`, `record_policy_step`, plus `DiagnosticReport` frozen dataclass with `{schema_version: "1.0", events, summary, rollup}`.
2. **`src/kailash/ml/errors.py` (NEW module)** — `MLError` + 11-family hierarchy per approved-decisions.md implications. Cross-SDK parity with kailash-rs.
3. **`src/kailash/tracking/migrations/` (NEW module)** — numbered migration helpers for 0.17.0 → 1.0.0 (status vocabulary, table consolidation, keyspace reshape).
4. **`kailash.workflow.nodes.ml` — ML-specific workflow nodes** — `MLTrainingNode`, `MLInferenceNode`, `MLRegistryPromoteNode`, each consuming the new tracker and the MLError hierarchy.
5. **`kailash.observability.ml` — OTel/Prometheus hook module** — standard counters (`kailash_ml_train_duration_seconds`, `kailash_ml_inference_latency_ms`, `kailash_ml_drift_alerts_total`) with bounded-cardinality labels.

### 1.2 Out of Scope (Owned By Sibling Specs)

- Core workflow API (`WorkflowBuilder`) → `specs/core-workflows.md`.
- Local/Async runtime internals → `specs/core-runtime.md`.
- Node-catalog documentation → `specs/node-catalog.md`.
- DataFlow integration → `dataflow-ml-integration-draft.md`.
- Nexus propagation → `nexus-ml-integration-draft.md`.
- Kaizen adapter contract → `kaizen-ml-integration-draft.md`.
- PACT governance methods → `pact-ml-integration-draft.md`.
- The 15 `ml-*-draft.md` specs (kailash-ml itself).

### 1.3 Non-Goals

- **No breaking changes to existing `Diagnostic` Protocol.** `RLDiagnostic` is a NEW Protocol that extends the concept; existing adapters (`AgentDiagnostics`, `DLDiagnostics`) remain unchanged.
- **No centralised error hierarchy beyond ML.** DataFlow, Nexus, Kaizen, PACT, Align each keep their own base errors. Only `kailash-ml` and its downstream consumers use `MLError`.
- **No replacement for `WorkflowBuilder`.** ML workflow nodes are new entries in the node catalog, not a new orchestration layer.

---

## 2. `src/kailash/diagnostics/protocols.py` Expansion

### 2.1 Existing surface (unchanged)

Per `specs/diagnostics-catalog.md`, 2.8.x already ships:

- `Diagnostic` Protocol (`open`, `close`, `report`, `__enter__`, `__exit__`).
- `TraceEvent`, `TraceEventType`, `TraceEventStatus` dataclasses.
- `compute_trace_event_fingerprint(event) -> str` (returns `sha256:<8hex>` per approved-decisions.md Decision 3 discipline).
- `JudgeCallable` Protocol (used by kaizen.judges).

### 2.2 New: `RLDiagnostic` Protocol

```python
# src/kailash/diagnostics/protocols.py
from typing import Protocol, runtime_checkable, ClassVar, Optional, Mapping

@runtime_checkable
class RLDiagnostic(Protocol):
    """Diagnostic adapter specialised for reinforcement-learning runs.
    Satisfied by both classical RL (SB3/d3rlpy wrappers) and RLHF
    (kailash-align adapters) — the shared cross-family surface for metric
    emission in RL training loops."""

    name: ClassVar[str]

    def record_episode(
        self,
        *,
        step: int,
        episode_reward: float,
        episode_length: int,
        metrics: Optional[Mapping[str, float]] = None,
    ) -> None:
        """Record end-of-episode summary. `metrics` carries ad-hoc env info."""

    def record_eval(
        self,
        *,
        step: int,
        mean_reward: float,
        std_reward: float,
        n_episodes: int,
    ) -> None:
        """Record periodic evaluation results."""

    def record_policy_step(
        self,
        *,
        step: int,
        policy_loss: float,
        value_loss: Optional[float] = None,
        entropy: Optional[float] = None,
        kl_from_ref: Optional[float] = None,
    ) -> None:
        """Record per-optimizer-step policy metrics (classical PPO/SAC + RLHF DPO/PPO)."""
```

`RLDiagnostic` IS a `Diagnostic` — the conformance is structural, not nominal. An implementation satisfying both `Diagnostic` and the three new methods satisfies `RLDiagnostic` at runtime.

### 2.3 New: `DiagnosticReport` frozen dataclass

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass(frozen=True)
class DiagnosticReport:
    """Standardised result returned by `Diagnostic.report()`. Frozen so
    the report can be safely shared across threads / serialized."""
    schema_version: Literal["1.0"]          # locks deserialization contract
    events: tuple[TraceEvent, ...]          # immutable sequence
    summary: Mapping[str, float]            # numeric aggregates (counts, p50/p95, etc.)
    rollup: Mapping[str, str]               # string aggregates (status, winner, etc.)
    tenant_id: Optional[str] = None
    actor_id: Optional[str] = None
```

**MUST**: `schema_version` is a `Literal["1.0"]` — kailash 2.9.0 locks the report shape so downstream consumers (dashboards, cross-SDK subscribers) deserialize safely. A 2.0 bump requires a new literal (`Literal["2.0"]`) + forward-compat shims.

### 2.4 Cross-SDK parity

The same three `record_*` method names MUST exist on the kailash-rs side at `crates/kailash/src/diagnostics/protocols.rs` as a trait. Parity targets:

- Same method names and argument names.
- Same fingerprint format (`sha256:<8hex>`).
- Same `DiagnosticReport` serialized shape (`schema_version`, `events`, `summary`, `rollup`).

Cross-SDK follow-up is deferred until kailash-rs scopes the `DiagnosticReport` trait at `crates/kailash/src/diagnostics/protocols.rs`. The shape above is the parity contract — a future Rust-side issue may be filed when the trait is proposed. No tracking issue required until Rust-side scoping begins.

---

## 3. `src/kailash/ml/errors.py` — MLError Hierarchy

### 3.1 Module location rationale

Placing the error hierarchy at `kailash.ml.errors` (inside kailash-core) rather than `kailash_ml.errors` (inside kailash-ml) means:

- Every wave package (kailash-nexus, kailash-kaizen, kailash-align, kailash-dataflow, kailash-pact) can catch `MLError` without depending on kailash-ml.
- Cross-SDK parity is simpler — kailash-rs's `kailash/src/ml/errors.rs` sits in the analogous place.
- kailash-ml re-exports `MLError` from `kailash.ml.errors` so `from kailash_ml.errors import MLError` continues to work.

### 3.2 Full hierarchy (11 families + 2 cross-cutting per approved-decisions.md)

The authoritative tree is also rendered in `ml-tracking-draft.md §9.1.1` (canonical hierarchy diagram). In case of disagreement between this file and `ml-tracking §9.1`, `ml-tracking` wins — this file is the kailash-core-level module location + re-export contract, not a second source of truth for the hierarchy shape.

```python
# src/kailash/ml/errors.py

class MLError(Exception):
    """Base class for every exception raised by kailash-ml or its
    downstream consumers on ML-lifecycle code paths."""

# --- 11 domain families (one per spec) ---

class TrackingError(MLError):
    """Raised by ExperimentTracker, SQLiteStorageDriver, or the migration
    helpers. Subclasses: RunNotFoundError, ExperimentNotFoundError,
    MetricValueError, ParamValueError, TenantRequiredError,
    ActorRequiredError, AliasNotFoundError, ErasureRefusedError,
    ArtifactEncryptionError, ArtifactSizeExceededError,
    LineageRequiredError, ModelSignatureRequiredError,
    InvalidTenantIdError, MigrationImportError, TrackerStoreInitError."""

class AutologError(MLError):
    """Raised by km.autolog() instrumentation. Subclasses:
    AutologNoAmbientRunError, AutologUnknownFrameworkError."""

class RLError(MLError):
    """Raised by RL primitives. Subclasses:
    RLEnvIncompatibleError, RLPolicyShapeMismatchError,
    ReplayBufferUnderflowError, RewardModelRequiredError,
    FeatureNotYetSupportedError, RLBridgeImportError (see align spec)."""

class BackendError(MLError, RuntimeError):
    """Raised by device detection / backend-compat-matrix loading.
    Multi-inherits RuntimeError so 0.x `except RuntimeError` callers
    continue to catch. Subclasses: UnsupportedPrecision,
    UnsupportedFamily."""

class DriftMonitorError(MLError):
    """Raised by DriftMonitor. Subclasses: ReferenceNotFoundError,
    InsufficientSamplesError, DriftThresholdError."""

class InferenceServerError(MLError):
    """Raised by InferenceServer. Subclasses: ModelLoadError,
    InvalidInputSchemaError, RateLimitExceededError,
    TenantQuotaExceededError, ShadowDivergenceError,
    OnnxExportUnsupportedOpsError (D1 shard)."""

class ModelRegistryError(MLError):
    """Raised by ModelRegistry. Subclasses: ModelNotFoundError,
    AliasOccupiedError, CrossTenantLineageError,
    ImmutableGoldenReferenceError (D3 shard),
    TenantQuotaExceededError."""

class FeatureStoreError(MLError):
    """Raised by FeatureStore. Subclasses: FeatureNotFoundError,
    StaleFeatureError, PointInTimeViolationError,
    TenantQuotaExceededError."""

class AutoMLError(MLError):
    """Raised by AutoMLEngine. Subclasses: BudgetExhaustedError,
    InsufficientTrialsError, EnsembleFailureError."""

class DiagnosticsError(MLError):
    """Raised by DL/RL/Agent Diagnostics. Subclasses:
    DLDiagnosticsStateError, SeedReportError."""

class DashboardError(MLError):
    """Raised by MLDashboard. Subclasses: UnknownTenantError,
    AuthorizationError, LiveStreamError, RateLimitExceededError,
    RunNotFoundInDashboardError."""

# --- 2 cross-cutting errors (Decision 8 + Decision 12) ---

class UnsupportedTrainerError(MLError):
    """Raised by MLEngine.fit() when a Trainable's fit() bypasses
    L.Trainer (Decision 8 — hard Lightning lock-in). Inherits
    directly from MLError (NOT from any single domain family);
    engines + AutoML + RL importers re-export from
    kailash_ml.errors. See ml-engines-v2-draft.md §3.2 MUST 2."""

class MultiTenantOpError(MLError):
    """Raised by any primitive that performs a cross-tenant admin
    operation without PACT D/T/R clearance (registry export/import,
    feature-store snapshot, serving shadow across tenants, tracking
    cross-tenant compare). Inherits directly from MLError (NOT from
    ModelRegistryError alone) — cross-tenant surface spans every
    domain. ml-registry-pact.md (post-1.0) subclasses
    MultiTenantOpError without a kailash-ml dependency because the
    canonical class lives in kailash-core. See Decision 12."""
```

### 3.3 `MultiTenantOpError` — Decision 12 (cross-cutting)

Per approved-decisions.md Decision 12, cross-tenant admin operations raise `MultiTenantOpError` in 1.0.0 (cross-tenant surface is gated post-1.0). `MultiTenantOpError` lives in `kailash.ml.errors` so `ml-registry-pact.md` (post-1.0) can subclass it without a kailash-ml dependency.

**Inheritance:** `class MultiTenantOpError(MLError)` — directly under `MLError`, NOT under `ModelRegistryError` alone. The rationale is that cross-tenant admin ops surface across every kailash-ml domain:

- **Registry** — `export_tenant_snapshot()` / `import_tenant_snapshot()` (see `ml-registry-draft.md §13`).
- **Feature store** — `export_tenant_snapshot()` / `import_tenant_snapshot()` on a FeatureGroup (see `ml-feature-store-draft.md §12`).
- **Serving** — cross-tenant `predict_with_shadow()` and cross-tenant model mirror without PACT D/T/R clearance (see `ml-serving-draft.md §12`).
- **Tracking** — cross-tenant run compare in `kailash_ml.tracking` admin API (gated post-1.0).

Scoping `MultiTenantOpError` under a single domain would force callers to catch different typed errors per call path; promoting it to a top-level sibling of the families means `except MultiTenantOpError` catches every cross-tenant refusal uniformly, and `except MLError` continues to catch everything.

**Re-export symmetry:** kailash-ml re-exports `MultiTenantOpError` via `kailash_ml.errors` AND the sibling module roots so every spec that raises the error also publishes it in its own `__all__` — per `rules/orphan-detection.md §6`, eager re-export only. No lazy `__getattr__`.

### 3.4 Error message discipline

Every MLError subclass MUST:

- Carry a human-readable `reason` string.
- Carry structured context: `tenant_id`, `actor_id`, `resource_id` (when relevant) as attributes.
- NEVER echo classified payload fields verbatim (per `rules/event-payload-classification.md` §2). Use `sha256:<8hex>` fingerprint in error messages that reference classified content.

```python
# DO — structured + fingerprinted
raise ModelPromotionRefusedError(
    reason="no DTR clearance for production tier",
    tenant_id="tenant-alice",
    actor_id="agent-42",
    model_name="churn_v7",
)
# repr → ModelPromotionRefusedError(reason='no DTR clearance for production tier',
#                                    tenant_id='tenant-alice', actor_id='agent-42',
#                                    model_name='churn_v7')

# DO NOT — verbatim classified payload
raise ModelPromotionRefusedError(f"features contained {record['email']}")  # BLOCKED
```

### 3.5 Re-export from kailash-ml

```python
# packages/kailash-ml/src/kailash_ml/errors.py
from kailash.ml.errors import (
    # Root
    MLError,
    # 11 domain families
    TrackingError, AutologError, RLError, BackendError,
    DriftMonitorError, InferenceServerError, ModelRegistryError,
    FeatureStoreError, AutoMLError, DiagnosticsError, DashboardError,
    # 2 cross-cutting errors (Decision 8 + Decision 12)
    UnsupportedTrainerError,
    MultiTenantOpError,
    # TrackingError sub-types (15 total — see ml-tracking §9.1)
    TenantRequiredError, ActorRequiredError,
    RunNotFoundError, ExperimentNotFoundError,
    MetricValueError, ParamValueError,
    AliasNotFoundError, ErasureRefusedError,
    ArtifactEncryptionError, ArtifactSizeExceededError,
    LineageRequiredError, ModelSignatureRequiredError,
    InvalidTenantIdError, MigrationImportError, TrackerStoreInitError,
    # ... all other family subclasses per ml-tracking §9.1.1 tree ...
)
__all__ = [
    "MLError",
    "TrackingError", "AutologError", "RLError", "BackendError",
    "DriftMonitorError", "InferenceServerError", "ModelRegistryError",
    "FeatureStoreError", "AutoMLError", "DiagnosticsError", "DashboardError",
    "UnsupportedTrainerError",
    "MultiTenantOpError",
    "TenantRequiredError", "ActorRequiredError",
    "RunNotFoundError", "ExperimentNotFoundError",
    "MetricValueError", "ParamValueError",
    "AliasNotFoundError", "ErasureRefusedError",
    "ArtifactEncryptionError", "ArtifactSizeExceededError",
    "LineageRequiredError", "ModelSignatureRequiredError",
    "InvalidTenantIdError", "MigrationImportError", "TrackerStoreInitError",
    # ... all other family subclasses ...
]
```

Eager re-export (not lazy `__getattr__`) per `rules/orphan-detection.md` §6 — every `__all__` entry resolves at module scope. `UnsupportedTrainerError` + `MultiTenantOpError` are explicitly listed at the top-level (NOT buried inside a family subclass block) because they are direct MLError children, not family sub-types.

---

## 4. `src/kailash/tracking/migrations/` — 0.17.0 → 1.0.0 Migration Helpers

### 4.1 Module contents

```
src/kailash/tracking/migrations/
    __init__.py
    _base.py                              MigrationBase (abstract)
    v1_0_0_rename_status.py               COMPLETED/SUCCESS → FINISHED
    v1_0_0_merge_legacy_stores.py         Consolidate 0.x alternate paths into ~/.kailash_ml/ml.db
    v1_0_0_delete_sqlitetrackerbackend.py Remove legacy class imports
    v1_0_0_reshape_keyspace.py            Legacy cache keys → kailash_ml:v1:{tenant_id}:... form
    registry.py                           Numbered migration registry
```

### 4.2 `MigrationBase` contract

```python
# src/kailash/tracking/migrations/_base.py
from abc import ABC, abstractmethod

class MigrationBase(ABC):
    version: ClassVar[str]  # e.g. "1.0.0"
    name: ClassVar[str]     # e.g. "rename_status"

    @abstractmethod
    async def apply(self, *, tenant_id: Optional[str] = None, dry_run: bool = False) -> MigrationResult:
        """Apply the migration. Returns a frozen MigrationResult dataclass.
        Idempotent — re-running yields the same result once applied."""

    @abstractmethod
    async def verify(self) -> bool:
        """Verify the migration has been applied. Returns bool."""
```

### 4.3 `MigrationResult` frozen dataclass

```python
@dataclass(frozen=True)
class MigrationResult:
    version: str
    name: str
    applied_at: datetime
    rows_migrated: int
    tenant_id: Optional[str]
    was_dry_run: bool
```

### 4.4 Key invariants

- `rename_status` MUST use a transactional bulk UPDATE with bounded row count per transaction (10_000 rows per txn chunk to avoid WAL bloat on large SQLite stores).
- `merge_legacy_stores` MUST detect 0.x alternate-path DBs (e.g. `sqlite:///kailash-ml.db`) via a documented probe set, copy their rows into `~/.kailash_ml/ml.db`, then leave the legacy file UNTOUCHED (rename to `*.migrated.0.17.bak` for rollback recovery).
- `reshape_keyspace` applies to Redis/cache backends ONLY IF they are configured and accessible; otherwise it is a no-op with a DEBUG log line.
- All migrations acquire a POSIX file lock on `~/.kailash_ml/.migration.lock` BEFORE any write to prevent two processes racing on first-install.
- Dry-run mode (`dry_run=True`) reports projected row counts without writing.

### 4.5 Discovery + execution

`km doctor migrate --to=1.0.0` (CLI) walks the registry, finds pending migrations, applies them in version order. Failed migrations halt the sequence with a typed `MigrationFailedError(MLError)` and leave a recovery hint.

---

## 5. `kailash.workflow.nodes.ml` — ML-Specific Workflow Nodes

### 5.1 Node catalogue

Three new string-name-addressable nodes:

| Node name               | Purpose                                 | Required params                                                        |
| ----------------------- | --------------------------------------- | ---------------------------------------------------------------------- |
| `MLTrainingNode`        | Train a model via kailash-ml engines    | `engine`, `schema`, `model_spec`, `eval_spec`, `tenant_id`, `actor_id` |
| `MLInferenceNode`       | Run batch inference via InferenceServer | `model_name`, `version`, `input_ref`, `tenant_id`                      |
| `MLRegistryPromoteNode` | Promote a model through registry tiers  | `model_name`, `from_tier`, `to_tier`, `tenant_id`, `actor_id`          |

### 5.2 Workflow pattern

```python
# DO — string-based node registration (per kailash-py CLAUDE.md Critical Execution Rules)
from kailash.workflow import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("MLTrainingNode", "train_churn", {
    "engine": "sklearn.ensemble.RandomForestClassifier",
    "schema": churn_schema,
    "model_spec": {...},
    "eval_spec": {"metrics": ["accuracy", "f1"]},
    "tenant_id": tenant,
    "actor_id": actor,
})
workflow.add_node("MLRegistryPromoteNode", "promote", {
    "model_name": "churn_v3",
    "from_tier": "staging",
    "to_tier": "production",
    "tenant_id": tenant,
    "actor_id": actor,
})
workflow.connect("train_churn", "promote", mapping={"model.name": "model_name"})
```

### 5.3 Tracker consumption

Every ML node MUST:

1. Read the ambient `km.track()` run via `kailash_ml.tracking.get_current_run()` (compat layer per `nexus-ml-integration-draft.md` §2.3).
2. If ambient run exists, wrap the node's execute() in a child run spawned via `km.track(name=<node_id>, parent_run_id=...)`.
3. Emit the result via the child run's primitives.
4. Raise `MLError` subclasses (not generic `RuntimeError`) on failure.

### 5.4 String-based registration

Per kailash-py CLAUDE.md § "Critical Execution Rules", ML nodes are registered by string name in `kailash.workflow.nodes.ml.__init__.py` via the standard node-registration decorator. Backward-compat with `runtime.execute(workflow.build())` return shape `(results, run_id)` is preserved.

---

## 6. `kailash.observability.ml` — OTel / Prometheus Hooks

### 6.1 Standard counters

```python
# kailash.observability.ml
from prometheus_client import Counter, Histogram

kailash_ml_train_duration_seconds = Histogram(
    "kailash_ml_train_duration_seconds",
    "Training duration per engine, per tier",
    labelnames=["engine_name", "model_name", "tenant_id_bucket"],  # bounded cardinality
    buckets=(1, 5, 30, 60, 300, 900, 1800, 3600, 7200, 14400),
)

kailash_ml_inference_latency_ms = Histogram(
    "kailash_ml_inference_latency_ms",
    "Inference latency per model, per version",
    labelnames=["model_name", "version", "tenant_id_bucket"],
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500),
)

kailash_ml_drift_alerts_total = Counter(
    "kailash_ml_drift_alerts_total",
    "Drift alerts by feature, by severity",
    labelnames=["feature_name", "severity", "tenant_id_bucket"],
)
```

### 6.2 Bounded-cardinality discipline

Per `rules/tenant-isolation.md` §4, `tenant_id` is NEVER an unbounded label. The `tenant_id_bucket` dimension uses top-N + `"_other"` bucketing (N=100 default, configurable via `KAILASH_ML_METRICS_TOP_TENANTS` env var).

### 6.3 OTel bridge

`kailash.observability.ml.otel_bridge` exports the same metrics via OpenTelemetry SDK using the same metric names and labels. Operators who run a Prom+OTel stack see identical names in both surfaces.

### 6.4 No-op fallback

When `prometheus_client` is NOT installed, the counters are silent no-ops with a loud startup WARN: `"prometheus_client not installed; kailash_ml metrics are silent. Install kailash[observability] to enable."` (mirrors `rules/zero-tolerance.md` Rule 2 "no silent fake metrics").

---

## 7. Error Taxonomy — Complete List

Per §3.2 above, plus:

| Error                        | Family             | Raised when                                            |
| ---------------------------- | ------------------ | ------------------------------------------------------ |
| `MigrationFailedError`       | `TrackingError`    | A migration's `apply()` raises or `verify()` fails     |
| `ProtocolConformanceError`   | `DiagnosticsError` | An adapter fails `isinstance(adapter, RLDiagnostic)`   |
| `WorkflowNodeMLContextError` | `MLError`          | An ML node can't find an ambient tracker when required |

All new errors ship in kailash 2.9.0.

---

## 8. Test Contract

### 8.1 Tier 1 (unit)

- `test_rl_diagnostic_protocol_runtime_checkable.py` — a minimal adapter satisfies `isinstance(..., RLDiagnostic)`.
- `test_diagnostic_report_frozen_schema_version_locked.py` — can't mutate `.schema_version` on a frozen report.
- `test_ml_error_hierarchy_inheritance.py` — every 11 families correctly descend from `MLError`.
- `test_rename_status_migration_idempotent.py` — apply twice → second run is a no-op.
- `test_prometheus_fallback_silent_warn.py` — simulate missing `prometheus_client` → WARN at startup.

### 8.2 Tier 2 (integration wiring)

File naming per `rules/facade-manager-detection.md` §2:

- `tests/integration/test_diagnostic_report_serialization_roundtrip_wiring.py` — real report emitted, serialized, deserialized.
- `tests/integration/test_rename_status_migration_wiring.py` — real SQLite DB with 0.x legacy rows → migration → every row has `status` in `{RUNNING, FINISHED, FAILED, KILLED}`.
- `tests/integration/test_merge_legacy_stores_wiring.py` — two legacy stores + migration → single consolidated store, legacy files renamed to `.migrated.0.17.bak`.
- `tests/integration/test_ml_training_node_emits_to_tracker_wiring.py` — WorkflowBuilder with `MLTrainingNode` + ambient `km.track()` → metric row appears.
- `tests/integration/test_ml_registry_promote_node_wiring.py` — promotion with mandatory `tenant_id` + `actor_id` → audit row written.

### 8.3 Regression tests

- `tests/regression/test_issue_NNN_migration_lockfile_contention.py` — two concurrent processes attempting first-install migration → one acquires lock, other blocks.
- `tests/regression/test_issue_NNN_diagnostic_report_schema_version_frozen.py` — cannot mutate `schema_version`.
- `tests/regression/test_issue_NNN_ml_error_no_classified_payload_echo.py` — raising `ModelPromotionRefusedError` with classified context does not leak verbatim payload.

---

## 9. Cross-SDK Parity Requirements

Every surface ships with kailash-rs 3.18.0 parity targets:

- `kailash/src/diagnostics/protocols.rs` — `RLDiagnostic` trait with same method names.
- `kailash/src/ml/errors.rs` — `MLError` enum with same 11 family variants.
- `kailash/src/tracking/migrations/` — same version-numbered migrations.
- `kailash/src/observability/ml.rs` — same Prometheus metric names, same bounded-cardinality discipline.

Cross-SDK follow-up is deferred until kailash-rs scopes the corresponding Rust modules. kailash-rs does maintain ML crates today (`kailash-ml`, `kailash-ml-core`, `kailash-ml-metrics`) but the observability + tracking parity contract above is post-1.0 scope. A Rust-side parity issue will be filed when the Rust modules are proposed; until then, this spec is the parity baseline.

---

## 10. Industry Comparison

| Capability                                   | kailash 2.9.0 | kubeflow metadata | mlflow tracking DB | Flyte core | zenml core |
| -------------------------------------------- | ------------- | ----------------- | ------------------ | ---------- | ---------- |
| Cross-SDK shared Diagnostic Protocol         | Y             | N                 | N                  | N          | N          |
| Versioned frozen DiagnosticReport schema     | Y             | N                 | Partial            | Partial    | N          |
| Centralised ML error hierarchy (11 families) | Y             | N                 | Partial            | Partial    | N          |
| Numbered migrations with POSIX lockfile      | Y             | Partial           | Partial            | N          | N          |
| Bounded-cardinality tenant labels on metrics | Y             | N                 | N                  | N          | N          |
| ML workflow nodes consuming ambient tracker  | Y             | N                 | N                  | Partial    | Partial    |

**Position:** kailash 2.9.0 is the only core SDK that ships an ML-aware Protocol expansion, centralised error hierarchy, AND numbered migration helpers as first-class core primitives — every downstream wave package (ml, pact, nexus, kaizen, align, dataflow) inherits the same contract.

---

## 11. Migration Path (kailash 2.8.x → 2.9.0)

2.8.x users:

- `src/kailash/diagnostics/protocols.py` — existing `Diagnostic`, `JudgeCallable`, `TraceEvent` unchanged. New `RLDiagnostic`, `DiagnosticReport` are ADDITIVE.
- `src/kailash/ml/` — NEW subpackage. No migration for non-ml users.
- `src/kailash/tracking/migrations/` — NEW subpackage. No-op for non-ml users.
- `kailash.workflow.nodes.ml` — NEW nodes. Existing workflows unaffected.
- `kailash.observability.ml` — NEW module. Existing observability unchanged.

No breaking changes. All additions gated on the `kailash-ml` installation (imports fail loud if ml-specific surfaces are called without the ml package installed).

---

## 12. Release Coordination Notes

Part of the kailash-ml 1.0.0 wave release (see `pact-ml-integration-draft.md` §10 for the full wave list).

**Release order position: FIRST.** Every other wave package depends on kailash 2.9.0 (for `MLError`, `RLDiagnostic`, `DiagnosticReport`). kailash 2.9.0 MUST ship before any other package in the wave.

**Parallel-worktree ownership:** The repo-root version owner (NOT a sub-package specialist) owns `pyproject.toml` + `src/kailash/__init__.py::__version__` + `CHANGELOG.md`. Every wave-package agent's prompt MUST exclude these repo-root files.

---

## 13. Cross-References

- kailash-ml specs consuming this surface:
  - `ml-tracking-draft.md` §8 — typed exception list; all now re-exported from `kailash.ml.errors`.
  - `ml-rl-core-draft.md` — `RLDiagnostic` Protocol consumption.
  - `ml-rl-align-unification-draft.md` — `RLDiagnostic` + `MLError.RLError` shared surface.
  - `ml-engines-v2-draft.md` — `MLTrainingNode` / `MLInferenceNode` / `MLRegistryPromoteNode` wire to the engine surface.
- Other wave-package specs:
  - `pact-ml-integration-draft.md`, `nexus-ml-integration-draft.md`, `kaizen-ml-integration-draft.md`, `align-ml-integration-draft.md`, `dataflow-ml-integration-draft.md`.
- Core companion specs:
  - `specs/diagnostics-catalog.md` — existing catalogue; kailash 2.9.0 adds `RLDiagnostic` + `DiagnosticReport`.
  - `specs/core-workflows.md` — workflow builder surface; ML nodes register via standard pattern.
  - `specs/core-nodes.md` — node catalogue (new ML entries).
- Rule references:
  - `rules/orphan-detection.md` §6 — `__all__` hygiene for `kailash.ml.errors`.
  - `rules/event-payload-classification.md` §2 — fingerprint discipline in error messages.
  - `rules/tenant-isolation.md` §4 — bounded Prometheus label cardinality.
  - `rules/facade-manager-detection.md` §2 — Tier 2 wiring tests for migrations.
  - `rules/zero-tolerance.md` Rule 2 — no silent-fake-metrics discipline.
