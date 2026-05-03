# Round 1 — New Data Scientist / Junior ML Engineer UX Audit

**Persona**: A Year-2 ML engineer (or MLFP course student) who just ran
`pip install kailash-ml`, has a DataFrame, and wants to (a) train a model,
(b) see live metrics in a dashboard, (c) run diagnostics, and (d) stop
being scared to deploy.

**Method**: grep + file reads against
`/Users/esperie/repos/loom/kailash-py/packages/kailash-ml/`, cross-checked
against the brief's four known gaps.

**TL;DR for the product lead**: The package has the right ingredients
(`km.train`, `km.track`, `DLDiagnostics`, `MLDashboard`, `km.doctor`,
`km.device`) but **none of them compose**. A newbie running the documented
5-line quickstart will log metrics to `~/.kailash_ml/ml.db`, open the
dashboard, and see an empty page — because the dashboard reads a
completely different file (`./kailash-ml.db` in cwd), queried through a
completely different schema (the 1.x `ExperimentTracker` engine tables, not
the 2.x `SQLiteTrackerBackend` runs table). This is the exact
"two trackers, two DBs" known gap, and it is worse than the brief
describes: the diagnostics module doesn't bridge them either. **For MLFP
course students, this is the drop-to-PyTorch-Lightning moment.**

---

## Q1 — One-line fit?

**Verdict**: YES for sklearn; PARTIAL for DL; BROKEN for torch/lightning.

**Evidence**:

- `packages/kailash-ml/src/kailash_ml/__init__.py:80-101` defines
  `km.train(df, target, *, family="sklearn")` and exports it at line 286.
  Sklearn families get a zero-config default (RandomForestClassifier). This
  matches the README `Why kailash-ml` promise.
- BUT: the docstring at `__init__.py:93-96` says
  _"For torch/lightning families users MUST pass a pre-built
  `TorchTrainable` or `LightningTrainable` via `MLEngine.fit(trainable=…)`
  — those families have no zero-config defaults."_ — so a newbie who
  types `km.train(df, target="y", family="torch")` will hit a typed error
  rather than a default neural net. That is correct behaviour, but the
  README Quick Start does NOT show `km.train` at all — it shows the
  3-engine primitive path (`FeatureStore` + `ModelRegistry` +
  `TrainingPipeline`) at `README.md:68-121`. So a reader of the README
  will never discover the one-liner.

**What the new scientist types / gets / expects**:

- Types: `km.train(df, target="churned")`. Gets: `TrainingResult`. Expects: same.
- Types: anything from the README Quick Start. Gets: 50+ lines of engine
  boilerplate. Expects: 3-line sklearn-equivalent.

**Business impact**: The one-liner exists but the README buries it. Most
MLFP students never read `__init__.py` and will learn the old primitive
path, at which point the "PyCaret-better" differentiator is invisible.

---

## Q2 — One-line diagnose?

**Verdict**: NO. There is no `km.diagnose(result)` entry point.

**Evidence** (grep):

```
$ rg "^def diagnose\b|km\.diagnose" packages/kailash-ml/
(no matches)
```

The nearest equivalents:

- `packages/kailash-ml/src/kailash_ml/diagnostics/__init__.py:65-70`
  exposes `DLDiagnostics`, `RAGDiagnostics`, `run_diagnostic_checkpoint`,
  `diagnose_classifier`, `diagnose_regressor`. None are re-exported at
  the `kailash_ml` top level — user MUST type
  `from kailash_ml.diagnostics import ...`.
- `km.doctor()` exists (`__init__.py:206`), but it's a health-check
  diagnostic for the torch/GPU stack, NOT a model-diagnostics bundle.
- There is no "diagnose classical ML model" surface (sklearn + XGBoost +
  LightGBM + feature-importance + SHAP + confusion matrix + ROC).
  `diagnose_classifier` exists but is DL-only (requires `torch.nn.Module`).

**What the new scientist types / gets / expects**:

- Types: `km.diagnose(result)`. Gets: `AttributeError`. Expects: a
  bundled report with loss curves, confusion matrix, feature importance,
  and "here's what's wrong" diagnostics — the `km.doctor`-for-models
  story the engine-first mandate promised.

