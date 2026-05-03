# Round-3 Cross-Spec Consistency Re-Audit

**Date:** 2026-04-21
**Persona:** Cross-Spec Consistency Auditor (post-Phase-C re-audit)
**Inputs:**

- Round-2 Phase-B closure baseline: `workspaces/kailash-ml-audit/04-validate/round-2b-closure-verification.md` (12 CRIT GREEN, 58 GREEN, 11 YELLOW, 1 RED, 0 GAP).
- Approved decisions: `workspaces/kailash-ml-audit/04-validate/approved-decisions.md` (14 decisions, at-any-cost framing).
- 15 ML specs under `workspaces/kailash-ml-audit/specs-draft/ml-*-draft.md`.
- 6 supporting-module specs under `workspaces/kailash-ml-audit/supporting-specs-draft/*.md`.
- All checks re-derived from scratch via AST/grep per `skills/spec-compliance/SKILL.md` — `.test-results` / prior self-reports NOT trusted (audit-mode rule).

**Scope note.** The user prompt referenced a baseline file `round-2b-cross-spec-consistency.md` with "4 CRIT + 11 HIGH + 7 MED". That exact filename does not exist in the workspace; the closest available Round-2 artefact is `round-2b-closure-verification.md` (closure + theme audit of round-1 HIGH+CRIT). This report treats the closure-verification's CRITs + YELLOWs + RED as the Round-2 baseline AND additionally re-derives every Round-2 observation against the Phase-C drafts. CRIT IDs below map to user's four enumerated CRITs (DB URL / tracker constructor / error hierarchy / contextvar). HIGH IDs below map to Round-2 YELLOW-1 through YELLOW-10 + RED-1 = 11 HIGH slots.

**Verdict headline:** 4/4 CRIT GREEN, **5/11 HIGH still OPEN**, plus two NEW HIGH findings surfaced by the mechanical sweep (Decision 5 XPU native-first, Decision 6 backend-compat-matrix, Decision 7 CI runner policy). **Target 0 CRIT + 0 HIGH not met.** Phase-C must ship a follow-up targeted-edits shard before `/codify` gate can clear.

---

## Section A — CRIT Re-Verification (4 items)

### CRIT-1 — Default DB URL drift

**Check:** No `kailash-ml.db` / `kailash_ml.db` reference appears outside explicit legacy / migration / BLOCKED contexts. Canonical path `~/.kailash_ml/ml.db` is the single default.

**Sweep:** `rg '(kailash-ml|kailash_ml|ml)\.db' workspaces/kailash-ml-audit/specs-draft/`

**Findings (28 matches across 9 files):**

- `ml-tracking-draft.md` §2.2 (line 83): canonical MUST "`~/.kailash_ml/ml.db` ... any other default is BLOCKED". Repeated at lines 18, 71, 87–88, 158, 173, 1077.
- `ml-dashboard-draft.md` §2.1 + §3.2 + §3.3: same canonical path, 8 hits (lines 44, 49, 67, 79, 97, 369, 400, 401, 414, 581).
- `ml-drift-draft.md` L60: `# None → canonical ~/.kailash_ml/ml.db per ml-tracking §2.2`.
- `ml-rl-core-draft.md` lines 411, 822, 1061: use canonical path via `ExperimentTracker.create(...)`.
- `ml-rl-align-unification-draft.md` L241: canonical.
- `ml-automl-draft.md` L70: canonical.
- `ml-backends-draft.md` L393: canonical (km.doctor readout).
- `ml-engines-v2-draft.md` lines 98, 1496, 1645, 1702: canonical.

**Every `kailash-ml.db` string is inside migration context (`1_0_0_merge_legacy_stores`, `kailash-ml.db.pre-1.0` rollback rename) — tracking §16 migration matrix.**

**Verdict: GREEN.** CRIT-1 closed.

### CRIT-2 — `ExperimentTracker` constructor

**Check:** Every user-facing construction site uses `await ExperimentTracker.create(...)`. No `.open()` / `ExperimentTracker(conn)` / `ExperimentTracker("path.db")` appears except inside BLOCKED examples.

**Sweep:** `rg 'ExperimentTracker\.(create|open|__init__)|ExperimentTracker\(' specs-draft/`

**Findings:**

- `ml-tracking-draft.md` §2.5 (L169–185): canonical MUST. Contract: "Every sibling spec that constructs an `ExperimentTracker` directly (e.g. `ml-rl-core §13.1`, `ml-rl-align-unification §4`, `ml-engines-v2 §2.3`, `ml-engines-v2-addendum §E1.2`) MUST call `await ExperimentTracker.create(...)`. Direct `ExperimentTracker(conn)` / `ExperimentTracker(...)` synchronous instantiation is BLOCKED as user-facing API."
- `ml-tracking-draft.md` L182 — `ExperimentTracker.open(...)` appears ONLY inside a "BLOCKED — rename to .create()" example.
- `ml-tracking-draft.md` L178–179 — `ExperimentTracker(conn)` / `ExperimentTracker("path.db")` appear ONLY as BLOCKED examples.
- `ml-rl-core-draft.md` lines 411, 822, 1061: `await ExperimentTracker.create(...)`.
- `ml-rl-align-unification-draft.md` L241: `await ExperimentTracker.create(...)`.
- `ml-engines-v2-draft.md` L106, L136, L160: `await ExperimentTracker.create(...)` (L160 inside a BLOCKED example illustrating an ignored custom-tracker path; still uses `.create()`).

**Supporting specs:** 0 violations. `rg 'ExperimentTracker\.open|ExperimentTracker\(conn|_current_run\.get' supporting-specs-draft/` returns no matches.

**Verdict: GREEN.** CRIT-2 closed.

### CRIT-3 — `MLError` hierarchy

**Check:** Every typed exception inherits from `MLError` via a per-domain family.

**Sweep:**

- `rg 'class \w+Error\(' specs-draft/` — enumerates every error class.
- `rg 'class \w+Error\(Exception\)|class \w+Error\(ValueError\)|class \w+Error\(RuntimeError\)|class \w+Error\(TypeError\)' specs-draft/` — flags any error NOT rooted in MLError.

**Findings:**

