# kailash-ml Redesign Proposal — Synthesis of 5-Agent Audit

**Status:** pending human decision
**Inputs synthesized:** 5 parallel audit agents (analyst, ml-specialist, uiux-designer, reviewer, spec-compliance redteam). Source reports were written to agent worktrees and cleaned up when the agents completed; findings captured in the session transcript at the moment each agent reported back. Where this document cites numeric evidence, it is from that transcript.

---

## 1. Executive summary

The user's verdict — "kailash-ml is a toy rather than enterprise-ready, haphazardly put together, no engine workflow, devs hunt for API and work with primitives, extremely disjointed" — is independently corroborated by all 5 agents on grounded evidence. The package works on the happy path and fails on every axis of the stated vision.

**The single most important finding:**

`packages/kailash-dataflow/tests/unit/` — wait, wrong package. Re-state:

> `packages/kailash-ml/src/kailash_ml/engines/training_pipeline.py:581-591` — the Lightning training path creates CPU tensors and instantiates `L.Trainer()` with **no `accelerator` argument**. Apple Silicon, H100, TPU, AMD, and Intel GPU users all silently run on CPU. **This single bug blocks 5 of 6 backends simultaneously.**

Everything else — Lightning as spine, GPU-first, unified ML/DL/RL, PyCaret-better, MLflow-better — collapses onto that line and the missing single-point Engine that would have routed through it.

Recommended direction: **ADR Option C — Hybrid: replace the core, keep the edges.** Build a new `kailash_ml.Engine` as the single entry point. Reframe the current 18 classes as Primitives per the four-layer hierarchy (`rules/framework-first.md`). Wire Lightning as the default `Trainer` with `accelerator="auto"`. Collapse `[dl]/[dl-gpu]` extras into base. Unify RL + LLM-fine-tune under the same Engine surface. Existing consumers (aegis / aether / kz-engage) keep their direct primitive imports through 1.x; 2.0 demotes those to a power-user namespace.

---

## 2. Vision (North Star — locked)

1. **Lightning core** — PyTorch Lightning is the training spine, not a bolt-on branch.
2. **GPU-first out of the box** — `pip install kailash-ml` + any supported accelerator = GPU. Zero extra config. `torch`-style transparency.
3. **Single-point Engine** — one coherent `Engine` entry point; primitives remain accessible for power users but are not the default surface.
4. **Unified ML / DL / RL** — classical sklearn-level models, deep learning, and reinforcement learning all flow through the same Engine contract.
5. **PyCaret-better DX** — AutoML-style workflows that are easier than PyCaret (`setup()` / `compare_models()` / `finalize_model()` / `predict()`).
6. **MLflow-better tracking** — experiment tracking, model registry, artifact management that beat MLflow on ergonomics and features.
7. **Enterprise-ready** — observable, auditable, reliable, multi-tenant, no landmines.

Supported compute backends (first-class): **CPU, CUDA, MPS, ROCm, TPU, XPU**.

---

## 3. Verified current state

### 3.1 Structure (reviewer + ml-specialist audit)

- **18 engine classes**, not 13 (the skill `.claude/skills/34-kailash-ml/SKILL.md:28` is stale).
- **Zero common base class** across the 18; three different initialization protocols coexist (`await x.initialize()`, `await X.create(url)`, zero-init).
- **Six-constructor ceremony** required to train one model today: `FeatureStore`, `ModelRegistry`, `TrainingPipeline`, `ExperimentTracker`, `ConnectionManager`, `ArtifactStore`.
- **Public-surface ratio ≈ 20%** (27 `__init__` exports / ~137 public symbols). Result dataclasses and typed errors are in the 80% requiring source-reading to find.
- **RL is an orphan** — `rl/trainer.py` does not touch `ModelRegistry`, `ExperimentTracker`, or `TrainingPipeline`. `rl/` and `agents/` subpackages exist (~1.3K LOC combined) but are **not exposed via top-level `__init__.py`** — exactly the "devs hunt" shape the user described.
- **14 top-level facade orphans** (classes with zero in-package production call sites — they run only if a user imports them directly).
- **1 dead internal module**: `engines/_guardrails.py` (414 LOC, zero importers anywhere).
- **`AgentGuardrailMixin`** (214 LOC, 0 inheritors in production code) — classic orphan pattern.

