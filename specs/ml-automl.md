# Kailash ML AutoML & Hyperparameter Search Specification

**Version:** 1.1.1 (matches `kailash_ml.__version__`)
**Status:** v2.0.0 (re-derived from implementation 2026-04-26 — supersedes v1.0.0)
**Package:** `kailash-ml`
**Parent domain:** ML Lifecycle (see `ml-engines.md` for `MLEngine.compare`/`.fit`; `ml-tracking.md` for run hierarchy; `ml-feature-store.md` for data retrieval)
**License:** Apache-2.0
**Python:** >=3.11
**Owner:** Terrene Foundation (Singapore CLG)

Origin: re-derivation of `specs/ml-automl.md` (v1.0.0) against the actual shipped surface in `packages/kailash-ml/src/kailash_ml/automl/`. The v1 spec OVERSTATES the implementation — Wave 5 portfolio audit at `workspaces/portfolio-spec-audit/04-validate/W5-E2-findings.md` recorded eight HIGH findings (F-E2-01..10) where spec ≠ code. v2 is the contract that matches what users actually receive when they `pip install kailash-ml==1.1.1`. Every capability the v1 spec asserted but the implementation does not deliver is enumerated under § "Deferred to M2 milestone" with a per-item rationale + sketch.

This spec re-derives the assertions from scratch against the canonical surface at `packages/kailash-ml/src/kailash_ml/automl/__init__.py`.

---

## 1. Scope

### 1.1 In Scope (v1.1.1)

This spec is authoritative for the AutoML primitives that ship in `kailash_ml.automl`:

- **`AutoMLEngine`** (canonical, at `kailash_ml.automl.engine:AutoMLEngine`) — orchestrates one search-strategy implementation over a user-supplied `ParamSpec` list, enforces a microdollar cost budget, consults PACT admission, persists a tenant-scoped audit row per trial.
- **Four search strategies** at `kailash_ml.automl.strategies` — `GridSearchStrategy`, `RandomSearchStrategy`, `BayesianSearchStrategy`, `SuccessiveHalvingStrategy`.
- **`CostTracker`** (microdollar-granularity budget accounting) at `kailash_ml.automl.cost_budget:CostTracker`.
- **PACT admission wire-through** at `kailash_ml.automl.admission:check_trial_admission` — degrades gracefully when `kailash_pact` is absent or its `GovernanceEngine.check_trial_admission` is unimplemented.
- **`MLEngine.compare()`** at `kailash_ml.engine:MLEngine.compare` — the documented entry point for "train and rank candidate families." It does NOT delegate to `AutoMLEngine` and is documented in `specs/ml-engines.md`; this spec only references it.

### 1.2 Out of Scope

- **Feature engineering auto-search** — `FeatureEngineer` (under `kailash_ml.engines.feature_engineer`) owns the feature-generation search.
- **Reward model search for RLHF** — lives in `kailash-align` (RLHF-specific HPO).
- **Neural architecture search (NAS)** — not implemented.
- **AutoML UI / leaderboard rendering** — covered by `MLDashboard`; this spec owns the data model.
- **`MLEngine.fit_auto()`** — the v1 spec mandated this entry point; the canonical implementation does not provide it. See § "Deferred to M2 milestone" entry D-fitauto.

### 1.3 Two Coexisting Surfaces (v1.0.0 → v1.1.1 Migration)

Two `AutoMLEngine` classes ship in 1.1.1 and the user may encounter either:

| Path                                                                 | Status     | Constructor signature                                                                                                                                               |
| -------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kailash_ml.automl.engine.AutoMLEngine` (canonical M1 surface)       | preferred  | `AutoMLEngine(*, config, tenant_id, actor_id, connection=None, cost_tracker=None, governance_engine=None)`                                                          |
| `kailash_ml.engines.automl_engine.AutoMLEngine` (legacy M0 scaffold) | deprecated | `AutoMLEngine(pipeline, search, *, registry=None)` — ALSO reachable as `kailash_ml.AutoMLEngine` via the module-level `__getattr__` in `kailash_ml/__init__.py:593` |

Verified by direct read: top-level `kailash_ml.AutoMLEngine` resolves through `kailash_ml/__init__.py` `__getattr__` (lines 580-622) into `kailash_ml.engines.automl_engine` — i.e. the LEGACY scaffold. To use the canonical M1 surface, callers MUST `from kailash_ml.automl import AutoMLEngine`.

This is a known transitional state. The legacy scaffold is retained for backwards compatibility until the W32 sweep removes it; the canonical surface is the spec authority for every contract below.

**Wave 6 follow-up:** flip the `kailash_ml/__init__.py` `__getattr__` map entry (line 593) from `kailash_ml.engines.automl_engine` (legacy) to `kailash_ml.automl.engine` (canonical) so that `kailash_ml.AutoMLEngine` and `from kailash_ml.automl import AutoMLEngine` resolve to the same class. Until that lands, downstream code that follows the v1 spec's `from kailash_ml import AutoMLEngine` form receives the LEGACY scaffold; this is a user-hostile divergence that this spec documents but does not perpetuate.

---

## 2. Construction

### 2.1 `AutoMLEngine` (canonical)

```python
from kailash_ml.automl import (
    AutoMLConfig,
    AutoMLEngine,
    AutoMLResult,
    CostTracker,
    GovernanceEngineLike,
    TrialRecord,
)

config = AutoMLConfig(
    task_type="classification",                      # "classification" | "regression" | "ranking" | "clustering"
    metric_name="accuracy",
    direction="maximize",                            # "maximize" | "minimize"
    search_strategy="random",                        # "grid" | "random" | "bayesian" | "halving" | "successive_halving"
    max_trials=30,
    time_budget_seconds=3600,
    total_budget_microdollars=0,                     # 0 => unbounded (explicit opt-out)
    auto_approve_threshold_microdollars=0,
    agent=False,                                     # double opt-in (caller flag + kailash-ml[agents] extra)
    auto_approve=False,
    max_llm_cost_usd=5.0,
    min_confidence=0.6,
    seed=42,
)

