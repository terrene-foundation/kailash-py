# Kailash ML Backends Specification

Version: 1.0.0 (draft)

Parent domain: ML Lifecycle (`kailash-ml`). Companion files: `ml-engines.md` (engine contracts), `ml-integration.md` (architecture, type contracts, ONNX bridge).

Package: `kailash-ml` v1.0.0
License: Apache-2.0
Python: >=3.11
Cross-SDK: Shared semantics with `kailash-rs` per EATP D6 — see § 9.

This file is the domain truth for compute backend detection, selection, precision resolution, Trainer integration, non-Lightning family mapping, hardware-gated CI, the `km.doctor()` diagnostic, and the typed error hierarchy. Any training or inference path that touches a device MUST comply with every MUST clause below.

**Origin**: `workspaces/kailash-ml-audit/analysis/00-synthesis-redesign-proposal.md` § 4 ("cascading bug") + § 6.1 (Backend Matrix). Spec authored to prevent regression of `training_pipeline.py:581-591` where `L.Trainer()` was instantiated with no `accelerator` argument — 5 of 6 backends silently ran on CPU.

---

## 1. Backend Enumeration

Six first-class backends. Every engine that places tensors, invokes a Trainer, or serves inference MUST support this matrix. Backends not listed here (IPU, HPU, DirectML, Vulkan) are OUT OF SCOPE for 2.0 and MUST raise `UnsupportedFamily`.

| Backend  | Vendor / line                                      | Lightning `accelerator`  | torch device string                         | Install (PyPI)                                                                                                                        | Detection probe                                                                                   | fp32 | fp16 | bf16     | int8       |
| -------- | -------------------------------------------------- | ------------------------ | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ---- | ---- | -------- | ---------- |
| **cpu**  | Any x86_64/ARM64 host                              | `"cpu"`                  | `"cpu"`                                     | Base `pip install kailash-ml`                                                                                                         | Always available                                                                                  | yes  | no\* | no\*     | yes        |
| **cuda** | NVIDIA (A100, H100, L40S, V100, T4, RTX 30xx/40xx) | `"cuda"` (alias `"gpu"`) | `"cuda:{idx}"`                              | `pip install kailash-ml[cuda]` (pulls `torch` CUDA wheel from PyPI)                                                                   | `torch.cuda.is_available()`                                                                       | yes  | yes  | yes\*\*  | yes        |
| **mps**  | Apple Silicon (M1/M2/M3/M4)                        | `"mps"`                  | `"mps"`                                     | Base install; `torch` universal2 wheel on Darwin ARM64                                                                                | `torch.backends.mps.is_available()` AND `torch.backends.mps.is_built()`                           | yes  | yes  | no\*\*\* | no\*\*\*\* |
| **rocm** | AMD Instinct (MI210, MI250, MI300)                 | `"cuda"` (HIP layer)     | `"cuda:{idx}"` (HIP→CUDA API source-compat) | `pip install kailash-ml[rocm]` (separate torch ROCm wheel index; MUST specify `--index-url https://download.pytorch.org/whl/rocm6.0`) | `torch.version.hip is not None` AND `torch.cuda.is_available()`                                   | yes  | yes  | yes\*\*  | yes        |
| **xpu**  | Intel Data Center GPU Max, Arc                     | `"xpu"`                  | `"xpu:{idx}"`                               | Base install on torch ≥ 2.5 (native `torch.xpu`); `pip install kailash-ml[xpu]` on pre-2.5 boxes (ipex fallback; Linux only)          | Dual-path probe (Decision 5; § 2.2.1) — native `torch.xpu.is_available()` then `ipex` fallback    | yes  | yes  | yes\*\*  | yes        |
| **tpu**  | Google TPU v2/v3/v4/v5                             | `"tpu"`                  | `xm.xla_device()`                           | `pip install kailash-ml[tpu]` (pulls `torch_xla`; Linux only)                                                                         | Successful `import torch_xla.core.xla_model as xm` AND non-empty `xm.get_xla_supported_devices()` | yes  | no   | yes      | no         |

Notes on the precision matrix:

- `*` CPU fp16/bf16 exists in PyTorch (autocast) but is slower than fp32 on most CPUs; not recommended. MUST raise `PrecisionUnsupported` if a caller requests CPU fp16 without `force=True`.
- `**` CUDA bf16 requires compute capability ≥ 8.0 (Ampere+, i.e. A100/H100/RTX 30+/L40S). V100 and T4 (CC 7.0/7.5) MUST NOT be given bf16; the resolver SHALL return fp16. Same rule applies to ROCm bf16 (MI250X and later) and XPU bf16 (PVC and later). Detection SHALL probe `torch.cuda.get_device_capability()` for CUDA, and a vendor-specific probe for ROCm/XPU.
- `***` MPS bf16: OPEN QUESTION. PyTorch ≥ 2.3 announced partial bf16 on MPS but op coverage is incomplete (e.g. `scaled_dot_product_attention` falls back to fp32). Spec SHALL default MPS to fp16 and flag bf16 as experimental behind `precision="bf16-mixed"` + `force=True`.
- `****` MPS int8: OPEN QUESTION. Metal backend supports quantized kernels via CoreML ANE but PyTorch's direct int8 path is limited. Treat as N/A for 2.0.

### 1.1 Known Gotchas (per backend)

Gotchas below MUST be surfaced by `km.doctor()` (§ 7) when the relevant backend is detected.