### 3.2 Docstring lies (reviewer + spec-compliance)

- `AutoMLEngine` docstring promises orchestration of `TrainingPipeline + ModelRegistry + ExperimentTracker + HyperparameterSearch`. **Only `HyperparameterSearch` is actually imported**. The composition the engine advertises is a fiction.
- ONNX `export()` advertises `xgboost=guaranteed` in its compatibility matrix but has no xgboost branch — falls through to `"Export not implemented for framework: xgboost"` and returns `onnx_status="skipped"`. Spec §3.3 is a lie against the code.
- `_gpu_setup.py:164` tells users `pip install 'kailash-ml[full-gpu]'`. The extra is named `all-gpu` in `pyproject.toml:91`. Every first-time GPU user hits `ERROR: Package 'kailash-ml' does not provide the extra 'full-gpu'`.

### 3.3 Competitive parity (ml-specialist audit)

| Capability                                                  | PyCaret | Kailash-ml current |
| ----------------------------------------------------------- | ------- | ------------------ |
| Primitives (features, training, eval, HP search, ensembles) | ~Equal  | **~80%**           |
| DX (`setup/compare/fit/predict` one-liners)                 | Has     | **~0%**            |

| Capability          | MLflow | Kailash-ml current |
| ------------------- | ------ | ------------------ |
| Tracking + registry | Has    | **~65%**           |
| Projects            | Has    | **~0%**            |
| Evaluate            | Has    | **~0%**            |
| Lineage             | Has    | **~0%**            |

### 3.4 "Lightning core" is aspirational

- `import lightning` appears in **1 source site** (one branch of `training_pipeline.py`).
- `import sklearn` / `from sklearn` appears in **53 sites**.
- The claim "PyTorch Lightning core" is currently a marketing statement, not an architectural fact.

### 3.5 Backend coverage (spec-compliance redteam)

| Backend             | Support    | Evidence                                                                                          |
| ------------------- | ---------- | ------------------------------------------------------------------------------------------------- |
| CPU                 | ✅ Full    | default everywhere                                                                                |
| CUDA                | 🟡 Partial | XGBoost path only (`automl_engine.py:292-307`); not Lightning, LightGBM, sklearn, InferenceServer |
| MPS (Apple Silicon) | ❌ Zero    | no references in source                                                                           |
| ROCm (AMD)          | ❌ Zero    | no references in source                                                                           |
| TPU (Google XLA)    | ❌ Zero    | no references in source                                                                           |
| XPU (Intel)         | ❌ Zero    | no references in source                                                                           |

42 load-bearing spec clauses checked: **33 PASS, 6 PARTIAL, 3 MISSING**.

### 3.6 DX pain points (uiux-designer)

- Every one of the user's 8 reported pain points traces to a structural cause (not a test flake):
  1. Schema content-hash — versioning strategy needs versioning ceremony, but no helper exists for the common "I tweaked one field" workflow.
  2. `schema=None` → `AttributeError: None.features` deep in `_compute_baseline_recommendation` — missing typed guard at public-API boundary.
  3. DB file path fragility — registry/tracker require file-backed SQLite; relative paths break on CWD change; no `file:memdb` acceptance.
  4. No graceful degradation — candidate families accepted without probing installed packages; fail mid-run.
  5. GPU not default — see §3.5.
  6. No package availability checks — see #4.
  7. `_detect_target()` silent breakage — including the target column in the feature list silently passes construction and fails at engine.run.
  8. `ExperimentTracker` can't use `:memory:` — architectural, blocks notebook workflows.
- Error messages: ~30-40% of `raise` sites use generic messages (`ValueError("invalid")`) without naming the offending input or the correct form.
- `README.md` version says `0.7.0`; `pyproject.toml` says `0.9.0`; SKILL.md references a non-existent `[full]` extra; README and SKILL.md disagree on `LocalFileArtifactStore` import path.
- No `examples/` directory.

