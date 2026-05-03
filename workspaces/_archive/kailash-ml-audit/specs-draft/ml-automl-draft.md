# Kailash ML AutoML & Hyperparameter Search Specification (v1.0 Draft)

Version: 1.0.0 (draft)
Package: `kailash-ml`
Parent domain: ML Lifecycle (see `ml-engines-v2-draft.md` for `MLEngine.compare` / `.fit`; `ml-tracking-draft.md` for run hierarchy; `ml-feature-store-draft.md` for data retrieval)
License: Apache-2.0
Python: >=3.11
Owner: Terrene Foundation (Singapore CLG)

Status: DRAFT at `workspaces/kailash-ml-audit/specs-draft/ml-automl-draft.md`. Becomes `specs/ml-automl.md` after human review. Supersedes the AutoML/HPO sections of `ml-engines.md v0.9.x`.

Origin: Round-1 MLOps audit `workspaces/kailash-ml-audit/04-validate/round-1-mlops-production.md` HIGH "AutoMLEngine cannot distribute trials — serial only" + round-1 industry audit H-5 "No autolog()" M-1 "No sweeps / HPO UI" + round-1 SYNTHESIS T2 "0/18 engines auto-wire to km.track()". Closes three round-1 HIGHs by specifying: agent-augmented AutoML, distributed HPO, nested-run tracker wiring.

---

## 1. Scope

### 1.1 In Scope

This spec is authoritative for three cooperating primitives, all exposed through `MLEngine`:

- **AutoMLEngine** — picks a model family AND hyperparameters jointly given data + a time budget; emits a leaderboard.
- **HyperparameterSearch (HPO)** — searches a fixed family's hyperparameter space; standalone OR called by AutoMLEngine.
- **Ensemble** — composes the top-N leaderboard entries into a single meta-model (weighted vote / stacking / bagging / boosting).

The spec owns:

1. Construction of each primitive (tenant-aware, tracker-aware, quota-aware).
2. The `fit_auto()` entry point on `MLEngine` and the `engine.compare()` delegation.
3. Trial-as-nested-run discipline with ambient tracker propagation.
4. Distributed execution via `parallel_trials=N` (local) and `executor=` (Ray / Dask).
5. Early-stopping, population-based training, and budget semantics.
6. LLM-augmented AutoML: the Kaizen agent recommending the next trial (a kailash-ml uniqueness).
7. Error taxonomy and test contract.

### 1.2 Out of Scope

- **Feature engineering auto-search** — `FeatureEngineer` (under `kailash_ml.primitives`) owns the feature-generation search; AutoML consumes the output.
- **Reward model search for RLHF** — lives in `kailash-align` (RLHF-specific HPO). AutoML here covers supervised families.
- **Neural architecture search (NAS)** — deferred to a future `ml-nas.md`; Lightning NAS integrations are NOT in this spec.
- **AutoML UI / leaderboard rendering** — covered by `MLDashboard`; this spec owns the data model.

---

## 2. Construction

### 2.1 `AutoMLEngine`

```python
from kailash_ml import AutoMLEngine
from kailash_ml.engines.automl_engine import AutoMLConfig

config = AutoMLConfig(
    task_type="classification",   # "classification" | "regression" | "ranking" | "clustering"
    time_budget_seconds=3600,
    metric="roc_auc",
    parallel_trials=4,            # local process pool parallelism
    executor="local",             # "local" | "ray" | "dask"
    max_trials=200,
    early_stopping_patience=10,
    agent=False,                  # opt-in LLM augmentation (requires kailash-ml[agents])
    auto_approve=False,           # human approval gate for agent recommendations
    max_llm_cost_usd=5.0,
)

engine = AutoMLEngine(
    config=config,
    feature_store=fs,
    model_registry=registry,
    trials_store=None,            # None → canonical ~/.kailash_ml/ml.db per ml-tracking §2.2
    tenant_id="acme",
    tracker=tracker,              # Optional[ExperimentRun]; ambient km.track() auto-wires via get_current_run() if None
)
```

Store-URL resolution for the `trials_store=` kwarg routes through `kailash_ml._env.resolve_store_url(explicit=...)` per `ml-engines-v2.md §2.1 MUST 1b` (single shared helper; hand-rolled `os.environ.get(...)` is BLOCKED per `rules/security.md` § Multi-Site Kwarg Plumbing). The `trials_store=None` default delegates the `KAILASH_ML_STORE_URL` / `KAILASH_ML_TRACKER_DB` bridge / `~/.kailash_ml/ml.db` precedence chain to the helper — the same precedence `ExperimentTracker.create()` (see `ml-tracking.md §2.5`) uses — so `AutoMLEngine`'s trial history and the ambient `km.track()` parent run land in the same physical store without a separate resolution path.

### 2.2 `HyperparameterSearch`

Standalone HPO over a fixed family/Trainable factory:

```python
from kailash_ml import HyperparameterSearch

hpo = HyperparameterSearch(
    trainable_factory=LightGBMTrainable,
    space=HyperparameterSpace(
        params=[
            IntParam("n_estimators", low=100, high=1500),
            FloatParam("learning_rate", low=1e-3, high=0.3, log=True),
            IntParam("max_depth", low=3, high=16),
        ],
    ),
    algorithm="bohb",             # "grid" | "random" | "bayesian" | "bohb" | "cmaes" | "halving"
    metric="roc_auc",
    mode="maximize",
    max_trials=100,
    parallel_trials=4,
    tenant_id="acme",
    tracker=tracker,
)
report = await hpo.search(train_df, target="churned")
```

### 2.3 MUST Rules

#### 1. Constructor Accepts Optional `tracker=`; Auto-Wires To Ambient `km.track()`

Both `AutoMLEngine` and `HyperparameterSearch` MUST accept `tracker: Optional[ExperimentRun] = None` (HIGH-8 — the user-visible async-context handle, NOT `Optional[ExperimentTracker]`). When `None`, the constructor MUST call `kailash_ml.tracking.get_current_run()` (the public accessor per `ml-tracking §10.1` — CRIT-4) to read the ambient run. If neither is present, the primitive operates without tracker (a plain algorithmic run) — but MUST log a WARN line stating "no tracker bound; trial history will not be recoverable". Direct access to `kailash_ml.tracking.runner._current_run` is BLOCKED for library callers.

```python
# DO — constructor reads ambient
async with km.track("automl-sweep") as parent:
    automl = AutoMLEngine(config=cfg, ...)  # tracker = parent implicitly
    await automl.run(schema=schema, data=df)

# DO — explicit tracker (overrides ambient)
explicit = MyMlflowTracker(...)
automl = AutoMLEngine(config=cfg, tracker=explicit)

# DO NOT — silent no-tracker without warning
automl = AutoMLEngine(config=cfg)  # outside any km.track() — must WARN
```

**Why:** Round-1 audit found 0/18 engines auto-wire to `km.track()`. Ambient-contextvar resolution makes the 5-line newbie scenario ("enter `km.track()`, let AutoML log every trial as a child") work without manual threading, while still allowing explicit injection for advanced users.

#### 2. Financial Field Validation

`AutoMLConfig.max_llm_cost_usd`, `time_budget_seconds`, and every numeric budget MUST be validated via `math.isfinite()` at construction. `NaN` and `Inf` are rejected with `InvalidConfigError`. Negative budgets raise. Violations of this are a `rules/zero-tolerance.md` Rule 2 stub — unbounded budgets defeat cost guards.

#### 3. Agent Mode Is Double Opt-In

`agent=True` MUST require BOTH:

1. The kwarg is explicitly set by the caller (default `agent=False`).
2. The optional extra `kailash-ml[agents]` is installed (providing `kailash_kaizen`); otherwise construction raises `MissingExtraError("kailash-ml[agents] required for agent=True")`.

**Why:** LLM calls have cost. A silent default of `agent=True` would run up API bills in users' CI without consent.

---

## 3. `MLEngine.fit_auto()` — The Canonical Entry Point

### 3.1 Signature

```python
# on MLEngine
async def fit_auto(
    self,
    data: pl.DataFrame | pl.LazyFrame,
    *,
    task: str = "auto",                     # "auto" | "classification" | "regression"
    target: str,
    time_budget: int = 3600,
    metric: str | None = None,              # None => primary metric per task_type
    families: list[str] | None = None,      # None => sensible default set
    parallel_trials: int = 4,
    executor: str = "local",                # "local" | "ray" | "dask"
    max_trials: int = 200,
    early_stopping_patience: int = 10,
    agent: bool = False,
    ensemble: bool = True,                  # build an ensemble from the top-k
    top_k: int = 3,
    seed: int = 42,
) -> LeaderboardReport: ...
```

### 3.2 `LeaderboardReport`

```python
@dataclass(frozen=True)
class LeaderboardEntry:
    rank: int
    family: str
    hyperparameters: dict
    metrics: dict[str, float]
    tracker_run_id: str                  # nested run under the AutoML parent
    feature_versions: dict[str, str]
    elapsed_seconds: float
    trial_number: int

@dataclass(frozen=True)
class LeaderboardReport:
    parent_run_id: str
    task_type: str
    primary_metric: str
    entries: list[LeaderboardEntry]       # sorted by primary_metric, best first
    ensemble_result: TrainingResult | None  # present when ensemble=True
    total_trials: int
    total_budget_seconds_used: float
    early_stopped: bool
    tenant_id: str | None
```

### 3.3 MUST Rules

#### 1. Every Trial Is A Nested Run

