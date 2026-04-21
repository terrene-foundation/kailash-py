# Round-2 Phase-B /redteam — Implementation Feasibility Audit

**Persona:** Implementation Feasibility Auditor
**Input:** 15 drafts at `workspaces/kailash-ml-audit/specs-draft/ml-*-draft.md`
**Question per MUST clause:** "Do I have enough detail to write the code without asking another question?"
**Date:** 2026-04-21

15 drafts audited (note: the brief said 13; there are actually 15 including `ml-engines-v2-addendum-draft.md` which is not standalone but an enrichment pass, and `ml-rl-core` + `ml-rl-algorithms` + `ml-rl-align-unification` which are 3 coupled drafts rather than one `ml-rl` file).

---

## Section A — Per-Spec Feasibility Scorecard

Legend: `Y` complete / `P` partial / `N` missing. "Verdict" column rolls up to READY / NEEDS-PATCH / BLOCKED.

| Spec                          | Signatures                                              | Dataclasses                                                                                                                                                             | Invariants testable | Schemas                                                                                       | Errors named                                                                                                                                              | Extras declared                                                         | Migration specified                                           | **Verdict**     |
| ----------------------------- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------- | --------------- |
| ml-tracking-draft             | Y                                                       | Y                                                                                                                                                                       | Y                   | Y (7 tables)                                                                                  | Y (13)                                                                                                                                                    | P (no extras section)                                                   | P (legacy demote described; no data-migration script outline) | **NEEDS-PATCH** |
| ml-autolog-draft              | Y                                                       | P (no AutologConfig / AutologHandle dataclasses)                                                                                                                        | Y                   | N/A                                                                                           | Y (5)                                                                                                                                                     | Y (7 extras)                                                            | N/A (new spec)                                                | **NEEDS-PATCH** |
| ml-diagnostics-draft          | Y                                                       | Y (ClassifierReport/RegressorReport/ClusteringReport)                                                                                                                   | Y                   | N/A                                                                                           | P (4 event types but no class names)                                                                                                                      | Y ([dl]/[rag]/[interpret]/[stats])                                      | N/A (extends v0.17)                                           | **NEEDS-PATCH** |
| ml-backends-draft             | Y                                                       | Y (BackendInfo)                                                                                                                                                         | Y                   | N/A                                                                                           | Y (3)                                                                                                                                                     | Y ([cuda]/[rocm]/[xpu]/[tpu])                                           | N/A                                                           | **READY**       |
| ml-registry-draft             | Y                                                       | Y (RegisterResult/PromoteResult/DemoteResult/ModelDiff)                                                                                                                 | Y                   | Y (\_kml_model_versions + aliases + audit implicit)                                           | Y (13)                                                                                                                                                    | P (format extras mentioned, no table)                                   | Y (§2.2 data migration outline)                               | **NEEDS-PATCH** |
| ml-drift-draft                | Y                                                       | Y (DriftMonitorConfig/AlertConfig/AlertRule/DriftAlert/ReferenceNotFoundError)                                                                                          | Y                   | Y (4 tables)                                                                                  | Y (9)                                                                                                                                                     | P (min_samples noted; no extras matrix)                                 | N/A (new tables)                                              | **NEEDS-PATCH** |
| ml-serving-draft              | Y                                                       | Y (InferenceServerConfig/ShadowSpec/CanarySpec/CacheSpec/RateLimitSpec/BatchInferenceResult)                                                                            | Y                   | Y (shadow + batch_jobs + inference_audit named, DDL not written)                              | Y (11)                                                                                                                                                    | P ([grpc] referenced; no pyproject fragment)                            | P (dashboard DB default change noted; no migration script)    | **NEEDS-PATCH** |
| ml-feature-store-draft        | Y                                                       | Y (no FeatureGroup dataclass given, described)                                                                                                                          | Y                   | P (tables named `_kml_feat_*` + `_kml_feature_groups` + `_kml_feature_audit` but no full DDL) | Y (10)                                                                                                                                                    | P (no extras matrix; Redis/DynamoDB adapters mentioned)                 | N/A (new)                                                     | **NEEDS-PATCH** |
| ml-dashboard-draft            | Y                                                       | Y (RunSummary/MetricSeries TypedDict)                                                                                                                                   | Y                   | N/A                                                                                           | N (error classes not enumerated as a named taxonomy)                                                                                                      | N (no [dashboard] extra declared despite Starlette/plotly/uvicorn deps) | N/A (new)                                                     | **NEEDS-PATCH** |
| ml-automl-draft               | Y                                                       | Y (AutoMLConfig/LeaderboardEntry/LeaderboardReport)                                                                                                                     | Y                   | P (`_kml_automl_agent_audit` named, no DDL)                                                   | Y (9)                                                                                                                                                     | P ([ray]/[dask]/[agents] mentioned, no pyproject fragment)              | N/A (new engine wires)                                        | **NEEDS-PATCH** |
| ml-rl-core-draft              | Y                                                       | Y (RLTrainingResult/EvalRecord/EpisodeRecord/PolicyArtifactRef)                                                                                                         | Y                   | N/A                                                                                           | Y (10)                                                                                                                                                    | Y ([rl]/[rl-offline]/[rl-distributed]/[rl-envpool])                     | Y (§16 migration path)                                        | **READY**       |
| ml-rl-algorithms-draft        | Y                                                       | Y (HyperparameterSpec/AlgorithmAdapter Protocol)                                                                                                                        | Y                   | N/A                                                                                           | P (no RL-algorithm-specific error taxonomy section — inherits from core)                                                                                  | Y                                                                       | N/A                                                           | **READY**       |
| ml-rl-align-unification-draft | Y                                                       | Y (RLLineage/RLLifecycleProtocol)                                                                                                                                       | Y                   | N/A                                                                                           | P (FeatureNotAvailableError named; other errors inherited from core)                                                                                      | Y ([rl-bridge] extra defined)                                           | Y (§10 migration path)                                        | **READY**       |
| ml-engines-v2-draft           | Y                                                       | Y (TrainingResult/SetupResult/ComparisonResult/PredictionResult/FinalizeResult/EvaluationResult/RegisterResult/ServeResult all listed, only TrainingResult fleshed out) | Y                   | N/A (defers to siblings)                                                                      | Y (9)                                                                                                                                                     | P (references [dl]/[interpret] etc. no consolidated extras table)       | Y (§8 legacy namespace)                                       | **NEEDS-PATCH** |
| ml-engines-v2-addendum-draft  | P (18-engine matrix gives names + methods but not sigs) | P (EngineInfo/LineageGraph mentioned, not defined)                                                                                                                      | Y                   | N/A                                                                                           | P (mentions TenantIsolationMismatchError, ActorRequiredError, ClearanceDeniedError, TenantQuotaExceededError, CrossTenantReadError — no taxonomy section) | N                                                                       | P (merge instructions provided; no data migration)            | **NEEDS-PATCH** |

