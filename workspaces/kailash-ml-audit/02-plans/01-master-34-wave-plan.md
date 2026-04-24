# kailash-ml 1.0.0 — 38-Wave Shard Implementation Plan (Amended Round-9)

**Date:** 2026-04-21 (original 34-wave); amended 2026-04-21 after Round-9 red team
**Input:** 21 canonical specs (15 ml-_.md + 6 _-ml-integration.md) + 14 approved decisions + Round-9 SYNTHESIS amendments (`04-validate/round-9-SYNTHESIS.md`)
**Output contract:** 7-package atomic wave release per Round-8 SYNTHESIS
**Autonomous execution:** each shard ≤500 LOC load-bearing + ≤5-10 invariants + ≤3-4 call-graph hops (per `rules/autonomous-execution.md`)
**Round-9 amendments applied:** Option A accepted (spec canonical). W1 relocated kailash core; W3/W4 relocated; W19/W20/W27/W33 split; W31 gains 31d observability sub-shard + spec-mandated node names; W32 adds tracker kwarg + 4 TRL adapters + 3 PACT methods; W34 gains rollback protocol. Total: **38 waves + 1 infra follow-up (IT-1)**.

## Global amendments (apply to every wave)

1. **Wiring-test convention (per `orphan-detection.md §2` + `facade-manager-detection.md`):** Every wave that adds a `*Manager`, `*Executor`, `*Store`, `*Registry`, `*Engine`, `*Service`, or `*Diagnostics` class exposed via a framework facade MUST include `tests/integration/test_<class_name>_wiring.py` that imports THROUGH the facade (not the class directly) + asserts externally-observable effect. 21 affected classes: `ExperimentTracker`, `ExperimentRun`, `AbstractTrackerStore`, `SqliteTrackerStore`, `PostgresTrackerStore`, `ModelRegistry`, `LocalFileArtifactStore`, `CasSha256ArtifactStore`, `ArtifactStore` ABC, `MLEngine`, `DLDiagnostics`, `RLDiagnostics`, `InferenceServer`, `ServeHandle`, `DriftMonitor`, `AutoMLEngine`, `FeatureStore`, `MLDashboard`, `RLTrainer`, `EnvironmentRegistry`, `PolicyRegistry` + 4 TRL adapters (W32 32b).

2. **Parallel-worktree discipline (per `agents.md § Parallel-Worktree` + `worktree-isolation.md §4-§5`):** Every delegation prompt for `isolation: "worktree"` sub-shards MUST use RELATIVE paths only (absolute paths to parent checkout BLOCKED); MUST include explicit commit-after-each-file instruction; parent MUST verify file existence post-exit. Cross-package sub-shards declare ONE version owner per package; sibling sub-shards MUST NOT edit the owner's `pyproject.toml` / `__version__` / `CHANGELOG.md`.

3. **W34 sole kailash-ml CHANGELOG owner:** W31/W32/W33a/W33b pass bullet text via PR description; ONLY W34 edits `packages/kailash-ml/CHANGELOG.md`.

4. **Extras pin discipline:** Every `[extras]` cross-reference uses `>=X.Y.Z` ranges, NEVER `==`.

5. **Env-var test isolation (per `testing.md § Env-Var Test Isolation`):** Every wave that monkeypatches `KAILASH_ML_*` env vars MUST use module-scope `threading.Lock` + function-scope `monkeypatch.setenv`. Applies minimum to W2, W14, W15, W22.

6. **Protocol-deterministic adapters (per `testing.md § Exception`):** Tier 2 DDP tests use real `torch.distributed` spin-up OR Protocol-conforming deterministic adapter — NEVER `MagicMock`. Applies minimum to W14, W22.

7. **Canonical location (per `kailash-core-ml-integration.md §1.1`):** MLError hierarchy at `src/kailash/ml/errors.py` (W1a); migrations at `src/kailash/tracking/migrations/` (W3, W4); ML nodes at `kailash.workflow.nodes.ml` (W31 31a); observability at `kailash.observability.ml` (W31 31d). kailash-ml re-exports (W1b).

## Wave Dependency Graph

```
M1 Foundations (W1a/W1b/W2-W6) ──┬─→ M2 Backends+Trainable (W7-W9) ──┐
                                 │                                    │
                                 └─→ M3 Tracking (W10-W13) ──┐        │
                                                             │        │
                                                             ▼        ▼
                                  M4 Tracking Storage (W14-W15)   M5 Registry (W16-W18)
                                                             │        │
                                                             └───┬────┘
                                                                 ▼
                                        M6 MLEngine (W19a/b + W20a/b + W21)
                                                                 │
                                        ┌────────────────────────┼────────────────────┐
                                        ▼                        ▼                    ▼
                        M7 Diagnostics+Autolog          M8 Serving/Drift/AutoML    M9 RL
                              (W22-W24)                  /FS/Dash (W25-W27a/b-W28)  (W29-W30)
                                        └────────────────────────┬────────────────────┘
                                                                 ▼
                                            M10 Integrations (W31 31a/b/c/d + W32 32a/b/c)
                                                                 │
                                                                 ▼
                                            M11 km.* + README (W33a + W33b)
                                                                 │
                                                                 ▼
                                            M12 7-package Release Wave (W34)
```

Waves within a milestone are mostly parallelizable after the milestone's foundation shard lands. Cross-milestone ordering is strict.

## Estimation (amended)

- **Total load-bearing LOC:** ~14,500 across 7 packages (budget: 38 × ~380 avg after Round-9 sub-shard splits)
- **Autonomous execution cycles (sessions):** 38 sessions × ~1.2hr each ≈ 45-55 effective hours (parallelized across ~10 specialist paths)
- **Test LOC:** ~7,000 across 3 tiers (including 21 wiring tests per Round-9 convention)
- **Migration LOC:** ~800 across two numbered migrations (in `src/kailash/tracking/migrations/`)
- **Human gates:** 2 structural (this /todos approval + /release authorization). Execution gates autonomous throughout.

## Wave inventory (38 total)

