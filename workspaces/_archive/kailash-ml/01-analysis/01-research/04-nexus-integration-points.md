# Nexus Integration Points

## Purpose

Research how InferenceServer and TrainingPipeline will expose endpoints via Nexus for model serving and training triggers.

## Nexus Architecture Summary

Nexus (`packages/kailash-nexus/`) provides zero-config multi-channel deployment:

1. **`Nexus()` class** (`nexus.core`): Main entry point. Creates API (FastAPI), CLI, and MCP channels simultaneously.
2. **`register_handler()`**: Register an async/sync function as a multi-channel endpoint. Builds a `HandlerNode` workflow from the function.
3. **`@app.handler()` decorator**: Syntactic sugar for `register_handler()`.
4. **`NexusEngine`** (`nexus.engine`): Builder pattern for more complex setups.
5. **Plugins**: `AuthPlugin`, `MonitoringPlugin`, `RateLimitPlugin` for cross-cutting concerns.
6. **Validation**: Input validation, workflow sandboxing, name validation.

## Integration Point 1: InferenceServer Endpoints

### Endpoint registration

```python
class InferenceServer:
    def register_endpoints(self, nexus: Nexus) -> None:
        """Register prediction and health endpoints."""
        nexus.register_handler(
            "predict",
            self._handle_predict,
            description="Serve model predictions",
            tags=["ml", "inference"],
        )
        nexus.register_handler(
            "model_health",
            self._handle_health,
            description="Model health check",
            tags=["ml", "health"],
        )

    async def _handle_predict(self, model_name: str, features: dict) -> dict:
        result = await self.predict(model_name, features)
        return result.to_dict()

    async def _handle_health(self, model_name: str) -> dict:
        return await self._get_health_status(model_name)
```

### What Nexus provides automatically

When `register_handler()` is called:

- **API**: `POST /api/predict` and `POST /api/model_health` (FastAPI routes)
- **CLI**: `nexus run predict --model_name "my_model" --features '{"a": 1}'`
- **MCP**: Tools registered for AI agent consumption

### Input/output handling

Nexus handlers receive kwargs (not raw HTTP requests). Return values are serialized to JSON. For kailash-ml:

- Input: `model_name: str` + `features: dict` (polars conversion happens inside InferenceServer, not in the handler)
- Output: `dict` (predictions, metadata, inference mode)

### Batch prediction endpoint

```python
# Batch prediction needs special handling -- pl.DataFrame cannot be passed as JSON
nexus.register_handler(
    "predict_batch",
    self._handle_predict_batch,
    description="Batch prediction from JSON array",
    tags=["ml", "inference"],
)

async def _handle_predict_batch(self, model_name: str, records: list[dict]) -> list[dict]:
    df = pl.DataFrame(records)  # Convert JSON array to polars
    result_df = await self.predict_batch(model_name, df)
    return result_df.to_dicts()  # Convert back to JSON array
```

**Note**: For very large batches (>10K records), JSON serialization overhead is significant. v1 accepts this limitation. v2 could add Arrow IPC or Parquet endpoints.

## Integration Point 2: TrainingPipeline Endpoints

```python
class TrainingPipeline:
    def register_endpoints(self, nexus: Nexus) -> None:
        nexus.register_handler(
            "train",
            self._handle_train,
            description="Trigger model training",
            tags=["ml", "training"],
        )
        nexus.register_handler(
            "pipeline_status",
            self._handle_status,
            description="Check training pipeline status",
            tags=["ml", "training"],
        )
```

### Long-running training

Training can take minutes to hours. The Nexus handler should:

1. Accept the training request
2. Start training as a background task
3. Return a `training_id` immediately
4. The `pipeline_status` endpoint returns progress

```python
async def _handle_train(self, pipeline_name: str, data_ref: str, spec: dict) -> dict:
    training_id = str(uuid.uuid4())
    # Start training in background
    asyncio.create_task(self._run_training(training_id, data_ref, spec))
    return {"training_id": training_id, "status": "started"}
```

**Concern**: `asyncio.create_task()` without proper lifecycle management can cause issues (lost exceptions, orphaned tasks). Consider integrating with Nexus's BackgroundService pattern if it exists in v2.

## Integration Point 3: ModelRegistry Endpoints

```python
nexus.register_handler("list_models", self._handle_list_models, ...)
nexus.register_handler("promote_model", self._handle_promote, ...)
nexus.register_handler("model_info", self._handle_model_info, ...)
```

These are straightforward CRUD endpoints. Express API wrapping with Nexus exposure.

## Integration Point 4: DriftMonitor Endpoints

```python
nexus.register_handler("check_drift", self._handle_check_drift, ...)
nexus.register_handler("drift_history", self._handle_drift_history, ...)
```

## Nexus Health Checks

Per `rules/connection-pool.md`, health checks must not use the application pool. InferenceServer's health endpoint should check:

1. Model cache status (in-memory, no DB hit)
2. ONNX runtime availability (import check, no inference)
3. Model count in cache

NOT: actual prediction (uses pool, takes time).

## Plugin Integration

### Rate limiting for prediction endpoints

Prediction endpoints should be rate-limited to prevent resource exhaustion:

```python
from nexus.plugins import RateLimitPlugin

nexus = Nexus()
nexus.use(RateLimitPlugin(rate="100/minute"))
inference_server.register_endpoints(nexus)
```

### Authentication for training endpoints

Training endpoints (which modify state) should require authentication:

```python
nexus.use(AuthPlugin(required_for=["train", "promote_model"]))
```

## Summary

| Endpoint               | Method | kailash-ml Engine | Notes                      |
| ---------------------- | ------ | ----------------- | -------------------------- |
| `/api/predict`         | POST   | InferenceServer   | Single prediction          |
| `/api/predict_batch`   | POST   | InferenceServer   | Batch (JSON array)         |
| `/api/model_health`    | GET    | InferenceServer   | No pool usage              |
| `/api/train`           | POST   | TrainingPipeline  | Returns training_id, async |
| `/api/pipeline_status` | GET    | TrainingPipeline  | Poll for progress          |
| `/api/list_models`     | GET    | ModelRegistry     | CRUD                       |
| `/api/promote_model`   | POST   | ModelRegistry     | Stage transition           |
| `/api/check_drift`     | POST   | DriftMonitor      | On-demand drift check      |

## Risks

1. **JSON serialization for large DataFrames**: Batch prediction via JSON is O(n) serialization. Arrow IPC would be better but is not a v1 priority.
2. **Long-running training via asyncio**: Background tasks need lifecycle management. Lost exceptions from `create_task()` are a production concern.
3. **Nexus optional dependency**: `kailash-nexus` is a required dependency in the architecture. If a user only wants training (no serving), they still pull in FastAPI/Nexus. Consider making Nexus integration lazy (import only when `register_endpoints()` is called).
