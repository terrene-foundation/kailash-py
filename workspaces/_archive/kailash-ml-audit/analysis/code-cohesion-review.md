# kailash-ml Code Cohesion Review

**Scope**: `packages/kailash-ml/` at 7f252967 (main, 2026-04-16). Cohesion audit, not line-level.
**Vision**: Single Engine, PyTorch Lightning core, GPU-first, ML/DL/RL unified, PyCaret-better DX, MLflow-better tracking, enterprise-ready.
**User verdict**: "haphazardly put together, no engine workflow, devs hunt for API and work with primitives, extremely disjointed."

**Top-line**: User is correct. `kailash-ml` is a catalogue of 17 mostly-independent engine classes with almost no wiring. The composition engine (`AutoMLEngine`) promises to orchestrate `TrainingPipeline + ModelRegistry + ExperimentTracker + HyperparameterSearch` but only imports the last one — the docstring lies. The "Lightning core" claim is false at module level: sklearn is referenced in 53 source sites; `import lightning` appears in 1 site (one branch of `training_pipeline.py`). The `agents/` subpackage is unreachable from `kailash_ml.__init__`. Top-level export / public surface ratio ≈ 20% (27 / ~137).

---

## 1. Module Dependency Graph

Internal edges only (`→` means "imports"). Omitted modules have no internal imports.

```
__init__                       → _version, types, engines.data_explorer
metrics/__init__               → metrics._registry
engines.clustering             → engines._shared, interop
engines.dim_reduction          → interop
engines.anomaly_detection      → interop
engines.ensemble               → interop, engines._shared
engines.inference_server       → types, engines.model_registry, interop
engines.training_pipeline      → types, engines.model_registry, interop, engines._shared
engines.feature_store          → types, engines._feature_sql, interop
engines.feature_engineer       → types, _decorators, engines._shared
engines.automl_engine          → types   (+ lazy: engines.hyperparameter_search)
engines.data_explorer          → engines._shared  (+ lazy: _data_explorer_report)
engines.{model_registry, drift_monitor, hyperparameter_search, model_visualizer}  → types | _decorators
engines.{model_explainer, preprocessing, experiment_tracker, _guardrails}         → (none internal)
rl.trainer                     → rl.policy_registry
dashboard.server               → (lazy) engines.experiment_tracker, engines.model_registry
agents.*                       → agents.tools, types    (never imported by anything outside agents/)
```

- **No circular deps, no god-modules.** Highest in-degree: `types.py` (7), `interop.py` (6) — appropriate for primitives.
- **16 of 17 engine modules have zero non-trivial cross-engine edges.** The only real cross-engine wiring is `training_pipeline → model_registry` and `inference_server → model_registry`. `AutoMLEngine → hyperparameter_search` is a lazy, in-method import.
- **`agents/` is disconnected from the package.** Zero non-agent files import anything from `agents/`. Zero top-level exports. `dir(kailash_ml)` never reveals its existence.
- **`engines/_guardrails.py` (414 LOC) has zero production callers** — the definition of orphan.
- **Clusters that should be one module**: (a) classical-ML sklearn wrappers (`clustering`, `anomaly_detection`, `dim_reduction`, `ensemble`, `feature_engineer`) all share the "wrap sklearn estimator, return a dataclass" shape but no base class; (b) registry trio (`model_registry`, `env_registry`, `policy_registry`) share a "versioned persistence" contract with zero reuse — `ArtifactStore` protocol lives inside `model_registry` and is not reused by the others.

---

## 2. Layering Assessment (Specs → Primitives → Engines → Entrypoints)

`rules/framework-first.md` mandates Engines as the default layer. `kailash-ml` inverts this.

| Claimed Engines that are actually Primitives | Why |
| -------------------------------------------- | --- |
| `PreprocessingPipeline` (1307 LOC)           | `setup`/`transform`/`inverse_transform` — sklearn wrapping, no composition, no registry binding. |
| `ClusteringEngine`, `AnomalyDetectionEngine`, `DimReductionEngine`, `EnsembleEngine`, `FeatureEngineer` | Each wraps sklearn with one-or-two verb methods; no cross-engine composition. |
| `ModelVisualizer` (745 LOC)                  | Plotly wrappers returning raw figures. |
| `ModelExplainer`                             | SHAP wrapper; marked `experimental`. |

| Correct Engines (real composition)           | Scope |
| -------------------------------------------- | ----- |
| `ModelRegistry`                              | Versioning, artifacts, promotion, MLflow import/export. |
| `ExperimentTracker`                          | Runs, metrics, artifacts, nested runs. |
| `DriftMonitor`                               | Schedules, callbacks, reference data. |
| `TrainingPipeline`                           | train/calibrate/evaluate/retrain, composes `ModelRegistry`. |
| `InferenceServer`                            | predict/batch/cache, composes `ModelRegistry`, exposes Nexus/MCP hooks. |
| `HyperparameterSearch`                       | Optuna-backed search orchestration. |
| `FeatureStore`, `DataExplorer`               | Borderline engines — real state management. |
| `AutoMLEngine`                               | **Engine, but orphaned composition** — docstring promises orchestration it does not perform. |