**M1:** W1a, W1b, W2, W3, W4, W5, W6
**M2:** W7, W8, W9
**M3:** W10, W11, W12, W13
**M4:** W14, W15
**M5:** W16, W17, W18
**M6:** W19a, W19b, W20a, W20b, W21
**M7:** W22, W23, W24
**M8:** W25, W26, W27a, W27b, W28
**M9:** W29, W30
**M10:** W31 (sub-shards 31a, 31b, 31c, 31d parallel), W32 (sub-shards 32a, 32b, 32c parallel)
**M11:** W33a, W33b
**M12:** W34
**IT:** IT-1 (GPU CI runner — not release-blocker)

## Milestone 1 — Foundations (W1-W6)

Baseline primitives every downstream engine imports. Must land before ANY engine shard.

### W1 — `kailash_ml.errors` Canonical MLError Hierarchy

- **Spec:** `ml-tracking.md §9.1` + `ml-engines-v2.md §2.3`
- **Deliverable:** `packages/kailash-ml/src/kailash_ml/errors.py` — `MLError(Exception)` root + 11 per-domain families (`TrackingError`, `AutologError`, `RLError`, `BackendError`, `DriftMonitorError`, `InferenceServerError`, `ModelRegistryError`, `FeatureStoreError`, `AutoMLError`, `DiagnosticsError`, `DashboardError`) + cross-cutting `UnsupportedTrainerError`, `EngineNotSetUpError`, `ConflictingArgumentsError`, `TargetNotFoundError`, `TargetInFeaturesError`, `AcceleratorUnavailableError`, `TenantRequiredError`, `ModelNotFoundError`, `OnnxExportError`, `SchemaDriftError`, `ParamValueError`, `EnvVarDeprecatedError`, `MultiTenantOpError`.
- **Invariants (7):** (1) `MLError(Exception)` root; (2) every public raise uses typed subclass; (3) no generic `RuntimeError`; (4) package re-export via `kailash_ml/__init__.py`; (5) each exception documents actionable message format; (6) exception messages never echo classified field values (per `event-payload-classification.md`); (7) cross-SDK parity with kailash-rs `MLError` trait (Decision 3).
- **Tests:** T1 unit — exception hierarchy assertions; T2 integration — every raising primitive catches a subclass cleanly.
- **Packages touched:** `kailash-ml` only.
- **Blocks:** W2-W34 (every subsequent shard imports from `kailash_ml.errors`).

### W2 — `kailash_ml._env` Store-Path Resolver

- **Spec:** `ml-engines-v2.md §2.1 MUST 1b`
- **Deliverable:** `kailash_ml/_env.py::resolve_store_url(explicit)` — single-point authority chain: explicit kwarg → `KAILASH_ML_STORE_URL` → `KAILASH_ML_TRACKER_DB` (legacy, emits DEBUG line) → `sqlite:///~/.kailash_ml/ml.db` default.
- **Invariants (5):** (1) env read once per construction; (2) legacy bridge emits ONE DEBUG line `kailash_ml.env.tracker_db_legacy` only; (3) 2.0 future-removal raises `EnvVarDeprecatedError`; (4) every engine imports from this module (no hand-rolled `os.environ.get` at engine sites); (5) grep gate `rg 'os.environ.get.*KAILASH_ML' src/` limited to this file.
- **Tests:** T1 unit — precedence chain; T2 integration — every engine resolves identical path.
- **Packages touched:** `kailash-ml` only.
- **Blocks:** W7-W34 engine shards.

### W3 — Numbered Migration 0001: COMPLETED/SUCCESS → FINISHED Status Hard-Migrate

- **Spec:** `ml-tracking.md §3.2 + §3.5` + Decision 1
- **Deliverable:** `packages/kailash-ml/migrations/0001_status_vocabulary_finished.py` — upgrade: `UPDATE _kml_runs SET status='FINISHED' WHERE status IN ('COMPLETED','SUCCESS')` + drop accept-on-read bridge code paths; downgrade: preserved-state tracking table + reversible restore.
- **Invariants (6):** (1) cross-SDK 4-member enum `{RUNNING, FINISHED, FAILED, KILLED}` locked; (2) no alias reads after migration; (3) writable status is write-only `FINISHED`; (4) migration reversible via `_kml_migration_0001_prior_status` preservation table; (5) `force_downgrade=True` required on rollback per `schema-migration.md` Rule 7; (6) DDL identifiers via `quote_identifier` helper per `dataflow-identifier-safety.md` Rule 1.
- **Tests:** T1 unit — enum parity; T2 integration — real PostgreSQL + SQLite migrate + roundtrip.
- **Packages touched:** `kailash-ml` (migrations).
- **Blocks:** W11, W14, W15.

### W4 — Numbered Migration 0002: `_kml_*` Table Prefix Unification + Tenant Columns

- **Spec:** `ml-tracking.md §6.3` + `approved-decisions.md § Implications`
- **Deliverable:** `migrations/0002_kml_prefix_tenant_audit.py` — creates or renames `_kml_runs`, `_kml_params`, `_kml_metrics`, `_kml_artifacts`, `_kml_tags`, `_kml_model_versions`, `_kml_aliases`, `_kml_audit`, `_kml_agent_runs` (kaizen integration placeholder), `_kml_classify_actions` (dataflow integration placeholder); every write-path table gets `tenant_id TEXT NOT NULL`; every audit table gets indexed `(tenant_id, created_at)`.
- **Invariants (9):** (1) all tables prefixed `_kml_`; (2) all within 63-char Postgres identifier limit; (3) every write-path table carries `tenant_id`; (4) audit tables are immutable (no UPDATE grant); (5) classification PK fingerprint form `sha256:<8hex>` per `event-payload-classification.md`; (6) DDL via `quote_identifier`; (7) SQLite + Postgres both supported; (8) `force_downgrade=True` required; (9) reversible downgrade preserves data via parking table.
- **Tests:** T1 unit — DDL generation; T2 integration — migrate + rollback on real PG + SQLite.
- **Packages touched:** `kailash-ml` (migrations).
- **Blocks:** W10-W18.

### W5 — `km.seed()` Global Reproducibility Surface