- `ml-tracking-draft.md` §9.1 (L828–888): authoritative hierarchy. `MLError(Exception)` → 11 family classes (`TrackingError`, `AutologError`, `RLError`, `BackendError`, `DriftMonitorError`, `InferenceServerError`, `ModelRegistryError`, `FeatureStoreError`, `AutoMLError`, `DiagnosticsError`, `DashboardError`) → 13 tracking-domain leaf errors. `BackendError(MLError, RuntimeError)` keeps `except RuntimeError` back-compat; `MetricValueError(TrackingError, ValueError)` keeps `except ValueError` back-compat (Decision 4).
- `ml-backends-draft.md` L418–423: `from kailash_ml.errors import MLError` + `class BackendError(MLError, RuntimeError)`. GREEN.
- `ml-engines-v2-draft.md` L469: `class UnsupportedTrainerError(MLError)`. GREEN.
- `ml-rl-core-draft.md` L1022: `class RewardModelRequiredError(RLError)`. GREEN.
- `ml-dashboard-draft.md` L555 + L576: `DashboardError(MLError)` + `DashboardStoreUnreachableError(DashboardError)`. GREEN.
- `ml-drift-draft.md` L274: `ReferenceNotFoundError(DriftMonitorError)` + §9 note "All inherit from `kailash_ml.errors.DriftMonitorError` → `kailash_ml.errors.MLError`." GREEN.
- `ml-registry-draft.md` §9 note: "All errors inherit from `kailash_ml.errors.ModelRegistryError`, which inherits from the canonical root `kailash_ml.errors.MLError` per `ml-tracking §9.1` (CRIT-3)." GREEN.
- `ml-serving-draft.md` §18 note: "All inherit from `kailash_ml.errors.InferenceServerError` → `kailash_ml.errors.MLError`." GREEN.

**Only `MLError(Exception)` at `ml-tracking §9.1` inherits directly from `Exception`. Every other leaf chains through a family.**

**Verdict: GREEN.** CRIT-3 closed.

### CRIT-4 — Contextvar accessor

**Check:** Public sites read ambient run via `kailash_ml.tracking.get_current_run()`. Direct `_current_run.get()` is restricted to `kailash_ml.tracking.runner` internals.

**Sweep:** `rg 'get_current_run|_current_run|get_current_tenant_id' specs-draft/ supporting-specs-draft/`

**Findings:**

- `ml-tracking-draft.md` §10.1 (L894–921): authoritative public accessor. "The public API for reading the ambient run is the module-level function `kailash_ml.tracking.get_current_run() -> Optional[ExperimentRun]`. Every sibling spec in this bundle (`ml-autolog`, `ml-diagnostics`, `ml-rl-core`, `ml-serving`, `ml-automl`, `ml-drift`, `ml-engines-v2`, `ml-engines-v2-addendum`, `ml-registry`, `ml-feature-store`, `ml-dashboard`) reads the ambient run through this accessor. Direct access to the internal `ContextVar` object is BLOCKED for library callers."
- `ml-tracking-draft.md` §10.2 (L923+): `get_current_tenant_id()` companion accessor.
- `ml-diagnostics-draft.md` L163 + L181 + L190: adapter reads through `get_current_run()`; "Direct access to `kailash_ml.tracking.runner._current_run` is BLOCKED for library callers."
- `ml-autolog-draft.md` L448 + L455 + L459 + L462 + L473 + L477: `autolog()` reads `get_current_run()`; raises `AutologNoAmbientRunError` on None (loud-failure); BLOCKED rationalisation example shows `from kailash_ml.tracking.runner import _current_run  # BLOCKED outside tracking package`.
- `ml-rl-core-draft.md` L108, L411, L449, L463: `get_current_run()`.
- `ml-engines-v2-addendum-draft.md` L49 + L55 + L59 + L70 + L71: `from kailash_ml.tracking import get_current_run` + BLOCKED example shows internal access.
- `ml-serving-draft.md` L72: `tracker: Optional[ExperimentRun] = None` with ambient resolution via `get_current_run()`.
- `ml-automl-draft.md` L72 + L107: tracker resolution via `get_current_run()`.

**No public site calls `_current_run.get()` directly. Every BLOCKED example uses the internal symbol to demonstrate what is BLOCKED.**

**Verdict: GREEN.** CRIT-4 closed.

---

## Section B — HIGH Re-Verification (11 items, user-numbered from Round-2 YELLOW-1..10 + RED-1)

### HIGH-1 (was YELLOW-1) — Spec-version header parity

**Round-2 finding.** `ml-tracking-draft.md` Version: 2.0.0 / `ml-diagnostics-draft.md` Version: 0.18.0 — cross-spec drift per `rules/specs-authority.md §5b`.

**Phase-C fix applied?** YES.

**Sweep:** `rg '^(\*\*)?Version' specs-draft/` returns 15/15 drafts at `1.0.0 (draft)` per Decision 14.

**One format inconsistency found:** `ml-rl-core-draft.md` L3 uses `**Version:** 1.0.0 (draft)` (bold) while the other 14 drafts use `Version: 1.0.0 (draft)` (no bold). Value identical; format cosmetic. **MED finding (formatting-only).**

**Verdict: GREEN (value), MED (format).** HIGH-1 closed as HIGH; demoted to MED for format.

### HIGH-2 (was YELLOW-2) — `km.serve` top-level wrapper

**Round-2 finding.** Engine-level `engine.serve(...)` existed but no top-level `km.serve(...)`. Recommendation (a): add one-line wrapper.

**Phase-C fix applied?** YES.

**Evidence:**

- `ml-engines-v2-draft.md` §15.5 (L1458–1473): `async def serve(model_uri_or_result, *, alias=None, channels=("rest",), tenant_id=None, version=None, autoscale=False, options=None) -> "ServeHandle"`.
- `ml-serving-draft.md` §2.3.4 MUST (L164–184): "`km.serve` is a package-level function. It MUST NOT be added as a ninth method on `MLEngine`." Full implementation sketch with tenant-scoped cached engine + URI parsing.
- `ml-engines-v2-draft.md` §15.1 table (L1308–1319): `km.serve` listed as package-level wrapper; dispatches to `engine.serve(...)` on cached default engine.

**Verdict: GREEN.** HIGH-2 closed.

### HIGH-3 (was YELLOW-3) — `km.watch` top-level wrapper

**Round-2 finding.** Engine-level `engine.monitor(...)` existed but no top-level `km.watch(...)`.

**Phase-C fix applied?** YES.

**Evidence:**

- `ml-engines-v2-draft.md` §15.6 (L1475–1489): `async def watch(model_uri, *, reference=None, axes=("feature","prediction","performance"), alerts=None, tenant_id=None, actor_id=None) -> "DriftMonitor"`.
- `ml-drift-draft.md` §12 (L785–803): "In addition to the canonical `engine.monitor(...)` entry (§2.2), `kailash-ml` exports a package-level `km.watch(...)` wrapper that dispatches to the tenant-scoped cached default engine (per `ml-engines-v2.md §15.6`)." Full signature.

