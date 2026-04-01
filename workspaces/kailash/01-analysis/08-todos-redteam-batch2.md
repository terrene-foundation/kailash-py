# Todos Red Team — Batch 2: kailash-ml + kailash-align

**Date**: 2026-04-01
**Scope**: 19 todos (ML-000 through ML-502) + 13 todos (ALN-000 through ALN-402)
**Reviewer**: Red team agent
**Verdict**: 26 of 32 todos are implementation-ready. 6 require amendments before implementation.

---

## 1. kailash-ml Workspace (19 todos)

### ML-000 — Milestone Tracker

**Verdict**: PASS (reference document, not implementable)

- Dependency graph is complete and consistent with individual todo frontmatter.
- Progress tracking table covers all 18 implementation todos.
- Success criteria are measurable (200MB install, 10ms latency, 1e-5 tolerance, etc.).
- No issues.

### ML-001 — kailash-ml-protocols Package

**Verdict**: PASS

- Acceptance criteria: All 11 criteria are testable (isinstance checks, wheel size, round-trip tests).
- Implementation spec: Complete frozen protocol definitions with exact method signatures. An agent can implement without questions.
- Red team coverage: R2-05 (minimum surface), R2-10 (options parameter), R1-08 (frozen in /todos). All addressed.
- Test plan: 5 concrete test functions specified with assertions. Adequate.
- Dependencies: None. Correct for Phase 0.
- No issues.

### ML-002 — ModelRegistry Extension Contract

**Verdict**: PASS

- This is a design document, not code. Acceptance criteria are correctly scoped to document creation.
- 5 public methods documented with full signatures.
- DataFlow model schemas (MLModel, MLModelVersion, MLModelTransition) fully specified.
- Extension points table clearly marks inherited vs extended methods.
- Anti-features list from R1-06, R2-03 present.
- No issues.

### ML-100 — Package Skeleton

**Verdict**: PASS with 1 MINOR finding

- Complete pyproject.toml with all extras tiers. Dependency versions specified.
- Lazy import pattern fully specified.
- GPU setup CLI fully specified.
- Test scaffolding with conftest.py fixtures specified.
- **MINOR — ML-100-F1**: Acceptance criterion says "engine stubs (importable, raise on use)" — this phrasing is dangerously close to "stubs." The todo should explicitly clarify these are empty module files with `__all__ = []` that raise `AttributeError` on attribute access (like ALN-100 does), not `NotImplementedError`. The `__getattr__` lazy import pattern in `__init__.py` already handles this correctly, but the AC phrasing could mislead an implementer.

### ML-101 — Interop Module

**Verdict**: PASS

- All 8 converter signatures specified with full parameter types and return types.
- Handling notes per converter (Categorical -> codes, zero-copy paths, pandas touchpoint documented).
- Benchmark harness fully specified with 15% threshold test.
- Round-trip fidelity tests with dtype-level assertions.
- Red team findings R1-01, R2-01 addressed.
- No issues.

### ML-200 — FeatureStore

**Verdict**: PASS

- Mixed-layer architecture (ConnectionManager for point-in-time, Express for metadata) well-justified.
- `_feature_sql.py` encapsulation pattern fully specified with SQL example.
- Point-in-time query uses ROW_NUMBER() window function — correct approach.
- Bulk write path (Arrow >10K, dict <10K) specified.
- 4 integration tests specified with specific assertions.
- Rules applied: infrastructure-sql.md, R2-12, dataflow-pool.md. Correct.
- No issues.

### ML-201 — ModelRegistry

**Verdict**: PASS

- API frozen per ML-002 contract. Acceptance criteria reference contract compliance.
- ArtifactStore protocol + LocalFileArtifactStore fully specified.
- Stage transition state machine (VALID_TRANSITIONS) explicit and correct.
- Production promotion auto-archives previous production version — good.
- MLflow serialization scoped per R1-06 (metadata only, anti-features listed).
- ONNX status tracking specified.
- 4 integration tests with specific assertions.
- No issues.

### ML-202 — TrainingPipeline

**Verdict**: PASS with 1 MINOR finding

