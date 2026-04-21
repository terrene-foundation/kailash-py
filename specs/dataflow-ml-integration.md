# DataFlow × kailash-ml Integration — Feature-Source Binding, @feature Pipeline Consumption, Lineage Hashing

Version: 1.0.0 (draft)
Package: `kailash-dataflow`
Target release: **kailash-dataflow 2.1.0** (shipping in the kailash-ml 1.0.0 wave)
Status: DRAFT at `workspaces/kailash-ml-audit/supporting-specs-draft/dataflow-ml-integration-draft.md`. Promotes to `specs/dataflow-ml-integration.md` after round-3 convergence.
Supersedes: none — this spec adds ML-facing surfaces to DataFlow without modifying existing engine / Express APIs.
Parent domain: Kailash DataFlow (database operations + classification + lineage).
Sibling specs: `specs/dataflow-core.md`, `specs/dataflow-express.md`, `specs/dataflow-models.md`, `specs/dataflow-cache.md`.

Origin: `ml-feature-store-draft.md` §2 mandates "DataFlow lineage integration" + `@feature` consuming `dataflow.transform`. `ml-registry-draft.md` mandates `lineage_dataset_hash` field on every model version. Round-1 theme T6 flagged spec-to-code drift where feature-store specs referenced a DataFlow binding that did not exist. This spec specifies the DataFlow-side surface kailash-ml 1.0.0 consumes.

---

## 1. Scope + Non-Goals

### 1.1 In Scope

Three capabilities DataFlow 2.1.0 ships for kailash-ml 1.0.0:

1. **`dataflow.ml_feature_source(feature_group)` polars binding** — materialize a `FeatureStore` feature group as a DataFlow read source that downstream Express / workflow operations can consume.
2. **`@feature` pipeline consumption of `dataflow.transform`** — feature-store decorators call into a new `dataflow.transform(expr, source)` helper for feature-computation pipelines that reuse DataFlow's parameterized-query guarantees.
3. **DataFlow × ML lineage** — `dataflow.hash(df)` returns a stable SHA-256 fingerprint consumed by `ModelRegistry.register_version(lineage_dataset_hash=...)` as the mandatory lineage field.

### 1.2 Out of Scope (Owned By Sibling Specs)

- Express CRUD surface → `specs/dataflow-express.md`.
- Model decorator / classification / masking → `specs/dataflow-models.md`.
- Cache / dialect / pooling → `specs/dataflow-cache.md`.
- Core engine / trust / fabric → `specs/dataflow-core.md`.
- FeatureStore decorator / materialization → `ml-feature-store-draft.md`.
- ModelRegistry model versions → `ml-registry-draft.md`.

### 1.3 Non-Goals

- **No new ORM layer.** `ml_feature_source` returns a `polars.LazyFrame` (not a new query-builder class).
- **No feature-engineering DSL.** `dataflow.transform(expr, source)` accepts polars expressions only — no SQL DSL, no pandas.
- **No caching of feature materializations inside DataFlow.** FeatureStore owns caching per `ml-feature-store-draft.md`; DataFlow is the data layer.

---

## 2. `dataflow.ml_feature_source` — Polars Binding

### 2.1 Contract

```python
# packages/kailash-dataflow/src/dataflow/ml_integration.py
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

- Accepts a `FeatureGroup` instance imported from `kailash_ml.engines.feature_store`. DataFlow does NOT take a hard dependency on kailash-ml — the import is deferred inside the function body, and if kailash-ml is absent the import raises `RuntimeError("dataflow.ml_feature_source requires kailash-ml>=1.0.0")`.
- `tenant_id` MUST be provided when the feature group's underlying model is `multi_tenant=True`. Omission raises `TenantRequiredError` (per `rules/tenant-isolation.md` §2). A `None` `tenant_id` for a single-tenant group is accepted.
- `point_in_time` enables point-in-time-correct feature joins (Feast-parity). When provided, the underlying query filters `WHERE effective_from <= point_in_time AND (effective_until IS NULL OR effective_until > point_in_time)`.
- `since` / `until` are window-bounds; `point_in_time` supersedes them when both are provided (raises `ValueError` to enforce explicit caller intent).
- `limit` is enforced at SQL level (`LIMIT n`) to bound query cost on large feature groups.
- Returns a `LazyFrame` (polars). Callers `.collect()` to materialize.

### 2.3 Tenant isolation

Cache keys for repeated feature-source queries follow the canonical `kailash_ml:v1:{tenant_id}:feature_source:{hash}` shape per approved-decisions.md implications. Invalidation uses tenant-scoped wildcards per `rules/tenant-isolation.md` §3a.

### 2.4 SQL safety

All identifier interpolation (`feature_group.name`, column names) routes through `dataflow.adapters.dialect.quote_identifier()` per `rules/dataflow-identifier-safety.md` §1. Parameter binding is used for VALUES per `rules/infrastructure-sql.md`.

### 2.5 Classification propagation

A `FeatureGroup.classification` field (from `ml-feature-store-draft.md` §3.1) propagates through `ml_feature_source`. Classified columns in the returned `LazyFrame` carry DataFlow classification metadata via polars metadata attributes so downstream consumers (InferenceServer, AutoML) can enforce `redact=` / `mask=` per `rules/dataflow-classification.md`.

---

## 3. `@feature` Pipeline Consumption Of `dataflow.transform`

### 3.1 New helper: `dataflow.transform`

```python
# packages/kailash-dataflow/src/dataflow/transforms.py
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