- **cpu** — default; no gotcha.
- **cuda** — honors `CUDA_VISIBLE_DEVICES=""` (MUST disable detection).
- **mps** — op coverage incomplete (torch 2.4); CPU fallback emits `UserWarning`. MUST log WARN when MPS triggers CPU fallback.
- **rocm** — `torch.version.hip` is the sole discriminator vs CUDA; some ops missing on ROCm < 6.0. MUST log ROCm version at INFO.
- **xpu** — dual-path resolver accepts BOTH native `torch.xpu` (torch ≥ 2.5) AND `intel-extension-for-pytorch` fallback (Decision 5; § 2.2.1). `km.doctor()` MUST report which path resolved via `BackendInfo.diagnostic_source` and `BackendInfo.xpu_via_ipex`.
- **tpu** — XLA compiles lazily; first step emits ~30s pause. MUST log INFO before first step so operators do not read the pause as a hang.

---

## 2. `detect_backend()` — Priority Resolver

### 2.1 Signature and Contract

```python
def detect_backend(prefer: Optional[str] = None) -> BackendInfo:
    """Resolve the compute backend to use for training/inference.

    Args:
      prefer: Backend name ("cuda", "mps", "rocm", "xpu", "tpu", "cpu"),
              or "auto" / None for priority-order detection.

    Returns:
      BackendInfo dataclass with backend, accelerator, device_string,
      device_count, capabilities, diagnostic_source, and rocm/xpu versions
      where applicable.

    Raises:
      BackendUnavailable: when `prefer` names a backend that is not present.
      ValueError: when `prefer` is a string outside the known set.
    """
```

### 2.2 MUST: Priority Order When `prefer is None`

`detect_backend(None)` and `detect_backend("auto")` MUST resolve in this order and return the first available:

1. **cuda** — `torch.cuda.is_available()` AND `torch.version.hip is None`
2. **mps** — `torch.backends.mps.is_available()` AND `torch.backends.mps.is_built()`
3. **rocm** — `torch.cuda.is_available()` AND `torch.version.hip is not None`
4. **xpu** — dual-path probe per Decision 5 (see § 2.2.1)
5. **tpu** — `torch_xla.core.xla_model.get_xla_supported_devices()` returns non-empty list
6. **cpu** — always available

#### 2.2.1 MUST: XPU Dual-Path Resolver (Decision 5)

Per approved Decision 5, the XPU probe MUST accept BOTH paths and MUST attempt them in native-first order:

1. **Native torch ≥ 2.5 XPU** — `hasattr(torch, "xpu") and torch.xpu.is_available()` — selected first.
2. **Intel Extension for PyTorch (ipex)** — fallback on `ImportError` / `AttributeError` from the native probe: `import intel_extension_for_pytorch` then `torch.xpu.is_available()` (ipex registers the `torch.xpu` namespace at import time).

The resolved `BackendInfo` MUST set `backend="xpu"` and MUST annotate the path used:

- `BackendInfo(backend="xpu", diagnostic_source="native-torch-xpu", xpu_via_ipex=False, ...)` when the native probe succeeded.
- `BackendInfo(backend="xpu", diagnostic_source="ipex", xpu_via_ipex=True, ...)` when the ipex fallback was required.

```python
# DO — dual-path with native first (Decision 5)
def _probe_xpu() -> tuple[bool, bool]:
    """Returns (available, via_ipex). Native-first; ipex fallback."""
    # Native torch ≥ 2.5 path
    if hasattr(torch, "xpu"):
        try:
            if torch.xpu.is_available():
                return (True, False)
        except (RuntimeError, AttributeError):
            pass  # fall through to ipex probe
    # ipex fallback — registers torch.xpu namespace on import
    try:
        import intel_extension_for_pytorch  # noqa: F401
    except ImportError:
        return (False, False)
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        return (True, True)
    return (False, False)

# DO NOT — sole-dependency lock-in on ipex
import intel_extension_for_pytorch  # hard import at module top
# ↑ breaks on torch ≥ 2.5 boxes that have native XPU without ipex installed

# DO NOT — native-only probe
if hasattr(torch, "xpu") and torch.xpu.is_available():
    ...
# ↑ misses ipex-only deployments on torch < 2.5 boxes
```

**Extra contract.** `[xpu]` extra per `rules/dependencies.md` (declared-imported discipline): `intel-extension-for-pytorch>=2.5; platform_system == "Linux"`. The native-first probe means `[xpu]` is NOT required on torch ≥ 2.5 Linux boxes; ipex is the fallback install for pre-2.5 boxes or users who prefer the Intel-distributed build.

**Why:** Approved Decision 5 pins "Native-first probe order. No sole-dependency lock-in." Hard-requiring ipex breaks modern torch; skipping ipex breaks pre-2.5 deployments. Dual-path with native-first is the only contract that survives both.

```python
# DO — let the resolver run
info = detect_backend()  # returns BackendInfo(backend="cuda", ...) on an H100 box

# DO NOT — hand-roll the priority in each engine
if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():
    device = "mps"
# ...priority drift across 6 engines
```

**Why:** Six engines (TrainingPipeline, InferenceServer, RLTrainer, HyperparameterSearch, AutoMLEngine, EnsembleEngine) each need to pick a backend; every hand-rolled priority block is a new place the priority can drift. One resolver = one enforcement point.

### 2.3 MUST: Explicit `prefer=` Raises On Unavailable Backend

`detect_backend(prefer="xpu")` MUST raise `BackendUnavailable` if XPU is not detected. Silent fallback to CPU is BLOCKED.

```python
# DO — fail fast
try:
    info = detect_backend(prefer="xpu")
except BackendUnavailable as e:
    logger.error("backend.xpu.unavailable", reason=str(e))
    # caller decides: error out OR explicitly fall back to cpu

# DO NOT — silent fallback
info = detect_backend(prefer="xpu")  # silently returns cpu on a CUDA box
# user thinks training is on XPU; it is on CPU
```