**Verdict: GREEN.** HIGH-3 closed.

### HIGH-4 (was YELLOW-4) — `DLDiagnostics.as_lightning_callback()` auto-attach at engine boundary (DL-2)

**Round-2 finding.** `as_lightning_callback()` exists in `ml-diagnostics §5.3`, but no MUST clause in `ml-engines-v2-draft.md §2.1 MUST 7` or `ml-engines-v2-addendum §E1` states that `TrainingPipeline._train_lightning` MUST append the diagnostics callback automatically when `get_current_run() is not None`.

**Phase-C fix applied?** **NO.**

**Sweep:**

- `rg 'as_lightning_callback' ml-engines-v2-draft.md` — **no matches.**
- `rg 'as_lightning_callback' ml-engines-v2-addendum-draft.md` — **no matches.**
- `ml-diagnostics-draft.md` L332 defines the return-type: `def as_lightning_callback(self) -> "lightning.pytorch.Callback": ...`. L849 describes a test that manually passes `callbacks=[diag.as_lightning_callback()]` to `Trainer.fit()`. **No spec mandates the engine to do this automatically.**

**Impact.** A user running `km.train(...)` inside `async with km.track(...)` will NOT get `DLDiagnostics` metrics emitted unless they manually construct `DLDiagnostics(model)` and wire the callback. The two specs describe the mechanism but do not wire it through the engine.

**Verdict: HIGH — OPEN.** Phase-C follow-up required: add explicit MUST clause to either (a) `ml-engines-v2-draft.md §2.1 MUST 7`, or (b) new `ml-engines-v2-addendum §E1.3`, stating: "`TrainingPipeline._train_lightning` MUST append `DLDiagnostics(model).as_lightning_callback()` to `trainer_kwargs['callbacks']` when `get_current_run() is not None`; users opting out pass `diagnostics=False` to `engine.fit()`." Same clause MUST cover `ModelCheckpoint` default (HIGH-6).

### HIGH-5 (was YELLOW-5) — Distributed strategy (DDP/FSDP/DeepSpeed) passthrough (DL-4)

**Round-2 finding.** `ml-diagnostics §5.5` closed the diagnostics side with `DistributionEnv` dataclass + rank-0 MUST rule. The engine-side passthrough (`Trainer(strategy=...)` kwargs in `TrainingPipeline._train_lightning`) was not specified.

**Phase-C fix applied?** **PARTIAL.**

**Sweep:**

- `ml-diagnostics-draft.md` L360–464: full `DistributionEnv` dataclass + detection protocol + FSDP full-weight norm + DeepSpeed ZeRO-3 safe grad extraction + Accelerate both-axis check + `RankSafetyCallback` cross-rank NaN detection. **CLOSED.**
- `ml-engines-v2-draft.md` L1284–1285 (§14 Future-Proofing table): "`DistributionEnv` dataclass captures `tp_size`, `pp_size`, `dp_size` explicitly; compatible with `accelerate launch --tp_size=N`." **REFERENCES DistributionEnv but no engine-side passthrough clause.**
- `rg 'trainer_strategy|L\.Trainer\(strategy|strategy=ctx|strategy="auto"' specs-draft/` — **no matches.**
- `rg 'DDP|FSDP|DeepSpeed' ml-engines-v2-draft.md` — 0 matches in MUST clauses of §2.1 or §3.2.
- `ml-engines-v2-draft.md` §3.2 MUST 4 (L541–545): `TrainingContext` carries accelerator/precision/tenant/tracker, but strategy=ddp/fsdp passthrough is not enumerated.

**Impact.** A multi-GPU user expects `km.train(data, trainer_strategy="ddp")` or `Trainer(strategy="fsdp")` to work; today the spec covers diagnostics but silently drops the strategy kwarg at the engine boundary.

**Verdict: HIGH — OPEN (partial).** Phase-C follow-up: add MUST clause to `ml-engines-v2-draft.md §3.2` `TrainingContext` fields or §2.1 MUST 7 enumerating: "Lightning `L.Trainer` kwargs MUST include `strategy=` resolved from `hyperparameters.get('trainer_strategy', 'auto')`, passing 'ddp' / 'fsdp' / 'fsdp2' / 'deepspeed' strings through to the Trainer constructor. Resolved strategy MUST be captured in `TrainingResult.lightning_trainer_config`."

### HIGH-6 (was YELLOW-6) — `ModelCheckpoint` default + `km.resume` (DL-6)

**Round-2 finding.** Diagnostics side has `checkpoint_state()` / `from_checkpoint()`; RL side has `resume_from=`. But the engine-level DL default `ModelCheckpoint` callback is not specified, and `km.resume(run_id)` top-level does not exist.

**Phase-C fix applied?** **NO.**

**Sweep:**

- `rg 'ModelCheckpoint' specs-draft/` — **no matches in ml-engines-v2 or ml-engines-v2-addendum.**
- `rg 'enable_checkpointing' specs-draft/` — **no matches.**
- `rg 'km\.resume' specs-draft/` — **no matches in top-level wrapper table.**
- `ml-engines-v2-draft.md` §15.1 package-level wrapper table (L1308–1319) lists 9 wrappers (`km.train`, `km.register`, `km.serve`, `km.watch`, `km.dashboard`, `km.diagnose`, `km.track`, `km.autolog`, `km.rl_train`) — NO `km.resume`.

**Impact.** A Lightning user whose training crashes at epoch 8/10 cannot resume via `km.resume(run_id)`; must hand-craft `L.Trainer(ckpt_path=...)`. `trainable.py:268`'s `enable_checkpointing=False` default is documented nowhere to flip.

**Verdict: HIGH — OPEN.** Phase-C follow-up: add clause in `ml-engines-v2-addendum §E4.3` (or new §E4) enumerating (1) `TrainingPipeline._train_lightning` installs `ModelCheckpoint(save_last=True, save_top_k=3, dirpath=~/.kailash_ml/checkpoints/<run_id>/)` by default; (2) top-level `km.resume(run_id)` function; (3) `enable_checkpointing` defaults to True. Lands in same PR as HIGH-4 (both address the same DL engine boundary).

### HIGH-7 (was YELLOW-7) — LR finder auto-invoke (`auto_find_lr`, DL-7)

**Round-2 finding.** `lr_range_test` appears in `ml-diagnostics §7` parity table as "Primitive (opt-in)"; no `auto_find_lr=True` kwarg on `MLEngine.fit()`.

