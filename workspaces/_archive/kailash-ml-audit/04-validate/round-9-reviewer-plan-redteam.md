# Round 9 — /todos plan red team

Reviewer: quality-reviewer (kailash-py, 2026-04-21)
Inputs: `02-plans/01-master-34-wave-plan.md`, 34 `todos/active/W*.md`, `IT1-gpu-ci-runner.md`, Round-8 SYNTHESIS, `approved-decisions.md`, `specs/_index.md`.

## Verdict: APPROVE with conditions

Structural shape is sound (capacity budget mostly respected, migration safety present, release order correct, 14 decisions traceable). However there are **6 HIGH findings** that WILL leak past `/redteam` if `/implement` starts as-drafted, because three integration specs contain named surfaces that no wave explicitly claims. The conditions are narrow and should be resolvable in one todo-revision pass (no re-sharding required for most).

## Spec coverage table

21 pinned specs. "Primary" = wave is the authoritative delivery. "Secondary" = wave touches it but is not the owner. Status flags the largest structural drift this reviewer found.

| Spec                             | Primary wave  | Secondary       | Status                                                                                                                                                                                                                                                                                      |
| -------------------------------- | ------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ml-engines-v2.md`               | W19, W20, W21 | W7, W8, W9, W33 | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-engines-v2-addendum.md`      | W9            | W21, W33        | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-backends.md`                 | W7            | W8, W19         | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-tracking.md`                 | W10-W15       | W33             | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-registry.md`                 | W16, W17, W18 | W21, W32        | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-serving.md`                  | W25           | W21, W31        | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-autolog.md`                  | W23           | W20             | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-diagnostics.md`              | W22           | W24, W20        | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-drift.md`                    | W26           | —               | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-feature-store.md`            | W27           | W30             | AMBER — DataFlow-side binding (`dataflow.ml_feature_source`, `dataflow.transform`, `dataflow.hash`) not wired in W27/W31                                                                                                                                                                    |
| `ml-automl.md`                   | W27           | W32             | AMBER — PACT `check_trial_admission` call-site not declared                                                                                                                                                                                                                                 |
| `ml-dashboard.md`                | W28           | W33             | AMBER — `auth="nexus"` adapter not declared in W28 or W31                                                                                                                                                                                                                                   |
| `ml-rl-core.md`                  | W29           | W30             | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-rl-algorithms.md`            | W29           | —               | GREEN                                                                                                                                                                                                                                                                                       |
| `ml-rl-align-unification.md`     | W30           | W32             | GREEN                                                                                                                                                                                                                                                                                       |
| `kailash-core-ml-integration.md` | W31           | W1              | **HIGH** — W31 names `TrainNode/PredictNode/ServeNode` but spec mandates `MLTrainingNode/MLInferenceNode/MLRegistryPromoteNode`; `kailash.observability.ml` metrics module + `src/kailash/ml/errors.py` + `src/kailash/tracking/migrations/` also missing from W31                          |
| `dataflow-ml-integration.md`     | W31           | W27             | **HIGH** — W31 calls surface `TrainingContext`+`lineage_dataset_hash` but spec's 3 mandates are `ml_feature_source`, `dataflow.transform`, `dataflow.hash`; none appear in any wave                                                                                                         |
| `nexus-ml-integration.md`        | W31           | W25, W28        | **HIGH** — W31 calls `mount_ml_endpoints`+`dashboard_embed`; spec's 4 mandates are `kailash_nexus.context._current_tenant_id`, `_current_actor_id`, `MLDashboard(auth="nexus")` adapter, inference-endpoint tenant propagation. None explicit in W28/W31                                    |
| `kaizen-ml-integration.md`       | W32           | W24             | **HIGH** — W32 names §2.4 Agent Tool Discovery + SQLiteSink + CostTracker; spec's 4 mandates also include **`tracker=` kwarg on `AgentDiagnostics`/`LLMDiagnostics`/`InterpretabilityDiagnostics`** and auto-emission from every `record_*`/`track_*` method — neither is in W32 invariants |
| `align-ml-integration.md`        | W32           | W30             | **HIGH** — W32 names LoRA Lightning callback + `Trajectory` import; spec's 4 mandates include 4 concrete TRL-adapter classes (`DPOTrainer`/`PPOTrainer`/`RLOOTrainer`/`OnlineDPOTrainer` conforming to `RLLifecycleProtocol`) — none named in W30 or W32                                    |
| `pact-ml-integration.md`         | W32           | W27             | **HIGH** — Spec's 3 mandates are `check_trial_admission`, `check_engine_method_clearance`, `check_cross_tenant_op`; W32 only names `ml_context` + `ClearanceRequirement` + governance-gated promote. No wave wires the three PACT methods by name                                           |

## Decision coverage table

All 14 approved decisions are traceable, but 3 have thin evidence that depends on the HIGH findings above landing properly.

| #   | Decision                                 | Wave(s)                 | Status                                                                                                                                                      |
| --- | ---------------------------------------- | ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Status vocab `FINISHED` only             | W3, W11                 | GREEN                                                                                                                                                       |
| 2   | GDPR erasure, audit immutable            | W15                     | GREEN                                                                                                                                                       |
| 3   | 4-member enum Rust parity                | W3, W1                  | GREEN                                                                                                                                                       |
| 4   | DDP/FSDP rank-0-only hardcoded           | W12, W14, W22, W23      | GREEN                                                                                                                                                       |
| 5   | XPU native-first + ipex fallback         | W7                      | GREEN                                                                                                                                                       |
| 6   | `backend-compat-matrix.yaml`             | W6                      | GREEN                                                                                                                                                       |
| 7   | CPU+MPS blocking; CUDA after self-hosted | W34, IT-1               | GREEN                                                                                                                                                       |
| 8   | Lightning hard lock-in; RL carve-out     | W9, W20, W29            | GREEN                                                                                                                                                       |
| 9   | Rust `start_run`/`end_run` parity        | W11                     | GREEN                                                                                                                                                       |
| 10  | Single-spec-plus-variant                 | IT-2                    | GREEN (tracked as follow-up; OK)                                                                                                                            |
| 11  | Legacy namespace sunset at 3.0           | W33, W34                | GREEN                                                                                                                                                       |
| 12  | Cross-tenant admin export v1.1           | W15, IT-4               | GREEN                                                                                                                                                       |
| 13  | Extras naming convention (hyphens)       | W22, W23, W27, W29, W30 | AMBER — no single wave owns a mechanical grep gate over every `[extra]` string used across the package; recommend adding a one-line grep gate to W33 or W34 |
| 14  | Package version at merge                 | W34                     | GREEN                                                                                                                                                       |

## Findings (HIGH / MED / LOW)

### HIGH-1 — W31 `kailash-core-ml-integration` spec drift: workflow-node naming + observability module + error module + migrations module all missing

**Location:** `W31-core-dataflow-nexus-integrations.md` sub-shard 31a.
**Risk:** W31 ships 3 wrong-named nodes; consumers of `specs/kailash-core-ml-integration.md` import `MLTrainingNode` and get `ImportError`. Cross-spec drift (specs-authority §5b).

Spec `§1.1` In-Scope mandates FIVE net-new core surfaces:

1. `src/kailash/diagnostics/protocols.py` expansion — `RLDiagnostic` Protocol + `DiagnosticReport`. **Not declared in any wave.**
2. `src/kailash/ml/errors.py` NEW module — `MLError` hierarchy lives in `kailash` (not `kailash-ml`). **W1 places it in `kailash-ml` — direct conflict with spec.**
3. `src/kailash/tracking/migrations/` NEW module. **W3/W4 place migrations in `kailash-ml/migrations/` — another location conflict.**
4. `kailash.workflow.nodes.ml` — `MLTrainingNode`, `MLInferenceNode`, `MLRegistryPromoteNode`. **W31 names `TrainNode`, `PredictNode`, `ServeNode` — different symbols.**
5. `kailash.observability.ml` — OTel/Prometheus counters (`kailash_ml_train_duration_seconds`, `kailash_ml_inference_latency_ms`, `kailash_ml_drift_alerts_total`). **Zero wave declares this.**

**Fix:** Pick one before `/implement` — either (a) accept W31 symbol drift and update the spec (per `specs-authority §6`) with a deviation note, OR (b) revise W31 sub-shard 31a to deliver the 5 spec-mandated surfaces. If (a), this decision MUST be logged explicitly because `src/kailash/ml/errors.py` vs `src/kailash_ml/errors.py` is load-bearing for every error-import in every other wave.

### HIGH-2 — W31 `dataflow-ml-integration` spec drift: `ml_feature_source`/`dataflow.transform`/`dataflow.hash` unclaimed

**Location:** `W31-core-dataflow-nexus-integrations.md` sub-shard 31b + missing coverage in W27 (FeatureStore).

Spec `§1.1` mandates three DataFlow surfaces:

1. `dataflow.ml_feature_source(feature_group)` → polars LazyFrame.
2. `@feature` calls `dataflow.transform(expr, source)`.
3. `dataflow.hash(df)` as the lineage fingerprint source.

W31 31b names `TrainingContext`, `lineage_dataset_hash`, and `_kml_classify_actions` bridge — which are the right-direction concepts but NOT the three spec-mandated symbols. W27 `FeatureStore` invariants never mention the DataFlow-side materializer; `ml-feature-store` §2 mandates it.

**Fix:** Add the three spec-mandated symbols to W31 31b's deliverable list, OR split into a new sub-shard 31d. Verify W27's `FeatureStore.get_features()` path calls `dataflow.ml_feature_source` or document the deviation.

### HIGH-3 — W31/W28 `nexus-ml-integration` spec drift: tenant/actor contextvars + dashboard auth adapter + inference tenant propagation

Spec `§1.1` mandates four Nexus-side surfaces:

1. `kailash_nexus.context._current_tenant_id` ContextVar + `get_current_tenant_id()`.
2. `kailash_nexus.context._current_actor_id` ContextVar + `get_current_actor_id()`.
3. `MLDashboard(auth="nexus")` validator adapter.
4. Inference-endpoint tenant propagation when `InferenceServer` runs behind Nexus.

W31 sub-shard 31c names `mount_ml_endpoints`, `UserContext` preservation, and `dashboard_embed`. `UserContext` is the right concept but "kailash_nexus.context.\_current_tenant_id" is the specific symbol. W28 (Dashboard) never mentions `auth="nexus"`. W15 (tenant resolver) names actor resolution `explicit → contextvar → env` but the contextvar it reads from is not pinned to `kailash_nexus.context` — so the standalone-vs-Nexus fallback chain specified in `nexus-ml-integration §1.3` is unwritten.

**Fix:** Add the 4 spec-mandated symbols to W31 31c + one invariant to W28 for `auth="nexus"` + one invariant to W15 for the Nexus-contextvar fallback.

### HIGH-4 — W32 `kaizen-ml-integration` spec drift: `tracker=` kwarg + auto-emission missing

Spec `§1.1` mandates FOUR integration surfaces in kaizen 2.12.0:

1. `tracker=` kwarg on `AgentDiagnostics`, `LLMDiagnostics`, `InterpretabilityDiagnostics`.
2. Auto-emission from every `record_*`/`track_*` method when ambient tracker is present — "no opt-in, no configuration flag".
3. Shared CostTracker wire format (integer microdollars + `to_dict`/`from_dict` parity).
4. `TraceExporter` → `SQLiteSink` writing to `~/.kailash_ml/ml.db`.

W32 32a names §2.4 Agent Tool Discovery + SQLiteSink + CostTracker (3 of 4) but the `tracker=` kwarg and auto-emission are NOT in invariants. This is the exact "kaizen adapters ship but never emit to the km.track() run" failure mode that round-1 theme T2 flagged.

**Fix:** Add two invariants to W32 32a: (1) `tracker=Optional[ExperimentRun]` kwarg on the three named adapters; (2) every `record_*`/`track_*` method MUST emit to ambient tracker when present (no opt-in). Add a Tier-2 integration test that asserts a metric written by `AgentDiagnostics.record_step()` shows up in `ExperimentRun.log_metric` query results.

### HIGH-5 — W30/W32 `align-ml-integration` spec drift: 4 TRL adapters unnamed

Spec `§1.1` mandates FOUR concrete `RLLifecycleProtocol` adapters in `kailash_align.rl_bridge`:

1. `DPOTrainer` adapter
2. `PPOTrainer` adapter
3. `RLOOTrainer` adapter
4. `OnlineDPOTrainer` adapter

W30 names the shared `Trajectory` + `align_bridge.py` + "GRPO in align re-uses ml.rl.Trajectory" — but none of the 4 adapter classes are named. W32 32b names "LoRA Lightning callback" + "trajectory unification entry point" — still no adapter class names. The orphan-detection risk is high: all 4 adapters are manager-shape (subclass of a TRL trainer, stateful training loop) and each would need a `test_<name>_adapter_wiring.py`.

**Fix:** Revise W30 and/or W32 32b to enumerate the 4 adapter classes by name; spell out wiring tests per adapter.

### HIGH-6 — W32/W27 `pact-ml-integration` spec drift: 3 governance methods unnamed

Spec `§1.1` mandates THREE `GovernanceEngine` methods:

1. `check_trial_admission(...)` → `AdmissionDecision` (called by `AutoMLEngine.run()`, `HyperparameterSearch.search()`, agent-driven sweeps).
2. `check_engine_method_clearance(...)` → per-method D/T/R gate on fit/promote/delete/archive/rollback.
3. `check_cross_tenant_op(...)` → explicit cross-tenant gate (post-1.0 surface).

W32 32c names `ml_context` kwarg + `ClearanceRequirement` decorators + governance-gated `AutoMLEngine.search_*` + `ModelRegistry.promote_model("production")`. None of the three methods are named. W27 `AutoMLEngine` never calls `check_trial_admission` by name.

**Fix:** Enumerate the three methods in W32 32c's invariants. Wire `W27 AutoMLEngine.run()` to call `check_trial_admission` with a regression test. Wire `W18 promote_model` + `W20 fit/finalize` + `W16 register` to call `check_engine_method_clearance`. Defer `check_cross_tenant_op` to IT-4 (already correctly deferred).

### MED-1 — W19 capacity-budget near-edge

- W19 LOC=500 load-bearing + invariant count 9 + describes 4 surfaces (init, DI, setup, compare).
- `autonomous-execution.md §1` caps LOC at 500 AND invariants at 5-10. W19 is at the edge.
- Narrative compresses to "zero-arg + DI + setup + compare" which is 4 sentences in invariant form.

**Fix:** Consider re-sharding into W19a (zero-arg + DI + setup) and W19b (compare). The pattern of splitting engine surface by "method grouping" matches `autonomous-execution.md §1` guidance ("size by complexity, not LOC alone"). Non-blocking; `/implement` can try 1 shard and split if it overflows budget mid-session, but this is exactly the pattern the rule was written to prevent.

### MED-2 — W20 capacity-budget near-edge

- W20 LOC=500 + 10 invariants + 4 methods (fit/predict/finalize/evaluate) + 6 Lightning passthrough kwargs.
- 10 invariants is AT the ceiling of the `5-10` budget; plus 6 kwarg-level plumbing guarantees → effective complexity is >10.

**Fix:** Same as MED-1 — re-shard W20 into W20a (fit + predict) and W20b (finalize + evaluate + lr_find). Lightning-strategy plumbing lands in W20a; schema-drift detection in W20b.

### MED-3 — W33 capacity-budget overflow likely

W33 declares LOC ~500 but deliverables include: 4 module-level functions, 9 `_wrappers` module functions, `engines/registry.py` with 2 public functions, 6-group `__all__` (34 symbols), README Quick Start literal block with fingerprint, regression test, MIGRATION.md guide. That's 6 deliverable surfaces + 11 invariants. Conservative estimate: 700-900 LOC load-bearing counting MIGRATION.md + regression harness.

**Fix:** Split into W33a (`km.*` wrappers + `engines/registry.py` + `__all__`) and W33b (MIGRATION.md + README Quick Start + regression test). Release-blocking test lands in W33b and gates W34.

### MED-4 — W14 capacity-budget near-edge

W14 LOC=450 + 7 invariants but carries "two backends + abstract base + contextvars + rank-0-filter + cross-backend parity". Complexity high due to cross-file reasoning (SQLite pool + PG ConnectionManager + contextvars all live in different trees).

**Fix:** Optional re-shard into W14a (SQLite + abstract + contextvars) and W14b (Postgres + cross-backend parity). Non-blocking.

### MED-5 — W4 migration: identifier-safety sweep not verified for all 15 tables

W4 invariants mandate `quote_identifier` (inv 6) + 63-char Postgres limit (inv 2) + tenant*id NOT NULL (inv 3). Migration creates 15 tables. `dataflow-identifier-safety §5` mandates that even hardcoded identifier lists MUST route through `_validate_identifier()`. The todo's grep-gate verifies `CREATE TABLE.\*\_kml*`count and`tenant_id TEXT NOT NULL`count but does NOT verify that every DDL identifier in the migration routed through`quote_identifier`.

**Fix:** Add a grep-gate to W4: `rg 'CREATE (TABLE|INDEX).*\{[^}]+\}' packages/kailash-ml/migrations/0002*` returns 0 (no f-string identifier interpolation without quoting). Add a regression test that passes a deliberately-malicious table name through the migration runner and asserts rejection.

### MED-6 — Wiring-test coverage implicit for most manager-shape classes

Master plan §Testing Policy Per Wave item 5 states every manager-shape class gets `test_<name>_wiring.py`. However, the per-wave todo files only explicitly mention "wiring test" in W32. Every other wave that ships a manager-shape class (`ExperimentTracker`, `ExperimentRun`, `ModelRegistry`, `ArtifactStore`, `AbstractTrackerStore`, `DLDiagnostics`, `RLDiagnostics`, `InferenceServer`, `ServeHandle`, `DriftMonitor`, `AutoMLEngine`, `FeatureStore`, `MLDashboard`, `RLTrainer`, `EnvironmentRegistry`, `PolicyRegistry`) says "Tier-1/2 green" but not the specific file-name convention.

**Fix:** Make the wiring-test file-name explicit per wave. This is mechanical — add one line to each manager-shape wave DoD: "`tests/integration/test_<class_name>_wiring.py` green per `orphan-detection.md` §2".

### MED-7 — W31/W32 version-owner ambiguity

Master plan `§Parallelization Plan` says "orchestrator designates ONE version owner for `pyproject.toml`/`__version__`/`CHANGELOG.md` per package". W31 names 3 sub-shards (31a, 31b, 31c) for 3 packages; each says "Version owner: kailash-{pkg} owner" — that's correct. W32 does the same for 32a/32b/32c. BUT:

- W31 31a (kailash-core ML integration) has NO version-owner line — the other two do. Master plan `§M10 Integrations` says `kailash 2.9.0` in W34 but no sub-shard in W31 claims ownership of `src/kailash/__init__.py::__version__`.
- W31 and W32 each touch `kailash-ml` (shim imports). Which of W31 or W32 is version-owner for `kailash-ml 1.0.0`? Master plan implies W33 (via `km.*` landing) but the two integration waves touch `kailash-ml` first.

**Fix:** Add explicit version-owner line to W31 31a (kailash-core). Clarify that `kailash-ml 1.0.0` version-owner is W34 (release wave) and W31/W32 MUST NOT edit `packages/kailash-ml/pyproject.toml` or `__version__`. This is exactly the failure mode `agents.md § Parallel-Worktree Package Ownership Coordination` was codified for.

### MED-8 — W34 release-order verification subtlety

Release order declared: `kailash` → `kailash-dataflow` → `kailash-nexus` → `kailash-kaizen` → `kailash-pact` → `kailash-align` → `kailash-ml`. The brief requested this be `kailash → dataflow → nexus → kaizen → pact → align → ml`, which matches. BUT kailash-nexus depends on kailash-core; kailash-kaizen depends on kailash-core; kailash-pact does NOT depend on kailash-kaizen (pact is an independent peer); kailash-align depends on kailash-ml's `Trajectory` (W30) — which means `kailash-align 0.5.0` CANNOT install until `kailash-ml 1.0.0` is on PyPI if `[rl-bridge]` pulls `kailash-ml>=1.0.0`.

Per `align-ml-integration §1.1` item 4: "`[rl-bridge]` extra pulls `kailash-ml>=1.0.0`. kailash-align remains installable standalone." The standalone install works (no kailash-ml requirement for base), so the publish order CAN have align before ml. **However**, W34 should verify that the reverse-dep graph extracted from actual `pyproject.toml` contents matches the claimed order, not just the narrative.

**Fix:** Add to W34 DoD: "`pip-compile --dry-run` each package in target order; zero unresolved deps before the next package publishes."

### MED-9 — W2 env-deprecation chain relies on `EnvVarDeprecatedError` scaffolded but not raised in 1.0

W2 invariant 3 states "2.0 future-removal: `KAILASH_ML_TRACKER_DB` raises `EnvVarDeprecatedError` (scaffolded in 1.0 behind a version flag)." Scaffolding is fine but the "version flag" is not specified. Risk: a future PR flips the flag without reviewing which callers still set the legacy env var.

**Fix:** Specify the flag (`KAILASH_ML_STRICT_ENV=1` or similar) in W2's deliverable. Document the sunset in MIGRATION.md (W33).

### LOW-1 — IT-3 `SystemMetricsCollector` explicitly deferred — confirmed

Round-8 SYNTHESIS says DL-GAP-2 (SystemMetricsCollector at `ml-diagnostics §7`) is v1.1-deferred. Master plan agrees. No fix needed; just confirm a `# v1.1-deferred: SystemMetricsCollector (DL-GAP-2)` marker lands in `ml-diagnostics` during `/implement` so next-session readers see the deferral inline, not only in audit files.

