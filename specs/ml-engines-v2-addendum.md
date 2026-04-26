# Kailash ML Engines — v2.0 Round-2 Addendum (Draft)

Version: 1.0.0 (draft)
Package: `kailash-ml`
Parent: `ml-engines-v2-draft.md` (v1.0 main spec; this file MUST be merged into it at integration time under the section numbers indicated below)
License: Apache-2.0

Status: DRAFT at `workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md`. This file is the enrichment pass closing every round-1 production finding that cuts across engines. Merge points are enumerated per clause; this file is NOT a standalone spec — it extends `ml-engines-v2-draft.md`.

Origin: `workspaces/kailash-ml-audit/04-validate/round-1-SYNTHESIS.md` themes T2 (0/18 engines auto-wire tracker) + T3 (tenant isolation absent from 13/13 engines) + T5 (two model registries) + T7 (industry parity sub-MLflow-1.0); `round-1-mlops-production.md` 13×Tracker + 13×Tenant matrices; `round-1-industry-competitive.md` §C scorecard. Split per `rules/specs-authority.md §8` (base file already >300 LOC — an addendum keeps each shard ≤500 LOC rather than ballooning the parent).

> **Wave 6.5 deferral note (2026-04-26):** This addendum cites `engine.fit_auto(...)` as a five-line Quick Start surface (§ E2.1, line 109). Per the Wave 6.5 spec realignment, `MLEngine.fit_auto()` is **not implemented** in kailash-ml 1.1.1 — see `ml-automl.md` § "Deferred to M2 milestone" entry D-fitauto. Callers today use `MLEngine.compare()` for family ranking and instantiate `kailash_ml.automl.AutoMLEngine` directly for HPO. The fit_auto facade lands in M2.

---

## Enrichment 1 — The 18-Engine × Tracker × Tenant × Actor Matrix

**Merge point:** `ml-engines-v2-draft.md §5` (Multi-Tenancy) — append as §5.3 "Engine Coverage Matrix".

### E1.1 Explicit Row Per Engine

This matrix is authoritative. Every row states the engine's auto-wire posture, the `tenant_id` kwarg, and the `actor_id` kwarg. No engine is silent on either column — an unspecified engine is a spec violation, not a default.

| Engine                 | Module                             | Ambient tracker auto-wire | Explicit `tracker=`? |  `tenant_id` kwarg  | `actor_id` kwarg | Primary mutation methods audited                                  |
| ---------------------- | ---------------------------------- | :-----------------------: | :------------------: | :-----------------: | :--------------: | ----------------------------------------------------------------- |
| `MLEngine`             | `engine.py`                        |             Y             |          Y           | Y (required for MT) |        Y         | `setup`, `fit`, `register`, `serve`, `predict`                    |
| `TrainingPipeline`     | `engines/training_pipeline.py`     |             Y             |          Y           |          Y          |        Y         | `train`                                                           |
| `ExperimentTracker`    | `engines/experiment_tracker.py`    |      is the tracker       |    is the tracker    |          Y          |        Y         | `create_experiment`, `create_run`, `log_metric`                   |
| `ModelRegistry`        | `engines/model_registry.py`        |             Y             |          Y           |          Y          |        Y         | `register_model`, `promote_model`, `demote_model`, `delete_model` |
| `FeatureStore`         | `engines/feature_store.py`         |             Y             |          Y           |          Y          |        Y         | `register_group`, `materialize`, `ingest`, `erase_tenant`         |
| `InferenceServer`      | `serving/server.py`                |             Y             |          Y           |          Y          |        Y         | `from_registry`, `start`, `predict`, `stop`                       |
| `DriftMonitor`         | `engines/drift_monitor.py`         |             Y             |          Y           |          Y          |        Y         | `set_reference_data`, `check_drift`, `schedule_monitoring`        |
| `AutoMLEngine`         | `engines/automl_engine.py`         |             Y             |          Y           |          Y          |        Y         | `run`, parent+nested run emission                                 |
| `HyperparameterSearch` | `engines/hyperparameter_search.py` |             Y             |          Y           |          Y          |        Y         | `search`, nested run emission                                     |
| `Ensemble`             | `engines/ensemble.py`              |             Y             |          Y           |          Y          |        Y         | `from_leaderboard`, `fit`                                         |
| `Preprocessing`        | `engines/preprocessing.py`         |             Y             |          Y           |          Y          |        Y         | `setup`, `transform` (auto-fit artifacts)                         |
| `FeatureEngineer`      | `engines/feature_engineer.py`      |             Y             |          Y           |          Y          |        Y         | `generate`, `select`, `rank`                                      |
| `ModelExplainer`       | `engines/model_explainer.py`       |             Y             |          Y           |          Y          |        Y         | `explain_global`, `explain_local`                                 |
| `DataExplorer`         | `engines/data_explorer.py`         |             Y             |          Y           |          Y          |        Y         | `profile`, `to_html`, `compare`                                   |
| `ModelVisualizer`      | `engines/model_visualizer.py`      |             Y             |          Y           |          Y          |        Y         | artifact emission to tracker                                      |
| `Clustering`           | `engines/clustering.py`            |             Y             |          Y           |          Y          |        Y         | `fit`, `predict`                                                  |
| `AnomalyDetection`     | `engines/anomaly_detection.py`     |             Y             |          Y           |          Y          |        Y         | `fit`, `score`, `flag`                                            |
| `DimReduction`         | `engines/dim_reduction.py`         |             Y             |          Y           |          Y          |        Y         | `fit`, `transform`                                                |