**Phase-C fix applied?** **NO decision codified.**

**Sweep:**

- `rg 'auto_find_lr|lr_range_test|LRFinder' specs-draft/` returns 2 matches, both in `ml-diagnostics-draft.md` parity table / bundle description. **No MUST clause in ml-engines-v2-draft.md.**
- No explicit deferred-item file at `workspaces/kailash-ml-audit/deferred-items/dl-auto-lr.md`.

**Impact.** Round-2 recommended EITHER "add `auto_find_lr: bool = False` kwarg" OR "document LR finder is opt-in". Neither disposition is locked in 1.0.0. An ambiguous opt-in surface is a future `DeprecationWarning` / API break.

**Verdict: HIGH — OPEN.** Phase-C follow-up: pick disposition (recommend explicit documentation — "LR finder is a diagnostic primitive; call `DLDiagnostics.lr_range_test(model, data)` before `fit()`; `auto_find_lr` kwarg is a deferred-to-1.1 item"). Add one-sentence §DL-7 note to `ml-diagnostics-draft.md §7` parity table footnote.

### HIGH-8 (was YELLOW-8) — `HuggingFaceTrainable` family (DL-9)

**Round-2 finding.** `ml-diagnostics §5.4` provides `as_transformers_callback()`, but no `HuggingFaceTrainable` family exists in `ml-engines-v2-draft.md §3` for non-LLM HF models (vision, audio, tabular). Round-1 labeled this `DL-GAP-2` as out-of-scope deferral.

**Phase-C fix applied?** **NO.**

**Sweep:**

- `rg 'HuggingFaceTrainable|wrap_hf_trainer' specs-draft/` — **no matches.**
- `rg 'DL-GAP-2' specs-draft/` — ONE match in `ml-diagnostics-draft.md` L729 as a bundle-description deferral note: "`DL-GAP-2` — Per-step system metrics (GPU util, mem, power). Requires a separate thread polling `nvidia-ml-py`; target v0.19.0." **This is NOT the DL-9 HuggingFaceTrainable deferral; the label collides with a different gap.**
- No `deferred-items/hf-trainable.md` file.

**Impact.** A user passing a `transformers.Trainer` subclass into `km.train()` gets no signal — falls through `Trainable` protocol check and likely raises `UnsupportedTrainerError` with no remediation message pointing at kailash-align. The "deferral" RED is neither filed nor documented.

**Verdict: HIGH — OPEN.** Phase-C follow-up: EITHER (a) add `HuggingFaceTrainable` family to `ml-engines-v2-draft.md §3` (non-LLM HF models: vision, audio, tabular — one §, ~100 LOC), OR (b) file `workspaces/kailash-ml-audit/deferred-items/hf-trainable.md` with explicit scope, upstream issue link, and `UnsupportedTrainerError` remediation message template. Recommendation: (b) — safe for 1.0; shipping (a) in 1.1.

### HIGH-9 (was YELLOW-9) — RL MARL deferral

**Round-2 finding.** `ml-rl-core §1.2 item 3` documented MARL as non-goal with `FeatureNotYetSupportedError` — needed formalization as `deferred-items/rl-marl.md`.

**Phase-C fix applied?** YES (in-spec).

**Evidence:**

- `ml-rl-core-draft.md` L38: "Multi-agent RL (MARL / PettingZoo) — RC-02. Non-goal. `kailash-ml` does not ship PettingZoo adapters, does not accept `pettingzoo.ParallelEnv`, and does not plan to. Users needing MARL MUST use RLlib directly; this is DOCUMENTED and will not change across the 1.x line. Passing a PettingZoo env raises `RLEnvIncompatibleError` with an explicit 'MARL is a documented non-goal' remediation."
- `ml-rl-core-draft.md` L1015 (error taxonomy): `FeatureNotYetSupportedError` + `RLEnvIncompatibleError` both enumerated.
- `ml-rl-core-draft.md` L1174 (competitor parity table row): MARL = NO (documented) for kailash-ml, NO for MLflow, YES for RLlib.

**Note:** `workspaces/kailash-ml-audit/deferred-items/` directory does NOT exist (confirmed via `Glob`). The deferral is fully in-spec rather than a separate file. This is defensible — the spec IS authoritative.

**Verdict: GREEN.** HIGH-9 closed.

### HIGH-10 (was YELLOW-10) — RL distributed rollout deferral

**Round-2 finding.** `ml-rl-core §1.2 item 4 + §11.2` documented; needed formalization as `deferred-items/rl-distributed.md`.

**Phase-C fix applied?** YES (in-spec).

**Evidence:**

- `ml-rl-core-draft.md` L986: "Multi-node distributed rollout (Ray actor placement, parameter-server replication) is `[rl-distributed]` extra for a follow-on release. Users who need it today MUST drop to rllib directly — `rl_train` does not silently no-op when asked for multi-node parallelism; it raises `FeatureNotYetSupportedError` with an upstream issue link."
- `ml-rl-core-draft.md` L1015: `FeatureNotYetSupportedError` in error taxonomy.
- `ml-rl-core-draft.md` L9: "Closes round-2b open-TBDs: RC-03 (distributed rollout)".

**Verdict: GREEN.** HIGH-10 closed.

### HIGH-11 (was RED-1) — README Quick Start rewrite (F-QUICK-START-PRIMITIVE)

**Round-2 finding.** `packages/kailash-ml/README.md` Quick Start sells the 40-line primitive path (FeatureStore + ModelRegistry + TrainingPipeline + InferenceServer ceremony). The engine-first 5-line flow is buried.

**Phase-C fix applied?** **NO.**

**Evidence (re-derived from `packages/kailash-ml/README.md` at HEAD, 2026-04-21):**

- L7: `**Version**: 0.9.0` — violates Decision 14 (MAJOR 1.0.0) AND `rules/documentation.md` ("Version Numbers Must Match pyproject.toml").
- L56–80: Quick Start imports `ConnectionManager` + `FeatureStore` + `ModelRegistry` + `LocalFileArtifactStore` + `TrainingPipeline` + `ModelSpec` + `EvalSpec` + `InferenceServer` + `FeatureSchema` + `FeatureField` — **nine imports for a Quick Start**. The 5-line `km.train + km.track + kailash-ml-dashboard` flow from `ml-engines-v2-addendum §E2.1` is not present.

**Impact.** Newbie-UX finding F-QUICK-START-PRIMITIVE is empirically reproducible today — the README sells primitives, not the engine-first surface. Users who read only the README never discover `km.*`.