**Orphan primitive**: `_guardrails.py` — a Mixin + CostTracker + AuditEntry defined under `engines/`, not exported, never imported by any other module. Dead code.

**Hidden subpackages**: `agents/` (7 files, ~930 LOC) and `rl/` (3 classes) are not surfaced at top-level. Users must know the exact module path to import `FeatureEngineerAgent` or `RLTrainer`.

---

## 3. Orphan Detection (per `rules/orphan-detection.md`)

Every top-level `*Engine` / `*Store` / `*Registry` / `*Tracker` / `*Monitor` / `*Pipeline` / `*Server` from `kailash_ml.__init__`, with its in-package non-test production call sites:

| Class                     | In-package production callers |
| ------------------------- | ----------------------------- |
| `ModelRegistry`           | 2 (`training_pipeline`, `inference_server`) — wired |
| `DriftMonitor`            | 1 (`dashboard.server` via `app.state`) — state-bag only |
| `ExperimentTracker`       | 1 (`dashboard.server`, lazy error imports only) — state-bag only |
| `HyperparameterSearch`    | 1 (`automl_engine`, lazy in-method) — wired via lazy |
| `FeatureStore`            | **0** (docstring mentions only) |
| `TrainingPipeline`        | **0** |
| `InferenceServer`         | **0** |
| `AutoMLEngine`            | **0** |
| `DataExplorer`            | **0** |
| `FeatureEngineer`         | **0** |
| `EnsembleEngine`          | **0** |
| `ClusteringEngine`        | **0** |
| `AnomalyDetectionEngine`  | **0** |
| `DimReductionEngine`      | **0** |
| `PreprocessingPipeline`   | **0** |
| `ModelVisualizer`         | **0** |
| `ModelExplainer`          | **0** |
| `OnnxBridge`              | **0** |
| `MlflowFormatReader/Writer` | **0** |
| `MLDashboard`             | 1 (same package `dashboard/`) — wired |
| `_guardrails.*` (mixin, trackers) | **0** — dead code |

**Orphan count**: **14 top-level facade classes** with zero in-package production call sites (they execute only when a user calls them directly), plus **1 fully dead internal module** (`_guardrails.py`, 414 LOC), plus **1 hidden subpackage** (`agents/`, 930 LOC not exposed).

This is NOT the Phase-5.11 "class claims to execute and doesn't" pattern — users CAN import these and they work. The failure shape is different: **`AutoMLEngine`, which exists specifically to compose the others, does not compose them.** That single fact IS the Phase-5.11 shape, at the composition layer. Its docstring says "TrainingPipeline / ModelRegistry / ExperimentTracker"; its imports say "HyperparameterSearch only."

---

## 4. API Surface Fragmentation

- `kailash_ml.__init__.py` `__all__`: **27** exports (1 version, 6 types, 20 engines/primitives).
- Total public classes + functions in the package: **~137**.
- Ratio: **~20%** — mid-zone; the user still "hunts" because the hidden 80% includes every result dataclass and the entire `agents/` and `rl/` subpackages.

Hidden surface users cannot find without reading source:
- All result dataclasses (`DriftReport`, `AutoMLResult`, `SearchResult`, `PredictionResult`, `TrainingResult`, `BlendResult`/`StackResult`/`BagResult`/`BoostResult`, `AnomalyResult`, `ClusterResult`, `DimReductionResult`, `DataProfile`, `ColumnProfile`, `GeneratedFeatures`, `SelectedFeatures`, `FeatureRank`, `VisualizationReport`, `Experiment`, `Run`, `MetricEntry`, `RunComparison`).
- All typed errors (`ExperimentNotFoundError`, `RunNotFoundError`, `ModelNotFoundError`, `LLMBudgetExceededError`, `GuardrailBudgetExceededError`).
- All agents (7) and RL classes (3).

**Recommendation**: Re-export result dataclasses and typed errors at top-level (ratio rises to ~45%, coherent) OR hide them behind `engine.last_result` / `engine.history` accessors (ratio ~20%, surface tightens). The current state is the worst of both — 27 exports, 110 more findable only via source-reading.

---

## 5. Test Coverage Distribution

Source = 19,198 LOC across 46 files. Tests = 14,016 LOC across 40 files. Ratio 0.73 overall — appears healthy in aggregate, but the distribution is uneven.

**Flags**:

- `engines/_data_explorer_report.py` — **525 LOC, zero tests.**
- `engines/_guardrails.py` — 414 LOC, 195 test LOC (Tier 1 only). Classic Phase-5.11 shape: tested but never invoked by any consumer.
- `engines/automl_engine.py` — **716 LOC, 236 test LOC (ratio 0.33).** The composition engine of the package has the weakest test coverage; none of its tests exercise cross-engine orchestration.
- `agents/*.py` — 930 LOC total, 175 test LOC (ratio 0.19). Most agents are not tested end-to-end.
- `engines/model_registry.py` — 920 LOC, 310 test LOC (ratio 0.34).

**Integration tier**: 6 files, all single-engine (`test_feature_store.py`, `test_model_registry.py`, `test_training_pipeline.py`, `test_inference_server.py`, `test_drift_monitor.py`, `test_hyperparameter_search.py`). **Zero integration tests exercise cross-engine orchestration.** No test proves `TrainingPipeline → ModelRegistry → InferenceServer → DriftMonitor` works end-to-end. This is why "enterprise-ready" is unsupported.

---

## 6. Cohesion per Engine

Scored on: (a) typed-result vs raw dict/tuple, (b) param naming consistency, (c) error taxonomy, (d) structured logging per `rules/observability.md`.

| Engine                           | Typed result | Param naming | Errors                 | Logging   | Cohesion |
| -------------------------------- | ------------ | ------------ | ---------------------- | --------- | -------- |
| `ModelRegistry`                  | yes          | yes          | typed (`ModelNotFoundError`) | yes   | **High** |
| `ExperimentTracker`              | yes          | yes          | typed (`Experiment/RunNotFoundError`) | yes | **High** |
| `DriftMonitor`                   | yes          | yes          | mixed                  | yes       | High     |
| `TrainingPipeline`               | yes          | yes          | generic                | partial   | Med-High |
| `InferenceServer`                | yes          | yes          | generic                | partial   | Med-High |
| `AutoMLEngine`                   | yes          | partial      | typed+generic          | partial   | Med      |
| `HyperparameterSearch`           | yes          | yes          | generic                | partial   | Med      |
| `FeatureStore`                   | mixed (dict/DataFrame/list) | yes | generic | partial | Med   |
| `DataExplorer`                   | yes          | yes          | generic                | partial   | Med      |
| `Clustering/Anomaly/DimReduction/FeatureEngineer` | yes | yes | generic   | minimal   | Med      |
| `EnsembleEngine`                 | 4 parallel result types | yes | generic     | minimal   | Med-Low  |
| `PreprocessingPipeline`          | mixed (SetupResult / DataFrame / dict) | **inconsistent vocabulary** | generic | **none** | **Low** |
| `ModelVisualizer`                | raw Plotly figures | **no** — every method has a different kwarg shape | generic | none | **Lowest** |
| `ModelExplainer`                 | raw dicts    | partial      | generic                | minimal   | Low      |

**Lowest-cohesion engine**: **`ModelVisualizer`** — 745 LOC of Plotly wrappers returning raw figures, 12 parallel `plot_*` methods with no shared contract, no binding to any other engine, zero in-package callers.

---

## 7. Refactor Priority — Top 10 value-per-LOC-deleted

| # | Path | LOC | Disposition | Rationale |
| - | ---- | --- | ----------- | --------- |
| 1 | `engines/_guardrails.py` | 414 | **Delete**, or fold into `AutoMLEngine` | Zero callers. Dead. |
| 2 | `engines/preprocessing.py` | 1307 | Extract to `primitives/preprocessing.py`; expose via `TrainingPipeline.preprocess(...)` | Largest file, low cohesion, primitive masquerading as engine |
| 3 | `engines/model_visualizer.py` | 745 | Merge into `ExperimentTracker.plot(...)` + `ModelExplainer.plot(...)` | No consumer; 12 parallel methods with no shared contract |
| 4 | `engines/ensemble.py` | 611 | Consolidate `blend/stack/bag/boost` into `TrainingPipeline.ensemble(strategy=…)`; one result type | 4 parallel methods, 4 parallel result classes, identical shape |
| 5 | `engines/{clustering, anomaly_detection, dim_reduction}.py` | 1313 | Unify under one `UnsupervisedEngine(strategy=…)` | 3 parallel sklearn wrappers with the same shape |
| 6 | `engines/_data_explorer_report.py` | 525 | Inline into `data_explorer.py` or add tests | Zero tests; unclear split from `data_explorer.py` |
| 7 | `agents/*.py` (7 files) | ~930 | Re-export at `kailash_ml.agents.*` top-level, or move to a `kaizen-ml` extra | Fully hidden subpackage; users cannot discover |
| 8 | `engines/automl_engine.py` | 716 | Rewrite to actually import `TrainingPipeline`, `ModelRegistry`, `ExperimentTracker` | Docstring promises composition it does not perform |
| 9 | `engines/model_explainer.py` | 468 | Merge into `InferenceServer.explain(...)` + `TrainingPipeline.explain_feature_importance(...)` | Standalone SHAP wrapper; belongs with whatever holds the model |
| 10 | `dashboard/server.py` | 505 | Replace `request.app.state.X` with typed `DashboardContext` protocol | No compile-time signal if an engine is missing |

