# Red Team Round 1 — GPU Stack for kailash-ml

Date: 2026-04-19
Target: the original GPU-acceleration research report (produced earlier
in this session) evaluated against the constraints in
`briefs/01-user-constraints.md` and the existing kailash-ml substrate
at `packages/kailash-ml/src/kailash_ml/`.

## Method

1. Re-read the report's recommended stack.
2. Map each recommendation against the 8 constraints.
3. Grep the existing kailash-ml for substrate that already exists
   (`detect_backend`, `BackendInfo`, `trainable.py`, `rl/`) so the
   redesign is a re-engineering, not a greenfield.
4. Flag each gap with severity + concrete remediation.

## Audit table — original recommendation vs constraints

| Recommendation                                                   | C1 ml/dl/rl | C2 GPU-first | C3 auto-detect | C4 no-config             | C5 transparent | C6 efficient       | C7 maintainable | C8 first-class | Severity                      |
| ---------------------------------------------------------------- | ----------- | ------------ | -------------- | ------------------------ | -------------- | ------------------ | --------------- | -------------- | ----------------------------- |
| Array-API sklearn over PyTorch tensors for linear / cluster / DR | ML only     | partial      | **NO**         | **NO**                   | partial        | yes                | yes             | partial        | **HIGH**                      |
| XGBoost 3.0 native GPU for trees                                 | ML only     | yes          | **NO**         | **NO**                   | silent OOM     | yes                | yes (2.0+)      | partial        | **HIGH**                      |
| Polars + Narwhals (cudf-polars for GPU)                          | all         | yes          | partial        | partial                  | yes            | yes                | yes (polars)    | yes            | MEDIUM                        |
| cuML as `[rapids]` extra for UMAP / HDBSCAN                      | ML only     | NVIDIA-only  | no             | no                       | opaque         | better than before | no              | no             | **CRITICAL**                  |
| ONNX ML opset + Treelite for serving                             | ML only     | n/a          | n/a            | partial                  | yes            | yes                | yes             | partial        | LOW                           |
| "PyTorch is the pragmatic multi-accelerator substrate"           | all         | yes          | yes            | yes (via detect_backend) | yes            | yes                | yes             | yes            | BASELINE — this is the keeper |

### Constraint legend

C1 ml/dl/rl seamless · C2 GPU-first · C3 auto-detect · C4 no-config ·
C5 transparent · C6 efficient · C7 maintainable · C8 first-class

## Findings

### CRITICAL-1 — cuML optional-extra contradicts "first-class"

**Claim in original report:** keep cuML as `kailash-ml[rapids]` for
UMAP + HDBSCAN + t-SNE because "no equivalent exists".

**Red team verdict:** this is the exact leakage the user flagged
("previously had to wrap RAPIDS which caused overhead"). An optional
NVIDIA-only extra for three algorithms contradicts:

- C1: UMAP/HDBSCAN exists for ML users on any accelerator; making it
  NVIDIA-only fractures the "seamless" promise.
- C2: if a user is on Apple MPS and calls `km.umap(...)`, GPU is
  present and they still fall to CPU — not GPU-first.
- C7: we own nothing about cuML; every release cycle, install matrix,
  and CUDA pin is dictated upstream.
- C8: "first-class" means the default path, not an installable extra.

**Remediation:** write torch-native UMAP and HDBSCAN. UMAP is ~2000
LOC of well-understood algorithm; HDBSCAN is ~500 LOC. Both compose
from primitives (k-NN graph, spanning tree, density estimation) that
are 5-50 LOC each in torch. This is an R&D track, not this-session
work. Until those land, the interim path is **scikit-learn's native
UMAP/HDBSCAN on CPU with a WARN log** — slower than cuML but portable,
zero-config, and removes the cuML dependency entirely. The speed gap
is tolerable for most workloads (UMAP CPU is 10-30 seconds on 100k
points; cuML is 1-3 seconds) and the transparency gain is large.

### HIGH-2 — "Array API sklearn" is not auto-detect

**Claim in original report:** scikit-learn 1.8 Array API dispatches to
PyTorch CUDA/MPS/XPU tensors on any hardware that supports them.

**Red team verdict:**

- **Not auto-detect.** Array API requires
  `with sklearn.config_context(array_api_dispatch=True)` around every
  fit/predict call. Users would have to write this themselves.
- **Not no-config.** Same reason — an explicit context manager IS
  configuration.
- **Partial coverage** — ~25 of 200 estimators. Silent fallback to
  CPU-numpy when the caller's estimator isn't covered is NOT
  transparent.
- **Not GPU-first on the library's own terms** — Array API is opt-in
  and experimental.

**Remediation:** inside kailash-ml, build a thin wrapper at the
`Trainable` / `MLEngine` layer that:

1. Routes every sklearn-family call through a module-level helper
   `_sklearn_fit(...)` which enters the
   `sklearn.config_context(array_api_dispatch=True)` itself based on
   `detect_backend().backend`.
2. Converts polars → torch tensor on the resolved device before
   calling fit. No numpy trampoline.
3. Logs `family=sklearn backend=cuda:0 array_api=true estimator=Ridge
n_rows=… n_features=…` before every fit.
4. On estimator-not-covered, log WARN with the fallback destination
   (CPU / torch-native reimplementation / raw sklearn), do NOT fall
   through silently.
5. Maintain an internal allowlist of array-API-supported sklearn
   estimators keyed by sklearn version, so the detection is
   deterministic rather than trial-and-error at runtime.

