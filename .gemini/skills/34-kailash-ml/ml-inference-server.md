# ML Inference Server

`InferenceServer` serves a single registered model over one or more channels, with
ONNX or pickle runtimes. A server instance is bound to ONE model — construct it from
the registry via `InferenceServer.from_registry(...)`, then `predict(features)`.

## Basic Setup

```python
from kailash_ml import InferenceServer
from kailash_ml.engines.model_registry import ModelRegistry, LocalFileArtifactStore
from kailash.db.connection import ConnectionManager

conn = ConnectionManager("sqlite:///ml.db")
await conn.initialize()
registry = ModelRegistry(conn, LocalFileArtifactStore("./artifacts"))

# One server per model, loaded from the registry. ONNX runtime by default.
server = InferenceServer.from_registry("churn_predictor", registry=registry)
```

`from_registry` accepts `alias=` / `version=` (pin a specific version; default is the
latest production version), `tenant_id=`, `channels=` (default `("rest",)`),
`runtime=` (`"onnx"` | `"pickle"`), `batch_size=`, and `server_id=`.

## Prediction

`predict(features)` takes a single feature mapping and returns a result mapping. The
server is already bound to its model — there is no `model_name` argument.

```python
result = await server.predict({"age": 35, "tenure_months": 24, "monthly_spend": 89.99})
# result is a Mapping — e.g. result["prediction"], result["probability"]

# Multi-tenant models require the tenant on every call
result = await server.predict(features, tenant_id="acme-corp")
```

## Runtime Selection (ONNX vs pickle)

```python
# ONNX runtime (default) — cross-language artifact, hardware acceleration
server = InferenceServer.from_registry("churn_predictor", registry=registry, runtime="onnx")

# pickle runtime — native sklearn/lightgbm object
server = InferenceServer.from_registry("churn_predictor", registry=registry, runtime="pickle")
```

ONNX is the default because it is the format the Rust SDK and any ONNX Runtime
environment can load — train in Python, serve anywhere.

## Version Pinning

```python
# Pin a specific registry version (default serves the latest production version)
server = InferenceServer.from_registry("churn_predictor", registry=registry, version=3)

# Pin via alias
server = InferenceServer.from_registry("churn_predictor", registry=registry, alias="champion")
```

## Serving Multiple Models

`from_registry_many` builds one `InferenceServer` per name, sharing the registry +
config kwargs.

```python
servers = InferenceServer.from_registry_many(
    ["churn_predictor", "revenue_forecast"],
    registry=registry,
    runtime="onnx",
)
churn_result = await servers["churn_predictor"].predict(features)
```

## Channels, Lifecycle, and Health

The server exposes its model over the configured `channels` (e.g. `("rest",)`).
`start()` returns a `ServeHandle`; `stop()` tears it down. `health()` and the
`status` / `model_signature` / `bindings` attributes report serving state.

```python
handle = await server.start()      # begin serving on the configured channels
info = await server.health()       # serving health (Mapping)
sig = server.model_signature       # input/output schema of the served model
await server.stop()
```

## Batch Throughput

Batch size is a serving-config concern set at construction — there is no separate
`predict_batch` method; the runtime batches internally up to `batch_size`.

```python
server = InferenceServer.from_registry(
    "churn_predictor", registry=registry, runtime="onnx", batch_size=1000,
)
```

## Drift Monitoring

Drift detection is a separate engine (`DriftMonitor`), not a serving-layer kwarg.
Collect production features, then check them on a schedule — see
`ml-drift-monitoring.md` for `DriftMonitor.schedule_monitoring` +
`DriftSpec(on_drift_detected=...)`. The serving layer and the drift engine compose;
the server does not own drift configuration.

## Critical Rules

- One `InferenceServer` instance per model — built via `from_registry(...)`
- `predict(features)` takes only the feature mapping (+ `tenant_id=` for multi-tenant)
- ONNX is the default runtime (cross-language); `pickle` serves the native object
- Default serves the latest `production` version; pin via `version=` / `alias=`
- Drift monitoring is a separate `DriftMonitor` engine, not a serving kwarg
