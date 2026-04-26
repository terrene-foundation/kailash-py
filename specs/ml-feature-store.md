# Kailash ML Feature Store Specification

**Version:** 1.1.1 (verified at `packages/kailash-ml/src/kailash_ml/_version.py`)
**Status:** v2.0.0 (re-derived from filesystem mechanical sweeps 2026-04-26 — supersedes v1.0.0)
**Package:** `kailash-ml`
**Canonical module:** `kailash_ml.features` (1.0+ surface)
**Legacy module:** `kailash_ml.engines.feature_store` (0.x surface, retained for 0.x callers; not specified here)
**Parent domain:** ML Lifecycle. See `ml-engines.md` (MLEngine), `ml-tracking.md` (runs/registry), `ml-drift.md` (monitoring), `dataflow-ml-integration.md §1.1` (the `ml_feature_source` polars binding this spec consumes).
**License:** Apache-2.0
**Python:** >=3.11
**Owner:** Terrene Foundation (Singapore CLG)

## Re-Derivation Note

This v2 round 2 draft replaces the v1 outline (`specs/ml-feature-store.md`) AND supersedes round 1 (which retained too much v1 inertia and shipped two CRIT-class fabrications). Section structure is re-derived directly from the canonical 1.0+ surface at `packages/kailash-ml/src/kailash_ml/features/`. v1 capabilities not present in 1.0+ are consolidated under § 11 "Deferred to M2".

Every "is implemented" claim below cites a file:line range read in this session. Every error class cited in § 6 is verified present in `src/kailash/ml/errors.py` via the round-2 mechanical sweep. Every test file cited in § 7 is verified present in `packages/kailash-ml/tests/`.

Origin: Wave 5 portfolio audit findings F-E2-18..24 + Wave 6.5 round-2 re-derivation (2026-04-26).

---

## 1. Scope

### 1.1 What FeatureStore Does in 1.0+

`kailash_ml.features.FeatureStore` is a thin polars-native DataFlow-bridge: it wraps a live `DataFlow` instance and routes every feature read through `dataflow.ml_feature_source(...)`. The store does NOT own a connection pool, does NOT own DDL, does NOT own a registry table — those concerns belong to the parent `DataFlow` and to numbered migrations per `rules/schema-migration.md`.

Concretely, the canonical surface ships:

- A frozen, content-addressed `FeatureSchema` + `FeatureField` dataclass pair (`features/schema.py:122-280`).
- A polars-native `FeatureStore.get_features(schema, timestamp, *, tenant_id, entity_ids)` retrieval method that delegates to `dataflow.ml_feature_source(point_in_time=...)` (`features/store.py:134-257`).
- Tenant-isolation primitives — `validate_tenant_id`, `make_feature_cache_key`, `make_feature_group_wildcard` — under `features/cache_keys.py`.
- Two read-path helpers on `FeatureStore` — `cache_key_for_row` and `invalidation_pattern` — that route through the cache_keys helpers (`features/store.py:263-308`).
- A loud `ImportError` when the DataFlow polars binding is absent (`features/store.py:329-361`), per `rules/dependencies.md` § "Declared = Imported".

### 1.2 What FeatureStore Does NOT Do in 1.0+

The 1.0+ canonical surface does NOT provide: `@feature` decorator, `FeatureGroup` class, registry persistence, materialization scheduling, online-vs-offline split, GDPR `erase_tenant`, feature evolution, version immutability enforcement at the FeatureStore layer, or industry-parity adapters. Each is enumerated under § 11 "Deferred to M2".

### 1.3 Source-File Surface

`packages/kailash-ml/src/kailash_ml/features/`:

- `__init__.py` — public re-exports (6 symbols, see § 2.1)
- `schema.py` — `FeatureField`, `FeatureSchema`, `ALLOWED_DTYPES`
- `store.py` — `FeatureStore` class + `_import_ml_feature_source()` helper
- `cache_keys.py` — tenant-isolation helpers + canonical key shape

---

## 2. Construction

### 2.1 Public Re-Exports (`features/__init__.py:12-27`)

`kailash_ml.features.__all__` exports exactly six symbols:

```python
__all__ = [
    "CANONICAL_SINGLE_TENANT_SENTINEL",
    "FeatureField",
    "FeatureSchema",
    "FeatureStore",
    "make_feature_cache_key",
    "make_feature_group_wildcard",
]
```

Every entry has a corresponding eager module-scope import in `__init__.py` (lines 12-18), satisfying `rules/orphan-detection.md` MUST 6.