**BLOCKED rationalizations:**

- "CPU fallback is friendly to users who typo the name"
- "We should be permissive — the training still runs"
- "The log line is enough; the fallback is harmless"

**Why:** Phase 5.11 pattern: silent fallback is the #1 cause of "my training was slow" post-mortems where the operator was convinced they ran on the GPU. Explicit `prefer=` is a promise the user made; break it loudly or not at all.

### 2.4 MUST: `BackendInfo` Carries Decision Evidence

```python
@dataclass(frozen=True)
class BackendInfo:
    backend: Literal["cpu", "cuda", "mps", "rocm", "xpu", "tpu"]
    accelerator: str                 # Lightning accelerator ("cuda", "mps", "tpu", "cpu")
    device_string: str               # torch device string ("cuda:0", "mps", "xpu:0", "cpu")
    device_count: int                # visible device count for this backend
    devices: int | list[int] | str   # Lightning `devices=` value (1, [0,1], or "auto")
    capabilities: frozenset[str]     # subset of {"fp16", "bf16", "int8", "distributed"}
    diagnostic_source: str           # how it was detected (e.g. "torch.cuda.is_available")
    rocm_version: str | None         # e.g. "6.0" when backend == "rocm"
    xpu_via_ipex: bool | None        # True when XPU requires intel-extension-for-pytorch
    cuda_capability: tuple[int,int] | None  # (major, minor) for CUDA/ROCm
```

`capabilities` MUST be derived from runtime probes, not hard-coded by backend. Example: a CUDA V100 returns `{"fp16", "int8", "distributed"}` (no bf16), while an H100 returns `{"fp16", "bf16", "int8", "distributed"}`.

**Why:** Precision resolution (§ 3) depends on capability detection at the device level, not the vendor level. A vendor-level assumption ("CUDA has bf16") silently downgrades a V100 cluster.

### 2.5 MUST: Regression Test Per Priority Step

A Tier 1 test with monkeypatched probes MUST exist for each of the 6 priority steps and for each BLOCKED-rationalization case. File: `tests/unit/test_detect_backend.py`. One test SHALL be named `test_detect_backend_explicit_prefer_raises_when_absent` and assert `BackendUnavailable` on `prefer="xpu"` when no XPU.

**Why:** The resolver is a load-bearing function for every GPU code path. A refactor that loosens `prefer=` to permissive fallback must fail at the PR gate.

---

## 3. Precision Auto-Selection

### 3.1 MUST: `precision="auto"` Resolves To Concrete Value Before Trainer Construction

```python
def resolve_precision(info: BackendInfo, requested: str = "auto") -> str:
    """Resolve precision='auto' into a concrete Lightning precision string."""
```

The resolver MUST return one of Lightning's concrete precision strings — `"32-true"`, `"16-mixed"`, `"bf16-mixed"`, `"bf16-true"`, `"16-true"` — never `"auto"`.

### 3.2 Auto-Selection Table

Resolution order for `requested == "auto"`:

| Backend | Device capability                 | Returned precision | Rationale                                                  |
| ------- | --------------------------------- | ------------------ | ---------------------------------------------------------- |
| cuda    | CC ≥ 8.0 (A100/H100/L40S/RTX 30+) | `"bf16-mixed"`     | bf16 dynamic range matches fp32; no loss scaling required  |
| cuda    | CC 7.0–7.5 (V100/T4)              | `"16-mixed"`       | fp16 supported; bf16 is not                                |
| cuda    | CC < 7.0 (P100/K80)               | `"32-true"`        | no mixed-precision hardware                                |
| mps     | any Apple Silicon                 | `"16-mixed"`       | bf16 op coverage incomplete (see § 1 footnote \*\*\*)      |
| rocm    | MI300-class                       | `"bf16-mixed"`     | bf16 available on MI300 series                             |
| rocm    | MI250-class                       | `"16-mixed"`       | bf16 partial on MI250; fp16 is the reliable path           |
| rocm    | older (MI100)                     | `"32-true"`        | no mixed-precision hardware                                |
| xpu     | PVC-class                         | `"bf16-mixed"`     | Data Center GPU Max supports bf16                          |
| xpu     | Arc / older                       | `"16-mixed"`       | fp16 is the reliable path                                  |
| tpu     | any                               | `"bf16-true"`      | TPU XLA compiles bf16 natively; mixed-precision not needed |
| cpu     | any                               | `"32-true"`        | fp16/bf16 on CPU is slower than fp32                       |

OPEN QUESTION: the exact MI250 vs MI300 / Arc vs PVC cutoff — MUST be validated against AMD ROCm 6.0 and Intel XPU docs before 2.0 locks. Flag as TODO until hardware CI lane confirms.

### 3.3 MUST: Caller-Specified Precision Is Validated, Not Overridden

When the caller passes `precision="bf16-mixed"` and the detected device does not support bf16, the resolver MUST raise `PrecisionUnsupported` with the specific device, requested precision, and suggested alternative. Silent downgrade to fp16 is BLOCKED.

```python
# DO — loud rejection with actionable message
raise PrecisionUnsupported(
    f"Requested precision 'bf16-mixed' but device {info.device_string} "
    f"(CC {info.cuda_capability}) does not support bf16. "
    f"Use precision='16-mixed' for fp16, or 'auto' for the resolver to pick."
)

# DO NOT — silent downgrade
logger.info("precision.downgraded", requested="bf16-mixed", using="16-mixed")
return "16-mixed"
```