Every trial MUST be logged as a nested run under the AutoML parent run. The parent run holds the leaderboard; each child holds the trial's params, metrics, and artifacts.

```python
# DO — nested-run discipline
async with km.track("automl-churn") as parent:
    automl_report = await engine.fit_auto(df, target="churned", time_budget=1800)
    # Under the hood:
    #   For each trial:
    #     async with km.track("trial", parent_run_id=parent.run_id) as child:
    #         await child.log_params(trial_hp)
    #         await child.log_metrics({"roc_auc": 0.83, ...})

# DO NOT — flat runs with no parent
# Every trial as its own top-level run — leaderboard is orphaned from the parent
```

**Why:** Per `ml-tracking-draft.md`, nested runs are the standard MLflow-parity model. The AutoML UI renders the parent as a collapsible leaderboard; flat runs destroy that hierarchy.

#### 2. Primary Metric MUST Be Deterministic Per Task Type

When `metric=None`, the primary metric MUST be resolved deterministically:

| task               | default metric                                    |
| ------------------ | ------------------------------------------------- |
| `"classification"` | `"roc_auc"` (binary) or `"f1_macro"` (multiclass) |
| `"regression"`     | `"neg_root_mean_squared_error"`                   |
| `"ranking"`        | `"ndcg"`                                          |
| `"clustering"`     | `"silhouette"`                                    |

The resolved metric MUST be captured on `LeaderboardReport.primary_metric` so downstream consumers never need to re-derive it.

#### 3. Ensemble Build Is Opt-Out, Not Opt-In

`ensemble=True` is the default. After the sweep completes, `MLEngine` MUST call `Ensemble.from_leaderboard(report, k=top_k)` and populate `LeaderboardReport.ensemble_result`. Setting `ensemble=False` skips it.

**Why:** A bare leaderboard is research output; the user still has to pick one. Ensembling top-k is what MLflow AutoML, FLAML, H2O AutoML, and AutoGluon all do by default. Matching that default aligns kailash-ml with the industry baseline.

#### 4. Time Budget Is A Hard Cap

`time_budget` seconds is a hard deadline. Active trials are cooperatively terminated when the budget expires. Trials in progress at deadline are allowed to finish their current epoch (via Lightning callback) but no new trial starts. Violation raises `BudgetExhaustedError` from `fit_auto()` even if `max_trials` not reached.

---

## 4. Standalone HPO — `HyperparameterSearch.search()`

### 4.1 Search Algorithms

Each algorithm MUST be a concrete class implementing `HPOAlgorithm`:

- `GridSearchAlgorithm` — exhaustive over discrete params; raises if space is unbounded.
- `RandomSearchAlgorithm` — uniform / log-uniform per param spec.
- `BayesianSearchAlgorithm` — GP + expected-improvement acquisition (via `scikit-optimize`).
- `BOHBAlgorithm` — Bayesian + hyperband; strong for neural nets. REQUIRES `fidelity_param`, `min_fidelity`, `max_fidelity`, `reduction_factor` (see §4.2 MUST 4).
- `CMAESAlgorithm` — evolutionary; good for non-separable continuous spaces.
- `SuccessiveHalvingAlgorithm` — prune the worst half every round.
- `ASHAAlgorithm` — Asynchronous Successive Halving; the default for `parallel_trials > 1` (see §4.2 MUST 5).

### 4.2 MUST Rules

#### 1. Every Algorithm Implements The Same Protocol

```python
@runtime_checkable
class HPOAlgorithm(Protocol):
    def suggest(self, history: list[Trial]) -> dict: ...
    def observe(self, trial: Trial, result: TrainingResult) -> None: ...
    def should_stop(self, history: list[Trial]) -> bool: ...
```

Swapping `algorithm="random"` for `algorithm="bayesian"` MUST NOT require any other code change in the caller.

**Why:** A protocol-based plugin surface matches `ml-tracking-draft.md`'s contract discipline and makes adding a new algorithm (e.g. population-based training) a one-class addition rather than a branch in every call site.

#### 2. Population-Based Training Is A First-Class Variant

