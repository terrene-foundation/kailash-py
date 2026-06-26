# ML ONNX Export

Export models from PyTorch and sklearn to ONNX format for cross-language serving. Train in Python, export to ONNX, serve in Rust or any ONNX Runtime environment.

## OnnxBridge

`OnnxBridge` in `kailash_ml.bridge` handles conversion, verification, and metadata embedding for all supported model types.

```python
from kailash_ml.bridge import OnnxBridge

bridge = OnnxBridge()
```

## sklearn to ONNX (via skl2onnx)

```python
from sklearn.ensemble import RandomForestClassifier
from kailash_ml.bridge import OnnxBridge

# Train sklearn model
model = RandomForestClassifier(n_estimators=100)
model.fit(X_train, y_train)

# Export to ONNX
bridge = OnnxBridge()
onnx_path = bridge.export_sklearn(
    model=model,
    output_path="./models/rf_churn.onnx",
    input_name="features",
    input_shape=(None, X_train.shape[1]),  # Dynamic batch size
    input_dtype="float32",
)
```

### Supported sklearn Models

All scikit-learn estimators supported by skl2onnx, including:

- Tree-based: RandomForest, GradientBoosting, ExtraTrees, AdaBoost
- Linear: LogisticRegression, LinearRegression, SGDClassifier, Ridge, Lasso
- SVM: SVC, SVR, LinearSVC
- Neighbors: KNeighborsClassifier, KNeighborsRegressor
- Ensemble: VotingClassifier, StackingClassifier, BaggingClassifier
- Pipeline: sklearn.pipeline.Pipeline (full pipeline export)

```python
# Export full sklearn pipeline (preprocessing + model)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

pipe = Pipeline([
    ("scaler", StandardScaler()),
    ("model", RandomForestClassifier()),
])
pipe.fit(X_train, y_train)

onnx_path = bridge.export_sklearn(
    model=pipe,
    output_path="./models/pipeline_churn.onnx",
    input_name="features",
    input_shape=(None, X_train.shape[1]),
    input_dtype="float32",
)
```

## LightGBM / XGBoost to ONNX

```python
import lightgbm as lgb

# Train LightGBM model
lgb_model = lgb.LGBMClassifier(n_estimators=200)
lgb_model.fit(X_train, y_train)

# Export via skl2onnx (LightGBM sklearn API)
onnx_path = bridge.export_sklearn(
    model=lgb_model,
    output_path="./models/lgb_churn.onnx",
    input_name="features",
    input_shape=(None, X_train.shape[1]),
    input_dtype="float32",
)
```

## PyTorch to ONNX

```python
import torch

# Train PyTorch model
class ChurnNet(torch.nn.Module):
    def __init__(self, input_dim):
        super().__init__()
        self.layers = torch.nn.Sequential(
            torch.nn.Linear(input_dim, 64),
            torch.nn.ReLU(),
            torch.nn.Linear(64, 32),
            torch.nn.ReLU(),
            torch.nn.Linear(32, 1),
            torch.nn.Sigmoid(),
        )

    def forward(self, x):
        return self.layers(x)

model = ChurnNet(input_dim=10)
# ... train model ...

# Export to ONNX
onnx_path = bridge.export_pytorch(
    model=model,
    output_path="./models/churn_net.onnx",
    input_shape=(1, 10),          # Example input shape
    input_names=["features"],
    output_names=["prediction"],
    dynamic_axes={
        "features": {0: "batch_size"},
        "prediction": {0: "batch_size"},
    },
    opset_version=17,
)
```

## Verification

Always verify exported ONNX models against the original. OnnxBridge provides automated verification that compares outputs within tolerance.

```python
# Verify sklearn export
verification = bridge.verify_sklearn(
    original_model=model,
    onnx_path="./models/rf_churn.onnx",
    test_data=X_test[:100],       # Sample test data
    tolerance=1e-5,               # Max absolute difference
)
# verification.passed          — True/False
# verification.max_difference  — largest output difference
# verification.mean_difference — average output difference

# Verify PyTorch export
verification = bridge.verify_pytorch(
    original_model=pytorch_model,
    onnx_path="./models/churn_net.onnx",
    test_input=torch.randn(10, 10),
    tolerance=1e-5,
)

assert verification.passed, f"ONNX export verification failed: max diff {verification.max_difference}"
```

## Cross-Language Serving Path

The primary use case for ONNX export: train in Python, serve in Rust (or any language with ONNX Runtime bindings).

```
Python (training)                    Rust (serving)
─────────────────                    ──────────────
sklearn/PyTorch model                onnxruntime-rs
        │                                   │
    OnnxBridge.export_*()            load("model.onnx")
        │                                   │
    model.onnx ──── transfer ────→   InferenceSession
        │                                   │
    bridge.verify_*()                session.run(inputs)
```

### Metadata Embedding

OnnxBridge embeds training metadata in the ONNX model for traceability:

```python
onnx_path = bridge.export_sklearn(
    model=model,
    output_path="./models/rf_churn.onnx",
    metadata={
        "model_name": "churn_predictor",
        "model_version": "3",
        "schema_name": "user_churn",
        "training_date": "2025-07-01",
        "metrics": {"accuracy": 0.92, "f1": 0.87},
    },
    input_name="features",
    input_shape=(None, X_train.shape[1]),
    input_dtype="float32",
)

# Read metadata back
meta = bridge.read_metadata("./models/rf_churn.onnx")
# meta["model_name"], meta["model_version"], etc.
```

## ModelRegistry Integration

Export and register ONNX models in a single step via TrainingPipeline.

```python
result = await pipeline.train(
    schema=schema,
    model_spec=ModelSpec(
        model_class="sklearn.ensemble.RandomForestClassifier",
        export_onnx=True,  # Automatically exports to ONNX after training
    ),
    eval_spec=EvalSpec(metrics=["accuracy", "f1"]),
)
# result.onnx_path — path to ONNX artifact
# Both .pkl and .onnx registered in ModelRegistry
```

## ONNX Runtime Providers

```python
import onnxruntime as ort

# CPU (default)
session = ort.InferenceSession("model.onnx", providers=["CPUExecutionProvider"])

# GPU (requires kailash-ml[dl-gpu])
session = ort.InferenceSession("model.onnx", providers=[
    "CUDAExecutionProvider",
    "CPUExecutionProvider",  # Fallback
])

# TensorRT (maximum GPU performance)
session = ort.InferenceSession("model.onnx", providers=[
    "TensorrtExecutionProvider",
    "CUDAExecutionProvider",
    "CPUExecutionProvider",
])
```

## Critical Rules

- Always verify ONNX export against original model before deploying
- Use dynamic batch axes for production serving (batch_size dimension)
- Embed training metadata in ONNX model for traceability
- sklearn pipeline export preserves preprocessing — no separate preprocessing needed at serving time
- PyTorch export: specify `opset_version=17` (or latest stable) for widest compatibility
- Cross-language path: Python trains, ONNX transfers, any runtime serves
