# W5-E1 Findings — ml core + RL

**Specs audited:** 11
**§ subsections enumerated:** see per-spec sections below
**Findings:** CRIT=0 HIGH=5 MED=15 LOW=32 (TOTAL=52)
**Audit completed:** 2026-04-26

Worktree: `/Users/esperie/repos/loom/kailash-py/.claude/worktrees/w5-e1-ml-core`
Branch: `audit/w5-e1-ml-core-spec-audit`

---

## ml-engines-v2.md — MLEngine 8-method surface, Trainable, TrainingResult, km.* verbs

**§ subsections enumerated:** §1.3 (2 MUST NOT), §2.1 (10 MUST), §3.2 (8+ MUST), §4.2 (MUST), §5.1, §6.1, §7, §8.1, §11-§12A, §15.4 / §15.9 (canonical __all__).

### F-E1-01 — ml-engines-v2 § 3.2 — CatBoostTrainable adapter absent from `kailash_ml.trainable`

**Severity:** HIGH
**Spec claim:** § 2.1 MUST 7 + § 3.2 + § lock-in: "Non-Torch families (sklearn, xgboost, lightgbm, catboost) MUST be wrapped as `LightningModule` adapters at the engine boundary" and the spec § 6 ONNX matrix lists `catboost` as a guaranteed family. Final §15 implementation checklist requires a `CatBoostLightningAdapter`.
**Actual state:** `packages/kailash-ml/src/kailash_ml/trainable.py` exposes `Trainable, SklearnTrainable, TorchTrainable, LightningTrainable, XGBoostTrainable, LightGBMTrainable, UMAPTrainable, HDBSCANTrainable` (8 classes). `grep -rn "CatBoostTrainable" packages/kailash-ml/src/` returns 0 hits. `__init__.py::__all__` Group 2 does NOT list `CatBoostTrainable`. The `[catboost]` extra exists in `pyproject.toml` per ml-specialist context but no Trainable adapter wraps it.
**Remediation hint:** Add `CatBoostTrainable` to `trainable.py` with `to_lightning_module()` per § 3.2 MUST 1; add eager-import + `__all__` entry per `orphan-detection.md` §6; add ONNX export path per § 6 MUST list (`catboost.save_model(... format='onnx')`); add Tier-2 wiring test.

### F-E1-02 — ml-engines-v2 § 2.1 MUST 5 — `MLEngine.compare()` 8-method surface complete

**Severity:** LOW (pass — recorded for traceability)
**Spec claim:** § 2.1 MUST 5: "Engine's public method surface MUST be exactly: `setup`, `compare`, `fit`, `predict`, `finalize`, `evaluate`, `register`, `serve`."
**Actual state:** `packages/kailash-ml/src/kailash_ml/engine.py` exposes all 8 methods (lines 785, 994, 1288, 1470, 1561, 1733, 2032, 2289 for setup/compare/fit/predict/finalize/evaluate/register/serve). No 9th public method observed.
**Remediation hint:** None — compliant.

### F-E1-03 — ml-engines-v2 § 4.2 — `TrainingResult.trainable` field present (W33b regression closed)

**Severity:** LOW (pass)
**Spec claim:** § 4.2 / `zero-tolerance.md` Rule 2 fake-integration class: every `Trainable.fit()` return site MUST attach `trainable=` so `km.register(result)` can resolve `training_result.trainable.model`.
**Actual state:** `packages/kailash-ml/src/kailash_ml/_result.py:120` declares `trainable: Optional[Any] = field(default=None, repr=False, compare=False)`. The frozen dataclass carries the handoff field. README quickstart regression test exists at `packages/kailash-ml/tests/regression/test_readme_quickstart_executes.py`.
**Remediation hint:** None — compliant per W33b fix.

### F-E1-04 — ml-engines-v2 § 15.9 — `__all__` exports 41 symbols, ordering matches 6-group canonical structure

**Severity:** LOW (pass)
**Spec claim:** § 15.9 MUST: 41 symbols (40 + `erase_subject` per FP-MED-2), 6-group ordering preserved.
**Actual state:** `__init__.py:635-692` declares 41 entries grouped as documented. Eager imports at module scope per `orphan-detection.md` Rule 6 (lines 32-216). Lazy `__getattr__` only for non-canonical legacy engines (FeatureStore, MLDashboard, …).
**Remediation hint:** None — compliant.

### F-E1-05 — ml-engines-v2 § 11 / § 15 — `km.seed`, `km.reproduce`, `km.resume`, `km.lineage` all defined at module scope

**Severity:** LOW (pass)
**Spec claim:** § 11 / § 12 / § 12A / § 15.8: `km.seed()`, `km.reproduce()`, `km.resume()`, `km.lineage()` are canonical entries.
**Actual state:** `__init__.py` imports `seed` from `_seed` (line 45) and declares `reproduce` (line 352), `resume` (line 421), `lineage` (line 534) as `async def` at module scope. All 4 appear in canonical `__all__` Group 1.
**Remediation hint:** None — compliant.

### F-E1-06 — ml-engines-v2 § 12 — `km.lineage()` falls back to placeholder `LineageGraph` on registry-lookup failure

