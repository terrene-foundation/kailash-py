# Feature Pipelines

Build polars-native feature pipelines with FeatureStore integration.

## FeatureStore Basics

```python
from kailash_ml.engines.feature_store import FeatureStore
import polars as pl

store = FeatureStore()

# Register a feature set
await store.register_features(
    name="user_features",
    schema={"age": pl.Int64, "income": pl.Float64, "tenure_days": pl.Int64},
)

# Store features
await store.put("user_features", pl.DataFrame({
    "user_id": ["u1", "u2", "u3"],
    "age": [25, 34, 45],
    "income": [50000.0, 75000.0, 120000.0],
    "tenure_days": [30, 365, 1200],
}))

# Retrieve for training
features = await store.get("user_features")
```

## Polars Pipelines

kailash-ml is polars-native. All engines accept `pl.DataFrame` directly.

```python
import polars as pl

# Feature engineering with polars expressions
df = df.with_columns([
    (pl.col("income") / pl.col("age")).alias("income_per_year_of_age"),
    pl.col("tenure_days").cast(pl.Float64).alias("tenure_years") / 365.0,
    pl.when(pl.col("income") > 100000).then(1).otherwise(0).alias("high_income"),
])
```

## Schema Validation

FeatureStore validates schemas on write:

```python
# This raises SchemaError -- "unknown_col" not in registered schema
await store.put("user_features", pl.DataFrame({
    "user_id": ["u1"],
    "unknown_col": [42],
}))
```

## Common Errors

**`SchemaError: column type mismatch`** -- Polars is strict about types. Cast columns explicitly: `pl.col("age").cast(pl.Int64)`.

**`FeatureNotFoundError`** -- Register features before putting data. Call `store.register_features()` first.