- **Spec:** `ml-engines-v2.md §11.1-§11.3`
- **Deliverable:** module-level `kailash_ml.seed(seed: int, *, torch=True, numpy=True, python=True, lightning=True, sklearn=True) -> SeedReport` in `kailash_ml/__init__.py` + `SeedReport` dataclass in `kailash_ml/_result.py` or adjacent.
- **Invariants (5):** (1) applies to `random`, `numpy.random`, `torch.manual_seed`, `lightning.seed_everything`, `PYTHONHASHSEED` on call; (2) returns `SeedReport(applied, skipped, torch_deterministic)`; (3) opt-out kwargs respect; (4) idempotent; (5) declared in `__all__` Group 1.
- **Tests:** T1 unit — each subsystem assertions; T2 integration — two `km.train` invocations with same seed produce byte-identical `result.metrics`.
- **Packages touched:** `kailash-ml`.
- **Blocks:** W19 (MLEngine imports), W33 (`__all__`), W34 (README Quick Start regression test shares fixture).

### W6 — `backend-compat-matrix.yaml` + `km.doctor` Subcommand

- **Spec:** Decision 6 + `ml-backends.md §GPU Arch Cutoff`
- **Deliverable:** `packages/kailash-ml/data/backend-compat-matrix.yaml` + `kailash_ml/doctor.py::run_subcommand(name)`.
- **Invariants (4):** (1) data file is installed package-data; (2) `km.doctor` reads at runtime; (3) matrix updateable without SDK release (semver for file format); (4) includes CUDA arch cutoffs, MPS min macOS, ROCm GPU list.
- **Tests:** T1 unit — yaml schema; T2 integration — `km.doctor gpu` against mocked lspci/nvidia-smi.
- **Packages touched:** `kailash-ml`.
- **Blocks:** W7.

## Milestone 2 — Backends + Trainable (W7-W9)

### W7 — `DeviceReport` + `detect_backend()`

- **Spec:** `ml-backends.md §1-§5` + Decision 5 (XPU dual-path)
- **Deliverable:** `kailash_ml/_device.py` + `kailash_ml/_device_report.py` (refactor existing) — `detect_backend(accelerator, precision) -> BackendInfo`; `DeviceReport.from_backend_info`; XPU native-first → ipex fallback probe; 6 backends `cpu/cuda/mps/rocm/xpu/tpu`.
- **Invariants (8):** (1) `accelerator="auto"` resolves in documented order; (2) XPU probe tries `torch.xpu.is_available()` first then `intel_extension_for_pytorch`; (3) MPS fp16 fallback to bf16 per Apple Silicon; (4) ROCm reads `HIP_VISIBLE_DEVICES`; (5) TPU guarded by `XRT_TPU_CONFIG`; (6) `DeviceReport` is frozen dataclass; (7) `AcceleratorUnavailableError` on explicit-but-missing request; (8) `km.doctor gpu` re-uses probe logic.
- **Tests:** T1 unit — probe ordering with monkeypatched torch; T2 integration (matrix) — real MPS detect on macos-14, real CUDA detect on self-hosted runner.
- **Packages touched:** `kailash-ml`.
- **Blocks:** W8, W19.

### W8 — `Trainable` Protocol + `TrainingResult` Wiring

- **Spec:** `ml-engines-v2.md §3-§4`
- **Deliverable:** refactor `kailash_ml/trainable.py::Trainable(Protocol)` + `kailash_ml/_result.py::TrainingResult` — ensure `device: DeviceReport` populated, `device_used: str` back-compat mirror, `metrics: dict`, `artifacts: list`, `model_ref`, `family`, `hyperparameters`, `lineage_dataset_hash`, `run_id`.
- **Invariants (7):** (1) `@runtime_checkable`; (2) `to_lightning_module()` mandatory on non-RL; (3) `family_name: str` class attribute; (4) `get_param_distribution() -> HyperparameterSpace`; (5) every `return TrainingResult(...)` site passes `device=`; (6) `device_used` computed from `device`; (7) parity grep gate `grep -c "return TrainingResult(" | eq | grep -cE "device=DeviceReport"`.
- **Tests:** T1 unit — protocol conformance; T2 integration — every adapter returns populated `TrainingResult`.
- **Packages touched:** `kailash-ml`.
- **Blocks:** W9, W19-W21.

### W9 — Lightning Adapters: Sklearn / XGBoost / LightGBM / CatBoost

- **Spec:** `ml-engines-v2.md §3.2 MUST 1-5` + `ml-engines-v2-addendum §E3-§E5`
- **Deliverable:** `kailash_ml/estimators/adapters/*.py` — `SklearnLightningAdapter`, `XGBoostLightningAdapter`, `LightGBMLightningAdapter`, `CatBoostLightningAdapter` each wrapping fit in a LightningModule `training_step` + `to_lightning_module()` implementation.
- **Invariants (6):** (1) all fit through `L.Trainer`; (2) raw loop → `UnsupportedTrainerError` (Decision 8); (3) `accelerator=auto` honored (no family-specific dispatch); (4) CPU/MPS families work on MPS accelerator; (5) `device=` populated in return; (6) `NaN`/`Inf` hyperparameters → `ParamValueError`.
- **Tests:** T1 unit — adapter pickle/unpickle; T2 integration — all 4 families train against real DF.
- **Packages touched:** `kailash-ml`.
- **Blocks:** W19, W20.

## Milestone 3 — Tracking Engine (W10-W13)

### W10 — `ExperimentTracker` Canonical Async Factory + `ExperimentRun` Wrapper

- **Spec:** `ml-tracking.md §2.1-§2.5`
- **Deliverable:** `kailash_ml/tracking/tracker.py::ExperimentTracker.create(store_url)` async factory + `ExperimentRun` thin async-context wrapper + `kailash_ml/tracking/runner.py` contextvar.
- **Invariants (7):** (1) async factory only (no sync `__init__`); (2) default store path via `_env.resolve_store_url()`; (3) `ExperimentRun` wraps `async with` context-manager lifecycle; (4) storage-driver migration runs at `create()`; (5) ExperimentRun does NOT hold a tracker ref — polymorphic over backends; (6) nested runs supported; (7) SIGINT/SIGTERM cleanly finalize as `KILLED`.
- **Tests:** T1 unit — factory + nested-run guard; T2 integration — signal handler round-trip.
- **Packages touched:** `kailash-ml`.
- **Blocks:** W11, W19, W21.

### W11 — Run Lifecycle: Status Transitions + Signal Handling + Nested Runs