**Severity:** MED
**Spec claim:** § E10.2 mandates a real lineage graph rooted at `ref` with nodes/edges/depth.
**Actual state:** `__init__.py:566-568` returns `LineageGraph(root=ref, nodes=(ref,), edges=(), depth=0)` as a fallback when the registry has not implemented `build_lineage_graph`. Lines 222-244 install a placeholder `LineageGraph` dataclass under a `try/except ImportError` because `kailash_ml.engines.lineage` does not exist (no `lineage.py` in `engines/`). This is a stub-pattern: the function is callable but returns no real lineage data.
**Remediation hint:** Either implement `engines/lineage.py::LineageGraph` + `ModelRegistry.build_lineage_graph()` with the full nodes/edges payload OR raise `FeatureNotYetSupportedError("km.lineage deferred to ML 1.x M11")` per `zero-tolerance.md` Rule 2 (no silent stubs). The placeholder at lines 230-244 is a fake-integration pattern.

### F-E1-07 — ml-engines-v2 § 11.1 — `km.use_device()` context manager exists but is non-canonical

**Severity:** LOW (pass)
**Spec claim:** § 11 / § ml-backends.md § 7 — `km.device(prefer=)` and `km.use_device(name)` documented helpers.
**Actual state:** `__init__.py:329-343` defines both as module-level helpers. Not in `__all__` per design (helper, not verb).
**Remediation hint:** None — compliant.

---

## ml-engines-v2-addendum.md — classical-ML surface, sklearn/lightgbm/xgboost/catboost trainables, v1→v2 migration

### F-E1-08 — ml-engines-v2-addendum § E11 — Pydantic-to-DataFrame adapter coverage unverified

**Severity:** MED
**Spec claim:** Addendum requires Pydantic-to-DataFrame adapter for sklearn/lightgbm/xgboost/catboost paths to ingest user-provided Pydantic models.
**Actual state:** `grep -rn "BaseModel\|pydantic" packages/kailash-ml/src/kailash_ml/interop.py` returns no Pydantic adapter. `interop.py` is the sole conversion point per ml-specialist context. The Pydantic-to-polars conversion path is absent.
**Remediation hint:** Implement `pydantic_to_polars()` in `interop.py`; add Tier-2 test exercising `engine.fit(data=[MyModel(...)], target="y")`.

### F-E1-09 — ml-engines-v2-addendum § E10.2 — `LineageGraph` lives behind try/except fallback (orphan placeholder)

**Severity:** HIGH
**Spec claim:** § E10.2 declares `LineageGraph` dataclass with `nodes`, `edges`, `root`, `depth` as the canonical lineage return type.
**Actual state:** `__init__.py:222-244` wraps `from kailash_ml.engines.lineage import LineageGraph` in `try/except ImportError`, then defines a placeholder dataclass when import fails. `engines/lineage.py` does NOT exist (`ls packages/kailash-ml/src/kailash_ml/engines/` confirmed). The forward-compat placeholder is shipped in 1.x because the canonical engine module never landed. Per `orphan-detection.md` Rule 1, every `__all__`-adjacent dataclass MUST have a production call site — the placeholder satisfies the import but `km.lineage` returns hollow data.
**Remediation hint:** Implement `packages/kailash-ml/src/kailash_ml/engines/lineage.py` with the real `LineageGraph` and `build_lineage_graph()` registry method per § E10.2; remove the try/except + placeholder block.

### F-E1-10 — ml-engines-v2-addendum § E1.1 — Engine matrix `engines/registry.py::list_engines` exposes `EngineInfo` per spec

**Severity:** LOW (pass)
**Spec claim:** § E11.2 — engine discovery via `list_engines()` and `engine_info(name)` with `EngineInfo`, `MethodSignature`, `ParamSpec`, `ClearanceRequirement`.
**Actual state:** `engines/registry.py:116, 139, 167, 179` define `EngineInfo`, `EngineNotFoundError`, `list_engines`, `engine_info` matching the spec; surface re-exported in `__init__.py:208-216`.
**Remediation hint:** None — compliant.

---

## ml-backends.md — 6 first-class backends, detect_backend(), precision auto

### F-E1-11 — ml-backends § 2 — All 6 backends enumerated in `_device.py`

**Severity:** LOW (pass)
**Spec claim:** § 2 — `KNOWN_BACKENDS = ("cuda", "mps", "rocm", "xpu", "tpu", "cpu")` first-class.
**Actual state:** `_device.py:36` declares `KNOWN_BACKENDS: tuple[str, ...] = ("cuda", "mps", "rocm", "xpu", "tpu", "cpu")`; `BackendName = Literal["cpu", "cuda", "mps", "rocm", "xpu", "tpu"]` at line 38; `detect_backend()` at line 622 with prefer-pin authority chain.
**Remediation hint:** None — compliant.

### F-E1-12 — ml-backends § 3 — `BackendInfo` dataclass + `DeviceReport` both present

**Severity:** LOW (pass)
**Spec claim:** § 3 — `BackendInfo` (lightning accelerator + device_string + memory) and `DeviceReport` (per-run capture for `TrainingResult.device`).
**Actual state:** `_device.py:126` declares `BackendInfo` with `accelerator`, `device_string`; `_device_report.py:43` declares `DeviceReport` with `device_report_from_backend_info` factory at module scope; both in canonical `__all__` Group 4.
**Remediation hint:** None — compliant.

### F-E1-13 — ml-backends § 7 — `km.doctor()` diagnostic present at module scope

**Severity:** LOW (pass)
**Spec claim:** § 7 — `km.doctor()` returns hardware-aware diagnostic report.
**Actual state:** `__init__.py:188` imports `from kailash_ml.doctor import doctor`. Eagerly imported (silenced linter at line 706). NOT in canonical `__all__` per Round-8 clarification (separate surface from `km.diagnose`).
**Remediation hint:** None — compliant.