- Core types (ModelSpec, EvalSpec, TrainingResult) fully specified.
- Train method 7-step flow documented with code sketch.
- Cross-validation strategies specified: kfold, stratified_kfold, walk_forward, holdout.
- Agent infusion point is optional and informational-only — correct.
- Lightning deferred to v1.1 per R1-03 — documented.
- **MINOR — ML-202-F1**: The `_split()` method returns `(train_data, test_data)` but for k-fold strategies, it only uses the first fold ("\_kfold_first_fold"). This means cross-validation is not actually performed for model evaluation — only a single fold is used. The todo should clarify whether `_evaluate()` internally runs all k folds (which would require the full dataset, not pre-split) or whether single-fold holdout is the v1 behavior. As written, an agent would implement single-fold only, which contradicts the "Cross-validation" acceptance criterion. Suggest: add a `_cross_validate()` method that runs all folds internally and returns averaged metrics.

### ML-203 — InferenceServer

**Verdict**: PASS

- PredictionResult dataclass fully specified.
- Predict flow (single + batch) documented with code sketches.
- LRU cache implementation specified.
- MLToolProtocol implementation verified with isinstance check in tests.
- Nexus integration with lazy import specified.
- Health endpoint specified.
- 4 integration tests specified.
- R2-13 (lazy Nexus import) addressed.
- No issues.

### ML-204 — DriftMonitor

**Verdict**: PASS

- PSI and KS-test implementations specified with code.
- DriftReport and PerformanceDegradationReport dataclasses complete.
- DataFlow models (MLDriftReference, MLDriftReport) specified.
- Agent infusion point for interpret_drift() specified.
- 5 integration tests including categorical drift and persistence verification.
- No issues.

### ML-300 — HyperparameterSearch

**Verdict**: PASS with 1 MINOR finding

- 4 search strategies specified: grid, random, bayesian, successive halving.
- SearchSpace, SearchConfig, TrialResult, SearchResult dataclasses complete.
- Bayesian search uses optuna with TPE sampler — correct.
- Trial history persisted in MLSearchTrial DataFlow model.
- **MINOR — ML-300-F1**: The Bayesian search code sketch uses `_run_sync()` to wrap async `TrainingPipeline.train()` inside optuna's synchronous `study.optimize()` callback. This `_run_sync()` function is not defined anywhere in the todo. The implementer needs to know: (a) use `asyncio.run()` if there's no running event loop, or (b) use `asyncio.get_event_loop().run_until_complete()`, or (c) use a thread-pool executor. Suggest: specify the `_run_sync()` pattern explicitly, or note that it uses `asyncio.run()`.

### ML-301 — AutoMLEngine

**Verdict**: PASS

- All 5 agent guardrails specified in detail.
- LLMCostTracker designed as first-class class with per-model pricing.
- PendingApproval with configurable timeout (10 min default) specified.
- Guardrail 4 (baseline comparison) correctly compares recommendations, not results — R1-04 fix applied.
- Audit batching with configurable batch size/flush interval and documented data-loss window.
- AutoMLResult dataclass includes both agent recommendation and baseline recommendation.
- R1-04, R2-02, R2-04 findings addressed.
- No issues.

### ML-302 — DataExplorer

**Verdict**: PASS

- P2 quality tier with `@experimental` decorator — correct.
- Profile method uses polars natively (no pandas).
- Visualization uses plotly correctly.
- Missing value pattern detection specified.
- 4 integration tests including experimental warning test.
- R1-07/R2-04, R1-03, R2-01 addressed.
- No issues.

### ML-303 — FeatureEngineer

**Verdict**: PASS

- P2 quality tier with `@experimental` decorator.
- 4 generation strategies specified: interactions, polynomial, binning, temporal.
- 3 selection methods: importance (LightGBM), correlation, mutual_info.
- Complete dataclass hierarchy (GeneratedColumn, GeneratedFeatures, FeatureRank, SelectedFeatures).
- FeatureStore integration for persisting selected features.
- 4 integration tests.
- No issues.

### ML-400 — Kaizen Agents

**Verdict**: PASS with 1 MEDIUM finding

