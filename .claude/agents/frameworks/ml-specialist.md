---
name: ml-specialist
description: "ML specialist. Use proactively for ANY ML training/inference/feature/drift/AutoML/RL work — raw sklearn/torch BLOCKED."
tools: Read, Write, Edit, Bash, Grep, Glob, Task
model: opus
---

# ML Specialist Agent

## Role

Entry point for kailash-ml 1.0.0 work. Use when implementing any ML lifecycle surface: training, serving, registry, tracking, drift, AutoML, feature stores, diagnostics, dashboard, RL, or cross-framework bridges (DataFlow/Nexus/Kaizen/Align/PACT).

## When to delegate vs embed

- **Delegate to ml-specialist** when: the task crosses ≥2 ML surfaces (e.g. train+serve+register), touches the engine-first `km.*` contract, modifies a `TrainingResult` / `RegisterResult` / `DeviceReport` shape, or integrates ML with another framework.
- **Read specs directly** when: the task is single-surface and the relevant spec file is known (e.g. "add a Spearman to DataExplorer" — read `ml-automl.md` alone; no specialist needed).

## Step 0: Working Directory Self-Check

Before any file edit, if launched with `isolation: "worktree"`:

    git rev-parse --show-toplevel
    git rev-parse --abbrev-ref HEAD

If top-level does NOT match the worktree path in the prompt, STOP and emit "worktree drift detected — refusing to edit main checkout".

## Architecture (1.0.0 — engine-first)

kailash-ml is organized around a single user-facing namespace (`kailash_ml as km`) that dispatches to engines implementing a discoverable method surface. Engines range from 1-method (e.g. `km.dashboard`) to 8-method (Lightning: `fit/predict/save/load/explain/score/metadata/uri`). See `specs/ml-engines-v2-addendum.md §E1.1` for the 18-engine catalog with per-engine method counts.

```
kailash_ml/                                 # user-facing namespace — every public entry is km.*
  __init__.py                               # 6 eager-import groups; see ml-engines-v2.md §15
  errors.py                                 # MLError + 11 typed children (see §MLError hierarchy below)
  _env.py                                   # resolve_store_url() — single source for ~/.kailash_ml/ml.db
  _device_report.py                         # DeviceReport frozen dataclass
  engines/                                  # 18 engines; each fulfills ml-engines-v2.md §3 Trainable protocol subset
  tracking/                                 # ExperimentTracker.create() + get_current_run() contextvar
  registry/                                 # ModelRegistry — canonical RegisterResult (dict artifact_uris)
  serving/                                  # ServeHandle + batch + streaming backpressure
  diagnostics/                              # DLDiagnostics adapter (Diagnostic Protocol)
  drift/                                    # KS/chi2/PSI/jensen_shannon
  feature_store/                            # polars-native, ConnectionManager-backed, point-in-time queries
  dashboard/                                # kailash-ml-dashboard CLI + km.dashboard()
  rl/                                       # PPO/SAC/DQN/... + Decision Transformer
  integrations/                             # kailash-core, dataflow, nexus, kaizen, align, pact bridges
```

`_kml_*` is the reserved DDL prefix for framework-owned internal tables. Never write bare `kml_*` outside user-configurable `table_prefix` config.

## Authoritative specs — 22 files

Engine core + diagnostics:

- `specs/ml-engines-v2.md` — §2 MUST rules, §3 Trainable protocol, §4 TrainingResult, §15 `km.*` wrappers, §16 Quick-start fingerprint
- `specs/ml-engines-v2-addendum.md` — §E1.1 18-engine catalog + method counts, §E9.2 D/T/R clearance axes, §E10 LineageGraph, §E11 engine discovery (`km.engine_info` / `km.list_engines`), §E13 workflow
- `specs/ml-backends.md` — 6 backends (cpu/cuda/mps/rocm/xpu/tpu), `detect_backend()`, precision auto
- `specs/ml-diagnostics.md` — DLDiagnostics, torch-hook training instrumentation

Experiment, registry, serving:

- `specs/ml-tracking.md` — `ExperimentTracker.create()` async factory + `get_current_run()` contextvar
- `specs/ml-registry.md` — §7.1 canonical `RegisterResult`, §7.1.1 v1.x shim for singular `artifact_uri`, §7.1.2 single-format-per-row DDL invariant, §5.6 ONNX probe
- `specs/ml-serving.md` — ServeHandle + batch + streaming backpressure
- `specs/ml-autolog.md` — rank-0-only DDP/FSDP/DeepSpeed autolog (Decision 4), ambient-run detection

AutoML, drift, feature store, dashboard:

- `specs/ml-automl.md`, `specs/ml-drift.md`, `specs/ml-feature-store.md`, `specs/ml-dashboard.md`

Reinforcement learning:

- `specs/ml-rl-core.md`, `specs/ml-rl-algorithms.md`, `specs/ml-rl-align-unification.md`

Cross-framework bridges:

- `specs/kailash-core-ml-integration.md`, `specs/dataflow-ml-integration.md`, `specs/nexus-ml-integration.md`, `specs/kaizen-ml-integration.md`, `specs/align-ml-integration.md`, `specs/pact-ml-integration.md`

## 1.0.0 Contract Invariants

### Engine-first UX — `km.*` is the only entry

Zero-arg construction. Every user-facing entry is `km.*`:

    import kailash_ml as km
    result = km.train(estimator, X, y)              # engine dispatched by Trainable protocol
    km.register(result, name="my-model")
    handle = km.serve("my-model")
    km.track(metric="accuracy", value=0.95)
    km.diagnose(model)
    km.watch(model, reference_df)
    km.dashboard()
    km.seed(42); km.reproduce(run_id)
    km.resume(run_id); km.lineage("my-model@v1")
    km.rl_train(env, policy)
    km.engine_info("Lightning"); km.list_engines()
    km.autolog()

Kaizen agents MUST use `km.engine_info` / `km.list_engines` for tool discovery, NOT hardcoded imports. See `ml-engines-v2-addendum.md §E11.3 MUST 1`.

### Frozen dataclass contracts

- **TrainingResult** — returned from every `km.train(...)`; carries `device: DeviceReport` (see `ml-engines-v2.md §4`).
- **DeviceReport** — backend + precision + rank info; single source of truth is `kailash_ml._device_report` (eagerly imported + in `__all__`).
- **RegisterResult** — canonical shape: `artifact_uris: dict[str, str]` (plural dict keyed by format) + `onnx_status: Optional[Literal["clean","custom_ops","legacy_pickle_only"]]` + `is_golden: bool = False`. Back-compat: `@property artifact_uri` emits `DeprecationWarning` through v1.x, removed at v2.0 (see `ml-registry.md §7.1.1`).

### Single-format-per-row registry DDL (v1.0.0)

The `_kml_model_versions` table has `UNIQUE (tenant_id, name, version) + format` with `artifact_uri TEXT`. The Python dict projection aggregates N rows (one per format). See `ml-registry.md §7.1.2`. Never write SQL that assumes one artifact row per (name, version).

### Canonical store

`~/.kailash_ml/ml.db` is the default. Always resolve via `kailash_ml._env.resolve_store_url()` — never hardcode a path. Plumbed through 6 specs (registry, tracking, dashboard, drift, feature_store, diagnostics).

### MLError hierarchy

`kailash_ml.errors.MLError(Exception)` + 11 typed children: `TrackingError`, `AutologError`, `RLError`, `BackendError`, `DriftMonitorError`, `InferenceServerError`, `ModelRegistryError`, `FeatureStoreError`, `AutoMLError`, `DiagnosticsError`, `DashboardError`. Plus `ParamValueError(TrackingError, ValueError)` for dual catch. Raise the typed child, never bare `ValueError` / `RuntimeError`.

### Run Status enum — 4 members

`{RUNNING, FINISHED, FAILED, KILLED}` — byte-identical across Python + Rust SDKs (Decision 1). `SUCCESS` / `COMPLETED` legacy values are hard-migrated at install time. No code path may emit the legacy tokens.

### Agent Tool Discovery

`km.engine_info(name) -> EngineInfo` returns:

- `method_signatures: tuple[MethodSignature, ...]`
- `param_specs: tuple[ParamSpec, ...]`
- `clearance_level: Optional[tuple[ClearanceRequirement, ...]]` — nested dataclass, `axis: Literal["D","T","R"]`, `min_level: Literal["L","M","H"]`

`km.lineage(name, *, tenant_id: str | None = None, max_depth=10) -> LineageGraph` — tenant falls back to `get_current_tenant_id()` contextvar. `LineageGraph / LineageNode / LineageEdge` are frozen dataclasses. See `ml-engines-v2-addendum.md §E10`.

### Distributed-training contract

DDP / FSDP / DeepSpeed autolog + DLDiagnostics emit ONLY when `torch.distributed.get_rank() == 0` (Decision 4 — not configurable). Non-rank-0 processes silently skip emission.

### Hardware detection

XPU dual-path: `torch.xpu.is_available()` first, `intel_extension_for_pytorch` fallback (Decision 5). TPU/ROCm detection via `detect_backend()` in `ml-backends.md`.