### 2.2 `FeatureStore.__init__` Signature

Verified at `features/store.py:98-114`:

```python
def __init__(
    self,
    dataflow: "DataFlow",
    *,
    default_tenant_id: str | None = None,
) -> None:
```

Behaviour:

- `dataflow is None` → raises `TypeError` with the actionable message: `"FeatureStore(dataflow=...) is required — construct via DataFlow(...) and pass the instance in. See rules/facade-manager-detection.md Rule 3."` (`store.py:104-109`).
- `default_tenant_id is not None` → eagerly invokes `validate_tenant_id(default_tenant_id, operation="FeatureStore.__init__")` to fail loudly at construction (`store.py:111-114`).
- `default_tenant_id is None` → store is constructed; every method call MUST then specify `tenant_id` explicitly or `TenantRequiredError` is raised at the call site.

#### MUST 1 — Construction Receives the Live DataFlow Instance

`FeatureStore` MUST receive the parent `DataFlow` instance via the positional `dataflow` argument. Self-construction (`FeatureStore(db_url=...)`) and global-lookup are BLOCKED — see `rules/facade-manager-detection.md` Rule 3.

### 2.3 Read-Only Properties

Verified at `features/store.py:314-321`:

- `fs.dataflow` returns the bound `DataFlow` instance (read-only).
- `fs.default_tenant_id` returns the `default_tenant_id` supplied at construction (read-only, may be `None`).

There are no other public attributes on `FeatureStore`.

---

## 3. Schema (FeatureField + FeatureSchema)

### 3.1 `FeatureField` (`features/schema.py:122-166`)

`@dataclass(frozen=True, slots=True)` with four fields:

| Field         | Type | Default | Validation                                                                                              |
| ------------- | ---- | ------- | ------------------------------------------------------------------------------------------------------- |
| `name`        | str  | —       | Validated against `^[a-zA-Z_][a-zA-Z0-9_]*$` (`schema.py:82`); `_validate_name` does NOT echo raw value |
| `dtype`       | str  | —       | Normalised via `_normalise_dtype` against `ALLOWED_DTYPES` allowlist + synonym table                    |
| `nullable`    | bool | `True`  | —                                                                                                       |
| `description` | str  | `""`    | —                                                                                                       |

`__post_init__` calls `object.__setattr__(self, "dtype", _normalise_dtype(self.dtype))` because the dataclass is frozen.

### 3.2 Dtype Allowlist (`features/schema.py:35-79`)

`ALLOWED_DTYPES` is a `frozenset` containing 19 polars-native dtypes: integer (8), float (2), text (2), bool, temporal (4), binary, categorical. `_DTYPE_SYNONYMS` maps 8 numpy/numpy-style aliases (`float`, `double`, `int`, `long`, `str`, `text`, `string`, `boolean`) to canonical forms.

#### MUST 2 — Dtype Strings Are Polars-Native

`FeatureField.dtype` MUST resolve (after synonym normalisation) to a member of `ALLOWED_DTYPES`. Pandas-style dtype strings outside the synonym table fail at construction with a `ValueError` whose message lists the allowed set (`schema.py:93-98`).

### 3.3 `FeatureSchema` (`features/schema.py:174-280`)

`@dataclass(frozen=True, slots=True)` with five caller-visible fields plus one derived field:

| Field              | Type                     | Default       | Notes                                                          |
| ------------------ | ------------------------ | ------------- | -------------------------------------------------------------- |
| `name`             | str                      | —             | Validated against the SQL identifier regex                     |
| `version`          | int                      | `1`           | MUST be `>= 1`; `bool` rejected via explicit check             |
| `fields`           | tuple[FeatureField, ...] | `()`          | MUST contain ≥1 field; duplicate names rejected                |
| `entity_id_column` | str                      | `"entity_id"` | Validated against the SQL identifier regex                     |
| `timestamp_column` | str \| None              | `None`        | If present, validated against the SQL identifier regex         |
| `content_hash`     | str (init=False)         | derived       | sha256 first-16-hex of canonical payload (`schema.py:248-251`) |

`_canonical_payload` (`schema.py:253-260`) serialises `{name, version, entity_id_column, timestamp_column, fields=[FeatureField.to_dict() ...]}` via `json.dumps(..., sort_keys=True)`, then sha256 → first 16 hex chars.

#### MUST 3 — `content_hash` Stability

`FeatureSchema.content_hash` MUST be deterministic across processes and machines for byte-identical input. Two `FeatureSchema` instances constructed with identical `(name, version, fields, entity_id_column, timestamp_column)` MUST yield the same `content_hash`.

