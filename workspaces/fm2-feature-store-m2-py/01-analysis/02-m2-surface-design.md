# kailash-ml M2 Feature-Store Surface Design

**Status:** DESIGN ANALYSIS (not implementation) — issue #1302
**Builds on:** shipped 1.0/2.0 read-only `kailash_ml.features.FeatureStore`
**Spec authority:** `specs/ml-feature-store.md` v2.0.0 §1–§6 (shipped contract) + §11 (M2 dispositions)
**Package version at analysis:** kailash-ml 2.0.1 (`packages/kailash-ml/src/kailash_ml/_version.py`)
**Ground-truth reads (this session):**

- `packages/kailash-ml/src/kailash_ml/features/{store,schema,cache_keys,_schema_feature_group,__init__}.py`
- `packages/kailash-ml/src/kailash_ml/errors.py` (re-export of `src/kailash/ml/errors.py`)
- `packages/kailash-ml/src/kailash_ml/tracking/erasure.py` (existing GDPR `erase_subject`)
- `packages/kailash-dataflow/src/dataflow/ml/_feature_source.py` (the `ml_feature_source` duck-type contract)

---

## 0. Ground-Truth Verification (gates the whole design)

Verified by `grep` against canonical `src/kailash/ml/errors.py` this session:

| Symbol                         | Status in errors.py                                      | Disposition                                                      |
| ------------------------------ | -------------------------------------------------------- | ---------------------------------------------------------------- |
| `FeatureGroupNotFoundError`    | **ABSENT**                                               | M2 must land (§6.3, §11.7)                                       |
| `FeatureVersionNotFoundError`  | **ABSENT**                                               | M2 must land                                                     |
| `FeatureEvolutionError`        | **ABSENT**                                               | M2 must land                                                     |
| `OnlineStoreUnavailableError`  | **ABSENT**                                               | M2 must land                                                     |
| `CrossTenantReadError`         | **ABSENT**                                               | M2 must land                                                     |
| `FeatureVersionImmutableError` | **ABSENT**                                               | M2 must land                                                     |
| `ErasureRefusedError`          | PRESENT (`errors.py:466`, `TrackingError` subclass)      | REUSE — do NOT redefine                                          |
| `CrossTenantLineageError`      | PRESENT (`errors.py:644`, `ModelRegistryError` subclass) | REUSE pattern; FeatureStore needs its own `CrossTenantReadError` |

Verified existing composition anchors:

- `ml_feature_source(feature_group, *, tenant_id, point_in_time, since, until, limit) -> polars.LazyFrame` duck-types on `.name` (non-empty str) + callable `.materialize(...)`. It reads `.multi_tenant` (or `.model.multi_tenant`) and `.classification` (propagated as `{"kailash_ml.classification": ...}` polars metadata via `_classification_metadata`).
- Internal `SchemaFeatureGroup` (`_schema_feature_group.py`) ALREADY satisfies this shape and ALREADY computes the polars-side as-of dedup. The public `FeatureGroup` (M2) MUST be distinct from this internal adapter.
- `erase_subject(subject_id, *, tenant_id, ...)` (tracking layer) is the GDPR-erase precedent: tenant-resolve → refusal-gate (`ErasureRefusedError` when a `production` alias is linked) → hot-path delete → immutable audit append. FeatureStore-layer `erase_tenant` mirrors this shape but operates on feature-table rows, not run traces.

**Spec §11.6 constraint (load-bearing for "minimal-correct"):** the 1.0+ constructor is intentionally narrow (`dataflow` positional + `default_tenant_id` kwarg only). M2 MUST prefer **composition** (separate `FeatureMaterialiser` / `FeatureRegistry`) over constructor-flag bloat. This is the single strongest design constraint and it drives every surface below.

---

## 1. Invariant Inventory (per surface — feeds shard-sizing)

Invariants counted per `autonomous-execution.md` § Per-Session Capacity Budget (≤5–10 simultaneous invariants per shard). The count below is the shard-sizing input.

