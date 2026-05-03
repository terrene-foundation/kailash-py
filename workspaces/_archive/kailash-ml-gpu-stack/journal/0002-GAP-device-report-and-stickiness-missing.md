# GAP — DeviceReport + device-stickiness not in current kailash-ml

Date: 2026-04-19
Severity: HIGH (against the user's transparency + no-manual-config constraints)

## Summary

kailash-ml has `BackendInfo` and `detect_backend()` already — the
routing layer is solid. What's missing is the caller-facing
transparency contract:

1. **No `DeviceReport` on results.** `TrainingResult` and
   `Predictions` do not expose which device/backend/precision was
   actually used for the call. Users have to guess from log lines.
2. **No device stickiness.** `MLEngine.predict()` does not automatically
   migrate inputs to the model's device. A model trained on CUDA and
   predicted with a CPU-tensor input either silently copies (slow) or
   raises `RuntimeError: Expected all tensors to be on the same device`.
3. **No per-call INFO log with backend/device/precision.** Some families
   log this; others do not. The surface is inconsistent.

## Disposition

Add a frozen `DeviceReport(family, backend, device_string, precision,
fallback_reason, array_api)` dataclass to `trainable.py`. Extend
`TrainingResult` and `Predictions` to carry it. Require every
Trainable's fit/predict to emit one structured INFO log with matching
fields.

`MLEngine.predict()` migrates the input tensor to
`model.device_report.device_string` with a DEBUG log; mismatched
device input is the common case, not the error case.

## Evidence

- `packages/kailash-ml/src/kailash_ml/_device.py:132` — `BackendInfo`
  exists with the fields we need, just not exposed via results.
- `packages/kailash-ml/src/kailash_ml/_result.py` — `TrainingResult`
  dataclass has no device field today.
- `rules/observability.md §2` — every integration point MUST log
  intent + result + duration; call sites without this are gaps.

## Action items

- [ ] Add `DeviceReport` dataclass to `trainable.py`
- [ ] Extend `TrainingResult` with `device: DeviceReport`
- [ ] Extend `Predictions` with `device: DeviceReport`
- [ ] Audit every Trainable's `fit()` and `predict()` for a structured
      INFO log that includes the three fields
- [ ] Implement auto-migration in `MLEngine.predict()`