Per `ml-feature-store-draft.md` §3.1, the `@feature` decorator wraps a function returning a polars Expr. At registration time:

```python
# conceptual
@feature(entity="user_id", dtype="float64", version="1.0")
def recent_clicks(df: pl.LazyFrame) -> pl.Expr:
    return pl.col("clicks").filter(pl.col("ts") > pl.lit(...)).count()

# FeatureStore stores the function + dtype + version (content SHA).
# At materialize time:
result = dataflow.transform(
    expr=recent_clicks.expr,
    source=dataflow.ml_feature_source(group, tenant_id=tid),
    name="recent_clicks@1.0",
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
# packages/kailash-dataflow/src/dataflow/lineage.py
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

Per `ml-registry-draft.md` (mandatory), every `ModelRegistry.register_version(...)` call requires `lineage_dataset_hash`:

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

`ModelRegistry.resolve_dataset(lineage_dataset_hash)` — posts-1.0 capability — resolves a hash back to a DataFlow-backed query snapshot if the caller stored the query under a named materialization. Out of scope for 1.0.0 but API stub reserved:

```python
# Placeholder signature for post-1.0 (raises NotImplementedError in 1.0.0 per
# zero-tolerance Rule 2 — NOT stubbed with fake implementation; instead a
# typed RuntimeError with an explicit "post-1.0" message):
class ModelRegistry:
    async def resolve_dataset(self, lineage_dataset_hash: str) -> "DatasetSnapshot":
        raise NotImplementedError(
            "ModelRegistry.resolve_dataset is reserved for post-1.0; "
            "use dataflow.lineage.replay(lineage_dataset_hash) directly."
        )
```

Per `rules/zero-tolerance.md` Rule 2, this is NOT a stub — it is an explicitly-declared future surface with a typed error indicating the correct alternative. The method body does not pretend to succeed.

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

The errors are DataFlow-side — the ML-side sees them wrapped via `FeatureStoreError(MLError)` when thrown through the `FeatureStore` API (per `kailash-core-ml-integration-draft.md` §3 hierarchy).

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

Cross-SDK follow-up tracked at kailash-rs#TBD. The hash-byte-parity test MUST be added to both SDKs' integration suites.

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

Part of the kailash-ml 1.0.0 wave release (see `pact-ml-integration-draft.md` §10 for the full wave list).

**Release order position:** after kailash 2.9.0 (the `DataFlowMLIntegrationError` hierarchy inherits discipline from kailash's MLError ladder). Parallel with kailash-pact 0.10.0, kailash-nexus 2.2.0, kailash-kaizen 2.12.0. Must be released BEFORE kailash-ml 1.0.0 because `FeatureStore.materialize()` (ml-side) calls `dataflow.ml_feature_source()`.

**Parallel-worktree ownership** (`rules/agents.md`): dataflow-specialist agent owns `packages/kailash-dataflow/pyproject.toml`, `packages/kailash-dataflow/src/dataflow/__init__.py::__version__`, and `packages/kailash-dataflow/CHANGELOG.md`. Every other agent's prompt MUST exclude these files.

---

## 11. Cross-References

- kailash-ml specs consuming this surface:
  - `ml-feature-store-draft.md` §2, §3.1 — `@feature` decorator + `FeatureStore.materialize()`.
  - `ml-registry-draft.md` §4 — `lineage_dataset_hash` mandatory field.
  - `ml-engines-v2-draft.md` §5 — training engines read from `dataflow.ml_feature_source` as a training-set source.
  - `ml-automl-draft.md` — AutoML consumes feature sources via DataFlow.
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
  - `rules/zero-tolerance.md` Rule 2 — reserved `resolve_dataset()` method uses typed `NotImplementedError` with actionable message, not a silent stub.