engine = AutoMLEngine(
    config=config,
    tenant_id="acme",
    actor_id="alice@acme",
    connection=conn_mgr,                             # optional ConnectionManager for `_kml_automl_trials` audit
    cost_tracker=None,                               # optional pre-built tracker; defaults from config
    governance_engine=None,                          # optional PACT engine; degrades gracefully if missing
)
```

### 2.2 `AutoMLConfig` Fields (verified at `automl/engine.py:117-190`)

| Field                                 | Type    | Default            | Validated at `__post_init__`                                                                                                      |
| ------------------------------------- | ------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `task_type`                           | `str`   | `"classification"` | MUST be one of `"classification" \| "regression" \| "ranking" \| "clustering"`                                                    |
| `metric_name`                         | `str`   | `"accuracy"`       | non-empty                                                                                                                         |
| `direction`                           | `str`   | `"maximize"`       | MUST be `"maximize" \| "minimize"`                                                                                                |
| `search_strategy`                     | `str`   | `"random"`         | resolved by `resolve_strategy()`; valid: grid \| random \| bayesian \| halving \| successive_halving                              |
| `max_trials`                          | `int`   | `30`               | MUST be positive                                                                                                                  |
| `time_budget_seconds`                 | `int`   | `3600`             | MUST be positive finite                                                                                                           |
| `total_budget_microdollars`           | `int`   | `0`                | MUST be ≥ 0 (0 = unbounded explicit opt-out)                                                                                      |
| `auto_approve_threshold_microdollars` | `int`   | `0`                | MUST be ≥ 0                                                                                                                       |
| `agent`                               | `bool`  | `False`            | flag only; the `kailash-ml[agents]` extra check is the engine's responsibility (see § 8)                                          |
| `auto_approve`                        | `bool`  | `False`            | when `False`, any trial whose `budget_microdollars > auto_approve_threshold_microdollars` raises `PromotionRequiresApprovalError` |
| `max_llm_cost_usd`                    | `float` | `5.0`              | MUST be finite + non-negative (`math.isfinite` enforces NaN/Inf rejection per `rules/zero-tolerance.md` Rule 2)                   |
| `min_confidence`                      | `float` | `0.6`              | MUST be finite, in `[0.0, 1.0]`                                                                                                   |
| `seed`                                | `int`   | `42`               | passed verbatim to strategy `__init__`                                                                                            |

`AutoMLConfig` is a regular `@dataclass` (not frozen). `to_dict()` returns a flat JSON-safe `dict[str, Any]`.

### 2.3 MUST Rules

#### MUST 1. Constructor Validates `tenant_id` And `actor_id`

`AutoMLEngine.__init__` (verified `automl/engine.py:419-423`) raises `ValueError` when either is empty or non-string. The check is the single enforcement point for `rules/tenant-isolation.md` MUST Rule 5 across the AutoML surface — there is no public path that bypasses this check.

#### MUST 2. Financial Field Validation

`AutoMLConfig.max_llm_cost_usd`, `time_budget_seconds`, `min_confidence`, and every numeric budget MUST be validated via `math.isfinite()` at construction. `NaN` and `Inf` are rejected with `ValueError` (NOT `InvalidConfigError` — see § 10 deferral note). Negative budgets raise. This is the literal contract at `automl/engine.py:143-173`.

#### MUST 3. Agent Mode Is Caller-Flag Only In v1.1.1

`config.agent=True` is a caller flag. The runtime extra check (`kailash-ml[agents]` installed, `kailash_kaizen` importable) is performed by callers that wire LLM suggestions into a `trial_fn`; the engine itself does NOT raise `MissingExtraError` because that error class is not in the package's typed-error set. Spec v1 § 2.3 MUST 3 ("`MissingExtraError` raised at `__init__` time") is NOT honoured by the canonical implementation. See § "Deferred to M2 milestone" entry D-missingextra.

#### MUST 4. Default Cost Ceiling Resolution

When `cost_tracker=None`, the engine constructs a `CostTracker` (`automl/engine.py:429-440`) using this precedence:

1. If `config.total_budget_microdollars > 0` → `ceiling = config.total_budget_microdollars`
2. Else if `config.agent and config.max_llm_cost_usd > 0` → `ceiling = usd_to_microdollars(config.max_llm_cost_usd)`
3. Else → `ceiling = 0` (unbounded; explicit opt-out)

The constructed tracker is `tenant_id`-scoped and uses the default `max_ledger_entries=10_000` bound (see § 8.1).

---

## 3. Run Surface — `AutoMLEngine.run()`

### 3.1 Signature (verified `automl/engine.py:513-540`)

```python
async def run(
    self,
    *,
    space: Sequence[ParamSpec],
    trial_fn: Callable[[Trial], Awaitable[TrialOutcome]],
    estimate_trial_cost_microdollars: Optional[Callable[[Trial], int]] = None,
    strategy: SearchStrategy | None = None,
    run_id: str | None = None,
    source_tag: str = "baseline",                    # "baseline" | "agent"
) -> AutoMLResult: ...
```

The user owns the trainer (`trial_fn`). `AutoMLEngine` provides governance + audit + cost-budget enforcement only. There is no `data` / `target` / `families` / `parallel_trials` / `executor` / `early_stopping_patience` / `top_k` / `ensemble` kwarg on `run()` — users who want those abstractions use `MLEngine.compare()` (separate spec, separate surface) or call `run()` repeatedly themselves.

(Engine module docstring at `automl/engine.py:7-12` mentions auto-deriving a `ParamSpec` from `FeatureSchema`; this is NOT implemented and should be stripped from the docstring as a Wave 6 follow-up. Until then the docstring is misleading; the canonical contract is the `space=` kwarg above.)

### 3.2 `AutoMLResult` Shape (verified `automl/engine.py:243-285`)

```python
@dataclass
class AutoMLResult:
    run_id: str
    tenant_id: str
    actor_id: str
    strategy: str
    total_trials: int
    completed_trials: int
    denied_trials: int
    failed_trials: int
    best_trial: TrialRecord | None     # None when every trial failed/was denied
    all_trials: list[TrialRecord]
    elapsed_seconds: float
    cumulative_cost_microdollars: int
    early_stopped: bool
    early_stopped_reason: str | None   # one of "time_budget_exceeded" | "promotion_requires_approval" | "cost_budget_exhausted" | None
```

`to_dict()` returns the result + an additional `cumulative_cost_usd` (presentation float).

`AutoMLResult` is the canonical return type. The v1-spec'd `LeaderboardReport` is NOT implemented — it is enumerated under § "Deferred to M2 milestone" entry D-leaderboard.

### 3.3 `TrialRecord` Shape (verified `automl/engine.py:193-240`, frozen dataclass)

```python
@dataclass(frozen=True)
class TrialRecord:
    trial_id: str                                       # uuid4
    run_id: str
    tenant_id: str
    actor_id: str
    trial_number: int
    strategy: str
    params: dict[str, Any]
    metric_name: str
    metric_value: float | None                          # None when status != "completed" or metric is non-finite
    cost_microdollars: int
    started_at: datetime                                 # tz-aware UTC
    finished_at: datetime | None
    status: str                                         # "completed" | "failed" | "skipped" | "denied" | "approval_required"
    admission_decision_id: str | None
    admission_decision: str | None                      # "admitted" | "denied" | "skipped" | "unimplemented" | "error"
    error: str | None = None
    source: str = "baseline"                            # "baseline" | "agent"
    fidelity: float = 1.0
    rung: int = 0
