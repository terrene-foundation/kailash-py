# W5-E2 Findings — ml extras + align + integrations + diagnostics catalog

**Specs audited:** 11
**§ subsections enumerated:** TBD
**Findings:** CRIT=0 HIGH=0 MED=0 LOW=0
**Audit completed:** 2026-04-26 (in progress)

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
