---
name: dataflow-ml-integration
description: "How kailash-ml FeatureStore integrates with DataFlow's ConnectionManager for point-in-time feature queries"
---

# DataFlow + kailash-ml Integration

kailash-ml's `FeatureStore` uses DataFlow's `ConnectionManager` directly (not Express API) because point-in-time feature queries require window-function-based temporal SQL that Express cannot express.

## Architecture

```
FeatureStore (kailash-ml)
    |
    v
ConnectionManager (kailash core)  <-- caller owns lifecycle
    |
    v
_feature_sql.py  <-- ALL raw SQL in one auditable module
    |
    v
SQLite / PostgreSQL / MySQL
```

**Key design decisions:**

- FeatureStore accepts a `ConnectionManager` -- it does NOT create its own
- All raw SQL is encapsulated in `_feature_sql.py` (zero SQL in `feature_store.py`)
- Uses `?` canonical placeholders (ConnectionManager translates per dialect)
- Table names use `_validate_identifier()` for SQL injection prevention

## Quick Start

```python
from kailash.db.connection import ConnectionManager
from kailash_ml import FeatureStore
from kailash_ml.types import FeatureSchema, FeatureField

# 1. Create ConnectionManager (caller owns lifecycle)
conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

# 2. Initialize FeatureStore with shared connection
store = FeatureStore(conn, table_prefix="kml_feat_")

# 3. Register a feature group
schema = FeatureSchema(
    name="user_features",
    entity_key="user_id",
    features=[
        FeatureField(name="login_count", dtype="int"),
        FeatureField(name="avg_session_min", dtype="float"),
    ],
)
await store.register_group(schema)

# 4. Ingest features (polars DataFrame)
import polars as pl
df = pl.DataFrame({
    "user_id": ["u1", "u2"],
    "login_count": [42, 7],
    "avg_session_min": [12.5, 3.2],
})
await store.ingest(schema.name, df)

# 5. Point-in-time query
result = await store.get_features(
    schema.name,
    entity_ids=["u1", "u2"],
    as_of=datetime(2026, 3, 30, tzinfo=UTC),  # temporal correctness
)
# Returns polars DataFrame
```

## Why Not Express API?

| Operation               | Express                         | ConnectionManager     | Winner            |
| ----------------------- | ------------------------------- | --------------------- | ----------------- |
| Simple CRUD             | 23x faster                      | Standard              | Express           |
| Point-in-time queries   | Cannot express window functions | Full SQL control      | ConnectionManager |
| DDL (CREATE TABLE)      | Not supported                   | Full control          | ConnectionManager |
| Bulk insert (>10k rows) | Row-by-row                      | Batched with chunking | ConnectionManager |

FeatureStore needs temporal window functions (`ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)`) for point-in-time correctness. Express API is designed for simple CRUD -- it cannot express this pattern.

## Connection Sharing

FeatureStore, ModelRegistry, and other kailash-ml engines all accept a `ConnectionManager` parameter. Share one connection to avoid pool exhaustion.

```python
# DO: Share one ConnectionManager across ML engines
conn = ConnectionManager("postgresql://...")
await conn.initialize()

feature_store = FeatureStore(conn)
model_registry = ModelRegistry(conn)

# DO NOT: Create separate connections per engine
feature_conn = ConnectionManager("postgresql://...")   # Wastes pool
model_conn = ConnectionManager("postgresql://...")     # Wastes pool
```

**Why**: Per `rules/dataflow-pool.md` and `rules/infrastructure-sql.md` Rule 2 (no separate ConnectionManagers per store), each ConnectionManager creates its own pool. Multiple pools to the same database waste connections.

## Interop Module

kailash-ml uses polars as its native data format. The `interop` module provides 8 converters:

| Converter                  | Direction                     | Use Case                   |
| -------------------------- | ----------------------------- | -------------------------- |
| `to_sklearn_input()`       | polars -> numpy               | Training with sklearn      |
| `from_sklearn_output()`    | numpy -> polars               | Predictions back to polars |
| `to_lgb_dataset()`         | polars -> LightGBM Dataset    | LightGBM training          |
| `to_hf_dataset()`          | polars -> HuggingFace Dataset | Tokenization, NLP          |
| `polars_to_arrow()`        | polars -> Arrow               | Zero-copy Arrow interop    |
| `to_pandas()`              | polars -> pandas              | Legacy library compat      |
| `from_pandas()`            | pandas -> polars              | Ingest from pandas sources |
| `polars_to_dict_records()` | polars -> list[dict]          | JSON serialization         |

All converters handle categoricals, nulls, and dtype preservation.

## Cross-References

- `kailash_ml.engines.feature_store` -- FeatureStore implementation
- `kailash_ml.engines._feature_sql` -- All SQL in one module
- `kailash_ml.interop` -- Polars conversion module
- `rules/infrastructure-sql.md` -- SQL safety patterns (identifier validation, transactions)
- `rules/dataflow-pool.md` -- Connection pool rules (no separate ConnectionManagers)