### LOW-2 — `kaizen-evaluation.md` spec exists in `_index.md` but not in 21-spec inventory

`specs/_index.md` lists `kaizen-evaluation.md` (ROUGE/BLEU/BERTScore, `[evaluation]` extra). This file is NOT one of the 21 pinned specs (15 ml-_ + 6 _-ml-integration). Not a gap; just noting that the "21 specs" count is strict to the ml/integration scope. kaizen-evaluation is owned by the kaizen release cadence, not the ml 1.0.0 wave. Confirm this is intended.

### LOW-3 — `kaizen-interpretability.md` / `kaizen-judges.md` / `kaizen-observability.md` also out of ml-wave scope

Same status as LOW-2: these are `specs/kaizen-*.md`, not `specs/ml-*.md` or `*-ml-integration.md`. W24 re-exports adapters from kaizen but does not deliver kaizen-side code. OK as long as kaizen's own release cadence has shipped these before W32's kaizen-ml integration lands.

### LOW-4 — Terrene Foundation naming and licensing implied but not asserted

No wave contains a Terrene Foundation licensing assertion or naming-compliance grep gate. `rules/terrene-naming.md` + `rules/independence.md` apply by default; adding a one-line grep gate to W34 (`rg 'partnership|proprietary|commercial version' packages/kailash-ml/` returns empty) is cheap insurance.