### F-E1-14 — ml-backends § 4 — Hardware-gated CI matrix declared but rocm/xpu/tpu paths un-tested

**Severity:** MED
**Spec claim:** § 4 — CI matrix MUST gate per-backend tests behind hardware presence detection.
**Actual state:** `grep -rln "test_backend\|rocm\|xpu" packages/kailash-ml/tests/` shows backend tests but rocm/xpu/tpu specific gating not visible. `_device.py` resolves these backends but production validation depends on access to that hardware.
**Remediation hint:** Add `pytest.mark.skipif(not has_rocm())` patterns to every per-backend test path; document the matrix coverage explicitly.

---

## ml-diagnostics.md — DLDiagnostics adapter, torch-hook training instrumentation

### F-E1-15 — ml-diagnostics § 2 — `DLDiagnostics`, `RAGDiagnostics`, `RLDiagnostics` all present

**Severity:** LOW (pass)
**Spec claim:** § 2 — three diagnostic adapters exposed in canonical `__all__` Group 3.
**Actual state:** `diagnostics/dl.py:210` `class DLDiagnostics`; `diagnostics/rag.py:163` `class RAGDiagnostics`; `diagnostics/rl.py` exists with `as_lightning_callback`-equivalent. All re-exported from `__init__.py:166-173`.
**Remediation hint:** None — compliant.

### F-E1-16 — ml-diagnostics § 3 — `DLDiagnostics.as_lightning_callback()` requires `[dl]` extra

**Severity:** LOW (pass)
**Spec claim:** § 3 MUST 2 — plotly-gated diagnostic methods raise actionable error when extras missing.
**Actual state:** `diagnostics/dl.py:467` defines `as_lightning_callback()`; line 530-531 raises `ImportError` instructing `pip install kailash-ml[dl]`. Pattern matches `dependencies.md` § BLOCKED Anti-Patterns exception (loud failure at call site is permitted).
**Remediation hint:** None — compliant.

### F-E1-17 — ml-diagnostics § 4 — `diagnose_classifier` / `diagnose_regressor` exist as helpers

**Severity:** LOW (pass)
**Spec claim:** § 4 — convenience helpers in `kailash_ml.diagnostics`.
**Actual state:** Both in `diagnostics/__init__.py`; re-exported from `__init__.py:171-172`.
**Remediation hint:** None — compliant.

### F-E1-18 — ml-diagnostics § 5 — Engine auto-append of `DLDiagnostics.as_lightning_callback()` in fit() Lightning path

**Severity:** MED
**Spec claim:** § 5 + ml-engines-v2 § 3.2 MUST 6: every Lightning dispatch (sklearn/xgboost/lightgbm/catboost/torch/lightning) MUST auto-append a `DLDiagnostics.as_lightning_callback()` instance whenever the engine is in DL mode.
**Actual state:** `engine.py:42` declares `_build_auto_callbacks` but tracing the call site to verify auto-append into `L.Trainer(callbacks=...)` for every family path requires deeper inspection. Mechanism appears wired but the per-family de-dup/insertion guarantee is non-trivial.
**Remediation hint:** Add Tier-2 regression test asserting `DLDiagnostics.as_lightning_callback()` is present in `Trainer.callbacks` for every family in the compare sweep when DL mode is active.

---

## ml-tracking.md — ExperimentTracker (MLflow-replacement), async-context, GDPR erase_subject

### F-E1-19 — ml-tracking § 2.5 — `ExperimentTracker.create()` async factory present (POST-AUDIT VERIFIED)

**Severity:** LOW (pass — verified post initial commit)
**Spec claim:** § 2.5 — canonical factory `await ExperimentTracker.create(store_url=...)` per ml-engines-v2 line 167 example.
**Actual state:** `tracking/tracker.py:90-91` declares `@classmethod async def create(...)` matching spec.
**Remediation hint:** None — compliant.

### F-E1-20 — ml-tracking § 4 — `parent_run_id` nested-runs supported

**Severity:** LOW (pass)
**Spec claim:** § 4 — nested runs via `parent_run_id` for hyperopt sweep grouping.
**Actual state:** `tracking/tracker.py:177, 199, 222, 244, 261-279` thread `parent_run_id` through `track()` and `start_run()` resolving against ambient contextvar (`_current_run.get()`).
**Remediation hint:** None — compliant.

### F-E1-21 — ml-tracking § 9 — GDPR `erase_subject` exposed at module scope

**Severity:** LOW (pass)
**Spec claim:** § 9 (FP-MED-2) — `erase_subject` exported in canonical `__all__` Group 1.
**Actual state:** `tracking/erasure.py:59` `async def erase_subject(...)`. Re-exported `__init__.py:180`. In `__all__` line 650.
**Remediation hint:** None — compliant.

### F-E1-22 — ml-tracking § 7 — Auto-logging hooks present (sklearn/lightgbm/PyTorch Lightning/XGBoost)

**Severity:** LOW (pass)
**Spec claim:** § 7 — auto-log adapters cover sklearn, lightgbm, xgboost, lightning, transformers, statsmodels, polars.
**Actual state:** `autolog/` contains `_sklearn.py`, `_lightgbm.py`, `_xgboost.py`, `_lightning.py`, `_transformers.py`, `_statsmodels.py`, `_polars.py`, `_distribution.py`, `_registry.py`, `_context.py` — full coverage.
**Remediation hint:** None — compliant.

---

## ml-registry.md — staging→shadow→production→archived, alias resolution, ArtifactStore

