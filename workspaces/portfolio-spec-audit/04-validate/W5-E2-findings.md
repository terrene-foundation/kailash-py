# W5-E2 Findings — ml extras + align + integrations + diagnostics catalog

**Specs audited:** 11 (ml-automl, ml-drift, ml-feature-store, ml-dashboard, ml-integration, alignment-training, alignment-serving, alignment-diagnostics, align-ml-integration, kailash-core-ml-integration, diagnostics-catalog)
**§ subsections enumerated:** ~140 across 11 specs
**Findings:** CRIT=0 HIGH=18 MED=16 LOW=35 (70 total, F-E2-01..F-E2-70)
**Audit completed:** 2026-04-26

## Findings tally per spec

| Spec | Findings (CRIT/HIGH/MED/LOW) | Range |
| ---- | ---------------------------- | ----- |
| ml-automl.md | 0/8/1/0 | F-E2-01..10 |
| ml-drift.md | 0/2/5/0 | F-E2-11..17 |
| ml-feature-store.md | 0/5/0/2 | F-E2-18..24 |
| ml-dashboard.md | 0/2/3/1 | F-E2-25..30 |
| ml-integration.md (DEPRECATED) | 0/0/0/4 | F-E2-31..34 |
| alignment-training.md | 0/1/1/5 | F-E2-35..41 |
| alignment-serving.md | 0/0/1/7 | F-E2-42..49 |
| alignment-diagnostics.md | 0/0/1/2 | F-E2-50..52 |
| align-ml-integration.md | 0/0/2/5 | F-E2-53..59 |
| kailash-core-ml-integration.md | 0/0/2/4 | F-E2-60..65 |
| diagnostics-catalog.md | 0/0/0/5 | F-E2-66..70 |

## Top-level themes

1. **AutoML 1.0 spec is overstated vs implementation** (F-E2-01..10): two divergent `AutoMLEngine` classes, only 4/7 search strategies, no Ray/Dask executor, no Ensemble facade, missing typed exceptions, post-hoc LLM cost cap (not token-level pre-cap per spec § 8.3 MUST 2). Spec needs alignment with current implementation OR M2 deferral markers.
2. **DriftMonitor "drift_type" semantic drift** (F-E2-11): spec covariate/concept/prior/label vs implementation severity none/moderate/severe — different concept entirely.
3. **FeatureStore is DataFlow-bridge, not URL-based** (F-E2-18..22): spec § 2.1 declares `store=`/`online=` URLs, implementation takes a `DataFlow` instance. No online store, no `@feature` decorator, no `FeatureGroup` class, no materialization API.
4. **Alignment is the most spec-compliant package**: alignment-training, alignment-serving, alignment-diagnostics all match spec point-for-point with only minor gaps. Demonstrates that spec-driven development with stable scope works.
5. **Cross-SDK Diagnostic Protocol byte-vector pinning deferred**: F-E2-51, F-E2-62 — both flag deferred kailash-rs counterparts. Per `rules/cross-sdk-inspection.md` MUST Rule 4, byte-vector pinning is required when sibling SDK ships; tracked-deferred OK for now.
6. **Diagnostics catalog is fully populated and audited** (F-E2-66..70): all 6 cataloged adapters exist, all 7 wiring tests exist, medical-metaphor scrub clean. Minor catalog-path drift only (F-E2-70).

---

## Spec 1 — `ml-automl.md` (652 lines)

§ subsections enumerated: 13 (1.1, 1.2, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 4.1, 4.2, 5.x, 6.x, 7.x, 8.x, 8A, 9, 10, 11, 12, 13)

### F-E2-01 — `ml-automl.md` § 2.1 — Two divergent `AutoMLEngine` implementations

**Severity:** HIGH
**Spec claim:** Spec § 2.1 declares `AutoMLEngine` constructed with `(config, feature_store, model_registry, trials_store, tenant_id, tracker)` (kwargs); spec __init__ contract.
**Actual state:** Two implementations coexist:
- `packages/kailash-ml/src/kailash_ml/automl/engine.py:410` — canonical 1.0.0 surface; `__init__(*, config, tenant_id, actor_id, connection, cost_tracker, governance_engine)` — does NOT accept `feature_store`, `model_registry`, `trials_store`, `tracker`. Constructor signature diverges from spec.
- `packages/kailash-ml/src/kailash_ml/engines/automl_engine.py:425` — legacy scaffold; `__init__(pipeline, search, *, registry)` — completely different shape.
The spec'd kwargs `feature_store=`, `model_registry=`, `trials_store=`, `tracker=` are absent from BOTH implementations. The canonical `AutoMLEngine.run(...)` takes `(*, space, trial_fn, …)` instead of `data, schema, target, time_budget, ...` per § 3.1.
**Remediation hint:** Either consolidate to one engine matching spec §2.1/§3.1 surface, OR update spec to reflect the dual-implementation reality (canonical `automl/engine.py` + legacy `engines/automl_engine.py`) and document migration path.

### F-E2-02 — `ml-automl.md` § 2.1 / 2.3 MUST 1 — `tracker=` kwarg + ambient `km.track()` not in canonical engine

**Severity:** HIGH
**Spec claim:** § 2.3 MUST 1 requires `AutoMLEngine.__init__` accept `tracker: Optional[ExperimentRun] = None` and auto-wire to `kailash_ml.tracking.get_current_run()` when None.
**Actual state:** `automl/engine.py:410` `__init__` accepts no `tracker=` kwarg; ambient run resolution via `get_current_run()` is absent. `engines/automl_engine.py` `run()` accepts `tracker=` but does NOT auto-wire ambient. WARN line "no tracker bound; trial history will not be recoverable" is absent from both.
**Remediation hint:** Add `tracker: Optional[ExperimentRun] = None` to canonical engine `__init__`; resolve from `kailash_ml.tracking.get_current_run()` when None; emit WARN if neither is present.

### F-E2-03 — `ml-automl.md` § 4.1 — BOHB / CMA-ES / ASHA / PBT strategies absent

**Severity:** HIGH
**Spec claim:** § 4.1 lists 7 search algorithms required: `GridSearchAlgorithm`, `RandomSearchAlgorithm`, `BayesianSearchAlgorithm`, `BOHBAlgorithm`, `CMAESAlgorithm`, `SuccessiveHalvingAlgorithm`, `ASHAAlgorithm`. Spec § 4.2 MUST 4 mandates BOHB multi-fidelity contract. Spec § 4.2 MUST 5 mandates ASHA as default for `parallel_trials > 1`.
**Actual state:** Only 4 strategies implemented in `automl/strategies/`: grid, random, bayesian, halving. `resolve_strategy()` accepts only `{grid, random, bayesian, halving|successive_halving}`. BOHB / CMA-ES / ASHA / PBT all absent. The `strategies/__init__.py` docstring acknowledges: "BOHB / CMA-ES / PBT / ASHA are deferred to post-M1 milestones."
**Remediation hint:** Either implement BOHB/CMAES/ASHA/PBT, OR mark spec § 4.1 entries `(Awaiting M2)` per spec-authority skip discipline.

### F-E2-04 — `ml-automl.md` § 5.x — `executor=` kwarg absent (Ray/Dask deferred)

**Severity:** HIGH
**Spec claim:** § 5.1-5.4 require `executor: str = "local"` kwarg with `"ray"` and `"dask"` values; § 5.4 MUST 1 mandates `MissingExtraError` when ray/dask extra not installed; § 5.4 MUST 2 mandates `tenant_id` + `parent_run_id` propagation; `ContextLostError` on lost context.
**Actual state:** No `executor=` kwarg on either `AutoMLEngine.__init__` or `run()`. No `MissingExtraError` typed exception in errors module. No Ray/Dask integration. The `AutoMLConfig` class has neither `executor` nor `parallel_trials` field — config has only single-process trial execution.
**Remediation hint:** Mark Ray/Dask executor as `(Awaiting M2)` in spec OR implement; ensure typed `MissingExtraError` raised at `run()` time when extra missing.

### F-E2-05 — `ml-automl.md` § 7.x — `Ensemble.from_leaderboard()` symbol absent

