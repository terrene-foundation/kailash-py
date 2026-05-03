# Kailash ML Feature Store Specification (v1.0 Draft)

Version: 1.0.0 (draft)
Package: `kailash-ml`
Parent domain: ML Lifecycle (see `ml-engines-v2-draft.md` for `MLEngine` composition; `ml-tracking-draft.md` for runs/registry; `ml-drift-draft.md` for monitoring)
License: Apache-2.0
Python: >=3.11
Owner: Terrene Foundation (Singapore CLG)

Status: DRAFT at `workspaces/kailash-ml-audit/specs-draft/ml-feature-store-draft.md`. Becomes `specs/ml-feature-store.md` after human review. Supersedes the feature-store sections of `ml-engines.md v0.9.x §1.1`.

Origin: Round-1 MLOps audit `workspaces/kailash-ml-audit/04-validate/round-1-mlops-production.md` HIGH "FeatureStore single-tenant only, no online/offline split, no feature-group concept" + industry-competitive audit Section C #13 "Feature store with offline+online parity". Closes round-1 CRIT T3 (tenant isolation absent from 13/13 engines) for the feature-store primitive.

---

## 1. Scope

### 1.1 In Scope

This spec is authoritative for:

- **Offline feature store** — bulk historical storage backed by a SQL dialect (Postgres, DuckDB, SQLite) for training/backtesting reads.
- **Online feature store** — low-latency key-value storage (Redis default; DynamoDB and MemoryDB acceptable adapters) for serving reads (sub-10ms p95).
- **Point-in-time joins** — training retrieval that returns the feature value correct `as_of` a supplied timestamp, per entity, without leakage.
- **Feature definition** — `@feature` decorator wrapping polars expressions; type-inferred; version-pinned; TTL; lineage capture.
- **Feature groups** — named collections of features sharing an entity key, access control, and ownership — the primitive AutoML and Training read against.
- **Materialization** — batch compute from source (DataFlow query, polars DataFrame, file) to offline store; streaming sync offline → online.
- **Feature versioning** — every feature spec change produces a new version pinned by content SHA and tracked in the registry.
- **Tenant isolation** — storage keys, query filters, audit rows all carry `tenant_id`; cross-tenant reads raise `TenantRequiredError`.
- **Drift integration** — feature distributions hooked into `DriftMonitor` so monitoring runs against live online-store snapshots.
- **Lineage** — every TrainingResult carries `feature_version` + `entity_snapshot_hash` for reproducibility.

### 1.2 Out of Scope

- **Feature engineering DSL** beyond polars expressions — advanced window / rolling / aggregate semantics live in `kailash-dataflow`.
- **Streaming infrastructure** (Kafka, Flink) — the online store consumes materialization writes; upstream streaming is user's concern.
- **Data cataloging UI** — covered by `MLDashboard` (ml-tracking/dashboard) at the inventory tab; this spec owns the API, not the UI shell.
- **ETL / bulk ingestion** — `DataFlow` owns that; `FeatureStore.ingest(df)` accepts a pre-computed DataFrame.

---

## 2. Construction

### 2.1 MUST Rules

#### 1. Single-Line Construction With Explicit Stores

`FeatureStore` MUST accept both offline and online store URLs at construction. Zero-arg construction is BLOCKED for this primitive — feature storage location is a deliberate operational choice.

```python
# DO — explicit stores, tenant explicit
from kailash_ml import FeatureStore

fs = FeatureStore(
    store="postgresql://user:pass@host:5432/ml",  # offline
    online="redis://cache:6379/0",                # online (optional)
    tenant_id="acme",
)
await fs.initialize()

# DO — engine propagates tenant
engine = km.Engine(store="postgresql://...", tenant_id="acme")
# engine.feature_store has tenant_id="acme" automatically

# DO NOT — zero-arg on the bare primitive
fs = FeatureStore()  # TypeError; operator must state the store explicitly
```

**Why:** The v0.9.x `FeatureStore(conn, table_prefix="kml_feat_")` shape required a pre-built `ConnectionManager`, discouraged tenant passage, and hid that online/offline parity was not supported. Explicit `store=` + `online=` makes every deployment answer both questions at construction.

Store-URL resolution for BOTH the `store=` (offline) and `online=` (online) kwargs routes through `kailash_ml._env.resolve_store_url(explicit=...)` per `ml-engines-v2.md §2.1 MUST 1b` (single shared helper; hand-rolled `os.environ.get(...)` is BLOCKED per `rules/security.md` § Multi-Site Kwarg Plumbing). When the caller passes an explicit URL (e.g. `store="postgresql://..."`, `online="redis://..."`), the helper returns it unchanged; when the caller passes `None` (offline store) or omits `online=`, the helper applies the `KAILASH_ML_STORE_URL` / per-backend env var / canonical default precedence chain so offline and online URL resolution share the same single enforcement point and cannot drift.

#### 2. Constructor Signature

```python
class FeatureStore:
    def __init__(
        self,
        store: str | ConnectionManager,         # REQUIRED: offline store URL
        *,
        online: str | OnlineStoreAdapter | None = None,  # Redis URL or adapter
        tenant_id: str | None = None,
        table_prefix: str = "_kml_feat_",
        registry: FeatureRegistry | None = None,
        ttl_online_seconds: int = 86400,        # default 24h TTL on online rows
    ) -> None: ...

    async def initialize(self) -> None: ...   # idempotent; creates tables/keys
```

