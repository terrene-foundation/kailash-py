# kailash-ml DX Audit

Scope: `packages/kailash-ml/` v0.9.0. UX principles applied against the
vision "PyCaret-better AutoML + MLflow-better tracking + single coherent
Engine + unified ML/DL/RL". Audit targets API/DX/documentation ergonomics
for data scientists. No frontend exists yet. No source edits performed.

Sources read: `src/kailash_ml/__init__.py`, `README.md` (935 LOC),
`.claude/skills/34-kailash-ml/SKILL.md`, `pyproject.toml`. No `examples/`
directory exists — that is itself a finding (see §4).

---

## 1. First-hour experience (PyCaret/MLflow user lens)

A data scientist who reached for `pip install kailash-ml` expecting
PyCaret's `setup() + compare_models()` or MLflow's `start_run()` fluency
hits the following sequence:

| Step | What the user does | What the user meets | Discovery cost / jargon tax |
|------|--------------------|---------------------|-----------------------------|
| 1 | `pip install kailash-ml` | ~195 MB install (ok) | Fine. |
| 2 | `import kailash_ml as km; km.<TAB>` | 22 symbols, no `train`, no `setup`, no `compare_models`, no `log_metric`, no `load_data`. The verbs PyCaret/MLflow users reach for are absent from the top level. | HIGH. Users expect verbs; they get nouns (Engines, Stores, Registries). |
| 3 | Reach for README Quick Start | 60 lines of setup before a model is trained. Must manually wire `ConnectionManager`, `FeatureStore.initialize()`, `ModelRegistry(..., LocalFileArtifactStore)`, `TrainingPipeline(fs, reg)`, `FeatureSchema(name, features=[FeatureField(...), ...], entity_id_column)`, then finally `pipeline.train(...)`. | HIGH. PyCaret is 3 lines to a trained model. This is 30+. |
| 4 | Encounter `entity_id_column="customer_id"` | No default. No "just pass a DataFrame with a target column" path. Must think about entity identity before training is even possible. | Jargon tax: "entity" is MLOps feature-store vocabulary, not data-science vocabulary. Users of sklearn/PyCaret have no entity. |
| 5 | Encounter `ModelSpec(model_class="sklearn.ensemble.RandomForestClassifier", framework="sklearn", ...)` | Must know the importable class path AND restate framework (redundant — the prefix already tells you). No model-family shorthand (`"rf"`, `"xgb"`, `"lgbm"`). | Parameter fatigue. Errors surface as `ValueError: model class not in allowlist` when users guess. |
| 6 | Try to log a metric | `ExperimentTracker` has its own init path (`.create()` factory OR `__init__(conn)` with `.initialize()` not required "auto-initializes on first use"). MLflow users expect `mlflow.start_run(); mlflow.log_metric(...)`. | HIGH. Two init patterns for one class is the single most-confusing surface in the package. |
| 7 | Try to load a CSV | Discover there is no `km.load_data()`. Must `pl.read_csv()` (polars — many users will instinctively reach for pandas and fail a dtype check). | Jargon tax: README says "polars-native" three times but never says "pandas users: call `from_pandas()` first." |
| 8 | Compare models | `AutoMLEngine.run()` is the path. Takes a `FeatureSchema` not a DataFrame. Returns `result.best_model` + `result.agent_recommendations` — undocumented return type in README. | HIGH. PyCaret's `compare_models()` returns a sorted leaderboard. Here the data structure is opaque. |

**PyCaret-user verdict**: abandon within 10 minutes.
**MLflow-user verdict**: tolerate until `ExperimentTracker` dual-init
confusion, then abandon.

UX principles violated: **Content-First** (chrome — init code — dwarfs
the content, the training call); **Progressive Disclosure** (full
infrastructure exposed before the 3-line hello-world); **Discoverability**
(verbs not on top-level namespace); **Consistency** (two init patterns
for one class).

---

## 2. API surface ergonomics

Audit of the 22 public symbols exported via lazy `__getattr__`:

| Criterion | Score | Evidence |
|-----------|-------|----------|
| **Discoverability** (`km.<TAB>`) | 2/5 | All nouns. No `km.train`, `km.compare`, `km.track`, `km.log_metric`, `km.load`, `km.profile`. IDE tab-complete gives a class inventory, not a task menu. |
| **Parameter sanity** | 2/5 | `FeatureSchema` requires `entity_id_column` — no default. `ModelSpec` requires `model_class` as dotted string AND `framework` — redundant. `TrainingPipeline.__init__` requires BOTH `feature_store=` AND `model_registry=` — can't try a train without instantiating two stateful DB-backed objects. |
| **Coherence — verb tense** | 2/5 | `pipeline.train()` vs `engine.run()` vs `searcher.search()` vs `ensemble.blend()/stack()/bag()/boost()` vs `tracker.log_metric()`. Five different action verbs for "do the ML thing." |
| **Coherence — return types** | 2/5 | `train()` → `TrainingResult` (undocumented shape). `search()` → `SearchResult`. `run()` (AutoML) → different result shape. `blend()/stack()/bag()/boost()` → yet another. No shared `Result` base class documented. |
| **Composition** | 3/5 | FeatureStore → TrainingPipeline → ModelRegistry → InferenceServer chains well. But: HyperparameterSearch takes a `pipeline` constructor arg; AutoMLEngine takes `feature_store` + `model_registry` separately and constructs its own internal pipeline. Two wiring conventions. |
| **Error surfaces** | 2/5 | Init-time errors surface at `await conn.initialize()` / `await fs.initialize()` — multiple initialization steps each with their own failure path. `ModelSpec(model_class="xgboost.XGBClassifier")` silently depends on the xgboost extra (now base) — user can't tell at construction time if the string resolves. |
| **Async everywhere** | 2/5 | Every entry point is `async`. README offers no sync variant. A data scientist in a Jupyter notebook typing `pipeline.train(...)` gets a coroutine back and no result. Requires `await` + `asyncio.run()` scaffolding. PyCaret and MLflow are sync. |

UX principles violated: **Hierarchy Everywhere** (primary action
`train` buried three method calls deep), **Efficient Workflows** (30+
lines for the hello-world), **Consistency** (verb drift, init drift,
result-type drift).

---

## 3. Translated pain points (user's 8 reports)

Each translated to "what the user expected vs what they got" with DX
severity (1=nuisance, 5=abandonment).

| # | User report | Expected vs got | UX failure mode | Severity |
|---|-------------|-----------------|-----------------|----------|
| 1 | Schema hash conflicts on retry | Expected: "my second `fs.ingest(...)` of the same schema is a no-op or a friendly upsert." Got: hash collision error, pipeline halts. | Idempotency violation. Re-running a cell in a notebook is the most common workflow and it must not fail. | 5 |
| 2 | `schema=None` crashes deep in stack | Expected: "a clear `TypeError: schema is required` at the call site." Got: AttributeError 6 frames down. | Input validation missing at the boundary; error surfaces at the wrong layer. | 4 |
| 3 | DB file path fragility | Expected: working dir changes are normal for notebooks — the DB file should follow a known default or resolve absolutely. Got: "database not found" after `cd`. | Configuration leaks implementation detail into user workflow. | 4 |
| 4 | No graceful degradation for missing optional packages | Expected: "if I ask for SHAP explanations without the `[explain]` extra, I get `ImportError: pip install kailash-ml[explain]` at the call site." Got: opaque import stack trace. | Optional dependency UX not surfaced — violates `dependencies.md` "optional extras with loud failure." | 4 |
| 5 | GPU not default | Expected: "XGBoost auto-detects GPU as the README claims." Got: CPU silently used because one of the detect-path dependencies was missing. | The README promise ("auto-detects") is not matched by the runtime. Silent fallback to CPU is a severity-5 surprise for users who paid for a GPU box. | 5 |
| 6 | No package-availability checks | Expected: one `km.doctor()` call reports what's present, what's missing, what each unlocks. Got: discover missing deps one by one via tracebacks. | No onboarding diagnostic. PyCaret's `check_version()` and HuggingFace's `transformers-cli env` are the industry bar. | 3 |
| 7 | Opaque `_detect_target()` | Expected: "if I pass a DataFrame without a schema, the framework tells me which column it picked as target and why." Got: a heuristic runs, picks something, fails later. | Magic without explanation. Principle violated: decisions MUST be observable (see `observability.md`). | 4 |
| 8 | ExperimentTracker needs file-backed SQLite | Expected: "the default tracker just works, like `mlflow.start_run()` with no config." Got: must construct `ConnectionManager("sqlite:///something.db")` + know that `:memory:` loses state across processes. | Zero-config promise broken; persistence ergonomics inferior to MLflow's single filepath default. This is the user's stated preference per `feedback_sqlite_default.md`. | 5 |

