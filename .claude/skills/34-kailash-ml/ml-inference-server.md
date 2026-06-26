# ML Inference Server

InferenceServer provides model serving via Nexus HTTP exposure, ONNX runtime acceleration, response caching, batch inference, and drift monitoring triggers.

## Basic Setup

```python
from kailash_ml import InferenceServer, ModelRegistry
from kailash_ml.engines import LocalFileArtifactStore
from kailash.db.connection import ConnectionManager

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()

registry = ModelRegistry(conn, artifact_store=LocalFileArtifactStore("./artifacts"))
await registry.initialize()

server = InferenceServer(model_registry=registry)
```

## Nexus HTTP Exposure

InferenceServer integrates with Nexus for zero-config HTTP deployment. No custom API code needed.

```python
from nexus import Nexus

app = Nexus()

# Register inference endpoint
server = InferenceServer(model_registry=registry)

@app.post("/api/predict")
async def predict(request: PredictRequest):
    result = await server.predict(
        model_name="churn_predictor",
        features=request.features,
    )
    return {
        "prediction": result.prediction,
        "probability": result.probability,
        "model_version": result.model_version,
    }

# Or use auto-registration (creates /predict/{model_name} for all production models)
server.register_with_nexus(app)
```

### Auto-Registration

```python
# Creates endpoints for all production-stage models automatically
server.register_with_nexus(app)

# Generates:
#   POST /predict/churn_predictor
#   POST /predict/revenue_forecast
#   POST /predict/{model_name}
#   GET  /models                    — list available models
#   GET  /models/{name}/info        — model metadata and metrics
```

## ONNX Serving

InferenceServer can serve ONNX models for cross-language compatibility and hardware acceleration.

```python
from kailash_ml import InferenceServer

server = InferenceServer(
    model_registry=registry,
    runtime="onnx",  # Use ONNX Runtime instead of native sklearn/lightgbm
)

# ONNX runtime provides:
# - 2-5x faster inference vs native sklearn
# - GPU acceleration (with kailash-ml[dl-gpu])
# - Cross-language serving (model trained in Python, served anywhere)

result = await server.predict(
    model_name="churn_predictor",
    features={"age": 35, "tenure_months": 24, "monthly_spend": 89.99},
)
```

### ONNX Model Loading

```python
# Load ONNX model from registry
server = InferenceServer(model_registry=registry, runtime="onnx")

# Load ONNX model from file path (standalone serving)
server = InferenceServer.from_onnx("./models/churn_predictor.onnx")

# With GPU acceleration
server = InferenceServer(
    model_registry=registry,
    runtime="onnx",
    providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
)
```

## Response Caching

Cache predictions for repeated inputs to reduce latency and compute cost.

```python
server = InferenceServer(
    model_registry=registry,
    cache_enabled=True,
    cache_ttl_seconds=300,       # Cache for 5 minutes
    cache_max_size=10_000,       # Max cached predictions
)

# First call: computes prediction (~50ms)
result1 = await server.predict(model_name="churn_predictor", features=features)

# Second call with same features: cache hit (~1ms)
result2 = await server.predict(model_name="churn_predictor", features=features)

# Cache invalidated automatically on model version change
```

## Batch Inference

Process multiple predictions in a single call for throughput optimization.

```python
import polars as pl

# Batch from polars DataFrame
batch_df = pl.read_csv("new_customers.csv")
results = await server.predict_batch(
    model_name="churn_predictor",
    data=batch_df,
    batch_size=1000,  # Process 1000 rows at a time
)
# results is a polars DataFrame with predictions appended

# Batch from list of feature dicts
feature_list = [
    {"age": 35, "tenure_months": 24, "monthly_spend": 89.99},
    {"age": 42, "tenure_months": 6, "monthly_spend": 149.99},
    {"age": 28, "tenure_months": 36, "monthly_spend": 59.99},
]
results = await server.predict_batch(
    model_name="churn_predictor",
    data=feature_list,
)
```

### Batch Performance

| Approach           | 10K predictions | Notes                     |
| ------------------ | --------------- | ------------------------- |
| Single predictions | ~50s            | 5ms each, serial          |
| Batch (sklearn)    | ~2s             | Vectorized numpy          |
| Batch (ONNX)       | ~0.5s           | ONNX Runtime optimization |
| Batch (ONNX + GPU) | ~0.1s           | GPU parallelism           |

## Drift Monitoring Triggers

InferenceServer can trigger DriftMonitor checks on incoming prediction data.

```python
from kailash_ml import InferenceServer, DriftMonitor

monitor = DriftMonitor(conn)
await monitor.initialize()

server = InferenceServer(
    model_registry=registry,
    drift_monitor=monitor,
    drift_check_interval=1000,   # Check drift every 1000 predictions
    drift_alert_threshold=0.1,   # Alert if PSI > 0.1
)

# Predictions are collected and checked periodically
result = await server.predict(model_name="churn_predictor", features=features)

# Access drift status
drift_status = await server.get_drift_status("churn_predictor")
# drift_status.is_drifting, drift_status.last_check, drift_status.psi_score
```

### Automatic Retraining Trigger

```python
server = InferenceServer(
    model_registry=registry,
    drift_monitor=monitor,
    on_drift="alert",          # Options: "alert", "shadow", "retrain"
    # "alert"   — log warning and notify
    # "shadow"  — switch to shadow model if available
    # "retrain" — trigger TrainingPipeline retraining
)
```

## Model Hot-Swap

Switch between model versions without downtime.

```python
# Serve latest production model (default)
server = InferenceServer(model_registry=registry)

# Model promoted to production in registry — server picks it up automatically
await registry.transition(new_model_id, stage="production")

# Or explicit version pinning
server = InferenceServer(
    model_registry=registry,
    model_version_pin={"churn_predictor": 3},  # Pin to version 3
)
```

## Health and Metrics

```python
# Health check endpoint (auto-registered with Nexus)
# GET /health — returns model load status, cache stats, drift status

# Metrics
metrics = await server.get_metrics("churn_predictor")
# metrics.total_predictions
# metrics.avg_latency_ms
# metrics.cache_hit_rate
# metrics.p99_latency_ms
# metrics.errors_last_hour
```

## Critical Rules

- InferenceServer serves models from ModelRegistry — only `production` stage models are served by default
- ONNX runtime provides 2-5x speedup and cross-language compatibility
- Batch inference always preferred over serial for >10 predictions
- Drift monitoring integrated at the serving layer, not as a separate pipeline
- Cache invalidated automatically on model version change
- All prediction data stays in polars — conversion to numpy happens internally