## Capacity-budget analysis

Waves at or exceeding budget per `autonomous-execution.md §1`:

- **W19 — AT edge** (500 LOC + 9 invariants + 4 surfaces): recommend sharding into W19a+W19b.
- **W20 — AT edge** (500 LOC + 10 invariants + 6 passthrough kwargs): recommend W20a (fit+predict) + W20b (finalize+evaluate+lr_find).
- **W33 — LIKELY OVERFLOW** (500 LOC declared, realistic ~700-900 LOC; 6 deliverable surfaces + 11 invariants): recommend W33a (wrappers+**all**+registry) + W33b (MIGRATION.md + README regression).
- **W14 — NEAR EDGE** (450 LOC + 7 invariants + 2 backends + contextvars): optional re-shard.

Well-sized waves (do NOT re-shard):

- W1 (250/7), W2 (120/5), W5 (150/6), W6 (200/5), W8 (300/7), W9 (450/7 — but boilerplate-heavy across 4 adapters, pattern-stamping so within spirit), W11 (250/6), W12 (400/9), W13 (300/6), W15 (400/7), W16 (400/7), W17 (400/6), W18 (400/7), W22 (400/7), W24 (350/5), W25 (500/8), W26 (450/8), W27 (500/10 — at edge but two-sub-shard), W28 (400/7), W29 (500/8), W30 (350/6), W32 (700/10 across 3 sub-shards).