**Summary:** 0 BLOCKED, 11 NEEDS-PATCH, 4 READY. Target for Phase-C entry: 0 NEEDS-PATCH via the fixes in Section B.

---

## Section B — HIGH Findings

Each HIGH is a spec that cannot be implemented without additional design decisions. Ordered by severity.

### B1. HIGH — `ml-dashboard-draft` missing `[dashboard]` extra declaration

**Spec:** `ml-dashboard-draft.md §9.1 + §9.3`
**Gap:** Dashboard declares Starlette, uvicorn, plotly as dependencies ("Starlette is already a transitive dep via `kailash-nexus`"). But plotly.min.js is bundled as a static asset (~3MB), and nothing pins the plotly Python version. No `[dashboard]` or `[dashboard-sse]` extra is defined. An implementer cannot generate the correct `pyproject.toml` fragment.

**Feasibility decision needed:**

- Is plotly a core dep of kailash-ml (already in base via ModelVisualizer? check) OR a new `[dashboard]` extra?
- Is `uvicorn` required in `[dashboard]` (for standalone run)?
- Is `jinja2` required (templates)?

**Verdict:** HIGH — one extras table needed before /implement starts. Estimated fix: 15 minutes.

### B2. HIGH — `ml-dashboard-draft` missing error taxonomy section

