# Round 1 — Industry / Competitive Auditor

**Persona:** Senior ML/DL/RL scientist in 2026 evaluating ML platforms for a new project. Has used MLflow in prod for 3 years, moved the last team to Weights & Biases for research, ships Hugging Face `Trainer` + Accelerate for fine-tuning, and runs Ray on a small GPU cluster. Knows every product's rough edges. Open-source-first, but judges UX, not ideology.

**Lens:** Market-position. NOT spec-to-code, NOT DL/RL mechanics, NOT code review. The question is: **"If a new ML scientist installs `kailash-ml` today, what exactly is she going to hit that MLflow / wandb / Lightning / HF solved five years ago?"**

**Method:** Training-data recall of each competitor's canonical one-line entry, auto-log surface, dashboard wiring, and sticky feature. Grounded against the two confirmed artifacts:

- `packages/kailash-ml/src/kailash_ml/tracking/runner.py:73-74` — `_DEFAULT_TRACKER_DB = Path.home() / ".kailash_ml" / "ml.db"` is where `km.track()` writes.
- Docstring at `packages/kailash-ml/src/kailash_ml/tracking/runner.py:18-22` — explicit comment: "This module is async-first and does NOT depend on the 1.x `kailash_ml.engines.experiment_tracker.ExperimentTracker`." Two trackers confirmed from source, not inference.

Findings are framed as **"Competitor X does Y out-of-the-box; kailash-ml requires user code / does not have this / has this but broken."**

---

## Section A — Feature matrix

Legend: `Y` = shipped and canonical, `Y*` = shipped with caveats, `P` = plugin/add-on (not default), `N` = absent, `?` = unclear from training data.

Columns:

- **1-line** — the canonical first-touch API a new user types
- **Auto-log** — auto-captures params / metrics / env / artefacts without manual calls
- **Dashboard** — native dashboard (web UI) ships with the tool
- **Registry** — model registry (versioned model store with stages)
- **AutoML** — first-party AutoML / hyperparameter search integrated with tracker
- **RL** — first-party RL support (PPO/DQN/etc) with diagnostics
- **Drift** — production drift / data-distribution monitoring
- **FStore** — feature store (offline + online parity)
- **Serve** — model serving (REST / gRPC / batch) integrated with registry
- **RLHF** — DPO / PPO-RLHF / reward-model training (2024+ table stakes for LLM)
- **RLHF-tool** — RLHF with tool-use / multi-turn trajectories (2026 frontier)
- **MM** — multimodal (vision + audio + text) tracking and diagnostics

| Product                    | 1-line                                        | Auto-log | Dashboard          | Registry | AutoML        | RL                   | Drift | FStore         | Serve       | RLHF      | RLHF-tool     | MM  |
| -------------------------- | --------------------------------------------- | -------- | ------------------ | -------- | ------------- | -------------------- | ----- | -------------- | ----------- | --------- | ------------- | --- |
| **MLflow**                 | `mlflow.start_run()` + `autolog()`            | Y        | Y                  | Y        | P             | N                    | P     | N              | Y           | P         | N             | P   |
| **Weights & Biases**       | `wandb.init()`                                | Y        | Y                  | Y        | Y (Sweeps)    | P                    | P     | P              | P           | P         | P             | Y   |
| **TensorBoard**            | `SummaryWriter()` / `tb.summary.*`            | Y\*      | Y                  | N        | N             | Y\*                  | N     | N              | N           | N         | N             | Y   |
| **Comet ML**               | `Experiment()`                                | Y        | Y                  | Y        | Y (Optimizer) | P                    | Y     | N              | P           | P         | P             | Y   |
| **Neptune**                | `neptune.init_run()`                          | Y        | Y                  | Y        | P             | P                    | P     | N              | P           | P         | N             | Y   |
| **ClearML**                | `Task.init()`                                 | Y        | Y                  | Y        | Y (HPO)       | P                    | Y     | Y\*            | Y           | P         | N             | Y   |
| **Kubeflow**               | `@component` / Pipelines + Katib + KServe     | N\*      | Y                  | Y        | Y (Katib)     | N                    | Y     | Y (Feast glue) | Y           | P         | N             | Y   |
| **Ray (Train+Tune+Serve)** | `tune.Tuner(...).fit()` / `ray.train.*`       | Y\*      | Y (dashboard)      | Y\*      | Y (Tune)      | Y (RLlib)            | P     | P              | Y           | Y         | Y             | Y   |
| **PyTorch Lightning**      | `Trainer(...).fit(model, dm)`                 | Y\*      | N (logger plugins) | N        | N             | P                    | P     | N              | N           | P         | N             | Y   |
| **fast.ai**                | `Learner(...).fit_one_cycle(n)`               | Y\*      | N                  | N        | N             | N                    | N     | N              | N           | N         | N             | Y\* |
| **Hugging Face stack**     | `Trainer(...).train()` / `SFTTrainer.train()` | Y        | Y (Hub UI)         | Y (Hub)  | P             | Y (RLlib/SB3 via HF) | P     | N              | Y (TGI/TEI) | Y (TRL)   | Y (TRL 0.12+) | Y   |
| **kailash-ml (current)**   | `km.train(...)` (stub) / `km.track()` ctx-mgr | Y\*      | Y\*                | Y\*      | Y\*           | Y\*                  | Y     | Y              | Y           | via Align | via Align     | N   |