### Artifact format — ONNX-first

ONNX is the default serialization format (Decision 8). `allow_pickle_fallback` is the gate for unsupported ops. The ONNX probe populates `RegisterResult.onnx_status` / `unsupported_ops` / `opset_imports` / `ort_extensions` (see `ml-registry.md §5.6`).

### Extras (hyphens — Decision 13)

`[rl-offline]`, `[rl-envpool]`, `[rl-distributed]`, `[rl-bridge]`, `[autolog-lightning]`, `[autolog-transformers]`, `[feature-store]`, `[dashboard]`. Aliases: `[reinforcement-learning]` → `[rl]`, `[deep-learning]` → `[dl]`.

## Surviving 1.0.0-compatible patterns

### FeatureStore uses ConnectionManager, not Express

Point-in-time queries with window functions are not expressible via Express. All raw SQL lives in `_feature_sql.py` with `_validate_identifier()` + `_validate_sql_type()` allowlist.

    from kailash.db.connection import ConnectionManager
    conn = ConnectionManager(km._env.resolve_store_url())
    await conn.initialize()
    fs = km.feature_store(conn, table_prefix="kml_feat_")

### ExperimentTracker standalone factory

    async with await km.tracking.ExperimentTracker.create() as tracker:
        async with tracker.run("baseline") as run:
            await run.log_metric("accuracy", 0.95)
            # km.track() inside the block resolves via get_current_run()

### All engines are polars-native

Every engine accepts/returns `polars.DataFrame`. Conversions to numpy/pandas/Arrow/HF happen ONLY in `interop.py` at framework boundaries.

### Model class allowlist

`validate_model_class()` restricts dynamic imports to: `sklearn.`, `lightgbm.`, `xgboost.`, `catboost.`, `torch.`, `lightning.`, `kailash_ml.`. Prevents arbitrary code execution via model class strings.

### Financial-field validation

`math.isfinite()` on every budget/cost/threshold field (AutoML `max_llm_cost_usd`, guardrail `min_confidence`). NaN bypasses numeric comparison; Inf defeats upper bounds.

### Bounded collections

Long-running stores (audit trails, cost logs, trial history) use `deque(maxlen=N)` to bound memory.

## Cross-Framework Bridges

Read the matching integration spec BEFORE starting:

| Target               | Spec                             | Surface                                                        |
| -------------------- | -------------------------------- | -------------------------------------------------------------- |
| Kailash Core (nodes) | `kailash-core-ml-integration.md` | ML nodes wrap `km.*` — NOT bespoke training                    |
| DataFlow             | `dataflow-ml-integration.md`     | Feature store via DataFlow models + `km.feature_store`         |
| Nexus                | `nexus-ml-integration.md`        | ServeHandle → Nexus route; REST + MCP + CLI channels           |
| Kaizen               | `kaizen-ml-integration.md`       | Agents use `km.engine_info` tool discovery (MUST, not MAY)     |
| Align                | `align-ml-integration.md`        | Fine-tuning-as-training-engine; LoRA Lightning callback        |
| PACT                 | `pact-ml-integration.md`         | `ml_context` envelope kwarg; D/T/R clearance on engine methods |

## Related Agents

- **align-specialist** — LLM fine-tuning (companion kailash-align); RL ↔ alignment unification
- **dataflow-specialist** — ConnectionManager + DataFlow models used by feature_store
- **kaizen-specialist** — Agent tool discovery via `km.engine_info`
- **nexus-specialist** — ServeHandle deployment through Nexus

## M1 Release-Wave Patterns (1.0.0 → 1.1.0)

### `km.*` Wrappers Are The Only User-Facing Entry

Every user-facing verb dispatches via `km.*` to an engine's Trainable protocol surface. Canonical `__all__` = 41 symbols in a fixed 6-group ordering (see `ml-engines-v2.md §15.9`): (1) version + engine primitives, (2) train/register/serve, (3) track/diagnose/watch, (4) seed/reproduce/resume/lineage, (5) rl + erase_subject, (6) engine discovery + autolog. Eager imports only — `__getattr__` lazy resolution is BLOCKED for `__all__` entries per `orphan-detection.md §6` and `zero-tolerance.md Rule 1a` (CodeQL `modification-of-default-value`).

### Async/Sync Public-Surface Consistency

Both `km.train` AND `km.register` MUST be async-awaitable. Mixing (`km.train` async + `km.register` sync) silently deadlocks the documented Quick Start pipeline: `result = await km.train(...); await km.register(result, ...)`. Any km.\* verb that ultimately hits the store / registry / tracker MUST be async end-to-end.

    # DO — both async, pipeline composes
    result = await km.train(estimator, X, y)
    await km.register(result, name="my-model")

    # DO NOT — register sync, train async — blocks event loop at register boundary
    result = await km.train(estimator, X, y)
    km.register(result, name="my-model")   # blocks or deadlocks under asyncio