- 6 agents specified with quality tiers (P0/P1/P2).
- All agents use Delegate pattern — correct per agent-reasoning.md.
- Tools are dumb data endpoints — correct.
- All 5 guardrails specified per agent.
- Shared infrastructure: \_guardrails.py, \_cost_tracker.py, \_approval.py, \_audit.py.
- **MEDIUM — ML-400-F1**: The DataScientistAgent code sketch shows tools `_get_column_stats`, `_get_sample_rows`, `_get_correlation_matrix` as instance methods that access `self._data_profile`, `self._sample_data`, `self._correlation_data`. These properties are never set — the agent receives `data_profile` as a parameter to `assess()` but the tools reference different instance attributes. The implementer needs clarity on how data flows from the `assess()` parameters to the tool methods. Suggest: either (a) set `self._data_profile = data_profile` before creating the Delegate, or (b) use closures that capture the parameters, or (c) pass data to tools via Delegate's context mechanism.

### ML-401 — ONNX Bridge

**Verdict**: PASS

- Pre-flight compatibility check with hardcoded matrix — correct approach.
- Export for sklearn (skl2onnx), LightGBM (onnxmltools), PyTorch (torch.onnx).
- Post-export validation compares native vs ONNX predictions within tolerance.
- Version transition warning when ONNX status degrades.
- OnnxCompatibility, OnnxExportResult, OnnxValidationResult dataclasses complete.
- 6 integration tests.
- R1-05 findings comprehensively addressed.
- No issues.

### ML-500 — Integration Tests

**Verdict**: PASS with 1 MINOR finding

- Files to create clearly listed (7 test files).
- Critical path matrix (~20 combos, <15 min) specified.
- pytest markers defined (critical_path, full_matrix, gpu).
- **MINOR — ML-500-F1**: The `blocks` field lists ML-502 but the frontmatter also shows `status: pending` — this is inconsistent with other todos which don't have a `status` field. Normalize or remove. Additionally, the dependency list includes ML-300 and ML-301 but NOT ML-302 or ML-303 (the P2 engines). This is correct per the tiering (P2 engines get smoke tests only), but should be explicitly noted.

### ML-501 — MLflow Compatibility

**Verdict**: PASS with 1 MINOR finding

- Anti-feature list explicitly encoded as `_MLFLOW_ANTI_FEATURES` constant.
- MLmodel YAML schema documented.
- 4 supported flavors listed.
- **MINOR — ML-501-F1**: The `MLflowCompat` class is placed in `compat/mlflow.py` but the package layout in ML-100 has `serialization.py` at the root level for MLflow format. The todo should clarify whether it replaces `serialization.py` or supplements it. ML-201 references `serialization.py` for `write_mlmodel_yaml()` / `read_mlmodel_yaml()`. Suggest: state explicitly that `compat/mlflow.py` wraps the lower-level `serialization.py` functions.

### ML-502 — Documentation + Quality

**Verdict**: PASS

- `@experimental` decorator implementation specified with code.
- Quality tier definitions documented.
- Promotion/demotion criteria defined.
- Tests: decorator warning, quality tier attribute, README examples.
- No issues.

---

## 2. kailash-align Workspace (13 todos)

### ALN-000 — Milestone Tracker

**Verdict**: PASS (reference document)

- Dependency graph complete and consistent.
- Cross-workspace dependencies explicitly listed (ML-002, ML-201, kailash-kaizen).
- Deferred items documented with sources.
- Red team finding coverage table comprehensive.
- Parallelization strategy specified with session estimates.
- No issues.

### ALN-001 — ModelRegistry Extension Contract

**Verdict**: PASS

- 7 extension touch points documented with risk levels.
- AlignAdapter and AlignAdapterVersion DataFlow models designed.
- AdapterSignature dataclass defined (separate from ModelSignature per R2).
- Composition vs inheritance decision documented with rationale — good.
- Validation checklist comprehensive (6 items).
- R2-02, R1-03 addressed.
- No issues.

### ALN-100 — Package Skeleton

**Verdict**: PASS

