# DataFlow × kailash-ml Integration — Feature-Source Binding, @feature Pipeline Consumption, Lineage Hashing

Version: 2.0.0 — graduated from `1.0.0 (draft)` (FM2 Wave 3, #693). DataFlow-side ML bridge re-derived against `kailash-dataflow 2.11.3` / `kailash-ml 2.1.1` shipped code.
Package: `kailash-dataflow`
Shipped in: **kailash-dataflow 2.1.0** (the ML bridge first landed here); `TenantRequiredError` rename closed F-B-23 in **2.3.2**; consumer side (`@feature` / `FeatureGroup` / `FeatureStore.materialize` / `FeatureMaterialiser` / `FeatureRegistry`) landed FM2 Waves 1+2 in `kailash-ml 2.1.x`, against the DataFlow primitives shipped in **kailash-dataflow 2.11.3**.
Supersedes: none — this spec adds ML-facing surfaces to DataFlow without modifying existing engine / Express APIs.
Parent domain: Kailash DataFlow (database operations + classification + lineage).
Sibling specs: `specs/dataflow-core.md`, `specs/dataflow-express.md`, `specs/dataflow-models.md`, `specs/dataflow-cache.md`, `specs/ml-feature-store.md` (the kailash-ml consumer of `ml_feature_source` / `transform` / `hash`).

Origin: `ml-feature-store.md` §2/§11 mandates DataFlow lineage integration + `@feature` consuming `dataflow.transform`; `ml-registry.md` mandates `lineage_dataset_hash` on every model version. This spec specifies the DataFlow-side surface kailash-ml consumes.

> **Graduation note (FM2 Wave 3, #693, 2026-06-13):** the prior Wave 6.5 deferral admonition gated this spec on the M2 consumer surface (`@feature`, `FeatureGroup`, `FeatureStore.materialize()`). That surface HAS shipped (FM2 Waves 1+2 — see `ml-feature-store.md` §11.1/§11.2/§11.3/§11.4): `@feature` (`kailash_ml.features.decorators`), public `FeatureGroup` (`kailash_ml.features.feature_group`), `FeatureStore.materialize` + `FeatureMaterialiser` (`kailash_ml.features.materialiser`), and `FeatureRegistry` (`kailash_ml.features.registry`) are all exported. The §2.5 / §3 clauses are now re-derived against the shipped `dataflow.ml._transform` / `dataflow.ml._feature_source` code. The `dataflow.ml_feature_source(...)` polars binding is consumed by `kailash_ml.features.FeatureStore.get_features(...)` via the internal `SchemaFeatureGroup` read adapter (`packages/kailash-ml/src/kailash_ml/features/_schema_feature_group.py`, issue #1241): the binding duck-types on a FeatureGroup-shaped `.materialize()`, which a declarative `FeatureSchema` does not expose, so the store wraps the schema in the adapter before calling the binding. End-to-end retrieval is verified by `packages/kailash-ml/tests/integration/test_feature_store_get_features_wiring.py` + `packages/kailash-ml/tests/regression/test_issue_1241_get_features_returns_dataframe.py` (point-in-time correctness included).

---

## 1. Scope + Non-Goals

### 1.1 In Scope

Four capabilities the `dataflow.ml` bridge ships (first landed in DataFlow 2.1.0; current as of kailash-dataflow 2.11.3):

1. **`dataflow.ml_feature_source(feature_group)` polars binding** — materialize a `FeatureStore` feature group as a DataFlow read source that downstream Express / workflow operations can consume.
2. **`@feature` pipeline consumption of `dataflow.transform`** — feature-store decorators call into a new `dataflow.transform(expr, source)` helper for feature-computation pipelines that reuse DataFlow's parameterized-query guarantees.
3. **DataFlow × ML lineage** — `dataflow.hash(df)` returns a stable SHA-256 fingerprint consumed by `ModelRegistry.register_version(lineage_dataset_hash=...)` as the mandatory lineage field.
4. **ML training-lifecycle event surface** — `dataflow.ml` ships a fixed pair of `DomainEvent` types (`ML_TRAIN_START_EVENT` / `ML_TRAIN_END_EVENT`), emit-helpers (`emit_train_start` / `emit_train_end`) for kailash-ml training engines, and subscribe-helpers (`on_train_start` / `on_train_end`) for downstream consumers (MLflow bridge, dashboard, audit trail). The events ride DataFlow's existing `event_bus` so every DataFlow consumer inherits the surface without a second event bus. See § 4A for the full contract. Module: `dataflow.ml._events` (re-exported through `dataflow.ml`).

Public symbols (re-exported through `dataflow.ml.__all__`):

- `ml_feature_source`, `transform`, `hash` — primary surface (§§ 2, 3, 4).
- `TrainingContext` — frozen dataclass `(run_id, tenant_id, dataset_hash, actor_id)` carried in every event payload.
- `ML_TRAIN_START_EVENT`, `ML_TRAIN_END_EVENT` — string constants for the two `event_type` values (§ 4A.1).
- `emit_train_start`, `emit_train_end` — emit-helpers used by kailash-ml training engines (§ 4A.2).
- `on_train_start`, `on_train_end` — subscribe-helpers for downstream consumers (§ 4A.3).
- `build_cache_key` — exposed for tenant-scoped invalidation callers (§ 2.3).
- `DataFlowMLIntegrationError`, `FeatureSourceError`, `DataFlowTransformError`, `LineageHashError`, `TenantRequiredError` — error taxonomy (§ 5).
- `MLTenantRequiredError` — deprecated alias resolved via module-level `__getattr__`; intentionally absent from `__all__` (§ 5).

### 1.2 Out of Scope (Owned By Sibling Specs)

- Express CRUD surface → `specs/dataflow-express.md`.
- Model decorator / classification / masking → `specs/dataflow-models.md`.
- Cache / dialect / pooling → `specs/dataflow-cache.md`.
- Core engine / trust / fabric → `specs/dataflow-core.md`.
- FeatureStore decorator / materialization → `specs/ml-feature-store.md` (§11).
- ModelRegistry model versions → `specs/ml-registry.md`.

### 1.3 Non-Goals

- **No new ORM layer.** `ml_feature_source` returns a `polars.LazyFrame` (not a new query-builder class).
- **No feature-engineering DSL.** `dataflow.transform(expr, source)` accepts polars expressions only — no SQL DSL, no pandas.
- **No caching of feature materializations inside DataFlow.** FeatureStore owns caching per `specs/ml-feature-store.md`; DataFlow is the data layer.

---

## 2. `dataflow.ml_feature_source` — Polars Binding

### 2.1 Contract

```python
# packages/kailash-dataflow/src/dataflow/ml/_feature_source.py
def ml_feature_source(
    feature_group: "FeatureGroup",
    *,
    tenant_id: Optional[str] = None,
    point_in_time: Optional[datetime] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> polars.LazyFrame:
    """Materialize a feature group from its DataFlow-backed offline store
    as a polars LazyFrame. Tenant-scoped, point-in-time-correct, bounded."""
```

### 2.2 Invariants

- Accepts ANY `FeatureGroup`-shaped object — DataFlow takes NO hard dependency on kailash-ml. The binding is **duck-typed** (`_feature_source.py:77-103::_validate_feature_group_shape`): an object satisfies the contract when it exposes a non-empty string `.name` AND a callable `.materialize(...)`. The public `kailash_ml.features.FeatureGroup`, the internal `SchemaFeatureGroup` read adapter, and the legacy `kailash_ml.engines.feature_store.FeatureGroup` all satisfy it. A `None` / shape-invalid object raises `FeatureSourceError` (NOT a `RuntimeError` — there is no `import kailash_ml` inside the function body to fail).
- `tenant_id` MUST be provided when the feature group is `multi_tenant=True` (`_is_multi_tenant_group` inspects `.multi_tenant`, or a nested `.model.multi_tenant`, defaulting `False`). Omission raises `TenantRequiredError` (per `rules/tenant-isolation.md` §2, `_feature_source.py:213-216`). A `None` `tenant_id` for a single-tenant group is accepted.
- `point_in_time` enables point-in-time-correct feature joins (Feast-parity); it is forwarded unchanged to the feature group's `.materialize(point_in_time=...)`. The DataFlow read pushes the `timestamp_column <= point_in_time` window filter down to SQL; the as-of dedup is computed in polars (see `ml-feature-store.md` §4 MUST-5).
- `since` / `until` are window-bounds; supplying `point_in_time` AND either `since`/`until` raises `ValueError` to enforce explicit caller intent (`_feature_source.py:198-202`).
- `limit` is forwarded to `.materialize(limit=...)` to bound query cost on large feature groups.
- Returns a `polars.LazyFrame` — a `DataFrame` returned by the feature group is collected to `.lazy()` (`_feature_source.py:282-283`). Callers `.collect()` to materialize.

### 2.3 Tenant isolation

Cache keys for repeated feature-source queries follow the canonical shape emitted by `_feature_source_cache_key` (`_feature_source.py:41-69`): multi-tenant `kailash_ml:v1:{tenant_id}:feature_source:{group}:{params}`, single-tenant `kailash_ml:v1:feature_source:{group}:{params}` (where `{params}` encodes `point_in_time`/`since`/`until`/`limit`). The tenant dimension is the second segment per `rules/tenant-isolation.md` §1; `build_cache_key` is re-exported from `dataflow.ml` for tenant-scoped invalidation callers (§3a wildcards).

### 2.4 SQL safety

`ml_feature_source` builds NO SQL of its own — it forwards `(tenant_id, point_in_time, since, until, limit)` to the feature group's `.materialize(...)`, which owns its backing-store query and its identifier-quoting / parameter-binding discipline (`rules/dataflow-identifier-safety.md` §1 + `rules/infrastructure-sql.md`). The binding only validates the feature group's shape and the window-arg conflict; it never interpolates a user identifier into a SQL string.

### 2.5 Classification propagation

A feature group's `.classification` attribute (when present) propagates through `ml_feature_source`. `_classification_metadata` (`_feature_source.py:133-150`) reads `getattr(feature_group, "classification", None)` and, when set, stashes it on the returned frame as the `frame._kailash_ml_metadata` attribute (`_feature_source.py:287-295` — polars exposes no public user-metadata API on `LazyFrame`, so the binding uses this attribute so `transform()` can forward it). Only classification METADATA travels (which column is classified, which strategy) — never raw classified VALUES — so downstream consumers can enforce `redact=` / `mask=` per `rules/dataflow-classification.md`.

---

## 3. `@feature` Pipeline Consumption Of `dataflow.transform`

### 3.1 New helper: `dataflow.transform`

```python
# packages/kailash-dataflow/src/dataflow/ml/_transform.py
def transform(
    expr: polars.Expr,
    source: polars.LazyFrame,
    *,
    name: str,
    tenant_id: Optional[str] = None,
) -> polars.LazyFrame:
    """Apply a polars expression to a DataFlow-backed LazyFrame source,
    tagging the result with the transform `name` in polars metadata for
    lineage capture downstream. Tenant-scoped."""
```

### 3.2 How `@feature` uses it

Per `ml-feature-store.md` §11.2, the shipped `@feature` decorator (`kailash_ml.features.decorators.feature`) is keyword-only — `@feature(*, name: str, dtype: str, description: str = "")` — and wraps a zero-arg function returning a `polars.Expr` into a frozen, content-addressed `FeatureDefinition` (`name` + `dtype` + a content-SHA `version` of the function body). It does NOT take an `entity` or `version` kwarg (entity scoping belongs to the `FeatureGroup` / `FeatureSchema`; the version is content-derived). `FeatureDefinition.expr()` is a METHOD that evaluates `self.fn()` and returns the `polars.Expr`, raising `TypeError` if the body returns a non-`Expr` (`decorators.py:82-99`). At materialise time `FeatureGroup.materialize` routes each derived column's expr through this binding:

```python
from kailash_ml.features import feature

@feature(name="amount_log", dtype="float64")
def amount_log():               # zero-arg; returns a polars.Expr
    return pl.col("amount").log()

# At materialise time FeatureGroup.materialize composes:
result = dataflow.transform(
    expr=amount_log.expr(),                                 # .expr() is a method call
    source=dataflow.ml_feature_source(group, tenant_id=tid),
    name=f"amount_log@{amount_log.version}",                # content-SHA version
    tenant_id=tid,
)
```

### 3.3 Benefits over direct polars

- Tenant-scoped caching (re-compute only when source + expr + tenant triple invalidates).
- Lineage capture (transform name + expr hash propagate to `dataflow.hash(result)`).
- Classification auto-propagation — a transform on a classified column produces a classified result; explicit casts reset classification per `rules/dataflow-classification.md`.
- Uniform error surface — failures raise `DataFlowTransformError(DataFlowError)`, not raw polars errors.

### 3.4 Parallel pipeline composition

`dataflow.transform` is composable:

```python
# Chain of transforms all tracked:
sessions = dataflow.ml_feature_source(sessions_group, tenant_id=tid)
clicks = dataflow.transform(click_count_expr, sessions, name="click_count@1.0", tenant_id=tid)
recency = dataflow.transform(recency_expr, clicks, name="recency@1.0", tenant_id=tid)
# recency's .collect() executes the full lazy chain in one polars pass.
```

---

## 4. DataFlow × ML Lineage

### 4.1 `dataflow.hash(df)` contract

```python
# packages/kailash-dataflow/src/dataflow/ml/_hash.py
def hash(
    df: Union[polars.DataFrame, polars.LazyFrame],
    *,
    algorithm: Literal["sha256"] = "sha256",
    stable: bool = True,
) -> str:
    """Return a stable content hash of the DataFrame or LazyFrame, used
    as lineage_dataset_hash in ModelRegistry. Format: 'sha256:<64hex>'.
    When given a LazyFrame, collects it first."""
```

### 4.2 Hash shape

Returns `f"sha256:{hexlify(hash)}"` — 64 hex chars after the `sha256:` prefix. NOT the 8-hex short form used for event-payload fingerprints (per `rules/event-payload-classification.md` §2). Lineage hashes need full collision resistance because they index the registry; fingerprints need forensic correlation only.

### 4.3 Stability contract

- `stable=True` (default): canonical column ordering (sorted ascending), canonical row ordering (sorted by all columns ascending — deterministic for pure data, O(n log n)). Bytes hashed = polars Arrow IPC stream of the canonicalized frame.
- `stable=False`: hash of polars Arrow IPC stream as-is. Faster, but order-sensitive. Use only when the caller already guarantees canonical ordering upstream.
- Column dtype changes DO affect the hash (dtype is part of the schema).
- `NaN` values hash identically when their bit patterns match (IEEE-754 NaN payload preserved).

### 4.4 Consumed by ModelRegistry

Per `specs/ml-registry.md` (mandatory), every `ModelRegistry.register_version(...)` call requires `lineage_dataset_hash` (the field is a `NOT NULL` column on the registry's backing model — `kailash_ml/tracking/registry.py:277`, `tracking/storage/postgres.py:215`):

```python
from dataflow.lineage import hash as df_hash

training_df = await db.express_list_df("TrainingSet", tenant_id=tid)
dataset_hash = df_hash(training_df)

await registry.register_version(
    model_name="churn",
    version="3.0",
    lineage_dataset_hash=dataset_hash,   # MANDATORY per ml-registry §4
    tenant_id=tid,
    actor_id=actor,
)
```

### 4.5 Resolution

Hash-to-snapshot resolution (resolving a `lineage_dataset_hash` back to the DataFlow-backed query that produced it) is **out of scope** for this spec — neither `ModelRegistry` nor `dataflow.lineage` ships a `resolve_dataset` / `replay` method today (`grep -rn 'resolve_dataset' packages/` returns no production match). `dataflow.hash(df)` is a one-way fingerprint: it indexes a dataset for registry provenance but does NOT retain the query needed to reconstruct it. Callers needing reproducibility MUST persist the producing query themselves (e.g. a named materialization the caller owns). When a reverse-resolution capability is genuinely scoped and implemented, it lands in a future revision of this spec describing the shipped surface — not as a reserved stub here (per `rules/spec-accuracy.md` Rule 5).

---

## 4A. Event Subscription Contract — `dataflow.ml._events`

The ML training-lifecycle event surface lives in `dataflow.ml._events` and is re-exported through `dataflow.ml`. kailash-ml does NOT ship a second event bus — every consumer subscribes through the DataFlow facade's existing `event_bus` (Core SDK `EventBus`).

### 4A.1 Event-Type Constants

```python
# packages/kailash-dataflow/src/dataflow/ml/_events.py
ML_TRAIN_START_EVENT = "kailash_ml.train.start"
ML_TRAIN_END_EVENT   = "kailash_ml.train.end"
```

These are the literal `event_type` strings carried on every `DomainEvent` published by the helpers in §§ 4A.2 and surfaced to subscribers in § 4A.3. Cross-SDK parity (per `rules/cross-sdk-inspection.md` § 3): kailash-rs MUST use byte-identical event-type strings if it ships an equivalent surface.

### 4A.2 Emit Helpers (kailash-ml producer side)

```python
def emit_train_start(
    db: Any,
    context: TrainingContext,
    *,
    model_name: Optional[str] = None,
    engine: Optional[str] = None,
) -> None:
    """Publish a ``kailash_ml.train.start`` event on ``db.event_bus``.

    Args:
        db: DataFlow instance (must expose ``event_bus``).
        context: Immutable provenance envelope (run_id / tenant_id /
            dataset_hash / actor_id).
        model_name: Optional name of the model being trained.
        engine: Optional training engine identifier
            (``"sklearn"``, ``"lightgbm"``, ``"pytorch-lightning"``, …).
    """

def emit_train_end(
    db: Any,
    context: TrainingContext,
    *,
    status: str,
    duration_seconds: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    """Publish a ``kailash_ml.train.end`` event on ``db.event_bus``.

    Args:
        db: DataFlow instance.
        context: Immutable training context (same as emit_train_start).
        status: ``"success"`` / ``"failure"`` / ``"cancelled"``.
        duration_seconds: Wall-clock duration of the run.
        error: Raw error message when ``status="failure"``. The emitter
            structurally redacts classified field values and classified
            field names via
            :func:`dataflow.classification.event_payload.format_error_for_event`
            BEFORE the event is published. Callers MAY pass ``str(exc)``
            directly — including exception strings that interpolate row
            data (``DETAIL: Failing row contains
            (alice@tenant.example, hunter2)``). Documentation-only
            caller-sanitization is BLOCKED per
            ``rules/event-payload-classification.md`` § 1; the
            single-filter-point at the emitter IS the structural
            defense.
    """
```

**Required `event_bus` attribute.** Both emit helpers raise `RuntimeError("DataFlow instance has no event_bus — call db.initialize() …")` when `getattr(db, "event_bus", None)` is `None`. The error message names the corrective action so callers do not have to grep the source.

**Fire-and-forget semantics.** Bus publish failures MUST NOT propagate up into the training run. Both helpers wrap `bus.publish(...)` in `try/except Exception` and emit `WARN` (not ERROR) so operators see the failure without aborting an in-progress training run. Per `rules/observability.md` Rule 7, the WARN line includes `run_id` for correlation.

**Logging.** Every emit call also writes a structured INFO/WARN log line BEFORE publishing (`dataflow.ml.train.start` / `dataflow.ml.train.end`) so the run is auditable even if the bus is unreachable. Log fields: `run_id`, `tenant_id`, `model_name`, `engine`, `dataset_hash` (already a `sha256:` fingerprint), `status`, `duration_seconds`. Per `rules/observability.md` Rule 8, no schema-revealing field names are included.

### 4A.3 Subscribe Helpers (consumer side)

```python
def on_train_start(db: Any, handler: Callable[[Any], None]) -> List[str]:
    """Subscribe ``handler`` to ``kailash_ml.train.start`` events.

    Args:
        db: DataFlow instance (must expose ``event_bus``).
        handler: Callable invoked with a single ``DomainEvent`` argument.

    Returns:
        ``[subscription_id]`` — single-element list matching the shape of
        :meth:`DataFlow.on_model_change` so callers can batch
        subscribe/unsubscribe uniformly.
    """

def on_train_end(db: Any, handler: Callable[[Any], None]) -> List[str]:
    """Subscribe ``handler`` to ``kailash_ml.train.end`` events.

    See :func:`on_train_start` for the return shape.
    """
```

**Single-element list return.** The return shape matches `DataFlow.on_model_change(...)` so a consumer can collect subscription IDs from heterogeneous event sources into one flat list and unsubscribe all on shutdown without special-casing.

**Handler contract.** The `handler` callable receives a `kailash.middleware.communication.domain_event.DomainEvent` instance. Subscribers iterate `event.event_type` and `event.payload`; the payload shape is defined in § 4A.4.

### 4A.4 Event Payload Shape

Every train-event payload is a flat dict with the shape:

```python
{
    "event":         <ML_TRAIN_START_EVENT | ML_TRAIN_END_EVENT>,
    "run_id":        <context.run_id>,        # opaque identifier
    "tenant_id":     <context.tenant_id>,     # operational metadata
    "dataset_hash":  <context.dataset_hash>,  # already "sha256:<64hex>"
    "actor_id":      <context.actor_id>,      # opaque identifier
    "record_id":     <fingerprint>,           # see classification path below
    # emit_train_start adds (when supplied):
    "model_name":    <str>,
    "engine":        <str>,
    # emit_train_end adds:
    "status":            <"success" | "failure" | "cancelled">,
    "duration_seconds":  <float>,                # when supplied
    "error":             <str>,                  # when status="failure"
}
```

**Classification path (mandatory).** Both emit helpers route `record_id` through `dataflow.classification.event_payload.format_record_id_for_event(...)` per `rules/event-payload-classification.md` § 1 — single filter point at the emitter, not at every caller. The `record_id` source is `context.dataset_hash` (already a 64-hex SHA-256 fingerprint, NOT a classified PK), but the routing-through-filter discipline is preserved so the classification policy attached to the DataFlow instance (`db._classification_policy`) is honored uniformly with DataFlow's write-event path.

**Why `TrainingContext` fields are safe to emit raw.** Per `dataflow/ml/_events.py` module docstring:

- `run_id` and `actor_id` are opaque caller-chosen identifiers (UUIDs / agent handles). Not classified data on their own.
- `tenant_id` is operational metadata — `rules/tenant-isolation.md` § 4 explicitly permits it as a metric label / event-payload dimension (bounded cardinality).
- `dataset_hash` is already a `sha256:<64hex>` fingerprint produced by `dataflow.hash(...)` (§ 4) — not a raw value.

No subscriber path ever echoes a classified PK back to the bus.

### 4A.5 `TrainingContext` Field Reference

```python
@dataclass(frozen=True)
class TrainingContext:
    run_id:       str   # opaque caller-chosen run identifier
    tenant_id:    str   # tenant scope (bounded cardinality per tenant-isolation §4)
    dataset_hash: str   # "sha256:<64hex>" from dataflow.hash(...)
    actor_id:     str   # opaque actor identifier (agent handle, user id)
```

Frozen so emit helpers cannot mutate the caller's provenance envelope mid-publish.

### 4A.6 Subscriber Test Contract

Per `rules/event-payload-classification.md` § 4 and `rules/orphan-detection.md` § 1, every emit/subscribe pair MUST have an end-to-end Tier 2 test:

- `tests/integration/test_train_event_emit_subscribe_wiring.py` — real DataFlow + real `event_bus` + `on_train_start(db, handler)` → `emit_train_start(db, context, …)` → assert `handler` was invoked with a `DomainEvent` whose `event_type == ML_TRAIN_START_EVENT` AND payload contains `run_id`, `tenant_id`, `dataset_hash`, `actor_id`, and a `record_id` matching the classification-path output.
- Companion test for `emit_train_end` / `on_train_end` covering all three `status` values (`"success"` / `"failure"` / `"cancelled"`).

Tier 1 helper-only unit tests are insufficient — they prove the helper hashes the record_id but NOT that the framework's hot path actually calls the helper (see `rules/orphan-detection.md` § 2a "crypto-pair round-trip through facade" — same pattern applies to event helpers).

---

## 5. Error Taxonomy

All errors inherit from `kailash_dataflow.exceptions.DataFlowError`:

```python
class DataFlowError(Exception):
    """Existing base."""

class DataFlowMLIntegrationError(DataFlowError):
    """Raised when ml_feature_source / transform / hash fails."""

class FeatureSourceError(DataFlowMLIntegrationError):
    """Raised when ml_feature_source can't resolve the feature group
    (missing kailash-ml, missing group, schema mismatch)."""

class DataFlowTransformError(DataFlowMLIntegrationError):
    """Raised when dataflow.transform can't apply the expr
    (invalid polars expr, type mismatch, tenant mismatch)."""

class LineageHashError(DataFlowMLIntegrationError):
    """Raised when dataflow.hash can't produce a stable hash
    (non-hashable cells, unsupported dtype)."""

class TenantRequiredError(DataFlowMLIntegrationError):
    """Raised when a multi_tenant=True feature group is queried without
    tenant_id. Per rules/tenant-isolation.md §2."""
```

**Canonical name:** `TenantRequiredError` (since kailash-dataflow 2.3.2 — closes F-B-23). The class lives at `dataflow.ml._errors.TenantRequiredError` and is re-exported from `dataflow.ml` namespace; it is **distinct** from the sibling-but-unrelated `dataflow.core.multi_tenancy.TenantRequiredError` (Express-path tenant guard).

**Deprecated alias:** `MLTenantRequiredError` resolves to `TenantRequiredError` via a module-level `__getattr__` on both `dataflow.ml._errors` and `dataflow.ml`; the alias emits a `DeprecationWarning` per access. Slated for removal in **kailash-dataflow v3.0**. Callers SHOULD migrate to the canonical name within the v2.x → v3.0 window. The alias is intentionally absent from `__all__` so star-imports pick up only the canonical name.

The errors are DataFlow-side — the ML-side sees them wrapped via `FeatureStoreError(MLError)` when thrown through the `FeatureStore` API (per `specs/kailash-core-ml-integration.md` §3 hierarchy).

---

## 6. Test Contract

### 6.1 Tier 1 (unit)

- `test_ml_feature_source_without_kailash_ml_raises.py` — simulated absent kailash-ml → `RuntimeError` with actionable message.
- `test_ml_feature_source_multi_tenant_requires_tenant_id.py` — `tenant_id=None` on `multi_tenant=True` group → `TenantRequiredError`.
- `test_transform_polars_expr_accepted.py` — valid expr → returns LazyFrame.
- `test_transform_rejects_pandas.py` — pandas DataFrame input → TypeError at decorator time.
- `test_hash_stable_reordered_same_hash.py` — same data in different row order → identical hash when `stable=True`.
- `test_hash_unstable_different_hash.py` — same data, different row order, `stable=False` → different hashes.
- `test_hash_nan_preserved.py` — NaN bit pattern preserved in hash.
- `test_hash_format_is_sha256_64hex.py` — returned string matches `r"^sha256:[a-f0-9]{64}$"`.

### 6.2 Tier 2 (integration wiring, per `rules/facade-manager-detection.md` §2)

File naming:

- `tests/integration/test_ml_feature_source_point_in_time_wiring.py` — real PG + feature group with `effective_from` / `effective_until` → `point_in_time=t0` returns correct snapshot.
- `tests/integration/test_transform_tenant_cache_isolation_wiring.py` — same expr, same source, two different tenants → two cache slots, no cross-leak.
- `tests/integration/test_hash_roundtrip_to_model_registry_wiring.py` — `dataflow.hash(df)` → `register_version(lineage_dataset_hash=...)` → readback returns the same hash.
- `tests/integration/test_classification_propagates_through_transform_wiring.py` — classified column + transform → result column carries classification metadata.

### 6.3 Regression tests

- `tests/regression/test_issue_NNN_feature_source_sql_injection_hardened.py` — malicious `FeatureGroup.name` (attempted injection) → raises `IdentifierError` (from dialect helper, per `rules/dataflow-identifier-safety.md` §2).
- `tests/regression/test_issue_NNN_hash_column_order_stable.py` — same data, columns re-ordered → identical hash when `stable=True`.
- `tests/regression/test_issue_NNN_transform_classification_survives.py` — behavioural test asserting classification metadata survives transform chain.

---

## 7. Cross-SDK Parity Requirements

DataFlow exists in kailash-rs at `crates/kailash-dataflow/`. Rust parity targets:

- `dataflow.ml_feature_source` → `dataflow::ml_feature_source()` returning a `LazyFrame` (polars-rs).
- `dataflow.transform` → `dataflow::transform()`.
- `dataflow.hash` → `dataflow::hash()` — MUST produce byte-identical SHA-256 hashes for the same canonicalized polars Arrow IPC stream.
- Same error taxonomy mapping to Rust `DataFlowError` variants.

Cross-SDK follow-up is deferred until kailash-rs scopes a Rust-side ML feature-source surface. The parity contract above (byte-identical SHA-256 hashes + DataFlowError taxonomy mapping) is the baseline, and the hash-byte-parity test MUST be added to both SDKs' integration suites when the Rust surface lands. No tracking issue required until Rust-side scoping begins.

---

## 8. Industry Comparison

| Capability                                                     | dataflow 2.1.0 | Feast   | Tecton  | Delta Lake | dbt Core |
| -------------------------------------------------------------- | -------------- | ------- | ------- | ---------- | -------- |
| Polars LazyFrame as feature-source output                      | Y              | Partial | N       | N          | N        |
| Tenant-scoped feature-source cache                             | Y              | N       | Partial | N          | N        |
| Point-in-time-correct joins via `point_in_time=` kwarg         | Y              | Y       | Y       | Partial    | N        |
| Classification metadata auto-propagation through transforms    | Y              | N       | N       | N          | N        |
| Stable content-hash for lineage (SHA-256, row-order-invariant) | Y              | N       | N       | Partial    | N        |
| SQL injection hardening on identifier interpolation            | Y (dialect)    | N/A     | N/A     | Y          | Partial  |

**Position:** DataFlow is the only lineage-aware data layer that produces a stable, cross-SDK content hash AND propagates PII classification through feature transforms — a researcher's feature pipeline remains PII-aware end-to-end without manual annotation.

---

## 9. Migration Path (kailash-dataflow 2.0.x → 2.1.0)

2.0.x users:

- Existing `db.express` / `db.model` / `db.fabric` — unchanged.
- `dataflow.ml_feature_source` — NEW function; no migration.
- `dataflow.transform` — NEW function; no migration.
- `dataflow.hash` — NEW function; no migration.
- `DataFlowMLIntegrationError` and subclasses — NEW hierarchy; catch-all `except DataFlowError` continues to work.

No breaking changes. Purely additive ML surface.

---

## 10. Release Coordination Notes

Part of the kailash-ml 1.0.0 wave release (see `specs/pact-ml-integration.md` §10 for the full wave list).

**Release order position:** after kailash 2.9.0 (the `DataFlowMLIntegrationError` hierarchy inherits discipline from kailash's MLError ladder). Parallel with kailash-pact 0.10.0, kailash-nexus 2.2.0, kailash-kaizen 2.12.0. Must be released BEFORE kailash-ml 1.0.0 because `FeatureStore.materialize()` (ml-side) calls `dataflow.ml_feature_source()`.

**Parallel-worktree ownership** (`rules/agents.md`): dataflow-specialist agent owns `packages/kailash-dataflow/pyproject.toml`, `packages/kailash-dataflow/src/dataflow/__init__.py::__version__`, and `packages/kailash-dataflow/CHANGELOG.md`. Every other agent's prompt MUST exclude these files.

---

## 11. Cross-References

- kailash-ml specs consuming this surface:
  - `specs/ml-feature-store.md` §11.1/§11.2 — public `FeatureGroup` + `@feature` decorator + `FeatureStore.materialize()` (SHIPPED, FM2 Waves 1+2).
  - `specs/ml-registry.md` §4 — `lineage_dataset_hash` mandatory field.
  - `specs/ml-engines-v2.md` §5 — training engines read from `dataflow.ml_feature_source` as a training-set source.
  - `specs/ml-automl.md` — AutoML consumes feature sources via DataFlow.
- DataFlow companion specs:
  - `specs/dataflow-core.md` — engine + exceptions.
  - `specs/dataflow-express.md` — Express API unchanged.
  - `specs/dataflow-models.md` — `@classify` / `multi_tenant=` discipline preserved.
  - `specs/dataflow-cache.md` — cache keyspace used by tenant-scoped feature-source caching.
- Rule references:
  - `rules/tenant-isolation.md` §1, §2, §3a — tenant_id on every cache key; keyspace version sweep.
  - `rules/dataflow-identifier-safety.md` §1 — identifier quoting on every DDL-touching path.
  - `rules/infrastructure-sql.md` — parameterized VALUES binding.
  - `rules/dataflow-classification.md` — classification propagation through transforms.
  - `rules/facade-manager-detection.md` §2 — Tier 2 wiring tests.
  - `rules/event-payload-classification.md` §2 — 8-hex short fingerprint (distinct from lineage hash's 64-hex full form).
  - `rules/spec-accuracy.md` Rule 5 — hash-to-snapshot resolution (§4.5) is out of scope: this spec describes only shipped behavior, no reserved-stub framing.
