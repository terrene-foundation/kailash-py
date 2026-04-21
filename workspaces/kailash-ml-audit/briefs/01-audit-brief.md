# Brief — Full ML/DL/RL Lifecycle Red-Team Audit

## Mandate

Red-team kailash-ml (and connected diagnostic adapters in kaizen/align) across the ENTIRE ML/DL/RL lifecycle — from a fresh data scientist's first `import` through production serving — until convergence with ZERO gaps.

## Non-negotiables

1. **Engine-first** — a new data/ML/DL/RL scientist must get production-grade results WITHOUT touching primitives. Primitive composition is for seasoned practitioners who explicitly drop below the engine layer.
2. **Seamless + auto** — the happy path MUST NOT require users to wire a tracker into a dashboard into a diagnostics class into a visualizer. The engine does that wiring.
3. **One entry per concern** — one canonical way to run training, one canonical way to run diagnostics, one canonical way to view the dashboard. No parallel implementations.
4. **Full lifecycle coverage** — classical ML, deep learning, reinforcement learning, AutoML, inference serving, drift monitoring, feature stores, experiment tracking, model registry, explainability/interpretability.
5. **No fake/orphan components** — per `rules/zero-tolerance.md` Rule 2 + `rules/orphan-detection.md`. `MLDashboard` + `km.track()` + `DLDiagnostics` currently do not compose. That is a Rule 2 violation.

## Known-real gaps (from 2026-04-21 MLFP-dev review)

The MLFP-dev review that triggered this audit surfaced four concrete gaps we MUST close:

1. **Two trackers, two DBs.** `km.track()` → `SQLiteTrackerBackend` → `~/.kailash_ml/ml.db`. `MLDashboard` → `ExperimentTracker` engine → `sqlite:///kailash-ml.db`. Different classes, different files. A `km.track()` run is invisible to `MLDashboard`.
2. **`ExperimentRun` has no `log_metric`.** Only `log_param` / `log_params` / `attach_training_result`. The ENGINE-LAYER `ExperimentTracker` has `log_metric` — but users calling `km.track()` never reach it.
3. **`DLDiagnostics` is an island.** No `tracker=` kwarg, no event sink. Its `plot_training_dashboard()` emits inline Plotly only; nothing propagates to `MLDashboard`.
4. **No RL diagnostics exist.** DL/RAG/Alignment/Interpretability/LLM/Agent adapters exist; RL is completely absent.

## Out-of-scope (for THIS audit)

- Rewriting the engine-vs-primitive hierarchy (that's `rules/framework-first.md`; still load-bearing).
- kailash-kaizen LLM deployment abstraction (shipped 2.11.0 in this session).
- kailash-pact GovernanceEngine extensions (shipped 0.9.0 earlier).

## Success criteria

1. Every spec promise in `specs/ml-*.md` verified via grep/AST (NOT file existence). Assertion table in `.spec-coverage-v2.md`.
2. Every lifecycle stage (training, evaluation, deployment, monitoring) has an engine-layer entry point that a newbie can call in ONE line.
3. Diagnostic coverage matrix: classical ML × DL × RL × feature engineering × serving × drift × interpretability — every cell has either (a) an engine-layer adapter that emits to the shared tracker OR (b) a documented "not applicable" rationale.
4. Industry benchmark pass — against mlflow, wandb, tensorboard, kubeflow, ray, comet, neptune, clearml. Where we're engine-first-better, highlight. Where we're behind, log a GAP.
5. 2 consecutive clean rounds of red-team audit with 0 HIGH/CRIT findings.
6. No orphans per `rules/orphan-detection.md` — every `db.x` / `km.x` / `MLDashboard.x` facade has a production call site AND a Tier 2 wiring test.

## Convergence protocol

Iterate in rounds. Each round:

- 6 persona agents in parallel (see Panel below)
- Aggregate findings into `04-validate/round-N-findings.md`
- Fix all HIGH/CRIT findings OR create explicit deferred-item tickets
- Re-run the round

Declare convergence when TWO consecutive rounds produce zero new HIGH/CRIT findings.

## Expert panel (6 personas, parallel audit)

1. **Spec-compliance analyst** — AST/grep verification of every `specs/ml-*.md` promise.
2. **New data-scientist UX auditor** — day-0 onboarding: "can I fit + eval + see a dashboard in 5 lines without reading 10 docs?"
3. **Deep-learning researcher** — gradient/activation/dead-neuron diagnostics + training dashboard + event-sink to tracker.
4. **Reinforcement-learning researcher** — RL lifecycle is MISSING; audit the full gap (environment abstraction, rollout buffer, Q/value/policy logging, reward tracking, replay stats, TRL/RLHF integration with align).
5. **MLOps / production engineer** — inference server, drift monitor, model registry, AutoML, feature store; engine-to-primitive layering; Ray/Kubeflow parity.
6. **Industry / competitive auditor** — against mlflow, wandb, tensorboard, comet, neptune, clearml, kubeflow, ray-train, fastai; which "best practice" entry points are we missing?

Each persona produces a HIGH/MED/LOW finding list with grep-verified line references. No hand-waving.