**Business impact**: "Debug my model" is the #1 daily operation. No
one-liner means students learn to stack-import 5 helpers from different
submodules, which is exactly the primitive-composition the brief's
non-negotiable #1 forbids. **MLFP students drop to PyTorch Lightning +
TensorBoard here because the latter's `lightning.Trainer(logger=...)` is
literally one kwarg.**

---

## Q3 — One-line dashboard? — THE KILLER FINDING

**Verdict**: NO. `km.dashboard()` does NOT exist, and the
`MLDashboard` / `kailash-ml-dashboard` CLI that DOES exist reads a
**different database, populated by a different class, than `km.track()`**.

**Evidence**:

1. `km.dashboard` is not in `__init__.py`. Grep:
   `rg "def dashboard\b|km\.dashboard" packages/kailash-ml/src/kailash_ml/__init__.py`
   — zero matches.
2. `km.track()` writes to `~/.kailash_ml/ml.db`
   (`tracking/runner.py:73-74`: `_DEFAULT_TRACKER_DB = _DEFAULT_TRACKER_DIR / "ml.db"` where
   `_DEFAULT_TRACKER_DIR = Path.home() / ".kailash_ml"`).
3. `MLDashboard` defaults to `sqlite:///kailash-ml.db` (note the hyphen
   AND the cwd-relative path) — `dashboard/__init__.py:46`:
   `db_url: str = "sqlite:///kailash-ml.db"`. Same on the CLI
   `dashboard/__init__.py:148`.
4. The dashboard ASGI app constructs `ExperimentTracker(self._conn, ...)`
   (`dashboard/server.py:446`) — the **1.x engine**, which queries a
   schema that `SQLiteTrackerBackend` does not populate.
5. `km.track()`'s `ExperimentRun` has `log_param` / `log_params` /
   `attach_training_result` (`tracking/runner.py:288-332`) — but **no
   `log_metric`**. Meanwhile the 1.x `ExperimentTracker` has
   `log_metric` at `engines/experiment_tracker.py:352` and 905. The
   metrics the dashboard reads from literally cannot come from
   `km.track()`.

So the new scientist types:

```python
async with km.track("my-exp", lr=0.01) as run:
    result = km.train(df, target="y")
    run.attach_training_result(result)  # param/device persisted
    # NO run.log_metric — the method doesn't exist on this class
```

Then opens another shell and types `kailash-ml-dashboard`. The dashboard
starts on :5000, but:

- It looks for `./kailash-ml.db` (cwd, not `~/.kailash_ml/ml.db`).
- Even if the user passes `--db ~/.kailash_ml/ml.db`, the dashboard
  opens it with `ExperimentTracker`, whose schema has
  `experiments`/`runs`/`metrics` tables, while `SQLiteTrackerBackend`
  only wrote a `runs` row with NO metrics table at all.
- Result: the dashboard either crashes on missing tables or renders
  empty.

**What the new scientist types / gets / expects**:

- Types: `kailash-ml-dashboard` (per README line 620). Gets: empty
  dashboard (or schema error). Expects: live metrics for the run they
  just did 30 seconds ago.

**Business impact**: **This is a deal-breaker, not a gap.** The
dashboard is advertised on README.md:612-627 as the way to view
experiments, but the documented Quick Start doesn't even use it — the
README's dashboard section (619-629) uses `ExperimentTracker` directly
(the 1.x path), while everything the engine-first mandate promotes
(`km.train`, `km.track`) writes somewhere the dashboard cannot read.
MLFP course students will run the Quick Start, see no dashboard value,
and assume the framework is broken. The primitives/engines split is
semantically correct but operationally catastrophic when the two stacks
do not share a store.

---

## Q4 — Auto-wiring?

**Verdict**: NO. Every component is an island. There is no
`diagnostics=`, `tracker=`, `dashboard=` kwarg anywhere.

**Evidence**:

1. `DLDiagnostics.__init__` signature
   (`diagnostics/dl.py:251-258`):
   ```python
   def __init__(
       self,
       model: Any,
       *,
       dead_neuron_threshold: float = 0.5,
       window: int = 64,
       run_id: Optional[str] = None,
   ) -> None:
   ```
   It takes a `run_id: str` but NO `tracker=` kwarg. The string has no
   connection to `km.track()`'s `ExperimentRun.run_id` — the user must
   manually thread the UUID across two surfaces that don't know about
   each other.