- **Spec:** `ml-tracking.md §3`
- **Deliverable:** extend W10 — `start_run()` / `end_run()` sync variant (Decision 9 Rust parity), `RUNNING → FINISHED/FAILED/KILLED` transition enforcement, SIGINT handler.
- **Invariants (5):** (1) status transitions monotonic; (2) SIGINT handler finalizes `KILLED` before propagating; (3) nested runs correctly scope contextvar; (4) `_kml_runs.finished_at` always populated on exit; (5) signal-handler re-entrancy safe.
- **Tests:** T1 unit — transition matrix; T2 integration — real SIGINT with pytest-subprocess.
- **Packages touched:** `kailash-ml`.
- **Blocks:** W12.

### W12 — Logging Primitives: Params / Metrics / Artifacts / Figures / Model / Tags

- **Spec:** `ml-tracking.md §4`
- **Deliverable:** `ExperimentRun.log_param/log_params/log_metric/log_metrics/log_artifact/log_figure/log_model/attach_training_result/add_tag/add_tags`.
- **Invariants (6):** (1) `log_metric` exists on RUN (not engine) — closes MLFP-dev gap 2; (2) polars metric rows; (3) artifact dedupe via content hash; (4) figure sink bridges to `DLDiagnostics` event listener; (5) model-log writes to `_kml_model_versions`; (6) `attach_training_result` flattens metrics/hyperparameters.
- **Tests:** T1 unit — each primitive; T2 integration — concurrent metric writes under load.
- **Packages touched:** `kailash-ml`.
- **Blocks:** W13, W19-W21.

### W13 — Query Primitives: `list_runs` (polars) + Filter DSL + `diff_runs`

- **Spec:** `ml-tracking.md §5`
- **Deliverable:** `ExperimentTracker.list_runs(filter=..., limit=...) -> pl.DataFrame` + `diff_runs(run_ids)`.
- **Invariants (5):** (1) polars return (no pandas); (2) tenant-scoped filter automatic; (3) filter DSL supports `metric_lt`, `param_eq`, `status`, `tags_contains`; (4) `diff_runs` returns wide polars DF; (5) ORDER BY latest finished_at default.
- **Tests:** T1 unit — filter parse; T2 integration — 10k-row table perf.
- **Packages touched:** `kailash-ml`.

## Milestone 4 — Tracking Storage + Tenant + Audit (W14-W15)

### W14 — Storage Layer + ContextVar Accessors

- **Spec:** `ml-tracking.md §6 + §10`
- **Deliverable:** `kailash_ml/tracking/storage/sqlite.py` + `postgres.py` + `kailash_ml/tracking/__init__.py::get_current_run/get_current_tenant_id`.
- **Invariants (5):** (1) SQLite + Postgres adapters share one `AbstractTrackerStore`; (2) connection pooling via `AsyncSQLitePool` (SQLite) or ConnectionManager (Postgres); (3) public accessor `get_current_run()` returns `Optional[ExperimentRun]`; (4) private `_current_run` contextvar not exposed; (5) DDP/FSDP rank-0-only emission (Decision 4).
- **Tests:** T1 unit — accessor isolation; T2 integration — DDP rank-0 mock cluster.
- **Packages touched:** `kailash-ml`.

### W15 — Tenant Isolation + Audit Rows + GDPR Erasure

- **Spec:** `ml-tracking.md §7-§8` + Decision 2
- **Deliverable:** tenant resolution helper + `_kml_audit` write-only append + `km.erase_subject(subject_id)` GDPR surface.
- **Invariants (7):** (1) audit rows immutable (no UPDATE grant, trigger blocks DELETE); (2) `km.erase_subject` deletes run content + artifact content + model content, preserves audit with `sha256:<8hex>` fingerprints; (3) cache keyspace `kailash_ml:v1:{tenant_id}:...`; (4) missing tenant → `TenantRequiredError`; (5) actor resolution order: explicit → contextvar → env; (6) audit (tenant_id, created_at) indexed; (7) cross-tenant admin op → `MultiTenantOpError` (Decision 12).
- **Tests:** T1 unit — tenant resolver; T2 integration — GDPR erase round-trip + audit preservation.
- **Packages touched:** `kailash-ml`.

## Milestone 5 — Registry + Artifacts (W16-W18)

### W16 — `ModelRegistry` Schema + Registration Core

- **Spec:** `ml-registry.md §3-§7`
- **Deliverable:** `kailash_ml/tracking/registry.py::ModelRegistry` + `register(run, name, stage, format, alias)` + schema enforcement.
- **Invariants (7):** (1) `(tenant_id, name, version)` uniqueness; (2) integer-monotonic versions; (3) reserved name patterns rejected; (4) every version has a Signature (input/output schema); (5) ONNX export probe default; (6) atomic registration (single tx); (7) dataset+code idempotence.
- **Tests:** T1 unit — version bump; T2 integration — concurrent register collision.
- **Packages touched:** `kailash-ml`.

### W17 — `ArtifactStore` (LocalFile + CAS sha256) + ONNX-Default

- **Spec:** `ml-registry.md §5.6 + §10`
- **Deliverable:** `kailash_ml/tracking/artifacts/*.py` — `LocalFileArtifactStore`, `CasSha256ArtifactStore`, `ArtifactStore` ABC + ONNX export via `torch.onnx.export` / `skl2onnx`.
- **Invariants (6):** (1) content addressing; (2) per-tenant quotas; (3) `artifact_uris["onnx"]` starts with `file://` or `cas://sha256:`; (4) ONNX export fail → `OnnxExportError(framework, cause)`; (5) pickle never default; (6) `register(format="both")` writes onnx+pickle.
- **Tests:** T1 unit — URI shape; T2 integration — export + load round-trip per family.
- **Packages touched:** `kailash-ml`.

### W18 — Aliases + Lineage + Query Ops

- **Spec:** `ml-registry.md §4 + §6 + §8-§9`
- **Deliverable:** `promote_model`, `demote_model`, `set_alias`, `clear_alias`, `get_model`, `list_models`, `search_models`, `diff_versions` + lineage persistence.
- **Invariants (6):** (1) aliases tenant-scoped; (2) reserved `@production`, `@staging`, `@shadow`, `@archived`; (3) lineage `dataset_hash + code_hash + parent_model` persisted; (4) cross-tenant lineage does NOT resolve; (5) every alias mutation emits log + event; (6) `is_golden=True` flag for reference registrations.
- **Tests:** T1 unit — alias conflict; T2 integration — lineage DAG walk + cross-tenant isolation.
- **Packages touched:** `kailash-ml`.

