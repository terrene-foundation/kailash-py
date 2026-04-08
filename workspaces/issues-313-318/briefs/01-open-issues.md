# Open GitHub Issues — #308, #313–#318

## P1 Issues (2)

### #313 — kailash-ml: PreprocessingPipeline one-hot encodes without cardinality guard

- `setup(categorical_encoding="onehot")` silently explodes columns for high-cardinality fields
- No `max_cardinality` threshold, no `exclude_columns` parameter
- Discovered via ASCENT M1 exercise with 50k-row taxi dataset → 48,611 columns from 10 inputs
- kailash-rs already has `max_categories` and `min_frequency` on OneHotEncoder
- **Labels**: enhancement, P1, sdk-engine

### #314 — kailash-ml: ModelVisualizer lacks EDA chart methods

- All 9 existing methods are post-training diagnostics; zero pre-training EDA
- Missing: histogram/distribution, scatter, box/violin plots
- Forces users to drop to raw Plotly for the most common data science activity
- Violates Framework-First principle
- **Labels**: enhancement, P1, sdk-engine

## Enhancement Issues (2)

### #315 — kailash-ml: training_history missing y_label parameter

- `training_history()` accepts `x_label` but not `y_label`
- Simple parameter addition
- **Labels**: enhancement, sdk-engine

### #316 — kaizen-agents: Export SupervisorWorkerPattern from top-level **init**

- `SupervisorWorkerPattern` exists but isn't exported from `kaizen_agents.__init__`
- All other major patterns (Delegate, Agent, ReActAgent, Pipeline) are top-level exports
- Also consider: ConsensusPattern, DebatePattern, HandoffPattern, SequentialPipelinePattern
- **Labels**: enhancement

## Documentation Issues (2)

### #317 — kailash-ml: ExperimentTracker needs standalone usage example

- No documented way to create a ConnectionManager for local/standalone usage
- Needs convenience factory or documented pattern
- **Labels**: documentation

### #318 — kailash-ml: Document ParamDistribution type field (shadows builtin)

- `type` field shadows Python builtin; confuses beginners, triggers linter warnings
- Needs docstring note; consider `distribution` alias in future minor version
- **Labels**: documentation

## Cross-SDK Tracking (1)

### #308 — cross-sdk: pact engine governance helpers

- Tracking issue for kailash-rs #216, #217, #219
- kailash-py already has implementations in PACT Platform (L3)
- Action: match kailash-rs when they implement; may move L3 code down to L1
- **No immediate Python work needed** — tracking only
