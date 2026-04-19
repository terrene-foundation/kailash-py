---
type: GAP
date: 2026-04-19
created_at: 2026-04-19T22:55:00.000Z
author: agent
session_id: continue-session-2026-04-19
project: kailash-ml-gpu-stack
topic: Predictions class has no device field; spec says "every predict returns one"
phase: redteam
tags: [transparency-contract, deviceReport, predictions, gap, phase-1, follow-up]
related_journal: [0002-GAP-device-report-and-stickiness-missing.md, 0004-RISK-torch-lightning-deviceReport-orphan.md]
---

# `Predictions.device` field missing — spec violation, deferred to 0.12.1

## What the spec requires

`workspaces/kailash-ml-gpu-stack/04-validate/02-revised-stack.md` § "Transparency contract" lines 54-78:

> Every call returns (or carries) a `DeviceReport`:
> ```
> @dataclass(frozen=True)
> class DeviceReport: ...
> ```
>
> This lands on:
> - TrainingResult.device — every fit returns one
> - Predictions.device — every predict returns one  ← THIS
> - km.device() — top-level helper

## What ships in 0.12.0

`Predictions` (defined at `packages/kailash-ml/src/kailash_ml/trainable.py:128`) has only:

```python
class Predictions:
    __slots__ = ("_raw", "_column")
    def __init__(self, raw: Any, *, column: str = "prediction") -> None: ...
    @property
    def raw(self) -> Any: ...
    @property
    def column(self) -> str: ...
    def to_polars(self) -> pl.DataFrame: ...
```

No `device` field. No `device` property. None of the 7 `predict()` methods construct or carry a DeviceReport.

## Scope decision for 0.12.0

Wiring `Predictions.device` requires:

1. New `device: Optional[DeviceReport]` field on `Predictions` (with backwards-compat optional default for callers that already construct it).
2. Update all 7 `Trainable.predict()` methods to construct and pass a DeviceReport (similar pattern to fit).
3. Predictions tests for every family verifying `pred.device` populated correctly.
4. Update `Predictions.__slots__` to include `_device`.

This is ~40 LOC of code + ~150 LOC of tests + a structural API change to a public class. It's a bounded shard but distinctly bigger than the post-redteam HIGH-1 fix (which was 30 LOC + 100 LOC test).

**Decision**: defer to 0.12.1. The 0.12.0 release ships the FIT half of the transparency contract complete (7/7 families) and the PREDICT half delegated to 0.12.1.

## Consequences

- 0.12.0 release notes MUST disclose that the predict-half of the transparency contract is incomplete. CHANGELOG `Known Limitations` section needed.
- Downstream callers cannot programmatically distinguish a CUDA-resolved predict from a CPU-fallback predict in 0.12.0. They CAN inspect `result.device` from the prior fit — sufficient for the common case where predict runs immediately after fit, insufficient for callers that round-trip the model through serialization.

## Plan for 0.12.1

1. Add `device: Optional[DeviceReport] = None` to `Predictions.__init__` and `__slots__`.
2. Update each Trainable.predict() to construct DeviceReport mirroring the fit-time call (cache `self._last_device_report` from fit, return it from predict).
3. Add `tests/regression/test_predictions_device_invariant.py` — AST sweep asserting every `Predictions(...)` constructor in trainable.py carries `device=` (the same shape as the new TrainingResult invariant landed in 0.12.0).
4. Tier 2 backend-matrix test additions for predict-time device assertions.

Estimated capacity: 1 session shard, ~200 LOC total, single-file edits + tests.

## For Discussion

1. **Counterfactual**: If 0.12.0 had attempted to wire Predictions.device too, would the parallel-shard experiment have failed harder? Likely yes — predict() is per-family, so a 6th shard would have been needed (or one of the existing 3 would have scope-crept further). The deferral is the right call given the parallel-execution mode this session ran in.

2. **Data-referenced**: How many downstream consumers actually need `Predictions.device`? Aether and aegis, the two known consumers, currently use TrainingResult fields immediately after fit. The Predictions surface is more relevant for inference-server scenarios (kailash-ml's `InferenceServer` engine) where predicts run hours/days after fit and the device may have changed. That's the audience to prioritize for 0.12.1.

3. **Should the regression invariant test land in 0.12.0?** Argument for: the test would assert "no Predictions(...) with device= today" — it would fail until 0.12.1 lands the field. Argument against: an always-failing test is worse than no test. Decision: land the assertion test ALONGSIDE the 0.12.1 implementation, not before.
