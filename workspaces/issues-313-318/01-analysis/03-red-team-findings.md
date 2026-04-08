# Red Team Findings

## Critical (Must Fix Before Implementation)

### C1: #316 — 29 files import from deprecated coordination module

The plan says "clean up deprecated module" but 29 files still import from it:

- 6 test files under `tests/unit/agents/coordination/`
- ~15 example files under `examples/coordination/`
- 1 benchmark file `benchmarks/suite7_multi_agent.py`

**Resolution**: Migrate all 29 importers to use `kaizen_agents.patterns.patterns` before removing the deprecated module. Or: keep the deprecated module one more release (to 0.7.0) with a louder warning, and include a CHANGELOG entry for the breaking change.

### C2: #317 — Factory method creates connection leak

`ExperimentTracker.create()` would internally create a `ConnectionManager`, but ExperimentTracker has no `close()` method. This leaks database connections.

**Resolution**: Add lifecycle management to ExperimentTracker:

1. Track whether connection is owned (`self._owns_conn = True` for factory, `False` for direct init)
2. Add `async def close()` that closes the connection only when owned
3. Add `__aenter__`/`__aexit__` for context manager support
4. Factory user flow: `async with await ExperimentTracker.create(...) as tracker:`

### C3: #317 — README context manager bug misidentified

The README uses `async with tracker.start_run(...)` but `start_run()` is NOT a context manager. The correct method is `tracker.run()` (line 411). Analysis caught wrong param types but missed the wrong method name.

**Resolution**: Fix README to use `tracker.run()` instead of `async with tracker.start_run()`.

## Important (Should Fix in Current Session)

### I1: #313 — `inverse_transform()` with mixed encoding unspecified

`inverse_transform()` at line 324 only handles inverse scaling. When mixed encoding is used (some columns onehot, some ordinal due to cardinality guard), behavior is undefined.

**Resolution**: Document limitation — cardinality-downgraded ordinal columns can be inversed, onehot columns cannot (this is already true for pure onehot).

### I2: #313 — Edge case: `max_cardinality` with target encoding

Does the cardinality guard apply only to `categorical_encoding="onehot"`, or also to `"target"`?

**Resolution**: Only apply to `"onehot"` — target encoding produces exactly one column per feature regardless of cardinality (it's already cardinality-safe).

### I3: #313 — `SetupResult.transformers` structure is public

`SetupResult` exposes `transformers=dict(self._transformers)`. Changing the internal structure changes this public interface.

**Resolution**: Maintain backward compatibility — keep `onehot_mappings` key containing only the columns that were actually onehot-encoded. Add `ordinal_overflow_mappings` as a new key for cardinality-downgraded columns.

### I4: #313 — Missing test scenarios

- All categorical columns exceed `max_cardinality` → pure ordinal fallback
- `exclude_columns` with non-categorical column → silently ignore
- `exclude_columns` with nonexistent column → raise ValueError
- `categorical_encoding="target"` combined with `max_cardinality` → guard should not apply

### I5: PR structure revision

#313 (behavioral change) should be its own PR for clean git bisect.

Revised PR structure:

- **PR-1**: #315 + #318 (trivial: y_label param + ParamDistribution docs)
- **PR-2**: #314 + #317 (new methods: EDA charts + ExperimentTracker factory + README fixes)
- **PR-3**: #313 (behavioral change: cardinality guard)
- **PR-4**: #316 (kaizen-agents: pattern exports + coordination cleanup)

### I6: Cross-SDK note

kailash-rs does not have kailash-ml or kaizen-agents packages. These are Python-only. #308 is the only cross-SDK issue and is tracking-only. No cross-SDK action needed for #313-318.

## Minor (Track, Can Defer)

### M1: #314 — Mixed plotly.express/graph_objects in ModelVisualizer

Existing methods use `go`, new EDA methods will use `px`. Functional but stylistically inconsistent. Add a class docstring note explaining the two patterns.

### M2: #316 — Broken a2a imports in benchmark

`suite7_multi_agent.py` imports from non-existent `a2a` sub-module. Pre-existing, unrelated to #316.

### M3: #316 — Deprecation warning has wrong import path

Line 46 says `kaizen.orchestration.patterns` but should say `kaizen_agents.patterns.patterns`. Fix as part of #316 work.

## Convergence

All critical findings have clear resolutions. No gaps remain that would block implementation. Analysis is approved with the amendments above.