**Total: 18 engines; 18/18 auto-wire; 18/18 accept `tenant_id`; 18/18 accept `actor_id`.** A PR that lands a new engine MUST add a row to this table before merge.

### E1.2 MUST Rules

#### 1. Every Engine Reads The Ambient Tracker Via The Public Accessor

Every engine listed in E1.1 MUST call `kailash_ml.tracking.get_current_run()` (the public accessor per `ml-tracking §10.1` — CRIT-4) at the start of any mutation method. When present, mutations emit `log_metric` / `log_event` to that run automatically. When absent AND `tracker=` kwarg is None AND the operation is a mutation, the engine MUST emit one WARN log line stating "mutation outside tracked run" (not fatal — the user may intentionally operate outside tracking).

Direct access to the internal `kailash_ml.tracking.runner._current_run` `ContextVar` is BLOCKED for library callers — the accessor is the stable API. The `tracker=` kwarg on every engine MUST annotate `Optional[ExperimentRun]` (the user-visible async-context handle), NOT `Optional[ExperimentTracker]` (the underlying engine) — per HIGH-8.

```python
# DO — shared helper at engine construction time, public accessor
from kailash_ml.tracking import get_current_run

class ModelRegistry:
    def __init__(self, ..., *, tracker: Optional[ExperimentRun] = None, ...):
        self._tracker = tracker or get_current_run()    # public accessor (CRIT-4)

    async def register_model(self, ...):
        if self._tracker:
            await self._tracker.log_event(
                kind="model.registered", payload={...}
            )
        elif self._is_mutation_warn_enabled:
            logger.warning("ModelRegistry.register_model outside tracked run")

# DO NOT — internal ContextVar reach-through
from kailash_ml.tracking.runner import _current_run   # BLOCKED outside tracking package
self._tracker = tracker or _current_run.get()         # BLOCKED — use get_current_run()
```

**Why:** Round-1 matrix showed 0/18 auto-wire. Per-engine manual threading of `tracker=` is exactly the "dev hunts for API" pattern the Engine layer is meant to eliminate. Contextvar resolution is cheap (~50ns) and makes `with km.track(): engine.X` work everywhere without threading. The public accessor is the stable API — the internal ContextVar may be renamed in any future minor release.

#### 2. Every Engine's Public Mutation Signature Accepts `tenant_id` AND `actor_id`

Both kwargs are positionally-rejected keyword-only. The Engine propagates its own `tenant_id` / `actor_id` automatically; direct primitive users MUST pass both explicitly. Per `rules/tenant-isolation.md` Rule 2 and `rules/security.md`, missing values on multi-tenant engines raise typed errors — NOT silently fall back to `"default"`.

```python
# DO — explicit plumbing
await registry.register_model(
    training_result,
    tenant_id="acme",
    actor_id="agent:hpo-driver-42",
)

# DO NOT — positional; silent fallback
await registry.register_model(training_result, "acme")  # TypeError (keyword-only)
await registry.register_model(training_result)          # raises TenantRequiredError
```

---

## Enrichment 2 — `MLEngine` Top-Level Facade (Fluent Chain)

**Merge point:** `ml-engines-v2-draft.md §2.1` (MUST Rules) — insert as MUST 11 "Fluent Chain".

### E2.1 The 5-Line Newbie Flow

```python
import kailash_ml as km
import polars as pl

df = pl.read_csv("churn.csv")
async with km.track("churn-v1") as run:
    engine = km.MLEngine(tenant_id="acme", actor_id="alice@acme.com")
    result = await engine.setup(df, target="churned")
    leader = await engine.fit_auto(df, target="churned", time_budget=600)
    registered = await engine.register(leader.entries[0])
    served = await engine.serve(registered, channels=["rest", "mcp"])
```

Five lines. One context manager. One Engine. One tenant. Every call lands in the run.

### E2.2 MUST Rules

#### 1. `km.MLEngine(...)` Accepts `tenant_id=None` And `actor_id=None` At Construction

A single-tenant deployment MAY omit both; a multi-tenant deployment MUST supply both. A mismatch (engine with `tenant_id` set, call with `tenant_id=None`) raises `TenantRequiredError`.

#### 2. Every Method Returns `self` Where Chaining Is Allowed OR A Typed Dataclass

Mutation methods return a typed dataclass (TrainingResult, RegisterResult, ServeResult); pure configuration / state-setter helpers return `self` for chaining:

```python
# DO — fluent config
engine = (
    km.MLEngine(tenant_id="acme", actor_id="agent-42")
    .with_executor("ray")
    .with_retention_days(90)
    .with_retry_policy(max_retries=3)
)
result = await engine.fit(family="lightgbm")   # TrainingResult (not self)
```

#### 3. `NotImplementedError` Is BLOCKED In Production Code Paths

