# Inference Server

Serve predictions over REST, MCP, and gRPC channels with model-signature
validation, ONNX-default runtime, and tenant-scoped lifecycle.

The legacy `kailash_ml.engines.inference_server.InferenceServer` was deleted
in W6-004 (F-E1-28); the canonical surface lives at
`kailash_ml.serving.server.InferenceServer` and follows the W25 lifecycle
contract documented in `specs/ml-serving.md`.

## Basic Setup

`InferenceServer.from_registry()` resolves a `models://name@alias` URI
through the registry's alias layer and returns a ready-to-start server.

```python
from kailash_ml.serving.server import InferenceServer

server = await InferenceServer.from_registry(
    "models://churn-predictor@production",
    registry=registry,
    tenant_id="acme",
    channels=("rest", "mcp"),
)
await server.start()

result = await server.predict({
    "tenure_months": 24,
    "monthly_charges": 79.99,
    "total_charges": 1919.76,
})
print(result["prediction"], result["latency_ms"])

await server.stop()
```

## Construction Envelope

When you need explicit control of `model_version`, `runtime`, or
`batch_size`, construct the `InferenceServerConfig` envelope directly:

```python
from kailash_ml.serving.server import InferenceServer, InferenceServerConfig

config = InferenceServerConfig(
    tenant_id="acme",
    model_name="churn-predictor",
    model_version=7,
    channels=("rest",),
    runtime="onnx",       # "onnx" (default) or "pickle" (explicit opt-in)
    batch_size=128,       # None = no batch mode
)
server = InferenceServer(config, registry=registry)
await server.start()
```

## Batch Predictions

Pass a `records` payload to score multiple rows in one call:

```python
result = await server.predict({
    "records": [
        {"tenure_months": 24, "monthly_charges": 79.99},
        {"tenure_months": 6, "monthly_charges": 29.99},
        {"tenure_months": 48, "monthly_charges": 99.99},
    ]
})
for row in result["predictions"]:
    print(row)
```

## Common Errors

**`InvalidInputSchemaError`** — the features payload does not match the
model's `ModelSignature` (W25 invariant 1). Compare the request keys
against `server.model_signature.input_schema.features`.

**`InferenceServerError`** — the server is not in the `ready` state, or a
cross-tenant request was attempted. `start()` MUST be awaited before
`predict()`; cross-tenant calls are rejected by design.

**`ModelNotFoundError`** — the URI does not resolve to a registered model.
Confirm the alias exists via `registry.list_aliases(name)` before
calling `from_registry()`.
