# Round-1 Synthesis — ML/DL/RL Lifecycle Red-Team

**Date:** 2026-04-21
**Scope:** kailash-ml + connected diagnostic adapters (kaizen.observability / kaizen.interpretability / kaizen.judges / kailash-align.diagnostics) + shared `src/kailash/diagnostics/protocols.py`.
**Round-1 agents:** 6 personas run in parallel. Full per-persona reports at `round-1-{spec-compliance, newbie-ux, dl-researcher, rl-researcher, mlops-production, industry-competitive}.md`.

## Aggregate counts

| Persona                | CRIT   | HIGH   | MED     | LOW     |
| ---------------------- | ------ | ------ | ------- | ------- |
| Spec-compliance        | 4      | 9      | 2       | 0       |
| Newbie UX              | 1      | 8      | 2       | 2       |
| DL researcher          | 0      | 9      | 4       | 2       |
| RL researcher          | 2      | 15     | 5       | 0       |
| MLOps production       | 4      | 9      | ≥4      | ≥2      |
| Industry competitive   | 1      | 4      | 6       | 4       |
| **TOTAL (unique-ish)** | **12** | **54** | **≥23** | **≥10** |

Convergence gate (`/redteam`): 0 CRIT + 0 HIGH + 2 consecutive clean rounds. **Round 1 is catastrophically far from convergence.** There are 66 HIGH+CRIT findings spread across 7 recurring themes.

## Seven recurring themes (ranked by dependency order — fix top-down)

### T1. Two-tracker split [CRIT × 5 personas]

| Component                                               | Store                     | Has `log_metric`? |
| ------------------------------------------------------- | ------------------------- | ----------------- |
| `km.track()` → `ExperimentRun` + `SQLiteTrackerBackend` | `~/.kailash_ml/ml.db`     | **NO**            |
| `MLDashboard` → engine-layer `ExperimentTracker`        | `sqlite:///kailash-ml.db` | YES               |

Verification: `grep -rn 'def log_metric' packages/kailash-ml/src/kailash_ml/tracking/` → EMPTY. `tracking/runner.py:74` vs `dashboard/__init__.py:46` — two different DB defaults. `dashboard/server.py:440` imports `ExperimentTracker`, NOT `SQLiteTrackerBackend`.

A `km.track()` run is invisible to `MLDashboard`. This is the root blocker: 6 of 13 MLOps findings + 5 of 13 Newbie-UX findings + 4 of 12 industry-competitive findings + every DL diagnostic finding chains off this gap.

### T2. Engine ↔ tracker wiring is 0/13 auto [CRIT MLOps, HIGH others]

MLOps matrix (18 engine classes): **0/18 auto-wire to `km.track()`**; **3/18 accept `tracker=`**. The 13 flagship engines (TrainingPipeline, InferenceServer, ModelRegistry, FeatureStore, DriftMonitor, AutoML, HyperparameterSearch, Ensemble, et al.) are research-quality in isolation but do not emit lifecycle events anywhere the tracker/dashboard reads.

`DLDiagnostics` is the canonical example: 1,938 LOC with 8 `plot_*` methods — `grep "log_metric|emit_event|self._tracker|tracker=" diagnostics/dl.py` returns ZERO matches. Classic Phase 5.11 orphan pattern (`rules/facade-manager-detection.md` §1 violation).

### T3. Tenant isolation absent from 13/13 engines [CRIT MLOps]

`rg tenant_id packages/kailash-ml/src/kailash_ml/engines/` returns ZERO matches across the production engines. Only scaffold code + `tracking/` module has it. `rules/tenant-isolation.md` MUST Rules 1-5 violated at near-100%. No actor_id on any mutation → cannot answer "who promoted v7 to production?"

### T4. RL is a pinned orphan [CRIT RL × 2]

Brief's KR4 ("No RL diagnostics exist") UNDER-states the problem. RL module exists (`kailash_ml/rl/`) but `tests/regression/test_rl_orphan_guard.py` explicitly ASSERTS:

- `RLTrainer` has zero production call sites
- RL symbols absent from `kailash_ml.__all__`
- `RLTrainer` does not consult `detect_backend()`
- Zero engine integration

Capability score vs SB3 baseline: **4 of 21** — framework-first value prop inverted. Worse: `kailash-align` has TRL RLHF (`DPOTrainer`, `PPOTrainer`, `RLOOTrainer`) with ZERO shared abstraction with `kailash_ml.rl`.

### T5. Two model registries, two lifecycles [CRIT MLOps]

`MLEngine._kml_engine_versions` (tenant-aware scaffold; raises `NotImplementedError`) vs `ModelRegistry._kml_model_versions` (single-tenant, production). Classic Phase 5.11 parallel-facade orphan pattern.