---

## 4. The single bug that cascades

`packages/kailash-ml/src/kailash_ml/engines/training_pipeline.py:581-591` (Lightning branch):

```python
# Current (roughly — paraphrased from spec-compliance findings)
def _train_lightning(self, model_cls, data, ...):
    dataset = self._build_tensor_dataset(data)          # CPU tensors
    loader = DataLoader(dataset, ...)
    module = model_cls(...)
    trainer = L.Trainer(max_epochs=..., callbacks=[...])  # <- no accelerator=
    trainer.fit(module, loader)
```

What it should be:

```python
def _train_lightning(self, model_cls, data, ..., accelerator="auto", devices="auto", precision="auto"):
    dataset = self._build_tensor_dataset(data)
    loader = DataLoader(dataset, ...)
    module = model_cls(...)
    trainer = L.Trainer(
        max_epochs=...,
        accelerator=accelerator,      # "auto" resolves cuda/mps/cpu; explicit "tpu"/"ipu"/"hpu" accepted
        devices=devices,
        precision=precision,          # "auto" resolves bf16 on CUDA A100+/H100, fp16 on MPS, fp32 elsewhere
        callbacks=[...],
    )
    trainer.fit(module, loader)
```

One line fixes 5 of 6 backends. But it MUST land together with:

1. A single-point `Engine` that actually routes every training call through this path (currently a three-branch dispatch lives at `training_pipeline.py:486/501/525`).
2. A `Trainable` protocol so sklearn / LGBM / XGBoost also route through the Lightning `Trainer` as wrapped `LightningModule`s.
3. A centralized `_device.py` that every engine consults (today LightGBM/Lightning/InferenceServer/direct-train XGBoost each have their own partial device story, or none).

Without the Engine + Trainable + \_device work, fixing the one line still leaves sklearn/LGBM ignoring GPU and users still wiring 6 constructors.

---

## 5. The new public API (proposed)

All 3 agents that proposed APIs converged on the same shape:

### 5.1 Three-line hello world

```python
import kailash_ml as km
best = km.train(df, target="churned")
print(best.metrics)   # {"accuracy": 0.92, "f1": 0.87, "model": "lightgbm", "device": "cuda:0"}
```

Behind the scenes: `km.train()` opens a default SQLite store at `~/.kailash_ml/ml.db`, infers schema from DataFrame dtypes, auto-detects task type (classification vs regression vs clustering), runs a `compare_models`-style sweep across a small default family set (`logreg`, `random_forest`, `lightgbm`, `xgboost`, `lightning_mlp`), returns a `TrainingResult` whose `.metrics` is a dict carrying `device_used`, `accelerator`, `precision`.

### 5.2 Five-line "explicit production"

```python
engine = km.Engine(store="postgresql://...", accelerator="auto", tenant_id="acme")
engine.setup(df, target="revenue", ignore=["customer_id"])
leaderboard = engine.compare(families=["xgboost", "lightgbm", "lightning_mlp"], n_trials=30)
model = engine.finalize(leaderboard.top())
endpoint = engine.serve(model, channels=["rest", "mcp"])
```

### 5.3 Thirty-line "advanced"

```python
async with km.track(experiment="cart-abandonment-v3") as tracker:
    engine = km.Engine(
        store="postgresql://…",
        accelerator="auto",                      # auto → cuda/mps/rocm/xpu/tpu/cpu
        precision="auto",                        # auto → bf16/fp16/fp32
        tenant_id="acme",
        tracker=tracker,
    )
    engine.setup(
        df, target="abandoned", ignore=["session_id"],
        feature_store=km.FeatureStore(name="cart_v3"),
    )
    leaderboard = await engine.compare(
        families=["lightning_transformer", "lightgbm", "torchrl_ppo"],
        n_trials=100,
        hp_search="optuna",
        early_stopping=km.Patience(10),
    )
    champion = await engine.ensemble(leaderboard.top_k(5))
    await engine.register(champion, alias="production", version="auto")
    endpoint = await engine.serve(champion, channels=["rest", "mcp"], autoscale=True)
```