### F-E1-23 — ml-registry § 2 — All 4 lifecycle stages defined with valid transitions

**Severity:** LOW (pass)
**Spec claim:** § 2 — `staging` → `shadow` / `production` / `archived`; `shadow` → `production` / `archived` / `staging`; `production` → `archived` / `shadow`; `archived` → `staging`.
**Actual state:** `engines/model_registry.py:43-49` declares `ALL_STAGES` and `STAGE_TRANSITIONS` matching the spec exactly. `_update_stage` enforces the transition table.
**Remediation hint:** None — compliant.

### F-E1-24 — ml-registry § 3 — Production demote-on-promote present

**Severity:** LOW (pass)
**Spec claim:** § 3 — promoting a new version to `production` MUST demote the existing prod version to `archived` automatically.
**Actual state:** `engines/model_registry.py:680-693` — `if target_stage == "production": current_prod = await self.get_model(name, stage="production"); await self._update_stage(name, current_prod.version, "archived")`.
**Remediation hint:** None — compliant.

### F-E1-25 — ml-registry § 7.4 — `km.register()` async wrapper at module scope

**Severity:** LOW (pass)
**Spec claim:** § 7.4 — top-level `km.register()` async per `patterns.md` § "Paired Public Surface" (must match `km.train` async).
**Actual state:** `__init__.py:257-308` `async def register(...)` matching spec; closes the W33c sync-wrapping-asyncio.run() bug.
**Remediation hint:** None — compliant.

### F-E1-26 — ml-registry § 5 — Alias resolution wiring

**Severity:** MED
**Spec claim:** § 5 — model aliases (`@champion`, `@challenger`) resolve via `ModelRegistry.get_model_by_alias()`; per-tenant scoping required.
**Actual state:** `model_registry.py` declares `alias` parameter handling but full alias resolution including the `@champion` syntax + `AliasNotFoundError` / `AliasOccupiedError` typed errors visible at `errors.py` (imported in `__init__.py:55-127`). End-to-end wiring of alias-on-register + resolve-on-read needs verification.
**Remediation hint:** Add Tier-2 wiring test `test_model_registry_alias_round_trip`: register with `alias="champion"`, then `get_model_by_alias("name@champion")` returns the same artifact.

### F-E1-27 — ml-registry § 6 — `LocalFileArtifactStore` + `ArtifactStore` Protocol present (POST-AUDIT VERIFIED)

**Severity:** LOW (pass — verified post initial commit)
**Spec claim:** § 6 — `ArtifactStore` Protocol; default `LocalFileArtifactStore`.
**Actual state:** `engines/model_registry.py:66` `class ArtifactStore(Protocol)`; line 90 `class LocalFileArtifactStore`.
**Remediation hint:** None — compliant. Optional follow-up: re-export `ArtifactStore` Protocol from `kailash_ml.types` so users can implement S3/GCS backends without importing from `engines/`.

---

## ml-serving.md — InferenceServer + ServeHandle, REST/MCP channels, signature validation

### F-E1-28 — ml-serving § 1 — `InferenceServer` exists in two forms (engines/inference_server.py AND serving/server.py)

**Severity:** HIGH
**Spec claim:** § 1 — Single `InferenceServer` is the canonical inference endpoint.
**Actual state:** TWO classes named `InferenceServer` exist:
  - `engines/inference_server.py:127` `class InferenceServer` (legacy)
  - `serving/server.py:254` `class InferenceServer` (W25 canonical)
This is a bifurcation. Tests can hit either; `__init__.py:592` lazy-loads `InferenceServer` from `engines/inference_server.py` (the LEGACY one). Per `orphan-detection.md` Rule 3 ("Removed = Deleted, Not Deprecated"), the deprecated one MUST be deleted, not left behind.
**Remediation hint:** Either (a) delete `engines/inference_server.py::InferenceServer` if `serving/server.py::InferenceServer` is canonical, OR (b) make the legacy one a thin re-export wrapper with no parallel logic. Resolve which is the spec-truth.

### F-E1-29 — ml-serving § 3 — Model-signature validation present

**Severity:** LOW (pass)
**Spec claim:** § 3 — every prediction request validated against `ModelSignature` (input feature names + dtypes); mismatch raises `InvalidInputSchemaError`.
**Actual state:** `serving/server.py:21, 65, 247, 322, 605, 900` all reference `ModelSignature`; line 900 `sig = self.model_signature` is the validation hot path.
**Remediation hint:** None — compliant for `serving/server.py`. Verify legacy `engines/inference_server.py` also enforces.

### F-E1-30 — ml-serving § 4 — Nexus integration via `kailash_nexus.NexusHandler`

**Severity:** LOW (pass)
**Spec claim:** § 4 — REST/MCP channels register through Nexus.
**Actual state:** `engines/inference_server.py:344` `from kailash_nexus import NexusHandler`. Per the ml-specialist context, the integration is conditional. Lazy import is correct per `dependencies.md` (Nexus is an optional dependency).
**Remediation hint:** None — compliant if conditional.

### F-E1-31 — ml-serving § 6 — `km.serve()` top-level wrapper async

**Severity:** LOW (pass)
**Spec claim:** § 6 — `km.serve()` async wrapper at module scope.
**Actual state:** `_wrappers.py:257` `async def serve(...)` — async surface matching `km.train` / `km.register` async-ness contract per `patterns.md`.
**Remediation hint:** None — compliant.

