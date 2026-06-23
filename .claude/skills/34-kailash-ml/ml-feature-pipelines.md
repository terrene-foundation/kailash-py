# ML Feature Pipelines

FeatureStore provides polars-native feature ingestion, point-in-time queries, and schema-driven composition. All SQL is isolated in `_feature_sql.py` — zero raw SQL in engine files.

## FeatureStore Setup

FeatureStore uses ConnectionManager (not Express) because point-in-time queries require window functions that Express cannot express.

```python
from kailash.db.connection import ConnectionManager
from kailash_ml import FeatureStore
from kailash_ml.types import FeatureSchema, FeatureField
import polars as pl

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

fs = FeatureStore(conn, table_prefix="kml_feat_")
await fs.initialize()
```

## Schema-Driven Ingestion

Every feature set is defined by a `FeatureSchema` before ingestion. The schema enforces types, names, and target designation.

```python
schema = FeatureSchema(
    name="user_churn",
    features=[
        FeatureField(name="age", dtype="float"),
        FeatureField(name="tenure_months", dtype="float"),
        FeatureField(name="monthly_spend", dtype="float"),
        FeatureField(name="support_tickets", dtype="int"),
        FeatureField(name="plan_type", dtype="text"),
    ],
    target=FeatureField(name="churned", dtype="int"),
    entity_key="user_id",        # Unique entity identifier
    timestamp_field="event_time", # For point-in-time queries
)

# Ingest from polars DataFrame
df = pl.read_csv("features.csv")
await fs.ingest("user_features", schema, df)
```

## Polars-Only Rule

All feature engineering happens in polars. No pandas or numpy in pipeline code. Conversion happens only at sklearn boundaries via `interop.py`.

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

## Feature Composition

Compose multiple feature sets into a single training DataFrame using entity keys and point-in-time joins.

```python
# Define multiple feature schemas
user_schema = FeatureSchema(name="user_demographics", ...)
behavior_schema = FeatureSchema(name="user_behavior", ...)
financial_schema = FeatureSchema(name="user_financials", ...)

# Ingest separately
await fs.ingest("demographics", user_schema, demo_df)
await fs.ingest("behavior", behavior_schema, behavior_df)
await fs.ingest("financials", financial_schema, financial_df)

# Compose into training set with point-in-time correctness
training_df = await fs.compose(
    feature_sets=["demographics", "behavior", "financials"],
    entity_key="user_id",
    as_of="2025-01-01T00:00:00",  # No future leakage
)
```

## Point-in-Time Queries

Point-in-time queries prevent future data leakage in training sets. The `as_of` parameter ensures only data available before the specified timestamp is included.

```python
# Get features as they existed at a specific point in time
historical_df = await fs.get_features(
    feature_set="user_features",
    entity_ids=["user_001", "user_002"],
    as_of="2025-06-15T12:00:00",
)

# Latest features (no time constraint)
current_df = await fs.get_features(
    feature_set="user_features",
    entity_ids=["user_001", "user_002"],
)
```

## Feature Versioning

Feature sets are versioned automatically on schema changes. Previous versions remain queryable for reproducibility.

```python
# Schema v1
schema_v1 = FeatureSchema(name="user_churn", features=[...], version=1)
await fs.ingest("user_features", schema_v1, df_v1)

# Schema v2 (added a feature)
schema_v2 = FeatureSchema(name="user_churn", features=[..., new_field], version=2)
await fs.ingest("user_features", schema_v2, df_v2)

# Query specific version
df = await fs.get_features("user_features", version=1)
```

## Sklearn Interop (Boundary Only)

Conversion to numpy/sklearn formats happens exclusively through `interop.py` at the framework boundary — never in pipeline code.

```python
from kailash_ml.interop import to_sklearn_arrays

# Convert at the sklearn boundary
X, y = to_sklearn_arrays(training_df, schema)
# X is numpy ndarray, y is numpy array
# Use with sklearn estimators

# Convert back after prediction
from kailash_ml.interop import from_numpy_predictions
result_df = from_numpy_predictions(predictions, entity_ids, schema)
# result_df is polars DataFrame
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
- FeatureStore uses ConnectionManager, not Express
- Zero raw SQL outside `_feature_sql.py`
- Point-in-time queries prevent future leakage
- Schema defines everything — no ad-hoc column creation
