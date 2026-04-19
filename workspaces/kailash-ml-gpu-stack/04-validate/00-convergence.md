# Convergence — kailash-ml GPU stack redteam

Date: 2026-04-19
Status: **NOT CONVERGED — 1 CRITICAL + 5 HIGH findings remediated in design,
but NOT yet in code.**

## Rounds

- Round 1: `01-redteam-round1.md` — 1 CRITICAL, 5 HIGH, 2 MEDIUM, 1 LOW
- Round 2: `02-revised-stack.md` — every finding has a concrete remediation
  and lives in the revised stack design.

## What the original report got right

- Identifying that RAPIDS-as-bridge is obsolete and the ecosystem has
  converged on Array API + torch as the multi-accelerator substrate.
- Recommending XGBoost 3.0 over cuML-RF for tree models.
- Recommending Polars/Narwhals for preprocessing.
- Identifying ONNX ML opset + Treelite as the serialization primitives.

## What the original report got wrong (and this redteam corrects)

1. **Proposed cuML as an optional `[rapids]` extra.** This contradicts
   "first-class GPU everywhere". Fix: evict cuML entirely; use
   CPU-native UMAP/HDBSCAN today, build torch-native implementations
   over 12-18 months.
2. **Treated Array API as a user-visible config.** Users would have
   had to write `with sklearn.config_context(array_api_dispatch=True):`
   — violating "no manual config". Fix: wrap this inside
   `SklearnTrainable`, invisible to callers.
3. **Didn't specify OOM fallback.** XGBoost GPU OOM would crash, not
   fall back. Fix: shared `try_device_fall_back_on_oom` helper.
4. **Excluded RL and DL from the analysis.** User constraint says
   seamless across ml/dl/rl. Fix: unified on torch substrate;
   `rl/trainer.py` audited to route through `detect_backend`.
5. **No device-stickiness or transparency contract.** Users would have
   had to infer device from log lines. Fix: `DeviceReport` attached
   to every `TrainingResult` and `Predictions`.
6. **Serialization fan-out (three formats).** Maintenance burden too
   high. Fix: ONNX primary + torch.save secondary, Treelite as
   optional extra.

## The converged architecture (short form)

```
User code
  ↓ no device=, no family= required
km.MLEngine / km.RLEngine
  ↓ TrainingContext with resolved backend
Trainable adapters (sklearn, xgboost, lightgbm, torch, lightning, rl, umap, hdbscan)
  ↓ inject device= / device_type= / accelerator= into library calls
km._device.detect_backend()
  ↓ priority: cuda > mps > rocm > xpu > tpu > cpu
torch (the one substrate) + polars (the one preprocessing library)
```

Every fit/predict returns a `DeviceReport`. Every GPU→CPU fallback
emits a WARN and records `fallback_reason`. Every family either
accepts what `detect_backend` resolved or raises `UnsupportedFamily`.

## Answer to "can we re-engineer it ourselves better?"

**Yes — and most of the substrate is already in kailash-ml.**

The existing `_device.py` + `trainable.py` + `rl/` layout is ~80% of
the architecture this redteam arrives at. What's missing is the
remediation list:

1. Evict `[rapids]` extra. (~1 hour of work)
2. Add `DeviceReport` + device-stickiness. (~3 hours)
3. Sklearn Array API auto-wrapping + allowlist. (~1 day)
4. OOM fallback helper + XGBoost/LightGBM wiring. (~3 hours)
5. RL device routing audit. (~2 hours)
6. CPU-native UMAP/HDBSCAN adapters (Phase 1). (~3 hours)
7. Top-level `km.device()` + `km.use_device(...)` helpers. (~2 hours)
8. Regression tests per family per available backend. (~1 day)

**Total: ~3 focused sessions** to land the transparent, GPU-first,
auto-detect, no-config, first-class surface.

R&D track (torch-native UMAP/HDBSCAN) is a 6-18 month
parallel effort that doesn't block anything else.

## Journal entries

- `journal/0001-RISK-cuml-optional-extra-breaks-first-class.md`
- `journal/0002-GAP-device-report-and-stickiness-missing.md`
- `journal/0003-RISK-xgboost-gpu-oom-silent-crash.md`

## Convergence criteria (per /redteam contract)

| Criterion                         | Status                                                                                    |
| --------------------------------- | ----------------------------------------------------------------------------------------- |
| 0 CRITICAL findings               | **OPEN** — CRITICAL-1 cuML eviction is design-only until Phase 1 implementation lands     |
| 0 HIGH findings                   | **OPEN** — 5 HIGH, all design-remediated but not coded                                    |
| 2 consecutive clean rounds        | **NOT MET** — round 1 is redteam, round 2 is design; round 3 would be post-implementation |
| 100% spec compliance via AST/grep | N/A — spec is a research report, not shipped code                                         |
| New code has new tests            | N/A for this phase — see action items in `02-revised-stack.md`                            |
| Frontend: 0 mock data             | N/A — no frontend in this phase                                                           |

**Convergence requires a follow-up implementation session** that
executes the 8 action items and produces round 3 with ≥2 clean
consecutive audits over actual code.

## Recommendation to user

1. **Ship the design** (this redteam + revised stack) as the
   architecture doc for the next implementation sprint.
2. **Open a follow-up GitHub issue** titled `kailash-ml: first-class
GPU surface (evict cuML, add DeviceReport, auto-detect)` that
   references this workspace and lists the 8 action items as
   acceptance criteria.
3. **Schedule one implementation session** (~3x /implement + /redteam
   cycles) to land Phase 1 (everything except torch-native
   UMAP/HDBSCAN).
4. **Schedule Phase 2 separately** — torch-native UMAP is 6+ months
   of R&D and benefits from being isolated from the substrate
   landing work.
