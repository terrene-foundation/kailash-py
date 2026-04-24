# Round 9 — /todos Plan Red Team Synthesis

**Date:** 2026-04-21
**Inputs:** `round-9-reviewer-plan-redteam.md` (reviewer) + `round-9-analyst-failure-points.md` (analyst)
**Scope:** 34-wave shard plan for kailash-ml 1.0.0 + 7-package atomic wave release

## Aggregate verdict: APPROVE with amendments

Both red-team agents converge: the plan is structurally coherent and every decision traceable, but SHIPS with real structural drift that `/implement` cannot recover from once shards launch. Amendments are mostly mechanical (symbol renames, wiring-test file-name convention, sub-shard splits) but load-bearing — without them, spec drift + orphan-class risk + capacity-budget overflow + release rollback ambiguity all leak past `/redteam` into `/release`.

## Convergent findings (both agents)

| Theme                                                                         | Reviewer finding                              | Analyst finding                                   |
| ----------------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------- |
| **Orphan-risk: manager-facades without wiring tests**                         | MED-6 (21 manager classes, only W32 explicit) | FP-HIGH-1/2/3 (W10, W16, W17, W22, W25, W26, W27) |
| **Capacity-budget: W19, W20, W33 over budget**                                | MED-1/2/3                                     | FP-HIGH-4 + FP-MED-9                              |
| **W31/W32 parallel worktree version ownership + CHANGELOG collision**         | MED-7                                         | FP-HIGH-6                                         |
| **Migration identifier-length audit + cross-failure recovery**                | MED-5                                         | FP-HIGH-7 + FP-MED-1                              |
| **Cross-SDK parity gaps (SeedReport, Trajectory, EngineInfo, run lifecycle)** | —                                             | FP-MED-8 + FP-LOW-5                               |

## Divergent findings — reviewer-unique

Reviewer identifies **symbol-level spec drift** on the 6 integration specs that the analyst did not surface:

### HIGH-R1 — Load-bearing location conflict: kailash-core vs kailash-ml

`specs/kailash-core-ml-integration.md §1.1` mandates FIVE surfaces live in **kailash core** (not kailash-ml):

1. `src/kailash/diagnostics/protocols.py` — expand with `RLDiagnostic` Protocol + `DiagnosticReport` dataclass.
2. **`src/kailash/ml/errors.py`** — `MLError` hierarchy lives in **kailash**, kailash-ml RE-EXPORTS. Plan's W1 placed it in kailash-ml — direct conflict.
3. **`src/kailash/tracking/migrations/`** — numbered migration helpers live in **kailash**. Plan's W3/W4 placed them in kailash-ml/migrations — direct conflict.
4. `kailash.workflow.nodes.ml` — `MLTrainingNode`, `MLInferenceNode`, `MLRegistryPromoteNode`. Plan's W31 named `TrainNode`, `PredictNode`, `ServeNode` — different symbols.
5. `kailash.observability.ml` — OTel/Prometheus counters. Zero wave declares this.

**Verified** via `specs/kailash-core-ml-integration.md` §1.1 + §3-§6.

### HIGH-R2 — W31 DataFlow integration symbol drift

`specs/dataflow-ml-integration.md §1.1` mandates: `dataflow.ml_feature_source(feature_group)`, `dataflow.transform(expr, source)`, `dataflow.hash(df)`. Plan named `TrainingContext`, `lineage_dataset_hash`, `_kml_classify_actions` — right concepts, wrong symbols.

### HIGH-R3 — W31 Nexus integration symbol drift

Spec mandates: `kailash_nexus.context._current_tenant_id` + `_current_actor_id` ContextVars, `MLDashboard(auth="nexus")` validator adapter, inference-endpoint tenant propagation. Plan named `UserContext` + `mount_ml_endpoints` + `dashboard_embed` — right direction, missing specific symbols.

### HIGH-R4 — W32 Kaizen integration missing `tracker=` kwarg + auto-emission

Spec `§1.1` mandates `tracker=Optional[ExperimentRun]` kwarg on `AgentDiagnostics`/`LLMDiagnostics`/`InterpretabilityDiagnostics` + auto-emission from every `record_*/track_*` method when ambient tracker present — "no opt-in, no configuration flag". Plan omitted both.

### HIGH-R5 — W30/W32 align integration: 4 TRL adapters unnamed

Spec mandates 4 concrete `RLLifecycleProtocol` adapters: `DPOTrainer`, `PPOTrainer`, `RLOOTrainer`, `OnlineDPOTrainer`. Plan named only "LoRA Lightning callback" + shared `Trajectory`.

### HIGH-R6 — W32/W27 PACT integration: 3 governance methods unnamed

Spec mandates `check_trial_admission`, `check_engine_method_clearance`, `check_cross_tenant_op`. Plan named only `ml_context` + `ClearanceRequirement` + governance-gated AutoML.