Net effect of 1–5: ~4,500 LOC consolidated; engine count drops from 17 to ~9 with real composition.

---

## 8. Red Team — Top 20 Integration Tests the Vision Requires

If the vision (single Engine, Lightning core, ML/DL/RL unified, enterprise-ready) is to land, Tier 2 tests MUST prove:

1. **Classical end-to-end**: `FeatureStore.register → TrainingPipeline.train(sklearn) → ModelRegistry.register → InferenceServer.predict` against real artifacts.
2. **Lightning end-to-end**: Same chain with a `LightningModule` — prove the Lightning path actually runs and persists.
3. **RL end-to-end**: `EnvironmentRegistry → RLTrainer → PolicyRegistry → InferenceServer.predict(obs)`.
4. **AutoML composition**: `AutoMLEngine.run(experiment_tracker=…, model_registry=…, training_pipeline=…)` — every candidate is a nested run, best candidate is registered. Will fail today.
5. **HPO + tracker**: `HyperparameterSearch.search(tracker=…)` — every trial becomes a run with params + metrics.
6. **Retraining loop**: `DriftMonitor` callback fires → `TrainingPipeline.retrain` → `ModelRegistry.promote_model`.
7. **Inference cache invalidation** on promote without server restart.
8. **MLflow import round-trip**: `ModelRegistry.import_mlflow(...) → InferenceServer.predict`.
9. **Feature store training set**: `get_training_set(timestamps) → TrainingPipeline.train` with point-in-time correctness.
10. **Tenant isolation** (per `rules/tenant-isolation.md`) on `FeatureStore.get_features` and `ModelRegistry` entries.
11. **Nested runs**: parent with N children, `list_child_runs` returns exactly those.
12. **DriftMonitor shutdown**: `schedule → cancel → shutdown` leaves no orphan asyncio tasks.
13. **ONNX round-trip**: `TrainingPipeline.train → OnnxBridge.export → validate → InferenceServer.predict(onnx)` with prediction parity.
14. **Ensemble under registry**: stacked model persists and serves from registry.
15. **Concurrent inference**: 100 parallel `predict` calls, no `_ModelCache` corruption.
16. **FeatureEngineer → Training**: `generate → select → train(selected)` without shape mismatch.
17. **Preprocessing leak-guard**: `setup(train) → transform(test)` — no test stats leak into setup.
18. **Explain a registered model**: `ModelExplainer.explain_global(registered_model)` loads via `ModelRegistry`.
19. **Dashboard live state**: register + run + drift → dashboard reflects changes in <1s via typed context.
20. **Agent opt-in**: `AutoMLEngine.run(agent=True, auto_approve=False)` — approval gate fires, `LLMCostTracker` records, `LLMBudgetExceededError` halts on overrun.

Today's tests cover 9 of these (flows 1 partial, 5, 9 partial, 11, 12, 15, 17, 18, 20 — none cross-engine). Missing: 2, 3, 4, 6, 7, 13, 14, 16, 19 — the tests that would prove the vision.

---

## Summary

**File**: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/analysis/code-cohesion-review.md`

**Orphan count**: 14 top-level facade classes with zero in-package production call sites; 1 fully dead internal module (`_guardrails.py`, 414 LOC); 1 hidden subpackage (`agents/`, 930 LOC) plus `rl/` (not exported at top-level).

**Top 3 consolidation moves that would most reduce "disjointed" perception**:

1. **Rewrite `AutoMLEngine` to compose `TrainingPipeline + ModelRegistry + ExperimentTracker + HyperparameterSearch` for real** — not just in the docstring. This single change turns 4 siblings into a workflow and is the shortest path to an "engine workflow" the user can demo. ~200 LOC of composition; eliminates the composition-layer orphan.

2. **Unify the sklearn-wrapper engines** (`ClusteringEngine`, `AnomalyDetectionEngine`, `DimReductionEngine`, plus `EnsembleEngine` and `PreprocessingPipeline`) under one `UnsupervisedEngine` / `TransformEngine` with a `strategy` discriminator. Removes ~3,000 LOC of parallel ceremony; leaves one coherent mental model where there are now five.

3. **Expose `agents/` and `rl/` at the top-level — or delete them.** Pick one. Today they exist, work, and cannot be discovered from `kailash_ml` — the exact "dev has to hunt" shape the user complained about.