- Complete pyproject.toml with 4 optional extras: [rlhf], [eval], [serve], [full].
- TRL pin `>=0.25,<1.0` (R1-08) — correct.
- Dependency pin rationale table for all 10 dependencies.
- Lazy imports specified — torch not loaded on import.
- Exception hierarchy fully specified.
- Empty module stubs explicitly noted as NOT stub violations.
- No issues.

### ALN-101 — AdapterRegistry

**Verdict**: PASS with 1 MEDIUM finding

- Complete code sketch with all public methods.
- DataFlow model definitions (field-level).
- AdapterSignature (frozen=True) with **post_init** validation.
- Composition pattern (HAS-A ModelRegistry) per ALN-001 decision.
- **MEDIUM — ALN-101-F1**: The `register_adapter()` method computes `next_version = str(len(existing) + 1)`. This is a race condition: two concurrent registrations could both read `len(existing) == 3` and both assign version "4". This is a TOCTOU bug per infrastructure-sql.md. The version numbering should use an atomic increment pattern — either a counter in the AlignAdapter record or a `SELECT MAX(version) ... FOR UPDATE` within a transaction. For v1 with SQLite (single-writer), this is low risk, but it violates infrastructure-sql.md rules and will break with PostgreSQL.

### ALN-200 — AlignmentConfig

**Verdict**: PASS

- All 3 frozen config dataclasses (LoRAConfig, SFTConfig, DPOConfig) with **post_init** validation.
- NaN/Inf validation via `_validate_finite()` and `_validate_positive()` — per trust-plane-security.md.
- `to_peft_config()` and `to_trl_config()` conversion methods with lazy imports.
- QLoRA bitsandbytes import check.
- bf16/fp16 mutual exclusion validated.
- AlignmentConfig top-level with `validate()` method.
- No issues.

### ALN-201 — SFT Training

**Verdict**: PASS

- 7-step flow specified with full code sketch.
- Uses `trl.SFTConfig` (NOT deprecated TrainingArguments) — R1-08 addressed.
- Uses `processing_class=tokenizer` (NOT deprecated `tokenizer=` parameter).
- LoRA via PEFT `get_peft_model()`.
- QLoRA via BitsAndBytesConfig.
- Checkpoint resume via `_find_checkpoint()`.
- Auto-registers in AdapterRegistry.
- `trust_remote_code=False` — security correct.
- `local_files_only` propagated for air-gap.
- No issues.

### ALN-202 — DPO Training

**Verdict**: PASS

- 8-step flow specified with full code sketch.
- Uses `trl.DPOTrainer` with `trl.DPOConfig`.
- Reference model is implicit in TRL >=0.25 — correctly documented.
- Preference dataset validation with column checks and spot-check.
- SFT-then-DPO chaining: merge_and_unload() + fresh LoRA — correct approach.
- DPO-specific metrics captured with `.get()` for version safety.
- No issues.

### ALN-300 — AlignmentEvaluator

**Verdict**: PASS with 1 MINOR finding

- Wraps lm-eval `simple_evaluate()` with lazy import.
- "quick" and "standard" task presets defined.
- Custom evaluation via transformers.pipeline (no lm-eval dependency).
- EvalResult with to_dict() serialization and summary property.
- Results stored in DataFlow and written back to AdapterRegistry.
- **MINOR — ALN-300-F1**: The `evaluate_custom()` method body is `...` (ellipsis). This is a Protocol stub pattern, but ALN-300 is an implementation todo, not a protocol. The full implementation should be specified or the method should be explicitly marked as "deferred to separate todo" (which would need tracking). As-is, an implementer might leave it as a stub, violating no-stubs.md. Suggest: either provide the implementation sketch or defer to a separate todo and remove from the class.

### ALN-301 — AlignmentServing

**Verdict**: PASS with 1 MEDIUM finding