**Why:** Silent downgrade produces a run that the user believes was bf16 but was fp16. Reproducibility and metric comparisons break silently across runs.

---

## 4. Lightning Trainer Integration

### 4.1 MUST: Every `L.Trainer()` Call Passes Resolved Values Explicitly

Every training call that ends up in Lightning MUST pass `accelerator`, `devices`, and `precision` as concrete values — never `"auto"` — and MUST log the resolution at INFO before instantiating the Trainer.

```python
# DO — resolve then instantiate then log
info = detect_backend(prefer=model_spec.prefer_backend)
precision = resolve_precision(info, requested=eval_spec.precision)
logger.info(
    "training.backend.selected",
    backend=info.backend,
    accelerator=info.accelerator,
    device_string=info.device_string,
    devices=info.devices,
    precision=precision,
    diagnostic_source=info.diagnostic_source,
)
trainer = pl.Trainer(
    accelerator=info.accelerator,    # "cuda", not "auto"
    devices=info.devices,            # 1 or [0,1] or "auto" resolved to a list
    precision=precision,             # "bf16-mixed", not "auto"
    callbacks=callbacks,
    max_epochs=max_epochs,
)

# DO NOT — let Lightning resolve silently
trainer = pl.Trainer(accelerator="auto", devices="auto", precision="auto")
# no evidence in logs; TrainingResult carries meaningless "auto"
```

**BLOCKED rationalizations:**

- "Lightning's own resolver is good enough"
- "Passing `auto` is simpler"
- "The log line duplicates what Lightning prints"

**Why:** Traceability. The single cascading bug at `training_pipeline.py:581-591` existed because `L.Trainer()` had no `accelerator=`. The user's post-mortem of "why is training slow?" has to start from a log line that names the resolved backend. "auto" in the logs is useless.

### 4.2 MUST: Device Placement Before `trainer.fit()`

Tensors and the LightningModule MUST be moved to the target device OR left to Lightning's accelerator dispatch — never both, never neither.

The canonical kailash-ml path is: **let Lightning dispatch via `accelerator=`**. The LightningModule is instantiated on CPU; the Trainer moves it. DataLoaders MUST set `pin_memory=True` when `info.backend in {"cuda", "rocm"}` and `pin_memory=False` elsewhere (pin_memory on MPS/XPU/TPU/CPU is either a no-op or counterproductive).

```python
# DO — let Lightning dispatch, set pin_memory per backend
pin = info.backend in {"cuda", "rocm"}
loader = DataLoader(dataset, batch_size=bs, shuffle=True, pin_memory=pin)
module = MyLightningModule(**kwargs)  # on CPU
trainer = pl.Trainer(accelerator=info.accelerator, devices=info.devices, precision=precision)
trainer.fit(module, loader)

# DO NOT — double-dispatch: manual .to() + accelerator=
module = MyLightningModule(**kwargs).to("cuda")  # manual move
trainer = pl.Trainer(accelerator="cuda")         # Trainer moves it again
# Can work, can crash, depends on Lightning version. Don't.
```

**Why:** Lightning's dispatch is the tested path; manual `.to()` before `trainer.fit()` is the untested path and produces subtle multi-GPU bugs (DataLoader on device 0 but DDP expects per-rank placement).

### 4.3 MUST: `TrainingResult` Carries The Resolved Values

Every `TrainingResult` returned by a Lightning-wrapped training path MUST populate `backend`, `accelerator`, `device_string`, `devices`, `precision`, and `cuda_capability` (when applicable). A TrainingResult with `backend="auto"` or `precision="auto"` is a contract violation.

**Why:** Downstream consumers (ExperimentTracker auto-logs, MLflow export, ModelRegistry metadata) rely on these fields for reproducibility. "auto" strings make the run impossible to replay.

---

## 5. Non-Lightning Family Backend Mapping

The Engine routes every training call through the Lightning wrapper (§ 4), but non-torch families have additional knobs that MUST be set before the wrapper hands off. Each family below has a mandated mapping.

### 5.1 sklearn

- **Backend support**: CPU only.
- **TrainingResult.backend**: always `"cpu"`.
- **Wrapping**: MUST be wrapped as `LightningModule` for metric/callback unification, but the inner `.fit()` runs on CPU regardless of `info.backend`.
- **If caller specifies `prefer_backend="cuda"`**: MUST log WARN `"sklearn.backend.ignored"` and proceed on CPU; MUST NOT raise. (Rationale: sklearn's CPU-only is not a user error; it is the family's nature.)

### 5.2 xgboost

- **Backend support**: CPU and CUDA (xgboost 2.0+ idiom `device="cuda"` / `device="cpu"`). MPS/ROCm/XPU/TPU not supported upstream.
- **Mapping**:
  - `info.backend == "cuda"` → pass `device="cuda"`
  - `info.backend == "cpu"` → pass `device="cpu"`
  - `info.backend in {"mps", "rocm", "xpu", "tpu"}` → MUST raise `UnsupportedFamily` naming the backend and the family. MUST NOT silently fall back to CPU.
- **ROCm note**: xgboost does not ship a ROCm build as of 2.0.3; `device="cuda"` on a ROCm box raises at runtime. MUST detect this and raise `UnsupportedFamily` before the training call.

### 5.3 lightgbm