---

## 4. Retrieval

### 4.1 `get_features` Signature

Verified at `features/store.py:134-141`:

```python
async def get_features(
    self,
    schema: FeatureSchema,
    timestamp: datetime | None = None,
    *,
    tenant_id: str | None = None,
    entity_ids: list[str] | None = None,
) -> pl.DataFrame:
```

#### MUST 4 — `get_features` Returns `polars.DataFrame`, Not `LazyFrame`

The public-API boundary returns a concrete `polars.DataFrame`. If `dataflow.ml_feature_source` returns a `LazyFrame`, `get_features` collects it (`store.py:204`). If the binding returns any other type, `FeatureStoreError` is raised with the offending type name in `reason` (`store.py:205-214`).

#### MUST 5 — Point-in-Time Join Delegates to DataFlow

When `timestamp` is supplied, `get_features` MUST pass it through unchanged as `point_in_time=timestamp` to `ml_feature_source` (`store.py:197-201`). The store does NOT compute the as-of join itself — that contract belongs to `dataflow-ml-integration.md §1.1`. `timestamp` MUST be a `datetime`; non-`datetime` raises `TypeError` (`store.py:172-176`).

This is the F-E2-23 positive: PIT join via `dataflow.ml_feature_source(point_in_time=timestamp)` is wired end-to-end.

#### MUST 6 — Tenant Validation Precedes Every Read

`get_features` MUST resolve `tenant_id` via `_resolve_tenant` (`store.py:120-128`) before any read. The resolver returns `tenant_id if tenant_id is not None else self._default_tenant_id`, then passes the result to `validate_tenant_id`. A missing tenant raises `TenantRequiredError`; the read does NOT proceed.

### 4.2 Error Pass-Through

The `try` block at `store.py:193-257` distinguishes three error families:

1. `TenantRequiredError` — re-raised unchanged (`store.py:232-236`). The contract is "tenant is a hard gate"; the store MUST NOT reclassify this as `FeatureStoreError`.
2. `ImportError` — re-raised unchanged (`store.py:237-240`). Operators MUST see the dependency gap clearly.
3. Any other `Exception` — wrapped as `FeatureStoreError(reason="get_features failed: <ExcClassName>", tenant_id=effective_tenant) from exc` (`store.py:241-257`). The `from exc` preserves the original cause for `__cause__` chaining.

### 4.3 Entity-ID Filter

When `entity_ids` is supplied, the returned DataFrame is post-filtered via `df.filter(pl.col(schema.entity_id_column).is_in(entity_ids))` (`store.py:215-216`). This is a polars in-memory filter applied AFTER the binding returns; it does not push down to DataFlow.

### 4.4 Structured Logging

Three structured INFO/EXCEPTION lines, all carrying `source="dataflow"`, `mode="real"`, plus `tenant_id`, `schema` (= `FeatureSchema.name`), `version` (`store.py:181-253`):

| Event                              | Level     | Additional fields               |
| ---------------------------------- | --------- | ------------------------------- |
| `feature_store.get_features.start` | INFO      | `has_timestamp`, `entity_count` |
| `feature_store.get_features.ok`    | INFO      | `row_count`, `latency_ms`       |
| `feature_store.get_features.error` | EXCEPTION | `latency_ms`                    |

#### MUST 7 — INFO-Level Logs MUST NOT Carry Field-Level Schema Identifiers

Per `rules/observability.md` Rule 8 the INFO lines emit the schema NAME (`schema.name` — a logical model identifier) and `version` only. Individual COLUMN names from `FeatureSchema.fields` MUST NOT appear at INFO+ level. The DEBUG path is the only acceptable destination if column-level diagnostics are needed.

---

## 5. Tenant Isolation

This is the F-E2-24 positive set, implemented at `features/cache_keys.py`.

### 5.1 Canonical Cache Key Shape

Verified at `features/cache_keys.py:196-199`:

```
kailash_ml:{FEATURE_KEY_VERSION}:{tenant_id}:feature:{schema_name}:{version}:{row_key}
```

With `FEATURE_KEY_VERSION = "v1"` (`cache_keys.py:42`), the concrete shape today is:

```
kailash_ml:v1:{tenant_id}:feature:{schema_name}:{version}:{row_key}
```

#### MUST 8 — Cache Keys Embed `tenant_id` As The Second Dimension

