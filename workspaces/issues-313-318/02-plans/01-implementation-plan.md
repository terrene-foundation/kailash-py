# Implementation Plan — Issues #313–#318 (Revised After Red Team)

## Execution Strategy

6 independent issues, no inter-dependencies. Maximum parallelization.

**Estimated effort**: 1 session (all 6 issues).

## PR Structure (Revised — per red-team finding I5)

4 PRs for clean bisectability and manageable review:

| PR   | Issues     | Scope                                                              | Risk   |
| ---- | ---------- | ------------------------------------------------------------------ | ------ |
| PR-1 | #315, #318 | Trivial: y_label param + ParamDistribution docs/alias              | None   |
| PR-2 | #314, #317 | New methods: EDA charts + ExperimentTracker factory + README fixes | Low    |
| PR-3 | #313       | Behavioral change: cardinality guard                               | Medium |
| PR-4 | #316       | kaizen-agents: pattern exports + coordination migration            | Low    |

## Issue Implementation Details

### PR-1: #315 + #318 (trivial)

#### #315 — training_history y_label

- Add `y_label: str = "Value"` param after `x_label` in `training_history()` signature
- Change line 614: `yaxis_title="Value"` → `yaxis_title=y_label`
- Add `test_custom_y_label` test
- **Files**: `model_visualizer.py`, `test_model_visualizer.py`

#### #318 — ParamDistribution type field

- Expand docstring: document all 4 valid `type` values, note builtin shadowing
- Add `@property def distribution(self) -> str` read-only alias (safe — custom `to_dict()`, no `dataclasses.asdict()`)
- Fix fabricated README SearchSpace example (wrong fields: `model_class`, `framework`, `parameters`, `values`)
- Add test for `distribution` property
- **Files**: `hyperparameter_search.py`, `test_hyperparameter_search.py`, `README.md`

### PR-2: #314 + #317 (new methods)

#### #314 — ModelVisualizer EDA charts

- Add 3 methods accepting `pl.DataFrame` + column names, returning `go.Figure`:
  - `histogram(data, column, *, bins=30, title=None)`
  - `scatter(data, x, y, *, color=None, title=None)`
  - `box_plot(data, column, *, group_by=None, title=None)`
- Use `plotly.express` internally (reference DataExplorer patterns)
- Add class docstring note: existing methods accept arrays, EDA methods accept DataFrames
- Write tests per method (positive, edge cases, missing columns)
- **Files**: `model_visualizer.py`, `test_model_visualizer.py`

#### #317 — ExperimentTracker standalone usage (with red-team fixes C2, C3)

- Add `@classmethod async def create(cls, url, artifact_root)` factory
- Add lifecycle management (red-team C2):
  - `self._owns_conn: bool` — True for factory, False for direct init
  - `async def close()` — closes connection only when owned
  - `__aenter__`/`__aexit__` for `async with` support
- Fix README bugs:
  - Remove `await tracker.initialize()` (doesn't exist)
  - Change `async with tracker.start_run(...)` → `tracker.run()` (red-team C3)
  - Fix `start_run` args (takes `experiment_name: str`, not experiment ID)
  - Fix `list_runs` params (no `order_by`/`ascending`)
- Write factory lifecycle test (create → experiment → run → log → close)
- **Files**: `experiment_tracker.py`, `test_experiment_tracker.py`, `README.md`

### PR-3: #313 (behavioral change)

#### #313 — PreprocessingPipeline cardinality guard

- Add params to `setup()`: `max_cardinality: int = 50`, `exclude_columns: list[str] | None = None`
- In `_encode_categoricals()`: check cardinality before dispatching (onehot only — target encoding is already cardinality-safe per red-team I2)
- Columns exceeding threshold → ordinal with `logger.warning()`
- Storage: keep `onehot_mappings` for low-cardinality columns, add `ordinal_overflow_mappings` for high-cardinality (preserves `SetupResult.transformers` backward compat per red-team I3)
- Update `_apply_fitted_encoding()` to apply both mapping types
- `inverse_transform()`: document limitation (red-team I1)
- **Tests** (per red-team I4):
  - High-cardinality auto-downgrade to ordinal
  - All columns exceed threshold → pure ordinal
  - `exclude_columns` with non-categorical column → silently ignore
  - `exclude_columns` with nonexistent column → raise ValueError
  - `categorical_encoding="target"` + `max_cardinality` → guard does not apply
  - Existing 3-category tests unaffected by default threshold
- **Files**: `preprocessing.py`, `test_preprocessing.py`

### PR-4: #316 (kaizen-agents)

#### #316 — Export pattern classes (with red-team fixes C1, M3)

- Add try/except imports for 5 pattern classes + 5 factory functions to `kaizen_agents/__init__.py`
- Re-export through `patterns/__init__.py` to fix middle-layer gap
- Add to `__all__`
- Migrate 29 importers from deprecated `agents/coordination/` to `kaizen_agents.patterns.patterns` (red-team C1):
  - 6 test files under `tests/unit/agents/coordination/`
  - ~15 example files under `examples/coordination/`
  - 1 benchmark file
- Fix deprecation warning message: `kaizen.orchestration.patterns` → `kaizen_agents.patterns.patterns` (red-team M3)
- Remove deprecated `agents/coordination/` module after migration
- Write import tests for all new top-level exports
- **Files**: `__init__.py`, `patterns/__init__.py`, `agents/coordination/`, test files, example files

## Cross-SDK Note

kailash-rs does not have kailash-ml or kaizen-agents packages. #313-318 are Python-only. #308 is tracking-only — no action needed this session.

## Validation

- Run full test suite per package after each PR
- Verify all 6 issues can be closed with `Fixes #N` in PR descriptions
- #308 remains open (tracking)