**Verdict: HIGH — OPEN (operational).** Phase-C follow-up (release-PR edit, not spec edit): rewrite `packages/kailash-ml/README.md` Quick Start to demonstrate the engine-first 5-line flow; bump README version line from 0.9.0 → 1.0.0; demote the primitive path to an "Advanced" section. Required in same PR as the spec-promotion commit (per `rules/documentation.md`).

---

## Section C — Approved Decisions Propagation Audit (14 decisions)

Independent grep of each decision against the 15 ML drafts + 6 supporting specs.

| #   | Decision                                         | Sweep                                                                                                                                                                      | Grep matches                                                                                                                                                                                                         | Verdict                              |
| --- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| 1   | Status vocabulary FINISHED-only                  | `rg 'FINISHED\|SUCCESS\|COMPLETED' ml-tracking-draft.md`                                                                                                                   | 14 hits, all FINISHED-only at write/read; legacy coerced via `1_0_0_rename_status`                                                                                                                                   | **GREEN**                            |
| 2   | GDPR erasure: immutable audit, hash fingerprints | `rg 'ErasureRefusedError\|sha256:' specs-draft/`                                                                                                                           | `ml-tracking §8.1` + §9.1 `ErasureRefusedError`; event-payload hashing in tracking §9                                                                                                                                | **GREEN**                            |
| 3   | Rust status enum 4-member parity                 | `rg 'RUNNING, FINISHED, FAILED, KILLED\|byte-identical' specs-draft/`                                                                                                      | `ml-tracking §3.2` + §3.5; cross-SDK parity note                                                                                                                                                                     | **GREEN**                            |
| 4   | DDP rank-0 hardcoded                             | `rg 'Decision 4\|rank-0\|get_rank\(\) == 0' specs-draft/`                                                                                                                  | 25 hits across ml-tracking §10.3, ml-diagnostics §4.5 + §5.5, ml-autolog §3.3, ml-rl-core §8.8 — all describe hardcoded, not configurable                                                                            | **GREEN**                            |
| 5   | XPU dual-path (torch.xpu native + ipex fallback) | `rg 'intel_extension_for_pytorch\|ipex\|native.*xpu' ml-backends-draft.md`                                                                                                 | L46: "OPEN QUESTION whether torch ≥ 2.5 native XPU suffices"; L137 `xpu_via_ipex` field; L524 still listed as OPEN QUESTION                                                                                          | **HIGH — OPEN (new)**                |
| 6   | `backend-compat-matrix.yaml` + km.doctor         | `rg 'backend-compat-matrix' specs-draft/`                                                                                                                                  | 0 hits                                                                                                                                                                                                               | **HIGH — OPEN (new)**                |
| 7   | CPU+MPS BLOCKING / CUDA BLOCKING on runner       | `rg 'BLOCKING\|macos-14\|self-hosted' ml-backends-draft.md`                                                                                                                | L369: "GPU jobs are non-blocking at 2.0" — contradicts Decision 7's "CUDA becomes BLOCKING the day a self-hosted runner lands"; no "infra todo" language                                                             | **HIGH — OPEN (new)**                |
| 8   | Lightning hard lock-in                           | `rg 'Decision 8\|UnsupportedTrainerError\|hard lock' specs-draft/`                                                                                                         | 19 hits across ml-tracking, ml-engines-v2 §3.2 MUST 2, ml-rl-core, ml-autolog                                                                                                                                        | **GREEN**                            |
| 9   | Rust `ExperimentTracker` explicit start/end      | `rg 'Decision 9\|AsyncDrop\|start_run.*end_run' specs-draft/`                                                                                                              | `ml-engines-v2-draft.md` L1065: "Python uses `async with run:` ... Rust uses explicit `start_run()` / `end_run()` (AsyncDrop not stable). Same observable behavior; different syntactic surface per language idiom." | **GREEN**                            |
| 10  | Single-spec, rust overlay in variants/rs/        | `rg 'Decision 10\|variants/rs' specs-draft/`                                                                                                                               | `ml-engines-v2-draft.md` L1067: "one canonical spec per domain. Rust-specific clauses (when divergent) live in `loom/.claude/variants/rs/specs/ml-*.md` overlay"                                                     | **GREEN**                            |
| 11  | Legacy namespace remove at 3.0                   | `rg 'Decision 11\|kailash_ml\.legacy' specs-draft/`                                                                                                                        | `ml-engines-v2-draft.md` §8 + §10.4 6 full lifecycle; `ml-rl-core §13.4`                                                                                                                                             | **GREEN**                            |
| 12  | Cross-tenant admin: `MultiTenantOpError`         | `rg 'MultiTenantOpError' specs-draft/ supporting-specs-draft/`                                                                                                             | 5 hits in `supporting-specs-draft/kailash-core-ml-integration-draft.md §3.3` and `pact-ml-integration-draft.md` §3 — **ZERO hits in ml-\*-draft.md error taxonomies**                                                | **MED — OPEN (new, cross-spec gap)** |
| 13  | Extras hyphen convention                         | `rg '\[(rl_offline\|rl_envpool\|rl_distributed\|rl_bridge\|autolog_lightning\|autolog_transformers\|feature_store\|reinforcement_learning\|deep_learning)\]' specs-draft/` | 0 hits                                                                                                                                                                                                               | **GREEN**                            |
| 14  | Package version 1.0.0 MAJOR                      | `rg 'kailash-ml 2\.0\|ml 0\.17\|ml 0\.18\|ml 0\.19' specs-draft/`                                                                                                          | **8 hits across 6 files — see new HIGH-N1 below**                                                                                                                                                                    | **HIGH — OPEN (new)**                |

---

## Section D — NEW Findings Surfaced By The Full Mechanical Sweep

Per `rules/specs-authority.md §5b` the sibling-spec sweep surfaces classes of drift that narrow-scope audits miss. Round-3 mechanical re-derivation surfaced FIVE new findings not enumerated in Round-2:

### NEW HIGH-N1 — Decision 14 Package-version drift (stale 2.0 / 0.17 / 0.18 / 0.19 references)

**Sweep:** `rg 'kailash-ml 2\.0|ml 0\.17|ml 0\.18|ml 0\.19' specs-draft/`

**Findings (8 matches across 6 files):**