No method on `MLEngine` may raise `NotImplementedError`. The v0.9.x `engine.py:75-80` `_PHASE_3` / `_PHASE_4` / `_PHASE_5` scaffolds MUST be removed; unreachable branches are `rules/zero-tolerance.md` Rule 2 stubs.

---

## Enrichment 3 — Tenant & Actor Propagation Contracts

**Merge point:** `ml-engines-v2-draft.md §5` — insert as §5.4 "Propagation".

### E3.1 MUST Rules

#### 1. Constructing `MLEngine(tenant_id="acme")` Sets Engine-Level Default For Every Sub-Primitive

Every primitive the Engine constructs inherits `tenant_id="acme"`. No per-method re-specification is required. An explicit override on a method call takes precedence:

```python
engine = km.MLEngine(tenant_id="acme")
await engine.fit(family="lightgbm")                    # acme
await engine.fit(family="lightgbm", tenant_id="beta")  # beta (explicit override)
```

#### 2. Missing Context In Multi-Tenant Mode Raises At The Earliest Boundary

If the Engine is constructed with `tenant_id=None` (single-tenant) but a primitive is called with `tenant_id="acme"` (multi-tenant), the primitive MUST raise `TenantIsolationMismatchError` — mixing modes in one Engine is BLOCKED. The typed error points the user to instantiate a new Engine with a consistent tenant mode.

#### 3. `actor_id` Propagates Through Audit Rows, Not Cache Keys

`actor_id` is an audit dimension only; it MUST appear on every audit row (`_kml_*_audit` tables) but MUST NOT appear in cache keys (would explode cardinality and tie cached results to a single user).

---

## Enrichment 4 — Engine Lifecycle — The Canonical Newbie Flow

**Merge point:** `ml-engines-v2-draft.md §2` — insert as §2.4 "Lifecycle".

### E4.1 The Five-Step Flow

```
setup(df)       →  SetupResult       (profile, schema, split)
fit*(...)       →  TrainingResult    (trained Trainable + metrics)
diagnose(res)   →  DiagnosticsReport (plots + metrics auto-attached to run)
register(res)   →  RegisterResult    (ONNX export + registry row)
serve(reg)      →  ServeResult       (URIs for rest/mcp/grpc)
monitor(reg)    →  MonitorResult     (drift schedule activated)
```

The documented README starts here. Every example file under `examples/` MUST walk this flow in the same order.

### E4.2 MUST Rules

#### 1. `diagnose()` Is A First-Class Engine Method

Per the Round-1 SHARD-B2, `km.MLEngine.diagnose(result)` is the canonical one-line diagnostics dispatcher. It inspects the `TrainingResult.family` and routes to the appropriate `DLDiagnostics` / `RLDiagnostics` / classical diagnostic adapter, renders a plotly dashboard, AND emits every recorded metric/plot to the ambient `km.track()` run.

```python
async with km.track("churn-v1") as run:
    result = await engine.fit(family="lightgbm")
    dash = await engine.diagnose(result)   # dashboard + events to tracker
```

#### 2. `monitor()` Wires A Drift Schedule On The Registered Model

`engine.monitor(registered, interval_hours=24, alert_channels=["email"])` creates a `DriftMonitor` schedule on the tenant-scoped registry entry. The schedule row is persistent (per `ml-drift-draft.md`), not an in-process task.

---

## Enrichment 5 — `km.MLEngine.compare(families=[...])`

**Merge point:** `ml-engines-v2-draft.md §2.1 MUST 7` — extend with compare-family semantics.

### E5.1 Behavior

`engine.compare(families=["logreg", "random_forest", "xgboost", "lightgbm", "lightning_mlp"])` runs each family through Lightning (per §2.1 MUST 7), logs each as a nested run under the parent, builds a leaderboard, and returns a `ComparisonResult`. This is the engine-level primitive; `fit_auto` adds HPO on top.

### E5.2 Integration With AutoML + Tracker

- Every family fit becomes a nested tracker run whose `parent_run_id` is the parent `km.track()` context.
- `ComparisonResult.leaderboard` is a polars DataFrame with one row per family; persisted to `_kml_comparisons` for dashboard render.
- If `compare()` is invoked inside an `AutoMLEngine.run()`, it becomes part of the broader AutoML sweep (no duplicate runs).

---

## Enrichment 6 — Retention & TTL

**Merge point:** New `ml-engines-v2-draft.md §5.5` "Retention & Quotas".

### E6.1 Per-Engine Retention Policies

| Engine              | Retention target  | Default        | Kwarg on Engine                  |
| ------------------- | ----------------- | -------------- | -------------------------------- |
| `ModelRegistry`     | archived versions | 365 days       | `registry_retention_days`        |
| `FeatureStore`      | offline rows      | forever (None) | `feature_offline_retention_days` |
| `FeatureStore`      | online rows       | 86400 seconds  | `feature_online_ttl_seconds`     |
| `DriftMonitor`      | drift reports     | 90 days        | `drift_report_retention_days`    |
| `ExperimentTracker` | runs + artifacts  | 365 days       | `run_retention_days`             |
| `InferenceServer`   | request-log rows  | 30 days        | `request_log_retention_days`     |

### E6.2 MUST Rules

#### 1. Retention Is Tenant-Scoped