Every cache key emitted by `make_feature_cache_key` MUST embed `tenant_id` between `FEATURE_KEY_VERSION` and the `feature` literal. This satisfies `rules/tenant-isolation.md` MUST 1 (cache keys include tenant_id for multi-tenant models).

### 5.2 `validate_tenant_id` Contract

Verified at `cache_keys.py:67-126`. The validator rejects:

| Input class                                    | Outcome                               | Site                |
| ---------------------------------------------- | ------------------------------------- | ------------------- |
| `tenant_id is None`                            | `TenantRequiredError`                 | `cache_keys.py:91`  |
| `not isinstance(tenant_id, str)`               | `TenantRequiredError`                 | `cache_keys.py:100` |
| `tenant_id in {"default", "global", ""}`       | `TenantRequiredError`                 | `cache_keys.py:107` |
| `not _TENANT_RE.match(tenant_id)` (regex fail) | `TenantRequiredError` (fingerprinted) | `cache_keys.py:117` |

Tenant-id regex (`cache_keys.py:56`): `^[A-Za-z_][A-Za-z0-9_\-]*$`. Colons are rejected because they would split the key shape; the validator's error message uses a 16-bit hash fingerprint to avoid echoing the rejected raw input.

#### MUST 9 — Forbidden Sentinels Raise, Not Default

`FORBIDDEN_TENANT_SENTINELS = frozenset({"default", "global", ""})` (`cache_keys.py:50`). Single-tenant deployments MUST use the canonical sentinel `CANONICAL_SINGLE_TENANT_SENTINEL = "_single"` (`cache_keys.py:46`); the validator accepts `"_single"` because the leading-underscore form satisfies `_TENANT_RE`.

Silent fallback to a default tenant is BLOCKED — this satisfies `rules/tenant-isolation.md` MUST 2 (multi-tenant strict mode — missing `tenant_id` is a typed error).

### 5.3 Invalidation Pattern (Version-Wildcard)

`make_feature_group_wildcard` (`cache_keys.py:202-224`) emits patterns matching the `v*` keyspace-version wildcard so a future `FEATURE_KEY_VERSION` bump (e.g. `v1 → v2`) does not strand legacy keys.

| Args                                            | Pattern                          |
| ----------------------------------------------- | -------------------------------- |
| `tenant_id="t1", schema_name="s", version=None` | `kailash_ml:v*:t1:feature:s:*`   |
| `tenant_id="t1", schema_name="s", version=2`    | `kailash_ml:v*:t1:feature:s:2:*` |

Tenant-scoped invalidation is REQUIRED — `make_feature_group_wildcard` calls `validate_tenant_id` first, so a missing tenant raises before any pattern is built. This satisfies `rules/tenant-isolation.md` MUST 3 (tenant-scoped invalidation) AND MUST 3a (keyspace-version wildcard sweep).

### 5.4 `row_key` Validation Contract

Verified at `cache_keys.py:186-195`. The contract for `row_key`:

- MUST be a non-empty string (`cache_keys.py:186-189`).
- MUST NOT contain `:` (`cache_keys.py:192-195`).
- No further regex is applied — `row_key` is opaque to the helper. It is NOT interpolated into SQL; it only goes into the Redis-compatible cache key namespace.

The `row_key` is rejected (not escaped) to keep key shape unambiguous.

### 5.5 Schema-Name Validation

`_validate_schema_name` (`cache_keys.py:129-140`) requires `schema_name` to match `^[a-zA-Z_][a-zA-Z0-9_]*$`. Failure raises `ValueError` with a 16-bit fingerprint, not the raw input.

### 5.6 Version Validation

`_validate_version` (`cache_keys.py:143-153`) requires `version` to be `int` (NOT `bool`) AND `>= 1`.

### 5.7 `FeatureStore.cache_key_for_row` and `invalidation_pattern`

These read-path helpers on the store delegate directly to the cache_keys module after resolving tenant via `_resolve_tenant` (`store.py:263-308`):

- `fs.cache_key_for_row(schema, row_key, *, tenant_id=None) -> str` calls `make_feature_cache_key(...)`.
- `fs.invalidation_pattern(schema, *, tenant_id=None, all_versions=False) -> str` calls `make_feature_group_wildcard(version=None if all_versions else schema.version)`.

Centralising the call sites here means a future keyspace-version bump patches one method per concern, not the entire codebase.

---

## 6. Errors

This section enumerates ONLY error classes that (a) exist in `src/kailash/ml/errors.py` AND (b) are reachable from the `kailash_ml.features.FeatureStore` surface in 1.0+.