| File                               | Line | Text                                                                              |
| ---------------------------------- | ---- | --------------------------------------------------------------------------------- |
| `ml-engines-v2-addendum-draft.md`  | 423  | `\| Capability ... \| kailash-ml 2.0 \| Kubeflow ...`                             |
| `ml-autolog-draft.md`              | 578  | `\| Competitor \| Autolog API ... \| kailash-ml 2.0 parity via this spec ... \|`  |
| `ml-feature-store-draft.md`        | 550  | `\| Capability ... \| kailash-ml 2.0 \| Feast \| Hopsworks ...`                   |
| `ml-automl-draft.md`               | 497  | `\| Capability ... \| kailash-ml 2.0 \| FLAML \| AutoGluon ...`                   |
| `ml-rl-align-unification-draft.md` | 25   | `RLTrainingResult (kailash-ml 0.17.0) vs AlignmentResult ...`                     |
| `ml-rl-align-unification-draft.md` | 371  | `kailash-ml 0.18.0 — ships RLLifecycleProtocol ...`                               |
| `ml-diagnostics-draft.md`          | 1032 | `Python surface: kailash_ml.diagnostics lands all adapters in kailash-ml 0.18.0.` |
| `ml-engines-v2-draft.md`           | 899  | `kailash-ml 2.0 replaces the v0.9.x 18-class public surface.`                     |

**Impact.** Every competitor-parity table column header labels the kailash-ml implementation as "kailash-ml 2.0" while Decision 14 pins the release at 1.0.0. README, docs site, CHANGELOG, and downstream consumer docs (aegis/aether/kz-engage) will quote these tables verbatim and publish the wrong version. Release PR will fail `rules/documentation.md` ("Version Numbers Must Match pyproject.toml").

**Verdict: HIGH — OPEN.** Phase-C follow-up: `sed -i '' 's/kailash-ml 2\.0/kailash-ml 1.0/g; s/kailash-ml 0\.17\.0/kailash-ml 1.0.0/g; s/kailash-ml 0\.18\.0/kailash-ml 1.0.0/g; s/kailash-ml 0\.19\.0/kailash-ml 1.0.0/g' specs-draft/ml-*.md` with spot-verify on each hit (line 25 + 371 of `ml-rl-align-unification-draft.md` might need manual review — some references are to historical versions and need context).

### NEW HIGH-N2 — Decision 5 XPU dual-path not codified

**Finding.** Approved decision 5 mandates: "Accept both `torch.xpu.is_available()` (torch ≥ 2.5 native) AND `intel_extension_for_pytorch` (ipex fallback). Native-first probe order. No sole-dependency lock-in."

**Evidence in ml-backends-draft.md:**

- L28 (backend table): install command is `pip install kailash-ml[xpu]` which "pulls `intel-extension-for-pytorch`" — single-dependency lock-in; no mention of native-first.
- L46 (table footnote): "xpu — requires `intel-extension-for-pytorch` at 2.0 (OPEN QUESTION whether torch ≥ 2.5 native XPU suffices)."
- L81 (detect_backend priority): `hasattr(torch, "xpu") and torch.xpu.is_available()` — matches native path, but no fallback clause when that fails.
- L137: `xpu_via_ipex: bool | None` field on `BackendInfo` — optional, not authoritative order.
- L524: still listed as OPEN QUESTION #4.

**Impact.** A user with torch 2.5 native XPU but no ipex installed will be told to install the `[xpu]` extra (which installs ipex); a user with ipex only will also work. Neither path is authoritatively "native-first". The OPEN QUESTION language directly contradicts Decision 5.

**Verdict: HIGH — OPEN.** Phase-C follow-up: rewrite `ml-backends-draft.md §2.2` priority step 4 to: "xpu — probe `torch.xpu.is_available()` first (torch ≥ 2.5 native); on False, probe `import intel_extension_for_pytorch; ipex.xpu.is_available()` (ipex fallback). Accept either path; `xpu_via_ipex` field on BackendInfo records which path resolved." Remove OPEN QUESTION #4.

### NEW HIGH-N3 — Decision 6 `backend-compat-matrix.yaml` + km.doctor consumer not specified

**Finding.** Approved decision 6 mandates: "`backend-compat-matrix.yaml` as data in `packages/kailash-ml/data/backend-compat-matrix.yaml`. `km.doctor` subcommand reads it. Update without SDK release."

**Evidence in ml-backends-draft.md:**

- `rg 'backend-compat-matrix' specs-draft/` returns **0 hits**.
- `ml-backends-draft.md §7` specifies `km.doctor()` but does NOT reference a YAML config file; the architecture cutoff table is inlined as markdown (§4).

**Impact.** The "update without SDK release" capability (Decision 6) is unimplementable as specced — km.doctor has no YAML consumer, and the hardware-architecture compat matrix is frozen into the spec markdown. New architectures require a spec edit + SDK release, contradicting the approved design.

**Verdict: HIGH — OPEN.** Phase-C follow-up: add `ml-backends-draft.md §4.1` (or new §8) specifying: file path `packages/kailash-ml/data/backend-compat-matrix.yaml`, YAML schema (family → architecture → {min_compute, recommended_driver, onnx_ep_compatible}), `km.doctor` loader contract ("reads from `importlib.resources.files('kailash_ml.data') / 'backend-compat-matrix.yaml'`; falls back to bundled default on missing file"), and "update path: edit YAML + pip install --upgrade kailash-ml-data (separate wheel) without main SDK release."

### NEW HIGH-N4 — Decision 7 CI runner policy inverted

**Finding.** Approved decision 7 mandates: "CPU + MPS (macos-14) BLOCKING now. CUDA becomes BLOCKING the day a self-hosted runner lands. Track runner acquisition as explicit infra todo."

**Evidence in ml-backends-draft.md L369:**

> "The `cpu` job is non-optional and blocks merge. **GPU jobs are non-blocking at 2.0** but MUST report status."

**This contradicts Decision 7 on two points:**

1. MPS (macos-14 on GitHub free) is BLOCKING per Decision 7 but listed as "non-blocking" here.
2. "CUDA becomes BLOCKING the day a self-hosted runner lands" — no clause, no infra-todo reference.

**Verdict: HIGH — OPEN.** Phase-C follow-up: rewrite `ml-backends-draft.md §6.3` to: "`cpu` + `mps` (GitHub `macos-14` runner) are BLOCKING and fail the merge on red (Decision 7). `cuda` / `rocm` / `xpu` / `tpu` are non-blocking today; `cuda` flips to BLOCKING at the same PR that registers a self-hosted NVIDIA runner — see `workspaces/kailash-ml-audit/todos/runner-acquisition.md` infra-todo (Decision 7)."

### NEW MED-N5 — Decision 12 `MultiTenantOpError` not cross-referenced in ml-registry error taxonomy