PBT-style HPO (trials that mutate their hyperparameters mid-run based on siblings' progress) MUST be available via `algorithm="pbt"`. The Lightning `PopulationBasedTraining` callback integrates via the Trainable's `LightningModule` adapter (see `ml-engines-v2-draft.md §3`).

#### 3. Early Stopping Is Per-Trial AND Population-Level

A trial MUST be stopped early if its rolling validation metric fails to improve by `min_delta` over `patience` epochs. The sweep as a whole MUST stop if no improvement over `early_stopping_patience` trials is observed on the best-so-far primary metric.

#### 4. BOHB Multi-Fidelity Contract

`algorithm="bohb"` REQUIRES four additional kwargs; omitting any raises `BOHBConfigError` at `search()` time:

```python
search = HyperparameterSearch(
    algorithm="bohb",
    fidelity_param="epochs",          # the HP that scales cost (neural net) or sample count (classical)
    fidelity_min=1.0,                  # smallest fidelity tried (e.g. 1 epoch)
    fidelity_max=81.0,                 # largest fidelity tried (e.g. 81 epochs)
    reduction_factor=3,                # successive-halving ratio (default 3; η in the BOHB paper)
)
```

Sane defaults per task type:

| Task type                                  | `fidelity_param`     | `min` | `max`  | `reduction_factor` |
| ------------------------------------------ | -------------------- | ----- | ------ | ------------------ |
| `deep_learning`                            | `"epochs"`           | 1     | 81     | 3                  |
| `classical_classification` / `_regression` | `"training_samples"` | 1000  | 100000 | 3                  |
| `time_series`                              | `"n_bootstraps"`     | 10    | 1000   | 3                  |

**Why:** Without a fidelity parameter, BOHB degenerates to Random + Hyperband promotion that isn't guided by Bayesian updates — 2-3× slower than well-configured Bayesian. The four-kwarg requirement forces users to think about what "cheap" vs "expensive" means for their task.

#### 5. ASHA — Fidelity-Aware Promotion

When `parallel_trials > 1`, the default promotion rule MUST be Async Successive Halving: trials are compared AT THE SAME fidelity rung, not across different fidelity tiers. A leaderboard entry `LeaderboardEntry` MUST carry `fidelity: float` and a `rung: int` (the halving rung where the entry was evaluated). Promotion is admitted only when N trials at the same rung complete.

```python
# DO — fidelity-aware comparison
if len(entries_at_rung(rung=2)) >= min_samples_per_rung:
    best_at_rung = max(entries_at_rung(rung=2), key=attr("metric"))
    if best_at_rung.metric > current_best_next_rung:
        promote(best_at_rung)

# DO NOT — comparing across rungs
best_any = max(all_entries, key=attr("metric"))   # trial-A at fidelity=81 vs trial-B at fidelity=3 — invalid
```

**MUST**: Cross-trial early-stopping rules (patience) apply only within a single rung. A 4-trial sweep where A runs at fidelity=81 while B/C/D run at fidelity=3 MUST NOT use A's score to early-stop B/C/D; they must first be promoted to A's fidelity.

**Why:** A trial at higher fidelity has a mechanical advantage (more training budget); comparing its score to low-fidelity trials promotes by budget, not by hyperparameter quality. The ASHA-paper promotion rule is the structural correctness contract.

---

## 5. Parallel / Distributed Execution

### 5.1 Local Parallelism (`executor="local"`)

Default. Uses a `ProcessPoolExecutor` sized to `parallel_trials`. Trials share the same offline feature store connection pool but run training in independent processes for GPU isolation.

### 5.2 Ray Executor (`executor="ray"`)

Requires optional extra `kailash-ml[ray]` (`ray[tune]>=2.10`). Trials run as Ray actors; the AutoML driver consumes Tune's result stream and logs each completed trial to the shared tracker.

```python
result = await engine.fit_auto(
    df,
    target="churned",
    time_budget=7200,
    parallel_trials=32,
    executor="ray",   # requires Ray cluster
)
```

### 5.3 Dask Executor (`executor="dask"`)

Requires optional extra `kailash-ml[dask]`. Similar to Ray but uses a Dask cluster for scheduling.

### 5.4 MUST Rules

#### 1. Executor Is Pluggable; Default Is Deterministic Local

`executor="local"` is the default. Selecting `"ray"` or `"dask"` without the optional extra installed MUST raise `MissingExtraError("kailash-ml[ray] required for executor='ray'")` at `fit_auto()` time, not later.

#### 2. Distributed Trials Propagate `tenant_id` + `parent_run_id`

Every dispatched trial MUST carry the parent's `tenant_id` and the AutoML parent's `run_id`. Trials that lose this context (e.g. a Ray actor constructed without the parent env) MUST raise `ContextLostError` rather than silently logging under the wrong tenant.

**Why:** Distributed execution is the #1 place tenant isolation breaks — workers pick up a default tenant instead of the caller's. Explicit propagation + loud failure on context loss is the structural defense per `rules/tenant-isolation.md` Rule 2.

#### 3. Ray / Dask Are Not Required For Correctness

A single-machine `parallel_trials=4` local run MUST produce identical results (within seed-determined variance) to a `parallel_trials=4` Ray run on one node. Divergence indicates executor bugs and is a regression blocker.

---

## 6. Early Stopping & Budget

See §3.3 MUST 4 (time budget) + §4.2 MUST 3 (early stopping per trial + population).

### 6.1 MUST Rules

#### 1. `BudgetExhaustedError` Is Non-Fatal

When `time_budget` expires, `fit_auto()` MUST return a `LeaderboardReport` with the completed trials and `early_stopped=True`, NOT raise. A separate `early_stopped_reason` field documents the cause.

**Why:** Users want partial leaderboards when the budget expires — research scenarios often "time-box" and accept the best-so-far. An exception discards useful state.

#### 2. Insufficient Trials Is An Error

If fewer than `min_trials=5` trials complete within the budget, `fit_auto()` MUST raise `InsufficientTrialsError(completed=N, min_required=5)`. A leaderboard of 1 entry is not a leaderboard.

---

## 7. Ensemble Composition

### 7.1 `Ensemble.from_leaderboard()`

```python
from kailash_ml import Ensemble

ensemble = Ensemble.from_leaderboard(
    report=leaderboard_report,
    method="stacking",        # "weighted_vote" | "stacking" | "bagging" | "boosting"
    k=5,                      # top-k to combine
    meta_learner="logistic",  # only for stacking
)
result = await ensemble.fit(train_df, target="churned")  # returns TrainingResult
```

### 7.2 MUST Rules

#### 1. Ensemble Trains As A Single `TrainingResult`

An ensemble fit MUST return a standard `TrainingResult` (per `ml-engines-v2-draft.md §4`) with:

- `model_uri` pointing to a registry entry of the stacked model;
- `metrics` measured on the holdout set after the meta-learner is fit;
- `feature_versions` aggregating all child groups;
- a new audit field `base_models: list[str]` enumerating child model_uris.

**Why:** The Engine's `register()` / `serve()` must be able to treat an ensemble like any other trained model. Divergent result types would fork the registration path.

#### 2. Ensemble Build Failures Surface As `EnsembleFailureError`

If the meta-learner fails to fit (singular stacking matrix, dimensional mismatch), `Ensemble.fit()` MUST raise `EnsembleFailureError(method=, cause=, child_uris=)`. A silent fallback to the best-single-model is BLOCKED.

---

## 8. LLM-Augmented AutoML (Kailash-Unique)

### 8.1 Purpose

When `agent=True` and `kailash-ml[agents]` is installed, a Kaizen agent proposes the next hyperparameter configuration to try. This is a genuine product differentiator against FLAML / AutoGluon / H2O (none of which have LLM-driven suggestion).

### 8.2 Operation

```python
report = await engine.fit_auto(
    df,
    target="churned",
    time_budget=3600,
    agent=True,
    agent_config={
        "model": "claude-opus-4",
        "max_llm_cost_usd": 5.0,
        "auto_approve": False,   # human confirms each recommendation
    },
)
```

### 8.3 MUST Rules

#### 1. Baseline Runs In Parallel With Agent

When `agent=True`, a baseline pure-algorithmic search (Bayesian / BOHB) MUST run alongside the agent's suggestions. Both streams write trials to the same leaderboard. The final report MUST tag each trial with `source="agent" | "baseline"`.

**Why:** Without a baseline the user can't tell whether the agent helped or hurt. The baseline is cheap to run (it's trials that would have happened anyway), and it provides the counterfactual needed for fair evaluation.