```

`to_dict()` returns a JSON-safe dict with `started_at` / `finished_at` already ISO-formatted.

### 3.4 Run-Loop Invariants

The `run()` loop enforces, in this order, on every iteration (verified `automl/engine.py:553-819`):

1. **Time budget check** (line 571): `time.monotonic() >= deadline` → set `early_stopped=True`, `early_stopped_reason="time_budget_exceeded"`, break.
2. **Prompt-injection scan** (lines 583-619): every `trial.params` value of type `str` is matched against six regex patterns (`ignore previous instructions`, `disregard the above`, `system:`, `<system>` / `<instruction>` / `<prompt>` open/close, `DROP TABLE`, trailing `--`). On match: record a `status="skipped"` row with `error="prompt_injection: ..."`, advance to the next suggestion. Defense-in-depth — the params are typed (int/float/categorical) at trainer-call time, so this catches misuse before audit pollution.
3. **Pre-flight cost estimate** (line 621): `estimated_cost = int(estimate_trial_cost_microdollars(trial))` if supplied else `0`.
4. **PACT admission** (lines 626-700): `check_trial_admission(...)` is called. Three outcomes:
   - Raises `PromotionRequiresApprovalError` → record `status="approval_required"`, set `early_stopped=True`, `early_stopped_reason="promotion_requires_approval"`, break.
   - Returns `admission.admitted=False` → record `status="denied"`, advance.
   - Returns `admission.admitted=True` → continue.
5. **Pre-flight budget check** (lines 701-717): when `estimated_cost > 0` and `cost_tracker.check_would_exceed(estimated_cost)` is True → set `early_stopped=True`, `early_stopped_reason="cost_budget_exhausted"`, break BEFORE the trial runs.
6. **Trial execution** (lines 718-761): `outcome = await trial_fn(trial)`. On exception: record `status="failed"` row with `error="<ExcClass>: <msg>"`, advance.
7. **Post-trial cost record** (lines 762-789): the cost is `outcome.cost_microdollars` if positive else `estimated_cost`. Recording goes through `CostTracker.record(...)`. If the record raises `BudgetExceeded`, the engine sets `early_stopped=True`, `early_stopped_reason="cost_budget_exhausted"`, but STILL records the trial's actual outcome (the trial completed before the budget check fired).
8. **Strategy observe + history** (lines 789-790): `strategy.observe(outcome); history.append(outcome)`.
9. **Strategy stop check** (line 815): `strategy.should_stop(history)` → break.

The loop terminates when `strategy.suggest(history)` returns `None` (strategy exhaustion, e.g. grid finished or halving last rung) OR any of the breaks above fire.

### 3.5 MUST Rules

#### MUST 1. Every Trial Persists An Audit Row

Every iteration of the loop records exactly one `TrialRecord` via `_record_trial(...)`. The recorder appends to in-memory `_trials` AND, when the audit table is ready, INSERTs into `_kml_automl_trials`. Failure to INSERT (table-create failed, transient DB error) emits a WARN but does NOT block the run — the in-memory record is still appended. This is the documented "in-memory fallback" mode at `automl/engine.py:476-511`.

#### MUST 2. Best-Trial Selection Is Direction-Aware

`_pick_best(...)` (`automl/engine.py:866-885`) returns the best `TrialRecord` among `status="completed"` rows whose `metric_value` is finite. Direction `"maximize"` sorts by `-metric_value`; `"minimize"` by `metric_value`. When zero completed/finite trials exist, `best_trial=None`.

#### MUST 3. `source_tag` Is Persisted Verbatim

Every `TrialRecord` carries `source` set to whatever `source_tag` the caller passed to `run()`. The orchestrator decides whether a particular `run()` invocation is `"agent"` or `"baseline"`; the engine itself does NOT split traffic between agent and baseline streams within a single `run()` call. See § "Deferred to M2 milestone" entry D-baselineparallel.

---

## 4. Search Strategies

### 4.1 Implemented Strategies (verified at `automl/strategies/`)

| Class                       | File                            | `name`       | Notes                                                                                                                                                      |
| --------------------------- | ------------------------------- | ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GridSearchStrategy`        | `automl/strategies/grid.py`     | `"grid"`     | Discretises `float` / `log_float` to `grid_resolution` evenly-spaced points; raises `HPOSpaceUnboundedError` (locally defined) when grid would be infinite |
| `RandomSearchStrategy`      | `automl/strategies/random.py`   | `"random"`   | Deterministic under seed; bounded by `max_trials`                                                                                                          |
| `BayesianSearchStrategy`    | `automl/strategies/bayesian.py` | `"bayesian"` | scikit-optimize when `kailash-ml[automl-bayes]` extra installed; deterministic local fallback otherwise                                                    |
| `SuccessiveHalvingStrategy` | `automl/strategies/halving.py`  | `"halving"`  | Rung-aware; `initial_trials=9`, `reduction_factor=3`, `min_fidelity=1.0`, `max_fidelity=81.0` defaults                                                     |

`resolve_strategy(name: str, *, seed: int = 42, **kwargs: object) -> SearchStrategy` at `automl/strategies/__init__.py:39-62` is the factory; accepted names are `grid`, `random`, `bayesian`, `halving`, `successive_halving` (alias). Unknown names raise `ValueError`.

### 4.2 `ParamSpec` (verified `automl/strategies/_base.py:18-61`)

```python
@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: str                  # "int" | "float" | "log_float" | "categorical" | "bool"
    low: float | int | None = None
    high: float | int | None = None
    choices: tuple[Any, ...] | None = None
```

Validation at `__post_init__`:

- `kind` MUST be one of the five values above.
- `int` / `float` / `log_float` REQUIRE `low` AND `high`, both finite, with `low <= high`.
- `log_float` REQUIRES `low > 0`.
- `categorical` REQUIRES non-empty `choices`.
- `bool` is implemented internally as `categorical` with `choices=(False, True)` (object-set after init).

### 4.3 `Trial` and `TrialOutcome` (verified `automl/strategies/_base.py:64-95`)

```python
@dataclass(frozen=True)
class Trial:
    trial_number: int
    params: dict[str, Any]
    fidelity: float = 1.0
    rung: int = 0

@dataclass
class TrialOutcome:
    trial_number: int
    params: dict[str, Any]
    metric: float
    metric_name: str
    direction: str             # "maximize" | "minimize"
    duration_seconds: float = 0.0
    cost_microdollars: int = 0
    fidelity: float = 1.0
    rung: int = 0
    error: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def is_finite(self) -> bool: ...
```

### 4.4 `SearchStrategy` Protocol (verified `_base.py:98-120`)

```python
@runtime_checkable
class SearchStrategy(Protocol):
    name: str
    def suggest(self, history: list[TrialOutcome]) -> Trial | None: ...
    def observe(self, outcome: TrialOutcome) -> None: ...
    def should_stop(self, history: list[TrialOutcome]) -> bool: ...
```

Adding a new strategy is one `@dataclass` + an entry in `resolve_strategy()`. Protocol conformance is checked at runtime by `isinstance(obj, SearchStrategy)`.

### 4.5 MUST Rules

#### MUST 1. Strategies Are Seed-Deterministic

Every strategy's `__post_init__` constructs `random.Random(self.seed)` (or for bayesian, the same seed seeds skopt). Re-running with the same `seed` and the same `space` produces a byte-identical sequence of `suggest()` returns. This invariant is the test contract for `test_hpo_algorithm_random_suggest_determinism` (per § 11).

#### MUST 2. SuccessiveHalving Is Rung-Aware

Promotion happens within a rung once `len(rung.outcomes) >= len(rung.trials) AND len(rung.trials) > 0`. Trials at different rungs are NOT compared. Higher-fidelity trials are NOT used to early-stop lower-fidelity siblings. (This is the v1 spec § 4.2 MUST 5 ASHA promotion rule, applied to non-async halving — async ASHA is deferred per § "Deferred to M2 milestone" entry D-asha.)

#### MUST 3. Bayesian Has Two Modes With Identical Protocol

When `scikit-optimize` is installed (`kailash-ml[automl-bayes]`), Bayesian routes through `skopt.Optimizer` with `acq_func="EI"`. When absent, a local mean+variance EI fallback runs. Both modes are deterministic under the seed and satisfy `SearchStrategy`. Switching is invisible to callers.

---

## 5. Parallel / Distributed Execution

### 5.1 Single-Process Local Only (v1.1.1)

The canonical engine executes trials sequentially in the calling event loop. There is NO `parallel_trials` kwarg, NO `executor` kwarg, NO Ray/Dask integration, and NO `MissingExtraError` typed exception. Multi-process trial execution is the caller's responsibility (e.g. dispatch trials to a `ProcessPoolExecutor` and feed results back to `engine.run(strategy=preconfigured_strategy)`).

This is a deliberate contraction of the v1 spec § 5 surface. See § "Deferred to M2 milestone" entry D-executor.

---

## 6. Early Stopping & Budget

### 6.1 Time Budget Hard Cap

`config.time_budget_seconds` is enforced via `time.monotonic()` against a deadline computed at `run()` start. When the deadline is reached, `early_stopped=True`, `early_stopped_reason="time_budget_exceeded"`. Trials in flight at the deadline are NOT pre-empted — the loop checks the deadline only at the top of the iteration, so an in-progress `trial_fn` runs to completion. The check fires BEFORE the next `strategy.suggest(history)` call.

### 6.2 Cost Budget Hard Cap

`CostTracker.check_would_exceed(estimated_cost)` is consulted pre-flight; on True, the run aborts with `early_stopped_reason="cost_budget_exhausted"` BEFORE the trial runs. When the actual cost (returned by `trial_fn` via `outcome.cost_microdollars`) exceeds the remaining budget after the trial completes, `CostTracker.record(...)` raises `BudgetExceeded` and the engine sets `early_stopped=True` but keeps the trial's audit row.

### 6.3 No `BudgetExhaustedError` Raised From `run()`

