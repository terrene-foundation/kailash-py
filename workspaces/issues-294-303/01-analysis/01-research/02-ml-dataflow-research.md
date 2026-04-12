# Research: ML (#295) and DataFlow (#296)

## Issue #295: DataExplorer Correlation NaN Guards

### Confirmed Gaps

| Method              | File                      | Line | Current                                  | Fix                                                 |
| ------------------- | ------------------------- | ---- | ---------------------------------------- | --------------------------------------------------- |
| \_compute_pearson   | data_explorer.py          | 709  | `float(val) if val is not None else 0.0` | Add `math.isfinite()` guard                         |
| \_compute_spearman  | data_explorer.py          | 729  | Same pattern                             | Same fix                                            |
| \_compute_cramers_v | data_explorer.py          | 797  | `float(np.sqrt(...))` — no guard         | Add `math.isfinite()` guard                         |
| \_matrix_table      | \_data_explorer_report.py | 391  | `.2f` renders "nan" as text              | Already guarded by \_corr_color, fix source instead |

### Pattern to Follow (skewness/kurtosis — same file, lines 458-472)

```python
skew_val = float(np.mean(centered**3))
base.skewness = skew_val if math.isfinite(skew_val) else 0.0  # ✅
```

### Missing Tests

- No test for constant-column correlation (produces NaN)
- No test for zero-variance columns
- No Cramer's V edge case tests

### Additional Gaps Found

1. `_generate_alerts()` (lines 913-923) doesn't guard NaN in correlation threshold check — NaN comparison returns False silently (benign but sloppy)
2. `fill_null(0.0)` before correlation changes correlation values — known limitation, not a bug

---

## Issue #296: DataFlow bulk_upsert

### Critical Finding: Method Missing

`bulk_upsert()` does **not exist** as a method in Express API. The WRITE_OPERATIONS constant lists 8 operations but only 7 are implemented:

| Operation   | Async | Sync | Events | Status      |
| ----------- | ----- | ---- | ------ | ----------- |
| create      | ✅    | ✅   | ✅     | Complete    |
| update      | ✅    | ✅   | ✅     | Complete    |
| delete      | ✅    | ✅   | ✅     | Complete    |
| upsert      | ✅    | ✅   | ✅     | Complete    |
| bulk_create | ✅    | ✅   | ✅     | Complete    |
| bulk_update | ✅    | ❌   | ✅     | No sync     |
| bulk_delete | ✅    | ✅   | ✅     | Complete    |
| bulk_upsert | ❌    | ❌   | ❌     | **MISSING** |

`upsert_advanced()` exists and already emits events as "upsert" — this is a separate method, not a bulk operation.

### Implementation Required

1. **Async `bulk_upsert()`** — accepts list of records with conflict resolution
2. **Sync `bulk_upsert()`** — wrapper via `_run_sync()`
3. **Event emission** — `_emit_write_event(model, "bulk_upsert", record_id=None)`
4. **Test** — verify event emission and correct bulk upsert behavior

### Event Emission Pattern (all write ops follow this)

```python
# TSG-201: Emit write event
if hasattr(self._db, "_emit_write_event"):
    self._db._emit_write_event(model, "operation_name", record_id=None)  # None for bulk
```