Every retention sweep filters by `tenant_id`. A GDPR erasure request (`engine.erase_tenant("acme", reason="...")`) triggers an immediate compaction across every store, persisted as an audit row with `actor_id`.

#### 2. Retention Defaults MUST NOT Be `None` For Audit-Material Tables

`_kml_*_audit` tables MUST NOT accept `retention_days=None` (forever). Audit tables have their own retention minimum of 1825 days (5 years) to satisfy typical audit/compliance regimes. The value is configurable UP from 1825 days but not BELOW.

---

## Enrichment 7 — Prometheus + OpenTelemetry

**Merge point:** New `ml-engines-v2-draft.md §5.6` "Observability".

### E7.1 Prometheus Metric Families

Every engine MUST emit at least the following Prometheus metric families via the shared `kailash_ml.metrics.registry`:

| Metric                                         | Type      | Labels                                            |
| ---------------------------------------------- | --------- | ------------------------------------------------- |
| `ml_operation_duration_seconds{engine,op}`     | Histogram | `engine`, `operation`, `tenant_bucket`            |
| `ml_operation_total{engine,op,outcome}`        | Counter   | `engine`, `operation`, `outcome`, `tenant_bucket` |
| `ml_inference_duration_seconds{model,version}` | Histogram | `model`, `version`, `tenant_bucket`               |
| `ml_inference_total{model,version,outcome}`    | Counter   | `model`, `version`, `outcome`                     |
| `ml_inference_cache_hit_total{model,version}`  | Counter   | `model`, `version`                                |
| `ml_drift_score{model,feature}`                | Gauge     | `model`, `feature`, `tenant_bucket`               |

### E7.2 MUST Rules

#### 1. Tenant Label Cardinality Is Bounded

Per `rules/tenant-isolation.md` MUST Rule 4, the `tenant_bucket` label emits the top-N tenants by traffic as `tenant_id`; others bucket as `"_other"`. Unbounded per-tenant label cardinality is BLOCKED.

#### 2. OpenTelemetry Spans Wrap Every Engine Method

Every public method on every engine MUST open an OTel span with attributes `engine.name`, `engine.op`, `tenant.id`, `actor.id`, `run.id`. Failed operations set span status to `ERROR` with the exception message.

#### 3. `/metrics` Endpoint On `InferenceServer`

When `InferenceServer.register_endpoints(app)` is called, a `GET /metrics` handler MUST be registered exposing the Prometheus registry. Absence is a `rules/observability.md` violation.

---

## Enrichment 8 — Resource Quotas

**Merge point:** New `ml-engines-v2-draft.md §5.7` "Quotas".

### E8.1 Per-Tenant Quota Dimensions

| Quota                          | Default per tenant | Backed by                                |
| ------------------------------ | ------------------ | ---------------------------------------- |
| `max_training_jobs_concurrent` | 4                  | `ProcessPoolExecutor` semaphore          |
| `max_storage_mb`               | 50000 (50GB)       | offline store + artifact store           |
| `max_inference_qps`            | 100                | `InferenceServer` rate-limit middleware  |
| `max_llm_cost_usd_per_day`     | 10.00              | AutoML agent + any LLM-augmented feature |
| `max_automl_trials_per_run`    | 500                | `AutoMLEngine.run()` hard cap            |

### E8.2 MUST Rules

#### 1. Quota Violations Raise `TenantQuotaExceededError`

Every quota is a hard gate. Crossing raises a typed error from the pertinent engine method. The error MUST name the quota, the current usage, and the cap.

#### 2. Quotas Are PACT-Integrated

`kailash-pact` governance envelopes MAY override the defaults above per dimension. A PACT-admitted tenant with a `max_llm_cost_usd_per_day=1000` envelope overrides the default 10.00 for that tenant.

---

## Enrichment 9 — RBAC & PACT Integration

**Merge point:** New `ml-engines-v2-draft.md §5.8` "RBAC".

### E9.1 `actor_id` → Clearance Lookup

Every mutation method calls `kailash_pact.GovernanceEngine.check_clearance(actor_id, resource, operation)` before acting. A denied clearance raises `ClearanceDeniedError(actor_id=, resource=, operation=, reason=)`.

### E9.2 D/T/R Declaration Per Method

Each engine method declares its D/T/R class (per `rules/pact-governance.md`):

| Method                                         | D   | T   | R     |
| ---------------------------------------------- | --- | --- | ----- |
| `MLEngine.fit()`                               | M   | L   | Agent |
| `MLEngine.register(stage="staging")`           | M   | M   | Agent |
| `MLEngine.register(stage="production")`        | H   | H   | Human |
| `MLEngine.serve(channels=["rest"])`            | M   | H   | Human |
| `ModelRegistry.promote_model(to="production")` | H   | H   | Human |
| `ModelRegistry.delete_model()`                 | H   | H   | Human |
| `FeatureStore.erase_tenant()`                  | H   | H   | Human |
| `DriftMonitor.schedule_monitoring()`           | M   | M   | Agent |

### E9.3 MUST Rules

#### 1. Clearance Lookup Happens Before Side Effect

The PACT check MUST complete before any database write / model load / endpoint registration. A denied check must leave system state unchanged.