### 6.1 Exception Classes Raised From The Canonical Surface

| Class                   | Defined in `errors.py`                                                                                | Raised at                                       | When                                                                    |
| ----------------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------- |
| `TypeError` (builtin)   | n/a (builtin)                                                                                         | `store.py:104-109`                              | `FeatureStore(None)` — missing dataflow positional argument             |
| `TypeError` (builtin)   | n/a (builtin)                                                                                         | `store.py:165-168`                              | `get_features(schema, ...)` where schema is not `FeatureSchema`         |
| `TypeError` (builtin)   | n/a (builtin)                                                                                         | `store.py:172-176`                              | `get_features(..., timestamp=...)` where timestamp is not `datetime`    |
| `TypeError` (builtin)   | n/a (builtin)                                                                                         | `schema.py:88-90`, `:104-105`, `:213-217`       | `FeatureField.dtype` not str; `FeatureSchema.version` not int           |
| `ValueError` (builtin)  | n/a (builtin)                                                                                         | `schema.py:93-98`, `:106-114`, `:218-225`       | dtype not allowed; identifier regex fail; empty fields                  |
| `ValueError` (builtin)  | n/a (builtin)                                                                                         | `cache_keys.py:131-139`, `:149-152`, `:186-195` | `schema_name`/`version`/`row_key` validation failures                   |
| `TenantRequiredError`   | `errors.py:389` (line of `class TenantRequiredError`) — declared at the canonical TrackingError home. | `cache_keys.py:91`, `:100`, `:107`, `:117`      | Missing/non-str/forbidden-sentinel/regex-fail tenant_id                 |
| `ImportError` (builtin) | n/a (builtin)                                                                                         | `store.py:354-361`                              | `dataflow.ml_feature_source` not importable from either resolution path |
| `FeatureStoreError`     | `errors.py:315` (`class FeatureStoreError(MLError)`)                                                  | `store.py:208-214`, `:254-257`                  | Binding returned non-DataFrame; or any other `Exception` from binding   |

`FeatureStoreError` is constructed with kwarg-only `reason=` per `MLError.__init__` (`errors.py:245-259`). The full kwargs surface is `reason=`, `tenant_id=`, `actor_id=`, `resource_id=`, `**context`.

### 6.2 Exception Classes Defined But NOT Raised From The Canonical FeatureStore Surface

Three subclasses of `FeatureStoreError` exist in `errors.py:632-643` but are NOT reached by any code path in `kailash_ml.features.FeatureStore` today:

| Class                       | Defined in `errors.py` | 1.0+ FeatureStore call sites |
| --------------------------- | ---------------------- | ---------------------------- |
| `FeatureNotFoundError`      | `errors.py:632`        | none                         |
| `StaleFeatureError`         | `errors.py:636`        | none                         |
| `PointInTimeViolationError` | `errors.py:641`        | none                         |

These typed exceptions are part of the M2 surface (see § 11). The 1.0+ FeatureStore does NOT raise them — feature-not-found at the polars-binding level surfaces as a `FeatureStoreError` wrapper with the original exception preserved via `from exc`. Downstream code that catches `FeatureStoreError` will continue to catch the M2 subclasses once the wiring lands; but downstream code MUST NOT today `try/except` against `FeatureNotFoundError` etc. expecting it to surface from `kailash_ml.features.FeatureStore` — those paths do not raise these classes today.

### 6.3 NOT Defined Anywhere — Do Not Reference

The following classes do NOT appear in `src/kailash/ml/errors.py` (verified via round-2 grep). v1 (and round 1 of this v2) referred to them; downstream code MUST NOT `try/except` against them.

`FeatureGroupNotFoundError`, `FeatureVersionNotFoundError`, `FeatureEvolutionError`, `OnlineStoreUnavailableError`, `CrossTenantReadError`, `FeatureVersionImmutableError`.

These are M2 placeholders to be defined IF and WHEN the corresponding surfaces (feature groups, evolution, online store, cross-tenant read guard, version immutability) ship — see § 11.

---

## 7. Test Contract

### 7.1 Tests That DO Exist (Verified Via `find`)

Filesystem sweep: `find packages/kailash-ml/tests -name 'test_feature*'` yields six files. Three of these exercise the canonical 1.0+ surface (verified via grep for `from kailash_ml.features` imports):