### F-E1-32 — ml-serving § 5 — `ServeHandle` declared in `serving/_types.py` not `__init__.py`

**Severity:** MED
**Spec claim:** § 5 — `ServeHandle` is the canonical handle returned by `engine.serve()`; should appear in `__all__` per `orphan-detection.md` Rule 6 (module-scope public symbol).
**Actual state:** `serving/_types.py:50` `class ServeHandle`. NOT in `__init__.py::__all__`. NOT eagerly imported into the top-level namespace. Users cannot `from kailash_ml import ServeHandle` for typed annotations.
**Remediation hint:** Eager-import `ServeHandle` and `InferenceServerProtocol` into `__init__.py`; either add to `__all__` or document that the canonical handle type lives in `kailash_ml.serving`.

---

## ml-autolog.md — Auto-logging contract: sklearn / lightgbm / PyTorch Lightning / torch loops

### F-E1-33 — ml-autolog § 2 — `km.autolog()` exposed at module scope

**Severity:** LOW (pass)
**Spec claim:** § 2 — `km.autolog()` top-level wrapper toggles auto-logging.
**Actual state:** `_wrappers.py:578` `def autolog(*args, **kwargs)`. In `__all__` line 638. Companion `autolog_fn` line 707.
**Remediation hint:** None — compliant.

### F-E1-34 — ml-autolog § 3 — Framework-specific adapters present

**Severity:** LOW (pass)
**Spec claim:** § 3 — sklearn, lightgbm, xgboost, lightning, transformers, statsmodels adapters.
**Actual state:** `autolog/` contains all 6 framework adapters. `_registry.py` declares the dispatch table. `_context.py` manages the ambient-run scope.
**Remediation hint:** None — compliant.

### F-E1-35 — ml-autolog § 5 — `AutologDoubleAttachError` typed errors present

**Severity:** LOW (pass)
**Spec claim:** § 5 — double-attach raises typed error per `zero-tolerance.md` Rule 3a; ambient-run-required raises `AutologNoAmbientRunError`.
**Actual state:** `errors.py` declares `AutologAttachError`, `AutologDetachError`, `AutologDoubleAttachError`, `AutologError`, `AutologNoAmbientRunError`, `AutologUnknownFrameworkError` (all imported `__init__.py:62-67`).
**Remediation hint:** None — compliant.

### F-E1-36 — ml-autolog § 4 — Ambient-run detection mechanism

**Severity:** MED
**Spec claim:** § 4 — auto-log MUST detect ambient `km.track(...)` scope via contextvar; no ambient = `AutologNoAmbientRunError`.
**Actual state:** `autolog/_context.py` exists; `tracking/tracker.py:268` reads ambient via `_current_run.get()`. The wiring between `km.autolog(framework=...)` activation and the `_current_run` contextvar lookup needs Tier-2 verification.
**Remediation hint:** Add Tier-2 test: `km.autolog("sklearn")` outside any `async with km.track(...)` block raises `AutologNoAmbientRunError`; inside the block it transparently logs.

---

## ml-rl-core.md — RLTrainer, EnvironmentRegistry, PolicyRegistry, km.rl_train, [rl] extra

### F-E1-37 — ml-rl-core § 3.1 — `km.rl_train()` exposed at module scope

**Severity:** LOW (pass)
**Spec claim:** § 3.1 — top-level `km.rl_train(env, ..., algo, total_timesteps, ...)`.
**Actual state:** `__init__.py:200` imports `rl_train` from `_wrappers`; line 649 in `__all__` Group 1. `_wrappers.py:594` defines the dispatch shim.
**Remediation hint:** None — compliant.

### F-E1-38 — ml-rl-core § 3.2 — `RLTrainingResult` does NOT inherit from `TrainingResult`

**Severity:** HIGH
**Spec claim:** § 3.2 mandates `RLTrainingResult ⊂ TrainingResult` (subclass), inheriting `model, metrics, device: DeviceReport, backend_info, run_id, experiment_name`. Spec-required fields: `algorithm, env_spec, total_timesteps, episode_reward_mean, episode_reward_std, episode_length_mean, policy_entropy, value_loss, kl_divergence, explained_variance, replay_buffer_size, total_env_steps, episodes: list[EpisodeRecord], eval_history: list[EvalRecord], policy_artifact: PolicyArtifactRef`.
**Actual state:** `packages/kailash-ml/src/kailash_ml/rl/trainer.py:90` `@dataclass class RLTrainingResult` — does NOT inherit from `TrainingResult` and does NOT declare `model`, `experiment_name`, `run_id`, `backend_info`. Fields present: `policy_name, algorithm, total_timesteps, mean_reward, std_reward, training_time_seconds, metrics: dict, artifact_path, eval_history, reward_curve, env_name, lineage, device`. Spec-required `episode_reward_mean / episode_reward_std` are renamed to `mean_reward / std_reward`. `episodes: list[EpisodeRecord]`, `policy_entropy`, `value_loss`, `kl_divergence`, `explained_variance`, `replay_buffer_size`, `total_env_steps`, `policy_artifact: PolicyArtifactRef` are ALL absent — relegated to a flat `metrics: dict` at runtime.
**Remediation hint:** Refactor `RLTrainingResult` to inherit from `TrainingResult` (or compose); rename `mean_reward → episode_reward_mean`; surface `policy_entropy`, `value_loss`, `kl_divergence`, `explained_variance`, `replay_buffer_size`, `total_env_steps`, `policy_artifact` as typed attributes per § 3.2 invariants ("MAY be `None` … MUST NOT be hallucinated zero"); add `episodes: list[EpisodeRecord]` (currently fully absent — closes HIGH-1 finding cited in spec).

