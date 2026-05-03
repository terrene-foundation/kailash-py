# Round 9 — Analyst failure-point red team

**Date:** 2026-04-21
**Persona:** Failure-point analyst (analyst agent)
**Input:** 34-wave plan + 34 todo shards + Round-8 SYNTHESIS + 14 approved decisions + 4 load-bearing rules
**Output:** `workspaces/kailash-ml-audit/04-validate/round-9-analyst-failure-points.md`

## Verdict: APPROVE with risks — 7 HIGH / 11 MED / 6 LOW must be mitigated before `/implement`

The plan is spec-convergent (Round-8 certified) and shard-budget-respectful at the top level, but carries concrete autonomous-execution failure modes that Round 8 did not address because Round 8 was scoped to spec-level readiness, not implementation orchestration. The seven HIGH findings below are all structural — they cannot be fixed inside `/implement` without aborting the in-flight shard. They MUST be amended into the plan or the todo shards before the first worktree launches.

---

## Failure point catalogue (HIGH / MED / LOW severity)

### FP-HIGH-1 — W10 ExperimentTracker facade ships with no same-wave wiring test; orphan risk Phase-5.11 class

**What fails:** W10 creates `ExperimentTracker.create(store_url)` + `ExperimentRun` as the canonical async-context surface. Tests listed are "factory + nested-run guard" (T1) + "signal handler round-trip" (T2). There is NO test that exercises the hot path from `km.train(...)` → `MLEngine.fit()` → `ExperimentRun.log_metric()` through the real facade. W11 (status transitions) and W12 (logging primitives) land in subsequent shards, but the tracker instance itself is a manager-shape class (`ExperimentTracker`) and a manager-shape wrapper (`ExperimentRun`) per `rules/facade-manager-detection.md §1`. Round 8's closure verification (24/24 GREEN) certified that the spec mentions a `test_*_wiring.py`, not that W10's todo has one in its T2 list.

