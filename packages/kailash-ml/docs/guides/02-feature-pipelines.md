# Feature Pipelines

Build polars-native feature pipelines with FeatureStore integration.

## FeatureStore Basics

Since kailash-ml 2.0.0, the top-level `FeatureStore` is the canonical 1.0+
**read** surface — a thin polars-native bridge over a live `DataFlow`
instance. It owns no DDL: you materialise features as ordinary `@db.model`
rows and read them back point-in-time-correct through `get_features`. The
backing table's name equals the schema's `name`.

```python
from datetime import datetime, timezone

from dataflow import DataFlow
from kailash_ml import FeatureStore
from kailash_ml.features import (
    CANONICAL_SINGLE_TENANT_SENTINEL,
    FeatureField,
    FeatureSchema,
)

df = DataFlow("sqlite:///ml.db", auto_migrate=True)


# Write path: features are ordinary DataFlow model rows. The model name
# MUST equal the FeatureSchema name the store reads.
@df.model
class UserFeatures:
    id: str
    user_id: str            # entity_id_column
    event_time: datetime    # timestamp_column
    income: float
    tenure_days: int


df.express_sync.create("UserFeatures", {
    "id": "r1", "user_id": "u1",
    "event_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
    "income": 50000.0, "tenure_days": 30,
})

# Read path: declare the schema, then retrieve through the canonical store.
schema = FeatureSchema(
    name="UserFeatures",
    version=1,
    fields=(
        FeatureField(name="income", dtype="float64"),
        FeatureField(name="tenure_days", dtype="int64"),
    ),
    entity_id_column="user_id",
    timestamp_column="event_time",
)

# Single-tenant: bind the canonical sentinel; multi-tenant: pass tenant_id=...
store = FeatureStore(df, default_tenant_id=CANONICAL_SINGLE_TENANT_SENTINEL)

# Latest value per entity (or as-of a timestamp) as a polars.DataFrame.
features = await store.get_features(schema)
as_of = await store.get_features(schema, timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc))
```

> **Need the self-contained write engine?** The legacy 0.x surface
> (`register_features` / `store` / `compute` / `get_training_set` /
> `get_features_lazy` / `list_schemas`) remains available via the explicit
> import `from kailash_ml.engines.feature_store import FeatureStore`
> (constructor `FeatureStore(conn, *, table_prefix=...)`). See `MIGRATION.md`.

## Polars Pipelines

kailash-ml is polars-native. All engines accept `pl.DataFrame` directly.

```python
import polars as pl

# Feature engineering with polars expressions
df_feats = raw.with_columns([
    (pl.col("income") / pl.col("age")).alias("income_per_year_of_age"),
    pl.col("tenure_days").cast(pl.Float64).alias("tenure_years") / 365.0,
    pl.when(pl.col("income") > 100000).then(1).otherwise(0).alias("high_income"),
])
```

## Point-in-Time Correctness

`get_features(schema, timestamp=T)` returns each entity's value AS OF `T` —
the latest row with `event_time <= T`, never a value materialised after `T`
(`specs/ml-feature-store.md` § 6.2). With no `timestamp`, the latest value per
entity is returned. The backing table can hold the full history; the store
computes the as-of view.

## Common Errors

- **`TenantRequiredError`** — `get_features` requires a tenant. Pass
  `tenant_id=...`, or construct the store with `default_tenant_id=` (use
  `CANONICAL_SINGLE_TENANT_SENTINEL` for single-tenant deployments).
- **`FeatureStoreError`** — wraps a failure from the underlying DataFlow read
  (for example, the backing model named after `schema.name` was never
  registered or migrated). Define the `@db.model` and `auto_migrate` first.
