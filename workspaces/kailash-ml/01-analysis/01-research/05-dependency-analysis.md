# Dependency Analysis

## Purpose

Analyze the full dependency chain for kailash-ml, install sizes, version compatibility risks, and the viability of the kailash-ml-protocols approach.

## Base Install Analysis (~195MB)

### Dependency breakdown

| Package              | Size       | Required By                                             | Transitive Deps                             |
| -------------------- | ---------- | ------------------------------------------------------- | ------------------------------------------- |
| polars               | ~30MB      | All engines                                             | pyarrow (via Arrow C interface, no pip dep) |
| numpy                | ~25MB      | sklearn, lightgbm, scipy, interop                       | None significant                            |
| scipy                | ~35MB      | DriftMonitor (KS test), HyperparameterSearch (Bayesian) | numpy                                       |
| plotly               | ~15MB      | DataExplorer                                            | tenacity, packaging                         |
| scikit-learn         | ~30MB      | TrainingPipeline, AutoML, FeatureEngineer               | numpy, scipy, joblib, threadpoolctl         |
| lightgbm             | ~5MB       | TrainingPipeline, AutoML baseline                       | numpy, scipy                                |
| skl2onnx             | ~5MB       | ModelSerializer (ONNX bridge)                           | numpy, onnx, protobuf                       |
| onnxmltools          | ~5MB       | ModelSerializer (LightGBM ONNX)                         | numpy, onnx                                 |
| kailash              | ~5MB       | Core SDK                                                | Many (runtime, workflow, nodes)             |
| kailash-dataflow     | ~5MB       | FeatureStore, ModelRegistry                             | kailash                                     |
| kailash-nexus        | ~5MB       | InferenceServer                                         | kailash, fastapi, uvicorn                   |
| kailash-ml-protocols | ~0.05MB    | Protocol contracts                                      | None                                        |
| **Total**            | **~165MB** |                                                         |                                             |

**Note**: The ~195MB estimate in the brief likely includes transitive dependencies (protobuf, onnx, joblib, threadpoolctl, etc.) which add ~30MB.

### Is 195MB acceptable?

**Context**: `pip install scikit-learn` alone is ~90MB (with numpy + scipy). `pip install lightgbm` adds ~5MB. The kailash-ml base is essentially "sklearn + lightgbm + polars + Kailash framework" -- the framework tax is ~35MB (kailash + dataflow + nexus + protocols).

**Comparison with competitors**:

- `pip install mlflow`: ~200MB
- `pip install tensorflow`: ~500MB
- `pip install torch` (CPU): ~200MB
- `pip install kedro`: ~50MB (but does nothing ML-specific)

**Verdict**: 195MB is in the normal range for an ML framework. The concern is not the absolute size but the **incremental** size for users who already have kailash (which is ~15MB). Adding kailash-ml adds ~180MB of ML libraries. This is unavoidable if the base install must be able to train models.

### The alternative: sklearn/lightgbm as optional

If sklearn and lightgbm were in `[classical]` extra instead of base, the base install would be ~65MB (polars + scipy + plotly + Kailash). But the base install could not train models -- only DataExplorer and FeatureStore would work. This defeats the purpose of a ML framework.

**The architecture decision (sklearn + lightgbm in base) is correct.** A base install that cannot train a model is a framework with no content.

## [dl] Extra Analysis (~285MB additional)

| Package      | Size (CPU) | Notes                                          |
| ------------ | ---------- | ---------------------------------------------- |
| torch        | ~200MB     | Largest single dependency. CPU-only from PyPI. |
| lightning    | ~5MB       | Thin orchestration layer on top of torch       |
| torchvision  | ~10MB      | Vision model building blocks                   |
| torchaudio   | ~10MB      | Audio model building blocks                    |
| timm         | ~5MB       | 800+ model architectures (weights on-demand)   |
| transformers | ~50MB      | HuggingFace ecosystem access                   |
| onnxruntime  | ~50MB      | ONNX inference engine                          |

**Total [dl] installed**: ~480MB (base + dl).

