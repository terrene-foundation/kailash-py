# Inference Server

Serve predictions via HTTP (Nexus) and MCP with automatic ONNX optimization.

## Basic Setup

```python
from kailash_ml.engines.inference_server import InferenceServer
from kailash_ml.engines.model_registry import ModelRegistry

registry = ModelRegistry()
server = InferenceServer(registry)

# Single prediction
result = await server.predict("churn-predictor", {
    "tenure_months": 24,
    "monthly_charges": 79.99,
    "total_charges": 1919.76,
})
print(f"Prediction: {result.prediction}, Time: {result.inference_time_ms}ms")
```

## Batch Predictions

```python
records = [
    {"tenure_months": 24, "monthly_charges": 79.99},
    {"tenure_months": 6, "monthly_charges": 29.99},
    {"tenure_months": 48, "monthly_charges": 99.99},
]
results = await server.predict_batch("churn-predictor", records)
for r in results:
    print(f"  {r.prediction} (confidence: {r.confidence})")
```

## Nexus HTTP Endpoints

```python
from kailash_nexus import Nexus

nexus = Nexus(api_port=8000)
server.register_endpoints(nexus)
nexus.start()
# POST http://localhost:8000/api/predict/churn-predictor
# POST http://localhost:8000/api/predict_batch/churn-predictor
# GET  http://localhost:8000/api/ml/health
```

## MCP Tools

```python
from mcp import FastMCP

mcp_server = FastMCP("ml-service")
server.register_mcp_tools(mcp_server, namespace="ml")
# Tools: ml.predict, ml.predict_batch, ml.model_info
```

## ONNX Optimization

InferenceServer automatically attempts ONNX export for sklearn and LightGBM models. When successful, predictions use the ONNX runtime for faster inference.

```python
result = await server.predict("iris-classifier", features)
print(f"Inference path: {result.inference_path}")  # "onnx" or "native"
```

## Common Errors

**`ModelNotFoundError`** -- The model name must match a registered model in the registry.

**`PredictionError: feature mismatch`** -- Ensure feature names match exactly what the model was trained on. Check `registry.load(name).feature_names`.

**`ONNXExportError`** -- ONNX export failed (unsupported model type). Predictions fall back to native inference automatically.