#### 3. `initialize()` MUST Be Idempotent

Calling `initialize()` on a fresh instance MUST create required SQL tables + Redis key namespaces. Calling it again on an already-initialized store MUST be a no-op.

**Why:** Notebook users re-run setup cells; non-idempotent initialize throws on the second call and blocks the happy path.

---

## 3. Feature Definition

### 3.1 `@feature` Decorator

Every feature MUST be defined via `@feature` on a Python function that returns a polars `Expr` or `Series`. The decorator captures dtype, dependencies, version (content SHA), and TTL.

```python
# DO — polars-native feature definition
from kailash_ml import feature
import polars as pl

@feature(
    entity="user_id",
    dtype=pl.Float64,
    ttl=3600,           # seconds; online-store eviction target
    description="Mean purchase value over the user's trailing 30 days.",
)
def avg_purchase_30d(df: pl.LazyFrame) -> pl.Expr:
    return (
        df.filter(pl.col("event_time") >= pl.col("as_of") - pl.duration(days=30))
        .group_by("user_id")
        .agg(pl.col("amount").mean().alias("avg_purchase_30d"))
    )

# DO NOT — pandas expressions
@feature(entity="user_id", dtype="float64")
def avg_purchase_30d(df: pd.DataFrame) -> pd.Series:  # BLOCKED
    return df.groupby("user_id")["amount"].mean()
```

**Why:** Polars is the internal data currency of kailash-ml (`ml-engines-v2-draft.md §1.1`). Accepting pandas would force a conversion boundary inside the feature pipeline, doubling memory for the largest operation in the system.

### 3.2 MUST Rules

#### 1. Every Feature Has An Entity Key

Every `@feature` MUST declare `entity="..."` naming the primary entity column (e.g. `user_id`, `session_id`, `device_id`). Features without entity keys are BLOCKED — they cannot participate in point-in-time joins.

#### 2. Feature Version Is Content-Addressed

The feature version MUST be the first 12 hex chars of `sha256(decorator_kwargs || inspect.getsource(fn) || py_version || polars_version || numpy_version || blas_backend)`. Two feature specs with byte-identical source, decorator kwargs, AND numeric library versions MUST produce the same version; any source OR library change MUST produce a new version.

```python
# DO — deterministic versioning including the numeric-library stack
feature_version = sha256(
    f"{sorted(decorator_kwargs)}"
    f"|{getsource(fn)}"
    f"|{sys.version_info[:2]}"
    f"|polars={polars.__version__}"
    f"|numpy={numpy.__version__}"
    f"|blas={detected_blas_backend}"        # "openblas" | "mkl" | "accelerate" | None
    .encode()
).hexdigest()[:12]
# avg_purchase_30d@a3f1c2d9b4e5
```

**Why:** Registry lineage (`TrainingResult.feature_versions`) must be reproducible. Source+kwargs alone miss BLAS-backend drift (OpenBLAS vs MKL changes sum-of-product order → 1-ULP float drift on 1B-row aggregates) and polars/numpy version drift (aggregation algorithm changes between minor versions). The expanded hash input binds the feature-version to the exact numeric substrate — matching `km.seed()` SeedReport fields (`ml-engines-v2.md §11.2 MUST 5`).

#### 3. TTL Applies To Online Store, Not Offline

`ttl=3600` means the online-store row expires after 3600 seconds. Offline rows are retained until an explicit `retention_days` policy expires them (see §8). Mixing TTL semantics between stores is BLOCKED.

---

## 4. Feature Groups

### 4.1 Purpose

A `FeatureGroup` is a named collection of features sharing an entity, ownership, and access policy. Training reads a group; serving reads a group. Groups — not individual features — are the atomic unit of versioning and access control.

```python
from kailash_ml import FeatureGroup

group = FeatureGroup(
    name="user_signals",
    entity="user_id",
    features=[avg_purchase_30d, login_count_7d, churn_risk_score],
    owner="growth-team",
    classification="PII",   # per kailash-dataflow classification
)
await fs.register_group(group, tenant_id="acme")
```

### 4.2 MUST Rules

#### 1. Group Registration Persists `tenant_id`

`register_group()` MUST persist `tenant_id` as a column on `_kml_feature_groups` row; the primary key is `(tenant_id, name, version)`. Two tenants MAY register a group with the same `name`.

**Why:** Per `rules/tenant-isolation.md` Rule 5 — per-tenant audit queries without a full table scan require the tenant column indexed on every metadata row.

#### 2. Classification Propagates To Training Rows

When a group is marked `classification="PII"`, every feature value served from that group MUST be classified in the TrainingResult's audit trail (per `rules/event-payload-classification.md`). A downstream inference that leaks a PII feature value into a log WARN is auditable back to the group declaration.

#### 3. Removing A Feature From A Group Requires A New Group Version

`FeatureGroup.evolve()` is the ONLY mutation path. Removing, renaming, or changing a feature's dtype produces a new group version with a distinct version SHA. Silent in-place edit is BLOCKED.

---

## 5. Materialization

### 5.1 Batch Materialization (offline)

