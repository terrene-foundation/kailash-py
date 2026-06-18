# #1241 — Canonical FeatureStore.get_features: Architecture Plan

Status: design COMPLETE + verified (file:line cited). User decision: **build the real read adapter now** (not honest-deferral).
Specialist consultation attempted twice (ml + dataflow) — both infra-rate-limited (0–5 tokens); the central as-of question was resolved by direct code investigation below. Gate-review (reviewer + security-reviewer) deferred to subagent-infra recovery.

## Root cause (corrected — bigger than the issue stated)

- `FeatureStore.get_features(schema,…)` (`packages/kailash-ml/src/kailash_ml/features/store.py:133-257`) forwards a declarative `FeatureSchema` to `dataflow.ml_feature_source(...)` at `store.py:197`.
- The binding (`packages/kailash-dataflow/src/dataflow/ml/_feature_source.py:77-103,195-280`) duck-types on a **FeatureGroup-shaped** object: `.name` + callable `.materialize(*, tenant_id, point_in_time, since, until, limit) -> polars.LazyFrame`. It calls `feature_group.materialize(...)` at `_feature_source.py:245`.
- `FeatureSchema` (`features/schema.py`) exposes only `name/version/fields/entity_id_column/timestamp_column/to_dict/from_dict/field_names/with_features/content_hash` — **no `.materialize`** → `_validate_feature_group_shape` raises `FeatureSourceError` → re-wrapped `FeatureStoreError`. Every call raises.
- `FeatureGroup` / `.materialize` exist **nowhere** in kailash-ml (grep-confirmed). `specs/ml-feature-store.md §11` explicitly defers `FeatureGroup` to M2. So `get_features` was specced against a class its own spec says doesn't exist yet.
- **Spec contradiction + false claim:** `specs/dataflow-ml-integration.md:13` claims the binding is "consumed by `FeatureStore.get_features(...)` end-to-end (verified positive at audit finding F-E2-23)." This is FALSE — `get_features` has never worked. MUST be corrected.

## Chosen design (Candidate 1 — spec-§1.1-consistent thin bridge)

Build a `FeatureSchema → FeatureGroup-shaped` **read adapter** inside kailash-ml; `get_features` constructs it from `(schema, self._df)` and passes it to the unchanged binding. Reference shape: `DataFlowTableFeatureGroup` in `packages/kailash-dataflow/tests/integration/test_dataflow_ml_feature_source_wiring.py:47-108` (but that test-double IGNORES point_in_time — we MUST implement real as-of).

### New file: `packages/kailash-ml/src/kailash_ml/features/_schema_feature_group.py`

```
class _SchemaFeatureGroup:
    def __init__(self, *, dataflow, schema, multi_tenant=False): ...
    name: str            # == schema.name (table/model convention)
    multi_tenant: bool
    classification: dict | None
    def materialize(self, *, tenant_id, point_in_time, since, until, limit):
        rows = _query_as_of(self._df, self._schema.name,
                            entity_id_col=schema.entity_id_column,
                            timestamp_col=schema.timestamp_column,
                            field_cols=list(schema.field_names()),
                            tenant_id=tenant_id, point_in_time=point_in_time,
                            since=since, until=until, limit=limit)
        frame = pl.DataFrame(rows) if rows else pl.DataFrame()
        # as-of: latest row per entity (already filtered ts<=T by the query)
        if point_in_time is not None and frame.height and timestamp_col in frame.columns:
            frame = (frame.sort(timestamp_col, descending=True)
                          .unique(subset=[entity_id_col], keep="first"))
        keep = [entity_id_col] + [c for c in field_cols if c in frame.columns]
        if frame.width: frame = frame.select([c for c in keep if c in frame.columns])
        return frame.lazy()
```

### As-of join (framework-first; NO raw SQL) — VERIFIED