- **Backend support**: CPU and GPU (via `device_type="gpu"`; requires lightgbm built with OpenCL or CUDA).
- **Mapping**:
  - `info.backend == "cuda"` → probe lightgbm build; if GPU support present, pass `device_type="gpu"` + `gpu_use_dp=False`. If not, raise `UnsupportedFamily` with the install hint: `pip install lightgbm --config-settings=cmake.define.USE_GPU=1`.
  - `info.backend == "cpu"` → pass `device_type="cpu"`.
  - `info.backend in {"mps", "rocm", "xpu", "tpu"}` → MUST raise `UnsupportedFamily`.

### 5.4 catboost

- **Backend support**: CPU and CUDA (`task_type="GPU"` / `"CPU"`).
- **Mapping**: same constraint shape as xgboost. MPS/ROCm/XPU/TPU → `UnsupportedFamily`.

### 5.5 torch / lightning

- **Backend support**: all 6 (via `accelerator=`).
- **Mapping**: § 4 governs.

### 5.6 stable-baselines3 / torchrl

- **Backend support**: follows torch's device support — cuda, mps, cpu. TPU/XLA path exists in `torchrl` ≥ 0.5 but is experimental. Default to `"cuda"` / `"mps"` / `"cpu"`; treat `"tpu"`/`"rocm"`/`"xpu"` as OPEN QUESTION and raise `UnsupportedFamily` at 2.0 until validated.
- **RL Engine wrapping**: RL trainers MUST use Lightning's accelerator for environment-rollout → learner transfers. The inner SB3/torchrl policy MUST be constructed with `device=info.device_string`.

---

## 6. Hardware-Gated CI

### 6.1 MUST: Per-Backend Test Files With Explicit Markers

Test organization:

```
packages/kailash-ml/tests/
  unit/
    test_detect_backend.py            # Tier 1: mocks all device probes
    test_resolve_precision.py         # Tier 1: mocks capabilities
  integration/
    backends/
      test_cpu_backend.py             # runs every CI build
      test_cuda_backend.py            # pytest.mark.gpu_cuda
      test_mps_backend.py             # pytest.mark.gpu_mps
      test_rocm_backend.py            # pytest.mark.gpu_rocm
      test_xpu_backend.py             # pytest.mark.gpu_xpu
      test_tpu_backend.py             # pytest.mark.tpu
```

Every per-backend file MUST exercise ALL of:

1. `detect_backend(prefer=<that backend>)` returns a `BackendInfo` with correct fields.
2. `resolve_precision(info, "auto")` returns the expected precision for that device class.
3. A small `BoringModel`-style Lightning training run completes one epoch and produces a `TrainingResult` whose `backend`, `accelerator`, `devices`, `precision` match the resolution.
4. The same run's `TrainingResult.device: DeviceReport` round-trips through `ModelRegistry.get_model()` unchanged — `device.backend_name`, `device.family`, and `device.precision` match the flattened `_kml_run` columns (state-persistence verification per `rules/testing.md` § Tier 2). The 1.x back-compat mirrors (`result.device_used`, `result.accelerator`, `result.precision`) MUST resolve to the same strings (see `ml-engines-v2.md §4.1` for the canonical dataclass shape).
5. A non-Lightning family run (sklearn MUST be in every file) produces a `TrainingResult` with `backend="cpu"` regardless of hardware, and (for xgboost/lightgbm on cuda-only backends) an `UnsupportedFamily` is raised when the family cannot run on the backend.

### 6.2 MUST: `skipif` Via Probe, Not Via Marker Alone

```python
# DO — skip only when the probe truly fails
@pytest.mark.gpu_mps
@pytest.mark.skipif(not _mps_available(), reason="MPS not available")
async def test_mps_lightning_training(...):
    info = detect_backend(prefer="mps")
    # ...

# DO NOT — rely on marker filtering alone
@pytest.mark.gpu_mps
async def test_mps_lightning_training(...):
    # runs on CI without MPS; fails with confusing torch error
```

**Why:** Marker filtering is an opt-in layer (`pytest -m gpu_mps`). Without `skipif`, a developer running the full suite locally gets confusing failures instead of clean skips.

### 6.3 MUST: CI Matrix Declares Hardware Lanes (Decision 7)

Per approved Decision 7, `.github/workflows/ml-backends.yml` MUST define separate jobs for every backend enumerated in § 1, with promotion status pinned by the workflow file:

| Lane   | Runner                                       | Status at 1.0.0                                                | Promotion trigger                                              |
| ------ | -------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------- |
| `cpu`  | GitHub hosted (`ubuntu-latest`, `macos-14`)  | **BLOCKING** — fails the merge on red                          | n/a (already blocking)                                         |
| `mps`  | GitHub hosted (`macos-14` on Apple Silicon)  | **BLOCKING** — fails the merge on red                          | n/a (already blocking)                                         |
| `cuda` | Self-hosted NVIDIA (pending; see infra todo) | NON-BLOCKING until the self-hosted runner lands; THEN BLOCKING | PR that registers the self-hosted NVIDIA runner flips the flag |
| `rocm` | Self-hosted AMD (pending; see infra todo)    | NON-BLOCKING until the self-hosted runner lands; THEN BLOCKING | PR that registers the self-hosted AMD runner flips the flag    |
| `xpu`  | Self-hosted Intel (pending; see infra todo)  | NON-BLOCKING until the self-hosted runner lands; THEN BLOCKING | PR that registers the self-hosted Intel runner flips the flag  |
| `tpu`  | Google TPU VM (pending; see infra todo)      | NON-BLOCKING until the TPU VM lane lands; THEN BLOCKING        | PR that provisions the TPU VM workflow target flips the flag   |

