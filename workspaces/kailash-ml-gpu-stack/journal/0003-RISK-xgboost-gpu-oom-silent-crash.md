# RISK — XGBoost GPU OOM does not fall back to CPU

Date: 2026-04-19
Severity: HIGH

## Summary

XGBoost 3.0 raises `xgboost.core.XGBoostError` on GPU OOM rather than
spilling or falling back to CPU. Without explicit handling in
`XGBoostTrainable`, a user whose training data fits RAM but not VRAM
sees a noisy crash instead of the "graceful CPU fallback" the user
constraint requires.

## Disposition

Wrap the `booster.fit()` call in `XGBoostTrainable` with a try/except
on `xgboost.core.XGBoostError`; on OOM detection (error message
contains `out of memory` or `cudaErrorMemoryAllocation`), re-invoke
the same fit on CPU with a structured WARN log:

```
xgboost.fit.fallback reason=cuda_oom original_device=cuda:0
  fallback_device=cpu n_rows=N n_features=F
```

Record the fallback in `DeviceReport.fallback_reason="cuda_oom"` so
the caller sees it in `TrainingResult.device`.

The same pattern applies to LightGBM (CUDA OOM path) and any future
torch-native family. The pattern goes in a shared helper
`_device_fallback.py`.

## Evidence

- User constraint C3: "auto-detect + CPU fallback".
- No grep hits for `XGBoostError` in `trainable.py` today.
- XGBoost 3.0 `device="cuda"` behavior on OOM is "raise and abort" per
  upstream docs.

## Action items

- [ ] Add `_device_fallback.py` helper with `try_device_fall_back_on_oom(...)`
- [ ] Wrap `XGBoostTrainable.fit()` with the helper
- [ ] Wrap `LightGBMTrainable.fit()` with the helper
- [ ] Regression test: simulate OOM (e.g. via torch env var or mock) and
      assert the result reports `fallback_reason="cuda_oom"` + uses CPU