Recommended re-shards (3 waves → 6):

- W19 → W19a + W19b
- W20 → W20a + W20b
- W33 → W33a + W33b

If the user prefers to hold the 34-wave count: each of W19/W20/W33 MAY proceed as-written with the explicit understanding that if budget overflows mid-`/implement`, the session MUST abort and re-shard before continuing, per `autonomous-execution.md` MUST NOT rule "Defer sharding decisions to /implement".

## Orphan-risk analysis

Per `orphan-detection.md §1` + `facade-manager-detection.md`, every manager-shape class (`*Manager`, `*Executor`, `*Store`, `*Registry`, `*Engine`, `*Service`) exposed via a facade attribute MUST have a `test_<name>_wiring.py` delivered in the same wave. Inventory:

| Manager-shape class        | Wave    | Wiring test explicit?                                      | Risk                                    |
| -------------------------- | ------- | ---------------------------------------------------------- | --------------------------------------- |
| `ExperimentTracker`        | W10     | NO — "Tier-1/2 green"                                      | MED-6                                   |
| `ExperimentRun`            | W10     | NO                                                         | MED-6                                   |
| `AbstractTrackerStore`     | W14     | NO                                                         | MED-6                                   |
| `SqliteTrackerStore`       | W14     | NO                                                         | MED-6                                   |
| `PostgresTrackerStore`     | W14     | NO                                                         | MED-6                                   |
| `ModelRegistry`            | W16     | NO                                                         | MED-6                                   |
| `LocalFileArtifactStore`   | W17     | NO                                                         | MED-6                                   |
| `CasSha256ArtifactStore`   | W17     | NO                                                         | MED-6                                   |
| `ArtifactStore` ABC        | W17     | NO                                                         | MED-6                                   |
| `Engine` / `MLEngine`      | W19     | NO                                                         | MED-6                                   |
| `DLDiagnostics`            | W22     | NO                                                         | MED-6                                   |
| `RLDiagnostics`            | W24     | NO                                                         | MED-6                                   |
| `InferenceServer`          | W25     | NO                                                         | MED-6                                   |
| `ServeHandle`              | W25     | NO                                                         | MED-6                                   |
| `DriftMonitor`             | W26     | NO                                                         | MED-6                                   |
| `AutoMLEngine`             | W27     | NO                                                         | MED-6                                   |
| `FeatureStore`             | W27     | NO                                                         | MED-6                                   |
| `MLDashboard`              | W28     | NO                                                         | MED-6                                   |
| `RLTrainer`                | W29     | NO                                                         | MED-6                                   |
| `EnvironmentRegistry`      | W29     | NO                                                         | MED-6                                   |
| `PolicyRegistry`           | W29     | NO                                                         | MED-6                                   |
| Kaizen ml adapters         | W32     | YES — "test\_<name>\_wiring.py per orphan-detection.md §2" | GREEN                                   |
| PACT governance methods    | W32     | IMPLICITLY covered by W32 inv 10                           | GREEN but method names missing (HIGH-6) |
| TRL RL adapters (DPO etc.) | W30/W32 | NO — not named                                             | HIGH-5                                  |