**Finding.** Decision 12 says: "`MultiTenantOpError` raised in 1.0.0. Ship PACT-gated cross-tenant spec (`ml-registry-pact.md`) post-1.0."

**Evidence:**

- `MultiTenantOpError` IS defined in `supporting-specs-draft/kailash-core-ml-integration-draft.md §3.3` (5 hits).
- `MultiTenantOpError` is NOT mentioned in `ml-registry-draft.md §9` error taxonomy (which only enumerates registry-domain errors).
- Per `rules/specs-authority.md §5b` every sibling spec that is a downstream consumer of an error MUST re-declare it.

**Impact.** A user calling `await registry.export(tenant_id=A, to_tenant=B)` gets `MultiTenantOpError` but cannot trace the error taxonomy from `ml-registry-draft.md`; they must cross-hop to the supporting-specs bundle.

**Verdict: MED — OPEN.** Phase-C follow-up: add one-line note to `ml-registry-draft.md §9`: "Cross-tenant operations raise `kailash.ml.errors.MultiTenantOpError` (Decision 12; defined in `kailash-core-ml-integration.md §3.3`; PACT-gated cross-tenant spec ships post-1.0 as `ml-registry-pact.md`)." Same pattern for `ml-feature-store-draft.md §9` and `ml-serving-draft.md §18`.

### NEW MED-N6 — Version header format inconsistency

**Finding.** 14/15 ML drafts use `Version: 1.0.0 (draft)` (no markdown bold); `ml-rl-core-draft.md` L3 uses `**Version:** 1.0.0 (draft)` (bold).

**Impact.** Cosmetic; `rules/specs-authority.md §5b` sibling-sweep prefers uniform formatting for grep-ability (`rg '^Version:'` vs `rg '^\*\*Version'`).

**Verdict: MED — OPEN.** Phase-C trivial: strip the two asterisks on `ml-rl-core-draft.md` L3.

### NEW MED-N7 — `deferred-items/` directory referenced but not present

**Finding.** Round-2 recommendations for YELLOW-8/9/10 and DL-GAP-1/2 referenced formalizing deferrals as `workspaces/kailash-ml-audit/deferred-items/rl-marl.md`, `rl-distributed.md`, `hf-trainable.md`. The directory does not exist.

**Disposition:** Since HIGH-9 (MARL) and HIGH-10 (distributed rollout) are GREEN via in-spec `FeatureNotYetSupportedError` mandates, the external `deferred-items/` file is redundant. BUT HIGH-8 (HuggingFaceTrainable) — if disposition (b) is chosen — needs one.

**Verdict: MED — OPEN (conditional on HIGH-8 disposition).**

---

## Section E — Consolidated Verdict

### E.1 CRIT (user-enumerated 4/4)

| ID     | Description                         | Round-2 Verdict | Round-3 Verdict |
| ------ | ----------------------------------- | --------------- | --------------- |
| CRIT-1 | Default DB URL drift                | GREEN           | **GREEN**       |
| CRIT-2 | `ExperimentTracker.create(...)`     | GREEN           | **GREEN**       |
| CRIT-3 | `MLError` hierarchy                 | GREEN           | **GREEN**       |
| CRIT-4 | `get_current_run()` public accessor | GREEN           | **GREEN**       |

**4/4 CRIT GREEN. Target 0 CRIT MET.**

### E.2 HIGH (user-enumerated 11 + 4 new)

| ID              | Description                                              | Round-2 Verdict | Round-3 Verdict                                              |
| --------------- | -------------------------------------------------------- | --------------- | ------------------------------------------------------------ |
| HIGH-1          | Spec-version header parity                               | YELLOW          | **GREEN** (MED format variance → HIGH-N6)                    |
| HIGH-2          | `km.serve` top-level                                     | YELLOW          | **GREEN**                                                    |
| HIGH-3          | `km.watch` top-level                                     | YELLOW          | **GREEN**                                                    |
| HIGH-4          | Lightning callback auto-attach at engine boundary (DL-2) | YELLOW          | **HIGH — OPEN**                                              |
| HIGH-5          | Distributed strategy passthrough (DL-4)                  | YELLOW          | **HIGH — OPEN** (partial; diag side closed, engine side not) |
| HIGH-6          | `ModelCheckpoint` default + `km.resume` (DL-6)           | YELLOW          | **HIGH — OPEN**                                              |
| HIGH-7          | `auto_find_lr` disposition (DL-7)                        | YELLOW          | **HIGH — OPEN**                                              |
| HIGH-8          | `HuggingFaceTrainable` family (DL-9)                     | YELLOW          | **HIGH — OPEN**                                              |
| HIGH-9          | RL MARL deferral                                         | YELLOW          | **GREEN**                                                    |
| HIGH-10         | RL distributed rollout deferral                          | YELLOW          | **GREEN**                                                    |
| HIGH-11         | README Quick Start (operational)                         | RED             | **HIGH — OPEN**                                              |
| **NEW HIGH-N1** | Package version drift (stale 2.0 / 0.17 / 0.18)          | n/a             | **HIGH — OPEN**                                              |
| **NEW HIGH-N2** | Decision 5 XPU dual-path not codified                    | n/a             | **HIGH — OPEN**                                              |
| **NEW HIGH-N3** | Decision 6 backend-compat-matrix not specified           | n/a             | **HIGH — OPEN**                                              |
| **NEW HIGH-N4** | Decision 7 CI runner policy inverted                     | n/a             | **HIGH — OPEN**                                              |

**Target 0 HIGH NOT met. 9 HIGH still open (5 from Round-2 + 4 surfaced new).**

### E.3 MED (new only — Round-2 did not enumerate MED)

| ID     | Description                                                                    | Verdict                                |
| ------ | ------------------------------------------------------------------------------ | -------------------------------------- |
| MED-N5 | `MultiTenantOpError` not in ml-registry/feature-store/serving error taxonomies | **MED — OPEN**                         |
| MED-N6 | Version header format: `**Version:**` vs `Version:`                            | **MED — OPEN**                         |
| MED-N7 | `deferred-items/` directory referenced but absent                              | **MED — OPEN** (conditional on HIGH-8) |

---

## Section F — Phase-C Follow-Up Shard (Before /codify Gate)

Ordered by blast radius. Each item is a one-paragraph spec edit; total estimated autonomous cycles: ≤1 session per `rules/autonomous-execution.md` 10× multiplier.