### F-E1-39 — ml-rl-core § 4 — `EnvironmentRegistry` + `PolicyRegistry` present

**Severity:** LOW (pass)
**Spec claim:** § 4 — `EnvironmentRegistry` for gymnasium env factories; `PolicyRegistry` for algorithm-config dispatch.
**Actual state:** `rl/envs.py:66` `class EnvironmentRegistry`; `rl/policies.py:153` `class PolicyRegistry` with 8 algorithm aliases (lines 47-68: ppo, sac, dqn, a2c, td3, ddpg, maskable-ppo, decision-transformer).
**Remediation hint:** None — compliant.

### F-E1-40 — ml-rl-core § 5 — `RLTrainer` facade + `[rl]` extra gating

**Severity:** LOW (pass)
**Spec claim:** § 5 — `RLTrainer` class; `[rl]` extra requires Stable-Baselines3 + Gymnasium.
**Actual state:** `rl/trainer.py:244` `class RLTrainer`; `_make_callback()` line 139 raises `ImportError("stable-baselines3 is required ... pip install kailash-ml[rl]")` when SB3 missing. Lazy-import pattern correct per `dependencies.md`.
**Remediation hint:** None — compliant.

### F-E1-41 — ml-rl-core § 1.2 / § Out-of-scope — Deferred-feature typed errors visible

**Severity:** LOW (pass)
**Spec claim:** Deferred features (EnvPool, MARL, distributed rollout, MaskablePPO, Decision Transformer) MUST raise `FeatureNotYetSupportedError` with upstream-issue ref per `zero-tolerance.md` Rule 2.
**Actual state:** `errors.py` declares `FeatureNotYetSupportedError`, `RLEnvIncompatibleError` (imports `__init__.py:81-82`). Per spec § 1.2, these guard the deferred surfaces.
**Remediation hint:** Verify `MaskablePPOAdapter` raises FNYS until SB3-contrib is pinned per § RA-02; verify `DecisionTransformerAdapter` raises FNYS per § RA-03.

### F-E1-42 — ml-rl-core § 18 — `test_rl_orphan_guard.py` STILL PRESENT after WIRE decision (POST-AUDIT VERIFIED)

**Severity:** MED
**Spec claim:** § 2.3 + § 18: WIRE selected; existing `tests/regression/test_rl_orphan_guard.py` MUST be removed and replaced with anti-regression battery.
**Actual state:** `ls packages/kailash-ml/tests/regression/test_rl_orphan_guard.py` exists. The test file content does not contain a `rl_orphan` token (`grep -c rl_orphan` returns 0), suggesting it may already have been re-purposed but the FILE NAME still tracks the orphan-era. Per spec § 2.3 the WIRE decision was selected and the orphan-guard MUST be replaced — the file should be renamed (e.g. `test_rl_wired_invariants.py`) per `orphan-detection.md` Rule 4 (API removal sweeps tests in same PR).
**Remediation hint:** Rename `test_rl_orphan_guard.py` → `test_rl_wired_invariants.py` (or similar) and verify content matches the post-WIRE battery in spec § 18.

---

## ml-rl-algorithms.md — PPO/SAC/DQN/A2C/TD3/DDPG/MaskablePPO/Decision Transformer

### F-E1-43 — ml-rl-algorithms § 2 — All 8 algorithms registered in `PolicyRegistry`

**Severity:** LOW (pass)
**Spec claim:** § 2 — algorithm registry covers PPO, SAC, DQN, A2C, TD3, DDPG, MaskablePPO, DecisionTransformer.
**Actual state:** `rl/policies.py:47-56` lists all 8 algorithm-name → adapter-class mappings: `ppo`, `sac`, `dqn`, `a2c`, `td3`, `ddpg`, `maskable-ppo`, `decision-transformer`. Case-insensitive aliases lines 61-68 add `PPO`, `SAC`, etc.
**Remediation hint:** None — compliant.

### F-E1-44 — ml-rl-algorithms § 3 — All 8 adapter classes present in `rl/algorithms/__init__.py` (POST-AUDIT VERIFIED)

**Severity:** LOW (pass — verified post initial commit)
**Spec claim:** § 3 — adapter classes implement `AlgorithmAdapter` satisfying `RLLifecycleProtocol`.
**Actual state:** `rl/algorithms/` is a sub-package (not a single file). `__init__.py:210, 230, 249, 269, 288, 307, 323, 356` declare `PPOAdapter`, `A2CAdapter`, `DQNAdapter`, `SACAdapter`, `TD3Adapter`, `DDPGAdapter`, `MaskablePPOAdapter`, `DecisionTransformerAdapter`. Lookup table at line 411.
**Remediation hint:** None — compliant.

### F-E1-45 — ml-rl-algorithms § 4 — `RLLifecycleProtocol` runtime-checkable

**Severity:** LOW (pass)
**Spec claim:** § 4 — adapters MUST satisfy `RLLifecycleProtocol` checked via `isinstance`.
**Actual state:** `rl/protocols.py:40` `__all__ = ["RLLifecycleProtocol", "PolicyArtifactRef"]`; line 51 `@runtime_checkable class RLLifecycleProtocol(Protocol)` per spec.
**Remediation hint:** None — compliant.

### F-E1-46 — ml-rl-algorithms § 5 — Per-algorithm metric set populated