**Summary:** 21 manager-shape classes across 15 waves ship without the file-name-explicit wiring-test convention. This is NOT a blocker if reviewers enforce `orphan-detection.md §2` at the implementation-review gate, but it IS a structural regression vs the Round-8 SYNTHESIS discipline. See MED-6 for the one-line fix.

## Release-order verification

Publishing order per W34:

1. `kailash 2.9.0` — no Kailash deps; foundation.
2. `kailash-dataflow 2.1.0` — depends on `kailash`.
3. `kailash-nexus 2.2.0` — depends on `kailash`.
4. `kailash-kaizen 2.12.0` — depends on `kailash`.
5. `kailash-pact 0.10.0` — depends on `kailash`.
6. `kailash-align 0.5.0` — depends on `kailash`; `[rl-bridge]` extra depends on `kailash-ml>=1.0.0` (optional).
7. `kailash-ml 1.0.0` — depends on `kailash`, `kailash-dataflow`, `kailash-nexus`, `kailash-kaizen`, `kailash-pact`, `kailash-align`.

Reverse-dep graph check: GREEN (last package has most deps, first package has none). Align publishing BEFORE ml is safe because the `[rl-bridge]` extra's `kailash-ml>=1.0.0` requirement resolves at opt-in install time, not at `kailash-align` base install. Matches `align-ml-integration §1.3 Non-Goals`: "No hard dependency on kailash-ml for standalone align users."

