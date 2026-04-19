---
type: RISK
date: 2026-04-19
created_at: 2026-04-19T22:50:00.000Z
author: agent
session_id: continue-session-2026-04-19
project: kailash-ml-gpu-stack
topic: TorchTrainable + LightningTrainable shipped without DeviceReport wire-up — caught by /redteam, fixed pre-merge
phase: redteam
tags: [orphan-detection, transparency-contract, deviceReport, redteam, phase-1]
related_journal: [0002-GAP-device-report-and-stickiness-missing.md]
---

# Round-3 redteam — Torch + Lightning Trainables shipped without DeviceReport

## What was found

The `/redteam` spec-compliance audit on `feat/ml-gpu-phase1-integration` found that `TorchTrainable.fit` (line 889) and `LightningTrainable.fit` (line 1023) returned `TrainingResult` WITHOUT populating the `device=DeviceReport(...)` field, despite the round-1 spec at `04-validate/02-revised-stack.md` § "Transparency contract" stating:

> This lands on:
> - TrainingResult.device — every fit returns one
> - Predictions.device — every predict returns one

Pre-redteam grep counts:
```
return TrainingResult sites: 7
device= kwarg sites:         5  ← 2 orphans
```

The two missing sites were the DL-spine families (Torch + Lightning), which were assumed-already-done because the punch list explicitly covered items 3/4/5/7/8 (sklearn array-API, xgboost/lightgbm OOM, UMAP/HDBSCAN, Tier 2 tests, [rapids] removal) — but the spec mandate "every fit returns one" applies to ALL 7 family adapters, not just the 5 explicitly named.

This is the same orphan failure mode `rules/orphan-detection.md` §1 describes at the class level, scoped down to the field level: a public spec promise (`TrainingResult.device`) wired into the framework's hot path for 5 of 7 families and silently un-wired for 2.

## Why it slipped past the round-3 reviewer

The reviewer agent's APPROVE-WITH-MINOR-FIXES verdict listed H1 as "missing test for `array_api_runtime_unavailable` fallback" but did not flag the missing Torch/Lightning device wire-up. The reviewer's check was scoped to the diff (which added DeviceReport to the 5 NEW family adapters), not the absolute state of every TrainingResult call site. The mechanical AST sweep `grep -c "return TrainingResult(" + grep -cE "device=DeviceReport"` would have caught it in seconds; the reviewer didn't run it.

Lesson: gate-level reviewers verify the diff; `/redteam` re-verifies the absolute state. Both are necessary; neither is sufficient alone.

## Fix

Same-PR fix on `feat/ml-gpu-phase1-integration` commit `1e233dcd`:
- TorchTrainable.fit now constructs DeviceReport from the resolved Lightning context (no eviction/OOM fallback path — native multi-backend via L.Trainer per ml-backends.md §5.4).
- LightningTrainable.fit — same pattern.
- New regression test at `tests/regression/test_trainable_device_report_invariant.py` mechanically asserts every `TrainingResult(...)` constructor in trainable.py carries `device=`. Future refactors that drop the kwarg fail loudly at AST parse time.

Post-fix counts:
```
return TrainingResult sites: 7
device= kwarg sites:         7  ← parity
```

## Consequences

- 0.12.0 release ships with the full transparency contract for `TrainingResult.device` across all 7 family adapters, not 5 of 7.
- The regression invariant test prevents the next session from silently dropping the field via refactor.

## Outstanding

- `Predictions.device` field is still missing from the `Predictions` class entirely (see journal 0005-GAP). Out of scope for 0.12.0; tracked for 0.12.1.

## For Discussion

1. **Counterfactual**: If `/redteam` had not been run, the 0.12.0 wheel would have shipped with TorchTrainable + LightningTrainable returning `TrainingResult.device = None`. Downstream consumers of the GPU-first transparency surface would silently fail to distinguish actual-CUDA-execution from fell-back-to-CPU for the two DL-spine families — exactly the failure mode the Phase 1 spec was designed to prevent.

2. **Data-referenced**: The reviewer agent ran in 5 minutes and produced a 5-finding report. The mechanical `/redteam` check that surfaced this finding ran in 4 seconds (two grep calls). What is the right division of labor between LLM-judgment review and mechanical AST/grep audit? Hypothesis: the mechanical sweep should be the FIRST gate (redteam phase 1), and the LLM reviewer should run AFTER it on the diff that's been mechanically pre-cleared.

3. **Scope-creep counter-question**: Shard B's agent scope-crept into Shard A's territory (helpfully — caught a missing impl). But three of three agents missed the Torch/Lightning device wire-up because none was instructed to look at it. Should the task decomposition for parallel shards include a "spec-completeness check" todo that explicitly enumerates EVERY TrainingResult call site, not just the ones touched by the in-scope items?