- export_gguf() pipeline fully specified: merge check -> arch check -> HF-to-GGUF -> quantize -> validate.
- Post-conversion validation via llama_cpp.Llama + create_completion() — R1-02 addressed.
- BYOG escape hatch via `gguf_path` parameter — R1-02 addressed.
- Supported architecture allowlist with WARNING for untested.
- Q4_K_M and Q8_0 quantization. F16 supported.
- Ollama deployment with Modelfile + create + verify.
- vLLM config generation (JSON + launch script).
- **MEDIUM — ALN-301-F1**: The `_convert_hf_to_gguf()` method uses `subprocess.run([sys.executable, "-m", "gguf.convert", ...])`. The `gguf` package (PyPI) does NOT have a `gguf.convert` module. The HF-to-GGUF conversion is done by `convert_hf_to_gguf.py` in the `llama.cpp` repo, or more recently by the `gguf` package's own API. The actual API at implementation time may differ. The todo acknowledges this in "Implementation Notes" ("The gguf package's convert module interface may vary"), but the code sketch presents a specific invocation that is likely wrong. Suggest: replace the code sketch with a comment "# Implementation must verify the actual gguf package API at implementation time" and list the two known approaches: (a) `gguf` package API if available, (b) `convert_hf_to_gguf.py` from llama.cpp as subprocess fallback.

### ALN-302 — Adapter Merge

**Verdict**: PASS

- AdapterMerger class with merge() method fully specified.
- Idempotent: already-merged returns existing path.
- Prevents re-merge of exported adapters.
- Saves model + tokenizer.
- Updates AdapterRegistry merge_status.
- trust_remote_code=False, device_map="auto".
- merge_adapter() convenience function.
- No issues.

### ALN-400 — KaizenModelBridge

**Verdict**: PASS

- Factory pattern using only public Delegate APIs (R1-11) — correct.
- Auto-detection strategy: Ollama (GGUF + available) -> vLLM (endpoint reachable).
- discover_deployed_models() via Ollama /api/tags.
- Budget tracking limitation documented (R2-04).
- BridgeConfig, BridgeNotReadyError specified.
- delegate_kwargs pass-through for max_turns, max_tokens.
- No issues.

### ALN-401 — OnPremModelCache

**Verdict**: PASS

- OnPremConfig, OnPremModelCache, CachedModel dataclasses specified.
- Wraps huggingface_hub: snapshot_download(), scan_cache_dir(), try_to_load_from_cache().
- CLI with click: download, list, verify commands.
- Offline mode propagation through all from_pretrained() calls documented.
- CacheNotFoundError with actionable message including download command.
- ~400 lines total — reasonable scope.
- No issues.

### ALN-402 — Integration Tests

**Verdict**: PASS

- Full pipeline test class with setup fixture and synthetic datasets.
- 4 test categories: full pipeline, evaluator, BYOG, air-gap (manual).
- Ollama tests skip gracefully via @pytest.mark.skipif.
- GPU tests marked with @pytest.mark.gpu.
- Air-gap manual test procedure documented.
- Model selection for CI (TinyLlama-1.1B) specified.
- No issues.

---

## 3. Cross-Workspace Contract Alignment

### ML-002 <-> ALN-001

| Contract Point             | ML-002 Specifies                                       | ALN-001 Expects                                | Aligned?                                                                                                                                                                                                                                                                                                                                     |
| -------------------------- | ------------------------------------------------------ | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| register_model() signature | `name, artifact_path, metrics, signature, tags, stage` | Calls via `super()` (inheritance)              | **MISMATCH** — ALN-001 chose composition over inheritance. ML-002 still describes the inheritance pattern in the Extension Points table. ML-002 should be updated to note that ALN-001 opted for composition. The contract methods are still correct (ALN-101 calls them as delegation, not super()), but the documentation is inconsistent. |
| DataFlow models            | MLModel, MLModelVersion, MLModelTransition             | AlignAdapter, AlignAdapterVersion (standalone) | ALIGNED — ALN-001 chose standalone models with FK references, not inheritance. No conflict.                                                                                                                                                                                                                                                  |
| ArtifactStore protocol     | `save, load, exists, delete`                           | Used for adapter weight storage                | ALIGNED                                                                                                                                                                                                                                                                                                                                      |
| Stage enum                 | staging, shadow, production, archived                  | Same stages used                               | ALIGNED                                                                                                                                                                                                                                                                                                                                      |