This converts "Array API exists in sklearn 1.8" from a user-facing
config burden into a substrate detail.

### HIGH-3 — XGBoost auto-detect is a library-side hole

**Claim in original report:** "XGBoost 3.0 native GPU dominates for
trees."

**Red team verdict:** XGBoost expects `device="cuda"` or `device="cpu"`
as an explicit parameter. Users writing `km.train(df, target=..., family="gbt")`
today would hit CPU unless kailash-ml injects `device=` from
`detect_backend()` into the XGBoost call.

Worse: if CUDA is present but OOM hits mid-training, XGBoost raises a
noisy GPU error rather than falling back — which breaks the C3
"graceful CPU fallback" promise.

**Remediation:** already partially addressed by `trainable.py::XGBoostTrainable`
— need to verify it:

1. Reads `TrainingContext.backend` (which comes from `detect_backend()`)
   and injects `device="cuda"` / `device="cpu"` accordingly.
2. Catches `xgboost.core.XGBoostError` on OOM + falls back to CPU with a
   WARN log and a `BackendFallback` event in the TrainingResult.
3. Rejects MPS/XPU/ROCm with a typed `UnsupportedFamily` error (XGBoost
   3.0 only supports CUDA + CPU) — this is already modeled.

**Grep verification required** — the current `trainable.py` imports
`detect_backend` but the XGBoost-specific GPU injection has not been
AST-audited. Listed as a Tier-2 regression test to add.

### HIGH-4 — RL path not mapped in original report

**Claim in original report:** "Don't cover deep learning or RL — out of
scope."

**Red team verdict:** user constraint C1 explicitly names RL. The
report discarded the RL quadrant and recommended a stack for the
ML-only surface.

**Current state:** `packages/kailash-ml/src/kailash_ml/rl/` already has
`env_registry.py`, `policy_registry.py`, `trainer.py`. These use
gymnasium + torch. The GPU path is whatever torch does. That's fine —
RL is already on the substrate.

**Gap:** nothing in the rl/ module routes through `detect_backend`.
`rl/trainer.py` should be audited for hardcoded `device="cpu"` /
`device="cuda"` strings and rewritten to use the resolver.

### HIGH-5 — No unified Predictions + device-stickiness contract

**Claim in original report:** implicit — each family does its own
device placement.

**Red team verdict:** users expect `model.predict(x)` to use the same
device the model was fit on, without re-specifying. Today, kailash-ml's
`Predictions` envelope accepts any raw but doesn't enforce
device-stickiness. A fit-on-CUDA model followed by predict with a
CPU-tensor input either silently copies (slow + surprising) or raises
a tensor-device-mismatch error.

**Remediation:** extend `Predictions` to carry a `device` field that
records the source tensor's device, and have `MLEngine.predict()`
transparently migrate inputs to the model's device with a DEBUG log.
This is a one-commit change; spec-level addition goes in
`ml-engines.md §3`.

### HIGH-6 — Transparency surface is underspecified

**Claim in original report:** "transparent via log"

**Red team verdict:** C5 is stronger than "log somewhere". Users need
per-call observability. Requirements:

1. Every fit / predict returns a `backend` + `device_string` +
   `precision` field in its result metadata.
2. Every fit / predict emits one structured INFO log with those three
   fields + family + n_rows + n_features.
3. Fallbacks (GPU → CPU) emit a WARN log AND set a
   `fallback_reason: str` field in the result metadata.
4. A `km.device()` entry point returns the detected BackendInfo so
   scripts can gate behavior.

The `BackendInfo` dataclass already exists at
`_device.py:132`. The gap is call-site coverage.

### MEDIUM-7 — Serialization format fan-out

**Claim in original report:** "torch.save for torch, Treelite for trees,
ONNX for linear."

**Red team verdict:** that's three formats. Maintainability takes a
hit: every upgrade of kailash-ml has to worry about backwards-compat
across three wire formats.

**Remediation:** standardize on ONE primary format — `ONNX` for
everything exportable, `torch.save` for torch-native primitives that
don't round-trip through ONNX cleanly. Drop Treelite as an optional
speed-up (`kailash-ml[tree-inference]`) not the default. One format
covers 90% of cases, two formats cover 100%.

### MEDIUM-8 — Polars GPU tied to NVIDIA

**Claim in original report:** cudf-polars for GPU preprocessing.

**Red team verdict:** `cudf-polars` is CUDA-only. For MPS / ROCm / XPU
users, the GPU preprocessing story reverts to polars CPU. That's
acceptable (polars CPU is already best-in-class), but the "GPU-first"
framing needs the caveat: preprocessing is CPU-fast by default, GPU is
NVIDIA-only today. Log this explicitly so users on Apple Silicon know
they're not missing a GPU preprocessing path.

### LOW-9 — No concrete API sketch

**Claim in original report:** recommends PyTorch + Array API + XGBoost

- Polars, but no sample of what the user writes.

**Red team verdict:** without an API sketch, the proposal reads as a
library-picker rather than an architecture. See 02-revised-stack.md
for a concrete API sketch.

## Convergence status — round 1

- **CRITICAL:** 1 open (cuML as optional extra)
- **HIGH:** 5 open (Array API detect, XGBoost inject, RL routing, device
  stickiness, transparency surface)
- **MEDIUM:** 2 open (serialization fan-out, polars GPU caveat)
- **LOW:** 1 open (API sketch missing)

**Not converged.** Round 2 target: revised stack (`02-revised-stack.md`)
addresses every CRITICAL + HIGH finding with a concrete remediation,
then re-audit.