The contract: **every non-trivial argument has a sensible default.** The three-line version does all the above implicitly.

### 5.4 Consolidated engine count (from reviewer)

From 18 → 5 user-facing engines + 1 RL sibling + 1 peer:

- `Engine` — single entry point (NEW)
- `FeatureStore` — retained, schema-versioned primitive
- `ModelRegistry` — retained
- `ExperimentTracker` — retained, async-context-managed
- `InferenceServer` — retained, GPU-aware
- `rl.Engine` — sibling (under `kailash_ml.rl`)
- `DriftMonitor` — peer

Merge 5 sklearn-wrapper engines (`ClusteringEngine`, `AnomalyDetectionEngine`, `DimReductionEngine`, `EnsembleEngine`, `PreprocessingPipeline`) into one `TransformEngine` with a `strategy=` discriminator — saves ~3000 LOC of parallel ceremony.

Delete dead modules: `engines/_guardrails.py`, `ModelVisualizer` if keepers cannot justify its 745-LOC plotly surface.

Expose or delete hidden subpackages: `agents/`, `rl/`.

---

## 6. Spec updates required

The user's vision is not in `specs/ml-engines.md` today. Seven new/tightened clauses:

### 6.1 NEW § Backend Matrix

> `kailash_ml.Engine` MUST support `accelerator="auto"` and resolve it in this priority: **cuda → mps → rocm → xpu → tpu → cpu**. Explicit overrides MUST be accepted and MUST fail fast with a typed error if unavailable. A public `km.detect_backend()` function MUST return the resolved backend and expose the decision path for logging.

### 6.2 NEW § Lightning Unified DL/RL Core

> Every engine that trains a model MUST route its training call through `lightning.pytorch.Trainer`. Non-torch families (sklearn, xgboost, lightgbm, catboost) MUST be wrapped as `LightningModule` adapters at the Engine boundary. Custom training loops in engine code are **BLOCKED** — if Lightning cannot express a need, the gap is a Lightning upstream issue, not a grounds to bypass it. RL training MUST compose on Lightning with `stable-baselines3` or `torchrl` as the inner policy.

### 6.3 NEW § Unified TrainingResult

> Every engine's train path MUST return a `TrainingResult` dataclass carrying (minimum): `model_uri`, `metrics`, `device_used`, `accelerator`, `precision`, `elapsed_seconds`, `tracker_run_id`, `tenant_id`. Any engine returning a dict or a raw model object fails this clause.

### 6.4 TIGHTEN § ONNX Export Contract

> The ONNX compatibility matrix keys (`sklearn`, `xgboost`, `lightgbm`, `torch`, `lightning`) MUST each have an implemented branch. A regression test per key asserting round-trip (train → export → load → predict) MUST exist. Matrix claims without branches are **BLOCKED**.

### 6.5 TIGHTEN § Agent Mixin Contract

> Every `AgentInfusionProtocol` consumer MUST inherit `AgentGuardrailMixin`. CI MUST grep the hierarchy and fail if a consumer class skips the mixin. (This closes the 214-LOC orphan.)

### 6.6 NEW § Multi-Tenancy

> Pre-1.0, `FeatureStore` / `ModelRegistry` / `ExperimentTracker` / `DriftMonitor` MUST all accept `tenant_id` as a construction or per-call parameter, propagate it into storage keys, and honor it in invalidation. Cache key shape: `kailash_ml:v1:{tenant_id}:{resource}:{id}`. See `rules/tenant-isolation.md`.

### 6.7 NEW § PyCaret/MLflow-Better Claims

Enumerate the concrete deltas as MUST clauses with tests:

- Adapter serving (REST + MCP from one `engine.serve()` call) — MLflow has no MCP channel
- Polars-native feature pipelines — MLflow is pandas-first
- ONNX-default model artifacts — MLflow is pickle-first
- Unified ML + DL + RL surface — PyCaret has no DL, MLflow has no unified train surface
- Schema-evolution helpers (`feature_store.evolve(add=[...])`) — no PyCaret equivalent

---

## 7. Migration plan