### T6. Spec-to-code drift [CRIT spec-compliance × 4]

- 9 of 12 typed exceptions declared in `specs/ml-tracking.md §11.1` are absent from code.
- `search_runs` returns `list[Run]` not `polars.DataFrame` (§2.6 violation).
- `sqlite+memory` alias missing (§2.7 + §9.1).
- `diff_runs` / `class RunDiff` / `TrackerMCPServer` / `import_mlflow` — grep returns EMPTY.
- Shared-keyspace `kailash_ml:v1:{tenant_id}:{resource}:{id}` absent (§6.1 violation).
- Cross-spec consistency: `ml-tracking.md` v2.0.0-draft vs `ml-diagnostics.md` v0.17.0-LIVE — same package, two claims; `rules/specs-authority.md` §5b violation.

### T7. Industry parity sub-MLflow-1.0-2018 [CRIT industry × 5 HIGH]

2026 table-stakes scorecard: 0 of 25 fully green. Missing or broken:

- No `km.autolog()` — MLflow has had this since 2019; ClearML, Comet, Neptune all ship it
- No sweeps / HPO UI
- No artifact management (images, confusion matrices, summary stats) tied to runs
- No system-metrics panel (CPU, GPU, memory, disk, network)
- No run-compare UI
- No offline / buffered sync
- No `report()` / notebook widget
- No deep-link URLs for runs

Every architectural differentiator in Section D (EATP run-level governance, Protocol-based diagnostic interop, PACT-governed AutoML, engine-first RLHF, DataFlow×ML lineage) is PowerPoint until T1 is fixed.

## Non-convergence call

Round 1 found 12 CRIT + 54 HIGH. Convergence requires 0+0 across **2 consecutive** clean rounds. **Round 1 closes zero findings. Round 2+ MUST run AFTER remediation, not before.**

## Remediation sharding (per `rules/autonomous-execution.md` capacity bands)

The 7 themes collapse into **9 implementation shards**. Each ≤500 LOC load-bearing, ≤5-10 invariants, ≤3-4 call-graph hops, describable in 3 sentences. Ordered by dependency so each shard unblocks the next.

**Tier-A (blocks everything; MUST merge first):**

1. **SHARD-A1: Unify the tracker store.** Choose `ExperimentTracker` engine as canonical (it already has `log_metric`, `log_metrics`, `list_runs`, `search_runs` with polars return). `km.track()` migrates to it. `SQLiteTrackerBackend` becomes a thin pass-through OR is deleted. One DB path `~/.kailash_ml/ml.db`. `MLDashboard` CLI default updated to match. Migrate any kailash-py code referencing `SQLiteTrackerBackend` to the engine layer. Regression test: a `km.track()` run appears in `MLDashboard` within 1 second. ~400 LOC.

2. **SHARD-A2: `ExperimentRun.log_metric(key, value, *, step=None)` + `log_metrics(mapping, *, step=None)`.** After A1, `ExperimentRun` wraps the engine and exposes the same metric API. Signature matches `specs/ml-tracking.md §2.5`. ~80 LOC + Tier 1 + Tier 2 tests against the shared store.

**Tier-B (lifecycle auto-wire; depends on A):**

3. **SHARD-B1: `DLDiagnostics(*, tracker=None)` auto-emit.** Accepts an `ExperimentRun` via kwarg OR reads the ambient `km.track()` contextvar (the `track()` async context manager already sets a contextvar per `tracking/runner.py`). On every `record_batch` / `record_epoch`, emit matching `log_metric` calls. `plot_training_dashboard()` stays as the inline-plotly path for notebook users. ~200 LOC + Tier 2 wiring test.

4. **SHARD-B2: `km.diagnose(run_or_result)` engine entry point.** One-line dispatcher: inspect the `Trainable`/`TrainingResult`/run type and run the appropriate adapter (DLDiagnostics for torch/Lightning trainables; sklearn-style diagnose_classifier/regressor for classical; `RLDiagnostics` stub for RL placeholder). Renders a single plotly dashboard AND emits events to the ambient tracker. ~300 LOC + Tier 2.

5. **SHARD-B3: `km.autolog()` integration.** Contextvar-based auto-instrumentation: inside a `with km.track(): km.autolog(): model.fit(...)` block, hook Lightning callbacks / sklearn.fit wrappers / transformers Trainer callbacks so metrics flow without user code. Parity with MLflow autolog. ~350 LOC + per-framework integration tests.

**Tier-C (production hardening; depends on A):**