#### 2. Cost Budget Is A Hard Cap — TOKEN-LEVEL Backpressure

`max_llm_cost_usd` MUST be enforced with TOKEN-LEVEL backpressure, NOT wall-clock OR post-hoc cost sum. The Kaizen signature used by the agent MUST set `max_prompt_tokens` and `max_completion_tokens` per call such that `(prompt_tokens + completion_tokens) × model_cost_per_token <= (remaining_budget_usd / safety_margin)` with `safety_margin = 1.2`.

```python
# DO — token-level cap per call
remaining = config.max_llm_cost_usd - cumulative_cost_usd
max_tokens_this_call = int(remaining / (model_cost_per_token * 1.2))
max_prompt_tokens = min(config.max_prompt_tokens, max_tokens_this_call * 0.75)
max_completion_tokens = min(config.max_completion_tokens, max_tokens_this_call * 0.25)

# DO NOT — post-hoc cap after overrun
if cumulative_cost_usd >= max_llm_cost_usd:
    suspend_agent()  # the call that pushed us over already ran — $4.99 → $7.50 in one call
```

#### 2a. Required Agent-Config Kwargs

```python
agent_config = {
    "model": "claude-opus-4",
    "max_llm_cost_usd": 5.0,
    "max_prompt_tokens": 8000,         # MUST be set
    "max_completion_tokens": 2000,     # MUST be set
    "auto_approve": False,
    "min_confidence": 0.6,             # MUST — from AgentGuardrailMixin
}
```

When remaining budget < one call's worth, the agent MUST be suspended, the baseline search continues, and a WARN `automl.agent.budget_exhausted` is emitted.

**Why:** A single agent call under `auto_approve=True` can burn $5 in 30 seconds if the agent retries, expands context, reads its own audit trail, etc. The post-hoc cap fires AFTER the overrun; the token-level pre-cap prevents it.