`run()` ALWAYS returns an `AutoMLResult` (possibly with `early_stopped=True`, possibly with `best_trial=None`). It does NOT raise `BudgetExhaustedError`, `InsufficientTrialsError`, or any AutoML-typed error from the AutoMLError family. Failures inside `trial_fn` are wrapped into per-trial `status="failed"` records and the run continues.

This diverges from v1 spec § 6.1 MUST 1 ("BudgetExhaustedError is non-fatal" — i.e., the v1 spec said it WOULD be raised but caught by `MLEngine.fit_auto`). In v1.1.1, the engine never raises an AutoMLError-family error; it returns an `AutoMLResult` whose `early_stopped_reason` field documents the cause. See § "Deferred to M2 milestone" entry D-typederrors.

### 6.4 No Per-Trial Early-Stopping Patience

The canonical engine has no `early_stopping_patience` field on `AutoMLConfig` and no per-trial early-stopping logic inside `run()`. Strategies own their own stop criteria via `should_stop(history)`. See § "Deferred to M2 milestone" entry D-earlystopping.

---

## 7. Ensemble Composition

### 7.1 Current Surface — `EnsembleEngine` (Method-Style)

`kailash_ml.engines.ensemble:EnsembleEngine` (verified, line 245) provides four ensemble methods as instance methods:

```python
from kailash_ml import EnsembleEngine

engine = EnsembleEngine()
result: BlendResult = engine.blend(models=[...], data=df, target="churned", weights=[...], method="soft", test_size=0.2, seed=42)
result: StackResult = engine.stack(...)
result: BagResult   = engine.bag(...)
result: BoostResult = engine.boost(...)
```

Each method returns a method-specific result dataclass (`BlendResult`, `StackResult`, `BagResult`, `BoostResult` — verified lines 45-163). Each result has its own `from_dict` classmethod for round-tripping but NOT a `from_leaderboard` constructor.

### 7.2 No `Ensemble.from_leaderboard()` In v1.1.1

The v1 spec § 7.1 declared `Ensemble.from_leaderboard(report=, method=, k=, meta_learner=)` as the canonical entry point. In v1.1.1:

- `Ensemble` (the class name) is NOT exported from `kailash_ml.__init__`.
- `EnsembleEngine` is exported (lazy via `__getattr__` per `kailash_ml/__init__.py:596`) but does NOT take a `LeaderboardReport` / `AutoMLResult` as input — its methods accept fitted estimators directly.
- `EnsembleFailureError` IS in the typed-error hierarchy (`kailash.ml.errors:659`), but is not currently raised from any code path inside `EnsembleEngine` (the methods raise `ValueError` on bad inputs).

See § "Deferred to M2 milestone" entries D-ensembleleaderboard and D-ensembleresult.

### 7.3 MUST Rules

#### MUST 1. Ensemble Methods Return Method-Specific Result Types

`blend()` returns `BlendResult`; `stack()` returns `StackResult`; etc. The v1 spec mandate that ensembles return a `TrainingResult` (§ 7.2 MUST 1) is NOT implemented at the `EnsembleEngine` level. Conversion to a `TrainingResult` for downstream `MLEngine.register()` is the caller's responsibility.

---

## 8. LLM-Augmented AutoML — v1.1.1 Behaviour

### 8.1 Caller-Driven Wiring Only

In v1.1.1 the engine itself does NOT manage an LLM. The `config.agent` flag is persisted on `AutoMLConfig` but is read only by callers who wire LLM suggestions into their own `trial_fn`. The legacy scaffold at `engines/automl_engine.py:201-230` (`LLMCostTracker`) implements POST-HOC cost summation (raises `LLMBudgetExceededError` AFTER the call when `_spent > _max_budget`); this is NOT wired into the canonical engine's `run()` loop.

### 8.2 Prompt-Injection Scan At Run-Loop Level

The canonical engine scans every `trial.params` value of type `str` against six regex patterns (verified `automl/engine.py:82-109`). On a hit, the trial is recorded as `status="skipped"` with `error="prompt_injection: <offenders>"` and the run continues. This is defense-in-depth — not a primary security boundary, since `trial_fn` consumes typed (int/float/categorical) hyperparameters, not raw strings passed to a downstream LLM.

### 8.3 Microdollar Cost Tracking (Atomic)

`CostTracker.record(...)` is the single atomic check+record entry point (verified `cost_budget.py:211-274`). It performs:

1. Type-check (`microdollars` MUST be `int`; floats raise `TypeError`).
2. Acquire `asyncio.Lock`.
3. If `microdollars > 0` and `check_would_exceed(...)` is True → emit WARN log, raise `BudgetExceeded(proposed, remaining, ceiling)`.
4. Append `CostRecord(timestamp, microdollars, kind, trial_number, note)` to a bounded `deque[CostRecord]` with `maxlen=max_ledger_entries` (default 10,000).
5. Update `_cumulative_microdollars` (clamped at 0 to permit negative-cost compensating entries without going below zero).
6. Emit INFO log line `automl.cost_tracker.record`.

The check is race-free across concurrent `record()` calls within ONE event loop. Cross-process sharing is deferred (the in-memory ledger is per-instance).

### 8.4 No Token-Level Backpressure

Spec v1 § 8.3 MUST 2 mandated TOKEN-LEVEL backpressure (compute `max_tokens_this_call` BEFORE the LLM call to prevent overrun). The v1.1.1 implementation has NO `max_prompt_tokens` / `max_completion_tokens` fields on `AutoMLConfig`. The caller's `estimate_trial_cost_microdollars` callback IS the pre-flight gate — but it is per-trial, not per-token. See § "Deferred to M2 milestone" entry D-tokenbackpressure.

### 8.5 No Baseline-Parallel-With-Agent Stream

The v1 spec § 8.3 MUST 1 mandated that, when `agent=True`, a baseline pure-algorithmic search runs in PARALLEL with the agent's suggestions. v1.1.1's `run()` executes ONE sequential stream per invocation; the orchestrator decides whether the stream is "baseline" or "agent" via the `source_tag` kwarg. See § "Deferred to M2 milestone" entry D-baselineparallel.

### 8.6 Approval Gate Before PACT

The human-approval gate fires BEFORE PACT consultation (verified `admission.py:221-239`):

```python
if not auto_approve and budget_microdollars > auto_approve_threshold_microdollars:
    raise PromotionRequiresApprovalError(...)
```

The `auto_approve=False` default matches the v1 spec § 8.3 MUST 4 "human-on-the-loop" intent.

---

## 8A. Schema DDL

### 8A.1 `_kml_automl_trials` (implemented)

The canonical audit table is `_kml_automl_trials` (NOT `_kml_automl_agent_audit` — that name is from the v1 spec and is not implemented). DDL is emitted at first use by `_ensure_trials_table(conn)` (verified `automl/engine.py:296-348`):

```sql
CREATE TABLE IF NOT EXISTS _kml_automl_trials (
  trial_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  trial_number INTEGER NOT NULL,
  strategy TEXT NOT NULL,
  params_json TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  metric_value REAL,
  cost_microdollars INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  admission_decision_id TEXT,
  admission_decision TEXT,
  error TEXT,
  source TEXT NOT NULL DEFAULT 'baseline',
  fidelity REAL NOT NULL DEFAULT 1.0,
  rung INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_automl_trials_tenant_run
  ON _kml_automl_trials(tenant_id, run_id, trial_number);
```

The DDL uses dialect-portable types (`TEXT` / `INTEGER` / `REAL`) that work for both Postgres and SQLite. Callers that want Postgres-native types (`UUID` / `JSONB` / `TIMESTAMPTZ` / `BIGSERIAL`) MUST land a numbered migration per `rules/schema-migration.md` MUST Rule 1 — the engine's own DDL is the lowest-common-denominator portable form.

### 8A.2 First-Use DDL Discipline

`_ensure_trials_table(conn)` is called at most once per `AutoMLEngine` instance (tri-state cache `_audit_table_ready: bool | None`). On the first `_record_trial(...)` call:

1. If `connection is None` → emit WARN `automl.engine.no_connection`, set cache to `False`, audit is in-memory only.
2. Else → call `_ensure_trials_table(conn)`. On success, cache `True`. On exception, emit WARN `automl.audit.table_create_failed`, cache `False`.
3. Subsequent INSERT failures emit WARN `automl.engine.audit_insert_failed` per row but do NOT block the run.

This is the documented "in-memory fallback" mode and is permitted per `rules/observability.md` Rule 7 (bulk-op partial failure WARN) + `rules/schema-migration.md` Rule 1 (first-use DDL is a degraded-mode development convenience; production deployments should land a numbered migration ahead of any sweep). The engine cannot install database migrations during a run, so emitting a WARN and continuing with in-memory persistence is the correct disposition. Wave 6 should ship a numbered migration that supersedes the lazy DDL path.

### 8A.3 No Separate `_kml_automl_agent_audit` Table

The v1 spec § 8A.2 declared a separate `_kml_automl_agent_audit` table with `(agent_kind, agent_model_id, pact_decision, pact_reason, proposed_config, budget_microdollars, actual_microdollars, outcome)` columns. v1.1.1's `_kml_automl_trials` carries `(admission_decision, admission_decision_id, source, cost_microdollars, params)` on the same row — agent-vs-baseline is split via the `source` column at query time.

See § "Deferred to M2 milestone" entry D-agentaudit.

---

## 9. Persistence

### 9.1 In-Memory By Default

`AutoMLEngine(connection=None)` is supported and persists trial audit rows to `self._trials` only. The `AutoMLResult.all_trials` field is the in-memory snapshot returned to the caller. WARN line `automl.engine.no_connection` emits on first `_record_trial(...)` call so operators can see the audit is degraded.

### 9.2 Database-Backed Audit

Pass any object with `execute(sql: str, *args)` and `fetch(...)` coroutine methods (`kailash.db.connection.ConnectionManager` is the canonical type). The engine uses positional `?` placeholders that work for both `aiosqlite` and `asyncpg` adapters.

### 9.3 No Cross-Process Cost Tracker (Yet)

`CostTracker` is in-memory + per-instance. W32 32a (per the docstring at `cost_budget.py:5-11`) is the planned ConnectionManager-backed persister that survives process restart and shares state across workers. Until then, parallel/distributed AutoML runs MUST construct one tracker per worker.

---

## 10. Error Taxonomy

### 10.1 Errors Currently Raised From The AutoML Surface (v1.1.1)

Verified by direct read of the canonical surface AND `kailash.ml.errors` (re-exported via `kailash_ml.errors`):

| Error                            | Source module                                | When raised                                                                                                                                                                                |
| -------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ValueError`                     | `automl/engine.py` `__post_init__` + `run()` | Non-finite budgets, negative trial count, unknown task_type/direction, empty `space`, empty/non-string tenant_id/actor_id                                                                  |
| `BudgetExceeded`                 | `automl/cost_budget.py:77`                   | Proposed spend would push cumulative cost over the configured ceiling. NOT a subclass of `MLError`/`AutoMLError` — it is a plain `Exception`.                                              |
| `PromotionRequiresApprovalError` | `automl/admission.py:58`                     | (a) `auto_approve=False` AND `budget_microdollars > auto_approve_threshold_microdollars`; (b) PACT engine raises any non-(`AttributeError`/`NotImplementedError`) exception (fail-CLOSED). |
| `HPOSpaceUnboundedError`         | `automl/strategies/grid.py:32`               | `GridSearchStrategy` invoked with an unbounded continuous dimension. Local class; NOT in `kailash.ml.errors` taxonomy.                                                                     |
| `TypeError`                      | `automl/cost_budget.py:64,228`               | Non-numeric USD input to `usd_to_microdollars`; non-int microdollars to `CostTracker.record`.                                                                                              |

### 10.2 Errors From `kailash_ml.errors` (Available But Not Currently Raised By AutoML)

Verified at `src/kailash/ml/errors.py`:

- `BudgetExhaustedError` (line 649) — `AutoMLError` subclass; spec'd for `MLEngine.fit_auto()` use.
- `InsufficientTrialsError` (line 654) — `AutoMLError` subclass; spec'd for `MLEngine.fit_auto()` use.
- `EnsembleFailureError` (line 659) — `AutoMLError` subclass; not currently raised by `EnsembleEngine`.
- `ParamValueError` (line 378) — `TrackingError, ValueError` multi-inherit; spec'd for HPO param validation.
- `UnsupportedTrainerError` (line 334) — direct `MLError` subclass; spec'd for Trainable-bypass detection.

These five are part of the typed taxonomy but the canonical AutoML surface does not raise them in v1.1.1. They are reserved for the M2 milestone surface (`MLEngine.fit_auto`, `Ensemble.from_leaderboard`).

### 10.3 Errors Named In v1 Spec But Absent From Both Surfaces

The v1 spec § 10 enumerated 11 typed exceptions. Six are absent from `kailash.ml.errors` AND not raised by the canonical AutoML surface:

- `TrialFailureError` — trial failures wrap into `TrialRecord(status="failed", error=...)` instead.
- `MissingExtraError` — caller-side responsibility; not raised by AutoMLEngine.
- `ContextLostError` — distributed execution is not implemented; the error has no call site.
- `InvalidConfigError` — `AutoMLConfig.__post_init__` raises plain `ValueError` instead.
- `AgentCostBudgetExceededError` — agent-baseline split is not implemented; cost-overrun raises `BudgetExceeded` (not `AgentCostBudgetExceededError`).
- (`HPOSpaceUnboundedError` exists locally in `automl/strategies/grid.py` but is NOT in the canonical `kailash.ml.errors` hierarchy.)

See § "Deferred to M2 milestone" entry D-typederrors.

### 10.4 MUST Rule

#### MUST 1. Cross-Cutting Errors Re-Exported From `kailash_ml.errors`

`kailash_ml.errors` re-exports the entire `kailash.ml.errors` hierarchy (verified `errors.py:21-94`). Identity is preserved: `kailash_ml.errors.MLError is kailash.ml.errors.MLError` is `True`. Callers MAY catch on either name. Per `rules/orphan-detection.md §6` every entry in `kailash_ml.errors.__all__` is eagerly imported (no lazy `__getattr__`).

---

## 11. Test Contract

### 11.1 Tier 1 + Tier 2 — Files Actually Present

Test files verified by `find packages/kailash-ml/tests -name 'test_automl*'`:

| File                                             | Tier   | Purpose                                                                                    |
| ------------------------------------------------ | ------ | ------------------------------------------------------------------------------------------ |
| `tests/unit/test_automl_engine.py`               | Tier 1 | Engine behaviour with stubbed connection + stubbed governance                              |
| `tests/unit/test_automl_engine_unit.py`          | Tier 1 | Engine helper internals (`_record_trial`, time-budget logic, `_select_best`)               |
| `tests/unit/test_automl_admission.py`            | Tier 1 | PACT admission decision matrix (skipped / unimplemented / approval_required / fail-closed) |
| `tests/unit/test_automl_cost_budget.py`          | Tier 1 | `CostTracker.record` atomicity, negative-compensation, `check_would_exceed` lock-free      |
| `tests/unit/test_automl_strategies.py`           | Tier 1 | `ParamSpec` validation, strategy protocol conformance, `resolve_strategy` factory          |
| `tests/integration/test_automl_engine_wiring.py` | Tier 2 | Real Postgres / SQLite, end-to-end run with audit row persistence — see § 11.3             |

The exact assertions per file are owned by the test code, not this spec. To enumerate the cases run:

```bash
pytest --collect-only -q packages/kailash-ml/tests/unit/test_automl_engine.py \
                        packages/kailash-ml/tests/unit/test_automl_engine_unit.py \
                        packages/kailash-ml/tests/unit/test_automl_admission.py \
                        packages/kailash-ml/tests/unit/test_automl_cost_budget.py \
                        packages/kailash-ml/tests/unit/test_automl_strategies.py \
                        packages/kailash-ml/tests/integration/test_automl_engine_wiring.py
