# kailash-ml Spec Compliance Red Team

**Scope:** `packages/kailash-ml/src/kailash_ml/` vs `specs/ml-engines.md` and `specs/ml-integration.md`.
**Method:** Spec-compliance skill protocol — AST/grep verification of every MUST/SHALL clause; file existence is not compliance.
**Complements (does not duplicate):** `gap-analysis.md` (analyst), `architecture-assessment.md` (ml-specialist), `dx-audit.md` (uiux-designer), `code-cohesion-review.md` (reviewer). This doc owns **spec traceability + backend matrix + spec-delta for the vision**.
**Audit date:** 2026-04-16. All grep/AST commands re-derived this round; no prior-round outputs trusted.

---

## 1. Executive Summary

Ran AST/grep verification across every mandatory clause in `ml-engines.md` and `ml-integration.md` against `kailash_ml/` production source.

- **Audit A (spec clauses):** 42 load-bearing clauses checked, **33 PASS, 6 PARTIAL, 3 MISSING**. Structural surface (17 engines, types, metrics registry, security allowlist, stage state machine, transaction guards) is accurate; the lies cluster in (i) ONNX bridge's advertised `xgboost`/`pytorch` export paths that fall through to `"not implemented"`, (ii) `@experimental` applied to only 2 of 4 P2 engines, (iii) `AgentGuardrailMixin` exists but no engine inherits it, and (iv) a user-facing CLI bug where `_gpu_setup.py` tells users to `pip install kailash-ml[full-gpu]` but that extra is named `[all-gpu]`.
- **Audit B (compute backends):** Of the 6 backends the user called out (CPU, CUDA, MPS, ROCm, TPU, XPU), only **CPU is fully supported end-to-end**. CUDA is partial (detection + XGBoost `device="cuda"` only). **MPS, ROCm, TPU, XPU have zero references in the source** — the Lightning training path never calls `.to(device)`, so an Apple Silicon user training a Lightning module gets silent CPU execution even though their hardware has Metal. This is the single biggest gap: kailash-ml is a CPU framework with a CUDA hint.
- **Top 3 critical gaps** (ranked severity × probability a user hits it): (1) **Lightning path has no device routing** — MPS/CUDA/TPU/XPU all fall back to CPU with no WARN; (2) **ONNX export "guaranteed" for xgboost is actually "skipped"** — the `xgboost` branch falls through to the unimplemented-framework error; (3) **`_gpu_setup.py` prints an install command with a non-existent extra name** — every CUDA user who runs the advertised CLI gets `ERROR: Package 'kailash-ml' does not provide the extra 'full-gpu'`.

---

## 2. Audit A: Spec Clause Traceability

