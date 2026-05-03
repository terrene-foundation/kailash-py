# Red Team Round 1 — PyCaret/MLflow Parity Analysis

## Critical Findings

### RT-P1: Inference server silently defaults missing features to 0.0

`inference_server.py` uses `features.get(name, 0.0)` for missing features. If a prediction request omits a feature, it silently substitutes 0.0 — producing wrong predictions with no error. MLflow validates signatures at inference. This is a production correctness issue.

**Action**: Add to scope as high-priority fix.

### RT-P2: Stratified KFold severity underestimated

Not just a stub — produces silently incorrect evaluation metrics for imbalanced datasets. Users who believe their folds preserve class distribution are getting misleading metrics.

**Action**: Escalate from "High" to "Critical".

### RT-P3: SHAP dependency chain risk (numba)

`shap` depends on `numba`, which pins `numpy` ranges tightly and can conflict with scientific packages. Also pulls in `matplotlib` and `pandas`, which kailash-ml avoids in core.

**Action**: Keep `[explain]` as optional extra. Consider implementing tree SHAP natively for supported models to minimize dependency surface.

## Missing Features Identified

### RT-P4: Additional PyCaret features not in analysis

| Feature                        | Priority | Rationale                                                  |
| ------------------------------ | -------- | ---------------------------------------------------------- |
| PCA / dimensionality reduction | Medium   | Common workflow, simple sklearn.decomposition.PCA          |
| Target transformation          | Medium   | Important for regression with skewed targets               |
| Unknown category handling      | High     | Runtime errors in production when unseen categories appear |
| RFE feature selection          | Low      | FeatureEngineer already has 3 methods                      |
| Rare category handling         | Low      | Niche PyCaret feature                                      |
| Low variance removal           | Low      | DataExplorer detects but doesn't remove                    |

### RT-P5: MLflow signature validation at inference

InferenceServer does no type checking, no missing feature detection, no shape validation at prediction time. Should validate model signatures.

## Scope Decision

For this implementation cycle, include:

- All 10 original items (stubs, SMOTE, SHAP, calibration, normalization, imputation, multicollinearity, nested runs, auto-logging)
- NEW: Inference signature validation (RT-P5)
- Defer: PCA, target transformation, unknown category handling, RFE → file as separate issues for future

## Corrections Applied

1. Analysis item #1 dependency description clarified (class_weight needs no dep, SMOTE/ADASYN need imbalanced-learn)
2. Stratified KFold escalated to Critical
3. Auto-logging priority raised (disconnected tracker is a major usability gap)
4. interop.py:300 characterization corrected (docstring mention, not "anticipated use case")
