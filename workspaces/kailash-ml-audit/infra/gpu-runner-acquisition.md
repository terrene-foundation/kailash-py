# GPU Runner Acquisition — Foundation Infra Todo

**Owner:** Terrene Foundation infra backlog.
**Related spec:** `workspaces/kailash-ml-audit/specs-draft/ml-backends-draft.md §6.3` (Decision 7).
**Status:** PENDING — one row per backend lane.

Decision 7 (approved 2026-04-21) pins CPU + MPS as BLOCKING CI gates now. CUDA, ROCm, XPU, TPU flip from NON-BLOCKING to BLOCKING the day their respective runner lands. This file tracks the acquisition work that gates the promotion.

## Status per lane

| Lane   | Target runner                                           | Owner                  | Status  | Next step                                                                               |
| ------ | ------------------------------------------------------- | ---------------------- | ------- | --------------------------------------------------------------------------------------- |
| `cpu`  | GitHub hosted (`ubuntu-latest`)                         | n/a                    | LIVE    | BLOCKING today; no acquisition required.                                                |
| `mps`  | GitHub hosted (`macos-14` Apple Silicon)                | n/a                    | LIVE    | BLOCKING today; no acquisition required.                                                |
| `cuda` | Self-hosted NVIDIA (A10 / L4 / T4 class; ≥ compute 7.0) | Foundation infra       | PENDING | Vendor quote → budget approval → runner provisioning → workflow PR that flips to BLOCK. |
| `rocm` | Self-hosted AMD (MI210 / MI250 / MI300)                 | Foundation infra       | PENDING | Scope after CUDA lane lands — lower priority per installed-base share.                  |
| `xpu`  | Self-hosted Intel (PVC / Arc)                           | Foundation infra       | PENDING | Scope after ROCm lane lands — narrow installed base at 1.0.0 timeframe.                 |
| `tpu`  | Google TPU VM (v4 preferred)                            | Foundation infra + GCP | PENDING | GCP project provisioning → per-run cost budget → workflow PR that flips to BLOCK.       |

## Promotion protocol

When a runner lands:

1. Land the runner registration PR against `.github/workflows/ml-backends.yml` (the workflow file IS the per-lane gate).
2. In the SAME PR, flip the lane's `continue-on-error` from `true` to `false` (or equivalent "blocking" flag).
3. In the SAME PR, update `ml-backends.md §6.3` table row from "NON-BLOCKING" to "BLOCKING" with the PR number.
4. Do NOT flip the promotion for any lane whose runner has not landed — `rules/zero-tolerance.md` Rule 2 (no stubs) blocks claiming a gate that doesn't actually fail on red.

## Related rules

- `rules/zero-tolerance.md` Rule 2 — no claiming a blocking CI gate that doesn't actually block.
- `rules/framework-first.md` — `km.doctor` is the primitive for hardware detection across every lane.
- `workspaces/kailash-ml-audit/04-validate/approved-decisions.md` Decision 7 — source of truth.