The user's requested order in the brief (`kailash → dataflow → nexus → kaizen → pact → align → ml`) matches W34 exactly. GREEN.

One subtle risk — see MED-8: no wave mechanically verifies the dep graph from `pyproject.toml` contents. Add `pip-compile --dry-run` per package in W34 DoD.

## Migration safety

W3 (0001 status migration) + W4 (0002 `_kml_*` prefix + tenant columns):

- `schema-migration.md §7 force_downgrade`: BOTH waves mandate `force_downgrade=True` (W3 inv 5, W4 inv 8). GREEN.
- Reversibility: BOTH use parking tables (W3 inv 4, W4 inv 9). GREEN.
- `dataflow-identifier-safety.md §1 quote_identifier`: BOTH mandate it (W3 inv 6, W4 inv 6). GREEN.
- Real-dialect tests: BOTH specify PG + SQLite Tier-2 (W3, W4). GREEN.
- Audit immutability (W4 inv 4): Trigger blocks UPDATE + DELETE. GREEN.

Gaps:

- MED-5 — no mechanical grep-gate that the migration file has zero raw-f-string identifier interpolation. One-line fix.
- `schema-migration.md` also mandates numbered migration sequencing + up/down symmetry. Both waves implement. GREEN.
- Location mismatch — W3/W4 place migrations in `packages/kailash-ml/migrations/` but `kailash-core-ml-integration.md §1.1 item 3` mandates `src/kailash/tracking/migrations/`. See HIGH-1.