#### 2. `actor_id` Is Always A Required Argument When PACT Is Active

When `kailash-pact` is installed AND `engine.pact_enforcement=True` (default under production), `actor_id` is mandatory on every mutation. Missing raises `ActorRequiredError`.

---

## Enrichment 10 — Cross-Engine Lineage

**Merge point:** New `ml-engines-v2-draft.md §5.9` "Lineage".

### E10.1 Linkage Contract

Every `TrainingResult` MUST carry:

- `run_id` — the ambient tracker run
- `feature_versions: dict[group, version_sha]` — what features were used
- `dataset_hash: str` — SHA of the training entity_df content
- `parent_run_id: str | None` — nested under an AutoML or HPO sweep if any

Every `RegisterResult` MUST carry the `TrainingResult`'s `run_id`, `feature_versions`, `dataset_hash`.

Every drift report MUST carry the `registered.model_uri` being monitored, plus the `feature_versions` it uses as reference.

### E10.2 Formal Dataclasses — `LineageGraph` / `LineageNode` / `LineageEdge`

The cross-engine lineage surface is three frozen dataclasses. `LineageNode` is one vertex (run / dataset / feature_version / model_version / deployment), `LineageEdge` is one directed edge with a typed `relation`, and `LineageGraph` is the rooted, tenant-scoped, depth-bounded result of `km.lineage(...)`. This is the canonical shape — every other spec that serializes lineage (`ml-dashboard-draft.md §4.1`, `ml-registry-draft.md`, any future REST / SSE / CLI surface) MUST import this shape, not redefine it.

```python
# Module: kailash_ml.engines.lineage
from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime

@dataclass(frozen=True)
class LineageNode:
    """Single node in a cross-engine lineage graph."""
    id: str                          # unique identifier (run_id / dataset_hash / feature_version / model_version_uuid)
    kind: Literal[
        "run",                       # an ExperimentRun (the training or AutoML pass)
        "dataset",                   # a registered training/eval dataset (identified by SHA)
        "feature_version",           # a FeatureStore group@version
        "model_version",             # a ModelRegistry entry at a specific version
        "deployment",                # an InferenceServer registration (channel endpoint)
    ]
    label: str                       # human-readable label (e.g. "training run #42", "User:v3")
    tenant_id: str                   # per `rules/tenant-isolation.md` — every node tenant-scoped (never None)
    created_at: datetime
    metadata: dict[str, str] = field(default_factory=dict)  # arbitrary key/value pairs, redacted per classification

@dataclass(frozen=True)
class LineageEdge:
    """Directed edge in lineage graph."""
    source_id: str
    target_id: str
    relation: Literal[
        "produced_by",               # model_version produced_by run
        "consumed",                  # run consumed dataset
        "used_features",             # run used_features feature_version
        "deployed_as",               # deployment deployed_as model_version
        "derived_from",              # feature_version derived_from dataset
        "evaluated_against",         # model_version evaluated_against dataset (test set)
    ]
    occurred_at: datetime

@dataclass(frozen=True)
class LineageGraph:
    """Cross-engine lineage graph — `km.lineage(run_id | model_version | dataset_hash)`.

    Canonical shape. `ml-dashboard-draft.md §4.1` REST endpoint
    `/api/v1/lineage/{run_id}` returns the JSON serialization of this
    dataclass (nodes: tuple[LineageNode, ...], edges: tuple[LineageEdge, ...]).
    """
    root_id: str                     # the queried node (run_id / model_version / dataset_hash)
    nodes: tuple[LineageNode, ...]
    edges: tuple[LineageEdge, ...]
    computed_at: datetime
    max_depth: int = 10              # bounded traversal (guards against cyclic and deep graphs)
```

### E10.3 MUST Rules

#### 1. Lineage Is Queryable In One Call

`km.lineage(model_uri_or_run_id_or_dataset_hash, *, tenant_id: str | None = None, max_depth=10)` returns a `LineageGraph` containing (subject to the `max_depth` bound). Per `ml-tracking.md §10.2`, `tenant_id=None` resolves to the ambient `get_current_tenant_id()` value; multi-tenant engines without ambient context raise `TenantRequiredError` per `rules/tenant-isolation.md` — matching every sibling `km.*` verb's default-None contract.

- the registered model_version node
- the training run that produced it
- the feature_version nodes consumed
- the dataset node(s) — training + eval — identified by `dataset_hash`
- the deployment node(s) (serving endpoints)
- active drift-monitor deployments (as `deployment` nodes with `metadata["role"]="drift_monitor"`)
- downstream model_versions (if this model is an input to another)

#### 2. Lineage Query Is Tenant-Scoped

Cross-tenant lineage reads raise `CrossTenantReadError` per `rules/tenant-isolation.md`. Every `LineageNode.tenant_id` MUST equal the caller's `tenant_id` argument.

#### 3. One Canonical Shape Across Specs

`LineageGraph` + `LineageNode` + `LineageEdge` are declared ONCE in this file. `ml-dashboard-draft.md §4.1` and any future lineage-emitting spec MUST import and reference this canonical shape rather than redefining `{nodes: list[...], edges: list[...]}` ad-hoc. Redefinition of the shape in sibling specs is a HIGH finding under `rules/specs-authority.md §5b` (full-sibling-spec re-derivation).