### Surface A — `@feature` decorator + public `FeatureGroup` class

**Invariants (6):**

1. **Distinctness from internal adapter** — public `FeatureGroup` is NOT `SchemaFeatureGroup`; it is the user-facing declarative wrapper that the registry persists and `ml_feature_source` can consume. (orphan-detection: two classes named the same concept is BLOCKED.)
2. **FeatureGroup wraps FeatureSchema (composition, not subclass)** — a `FeatureGroup` HAS-A `FeatureSchema`; it does not re-implement field/dtype validation (`schema.py` already owns that).
3. **Duck-type conformance** — public `FeatureGroup` MUST expose `.name`, `.multi_tenant`, `.classification`, callable `.materialize(...)` so it drops into `ml_feature_source` unchanged (framework-first: no new binding).
4. **Classification propagation** — `FeatureGroup.classification` populated from declared field classifications; flows to `ml_feature_source._classification_metadata` (per `dataflow-classification.md` — classification is a property of the field, carried on every read surface).
5. **`@feature` decorator is declarative-only** — it registers a feature definition (name, dtype, owning group), it does NOT itself materialize (per §11.2: materialization is a separate concern). No side-effecting compute in the decorator body.
6. **Content-addressing preserved** — a `FeatureGroup` derived from a `FeatureSchema` inherits the schema's `content_hash`; two byte-identical group definitions resolve identically (MUST-3 of §3).

### Surface B — `FeatureStore.materialize()` (write-through)

**Invariants (7):**

1. **Tenant isolation via cache_keys** — `materialize()` resolves tenant via `_resolve_tenant` (existing `store.py:120`) before any write; missing tenant → `TenantRequiredError`. Every cache key written/invalidated routes through `make_feature_cache_key` / `make_feature_group_wildcard`.
2. **Write-through DataFlow only (no raw SQL)** — persistence routes through DataFlow Express (`db.express.create`/`bulk_create`/`upsert`) against the backing `@db.model` table; DDL is migration-owned (framework-first + schema-migration Rule 1). Zero raw SQL in `store.py`.
3. **Classification redaction on the return path** — `materialize()` returns a polars DataFrame summarizing what was written; classified columns MUST route through the same redaction the read path uses (`dataflow-classification.md` MUST-1: every mutation return-path applies read redaction).
4. **Point-in-time write integrity** — materialized rows carry their `timestamp_column` value so a later `get_features(timestamp=T)` is point-in-time correct (MUST-5 of §4: as-of correctness depends on per-row event-time being persisted, not synthesized at read).
5. **Idempotent / version-immutable write** — re-materializing an already-registered `(name, version)` MUST NOT silently mutate a frozen version (composes with Surface E version immutability).
6. **Invalidation sweep on overwrite** — a materialize that supersedes cached rows emits the tenant-scoped `v*` wildcard invalidation (`cache_keys.make_feature_group_wildcard`), per tenant-isolation Rule 3a.
7. **Observability** — structured `feature_store.materialize.{start,ok,error}` lines carrying `source="dataflow"`, `mode="real"`, `tenant_id`, `schema`, `version`, `row_count`, `latency_ms`; column names DEBUG-only (observability Rule 8 / spec MUST-7).

### Surface C — Online-store adapter

**Invariants (5):**

