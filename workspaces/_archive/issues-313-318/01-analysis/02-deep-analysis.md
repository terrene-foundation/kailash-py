# Deep Analysis — Issues #313–#318

## #313 (P1): PreprocessingPipeline Cardinality Guard

### Current Code State

- **File**: `packages/kailash-ml/src/kailash_ml/engines/preprocessing.py`
- **`setup()` signature**: line 137–149
- **`_onehot_encode()`**: line 469–498 — iterates all unique values unconditionally
- **`_apply_fitted_encoding()`**: line 565–610 — assumes uniform encoding strategy across all columns

### Root Cause

`_onehot_encode()` at line 483 collects `categories = result[col].drop_nulls().cast(pl.Utf8).unique().sort().to_list()` with zero upper bound. A column with 50k unique values produces 50k new columns.

### Key Complexity

The current architecture assumes a single global encoding strategy. `_apply_fitted_encoding()` uses `elif` branching (lines 569/583/596) between onehot, ordinal, and target mappings — mutually exclusive. Supporting per-column mixed encoding (onehot for low-cardinality, ordinal for high-cardinality) requires refactoring this storage.

### Implementation Path

1. Add `max_cardinality: int = 50` and `exclude_columns: list[str] | None = None` to `setup()`
2. In `_encode_categoricals()`, check cardinality before dispatching. Columns exceeding threshold → ordinal with `logger.warning()`
3. Store per-column encoding type in `self._transformers` alongside mappings
4. Update `_apply_fitted_encoding()` to apply both onehot and ordinal mappings when mixed
5. Existing tests use 3 categories — unaffected by default threshold of 50

---

## #314 (P1): ModelVisualizer EDA Charts

### Current Code State

- **File**: `packages/kailash-ml/src/kailash_ml/engines/model_visualizer.py`
- 9 existing methods (lines 62–616), all post-training diagnostics
- Uses `plotly.graph_objects` for manual figure construction
- All methods accept raw arrays/lists, return `Any` (actually `go.Figure`)

### Design Decision

Existing methods accept raw arrays. EDA methods need DataFrame context (column names, grouping). Recommended: accept `pl.DataFrame` with column name parameters, converting to pandas at the plotly boundary.

### Reference Pattern

`DataExplorer.visualize()` already generates histograms and bar charts using `plotly.express` — can reference for consistency.

### New Methods (3 minimum)

```
histogram(data, column, *, bins=30, title=None) -> Figure
scatter(data, x, y, *, color=None, title=None) -> Figure
box_plot(data, column, *, group_by=None, title=None) -> Figure
```

Each method: ~20-30 lines of plotly code + tests.

---

## #315: training_history y_label

### Current Code State

- **File**: `model_visualizer.py`, line 575–616
- `x_label` used at line 613 → `xaxis_title=x_label`
- `yaxis_title="Value"` hardcoded at line 614

### Fix

Add `y_label: str = "Value"` parameter, change line 614 to `yaxis_title=y_label`. One test. Zero risk. Fully backward compatible.

---

## #316: Export SupervisorWorkerPattern

### Current Code State

- **File**: `packages/kaizen-agents/src/kaizen_agents/__init__.py`
- Current exports: `Delegate`, `GovernedSupervisor`, `SupervisorResult`, `Agent`, `ReActAgent`, `Pipeline`
- `patterns/__init__.py` does NOT re-export from `patterns.patterns/` — dead end in export chain

### 5 Pattern Classes Not Exported

| Pattern                     | File                                     | Line |
| --------------------------- | ---------------------------------------- | ---- |
| `SupervisorWorkerPattern`   | `patterns/patterns/supervisor_worker.py` | 668  |
| `ConsensusPattern`          | `patterns/patterns/consensus.py`         | 506  |
| `DebatePattern`             | `patterns/patterns/debate.py`            | 662  |
| `HandoffPattern`            | `patterns/patterns/handoff.py`           | 276  |
| `SequentialPipelinePattern` | `patterns/patterns/sequential.py`        | 209  |

Also missing: 5 factory functions (`create_supervisor_worker_pattern`, etc.) and `BaseMultiAgentPattern`.

### Deprecated Module

`agents/coordination/__init__.py` re-exports these same patterns with deprecation warning for v0.5.0. Current version: 0.6.0. This module has outlived its deprecation notice.

### Fix

Add try/except imports (matching existing pattern) for all 5 pattern classes + factories to `__init__.py`. Clean up deprecated coordination module.

---

## #317: ExperimentTracker Standalone Usage

### Current Code State

- **File**: `packages/kailash-ml/src/kailash_ml/engines/experiment_tracker.py`
- `__init__` at line 392–400: requires `conn: ConnectionManager`
- `ConnectionManager` at `kailash.db.connection`, requires `url: str` + `await .initialize()`
- No factory method, no `str` acceptance for `conn`

### README Bugs Found (3)

1. Calls `await tracker.initialize()` — method doesn't exist (uses internal `_ensure_tables()`)
2. `tracker.start_run(experiment.id, ...)` — `start_run` takes `experiment_name: str`, not ID
3. `tracker.list_runs(experiment.id, order_by=..., ascending=...)` — no `order_by`/`ascending` params

### Fix

1. Add `@classmethod async def create(cls, url, artifact_root)` factory method
2. Fix all 3 README bugs

---

## #318: ParamDistribution type Field Docs

### Current Code State

- **File**: `packages/kailash-ml/src/kailash_ml/engines/hyperparameter_search.py`, lines 38–65
- Docstring: just `"""Single hyperparameter distribution."""` (minimal)
- `type` used as discriminator in 3 locations (lines 74–91, 93–120, 454–470)
- Serialized as dict key in `to_dict()`/`from_dict()`

### Rename Safety

Rename to `distribution` is **unsafe** (breaking change): positional arg in all test code, dict key in serialization.

### README Bug Found

SearchSpace example (README lines 697–705) uses entirely fabricated API: `model_class=`, `framework=`, `parameters=`, `type="choice"`, `values=` — none of which exist on the real classes.

### Fix

1. Expand docstring with valid values and builtin-shadowing note
2. Add `@property def distribution(self) -> str` read-only alias
3. Fix fabricated README example