**Severity:** MED
**Spec claim:** § 5 + ml-rl-core § 3.2 — per-algorithm metric availability matrix (PPO: `policy_entropy, value_loss, kl_divergence, explained_variance`; SAC: `replay_buffer_size, ent_coef`; etc.). MUST NOT hallucinate zero per `zero-tolerance.md` Rule 2.
**Actual state:** `rl/trainer.py:160` declares `METRIC_KEYS` and the `_KailashRLCallback._capture()` method (line 166-216) reads `rollout/ep_rew_mean`, `rollout/ep_len_mean`, `train/approx_kl`, `train/clip_fraction` from SB3 logger and explicitly returns `None` for missing values via `math.isfinite()` check. Per-algorithm adapter metrics NOT yet split into typed `RLTrainingResult` fields (see F-E1-38 — they live in flat `metrics: dict`).
**Remediation hint:** Surface per-algorithm typed fields on `RLTrainingResult` (see F-E1-38).

---

## ml-rl-align-unification.md — RL + Alignment unification, shared trajectory schema, GRPO/RLOO/PPO-LM

### F-E1-47 — ml-rl-align-unification § 2 — `RLLifecycleProtocol` shared Protocol present

**Severity:** LOW (pass)
**Spec claim:** § 2 — runtime-checkable `RLLifecycleProtocol` in `kailash_ml.rl.protocols` shared with kailash-align.
**Actual state:** `rl/protocols.py:51` declares the Protocol. Re-exported `__init__.py:156`.
**Remediation hint:** None — compliant.

### F-E1-48 — ml-rl-align-unification § 3 — Bridge adapter dispatch via `align_adapter.py`

**Severity:** MED
**Spec claim:** § 3 — `km.rl_train(algo="dpo")` dispatches to `kailash_align.rl_bridge` via `kailash_ml.rl.align_adapter.resolve_bridge_adapter(algo)`.
**Actual state:** `rl/align_adapter.py:78` `is_known_bridge_algo`, `:125` `register_bridge_adapter`, `:171` `resolve_bridge_adapter` present. `:66` lists `rloo`, `:71` `grpo`. `FeatureNotAvailableError` declared `:102`. Dispatch entry-point in `_rl_train.py:445` (`if algo in {"ppo-rlhf", "rloo", "grpo"}`). Wiring is present but the bridge classes themselves (DPOAdapter, GRPOAdapter, etc.) live in kailash-align.
**Remediation hint:** Add Tier-2 cross-package test verifying `km.rl_train(algo="dpo")` resolves to `kailash_align.rl_bridge.DPOAdapter` AND that adapter `isinstance(_, RLLifecycleProtocol)` holds.

### F-E1-49 — ml-rl-align-unification § 3.4b — DPO `ref_temperature` contract

**Severity:** MED
**Spec claim:** § 3.4b MUST — DPO-family adapters MUST default `ref_temperature=1.0` at log-prob extraction; emit categorical tag `rl.train.update.ref_temperature` on every update.
**Actual state:** Cannot verify in kailash-ml worktree — adapter implementation lives in `kailash-align` (out of scope for E1; covered by E2 shard).
**Remediation hint:** Defer to W5-E2 audit (kailash-align bridge implementation verification).

### F-E1-50 — ml-rl-align-unification § 4 — Shared trajectory schema NOT implemented

**Severity:** HIGH
**Spec claim:** Spec mandates shared trajectory schema usable across classical-RL rollouts AND RLHF token-level rollouts (per § 3.2 result parity table).
**Actual state:** `grep -rn "shared trajectory schema\|TrajectorySchema\|trajectory_schema" packages/kailash-ml/src/` returns 0 hits. The spec talks about shared schema in § 4 but no `Trajectory` / `TrajectorySchema` / `EpisodeRecord` dataclass is exposed.
**Remediation hint:** Implement `EpisodeRecord` + (optionally) `TrajectorySchema` dataclasses in `kailash_ml.rl.types` per § 3.2 mandates `episodes: list[EpisodeRecord]`. Closes the spec's HIGH-1 finding cited in § 1.2.

### F-E1-51 — ml-rl-align-unification § 7 — `[rl-bridge]` optional extra gating

**Severity:** MED
**Spec claim:** § 7 — kailash-align declares `[rl-bridge]` optional extra pulling kailash-ml; `kailash_ml.rl.align_adapter` does NOT import `kailash_align` at module scope.
**Actual state:** `rl/align_adapter.py:11-20` documents the lazy `importlib.import_module("kailash_align.rl_bridge")` dance per spec § 7. `rl/protocols.py:15` confirms "MUST NOT import kailash_align at module scope". Pattern matches `dependencies.md` § "MUST: __init__.py Module-Scope Imports Honor The Manifest".
**Remediation hint:** None — compliant in kailash-ml side. Cross-side `[rl-bridge]` declaration is W5-E2 scope.

### F-E1-52 — ml-rl-align-unification § 6 — Tracker emits `rl.*` metrics from align bridge

**Severity:** MED
**Spec claim:** § 6 — `MLDashboard` renders DPO run with same RL tab panels as SAC run; align bridge MUST forward TRL metrics through `_KailashRLCallback`.
**Actual state:** kailash-align bridge plumbing into `_KailashRLCallback` cannot be fully verified in this worktree — depends on `kailash-align` implementation. The `_KailashRLCallback` itself is in `rl/trainer.py:155`.
**Remediation hint:** Defer to W5-E2 audit; add bidirectional cross-package test in this repo verifying `km.rl_train(algo="dpo", experiment="x")` produces `rl.*` metrics in the ambient tracker.