Consumers today (in-repo, verified by reviewer):

- `workspaces/aegis/` — imports `AutoMLEngine`, `FeatureStore`, `ModelRegistry` directly
- `workspaces/aether/` — imports `TrainingPipeline`, `ExperimentTracker`
- `workspaces/kz-engage/` — imports `FeatureStore`, `ModelRegistry`, `InferenceServer`

  1.x line (current major series):

- All existing classes remain importable at current paths
- Add `kailash_ml.Engine` as the new default
- Add `km.train()` / `km.track()` convenience
- Mark the 13 internal legacy classes `@experimental` with a decorator (not deprecation — just discoverability)
- Land the Lightning `accelerator="auto"` fix and the unified `TrainingResult`
- Fix the 3 docstring lies (AutoMLEngine composition, ONNX matrix, `[full-gpu]` → `[all-gpu]`)

  2.0 breaking release:

- Demote primitive imports to `kailash_ml.primitives.*`
- Top-level `kailash_ml` exports only `Engine`, `FeatureStore`, `ModelRegistry`, `ExperimentTracker`, `InferenceServer`, `DriftMonitor`, `train`, `track`, `detect_backend`
- Merge sklearn wrappers into `TransformEngine`
- Delete `engines/_guardrails.py`
- Delete or expose `agents/` + `rl/` at top level

---

## 8. Kailash-rs spec-alignment delta

The user queued kailash-rs alignment after this audit. Per `rules/cross-sdk-inspection.md` (EATP D6: independent implementation, matching semantics), the Rust SDK inherits the SPEC updates in §6, not the implementation.

Rust-specific translation:

- § Backend Matrix → Rust uses `candle` / `tch` / `burn`. Priority order matches: CUDA → Metal → ROCm → Vulkan (XPU equivalent) → CPU. TPU via `torch_xla` is Python-only; document as N/A-Rust.
- § Lightning Unified DL/RL Core → Rust has no Lightning. Analog: `burn::Trainer` or `tch::train::Trainer`. The clause in Rust becomes "all DL/RL training goes through one trait-based `Trainer`; custom loops BLOCKED."
- § Unified TrainingResult → Straight port; the struct is cross-SDK.
- § ONNX Export Contract → `tract-onnx` or `ort` as the export path. Matrix-keys-must-equal-branches rule applies unchanged.
- § Multi-Tenancy → `tenant_id: Option<String>` on every store constructor. Same cache-key shape.
- § PyCaret/MLflow-Better Claims → Rust claims are smaller (no PyCaret-DX ambition for a Rust library). Scope to "MLflow-better tracking registry semantics from Rust."

Concrete deliverable: `specs/ml-engines.md` becomes the shared contract; `specs/ml-engines-python.md` + `specs/ml-engines-rust.md` carry only the language-specific primitives (Lightning-vs-burn, torch-vs-tch). Or keep one spec with "Python implementation" / "Rust implementation" subsections per clause. Final shape is a loom/ classification decision (Global vs variant per `rules/artifact-flow.md`).

---

## 9. Execution plan

### Phase A — pre-release hygiene (lands this session or the next)

Already in flight or complete:

- [x] Guard `schema=None` at Engine entry (ml-specialist tactical)
- [x] Validate target-not-in-features at AutoMLConfig construction (ml-specialist tactical)
- [x] XGBoost + LightGBM moved to base deps (ml-specialist tactical)
- [x] Runtime GPU auto-detect helper for XGBoost (ml-specialist tactical)

Needs to land before any further redesign work:

- [ ] Fix the one-line `L.Trainer(accelerator="auto")` at `training_pipeline.py:581-591`
- [ ] Fix the `[full-gpu]` typo in `_gpu_setup.py:164`
- [ ] Fix the README/pyproject version drift (`0.7.0` → `0.9.0`)
- [ ] Fix AutoMLEngine docstring to match actual imports (or make imports match docstring)

### Phase B — single-point Engine

- [ ] Create `kailash_ml.Engine` as a thin facade wrapping the 6 constructors
- [ ] `km.train(df, target=...)` convenience that constructs a default Engine
- [ ] Unified `TrainingResult` dataclass with `device_used` / `accelerator` / `precision`