| File                                          | Tier | Surface exercised                                                                                                                                   |
| --------------------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/unit/test_feature_store_unit.py`       | T1   | Canonical (`from kailash_ml.features import FeatureStore`) — constructor validation, tenant resolution, cache helpers, deferred-import loud failure |
| `tests/unit/test_feature_store_schema.py`     | T1   | Canonical (`from kailash_ml.features import FeatureField, FeatureSchema`)                                                                           |
| `tests/unit/test_feature_store_cache_keys.py` | T1   | Canonical (`from kailash_ml.features import ...`)                                                                                                   |
| `tests/integration/test_feature_store.py`     | T2   | **LEGACY** (`from kailash_ml.engines.feature_store import FeatureStore`) — exercises the 0.x engine, NOT the 1.0+ canonical surface                 |
| `tests/unit/test_feature_engineer.py`         | T1   | Out-of-scope (feature-engineering primitive, not FeatureStore)                                                                                      |
| `tests/unit/test_feature_sql.py`              | T1   | Out-of-scope (legacy SQL builder)                                                                                                                   |

### 7.2 Test The Canonical FeatureStore Currently Lacks

The canonical 1.0+ `kailash_ml.features.FeatureStore` has **zero Tier-2 wiring tests** — the existing `tests/integration/test_feature_store.py` exercises the LEGACY `kailash_ml.engines.feature_store` module (verified by reading line 15: `from kailash_ml.engines.feature_store import FeatureStore`).

Per `rules/facade-manager-detection.md` MUST 1 (every `*Store` manager exposed via the public surface MUST have a Tier-2 test imported through the framework facade) AND MUST 2 (the test file MUST be named `test_<lowercase_manager_name>_wiring.py` so the absence is grep-able), this is a gap.

#### Wave 6 follow-up: create `packages/kailash-ml/tests/integration/test_feature_store_wiring.py` exercising `kailash_ml.features.FeatureStore` via a real `DataFlow(...)` instance + real Postgres + the `dataflow.ml_feature_source` binding. The wiring test SHOULD cover the conformance assertions in § 10.

Until that test lands, the canonical FeatureStore surface MUST be marked as having a Tier-2 wiring gap in any release notes that announce it as production-ready.

---

## 8. Examples

DOCS-EXACT code that runs against the canonical 1.0+ surface.

### 8.1 Schema Definition

```python
from datetime import datetime, timezone
from kailash_ml.features import FeatureField, FeatureSchema

schema = FeatureSchema(
    name="user_churn",
    version=1,
    fields=(
        FeatureField(name="login_count_7d", dtype="int64"),
        FeatureField(name="purchase_amount_30d", dtype="float64"),
        FeatureField(name="is_premium", dtype="bool", nullable=False),
    ),
    entity_id_column="user_id",
    timestamp_column="event_time",
)

print(schema.content_hash)  # 16-hex deterministic fingerprint
print(schema.field_names)   # ['login_count_7d', 'purchase_amount_30d', 'is_premium']
```

### 8.2 Feature Retrieval (Multi-Tenant)

```python
from datetime import datetime, timezone
from dataflow import DataFlow
from kailash_ml.features import FeatureStore

db = DataFlow("postgresql://...")  # caller owns the lifecycle
fs = FeatureStore(db)

# Latest values, scoped to tenant "acme":
df_latest = await fs.get_features(schema, tenant_id="acme")

# Point-in-time correct (as-of 2026-04-01T00:00:00Z), scoped to tenant "acme",
# filtered to 3 entities:
as_of = datetime(2026, 4, 1, tzinfo=timezone.utc)
df_pit = await fs.get_features(
    schema,
    timestamp=as_of,
    tenant_id="acme",
    entity_ids=["u1", "u2", "u3"],
)
```

### 8.3 Single-Tenant Default

```python
from kailash_ml.features import CANONICAL_SINGLE_TENANT_SENTINEL, FeatureStore

# Single-tenant deployment: bind the sentinel at construction; method calls
# can omit tenant_id thereafter.
fs = FeatureStore(db, default_tenant_id=CANONICAL_SINGLE_TENANT_SENTINEL)
df = await fs.get_features(schema)  # tenant_id omitted; default applies
```

### 8.4 Cache Key + Invalidation

```python
key = fs.cache_key_for_row(schema, row_key="u1", tenant_id="acme")
# → 'kailash_ml:v1:acme:feature:user_churn:1:u1'

pattern = fs.invalidation_pattern(schema, tenant_id="acme")
# → 'kailash_ml:v*:acme:feature:user_churn:1:*'