| # | Spec | § / Clause | Implementation | Status | Evidence |
|---|------|------------|----------------|--------|----------|
| 1 | ml-engines | §1.1 `FeatureStore(conn, *, table_prefix)` + regex validation | `engines/feature_store.py:37` | PASS | class at L37 |
| 2 | ml-engines | §1.1 `_BULK_THRESHOLD = 10_000` | `engines/feature_store.py:28` | PASS | literal present |
| 3 | ml-engines | §1.1 zero raw SQL in `feature_store.py` | grep SELECT/INSERT | PASS | 0 hits outside docstrings |
| 4 | ml-engines | §1.1 LazyFrame collected eagerly in `compute` | `feature_store.py:157` | PASS | `isinstance(..., pl.LazyFrame)` |
| 5 | ml-engines | §1.1 `list_schemas()` method | `feature_store.py:393` | PASS | present |
| 6 | ml-engines | §1.2 stage machine `VALID_TRANSITIONS` | `model_registry.py:42-48` | PASS | dict matches spec verbatim |
| 7 | ml-engines | §1.2 TOCTOU version-increment transaction | `model_registry.py:469-470` | PASS | `async with self._conn.transaction()` |
| 8 | ml-engines | §1.2 ONNX export non-fatal on failure | model_registry.py | PASS | `onnx_status` branches |
| 9 | ml-engines | §1.2 `register_model` saves pkl+onnx+metadata | model_registry.py | PASS | all three artifacts |
| 10 | ml-engines | §1.3 frameworks: sklearn, lightgbm, lightning | `training_pipeline.py:259-261` | PASS | if/elif present |
| 11 | ml-engines | §1.3 Lightning `trainer_` prefix splits kwargs | `training_pipeline.py:564-567` | PASS | prefix-strip correct |
| 12 | ml-engines | §1.3 Lightning path places tensors/model on accelerator device | `engines/training_pipeline.py:581-592` | **MISSING** | `X_tensor = torch.tensor(X_train, dtype=torch.float32)` at L581 — no `.to(device)`; `L.Trainer(**trainer_kwargs)` at L591 — no `accelerator="auto"` default. Confirmed by grep `.to(device\|\.cuda()\|accelerator=\"auto` in `training_pipeline.py` returning 0 hits. |
| 13 | ml-engines | §1.3 splitting strategies (4) | training_pipeline.py | PASS | all branches |
| 14 | ml-engines | §1.3 `calibrate()` uses `FrozenEstimator` | training_pipeline.py | PASS | grep present |
| 15 | ml-engines | §1.4 `InferenceServer(registry, *, cache_size=10)` LRU | `inference_server.py:127` | PASS | `_ModelCache` OrderedDict |
| 16 | ml-engines | §1.4 Lightning supported by InferenceServer | `inference_server.py:523` | **MISSING** | ternary hard-codes `"lightgbm" else "sklearn"`; no torch/lightning branch. Registered Lightning model is classified `sklearn` and `.predict()` fails. |
| 17 | ml-engines | §1.4 `register_endpoints` + `register_mcp_tools` | `inference_server.py:341,370` | PASS | both present |
| 18 | ml-engines | §1.4 ONNX float32 / native float64 | inference_server.py | PASS | both dtypes in predict |
| 19 | ml-engines | §1.5 DriftMonitor thresholds finite-validated | `drift_monitor.py:378` | PASS | `__init__` validates |
| 20 | ml-engines | §1.5 `_references` bounded to 100 | drift_monitor.py | PASS | bound present |
| 21 | ml-engines | §1.5 `schedule_monitoring` min 1s asyncio task | drift_monitor.py | PASS | present |
| 22 | ml-engines | §1.7 HPO strategies (4) incl. Optuna `SuccessiveHalvingPruner` | hyperparameter_search.py | PASS | all four |
| 23 | ml-engines | §1.8 AutoML classifier candidates | `automl_engine.py:315-350` | PASS | RF/GBC/LR present (plus XGB+LGBM — see row 24) |
| 24 | ml-engines | §1.8 candidate family COUNT matches spec | automl_engine.py | **PARTIAL** | spec lists 3+3, code has 5+5. Spec drift — update spec or remove extras. |
| 25 | ml-engines | §1.8 `LLMCostTracker` + `LLMBudgetExceededError` | `automl_engine.py:38,201` | PASS | both present |
| 26 | ml-engines | §1.8 Agent double opt-in (`[agents]` + `agent=True`) | `automl_engine.py:433` | PASS | `if agent:` branch |
| 27 | ml-engines | §1.9-1.13 P1 engines (5) | engines/*.py | PASS | all 5 classes present |
| 28 | ml-engines | §1.14-1.17 `@experimental` on 4 P2 engines | grep `@experimental` | **PARTIAL** | only 2/4: FeatureEngineer, ModelVisualizer decorated. DataExplorer (L259) and ModelExplainer (L67) have NO decorator — users get no `ExperimentalWarning`. |
| 29 | ml-integration | §1.1 No pandas in engines/ | grep pandas | PASS | 0 hits (only `interop.py`) |
| 30 | ml-integration | §1.1 `ALLOWED_MODEL_PREFIXES` | `_shared.py:48-59` | PASS | frozenset matches spec verbatim |
| 31 | ml-integration | §1.3 Lazy loading via `__getattr__` | `__init__.py:28` | **PARTIAL** | `__getattr__` works but `__init__.py:16` eagerly `from kailash_ml.engines.data_explorer import AlertConfig` — pulls plotly on every `import kailash_ml`, violating "only types.py + _version.py eager." |
| 32 | ml-integration | §2.1 MLToolProtocol on InferenceServer | types.py + inference_server.py | PASS | 3 methods async |
| 33 | ml-integration | §2.2 AgentInfusionProtocol | types.py | PASS | protocol + 2 consumer call sites |
| 34 | ml-integration | §3.2 OnnxBridge `export()` for sklearn, lightgbm | `onnx_bridge.py:325,334` | PASS | both implemented |
| 35 | ml-integration | §3.3 matrix advertises xgboost=guaranteed, pytorch=best_effort | `onnx_bridge.py:100,107` | **PARTIAL** | matrix entries exist but `export()` at L215-225 has NO xgboost/pytorch branch — falls through to `"Export not implemented for framework: {framework}"` → deterministic `onnx_status="skipped"`. The matrix lies. |
| 36 | ml-integration | §4 MLflow v1 read/write | `compat/mlflow_format.py:49,194` | PASS | both classes present |
| 37 | ml-integration | §5.2 6 Kaizen agents | agents/*.py | PASS | all 6 files + classes |
| 38 | ml-integration | §5.4 `AgentGuardrailMixin` 5 mandatory guardrails | `_guardrails.py:214` | **MISSING (orphan)** | class defined (214 LOC); grep across `engines/` returns only self-ref + `__all__`. NO engine inherits. AutoMLEngine reimplements 2/5 inline. Orphan per `rules/orphan-detection.md` — wire or delete. |
| 39 | ml-integration | §7.2 12 built-in metrics registered | `metrics/_registry.py:348+` | PASS | all 12 `register_metric` calls present |
| 40 | ml-integration | §8.4 `kailash-ml-dashboard` CLI | `pyproject.toml:102` | PASS | entry point present |
| 41 | ml-integration | §10 `kailash-ml-gpu-setup` CLI | `pyproject.toml:101`, `_gpu_setup.py` | **PARTIAL** | CLI exists, detects CUDA, but `_gpu_setup.py:164` prints `pip install 'kailash-ml[full-gpu]'`; extra is `all-gpu` (pyproject.toml:91). Advertised command errors. |
| 42 | ml-integration | §12.1 `validate_model_class` at every importlib site | `_shared.py:61` + ≥3 call sites | PASS | ModelSpec, Ensemble.stack, _train_lightning |

**Audit A totals: 33 PASS / 6 PARTIAL / 3 MISSING out of 42.**

---

## 3. Audit B: Compute Backend Coverage Matrix

Grep protocol (verbatim): `/usr/bin/grep -rnE --include="*.py" "<pattern>" packages/kailash-ml/src/kailash_ml/`

| Backend | Detection | Tensor placement | Model placement | Training loop | Inference | Data loader | Fallback WARN |
|---|---|---|---|---|---|---|---|
| **CPU** | PASS (default; `_select_xgboost_device()` returns `"cpu"` when no CUDA) | PASS (all engines default) | PASS | PASS | PASS (all sklearn/lightgbm/onnx paths) | PASS (numpy) | N/A-by-design |
| **CUDA** (NVIDIA) | PARTIAL: `_cuda_available()` at `automl_engine.py:260` (torch probe + nvidia-smi fallback); `detect_cuda_version()` at `_gpu_setup.py:28` | MISSING: Lightning path `training_pipeline.py:581-583` creates tensors on CPU with no `.to("cuda")`; no device param anywhere | MISSING: `L.Trainer(**trainer_kwargs)` at L591 has no `accelerator="gpu"` default | PARTIAL: only XGBoost candidate receives `device="cuda"` (automl_engine.py:340); sklearn, LightGBM, Lightning all CPU | MISSING: `InferenceServer._load` does not route to GPU for torch/Lightning models (also, torch models aren't supported by InferenceServer at all — see Audit A row 16) | MISSING: `DataLoader(dataset, ...)` at L584 has no pin_memory / no device transfer | MISSING (no WARN when CUDA device not used despite availability) |
| **MPS** (Apple Silicon Metal) | MISSING: `grep "torch.backends.mps\|mps.is_available\|device=\"mps\"\|MPS"` returns **0 hits** in `src/` | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING (silent CPU on Apple Silicon) |
| **ROCm** (AMD HIP) | MISSING: `grep "rocm\|ROCm\|HIP\|hip_"` returns **0 hits** | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING |
| **TPU** (XLA/torch_xla) | MISSING: `grep "torch_xla\|xla_device\|TPU"` returns **0 hits** | MISSING | MISSING | MISSING (no `accelerator="tpu"` path) | MISSING | MISSING | MISSING |
| **XPU** (Intel GPU / oneAPI) | MISSING: `grep "torch.xpu\|intel_extension\|XPU"` returns **0 hits** | MISSING | MISSING | MISSING | MISSING | MISSING | MISSING |

**Non-torch families:**
- **XGBoost**: PASS (CUDA only). `automl_engine.py:300` passes `device="cuda"` when GPU is detected; XGBoost 2.0+ handles the rest. No MPS/XPU story (also not supported upstream).
- **LightGBM**: PARTIAL. No `device_type="gpu"` configured anywhere (`grep device_type` returns 0). LightGBM CPU-only by default in this codebase even though upstream supports `device_type="gpu"`.
- **sklearn**: N/A-by-design. CPU-only upstream.
- **CatBoost**: MISSING. Listed in `ALLOWED_MODEL_PREFIXES` and as an extra, but no candidate in AutoML, no `task_type="GPU"` routing, no test coverage.

**Backend test coverage:** `grep` for `mps|MPS|cuda|xpu|tpu|rocm|Lightning` across `tests/` (excluding `__pycache__`) — the only real hit is `tests/unit/test_gpu_setup.py` (tests the CUDA CLI). **Zero tests exercise `_train_lightning` / `_predict_lightning`** (`grep "_train_lightning\|_predict_lightning" tests/` returns empty).

**Net:** out of 6 backends × 7 dimensions (42 cells), 7 PASS / 2 PARTIAL / 29 MISSING / 4 N/A-by-design. The framework supports one backend (CPU) plus a narrow XGBoost CUDA path.

---

## 4. Critical Gaps (Top 10, ranked)

1. **Lightning training path has no device routing.** `training_pipeline.py:581-591` creates `torch.tensor(..., dtype=torch.float32)` on CPU and calls `L.Trainer(**trainer_kwargs)` with no `accelerator` default. A user on an 8×H100 rig trains on CPU with no warning. **User hits this:** first Lightning training run. **Fixed looks like:** accept `device` or `accelerator` in `EvalSpec`/`ModelSpec` with `auto` default that picks `cuda`/`mps`/`xpu`/`tpu`/`cpu` in priority; move tensors via `.to(device)`; pin_memory on DataLoader when GPU; emit `INFO` log `lightning.device_selected` with chosen device. This single fix unblocks CUDA/MPS/ROCm/XPU/TPU simultaneously because Lightning's `Trainer` already has the abstraction; we just never used it.
2. **ONNX export silently "skipped" for xgboost despite spec "guaranteed".** `bridge/onnx_bridge.py:215-225` has branches for `sklearn`, `lightgbm`, else falls through to "Export not implemented for framework: {framework}". Spec §3.3 advertises xgboost=`guaranteed`. **User hits this:** any user training XGBoost models — the auto-generated `.onnx` artifact is missing and `InferenceServer` silently uses native path. **Fixed looks like:** implement `_export_xgboost` via `onnxmltools.convert_xgboost` (already a base dep after 0.9.1), add `pytorch` best-effort via `torch.onnx.export`, add regression test asserting export produces non-zero bytes for each framework.
3. **`_gpu_setup.py` prints a non-existent pip extra name.** Line 164: `pip install 'kailash-ml[full-gpu]'`. Extra in pyproject.toml is `all-gpu`. **User hits this:** every first-time CUDA user running the documented CLI. **Fixed:** one-line change `full-gpu` → `all-gpu`, add a `pip install .[all-gpu]` smoke test.
4. **InferenceServer classifies any non-lightgbm model as `sklearn` and calls `.predict()`.** `inference_server.py:523`. A Lightning module (no `.predict()` method) registered via TrainingPipeline becomes unserviceable through `predict()`. **User hits this:** any DL training + inference flow. **Fixed:** detect by `module_name.startswith("lightning") or isinstance(model, torch.nn.Module)`; route to a `_predict_lightning` path that mirrors `training_pipeline._predict_lightning`.
5. **`AgentGuardrailMixin` is an orphan.** `engines/_guardrails.py:214`, 214 LOC, zero inheritors. Per `rules/orphan-detection.md`: either wire or delete. **Fixed:** `class AutoMLEngine(AgentGuardrailMixin)` + call mixin methods from the agent-opt-in branches; or delete and document the 5 guardrails where they actually live (AutoMLEngine has baseline + budget + audit inline; confidence + approval are unwritten).
6. **Two P2 engines missing `@experimental`.** `DataExplorer` (`data_explorer.py:259`) and `ModelExplainer` (`model_explainer.py:67`) have no decorator. Spec §1.14/§1.17 and §11.2 say P2 engines MUST emit `ExperimentalWarning` on first instantiation. **Fixed:** add `@experimental` above both class definitions + regression test that instantiating each emits `ExperimentalWarning` once per interpreter.
7. **LightGBM GPU path not reachable.** `automl_engine.py` constructs `LGBMClassifier` with no `device_type` or `gpu_use_dp` kwargs. LightGBM ships with GPU support when built with OpenCL, but kailash-ml never asks for it. **Fixed:** accept `lgb_device` in `AutoMLConfig` or probe and pass `device_type="gpu"` when `_cuda_available()` is True; document that users must `pip install lightgbm --config-settings=cmake.define.USE_GPU=1` for full support.
8. **Lazy-load invariant broken.** `__init__.py:16` eagerly imports `AlertConfig` (from `data_explorer.py` which pulls plotly). Spec §1.3 says `import kailash_ml` "is always fast (loads only `types.py` and `_version.py` eagerly)." **Fixed:** move `AlertConfig` into the `_engine_map` dict so it lazy-loads on attribute access; or re-export from `types.py` if it's lightweight enough.
9. **AutoML default candidate families drifted from spec.** Spec §1.8 lists 3 classifiers + 3 regressors; code has 5 + 5 (adds XGBoost + LightGBM). **Disposition:** update `specs/ml-engines.md` §1.8 OR remove extras. Either direction, but the current divergence is a spec-authority violation (`rules/specs-authority.md` MUST Rule 5/6).
10. **Zero tests exercise Lightning / any GPU backend.** `grep "_train_lightning\|_predict_lightning" tests/` returns empty. The "PyTorch Lightning framework supported" claim has no integration test. Per `rules/testing.md` "Verify NEW modules have NEW tests": HIGH. **Fixed:** Tier 2 test that trains a tiny `BoringModel` through `TrainingPipeline`, asserts the run succeeds, the model is registered, and (if a GPU is present) device placement was honored — parametrize over `["cpu", "cuda", "mps"]` with `skipif` on unavailable devices.

---

## 5. Spec Deltas — Encoding the Vision

The user's vision (Lightning core / multi-backend / unified ML-DL-RL / PyCaret+MLflow-better / enterprise) implies these MUST clauses that current specs do NOT carry. Keep `ml-engines.md` under 300 LOC; split into new `ml-backends.md` sub-spec per `specs-authority.md` MUST Rule 8.

- **§ Backend Matrix (NEW).** Framework MUST support `cpu`, `cuda`, `mps`, `rocm`, `xpu`, `tpu` as first-class targets. Single `backend.py` module exposes `detect_backend() -> Literal[...]` with priority: `CUDA_VISIBLE_DEVICES` → `torch.cuda` → `torch.backends.mps` → `torch_xla.xla_device` → `torch.xpu` → `torch.version.hip` → `"cpu"`. Every GPU-capable engine (TrainingPipeline, InferenceServer, RLTrainer) MUST accept `device: str | None = None` (None = auto). Selected device MUST be logged at INFO.
- **§ Lightning Unified DL/RL Core (NEW).** All DL engines MUST compose on `lightning.pytorch.Trainer`. `accelerator="auto"` + `devices="auto"` is the single source of backend selection. Custom training loops are BLOCKED for new engines. This gives MPS/TPU/XPU/ROCm support for free.
- **§ Unified TrainingResult (NEW).** MUST carry `device_used`, `accelerator`, `precision: Literal["fp32","fp16","bf16"]`. PyCaret/MLflow users expect these fields.
- **§ ONNX Export Contract (TIGHTEN §3).** `OnnxBridge.export()` MUST implement every framework in its compatibility matrix, or remove that framework. "Export not implemented" IS a stub (zero-tolerance Rule 2) when the framework appears in the matrix. Regression tests enumerate `matrix.keys()` and assert non-zero bytes each.
- **§ Agent Mixin Contract (TIGHTEN §5.4).** Every AgentInfusionProtocol consumer MUST inherit `AgentGuardrailMixin`. Mechanically verified: `grep "class.*AgentGuardrailMixin" engines/` count == consumer count.
- **§ Multi-Tenancy (NEW, cross-cut).** FeatureStore, ModelRegistry, ExperimentTracker, DriftMonitor currently have NO `tenant_id` dimension. If the vision is enterprise-grade, every persisted row + cache key MUST include `tenant_id`, every invalidate entry point MUST accept optional `tenant_id` per `tenant-isolation.md`. Structural change, must land pre-1.0.
- **§ PyCaret/MLflow-Better Claims (NEW).** Spec MUST enumerate concrete deltas: (a) adapter-based serving PyCaret lacks, (b) polars-native MLflow lacks, (c) ONNX-by-default neither has, (d) unified ML+DL+RL neither has. Each becomes a MUST clause with test coverage.

---

## 6. Cross-SDK Note

Per EATP D6 (`cross-sdk-inspection.md`): semantics match, implementation differs.

**Shared spec (both SDKs implement — belongs in spec deltas):**
- Backend matrix + `detect_backend()` priority (gap 1)
- ONNX matrix ↔ implementation parity (gap 2)
- `AgentGuardrailMixin` / `AgentGuardrailTrait` contract (gap 5)
- VALID_TRANSITIONS stage machine (row 6) — language-neutral
- Multi-tenancy `tenant_id` dimension (§5 delta)
- InferenceServer framework classification (gap 4) — both SDKs hit this

**Python-only implementation gaps:**
- `_gpu_setup.py` extra-name typo `full-gpu` → `all-gpu` (gap 3)
- Eager `AlertConfig` import in `__init__.py` (gap 8) — `__getattr__` Python idiom
- `@experimental` application on P2 engines (gap 6) — Python decorator; Rust equivalent is `#[experimental]` attribute

**Next step:** after landing §5 deltas, run the same two audits against `kailash-rs/crates/kailash-ml` (if it exists). Backend matrix will be most revealing — Rust's ML story typically has worse MPS/TPU coverage than Python since `tch-rs` is the primary bridge.

---

## 7. Verification Commands (Re-runnable)

From `packages/kailash-ml/`:

```bash
grep -rnE --include="*.py" "torch\.cuda|cuda\.is_available" src/kailash_ml/        # 4 (partial CUDA)
grep -rnE --include="*.py" "torch\.backends\.mps|device=\"mps\"" src/kailash_ml/   # 0
grep -rnE --include="*.py" "torch_xla|xla_device|TPU" src/kailash_ml/              # 0
grep -rnE --include="*.py" "torch\.xpu|intel_extension|XPU" src/kailash_ml/        # 0
grep -rnE --include="*.py" "rocm|ROCm|HIP|hip_" src/kailash_ml/                    # 0
grep -rn "AgentGuardrailMixin" src/kailash_ml/engines/                              # orphan
grep -rn "@experimental" src/kailash_ml/engines/                                    # expect 4, actual 2
grep -n "full-gpu\|all-gpu" pyproject.toml src/kailash_ml/_gpu_setup.py             # extra-name mismatch
grep -n "def _export_" src/kailash_ml/bridge/onnx_bridge.py                         # only sklearn + lightgbm
grep -n "\.to(device\|\.cuda()\|accelerator=" src/kailash_ml/engines/training_pipeline.py  # 0
grep -rln "_train_lightning\|_predict_lightning" tests/                              # 0
```
