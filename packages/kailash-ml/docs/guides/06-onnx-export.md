# ONNX Export

Export trained models to ONNX for cross-platform inference.

## Supported Frameworks

| Framework    | Export    | Notes                 |
| ------------ | --------- | --------------------- |
| scikit-learn | Automatic | Via skl2onnx          |
| LightGBM     | Automatic | Via onnxmltools       |
| XGBoost      | Automatic | Via onnxmltools       |
| PyTorch      | Manual    | Via torch.onnx.export |

## Automatic Export

InferenceServer prefers ONNX when an `.onnx` artifact is registered alongside the model. Set `runtime="onnx"` on `InferenceServerConfig` (the default) to require ONNX; pass `runtime="pickle"` to opt into native deserialization.

```python
from kailash_ml.serving.server import InferenceServer, InferenceServerConfig

config = InferenceServerConfig(
    tenant_id="acme",
    model_name="my-model",
    model_version=3,
    channels=("rest",),
    runtime="onnx",
)
server = InferenceServer(config, registry=registry)
await server.start()
result = await server.predict(features)
await server.stop()
```

## Manual Export

```python
from kailash_ml.bridge.onnx_bridge import OnnxBridge

bridge = OnnxBridge()

# Export sklearn model
onnx_path = bridge.export(
    model=trained_sklearn_model,
    input_shape={"float_input": [None, 4]},  # batch_size x features
    output_path="model.onnx",
)

# Verify export
is_valid = bridge.verify(onnx_path, sample_input)
print(f"ONNX valid: {is_valid}")
```

## Rust Serving Bridge

Exported ONNX models can be served by kailash-rs for production deployments:

```bash
# Export from Python
python -c "
from kailash_ml.bridge.onnx_bridge import OnnxBridge
bridge = OnnxBridge()
bridge.export(model, input_shape={'float_input': [None, 4]}, output_path='model.onnx')
"

# Serve from Rust (kailash-rs)
# See kailash-rs documentation for ONNX inference server setup
```

## Common Errors

**`ONNXExportError: unsupported operator`** -- Some sklearn transformers lack ONNX converters. Simplify preprocessing or use native inference.

**`ONNXVerificationError: output mismatch`** -- Numeric precision differences between ONNX and native. Tolerance is 1e-5 by default.
