# Issue #495 — `register_estimator()` Audit (kailash-py)

Cross-SDK audit of kailash-rs#402 (commit 5429928c) which added
`register_estimator()` / `register_transformer()` hooks to open hardcoded
`isinstance(x, (Pipeline, FeatureUnion, ColumnTransformer))` allowlists.

## Per-File Findings

| Path                               | `isinstance(...)` match                                                                                                                                                                                                                                     | Category                                                                               | Verdict |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ------- |
| `engines/preprocessing.py`         | none — `data[col].dtype in (pl.Boolean, ...)` (L66, L87), `if dtype in NUMERIC_DTYPES` (L85, L968)                                                                                                                                                          | not user-estimator gates; only **polars dtype** membership tests                       | NO-GAP  |
| `engines/preprocessing.py`         | scaler/imputer/encoder selection by **string keyword** (L1080 `scaler_classes[self._normalize_method]`, L629 `KNNImputer`, L636 `IterativeImputer`)                                                                                                         | string-dispatch enum, not isinstance allowlist                                         | NO-GAP  |
| `engines/training_pipeline.py`     | none — model loaded via `importlib.import_module(parts[0])` + `cls(**hp)` (L67, L598). Validation is **prefix allowlist** in `_shared.validate_model_class` (`sklearn.` / `lightgbm.` / `xgboost.` / `catboost.` / `kailash_ml.` / `torch.` / `lightning.`) | duck-typed import + prefix allowlist (extensible by string prefix, not isinstance)     | NO-GAP  |
| `engines/training_pipeline.py`     | `isinstance(output, torch.Tensor)` (L671)                                                                                                                                                                                                                   | output-shape check on Lightning forward pass, not estimator gating                     | NO-GAP  |
| `engines/training_pipeline.py`     | framework dispatch by **string** `model_spec.framework == "lightning"/"lightgbm"/else sklearn` (L254-265)                                                                                                                                                   | string discriminator; sklearn branch accepts any duck-typed `.fit()/.predict()`        | NO-GAP  |
| `engines/hyperparameter_search.py` | none — only `isinstance(output, torch.Tensor)`-style absent. All param/model dispatch is `p.type == "uniform"/...` string match (L102-140, L553-567, L658-672)                                                                                              | string-typed distribution dispatch                                                     | NO-GAP  |
| `engines/hyperparameter_search.py` | model is forwarded as `base_model_spec` to `pipeline.train()` — duck-typed via `getattr(base_model_spec, "model_class", "")` (L331) and attribute access in trial loops (L432-434)                                                                          | structural / duck-typed                                                                | NO-GAP  |
| `engines/automl_engine.py`         | candidate families are `(model_class_str, framework_str, hp_dict)` tuples (L341-417). Selection by `config.task_type == "classification"/"regression"` string (L642-647)                                                                                    | string registry, no isinstance gate                                                    | NO-GAP  |
| `engines/automl_engine.py`         | search-space dispatch by `framework == "xgboost"/"lightgbm"` and substring `"randomforest" in cls_name` (L707-756)                                                                                                                                          | string substring match; falls through to a generic `n_estimators` space (no rejection) | NO-GAP  |

## Final Verdict

**NO-GAP** across all four files.

## Why kailash-py Has No Equivalent Bug

kailash-py's ML engine never accepts an estimator/transformer **object** at
the API surface. Users supply a `model_class: str` (e.g.
`"sklearn.ensemble.RandomForestClassifier"`), and the pipeline imports +
instantiates via `importlib`. The only gate is
`_shared.validate_model_class()`, a **prefix allowlist** that already
satisfies the kailash-rs#402 requirement: third-party estimators are
admitted by exporting them from any module under one of the seven allowed
prefixes (e.g. `kailash_ml.user_models.MyEstimator`). No source edit is
needed; no `register_estimator()` API is needed.

The Rust isinstance gate exists because Rust generics force the engine to
type-erase to a concrete trait object enum, requiring an explicit
allowlist of accepted concrete types. Python's duck typing dissolves the
problem at the language level — the sklearn branch just calls
`model.fit(X, y)` and `model.predict(X)` (training_pipeline.py L497, L653).

The only **substring matches** in `automl_engine._default_search_space`
(L733 `"randomforest" in cls_name`, L740 `"gradientboosting" in cls_name`)
fall through to a generic `n_estimators`-only search space rather than
rejecting unknown classes — degraded search quality, not a hard gate.
That is a P3 enhancement (allow users to register custom default search
spaces), not the issue raised by kailash-rs#402.

## Cross-SDK Note

**Recommendation: close kailash-py side as wontfix-by-design.**

Per `rules/cross-sdk-inspection.md` MUST Rule 3 (EATP D6 — semantics
match, implementation may differ), the Python idiom for "user supplies
their own estimator" IS the prefix allowlist + `importlib`, not a
`register_estimator()` decorator registry. Adding a Python
`register_estimator()` would create a parallel API with no functional
benefit and would violate `framework-first.md` (raw allowlist + import
path is the established pattern). Add a short note on kailash-rs#402
linking back to this audit so the cross-SDK alignment is recorded.

If the team wants to harmonize the `automl_engine._default_search_space`
substring dispatch, file that as a separate kailash-py P3 enhancement —
it is unrelated to the kailash-rs#402 root cause.