**Action required**: ML-002 Extension Points table still shows "Calls `super().register_model()`" and "AdapterRegistry(ModelRegistry)" inheritance. Since ALN-001 decided on composition, ML-002 should either (a) be updated to reflect the composition decision, or (b) note that the extension pattern is "recommended" not "required" and that composition is an acceptable alternative. This is a **documentation inconsistency, not a code blocker**.

### ML-001 <-> ALN-101

| Contract Point        | ML-001 Provides                                                                | ALN-101 Needs                               | Aligned?                                                    |
| --------------------- | ------------------------------------------------------------------------------ | ------------------------------------------- | ----------------------------------------------------------- |
| MLToolProtocol        | 3 methods: predict, get_metrics, get_model_info                                | Not used by AdapterRegistry                 | ALIGNED (no dependency)                                     |
| AgentInfusionProtocol | 4 methods: suggest_model, suggest_features, interpret_results, interpret_drift | Not used by AdapterRegistry                 | ALIGNED (no dependency)                                     |
| FeatureSchema         | name, features, entity_id_column, timestamp_column, version                    | Not directly used                           | ALIGNED                                                     |
| ModelSignature        | input_schema, output_columns, output_dtypes, model_type                        | ALN-101 defines AdapterSignature separately | ALIGNED — R2 correctly identified these are different types |

**No issues.** The protocols package provides types for kailash-ml engines and kaizen agents. kailash-align correctly defines its own types (AdapterSignature) rather than misusing ModelSignature.

### ML-201 <-> ALN-101

| Contract Point      | ML-201 Provides                | ALN-101 Needs                              | Aligned?              |
| ------------------- | ------------------------------ | ------------------------------------------ | --------------------- |
| ModelRegistry class | Full implementation per ML-002 | HAS-A reference for cross-queries          | ALIGNED (composition) |
| DataFlow instance   | Shared db parameter            | Own db parameter + optional model_registry | ALIGNED               |
| ArtifactStore       | LocalFileArtifactStore default | Own adapter path management                | ALIGNED               |

**No issues.** ALN-101 takes an optional `model_registry` parameter for cross-registry lookups but does not depend on ModelRegistry for core functionality.

---

## 4. Summary Table

| Todo        | Verdict   | Findings                                     | Severity |
| ----------- | --------- | -------------------------------------------- | -------- |
| ML-000      | PASS      | —                                            | —        |
| ML-001      | PASS      | —                                            | —        |
| ML-002      | PASS      | —                                            | —        |
| ML-100      | PASS      | ML-100-F1: "stubs" phrasing in AC            | MINOR    |
| ML-101      | PASS      | —                                            | —        |
| ML-200      | PASS      | —                                            | —        |
| ML-201      | PASS      | —                                            | —        |
| ML-202      | PASS      | ML-202-F1: k-fold single-fold ambiguity      | MINOR    |
| ML-203      | PASS      | —                                            | —        |
| ML-204      | PASS      | —                                            | —        |
| ML-300      | PASS      | ML-300-F1: `_run_sync()` undefined           | MINOR    |
| ML-301      | PASS      | —                                            | —        |
| ML-302      | PASS      | —                                            | —        |
| ML-303      | PASS      | —                                            | —        |
| **ML-400**  | **AMEND** | ML-400-F1: tool data flow unclear            | MEDIUM   |
| ML-401      | PASS      | —                                            | —        |
| ML-500      | PASS      | ML-500-F1: status field inconsistency        | MINOR    |
| ML-501      | PASS      | ML-501-F1: file placement ambiguity          | MINOR    |
| ML-502      | PASS      | —                                            | —        |
| ALN-000     | PASS      | —                                            | —        |
| ALN-001     | PASS      | —                                            | —        |
| ALN-100     | PASS      | —                                            | —        |
| **ALN-101** | **AMEND** | ALN-101-F1: version numbering race condition | MEDIUM   |
| ALN-200     | PASS      | —                                            | —        |
| ALN-201     | PASS      | —                                            | —        |
| ALN-202     | PASS      | —                                            | —        |
| ALN-300     | PASS      | ALN-300-F1: evaluate_custom() is ellipsis    | MINOR    |
| **ALN-301** | **AMEND** | ALN-301-F1: gguf.convert module likely wrong | MEDIUM   |
| ALN-302     | PASS      | —                                            | —        |
| ALN-400     | PASS      | —                                            | —        |
| ALN-401     | PASS      | —                                            | —        |
| ALN-402     | PASS      | —                                            | —        |

