# DataFlow Integration Points

## Purpose

Research how kailash-ml engines will use DataFlow for persistent storage of models, features, drift reports, and audit logs.

## DataFlow Architecture Summary

DataFlow (`packages/kailash-dataflow/`) provides:

1. **`@db.model` decorator**: Define Python classes that auto-generate CRUD nodes
2. **Express API** (`db.express`): 23x faster than workflows for single-record CRUD operations
3. **WorkflowBuilder**: Multi-step operations with node wiring
4. **Migration system**: Auto-migrates schema changes (table creation, column additions)
5. **Bulk operations**: Batch insert/update for large datasets
6. **Multi-tenant**: Tenant isolation for SaaS deployments

**Key class**: `DataFlow` in `packages/kailash-dataflow/src/dataflow/core/engine.py` -- main entry point, manages connection pools, runtimes, and express APIs.

## Integration Point 1: FeatureStore Storage

### How FeatureStore will use DataFlow

FeatureStore needs to persist:

- **Feature metadata**: Schema definitions, versions, computation status
- **Feature values**: Per-entity feature vectors with timestamps (point-in-time retrieval)

### Recommended approach

```python
# FeatureStore creates DataFlow models dynamically at register_features() time
class FeatureStore:
    def __init__(self, db: DataFlow):
        self._db = db

    async def register_features(self, schema: FeatureSchema):
        # Create a DataFlow table for this feature group
        # Use Express API for metadata CRUD
        await self._db.express.upsert(
            "_MLFeatureMetadata",
            {"name": schema.name, "version": schema.version, ...},
            conflict_keys=["name"]
        )
```

### Concern: Dynamic table creation

FeatureStore creates tables at runtime (`register_features()` creates a table per feature group). DataFlow supports this via its migration system, but:

- **Idempotency**: `register_features()` must be idempotent (call it 10 times, same result). DataFlow's `auto_migrate=True` handles this.
- **Table naming**: Feature group names become table names. Must validate with `_validate_identifier()` (see `rules/infrastructure-sql.md`).
- **Column types**: polars dtypes must map to SQL types. Mapping: `pl.Int64` -> `INTEGER`, `pl.Float64` -> `REAL/DOUBLE`, `pl.Utf8` -> `TEXT`, `pl.Boolean` -> `BOOLEAN`, `pl.Datetime` -> `TIMESTAMP`.

### Express API for feature retrieval

```python
# Point-in-time retrieval via Express
features = await self._db.express.list(
    f"_MLFeatures_{schema.name}",
    filter={"entity_id": entity_id},
    order_by=[("created_at", "desc")],
    limit=1  # Latest before timestamp
)
```

**Limitation**: Express API does not support complex WHERE clauses like `created_at <= ?`. Point-in-time queries may need WorkflowBuilder with raw SQL nodes, or a custom Express extension.

**Recommendation**: Implement point-in-time retrieval as a SQL query via `ConnectionManager.execute()` rather than Express, since Express is optimized for simple CRUD patterns. The FeatureStore should accept the DataFlow instance and extract its connection manager for complex queries.

## Integration Point 2: ModelRegistry Storage

### DataFlow models needed

```python
# These will be auto-created DataFlow models
MLModel:          id, name, description, owner, created_at
MLModelVersion:   id, model_id, version, stage, metrics_json, feature_schema_ref,
                  artifact_path, onnx_path, onnx_status, created_at
MLModelTransition: id, version_id, from_stage, to_stage, timestamp, reason
```

### Stage transition as Express operations

```python
# Promote model version
await db.express.update("MLModelVersion", version_id, {"stage": "production"})
await db.express.create("MLModelTransition", {
    "version_id": version_id,
    "from_stage": "staging",
    "to_stage": "production",
    "timestamp": datetime.utcnow().isoformat(),
    "reason": reason,
})
```

Express API is well-suited for ModelRegistry CRUD: register, list versions, promote, archive. These are all single-record or simple-filter operations.

### Artifact storage

Model artifacts (serialized model files, ONNX exports) are stored on the filesystem, NOT in DataFlow. DataFlow stores metadata only (paths, sizes, hashes). The `ArtifactStore` protocol handles file I/O.

## Integration Point 3: DriftMonitor History

DriftMonitor stores:

- **Reference statistics**: Per-feature baseline distributions (DataFlow model)
- **Drift reports**: PSI/KS scores per check (DataFlow model)

```python
MLDriftReference:  id, model_name, feature_name, reference_stats_json, created_at
MLDriftReport:     id, model_name, check_time, psi_scores_json, ks_scores_json,
                   alert_triggered, created_at
```

Express API is sufficient -- these are simple CRUD operations with time-based filtering.

## Integration Point 4: Agent Audit Log

```python
MLAgentAuditLog:   id, engine, agent_name, action, input_summary, output_summary,
                   confidence, cost_usd, approved, created_at
```

Write-heavy, read for audit. Express `create()` and `list()` with filters. No complex queries needed.

## Integration Point 5: Bulk Data Operations

### Challenge: Large feature datasets

FeatureStore may write 100K+ rows when materializing features. DataFlow's Express API processes one record at a time -- `bulk_create()` exists but may be slow for very large datasets.

### Recommendation

1. For < 10K rows: Use `db.express.bulk_create()` (exists, documented)
2. For > 10K rows: Use DataFlow's `ConnectionManager` directly with batch SQL inserts (Arrow-native path if available, else chunked `to_dicts()`)
3. The architecture already specifies this: "Arrow-native path for >10K rows"

### Connection pool considerations

kailash-ml engines must follow `rules/dataflow-pool.md`:

- Accept DataFlow instance (shared pool), never create their own
- No orphan runtimes (accept `runtime` parameter)
- All engines must implement `close()` that releases resources

```python
class FeatureStore:
    def __init__(self, db: DataFlow):
        self._db = db  # Shared -- NOT a new DataFlow instance
        # Use db's existing connection pool
```

## Summary of Integration Patterns

| kailash-ml Engine    | DataFlow Usage                       | API                                                  |
| -------------------- | ------------------------------------ | ---------------------------------------------------- |
| FeatureStore         | Feature metadata + values            | Express (CRUD) + ConnectionManager (complex queries) |
| ModelRegistry        | Model/version/transition metadata    | Express (all CRUD)                                   |
| DriftMonitor         | Reference stats + drift reports      | Express (all CRUD)                                   |
| AutoMLEngine         | Agent audit log                      | Express (write + filter read)                        |
| DataExplorer         | None (stateless)                     | N/A                                                  |
| HyperparameterSearch | None (delegates to TrainingPipeline) | N/A                                                  |
| FeatureEngineer      | Via FeatureStore                     | Indirect                                             |
| InferenceServer      | Via ModelRegistry                    | Indirect                                             |
| TrainingPipeline     | Via FeatureStore + ModelRegistry     | Indirect                                             |

## Risks

1. **Express API limitations for complex queries**: Point-in-time feature retrieval needs `WHERE created_at <= ? ORDER BY created_at DESC LIMIT 1` -- Express may not support this directly. Fallback: raw SQL via ConnectionManager.
2. **Bulk write performance**: 100K+ row feature materialization through Express will be slow. Arrow-native batch insert path is essential.
3. **DataFlow model naming**: All ML-specific tables should use `_ML` prefix to avoid collision with user-defined models.