**Risk**: PyTorch CPU from PyPI works. But `[dl-gpu]` requires `--extra-index-url` for CUDA wheels. pip/uv extras cannot enforce an extra index URL. The `kailash-ml-gpu-setup` CLI mitigates this but adds friction.

## [rl] Extra Analysis (~15MB additional)

| Package           | Size  | Notes                   |
| ----------------- | ----- | ----------------------- |
| stable-baselines3 | ~5MB  | Classical RL algorithms |
| gymnasium         | ~10MB | Environment interface   |

**Dependencies**: [rl] requires [dl] (SB3 uses PyTorch internally). This means `pip install kailash-ml[rl]` pulls in ~500MB total.

## kailash-ml-protocols Viability

### Size: ~50KB

```
kailash_ml_protocols/
  __init__.py       # Exports
  protocols.py      # MLToolProtocol, AgentInfusionProtocol (~100 lines)
  schemas.py        # FeatureSchema, ModelSignature, MetricSpec (~200 lines)
```

No dependencies beyond Python standard library (uses `typing.Protocol`). This is genuinely thin.

### Maintenance burden

- **Release cadence**: Must be released before kailash-ml OR kailash-kaizen when protocols change
- **Backward compatibility**: Protocol methods cannot be removed without breaking implementations. Only additive changes are safe.
- **Versioning**: `>=1.0,<2.0` pin in both kailash-ml and kailash-kaizen. Breaking protocol changes require a major version bump of ALL three packages.

### Alternative considered: no protocol package

Without kailash-ml-protocols:

- kailash-ml would define its own types and check for kailash-kaizen at runtime
- kailash-kaizen would define its own ML types and check for kailash-ml at runtime
- No shared type contracts -- duck typing everywhere
- Type checkers (mypy, pyright) cannot verify the interface

**Assessment**: The protocol package is worth the maintenance cost. The alternatives are all worse.

## Version Compatibility Matrix

### Critical version pins

| Package      | Min Version | Why This Minimum                                  |
| ------------ | ----------- | ------------------------------------------------- |
| polars       | >=1.0       | Stable API (pre-1.0 had breaking changes monthly) |
| scikit-learn | >=1.4       | `set_output("polars")` support (v1.4+)            |
| lightgbm     | >=4.3       | Categorical feature improvements                  |
| torch        | >=2.2       | `torch.compile()` stability                       |
| lightning    | >=2.2       | Matches torch >=2.2 compatibility                 |
| onnxruntime  | >=1.17      | Matches ONNX opset version from skl2onnx >=1.16   |

### Version conflict risks

1. **numpy version**: sklearn >=1.4 requires numpy >=1.23. torch >=2.2 requires numpy >=1.22. Compatible.
2. **scipy version**: sklearn >=1.4 requires scipy >=1.6. DriftMonitor uses scipy >=1.12 for KS test improvements. Compatible (higher wins).
3. **protobuf version**: onnx requires protobuf >=3.20. transformers requires protobuf >=3.20. Compatible.
4. **CUDA versions**: torch CUDA builds are tied to specific CUDA toolkit versions (11.8, 12.1, 12.4). Users must match. The `kailash-ml-gpu-setup` CLI detects and advises.

### No maximum version pins on ML libraries

The architecture deliberately avoids maximum version pins (`scikit-learn>=1.4` not `scikit-learn>=1.4,<2.0`). Rationale: ML libraries evolve rapidly. Maximum pins create dependency hell in environments where users also install other ML tools.

**Risk**: A future sklearn 2.0 could break kailash-ml. Mitigation: CI tests against latest versions weekly. Breaking changes are caught before they reach users.

## Summary

| Aspect                    | Assessment                                                             |
| ------------------------- | ---------------------------------------------------------------------- |
| Base install size (195MB) | Acceptable -- comparable to mlflow, lighter than tensorflow            |
| [dl] size (480MB CPU)     | Expected for PyTorch-based ML                                          |
| [dl-gpu] friction         | Real -- requires --extra-index-url for CUDA wheels                     |
| kailash-ml-protocols      | Viable -- standard circular dep solution, ~50KB, worth the maintenance |
| Version compatibility     | Good -- no conflicts between pinned minimums                           |
| Max version risk          | Accepted trade-off -- CI catches breaks weekly                         |