### Observations on the kailash-ml row (grounded)

- **`Y*` for Auto-log:** `km.track()` captures 17 fields per spec §2.4 (runner.py:12-16: `kailash_ml_version / lightning_version / torch_version / cuda_version / device_used / accelerator / precision` on top of the original 10). That is competitive with `mlflow.autolog()` and ahead of TensorBoard's env capture. Counted as `Y*` because tracker-and-dashboard don't share a store (Finding H-1 below) so the auto-captured fields never reach `MLDashboard`.
- **`Y*` for Dashboard:** `packages/kailash-ml/src/kailash_ml/dashboard/server.py` exists (505 LOC) — but it reads a _different_ SQLite DB than `km.track()` writes. That makes the dashboard `Y*` at the install level and `N` at the integrate level.
- **`Y*` for Registry / AutoML / RL / Drift / FStore / Serve:** every one of `engines/model_registry.py`, `engines/automl_engine.py`, `rl/trainer.py`, `engines/drift_monitor.py`, `engines/feature_store.py`, `engines/inference_server.py` exists on disk — but the tracker is an island, so the "shipped + integrated" claim isn't supportable without the compose path.
- **`Y*` for RL:** directory exists (`rl/trainer.py`, `rl/env_registry.py`, `rl/policy_registry.py`) but brief §2 "Known real gaps #4" states "No RL diagnostics exist. DL/RAG/Alignment/Interpretability/LLM/Agent adapters exist; RL is completely absent." RL primitives without RL diagnostics = `Y*` that degrades to `N` the moment a user wants episode-return curves.
- **`N` for MM:** no `diagnostics/multimodal.py` in `packages/kailash-ml/src/kailash_ml/diagnostics/`; only `dl.py` and `rag.py`. wandb, Comet, Neptune, and the HF Hub all render image/audio tiles out of the box.

---

## Section B — Severity-ranked findings

Each finding is framed as "Competitor X does Y; kailash-ml requires Z." Severity reflects buyer-perception gravity for a new ML scientist, not implementation difficulty.

### H-1 — CRITICAL: Tracker ↔ dashboard do not compose (parity with every competitor broken)

**MLflow does:** `mlflow.start_run() + mlflow.autolog()` + `mlflow ui` reads the same `mlruns/` directory. Five years of users expect this. W&B does it with `wandb.init()` and the cloud/local UI pointing at the same project. Comet, Neptune, ClearML, TensorBoard — identical single-store contract.

**kailash-ml requires:** The user to notice that `km.track()` writes `~/.kailash_ml/ml.db` (runner.py:73-74) while `MLDashboard` engine reads `sqlite:///kailash-ml.db` (brief §2 "Known real gaps #1"), and then to write a bridge class that neither exists nor is documented. A `km.track()` run is invisible to `MLDashboard.latest()`. This is the single failure the market has solved since ~2018.

**Competitive evidence:** There is no 2026 ML platform a scientist would install where `start_run()` and the dashboard look at different files. The only systems that do are internal-to-company hand-rolls. Shipping a dashboard that doesn't see your own tracker is a demo-abort on day 0.

**Severity:** CRITICAL — P0 for competitive parity. This is the defining failure mode for the audit.

### H-2 — HIGH: No `log_metric` on `ExperimentRun` (sub-parity with MLflow 1.0, 2018)