#### 2b. Cumulative Cost Tracking

Cumulative LLM cost across all suggestions is tracked; when the per-call pre-cap reduces `max_tokens_this_call < 100`, subsequent trials revert to pure baseline (the agent cannot form a useful suggestion under that constraint). The cap MUST be reported in `LeaderboardReport.agent_cost_usd`.

#### 3. Audit Trail Per `rules/event-payload-classification.md`

Every agent decision (suggested HP, reasoning, cost) MUST be persisted to `_kml_automl_agent_audit` with `(tenant_id, actor_id, parent_run_id, trial_number, suggested_hp, llm_cost_microdollars, model, prompt_hash)`. PII-classified prompts are hashed, not raw-stored.

#### 4. Approval Gate Default Is Human-In-Loop

`auto_approve=False` is the default. The agent's suggestion is shown to a human reviewer (via Nexus / CLI) before the trial runs. Only when `auto_approve=True` does the agent run unattended. This matches `rules/autonomous-execution.md` "Human-on-the-Loop, not in-the-loop" for cost-bearing actions.

---

## 8A. Schema DDL (AutoML Agent Audit)

Resolves Round-3 HIGH B15: the DDL block for `_kml_automl_agent_audit` the spec references in §8.3 MUST Rule 3 but did not define. Carries `tenant_id` per `rules/tenant-isolation.md` MUST Rule 5 and `actor_id` per `rules/event-payload-classification.md`.

### 8A.1 Identifier Discipline

The `_kml_` table prefix (leading underscore marks these as internal tables users should not query directly) MUST be validated in the caller's `__init__` against the regex `^[a-zA-Z_][a-zA-Z0-9_]*$` per `rules/dataflow-identifier-safety.md` MUST Rule 2. Any dynamic identifier injected into DDL MUST route through `kailash.db.dialect.quote_identifier()` per `rules/dataflow-identifier-safety.md` MUST Rule 1. Table-name + prefix total length stays within the Postgres 63-char limit (Decision 2 approved).

### 8A.2 Postgres DDL

```sql
-- _kml_automl_agent_audit
CREATE TABLE _kml_automl_agent_audit (
  id BIGSERIAL PRIMARY KEY,
  tenant_id VARCHAR(255) NOT NULL,
  automl_run_id UUID NOT NULL,  -- FK to the parent tracker run
  trial_number INTEGER NOT NULL,
  agent_kind VARCHAR(64) NOT NULL,  -- 'llm_suggester' | 'baseline'
  agent_model_id VARCHAR(255),
  actor_id VARCHAR(255) NOT NULL,
  pact_decision VARCHAR(16) NOT NULL,  -- 'admit' | 'reject' per PACT admission
  pact_reason TEXT,
  proposed_config JSONB NOT NULL,
  budget_microdollars BIGINT NOT NULL,
  actual_microdollars BIGINT,
  outcome VARCHAR(16),  -- {FINISHED, FAILED, KILLED, PENDING} — Decision 1 status vocab
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_automl_agent_tenant_run ON _kml_automl_agent_audit(tenant_id, automl_run_id, trial_number);
```

### 8A.3 SQLite-Compatible Variant

SQLite does not support `BIGSERIAL`, `UUID`, `JSONB`, `TIMESTAMPTZ`, or `BIGINT` as distinct types. The SQLite subset MUST substitute:

- `BIGSERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`
- `UUID` → `TEXT` (canonical 36-char hyphenated string; caller generates via `uuid.uuid4()`)
- `JSONB` → `TEXT` (JSON-serialized string; caller `json.dumps()` / `json.loads()`)
- `TIMESTAMPTZ` → `TEXT` (ISO-8601 UTC string; caller normalizes to UTC before write)
- `BIGINT` → `INTEGER`
- `DEFAULT NOW()` → omitted; caller supplies ISO-8601 UTC string at insert

### 8A.4 Tier-2 Schema-Migration Test

- `test__kml_automl_agent_audit_schema_migration.py` — applies §8A.2 + §8A.3 DDL to a fresh Postgres (via `ConnectionManager`) AND a fresh SQLite (`:memory:`); asserts `pragma_table_info` / `information_schema.columns` match the declared shape; asserts `pact_decision` round-trips both `'admit'` and `'reject'`; asserts `outcome` accepts the Decision 1 status vocab `{FINISHED, FAILED, KILLED, PENDING}` and rejects `'INVALID'` when a CHECK constraint is registered; asserts the composite index `idx_automl_agent_tenant_run` is created; asserts `quote_identifier()` is the only path used to interpolate the table name in test fixtures per `rules/dataflow-identifier-safety.md` Rule 5.

---

## 9. Industry Parity

