---
type: DISCOVERY
date: 2026-06-07
author: agent
project: F32 (kailash-ml doc phantom-API remediation)
topic: import-execution sweep reveals 87-finding platform-wide doc rot, not 6-file FeatureStore rot
phase: redteam
tags:
  [doc-rot, phantom-api, sweep, kailash-ml, spec-accuracy, user-flow-validation]
relates_to: 0005-DISCOVERY-phantom-api-doc-rot-in-synced-skill-examples
---

# DISCOVERY — sweep reveals platform-wide kailash-ml doc rot

## What surfaced

F32 was scoped (journal 0005, .session-notes ledger) as "rewrite the 6 FeatureStore
skill examples (phantom `ingest`/`compose`/`register_schema`/`register_group`)". Building
the proposed import-execution sweep (`tools/check_doc_api_examples.py`) and running it
across the full doc surface (`.claude/skills/**`, `packages/kailash-ml/README.md`,
`packages/kailash-ml/docs/**`, `MIGRATION.md`) returned **87 findings across 17 files** —
the fictional-API rot is platform-wide across kailash-ml docs, not FeatureStore-only.

The sweep parses every `python` fence with `ast`, resolves each `kailash_ml` symbol against
the _installed 2.0.0 code_, and flags (a) imports that do not resolve, (b) methods called on
a resolved class that do not exist (`hasattr`), (c) constructor kwargs that are not real
parameters (`inspect.signature`). Bindings resolve in source order, so a migration
before/after fence that imports both the legacy and canonical surface validates each use
against the binding active at its line.

## Real-API map (authoritative — resolved against installed kailash-ml 2.0.0)

**FeatureStore — two distinct surfaces, two distinct schema types:**

- Canonical read: `from kailash_ml import FeatureStore` → `kailash_ml.features.store.FeatureStore(dataflow, *, default_tenant_id=None)`; method `get_features(schema, timestamp=None, *, tenant_id=None, entity_ids=None)`. Schema MUST be `kailash_ml.features.schema.FeatureSchema` — `FeatureSchema(name, version=1, fields=(...), entity_id_column, timestamp_column)` (note **`fields=`** tuple). Import via `from kailash_ml.features import FeatureStore, FeatureSchema, FeatureField, CANONICAL_SINGLE_TENANT_SENTINEL`.
- Legacy write/registry/training: `from kailash_ml.engines.feature_store import FeatureStore` → `FeatureStore(conn: ConnectionManager, *, table_prefix=...)`; methods `initialize / register_features(schema) / compute(raw_data, schema) / store(features, schema) / get_features(entity_ids, feature_names, *, schema_name=None, schema=None, as_of=None) / get_training_set(schema, ...) / get_features_lazy(...) / list_schemas()`. Schema is `kailash_ml.types.FeatureSchema(name, features=[...], entity_id_column, timestamp_column=None, version=1)` (note **`features=`** list). NO `target`, NO `entity_key`, NO `timestamp_field`.

**Phantom methods → real:** `ingest`→`register_features`+`store`; `compose`→`get_training_set` (single schema; multi-set join is not a shipped method); `register_schema`/`register_group`→`register_features`.

**Other engines (real surfaces):**