```

### 11.2 Tier 3 (E2E)

No Tier 3 e2e file exists for the canonical `kailash_ml.automl.engine.AutoMLEngine` surface as of v1.1.1. The legacy scaffold has e2e coverage under `kailash-ml`'s broader test pyramid; the canonical surface relies on the Tier 2 wiring test (§ 11.3) for end-to-end coverage with real infrastructure. Wave 6 follow-up: add `test_automl_engine_e2e_with_real_trainer.py` exercising the canonical surface against a real model family.

### 11.3 Wiring Test Per `rules/facade-manager-detection.md`

Per the docstring at `automl/engine.py:29-32`, `AutoMLEngine` is a manager-shape class. The wiring test lives at `packages/kailash-ml/tests/integration/test_automl_engine_wiring.py` (verified to exist) and constructs the engine through the public facade (`from kailash_ml.automl import AutoMLEngine`) with real `AutoMLConfig` + real `ConnectionManager`.

---

## 12. Cross-References

- `specs/ml-engines.md` — `MLEngine.compare()` is the high-level "train and rank candidate families" surface; this spec covers `AutoMLEngine` as the lower-level orchestration primitive.
- `specs/ml-tracking.md` — nested-run semantics for tracking AutoML parents + per-trial children.
- `specs/ml-feature-store.md` — feature retrieval; out of scope for this spec.
- `specs/pact-ml-integration.md` §2.1 — upstream `GovernanceEngine.check_trial_admission` contract that `kailash_ml.automl.admission` wires against.
- `rules/tenant-isolation.md` MUST 5 — every audit row carries `tenant_id`.
- `rules/event-payload-classification.md` — agent-side payload hashing applies to `_record_trial` rows when classified params are involved.
- `rules/zero-tolerance.md` Rule 2 — non-finite budgets rejected at construction.
- `rules/dataflow-identifier-safety.md` — `_kml_automl_trials` table name routes through dialect quoting at the connection layer (callers' responsibility; the engine emits the literal name).
- `rules/schema-migration.md` MUST 1 — production deployments SHOULD land a numbered migration that creates `_kml_automl_trials` ahead of first use; the first-use DDL is degraded-mode for development only.
- `rules/orphan-detection.md` § 6 — every error in `kailash_ml.errors.__all__` is eagerly imported.
- `rules/facade-manager-detection.md` MUST 1 — `AutoMLEngine` wiring test exists at `tests/integration/test_automl_engine_wiring.py`.

---

## 13. Examples

### 13.1 Minimal Sweep (No PACT, No Connection, In-Memory)

```python
import asyncio
from kailash_ml.automl import (
    AutoMLConfig, AutoMLEngine, ParamSpec, Trial, TrialOutcome,
)

config = AutoMLConfig(
    task_type="classification",
    metric_name="accuracy",
    direction="maximize",
    search_strategy="random",
    max_trials=10,
    time_budget_seconds=60,
    seed=42,
)

engine = AutoMLEngine(
    config=config,
    tenant_id="acme",
    actor_id="alice@acme",
)

space = [
    ParamSpec(name="n_estimators", kind="int", low=10, high=200),
    ParamSpec(name="max_depth", kind="int", low=2, high=12),
    ParamSpec(name="learning_rate", kind="log_float", low=1e-3, high=0.3),
]

async def trial_fn(trial: Trial) -> TrialOutcome:
    # User-owned trainer; e.g. fit a LightGBM and return validation accuracy
    accuracy = await my_train_and_eval(trial.params)
    return TrialOutcome(
        trial_number=trial.trial_number,
        params=dict(trial.params),
        metric=accuracy,
        metric_name=config.metric_name,
        direction=config.direction,
    )

result = asyncio.run(engine.run(space=space, trial_fn=trial_fn))
print(result.best_trial.metric_value, result.best_trial.params)
```

### 13.2 With Cost Budget + PACT Stub

```python
from kailash_ml.automl import (
    AutoMLConfig, AutoMLEngine, CostTracker, ParamSpec,
)

config = AutoMLConfig(
    task_type="regression",
    metric_name="rmse",
    direction="minimize",
    search_strategy="bayesian",
    max_trials=50,
    time_budget_seconds=1800,
    total_budget_microdollars=10_000_000,             # $10
    auto_approve=False,                                # require approval over threshold
    auto_approve_threshold_microdollars=1_000_000,    # $1 per-trial threshold
)

engine = AutoMLEngine(
    config=config,
    tenant_id="acme",
    actor_id="alice@acme",
    connection=conn_mgr,                               # writes _kml_automl_trials
    cost_tracker=CostTracker(
        ceiling_microdollars=10_000_000,
        tenant_id="acme",
    ),
    governance_engine=None,                            # PACT degrades to "skipped"
)

def estimate_cost(trial):
    return 500_000  # $0.50 per trial

result = await engine.run(
    space=space,
    trial_fn=trial_fn,
    estimate_trial_cost_microdollars=estimate_cost,
)

if result.early_stopped:
    print(f"stopped: {result.early_stopped_reason}")
print(f"spent: ${result.cumulative_cost_microdollars/1_000_000:.2f}")
```

### 13.3 Standalone Strategy Use (Without `AutoMLEngine`)

```python
from kailash_ml.automl import resolve_strategy, ParamSpec, Trial, TrialOutcome

strategy = resolve_strategy(
    "halving",
    space=[ParamSpec("lr", "log_float", low=1e-4, high=1.0)],
    initial_trials=9,
    reduction_factor=3,
    seed=42,
)
history: list[TrialOutcome] = []
while (trial := strategy.suggest(history)) is not None:
    outcome = my_evaluate(trial)
    strategy.observe(outcome)
    history.append(outcome)
    if strategy.should_stop(history):
        break