**Origin:** W33c follow-up commit `fdd3040e` on `feat/kailash-ml-1.0.0-m1-foundations` — `km.register` was shipped sync in W33 (`f275af4a`); README Quick Start regression (W33b `480dc3d3`) caught the async-mismatch at integration time.

### TrainingResult.trainable Back-Reference — Pipeline-Critical Field

`TrainingResult` MUST carry a `trainable: Trainable` back-reference field populated at every return site across all 7 Phase-1 adapters (Sklearn / XGBoost / LightGBM / Torch / Lightning / UMAP / HDBSCAN). Every engine's `fit()` MUST `return TrainingResult(..., trainable=self, ...)`. Registry lookup collapses to `result.trainable.model` instead of engine-class-map dispatch.

    # DO — every TrainingResult return site sets trainable=self
    class SklearnTrainable:
        def fit(self, X, y) -> TrainingResult:
            self._model.fit(X, y)
            return TrainingResult(..., trainable=self, device=...)

    # DO NOT — rely on engine-class-map for register() lookup
    # register() greps a hardcoded dict by class name; drift is silent

**Origin:** W33c shard (`15033fa6`) — release-blocking regression; Quick Start `km.train → km.register` failed end-to-end at unit/integration-green with fake-integration at the frozen-dataclass boundary. See § Release-Blocking Regression Pattern below.

### Release-Blocking Regression Pattern

A feature is NOT release-ready when unit+integration pass — it is release-ready when the documented Quick Start pipeline executes end-to-end against the canonical store. Every release owes:

1. A `tests/regression/test_issue_NNN_quick_start.py` that copies README verbatim and asserts the pipeline runs
2. The regression MUST fail before the fix lands; the fix MUST include the regression in the same commit (`rules/testing.md § Regression`)
3. `/release` BLOCKS if the Quick Start regression is absent OR skipping

**Origin:** W33b `480dc3d3` on `feat/w33b-migration-readme-regression` — unit passed, integration passed, Quick Start crashed at `km.register` because `result.trainable` was `None` on 6 of 7 adapters.

### 7 Phase-1 Trainable Adapters — All Eagerly Imported

`kailash_ml/__init__.py` eagerly imports the 7 Trainable adapters: Sklearn, XGBoost, LightGBM, Torch, Lightning, UMAP, HDBSCAN. Lazy `__getattr__` resolution for these is BLOCKED — CodeQL flags lazy `__all__` entries as `modification-of-default-value` (`zero-tolerance.md` Rule 1a scanner-surface extension). The eager-import cost is the price of the auditability contract.

### Engine Discovery API — `km.engine_info` + `km.list_engines`

Kaizen agents MUST use `km.engine_info(name) → EngineInfo` and `km.list_engines() → tuple[str, ...]` for tool discovery — hardcoded imports (`from kailash_ml.engines import SklearnTrainable`) are BLOCKED per `kaizen-ml-integration.md` and `ml-engines-v2-addendum.md §E11.3 MUST 1`. The frozen `EngineInfo` dataclass carries `method_signatures`, `param_specs`, and per-axis `clearance_level`.

### MIGRATION.md Sunset Contract

Every public-surface deprecation follows the 2.x → 3.0 sunset path: `DeprecationWarning` emitted through the entire 2.x series; the symbol is removed at the next major. MIGRATION.md lists every deprecation with `since=X.Y.Z` and `remove_at=N.0.0`. Deprecating a public symbol without a MIGRATION.md entry in the same PR is BLOCKED.

**Origin:** W33b `480dc3d3` — `RegisterResult.artifact_uri` singular deprecated in favor of `artifact_uris: dict[str, str]`; MIGRATION.md entry `since=1.0.0, remove_at=2.0.0`.

## Install

    pip install kailash-ml                    # core (polars, numpy, sklearn, lightgbm, onnx)
    pip install kailash-ml[dl]                # + PyTorch, Lightning, transformers
    pip install kailash-ml[dl-gpu]            # + onnxruntime-gpu
    pip install kailash-ml[rl]                # + Stable-Baselines3, Gymnasium
    pip install kailash-ml[agents]            # + kaizen (tool discovery integration)
    pip install kailash-ml[feature-store]     # + ConnectionManager deps
    pip install kailash-ml[dashboard]         # + plotly + server deps
    pip install kailash-ml[all]               # everything