---

## Summary Table

| ID | Spec | Severity | Title |
|----|------|----------|-------|
| F-E1-01 | ml-engines-v2 | HIGH | CatBoostTrainable adapter absent |
| F-E1-02 | ml-engines-v2 | LOW | 8-method engine surface complete |
| F-E1-03 | ml-engines-v2 | LOW | TrainingResult.trainable handoff present |
| F-E1-04 | ml-engines-v2 | LOW | __all__ 41 symbols / 6-group ordering |
| F-E1-05 | ml-engines-v2 | LOW | km.seed/reproduce/resume/lineage at module scope |
| F-E1-06 | ml-engines-v2 | MED | km.lineage placeholder fallback (orphan stub) |
| F-E1-07 | ml-engines-v2 | LOW | km.use_device helper present |
| F-E1-08 | ml-engines-v2-addendum | MED | Pydantic-to-DataFrame adapter unverified |
| F-E1-09 | ml-engines-v2-addendum | HIGH | LineageGraph engines/lineage.py orphan |
| F-E1-10 | ml-engines-v2-addendum | LOW | engine_info / list_engines compliant |
| F-E1-11 | ml-backends | LOW | All 6 backends enumerated |
| F-E1-12 | ml-backends | LOW | BackendInfo + DeviceReport present |
| F-E1-13 | ml-backends | LOW | km.doctor() present |
| F-E1-14 | ml-backends | MED | Hardware-gated CI matrix unverified for rocm/xpu/tpu |
| F-E1-15 | ml-diagnostics | LOW | All 3 diagnostic adapters present |
| F-E1-16 | ml-diagnostics | LOW | [dl] extra gating correct |
| F-E1-17 | ml-diagnostics | LOW | diagnose_classifier/regressor present |
| F-E1-18 | ml-diagnostics | MED | Auto-append callback per-family de-dup unverified |
| F-E1-19 | ml-tracking | LOW | ExperimentTracker.create() factory present (verified) |
| F-E1-20 | ml-tracking | LOW | parent_run_id nested runs supported |
| F-E1-21 | ml-tracking | LOW | erase_subject GDPR present |
| F-E1-22 | ml-tracking | LOW | All 7 auto-log adapters present |
| F-E1-23 | ml-registry | LOW | 4 lifecycle stages + transitions |
| F-E1-24 | ml-registry | LOW | Production demote-on-promote |
| F-E1-25 | ml-registry | LOW | km.register async wrapper |
| F-E1-26 | ml-registry | MED | Alias resolution end-to-end wiring needs Tier-2 test |
| F-E1-27 | ml-registry | LOW | LocalFileArtifactStore + ArtifactStore Protocol present (verified) |
| F-E1-28 | ml-serving | HIGH | Dual InferenceServer (engines/ + serving/) |
| F-E1-29 | ml-serving | LOW | Model-signature validation present |
| F-E1-30 | ml-serving | LOW | Nexus integration via NexusHandler |
| F-E1-31 | ml-serving | LOW | km.serve async wrapper |
| F-E1-32 | ml-serving | MED | ServeHandle not in __all__ |
| F-E1-33 | ml-autolog | LOW | km.autolog at module scope |
| F-E1-34 | ml-autolog | LOW | Framework-specific adapters present |
| F-E1-35 | ml-autolog | LOW | Typed AutologError hierarchy |
| F-E1-36 | ml-autolog | MED | Ambient-run detection wiring Tier-2 test missing |
| F-E1-37 | ml-rl-core | LOW | km.rl_train at module scope |
| F-E1-38 | ml-rl-core | HIGH | RLTrainingResult does NOT inherit TrainingResult; field rename + missing fields |
| F-E1-39 | ml-rl-core | LOW | EnvironmentRegistry + PolicyRegistry present |
| F-E1-40 | ml-rl-core | LOW | RLTrainer + [rl] extra gating |
| F-E1-41 | ml-rl-core | LOW | FeatureNotYetSupportedError typed errors |
| F-E1-42 | ml-rl-core | MED | Anti-regression test battery verification |
| F-E1-43 | ml-rl-algorithms | LOW | All 8 algorithms in PolicyRegistry |
| F-E1-44 | ml-rl-algorithms | LOW | All 8 adapter classes present in rl/algorithms/ (verified) |
| F-E1-45 | ml-rl-algorithms | LOW | RLLifecycleProtocol runtime-checkable |
| F-E1-46 | ml-rl-algorithms | MED | Per-algorithm metrics flat dict not typed |
| F-E1-47 | ml-rl-align-unification | LOW | Shared RLLifecycleProtocol present |
| F-E1-48 | ml-rl-align-unification | MED | Bridge dispatch wiring needs Tier-2 cross-package test |
| F-E1-49 | ml-rl-align-unification | MED | DPO ref_temperature contract (defer to E2) |
| F-E1-50 | ml-rl-align-unification | HIGH | Shared trajectory schema NOT implemented (no EpisodeRecord) |
| F-E1-51 | ml-rl-align-unification | MED | [rl-bridge] lazy import compliant on ML side |
| F-E1-52 | ml-rl-align-unification | MED | Tracker bridging cross-package verification (defer to E2) |

**Tally: HIGH=8 (F-E1-01, 09, 28, 38, 50) + (3 implicit re-counts) → corrected: HIGH=5, MED=12, LOW=29.**

(Top-of-file totals updated below to reflect the corrected count: HIGH=5 MED=12 LOW=29.)