**MLflow does:** `mlflow.log_metric("loss", 0.3, step=i)` inside a `with mlflow.start_run():` block. Shipped 2018. Universal muscle memory.

**W&B does:** `wandb.log({"loss": 0.3})` — even simpler.

**Lightning does:** `self.log("train_loss", loss)` inside `training_step` — Trainer plumbs to whichever Logger is active.

**kailash-ml requires:** Per brief §2 "Known real gaps #2", `ExperimentRun` has `log_param / log_params / attach_training_result` but **no `log_metric`**. The metric API lives on the engine-layer `ExperimentTracker`, which users calling `km.track()` do not reach. Users who try `run.log_metric("loss", x)` will hit `AttributeError`, google, find no docs, and bounce.

**Competitive evidence:** `log_metric` is table-stakes going back to MLflow 0.9 (2018). Every tutorial, every O'Reilly book, every Stack Overflow snippet uses this. Missing it from the 2.0 tracker is a regression-looking gap even though it's actually a forward-port gap.

**Severity:** HIGH — eight-year-old muscle memory fails at the first keystroke.

### H-3 — HIGH: `DLDiagnostics` is an island; no event-sink to tracker (sub-parity with TensorBoard's SummaryWriter, 2016)

**TensorBoard does:** `SummaryWriter.add_histogram("gradients/layer1", grad, step=i)` writes to the same event file the dashboard reads. Shipped 2016.

**W&B does:** `wandb.log({"gradients": wandb.Histogram(grad)})` — histogram tiles auto-render.

**PyTorch Lightning + any logger does:** Callbacks emit histograms to the active Logger (TB, W&B, MLflow, Comet) without user code.

**kailash-ml requires:** Per brief §2 "Known real gaps #3", `DLDiagnostics` has no `tracker=` kwarg, no event sink. Its `plot_training_dashboard()` emits inline Plotly to the notebook; nothing propagates to `MLDashboard`. That's at parity with a 2015 Jupyter notebook, not with a 2026 DL platform.

**Competitive evidence:** TensorBoard histograms + projector have been the default mental model for gradient/activation diagnostics for a decade. A DL tool that renders gradient plots only inline makes "go compare run A vs run B's gradient norms" impossible without manually zipping HTMLs.

**Severity:** HIGH — a DL scientist's default diagnostic loop is blocked.

### H-4 — HIGH: Zero RL diagnostics adapter (RLlib / SB3 / CleanRL ship this by default)

**Ray RLlib does:** `Algorithm.train()` logs `episode_reward_mean / episode_len_mean / policy_loss / vf_loss / entropy / kl` to the configured logger (TB or W&B) per iteration automatically.

**Stable-Baselines3 does:** `TensorboardCallback` auto-renders reward curves, entropy, clip fraction, explained variance.

**CleanRL does:** Every script writes to W&B by default, with reward + episodic-length + policy-grad-norm + value-loss on fixed tile names.

**kailash-ml requires:** Per brief §2 "Known real gaps #4", "No RL diagnostics exist." The `rl/trainer.py`, `rl/env_registry.py`, `rl/policy_registry.py` primitives exist but emit no adapter to the tracker. An RL scientist who installs `kailash-ml` cannot see reward-curves, policy-entropy, or Q-value distributions without writing their own wall-clock plumbing.

**Competitive evidence:** 2026 RL is dominated by TRL / RLlib / SB3 / CleanRL + W&B or TB. An RL product with no reward-curve dashboard by default is a day-0 non-starter.

**Severity:** HIGH — entire lifecycle stage unsupported at the diagnostic layer.

### H-5 — HIGH: No `autolog()` equivalent (MLflow, Neptune, Comet, ClearML, W&B all have it)

**MLflow does:** `mlflow.autolog()` — one call patches sklearn, xgboost, lightgbm, pytorch-lightning, keras, tensorflow, spark, statsmodels, fastai, transformers. Captures params, metrics, model artefacts, feature importance, confusion matrix. Shipped 2020.

**ClearML does:** `Task.init()` — zero additional calls required; monkey-patches every major framework on import.

**Comet does:** `Experiment()` auto-logs sklearn / keras / torch / transformers / xgboost / lightgbm.

**kailash-ml requires:** `km.track()` captures the RUN envelope (17 fields per spec §2.4) but does NOT monkey-patch sklearn / lightgbm / lightning / torch to auto-capture hyperparams + metrics + artefacts per step. A user converting an MLflow notebook hits: "Where do I put `autolog()`?" — no equivalent surface.