**Where:** `todos/active/W10-experiment-tracker-factory.md` Tests section. Phase 5.11 orphan was 2,407 LOC of trust integration that the production hot path never invoked; W10 carries the identical shape (manager-facade on the framework's top-level instance, no same-PR hot-path call site).

**Probability:** HIGH. `rules/orphan-detection.md §1` requires the call site within the same PR. W10 blocks W11/W19/W21, and those waves will have to wire backwards into W10's facade. The wiring test belongs in W10 to close the orphan window; deferring to W19 (5 waves later) is exactly the deferred-wiring pattern the rule prohibits.

**Mitigation:** Add to W10 `Tests` section: "T2 wiring — `tests/integration/test_experiment_tracker_wiring.py` constructs `ExperimentTracker.create(url)`, enters `async with` block, writes a metric via the in-shard stub `ExperimentRun.log_metric` shim, asserts row appears in `_kml_metrics`." The stub can be replaced with the full W12 primitive in wave 12 — the point is the framework-level facade invocation exists in W10.

---

### FP-HIGH-2 — W16 ModelRegistry, W17 ArtifactStore, W25 InferenceServer all ship manager-facades with Tier-2 tests that don't exercise the hot path

**What fails:** Same shape as FP-HIGH-1. W16 creates `ModelRegistry.register(...)`. W17 creates `ArtifactStore` (LocalFile + CAS). W25 creates `InferenceServer` + `ServeHandle`. All three are `*Registry` / `*Store` / `*Server` manager-shapes per `rules/facade-manager-detection.md`. Their T2 tests are described as "concurrent register collision" / "export + load round-trip per family" / "RF/LGB/Torch all serve, roundtrip predict" — those exercise the class through a direct import, NOT through `db.trust_executor`-style facade invocation from a realistic user entry point (e.g. `km.register(...)` → `MLEngine.register()` → `ModelRegistry.register()`).

**Where:** W16, W17, W25 todos. `rules/orphan-detection.md §1` requires "facade + hot-path call site in the same PR." The hot-path call site for ModelRegistry is `MLEngine.register()` (W21), for ArtifactStore is `MLEngine.register()` via `ArtifactStore.put(...)` (W21), for InferenceServer is `MLEngine.serve()` (W21). All three hot-path wirings land in W21 — 2-6 waves after the manager facade.

**Probability:** HIGH. Three independent manager-facades, each with a multi-wave gap between facade landing and hot-path wiring. Each gap is one ratchet-step where a downstream agent or reviewer assumes the facade is "tested" because T2 passes.

**Mitigation:** Each of W16, W17, W25 MUST include a Tier-2 wiring test that invokes the facade THROUGH a stub of the hot-path caller (even if the hot-path caller itself lands in W21). Concretely: `test_model_registry_wiring.py` imports `ModelRegistry` via `db.registry` (or similar framework accessor built in W16), not via `from kailash_ml.tracking.registry import ModelRegistry`. See `rules/facade-manager-detection.md §2` — test imports through the facade, not the class.

---

### FP-HIGH-3 — W22 DLDiagnostics + W26 DriftMonitor + W27 AutoMLEngine ship as `*Diagnostics` / `*Monitor` / `*Engine` manager-shapes without same-wave hot-path wiring tests

**What fails:** Identical pattern to FP-HIGH-1/2. W22 DLDiagnostics — T2 is "full fit writes figures to run" which requires W20 (`MLEngine.fit`) already landed. W26 DriftMonitor — T2 is "drift-trigger fires retrain callback" which requires a real `MLEngine.fit()` to retrain against. W27 AutoMLEngine + FeatureStore — T2 is "full automl run + feature version retrieval" which requires end-to-end plumbing. All three are valid tests IF the facades they call through are already in place, but W22 is downstream of W20 (OK) while W26+W27 are independent of the MLEngine waves in the dependency graph (not gated). An agent implementing W26 in parallel with W20 may pass its T2 against a mocked `MLEngine` — which is a Tier-2 violation (mocking in Tier 2) that also silently orphans the retrain callback.

**Where:** W22, W26, W27 todos. The plan's parallelization table puts "W25-W28: parallel across 4 specialists" — including W26 and W27 running in parallel with W28 (dashboard) while W20 is already done. That's fine for ordering BUT does not guarantee W26's T2 actually triggers a real `MLEngine.fit()` retrain.

**Probability:** MED-HIGH. Parallel execution + "real infra" test statement is ambiguous — an agent can satisfy "real PG + real polars" while mocking the retrain callback target. The hot-path wiring to `MLEngine.fit()` must be explicit in the T2 fixture.

**Mitigation:** W26 T2 MUST use a real `MLEngine` instance to receive the retrain callback; `DriftMonitor` MUST be constructed via `db.drift` or the MLEngine-integrated accessor; mocking `MLEngine.fit` inside T2 is BLOCKED. W27 same discipline. W22 same — the DLDiagnostics Lightning callback MUST be appended to a real `L.Trainer` inside a real `MLEngine.fit()` call.

---

### FP-HIGH-4 — W19 MLEngine 500 LOC shard sits at the capacity-budget cliff; 9 invariants + 7 DI slots + 8-method surface overflows the 5-10 invariant band

**What fails:** W19 is estimated at ~500 LOC load-bearing, lists 9 invariants, requires 7 DI slot wiring, 8-method public surface preservation, 3 distinct `__init__` paths (zero-arg, full-DI, partial-DI), 3 validation error types (`TargetNotFoundError`, `TargetInFeaturesError`, `ConflictingArgumentsError`), and `setup()` idempotence fingerprint (§15.10 requires exactly 8 methods — this is the 10th invariant implicitly). That's 10+ simultaneous invariants, at or above the `rules/autonomous-execution.md` Per-Session Capacity Budget upper bound of 10 invariants per shard. W20 immediately follows with 10 more invariants + 4 methods + Lightning passthrough (5 kwargs) + auto-checkpoint + auto-lr + schema drift — another 10-invariant shard.

**Where:** W19 and W20 todos. `rules/autonomous-execution.md § Per-Session Capacity Budget MUST Rule 1`: "≤5-10 simultaneous invariants the implementation must hold." Phase-5.11 orphan (2,407 LOC) was "one conceptual change that exceeded the invariant budget."

**Probability:** MED-HIGH for W19, MED-HIGH for W20. Both are exactly the shape the capacity rule warns about — a state machine + multiple cross-cutting invariants. Feedback-loop multiplier (Rule 3) applies ONLY if a live test harness fires during the session; the shard plan lists Tier-1 unit tests + Tier-2 integration but Tier-2 requires real PG + real MPS which is not guaranteed to fire on every iteration.

**Mitigation:** Split W19 into two shards:

- W19a — `MLEngine.__init__` + DI resolution + zero-arg construction (4 invariants: zero-arg works, 7 DI slots accepted, overrides honored, async-first).
- W19b — `setup()` + `compare()` (5 invariants: idempotence fingerprint, target validation, family dispatch, Lightning routing, 8-method surface preservation).
  Similarly split W20 into W20a (`fit()` + `predict()`, 5 invariants) and W20b (`finalize()` + `evaluate()` + schema drift + lr_find, 5 invariants). This retains the single-session feedback loop for each half while keeping each within the 5-invariant safe zone.

---

### FP-HIGH-5 — W34 atomic 7-package release lacks transactional rollback semantics; partial-success window is 6 PyPI uploads wide

**What fails:** W34 invariant 1 says "all 7 versions atomic in single PR (same commit or sequential but all in same session)." That conflates PR-atomic (git) with publish-atomic (PyPI). PyPI has NO cross-package transaction primitive. The release order is linear: `kailash` → `kailash-dataflow` → `kailash-nexus` → `kailash-kaizen` → `kailash-pact` → `kailash-align` → `kailash-ml`. If upload 4 (`kailash-kaizen 2.12.0`) succeeds but upload 5 (`kailash-pact 0.10.0`) fails (transient network, PyPI 5xx, token expiry, rate limit), the ecosystem is now permanently inconsistent:

- `kailash-ml 1.0.0` depends on `kailash-pact>=0.10.0` — upload 7 succeeds but users hit dependency resolution failure
- `kailash-kaizen 2.12.0` is published and cannot be yanked-and-replaced without bumping to 2.12.1
- Rolling back uploads 1-4 requires yanking, which leaves 1.x users in a worse state

**Where:** `todos/active/W34-release-wave.md` Invariants 1, 4, 6. The invariants assert order but not atomicity. There is no pre-flight check that EVERY package has a valid PyPI upload token + builds cleanly BEFORE any upload starts.

**Probability:** MED. Transient PyPI failures occur frequently enough to be a real risk on a 7-package sequence. The blast radius is a public-facing dependency graph inconsistency that external users hit immediately via `pip install kailash-ml==1.0.0`.

**Mitigation:** Add invariants:

- **Pre-flight all 7 builds in CI** — every package passes `python -m build` + `twine check dist/*` BEFORE any `twine upload` runs.
- **Pre-flight credential check** — `twine upload --repository-url testpypi ...` (dry-run against TestPyPI) for every package before the real uploads start.
- **Staged publish with verification loop** — after each `twine upload`, poll PyPI JSON API with retry ≤3× × 60s (already in invariant 9) AND verify the package is installable from a clean venv BEFORE proceeding to upload N+1. If any step fails, HALT and report — do not continue uploading subsequent packages.
- **Rollback protocol documented** — if upload N+1 fails after N successes, the disposition is `yank` uploads 1..N (retains index entry, blocks new installs) + bump patch version on all 7 packages + retry full sequence. Document this in W34 DoD.

---

### FP-HIGH-6 — W31 / W32 parallel sub-shards risk version drift + CHANGELOG collision despite "version owner" rule

**What fails:** W31 spawns 3 parallel sub-shards (31a kailash-core, 31b kailash-dataflow, 31c kailash-nexus). Each sub-shard edits a DIFFERENT package's `pyproject.toml` — so the version-owner rule says "one owner per package" which is trivially satisfied (each sub-shard is the sole owner of its package). BUT:

1. All 3 sub-shards are parallel against the SAME base SHA of `main`. If 31a's kailash shim imports from `kailash_ml` while kailash-ml is at `1.0.0.dev0` vs `1.0.0.rc1` vs `1.0.0` — sub-shards see different kailash-ml versions depending on when the sibling worktree's commits reach `main`.
2. 31a MUST update `src/kailash/pyproject.toml` `extras = ["ml"]` to point to `kailash-ml>=1.0.0` — this pins a SPECIFIC version of kailash-ml that doesn't exist yet (W33/W34 ship it). If 31a bumps to `kailash 2.9.0` and locks `kailash-ml==1.0.0` as a hard requirement, but W34 doesn't land for another 3 sessions, every `pip install kailash[ml]` in the interim fails.
3. W32's 3 sub-shards similarly each edit a different CHANGELOG (32a kaizen, 32b align, 32c pact), so CHANGELOG collision is not a direct risk. BUT `packages/kailash-ml/CHANGELOG.md` MUST also reference each integration — and W31/W32/W33/W34 all add entries there. Multiple waves editing the SAME top-of-CHANGELOG section IS the collision.

**Where:** W31, W32, W33, W34 — all four waves write to `packages/kailash-ml/CHANGELOG.md`. The plan does not designate a single CHANGELOG owner for kailash-ml.

**Probability:** MED-HIGH. `rules/agents.md § MUST: Parallel-Worktree Package Ownership Coordination` documents the kailash-ml 0.13.0 + kailash 2.8.10 parallel-release cycle (2026-04-20) as exactly this failure mode.

**Mitigation:**

- **Declare W34 the sole CHANGELOG owner for kailash-ml** — W31/W32/W33 MUST NOT edit `packages/kailash-ml/CHANGELOG.md`; they pass "CHANGELOG bullet text for W34 to consolidate" via their PR body instead.
- **Pin kailash-ml extras via >= not ==** — `kailash[ml]` uses `kailash-ml>=1.0.0,<2.0.0` (compatible release range), not `kailash-ml==1.0.0`. This allows the 1.0.0 release to land in W34 without stranding 2.9.0 users in the interim.
- **Sub-shard prompts MUST explicitly exclude sibling-package version edits** per `rules/agents.md § MUST: Parallel-Worktree Package Ownership Coordination`.

---

### FP-HIGH-7 — W4 migration 0002 identifier-length audit is incomplete; 4 of the 15 table names hit the 63-char limit via index names

**What fails:** W4 invariant 2 says "all identifiers ≤63 chars (Postgres limit)." The 15 declared table names all fit (`_kml_automl_trials` is 18 chars). BUT `rules/dataflow-identifier-safety.md § 2` requires the `quote_identifier` helper check identifier length; and the table creation includes indexes whose names are derived from `idx_<table>_<cols>`. `_kml_classify_actions` (21 chars) with a multi-column index `idx__kml_classify_actions_tenant_resource_action_timestamp` is 57 chars + prefix — still fits, but `_kml_automl_trials` + `idx__kml_automl_trials_tenant_experiment_id_trial_id_created_at` = 63 chars exactly. One more column and it's truncated. PostgreSQL does NOT truncate — it raises an error at CREATE INDEX time. Migration fails mid-way, leaving tables created but indexes partial.

**Where:** W4 Invariants. Grep gate checks `CREATE TABLE.*_kml_` count (15) but NOT `CREATE INDEX` identifier lengths.

**Probability:** MED. The exact failure mode depends on the final index list, which W4 doesn't enumerate. The audit requires enumerating every `CREATE INDEX` in 0002 and asserting each name ≤63 chars BEFORE the migration runs. A parking-table fallback (invariant 9) catches DATA loss but not DDL failure mid-migration — a DDL failure leaves the database in an inconsistent DDL state that the parking table does not cover.

**Mitigation:**

- Add to W4 Invariants: "Every `CREATE INDEX` statement in 0002 MUST route its index name through `dialect.quote_identifier()` and the helper's 63-char length check raises `IdentifierError` BEFORE migration applies any DDL."
- Add to W4 Tests: "T1 unit — enumerate every index name in 0002 + assert `len(name) <= 63`."
- Add to W4 invariant 9: "Parking tables preserve ROW data AND DDL state snapshot; downgrade restores BOTH."

---

### FP-MED-1 — W3 parking-table approach doesn't cover "migration 0001 succeeds but 0002 fails" cross-migration failure

**What fails:** Scenario: a fresh PG instance runs 0001 (status vocab migrate) successfully, then 0002 (prefix unification) fails on the 47th CREATE INDEX statement. The parking table `_kml_migration_0001_prior_status` from 0001 persists (correctly), BUT 0002's partial tables are in an inconsistent state (some `_kml_*` renamed, some legacy names remaining, some indexes created, some failed). W4 says "reversible downgrade preserves data via parking tables" but that's 0002's own downgrade. The cross-migration failure is: user can't downgrade 0002 (it failed mid-way) AND can't re-run 0001 (already done) — the DB is stuck.

**Where:** W3 + W4. Neither wave tests the CROSS-migration failure case (0001 done + 0002 partial).

**Probability:** MED. This surfaces the first time a real PG instance has data in `ml_runs` (legacy name) AND a transient error interrupts 0002's renames.

**Mitigation:** Add a regression test in W4: `tests/regression/test_migration_0002_resumes_after_partial.py` seeds a DB with 0001 complete, simulates 0002 failure after table 7 of 15, asserts the migration framework's resume-from-checkpoint logic picks up and completes OR raises a typed `MigrationResumeRequiredError`.

### FP-MED-2 — W15 GDPR erasure `km.erase_subject()` hot path not wired in W15 test

**What fails:** W15 Invariant 2 says "`km.erase_subject` deletes run content + artifact content + model content, preserves audit." `km.erase_subject` is NOT in the W33 `km.*` wrapper list (W33 lists `seed, reproduce, resume, lineage, train, autolog, track, register, serve, watch, dashboard, diagnose, rl_train` — no `erase_subject`). `specs/ml-tracking.md §8.4` (Decision 2) references the behavior. So the facade `km.erase_subject` is either (a) a new `km.*` wrapper not in the §15.9 list, (b) a method on `ExperimentTracker`, or (c) an orphan that never surfaces in the public API.

**Where:** W15 + W33. `__all__` ordering in `specs/ml-engines-v2.md §15.9` should list `erase_subject` if it's a module-level wrapper.

**Probability:** MED. If W15 ships `km.erase_subject` as a wrapper but W33's `__all__` doesn't include it, the symbol is reachable via `from kailash_ml import erase_subject` but absent from `from kailash_ml import *` — the `__all__` drift pattern from `rules/orphan-detection.md §6`.

**Mitigation:** W15 MUST (a) clarify where `km.erase_subject` lives (module-level wrapper vs method), (b) add it to W33 `__all__` if module-level, (c) add a W15 wiring test that calls through `km.erase_subject(subject_id)` not `ExperimentTracker.erase_subject(...)`.

### FP-MED-3 — W21 `MLEngine.serve()` invariant 6 "serve dispatches to Nexus ml-endpoints (W31)" creates forward dependency

**What fails:** W21 invariant 6 says "serve dispatches to Nexus ml-endpoints (W31)" but W21 is BLOCKED-BY W20 only, and W31 is BLOCKED-BY W18/W21/W25. So W21 lands before W31. The Nexus ml-endpoints don't exist yet. If W21's `MLEngine.serve()` hardcodes an import of `nexus.ml.mount_ml_endpoints`, implementing W21 requires it to exist — which it doesn't. If W21 uses a late import / try/except, the T2 integration test "full Quick Start to `/health → 200`" cannot pass until W31 lands.

**Where:** W21 Invariants 3 + 6. The dependency graph in the master plan shows W21 → W25 → W28 → W31, but W21 already references W31.

**Probability:** MED. The test "full Quick Start to `/health → 200`" is listed as W21's T2 but factually requires W31. Either the test is a lie at W21 time, or W21 must include a stub Nexus mount that W31 replaces (which is fake-serve per `rules/zero-tolerance.md` Rule 2).

**Mitigation:** Move W21's "full Quick Start" T2 test to W31 (after Nexus ml-endpoints exist) OR downgrade W21's T2 to "direct-channel predict round-trip" (no REST, no MCP) with the REST/MCP integration landing as a W31 wiring test.

### FP-MED-4 — W23 autolog monkey-patching order vs W20 `MLEngine.fit()` auto-checkpoint callback appending — last-writer-wins race

**What fails:** W23 autolog monkey-patches sklearn/lightning/torch to emit metrics into ambient run. W20 auto-appends `ModelCheckpoint` callback to `L.Trainer`. Both happen "when `MLEngine.fit()` runs." If autolog is enabled via `km.autolog("lightning")`, the monkey-patched `Trainer.__init__` may already have run; W20's `fit()` then tries to append its checkpoint callback to a Trainer whose `callbacks=` list was already captured by the monkey-patch. The order matters and neither wave specifies it.

**Where:** W20 invariant 5 (callbacks) + W23 invariant 4 (`[autolog-lightning]` gated).

**Probability:** MED. Silent metric-loss or silent checkpoint-loss depending on order.

**Mitigation:** W20 Tests MUST include a T2 case with `km.autolog("lightning")` already called before `km.train()` runs; assert BOTH autolog metrics AND auto-checkpoint fire. W23 Tests MUST include the converse — autolog called after an `MLEngine.fit()` is already in-flight, assert no double-patch + no callback loss.

### FP-MED-5 — W9 Lightning adapters "parallel across 4 adapter files" drifts the `accelerator=auto` invariant

**What fails:** Parallelization plan says W9 parallel across 4 adapter files (sklearn, xgboost, lightgbm, catboost). Each sub-shard independently implements `to_lightning_module()`. Invariant 3 says "accelerator=auto honored (no family-specific dispatch)." If sub-shard A hardcodes `accelerator='cpu'` for sklearn (sklearn has no GPU), sub-shard B hardcodes `accelerator='gpu'` for xgboost via device_type param, etc., the unified `MLEngine.compare()` sweep gets heterogeneous accelerator dispatch — exactly what invariant 3 forbids.

**Where:** W9 Invariants + parallelization table.

**Probability:** MED. Cross-shard invariant (same contract across 4 files) is exactly the case the capacity-budget rule warns about — one invariant spread across 4 parallel work items with no single owner.

**Mitigation:** W9 should land ONE shared `LightningAdapterBase` first (serial) + 4 family sub-shards second (parallel against the base). The base enforces `accelerator=auto` in one place; sub-shards cannot drift without editing the base.

### FP-MED-6 — W24 "existing kaizen adapters unchanged — wire only" hides a real integration cost

**What fails:** W24 says "existing kaizen adapters (Rag/Interpret/Judge) unchanged — wire only." But W32 32a says kaizen agents MUST use `km.engine_info()` for tool-set construction — which is a NEW behavior, not wire-only. W24's T2 test "PPO rollout writes reward curve" doesn't exercise the agent-tool-discovery integration.

**Where:** W24 + W32 32a.

**Probability:** MED. Integration cost leakage across two waves creates an orphan window where W24 claims done but W32 is still needed for actual wiring.

**Mitigation:** W24 should explicitly state "RL diagnostics only; kaizen §2.4 Agent Tool Discovery is W32 scope." Removes the ambiguity.

### FP-MED-7 — W32 cross-package sub-shards claim "single source in ml" for Trajectory but align already has its own

**What fails:** W32 32b invariant 6: "align trajectory schema imports `ml.rl.Trajectory` (single source in ml)." This requires DELETING the existing `align.training.Trajectory` (if any). A deletion without the sibling-test sweep per `rules/orphan-detection.md §4` breaks `align` tests.

**Where:** W30 + W32 32b.

**Probability:** MED. W30 lands the shared schema; W32 32b imports it in align. If W30 doesn't also sweep `align`'s existing `Trajectory` definitions + tests, W32 32b lands with a doubly-defined class.

**Mitigation:** W30 DoD MUST include "grep `class Trajectory` in packages/kailash-align/ — delete or port EVERY existing definition + test in same commit."

### FP-MED-8 — W5 `km.seed(lightning=True)` cross-SDK parity not audited

**What fails:** Decision 3 promises Python↔Rust byte-identical `Status` enum. Decision 9 promises `start_run`/`end_run` Python async-context vs Rust explicit-calls. W5 `km.seed()` is a Python-only primitive; Rust's equivalent is unstated. If the Rust SDK has `seed(int) -> SeedReport` but Rust's `SeedReport` has different field names (e.g. `torch_det` vs `torch_deterministic`), a polyglot user correlating seed behavior across SDKs sees drift.

**Where:** W5 + Decision 9 + kailash-rs#502.

**Probability:** MED. Cross-SDK parity rules require field-name identity (`rules/event-payload-classification.md §2` "cross-SDK contract"). W5 doesn't mention Rust at all.

**Mitigation:** W5 DoD adds "kailash-rs#502 updated with Python SeedReport field names as canonical; Rust variant overlay expected to match."

### FP-MED-9 — W33 `__all__` eager-import for 34 symbols exceeds the 5-10 invariant budget for the single `__init__.py` edit

**What fails:** W33 is one shard + ~500 LOC but 11 invariants (listed) — over the upper bound. 34 symbols × per-symbol eager-import declaration + import-cycle avoidance + 6-group order preservation is a LOT of invariants for one wave. The shard prompt mentions `kailash_ml/_wrappers.py` module PLUS `kailash_ml/__init__.py` PLUS `kailash_ml/engines/registry.py` PLUS `packages/kailash-ml/MIGRATION.md` PLUS the regression test. That's 5 distinct files, each with cross-file invariants.

**Where:** W33 todo.

**Probability:** MED. Feedback-loop multiplier (Rule 3) applies since `pytest --collect-only` + the `__all__` membership test fire during the session, so this may be survivable. But the risk is the README fingerprint constant drift (invariant 4) — one whitespace char in the canonical block and the test fails.

**Mitigation:** Split W33 into W33a (wrappers + registry + `__all__` — 5 invariants) + W33b (MIGRATION.md + README Quick Start + regression test + fingerprint — 5 invariants). Keeps each within budget.

### FP-MED-10 — W34 invariant 8 "tag pushes trigger publish workflow" has no rollback path if the workflow DOES trigger but fails mid-flight

**What fails:** Invariant 8 says "verify workflow run success." If the workflow triggers and uploads 5 of 7 packages then crashes on #6, the tag is already pushed. Re-triggering requires either retrying-idempotent publish (most workflows aren't) or bumping a patch version AND pushing a new tag. No protocol documented.

**Where:** W34.

**Probability:** MED. Connected to FP-HIGH-5; this is the CI-workflow-level expression of the same atomic-release risk.

**Mitigation:** Document in W34: "Each package's CI job MUST be idempotent — re-running after a partial failure either succeeds (if upload already done, verify + exit) or retries cleanly. Non-idempotent publish = HIGH finding."

### FP-MED-11 — Spec coverage does not include `ml-engines-v2-addendum.md §E11.2-E11.3` as standalone coverage — only referenced by W33

**What fails:** The Spec Coverage Matrix lists `ml-engines-v2-addendum.md` as Primary W9, Secondary W21, W33. But addendum §E11.2-E11.3 describes `engine_info` + `list_engines` + `DeviceReport` dataclass shape — these land in W33 + W7 respectively, not W9. The matrix misrouts the addendum primary.

**Where:** Master plan § Spec Coverage Matrix.

**Probability:** LOW-MED. Cosmetic + coverage-audit risk. `/redteam` per `rules/specs-authority.md §5b` would flag this as spec-drift if §E11.3 is amended mid-implement without sweeping §15.9 in the main spec.

**Mitigation:** Update matrix: addendum Primary W9 (adapter signatures) + W33 (§E11.2-E11.3 engine_info + list_engines); matrix should split by addendum section.

### FP-LOW-1..6 — Additional lower-severity findings

- **FP-LOW-1:** W6 `backend-compat-matrix.yaml` is package-data; W34 doesn't verify it ships correctly through `pip install kailash-ml` + `km.doctor gpu`. Add installability verification.
- **FP-LOW-2:** W13 `list_runs` returns polars DF but no invariant specifies the column set — downstream readers (W28 dashboard, W33 lineage wrappers) may drift.
- **FP-LOW-3:** W18 "cross-tenant lineage does NOT resolve" is a MultiTenantOpError path but W15 tests the tenant-boundary in admin ops, not in lineage queries.
- **FP-LOW-4:** W28 `km.dashboard()` launcher thread cleanup on notebook kernel restart not specified.
- **FP-LOW-5:** W30 `Trajectory` cross-SDK parity doesn't specify Rust equivalent field names.
- **FP-LOW-6:** W22 DLDiagnostics `[dl]` extra gated but W5/W7 don't check for `[dl]` absence — missing extra leads to `ImportError` on first diagnostics call, not a typed `DiagnosticsError`.

---

## Capacity-budget ROM table

| Wave                        | Est LOC           | Invariant count | Call hops | Describable in 3 sentences? | Budget OK?                          |
| --------------------------- | ----------------- | --------------- | --------- | --------------------------- | ----------------------------------- |
| W1 errors                   | ~150              | 7               | 1         | Y                           | OK                                  |
| W2 env resolver             | ~100              | 5               | 1         | Y                           | OK                                  |
| W3 migration 0001           | ~200              | 7               | 2         | Y                           | OK                                  |
| W4 migration 0002           | ~400              | 9               | 2         | Y                           | **TIGHT** (9 invariants near limit) |
| W5 km.seed                  | ~150              | 5               | 1         | Y                           | OK                                  |
| W6 backend-compat           | ~200              | 4               | 2         | Y                           | OK                                  |
| W7 DeviceReport             | ~300              | 8               | 2         | Y                           | **TIGHT** (8 invariants)            |
| W8 Trainable                | ~250              | 7               | 2         | Y                           | OK                                  |
| W9 Lightning adapters       | ~600 (parallel×4) | 6               | 3         | Y                           | OK if base-first (see FP-MED-5)     |
| W10 Tracker                 | ~350              | 7               | 2         | Y                           | OK                                  |
| W11 Run lifecycle           | ~250              | 6               | 2         | Y                           | OK                                  |
| W12 Logging primitives      | ~400              | 6               | 3         | Y                           | OK                                  |
| W13 Query primitives        | ~300              | 5               | 2         | Y                           | OK                                  |
| W14 Storage                 | ~500              | 5               | 3         | Y                           | OK                                  |
| W15 Tenant/audit/GDPR       | ~400              | 7               | 3         | Y                           | **TIGHT**                           |
| W16 Registry core           | ~400              | 7               | 2         | Y                           | **TIGHT**                           |
| W17 ArtifactStore           | ~450              | 6               | 3         | Y                           | OK                                  |
| W18 Aliases/lineage         | ~400              | 6               | 3         | Y                           | OK                                  |
| **W19 MLEngine init+setup** | **~500**          | **9+**          | **4**     | **Marginal**                | **OVER (see FP-HIGH-4)**            |
| **W20 MLEngine fit+**       | **~500**          | **10**          | **4**     | **Marginal**                | **OVER (see FP-HIGH-4)**            |
| W21 register+serve          | ~350              | 6               | 3         | Y                           | OK                                  |
| W22 DLDiagnostics           | ~400              | 7               | 3         | Y                           | **TIGHT**                           |
| W23 Autolog                 | ~350              | 6               | 3         | Y                           | OK                                  |
| W24 RL/RAG/Judge            | ~400              | 5               | 3         | Y                           | OK                                  |
| W25 InferenceServer         | ~500              | 7               | 3         | Y                           | **TIGHT**                           |
| W26 DriftMonitor            | ~400              | 6               | 3         | Y                           | OK                                  |
| W27 AutoML+FeatureStore     | ~700              | 9               | 4         | N (2 specs in 1)            | **OVER** — split into W27a+W27b     |
| W28 Dashboard               | ~500              | 5               | 2         | Y                           | OK                                  |
| W29 RL core                 | ~600              | 8               | 3         | Y                           | **TIGHT**                           |
| W30 RL/align unification    | ~400              | 5               | 3         | Y                           | OK                                  |
| **W31 3 sub-shards**        | **~600**          | **10 total**    | **3**     | **N (3 packages)**          | **OVER — see FP-HIGH-6**            |
| **W32 3 sub-shards**        | **~700**          | **10 total**    | **3**     | **N (3 packages)**          | **OVER — see FP-HIGH-6**            |
| **W33 km wrappers+**all**** | **~500**          | **11**          | **3**     | **Marginal**                | **OVER — split into W33a+W33b**     |
| W34 release                 | ~200 (non-code)   | 9               | —         | Y                           | OK (non-impl shard)                 |

**Summary:** 5 waves over budget (W19, W20, W27, W33 + W31/W32 parallel coordination), 7 waves tight. All OVER waves have specific mitigation above.

---

## Dependency graph verification

**Claimed vs actual blocking (selected):**

| Wave                                                 | Claimed "Blocks"                                                  | Actual code dependency                    | Drift? |
| ---------------------------------------------------- | ----------------------------------------------------------------- | ----------------------------------------- | ------ |
| W10 blocks W11, W19, W21                             | W11 extends W10, W19 imports tracker, W21 uses log_model          | ✓ Consistent                              |
| W3 blocks W11, W14, W15                              | W11 uses status enum from migration, W14 storage reads, W15 audit | ✓ Consistent                              |
| W21 "serve dispatches to Nexus ml-endpoints (W31)"   | W31 is downstream of W21 in graph                                 | **✗ Backward ref — see FP-MED-3**         |
| W24 "existing kaizen adapters unchanged — wire only" | W32 32a adds new §2.4 behavior                                    | **✗ Split responsibility — see FP-MED-6** |
| W30 shared Trajectory                                | W32 32b imports it                                                | ✓ Consistent                              |
| W31 31a "re-export kailash_ml"                       | depends on kailash-ml 1.0.0 version                               | **✗ Forward version ref — see FP-HIGH-6** |
| W33 depends on W5, W15, W18, W21, W24, W28, W29      | 7 upstream waves                                                  | ✓ Consistent but fragile                  |

**The graph-vs-todos mismatches are limited to the 3 HIGH/MED findings above.** All other W-block relationships match actual code dependency.

---

## Atomic release failure modes

**Partial-success matrix for W34** (7 sequential PyPI uploads):

| Fail point                                    | State after fail                                                                                                                          | Recovery                                                                                                  |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Upload 1 (kailash) fails                      | Nothing published. Clean retry.                                                                                                           | Retry same versions.                                                                                      |
| Upload 2-5 fails (middle packages)            | N packages published; `kailash-ml` not yet. External users cannot `pip install kailash-ml==1.0.0`. **Internal deps may resolve wrong**.   | Yank 1..N-1, bump patch on ALL 7, re-push tags, re-run full sequence.                                     |
| Upload 6 (kailash-align) fails                | kailash-ml about to publish; align missing. `kailash-ml` depends on `kailash-align>=0.5.0` — resolution FAILS.                            | Yank 1-5, bump patch, re-run.                                                                             |
| Upload 7 (kailash-ml) fails after 1-6 succeed | All deps published; kailash-ml missing. Downstream can install the new sub-packages but not the ml SDK. Partial-release visible to users. | Bump kailash-ml to 1.0.1, retry upload 7 ONLY (sub-packages already published). Acceptable recovery path. |

**Recommendation:** Only upload 7 is "safely retryable alone." Uploads 2-6 failing require full rollback.

**Plan amendment:** W34 MUST document the recovery decision-tree above. DO NOT attempt to continue uploads after any failure in positions 2-6 without a full yank+bump cycle.

---

## Parallel-worktree risks

### Absolute-path drift (rules/worktree-isolation.md §4)

The plan's "Parallelization Plan" section does not specify path conventions. Three parallel specialists in W9 (4 adapter files), W31 (3 packages), W32 (3 packages), W22/W23/W24 (3 specialists), W25/W26/W27/W28 (4 specialists) ALL require relative-path discipline in delegation prompts.

**Risk:** Session 2026-04-19 logged "2 of 3 parallel ml-specialist shards writing to MAIN; Shard A lost 300+ LOC." The plan does not prescribe the absolute-path prohibition at the orchestrator prompt level.

**Mitigation:** Add to master plan § Parallelization Plan: "Every sub-shard delegation prompt MUST use RELATIVE paths only per `rules/worktree-isolation.md §4`. The orchestrator verifies this at prompt-build time."

### CHANGELOG collision across waves

- W31 + W32 + W33 + W34 ALL potentially edit `packages/kailash-ml/CHANGELOG.md`.
- W34 is the declared sole release wave.

**Mitigation (FP-HIGH-6):** W34 is the sole kailash-ml CHANGELOG editor. Earlier waves pass bullet text via PR description only.

### Version drift in parallel W31/W32

- W31 31a bumps `kailash 2.9.0` — MUST NOT pin `kailash-ml==1.0.0` (forward ref).
- W31 31b bumps `kailash-dataflow 2.1.0` — MUST NOT touch `packages/kailash-ml/pyproject.toml`.
- W31 31c bumps `kailash-nexus 2.2.0` — same.

**Mitigation (FP-HIGH-6):** Sub-shard prompts explicitly exclude sibling-package version edits; extras pins use `>=` ranges.

---

## Spec coverage gaps

Cross-referencing specs/\_index.md against the 34 waves:

| Spec                                      | Wave(s) | Coverage              |
| ----------------------------------------- | ------- | --------------------- |
| ml-engines-v2 §15.9 `__all__` ordering    | W33     | ✓ Primary             |
| ml-engines-v2 §16 Quick Start fingerprint | W33     | ✓ Primary             |
| ml-tracking §3.2 status transitions       | W3, W11 | ✓ Migration + runtime |
| ml-tracking §8 audit immutability         | W15     | ✓                     |
| ml-registry §7 registration atomicity     | W16     | ✓ Invariant 6         |

**SHOULD clauses not explicitly mapped to a wave:**

- ml-engines-v2 §15.1 "`km.*` matches every competitor's newbie-UX pattern" — no explicit regression gate for this (aspirational, not testable directly).
- ml-engines-v2 §12A `km.resume(tolerance=)` tolerance param shape — W33 mentions `km.resume(run_id, tolerance=...)` but the validation of tolerance semantics isn't in any T2.
- ml-diagnostics §7 SystemMetricsCollector — **explicitly v1.1-deferred per Round 8**, noted as IT-3. Correctly excluded.
- ml-registry-pact cross-tenant admin export — **explicitly v1.1-deferred**, noted as IT-4. Correctly excluded.

**Gap:** `km.resume(tolerance=...)` tolerance validation needs a T2 case in W33.

---

## Cross-SDK semantic drift risks

Per Decisions 3, 9, 10:

| Surface                    | Python (wave)                                   | Rust (kailash-rs)          | Drift risk                                                                            |
| -------------------------- | ----------------------------------------------- | -------------------------- | ------------------------------------------------------------------------------------- |
| Status enum 4-member       | W3, W11                                         | kailash-rs#502             | **LOW** — enum values pinned in spec                                                  |
| Run lifecycle              | W11 async-context + sync start/end (Decision 9) | explicit start_run/end_run | **LOW** — Decision 9 explicitly permits syntactic divergence with observable-equality |
| SeedReport                 | W5                                              | ???                        | **MED** — see FP-MED-8                                                                |
| TrainingResult.device      | W8                                              | kailash-rs DeviceReport    | **LOW** — ml-backends.md pins field shape                                             |
| format_record_id_for_event | W15                                             | kailash-rs BP-048          | **LOW** — `sha256:<8hex>` already pinned                                              |
| Trajectory schema          | W30                                             | ???                        | **MED** — see FP-LOW-5                                                                |
| EngineInfo                 | W33                                             | ???                        | **MED** — not mentioned in kailash-rs#502 per Round 8                                 |

**Critical:** W11's sync variant `tracker.start_run()` / `tracker.end_run(run, status="FINISHED")` MUST preserve semantic parity with Rust's `ExperimentTracker::start_run()` / `end_run(run, Status::Finished)`. Python's async context manager finalizes on `__aexit__`; Rust's explicit `end_run` finalizes on call. Observable equivalence requires: both finalize `_kml_runs.finished_at` + both write an audit row with identical timestamp semantics. W11 T2 doesn't test cross-SDK observable equivalence — only Python-side transitions.

**Mitigation:** W11 DoD adds "kailash-rs#502 documents the semantic-parity contract; Python T2 asserts observable fields match Rust-side expected shape per the parity doc."

---

## Recommended plan amendments

Before the orchestrator enters `/implement`, the following changes MUST be merged into `02-plans/01-master-34-wave-plan.md` and the corresponding `todos/active/`:

1. **Add same-wave wiring tests for manager-facades:** W10 (ExperimentTracker), W16 (ModelRegistry), W17 (ArtifactStore), W22 (DLDiagnostics), W25 (InferenceServer), W26 (DriftMonitor), W27 (AutoMLEngine + FeatureStore). Each MUST ship a `tests/integration/test_<name>_wiring.py` that imports through the framework facade, not the class directly. (FP-HIGH-1, FP-HIGH-2, FP-HIGH-3)

2. **Split over-budget waves:**
   - W19 → W19a (init+DI) + W19b (setup+compare).
   - W20 → W20a (fit+predict) + W20b (finalize+evaluate).
   - W27 → W27a (AutoMLEngine) + W27b (FeatureStore).
   - W33 → W33a (wrappers + `__all__`) + W33b (MIGRATION.md + README regression).
     (FP-HIGH-4, FP-MED-9)

3. **Atomic release protocol for W34:**
   - Pre-flight all 7 builds + twine check + TestPyPI dry-run BEFORE any real upload.
   - Per-upload verification loop (PyPI JSON + clean-venv install + import).
   - Documented rollback decision tree for partial failures.
   - Non-idempotent publish workflow = HIGH finding. (FP-HIGH-5, FP-MED-10)

4. **Parallel-worktree ownership:**
   - W34 sole CHANGELOG owner for `packages/kailash-ml/CHANGELOG.md` across W31/W32/W33/W34.
   - Sub-shard prompts explicitly exclude sibling-package `pyproject.toml` edits.
   - Extras pins use `>=` ranges, not `==`.
   - Relative-path discipline restated at master-plan level. (FP-HIGH-6, worktree-isolation.md §4)

5. **Migration cross-failure test:**
   - W4 adds regression `test_migration_0002_resumes_after_partial.py`.
   - W4 invariant 2 extended: `CREATE INDEX` name lengths routed through `quote_identifier` with 63-char check. (FP-HIGH-7, FP-MED-1)

6. **Forward-reference cleanup:**
   - W21 T2 downgrades to "direct-channel predict round-trip"; REST/MCP serve testing moves to W31.
   - W24 scope clarified: "RL diagnostics only; §2.4 Agent Tool Discovery is W32." (FP-MED-3, FP-MED-6)

7. **Cross-SDK parity:**
   - W5, W11, W30, W33 DoDs include "kailash-rs#502 updated with Python-side canonical shapes."
   - W11 T2 asserts observable-equivalence fields per the Rust parity doc. (FP-MED-8, FP-LOW-5)

8. **km.erase_subject location resolved:**
   - W15 clarifies module-level vs tracker-method.
   - If module-level: add to W33 `__all__` list.
   - W15 wiring test uses `km.erase_subject(...)`. (FP-MED-2)

9. **W9 shared base first:**
   - W9 lands `LightningAdapterBase` serially, THEN parallel 4 family sub-shards. (FP-MED-5)

10. **W30 sweep existing align Trajectory:**

- W30 DoD adds "grep `class Trajectory` in packages/kailash-align/; delete/port every definition + test in same commit." (FP-MED-7)

11. **Spec coverage matrix fix:**

- Addendum section split across W9 (adapter signatures) + W7 (DeviceReport) + W33 (engine_info). (FP-MED-11)

12. **Lower-severity items:**

- W6 installability verification of backend-compat-matrix.yaml.
- W13 polars column set pinned.
- W22 typed `DiagnosticsError` on missing `[dl]` extra.
- W28 dashboard thread cleanup on kernel restart.
- W33 `km.resume(tolerance=...)` T2 case.

**Blocking verdict:** With amendments 1-11 in place, the plan is APPROVE for `/implement`. Without amendments 1, 2, 3, 4, 5: BLOCK — these are the structural failure modes that reproduce the Phase-5.11 orphan (HIGH-1..3) + capacity-budget overflow (HIGH-4) + partial-release inconsistency (HIGH-5) + parallel-worktree collision (HIGH-6) + cross-migration failure (HIGH-7).