#### 4. Tier 2 Wiring Test

Per `rules/facade-manager-detection.md`, the lineage surface MUST have a Tier 2 wiring test:

- `tests/integration/engines/test_lineage_graph_cross_engine_wiring.py` — constructs a real MLEngine flow (train → register → serve → monitor), invokes `km.lineage(registered.model_uri, tenant_id="acme")`, and asserts the returned `LineageGraph` contains one node of each kind (`run`, `dataset`, `feature_version`, `model_version`, `deployment`) AND edges connecting them via the canonical relations (`produced_by`, `consumed`, `used_features`, `deployed_as`).

---

## Enrichment 11 — Engine Registry (Programmatic Discovery)

**Merge point:** New `ml-engines-v2-draft.md §2.5` "Engine Registry".

### E11.1 Discovery API — Formal Dataclasses

The registry surface is three frozen dataclasses: `ParamSpec` (single positional/keyword argument), `MethodSignature` (one public method), `EngineInfo` (one engine's full contract). All three are `@dataclass(frozen=True)` so the registry values are hashable and safe to cache in agent tool descriptors.

```python
# Module: kailash_ml.engines.registry
from dataclasses import dataclass, field
from typing import Literal, Optional

@dataclass(frozen=True)
class ParamSpec:
    """Single parameter of a public method signature — kailash_ml.engines.registry."""
    name: str
    annotation: str                  # stringified type annotation (e.g. "polars.DataFrame", "Optional[str]")
    default: Optional[str]           # stringified default value; "<NO_DEFAULT>" sentinel when arg is positional-required
    kind: Literal[
        "positional_or_keyword",
        "keyword_only",
        "var_positional",            # *args
        "var_keyword",               # **kwargs
    ]

@dataclass(frozen=True)
class MethodSignature:
    """Complete public-method signature — kailash_ml.engines.registry."""
    method_name: str
    params: tuple[ParamSpec, ...]    # tuple (not list) for immutability; position-ordered
    return_annotation: str           # stringified return type (e.g. "TrainingResult", "None")
    is_async: bool
    is_deprecated: bool = False
    deprecated_since: Optional[str] = None   # semver string, e.g. "0.12.0"
    deprecated_removal: Optional[str] = None # semver string, e.g. "2.0.0"

# D/T/R are axes (Data / Transform / Ride) per Decision 12 + `rules/pact-governance.md`.
# L/M/H are levels-on-an-axis per §E9.2 (Low / Medium / High).
# The previous flat Literal["D", "T", "R", "DTR"] conflated axis labels with level
# labels; the nested shape below makes the distinction explicit.
ClearanceLevel = Literal["L", "M", "H"]
ClearanceAxis = Literal["D", "T", "R"]

@dataclass(frozen=True)
class ClearanceRequirement:
    """One axis + minimum level pair — see §E9.2 for axis/level semantics."""
    axis: ClearanceAxis
    min_level: ClearanceLevel

@dataclass(frozen=True)
class EngineInfo:
    """Agent-discoverable engine metadata — `km.engine_info(name)` / `km.list_engines()`."""
    name: str                        # e.g. "TrainingPipeline", "InferenceServer"
    version: str                     # semver string; MUST match `packages/kailash-ml/pyproject.toml::version`
    module_path: str                 # dotted import path, e.g. "kailash_ml.engines.training_pipeline"
    accepts_tenant_id: bool
    emits_to_tracker: bool
    # Empty tuple = no clearance required. Each entry pairs ONE axis (D/T/R per
    # Decision 12) with its minimum required level (L/M/H per §E9.2).
    clearance_level: Optional[tuple[ClearanceRequirement, ...]]
    signatures: tuple[MethodSignature, ...]   # Per-engine public-method count — varies per §E1.1 (MLEngine=8, support engines 1-4). Decision 8 is Lightning lock-in, NOT a method-count invariant. See §E11.3 MUST 4.
    extras_required: tuple[str, ...] = ()     # e.g. ("dl",) per Decision 13 hyphen convention
```

An engine method that requires "Medium data clearance + Low transform clearance" declares:

```python
clearance_level = (
    ClearanceRequirement(axis="D", min_level="M"),
    ClearanceRequirement(axis="T", min_level="L"),
)
```

See §E9.2 for the L/M/H level semantics and Decision 12 for the D/T/R axis semantics.

```python
# Usage — Kaizen agents / human developers
engines = km.list_engines()
# tuple[EngineInfo, ...] — one entry per engine listed in §E1.1 above
# (MLEngine, TrainingPipeline, ExperimentTracker, ModelRegistry, FeatureStore,
#  InferenceServer, DriftMonitor, AutoMLEngine, HyperparameterSearch, Ensemble,
#  Preprocessing, FeatureEngineer, ModelExplainer, DataExplorer, ModelVisualizer,
#  Clustering, AnomalyDetection, DimReduction)

info = km.engine_info("TrainingPipeline")
# EngineInfo(
#     name="TrainingPipeline",
#     version="1.0.0",
#     module_path="kailash_ml.engines.training_pipeline",
#     accepts_tenant_id=True,
#     emits_to_tracker=True,
#     clearance_level=(      # from §E9.2 D/T/R table: MLEngine.fit() = D:M, T:L
#         ClearanceRequirement(axis="D", min_level="M"),
#         ClearanceRequirement(axis="T", min_level="L"),
#     ),
#     signatures=(
#         MethodSignature(
#             method_name="train",
#             params=(
#                 ParamSpec(name="data", annotation="polars.DataFrame",
#                           default="<NO_DEFAULT>", kind="positional_or_keyword"),
#                 ParamSpec(name="target", annotation="str",
#                           default="<NO_DEFAULT>", kind="keyword_only"),
#                 ParamSpec(name="tenant_id", annotation="Optional[str]",
#                           default="None", kind="keyword_only"),
#                 ParamSpec(name="actor_id", annotation="Optional[str]",
#                           default="None", kind="keyword_only"),
#                 # ...
#             ),
#             return_annotation="TrainingResult",
#             is_async=True,
#         ),
#     ),
#     extras_required=(),
# )
```

### E11.2 Top-Level Helpers — `km.list_engines()` / `km.engine_info()`

Two module-level async-safe helpers MUST live in `kailash_ml/engines/registry.py` and MUST be re-exported from `kailash_ml/__init__.py`:

```python
def list_engines() -> tuple[EngineInfo, ...]:
    """Return all registered engines as an immutable tuple.

    Registry is populated at import-time via the `@register_engine` decorator
    applied to each engine class in `kailash_ml/engines/*.py`. Order is
    insertion-order (stable across Python ≥3.7).
    """

def engine_info(name: str) -> EngineInfo:
    """Lookup a single engine by class name.

    Raises `EngineNotFoundError` (subclass of `MLError`) when the name is
    not in the registry. The error message MUST list the available engine
    names (tuple of `list_engines()` names) to guide discovery.
    """
```

### E11.3 MUST Rules

#### 1. Discovery Is The Single Source Of Truth For Agent Tools

Kaizen agents that call ML functionality MUST obtain the method signatures via `km.engine_info()`, not hard-coded imports. This keeps agent tool contracts in sync with the Engine API surface automatically.

#### 2. Every Registered Engine Has An `EngineInfo` Dataclass Entry

The registry is populated at import-time by decorator. An engine without an `EngineInfo` entry is not discoverable — and therefore not available to agents — so forgetting the decorator is a loud failure, not a silent one.

#### 3. `EngineInfo.version` Tracks The Package Version Atomically

`EngineInfo.version` MUST equal `kailash_ml.__version__` at import time (and therefore equal `packages/kailash-ml/pyproject.toml::version`). Per `rules/zero-tolerance.md Rule 5`, split-version states are BLOCKED — the registry decorator MUST read `kailash_ml.__version__` rather than hardcode.

#### 4. Tier 2 Wiring Test

Per `rules/facade-manager-detection.md`, the registry MUST have a Tier 2 wiring test:

- `tests/integration/engines/test_engine_registry_signature_discovery.py` — asserts `list_engines()` returns all **18 engines** enumerated in §E1.1 (MLEngine + 17 support engines: TrainingPipeline, ExperimentTracker, ModelRegistry, FeatureStore, InferenceServer, DriftMonitor, AutoMLEngine, HyperparameterSearch, Ensemble, Preprocessing, FeatureEngineer, ModelExplainer, DataExplorer, ModelVisualizer, Clustering, AnomalyDetection, DimReduction) AND every `EngineInfo.signatures` tuple contains the **per-engine public-method count specified in §E1.1** (varies per engine — MLEngine's 8-method surface per Decision 8 is a per-engine invariant, NOT a fixed "8 per engine" constraint across all 18). Any engine whose `len(signatures)` diverges from its §E1.1 row is a §5b cross-spec drift violation.

---

## Enrichment 12 — Industry Parity (Engine Composition + Auto-Wire)

**Merge point:** `ml-engines-v2-draft.md §7` (PyCaret/MLflow-Better Claims) — append as §7.3.

### E12.1 Composition + Auto-Wire Matrix

| Capability                          | kailash-ml 1.0.0              | Kubeflow       | MLflow               | Ray                           | SageMaker         |
| ----------------------------------- | ----------------------------- | -------------- | -------------------- | ----------------------------- | ----------------- |
| Single Engine facade                | Y (`MLEngine`)                | N (pipelines)  | N (multiple clients) | N (Train/Tune/Serve separate) | N (separate SDKs) |
| Engine auto-wires to tracker        | Y (contextvar)                | Partial        | Y (autolog)          | Y (callbacks)                 | Y (auto)          |
| Engine auto-wires to feature store  | Y (contextvar)                | Partial        | Partial              | Partial                       | Y                 |
| Engine auto-wires to model registry | Y (contextvar)                | Y              | Y                    | Y\*                           | Y                 |
| Engine auto-wires to drift monitor  | Y (`engine.monitor()`)        | Partial        | Partial              | N                             | Y                 |
| One-call multi-channel serve        | Y (`channels=[...]`)          | Partial (gRPC) | Partial (REST)       | Y (Serve)                     | Partial           |
| Polars-native                       | Y                             | N              | N                    | N                             | N                 |
| ONNX-default                        | Y                             | N              | N                    | N                             | Partial           |
| Agent-augmented AutoML              | Y (unique)                    | N              | N                    | N                             | N                 |
| EATP governance envelope            | Y (unique via `kailash-pact`) | N              | N                    | N                             | N                 |

**Position:** Engine facade + contextvar auto-wire is the categorical differentiator. Kubeflow / MLflow / Ray / SageMaker each require the user to wire N primitives together; kailash-ml collapses that to a 5-line flow.

---

## Enrichment 13 — Cross-Engine E2E Test Contract

**Merge point:** `ml-engines-v2-draft.md §7.2` (Claim-to-Test Mapping) — append.

### E13.1 Mandatory E2E Test

`tests/integration/test_mlengine_lifecycle_e2e.py` MUST exist and MUST:

1. Enter a `km.track("e2e-lifecycle")` context.
2. Construct `km.MLEngine(tenant_id="test-acme", actor_id="ci-runner")`.
3. Call `engine.setup(df, target="label")`.
4. Call `engine.fit(family="lightgbm")`.
5. Call `engine.diagnose(result)`.
6. Call `engine.register(result)`.
7. Call `engine.serve(registered, channels=["rest"])`.
8. POST /predict and read a response.
9. Call `engine.monitor(registered, interval_hours=24)`.
10. Assert every one of these 18 engines has emitted at least one row to the shared tracker DB: `MLEngine`, `TrainingPipeline`, `ExperimentTracker`, `ModelRegistry`, `FeatureStore`, `InferenceServer`, `DriftMonitor`, plus every support engine the flow actually touched.
11. Assert the shared tracker DB contains `tenant_id="test-acme"` on every row (multi-tenant enforcement verified end-to-end).
12. Assert the model's `LineageGraph` (via `km.lineage(registered.model_uri, tenant_id=engine.tenant_id)`) contains: training run_id, feature versions, dataset_hash, and serving endpoint URI. Note: `km.lineage` is the canonical top-level wrapper per `ml-engines-v2-draft.md §15.8`; the engine instance has no `.lineage()` method (the eight-method `MLEngine` surface per §2.1 MUST 5 is `setup`/`compare`/`fit`/`predict`/`finalize`/`evaluate`/`register`/`serve` only).
13. Assert Prometheus `/metrics` response contains `ml_inference_total{model="...",outcome="success"}` counter ≥ 1.

### E13.2 MUST Rules

#### 1. This E2E Is A Merge Gate

`test_mlengine_lifecycle_e2e.py` is the single highest-leverage regression test in the package. It MUST run on every PR (not gated by slow-test marker). Any PR that breaks it is BLOCKED from merging.

#### 2. Per-Engine Tracker Emission Is Asserted Mechanically

The test grep-asserts that `run.list_events(kind="<engine>.<op>")` returns ≥1 for each expected engine/op pair. A silent regression where one engine stops emitting is caught here; round-1 audit's 0/18 coverage would have been caught on day one with this test.

---

## Enrichment 14 — Merge Instructions

When this addendum is merged into `ml-engines-v2-draft.md`:

1. **E1 → §5.3 (Engine Coverage Matrix)** — after §5.2 Audit Row Contract.
2. **E2 → §2.1 MUST 11 (Fluent Chain)** — after §2.1 MUST 10.
3. **E3 → §5.4 (Propagation)**.
4. **E4 → §2.4 (Lifecycle)** — after §2.3.
5. **E5 → §2.1 MUST 7 extension** — inline.
6. **E6 → §5.5 (Retention & Quotas)**.
7. **E7 → §5.6 (Observability)**.
8. **E8 → §5.7 (Quotas)**.
9. **E9 → §5.8 (RBAC)**.
10. **E10 → §5.9 (Lineage)**.
11. **E11 → §2.5 (Engine Registry)**.
12. **E12 → §7.3 (Composition + Auto-Wire Industry Matrix)**.
13. **E13 → §7.2 + new §7.4 (E2E Test Contract)**.
14. **E14** — remove this section; integration note for the editor.

After merge, update `ml-engines-v2-draft.md §12 Conformance Checklist` to include every new MUST clause added above. The conformance checklist MUST reach 25+ items after merge (currently 17).

---

## Cross-References (additions)

- `ml-feature-store-draft.md` — FeatureStore tenant / actor plumbing (aligned via E1, E3).
- `ml-automl-draft.md` — AutoML nested-run discipline + agent audit (aligned via E1, E9).
- `ml-tracking-draft.md` — contextvar-based ambient tracker (E1 MUST 1 binding).
- `ml-drift-draft.md` — `DriftMonitor.schedule_monitoring` is PACT-governed (E9).
- `rules/tenant-isolation.md` — authoritative for tenant_id plumbing; E1 enforces on every engine.
- `rules/observability.md` — Mandatory Log Points §1-4 — E7 enforces at the engine layer.
- `rules/pact-governance.md` — D/T/R declarations per method (E9.2).
- `rules/orphan-detection.md` + `rules/facade-manager-detection.md` — E1 + E13 close the orphan failure modes for every engine.

---

_End of ml-engines-v2-addendum-draft.md_