**Competitive evidence:** The "one decorator, everything logged" UX has been the implicit baseline since ClearML's 2019 auto-instrumentation and MLflow's 2020 autolog. Not having it means every framework integration becomes per-user boilerplate.

**Severity:** HIGH — the product's main differentiator (engine-first) fails to ship the industry's main UX sugar.

### M-1 — MEDIUM: No sweeps / hyperparameter-search integrated with tracker (W&B Sweeps, Optuna+MLflow, Katib, Ray Tune)

**W&B Sweeps does:** `wandb sweep sweep.yaml` → a parameter-grid / Bayesian / random search where every trial auto-attaches to the same project. UI renders the parallel-coordinates plot without user code.

**Optuna + MLflow do:** `optuna.integration.MLflowCallback` — every trial is a run, parent-child hierarchy rendered natively.

**Ray Tune does:** `tune.Tuner(...).fit()` — native Tune Dashboard + optional TB/W&B callback.

**Katib does:** `Experiment(trialTemplate=...)` — Kubernetes-native HPO.

**kailash-ml has:** `engines/hyperparameter_search.py` in the file listing, but no evidence of a one-line `km.sweep(...)` entry point that attaches every trial to a parent run in the shared tracker. The engine-layer HPO class exists; the engine-first UX doesn't.

**Severity:** MEDIUM — AutoML-adjacent; users expect it once `km.track()` exists.

### M-2 — MEDIUM: No artefact-typed UI tiles (W&B / Comet / Neptune)

**W&B does:** `wandb.log({"image": wandb.Image(im), "pr_curve": wandb.plot.pr_curve(...), "confusion_matrix": wandb.plot.confusion_matrix(...)})`. UI auto-renders.

**Comet does:** `experiment.log_confusion_matrix()`, `experiment.log_image()`, `experiment.log_histogram_3d()`.

**kailash-ml has:** `engines/model_visualizer.py` (confirmed present) but the docstring in `runner.py` says "auto-capture surface" is 17 fields — those are envelope fields, not typed artefacts. The dashboard renders metrics tables and training-history lines per the server.py endpoints; typed artefact tiles are not visible at the `km.track()` surface.

**Severity:** MEDIUM — hurts the eval / report / share loop.

### M-3 — MEDIUM: No native sharable report / notebook-to-UI export (W&B Reports, Neptune Dashboards, Comet Reports)

**W&B Reports:** `wandb.Report` API + UI-side editor produces sharable analytic reports that embed run data live.

**Neptune Dashboards:** runtime-composable dashboards with linked widgets.

**Comet Reports:** similar.

**kailash-ml has:** No reports / exportable-analysis surface in `packages/kailash-ml/src/kailash_ml/dashboard/`. `server.py` serves the real-time dashboard; there is no `km.report(run_id)` nor `MLDashboard.export_report()` in the file listing.

**Severity:** MEDIUM — collaboration UX gap.

### M-4 — MEDIUM: No per-run system metrics (GPU util, memory, power) auto-capture at tracker level

**W&B does:** auto-captures GPU util, GPU memory, CPU, RAM, disk I/O, network. Shipped ~2020.

**Neptune / Comet / ClearML do:** equivalent hardware-metric auto-capture.

**kailash-ml does:** `_device_report.py` + `DeviceReport` envelope captures the device _once_ at run start (static snapshot). Per-step GPU util is not in the 17-field surface (runner.py:12-16 enumerates envelope fields, not time-series). Users who want "did I OOM this run?" or "was GPU util 30% because of a DataLoader bottleneck?" have no built-in path.

**Severity:** MEDIUM — a DL scientist's #2 diagnostic (after loss-curve).

### M-5 — MEDIUM: No run-compare UI (W&B Compare, MLflow compare, TensorBoard scalar compare)

**MLflow does:** select N runs → compare table + side-by-side metric charts.

**W&B does:** same, with parallel coordinates for HPO.

**TensorBoard does:** multi-run overlay.

**kailash-ml has:** `server.py` at 505 LOC; no evidence of a `/compare?run_ids=…` endpoint in the file listing. Would need grep of the server routes to be definitive.

**Severity:** MEDIUM — cross-run analysis is how ML scientists actually use dashboards.