2. Grep `attach_diagnostic|diagnostics=|tracker\.attach|run\.attach`
   across `packages/kailash-ml/src/kailash_ml/` returns **zero matches**.
3. `ExperimentRun` in `tracking/runner.py:211-503` does not expose any
   `attach_diagnostic(diag)` or `diagnostics` property. The only wiring
   hook is `attach_training_result` for a `TrainingResult` dataclass
   (line 299).
4. `MLEngine.fit()` (`engine.py:1067-1153` covering signature + body)
   does NOT accept a `tracker=` or `diagnostics=` kwarg — it produces a
   `TrainingResult` that the user must manually pass into
   `run.attach_training_result(result)`. If the user forgets, the run
   row has `device_used=None` even though the training completed.

**What the new scientist types / gets / expects**:

- Types: `DLDiagnostics(model, tracker=run)`. Gets:
  `TypeError: unexpected keyword argument 'tracker'`. Expects: the
  diagnostics push gradient/activation/dead-neuron metrics into the
  tracker so the dashboard shows them.

**Business impact**: The brief's non-negotiable #2 ("the engine does the
wiring") is unmet. Every new user has to wire tracker → diagnostics →
dashboard manually, and the documented helpers encourage them to do so
through 3 different import paths. This is the PyTorch-Lightning
`Trainer(logger=..., callbacks=[EarlyStopping(...)])` one-kwarg story we
are losing against.

---

## Q5 — Discoverability from `from kailash_ml import *`?

**Verdict**: PARTIAL. The kernel is discoverable; the lifecycle is not.

**Evidence** — `__init__.py:255-338` `__all__`:

Present and promoted:

- `train`, `track`, `doctor`, `device`, `use_device`, `MLEngine`,
  `TrainingResult`, `Trainable` + 7 family adapters.
- Engines: `FeatureStore`, `ModelRegistry`, `TrainingPipeline`,
  `InferenceServer`, `DriftMonitor`, `ExperimentTracker`,
  `MLDashboard`, `AutoMLEngine`, `HyperparameterSearch`, etc. (14
  engines).

ABSENT from `__all__`:

- `diagnose`, `DLDiagnostics`, `RAGDiagnostics`, `diagnose_classifier`,
  `diagnose_regressor`, `run_diagnostic_checkpoint` — **the entire
  diagnostics module is hidden** behind
  `from kailash_ml.diagnostics import …`.
- `ExperimentRun`, `RunStatus` — the tracker result types — are hidden
  behind `from kailash_ml.tracking import …`. A user who wrote
  `async with km.track(...) as run:` and wants to type-annotate `run`
  must know the submodule.
- Anything RL. Neither `RLTrainer` nor `RLTrainingConfig` is in
  `__all__` even though `packages/kailash-ml/src/kailash_ml/rl/trainer.py`
  exists.

**What the new scientist types / gets / expects**:

- Types: `import kailash_ml as km; dir(km)`. Gets: 40+ symbols
  dominated by engine names (`FeatureStore`, `HyperparameterSearch`,
  `PreprocessingPipeline`, …). Expects: a short lifecycle-ordered list
  like `{train, track, diagnose, serve, monitor, doctor, device}`.

**Business impact**: The 5-minute "what is this package?" read surfaces
the primitive engines first and the lifecycle verbs second. The
non-negotiable #1 (engine-first) breaks at the import surface itself.

---

## Q6 — Lifecycle holes

### Classical ML (sklearn-equivalent) — PARTIAL

- `km.train(df, target, family="sklearn")` exists (`__init__.py:80`).
  One line, works. GOOD.
- `km.evaluate(result)` — **does not exist**. Grep:
  `rg "^def evaluate\b|km\.evaluate" packages/kailash-ml/src/kailash_ml/__init__.py`
  returns zero. `MLEngine.evaluate()` exists at line 1420 but requires a
  `setup()` call first (line 1086) per spec §5.
- `km.predict(result, new_df)` — **does not exist at top level**. Only
  `MLEngine.predict()` at line 1157.
