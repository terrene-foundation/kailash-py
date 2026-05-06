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

## Quick Start (canonical 1.0+ surface)

```python
from datetime import datetime, timezone
from dataflow import DataFlow
from kailash_ml.features import FeatureStore, FeatureSchema, FeatureField

# 1. Live DataFlow instance owns the connection pool + auto-migration.
df = DataFlow("sqlite:///ml.db", auto_migrate=True)

# 2. Define the feature schema (polars-native dtypes, tuple of fields).
schema = FeatureSchema(
    name="user_features",
    version=1,
    fields=(
        FeatureField(name="login_count", dtype="int64"),
        FeatureField(name="avg_session_min", dtype="float64"),
    ),
    entity_id_column="user_id",
    timestamp_column="event_time",
)

# 3. Construct the FeatureStore as a tenant-scoped DataFlow bridge.
fs = FeatureStore(df, default_tenant_id="acme")

# 4. Point-in-time query — routes through dataflow.ml_feature_source(...)
result = await fs.get_features(
    schema,
    timestamp=datetime(2026, 3, 30, tzinfo=timezone.utc),
    tenant_id="acme",
    entity_ids=["u1", "u2"],
)
# Returns polars DataFrame
```

The canonical FeatureStore is a thin DataFlow bridge — the parent `DataFlow`
owns DDL, connection pooling, and the migration framework; the FeatureStore
delegates every feature read through `dataflow.ml_feature_source(...)`. See
`specs/ml-feature-store.md` § 1.1 for the contract and `specs/dataflow-ml-integration.md`
§ 1.1 for the polars-LazyFrame binding.

### Legacy ConnectionManager path (1.x bridge release)

```python
# DEPRECATED at 1.7+ — emits DeprecationWarning, removed in 2.0.0
from kailash.db.connection import ConnectionManager
from kailash_ml import FeatureStore  # resolves to legacy engines.feature_store

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()
store = FeatureStore(conn, table_prefix="kml_feat_")
```

This top-level import is retained for 1.x backwards compatibility; first
access emits a `DeprecationWarning` pointing at the canonical surface above.
The legacy resolution path will be removed in kailash-ml 2.0.0. See
`packages/kailash-ml/MIGRATION.md` for the migration recipe.

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