### M-6 — MEDIUM: No offline-to-cloud sync story (W&B `WANDB_MODE=offline`, MLflow tracking URI swap)

Most 2026 ML runs are on isolated GPU nodes and must sync back later. W&B does this with `wandb sync`. MLflow does it by changing the tracking URI. Kailash-ml has two local SQLite files and no documented "swap backend to Postgres for team share" path. Brief §1 "Known real gaps" signals `~/.kailash_ml/ml.db` as the only default.

**Severity:** MEDIUM — team collaboration blocker.

### L-1 — LOW: No `wandb.init(tags=[...], group=..., job_type=...)` run-organization grammar

Minor but users expect to tag/group/filter. `km.track()` accepts `tenant_id` (from contextvars) but the spec-level tag/group/job_type grammar is not in the 17-field surface.

### L-2 — LOW: No "open run in UI" deep-link after `with km.track()` exits

W&B prints the run URL. Neptune prints the run URL. Comet prints the run URL. A 2026 ML scientist expects `--> https://.../run/abc123` in stdout. Training-data uncertainty on kailash-ml's stdout; would need to run once.

### L-3 — LOW: No notebook inline-cell widget (W&B `wandb.init()` renders an IFrame in Jupyter)

Non-critical but the notebook-inline UX pattern is what wandb owns in the market.

### L-4 — LOW: Name collision risk with `kailash-kaizen`, `kailash-align` diagnostic adapters

Brief mentions "DL/RAG/Alignment/Interpretability/LLM/Agent adapters exist" across kailash-kaizen/align and `kailash-ml/src/kailash_ml/diagnostics/`. If those adapters each emit to their own store (the same pattern as `km.track()` vs `MLDashboard`), the audit will find multiple sibling instances of H-1 across packages.

---

## Section C — 2026 table-stakes checklist

Every ML platform a new scientist installs in 2026 is expected to have each of these ON BY DEFAULT (no manual wiring). I mark each against kailash-ml current main.

| #   | Table-stakes feature                                                                 | kailash-ml status                           | Canonical reference product        |
| --- | ------------------------------------------------------------------------------------ | ------------------------------------------- | ---------------------------------- |
| 1   | One-line run context manager                                                         | PARTIAL (`km.track()` exists, not composed) | MLflow / W&B                       |
| 2   | `log_metric(key, value, step=)` on the run object                                    | **MISSING** (brief §2.2)                    | MLflow since 2018                  |
| 3   | `autolog()` or monkey-patch instrumentation for sklearn/torch/lightning/transformers | **MISSING**                                 | MLflow 2020 / ClearML 2019         |
| 4   | Dashboard reads the same store the tracker writes                                    | **BROKEN** (brief §2.1)                     | Everyone                           |
| 5   | Gradient / activation histograms → dashboard                                         | **MISSING** (brief §2.3)                    | TensorBoard 2016                   |
| 6   | RL reward-curve / policy-entropy / KL by default                                     | **MISSING** (brief §2.4)                    | RLlib / SB3 / CleanRL+W&B          |
| 7   | System metrics (GPU util, mem, power) per-run time-series                            | **MISSING** (static only)                   | W&B / Neptune / ClearML            |
| 8   | Artefact-typed tiles (image, confusion-matrix, PR curve)                             | UNCLEAR                                     | W&B / Comet / Neptune              |
| 9   | Hyperparameter sweep with trials auto-linked to parent run                           | PARTIAL (engine exists, no UX)              | W&B Sweeps / Optuna+MLflow         |
| 10  | Model registry with stage transitions (None → Staging → Production → Archived)       | PARTIAL (`model_registry.py` exists)        | MLflow / W&B Artifacts             |
| 11  | Model serving endpoint directly off a registered version                             | PARTIAL (`inference_server.py` exists)      | MLflow Model Serving / Ray Serve   |
| 12  | Data-distribution / feature drift monitor                                            | PARTIAL (`drift_monitor.py` exists)         | ClearML / EvidentlyAI / Neptune    |
| 13  | Feature store with offline+online parity                                             | PARTIAL (`feature_store.py` exists)         | Feast / Tecton / ClearML           |
| 14  | Run-compare UI (select N runs, overlay metrics)                                      | UNCLEAR                                     | MLflow / W&B / TB                  |
| 15  | Run URL printed on exit / notebook-inline widget                                     | UNCLEAR                                     | W&B / Neptune                      |
| 16  | Offline-first with explicit sync to shared backend                                   | **MISSING** (SQLite only)                   | W&B offline mode                   |
| 17  | Distributed training integration (DDP / FSDP / Lightning Fabric / Accelerate)        | PARTIAL (Lightning adapter)                 | Lightning / Accelerate / Ray Train |
| 18  | Data-version tagging (DVC / lakeFS / W&B Artifacts versioning)                       | UNCLEAR                                     | W&B / DVC                          |
| 19  | Lineage (which data → which run → which model → which deployment)                    | UNCLEAR                                     | ClearML / MLflow                   |
| 20  | Report / share URL that embeds live run data                                         | **MISSING**                                 | W&B Reports / Neptune Dashboards   |
| 21  | RLHF-adjacent logging (DPO / SFT / reward-model metrics)                             | PARTIAL (via Align)                         | HF TRL + W&B                       |
| 22  | Tool-use / multi-turn trajectory capture                                             | **MISSING**                                 | Emerging (LangSmith / Braintrust)  |
| 23  | Multimodal tiles (vision / audio / video)                                            | **MISSING**                                 | W&B / Comet                        |
| 24  | Python + notebook inline `display()` support                                         | UNCLEAR                                     | All                                |
| 25  | Auto-capture of `git status` + diff + commit SHA at run start                        | PARTIAL (DeviceReport captures some env)    | W&B / MLflow / ClearML             |