- `ModelSpec` / `EvalSpec`: `from kailash_ml.engines.training_pipeline import ModelSpec, EvalSpec`. `ModelSpec(model_class, hyperparameters={}, framework="sklearn")`; `EvalSpec(metrics=[], split_strategy="holdout", n_splits=5, test_size=0.2, min_threshold={})`. NOT top-level `kailash_ml`.
- `LocalFileArtifactStore` / `ArtifactStore`: `from kailash_ml.engines.model_registry import LocalFileArtifactStore`. NOT `kailash_ml.engines.*` bare, NOT `kailash_ml.artifacts.*`.
- `ModelRegistry(conn, artifact_store=None, *, auto_migrate=True)` — **no `initialize()`** (ready on construct). Methods: `register_model(name, artifact, *, metrics=, signature=, tenant_id=) / promote_model(name, version, target_stage, *, reason=, tenant_id=) / get_model / get_model_versions / list_models / load_artifact / compare / export_mlflow / import_mlflow / build_lineage_graph / record_lineage`. (`register`→`register_model`, `promote`→`promote_model`.)
- `TrainingPipeline(feature_store, registry)` — NOT `model_registry=`/`experiment_tracker=`. The tracker is passed to `.train(data, schema, model_spec, eval_spec, experiment_name, *, agent=None, tracker=None, parent_run_id=None)`.
- `DriftMonitor(conn, *, tenant_id, psi_threshold=0.2, ...)` — **no `initialize()`**. `set_reference()`→`set_reference_data(model_name, reference_data, feature_columns, ...)`. `check_drift(model_name, current_data, ...)`. No `set_retraining_trigger` — use `schedule_monitoring(...)`. `data_source="feature_store:..."` string is illustrative only.
- `ExperimentTracker` — **two classes**: top-level `from kailash_ml import ExperimentTracker` → `kailash_ml.tracking.tracker.ExperimentTracker` (factory `.create(url=...)`, methods `track / start_run / end_run / get_run / search_runs / ...` — **no `run()`, no `initialize()`**). Engine `from kailash_ml.engines.experiment_tracker import ExperimentTracker(conn, artifact_root="./mlartifacts")` has `run()` (async ctx), `start_run`, `log_metric`, etc., **no `initialize()`**. Pick ONE per example; do not mix.
- `InferenceServer(config=None, *, registry=None, cache_size=None, server_id=None)` — NOT `model_registry=`/`runtime=`/`drift_monitor=`/`drift_*=`. No `get_drift_status()`. Methods: `predict / health / status / start / stop / from_registry / model_signature`.
- `AutoMLEngine(*, config, tenant_id, actor_id, connection=None, cost_tracker=None, governance_engine=None)` — NOT `registry=`/`pipeline=`/`feature_store=`/`model_registry=`/`agent_infusion=`. `AutoMLConfig`: `from kailash_ml.automl import AutoMLConfig` (NOT `kailash_ml.engines.automl_engine`).
- `OnnxBridge`: `from kailash_ml import OnnxBridge` (NOT `kailash_ml.bridge`).
- `MlflowFormatReader/Writer`: `from kailash_ml import MlflowFormatReader, MlflowFormatWriter` (NOT `kailash_ml.compat`). `writer.save()`→`writer.write(...)`.
- `PreprocessingPipeline`: `from kailash_ml import PreprocessingPipeline`.
- Hyperparameter search (`kailash_ml.engines.hyperparameter_search`): the 4 classes `GridSearch/RandomSearch/BayesianSearch/SuccessiveHalving` are FICTIONAL. Real API: ONE `HyperparameterSearch(pipeline)` parametrized by `SearchConfig(strategy="grid"|"random"|"bayesian"|..., n_trials=, metric_to_optimize=, direction=)` + `SearchSpace([ParamDistribution(name, type, low=, high=, choices=)])` → `SearchResult`.
- interop: `to_sklearn_arrays`/`from_numpy_predictions` are FICTIONAL. Real: `from kailash_ml.interop import to_sklearn_input, from_sklearn_output, to_pandas, from_pandas` (+ `to_lgb_dataset / to_hf_dataset / polars_to_arrow / dict_records_to_polars`).
- RL `PolicyRegistry.get()` (README) is fictional → `get_version` / `get_latest_version`.
- `kailash_ml.legacy.*` (MIGRATION 3.0 example) does not exist at 2.0.0 — the namespace is forward-looking; the real explicit path today is `kailash_ml.engines.*`.

## Disposition

The sweep is the structural defense journal 0005 §"Codify candidate" proposed. It is wired as
an **advisory** `/redteam` gate (journal 0005 FD#3 conservative disposition — advise at
`/redteam`, do not block `/sync`). Remediation drives the full 17-file surface to sweep-zero;
the tool is the continuous gate + the durable regression guard.

## For Discussion

1. Counterfactual: had the sweep existed at #643-step-3, would the README/guide rewrites in
   PR #1274 have been declared "done" with the 87 sibling-surface findings still open? The
   sweep makes "the docs are fixed" a falsifiable exit-code, not a judgment.
2. The two-`ExperimentTracker` / two-`FeatureSchema` split (same class name, different module,
   different API) is the highest-residual-risk pattern: an example that imports one and calls
   the other's method passes a human skim but fails the sweep. Should the package collapse the
   duplicate names, or is the sweep the permanent guard?
3. The sweep validates symbol/method/kwarg existence, NOT that an example _runs_ end-to-end
   (`user-flow-validation` gap). Is a Tier-2 "execute the README quickstart fence" test
   (`test_readme_quickstart_executes.py` already exists for the canonical quickstart) the
   right next layer, extended to the guide fences?