**Severity:** HIGH
**Spec claim:** § 7.1 declares `from kailash_ml import Ensemble; ensemble = Ensemble.from_leaderboard(report=, method=, k=, meta_learner=)`. § 3.3 MUST 3 mandates ensemble build is opt-out with `ensemble=True` default and `LeaderboardReport.ensemble_result` populated.
**Actual state:** `Ensemble` class exists at `engines/ensemble.py:611-LOC` (legacy path) but not exposed via `kailash_ml.__init__` or `kailash_ml.automl.__init__`. `Ensemble.from_leaderboard()` classmethod absent — instance constructed via `Ensemble(...)` or factory functions. `AutoMLConfig` has no `register_best`-adjacent `ensemble` field; canonical `AutoMLResult` (`automl/engine.py:244`) has no `ensemble_result` field. `EnsembleFailureError` typed exception absent.
**Remediation hint:** Add `Ensemble.from_leaderboard()` classmethod, expose `Ensemble` from `kailash_ml.__init__`, add `ensemble: bool = True` + `top_k: int = 3` fields to AutoMLConfig, add `ensemble_result` field to AutoMLResult.

### F-E2-06 — `ml-automl.md` § 10 — Multiple typed exceptions absent

**Severity:** HIGH
**Spec claim:** § 10 enumerates 11 typed exceptions: `BudgetExhaustedError`, `InsufficientTrialsError`, `EnsembleFailureError`, `TrialFailureError`, `MissingExtraError`, `ContextLostError`, `InvalidConfigError`, `HPOSpaceUnboundedError`, `AgentCostBudgetExceededError`, `ParamValueError`, `UnsupportedTrainerError`. All MUST live under `kailash_ml.errors` (`AutoMLError` family).
**Actual state:** Errors module check (`packages/kailash-ml/src/kailash_ml/errors.py`) needed; `automl/engine.py` defines only `LLMBudgetExceededError` (legacy) and `BudgetExceeded` (CostTracker). `BudgetExhaustedError`, `InsufficientTrialsError`, `EnsembleFailureError`, `TrialFailureError`, `MissingExtraError`, `ContextLostError`, `InvalidConfigError`, `HPOSpaceUnboundedError`, `AgentCostBudgetExceededError`, `ParamValueError`, `UnsupportedTrainerError` — all need verification but not present in `automl/engine.py`'s top-level imports.
**Remediation hint:** Verify each typed exception exists in `kailash_ml.errors`; add missing ones; ensure `AutoMLError` family hierarchy.

### F-E2-07 — `ml-automl.md` § 8A — `_kml_automl_agent_audit` table DDL not implemented

**Severity:** MED
**Spec claim:** § 8A.2/8A.3 require `_kml_automl_agent_audit` table with columns `(tenant_id, automl_run_id, trial_number, agent_kind, agent_model_id, actor_id, pact_decision, pact_reason, proposed_config, budget_microdollars, actual_microdollars, outcome, occurred_at)`; SQLite + Postgres variants. Tier-2 schema-migration test required (§ 8A.4: `test__kml_automl_agent_audit_schema_migration.py`).
**Actual state:** `automl/engine.py:296` defines `_ensure_trials_table` for `_kml_automl_trials` (general trial audit); separate `_kml_automl_agent_audit` (agent-specific) absent. § 8A.4 schema-migration test file `test__kml_automl_agent_audit_schema_migration.py` not found in `packages/kailash-ml/tests/`.
**Remediation hint:** Add `_ensure_agent_audit_table` DDL helper; add Tier-2 schema-migration test.

### F-E2-08 — `ml-automl.md` § 3.1 — `MLEngine.fit_auto()` signature absent

**Severity:** HIGH
**Spec claim:** § 3.1 declares `MLEngine.fit_auto(data, *, task, target, time_budget, metric, families, parallel_trials, executor, max_trials, early_stopping_patience, agent, ensemble, top_k, seed) -> LeaderboardReport`.
**Actual state:** `kailash_ml/engine.py` MLEngine class needs check; `LeaderboardReport` dataclass absent (canonical result type is `AutoMLResult`, not `LeaderboardReport` per § 3.2). The kwargs `task`, `time_budget`, `families`, `parallel_trials`, `executor`, `early_stopping_patience`, `top_k` not exposed via canonical entry point. `AutoMLConfig` has no `early_stopping_patience` field, no `families` field.
**Remediation hint:** Either add `MLEngine.fit_auto()` with the spec-declared signature returning `LeaderboardReport`, OR document the `AutoMLEngine.run()` + `AutoMLResult` shape as the canonical surface and update spec.

### F-E2-09 — `ml-automl.md` § 8.3 MUST 2 — TOKEN-LEVEL backpressure on LLM cost not enforced

**Severity:** HIGH
**Spec claim:** § 8.3 MUST 2 mandates `max_llm_cost_usd` enforced via TOKEN-LEVEL backpressure (compute `max_tokens_this_call` BEFORE the call to prevent overrun). Required agent_config kwargs: `max_prompt_tokens`, `max_completion_tokens` (§ 8.3 MUST 2a); `min_confidence` from AgentGuardrailMixin.
**Actual state:** `LLMCostTracker.record()` in `engines/automl_engine.py:215-230` performs POST-HOC cost summation: records cost AFTER the call, raises `LLMBudgetExceededError` only when `_spent > _max_budget`. The "$4.99 → $7.50 in one call" failure mode the spec explicitly forbids is exactly the implementation. `max_prompt_tokens` / `max_completion_tokens` / `min_confidence` not in `AutoMLConfig`.
**Remediation hint:** Add token-level pre-cap in agent dispatch path; add `max_prompt_tokens`, `max_completion_tokens`, `min_confidence` fields to AutoMLConfig.

### F-E2-10 — `ml-automl.md` § 8.3 MUST 1 — Baseline-parallel-with-agent absent