6. **SHARD-C1: Plumb `tenant_id` through 13 engines.** Every engine constructor accepts `tenant_id` kwarg. Every storage key includes the tenant dimension (`kailash_ml:v1:{tenant_id}:...`). Every audit row persists it. Mechanical but invariant-heavy — split into 2-3 sub-shards if needed. ~500 LOC across engines + conftest + regression tests.

7. **SHARD-C2: Unify the two model registries.** `MLEngine._kml_engine_versions` deleted; `ModelRegistry` becomes the sole path with tenant_id + actor_id added. Remove the `NotImplementedError` raise. Regression tests cover the delete-vs-merge decision documented in the PR body. ~400 LOC.

8. **SHARD-C3: `actor_id` + audit trail on every mutation.** Register/promote/demote/delete all require `actor_id` kwarg. Audit row: `(timestamp, actor_id, tenant_id, resource_kind, resource_id, action, prev_state, new_state)`. Indexed on `tenant_id + actor_id + timestamp`. ~250 LOC + integration test.

**Tier-D (RL lifecycle; depends on A + B):**

9. **SHARD-D1: RL unification + `km.rl_train()` + `RLDiagnostics` + TRL alignment.** Decide delete-or-wire for `kailash_ml/rl/`. If wire: unify with `kailash-align.method_registry` RLHF trainers via a shared `RLLifecycleProtocol`. Add `RLDiagnostics(env, policy, *, tracker=None)` adapter emitting reward/entropy/KL/advantage to the shared tracker. Add `km.rl_train(env, policy, algo='ppo')` one-line entry. Remove the `test_rl_orphan_guard.py` pinning — it's now an anti-regression asserting the OPPOSITE (wired + production). ~600 LOC → SPLIT into D1a (delete-or-wire decision + core migration) + D1b (RLDiagnostics + km.rl_train). Each ~300 LOC.

## Execution plan

- **Sessions 1-2:** Tier-A shards (A1 + A2). Close T1 root gap. All Tier-B/C/D depend on this.
- **Session 3:** Tier-B shard B1. Unlocks DL researcher use case (#1 severity gap for MLFP course).
- **Session 4:** Tier-B shards B2 + B3 in parallel (different surfaces). Unlocks newbie-UX + industry parity.
- **Session 5-6:** Tier-C shards C1 + C2 + C3 in parallel (tenant + registry + audit). Unlocks MLOps production.
- **Session 7-8:** Tier-D shards D1a + D1b. Unlocks RL + TRL parity.
- **Session 9:** Spec update — align `specs/ml-tracking.md` + `specs/ml-diagnostics.md` to shipped code; add RLDiagnostics + tracker unification narratives.
- **Session 10:** Round-2 /redteam against fixed main.
- **Session 11:** Round-3 /redteam (convergence confirmation).

Each session = 1-3 shards per `autonomous-execution.md` 10× multiplier. Parallelism via worktree-isolation per `agents.md` § "Parallel-Worktree Package Ownership Coordination" — all shards touch `kailash-ml` so version-owner coordination is required.

## Decision gates (structural — human required)

Per `autonomous-execution.md` § Structural vs Execution Gates:

- **Gate 1:** Approve the shard plan above (this PR). Unlocks Session 1.
- **Gate 2 (at end of Tier-A, ~Session 2):** Approve T1 fix + version bump direction. kailash-ml 0.17.0 → 0.18.0 (minor: new `log_metric` API, unified store) OR 0.17.1 (patch: store alias + bridge). Recommend 0.18.0.
- **Gate 3 (at end of Session 8):** Approve overall direction before round-2 audit. Confirm no additional theme emerged that needs a new Tier.
- **Gate 4 (round-3 convergence):** Ship kailash-ml 0.18.0 or 1.0.0 (semver decision — this is the first time the package is actually composed).

## Success metrics

- **Code:** 0 HIGH+CRIT findings across 2 consecutive round-N audits.
- **UX:** Newbie scenario executes in ≤5 lines of user code (fit → track → diagnose → dashboard). Measured via a literal 5-line e2e test.
- **Industry:** At least 18 of 25 2026 table-stakes checkbox features present (currently 0). Target full 25 over two follow-on releases.
- **Spec:** Every `specs/ml-*.md` assertion grep-verified; zero drift per `rules/specs-authority.md` §5b.

## Out of scope (for THIS audit)

- kaizen-llm-deployments v2.11.0 (shipped earlier this session).
- pact-absorb-capabilities (shipped earlier).
- align RLHF integration beyond protocol alignment (full deep integration is D1's scope; advanced features are follow-on).

## Round-2 entry criteria

Round 2 starts after Tier-A merges (Session 2 complete). Round 2 verifies T1 + T2 closed and confirms the rest remain findings or regressed. Round 3 after Tier-D, full sweep.