1. **Tenant-scoped keyspace** — every online-store key is `make_feature_cache_key`-shaped (tenant is the 2nd dimension); cross-tenant key collision is structurally impossible.
2. **Loud-failure on unavailable backend** — backend absence/unreachable raises `OnlineStoreUnavailableError` (M2 typed), NOT silent degrade to offline (`dependencies.md` § Optional Extras With Loud Failure; mirrors `store.py`'s `_import_ml_feature_source` loud ImportError).
3. **Offline ↔ online consistency** — online reads return values consistent with the offline materialized table for the same `(tenant, group, version, entity)`; the online store is a cache, not a second source of truth.
4. **Adapter is composed, not constructor-flagged** — wired as a separate object passed to the materialiser, NOT a `FeatureStore(online_store=...)` kwarg (§11.6).
5. **GDPR erase reaches online keys** — `erase_tenant` (Surface F) MUST sweep the online keyspace via the tenant wildcard, not just the offline table.

### Surface D — M2 typed exceptions

**Invariants (3):**

1. **Land in canonical `src/kailash/ml/errors.py`** — NOT in `kailash_ml` package; the package `errors.py` only re-exports (identity preservation `kailash_ml.errors.X is kailash.ml.errors.X`). Each new class MUST be added to BOTH the canonical hierarchy AND the `kailash_ml/errors.py` `__all__` re-export list in the SAME PR (orphan-detection Rule 6).
2. **Correct parent class** — `FeatureGroupNotFoundError`, `FeatureVersionNotFoundError`, `FeatureEvolutionError`, `OnlineStoreUnavailableError`, `CrossTenantReadError`, `FeatureVersionImmutableError` are all `FeatureStoreError` subclasses (so existing `except FeatureStoreError` keeps catching them, per §6.2).
3. **Land WITH their raising surface** — each exception lands in the PR that lands the surface that raises it (spec-accuracy Rule 5 + §11.7: no class defined ahead of its raise site). `FeatureGroupNotFoundError` with FeatureGroup/Registry; `FeatureVersionImmutableError` with version immutability; `OnlineStoreUnavailableError` with the online adapter; `CrossTenantReadError` with the cross-tenant read guard.

### Surface E — Feature-evolution / version-immutability enforcement

**Invariants (6):**

1. **Registry-backed `UNIQUE(tenant_id, name, version)`** — immutability is enforced at the registry-mutation site (DataFlow `@db.model` unique constraint), NOT only content-addressed (§11.3 explicitly notes 1.0+ has NO DDL-level uniqueness).
2. **Re-register-with-different-fields raises `FeatureVersionImmutableError`** — registering `(name=x, version=1, fields=B)` when `(name=x, version=1, fields=A)` exists raises (M2 typed).
3. **Evolution is explicit version-bump** — schema evolution routes through the existing `FeatureSchema.with_features(bump_version=True)` (already shipped, `schema.py:283`); an incompatible field change without a bump raises `FeatureEvolutionError`.
4. **Tenant-scoped immutability** — version immutability is per-tenant; tenant A's `(x, v1)` and tenant B's `(x, v1)` are independent rows (composes with Surface F tenant isolation).
5. **Content-hash cross-check** — registry stores `content_hash`; a mutation attempt that changes `content_hash` for a frozen `(name, version)` is the immutability trigger.
6. **`FeatureVersionNotFoundError` on read of absent version** — `get_features` / registry lookup for an unregistered `(name, version)` raises the M2 typed class instead of an opaque `FeatureStoreError` wrapper.

### Surface F — FeatureStore-layer GDPR `erase_tenant`

**Invariants (5):**

1. **Tenant-resolve-then-erase** — mirrors `erase_subject`: resolve tenant via `validate_tenant_id`, refuse if absent.
2. **Refusal gate** — `erase_tenant` refuses with `ErasureRefusedError` (REUSE existing class) if the tenant has a feature group linked to a protected resource (e.g. a `production`-aliased model consuming it). Default disposition without a refusal hook = proceed (same forward-compat hook pattern as `erasure.py`).
3. **Sweeps BOTH offline table AND online keyspace** — deletes backing-table rows (via DataFlow Express delete) AND online-store keys (via the tenant `v*` wildcard). Partial erase is BLOCKED.
4. **Immutable audit append** — erasure appends an audit row (`action='erase'`, `resource_kind='feature_tenant'`, tenant fingerprinted via `fingerprint_classified_value`); audit rows are never deleted (mirrors `erasure.py`).
5. **Idempotent + structured return** — returns an `EraseResult`-shaped dict (`tenant_fingerprint`, per-resource counts); a second call on an already-erased tenant returns zero-counts, not an error.

### Surface G — DB-side windowed as-of (replaces in-memory dedup)

**Invariants (4):**

1. **Semantic equivalence to current polars dedup** — DB-side as-of MUST return the identical "latest row per entity with `timestamp <= T`" result the current `SchemaFeatureGroup` polars `sort+unique` produces (§4 MUST-5, the canonical as-of step). A regression test pins byte-equivalence on a shared fixture.
2. **No raw SQL** — requires a DataFlow aggregation/window primitive (§4 scale-note + `_schema_feature_group.py:34` explicitly defers this to M2 "requires a DataFlow aggregation primitive DataFlow does not yet expose without raw SQL"). This surface is GATED on DataFlow shipping that primitive — if absent, the surface is deferred, NOT raw-SQL'd (framework-first + zero-tolerance Rule 4).
3. **No in-memory candidate-window cap** — removes the `_CANDIDATE_FETCH_LIMIT = 1_000_000` materialize-everything bound; the whole point is large-table scale.
4. **Tenant scoping preserved** — DB-side as-of runs inside the same `db.tenant_context.switch(tenant_id)` binding the current adapter uses.

**Per-surface invariant totals:** A=6, B=7, C=5, D=3, E=6, F=5, G=4. Surface B and Surface E sit at/near the ≤5–10 invariant ceiling → each is its own shard. Surface G is gated on an external DataFlow dependency → separate shard, possibly deferred.

---

## 2. Composition Map (how each surface composes with the 1.0 read path)

```
                         FeatureSchema (shipped, frozen, content-addressed — schema.py)
                                  │ HAS-A
                                  ▼
   @feature decorator ───────► FeatureGroup (PUBLIC, M2) ──duck-types──► dataflow.ml_feature_source
        (declarative)               │  .name/.multi_tenant/.classification/.materialize()    │ (shipped binding)
                                    │                                                         ▼
                                    │                                              polars.LazyFrame
                                    ▼
                          FeatureRegistry (M2, composed)  ◄── persists group defs, enforces
                            │  UNIQUE(tenant,name,version) │    version immutability (Surface E)
                            │  via DataFlow @db.model      │
                            ▼
                          FeatureMaterialiser (M2, composed)  ── write-through via DataFlow Express
                            │  (NOT a FeatureStore kwarg)      │  (Surface B), invalidation sweep
                            ▼
                          OnlineStoreAdapter (M2, composed) ── tenant-scoped keyspace (Surface C)

   FeatureStore (shipped) — get_features() read path UNCHANGED; internally still wraps
     FeatureSchema in the INTERNAL SchemaFeatureGroup adapter. M2 adds thin delegating
     methods (materialize / register / erase_tenant) that forward to the composed
     Materialiser / Registry — FeatureStore stays a facade, gains no constructor flags.
```

**Key composition decisions:**

- **`FeatureGroup` (public) wraps `FeatureSchema`** — it does NOT subclass `SchemaFeatureGroup`. The internal adapter stays internal (read-path bridge); the public class is the user's declarative handle that the registry persists and the binding consumes. Both satisfy the same `ml_feature_source` duck-type, so the read path is unchanged.
- **`materialize()` writes through DataFlow Express** — no raw SQL, no new DDL in `store.py`. The backing table is the user's `@db.model` (convention `schema.name == model name`, already established in `_schema_feature_group.py`).
- **Typed exceptions raised at composed sites, re-raised through `FeatureStore`** — `FeatureStore.get_features` keeps its three-family error pass-through (`store.py:232-257`): `TenantRequiredError` and `ImportError` re-raised unchanged, everything else wrapped. M2 adds the new `FeatureStoreError` subclasses; since they subclass `FeatureStoreError` they slot into the existing `except Exception → FeatureStoreError` path AND can be raised explicitly at the registry/materialiser/online-adapter sites where the specific condition is known. `CrossTenantReadError` is raised at the read guard (a cross-tenant `entity_ids` or group reference); `FeatureVersionNotFoundError` at registry lookup.
- **`erase_tenant` lives on `FeatureStore`, delegates to an erasure helper** mirroring `tracking/erasure.py` — resolve tenant → refusal gate (`ErasureRefusedError`) → DataFlow Express delete + online wildcard sweep → immutable audit append.
- **DB-side as-of replaces the polars dedup INSIDE `SchemaFeatureGroup._query_window`** when DataFlow ships the window primitive — the public read path (`get_features`) is unchanged; only the internal adapter's dedup mechanism swaps.

---

## 3. Minimal-Correct Surface (smallest public API per surface, no constructor-flag bloat)

Per §11.6: prefer composition. The composed objects are constructed separately and passed in / attached, NOT added as `FeatureStore.__init__` kwargs.

### A. `@feature` decorator + `FeatureGroup`

```python
# kailash_ml/features/group.py  (NEW — public FeatureGroup, distinct from internal SchemaFeatureGroup)
class FeatureGroup:
    """Public declarative feature group. Wraps a FeatureSchema; satisfies the
    ml_feature_source duck-type (.name/.multi_tenant/.classification/.materialize)."""
    def __init__(self, schema: FeatureSchema, *, multi_tenant: bool = False,
                 classification: dict | None = None) -> None: ...
    # .name, .multi_tenant, .classification, .materialize(...) — duck-type surface

# kailash_ml/features/decorator.py  (NEW)
def feature(*, group: str, dtype: str, nullable: bool = True, description: str = ""):
    """Declarative registration of one feature column into a named group.
    Does NOT materialize (materialization is FeatureMaterialiser's job)."""
```

Smallest surface: the decorator only declares; `FeatureGroup` only wraps + conforms.

### B. `FeatureStore.materialize()`

```python
async def materialize(
    self, group: FeatureGroup, data: pl.DataFrame, *,
    tenant_id: str | None = None,
) -> pl.DataFrame:
    """Write-through the group's rows via DataFlow Express; return a redacted
    summary frame. Raises FeatureVersionImmutableError on frozen-version mutation."""
```

`FeatureStore` gains one method; the actual write logic lives in a composed `FeatureMaterialiser` (constructed internally from the bound `self._df`, no new constructor kwarg).

### C. Online-store adapter

```python
# kailash_ml/features/online.py  (NEW)
class OnlineStoreAdapter(Protocol):  # Protocol — users bring Redis/DynamoDB impl
    async def get(self, key: str) -> dict | None: ...
    async def set(self, key: str, value: dict) -> None: ...
    async def delete_pattern(self, pattern: str) -> int: ...
# Wired into FeatureMaterialiser via composition: FeatureMaterialiser(df, online=adapter)
```

A `Protocol` (not a base class) keeps the adapter pluggable; absence → `OnlineStoreUnavailableError`.

### D. M2 typed exceptions

Land in `src/kailash/ml/errors.py` as `FeatureStoreError` subclasses; add to `kailash_ml/errors.py` `__all__`. Zero new public API beyond the class names.

### E. `FeatureRegistry` (version immutability)

```python
# kailash_ml/features/registry.py  (NEW — composition, NOT a FeatureStore kwarg)
class FeatureRegistry:
    def __init__(self, dataflow: "DataFlow") -> None: ...   # mirrors FeatureStore Rule 3
    async def register(self, group: FeatureGroup, *, tenant_id: str | None = None) -> None:
        """Persist via @db.model with UNIQUE(tenant,name,version).
        Raises FeatureVersionImmutableError / FeatureEvolutionError."""
    async def get(self, name: str, version: int, *, tenant_id: str | None = None) -> FeatureGroup:
        """Raises FeatureGroupNotFoundError / FeatureVersionNotFoundError."""
```

### F. `erase_tenant`

```python
async def erase_tenant(
    self, *, tenant_id: str | None = None, force: bool = False,
) -> dict:   # EraseResult-shaped
    """Sweep offline rows + online keys for a tenant. Refuses with
    ErasureRefusedError on protected linkage. Appends immutable audit row."""
```

### G. DB-side windowed as-of

No new public API — swaps the internal `SchemaFeatureGroup._query_window` dedup mechanism. Gated on DataFlow window primitive; deferred (not raw-SQL'd) if absent.

---

## 4. Framework-First Check (every surface routes through DataFlow — no raw SQL)

| Surface                        | Persistence/IO path                                                          | Framework-first verdict                                                                                         |
| ------------------------------ | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| A. `@feature` / `FeatureGroup` | none (declarative) + `ml_feature_source` for reads                           | PASS — reuses shipped DataFlow binding                                                                          |
| B. `materialize()`             | DataFlow Express `create`/`bulk_create`/`upsert`; DDL via numbered migration | PASS — zero raw SQL; DDL is migration-owned                                                                     |
| C. online adapter              | user-provided backend behind a Protocol; keys via `cache_keys` helper        | PASS — kailash-ml ships no raw backend driver; loud-failure on absence                                          |
| D. typed exceptions            | n/a                                                                          | PASS — error taxonomy only                                                                                      |
| E. `FeatureRegistry`           | DataFlow `@db.model` + `UNIQUE` constraint; reads via Express                | PASS — immutability is a DB constraint, not hand-rolled                                                         |
| F. `erase_tenant`              | DataFlow Express delete + tenant wildcard online sweep + audit append        | PASS — no raw SQL; mirrors `tracking/erasure.py`                                                                |
| G. DB-side as-of               | **GATED** on a DataFlow window/aggregation primitive                         | CONDITIONAL — if DataFlow lacks the primitive, the surface is DEFERRED, never raw-SQL'd (zero-tolerance Rule 4) |

**Net:** every M2 surface routes through DataFlow for persistence. Surface G is the only framework-first risk — it MUST NOT be unblocked by dropping to raw SQL; if the DataFlow primitive is absent, Surface G stays deferred and the shipped polars-dedup as-of remains the correct 1.x-scale behavior.

---

## 5. Shard-Sizing Recommendation (from invariant counts)

| Shard | Surfaces                                 | Invariants | Notes                                                                                                                                                                             |
| ----- | ---------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1    | D (typed exceptions)                     | 3          | Lands first; other shards depend on the classes existing. Each class lands WITH its raiser, so S1 is the canonical-hierarchy + re-export skeleton; raise-sites added by S3/S4/S5. |
| S2    | A (`@feature` + `FeatureGroup`)          | 6          | Public declarative surface; distinct-from-internal-adapter is the load-bearing invariant.                                                                                         |
| S3    | E (`FeatureRegistry` + immutability)     | 6          | Near ceiling; standalone. Pulls `FeatureVersionImmutableError`/`FeatureEvolutionError`/`FeatureVersionNotFoundError`/`FeatureGroupNotFoundError` raise-sites from S1.             |
| S4    | B (`materialize()`) + C (online adapter) | 7+5        | B is at the 7-invariant ceiling → B alone may be one shard, C a sibling. Split if either grows.                                                                                   |
| S5    | F (`erase_tenant`)                       | 5          | Mirrors `tracking/erasure.py`; standalone.                                                                                                                                        |
| S6    | G (DB-side as-of)                        | 4          | GATED on DataFlow window primitive. Verify the primitive exists before planning; else DEFER per spec §4 scale-note.                                                               |

Surfaces B and E both sit at/near the ≤5–10 invariant ceiling — neither may be bundled with another load-bearing surface. S6 carries an external-dependency gate and may not be schedulable at all this cycle.