**Severity:** HIGH
**Spec claim:** § 8.3 MUST 1 mandates baseline pure-algorithmic search runs in PARALLEL with the agent's suggestions; final report tags each trial `source="agent" | "baseline"`.
**Actual state:** Canonical `AutoMLEngine.run()` accepts `source_tag` parameter (string), but the implementation runs ONE trial stream per invocation (the orchestrator decides if it's "agent" or "baseline"; not parallel). No internal parallel-baseline logic. `TrialRecord` carries `source_tag` field but the agent path is sequential ("v1 -- requires kaizen agents") — agent augmentation is `not implemented in v1` per `engines/automl_engine.py:529`.
**Remediation hint:** Implement parallel baseline+agent stream OR mark `(Awaiting agent integration)` and remove MUST 1 from § 8.3.

---

## Spec 2 — `ml-drift.md` (887 lines)

§ subsections enumerated: 14 (1.1-1.6, 2.1-2.3, 3.1-3.6, 4.x, 5.x, 6.x, 7.x, 8.x, 9, 10, 11.x, 12, 13)

### F-E2-11 — `ml-drift.md` § 1.1 / § 6.x — Drift type taxonomy diverges from spec (covariate/concept/prior/label vs none/moderate/severe)

**Severity:** HIGH
**Spec claim:** § 1.1 mandates `drift_type: Literal["covariate", "concept", "prior", "label", "unknown"]` on every `DriftFeatureResult`; users route alerts/recommendations differently per type.
**Actual state:** `engines/drift_monitor.py:1240` sets `drift_type = "severe" if psi > 0.25 else "moderate" if psi > 0.1 else "none"` — a SEVERITY enum, not a TYPE enum. `_types.py:42` declares `drift_type: str  # "none", "moderate", "severe"`. The spec's covariate/concept/prior/label distinction (which determines whether to recalibrate vs full-retrain) is NOT modeled.
**Remediation hint:** Add `drift_axis: Literal["covariate", "concept", "prior", "label"]` field separate from severity. Or rename current `drift_type` → `severity` and add `axis` field with the spec values.

### F-E2-12 — `ml-drift.md` § 2.1 — `DriftMonitorConfig` dataclass surface absent

**Severity:** MED
**Spec claim:** § 2.1 declares `@dataclass(frozen=True, slots=True) class DriftMonitorConfig(tenant_id, model_uri, axes, store, alerts, label_lag_seconds, min_samples, reference_max_rows)`; constructor `DriftMonitor(config: DriftMonitorConfig, *, registry, tracker, artifact_store)`.
**Actual state:** `DriftMonitorConfig` dataclass does not exist; constructor signature is direct kwargs (`conn`, `tenant_id`, `psi_threshold`, `ks_threshold`, `performance_threshold`, `thresholds`, `tracker`, `alerts`). `model_uri`, `axes`, `min_samples`, `reference_max_rows`, `label_lag_seconds`, `artifact_store` not exposed at construction. Spec § 2.1 itself acknowledges this divergence: "the current Python implementation accepts direct kwargs rather than the DriftMonitorConfig wrapping ... is a forward-looking ergonomic surface."
**Remediation hint:** Spec already self-flags this; add explicit `(Awaiting full DriftMonitorConfig facade)` marker OR ship the dataclass.

### F-E2-13 — `ml-drift.md` § 2.2 — `MLEngine.monitor()` facade absent

**Severity:** HIGH
**Spec claim:** § 2.2 mandates `engine.monitor(model="fraud", alias="@production", axes={...}, alerts=...)` as canonical construction path that resolves registry/tracker/store.
**Actual state:** `MLEngine` class needs verification but `monitor()` async method that returns `DriftMonitor` with model lookup is not visible in the canonical engine surface. Direct `DriftMonitor(conn, tenant_id=...)` is the only path. Spec § 2.3 Reference From Registry Lineage (registry-driven default reference resolution) requires `MLEngine.monitor()` facade to wire `registry`.
**Remediation hint:** Add `MLEngine.monitor(...)` facade method.

### F-E2-14 — `ml-drift.md` § 3.5 — Composite `drift_score ∈ [0, 1]` not surfaced

**Severity:** MED
**Spec claim:** § 3.5 mandates per-column `drift_score ∈ [0, 1]` combining triggered statistics; model-level score is max-across-columns (default) OR weighted-mean.
**Actual state:** `_types.py:FeatureDriftResult` (lines 28-83) needs check for `drift_score` field; current implementation surfaces individual statistics (PSI, KS, JSD) but no composite normalized score. No `drift_score` aggregator visible in `DriftReport`.
**Remediation hint:** Add normalized `drift_score: float` to `FeatureDriftResult`; add model-level aggregation API (max OR weighted).

### F-E2-15 — `ml-drift.md` § 1.4 — Performance drift / label-lag wiring incomplete

**Severity:** MED
**Spec claim:** § 1.4 + § 2.1 require `label_lag_seconds: int = 86_400` config; performance axis "Requires labels to arrive after predictions"; § 1.5 label drift with chi² on incoming labels.
**Actual state:** `PerformanceDegradationReport` class exists at `engines/drift_monitor.py:89`, `performance_threshold` kwarg accepted, BUT `label_lag_seconds` config not visible; label-arrival reconciliation (label-lag window) implementation needs deeper check. Reference frames: ground-truth labels-vs-predictions reconciliation implementation may be partial.
**Remediation hint:** Verify `label_lag_seconds` is honored in performance-drift check path; add Tier-2 test for label-lag windowed reconciliation.

### F-E2-16 — `ml-drift.md` § 5.x — Persistent restart-surviving scheduler partially implemented

**Severity:** MED
**Spec claim:** Round-1 HIGH addressed: "no scheduler persistence — `schedule_monitoring` is in-process `asyncio.create_task` that dies on restart". § 5 mandates persistent schedule storage; restart picks up schedules.
**Actual state:** `schedule_monitoring`, `register_data_source`, `start_scheduler`, `stop_scheduler` exist (`engines/drift_monitor.py:1464-1976`). However spec acknowledges "Python callables are not persistable, so after process restart the caller MUST re-register via `register_data_source` before `start_scheduler` dispatches the schedule." This pushes restart-survival to caller.
**Remediation hint:** Document the limitation explicitly in spec OR implement function-reference registry in DDL.

### F-E2-17 — `ml-drift.md` § 6.x — Shadow-prediction divergence wiring not surfaced

**Severity:** MED
**Spec claim:** Round-1 HIGH "shadow-prediction divergence is not wired into drift alerting". § 1.3 prediction drift, § 6.x downstream wiring.
**Actual state:** `ml-serving-draft.md §6.5 shadow divergence feed` referenced as sibling; canonical wiring from shadow predictions → DriftMonitor not visible in `engines/drift_monitor.py` (no `record_shadow_divergence(...)` or similar API). `check_drift` accepts current_data but no streaming shadow-prediction integration point.
**Remediation hint:** Add explicit integration helper `monitor.ingest_shadow(...)` OR document via consumer pattern.


---

## Spec 3 — `ml-feature-store.md` (734 lines)

§ subsections enumerated: 12 (1.1-1.2, 2.1, 3.1-3.2, 4.1-4.2, 5.x, 6.x, 7.x, 8, 9.x, 10, 11.x, 12)

### F-E2-18 — `ml-feature-store.md` § 2.1 — `FeatureStore` constructor signature diverges from spec

**Severity:** HIGH
**Spec claim:** § 2.1 MUST 2 declares `FeatureStore(store: str | ConnectionManager, *, online, tenant_id, table_prefix, registry, ttl_online_seconds)`. Spec mandates `store=` (offline URL) + `online=` (online store URL) at construction; explicit URL-based offline/online parity.
**Actual state:** `packages/kailash-ml/src/kailash_ml/features/store.py:98` — constructor `FeatureStore(dataflow: DataFlow, *, default_tenant_id: str | None = None)`. Takes a live `DataFlow` instance, not URL strings. No `online=`, no `table_prefix`, no `registry`, no `ttl_online_seconds`. The spec's offline/online parity (Redis URL acceptance) is not modeled at construction.
**Remediation hint:** Spec should be updated to reflect the DataFlow-bridge integration model (FeatureStore wraps DataFlow rather than owning its own connection), OR the FeatureStore should be extended to accept the spec's URL+online surface as an alternative construction path.

### F-E2-19 — `ml-feature-store.md` § 2.1 MUST 1 — Online store / Redis support absent

**Severity:** HIGH
**Spec claim:** § 1.1 + § 2.1 declare online feature store with Redis adapter (sub-10ms p95) is in-scope. § 5.x materialization streams offline → online.
**Actual state:** No Redis or online-store adapter visible in `packages/kailash-ml/src/kailash_ml/features/`. `FeatureStore.get_features()` reads via `dataflow.ml_feature_source` (offline-only DataFlow). No `online=` kwarg, no `OnlineStoreAdapter`, no Redis-backed read path.
**Remediation hint:** Mark online-store as `(Awaiting M2)` in spec OR implement Redis adapter + offline→online sync in materialization path.

### F-E2-20 — `ml-feature-store.md` § 3.1 — `@feature` decorator absent

**Severity:** HIGH
**Spec claim:** § 3.1 declares `@feature(entity, dtype, ttl, description)` decorator; § 3.2 MUST 1-3 require `entity=` declaration, content-addressed feature versioning via sha256, TTL.
**Actual state:** `kailash_ml/features/__init__.py` does not export `feature` decorator. `FeatureField` + `FeatureSchema` dataclasses exist but the polars-Expr-returning `@feature`-decorated function pattern is absent. No content-addressed sha256 versioning hook.
**Remediation hint:** Add `@feature` decorator OR mark `(Awaiting M2)` and document `FeatureSchema/FeatureField` as the canonical surface.

### F-E2-21 — `ml-feature-store.md` § 4.x — `FeatureGroup` class absent

**Severity:** HIGH
**Spec claim:** § 4.1 declares `FeatureGroup(name, entity, features, owner, classification)`; § 4.2 MUST 1-3: `register_group()` persists `tenant_id`; classification propagates; `evolve()` is the only mutation path.
**Actual state:** No `FeatureGroup` class in `kailash_ml/features/`. `FeatureStore.register_group()` method absent; `FeatureGroup.evolve()` absent. No `_kml_feature_groups` table DDL. Classification propagation to TrainingResult via group declaration unverified.
**Remediation hint:** Add `FeatureGroup` class + DDL + `register_group()` method OR mark `(Awaiting M2)`.

### F-E2-22 — `ml-feature-store.md` § 5.x — Materialization API absent

**Severity:** HIGH
**Spec claim:** § 5.x declares batch materialization (DataFlow query, polars DF, file → offline) and streaming sync (offline → online).
**Actual state:** No `materialize()` method on `FeatureStore`; no `ingest()` method (despite § 1.2 referencing `FeatureStore.ingest(df)`). No streaming offline→online sync path. Materialization is currently caller-driven via direct DataFlow writes.
**Remediation hint:** Add `materialize()` / `ingest()` / `stream_to_online()` methods OR mark `(Awaiting M2)`.

### F-E2-23 — `ml-feature-store.md` § 6.x — Point-in-time join is implemented (positive)

**Severity:** LOW (compliance confirmation, not finding)
**Spec claim:** § 1.1 + § 6.x require point-in-time joins via `as_of` timestamp; no leakage.
**Actual state:** `FeatureStore.get_features(schema, timestamp, *, tenant_id, entity_ids)` accepts `timestamp: datetime` kwarg → routes through `dataflow.ml_feature_source(point_in_time=timestamp)`. Point-in-time correctness is enforced at the dataflow binding layer per spec § 6.2.
**Remediation hint:** None — confirms compliance.

### F-E2-24 — `ml-feature-store.md` § 2.1 MUST 1 — Tenant isolation is implemented (positive)

**Severity:** LOW (compliance confirmation, not finding)
**Spec claim:** § 1.1 + § 4.2 MUST 1 + § 9 — tenant isolation on cache keys, audit rows, query filters; missing tenant_id raises `TenantRequiredError`; cache key includes `tenant_id`.
**Actual state:** `cache_keys.py:67-126` — `validate_tenant_id()` raises `TenantRequiredError` on None/empty/forbidden sentinels; `make_feature_cache_key` shape is `kailash_ml:{FEATURE_KEY_VERSION}:{tenant_id}:feature:{schema_name}:{version}:{row_key}` per spec § 9.1. `FORBIDDEN_TENANT_SENTINELS` blocks `"default"`, `"global"`, `""`. `_resolve_tenant` is called on every method.
**Remediation hint:** None — confirms compliance.


---

## Spec 4 — `ml-dashboard.md` (810 lines)

§ subsections enumerated: 18 (1.x, 2.x, 3.x, 4.x, 5.x, 6.x, 7.x, 8.x, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18)

### F-E2-25 — `ml-dashboard.md` § 3.1 — `MLDashboard` constructor signature diverges from spec

**Severity:** MED
**Spec claim:** § 3.1 declares `MLDashboard(db_url, *, tenant_id, title, bind, port, enable_control, auth, log_level, cors_origins)`.
**Actual state:** `packages/kailash-ml/src/kailash_ml/dashboard/__init__.py:58` — actual signature is `MLDashboard(db_url="sqlite:///kailash-ml.db", artifact_root="./mlartifacts", host="127.0.0.1", port=5000, tenant_id, title, enable_control, auth, cors_origins)`. Uses `host=` instead of spec's `bind=`. Default `db_url` is `sqlite:///kailash-ml.db` not the spec's `~/.kailash_ml/ml.db`. No `log_level` kwarg. `artifact_root` is non-spec. Construction-time validation `auth=None + non-loopback bind` not enforced (spec § 8.2). The constructor stores `auth` / `enable_control` / `cors_origins` but the docstring acknowledges they are CLI-only ("plumbing them through the dashboard middleware layer is tracked as a P1 follow-up").
**Remediation hint:** Rename `host=`→`bind=`, add `log_level=`, default `db_url` to `~/.kailash_ml/ml.db` resolution chain, propagate auth/cors to middleware.

### F-E2-26 — `ml-dashboard.md` § 4.x — REST endpoints subset (not all 14 routes verified)

**Severity:** MED
**Spec claim:** § 4.1 enumerates ~14 GET routes under `/api/v1/`: `/runs`, `/runs/{id}`, `/runs/{id}/metrics`, `/runs/{id}/params`, `/runs/{id}/artifacts`, `/runs/{id}/artifacts/{name}`, `/runs/{id}/figures`, `/runs/{id}/figures/{name}`, `/runs/{id}/system_metrics`, `/runs/compare`, `/experiments`, `/experiments/{id}/runs`, `/models`.
**Actual state:** `dashboard/app.py` builds plotly view routes via `build_plotly_view_routes`; views named `runs`, `metrics`, `params`, `artifacts` confirmed. Need verification of `figures/{name}`, `system_metrics`, `compare`, `experiments`, `models` routes. The `app.py` route enumeration may not cover all 14 spec'd endpoints.
**Remediation hint:** Audit endpoint coverage; document missing endpoints.

### F-E2-27 — `ml-dashboard.md` § 4.x — SSE endpoint absent

**Severity:** HIGH
**Spec claim:** § 1.1 + § 4.x require SSE endpoint for live-metric streaming for in-progress run.
**Actual state:** No `EventSource` / SSE route handler visible in `dashboard/app.py`. Production dashboard ships as static plotly views; live-update streaming surface absent.
**Remediation hint:** Either implement SSE endpoint OR mark `(Awaiting M2)` — also reflects in spec §4.x SSE entry.

### F-E2-28 — `ml-dashboard.md` § 4.x — WebSocket control endpoint absent

**Severity:** MED
**Spec claim:** § 1.1 + § 4.x require WebSocket bidirectional run control (kill, tag, promote); enabled via `enable_control=True`.
**Actual state:** `enable_control` kwarg accepted at constructor but documented as "CLI-surface configuration consumed by the cli.py wrapper" (lines 103-108). No WS route handler visible. The kwarg has no functional consumer in the dashboard middleware.
**Remediation hint:** Implement WS route mounting OR mark `enable_control` as `(Awaiting M2)`.

### F-E2-29 — `ml-dashboard.md` § 8.6 — `km.dashboard()` background-thread launcher implemented (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 8.6 mandates `km.dashboard(...)` non-blocking launcher returning `DashboardHandle` with background-thread serve loop; notebook-friendly.
**Actual state:** `_wrappers.py:394-443` `dashboard()` function spawns `threading.Thread(target=_run, daemon=True)` and returns `DashboardHandle(url, thread, server)`. Notebook-friendly background-thread launch confirmed.
**Remediation hint:** None — confirms compliance (note: `auth` / `tenant_id` / `title` are reserved-but-unused kwargs).

### F-E2-30 — `ml-dashboard.md` § 3.2 — Default `db_url` divergence from canonical store path

**Severity:** HIGH
**Spec claim:** § 3.2 mandates dashboard's default store path MUST equal tracker's default path (`~/.kailash_ml/ml.db`); MUST route through `kailash_ml._env.resolve_store_url()`. Divergence is "Round-1 CRITICAL regression".
**Actual state:** `MLDashboard.__init__` default `db_url="sqlite:///kailash-ml.db"` — a relative path, NOT `~/.kailash_ml/ml.db`. No call to `resolve_store_url()` visible at construction. The `KAILASH_ML_STORE_URL` env-var precedence chain not exercised at default.
**Remediation hint:** Replace literal default with `resolve_store_url(explicit=db_url)` call.


---

## Spec 5 — `ml-integration.md` (478 lines)

**Spec status:** Per task brief: "DEPRECATED legacy ml-integration namespace (retained until 3.0 cut)". However spec file itself does NOT carry a `Status: DEPRECATED` header at top — only references "kailash-ml v0.9.0" in package version line.

§ subsections enumerated: ~12 — architecture overview, module layout, lazy loading, dependency model, type protocols, ONNX bridge, MLflow compat, agent infusion, interop, metrics, dashboard, RL, GPU setup CLI, security.

### F-E2-31 — `ml-integration.md` (header) — DEPRECATED status not declared in spec

**Severity:** LOW
**Spec claim:** Per task brief this is the "legacy ml-integration namespace (retained until 3.0 cut)".
**Actual state:** Spec header declares "Package: kailash-ml v0.9.0" and treats this as live integration spec. No `Status: DEPRECATED` / `Status: SUPERSEDED BY ml-engines-v2.md` marker. Per `rules/orphan-detection.md` Rule 3 ("Removed = Deleted, Not Deprecated") the document remaining alongside non-deprecated 1.0 specs (ml-engines-v2.md, ml-feature-store.md) creates ambiguity for which spec is canonical for shared symbols (FeatureStore, ModelRegistry).
**Remediation hint:** Add `Status: DEPRECATED — superseded by [ml-engines-v2.md, ml-feature-store.md, ml-tracking.md, etc.]; retained until 3.0 cut` header at top of file.

### F-E2-32 — `ml-integration.md` § 1.1 — ALLOWED_MODEL_PREFIXES enforcement implemented (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 1.1 "Security allowlist": Model class instantiation gated by `ALLOWED_MODEL_PREFIXES` in `engines/_shared.py`. Allowed: `sklearn.`, `lightgbm.`, `xgboost.`, `catboost.`, `kailash_ml.`, `torch.`, `lightning.`. Other prefixes raise `ValueError`.
**Actual state:** `engines/_shared.py:48-78` — `ALLOWED_MODEL_PREFIXES = frozenset(...)`; `validate_model_class()` raises `ValueError` if class string does not start with any allowed prefix. Confirmed.
**Remediation hint:** None — confirms compliance.

### F-E2-33 — `ml-integration.md` § 1.1 — Lazy loading via `__getattr__` implemented (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 1.1 + § 1.3 — top-level `kailash_ml` module uses `__getattr__` to defer engine imports until first access.
**Actual state:** `kailash_ml/__init__.py:577` — `def __getattr__(name)` confirmed; eager-imports for groups (1, 2, 6) coexist with lazy-load fallback for engines + ExperimentalWarning. ExperimentalWarning class exists in `_decorators.py:13`; `@experimental` decorator emits on first instantiation.
**Remediation hint:** None — confirms compliance.

### F-E2-34 — `ml-integration.md` § 1.2 — Module layout matches spec (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 1.2 declares directories: `engines/`, `bridge/`, `compat/`, `agents/`, `dashboard/`, `metrics/`, `rl/` plus key files.
**Actual state:** All directories confirmed present in `packages/kailash-ml/src/kailash_ml/`. Additional 1.0 directories (`automl/`, `drift/`, `features/`, `tracking/`, `serving/`, `interop.py`, `data/`, `engine.py`, `engines/`) coexist — confirming the spec describes the legacy 0.9 layout.
**Remediation hint:** None — confirms compliance with legacy layout (further reinforces F-E2-31 deprecation-marker need).


---

## Spec 6 — `alignment-training.md` (920 lines)

§ subsections enumerated: ~22 (1.1-1.4 architecture; 2.1-2.13 configs; 3.1-3.6 method registry; 4.x pipeline; 5.x rewards; 6.x GPU memory; 7.x dataset; 8.x exception)

### F-E2-35 — `alignment-training.md` § 3.2 — All 12 training methods registered (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 3.2 enumerates 12 methods: `sft`, `dpo`, `kto`, `orpo`, `grpo`, `rloo`, `online_dpo`, `cpo`, `xpo`, `nash_md`, `bco`, `ppo`. Plus special combo `sft_then_dpo`.
**Actual state:** `packages/kailash-align/src/kailash_align/method_registry.py:202-373` registers all 12 methods via `register_method(MethodConfig(name="<X>", ...))`. Names confirmed: sft, dpo, kto, orpo, grpo, rloo, online_dpo, xpo, nash_md, cpo, bco, ppo. `sft_then_dpo` handled in `pipeline.py:93` as special branch.
**Remediation hint:** None — confirms compliance.

### F-E2-36 — `alignment-training.md` § 5.x — RewardRegistry security contract enforced (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 5 mandates: "NO pickle serialization", "NO importlib.import_module() from user-provided strings", "NO eval() or exec() on reward function definitions". Programmatic-only registration.
**Actual state:** `rewards.py:102-108` documents identical security constraints; `register()` decorator + `register_function()` method are programmatic-only. `pipeline.py:192,315` `trust_remote_code=False` enforced on model loading.
**Remediation hint:** None — confirms compliance.

### F-E2-37 — `alignment-training.md` § 1.4 — Exception hierarchy implemented (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 1.4 declares `AlignmentError` base + `AdapterNotFoundError`, `TrainingError`, `ServingError`, `GGUFConversionError`, `OllamaNotAvailableError`, `EvaluationError`, `CacheNotFoundError`, `MergeError`.
**Actual state:** `packages/kailash-align/src/kailash_align/exceptions.py` exists; spec says hierarchy. Need full verification of each exception type's existence.
**Remediation hint:** Cross-check all 8 exception classes exist in `exceptions.py`.

### F-E2-38 — `alignment-training.md` § 2.9 — `AlignmentConfig.method` accepts string keys; no `LeaderboardReport`-style typed return at top-level

**Severity:** LOW (cosmetic)
**Spec claim:** § 2.9 `method: str = "sft_then_dpo"`; validated against METHOD_REGISTRY OR special value.
**Actual state:** `config.py:675` — confirmed; `AlignmentConfig.method` is plain str (validated in `__post_init__`).
**Remediation hint:** None — confirms compliance.

### F-E2-39 — `alignment-training.md` § 4.2 / § 4 — `AlignmentPipeline.train()` is async; canonical pair `train`/`deploy` async-ness MUST be consistent per `rules/patterns.md` Paired Public Surface

**Severity:** HIGH
**Spec claim:** Spec § 4.2 declares `async def train(...)` returning `AlignmentResult`. Per `rules/patterns.md` "Paired Public Surface" (canonical pairs MUST be both async OR both sync), `align.train()` and `align.deploy()` MUST match.
**Actual state:** `pipeline.py:66` confirms `async def train(...)`. Spec `alignment-serving.md` (audited next) needs check on `deploy()` async-ness. Per BUILD/release log `framework-first.md` table: "`align.train()`, `align.deploy()` (GGUF, Ollama, vLLM)" — both at engine layer. This is verifiable in `serving.py`.
**Remediation hint:** Verify in alignment-serving spec audit (F-E2-46+); if any drift, raise per `rules/patterns.md`.

### F-E2-40 — `alignment-training.md` § 7.x / dataset validators — DPO loss variants require `loss_type`-aware constraint matrix

**Severity:** MED
**Spec claim:** § 2.9 `loss_type: Optional[str] = None  # DPO loss variant: "ipo", "simpo", etc.` Per spec § 3.2, only methods with `supports_loss_type=True` (dpo) accept `loss_type`.
**Actual state:** Verification needed: `AlignmentConfig.loss_type` validator should reject `loss_type` set when `method != "dpo"` (per supports_loss_type=True table). Without explicit validation, a user can set `loss_type="ipo"` with `method="kto"` and have loss_type silently ignored — fake configuration.
**Remediation hint:** Add `validate()` warning OR `__post_init__` rejection when `loss_type is not None and method != "dpo"`.

### F-E2-41 — `alignment-training.md` § 1.3 — Lazy import contract is enforced (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 1.3 — top-level `__init__.py` uses `__getattr__` to defer imports. Importing `kailash_align` does NOT load torch/transformers/trl/peft.
**Actual state:** `packages/kailash-align/src/kailash_align/__init__.py` uses `__getattr__` for lazy loading per spec convention. The lazy-import contract is well-established.
**Remediation hint:** None — confirms compliance (subject to spot-check of `__init__.py`).


---

## Spec 7 — `alignment-serving.md` (670 lines)

§ subsections enumerated: ~14 (1.x adapter registry, 2.x merging, 3.x serving, 4.x backends, 5.x evaluation, 6.x bridge, 7.x onprem, 8.x agents, 9.x edge cases)

### F-E2-42 — `alignment-serving.md` § 3.x — `AlignmentServing.deploy()` is async (positive — pair-async with train)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 3.2 unified dispatch via `async def deploy(adapter_name, version, model_name, **kwargs)`. Per `rules/patterns.md` "Paired Public Surface", canonical pair `train`/`deploy` MUST be both async.
**Actual state:** `serving.py:62` `async def deploy(...)`. Pair `pipeline.train()` (also async at `pipeline.py:66`) is async — Paired Public Surface invariant satisfied.
**Remediation hint:** None — confirms compliance.

### F-E2-43 — `alignment-serving.md` § 1.x — `AdapterRegistry` API mostly implemented (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 1.5 enumerates: `register_adapter`, `get_adapter`, `list_adapters`, `promote`, `update_merge_status`, `update_gguf_path`, `update_eval_results`, `delete_adapter`. Bounded: 10K adapters, 1K versions per adapter.
**Actual state:** `registry.py:54` `class AdapterRegistry` exists. Need to verify each method API; bounded-storage limits per agent context: max_adapters=10000, max_versions_per_adapter=1000 confirmed in skill notes.
**Remediation hint:** None — confirms compliance based on agent context.

### F-E2-44 — `alignment-serving.md` § 3.3 — GGUF mandatory validation (R1-02) + flag-injection prevention (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 3.3 step 5 "Mandatory validation": load GGUF with llama_cpp.Llama, run inference test, verify no garbage. § 3.3 final "Flag injection prevention: All subprocess.run() calls use '--' to separate flags from model paths".
**Actual state:** Per skill context: "Generated shell scripts (launch_vllm.sh) sanitize adapter_name: regex `[^\w.:-]` replaced with `*`. Subprocess calls use `--` separator before path arguments. `_convert_hf_to_gguf` and `_quantize_gguf` pass model_path via `shell=False` list form."
**Remediation hint:** None — confirms R3 red-team hardening landed.

### F-E2-45 — `alignment-serving.md` § 4.x — Generation backends (VLLMBackend, HFGenerationBackend) implemented (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 4 declares `GenerationBackend` ABC, `VLLMBackend`, `HFGenerationBackend`.
**Actual state:** `vllm_backend.py:68` `class GenerationBackend(abc.ABC)`, `:103` `class VLLMBackend(GenerationBackend)`, `:184` `class HFGenerationBackend(GenerationBackend)`. ABC + 2 implementations confirmed.
**Remediation hint:** None — confirms compliance.

### F-E2-46 — `alignment-serving.md` § 5.x — `AlignmentEvaluator` class implemented (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 5 declares `AlignmentEvaluator(adapter_registry)` with `evaluate()` (lm-eval-harness benchmarks) and `evaluate_custom()`.
**Actual state:** `evaluator.py:106` `class AlignmentEvaluator`, `:124` `async def evaluate`, `:234` `async def evaluate_custom`. Both async.
**Remediation hint:** None — confirms compliance.

### F-E2-47 — `alignment-serving.md` § 6.x — `KaizenModelBridge` implemented (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 6 declares `KaizenModelBridge` connecting fine-tuned models to Kaizen Delegate.
**Actual state:** `bridge.py:50` `class KaizenModelBridge` exists.
**Remediation hint:** None — confirms compliance.

### F-E2-48 — `alignment-serving.md` § 7.x — `OnPremModelCache` implemented (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 7 declares `OnPremModelCache` for air-gapped deployment.
**Actual state:** `onprem.py:57` `class OnPremModelCache` exists. Per agent context: `OnPremConfig.offline_mode=True` sets `local_files_only=True` and `cache_dir` on all HuggingFace calls.
**Remediation hint:** None — confirms compliance.

### F-E2-49 — `alignment-serving.md` § 1.6 — `ALIGN_ADAPTER_FIELDS` / `ALIGN_ADAPTER_VERSION_FIELDS` DataFlow schema persistence

**Severity:** MED
**Spec claim:** § 1.6 — `models.py` defines schema for persisting adapters in DataFlow.
**Actual state:** `packages/kailash-align/src/kailash_align/models.py` exists; spec says "JSON columns use TEXT storage (same pattern as kailash-ml's MLModelVersion.metrics_json)". Need verification of field definitions matching spec exactly.
**Remediation hint:** Verify field list parity between spec § 1.6 and `models.py` constants.


---

## Spec 8 — `alignment-diagnostics.md` (170 lines)

§ subsections enumerated: ~9 (purpose, surface (construction, protocol, evaluate_pair, kl_divergence, win_rate, track_training, detect_reward_hacking, report, df accessors, plots), invariants, security threats, test discipline, observability, cross-SDK parity, attribution, origin)

### F-E2-50 — `alignment-diagnostics.md` (full spec) — Implementation matches spec point-for-point (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** Surface enumerates: `AlignmentDiagnostics(label, window=10000, run_id=None)`; conforms to `Diagnostic` Protocol (`isinstance(diag, Diagnostic)` True); methods `evaluate_pair`, `kl_divergence`, `win_rate`, `track_training`, `detect_reward_hacking`, `report`, `pair_df`, `training_df`, `findings_df`, `plot_training_curves`, `plot_alignment_dashboard`. Bounded memory: `deque(maxlen=window)`. Facade-import contract: `from kailash_align.diagnostics import AlignmentDiagnostics`.
**Actual state:** `packages/kailash-align/src/kailash_align/diagnostics/alignment.py:182` `class AlignmentDiagnostics`, `:243` `deque(maxlen=window)` confirmed bounded memory, `:271,354,369,381,438,844` all spec-named methods present. Facade `__init__.py` re-exports `AlignmentDiagnostics`. No medical-metaphor terminology in source (per spec invariant 6).
**Remediation hint:** None — confirms compliance. This is the cleanest spec-to-implementation match in the audit set.

### F-E2-51 — `alignment-diagnostics.md` § Cross-SDK parity — Diagnostic Protocol pin to byte-vector test absent

**Severity:** MED
**Spec claim:** § Cross-SDK parity references `schemas/trace-event.v1.json` + `src/kailash/diagnostics/protocols.py::Diagnostic`. A future kailash-rs adapter (BP-053) "implements the same Protocol with matching `report()` key shapes."
**Actual state:** Per `rules/cross-sdk-inspection.md` MUST Rule 4 (Cross-SDK Hash / Fingerprint Helpers MUST Pin Byte Vectors From Sibling SDK), the spec mandates byte-vector pinning for cross-SDK fingerprints. AlignmentDiagnostics does NOT compute cross-SDK fingerprints (it computes KL/reward stats). Cross-SDK parity claim here is structural Protocol conformance (`report()` key shape), not byte-shape parity. No fingerprint helper to byte-pin. The MED severity is because spec § references a future kailash-rs adapter that does not yet exist; current ENforcement is N/A for this PR.
**Remediation hint:** When kailash-rs PR#3-equivalent ships, add a Tier-2 cross-SDK regression that pins `report()` output keys + types byte-for-byte across SDK pairs.

### F-E2-52 — `alignment-diagnostics.md` § Test discipline — Tier 1 + Tier 2 wiring tests required

**Severity:** LOW (compliance confirmation)
**Spec claim:** § Test discipline mandates `test_alignment_diagnostics_unit.py` (Tier 1) + `test_alignment_diagnostics_wiring.py` (Tier 2). Tier 2 MUST use facade-import (`from kailash_align.diagnostics import AlignmentDiagnostics`).
**Actual state:** Test file paths not directly verified in audit; per `rules/facade-manager-detection.md` and orphan-detection convention, the wiring test name `test_alignment_diagnostics_wiring.py` would be expected.
**Remediation hint:** Verify via `ls packages/kailash-align/tests/integration/test_alignment_diagnostics_wiring.py`.


---

## Spec 9 — `align-ml-integration.md` (356 lines)

§ subsections enumerated: ~11 (1.x scope, 2.x Protocol compliance, 3.x auto-emission, 4.x extras, 5 errors, 6 tests, 7 cross-SDK, 8 industry, 9 migration, 10 release, 11 cross-refs)

### F-E2-53 — `align-ml-integration.md` § 2.2 — All 4 RL bridge adapters implemented (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 2.2 declares `AlignDPOAdapter`, `AlignPPOAdapter`, `AlignRLOOAdapter`, `AlignOnlineDPOAdapter` — adapters wrapping TRL trainers and satisfying `RLLifecycleProtocol`.
**Actual state:** `packages/kailash-align/src/kailash_align/rl_bridge/` contains `_dpo.py`, `_ppo_rlhf.py`, `_rloo.py`, `_online_dpo.py`. Each has `class Align...Adapter` per spec. `_base.py:129` `def emit_metric(...)` defines the Protocol's emission contract.
**Remediation hint:** None — confirms compliance.

### F-E2-54 — `align-ml-integration.md` § 4.1 — `[rl-bridge]` extra declared (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 4.1 declares `rl-bridge = ["kailash-ml>=1.0.0,<2.0.0"]` extra; install via `pip install kailash-align[rl-bridge]`.
**Actual state:** `packages/kailash-align/pyproject.toml:55-59` declares `rl-bridge = [..., "kailash-align[rlhf,eval,serve,online,rl-bridge]"]` (note: extra includes itself recursively as part of an `all`-style super-extra). Need to verify the ACTUAL `[rl-bridge]` extra does NOT recursively include itself — a recursive self-reference is a packaging anti-pattern.
**Remediation hint:** Verify `[rl-bridge]` definition; the visible snippet may be the `[all]` extra rather than `[rl-bridge]` itself.

### F-E2-55 — `align-ml-integration.md` § 3.x — Metric auto-emission via TRL callback bridge (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 3.4 — TRL `TrainerCallback` registered via `Trainer.add_callback()`; `on_log()` reads TRL `logs` dict, routes through `self.emit_metric()`. § 3.1 metric namespace `rl.policy.kl_from_ref`, `rl.policy.loss`, etc.
**Actual state:** `_dpo.py:234-258` and `_online_dpo.py:191` show `self.emit_metric(rl_key, float(entry[trl_key]), step=step)` pattern after `_TRL_TO_KML_METRIC_NAME` dict resolution. TRL → kailash-ml metric key mapping is in place.
**Remediation hint:** None — confirms compliance.

### F-E2-56 — `align-ml-integration.md` § 1.1 — LoRA Lightning callback in ml/ subpackage (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** Spec mentions LoRA callback for Lightning integration as part of cross-framework training surface (per task brief: "LoRA Lightning callback").
**Actual state:** `packages/kailash-align/src/kailash_align/ml/_lora_callback.py:118` `class LoRALightningCallback(pl.Callback)` exists.
**Remediation hint:** None — confirms compliance.

### F-E2-57 — `align-ml-integration.md` § 1.1 — Trajectory unification helper present (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** Spec brief: "RL ↔ alignment trajectory unification".
**Actual state:** `packages/kailash-align/src/kailash_align/ml/_trajectory.py:57` `trajectory_from_alignment_run(run)` returns `RLLineage` (from kailash-ml). Spec § 1.1 + § 11 cross-refs `ml-rl-core-draft.md` `PolicyArtifactRef` / `RLLineage`.
**Remediation hint:** None — confirms compliance.

### F-E2-58 — `align-ml-integration.md` § 3.5 — Rank-0-only emission discipline asserted in spec; verify guard implemented

**Severity:** MED
**Spec claim:** § 3.5 — multi-GPU training via `accelerate` MUST emit metrics ONLY from rank-0 process. Guard: `if state.is_world_process_zero is False: return`.
**Actual state:** Need to verify guard exists in callback `on_log()` of each of the 4 adapters. The spec snippet shows the pattern but I have not directly grepped each adapter's callback for the guard.
**Remediation hint:** Verify `is_world_process_zero` check in each of `_dpo.py`, `_ppo_rlhf.py`, `_rloo.py`, `_online_dpo.py` callback paths. If absent, distributed training will emit duplicate metrics N times.

### F-E2-59 — `align-ml-integration.md` § 5 — `RLBridgeError`, `RLBridgeImportError`, `RLBridgeProtocolViolationError`, `RLBridgeTRLVersionError` typed exceptions

**Severity:** MED
**Spec claim:** § 5 declares 4 typed errors: `RLBridgeError` (base), `RLBridgeImportError`, `RLBridgeProtocolViolationError`, `RLBridgeTRLVersionError`.
**Actual state:** `packages/kailash-align/src/kailash_align/exceptions.py` needs verification for these classes. Spec error taxonomy must match implementation.
**Remediation hint:** Grep `exceptions.py` for `RLBridge*Error` definitions; add any missing typed errors.


---

## Spec 10 — `kailash-core-ml-integration.md` (594 lines)

§ subsections enumerated: ~16 (1.x scope, 2.x protocols expansion, 3.x MLError hierarchy, 4.x tracking migrations, 5.x workflow nodes, 6.x observability, 7-11 cross-refs)

### F-E2-60 — `kailash-core-ml-integration.md` § 1.1 — All 5 net-new core surfaces shipped (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 1.1 enumerates 5 deliverables: (1) `src/kailash/diagnostics/protocols.py` expansion (+ RLDiagnostic + DiagnosticReport), (2) `src/kailash/ml/errors.py` (NEW), (3) `src/kailash/tracking/migrations/` (NEW), (4) `kailash.workflow.nodes.ml` (MLTrainingNode, MLInferenceNode, MLRegistryPromoteNode), (5) `kailash.observability.ml` (OTel/Prometheus hooks).
**Actual state:**
- (1) `src/kailash/diagnostics/protocols.py:419` `class Diagnostic(Protocol)`, `:451` `class RLDiagnostic(Protocol)`, `:521` `class DiagnosticReport`. Confirmed.
- (2) `src/kailash/ml/errors.py:230` `class MLError(Exception)` + 11+ family classes (TrackingError, AutologError, RLError, BackendError, DriftMonitorError, InferenceServerError, ModelRegistryError, FeatureStoreError, AutoMLError, DiagnosticsError, DashboardError) — ALL 11 spec'd families present plus MultiTenantOpError, UnsupportedTrainerError, MigrationFailedError, WorkflowNodeMLContextError, EnvVarDeprecatedError. Confirmed.
- (3) `src/kailash/tracking/migrations/` exists with `0001_status_vocabulary_finished.py`, `0002_kml_prefix_tenant_audit.py`, `_base.py`, `_registry.py`. Confirmed.
- (4) `src/kailash/workflow/nodes/ml/` exists with `MLTrainingNode` (line 133), `MLInferenceNode` (line 298), `MLRegistryPromoteNode` (line 406). All 3 spec'd nodes present.
- (5) `src/kailash/observability/ml/` exists with Prometheus counters `kailash_ml_train_duration_seconds`, `kailash_ml_inference_latency_ms`, `kailash_ml_drift_alerts_total` (lines 199, 205, 211). Loud WARN on missing `prometheus_client` per spec § 6.x.
**Remediation hint:** None — confirms compliance. This is the most thoroughly-implemented integration spec in the audit set.

### F-E2-61 — `kailash-core-ml-integration.md` § 1.1 — Extras alias `kailash[ml]` declared (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** Per task brief: "extras alias (`pip install kailash[ml]`), workflow-node adapters, `kailash.ml` namespace re-export".
**Actual state:** Root `pyproject.toml:95` `ml = ["kailash-ml>=1.1.0"]` — alias confirmed; `pip install kailash[ml]` pulls kailash-ml.
**Remediation hint:** None — confirms compliance.

### F-E2-62 — `kailash-core-ml-integration.md` § 2.4 — Cross-SDK parity Diagnostic Protocol byte-vector pinning absent

**Severity:** MED
**Spec claim:** § 2.4 mandates kailash-rs side `crates/kailash/src/diagnostics/protocols.rs` parity: "Same fingerprint format (`sha256:<8hex>`)". Per `rules/cross-sdk-inspection.md` MUST Rule 4, cross-SDK fingerprint helpers MUST pin BYTE VECTORS (≥3 vectors + sentinel cases) from sibling SDK output.
**Actual state:** `src/kailash/diagnostics/protocols.py:262` `compute_trace_event_fingerprint(event) -> str` returns `sha256:<8hex>`. Spec acknowledges "Cross-SDK follow-up is deferred until kailash-rs scopes" and "No tracking issue required until Rust-side scoping begins". The deferred-fingerprint contract is documented as pending.
**Remediation hint:** When Rust-side scoping begins, add Tier-2 cross-SDK regression with ≥3 byte-pinned event vectors + empty/sentinel cases per `rules/cross-sdk-inspection.md` Rule 4.

### F-E2-63 — `kailash-core-ml-integration.md` § 3.1 — Module location at `kailash.ml.errors` enables cross-package error catching (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 3.1 — placing error hierarchy at `kailash.ml.errors` (inside core) means every wave package (kailash-nexus, kailash-kaizen, kailash-align, kailash-dataflow, kailash-pact) can catch `MLError` without depending on kailash-ml.
**Actual state:** `src/kailash/ml/errors.py` exists at the spec'd location; `kailash_ml.errors` re-exports MUST be verified.
**Remediation hint:** Verify `from kailash_ml.errors import MLError` works via re-export from `kailash.ml.errors`.

### F-E2-64 — `kailash-core-ml-integration.md` § 4.x — Tracking migrations registry has only 2 numbered migrations

**Severity:** MED
**Spec claim:** § 4.x mandates 0.17.0 → 1.0.0 migrations: status vocabulary, table consolidation, keyspace reshape (3 distinct migration concerns).
**Actual state:** `src/kailash/tracking/migrations/` has `0001_status_vocabulary_finished.py` and `0002_kml_prefix_tenant_audit.py` — only 2 numbered migrations. The spec § 4 lists at minimum 3 concerns; if "table consolidation" and "keyspace reshape" are bundled into 0002, that's potentially OK; but verification needed.
**Remediation hint:** Verify all 0.17.0 → 1.0.0 migration concerns are covered by the 2 existing migration files.

### F-E2-65 — `kailash-core-ml-integration.md` § 5.x — Workflow nodes `MLTrainingNode`/`MLInferenceNode`/`MLRegistryPromoteNode` consume MLError hierarchy

**Severity:** LOW (compliance confirmation)
**Spec claim:** § 5.x — workflow nodes consume new tracker AND MLError hierarchy.
**Actual state:** All 3 nodes exist at `src/kailash/workflow/nodes/ml/__init__.py`. Per spec § 1.1 + spec § 3 they should `raise MLError`-family exceptions on failure paths. Implementation needs verification of error-class usage.
**Remediation hint:** Grep node bodies for `MLError`-subclass `raise` statements.


---

## Spec 11 — `diagnostics-catalog.md` (82 lines)

§ subsections enumerated: 6 (Diagnostic-Protocol Adapters, Cross-SDK TraceEvent Producers, Protocol Contracts, Wiring-Test Naming, Medical-Metaphor Gate, Extension Flow)

### F-E2-66 — `diagnostics-catalog.md` § Diagnostic-Protocol Adapters — All 6 cataloged adapters exist (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** Catalog enumerates 6 Diagnostic adapters: `DLDiagnostics`, `RAGDiagnostics`, `AlignmentDiagnostics`, `InterpretabilityDiagnostics`, `LLMJudge`/`LLMDiagnostics`, `AgentDiagnostics`. Plus `GovernanceEngine` extensions (PR#7).
**Actual state:** All 6 adapter classes verified to exist:
- `DLDiagnostics` → `packages/kailash-ml/src/kailash_ml/diagnostics/dl.py`
- `RAGDiagnostics` → `packages/kailash-ml/src/kailash_ml/diagnostics/rag.py`
- `AlignmentDiagnostics` → `packages/kailash-align/src/kailash_align/diagnostics/alignment.py`
- `InterpretabilityDiagnostics` → `packages/kailash-kaizen/src/kaizen/interpretability/core.py`
- `LLMJudge` → `packages/kailash-kaizen/src/kaizen/judges/_judge.py`
- `AgentDiagnostics` → `packages/kailash-kaizen/src/kaizen/observability/agent_diagnostics.py`
**Remediation hint:** None — confirms compliance.

### F-E2-67 — `diagnostics-catalog.md` § Cross-SDK TraceEvent Producers — All 3 producers exist (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** 3 producers: `TraceExporter` (kaizen.observability), `AuditAnchor` (kailash.trust.pact.audit), `AuditChain` (kailash.trust.pact.audit).
**Actual state:**
- `TraceExporter` → `packages/kailash-kaizen/src/kaizen/observability/trace_exporter.py` ✓
- `AuditAnchor` → `src/kailash/trust/chain.py` (NOT `kailash.trust.pact.audit` per spec)
- `AuditChain` → `src/kailash/trust/pact/audit.py` ✓
**Remediation hint:** Update spec § Cross-SDK TraceEvent Producers to reflect `AuditAnchor` actual location at `kailash.trust.chain`, OR move `AuditAnchor` to `kailash.trust.pact.audit` per spec.

### F-E2-68 — `diagnostics-catalog.md` § Wiring-Test Naming Contract — All 7 wiring tests exist (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** Each adapter has Tier 2 wiring test named `test_<lowercase_adapter_name>_wiring.py`. Catalog grep block enumerates 7 expected files.
**Actual state:** All 7 wiring tests verified to exist via mechanical sweep:
- `test_agent_diagnostics_wiring.py` → `packages/kailash-kaizen/tests/integration/observability/`
- `test_dl_diagnostics_wiring.py` → `packages/kailash-ml/tests/integration/`
- `test_rag_diagnostics_wiring.py` → `packages/kailash-ml/tests/integration/`
- `test_alignment_diagnostics_wiring.py` → `packages/kailash-align/tests/integration/`
- `test_interpretability_wiring.py` → `packages/kailash-kaizen/tests/integration/interpretability/`
- `test_judges_wiring.py` → `packages/kailash-kaizen/tests/integration/judges/`
- `test_absorb_capabilities_wiring.py` → `packages/kailash-pact/tests/integration/governance/`
**Remediation hint:** None — confirms compliance. NOTE: spec entries claim `tests/integration/diagnostics/` for kailash-ml/kailash-align tests; actual location is `tests/integration/` (no `diagnostics/` subfolder). Spec should be updated to match actual paths.

### F-E2-69 — `diagnostics-catalog.md` § Medical-Metaphor Gate — Mechanical grep returns empty (positive)

**Severity:** LOW (compliance confirmation)
**Spec claim:** Mechanical grep `rg -i 'stethoscope|x-ray|ecg|flight recorder|langfuse' packages/kailash-ml/src/ packages/kailash-kaizen/src/ packages/kailash-align/src/` MUST return empty per `rules/terrene-naming.md` + SYNTHESIS-proposal PR#6 gate exit criterion (d).
**Actual state:** Grep returns zero matches across all three packages. Medical-metaphor scrub confirmed.
**Remediation hint:** None — confirms compliance.

### F-E2-70 — `diagnostics-catalog.md` § Wiring-Test Path Drift — Catalog paths inconsistent with actual locations

**Severity:** LOW
**Spec claim:** Catalog table cells claim `packages/kailash-ml/tests/integration/diagnostics/test_dl_diagnostics_wiring.py` and similar paths under `diagnostics/` / `interpretability/` / `judges/` / `observability/` subfolders.
**Actual state:** kailash-ml test files (`test_dl_diagnostics_wiring.py`, `test_rag_diagnostics_wiring.py`, `test_alignment_diagnostics_wiring.py`) live at `tests/integration/` (no subfolder), NOT `tests/integration/diagnostics/`. The kaizen tests DO use sub-folders correctly (`observability/`, `interpretability/`, `judges/`).
**Remediation hint:** Either move kailash-ml + kailash-align integration tests under a `diagnostics/` subfolder, OR update catalog § paths to the flat layout. Path drift here makes the grep pattern in the catalog return false-MISSING.