## Testing rigor

- Tier-1 unit + Tier-2 integration explicit? YES on all 34 waves.
- Protocol adapters in Tier-2 per `testing.md §Exception: Protocol-Satisfying Deterministic Adapters`? Not named explicitly, but the pattern fits W24 (kaizen adapter re-exports) and W32 (PACT governance). Recommend adding one explicit `Protocol-conformance` Tier-2 assertion per wave that ships a new Protocol (W8 Trainable, W22 DLDiagnostics, W24 RLDiagnostics).
- Regression tests per wave? YES per master-plan §Testing Policy 3.
- Env-var test isolation per `testing.md § Env-Var Test Isolation`? Not mentioned in any wave. W2 tests mutate `KAILASH_ML_STORE_URL` + `KAILASH_ML_TRACKER_DB` — MUST use `threading.Lock` + `monkeypatch.setenv` pattern. Add a one-line note to W2's test invariants.
- Tier-2 "no mocking" discipline: W14 DDP rank-0 "mock cluster" — is this a real 2-rank `torch.distributed` spin-up or a mock? If mock, it's Tier-1-legal only. Clarify W14 whether the "2-rank mock" is a Protocol-conforming deterministic adapter or a `MagicMock` (the latter is BLOCKED per `testing.md`).
- `pytest --collect-only` per `orphan-detection.md §5`: no wave sets this as a merge gate. Recommend adding to W34 DoD.

