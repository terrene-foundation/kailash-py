# ML Feature Pipelines

The legacy `FeatureStore` engine provides polars-native feature materialisation,
point-in-time queries, and schema-enforced storage. All SQL is isolated in
`_feature_sql.py` — zero raw SQL in engine files.

> **Which FeatureStore?** Since kailash-ml 2.0.0 (#643) the top-level
> `from kailash_ml import FeatureStore` resolves to the **canonical read surface**
> (`kailash_ml.features.FeatureStore` — a DataFlow bridge that reads features you
> materialise as ordinary `@db.model` rows; see `dataflow-ml-integration.md`). The
> self-contained **write/registry/training** engine shown here is the legacy
> surface, reached via its explicit module path. Use it when you need
> `register_features` / `store` / `get_training_set` (the canonical read store does
> not expose a write path). See `MIGRATION.md` for the canonical recipe.

## FeatureStore Setup

The legacy engine uses ConnectionManager (not Express) because point-in-time
queries require window functions that Express cannot express.

```python
from kailash.db.connection import ConnectionManager
from kailash_ml.engines.feature_store import FeatureStore  # legacy write surface
from kailash_ml.types import FeatureSchema, FeatureField
import polars as pl

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

fs = FeatureStore(conn, table_prefix="kml_feat_")
await fs.initialize()
```

## Schema-Driven Registration

Every feature set is defined by a `FeatureSchema` before storage. The schema
enforces types, names, the entity key, and the point-in-time timestamp column.
There is no `target` on the schema — the training target is an ordinary feature
column you name at train time (`ModelSpec` / `km.train(df, target=...)`).

```python
schema = FeatureSchema(
    name="user_churn",
    features=[
        FeatureField(name="age", dtype="float"),
        FeatureField(name="tenure_months", dtype="float"),
        FeatureField(name="monthly_spend", dtype="float"),
        FeatureField(name="support_tickets", dtype="int"),
        FeatureField(name="plan_type", dtype="text"),
        FeatureField(name="churned", dtype="int"),  # training target column
    ],
    entity_id_column="user_id",       # unique entity identifier
    timestamp_column="event_time",    # enables point-in-time queries
)

# Register the schema (creates the backing table), then materialise rows.
await fs.register_features(schema)

# `compute` validates + projects a DataFrame to the schema; `store` persists it.
df = pl.read_csv("features.csv")
projected = fs.compute(df, schema)
rows_stored = await fs.store(projected, schema)
```

## Polars-Only Rule

All feature engineering happens in polars. No pandas or numpy in pipeline code.
Conversion happens only at sklearn boundaries via `interop.py`.

```python
# DO: Polars expressions for feature engineering
df = df.with_columns([
    (pl.col("monthly_spend") / pl.col("tenure_months")).alias("spend_per_month"),
    pl.col("support_tickets").rolling_mean(window_size=3).alias("tickets_rolling_3"),
    pl.when(pl.col("plan_type") == "premium").then(1).otherwise(0).alias("is_premium"),
])

# DO NOT: Convert to pandas for feature engineering
df_pd = df.to_pandas()               # WRONG
df_pd["spend_per_month"] = df_pd["monthly_spend"] / df_pd["tenure_months"]  # WRONG
```

## Composing Multiple Feature Sets

The legacy store materialises and retrieves one schema at a time — there is no
multi-set join method. Register and store each feature set, retrieve each through
`get_features`, then join in polars on the entity key.

```python
# Register + store each feature set separately
for schema, frame in (
    (demographics_schema, demo_df),
    (behavior_schema, behavior_df),
    (financials_schema, financial_df),
):
    await fs.register_features(schema)
    await fs.store(fs.compute(frame, schema), schema)

# Retrieve each, then join in polars on the entity key
entity_ids = ["user_001", "user_002"]
demo = await fs.get_features(entity_ids, [f.name for f in demographics_schema.features], schema=demographics_schema)
beh = await fs.get_features(entity_ids, [f.name for f in behavior_schema.features], schema=behavior_schema)
training_df = demo.join(beh, on="user_id", how="inner")
```

## Point-in-Time Queries

Point-in-time queries prevent future data leakage in training sets. The `as_of`
parameter on `get_features` returns the latest feature values that existed at or
before the given timestamp; `get_training_set` returns a time-windowed set for one
schema.

```python
from datetime import datetime, timezone

# Features as they existed at a specific point in time (no future leakage)
historical_df = await fs.get_features(
    ["user_001", "user_002"],
    ["age", "tenure_months", "monthly_spend"],
    schema=schema,
    as_of=datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc),
)

# Latest features (no time constraint)
current_df = await fs.get_features(
    ["user_001", "user_002"],
    ["age", "tenure_months", "monthly_spend"],
    schema=schema,
)

# Point-in-time-correct training window for one schema
training_df = await fs.get_training_set(
    schema,
    start=datetime(2025, 1, 1, tzinfo=timezone.utc),
    end=datetime(2025, 6, 1, tzinfo=timezone.utc),
)
```

## Feature Versioning

Feature sets are versioned by the schema `version`. Bump `version` when feature
semantics change; previous versions remain queryable for reproducibility.

```python
# Schema v1
schema_v1 = FeatureSchema(name="user_churn", features=[...], entity_id_column="user_id", version=1)
await fs.register_features(schema_v1)
await fs.store(fs.compute(df_v1, schema_v1), schema_v1)

# Schema v2 (added a feature — bump version)
schema_v2 = FeatureSchema(name="user_churn", features=[..., new_field], entity_id_column="user_id", version=2)
await fs.register_features(schema_v2)
await fs.store(fs.compute(df_v2, schema_v2), schema_v2)

# Inspect registered schemas
registered = await fs.list_schemas()
```

## Sklearn Interop (Boundary Only)

Conversion to numpy/sklearn formats happens exclusively through `interop.py` at the
framework boundary — never in pipeline code.

```python
from kailash_ml.interop import to_sklearn_input, from_sklearn_output

# Convert at the sklearn boundary
X, y, column_info = to_sklearn_input(
    training_df,
    feature_columns=["age", "tenure_months", "monthly_spend"],
    target_column="churned",
)
# X is a numpy ndarray, y is a numpy array (or None when target_column is omitted)

# Convert predictions back to a polars DataFrame
result_df = from_sklearn_output(predictions, column_info)
```

## SQL Safety

All SQL in `_feature_sql.py` uses identifier validation from `kailash.db.dialect`:

- `_validate_identifier()` on all interpolated table/column names
- `_validate_sql_type()` allowlist: INTEGER, REAL, TEXT, BLOB, NUMERIC only
- Table prefix validated in `FeatureStore.__init__` via regex

```python
# _feature_sql.py handles all queries
# Engine files NEVER contain raw SQL
# This pattern ensures SQL injection is impossible at the engine layer
```

## Critical Rules

- All data in polars — no pandas/numpy in pipeline code
- Conversion only at sklearn boundary via `interop.py`
- Legacy `FeatureStore` uses ConnectionManager, not Express
- Top-level `from kailash_ml import FeatureStore` is the canonical _read_ surface
- Zero raw SQL outside `_feature_sql.py`
- Point-in-time queries (`as_of` / `get_training_set`) prevent future leakage
- Schema defines everything — no ad-hoc column creation; no `target` on the schema