**MUST clause.** CPU and MPS are BLOCKING gates for every PR. CUDA, ROCm, XPU, TPU jobs are NON-BLOCKING until a self-hosted runner (or equivalent managed lane) lands for each — at which point they promote to BLOCKING. The promotion is locked by the CI workflow file (NOT changeable per-PR); a PR that tries to demote a backend from BLOCKING to NON-BLOCKING is rejected at review.

**Runner acquisition todo.** Tracked in `workspaces/kailash-ml-audit/infra/gpu-runner-acquisition.md` (Foundation infra backlog). Each row in the table above flips to BLOCKING in the same PR that registers the corresponding runner with GitHub Actions.

**Why:** Decision 7 approved 2026-04-21 says: "CPU + MPS (macos-14) BLOCKING now. CUDA becomes BLOCKING the day a self-hosted runner lands. Track runner acquisition as explicit infra todo." The prior text ("GPU jobs are non-blocking at 2.0 but MUST report status") inverted both halves: it dropped MPS from BLOCKING and left CUDA non-blocking forever.

---

## 7. `km.doctor()` Diagnostic

### 7.1 MUST: Public Diagnostic Command

```bash
$ python -m kailash_ml.doctor
# or via console_script:
$ km-doctor
```

Outputs (structured JSON when `--json`, human-readable by default):

- **Detected backends**: enumeration of which of the 6 backends are present, with `diagnostic_source` for each.
- **Selected default**: the backend `detect_backend(None)` would return.
- **Precision for each detected backend**: result of `resolve_precision(info, "auto")`.
- **Installed extras**: which of `[cuda]`, `[rocm]`, `[xpu]`, `[tpu]`, `[dl]`, `[dl-deepspeed]`, `[dl-fsdp]`, `[agents]`, `[explain]`, `[imbalance]` are installed. `[dl-deepspeed]` pins `deepspeed>=0.14.0 + pydantic>=2.0` and is the required extra for `MLEngine.fit(strategy="deepspeed")` per `ml-engines-v2-draft.md §3.2 MUST 6`; `[dl-fsdp]` is an alias for `[dl]` + `torch>=2.3`.
- **Family probes**: torch, lightning, sklearn, xgboost, lightgbm, catboost, onnxruntime, onnxruntime-gpu — each with version or `"not installed"`.
- **ONNX runtime availability**: including CUDA EP, ROCm EP, DirectML EP detection.
- **Default SQLite path**: `~/.kailash_ml/ml.db` and whether the directory is writable.
- **Cache paths**: `~/.kailash_ml/cache` writable, current size.
- **Tenant mode**: whether `KAILASH_ML_DEFAULT_TENANT` is set.
- **Known gotchas**: § 1.1 entries relevant to detected backends.

### 7.2 MUST: Exit Codes

- Exit 0 — base install works on CPU (minimum viable).
- Exit 1 — any backend explicitly requested via `--require=<name>` is unreachable; OR the base CPU path is broken (torch missing, polars import fails, etc.).
- Exit 2 — reserved for degraded modes (e.g. ONNX export not available but training works).

### 7.3 MUST: Used By CI

The `cpu` CI lane MUST run `km-doctor --json` after install and fail if exit != 0. Each hardware lane MUST run `km-doctor --require=<backend> --json` and fail if exit != 0.

**Why:** Install correctness is harder to test than training correctness. `doctor` is the single command that turns "does the install work?" from a 20-minute investigation into a 200ms script.

### 7.4 MUST: `backend-compat-matrix.yaml` As Data, Not Code (Decision 6)

Per approved Decision 6, the hardware-architecture compatibility matrix MUST live as a YAML data file packaged with the SDK, NOT hardcoded in spec markdown or Python source. This lets new GPU architectures, new driver minimum versions, and new precision cutoffs ship as data-file updates without a kailash-ml SDK re-release.

**File path.** `packages/kailash-ml/data/backend-compat-matrix.yaml` (shipped as package data via `importlib.resources.files("kailash_ml.data") / "backend-compat-matrix.yaml"`).

**Schema (v1).**

```yaml
# packages/kailash-ml/data/backend-compat-matrix.yaml
schema_version: 1
backends:
  cuda:
    min_compute: 7.0 # Volta; no Kepler/Maxwell/Pascal
    supported_precision: [fp32, fp16, bf16, int8]
    notes: {}
  mps:
    min_macos: 14.0
    supported_precision: [fp32, fp16]
    experimental_precision: [bf16]
    notes:
      bf16: "PyTorch 2.3+ bf16 on MPS requires force=True; SDPA still fp32 fallback"
  rocm:
    arch_allowlist: [gfx906, gfx908, gfx90a, gfx942] # MI50/MI100/MI210/MI250/MI300
    supported_precision: [fp32, fp16, bf16]
  xpu:
    native_min_torch: "2.5"
    ipex_min_version: "2.5"
    supported_precision: [fp32, fp16, bf16]
  tpu:
    min_jax_tpu: "0.4"
    supported_precision: [bf16, fp32]
  cpu:
    supported_precision: [fp32]
```

**Loader contract.** `kailash_ml.backends._compat_matrix.load_compat_matrix()` MUST:

1. Read from `importlib.resources.files("kailash_ml.data") / "backend-compat-matrix.yaml"`.
2. Validate `schema_version == 1`; unknown versions raise `CompatMatrixSchemaError(BackendError)` with the observed-vs-expected schema_version.
3. Memoize the parsed matrix at module load; re-read on explicit `load_compat_matrix(force_reload=True)` for tests.

**`km.doctor` consumer contract.** `km.doctor()` (§ 7) MUST:

1. Call `load_compat_matrix()` at the start of the doctor run.
2. For the detected backend, look up the supported precision set AND the architecture/OS/version gate (CUDA compute, macOS version, ROCm arch, torch/ipex version, TPU jax_tpu min).
3. If the detected hardware is outside the matrix's supported envelope, raise `UnsupportedPrecision(BackendError, RuntimeError)` with actionable install hints (e.g. `"Detected CUDA compute 6.1 (Pascal); kailash-ml requires compute >= 7.0 (Volta+). Upgrade hardware or use precision='32-true' on CPU."`).
4. In `--json` mode, emit the matrix values under `compat_matrix` so the CI lane can assert against them.

**Update path.** New architecture support MUST be shipped by (a) editing the YAML, (b) bumping a `kailash-ml-data` companion wheel version, and (c) `pip install --upgrade kailash-ml-data`. No kailash-ml code change required for envelope widening. Envelope narrowing (dropping a previously-supported arch) MUST go through a standard semver-major kailash-ml release with migration notes.

**Tier 2 tests (required).**

- `packages/kailash-ml/tests/integration/test_backend_compat_matrix_loads.py` — imports `load_compat_matrix()`, asserts `schema_version == 1`, asserts every backend in § 1 has an entry, asserts every entry's `supported_precision` is a subset of `{fp32, fp16, bf16, int8}`.
- `packages/kailash-ml/tests/integration/test_backend_compat_matrix_schema.py` — schema validator (pydantic / voluptuous / jsonschema) that asserts the YAML matches the Rule 1 schema; unknown top-level keys fail. Runs against a hand-crafted invalid YAML fixture to prove the validator rejects drift.
- `packages/kailash-ml/tests/integration/test_km_doctor_uses_compat_matrix.py` — runs `km-doctor --json`, asserts the output `compat_matrix` key matches the packaged YAML verbatim.

**BLOCKED rationalizations:**

- "Hardcoding in Python is fine; new archs are rare"
- "We can update the spec markdown instead"
- "YAML introduces a parser dependency"
- "One matrix source — the code — is simpler than two"

**Why:** Decision 6 approved 2026-04-21 says: "`backend-compat-matrix.yaml` as data in `packages/kailash-ml/data/backend-compat-matrix.yaml`. `km.doctor` subcommand reads it. Update without SDK release." Hardcoding the matrix forces an SDK release for every NVIDIA / AMD / Intel / Apple hardware generation — the exact constraint the decision rejected.

---

## 8. Error Hierarchy

### 8.1 Typed Exceptions

```python
# kailash_ml/backends/errors.py
# Canonical hierarchy: every backend error inherits from the canonical MLError
# family root per `ml-tracking.md §9.1` (CRIT-3). Multi-inherits RuntimeError
# so `except RuntimeError` call sites continue to work (0.x back-compat).
from kailash_ml.errors import MLError

class BackendError(MLError, RuntimeError):
    """Base class for all backend-selection errors. Canonical family root per CRIT-3."""

class BackendUnavailable(BackendError):
    """Requested backend is not present in the current environment."""
    # MUST carry: requested, detected_backends, install_hint, diagnostic_source

class UnsupportedFamily(BackendError):
    """The requested family cannot run on the requested backend."""
    # MUST carry: family, backend, supported_backends_for_family

class PrecisionUnsupported(BackendError):
    """The requested precision is not supported by the detected hardware."""
    # MUST carry: requested_precision, device_string, cuda_capability,
    #             supported_precisions, suggested_precision
```

### 8.2 MUST: Every Error Message Is Actionable

Every exception MUST include, at minimum:

1. What the user asked for (e.g., `prefer="xpu"`, `precision="bf16-mixed"`).
2. What the environment actually provides (detected backends, device capability).
3. The concrete fix (pip install hint, alternative precision, or "use prefer='auto' to let the resolver pick").

```python
# DO — actionable message
raise BackendUnavailable(
    f"Requested backend 'xpu' is not available. "
    f"Detected backends: {detected}. "
    f"Install Intel XPU support with: pip install kailash-ml[xpu]. "
    f"Or use prefer='auto' to let the resolver pick the best available backend."
)

# DO NOT — opaque message
raise BackendUnavailable("xpu not found")
```

**Why:** Every error thrown is a user's 5-minute debugging session OR a 5-second "ah, I know what to do next" moment. The actionable template turns the former into the latter.

### 8.3 MUST: Errors Do Not Echo Raw User Input Verbatim In Messages Bound For Logs

Per `rules/dataflow-identifier-safety.md` MUST Rule 2: error messages MUST NOT echo user-supplied strings verbatim when those messages will be logged. For backend errors, `prefer` is a small enum — safe to echo. For `precision` and family names, same. For anything accepting free-form strings (future extension), a fingerprint (`hash(...) & 0xFFFF`) MUST be used.

**Why:** Log poisoning / stored XSS via error messages is a recurring low-severity finding; prevention is cheap at the source.

---

## 9. Cross-SDK Alignment (EATP D6)

This spec's semantics are shared with `kailash-rs`. Implementation details differ; API shape and behavior match.

### 9.1 Shared (both SDKs MUST implement identically)

- The 6-backend enumeration (cpu, cuda, mps, rocm, xpu, tpu) and their priority order.
- `detect_backend(prefer=...)` returning an equivalent `BackendInfo` struct with the same fields.
- `resolve_precision(info, requested)` returning equivalent precision strings.
- The error hierarchy: `BackendUnavailable`, `UnsupportedFamily`, `PrecisionUnsupported`.
- `km.doctor()` equivalent (Rust: `kailash-ml-doctor` binary crate), with the same structured-JSON schema.
- `TrainingResult` fields: `backend`, `device_string`, `devices`, `precision`, `cuda_capability`.