**Spec:** `ml-dashboard-draft.md` — no §Errors section.

**Gap:** REST handlers raise HTTP 400/401/403/404/413/429/500. CLI exits with codes 1-4 (§8.4). Security section references "return 403" and "return 429" but no Python exception classes are enumerated. Per the audit brief Question 6 ("Every error scenario named — No `... and possibly others`"), dashboard has no error taxonomy.

**Feasibility decision needed:** Enumerate `DashboardError` subclasses: `DashboardStoreUnreachableError`, `DashboardAuthDeniedError`, `DashboardTenantMismatchError`, `DashboardArtifactPathTraversalError`, `DashboardRateLimitExceededError`, `DashboardBackpressureDroppedError`.

**Verdict:** HIGH — 30 minutes to enumerate.

### B3. HIGH — `ml-engines-v2-addendum-draft` Enrichment 11 (`EngineInfo`) has no dataclass definition

**Spec:** `ml-engines-v2-addendum-draft.md §E11.1`

```python
info = km.engine_info("TrainingPipeline")
# EngineInfo(
#   name="TrainingPipeline",
#   module="kailash_ml.engines.training_pipeline",
#   public_methods=["train"],
#   signature_per_method={...},
#   requires_extras=[],
#   tenant_aware=True,
#   tracker_auto_wired=True,
# )
```

**Gap:** `signature_per_method={...}` is elided. What type? `dict[str, inspect.Signature]`? `dict[str, CallableSpec]`? The `CallableSpec` dataclass (if it exists) is not defined. Every agent-tool-call integration (Kaizen) depends on this shape.

**Feasibility decision needed:** Define `EngineInfo` as a frozen dataclass with fully typed fields. Define the `signature_per_method` element type explicitly (propose: `dict[str, MethodSignature]` where `MethodSignature` has `{name: str, params: list[ParamSpec], return_type: str, is_async: bool}`).

**Verdict:** HIGH — 20 minutes. Affects Kaizen agent tool discovery.

### B4. HIGH — `ml-engines-v2-addendum-draft` Enrichment 10 (`LineageGraph`) has no schema

**Spec:** `ml-engines-v2-addendum-draft.md §E10.2 MUST 1`

```python
engine.lineage(model_uri="models://User/v3") -> LineageGraph
```

**Gap:** `LineageGraph` is named but not defined. §E10.1 lists 7 fields a lineage query MUST return ("the registered model", "the training run", etc.) but no dataclass. Cross-spec contract with `ml-dashboard-draft.md §4.1` `/api/v1/lineage/{run_id}` returns `{nodes: list[...], edges: list[...]}` — different shape. The two specs will implement two different types.

**Feasibility decision needed:** Pick ONE shape. Recommend `LineageGraph = {nodes: list[LineageNode], edges: list[LineageEdge], root_model_uri: str, tenant_id: str | None}` with `LineageNode.kind ∈ {"model", "run", "feature_version", "dataset", "endpoint", "monitor"}`.

**Verdict:** HIGH — 30 minutes. Cross-spec consistency blocker.

### B5. HIGH — `ml-autolog-draft` `AutologConfig` / `AutologHandle` undefined

**Spec:** `ml-autolog-draft.md §2.1 + §3.2`

```python
async def autolog(...) -> AsyncIterator[AutologHandle]: ...
```

```python
class FrameworkIntegration(ABC):
    def attach(self, run: "ExperimentRun", config: AutologConfig) -> None: ...
```

**Gap:** Both types referenced, neither defined. `AutologConfig` presumably packages the 7 kwargs from §2.1 (`disable`, `log_models`, `log_datasets`, `log_figures`, `log_system_metrics`, `sample_rate_steps`, `disable_metrics`), but this is implied, not explicit.

**Feasibility decision needed:** Define both frozen dataclasses. Propose:

```python
@dataclass(frozen=True)
class AutologConfig:
    enabled_frameworks: frozenset[str]
    disable: frozenset[str]
    log_models: bool
    log_datasets: bool
    log_figures: bool
    log_system_metrics: bool
    sample_rate_steps: int
    disable_metrics: tuple[str, ...]   # glob patterns

@dataclass(frozen=True)
class AutologHandle:
    config: AutologConfig
    attached_integrations: tuple[str, ...]
    run_id: str
```

**Verdict:** HIGH — 15 minutes.

### B6. HIGH — `ml-serving-draft` shadow table DDL missing

**Spec:** `ml-serving-draft.md §6.2 + §4.5 + §11.4`

Tables named: `_kml_shadow_predictions`, `_kml_inference_batch_jobs`, `_kml_inference_audit`.

**Gap:** Column lists described in prose (e.g. "tenant_id, request_id, main_version, shadow_version, main_output_fingerprint, shadow_output_fingerprint, divergence, occurred_at") — no DDL, no types, no indexes. `ml-drift-draft.md §6.5` consumes `_kml_shadow_predictions` directly — the two specs MUST agree on column names and types. Without DDL the implementer guesses.

**Feasibility decision needed:** Write 3 DDL blocks (one per table) with column types + indexes. Match `ml-registry-draft.md §14.2 audit ("actor_id" string, "tenant_id" string) pattern.

**Verdict:** HIGH — 30 minutes. Cross-spec shadow consumption blocker.

### B7. HIGH — `ml-feature-store-draft` table DDL missing

**Spec:** `ml-feature-store-draft.md §9.2 MUST 1 + §13.2`

**Gap:** References to `_kml_feature_groups`, `_kml_feature_audit`, and "per-feature-group tables named `_kml_feat_{group_name}`" — no schemas. §8.3 mentions `fs.erase_tenant(...)` drops every `_materialized_*` row but the table name pattern `_materialized_*` conflicts with `_kml_feat_*` prefix (§6.2 MUST 2 adds `_materialized_at TIMESTAMP column` — the table still has `_kml_feat_` prefix? unclear). Two naming conventions coexisting without resolution.

**Feasibility decision needed:** Pick one table naming convention. Write DDL for `_kml_feature_groups`, `_kml_feature_audit`, and the dynamic-per-group `_kml_feat_{name}_v{version}` (DDL template).

**Verdict:** HIGH — 45 minutes.

### B8. HIGH — `ml-tracking-draft` migration script outline missing

**Spec:** `ml-tracking-draft.md §15 (Changelog) + §2.3`

**Gap:** Spec states `SQLiteTrackerBackend` is "demoted to storage driver; public re-exports removed at 2.0.0" and "callers that imported `SQLiteTrackerBackend` directly from the public surface before 2.0 receive a `DeprecationWarning` shim during the 0.x → 2.0 transition". But:

- No `kailash_ml.legacy.*` equivalent is declared for `SQLiteTrackerBackend` (unlike `ml-engines-v2-draft.md §8`).
- No data migration for existing `~/.kailash_ml/kailash-ml.db` users → `~/.kailash_ml/ml.db` (dashboard was reading the former; tracker was writing the latter).
- No numbered migration file referenced for the schema DDL in §6.3.

**Feasibility decision needed:**

1. Migration `0001_create_kml_tracking_v2.py` that creates the 7 tables.
2. Migration `0002_import_from_legacy_ml_db.py` that reads legacy DB if present and re-inserts into new DB.
3. Legacy-namespace shim `kailash_ml.legacy.SQLiteTrackerBackend` with `DeprecationWarning`.

**Verdict:** HIGH — 60 minutes.

### B9. HIGH — `ml-engines-v2-draft §8.2` and `ml-registry-draft §2.2` inconsistent on `AutoMLEngine` / `EnsembleEngine` legacy status

**Spec:** `ml-engines-v2-draft.md §8.2` demotes `AutoMLEngine` to `kailash_ml.legacy`; `ml-automl-draft.md §2.1` reinstates `AutoMLEngine` as a first-class constructible class. Similarly `EnsembleEngine` → `Ensemble` in §8.2 but `ml-automl-draft.md §7.1` uses `Ensemble`.

**Gap:** Conflict. Are `AutoMLEngine` and `Ensemble` top-level 2.0 classes or legacy shims?

**Feasibility decision needed:** Reconcile. Recommendation: `AutoMLEngine` and `Ensemble` are top-level 2.0 classes; `ml-engines-v2-draft.md §8.2` row needs deletion OR rewording ("v0.9.x `AutoMLEngine` class survives at top-level; the v0.9.x single-family-centric API is demoted").

**Verdict:** HIGH — 15 minutes for alignment edit across two specs.

### B10. HIGH — `ml-rl-core-draft §13` error taxonomy table has malformed rows

**Spec:** `ml-rl-core-draft.md §13`

```
| `RewardModelRequiredError`    | `algo="ppo-rlhf"                                                                      | "dpo" | ...`without`reward_model` kwarg OR preference data |
```

**Gap:** The `RewardModelRequiredError` row has pipe-escaped content that renders broken — the "algo" string is split across 4 columns. Implementers cannot parse the trigger condition. Cosmetic-looking but load-bearing (this error's triggering condition is the RLHF kwarg contract).

**Feasibility decision needed:** Rewrite the row. Propose:

```
| `RewardModelRequiredError` | algo in {"ppo-rlhf", "dpo", "rloo", "online-dpo"} without `reward_model` AND without `preference_dataset` kwarg |
```

**Verdict:** HIGH (table-parse bug) — 5 minutes.

---

## Section C — Implementation Shard Estimation Table

Per `rules/autonomous-execution.md` capacity bands (≤500 LOC load-bearing logic, ≤5-10 invariants, ≤3-4 call-graph hops). Estimate `shard_count` = session count needed. `order` = dependency-ordered implementation sequence. `blockers` = upstream spec that MUST land first.

| Spec                    | Shard count | Order | Blockers                                                                                                                                                                                                                                                                            |
| ----------------------- | ----------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ml-backends             | 1           | 1a    | None (foundation — detect_backend, BackendInfo, resolve_precision)                                                                                                                                                                                                                  |
| ml-tracking             | 3           | 1b    | ml-backends (TrainingResult carries BackendInfo). 3 shards: (a) canonical ExperimentTracker + 7-table DDL + keyspace + tenant, (b) `ExperimentRun` async context + log_metric/log_param/log_figure, (c) `diff_runs` + MCP server + MLflow import                                    |
| ml-engines-v2 (main)    | 3           | 2     | ml-backends, ml-tracking. Shards: (a) `MLEngine.__init__` + zero-arg construction + DI overrides, (b) 8-method surface with stub `TrainingResult` returns, (c) `Trainable` protocol + LightningModule adapters for 6 families                                                       |
| ml-engines-v2-addendum  | 2           | 3     | ml-engines-v2 main. Shards: (a) 18-engine matrix wiring + fluent chain + contextvar auto-wire helper, (b) Prometheus + OTel + quotas + PACT clearance                                                                                                                               |
| ml-registry             | 2           | 4a    | ml-engines-v2. Shards: (a) `_kml_model_versions` + migration from `_kml_models` + aliases + audit, (b) CAS artifact store + encryption + quotas + retention                                                                                                                         |
| ml-feature-store        | 3           | 4b    | ml-engines-v2. Shards: (a) offline store DDL + `@feature` + FeatureGroup + materialize, (b) Redis online store + sync + TTL, (c) point-in-time join + drift integration + tenant erasure                                                                                            |
| ml-autolog              | 3           | 5     | ml-tracking. Shards: (a) `autolog()` context + `FrameworkIntegration` ABC + sys.modules detection + registration, (b) 4 first-party integrations (Lightning, sklearn, transformers, xgboost), (c) remaining 3 (lightgbm, statsmodels, polars) + regression tests                    |
| ml-diagnostics          | 3           | 5     | ml-tracking, ml-engines-v2 (Trainable). Shards: (a) Protocol conformance + `km.diagnose` dispatch + tracker wiring, (b) DLDiagnostics + Lightning/transformers callbacks + DDP/FSDP + mixed-precision, (c) classical diagnosers (classifier/regressor/clustering) + plot dashboards |
| ml-serving              | 3           | 6     | ml-registry, ml-tracking, ml-drift (shadow feed). Shards: (a) `InferenceServer` + ONNX load + REST/MCP mount + 9 Prometheus metrics + audit row, (b) shadow + canary + reload-on-promotion, (c) batch + streaming (SSE/gRPC) + tenant isolation                                     |
| ml-drift                | 2           | 6     | ml-registry, ml-serving (shadow table). Shards: (a) 3 drift axes + reference persistence + tenant isolation, (b) restart-surviving scheduler + alerts + performance drift                                                                                                           |
| ml-dashboard            | 2           | 7     | ml-tracking, ml-registry, ml-drift (panel data). Shards: (a) Starlette ASGI + 18 REST endpoints + auth + tenant scope, (b) SSE broker + WebSocket control + 14 panels + CLI entry point                                                                                             |
| ml-rl-core              | 2           | 6     | ml-engines-v2, ml-backends. Shards: (a) `km.rl_train` + environment protocol + buffers + policy/value/Q protocols + RLLifecycleProtocol stub, (b) `RLDiagnostics` + tracker wiring + checkpoint/resume + eval rollouts                                                              |
| ml-rl-algorithms        | 2           | 7     | ml-rl-core. Shards: (a) 3 on-policy + 4 off-policy adapters (SB3), (b) 3 offline adapters (d3rlpy) + RLHF dispatch stubs                                                                                                                                                            |
| ml-rl-align-unification | 1           | 8     | ml-rl-core, ml-rl-algorithms, kailash-align 0.5.0. Single shard: `kailash_align.rl_bridge` with 4 bridge adapters + cross-SDK test                                                                                                                                                  |
| ml-automl               | 2           | 8     | ml-engines-v2, ml-tracking, ml-feature-store. Shards: (a) HyperparameterSearch + 6 algorithms + local executor + nested runs, (b) Ray/Dask executors + agent-augmented + baseline parallel + cost cap                                                                               |

**Total: 34 shards** across 14 specs (the addendum merges into the main engines spec at implementation time). Distributed across ~8 dependency waves, with 4 specs requiring 3 shards each (tracking, engines-v2, feature-store, autolog, diagnostics, serving).

**Specs exceeding 3-shard budget:** 0. The audit brief's threshold ("Flag any spec whose implementation would require >3 shards — too large for a single session") is not violated. Three specs (ml-tracking, ml-engines-v2, ml-serving, ml-feature-store, ml-autolog, ml-diagnostics) hit exactly 3 shards — at the upper boundary, sharding decisions MUST land at `/todos` time not `/implement` time per `rules/autonomous-execution.md §1` Rule 1.

**Parallelization opportunities:**

- Wave 1: ml-backends (1 shard) + ml-tracking (3 shards, parallel across 3 worktrees).
- Wave 4: ml-registry (2) + ml-feature-store (3) can run in parallel once ml-engines-v2 lands.
- Wave 5: ml-autolog (3) + ml-diagnostics (3) can run fully parallel.
- Wave 6: ml-serving (3) + ml-drift (2) + ml-rl-core (2) can run in parallel (if ml-serving tolerates ml-drift shard 1 landing slightly after).

**Critical path:** ml-backends → ml-tracking → ml-engines-v2 → (ml-registry | ml-feature-store) → ml-serving. 5 waves × median 3 shards = ~15 critical-path shards. At one session per shard with parallelization across independent waves, ~15-20 sessions to full implementation. Per `rules/autonomous-execution.md §10x multiplier`, this is ~3 human-weeks of autonomous execution.

---

## Section D — Open TBD Inventory

Consolidated across all 15 drafts. Grep pattern `TBD|TODO|OPEN QUESTION|Open Question|Deferred To Round-2` found 27 items. Triaged:

### D.1 SAFE DEFAULT (decision is obvious and pre-seeded in the spec) — 14 items

1. **ml-tracking §App A Q1 — Status vocabulary migration**: "accept both on read; write FINISHED only". Safe default; proceed.
2. **ml-tracking §App A Q3 — `MetricValueError` inheritance**: "subclass both TrackingError AND ValueError". Safe default.
3. **ml-tracking §App A Q4 — Actor-resolution default**: "`require_actor=False` at engine construction, flipped to True by `multi_tenant=True`". Safe default.
4. **ml-tracking §App A Q5 — Table prefix `kml_` vs `kailash_ml:`**: pragmatic split by layer; safe.
5. **ml-tracking §App A Q7 — Cross-SDK status enum parity**: file as cross-SDK follow-up; not a blocker.
6. **ml-autolog §App A Q1 — Transformers model-card emission**: "YES behind log_models=True"; safe.
7. **ml-autolog §App A Q2 — Sklearn ONNX fallback**: "YES with WARN"; safe.
8. **ml-autolog §App A Q3 — Per-batch sample rate**: "1 for epoch-level, 1-in-10 for step-level"; safe.
9. **ml-autolog §App A Q4 — Polars fingerprint scope**: "only explicit"; safe.
10. **ml-autolog §App A Q5 — System-metrics cost**: "5s interval default"; safe.
11. **ml-autolog §App A Q6 — Thread-safety of attach/detach**: "contextvar sufficient"; safe.
12. **ml-autolog §App A Q7 — Cross-framework conflict**: "emit both"; safe.
13. **ml-registry §16 Q1 — Soft-delete TTL**: "365 days matches audit retention"; safe.
14. **ml-rl-align §11 D1-D5**: 5 open decisions already RESOLVED in the spec body (stated "RESOLVED in this draft"); not actually open.

### D.2 NEEDS DECISION (blocks a design choice in `/todos`) — 9 items

15. **ml-engines-v2 §10.4 Q1 — Default backend priority order**: lock OR configurable? Decision owner: human at /todos. Default recommended: **lock the order; env var override only for TPU-first shops** (constants.py module with `BACKEND_ORDER: tuple[str, ...]`).
16. **ml-engines-v2 §10.4 Q2 — Lightning hard lock-in with escape hatch**: BLOCKED or `escape_hatch.RawTrainer`? Default recommended: **BLOCKED with no exception** (research users drop to pure PyTorch, bypassing kailash-ml entirely — not a second kailash-ml surface).
17. **ml-engines-v2 §10.4 Q5 — Single-spec vs split-spec cross-SDK**: at loom/ classification. Recommend: single-spec-with-§10 (current) since most clauses shared verbatim.
18. **ml-engines-v2 §10.4 Q6 — Legacy namespace sunset**: lock to 3.0 or allow earlier? Default: **lock to 3.0**. `rules/zero-tolerance.md` Rule 4 is stronger than downstream-consumer-check.
19. **ml-backends §11 Q1 — ROCm/XPU/TPU runner availability**: infrastructure question. Human owns.
20. **ml-backends §11 Q2 — MPS bf16 status**: keep fp16 default; re-visit when PyTorch ≥ 2.5 ships. Low-priority decision.
21. **ml-backends §11 Q3 — TPU first-class vs experimental**: recommend **demote TPU to `[tpu-experimental]` extra**. Per §10.3 cons (1-2% market share, 40% maintenance burden), safe. Needs human sign-off.
22. **ml-backends §11 Q6 — CUDA bf16 probe**: use `torch.cuda.is_bf16_supported()` (safer than hand-coded CC table). Recommend accept.
23. **ml-serving §16 Q1 — gRPC vs MCP first**: recommend **REST+MCP core, gRPC [grpc] extra**. Needs human sign-off.

### D.3 BLOCKER (spec cannot progress without decision) — 4 items

24. **ml-backends §11 Q4 — XPU via ipex vs native `torch.xpu`**: decision affects `is_available()` probe, affects `BackendInfo.xpu_via_ipex` flag semantics. CANNOT be defaulted — the probe branches differently on each answer. Need: PyTorch 2.5 XPU native probe test on real PVC hardware.
25. **ml-backends §11 Q5 — ROCm bf16 cutoff (MI250 vs MI300)**: affects `resolve_precision()` truth table §3.2. CANNOT be guessed — wrong default silently downgrades precision. Need: hardware CI lane confirmation.
26. **ml-drift §13 Q1 — Reference sub-sampling seed per tenant**: "recommend yes, defer mechanism to implementation" — this IS a blocker because the default seed (42) is already in the spec. If "yes per tenant", the seed becomes `hash(tenant_id)`; if "no", stays 42. Every drift test that asserts reproducibility depends on this.
27. **ml-registry §16 Q3 — Audit row partitioning at 10M rows**: NOT a 2.0 blocker (v2.2) but the partitioning strategy affects v2.0 table creation (partition key column, partition-ready index shape). Recommend include partition-ready columns in v2.0 DDL so v2.2 migration is metadata-only.

### D.4 Spec Cross-Cutting Inconsistencies (additional blockers not in prose-flagged TBD lists)

28. **B4 — `LineageGraph` shape mismatch** between ml-engines-v2-addendum §E10.2 (returns `LineageGraph` object with 7 typed kinds of nodes) and ml-dashboard-draft §4.1 (returns `{nodes: list[...], edges: list[...]}`). Both paths MUST emit the same shape.
29. **B9 — `AutoMLEngine` / `Ensemble` legacy vs first-class** between ml-engines-v2 §8.2 (demoted to legacy) and ml-automl-draft §2.1 (first-class top-level). Reconcile before /implement.
30. **`@production` vs `"production"`** — ml-registry-draft §4.1 alias uses `"@production"` (with @ prefix); ml-engines-v2-draft §2.2 `engine.register(stage="staging"|"shadow"|"production")` does not include the @ prefix; ml-engines-v2-addendum E9.2 PACT matrix writes `stage="production"`. Pick one: recommend **alias strings carry `@`; stage strings do not**. ml-registry-draft §4.1 MUST 2 already uses `@production` for alias row (correct). ml-engines-v2 §2.2 `stage=` kwarg is a different field (confusing naming — rename to `alias="@production"`?).

---

## Summary — Verdict

- **READY:** 4 specs (ml-backends, ml-rl-core, ml-rl-algorithms, ml-rl-align-unification).
- **NEEDS-PATCH:** 11 specs. All fixes listed in Section B total ~4.5 hours of spec work.
- **BLOCKED:** 0 specs. No spec needs a Phase-C design session; every HIGH is a local patch.

**Open TBDs by triage:** 14 safe-default, 9 needs-decision, 4 blocker, 3 cross-cutting inconsistencies.

**Estimated Phase-C scope:** Patch the 10 HIGH findings from Section B (~4.5 hours spec work) + human sign-off on 4 BLOCKER TBDs (D3 items 24-27) + Section D4 cross-cutting reconciliation (~1 hour). **Total: half a session of focused spec editing** before /implement can start safely.

**Per `rules/autonomous-execution.md §Per-Session Capacity Budget`:** None of the 15 specs requires an implementation shard exceeding 500 LOC load-bearing logic / 5-10 invariants / 3-4 call-graph hops. Each spec's sharding is pre-computed in Section C and fits the budget.

**Phase-C recommendation:**

1. Apply B1-B10 patches (spec-editing, no design work).
2. Human resolves D3 items 24-27 (XPU/ROCm hardware lanes, drift seed, audit partition).
3. Apply D4 items 28-30 cross-cutting reconciliations.
4. Re-run Phase-B /redteam for verification.
5. Enter /implement with 34-shard plan from Section C.

---

_End of round-2b-feasibility.md. Author: Implementation Feasibility Auditor persona. 2026-04-21._