## Overall assessment

The 34-wave plan is structurally coherent, the dependency graph is correct, the 14 decisions are all traceable, migration safety is well-specified, and release order respects the reverse-dep graph. What the plan currently MISSES is **symbol-level spec conformance on the 6 integration specs** — W31 and W32 name surfaces that do NOT match the spec mandates for `kailash-core-ml-integration`, `dataflow-ml-integration`, `nexus-ml-integration`, `kaizen-ml-integration`, `align-ml-integration`, and `pact-ml-integration`. This is the `specs-authority.md §5b` full-sibling-spec re-derivation failure mode in reverse: the plan was derived from the Round-8 narrative rather than from each spec's `§1.1 In Scope` enumeration. `/implement` will ship working code for non-spec symbols, `/redteam` will flag it as cross-spec drift, and the 7-package wave will either slip a week to reconcile or ship with documented deviations. Neither outcome is what the user asked for. The 3 MED-level capacity-budget concerns (W19, W20, W33) are defensible now, but will surface as mid-`/implement` shard-abort events unless re-sharded proactively. The MED-6 wiring-test convention gap is the cheapest fix (one line per wave) with the highest leverage. Net recommendation: **do not approve the plan for `/implement` as-drafted** — revise W31/W32/W28/W27/W30/W15 to name the 20-odd spec-mandated symbols listed in HIGH-1 through HIGH-6, apply the 3 re-shard recommendations, and make wiring tests file-name explicit. After that one revision pass, APPROVE.
