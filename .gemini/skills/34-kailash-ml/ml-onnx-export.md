# ML ONNX Export

Export models to ONNX for cross-language serving. Train in Python, export to ONNX,
serve in Rust or any ONNX Runtime environment.

## OnnxBridge

`OnnxBridge` (top-level `from kailash_ml import OnnxBridge`) handles conversion and
validation for all supported model families. The bridge has three methods:
`export(model, framework, ...)`, `validate(model, onnx_path, sample_input, ...)`,
and `check_compatibility(model, framework)` — there are no per-framework
`export_sklearn` / `export_pytorch` variants; `framework` is a parameter.

```python
from kailash_ml import OnnxBridge

bridge = OnnxBridge()
```

## sklearn to ONNX (via skl2onnx)

```python
from sklearn.ensemble import RandomForestClassifier
from kailash_ml import OnnxBridge

# Train sklearn model
model = RandomForestClassifier(n_estimators=100)
model.fit(X_train, y_train)

# Export to ONNX — framework selects the converter; n_features sizes the input.
bridge = OnnxBridge()
result = bridge.export(
    model,
    framework="sklearn",
    n_features=X_train.shape[1],
    output_path="./models/rf_churn.onnx",
)
print(f"exported={result.success} path={result.onnx_path} status={result.onnx_status}")
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
# Export a full sklearn pipeline (preprocessing + model) — same export() call.
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

pipe = Pipeline([
    ("scaler", StandardScaler()),
    ("model", RandomForestClassifier()),
])
pipe.fit(X_train, y_train)

result = bridge.export(
    pipe,
    framework="sklearn",
    n_features=X_train.shape[1],
    output_path="./models/pipeline_churn.onnx",
)
```

## LightGBM / XGBoost to ONNX

LightGBM/XGBoost expose the sklearn estimator API, so they export via the
`"sklearn"` framework converter.

```python
import lightgbm as lgb

lgb_model = lgb.LGBMClassifier(n_estimators=200)
lgb_model.fit(X_train, y_train)

result = bridge.export(
    lgb_model,
    framework="sklearn",
    n_features=X_train.shape[1],
    output_path="./models/lgb_churn.onnx",
)
```

## PyTorch to ONNX

```python
import torch

class ChurnNet(torch.nn.Module):
    def __init__(self, input_dim):
        super().__init__()
        self.layers = torch.nn.Sequential(
            torch.nn.Linear(input_dim, 64),
            torch.nn.ReLU(),
            torch.nn.Linear(64, 1),
            torch.nn.Sigmoid(),
        )

    def forward(self, x):
        return self.layers(x)

model = ChurnNet(input_dim=10)
# ... train model ...

# A sample input tensor sizes the exported graph (dynamic batch axis).
result = bridge.export(
    model,
    framework="pytorch",
    sample_input=torch.randn(1, 10),
    output_path="./models/churn_net.onnx",
)
```

## Validation

Always validate an exported ONNX model against the original — `validate` compares
outputs within `tolerance` and returns a structured result.

```python
validation = bridge.validate(
    model,                       # the original model
    result.onnx_path,            # path from the export result
    sample_input=X_test[:100],   # representative input
    tolerance=1e-5,
)
print(f"valid={validation.valid} max_diff={validation.max_diff} mean_diff={validation.mean_diff}")
assert validation.valid, f"ONNX validation failed: max diff {validation.max_diff}"
```

## Compatibility Pre-Check

Before exporting, confirm a model family is convertible:

```python
compat = bridge.check_compatibility(model, framework="sklearn")
# Inspect compat before committing to an export path.
```

## Cross-Language Serving Path

The primary use case: train in Python, serve in Rust (or any ONNX Runtime).

```
Python (training)                    Rust (serving)
─────────────────                    ──────────────
sklearn/PyTorch model                onnxruntime-rs
        │                                   │
    bridge.export(framework=...)     load("model.onnx")
        │                                   │
    model.onnx ──── transfer ────→   InferenceSession
        │                                   │
    bridge.validate(...)             session.run(inputs)
```

## ModelRegistry Integration

Export + register ONNX in one step via `ModelSpec` — ONNX is the default
`km.register` / registry format (`format="onnx"`).

```python
from kailash_ml.engines.training_pipeline import ModelSpec, EvalSpec

result = await pipeline.train(
    data=df,
    schema=schema,
    model_spec=ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier"),
    eval_spec=EvalSpec(metrics=["accuracy", "f1"]),
    experiment_name="churn-onnx",
)
# The registered version carries onnx_status; load the artifact via the registry.
```

## ONNX Runtime Providers

```python
import onnxruntime as ort

# CPU (default)
session = ort.InferenceSession("model.onnx", providers=["CPUExecutionProvider"])

# GPU (requires the kailash-ml deep-learning GPU extra)
session = ort.InferenceSession("model.onnx", providers=[
    "CUDAExecutionProvider",
    "CPUExecutionProvider",  # fallback
])
```

## Critical Rules

- Always `validate()` an export against the original before deploying
- `export(model, framework=...)` — one method, `framework` selects the converter
- LightGBM / XGBoost export through the `"sklearn"` framework (sklearn estimator API)
- PyTorch export: pass a representative `sample_input` to size the graph
- Cross-language path: Python trains, ONNX transfers, any runtime serves