`fs.materialize(group, source)` reads the source (a polars LazyFrame or DataFlow query), computes every feature, and writes to the offline store. Writes are tenant-scoped.

```python
# DO — materialize a group from a polars LazyFrame
events = pl.scan_parquet("s3://events/*.parquet")
await fs.materialize(group, source=events, tenant_id="acme")

# DO — materialize from a DataFlow query
result = await fs.materialize(group, source=db.express.query("User"), tenant_id="acme")
# result.rows_written: int
# result.feature_version: str
# result.entity_snapshot_hash: str
```

### 5.2 Streaming Sync offline → online

`fs.sync_to_online(group)` reads every materialized row from offline, upserts into the online store with the group's TTL. Tenant scoping applies.

### 5.3 MUST Rules

#### 1. Materialization Writes To Offline Only; Sync Writes Online

`materialize()` MUST NOT write to the online store. `sync_to_online()` MUST NOT compute features. Conflating them is BLOCKED — the offline compute path can take minutes/hours; the online sync must stay snappy.

#### 2. Materialization MUST Record Materialized-At Timestamp

Every offline row MUST carry a `_materialized_at` TIMESTAMP column. Point-in-time joins use this column in addition to event timestamps to provide reproducibility.

#### 2a. `_materialized_at` MUST Be Indexed

Every offline feature group table MUST carry a composite index `(tenant_id, entity_id, _materialized_at DESC)`. On tables with 10B+ rows, an unindexed `WHERE _materialized_at <= as_of` is a full scan; the index converts point-in-time joins to logarithmic lookups.

```sql
-- DO — index for point-in-time joins + late-arrival filter
CREATE INDEX idx_kml_feat_user_signals_pit
  ON _kml_feat_user_signals (tenant_id, user_id, _materialized_at DESC);

-- DO NOT — unindexed _materialized_at
-- (scan cost linear in row count; point-in-time queries stall at scale)
```

The index ordering (`DESC` on `_materialized_at`) matches the "latest-value-as-of-as_of" access pattern. The DAL MUST route every PIT query through this index via explicit ORDER BY + LIMIT 1 on the column.

#### 3. Streaming Sync Is Tenant-Scoped

`sync_to_online(group, tenant_id=...)` MUST restrict sync to keys matching `kailash_ml:v1:{tenant_id}:feature:{group}:*`. Cross-tenant accidental syncs are blocked by the key shape.

---

## 6. Offline Retrieval (Training)

### 6.1 `get_training_features()` — Point-In-Time-Correct

```python
# DO — point-in-time retrieval with as_of per entity
entity_df = pl.DataFrame({
    "user_id": ["u1", "u2", "u3"],
    "as_of":   [datetime(2026, 3, 15), datetime(2026, 3, 20), datetime(2026, 3, 21)],
    "label":   [0, 1, 0],
})

training = await fs.get_training_features(
    entity_df=entity_df,
    groups=["user_signals", "device_signals"],
    tenant_id="acme",
)
# training is a polars DataFrame: entity_df + joined feature columns
# Each row's features are the value correct as_of that row's as_of timestamp
```

### 6.2 MUST Rules

#### 1. No Future Leakage — Strict `as_of` Correctness

For every `(entity_id, as_of)` tuple in `entity_df`, the returned feature values MUST be computed from source events with `event_time <= as_of`. An event at `as_of + epsilon` MUST NOT influence the feature value. Violations are caught by `test_feature_store_no_future_leakage`.

```python
# DO — strict upper-bound
# For avg_purchase_30d joining with as_of=2026-03-15:
#   include events: 2026-02-13 <= event_time <= 2026-03-15
#   exclude events: event_time > 2026-03-15

# DO NOT — off-by-one upper bound
#   include event_time <= as_of + 1 second   (leakage)
```

**Why:** Future leakage is the #1 failure mode of training pipelines; a model that trains on features computed from future events appears to have uncanny predictive power in backtest and immediately regresses in production.

#### 2. Missing Feature Values Raise `StaleFeatureError` OR Return NaN (User Configurable)

```python
training = await fs.get_training_features(
    entity_df=entity_df,
    groups=["user_signals"],
    missing_feature_policy="raise",  # "raise" | "null" | "exclude" | "default"
    tenant_id="acme",
)
```

`missing_feature_policy`:

- `"raise"` (default) — raise `StaleFeatureError(entity_id=, feature=, as_of=, reason=)` naming the first missing cell.
- `"null"` — fill missing cells with `null`; the column remains nullable.
- `"exclude"` — drop the entire entity-row from the training DataFrame when ANY feature is missing at `as_of` (conservative; prevents training on partial records).
- `"default"` — use the `@feature(default=...)` value declared on the feature definition.

Silent NaN is BLOCKED as the default because it masks training bugs.

#### 2a. Late-Arriving Data Policy (Point-In-Time Correctness)