| Capability                      | kailash-ml 1.0.0 | FLAML | AutoGluon | H2O AutoML | Ray Tune  | Optuna     | Katib   | SageMaker HPO |
| ------------------------------- | ---------------- | ----- | --------- | ---------- | --------- | ---------- | ------- | ------------- |
| Time-budget + leaderboard       | Y                | Y     | Y         | Y          | Y\*       | Y\*        | Y       | Y             |
| Nested-run tracker wiring       | Y (km.track)     | P     | P         | P          | Y (TB/WB) | Y (MLflow) | Y       | Y             |
| Parallel trials (local)         | Y                | Y     | Y         | Y          | Y         | Y          | Y       | Y             |
| Distributed executor (Ray/Dask) | Y (plug-in)      | Y     | Y         | N          | Y (core)  | Y          | Y (K8s) | Y             |
| Bayesian HPO                    | Y                | Y     | Y         | Y          | Y         | Y          | Y       | Y             |
| BOHB / Hyperband                | Y                | Y     | Y         | N          | Y         | Y          | Y       | Y             |
| CMA-ES                          | Y                | N     | N         | N          | Y         | Y          | N       | N             |
| Population-based training       | Y                | N     | N         | N          | Y         | N          | N       | N             |
| Ensemble build from leaderboard | Y (default)      | Y     | Y         | Y          | N         | N          | N       | Y             |
| Stacking meta-learner           | Y                | Y     | Y         | Y          | N         | N          | N       | Y             |
| Polars-native data input        | Y                | N     | N         | N          | N         | N          | N       | N             |
| Multi-tenant keyspace           | Y                | N     | N         | N          | N         | N          | Y (K8s) | Y (IAM)       |
| **LLM-augmented suggestions**   | **Y (unique)**   | N     | N         | N          | N         | N          | N       | N             |
| PACT-governed trial admission   | Y (via `pact`)   | N     | N         | N          | N         | N          | N       | N             |

**Position:** Parity with FLAML/AutoGluon/H2O on classical AutoML; ahead on (a) polars-native perf, (b) tenant isolation by construction, (c) LLM-augmented suggestion as a first-class option, (d) PACT governance over admission. The LLM-augmentation + baseline-counterfactual design is the category-defining delta.

---

## 10. Error Taxonomy

Every AutoML / HPO / Ensemble error MUST be a typed exception under `kailash_ml.errors` (AutoMLError family per `ml-tracking-draft.md §9.1`). Cross-cutting errors (`UnsupportedTrainerError` per Decision 8, `MultiTenantOpError` per Decision 12, `ParamValueError` for HPO param-space validation) sit at the `MLError` root or `TrackingError` family and are re-exported from `kailash_ml.errors`.

| Exception                      | When raised                                                                                                                                                                                                                                                                                                                           |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `BudgetExhaustedError`         | Wall-clock budget expired before user-requested `max_trials` reached (WARN, not fatal).                                                                                                                                                                                                                                               |
| `InsufficientTrialsError`      | Fewer than `min_trials=5` trials completed — leaderboard not meaningful.                                                                                                                                                                                                                                                              |
| `EnsembleFailureError`         | Meta-learner failed; child_uris + cause included.                                                                                                                                                                                                                                                                                     |
| `TrialFailureError`            | A single trial raised uncaught; wrapped with parent context.                                                                                                                                                                                                                                                                          |
| `MissingExtraError`            | `executor="ray"` / `agent=True` without the optional extra installed.                                                                                                                                                                                                                                                                 |
| `ContextLostError`             | Distributed worker launched without parent `tenant_id` / `parent_run_id`.                                                                                                                                                                                                                                                             |
| `InvalidConfigError`           | Non-finite budget, negative trial count, unknown algorithm name.                                                                                                                                                                                                                                                                      |
| `HPOSpaceUnboundedError`       | `algorithm="grid"` invoked with an unbounded param space.                                                                                                                                                                                                                                                                             |
| `AgentCostBudgetExceededError` | Cumulative LLM cost ≥ `max_llm_cost_usd`; subsequent trials revert to baseline.                                                                                                                                                                                                                                                       |
| `ParamValueError`              | (cross-cutting, TrackingError family) HPO proposal contained a numeric hyperparameter with NaN or ±Inf — sampled point fails `math.isfinite()`. Re-exported from `kailash_ml.errors`. Multi-inherits `ValueError` so `except ValueError` continues to catch. See `ml-engines-v2-draft.md §3.2 MUST 3a` + `ml-tracking-draft.md §9.1`. |
| `UnsupportedTrainerError`      | (cross-cutting, direct MLError child) A trial's Trainable bypasses `L.Trainer` during AutoML dispatch (Decision 8). Re-exported from `kailash_ml.errors`. See `ml-engines-v2-draft.md §3.2 MUST 2`.                                                                                                                                   |

---

## 11. Test Contract

### 11.1 Tier 1 (Unit)

