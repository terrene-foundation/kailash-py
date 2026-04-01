# ONNX Bridge Feasibility

## Purpose

Assess which model types can reliably export to ONNX, what the failure modes are, and what percentage of models the ONNX bridge will actually work for.

## ONNX Export Landscape (2026)

### sklearn models via skl2onnx

`skl2onnx` is the standard converter for sklearn models to ONNX format.

**Reliably supported** (>95% success rate):

- Linear models: LinearRegression, LogisticRegression, Ridge, Lasso, ElasticNet, SGDClassifier, SGDRegressor
- Tree models: DecisionTreeClassifier/Regressor, RandomForestClassifier/Regressor, GradientBoostingClassifier/Regressor, ExtraTreesClassifier/Regressor
- SVM: SVC (linear, rbf, poly kernels), SVR, LinearSVC, LinearSVR
- Neighbors: KNeighborsClassifier/Regressor
- Naive Bayes: GaussianNB, BernoulliNB, MultinomialNB
- Clustering: KMeans, MiniBatchKMeans
- Preprocessing: StandardScaler, MinMaxScaler, LabelEncoder, OneHotEncoder, PCA
- Pipeline: sklearn.pipeline.Pipeline (if all steps are supported)

**Partially supported** (may fail on edge cases):

- Custom kernels in SVM (unsupported kernel types fail)
- Stacking/Voting classifiers (complex meta-estimators)
- ColumnTransformer with complex routing
- IsolationForest (supported since skl2onnx 1.14)

**Not supported**:

- Custom sklearn transformers (user-defined classes)
- Models using `__getstate__`/`__setstate__` customization
- Some clustering algorithms (DBSCAN, OPTICS)

**Coverage estimate**: ~90% of common sklearn models export successfully.

### LightGBM via onnxmltools

LightGBM ONNX export is well-supported:

**Reliably supported**:

- LGBMClassifier (binary and multiclass)
- LGBMRegressor
- LGBMRanker

**Limitations**:

- Custom objective functions may not have ONNX equivalents
- Very deep trees (>255 levels) can hit ONNX opset limitations
- Feature names must be consistent between training and ONNX model

**Coverage estimate**: ~95% of LightGBM models export successfully.

### XGBoost via onnxmltools

Similar to LightGBM. XGBoost has native ONNX export support.

**Coverage estimate**: ~95%.

### CatBoost via onnxmltools

CatBoost has native ONNX export:

```python
model.save_model("model.onnx", format="onnx")
```

**Coverage estimate**: ~90% (categorical handling can cause issues in ONNX).

### PyTorch via torch.onnx.export

PyTorch ONNX export is the most variable:

**Reliably supported**:

- Feedforward networks (MLP)
- CNNs (standard architectures: ResNet, VGG, EfficientNet)
- Standard RNNs/LSTMs (with fixed sequence lengths)
- Most torchvision models

**Partially supported** (requires careful input spec):

- Transformer architectures (attention mask shapes must be specified)
- Dynamic control flow (`if` statements based on tensor values)
- Custom autograd functions
- Models using `torch.compile()` (must export before compilation)

**Not supported**:

- Models with Python control flow that depends on input (dynamic shapes)
- Custom CUDA kernels
- Models using unsupported operators (custom ops)
- Some HuggingFace models with complex tokenizer integration

**Coverage estimate**: ~70% of PyTorch models export successfully on first try. ~85% with workarounds (tracing vs scripting, operator overrides).

## ONNX Export Failure Modes

### Failure Mode 1: Unsupported operator

```
RuntimeError: Exporting operator 'aten::unflatten' to ONNX opset 17 is not supported.
```

**Cause**: The model uses a PyTorch operator that has no ONNX equivalent.
**Mitigation**: Check operator support before export. Fall back to native artifact.

### Failure Mode 2: Dynamic shapes

```
torch.onnx.errors.SymbolicValueError: Unsupported: ONNX export of operator reshape with dynamic shape
```

**Cause**: The model reshapes tensors with shapes that depend on input.
**Mitigation**: Specify fixed input shapes via `dynamic_axes` argument. Some models cannot be fixed.

### Failure Mode 3: Custom sklearn transformer

```
skl2onnx.common.exceptions.MissingConverter: Unable to find converter for 'MyCustomTransformer'
```

**Cause**: User-defined sklearn transformers have no ONNX converter.
**Mitigation**: Users must register custom converters or accept native-only inference.

### Failure Mode 4: ONNX runtime shape mismatch

Model exports successfully but fails at inference:

```
onnxruntime.capi.onnxruntime_pybind11_state.InvalidArgument: [ONNXRuntimeError] : 2 : INVALID_ARGUMENT : Invalid rank for input: input expected 2, got 3
```

**Cause**: Input shape at inference does not match the shape used during export.
**Mitigation**: `model_metadata.json` stores input/output schemas. InferenceServer validates inputs before calling ONNX runtime.

### Failure Mode 5: Numeric precision drift

Model exports successfully, inference runs, but predictions differ from native:

```
# Native Python: 0.8734
# ONNX runtime:  0.8731
```

**Cause**: Float32 vs Float64 differences between sklearn (float64) and ONNX runtime (default float32).
**Mitigation**: Document acceptable tolerance. For most ML use cases, 1e-4 precision difference is irrelevant.

## What Percentage of Models Will the ONNX Bridge Work For?

### By framework

| Framework                        | Success Rate | Notes                              |
| -------------------------------- | ------------ | ---------------------------------- |
| sklearn (standard models)        | ~90%         | Custom transformers fail           |
| LightGBM                         | ~95%         | Custom objectives fail             |
| XGBoost                          | ~95%         | Custom objectives fail             |
| CatBoost                         | ~90%         | Categorical handling edge cases    |
| PyTorch (standard architectures) | ~70-85%      | Dynamic shapes, custom ops         |
| PyTorch (HuggingFace)            | ~60-70%      | Complex tokenizer integration      |
| Custom models                    | ~30%         | Depends entirely on implementation |

### Weighted estimate for typical kailash-ml usage

Assuming a typical user trains 60% classical models (sklearn/LightGBM) and 40% deep learning:

- Classical: 0.6 \* 0.92 = 0.55
- Deep learning: 0.4 \* 0.75 = 0.30
- **Weighted success rate: ~85%**

This means ~15% of models will fail ONNX export. The architecture's fallback design (native Python inference, `onnx_status="failed"`) is essential.

## Recommendations

1. **ONNX export should be attempted but never required** -- the current architecture is correct in treating ONNX failure as non-fatal.
2. **Pre-flight check**: Before attempting export, check if the model type is in the known-supported list. If not, skip ONNX export and set `onnx_status="not_applicable"`.
3. **Validation pass**: After ONNX export, run a validation pass: predict on 10 sample inputs with both native and ONNX, compare outputs within tolerance (1e-4). If validation fails, set `onnx_status="failed"` even though export succeeded.
4. **Clear error messages**: When ONNX fails, the error message should say exactly what happened and what the user can do (use native inference, simplify the model, register a custom converter).
5. **Rust consumers**: The Rust SDK (kailash-rs) can only use ONNX models. When a model's `onnx_status` is not "success", the Rust-side error should clearly state: "This model requires Python inference. Use the Python InferenceServer."
6. **v1 ONNX guarantees vs best-effort**: The brief lists "v1 guarantees" and "best effort." This distinction must be reflected in the `model_metadata.json` so InferenceServer can set user expectations.