```

---

## Deferred to M2 milestone

The v1 spec promises 12 capabilities the v1.1.1 implementation does not provide. Each is enumerated here with the spec citation, current behaviour, deferral rationale, and a 1-2 sentence implementation sketch.

### D-bohb. BOHB / CMA-ES / PBT Search Strategies

- **v1 spec citation:** § 4.1 ("`BOHBAlgorithm`, `CMAESAlgorithm`, `ASHAAlgorithm`, plus `pbt` algorithm") + § 4.2 MUST 4 (BOHB multi-fidelity contract) + MUST 2 (PBT first-class).
- **Current behaviour:** Only four strategies (grid/random/bayesian/halving). `automl/strategies/__init__.py` docstring (verified line 11) acknowledges "BOHB / CMA-ES / PBT / ASHA are deferred to post-M1 milestones." `resolve_strategy("bohb")` raises `ValueError`.
- **Deferral rationale:** Each is a substantial new strategy class with its own protocol-conformant `suggest`/`observe`/`should_stop` plus specific required kwargs (BOHB needs `fidelity_param`/`fidelity_min`/`fidelity_max`/`reduction_factor`); shipping all four together would double the strategy surface area without a proven user pull.
- **Sketch:** Add four new files under `automl/strategies/{bohb,cmaes,pbt,asha}.py`, each a `@dataclass` implementing `SearchStrategy`. BOHB wraps `hpbandster` (or local fallback). CMA-ES wraps `cma`. PBT extends `SuccessiveHalvingStrategy` with a per-trial mutation step. ASHA is the async variant of halving (rung promotion is event-driven, not population-complete). Add each name to `resolve_strategy()`.

### D-asha. ASHA As Default For `parallel_trials > 1`

- **v1 spec citation:** § 4.2 MUST 5 — ASHA is the default promotion rule when `parallel_trials > 1`.
- **Current behaviour:** No `parallel_trials` kwarg exists; `SuccessiveHalvingStrategy` is the closest analogue but is synchronous.
- **Deferral rationale:** Depends on D-executor (parallel/distributed execution).
- **Sketch:** Add `ASHAStrategy` class that promotes trials event-driven (as outcomes land) instead of waiting for the rung to fill. Default `search_strategy="asha"` when `parallel_trials > 1` is detected. Requires D-executor first.

### D-executor. `executor=` Kwarg (Local / Ray / Dask)

- **v1 spec citation:** § 5.1-5.4 — `executor: str = "local"` with `"ray"` / `"dask"` values; § 5.4 MUST 1 mandates `MissingExtraError` when extra missing; § 5.4 MUST 2 mandates `tenant_id` + `parent_run_id` propagation; `ContextLostError` on lost context.
- **Current behaviour:** Single-process sequential only. No `executor` / `parallel_trials` kwarg on `AutoMLEngine.__init__` or `run()`. `MissingExtraError` and `ContextLostError` are not in the typed-error set.
- **Deferral rationale:** Distributed trial execution is a substantial architectural addition (worker dispatch, result-stream consumption, tenant-scoped Redis or worker registry); high-leverage but high-cost. The single-process surface in v1.1.1 satisfies the critical-path use cases (CLI, single-host tutorials, CI runs).
- **Sketch:** Add `executor: str = "local"` and `parallel_trials: int = 1` fields to `AutoMLConfig`. Implement three executor classes: `LocalExecutor` (uses `ProcessPoolExecutor`), `RayExecutor` (requires `kailash-ml[ray]` extra), `DaskExecutor` (requires `kailash-ml[dask]` extra). Add `MissingExtraError` and `ContextLostError` to `kailash.ml.errors`. Every dispatched task carries `(tenant_id, parent_run_id)` as bound context; missing on the worker → `ContextLostError`.

### D-ensembleleaderboard. `Ensemble.from_leaderboard()` Classmethod

- **v1 spec citation:** § 7.1 — `Ensemble.from_leaderboard(report=, method=, k=, meta_learner=)` as the canonical entry point + § 3.3 MUST 3 (ensemble build is opt-out with `ensemble=True` default).
- **Current behaviour:** `EnsembleEngine` exposes `blend()` / `stack()` / `bag()` / `boost()` instance methods that take fitted estimators directly. There is no `Ensemble` class with a `from_leaderboard` classmethod. `AutoMLConfig` has no `ensemble: bool` or `top_k: int` field.
- **Deferral rationale:** Requires a `LeaderboardReport` type (D-leaderboard) before it has anything to consume; cycles with D-fitauto.
- **Sketch:** Introduce `Ensemble` (or rename `EnsembleEngine`) with `from_leaderboard(report: LeaderboardReport, *, method: str, k: int = 3, meta_learner: str = "logistic") -> Ensemble`. Add `ensemble: bool = True` and `top_k: int = 3` fields to a new (M2-era) config class. Wire a call to `Ensemble.from_leaderboard(...)` into `MLEngine.fit_auto()` (D-fitauto) when `config.ensemble=True`.

### D-ensembleresult. `Ensemble.fit()` Returns `TrainingResult`

- **v1 spec citation:** § 7.2 MUST 1 — ensemble fit returns standard `TrainingResult` with `model_uri`, `metrics`, `feature_versions`, plus a new `base_models: list[str]` field.
- **Current behaviour:** Each ensemble method returns its method-specific result dataclass (`BlendResult` / `StackResult` / `BagResult` / `BoostResult`). None return a `TrainingResult`. None populate a `base_models` list.
- **Deferral rationale:** Requires both a `TrainingResult` shape that accommodates ensembles AND a downstream `MLEngine.register(ensemble_result)` path. The v1 spec also adds a new audit field that is a schema change.
- **Sketch:** Add `Ensemble.fit(...) -> TrainingResult` as the canonical entry point that internally calls the appropriate `EnsembleEngine.{blend,stack,bag,boost}`. Convert the method-specific result into a `TrainingResult` with `base_models=[r.model_uri for r in inputs]`. Raise `EnsembleFailureError` (already in `kailash.ml.errors:659`) on meta-learner failure.

### D-fitauto. `MLEngine.fit_auto()` Convenience Method

- **v1 spec citation:** § 3.1 — `MLEngine.fit_auto(data, *, task, target, time_budget, metric, families, parallel_trials, executor, max_trials, early_stopping_patience, agent, ensemble, top_k, seed) -> LeaderboardReport`.
- **Current behaviour:** `MLEngine` has `compare()` (verified `engine.py:994`) which is similar but NOT identical: `compare(*, families, n_trials, hp_search, metric, early_stopping, timeout_seconds, data, target) -> ComparisonResult`. The kwargs `task`, `time_budget`, `parallel_trials`, `executor`, `early_stopping_patience`, `top_k`, `agent`, `ensemble`, `seed` are NOT exposed. The return type is `ComparisonResult`, not `LeaderboardReport`.
- **Deferral rationale:** A new entry point with a different return type would fork `MLEngine`'s public surface without a corresponding implementation underneath. Until D-leaderboard, D-executor, D-ensembleleaderboard land, `fit_auto` would be a documentation lie.
- **Sketch:** Add `fit_auto(...)` to `MLEngine` once the prerequisites land. It composes `setup() → compare(hp_search="bayesian", n_trials=...) → finalize() → Ensemble.from_leaderboard(...)`, returning a `LeaderboardReport` whose entries reference per-trial nested run IDs.

### D-leaderboard. `LeaderboardReport` Typed Result

- **v1 spec citation:** § 3.2 — `LeaderboardReport` dataclass with `parent_run_id`, `task_type`, `primary_metric`, `entries: list[LeaderboardEntry]`, `ensemble_result: TrainingResult | None`, `total_trials`, `total_budget_seconds_used`, `early_stopped`, `tenant_id`. `LeaderboardEntry` has `rank`, `family`, `hyperparameters`, `metrics`, `tracker_run_id`, `feature_versions`, `elapsed_seconds`, `trial_number`.
- **Current behaviour:** The canonical result type is `AutoMLResult` (verified `automl/engine.py:243-285`); the field set is described in § 3.2 above. There is no `family` field (single-family sweeps), no `tracker_run_id` (the engine doesn't bind to `kailash_ml.tracking`), no `feature_versions` (feature-store integration is the caller's responsibility), no `ensemble_result`. `MLEngine.compare()` returns `ComparisonResult`, a separate type owned by `specs/ml-engines.md`.
- **Deferral rationale:** Two divergent result types (`AutoMLResult` for the engine, `ComparisonResult` for `MLEngine.compare()`) plus the v1-spec'd `LeaderboardReport` makes three. Reconciliation is a separate work item.
- **Sketch:** Define `LeaderboardReport` and `LeaderboardEntry` in a new module `kailash_ml/automl/report.py`. Add a converter `LeaderboardReport.from_automl_result(result, families, ensemble_result=None) -> LeaderboardReport`. Reserve `AutoMLResult` for the low-level engine; `LeaderboardReport` for the `MLEngine.fit_auto()` surface.

### D-tokenbackpressure. Token-Level LLM Backpressure

- **v1 spec citation:** § 8.3 MUST 2 — `max_llm_cost_usd` enforced via TOKEN-LEVEL backpressure (compute `max_tokens_this_call` BEFORE the call to prevent overrun); § 8.3 MUST 2a mandates `max_prompt_tokens` / `max_completion_tokens` agent-config kwargs; `min_confidence` from `AgentGuardrailMixin`.
- **Current behaviour:** `AutoMLConfig` has `min_confidence` but NOT `max_prompt_tokens` / `max_completion_tokens`. The legacy `LLMCostTracker.record(...)` (`engines/automl_engine.py:215-230`) performs POST-HOC summation: it records cost AFTER the call and raises `LLMBudgetExceededError` only when `_spent > _max_budget`. The exact "$4.99 → $7.50 in one call" failure mode the v1 spec forbids is the implementation's actual behaviour.
- **Deferral rationale:** Token-level backpressure requires per-model pricing tables AND per-call computation of max_tokens — significant complexity that depends on D-baselineparallel before it has a meaningful enforcement seat.
- **Sketch:** Add `max_prompt_tokens` and `max_completion_tokens` to a new `AgentConfig` dataclass under `kailash_ml/automl/agent.py`. Compute `max_tokens_this_call = remaining_budget / (model_cost_per_token * safety_margin=1.2)`. Wire into the agent-side `trial_fn` factory (the engine itself stays neutral about LLM; the agent factory enforces). Also re-route `LLMCostTracker` to call the canonical `CostTracker` so cost tracking is unified.

### D-baselineparallel. Baseline-Parallel-With-Agent Stream

- **v1 spec citation:** § 8.3 MUST 1 — when `agent=True`, a baseline pure-algorithmic search runs in PARALLEL with the agent's suggestions; final report tags each trial `source="agent" | "baseline"`.
- **Current behaviour:** The canonical engine runs ONE stream per `run()` invocation. The orchestrator chooses `source_tag="baseline"` or `source_tag="agent"`. The legacy scaffold's `engines/automl_engine.py:529` says "Agent augmentation (not implemented in v1 -- requires kaizen agents)" and proceeds without parallelism.
- **Deferral rationale:** Depends on D-executor (parallel infrastructure) AND D-fitauto (the high-level surface that would orchestrate the two streams).
- **Sketch:** Inside `MLEngine.fit_auto(agent=True)`, dispatch two `AutoMLEngine.run(...)` invocations (one with `source_tag="baseline"`, one with `source_tag="agent"`) to the configured executor and merge results into one `LeaderboardReport`. Trials in both streams write to the same `_kml_automl_trials` table — `source` column is the partitioning key.

### D-agentaudit. `_kml_automl_agent_audit` Separate Audit Table

- **v1 spec citation:** § 8A.2 / § 8A.3 — separate `_kml_automl_agent_audit` table with `(tenant_id, automl_run_id, trial_number, agent_kind, agent_model_id, actor_id, pact_decision, pact_reason, proposed_config, budget_microdollars, actual_microdollars, outcome, occurred_at)` columns; SQLite + Postgres variants. § 8A.4 mandates `test__kml_automl_agent_audit_schema_migration.py`.
- **Current behaviour:** A single `_kml_automl_trials` table carries all the columns (including agent-relevant fields like `admission_decision_id`, `admission_decision`, `cost_microdollars`, `source`); the `source` column is the agent/baseline split. There is no separate `_kml_automl_agent_audit` table and no schema-migration test for it.
- **Deferral rationale:** A separate agent-audit table is justified IF the column set diverges meaningfully from the trial-audit table (e.g., per-call LLM telemetry that would bloat trial rows). Until LLM telemetry is wired (D-tokenbackpressure), the unified table is sufficient.
- **Sketch:** Add `_kml_automl_agent_audit` as a numbered migration when token-level LLM telemetry lands. Schema: `(id BIGSERIAL, tenant_id, automl_run_id UUID, trial_number, agent_kind, agent_model_id, actor_id, pact_decision, pact_reason, proposed_config JSONB, prompt_tokens INTEGER, completion_tokens INTEGER, budget_microdollars BIGINT, actual_microdollars BIGINT, outcome, occurred_at TIMESTAMPTZ)`. Add SQLite-portable variant. Add `test__kml_automl_agent_audit_schema_migration.py` per `rules/schema-migration.md` MUST 5.

### D-typederrors. Six Missing Typed Errors

- **v1 spec citation:** § 10 enumerates 11 typed exceptions; v1.1.1 has six of them (`BudgetExhaustedError`, `InsufficientTrialsError`, `EnsembleFailureError`, `ParamValueError`, `UnsupportedTrainerError`, plus `HPOSpaceUnboundedError` defined locally in `automl/strategies/grid.py`). Six are missing entirely from `kailash.ml.errors`: `TrialFailureError`, `MissingExtraError`, `ContextLostError`, `InvalidConfigError`, `AgentCostBudgetExceededError`. (HPOSpaceUnboundedError exists locally but is not in the canonical taxonomy.)
- **Current behaviour:** The canonical engine raises `ValueError` (for InvalidConfig-class scenarios), `BudgetExceeded` (cost overruns), `PromotionRequiresApprovalError` (approval gate). Trial failures wrap into `TrialRecord(status="failed", error=...)` instead of raising `TrialFailureError`. There is no `MissingExtraError` raised for missing optional extras (caller is expected to handle).
- **Deferral rationale:** Adding the missing six is straightforward but must be done deliberately — each new error class is a public-API commitment, and the v1 spec's `ContextLostError` only makes sense alongside D-executor.
- **Sketch:** Add five typed exceptions to `kailash.ml.errors`: `TrialFailureError(AutoMLError)`, `MissingExtraError(MLError)`, `ContextLostError(AutoMLError)`, `InvalidConfigError(AutoMLError, ValueError)`, `AgentCostBudgetExceededError(AutoMLError, BudgetExhaustedError)`. Promote `HPOSpaceUnboundedError` from `automl/strategies/grid.py` to `kailash.ml.errors` and re-export from the local module for backwards compatibility. Replace `ValueError` raises in `AutoMLConfig.__post_init__` with `InvalidConfigError`. Re-export all from `kailash_ml.errors`.

### D-trackerwiring. Constructor `tracker=` Kwarg + Ambient `km.track()`

- **v1 spec citation:** § 2.3 MUST 1 — `AutoMLEngine.__init__` accepts `tracker: Optional[ExperimentRun] = None` and auto-wires to `kailash_ml.tracking.get_current_run()` when `None`. Emits WARN when no tracker is bound.
- **Current behaviour:** `AutoMLEngine.__init__` does NOT accept `tracker=`. There is no auto-wire to `kailash_ml.tracking.get_current_run()`. There is no WARN line "no tracker bound; trial history will not be recoverable" — the audit row goes to `_kml_automl_trials` directly via `connection`, decoupled from the tracking system.
- **Deferral rationale:** Trial-as-nested-run discipline is a separate concern from trial-audit-row persistence. The v1 spec's design coupled them; the canonical implementation chose to keep them independent (tracker for `MLEngine.compare/fit`; audit table for `AutoMLEngine.run`).
- **Sketch:** Either (a) reconcile by adding `tracker=` to `AutoMLEngine.__init__` and emitting nested-run children inside `_record_trial`, OR (b) document the decoupling explicitly and provide a helper `tracker.attach(automl_engine)` that subscribes to trial events. Option (b) is the cleaner architecture; option (a) is the v1-spec-aligned path.

### D-earlystopping. `early_stopping_patience` Field

- **v1 spec citation:** § 3.1 — `MLEngine.fit_auto(... early_stopping_patience: int = 10 ...)`; § 4.2 MUST 3 — sweep-level early stopping when no improvement over N trials.
- **Current behaviour:** `AutoMLConfig` has no `early_stopping_patience` field. Sweep-level early stopping is the strategy's `should_stop(history)` responsibility; no patience mechanism is bundled into `AutoMLEngine`.
- **Deferral rationale:** A patience mechanism is genuinely useful but adds non-trivial state (best-so-far tracking, generation counter). Until D-fitauto, it has no high-level entry point to enforce.
- **Sketch:** Add `early_stopping_patience: int = 0` (0 = disabled) to `AutoMLConfig`. In `run()`, after each completed trial, track `trials_since_best_improved` and break with `early_stopped_reason="no_improvement"` when ≥ patience.

---

_End of ml-automl-v2-draft.md_