## Milestone 6 — MLEngine 8-method Surface (W19-W21)

### W19 — `MLEngine.__init__` + DI + `setup()` + `compare()`

- **Spec:** `ml-engines-v2.md §2.1 MUST 1-7 + §2.2`
- **Deliverable:** rewrite `kailash_ml/engine.py::Engine` — zero-arg construction + 6-primitive composition + DI overrides + `setup()` idempotent + `compare()` Lightning-routed sweep.
- **Invariants (9):** (1) zero-arg works; (2) all 7 DI slots accepted; (3) overrides honored; (4) `setup()` idempotent per `(df_fingerprint, target, ignore, feature_store_name)`; (5) `compare()` routes every family through `L.Trainer`; (6) `setup()` raises `TargetNotFoundError` / `TargetInFeaturesError`; (7) 8-method surface exactly; (8) async-first (sync variant delegates); (9) `tenant_id` plumbed to every store.
- **Tests:** T1 unit — DI resolution; T2 integration — compare + setup idempotence.
- **Packages touched:** `kailash-ml`.
- **Blocks:** W20, W21.

### W20 — `MLEngine.fit()` + `predict()` + `finalize()` + `evaluate()`

- **Spec:** `ml-engines-v2.md §2.1 MUST 8-9 + §2.2`
- **Deliverable:** 4 methods + Lightning passthrough kwargs (strategy, devices, num_nodes, enable_checkpointing, auto_find_lr, callbacks).
- **Invariants (10):** (1) `fit(family=)` OR `fit(trainable=)` mutually exclusive (`ConflictingArgumentsError`); (2) `EngineNotSetUpError` if no setup; (3) `UnsupportedTrainerError` on raw loop detection; (4) strategy=ddp/fsdp/deepspeed plumbed to `L.Trainer`; (5) auto `ModelCheckpoint` appended rooted at ambient run; (6) `auto_find_lr=True` runs `Trainer.lr_find()` and overrides LR; (7) `predict(channel="direct"|"rest"|"mcp")`; (8) `finalize(full_fit=True)` retrains on train+holdout; (9) `evaluate(mode="holdout"|"shadow"|"live")`; (10) `SchemaDriftError` if `fit` schema != `setup` schema.
- **Tests:** T1 unit — arg validation; T2 integration — DDP rank-0 callback firing + lr_find round-trip.
- **Packages touched:** `kailash-ml`.

### W21 — `MLEngine.register()` + `serve()` + ONNX Default Channel Dispatch

- **Spec:** `ml-engines-v2.md §2.1 MUST 9-10 + §6`
- **Deliverable:** `register()` ONNX-default + `serve(channels=[rest,mcp,grpc])` multi-channel single call.
- **Invariants (6):** (1) `register(format="onnx")` default; (2) `artifact_uris["onnx"]` present; (3) `serve()` multi-channel from one call; (4) `ServeResult.uris` per-channel; (5) `format="both"` writes onnx+pickle; (6) serve dispatches to Nexus ml-endpoints (W31).
- **Tests:** T1 unit — serve result shape; T2 integration — full Quick Start to `/health → 200`.
- **Packages touched:** `kailash-ml`.

## Milestone 7 — Diagnostics + Autolog (W22-W24)

### W22 — `DLDiagnostics` + Lightning Callback + Rank-0-Only

- **Spec:** `ml-diagnostics.md` + Decision 4
- **Deliverable:** `kailash_ml/diagnostics/dl.py::DLDiagnostics` — torch hooks for activations/gradients/dead-neurons + `.as_lightning_callback()` + event sink to current run.
- **Invariants (7):** (1) rank-0-only emission (hardcoded `torch.distributed.get_rank() == 0`); (2) `[dl]` extra gates plotly; (3) `tracker=` kwarg is `Optional[ExperimentRun]`; (4) callback appended by `MLEngine.fit`; (5) figure events flow through `ExperimentRun.log_figure`; (6) dead-neuron detector uses documented threshold; (7) cross-SDK Diagnostic Protocol (Python satisfies Rust-aligned interface).
- **Tests:** T1 unit — rank-filter; T2 integration — full fit writes figures to run.
- **Packages touched:** `kailash-ml`.

### W23 — Autolog: sklearn + lightgbm + Lightning + torch

- **Spec:** `ml-autolog.md`
- **Deliverable:** `kailash_ml/autolog/*.py` — monkey-patch-based ambient-run detection + non-intrusive.
- **Invariants (6):** (1) `km.autolog(flavor="sklearn"|...)` enables per-flavor; (2) `ambient_run is None` → silent skip; (3) metric namespace discipline `train/{metric}`, `val/{metric}`; (4) `[autolog-lightning]` + `[autolog-transformers]` gated; (5) unpatch on opt-out; (6) rank-0-only for Lightning.
- **Tests:** T1 unit — patch/unpatch; T2 integration — sklearn fit auto-logs under ambient run.
- **Packages touched:** `kailash-ml`.

### W24 — `RLDiagnostics` + RAG/Interpretability/LLMJudge Adapters

- **Spec:** `ml-rl-core.md §7` + `kaizen-interpretability.md` + `kaizen-judges.md` + `ml-diagnostics.md`
- **Deliverable:** `kailash_ml/diagnostics/rl.py` (reward/value/policy/replay) + cross-SDK adapter parity for Rag/Interpret/Judge (already largely in kaizen per specs).
- **Invariants (5):** (1) RL metric namespace `rl/{episode_reward_mean, kl, clip_frac, entropy, ...}`; (2) Stable-Baselines3 callback hook; (3) reward-hacking signal emitted per `ml-rl-align-unification.md`; (4) existing kaizen adapters unchanged — wire only; (5) `AgentDiagnostics` SQLiteSink TraceExporter integrated (W32).
- **Tests:** T1 unit — callback hook; T2 integration — PPO rollout writes reward curve.
- **Packages touched:** `kailash-ml`, `kailash-kaizen` (wire-only, adapter code already exists).