- `km.serve(result)` — **does not exist at top level**. Only
  `InferenceServer` which requires a `ModelRegistry`, which requires a
  `ConnectionManager`, which requires a `db_url`. Three hops for
  "serve this model I just trained."

**User-visible impact**: The sklearn one-liner exists, but the next step
after fitting ("now show me a scorecard and let me predict on a new
row") requires dropping down to primitives. `PyCaret.setup() →
PyCaret.compare_models() → PyCaret.predict_model()` is a
3-verb story; ours is a 1-verb-then-5-imports story.

### Deep Learning (PyTorch Lightning-equivalent) — HOLE

- `km.train(df, family="torch")` gives a typed error saying "pass a
  Trainable" (`__init__.py:93-95`). That is correct for advanced
  users but for a student who types
  `model = nn.Sequential(...); km.train(model, train_ds)` this is a wall.
- `lightning.Trainer(logger=TensorBoardLogger(...), callbacks=[...])`
  competitor has ONE kwarg that wires training → logger → dashboard.
  Kailash equivalent: construct `LightningTrainable`, construct
  `DLDiagnostics` separately, construct `km.track()` context
  separately, thread `run_id` by hand. 3 imports, 3 instantiations,
  1 manual ID plumbing.

**User-visible impact**: The DL path is the feature we need to beat
Lightning on. We lose at the first 30 seconds.

### Reinforcement Learning — HOLE

- `packages/kailash-ml/src/kailash_ml/rl/trainer.py` exists and has
  `RLTrainer` + `RLTrainingConfig` + `RLTrainingResult`. GOOD baseline.
- But: NO `km.rl_train()` / `km.rl_diagnose()` / RL diagnostics module.
  Grep `rg "rl_diag|reinforcement|rollout|Q_value|policy_grad|replay_buffer" packages/kailash-ml/src/kailash_ml` returns only
  the RL trainer file — **no diagnostics, no RL-specific tracker
  wiring, no RL dashboard tab.**
- The brief confirms "No RL diagnostics exist" — EVIDENCE-CONFIRMED.

**User-visible impact**: Students who want to dip into RL get a training
loop but zero feedback (no episode-reward curves, no entropy, no
KL-divergence from reference policy, no exploration-rate trace). They
will use Stable-Baselines3's own TensorBoard integration instead.

### Serving (trained model → endpoint) — HOLE

- No `km.serve(result)` top-level. `InferenceServer`
  (`engines/inference_server.py:127`) requires a `model_registry` kwarg.
- No `model.save("/tmp/mymodel")` one-liner either — the ONNX bridge
  exists (`OnnxBridge` in `__all__`) but the user must know it, import
  it, and invoke it manually after training.

**User-visible impact**: "I trained, how do I deploy?" is the 5th
question every new user asks. Currently: read 4 README sections.

### Drift monitoring ("my model is live, alert me") — HOLE

- `DriftMonitor` engine exists. Grep:
  `rg "def check_drift\b" packages/kailash-ml/src/kailash_ml` shows the
  primitive.
- NO `km.watch(model_name, live_data_stream)` top-level helper, NO
  `drift=True` kwarg on `km.serve()` (which doesn't exist anyway).
- README Drift Monitoring section (line 633+) uses the primitive path
  with `ConnectionManager` + `DriftMonitor(conn)` + `DriftSpec` +
  `monitor.check_drift(...)` — a 4-step ritual.

**User-visible impact**: The "alert me when things go wrong" promise is
the #1 enterprise sell vs. a raw sklearn pipeline. Currently buried
under primitive composition.

---

## Additional moment-of-first-use findings

### F-README-VERSION (MED): README advertises 0.9.0; package is 0.17.0

**Evidence**:

- `packages/kailash-ml/README.md:7`: `**Version**: 0.9.0`
- `packages/kailash-ml/pyproject.toml`: `version = "0.17.0"`

**User-visible impact**: A student reading the README thinks they're
installing 0.9.0 and their feature matrix corresponds to that. Eight
minor versions have shipped with no README update. First impression:
"unmaintained."

### F-QUICK-START-PRIMITIVE (HIGH): README Quick Start predates the 2.0 kernel

**Evidence**:

- `README.md:56-121` "Quick Start" uses
  `FeatureStore + ModelRegistry + TrainingPipeline` — the 1.x primitive
  path — with a `ConnectionManager`, `LocalFileArtifactStore`,
  `FeatureSchema`, `ModelSpec`, `EvalSpec` — **6 imports before the
  first `.train(...)` call.**
- `__init__.py:80-101` already ships `km.train(df, target)` — one import,
  one line.

**User-visible impact**: The package's own README sells against the
package's own differentiator. First 5 minutes of onboarding teach the
student to never use the one-liner. This is the origin of the
"two-parallel-APIs" confusion the MLFP-dev review surfaced.

### F-DASHBOARD-DB-MISMATCH (CRITICAL): Dashboard reads schema km.track doesn't populate

**Evidence**: see Q3.

**User-visible impact**: See Q3.

### F-LOG-METRIC-MISSING (HIGH): `ExperimentRun` has no `log_metric`

**Evidence**:

- `tracking/runner.py:231-332` — `ExperimentRun` class surface:
  `log_param`, `log_params`, `attach_training_result`. NO `log_metric`.
- `engines/experiment_tracker.py:352` AND `905` — the 1.x
  `ExperimentTracker.Run` has `log_metric` and `log_metrics`. New users
  following `km.track()` never reach this code path.

**User-visible impact**: Students will write

```python
async with km.track("my-exp") as run:
    for epoch in range(10):
        await run.log_metric("loss", loss.item(), step=epoch)
```

because that's the MLflow / wandb idiom. They will get
`AttributeError: 'ExperimentRun' object has no attribute 'log_metric'`.
They will conclude the tracker is incomplete and switch to MLflow.

### F-DIAGNOSTICS-NO-DASHBOARD-SINK (HIGH): `DLDiagnostics.plot_*` emits inline Plotly

**Evidence**:

- `diagnostics/dl.py:965` — `DLDiagnostics.report()` and per docstring
  header lines 33-51, the plot surface is `plot_training_dashboard()`.
- No `diag.push_to_tracker(run)` method. Grep confirms no
  `push_to_tracker` / `emit_to` / `sink` in the file.

**User-visible impact**: A student who trains a DL model and wants the
dashboard to show gradient norms, dead-neuron rates, activation
distributions gets: nothing. The diagnostics module produces inline
Plotly figures that live in a notebook cell. They cannot be persisted
to `MLDashboard`. TensorBoard's `add_histogram` / `add_scalar` is
literally one call per metric.

### F-NO-RL-DIAGNOSTICS (HIGH, already called out in brief)

**Evidence**: Grep above — only `rl/trainer.py` exists in the RL
subtree; no `rl/diagnostics.py` parallel to `diagnostics/dl.py`.

**User-visible impact**: RL students will bounce.

### F-IMPORT-SHADOWING-LIFECYCLE (MED): `__all__` buries verbs under nouns

**Evidence**: `__init__.py:255-338` — the order of symbols in `__all__`
is: `__version__`, kernel, GPU, `Trainable`, 7 adapters, `train`,
`track`, `doctor`, `resolve_torch_wheel`, DeviceReport helpers, types,
then 18 engines (most of them primitives), then utilities. There is no
visual grouping and no lifecycle-ordered subgroup like
`# Train → Track → Diagnose → Serve → Monitor`.

**User-visible impact**: `dir(km)` alphabetised lists RL, feature store,
anomaly detection, ensemble, clustering BEFORE `train` and `track`.
Discoverability of the happy path is buried.

---

## Severity Table

| Finding                         | Severity     | Lifecycle stage          | User-journey step                 | Evidence                                                                             | Fix category               |
| ------------------------------- | ------------ | ------------------------ | --------------------------------- | ------------------------------------------------------------------------------------ | -------------------------- |
| F-DASHBOARD-DB-MISMATCH         | **CRITICAL** | Track + Visualize        | Day-0 dashboard open              | `tracking/runner.py:73-74` vs `dashboard/__init__.py:46` + `dashboard/server.py:446` | FLOW                       |
| F-QUICK-START-PRIMITIVE         | **HIGH**     | Onboarding               | First 5 min of README             | `README.md:56-121` vs `__init__.py:80`                                               | NARRATIVE                  |
| F-LOG-METRIC-MISSING            | **HIGH**     | Track                    | First `await run.log_metric(...)` | `tracking/runner.py:231-332`                                                         | DATA (API gap)             |
| F-DIAGNOSTICS-NO-DASHBOARD-SINK | **HIGH**     | Diagnose → Visualize     | DL-student first diag run         | `diagnostics/dl.py:251-300` + absence of push_to_tracker grep                        | FLOW                       |
| F-NO-RL-DIAGNOSTICS             | **HIGH**     | Diagnose (RL)            | First RL training run             | Grep — only `rl/trainer.py` exists                                                   | DATA (module missing)      |
| F-SERVE-HOLE                    | **HIGH**     | Deploy                   | "now put this online"             | `inference_server.py:127` + grep for `km.serve` returns nothing                      | DESIGN (missing one-liner) |
| F-DRIFT-HOLE                    | **HIGH**     | Monitor                  | "alert me on shift"               | `README.md:633-664` + grep for `km.watch` returns nothing                            | DESIGN (missing one-liner) |
| F-DIAGNOSE-NO-TOPLEVEL          | **HIGH**     | Diagnose                 | First debug session               | grep `km\.diagnose` → zero                                                           | DESIGN (missing one-liner) |
| F-DL-NO-AUTO-WIRE               | **HIGH**     | Train → Track → Diagnose | DL students wiring trio           | `diagnostics/dl.py:251-258` signature has no `tracker=`                              | DESIGN (auto-wire)         |
| F-README-VERSION                | MED          | Onboarding               | Install check                     | `README.md:7` vs `pyproject.toml`                                                    | DOCS                       |
| F-IMPORT-SHADOWING-LIFECYCLE    | MED          | Onboarding               | `dir(km)`                         | `__init__.py:255-338`                                                                | NARRATIVE                  |
| F-DIAGNOSTICS-OUT-OF-ALL        | LOW          | Diagnose                 | `from kailash_ml import *`        | `__init__.py:255-338` omits `DLDiagnostics`                                          | DATA (export list)         |
| F-RL-TRAINER-OUT-OF-ALL         | LOW          | Train (RL)               | `dir(km)`                         | `__init__.py:__all__` omits RL symbols                                               | DATA (export list)         |

---

## The single highest-leverage recommendation

**Unify the tracker store and wire it automatically.**

Three concrete fixes, done as one PR, close 6 of the 13 findings above
(F-DASHBOARD-DB-MISMATCH, F-LOG-METRIC-MISSING,
F-DIAGNOSTICS-NO-DASHBOARD-SINK, F-DL-NO-AUTO-WIRE,
F-IMPORT-SHADOWING-LIFECYCLE, F-README-VERSION) and turn the
happy-path story from "I typed 5 lines and saw nothing" into "I typed
5 lines, `kailash-ml-dashboard` shows my run":

1. **Make `km.track()` and `MLDashboard` share exactly one default
   store path and exactly one schema.** Either the 2.x
   `SQLiteTrackerBackend` gains a `metrics` table and the dashboard
   reads it, or the 1.x `ExperimentTracker` becomes the backend for
   `km.track()`. Either way, `kailash-ml-dashboard` with no args MUST
   render the run `km.track()` just finished.

2. **Add `ExperimentRun.log_metric(name, value, step=None)` and have
   `MLEngine.fit()` auto-log metrics to the currently-active
   `km.track()` context** (via the existing `_current_run` contextvar
   at `tracking/runner.py:84-86`). No manual wiring required. Also
   add `DLDiagnostics.__init__(..., tracker=None)` that, when
   non-None, emits every `track_gradients` / `track_activations` /
   `record_batch` / `record_epoch` sample through
   `tracker.log_metric(...)` during the training loop. Result:
   `async with km.track("my-exp") as run: DLDiagnostics(model,
tracker=run)` is the one-kwarg PyTorch-Lightning-equivalent.

3. **Rewrite the README Quick Start to use `km.train + km.track +
kailash-ml-dashboard`** and demote the primitive path to an
   "Advanced" section. Update `**Version**: 0.17.0` at the same time.

Everything else in the table above is follow-up work, but those three
changes are the difference between "students drop us for Lightning at
minute 5" and "students stay for the diagnostic breadth."

---

**Output path**: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-1-newbie-ux.md`
