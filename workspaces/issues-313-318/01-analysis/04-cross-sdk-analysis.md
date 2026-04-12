# Cross-SDK Analysis — kailash-rs Equivalents

| Python Issue                      | kailash-rs Equivalent?                              | RS Status        | RS Issue    | Action                  |
| --------------------------------- | --------------------------------------------------- | ---------------- | ----------- | ----------------------- |
| #313 cardinality guard            | OneHotEncoder has `max_categories`, `min_frequency` | ✅ Already fixed | None        | No action — RS is ahead |
| #314 EDA charts                   | No ModelVisualizer class                            | ❌ Missing       | #223 (OPEN) | Already tracked         |
| #315 y_label                      | No training_history viz method                      | ❌ Missing       | None        | File new issue          |
| #316 pattern exports              | SupervisorWorkerPattern properly exported           | ✅ Already fixed | None        | No action — RS is ahead |
| #317 ExperimentTracker standalone | ExperimentTracker exists but not exported           | ⚠️ Blocked       | #224 (OPEN) | Depends on #224         |
| #318 ParamDistribution            | No ParamDistribution struct                         | ❌ Missing       | None        | File new issue          |

## New Issues to File on kailash-rs

1. **training_history visualization** — depends on #224 (engine module export)
2. **ParamDistribution struct** — for RandomizedSearchCV distribution support
