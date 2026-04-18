# kailash-rs ML Module — Cross-SDK Parity Analysis

**Status:** read-only inspection, 2026-04-17
**Scope:** Does `kailash-rs` have a parallel ML/DL/RL module, and if so, does it share the failure modes the kailash-py 2.0 redesign is fixing?
**Originating audit:** [kailash-py synthesis proposal](./00-synthesis-redesign-proposal.md)
**Cross-SDK rule:** `loom/.claude/rules/cross-sdk-inspection.md` (D6 — matching semantics, independent implementation)

---

## 1. Summary

**kailash-rs has a large, parallel, CPU-only classical-ML implementation** (19 crates under `crates/kailash-ml-*`, ~18 algorithm families plus an Engine layer that mirrors kailash-py's surface: `MlEngine`, `ModelRegistry`, `ExperimentTracker`, `AutoMl`, `DriftMonitor`, `FeatureStore`, `InferenceServer`, `OnnxBridge`). It has a **separate `kailash-rl` crate** (tabular RL only — Q-learning, SARSA, Monte Carlo, bandits — DL backends commented out as "Future") and a **separate `kailash-align-serving` crate** (GGUF/llama-cpp for LLM serving, no training/fine-tuning). There is **no DL training crate at all** — no `tch-rs`, no `candle`, no `burn` in active deps; the only mention of `burn-backend` is an empty feature flag. Net: kailash-rs ML is in **a different shape than kailash-py** — less ambitious on DL (so most py failure modes are N/A) but shares the orphan/unified-engine/backend-fragmentation pattern and will need its own 2.0 alignment pass.

## 2. Module inventory

### 2.1 Classical ML (`crates/kailash-ml*`, 19 crates)

| Crate                                                                                                            | Purpose                                                                                                                        |
| ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `kailash-ml-core`                                                                                                | Traits (`Fit`, `Predict`, `Transform`, `DynEstimator`), `DataSet`, `MlError`, compile-time `EstimatorRegistry` via `inventory` |
| `kailash-ml-linalg`                                                                                              | Linear algebra, optional BLAS feature                                                                                          |
| `kailash-ml-linear / -tree / -ensemble / -boost / -svm / -neighbors / -cluster / -decomposition / -text / -misc` | 40+ estimators                                                                                                                 |
| `kailash-ml-preprocessing / -metrics / -pipeline / -selection / -explorer`                                       | Infra (scalers, CV, grid search, profiling)                                                                                    |
| `kailash-ml`                                                                                                     | Umbrella crate + `engine/` module (10 sub-modules)                                                                             |
| `kailash-ml-nodes`                                                                                               | Workflow-node wrappers                                                                                                         |
| `kailash-ml-python`                                                                                              | PyO3 extension (`_kailash_ml`), `src/lib.rs` is **1 line** — currently a placeholder                                           |

### 2.2 Engine layer (`crates/kailash-ml/src/engine/`)

Mirrors kailash-py's engine surface: `MlEngine` (builder), `ModelRegistry`, `ExperimentTracker`, `AutoMl` (requires `selection`), `DriftMonitor`, `FeatureStore`, `InferenceServer`, `OnnxBridge`, `FeatureEngineer`, `ModelVisualizer`. Unlike kailash-py, there is **no Lightning equivalent** because there is no deep-learning backend at all.

### 2.3 RL (`crates/kailash-rl`)

Tabular only: `QLearning`, `SARSA`, `ExpectedSarsa`, `MonteCarlo`, bandits (`EpsilonGreedy`, `ThompsonSampling`, `Ucb1`). Envs: `FrozenLake`, `CartPole`, `CliffWalking`, `GridWorld`, `MountainCar`, `Pendulum`. Features declare `burn-backend = []` and comment-out `candle-backend` / `tch-backend`. **Function-call RL only; no deep RL.**

### 2.4 LLM serving (`crates/kailash-align-serving`)

GGUF model serving via `llama-cpp-2` (optional feature `llama-cpp`). No fine-tuning, no LoRA training — serving-only. `candle` feature commented out.

### 2.5 What does NOT exist

- No `tch-rs` / `candle` / `burn` in active dependencies anywhere in the workspace (grep confirmed)
- No equivalent of PyTorch Lightning
- Zero `accelerator` / `cuda` / `mps` / `gpu` references in `kailash-ml/src` (grep confirmed)
- No xgboost / lightgbm / catboost bindings (grep confirmed; classical ML is pure Rust)
- `kailash-ml-python` is a 1-line stub — Python bindings over the Rust ML crate are not meaningfully populated yet

## 3. Failure-mode parity table

The 7 failure modes from the kailash-py audit ([synthesis §3](./00-synthesis-redesign-proposal.md)):

| #   | Failure mode                                                             | kailash-py state                            | kailash-rs state                                                                                                                                                                                                                                                                                                                                                         | Action required                                                                                                                                                                                                |
| --- | ------------------------------------------------------------------------ | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Lightning Trainer missing `accelerator=` → silent CPU on GPU hosts       | Confirmed in `training_pipeline.py:581-591` | **N/A** — no DL backend exists (no Lightning, no tch, no candle). All Rust ML is CPU-only by design today.                                                                                                                                                                                                                                                               | None now. When a DL backend lands, open the audit.                                                                                                                                                             |
| 2   | `[dl-gpu]` extras duplicate `[dl]` → drift risk                          | Confirmed in `pyproject.toml:91`            | **N/A** — Cargo has no equivalent. Features are compositional, not duplicated. `burn-backend`/`candle-backend`/`tch-backend` are planned but commented out.                                                                                                                                                                                                              | None.                                                                                                                                                                                                          |
| 3   | ONNX export docstring claims xgboost=guaranteed with no xgboost branch   | Confirmed in py engines/onnx                | **Partial parity risk** — `OnnxBridge` (`engine/onnx.rs`) documents "linear + tree ensembles" as supported. Uses a JSON graph format, not protobuf. **Needs verification** that every documented framework has a code branch — same failure pattern possible if claims drift from code.                                                                                  | Audit kailash-rs OnnxBridge docstring vs code branches. Low priority; the surface is smaller.                                                                                                                  |
| 4   | AutoMLEngine docstring lies about what it orchestrates                   | Confirmed in py automl_engine               | **Needs verification** — `kailash-ml/src/engine/automl.rs` exists; haven't audited whether its docstring matches composition.                                                                                                                                                                                                                                            | Audit `automl.rs` and `builder.rs` for docstring ↔ composition parity.                                                                                                                                         |
| 5   | Orphan `rl/` + `agents/` subpackages not exposed at top-level `__init__` | Confirmed in py                             | **Different shape, same class.** kailash-rl is a separate crate with its own prelude and is reachable via its own `lib.rs`. It is **not** re-exported from `kailash-ml` (ML and RL are parallel, not unified). If the user vision in `00-synthesis` is "unified ML/DL/RL under one Engine," kailash-rs does NOT currently satisfy that — RL lives outside the ML Engine. | Decide whether kailash-rs should mirror the py 2.0 unified-Engine vision. If yes: add a thin trait/facade in `kailash-ml::engine` that also accepts RL trainers. If no: accept the divergence and document it. |
| 6   | `_device.py` resolver exists but not every Trainer consults it           | Confirmed in py                             | **N/A** — no device resolver exists because no DL backend exists. CPU-only classical ML has no device selection.                                                                                                                                                                                                                                                         | None now.                                                                                                                                                                                                      |
| 7   | Version drift between `pyproject.toml` and README                        | Confirmed in py (0.7 vs 0.9)                | **Needs verification** — `kailash-rs` workspace version is `3.16.3`; kailash-ml crates inherit via `version.workspace = true` (good, single source of truth). README versions for `kailash-ml` / `kailash-rl` / `kailash-align-serving` not audited.                                                                                                                     | Check the three crate-level READMEs against workspace version.                                                                                                                                                 |

### 3.1 Additional kailash-rs-specific findings (not in py audit)

- **`kailash-ml-python` is an empty PyO3 stub** (1-line `lib.rs`). This is a facade-manager-orphan-adjacent risk per `rules/orphan-detection.md`: the crate exists, is a workspace member, declares `features = ["full"]` on kailash-ml, but exposes nothing. Either populate it or delete it.
- **RL DL backends are commented out in `Cargo.toml`** (`# candle-backend`, `# tch-backend`). That is a documented deferral, not a stub, but `burn-backend = []` is live and does nothing — classic dead feature flag, equivalent to the py audit's §5 orphan pattern at the Cargo-feature layer.
- **`MlEngine` exposes nine public accessors** (`registry`, `tracker`, `AutoMl`, `DriftMonitor`, `FeatureStore`, `InferenceServer`, `OnnxBridge`, `FeatureEngineer`, `ModelVisualizer`) but the builder example in the module docstring only shows `registry()` and `tracker()`. Risk of Engine-as-bag-of-primitives (same DX complaint the py user raised) unless the Rust side adopts a similar workflow-level API.

## 4. Recommendations

### 4.1 Does the kailash-py 2.0 redesign block the kailash-rs release?

**No.** kailash-rs's ML scope (CPU classical + tabular RL + GGUF serving) is a proper subset of what the kailash-py 2.0 redesign addresses. The GPU / Lightning / DL failures that drive the py redesign do not exist in kailash-rs source. kailash-rs can ship independently; no blocking coupling.

### 4.2 However, keep three alignment items on the kailash-rs backlog

These are D6 (matching-semantics) debts that should be addressed before kailash-rs adds DL. Each corresponds to a py-2.0 finding worth pre-empting in Rust:

**Issue draft (to file manually on `esperie-enterprise/kailash-rs`):**

> **Title:** [cross-sdk] Pre-empt DL-era failure modes from kailash-py 2.0 redesign
>
> **Body:**
> kailash-py is undergoing a 2.0 redesign to address 7 failure modes in its ML layer. See `terrene-foundation/kailash-py` workspace `kailash-ml-audit` synthesis proposal at `workspaces/kailash-ml-audit/analysis/00-synthesis-redesign-proposal.md`.
>
> Three of those findings are pre-emptively addressable in kailash-rs before it grows a DL backend:
>
> 1. **Device-first architecture (py finding #1, #6)** — when `burn-backend` / `candle-backend` / `tch-backend` are uncommented, plumb a device resolver (`CPU|CUDA|MPS|ROCm|Metal`) through every Trainer and registry. Do not ship a DL backend that silently runs on CPU when a GPU is available.
> 2. **Unified Engine surface (py finding #5)** — kailash-rl and kailash-align-serving currently live outside `kailash-ml::engine`. Before adding DL, decide whether a unified `Trainable` trait in `kailash-ml-core` should be the common spine so ML, DL, and RL all flow through `MlEngine`. The py 2.0 direction is "single-point Engine with Primitives under the hood."
> 3. **Docstring ↔ code parity for `AutoMl` and `OnnxBridge` (py findings #3, #4)** — audit that every framework/export the Rust docstrings claim is supported has a live code branch. py found xgboost promised with no branch; catch this class early in Rust.
>
> Also populate or delete `crates/kailash-ml-python` — the 1-line `lib.rs` is currently an orphan crate (see `loom/.claude/rules/orphan-detection.md`).
>
> **Cross-SDK alignment:** this is the Rust equivalent of the kailash-py 2.0 redesign tracked at `workspaces/kailash-ml-audit/`. Originating synthesis: `00-synthesis-redesign-proposal.md`.
> **Labels:** `cross-sdk`, `ml`, `technical-debt`

### 4.3 Do NOT bring kailash-rs to py-2.0 parity in-place right now

Because there is no DL in kailash-rs today, building a full GPU-first Lightning-equivalent would be speculative. Preferred path:

1. Ship kailash-py 2.0 first (reference architecture).
2. When kailash-rs adds a DL backend (burn, candle, or tch), use the py 2.0 Engine contract as the spec (D6 matching semantics) rather than re-deriving it.
3. The `kailash-ml-python` PyO3 crate is the place to evaluate whether "defer to kailash-py via FFI" is the right Rust DL strategy — but the decision belongs to the Rust SDK authors once py 2.0 stabilises.

## 5. Cross-reference

- **kailash-py synthesis (source of truth for the 2.0 redesign):** [`00-synthesis-redesign-proposal.md`](./00-synthesis-redesign-proposal.md)
- **Cross-SDK inspection rule:** `loom/.claude/rules/cross-sdk-inspection.md` (D6)
- **Orphan detection rule:** `loom/.claude/rules/orphan-detection.md` (applies to `kailash-ml-python` stub and dead `burn-backend` feature)
- **Facade manager detection rule:** `loom/.claude/rules/facade-manager-detection.md` (applies to `MlEngine`'s nine accessors if `builder.rs` docstring drifts from composition)
- **Inspected Rust paths:** `/Users/esperie/repos/loom/kailash-rs/Cargo.toml`, `crates/kailash-ml*/Cargo.toml`, `crates/kailash-ml/src/lib.rs`, `crates/kailash-ml/src/engine/{mod,builder,onnx}.rs`, `crates/kailash-rl/{Cargo.toml,src/lib.rs,src/training/mod.rs}`, `crates/kailash-align-serving/Cargo.toml`, `crates/kailash-ml-python/{Cargo.toml,src/lib.rs}`

---

_Analysis per `rules/cross-sdk-inspection.md` — read-only inspection of `/Users/esperie/repos/loom/kailash-rs`; no modifications made to the Rust SDK._
