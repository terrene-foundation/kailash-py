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

InferenceServer attempts ONNX export automatically when a model is loaded:

```python
from kailash_ml.engines.inference_server import InferenceServer

server = InferenceServer(registry)
result = await server.predict("my-model", features)
print(result.inference_path)  # "onnx" if export succeeded
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