- `test_leaderboard_rank_ordering` — entries sorted by primary metric.
- `test_hpo_algorithm_random_suggest_determinism` — same seed → same suggestions.
- `test_hpo_algorithm_bayesian_observes_history` — `observe()` updates the GP.
- `test_hpo_algorithm_bohb_halving` — trials prune at correct budget levels.
- `test_ensemble_from_leaderboard_respects_k` — top-k selection is correct.
- `test_automl_config_budget_non_finite_rejected` — `time_budget=float('inf')` raises.
- `test_automl_config_llm_cost_nan_rejected` — `max_llm_cost_usd=nan` raises.
- One test per error taxonomy entry.

### 11.2 Tier 2 (Integration)

- `test_automl_ray_executor_wiring.py` — **only when `[ray]` installed**: `executor="ray"` runs 8 trials on a local Ray cluster; tracker captures each as nested run.
- `test_automl_dask_executor_wiring.py` — **only when `[dask]` installed**.
- `test_automl_nested_run_tracking.py` — real SQLite tracker; `fit_auto(df, ...)` produces N+1 runs (1 parent + N trials); `tracker.list_runs(parent_id=...)` returns N children.
- `test_automl_tenant_propagation.py` — distributed trials inherit `tenant_id="acme"`; cross-tenant audit query returns only acme's trials.
- `test_automl_budget_hard_cap.py` — `time_budget=5` returns a report before wall-clock exceeds 10s; `early_stopped=True`.
- `test_automl_ensemble_default_on.py` — no `ensemble=` kwarg → report.ensemble_result is not None.
- `test_hpo_search_polars_native.py` — search against a polars DataFrame, no pandas conversion happens internally.
- `test_automl_agent_mode_double_optin.py` — `agent=True` without `[agents]` extra raises `MissingExtraError`.
- `test_automl_agent_baseline_parallel.py` — `agent=True` with fake LLM → report contains both `source="agent"` and `source="baseline"` trials.
- `test_automl_agent_cost_cap.py` — `max_llm_cost_usd=0.01` with expensive fake LLM → audit row records cap hit; trials continue via baseline.

### 11.3 Tier 3 (E2E via `MLEngine`)

- `test_mlengine_fit_auto_churn_e2e.py` — `engine.fit_auto(df, target="churned", time_budget=120)` produces leaderboard; best entry's `tracker_run_id` points to a real run; `engine.register(result.entries[0])` succeeds.

---

## 12. Cross-References

- `ml-engines-v2-draft.md §2.1 MUST 5` — the eight-method Engine surface; `fit_auto` is a convenience on top of `compare() → finalize()`.
- `ml-engines-v2-draft.md §5` — tenant propagation; every AutoML trial inherits the Engine's `tenant_id`.
- `ml-tracking-draft.md` — nested-run semantics; `log_metric`, `log_params` on child runs.
- `ml-feature-store-draft.md` — AutoML consumes feature groups as candidate inputs; every trial logs `feature_versions`.
- `rules/tenant-isolation.md` — MUST Rules 1-5; every storage key and audit row tenant-scoped.
- `rules/autonomous-execution.md` — "Human-on-the-Loop" shapes the agent-mode approval gate.
- `rules/event-payload-classification.md` — agent audit rows hash PII prompts.
- `rules/zero-tolerance.md` Rule 2 — non-finite budgets treated as stubs and blocked.
- `kailash-pact` — `PACT.GovernanceEngine.check_trial_admission()` consulted before every trial when `pact_enforcement=True`; a trial that exceeds a PACT dimension (cost, latency, fairness) is skipped before spin-up.

---

## 13. Conformance Checklist

- [ ] `AutoMLEngine` constructor accepts `tracker=None` and reads ambient `km.track()` context.
- [ ] `HyperparameterSearch` constructor signature matches §2.2.
- [ ] `fit_auto()` returns `LeaderboardReport` with both parent + nested trial runs logged.
- [ ] Primary metric resolution is deterministic per §3.3 MUST 2.
- [ ] `ensemble=True` is the default; `ensemble_result` populated for non-empty leaderboards.
- [ ] `time_budget` is a hard cap; deadline-hit returns report with `early_stopped=True`.
- [ ] `executor="ray"` / `"dask"` raise `MissingExtraError` if extra not installed.
- [ ] Distributed trials carry `tenant_id` + `parent_run_id`; loss raises `ContextLostError`.
- [ ] `agent=True` is double opt-in; baseline runs in parallel; cost cap is hard.
- [ ] Every error is a typed exception per §10.
- [ ] Tier 2 tests in §11.2 all named and passing.
- [ ] `rg 'NotImplementedError' packages/kailash-ml/src/kailash_ml/engines/automl_engine.py` returns zero matches.
- [ ] `rg 'tenant_id' packages/kailash-ml/src/kailash_ml/engines/automl_engine.py` matches every trial emission.

---

_End of ml-automl-draft.md_