- DataFlow `database/query_builder.py:35-46` translates `$gt/$gte/$lt/$lte/$in` → SQL `>/>=/</<=/IN`.
- `express.list(model, filter=..., limit=..., order_by="-ts")` supports MongoDB filter + order_by (`features/express.py:1004-1031`) but has **no group-by/distinct** → "latest PER ENTITY" is NOT expressible in `list` alone.
- Therefore: **DataFlow fetches the candidate window** (`filter={ts:{"$lte":T}}`, `+ {ts:{"$gte":since}}` / `{ts:{"$lte":until}}` for window, `+ entity_id:{"$in":entity_ids}`, `+ tenant_id` for multi_tenant), **polars computes the as-of** dedup (`.sort(ts,desc).unique(subset=entity, keep="first")`). Each tool native to its job; matches the "polars-native feature store" framing.

### `_query_as_of(...)` helper (in kailash-ml, calls DataFlow read API only)

Builds the MongoDB filter dict, calls the DataFlow read. **Sync/async:** `get_features` is `async def`; the binding calls `materialize()` synchronously; the reference double uses `db.express_sync.list(...)`. → adapter `materialize` is **sync**, uses `self._df.express_sync.list(...)` (mirrors the reference). Confirm `express_sync` exists on the live DataFlow at call time.

### store.py edit (minimal — `store.py:193-201` only)

Replace `lazy = ml_feature_source(schema, tenant_id=…, point_in_time=…)` with:

```
group = _SchemaFeatureGroup(dataflow=self._df, schema=schema,
                            multi_tenant=<detected>)
lazy = ml_feature_source(group, tenant_id=effective_tenant, point_in_time=timestamp)
```

Keep `store.py:202-257` (collect/DataFrame-contract/`entity_ids` filter/logging/error-wrap) UNCHANGED. `entity_ids` already post-filtered at `store.py:215-216` — but pushing `$in` into the query is cheaper; keep BOTH (push-down + existing post-filter is harmless defense-in-depth). Tenant already validated upstream by `_resolve_tenant` (`store.py:169-171`) — do NOT double-raise.

### Binding: NO change. `ml_feature_source` already consumes FeatureGroup-shape correctly.

## Backing-table convention

`schema.name` == DataFlow model name (FeatureSchema has no explicit model ref). Spec §1.1 framing ("thin bridge, does NOT own DDL") → the store reads a table the USER registered via `@db.model`; ingestion is the user's (no write path added — out of scope, M2). Document this convention in get_features docstring + spec §4.

## Tests (Tier-2 file-backed sqlite per binding-test precedent; Tier-3 Postgres)

New `packages/kailash-ml/tests/integration/test_feature_store_get_features_wiring.py`:

1. happy path → DataFrame with entity_id + field columns, real rows.
2. **point-in-time correctness**: write entity e1 rows at t1(v=1) and t3(v=3); `get_features(schema, timestamp=t2)` → e1 row has v=1 (latest ≤ t2), NOT v=3.
3. tenant scoping (multi_tenant model).
4. `entity_ids` filter.
5. empty table → empty DataFrame (not raise).
6. classification metadata propagation survives.
   Rewrite `tests/integration/test_feature_store_wiring.py::test_assertion_09b`: happy path now returns DataFrame; move the FeatureStoreError contract assertion to a genuine error (e.g. missing/unmigrated table).
   Regression: `tests/regression/test_issue_1241_get_features_returns_dataframe.py`.

## Spec reconciliation (same PR)

- `specs/ml-feature-store.md §4`: document the schema.name→table convention + that get_features now returns real data; reconcile §6.2 MUST-1 (as-of) with the polars-dedup implementation location.
- `specs/dataflow-ml-integration.md:13`: DELETE the false "verified positive F-E2-23 end-to-end" claim; correct the `FeatureGroup` import path note (adapter is kailash-ml-internal `_SchemaFeatureGroup`, the binding stays duck-typed).

## Cross-SDK (cross-sdk-inspection MUST)

Check kailash-rs FeatureStore retrieval path for the same gap; file scoped issue if present (human-gated per upstream-issue-hygiene).

## Sizing

~1 shard: adapter ~80 LOC + helper ~40 LOC + store edit ~10 LOC load-bearing; invariants: as-of correctness, tenant scoping, DataFrame contract, column selection, classification metadata (5). Live feedback loop (Tier-2 tests). Fits one shard.

## Gate status

- /implement reviewer + security-reviewer: REQUIRED (agents.md MUST) — run on infra recovery.
- This is a kailash-ml package change → version bump + `/release` if it lands (per feedback_build_repo_release).