Events with `event_time < as_of <= _materialized_at` (late-arriving data — the event belongs to the past but materialised AFTER the query's as_of reference) require a defensible semantic choice. Feast includes them ("as-of-event-time"); Tecton excludes them when the materialization window is closed ("as-of-materialization-time"). kailash-ml picks the CONSERVATIVE default:

```python
training = await fs.get_training_features(
    entity_df=entity_df,
    groups=["user_signals"],
    late_arrival_policy="exclude",  # "include" | "exclude" | "warn" — default "exclude"
    tenant_id="acme",
)
```

| Policy    | Behaviour                                                                                                                                     | Use case                                               |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `exclude` | (default) Late events IGNORED at query time — only events with `_materialized_at <= as_of` included. Matches training-serving-skew tolerance. | Most production models; conservative default.          |
| `include` | Late events INCLUDED — matches Feast "as-of-event-time". Use when backfill is part of the feature pipeline.                                   | Backfill-heavy pipelines; research environments.       |
| `warn`    | Late events INCLUDED but every late-cell is emitted to the tracker as `feature_store.late_arrival.{feature}`.                                 | Initial rollout — observe before choosing the default. |

**MUST 1**: The default is `"exclude"` — explicit opt-in required for `"include"`. BLOCKED rationalization: "we want as-of-event-time to maximise data" — use `"include"` with an explicit kwarg; silent default change is a correctness regression.

**MUST 2**: Two Tier 2 tests — `test_feature_store_late_arrival_exclude.py` AND `test_feature_store_late_arrival_include.py` — MUST exist and assert divergent behavior on the same dataset.

**Why:** Without a documented policy, different calls return different numbers for the same `(entity_id, as_of)` pair depending on when the call ran. Making the policy explicit with a conservative default makes backtest results reproducible across re-runs.

#### 3. Return Type Is Always `polars.DataFrame`

`get_training_features` MUST return `pl.DataFrame`. Returning pandas, dict-of-arrays, or a generator is BLOCKED.

#### 4. Training-Serving Skew Detection — `FeatureStore.detect_skew`

```python
async def detect_skew(
    self,
    *,
    model_name: str,
    tenant_id: str,
    window: timedelta = timedelta(days=7),
    sample_size: int = 1000,
) -> SkewReport: ...

@dataclass(frozen=True)
class SkewReport:
    model_name: str
    sampled_at: datetime
    n_entities_sampled: int
    per_feature: "polars.DataFrame"        # columns: feature, ks_statistic, ks_p_value, l1_distance, online_mean, offline_mean
    severity: Literal["healthy", "warning", "critical"]
    recommendation: str
```

Samples N entities at random, fetches the online-served feature value AND the offline-materialised value at the same `event_time`, computes per-feature divergence statistics (KS, L1). Emits `feature_store.skew.{feature}` metrics and appears as a default tile in `MLDashboard`.

**MUST 1**: `detect_skew` MUST be called automatically by `MLDashboard` every 24h for every tenant's every active model. An operator can cron-disable via config.

**MUST 2**: Severity thresholds — `ks_p_value < 0.01` → CRITICAL (training-serving skew detected); `< 0.05` → WARNING.

**Why:** Training-serving skew is the #1 cause of model degradation in production after deployment. Without a first-class primitive, users write one-off scripts that drift from reality. Feast ships `feast materialize-incremental` followed by a skew check; Tecton ships `skew_analysis`. Kailash-ml's `detect_skew` is the parity surface with a conservative default cadence.

---

## 7. Online Retrieval (Serving)

### 7.1 `get_online_features()` — Sub-10ms p95

```python
# DO — online lookup for a single entity
features = await fs.get_online_features(
    entity_id="u1",
    groups=["user_signals"],
    tenant_id="acme",
)
# features: dict[str, Any]; {"avg_purchase_30d": 42.10, "login_count_7d": 5, ...}

# DO — batch online lookup
features_batch = await fs.get_online_features_batch(
    entity_ids=["u1", "u2", "u3"],
    groups=["user_signals"],
    tenant_id="acme",
)
# features_batch: dict[entity_id -> dict[feature -> value]]
```

### 7.2 MUST Rules

#### 1. Target p95 Latency ≤ 10ms For Cache-Hit Reads

With Redis as online store on the same VPC, p95 of `get_online_features(entity_id)` MUST be ≤ 10ms. This is the InferenceServer budget constraint — features must arrive in <10ms so the end-to-end predict() budget ≤ 50ms is achievable.

**Why:** Every real-time inference (fraud, recommendation, routing) has a tight budget. An online store that takes 100ms blows the latency SLO before the model even sees the features.

#### 2. Stale Value Behavior Is Explicit

If an online-store row has aged past its TTL, the reader MUST raise `StaleFeatureError` OR return NaN OR return the default — user-selectable via `on_stale=` kwarg. Silent return of stale values is BLOCKED.

```python
# DO — explicit handling
features = await fs.get_online_features(entity_id="u1", groups=["..."], on_stale="raise")
# Raises StaleFeatureError if any feature's row is past TTL
```

#### 3. Tenant Isolation — Missing `tenant_id` Raises `TenantRequiredError`

Per `rules/tenant-isolation.md` MUST Rule 2. The online store key shape is `kailash_ml:v1:{tenant_id}:feature:{group}:{entity_id}` — a missing `tenant_id` produces a malformed key that MUST be rejected at the API, not constructed as `kailash_ml:v1::feature:...` and read silently.

---

## 8. Versioning & Retention

### 8.1 Feature Version Lineage

Every `TrainingResult` carries `feature_versions: dict[group_name, version_sha]`. Re-training against the same feature versions reproduces the exact feature values (given materialization is deterministic on the same source).

### 8.1a Feature Versions Are Monotonic AND Immutable Post-Materialisation

Once a feature version `sha_v1 = sha256(decorator_kwargs || inspect.getsource(fn) || py_version || polars.__version__ || numpy.__version__ || blas_backend)` has been materialised to `_kml_feature_group_history`, it MUST NOT be mutated. A source-level change produces a NEW version; the old version persists untouched.

```python
# DO — version bump creates a new row, old persists
@feature(name="avg_purchase_30d", group="user_signals", version=1)
def avg_purchase_30d(tx_df): ...
# Materialised → sha_abc123 written to _kml_feature_group_history

# User edits the function body (reformat or rename variable)
# → new sha_def456 auto-computed on next materialisation
# → two rows now exist in history: (sha_abc123, sha_def456)
# → ModelVersion.feature_versions pinned to abc123 still resolves

# DO NOT — overwrite existing version
# UPDATE _kml_feature_group_history SET fn_source = ? WHERE sha = 'abc123'  # BLOCKED
```

#### MUST 1. History Table Append-Only

`_kml_feature_group_history` is append-only. Writes with an existing `(tenant_id, group, version_sha)` composite key MUST raise `FeatureVersionImmutableError`. The table MUST NOT have an `UPDATE` path in any DAL method.

#### MUST 2. ModelVersion Pins Exact SHAs, Not `@latest`

`ModelVersion.feature_versions: dict[str, str]` stores the EXACT `(group, version_sha)` pairs the model was trained on. Consumers asking for `group@abc123` get the exact definition — resurrected from history.

#### MUST 3. Version Bump Forces New Row

A user who updates a `@feature` body triggers automatic version bump on next materialisation — kailash-ml computes the new SHA and INSERTs a fresh history row. The prior version remains live.

#### MUST 4. `get_feature_version(group, version)` Is Immutable Post-Materialisation

`FeatureStore.get_feature_version(group, version_sha) -> FeatureVersion` MUST always resolve, even for superseded versions (as long as retention hasn't purged them per §8.2).

#### MUST 5. Tier 2 Test

`tests/integration/test_feature_version_immutability.py` MUST:

1. Train model M1 at feature group G version v1 (sha_abc).
2. Edit G's source → new version v2 (sha_def).
3. Assert M1's inference still fetches v1 features correctly.
4. Assert attempting to UPDATE v1's source in history raises `FeatureVersionImmutableError`.

**Why:** Downstream models pin to exact feature SHAs. A mutable feature version silently changes the semantic meaning of every model that pinned it, retrospectively invalidating every cached prediction. Append-only history is the structural defense. See Tecton / Feast for similar immutability contracts.

### 8.2 Retention

```python
fs = FeatureStore(
    store="postgresql://...",
    online="redis://...",
    tenant_id="acme",
    offline_retention_days=365,    # default None = forever
    online_ttl_seconds=86400,      # default 24h
)
```

`offline_retention_days` triggers a background compaction that truncates offline rows older than N days. `online_ttl_seconds` is enforced by Redis EXPIRE on every write.

### 8.3 MUST Rules

#### 1. Retention Is Tenant-Scoped

Per-tenant retention overrides are accepted via `fs.set_retention(tenant_id="acme", days=90)`. A tenant-level GDPR erasure request triggers `fs.erase_tenant(tenant_id="acme", reason="GDPR article 17")` which drops every `_materialized_*` row AND every online key for that tenant. Erasure writes an audit row with `actor_id` + `occurred_at`.

---

## 9. Tenant Isolation (Binding to `rules/tenant-isolation.md`)

### 9.1 Keyspace

```
kailash_ml:v1:{tenant_id}:feature:{group_name}:{entity_id}:{feature_version}
```

Single-tenant deployments MUST use the literal `"_single"` for `{tenant_id}` per `ml-tracking.md §7.2` (the canonical cross-spec sentinel). The strings `"default"` and `"global"` are BLOCKED (see `rules/tenant-isolation.md` Rule 2 for "default"; `ml-tracking.md §7.2` for the canonical-sentinel authority).

### 9.2 MUST Rules

#### 1. Every SQL Query Filters By `tenant_id`

SQL reads (`SELECT * FROM _kml_feat_user_signals WHERE user_id = ...`) MUST include `AND tenant_id = $N`. Missing filter raises `TenantFilterMissingError` at the DAL — tested in `test_feature_store_tenant_filter_enforced`.

#### 2. Cross-Tenant Reads Raise

A read for `tenant_id="acme"` that would return a row with `tenant_id="bob"` MUST raise `CrossTenantReadError`. Regression test: two tenants store features with the same entity ID; one tenant's read sees zero rows of the other's data.

#### 3. Audit Rows Persist `tenant_id`

Every `_kml_feature_audit` row (materialize, register_group, sync, erase) MUST persist `tenant_id` indexed per Rule 5. Forensic queries "what did tenant X materialize last week" are O(index-scan).

---

## 10. Drift Integration

### 10.1 Hooks Into `DriftMonitor`

```python
# DO — attach feature distributions as drift baselines
await drift_monitor.set_reference_from_feature_group(
    group_name="user_signals",
    feature_version="a3f1c2d9b4e5",
    tenant_id="acme",
)
# DriftMonitor pulls baseline distribution from offline store rows
# at the group's feature_version; live snapshots pulled periodically from online

report = await drift_monitor.check_drift(
    group_name="user_signals",
    tenant_id="acme",
)
# report.drift_per_feature: {"avg_purchase_30d": 0.12, ...}
```

### 10.2 MUST Rules

#### 1. Feature Monitoring Consumes `FeatureGroup`, Not Ad-Hoc Columns

`DriftMonitor` MUST accept `set_reference_from_feature_group(group, version, tenant_id)` as a first-class method. A drift baseline pinned to a feature version survives schema evolution: if the group evolves to v2, the v1 baseline is still valid for v1 models, and the v2 baseline is auto-computed on next materialization.

**Why:** Ad-hoc column-list drift baselines go stale the moment the feature catalog evolves, forcing manual re-baselining. Group-linked baselines auto-track the lineage.

---

## 10A. Schema DDL (Feature Store Tables)

Resolves Round-3 HIGH B7: DDL blocks for the four feature-store tables the spec references (`_kml_feature_groups`, `_kml_feature_versions`, `_kml_feature_materialization`, `_kml_feature_audit`) but did not define. All four carry `tenant_id` per `rules/tenant-isolation.md` MUST Rule 5 where the data is tenant-scoped; the audit table additionally carries `actor_id` per `rules/event-payload-classification.md`.

### 10A.1 Identifier Discipline

All dynamic table names written by DDL-emitting code MUST route through `kailash.db.dialect.quote_identifier()` per `rules/dataflow-identifier-safety.md` MUST Rule 1. The `_kml_` table prefix (leading underscore marks these as internal metadata tables users should not query directly — distinct from the user-configurable per-tenant feature-table prefix `table_prefix="kml_feat_"` in `FeatureStore.__init__`) MUST be validated in the caller's `__init__` against the regex `^[a-zA-Z_][a-zA-Z0-9_]*$` per `rules/dataflow-identifier-safety.md` MUST Rule 2; table-name + prefix total length stays within the Postgres 63-char limit (Decision 2 approved).

Polars expression sources (`polars_expr_src`) are stored as inert TEXT — never interpolated into executable SQL. When a feature-version materializes, the polars expression is evaluated by the polars engine against the offline store, never handed to the SQL interpolator.

### 10A.2 Postgres DDL

```sql
-- _kml_feature_groups
CREATE TABLE _kml_feature_groups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id VARCHAR(255) NOT NULL,
  name VARCHAR(255) NOT NULL,
  entity VARCHAR(255) NOT NULL,
  owner VARCHAR(255),
  description TEXT,
  ttl_seconds INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, name)
);

-- _kml_feature_versions
CREATE TABLE _kml_feature_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  feature_group_id UUID NOT NULL REFERENCES _kml_feature_groups(id),
  version_sha VARCHAR(72) NOT NULL,  -- sha256 of the feature definition
  polars_expr_src TEXT NOT NULL,  -- polars expression source (inert; never interpolated into SQL)
  schema_json JSONB NOT NULL,
  registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (feature_group_id, version_sha)
);

-- _kml_feature_materialization
CREATE TABLE _kml_feature_materialization (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  feature_version_id UUID NOT NULL REFERENCES _kml_feature_versions(id),
  kind VARCHAR(16) NOT NULL,  -- 'offline' | 'online'
  last_run_at TIMESTAMPTZ,
  row_count BIGINT,
  status VARCHAR(16) NOT NULL DEFAULT 'IDLE'
);

-- _kml_feature_audit
CREATE TABLE _kml_feature_audit (
  id BIGSERIAL PRIMARY KEY,
  tenant_id VARCHAR(255) NOT NULL,
  feature_group_id UUID NOT NULL,
  actor_id VARCHAR(255) NOT NULL,
  action VARCHAR(32) NOT NULL,  -- register | update | promote | delete | materialize
  prev_state JSONB,
  new_state JSONB,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_feature_audit_tenant_time ON _kml_feature_audit(tenant_id, occurred_at DESC);
```

### 10A.3 SQLite-Compatible Variant

SQLite does not support `UUID`, `JSONB`, `TIMESTAMPTZ`, `BIGSERIAL`, or `BIGINT` as distinct types. The SQLite subset MUST substitute:

- `UUID` → `TEXT` (canonical 36-char hyphenated string; caller generates via `uuid.uuid4()`)
- `JSONB` → `TEXT` (JSON-serialized string; caller `json.dumps()` / `json.loads()`)
- `TIMESTAMPTZ` → `TEXT` (ISO-8601 UTC string, e.g. `2026-04-21T12:34:56.789Z`; caller normalizes to UTC before write)
- `BIGSERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`
- `BIGINT` → `INTEGER`
- `DEFAULT gen_random_uuid()` → omitted; caller supplies UUID at insert
- `DEFAULT NOW()` → omitted; caller supplies ISO-8601 UTC string at insert
- `REFERENCES ... (id)` → kept verbatim (SQLite supports FK syntax; enforcement requires `PRAGMA foreign_keys = ON`)

### 10A.4 Tier-2 Schema-Migration Tests

- `test__kml_feature_groups_schema_migration.py` — applies §10A.2 + §10A.3 DDL to a fresh Postgres (via `ConnectionManager`) AND a fresh SQLite (`:memory:`); asserts `pragma_table_info` / `information_schema.columns` match the declared shape; asserts the `UNIQUE(tenant_id, name)` constraint rejects a duplicate row on both backends.
- `test__kml_feature_versions_schema_migration.py` — same contract; additionally asserts the `UNIQUE(feature_group_id, version_sha)` constraint and the FK to `_kml_feature_groups(id)` on both backends; asserts that `polars_expr_src` round-trips a large expression verbatim (never SQL-interpolated at read).
- `test__kml_feature_materialization_schema_migration.py` — same contract; additionally asserts the `kind` column round-trips both `'offline'` and `'online'` values; asserts the FK to `_kml_feature_versions(id)`.
- `test__kml_feature_audit_schema_migration.py` — same contract; additionally asserts the composite index `idx_feature_audit_tenant_time` exists; asserts the `action` vocab round-trips `register | update | promote | delete | materialize`.

Each test MUST use `quote_identifier()` when referencing the table name by string for validation queries, closing the `rules/dataflow-identifier-safety.md` Rule 5 loop even for hardcoded test fixtures.

---

## 11. Industry Parity

| Capability                         | kailash-ml 1.0.0 | Feast | Hopsworks | Tecton | SageMaker FS | ClearML |
| ---------------------------------- | ---------------- | ----- | --------- | ------ | ------------ | ------- |
| Offline store (Postgres / DuckDB)  | Y                | Y     | Y         | Y      | Y            | Y\*     |
| Online store (Redis / DynamoDB)    | Y                | Y     | Y         | Y      | Y            | Y\*     |
| Point-in-time correctness          | Y (native)       | Y     | Y         | Y      | Y            | N       |
| Polars-native                      | Y                | N     | N         | N      | N            | N       |
| Feature groups                     | Y                | Y     | Y         | Y      | Y            | Y       |
| TTL on online rows                 | Y                | Y     | Y         | Y      | Y            | Y       |
| Schema evolution without rewrite   | Y (`evolve()`)   | Y     | Y         | Y\*    | Y\*          | N       |
| Per-tenant isolation (multi-CLG)   | Y (native)       | N     | Y\*       | Y\*    | Y (IAM)      | N       |
| DataFlow lineage integration       | Y (unique)       | N     | N         | N      | N            | N       |
| Classification-aware (PII tagging) | Y (unique)       | N     | Y\*       | Y\*    | N            | N       |
| Drift-baseline hooks built-in      | Y                | N     | Y         | Y      | Y            | Y       |

**Position:** Polars-native + DataFlow-integrated + PACT/tenant-native. Parity with Feast/Tecton on table-stakes (point-in-time, online/offline split, feature groups); ahead on polars-native (3-5x perf on typical reads), ahead on DataFlow lineage (feature spec carries the exact source query), and uniquely integrated with `kailash-dataflow` classification for PII-aware feature groups.

---

## 12. Error Taxonomy

Every error from the feature-store surface MUST be a typed exception under `kailash_ml.errors` (FeatureStoreError family per `ml-tracking-draft.md §9.1`). Cross-domain errors (`TenantRequiredError`) live under `TrackingError` and are re-exported. Cross-cutting errors sitting at the `MLError` root (`MultiTenantOpError` per Decision 12) are ALSO re-exported from `kailash_ml.errors` so feature-store callers may write `except MultiTenantOpError` without importing the `kailash.ml.errors` module directly.

| Exception                     | When raised                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FeatureNotFoundError`        | `get_*_features()` names a feature not in any registered group.                                                                                                                                                                                                                                                                                                                                                                                   |
| `FeatureGroupNotFoundError`   | Group name not registered for the requested `tenant_id`.                                                                                                                                                                                                                                                                                                                                                                                          |
| `FeatureVersionNotFoundError` | `feature_version=` parameter doesn't exist in the registry.                                                                                                                                                                                                                                                                                                                                                                                       |
| `StaleFeatureError`           | Online row past TTL with `on_stale="raise"`; offline missing with `on_missing="raise"`.                                                                                                                                                                                                                                                                                                                                                           |
| `PointInTimeViolationError`   | Internal audit detects a row in `get_training_features` result that was materialized after its `as_of`.                                                                                                                                                                                                                                                                                                                                           |
| `TenantRequiredError`         | Multi-tenant store called without `tenant_id`.                                                                                                                                                                                                                                                                                                                                                                                                    |
| `CrossTenantReadError`        | Query with `tenant_id="acme"` resolves a row with different `tenant_id`.                                                                                                                                                                                                                                                                                                                                                                          |
| `TenantQuotaExceededError`    | Tenant exceeds per-tenant storage / read QPS quota (see `ml-engines-v2-draft.md §5.3`).                                                                                                                                                                                                                                                                                                                                                           |
| `FeatureEvolutionError`       | `FeatureGroup.evolve()` requested a schema change that would break an active model signature.                                                                                                                                                                                                                                                                                                                                                     |
| `OnlineStoreUnavailableError` | Online store unreachable; caller may fallback to offline OR raise, user-selectable via `on_online_miss=` kwarg.                                                                                                                                                                                                                                                                                                                                   |
| `MultiTenantOpError`          | (Decision 12, cross-cutting, post-1.0) `export_tenant_snapshot()` / `import_tenant_snapshot()` on a feature group called without PACT D/T/R clearance for cross-tenant admin export/import. Root inherits `MLError`, NOT `FeatureStoreError`, so `except MLError` catches uniformly across registry + feature-store + serving + tracking. See `ml-tracking-draft.md §9.1.1` + `supporting-specs-draft/kailash-core-ml-integration-draft.md §3.3`. |

---

## 13. Test Contract

### 13.1 Tier 1 (Unit)

- `test_feature_decorator_versioning` — content SHA is deterministic for identical source; changes for mutated source.
- `test_point_in_time_upper_bound` — synthetic events with known `event_time`, `as_of` placements, strict upper-bound assertion.
- `test_key_shape_formatter` — `kailash_ml:v1:{tenant_id}:feature:...` produced correctly; "default" tenant raises.
- One test per error taxonomy entry (12 tests).

### 13.2 Tier 2 (Integration, Real Postgres + Real Redis)

Per `rules/facade-manager-detection.md` Rule 1, these tests MUST import via the framework facade (`engine.feature_store.X`, not `from kailash_ml.engines.feature_store import FeatureStore`):

- `test_feature_store_point_in_time_wiring.py` — real Postgres; materialize 10k events; assert `get_training_features(entity_df, as_of=...)` returns values with strict upper-bound; mutate a row and re-check.
- `test_feature_store_online_latency.py` — real Redis; p95 `get_online_features` under 10ms over 1000 reads.
- `test_feature_store_tenant_isolation.py` — two tenants materialize the same group name with different entities; cross-tenant reads raise; invalidation is scoped.
- `test_feature_store_sync_offline_to_online.py` — materialize then sync; verify online returns the same value.
- `test_feature_store_evolve.py` — `evolve(add=[...], drop=[...])` produces a new group version; old version remains readable.
- `test_feature_store_retention_gdpr_erase.py` — `erase_tenant()` drops offline + online + records audit row.
- `test_feature_store_drift_baseline_hook.py` — `DriftMonitor.set_reference_from_feature_group()` reads feature values at the pinned version; live snapshot reads from online store.
- `test_feature_store_classification_propagation.py` — PII-classified group values do NOT appear raw in log lines (`rules/event-payload-classification.md`).

### 13.3 Tier 3 (E2E, via `MLEngine`)

- `test_mlengine_train_reads_feature_group.py` — `engine.fit(group="user_signals", target="churned")` trains against the feature store; `TrainingResult.feature_versions` contains the exact SHA.
- `test_mlengine_serve_reads_online_store.py` — `engine.serve(model, channels=["rest"])` + POST /predict reads online features sub-10ms.

---

## 14. Cross-References

- `ml-engines-v2-draft.md §5` — tenant propagation contract; `FeatureStore` inherits the Engine's `tenant_id`.
- `ml-tracking-draft.md` — `ExperimentTracker` reads `feature_versions` from every `TrainingResult`; run detail page renders the group/version lineage.
- `ml-drift-draft.md` — drift baseline hooks; feature groups as first-class drift targets.
- `ml-automl-draft.md` — AutoML reads feature groups as candidate feature sets; HPO trials log group+version per trial.
- `rules/tenant-isolation.md` — MUST Rules 1-5, cache key shape, invalidation scoping, audit row discipline. Binding.
- `rules/event-payload-classification.md` — classified PII feature values never appear raw in event payloads.
- `rules/facade-manager-detection.md` — FeatureStore is a `*Store` manager-shape class; MUST have `test_feature_store_*_wiring.py` tests through the Engine facade.
- `kailash-dataflow` classification model — `FeatureGroup.classification` propagates from dataflow's `@classify` decorator when features derive from classified columns.

---

## 15. Conformance Checklist

- [ ] `FeatureStore(store=..., online=..., tenant_id=...)` constructs zero-arg-free; `initialize()` is idempotent.
- [ ] Every feature has `entity=`, `dtype=`, content-addressed version.
- [ ] `@feature` accepts polars expressions only; pandas raises at decorator time.
- [ ] `FeatureGroup` versioning via `evolve()`; in-place mutation BLOCKED.
- [ ] `materialize()` writes offline; `sync_to_online()` writes online; conflating raises.
- [ ] `get_training_features(entity_df, as_of=...)` is point-in-time correct; no future leakage.
- [ ] `get_online_features()` p95 ≤ 10ms on same-VPC Redis; Tier 2 latency test passes.
- [ ] `tenant_id` required on every read; missing raises `TenantRequiredError`.
- [ ] Storage keys use `kailash_ml:v1:{tenant_id}:feature:...` with `"_single"` canonical sentinel for single-tenant per `ml-tracking.md §7.2`.
- [ ] Every error is a typed exception per §12.
- [ ] Every Tier 2 test in §13.2 is named and imports via the facade.
- [ ] `rg tenant_id packages/kailash-ml/src/kailash_ml/engines/feature_store.py` returns matches on every public method signature.

---

_End of ml-feature-store-draft.md_