pattern_all_versions = fs.invalidation_pattern(schema, tenant_id="acme", all_versions=True)
# → 'kailash_ml:v*:acme:feature:user_churn:*'
```

---

## 9. Cross-References

Sibling specs that interact with the FeatureStore surface:

- **`dataflow-ml-integration.md §1.1`** — owner of `dataflow.ml_feature_source(feature_group, *, tenant_id, point_in_time)`. The canonical FeatureStore retrieval path (§ 4.1) DOES NOT implement the polars binding; it delegates. Any change to `ml_feature_source`'s signature or semantics requires this spec to re-derive § 4. Per `rules/specs-authority.md` § 5b a sibling-spec re-derivation sweep is mandatory when this spec changes.
- **`ml-engines.md`** — `MLEngine` may consume features via `FeatureStore` for `fit_auto`/`compare`. Today's `MLEngine` does not import the canonical `FeatureStore`; an integration is M2.
- **`ml-tracking.md`** — `tenant_id` semantics + `CANONICAL_SINGLE_TENANT_SENTINEL` ("\_single") originate in `ml-tracking.md §7.2`. This spec re-uses that sentinel verbatim.
- **`ml-drift.md`** — drift monitoring (M2) will consume materialised feature snapshots; today no integration.
- **`rules/tenant-isolation.md`** MUST 1, 2, 3, 3a — satisfied at `cache_keys.py` (see § 5.1, § 5.2, § 5.3 above).
- **`rules/facade-manager-detection.md`** MUST 1, 2, 3 — partially satisfied (constructor takes parent framework instance per Rule 3; Tier-2 wiring test absent per Rule 1, see § 7.2).
- **`rules/orphan-detection.md`** MUST 6 — satisfied (`__init__.py:12-27` imports every `__all__` entry eagerly).
- **`rules/dependencies.md`** § "Declared = Imported" — satisfied by loud `ImportError` at `store.py:354-361`.
- **`rules/observability.md`** Rule 8 — satisfied (INFO logs emit schema NAME, never field names).
- **`rules/schema-migration.md`** — FeatureStore owns NO DDL. Any feature-table DDL belongs to numbered migrations under `dataflow-ml-integration.md §1.1`.

---

## 10. Conformance Checklist

A feature-store implementation claiming "1.0+ canonical surface" MUST satisfy ALL of:

- [ ] `kailash_ml.features.__all__` lists exactly the six symbols in § 2.1, every one with a corresponding eager import.
- [ ] `FeatureStore.__init__(dataflow, *, default_tenant_id=None)` signature matches § 2.2 exactly.
- [ ] `FeatureStore(None)` raises `TypeError` with the actionable message at `store.py:104-109`.
- [ ] `default_tenant_id` is eager-validated at construction via `validate_tenant_id`.
- [ ] `fs.dataflow` and `fs.default_tenant_id` are read-only properties.
- [ ] `FeatureSchema.content_hash` is sha256 first-16-hex of the canonical payload, deterministic across processes.
- [ ] `FeatureField.dtype` rejects non-allowlist values at construction.
- [ ] `get_features(schema, timestamp=None, *, tenant_id=None, entity_ids=None) -> pl.DataFrame` matches § 4.1 exactly.
- [ ] `get_features` re-raises `TenantRequiredError` and `ImportError` unchanged; wraps every other `Exception` as `FeatureStoreError(reason=..., tenant_id=...) from exc`.
- [ ] Cache key shape matches `kailash_ml:v1:{tenant_id}:feature:{schema_name}:{version}:{row_key}`.
- [ ] `validate_tenant_id` rejects `None`, non-`str`, the three forbidden sentinels, and any tenant*id failing `^[A-Za-z*][A-Za-z0-9_\-]\*$`.
- [ ] `make_feature_group_wildcard` emits `v*` so a future keyspace-version bump does not strand legacy keys.
- [ ] `_import_ml_feature_source` raises a loud `ImportError` whose message names the upstream binding requirement and points to `dataflow-ml-integration.md §1.1`.
- [ ] Three structured INFO/EXCEPTION lines emitted on every `get_features` call: `feature_store.get_features.{start,ok,error}`.
- [ ] No column names from `FeatureSchema.fields` appear at INFO+ log level.
- [ ] The error classes raised from this surface are exactly the eight in § 6.1; classes in § 6.3 are NEVER raised.

---

## 11. Deferred to M2

Each entry below was specified in v1 and does NOT exist in 1.0+. The Wave 5 audit (F-E2-18..22) flagged these. Each entry: what was specified, what's in 1.0+, M2 disposition.

### 11.1 Feature Groups (was § 4 in v1; F-E2-19)

V1 specified a `FeatureGroup` class with online + offline views, materialisation policies, and online-store backends.

1.0+ ships only `FeatureSchema` (the schema definition) plus `FeatureStore.get_features` (a single retrieval surface). There is no `FeatureGroup` class. Online vs offline split is collapsed into "whatever `dataflow.ml_feature_source` returns".

**M2 disposition:** Re-introduce `FeatureGroup` if and only if a downstream Engine surfaces a need that `FeatureSchema + ml_feature_source(...)` cannot express. If introduced, define `FeatureGroupNotFoundError` in `errors.py` (currently absent — see § 6.3) at the same time the class lands.

### 11.2 `@feature` Decorator + Materialization (was § 5 in v1; F-E2-18)

V1 specified `@feature` for declarative materialisation pipelines + scheduling.

1.0+ ships nothing in this surface. Materialisation is a DataFlow concern; scheduling lives in workflow primitives.

**M2 disposition:** Defer until DataFlow ships a materialisation primitive that the FeatureStore can wrap. The decorator surface is a UX concern best deferred until the underlying mechanism ships.

### 11.3 Feature Versioning + Immutability Enforcement (was § 7 in v1; F-E2-20)

V1 specified that registered feature versions are immutable; mutation attempts raise `FeatureVersionImmutableError`.

1.0+ ships `FeatureSchema.version: int` (`schema.py:203`) which is part of the content-addressed hash, but there is NO registry-backed immutability check at the `FeatureStore` layer. `FeatureVersionImmutableError` does NOT exist in `errors.py` (verified § 6.3).

**M2 disposition:** Define `FeatureVersionImmutableError` in `errors.py` AND wire the immutability check at the registry-mutation site (M2 — when the registry-backed feature group lands, see § 11.1). Today, immutability is content-addressed only — two callers writing `FeatureSchema(name="x", version=1, fields=A)` and `FeatureSchema(name="x", version=1, fields=B)` produce different `content_hash` values, but the FeatureStore has no DDL-level `UNIQUE(name, version)` enforcement to reject the second registration.

### 11.4 Storage / Retention / Eraser (was § 8 in v1; F-E2-21)

V1 specified online-store backends (Redis, DynamoDB) + retention policies + GDPR `erase_tenant`.

1.0+ ships none of this. The cache-key helpers in § 5 produce keys SUITABLE for a Redis backend, but no Redis adapter is shipped at the FeatureStore layer.

**M2 disposition:** Defer. GDPR erasure is a cross-cutting concern — `ml-tracking.md §8.4` already defines `ErasureRefusedError` (canonical home: `TrackingError`) — when the FeatureStore lands a registry-backed online surface, GDPR erasure plumbs through that path.

### 11.5 Industry Parity Adapters (was § 15 in v1)

V1 enumerated parity adapters for sibling feature-store products.

1.0+ ships none of this. Per `rules/independence.md` no commercial-product comparisons appear in the spec.

**M2 disposition:** Defer indefinitely. If users request a migration adapter, ship an external `kailash-feature-store-migrate` package.

### 11.6 Constructor Kwargs Subset (F-E2-18)

V1 implied a richer constructor surface (e.g. `FeatureStore(connection_manager=..., online_store=..., retention=...)`).

1.0+ ships exactly two kwargs: `dataflow` (positional) + `default_tenant_id=` (kwarg-only). The 1.0+ surface is intentionally narrow per `rules/facade-manager-detection.md` Rule 3.

**M2 disposition:** Defer constructor expansion. If new kwargs are needed, prefer composition (separate `FeatureMaterialiser`, `FeatureRegistry`) over constructor-flag bloat.

### 11.7 Typed Exceptions Absent At The Surface (F-E2-22)

The five exception classes referenced in v1 (and falsely cited by round 1 of this draft) do NOT exist in `errors.py` today (§ 6.3): `FeatureGroupNotFoundError`, `FeatureVersionNotFoundError`, `FeatureEvolutionError`, `OnlineStoreUnavailableError`, `CrossTenantReadError`.

**M2 disposition:** Each will land in `errors.py` at the same PR that lands the corresponding surface (§ 11.1, § 11.2, § 11.3, § 11.4). Until then, downstream code MUST NOT `try/except` against any of these classes.

---

**End of v2 round 2 draft. Mechanical sweeps performed: 5. All "is implemented" claims cite a file:line range read in this session. The fabricated symbols flagged by the round-1 reviewer have been deleted and consolidated under § 6.3 + § 11.7 as "deferred + not yet defined".**