1. **HIGH-N1 (version drift) — one-shot `sed` sweep.** Replace `kailash-ml 2.0` / `kailash-ml 0.17.0` / `kailash-ml 0.18.0` / `kailash-ml 0.19.0` → `kailash-ml 1.0.0` across 6 spec files, 8 line-locations. Spot-verify `ml-rl-align-unification-draft.md` L25 + L371 for historical-vs-current disambiguation.
2. **HIGH-11 (README rewrite) — release PR edit.** Rewrite `packages/kailash-ml/README.md` Quick Start to the 5-line `km.*` flow; bump version line 0.9.0 → 1.0.0; demote primitives to "Advanced" section. Same PR as spec promotion.
3. **HIGH-4 + HIGH-6 (engine-boundary callback + ModelCheckpoint + km.resume) — single spec-edit.** Add `ml-engines-v2-addendum §E1.3` (or equivalent) enumerating: (a) `TrainingPipeline._train_lightning` MUST append `DLDiagnostics(model).as_lightning_callback()` to `trainer_kwargs['callbacks']` when `get_current_run() is not None`; (b) `TrainingPipeline._train_lightning` MUST install `ModelCheckpoint(save_last=True, save_top_k=3, dirpath=~/.kailash_ml/checkpoints/<run_id>/)` by default; (c) `enable_checkpointing=True` default; (d) top-level `km.resume(run_id)` added to `ml-engines-v2-draft.md §15.1` wrapper table. ~80 LOC in one addendum section.
4. **HIGH-5 (DDP/FSDP strategy passthrough) — one MUST clause in `ml-engines-v2-draft.md §3.2` `TrainingContext` fields.** "Lightning `L.Trainer` kwargs MUST include `strategy=` resolved from `hyperparameters.get('trainer_strategy', 'auto')`; resolved strategy MUST be captured in `TrainingResult.lightning_trainer_config`."
5. **HIGH-N4 (CI runner policy) — rewrite `ml-backends-draft.md §6.3` per Decision 7.** `cpu`+`mps` BLOCKING; `cuda` flips to BLOCKING on self-hosted runner acquisition; infra-todo reference.
6. **HIGH-N2 (XPU dual-path) — rewrite `ml-backends-draft.md §2.2` step 4 per Decision 5.** Native-first `torch.xpu.is_available()`, ipex fallback. Remove OPEN QUESTION #4.
7. **HIGH-N3 (backend-compat-matrix YAML) — add new §4.1 (or §8) per Decision 6.** File path, schema, loader contract, update-without-release path.
8. **HIGH-7 (auto_find_lr disposition) — one-sentence footnote on `ml-diagnostics-draft.md §7` parity table.** "LR finder is a diagnostic primitive; `auto_find_lr=True` kwarg deferred to 1.1."
9. **HIGH-8 (HuggingFaceTrainable) — file `workspaces/kailash-ml-audit/deferred-items/hf-trainable.md`** (disposition b) with scope + upstream issue link + `UnsupportedTrainerError` remediation template. Add one-line note to `ml-engines-v2-draft.md §14 Future-Proofing` table.
10. **MED-N5 (MultiTenantOpError cross-ref) — 3 one-line additions** to `ml-registry-draft.md §9`, `ml-feature-store-draft.md §9`, `ml-serving-draft.md §18`. "Cross-tenant operations raise `kailash.ml.errors.MultiTenantOpError` (Decision 12)."
11. **MED-N6 (version header format) — trivial edit.** Strip `**` bold from `ml-rl-core-draft.md` L3.
12. **MED-N7 (deferred-items directory) — create iff HIGH-8 disposition (b) chosen.**

---

## Section G — Convergence Readiness

- **Round 3 did NOT converge to 0 CRIT + 0 HIGH.** 0 CRIT MET; 9 HIGH open.
- **Round 4 MUST run after the Phase-C follow-up shard above lands**, re-deriving every check from scratch per audit-mode rule. Running `/redteam` on the current spec-draft set would re-surface the 9 HIGH as HIGH findings.
- **The rules-reminder system flagged 7 distinct rule contexts** during this audit: `rules/refactor-invariants.md`, `rules/documentation.md`, `rules/specs-authority.md §5b`, `rules/testing.md` audit-mode re-derivation, `rules/terrene-naming.md` (independence + CC-BY-4.0), `rules/artifact-flow.md` (loom/ authority chain), `workspaces/CLAUDE.md` (phase contract). All checks in this report honor those rules. The `/redteam` round 3 scoping did NOT edit any `.claude/` artefact; output is confined to `workspaces/kailash-ml-audit/04-validate/`.

---

**Output path:** `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-3-cross-spec-consistency.md`

**Total sweeps executed (re-derived from scratch, no trust of prior rounds):**

1. `rg 'kailash-ml\.db|kailash_ml\.db|ml\.db' specs-draft/` — 28 matches, all canonical or migration-context.
2. `rg 'ExperimentTracker\.(create|open|__init__)|ExperimentTracker\(' specs-draft/` — GREEN, `.open` only inside BLOCKED example.
3. `rg 'class \w+Error\(' specs-draft/` — every leaf chains through MLError family.
4. `rg 'get_current_run|_current_run|get_current_tenant_id' specs-draft/ supporting-specs-draft/` — public accessor used everywhere; direct \_current_run.get() only in BLOCKED examples.
5. `rg '^(\*\*)?Version:' specs-draft/ supporting-specs-draft/` — 15+6 drafts at `1.0.0 (draft)`.
6. `rg '\[(rl_offline|...|reinforcement_learning|deep_learning)\]' specs-draft/` — 0 underscore-extras.
7. `rg 'km\.serve|km\.watch|km\.diagnose|km\.resume' specs-draft/` — serve/watch/diagnose present; resume absent.
8. `rg 'Decision [1-9]|Decision 1[0-4]' specs-draft/` — 65 references; decisions 5/6/7/14 partially-codified or contradicted.
9. `rg 'kailash-ml 2\.0|ml 0\.17|ml 0\.18|ml 0\.19' specs-draft/` — 8 stale version mentions.
10. `rg 'MultiTenantOpError' specs-draft/ supporting-specs-draft/` — present in supporting specs only.
11. `rg 'intel_extension_for_pytorch|ipex|backend-compat-matrix' specs-draft/` — XPU dual-path + YAML file undeclared.
12. `rg 'BLOCKING|macos-14|self-hosted' ml-backends-draft.md` — CI policy contradicts Decision 7.
13. `rg 'ModelCheckpoint|as_lightning_callback|enable_checkpointing|trainer_strategy|HuggingFaceTrainable|auto_find_lr' specs-draft/` — 4 distinct engine-boundary MUST clauses absent.

All 13 sweeps performed directly via Grep tool without consulting prior Round-2 verdicts.