### 9.2 Python-Specific

- Lightning `L.Trainer(accelerator=..., devices=..., precision=...)` wrapping.
- `torch.backends.mps.is_available()` / `torch.cuda.is_available()` / `torch_xla` probes.
- `intel-extension-for-pytorch` integration.
- `pytest.mark.gpu_{cuda,mps,rocm,xpu}` + `pytest.mark.tpu` markers.

### 9.3 Rust-Specific

- No Lightning. Analog: `burn::Trainer` (Rust-native) or `tch::train::Trainer` (torch bindings). The MUST clause of § 4.1 becomes "every `Trainer::new(..)` call passes accelerator/devices/precision as concrete values; custom training loops BLOCKED for new engines."
- **TPU is N/A-Rust.** `torch_xla` is Python-only. `BackendInfo` in Rust omits the tpu variant; `detect_backend(prefer="tpu")` MUST raise `BackendUnavailable` with a message naming the Python-only constraint.
- **MPS** supported via `tch::Device::Mps`.
- **ROCm** maps to `tch::Device::Cuda` (HIP is source-compatible with CUDA API at the torch-binding layer) with a runtime tag in `BackendInfo.rocm_version`.
- **XPU** in Rust goes through `ort` (ONNX Runtime) with the Intel EP for inference; training-time XPU support is OPEN QUESTION pending `burn`'s Intel backend.
- Markers: `#[cfg(feature = "gpu_cuda")]` / `#[cfg(feature = "gpu_mps")]` etc.

### 9.4 Cross-SDK Test Parity

Both SDKs MUST pass a shared test matrix encoded in `tests/integration/backends/_shared_contract.toml` that lists the expected `BackendInfo` fields per hardware class. Drift between SDKs on the shared contract is a cross-SDK issue per `rules/cross-sdk-inspection.md`.

**Why:** EATP D6 (independent implementation, matching semantics). A Python user reading a TrainingResult and a Rust user reading the same must see identical backend/precision strings.

---

## 10. Relationship To Other Rules

- `rules/zero-tolerance.md` Rule 1 — silent CPU fallback when a GPU is requested is a warning-grade silent failure; MUST log WARN and raise per § 2.3.
- `rules/zero-tolerance.md` Rule 2 — a `precision="auto"` passed unresolved into `L.Trainer()` is a stub per `BLOCKED: "auto" in TrainingResult` (§ 4.3).
- `rules/observability.md` § 5 — the WARN log `"training.backend.selected"` is mandatory per § 4.1.
- `rules/tenant-isolation.md` — `BackendInfo` does NOT carry tenant_id; tenant scoping is handled by engines (ModelRegistry, FeatureStore, etc.), not by the backend layer.
- `rules/orphan-detection.md` — `detect_backend()` and `resolve_precision()` MUST have production call sites inside the framework hot path (TrainingPipeline, InferenceServer, RLTrainer) within the same PR as this spec.
- `rules/framework-first.md` — the centralized `_backend.py` module IS the primitive; engines MUST NOT re-implement device detection.

---

## 11. RESOLVED — Prior Open Questions

All spec-lock questions are resolved. Cited decisions live in `workspaces/kailash-ml-audit/04-validate/approved-decisions.md`; Phase-B SAFE-DEFAULTs live in the round-2b open-tbd-triage file under `workspaces/kailash-ml-audit/04-validate/`.

| Original TBD                                  | Disposition                                                                                                                                                                                      | Reference                                                                        |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| ROCm / XPU / TPU runner availability          | Runner acquisition tracked as infra todo. CI promotion flipped lane-by-lane via the CI workflow file.                                                                                            | Decision 7; `workspaces/kailash-ml-audit/infra/gpu-runner-acquisition.md`; § 6.3 |
| MPS bf16 status                               | Default fp16; bf16 experimental behind `precision="bf16-mixed"` + `force=True`. Envelope pinned in `backend-compat-matrix.yaml` under `mps.experimental_precision`.                              | Decision 6; § 3.2; § 7.4                                                         |
| TPU first-class-ness                          | TPU remains first-class at 1.0.0. Compat envelope (`min_jax_tpu: "0.4"`, `supported_precision: [bf16, fp32]`) pinned in the matrix YAML; envelope changes ship as data, not SDK.                 | Decision 6; § 7.4                                                                |
| XPU via ipex vs native `torch.xpu`            | Both. Native-first dual-path resolver: `torch.xpu.is_available()` then `ipex` fallback on `ImportError` / `AttributeError`. `BackendInfo.xpu_via_ipex` reports which path resolved.              | Decision 5; § 2.2.1                                                              |
| ROCm bf16 cutoff (MI250 vs MI300)             | Data-driven via `backend-compat-matrix.yaml` `rocm.arch_allowlist`. Ship `gfx906/gfx908/gfx90a/gfx942` at 1.0.0; envelope widening ships via `kailash-ml-data` companion wheel (no SDK release). | Decision 6; § 7.4                                                                |
| CUDA bf16 probe (`is_bf16_supported()` vs CC) | Runtime probe via `torch.cuda.get_device_capability()` — the `BackendInfo.cuda_capability` field (§ 2.4) carries the (major, minor) tuple. Matrix YAML gates `cuda.min_compute: 7.0`.            | § 2.4; § 7.4                                                                     |

---

_End of draft. Target final location: `specs/ml-backends.md` after human classification per `rules/artifact-flow.md`. Companion file `specs/ml-engines.md` (§§ 1.3, 1.4, 1.7, 1.8) MUST be updated to reference this spec in the same commit the final `ml-backends.md` lands._