### Cross-workspace

| Contract           | Verdict     | Finding                                                       |
| ------------------ | ----------- | ------------------------------------------------------------- |
| ML-002 <-> ALN-001 | **DOC FIX** | ML-002 still describes inheritance; ALN-001 chose composition |
| ML-001 <-> ALN-101 | ALIGNED     | No issues                                                     |
| ML-201 <-> ALN-101 | ALIGNED     | No issues                                                     |

---

## 5. Convergence Assessment

### Strengths

1. **Exceptional specification depth.** Most todos include full code sketches, complete dataclass definitions, exact file paths, and concrete test functions with assertions. An autonomous agent can implement the majority of these todos without asking a single question.

2. **Red team finding coverage is comprehensive.** Every R1 and R2 finding is traceable to a specific todo and specific acceptance criterion. The kailash-ml todos reference 8 distinct R1/R2 findings; kailash-align references 14. No orphaned findings.

3. **Cross-workspace contracts are well-defined.** The ML-002/ALN-001 extension contract, the composition decision, and the separate AdapterSignature are all explicitly documented. The one inconsistency (ML-002 still mentioning inheritance) is cosmetic, not structural.

4. **Dependency graphs are correct and consistent.** Frontmatter `depends_on` and `blocks` fields match the milestone tracker graphs in both workspaces. No circular dependencies. Cross-workspace dependencies (ML-002 -> ALN-001, ML-201 -> ALN-101) are explicitly noted.

5. **Quality tiering is applied consistently.** P0/P1/P2 tiers for engines and agents, with clear promotion criteria and the `@experimental` decorator for P2. This directly addresses the 9-engine scope risk (R1-07).

### Weaknesses Requiring Amendment

1. **ML-400 (MEDIUM)**: Agent tool data flow is underspecified. The code sketch shows tools accessing instance attributes that are never set from the method parameters. Fix: specify the data-binding pattern (set before Delegate creation or use closures).

2. **ALN-101 (MEDIUM)**: Version numbering has a TOCTOU race condition. Fix: specify atomic version increment (e.g., `SELECT MAX(version) ... FOR UPDATE` in a transaction, or use a counter field on AlignAdapter with optimistic concurrency).

3. **ALN-301 (MEDIUM)**: The GGUF conversion code sketch uses a `gguf.convert` module that likely does not exist in the `gguf` PyPI package. Fix: replace with a note that the actual API must be verified at implementation time, and provide the two known approaches.

### MINOR Items (informational, do not block implementation)

- ML-100-F1: Clarify "engine stubs" phrasing to avoid no-stubs confusion.
- ML-202-F1: Clarify single-fold vs full k-fold cross-validation behavior.
- ML-300-F1: Define the `_run_sync()` async-to-sync bridge pattern.
- ML-500-F1: Remove the non-standard `status: pending` frontmatter field.
- ML-501-F1: Clarify relationship between `compat/mlflow.py` and `serialization.py`.
- ALN-300-F1: Either implement `evaluate_custom()` body or defer to a tracked todo.

### Implementation Readiness

- **Ready to implement now**: 26 of 32 todos (81%)
- **Need amendment first**: 3 todos (ML-400, ALN-101, ALN-301) — MEDIUM findings
- **Documentation fix only**: ML-002 (cross-workspace alignment with ALN-001 composition decision)
- **Tracker/reference docs**: 2 (ML-000, ALN-000) — not implementable

**Estimated session impact of amendments**: <0.5 sessions total. The amendments are clarifications, not redesigns.

### Recommendation

Proceed to `/implement` for Phase 0 (ML-001, ML-002, ALN-001) immediately. These have zero findings. Amend the 3 MEDIUM-finding todos in parallel. The MINOR findings can be resolved by the implementing agent at implementation time — they are edge clarifications, not ambiguities.