**Scorecard:** 4 MISSING, 3 BROKEN-or-PARTIAL-but-functionally-broken (#1, #4, #20), 9 PARTIAL-engine-exists-but-not-UX-composed, 9 UNCLEAR. **Zero** fully green.

A new ML scientist reading that row-by-row would close the tab.

---

## Section D — Differentiators kailash-ml _could_ lead on

These are angles where the competitor stack is structurally weaker AND kailash-ml has Foundation-level architectural machinery that could genuinely advance the state of the art if wired to the engine layer properly.

### D-1 — EATP governance at the run level (unique to the Foundation stack)

**Market gap:** No existing ML platform ships a first-class governance envelope on every experiment run. MLflow Gateway (Databricks) ships LLM-scoped governance, not run-scoped. W&B / Comet / Neptune have team/project ACLs, not fine-grained envelope-based policy. Model cards exist (HF Hub, ClearML) but are static documents, not runtime-enforced.

**What kailash-ml could do:** Every `km.track()` run emits an EATP D/T/R envelope (Dimensions / Thresholds / Responsibilities) that is part of the run's canonical surface. The envelope travels with the run through registry → serving → drift. Decision points (promote-to-prod, deploy-to-public-endpoint) consult `GovernanceEngine` before admitting the model.

**Why this is defensible:** The ecosystem is moving toward EU AI Act / NIST AI RMF compliance; every org is bolting governance _onto_ MLflow. Shipping it in the core run model is the generational move. **P1 differentiator** — but contingent on H-1 being fixed first.

### D-2 — Protocol-based diagnostic interop (unique: Foundation's `Protocol` usage)

**Market gap:** Every competitor's diagnostic layer is monolithic — `wandb.log({...})` hardcodes the W&B types. `mlflow.log_metric` hardcodes MLflow's store. TensorBoard's `SummaryWriter` hardcodes the TB file format. An ML scientist who wants to send a gradient histogram to BOTH W&B _and_ their internal governance bus writes the code twice.

**What kailash-ml could do:** Define a `DiagnosticEvent` Protocol (envelope + classification + payload) and have every engine emit it. Sinks (`km.track()` SQLite backend, W&B bridge, TensorBoard bridge, Prometheus bridge, EATP audit bridge) all consume the same event. Users register sinks declaratively.

**Why this is defensible:** None of the incumbents have an open protocol. The ecosystem has been waiting for one since OpenTelemetry ML-SIG discussions stalled in 2023. A clean Protocol contract with working adapters (MLflow / W&B / TB / Prometheus) would be a standard-setting move. **P2 differentiator.**

### D-3 — PACT-governed AutoML (unique: PACT D/T/R over hyperparameter search)

**Market gap:** AutoML today is a black box that asks "what's the best model?" A scientist running W&B Sweeps has no built-in answer to "am I allowed to train 500 trials on a production-class dataset?" or "do these candidate models respect our fairness envelope?" The answer is always "we audit at the end."

**What kailash-ml could do:** `km.sweep(...)` consults PACT before every trial. A trial that would violate a dimension (cost, latency, fairness, data-access) is skipped before it spins up. The UI shows skipped-trial provenance. Failed-to-admit trials feed back into the search space shrinker.

**Why this is defensible:** Reg-bound orgs (finance, healthcare, gov) will preferentially install a platform that blocks non-compliant trials at search time. No one else ships this. **P2 differentiator — blocked by H-1 + M-1.**

### D-4 — Engine-first RLHF + tool-use trajectories (2026 frontier, no incumbent)

**Market gap:** TRL ships DPO/SFT/PPO-RLHF but the tool-use + multi-turn trajectory format is still being invented (LangSmith, Braintrust, Phoenix, Weave). No incumbent has engine-first tool-call RL.

**What kailash-ml could do:** `km.align(...)` that speaks the tool-call-trajectory dialect natively — reward captured at the trajectory level, per-tool-call advantage, policy KL against the SFT baseline — with diagnostics auto-wired to the shared tracker.

**Why this is defensible:** This is the product category that will own 2026-2027. Being the first open-source stack with engine-first tool-call RLHF is strategically decisive. **P1 differentiator — blocked by H-4 first.**

### D-5 — DataFlow × ML lineage (unique: Foundation's DataFlow integration)

**Market gap:** Every lineage story in the market (ClearML, W&B Artifacts, MLflow's dataset tracking) is retrofit. The tracker doesn't know which table the training data came from because the training data came from pandas.

**What kailash-ml could do:** `km.train(model, dataset=db.query("SELECT ..."))` captures the exact DataFlow query, the snapshot ID, the classification policy applied, the tenant_id, and writes them to the run envelope. "Why did model v42 shift?" becomes a DataFlow query, not a postmortem.

**Why this is defensible:** Tight vertical integration with a first-party data layer is what no standalone tracker can offer. **P2 differentiator — contingent on H-1.**

### D-6 — Multi-backend dashboard (sink to Postgres / Redis / DataFlow instead of SQLite-only)

**Market gap:** W&B requires wandb.ai (or a paid on-prem install). MLflow self-host is possible but the UI is 2018-vintage. ClearML on-prem is heavy.

**What kailash-ml could do:** Dashboard reads from DataFlow (`dataflow.fabric` layer), which already supports Postgres / Redis / SQLite / fabric. A team upgrades from "SQLite in my home dir" to "Postgres shared backend" by flipping a connection string. The dashboard code doesn't change.

**Why this is defensible:** Upgrade path from solo to team without re-platforming. Incumbents force a cloud upgrade. **P2 differentiator — contingent on fixing H-1 via the right abstraction (not by bridging two SQLites).**

---

## Bottom line for this persona

**Where kailash-ml is ahead:** Nothing user-observable today. The Foundation-layer architectural machinery (EATP, PACT, DataFlow, Protocol-based Kailash Core) is genuinely novel and no incumbent has an equivalent. But none of it is composed into the engine-first ML UX yet.

**Where kailash-ml is at parity:** The engine file listing shows every competitor's engine category (registry, AutoML, drift, feature store, inference server). At the file-existence level it looks credible.

**Where kailash-ml is behind:** Every observable UX pattern that ships on day 0 with MLflow / W&B / Lightning / HF `Trainer` / Ray Tune. The tracker-dashboard split (H-1) is decisive; `log_metric` absence (H-2) is a second decisive failure; no `autolog()` (H-5) is a third. Each of these is a sub-5-minute bounce trigger for a 2026 ML scientist evaluating on a Friday afternoon.

**The single highest-leverage fix** is H-1 (one shared store, tracker and dashboard and diagnostics all speak to it). H-2, H-3, H-4, H-5 compound on top of that. Until H-1 is solved, the differentiators in Section D are architectural PowerPoint — not UX reality.

**Recommended audit disposition:** HIGH findings H-1, H-2, H-3, H-4, H-5 are all blocking for "industry-benchmark pass" per the brief's Success Criterion #4. Round 2 cannot declare convergence without concrete fixes landed for H-1–H-5. Section C's MISSING-or-BROKEN items (#2, #3, #4, #5, #6, #7, #16, #20, #22, #23) should be rolled up into todos for phase 02.

---

**Report path:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-1-industry-competitive.md`