## Milestone 8 — Serving + Drift + AutoML + FeatureStore + Dashboard (W25-W28)

### W25 — `InferenceServer` + `ServeHandle` + Channel Dispatch

- **Spec:** `ml-serving.md`
- **Deliverable:** `kailash_ml/serving/server.py` + `serve_handle.py` + REST/MCP/gRPC channel adapters.
- **Invariants (7):** (1) signature validates input schema; (2) batch mode supported; (3) `ServeHandle.uris` per-channel; (4) health endpoint `GET /health → 200`; (5) `km.serve("name@stage")` resolves via ModelRegistry; (6) ONNX runtime preferred (cross-language serving); (7) `InferenceServerError` typed.
- **Tests:** T1 unit — signature validation; T2 integration — RF/LGB/Torch all serve, roundtrip predict.
- **Packages touched:** `kailash-ml`.

### W26 — `DriftMonitor` — KS / chi2 / PSI / JS + Scheduled + Retraining Hook

- **Spec:** `ml-drift.md`
- **Deliverable:** `kailash_ml/drift/monitor.py` + per-feature + overall drift + retraining trigger callback.
- **Invariants (6):** (1) reference-vs-current polars DF input; (2) 4 test statistics implemented; (3) per-feature threshold config; (4) alert emits to tracker; (5) scheduled via `WorkflowScheduler`; (6) retraining hook is opt-in callback.
- **Tests:** T1 unit — each test stat; T2 integration — drift-trigger fires retrain callback.
- **Packages touched:** `kailash-ml`.

### W27 — `AutoMLEngine` + `FeatureStore`

- **Spec:** `ml-automl.md` + `ml-feature-store.md`
- **Deliverable:** `kailash_ml/automl/engine.py` + `kailash_ml/features/store.py` (polars-native).
- **Invariants (9):** (1) search strategies grid/random/bayesian/halving; (2) cost budget enforced (microdollars); (3) human-approval gate (PACT ml_context clearance, W32); (4) full audit trail to `_kml_audit`; (5) LLM guardrails (prompt injection scan per `security-threats.md`); (6) FeatureStore ConnectionManager-backed; (7) point-in-time queries; (8) schema enforcement + versioning; (9) tenant-scoped keys.
- **Tests:** T1 unit — search-strategy algorithms; T2 integration — full automl run + feature version retrieval.
- **Packages touched:** `kailash-ml`.

### W28 — `MLDashboard` CLI + `km.dashboard()` Launcher

- **Spec:** `ml-dashboard.md`
- **Deliverable:** `kailash_ml/dashboard/cli.py::main` + `km.dashboard()` in-notebook background-thread launcher + plotly views for runs/models/serving.
- **Invariants (5):** (1) CLI command `kailash-ml-dashboard` registered in `pyproject.toml`; (2) `km.dashboard()` non-blocking; (3) tenant filter on every view; (4) reads from the SAME tracker store the run used; (5) notebook-friendly.
- **Tests:** T1 unit — CLI argparse; T2 integration — end-to-end dashboard writes match run data.
- **Packages touched:** `kailash-ml`.

## Milestone 9 — Reinforcement Learning (W29-W30)

### W29 — RL Core — `RLTrainer` + `EnvironmentRegistry` + `PolicyRegistry` + `km.rl_train()`

- **Spec:** `ml-rl-core.md` + `ml-rl-algorithms.md`
- **Deliverable:** `kailash_ml/rl/trainer.py`, `envs.py`, `policies.py`, + SB3 wrappers + algorithm presets.
- **Invariants (8):** (1) `[rl]` extra gates sb3+gymnasium; (2) `RLTrainer` composes SB3 + Gymnasium; (3) algorithms: PPO, SAC, DQN, A2C, TD3, DDPG, MaskablePPO, DecisionTransformer; (4) `km.rl_train(env, algo)` entry; (5) cross-algo TrainingResult parity (reward_mean, ep_len_mean); (6) reward registry callable; (7) `[rl-offline]`, `[rl-envpool]`, `[rl-distributed]` extras; (8) NOT Lightning-routed (SB3 is substrate per Decision 8 carve-out).
- **Tests:** T1 unit — algo dispatch; T2 integration — PPO CartPole-v1 train 10K steps.
- **Packages touched:** `kailash-ml`.

### W30 — RL + Alignment Unification — Trajectory Schema + GRPO Bridge

- **Spec:** `ml-rl-align-unification.md`
- **Deliverable:** shared `Trajectory` schema + `kailash-align ↔ kailash-ml.rl` bridge + GRPO/RLOO/PPO-LM interop.
- **Invariants (5):** (1) trajectory schema byte-identical across `ml.rl` and `align.training`; (2) cross-framework reward_hacking signal; (3) `[rl-bridge]` extra; (4) GRPO in align re-uses `ml.rl.Trajectory`; (5) kaizen RL agents consume same schema.
- **Tests:** T1 unit — schema stability; T2 integration — align GRPO writes into `_kml_runs`.
- **Packages touched:** `kailash-ml`, `kailash-align`.

## Milestone 10 — Cross-framework Integrations (W31-W32)

### W31 — Core SDK + DataFlow + Nexus ML Integrations

- **Specs:** `kailash-core-ml-integration.md`, `dataflow-ml-integration.md`, `nexus-ml-integration.md`
- **Deliverables:**
  - `src/kailash/ml/__init__.py` — re-export `kailash_ml` + `pip install kailash[ml]` extras alias + workflow-node adapters (`TrainNode`, `PredictNode`, `ServeNode`).
  - `packages/kailash-dataflow/src/dataflow/ml/__init__.py` — `TrainingContext` dataclass, `lineage_dataset_hash(df)` helper, multi-tenant feature-group classification, ML-event subscriber (`on_train_start/on_train_end`), `_kml_classify_actions` bridge.
  - `packages/kailash-nexus/src/nexus/ml/__init__.py` — `mount_ml_endpoints(nexus, serve_handle)` → REST + MCP + WebSocket; `UserContext` preserved across channels; `nexus.ml.dashboard_embed()` iframe integration.