Mean severity: 4.25/5. Three of eight are abandonment-triggering.

---

## 4. Documentation audit

**Is there a `pip install kailash-ml` → first-trained-model tutorial?**
The README Quick Start is the closest candidate. It is not a tutorial —
it is a reference assembly of primitives. There is no `docs/` Sphinx
tree specific to kailash-ml in the package directory and no `examples/`
directory (the `Glob` confirmed absence, consistent with what
`pyproject.toml` packages via Hatch: only `src/kailash_ml`).

**Industry bar comparison**:

| Bar | Their opening | kailash-ml opening |
|-----|---------------|--------------------|
| scikit-learn tutorial | "Fit a model to data" in 5 lines | 30+ lines |
| PyCaret Quickstart | `s = setup(data, target=...); best = compare_models()` — 2 lines | ≥30 lines, no `compare_models` equivalent documented |
| HuggingFace course | `pipeline("sentiment-analysis")(text)` — 1 line | no 1-line path exists |
| MLflow | `with mlflow.start_run(): mlflow.log_metric(...)` — 2 lines | dual-init confusion on `ExperimentTracker.create()` vs `ExperimentTracker(conn)` |

**Missing from docs**:
- A "convert from PyCaret" migration page.
- A "convert from MLflow" migration page.
- A `km.doctor()` / environment-diagnostic section.
- An `examples/` directory with runnable `.py` files (critical for data scientists who learn by running).
- Return-type documentation for `TrainingResult`, `SearchResult`, AutoML result, ensemble results.
- A single image of the engine-composition graph (README has ASCII; ASCII does not onboard data scientists).
- Troubleshooting coverage is 6 entries; real bar (scikit-learn, PyCaret) is 30+.

**Wrong in docs**:
- README line 7 says "Version: 0.7.0"; `pyproject.toml` says `0.9.0`. Version-drift violation of `documentation.md` "Version Numbers Must Match pyproject.toml." (1 finding)
- README line 64 imports `ModelRegistry, LocalFileArtifactStore` from `kailash_ml.engines.model_registry`; SKILL.md line 84 imports `LocalFileArtifactStore` from `kailash_ml.engines` (no `.model_registry` suffix). Drift between the two canonical docs.
- README "Installation" says `[full]` extra. SKILL.md line 24 also says `[full]`. `pyproject.toml` defines `[all]` and `[all-gpu]`, not `[full]`. Both docs reference a non-existent extra.

---

## 5. Error message audit

I could not run `grep raise` (the environment's `rg` glob resolution
failed), so I assessed the messages surfaced in README/SKILL.md + the
reported pain points. From these samples:

| Message (or implied) | Actionable? | Names input? | Suggests fix? |
|----------------------|-------------|--------------|---------------|
| "model class not in allowlist" (§3 pain #5) | N | Y | N |
| "database is locked" (README Troubleshooting) | Partial | N | Y ("use ConnectionManager") |
| ONNX export failure → silent (by design) | N | N | Partial |
| `schema=None` crash (§3 pain #2) | N | N | N |
| `GuardrailBudgetExceededError` | Y | Y | Partial |
| "Agent features not available" (README) | Y | N | Y (pip line given) |

Rough pass-rate on the 3-point test: 1 of 6 (GuardrailBudgetExceededError).
The rest fail either actionability or "suggests correct form." This is
far below the bar set by scikit-learn's parameter-validation messages
(which always name the invalid value AND the allowed values).

**UX principle violated**: **Error surfaces** must be actionable at the
call site, not 6 frames down. `observability.md` §1 mandates entry+exit
+error structured log lines; the silent-ONNX-fallback pattern violates
that principle at the API level.

---

## 6. Naming audit

**Against industry** (PyCaret/MLflow/sklearn vocabulary):

| Kailash term | Industry term | Issue |
|--------------|---------------|-------|
| `FeatureSchema` with `entity_id_column` | (none in PyCaret); `feature_store.Entity` in Feast | Forces MLOps-feature-store vocabulary on users who just want to train a model. |
| `TrainingPipeline.train()` | `sklearn.fit()`, `PyCaret.compare_models()` | Fine in isolation; awkward that the "pipeline" is the caller rather than the model. |
| `AutoMLEngine.run()` | `PyCaret.compare_models()` | "run" is a generic verb; gives no hint of the leaderboard output. |
| `ExperimentTracker.create()` AND `ExperimentTracker(conn)` | `mlflow.start_run()` | Two init patterns is unique to kailash-ml; MLflow has exactly one. |
| `ModelSpec` / `EvalSpec` / `DriftSpec` / `SearchSpec` | `sklearn.Pipeline` / `mlflow.log_params` | "Spec" suffix is Kaizen-idiomatic (signatures are specs) but reads as over-engineered to ML users. |
| `InferenceServer` | `mlflow.pyfunc.serve` / `FastAPI /predict` | Fine, industry-standard. |
| `OnnxBridge` | (none) | Fine. |

**Against the rest of Kailash SDK**:
- `Pipeline` here ≠ `WorkflowBuilder` in core — users moving between core and ML face two meanings of "pipeline."
- `FeatureStore` ≠ `DataFlow` — conceptually adjacent but unrelated wiring (FeatureStore uses `ConnectionManager` directly, not DataFlow). The README explains this in prose; users will miss it.

**Kailash-only term blocking discoverability**: `Express` (on DataFlow)
does not appear here even though `db.express`-style shortcuts would be
the natural home for a `km.express` 3-line hello-world. Gap, not a
collision.

---

## 7. Top 10 DX fixes (impact × effort)

Ordered by impact × effort ratio. Each is a one-liner stating what
changes and the user experience unlocked.

| # | Fix | Impact × Effort | What changes → what unlocks |
|---|-----|-----------------|----------------------------|
| 1 | Add top-level `km.train(df, target=...)` convenience that auto-wires Store+Registry+Pipeline against a default SQLite store at `~/.kailash_ml/ml.db`. | 5 × 2 = 10 | Unlocks 3-line hello-world. PyCaret parity. This is THE fix. |
| 2 | Consolidate `ExperimentTracker` init to one path — `async with km.track(name): km.log_metric(...)`. Remove the dual-init surface. | 5 × 2 = 10 | Unlocks MLflow parity. Removes the single most-confusing surface. |
| 3 | Add `km.doctor()` — prints installed extras, missing extras, detected GPU/CUDA, SQLite path, env-var status. | 4 × 1 = 4 | Unlocks self-service diagnostic. Kills "no package-availability checks" pain point. |
| 4 | Make `entity_id_column` optional — synthesize a row index if absent; warn at DEBUG (per `observability.md` §8, not WARN with the schema name). | 4 × 1 = 4 | Unlocks "I just want to train on this CSV" path. |
| 5 | Accept model-family shorthands in `ModelSpec` (`"rf"`, `"xgb"`, `"lgbm"`, `"logreg"`) — still route through the allowlist. | 4 × 1 = 4 | Unlocks tab-discoverable model selection; removes the "dotted-string guessing game." |
| 6 | Provide sync-facade mirror (`km.train_sync`, `tracker.log_metric_sync`) for notebook users. Follows the DataFlow `express`/`express_sync` pattern already in the codebase. | 4 × 2 = 8 | Unlocks Jupyter UX without `asyncio.run()` gymnastics. |
| 7 | Fix all error-site boundaries to validate inputs at the public API (`schema=None`, wrong dtype, unknown model family) with typed errors naming the input and the valid set. | 4 × 2 = 8 | Unlocks actionable errors; aligns with `zero-tolerance.md` Rule 3a (typed delegate guards). |
| 8 | Ship `examples/` directory with 6 runnable scripts: `01_quickstart.py`, `02_track.py`, `03_automl.py`, `04_drift.py`, `05_gpu.py`, `06_pycaret_migration.py`. | 5 × 2 = 10 | Unlocks "learn by running." Closes the #1 doc gap. |
| 9 | Fix README version (0.7.0 → 0.9.0), `[full]` → `[all]`, and import-path drift between README and SKILL.md. | 3 × 1 = 3 | Unlocks first-impression trust. Violates `documentation.md` rule explicitly. |
| 10 | Single Engine entry point `km.Engine(...)` that owns Store+Registry+Tracker+Inference and exposes `.train / .track / .serve / .monitor / .compare` — the "one coherent Engine" vision. | 5 × 4 = 20 (bigger, but it's the vision) | Unlocks the North Star. Replaces the primitive scavenger hunt with one discoverable surface. |

Top five by **impact × effort** ratio (lower effort preferred): **1, 2,
8** (tied), then **3, 4, 5**.

---

## 8. North-star API sketch

Based on the vision (PyCaret-better + MLflow-better + single-engine +
unified ML/DL/RL). Illustrative only — no source changes proposed.

### 3-line hello-world (train a model)

```python
import kailash_ml as km
best = km.train(df, target="churned")
print(best.metrics)  # {'accuracy': 0.92, 'f1': 0.87, 'model': 'lightgbm'}
```

Behind the scenes `km.train` opens a default SQLite store at
`~/.kailash_ml/ml.db`, infers schema from DataFrame dtypes, picks a
reasonable default family set (logreg, rf, lgbm, xgb), runs
`compare_models`-style, returns the leaderboard winner. Classification
vs regression auto-detected; override via `task="regression"`.

### 10-line "production" (tracked, GPU, registered, served)

```python
import kailash_ml as km

with km.track("churn-prod-2026-04") as run:
    result = km.train(
        df, target="churned",
        families=["lgbm", "xgb"],
        gpu=True,                         # explicit; no silent fallback
        hpo={"strategy": "bayesian", "n_trials": 50},
    )
    run.log(result)                       # metrics + params + model artifact
    version = km.register(result, name="churn", stage="staging")

server = km.serve(version, port=8080)     # Nexus under the hood
```

### 30-line "advanced" (custom families, HP search, deploy)

```python
import kailash_ml as km
import polars as pl

engine = km.Engine(store="postgresql://user:pw@host/mldb")

schema = km.schema_from(df, target="churned")          # infer
schema.entity = "customer_id"                           # only if multi-tenant

search = km.search_space(
    lgbm={"num_leaves": km.int_range(16, 256),
          "learning_rate": km.log_range(1e-3, 0.3)},
    xgb ={"max_depth":   km.int_range(3, 12),
          "eta":         km.log_range(1e-3, 0.3)},
)

with engine.track("churn-prod") as run:
    leaderboard = engine.compare(
        df, schema,
        families=["lgbm", "xgb", "rf"],
        search=search, n_trials=50,
        metric="f1", higher_is_better=True,
        gpu=True,
    )
    run.log_leaderboard(leaderboard)

    best = leaderboard.best()
    calibrated = engine.calibrate(best, method="isotonic")
    explained  = engine.explain(calibrated, sample=df.sample(500))
    run.log_artifact(explained.to_plotly("summary"), "shap.html")

    version = engine.register(calibrated, name="churn", stage="shadow")

engine.monitor(version, reference=df).on_drift(
    lambda report: engine.retrain_if(report.severity == "severe"),
)

engine.serve(version, channels=["http", "mcp"])         # Nexus
```

Vision properties observable in the sketch:

- **One Engine.** `km.Engine(...)` owns `.train / .track / .compare /
  .calibrate / .explain / .register / .monitor / .serve`. No separate
  Store / Registry / Tracker wiring.
- **Verbs on top-level namespace.** Tab-completes to actions, not
  classes.
- **Sync-by-default facade.** No `await`, no `asyncio.run()`.
- **GPU explicit.** `gpu=True` is a contract the Engine MUST meet or
  raise; no silent CPU fallback.
- **Leaderboard is a first-class object.** `leaderboard.best()`,
  `leaderboard.to_polars()`, `leaderboard.plot()`.
- **MLflow-parity context manager.** `with engine.track(name) as run`.
- **Monitor callback composition.** `on_drift(lambda ...)` replaces
  the multi-engine wiring in today's API.
- **Deploy is one call.** `engine.serve(version, channels=[...])`
  routes through Nexus — framework-first per `framework-first.md`.

---

## Closing

The user's "devs need to hunt for API and work with primitives" is
accurate as a DX diagnosis. The engines are individually high-quality;
the problem is they are exposed at the wrong abstraction layer for the
data-science persona. The package currently ships the Primitive layer
and is missing the Engine layer — same failure pattern as DataFlow
before `db.express` landed. The fix is a thin top-level Engine facade
with sync-by-default verb methods, not a rewrite. Top five DX fixes by
impact × effort: #1 (`km.train`), #2 (unified `ExperimentTracker`), #8
(runnable `examples/`), #3 (`km.doctor`), #4 (optional
`entity_id_column`).

Word count: ~2,380.