### Phase C — Lightning as spine

- [ ] `Trainable` protocol
- [ ] LightningModule adapters for sklearn / xgboost / lightgbm
- [ ] Centralized `_device.py` — every engine consults one resolver
- [ ] Backend matrix tests: CPU green always; CUDA/MPS gated by GPU detection; ROCm/XPU/TPU marked `pytest.mark.gpu-<backend>` and skipped without the hardware

### Phase D — DX and doc parity

- [ ] `km.doctor()` diagnostic command
- [ ] `examples/` directory with 6 runnable scripts (`01_quickstart.py` → `06_pycaret_migration.py`)
- [ ] README rewrite: first-trained-model in under 10 lines
- [ ] Error-message audit pass — every `raise` cites the offending input and the correct form

### Phase E — MLflow+PyCaret-better features

- [ ] `engine.serve()` → REST + MCP in one call (MLflow-better: MCP channel)
- [ ] Polars-native feature pipelines (PyCaret is pandas-first)
- [ ] ONNX-default model artifacts (MLflow default is pickle)
- [ ] Unified RL surface (`km.rl.Engine`)
- [ ] Feature-store evolution helpers

### Phase F — 2.0 demotion + consolidation

- [ ] Move 13 primitives to `kailash_ml.primitives.*`
- [ ] Merge 5 sklearn wrappers into `TransformEngine`
- [ ] Delete `engines/_guardrails.py` + `ModelVisualizer` (unless a champion surfaces)
- [ ] Expose or delete `agents/` + `rl/` at top level
- [ ] Tag `kailash-ml 2.0.0`

Estimated shard count (per `rules/autonomous-execution.md` Per-Session Capacity Budget): Phase A is 1 shard; Phase B is 1-2; Phase C is 3-4 (Trainable protocol, adapters, \_device, backend tests); Phase D is 2; Phase E is 4-5; Phase F is 3. **Total: ~15-17 autonomous execution cycles.**

---

## 10. Decisions needed from human

1. **ADR Option**: approve Option C (hybrid — recommended) or choose A (rebuild-from-scratch) or B (incremental-refactor-only)?
2. **1.x/2.0 split**: acceptable to demote primitives in 2.0 breaking, or must 2.0 stay source-compatible?
3. **Default backend priority**: confirm `cuda → mps → rocm → xpu → tpu → cpu` or reorder (e.g. some shops prefer TPU-first)?
4. **Lightning hard lock-in**: accept "custom training loops BLOCKED" as a spec clause, or leave escape hatch for research users?
5. **Release impact**: `kailash-ml` stays out of this session's release; Phase A lands as `0.9.1` patch; Phase B-D as `0.10.0` minor; Phase E-F as `2.0.0` major. Confirm?
6. **Kailash-rs**: draft `specs/ml-engines-python.md` + `specs/ml-engines-rust.md` split, or keep one shared spec with Python/Rust subsections?

---

## 11. Files to update when decisions land

- `specs/ml-engines.md` — new clauses from §6 above
- `specs/ml-integration.md` — backend matrix, TrainingResult contract
- `.claude/skills/34-kailash-ml/SKILL.md` — correct 13 → 18 → 5 engine count, update API examples
- `packages/kailash-ml/src/kailash_ml/__init__.py` — new top-level surface
- `packages/kailash-ml/README.md` — rewrite
- `packages/kailash-ml/examples/` — new directory, 6 scripts
- `packages/kailash-ml/pyproject.toml` — base deps (xgboost/lightgbm), remove `[full-gpu]` / fix to `all-gpu`
- `rules/framework-first.md` — kailash_ml entries updated to reflect Engine as default
- `.claude/.proposals/latest.yaml` — append proposal for loom/ Gate 1 classification

---

_Audit inputs: 5 agents × 2000-3000 words each, synthesized from session transcript because worktree report files were auto-cleaned before archival. Full raw reports irrecoverable; synthesis draws on the agents' self-reported summaries that captured file paths, line numbers, and specific evidence._