- **Invariants (10):** (1) `kailash[ml]` extras alias installs kailash-ml; (2) `kailash.ml.workflow_nodes` is a single-import surface; (3) `TrainingContext` contains `run_id + tenant_id + dataset_hash`; (4) `lineage_dataset_hash` deterministic over polars DF content; (5) ML events classify per DataFlow classification policy; (6) `nexus.ml.mount_ml_endpoints` registers all channels in one call; (7) `UserContext` visible to ML audit (actor resolution W15); (8) dashboard embed uses same session; (9) no import cycles; (10) each integration loads under `try/except ImportError` with loud failure (per `dependencies.md` "Optional Extras").
- **Tests:** T1 unit — extras alias + imports; T2 integration — end-to-end workflow: DataFlow feature set → kailash.ml train → Nexus serve → Dashboard reads run.
- **Packages touched:** `kailash`, `kailash-dataflow`, `kailash-nexus`, `kailash-ml` (shim imports).

### W32 — Kaizen + Align + PACT ML Integrations

- **Specs:** `kaizen-ml-integration.md`, `align-ml-integration.md`, `pact-ml-integration.md`
- **Deliverables:**
  - `packages/kailash-kaizen/src/kaizen/ml/__init__.py` — §2.4 Agent Tool Discovery via `km.engine_info()`, `SQLiteSink` TraceExporter (N4 fingerprint parity), shared `CostTracker`, `_kml_agent_runs` + `_kml_agent_events` tables.
  - `packages/kailash-align/src/align/ml/__init__.py` — fine-tuning-as-training-engine bridge, LoRA Lightning callback, RL↔alignment trajectory unification entry point.
  - `packages/kailash-pact/src/pact/ml/__init__.py` — `ml_context` envelope kwarg, D/T/R `ClearanceRequirement` decorators on engine methods, governance-gated `AutoMLEngine`+`ModelRegistry.promote_model`.
- **Invariants (10):** (1) `km.engine_info()` returns `EngineInfo` (signatures + metadata) used by agent tool construction; (2) Agents MUST use engine*info for tool-set build (no hardcoded imports); (3) SQLiteSink fingerprints match rust v3.17.1; (4) `CostTracker` shared across engine+agent; (5) LoRA Lightning callback appended to `MLEngine.fit` when `trainable` is LoRA trainable; (6) align trajectory imports `ml.rl.Trajectory`; (7) PACT `ml_context` envelope plumbed to every `MLEngine` method; (8) `ClearanceRequirement` on `promote_model("production")` + `automl.search*_`; (9) governance audit rows link `*kml_audit` + PACT audit; (10) cross-package invariants tested via Tier 2 wiring tests (`test*_\_wiring.py`).
- **Tests:** T1 unit — protocol/signature; T2 integration — agent tool discovery + LoRA train via engine + PACT-gated promote.
- **Packages touched:** `kailash-kaizen`, `kailash-align`, `kailash-pact`, `kailash-ml` (shim imports).

## Milestone 11 — `km.*` Convenience + `__all__` + README (W33)

### W33 — `km.*` Top-Level Wrappers + Canonical `__all__` + README Quick Start Regression

- **Spec:** `ml-engines-v2.md §15 + §16` + `ml-engines-v2-addendum §E11.2-E11.3`
- **Deliverables:**
  - Module-level functions in `kailash_ml/__init__.py`: `seed`, `reproduce`, `resume`, `lineage`, plus `_wrappers` module for `train`, `autolog`, `track`, `register`, `serve`, `watch`, `dashboard`, `diagnose`, `rl_train`.
  - `kailash_ml/engines/registry.py::engine_info`, `list_engines` (Group 6 Engine Discovery).
  - Canonical 6-group `__all__` ordering per §15.9.
  - Migration guide `packages/kailash-ml/MIGRATION.md` (legacy namespace sunset per Decision 11).
  - README Quick Start literal block per §16.1 (fingerprint `c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00`).
  - `tests/regression/test_readme_quickstart_executes.py` — fingerprint + end-to-end execute against real infra (RELEASE-BLOCKING).
- **Invariants (10):** (1) 34 symbols in `__all__`; (2) every entry eagerly imported at module scope (CodeQL); (3) 6-group order preserved; (4) Quick Start SHA-256 matches spec; (5) Quick Start executes `/health→200`; (6) `km.reproduce(run_id)` reconstructs TrainingResult from tracker (§12); (7) `km.resume(run_id)` restarts from `last.ckpt` (§12A); (8) `km.lineage(id)` returns LineageGraph dataclass; (9) `km.engine_info(name)` returns EngineInfo; (10) `km.list_engines()` enumerates.
- **Tests:** T1 unit — `__all__` membership + ordering; T2 integration — README regression + all wrappers dispatch.
- **Packages touched:** `kailash-ml`.

## Milestone 12 — 7-Package Atomic Release Wave (W34)

### W34 — Release Orchestration

- **Spec:** Decision 14 + `build-repo-release-discipline.md`
- **Version bumps (atomic):**
  - `kailash 2.9.0` (extras alias `[ml]` + kailash.ml shim)
  - `kailash-dataflow 2.1.0` (TrainingContext + ml-lineage)
  - `kailash-nexus 2.2.0` (ml-endpoints + UserContext)
  - `kailash-kaizen 2.12.0` (§2.4 Agent Tool Discovery + SQLiteSink + CostTracker)
  - `kailash-pact 0.10.0` (ml_context + ClearanceRequirement)
  - `kailash-align 0.5.0` (ml-unification + LoRA callback)
  - `kailash-ml 1.0.0` (the 15-spec body + 6 integrations)
- **Deliverables:**
  - All 7 `pyproject.toml` + `__init__.py::__version__` atomically bumped
  - 7 CHANGELOGs updated with 1.0.0 breaking-change list (SQLiteTrackerBackend deleted, two registries merged, status vocab `COMPLETED`→`FINISHED`, `_kml_engine_versions` scaffold deleted, `km.*` added, mandatory tenant_id+actor_id+audit)
  - `packages/kailash-ml/MIGRATION.md` cross-referenced from every CHANGELOG
  - PyPI publish order (reverse dep graph): `kailash 2.9.0` → `kailash-dataflow 2.1.0` → `kailash-nexus 2.2.0` → `kailash-kaizen 2.12.0` → `kailash-pact 0.10.0` → `kailash-align 0.5.0` → `kailash-ml 1.0.0`
  - Installability verification from clean venv per `build-repo-release-discipline.md` Rule 2
  - Cross-SDK parity issue kailash-rs#502 updated with release SHAs
