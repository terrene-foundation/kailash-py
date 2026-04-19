---
type: DISCOVERY
date: 2026-04-20
created_at: 2026-04-20T00:30:00.000Z
author: co-authored
session_id: continue-session-2026-04-19
project: kailash-ml-gpu-stack
topic: Full-specs /redteam round caught cross-spec inconsistencies that ml-engines+ml-backends-only sweep missed
phase: redteam
tags:
  [
    redteam,
    specs-authority,
    cross-spec-consistency,
    ml-tracking,
    scope-discipline,
  ]
related_journal:
  [
    0004-RISK-torch-lightning-deviceReport-orphan.md,
    0005-GAP-predictions-device-field-missing.md,
  ]
---

# Discovery — full-specs sweep is structurally distinct from "specs I edited" sweep

## What happened

After the round-3 redteam-against-specs scope (which only verified `ml-engines.md` + `ml-backends.md` — the two specs I had just updated), the user explicitly asked: "do another /redteam against FULL specs and update specs as required." The full sweep caught two new findings that the narrow sweep missed:

1. **HIGH (cross-spec inconsistency)** — `ml-backends.md` repeatedly referenced `TrainingResult.backend`, `TrainingResult.devices`, `TrainingResult.cuda_capability` as if they were top-level `TrainingResult` fields (lines 267, 365, 500). None of these exist — the actual shape per `ml-engines.md` §4.1 is `{accelerator, device_used, precision, lightning_trainer_config}` plus the new `device: DeviceReport` envelope. The drift had been silently accumulating since the spec was first drafted; the Phase 1 work just made it more visible because the new `device` field absorbed what these flat fields were trying to express.

2. **MEDIUM (ml-tracking auto-capture gap)** — `ml-tracking.md` §2.4 mandatory auto-capture table listed `device_used` / `accelerator` / `precision` but not the new `TrainingResult.device: DeviceReport` fields. `ExperimentTracker.log_model(training_result=...)` is the reproducibility envelope; without capturing `fallback_reason` / `array_api` / `device.family` / `device.backend`, a run that "succeeded" with `fallback_reason="oom"` records as a normal CUDA run — exactly the bug the Phase 1 transparency contract was designed to prevent.

## Why the narrow sweep missed both

The narrow sweep was scoped to "specs I just edited" (ml-engines + ml-backends). That scope has a structural blind spot:

- **Cross-spec inconsistencies** between the spec I edited and a sibling spec I didn't touch are invisible. `ml-backends.md` claimed `TrainingResult.backend` exists; my edits to `ml-engines.md` defined the actual `TrainingResult` shape. The contradiction was only visible by comparing them.
- **Downstream specs that consume the changed surface** (here: `ml-tracking.md` consumes `TrainingResult.device` via `log_model(training_result=...)`) need updates too — but they're not part of "specs I edited."

## Lesson for future /redteam

A `/redteam` against specs MUST always scope to ALL specs in the project's domain (here: every `specs/ml-*.md` file), not just the specs the agent touched. Three categories of finding that only emerge from the full sweep:

1. **Field-shape divergence** — sibling specs reference the changed dataclass differently.
2. **Downstream consumer drift** — specs whose mandates depend on the changed surface are now stale.
3. **Cross-spec terminology drift** — the same concept named two ways across files.

The narrow scope is faster but produces false-confidence APPROVE verdicts. Future codify could add a `specs-authority.md` MUST clause: "Every spec edit triggers a re-derivation against the full sibling-spec set, not only the file edited."

## What landed

- Commit `cd9abde1` — ml-backends.md §4.3 + §5.1 + §6.6 + §9.1 rewritten around the actual `{accelerator, device_used, device: DeviceReport}` shape.
- Commit `cd9abde1` — ml-tracking.md §2.4 added 4 new auto-capture rows mapping `device_family` / `device_backend` / `device_fallback_reason` / `device_array_api` to their `TrainingResult.device.<X>` sources.
- Commit `11f31ba8` — ml-backends.md §5.7 + §5.8 added explicit `UMAPTrainable` / `HDBSCANTrainable` class names so spec-to-code grep can match directly.

Spec-to-code parity table (now 14/14 green):

- A1 ✓ 7/7 Trainables in `kailash_ml.__all__`
- A2 ✓ TrainingResult.device field exists
- A3 ✓ 7/7 return TrainingResult sites carry device=
- A4 ✓ 8 estimators in Array API allowlist
- A5 ✓ 3/3 sklearn fallback log keys present
- A6 ✓ \_is_gpu_oom_error helper + xgb/lgbm fallback log keys
- A7 ✓ UMAP + HDBSCAN cuml_eviction logs + fallback_reason
- A8 ✓ no [rapids] extra
- A9 ✓ Predictions.device deferred (matches 0.12.1 plan)
- A10 ✓ AST regression invariants pass
- A11 ✓ no dangling TrainingResult flat-field claims
- A12 ✓ ml-tracking auto-capture covers Phase 1 DeviceReport fields
- A14 ✓ round-2 re-verification — still no flat-field drift
- A15 ✓ Phase 1 surface in 3/3 ml-\* specs

## For Discussion

1. **Counterfactual**: If you had not pushed for the full-specs sweep, the 0.12.0 release would have shipped with a HIGH cross-spec inconsistency (ml-backends.md → ml-engines.md) plus a MEDIUM downstream-spec gap (ml-tracking.md). Both would have surfaced as confused user reports months later ("the docs say `TrainingResult.backend` but my IDE doesn't autocomplete it"). What's the systematic version of "ask the user to push back on my scope"?

2. **Data-referenced**: This /redteam round added 4 spec-coverage assertions (A11-A14) on top of the 10 from the prior round. The new ones came from the full-specs scope. Three rounds of /redteam, four findings each round. The asymptote is unclear; round 4 might find more or might find none. Question: is there a structural endpoint to /redteam, or does each round narrow the search but never reach zero?

3. **`rules/specs-authority.md` extension**: Should MUST 5 ("Spec files are updated at first instance") be extended with a sibling clause MUST 5b ("Every spec edit triggers a re-derivation against the full sibling-spec set in the same domain, not only the edited file")? The narrow-vs-full scope ambiguity in this round is the evidence base. Defer to next codify if the pattern recurs in another session.