## Divergent findings — analyst-unique

### HIGH-A5 — W34 atomic release: 6-upload partial-success window

PyPI has no cross-package transaction. Uploads 2-6 failing require full yank+bump. Plan lacks:

- Pre-flight all 7 builds + TestPyPI dry-run before real uploads
- Per-upload PyPI JSON + clean-venv verification loop
- Documented rollback decision tree

### MED-A2 — `km.erase_subject` location ambiguity

W15 says `km.erase_subject` is a module-level wrapper, but W33's `__all__` list doesn't include it. Either add to `__all__` or clarify as `ExperimentTracker` method.

### MED-A3 — W21 forward reference to W31

W21 T2 test "full Quick Start to `/health → 200`" requires W31 (Nexus ml-endpoints) which lands later. Test downgrades to direct-channel OR moves to W31.

### MED-A4 — W20 auto-checkpoint vs W23 autolog ordering race

Both patch `L.Trainer.callbacks`. Ordering matters; neither wave specifies.

### MED-A5 — W9 parallel adapters drift `accelerator=auto`

4 parallel sub-shards each own `accelerator` dispatch. Shared base must land first.

### MED-A7 — W30 must sweep existing align `Trajectory` in same commit

Dual-definition risk per `orphan-detection.md §4`.

## Decision required from human

**Q: Accept reviewer HIGH-R1 spec mandate — MLError + migrations + nodes + observability in kailash CORE, re-exported from kailash-ml?**

This is load-bearing for every other wave that imports MLError. Two options:

**Option A (ACCEPT spec — recommended):**

- Move MLError hierarchy from `kailash-ml/src/kailash_ml/errors.py` to `src/kailash/ml/errors.py` in kailash core (W1 relocated).
- Move migrations from `packages/kailash-ml/migrations/` to `src/kailash/tracking/migrations/` (W3/W4 relocated).
- Rename W31 nodes to spec-mandated names (`MLTrainingNode`, `MLInferenceNode`, `MLRegistryPromoteNode`).
- Add new wave (W31-a) for `kailash.observability.ml` OTel/Prometheus module.
- `kailash-ml` re-exports all four surfaces.

**Option B (DEVIATE from spec):**

- Update 6 integration specs to match plan (W1 in kailash-ml, W3/W4 in kailash-ml/migrations).
- Requires spec-change PR + `specs-authority.md §6` deviation logging + 5b sibling sweep.
- Risk: spec-drift compounding across sibling specs.

## Proposed amendments (Option A assumed)

### 1. Location corrections (HIGH-R1)

- **W1** → move MLError hierarchy to `src/kailash/ml/errors.py`. Add W1b: `kailash_ml.errors` re-exports from `kailash.ml.errors`.
- **W3 + W4** → move migrations to `src/kailash/tracking/migrations/`.
- **W31 31a** → rename nodes to `MLTrainingNode`, `MLInferenceNode`, `MLRegistryPromoteNode`.
- **NEW W31-aOBS** → sub-shard for `kailash.observability.ml` OTel/Prometheus module (spec `§6`).

### 2. Sub-shard splits (capacity budget — analyst FP-HIGH-4, reviewer MED-1/2/3)

- **W19 → W19a + W19b** — W19a init+DI+zero-arg; W19b setup+compare.
- **W20 → W20a + W20b** — W20a fit+predict; W20b finalize+evaluate+lr_find.
- **W27 → W27a + W27b** — W27a AutoMLEngine; W27b FeatureStore.
- **W33 → W33a + W33b** — W33a wrappers+`__all__`+registry; W33b MIGRATION.md+README+regression.

New total: **38 waves** (34 + 4 splits). IT tasks unchanged.

### 3. Orphan wiring tests (analyst FP-HIGH-1/2/3, reviewer MED-6)

Add explicit `tests/integration/test_<name>_wiring.py` file-name convention to 21 waves' DoDs: W10, W14, W16, W17, W19a, W19b, W22, W24, W25, W26, W27a, W27b, W28, W29.

### 4. Parallel-worktree ownership (reviewer MED-7, analyst FP-HIGH-6)

- **W34 = sole kailash-ml CHANGELOG owner.** W31/W32/W33 MUST NOT edit `packages/kailash-ml/CHANGELOG.md` — pass bullet text via PR description only.
- W31 31a → explicit version owner for `src/kailash/__init__.py::__version__` (currently missing).
- Extras pins use `>=` not `==` (all waves).
- Master plan adds relative-path-only discipline (per `worktree-isolation.md §4`).

### 5. W34 atomic release rollback protocol (analyst FP-HIGH-5)

New W34 invariants:

- **Pre-flight all 7 builds** — every package `python -m build` + `twine check dist/*` BEFORE first real upload.
- **TestPyPI dry-run per package** — all 7 before real uploads.
- **Per-upload verification loop** — PyPI JSON retry + clean-venv install + import; HALT on failure.
- **Documented rollback decision tree** — uploads 2-6 fail → yank 1..N-1 + bump patch + retry.
- **Idempotent publish workflow** — re-run after partial failure either succeeds or retries cleanly.

### 6. Migration identifier-length audit (analyst FP-HIGH-7, reviewer MED-5)

- W4 invariant — every `CREATE INDEX` name ≤63 chars enforced via `quote_identifier`.
- W4 unit test — enumerate every index name + assert length.
- W4 regression test — `test_migration_0002_resumes_after_partial.py` for cross-migration failure.
- W4 grep gate — zero raw-f-string identifier interpolation in migration file.

### 7. Symbol-level spec conformance (reviewer HIGH-R2..R6)

- **W31 31b** — add `dataflow.ml_feature_source`, `dataflow.transform`, `dataflow.hash` to deliverable.
- **W31 31c** — add `kailash_nexus.context._current_tenant_id`/`_current_actor_id` ContextVars, `MLDashboard(auth="nexus")` adapter.
- **W32 32a** — add `tracker=Optional[ExperimentRun]` kwarg on Agent/LLM/Interpret diagnostics + auto-emission invariant.
- **W30 + W32 32b** — enumerate 4 TRL adapters (`DPOTrainer`, `PPOTrainer`, `RLOOTrainer`, `OnlineDPOTrainer`) per `align-ml-integration §1.1`.
- **W32 32c** — enumerate 3 PACT methods (`check_trial_admission`, `check_engine_method_clearance`, `check_cross_tenant_op`) + call-site wiring in W16, W18, W20, W27a.

### 8. Forward-reference + ordering cleanup

- **W21** T2 downgrades to direct-channel predict; REST/MCP testing moves to W31.
- **W9** — shared `LightningAdapterBase` serial, THEN 4 family sub-shards parallel.
- **W20 + W23** — autolog vs auto-checkpoint ordering: W20 T2 includes `km.autolog` already enabled; W23 T2 includes autolog called mid-flight.
- **W30 DoD** — grep existing `class Trajectory` in kailash-align + delete/port every definition + test in same commit.
- **W15** — clarify `km.erase_subject` location; if module-level add to W33a `__all__`.

### 9. Cross-SDK parity

- **W5, W11, W30, W33a** — DoDs include "kailash-rs#502 updated with Python canonical shapes."
- **W11 T2** — assert observable-equivalence fields per Rust parity doc.

### 10. Testing rigor

- **W2 tests** — env-var isolation per `testing.md § Env-Var Test Isolation` (`threading.Lock` + `monkeypatch.setenv`).
- **W14 DDP test** — clarify "2-rank mock" is Protocol-conforming deterministic adapter (NOT MagicMock).
- **Master plan** — `pytest --collect-only` merge gate added to W34 DoD.

### 11. Minor items

- **W6** — W34 verifies `backend-compat-matrix.yaml` installability.
- **W13** — pin polars column set explicitly.
- **W22** — `[dl]` absence raises typed `DiagnosticsError`.
- **W28** — notebook kernel-restart thread cleanup documented.
- **W33b** — `km.resume(tolerance=...)` tolerance T2 case.
- **LOW-4** — W34 Terrene Foundation naming grep gate (`rg 'partnership|proprietary|commercial version' packages/kailash-ml/` empty).
- **MED-9** — W2 specifies `KAILASH_ML_STRICT_ENV=1` flag for deprecation sunset.

## Risk Register (Post-Amendment)

| Risk                                   | Severity | Mitigation                             | Residual |
| -------------------------------------- | -------- | -------------------------------------- | -------- |
| Spec drift on 6 integration specs      | HIGH     | Amendments §1, §7                      | LOW      |
| Orphan manager-classes                 | HIGH     | Amendments §3 wiring-test convention   | LOW      |
| Capacity-budget overflow mid-implement | HIGH     | Amendments §2 sub-shard splits         | LOW      |
| Atomic release partial success         | HIGH     | Amendments §5 rollback protocol        | LOW      |
| Parallel-worktree version drift        | HIGH     | Amendments §4 ownership discipline     | LOW      |
| Migration cross-failure stuck DDL      | HIGH     | Amendments §6 index audit + regression | LOW      |
| Cross-SDK semantic drift               | MED      | Amendments §9 parity docs              | LOW      |
| Autolog × auto-checkpoint race         | MED      | Amendments §8 T2 ordering cases        | LOW      |

## Next step

Human decision on HIGH-R1 (Option A accept spec vs Option B deviate) + acknowledgment of amendments list. With Option A + amendments applied, the plan is APPROVE for `/implement` and will not ship the three structural failure modes identified (Phase-5.11 orphan pattern, capacity-budget overflow, atomic-release partial state).