- **Invariants (9):** (1) all 7 versions atomic in single PR; (2) `pyproject.toml` + `__version__` consistency per `zero-tolerance.md` Rule 5; (3) migration guide co-located with release PR; (4) 5→10 line Quick Start regression test GREEN on CI; (5) CPU+MPS CI blocking (Decision 7); (6) release-order respects reverse dep graph; (7) clean-venv install + import verified per package; (8) tag pushes trigger publish workflow; (9) PyPI JSON reflects new versions before gate closes (with retry loop).
- **Gate type:** Structural — human authorizes release.
- **Packages touched:** ALL 7.

## Out-of-band: Infra Tasks

### IT-1 — GPU CI Runner Acquisition (Decision 7)

- Separate infra todo tracking: self-hosted GPU runner (CUDA) required to flip CUDA from non-blocking → blocking per Decision 7.
- Not a release blocker; tracked as follow-up work.

### IT-2 — kailash-rs#502 Parity Variant Overlay

- Per Decision 10 single-spec-plus-variant approach, Rust variant overlays for ml-_ specs land via `loom/.claude/variants/rs/specs/ml-_.md`after next`/sync`. Not in 1.0.0 py release scope.

### IT-3 — v1.1 Deferred: `SystemMetricsCollector`

- DL-GAP-2 at `ml-diagnostics §7` — explicitly v1.1-deferred per Round-8 SYNTHESIS. Does NOT block 1.0.0 ship.

### IT-4 — v1.1 Deferred: PACT Cross-tenant Admin Export (`ml-registry-pact.md`)

- Decision 12 — 1.0.0 raises `MultiTenantOpError`; cross-tenant export spec ships post-1.0 under PACT D/T/R clearance.

## Parallelization Plan

**Wave parallelization capability** (specialist × wave map; each worktree isolated per `worktree-isolation.md`):

- W1-W6 Milestone 1: **serial** (foundations, cannot parallelize)
- W7-W9: W7 serial → W8 serial → W9 parallel across 4 adapter files
- W10-W13: W10 serial → W11-W13 can run in 2 shards
- W14-W15: W14 serial → W15 serial
- W16-W18: W16 serial → W17-W18 parallel
- W19-W21: **serial** (MLEngine surface has cross-method invariants)
- W22-W24: parallel across 3 specialists (ml, kaizen, rl)
- W25-W28: parallel across 4 specialists
- W29-W30: W29 serial → W30 serial (cross-package)
- W31-W32: each wave internal parallelism across 3 integration packages (coordinate version-owner per `agents.md` parallel-worktree rule)
- W33: serial (single package, heavy `__init__.py`)
- W34: **strictly serial** (release order)

**Version-owner rule (per `agents.md`):** When W31/W32 spawn multiple specialists editing the same sub-package, orchestrator designates ONE version owner for `pyproject.toml`/`__version__`/`CHANGELOG.md` per package. Explicit exclusion clause in sibling prompts.

## Testing Policy Per Wave

Every wave MUST land:

1. **Tier 1 unit tests** — mocking allowed per `rules/testing.md`.
2. **Tier 2 integration tests** — real PostgreSQL + real SQLite + (where gated) real CUDA/MPS.
3. **Regression tests** (per wave) in `tests/regression/test_w{NN}_*.py` for every bug class surfaced during Round 1-8 convergence.
4. **Invariant tests** — every LOC-reducing refactor lands `@pytest.mark.invariant` file-size guard (per `rules/refactor-invariants.md`).
5. **Wiring tests** — every manager-shape class (`*Tracker`, `*Registry`, `*Store`, `*Engine`) gets `test_<name>_wiring.py` (per `rules/orphan-detection.md` §2 + `facade-manager-detection.md`).

## Gate Protocol

- **Execution gates (autonomous):** W1-W33. Red team converges in background agents per wave.
- **Structural gates (human):**
  - Now: `/todos` approval of this plan.
  - End of W34: `/release` authorization before PyPI publication.
- **MUST review gate after `/implement`:** reviewer + security-reviewer run as parallel background agents per wave batch (per `rules/agents.md`).

## Spec Coverage Matrix

| Spec                             | Primary Wave | Secondary Waves          |
| -------------------------------- | ------------ | ------------------------ |
| `ml-engines-v2.md`               | W19-W21      | W7, W8, W9, W33          |
| `ml-engines-v2-addendum.md`      | W9           | W21, W33                 |
| `ml-backends.md`                 | W7           | W8, W19                  |
| `ml-tracking.md`                 | W10-W15      | W33                      |
| `ml-registry.md`                 | W16-W18      | W21, W32                 |
| `ml-serving.md`                  | W25          | W21, W31                 |
| `ml-autolog.md`                  | W23          | W20                      |
| `ml-diagnostics.md`              | W22, W24     | W20                      |
| `ml-drift.md`                    | W26          | —                        |
| `ml-feature-store.md`            | W27          | W30 (trajectory feature) |
| `ml-automl.md`                   | W27          | W32 (PACT gate)          |
| `ml-dashboard.md`                | W28          | W33 (km.dashboard)       |
| `ml-rl-core.md`                  | W29          | W30                      |
| `ml-rl-algorithms.md`            | W29          | —                        |
| `ml-rl-align-unification.md`     | W30          | W32                      |
| `kailash-core-ml-integration.md` | W31          | —                        |
| `dataflow-ml-integration.md`     | W31          | —                        |
| `nexus-ml-integration.md`        | W31          | W25 (serve channel)      |
| `kaizen-ml-integration.md`       | W32          | W24                      |
| `align-ml-integration.md`        | W32          | W30                      |
| `pact-ml-integration.md`         | W32          | W27 (AutoML gate)        |

Every spec has ≥1 primary wave. No orphan specs.

## Exit Criterion

All 34 waves complete + `/redteam` converges 2 consecutive clean rounds + `/release` authorization + PyPI 7-package wave installable via fresh `pip install kailash-ml==1.0.0`.
