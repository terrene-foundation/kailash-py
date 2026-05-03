# RISK — cuML optional extra breaks first-class GPU semantics

Date: 2026-04-19
Severity: CRITICAL (against the user's constraints)

## Summary

A GPU research report proposed keeping NVIDIA cuML as an
installable `kailash-ml[rapids]` extra to cover UMAP / HDBSCAN /
t-SNE because "no equivalent exists". This contradicts the user's
"seamless, GPU-first, no-manual-config, first-class" constraints:

- Users on Apple MPS / AMD ROCm / Intel XPU get no GPU path for those
  three algorithms — silent fall to CPU.
- `[rapids]` extra means users who install the default package get
  ImportError on a public API surface, contradicting "first-class".
- Every CUDA version bump in the upstream cuML wheel forces a
  kailash-ml release — re-introducing the "RAPIDS is a bridge layer"
  pain the user originally fled.

## Disposition

Phase 1 (immediate): evict `[rapids]` extra. Replace cuML UMAP with
`umap-learn` (CPU) and cuML HDBSCAN with `sklearn.cluster.HDBSCAN`
(CPU). Document the NVIDIA speed regression explicitly; users who
need cuML speed install it themselves and register a custom
Trainable.

Phase 2 (6-12 months): torch-native UMAP implementation. Algorithm
is ~2000 LOC, every primitive (k-NN graph, sparse edge matrix,
cross-entropy optimizer) has a 5-50 LOC torch equivalent. Target:
within 2× of cuML on NVIDIA, runnable on MPS/ROCm/XPU/CPU.

Phase 3 (12-18 months): torch-native HDBSCAN (~500 LOC).

## Evidence

- Original report recommended `kailash-ml[rapids]` extra for 3
  algorithms.
- `packages/kailash-ml/src/kailash_ml/_device.py:35` already supports
  `cuda, mps, rocm, xpu, tpu, cpu` as equal-priority backends — the
  framework contract says "all accelerators are first class."
- cuML coverage limits mean the extra would satisfy only NVIDIA
  customers.

## Action items

- [ ] Delete `[rapids]` extra from `packages/kailash-ml/pyproject.toml`
- [ ] Add `UMAPTrainable` + `HDBSCANTrainable` using CPU-native libraries
- [ ] File follow-up issue for Phase 2 torch-native UMAP R&D track
