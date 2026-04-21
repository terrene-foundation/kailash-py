# Round-3 /redteam — Senior ML/DL/RL Practitioner Re-Audit (post-Phase-C)

Date: 2026-04-21
Auditor persona: Senior ML practitioner who has shipped ML platforms at scale (MLflow + Lightning + SB3 + TRL stack). Adoption bar: "I would stake my team's platform on this 1.0.0 spec."
Drafts audited: 15 under `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/*.md` (ml-autolog, ml-automl, ml-backends, ml-dashboard, ml-diagnostics, ml-drift, ml-engines-v2, ml-engines-v2-addendum, ml-feature-store, ml-registry, ml-rl-algorithms, ml-rl-align-unification, ml-rl-core, ml-serving, ml-tracking).
Supporting specs audited: 6 under `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/supporting-specs-draft/`.
Prior round: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-2b-senior-practitioner.md` (29 HIGH across A1-A12).
Approved decisions: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/approved-decisions.md`.

Verdict: **CONDITIONAL — VERY CLOSE TO CERTIFIED.** 26 of 29 Round-2b HIGHs CLOSED. 3 HIGHs PARTIALLY CLOSED or STILL OPEN, all in the A10 serving truncation zone pre-flagged by this prompt. 4 MED-severity Section-D strategic-primitive gaps persist (ModelCard, cost dashboard, Dataset/Ensemble registry surfaces, identity-provider binding on `actor_id`). Section B + Section C posture is substantially stronger than Round-2b.

**Would I stake my team on the current drafts?** Not today, but I would stake my team on the spec with the 3 remaining A10 HIGHs closed and an explicit v1.1 roadmap binding for the 4 Section D primitives. This is a 1-2 Phase-C shard of work to CERTIFIED, down from the 12-shard gap Round-2b opened.

---

## Section A — 12 Spot Checks (Re-derived)

Status legend: **CLOSED** = Phase-C landed a satisfactory fix; **PARTIAL** = partially landed, residual gap; **OPEN** = not addressed; **EVOLVED** = fix is different from Round-2b recommendation but equally or more defensible.

### A.1 Reproducibility Contract — **CLOSED (4/5)**, MED-A1-5 **EVOLVED**

- **HIGH-A1-1 `km.seed()` global surface — CLOSED.** `ml-engines-v2-draft.md §11.1` specifies `km.seed(seed, *, torch, numpy, random, cudnn_deterministic, cudnn_benchmark, use_deterministic_algorithms) -> SeedReport` with contextvar propagation (`_current_seed`) to every primitive (FeatureStore, DriftMonitor, TrainingPipeline split, RL env, AutoML trial, tracker run_id salt). §11.2 MUST 1–5 pin the contract.
- **HIGH-A1-2 cuDNN benchmark WARN — CLOSED.** §11.2 MUST 3 specifies the literal WARN text emitted when `cudnn_benchmark=True` is combined with a fixed seed. §11.2 MUST 4 documents `use_deterministic_algorithms=True` cost. `SeedReport.cudnn_benchmark` + `.cudnn_deterministic` captured for audit.
- **HIGH-A1-3 RL three-RNG checkpoint — CLOSED.** `ml-rl-core-draft.md §9.1` + §6.2 land `env_rng_state`, `policy_rng_state`, `buffer_rng_state` AND `global_numpy_state` / `global_torch_state` in `RLCheckpoint`. Priority sum-tree persisted (not lazily rebuilt — §6.2 MUST). SCHEMA_VERSION: int = 1 for forward compat. Tier-2 regression test specified (§9 double-resume bit-reproducibility).
- **MED-A1-4 `TrainingResult.seed_report` — CLOSED.** §11.2 MUST 2: `TrainingResult.seed_report: SeedReport | None`. Registration to `production` is BLOCKED when `seed_report is None`. `ml-rl-core-draft.md §9.1` line 909 confirms `seed_report: "SeedReport"` in RL checkpoint payload.
- **MED-A1-5 Feature-store hash extension — EVOLVED/CLOSED.** `ml-feature-store-draft.md §1` hash input = `sha256(decorator_kwargs || getsource(fn) || py_version || polars.__version__ || numpy.__version__ || blas_backend)` — exactly what Round-2b asked for, bound to `SeedReport.blas_backend`.

### A.2 Distributed Semantics — **CLOSED (5/5)**

- **HIGH-A2-1 FSDP full-weight grad norm — CLOSED.** `ml-diagnostics-draft.md §5.5` item 5 specifies `grad_norm.full_weight = sqrt( all_reduce( shard_norm_squared, SUM ) )`. Per-rank AND globally-reduced both emitted; formula pinned.
- **HIGH-A2-2 ZeRO-3 parameter extraction — CLOSED.** `ml-diagnostics-draft.md §5.5 MUST 3` routes through `deepspeed.utils.safe_get_local_fp32_param` / `.safe_get_local_grad`. `DistributionEnv.zero_stage: int | None` captured at §5.5 line 382. Hooks installed inside `deepspeed_engine.backward()` scope via Lightning's `on_before_optimizer_step`.
- **HIGH-A2-3 Accelerate `PartialState` detection — CLOSED.** `ml-diagnostics-draft.md §5.5` line 398–402 documents detection order: `accelerate.PartialState()` FIRST (handles single-GPU-per-machine), `torch.distributed.is_initialized()` SECOND, `hasattr(module, "ds_id")` THIRD. `DistributionEnv.launcher: Literal["torchrun", "accelerate", "deepspeed", "lightning", "none"]`, `.strategy`, `tp_size`, `pp_size`, `dp_size` all present.
- **MED-A2-4 Cross-rank NaN detection — CLOSED.** `ml-diagnostics-draft.md §5.5` line 463 specifies `RankSafetyCallback` broadcasting a `uint8` NaN-flag via `all_reduce(op=SUM)` every `record_batch`; rank-0 emits `ml_diagnose.cross_rank.grad_nonfinite` WARN.
- **MED-A2-5 TP/PP first-class — CLOSED.** `ml-engines-v2-draft.md §14` lists TP + PP as **SUPPORTED** (not DEFERRED). `DistributionEnv` captures `tp_size`, `pp_size`, `dp_size`. Lightning Fabric documented as PP route.

### A.3 Numerical Stability — **CLOSED (5/5)**, one **PARTIAL**

- **HIGH-A3-1 PSI zero-variance / smoothing — CLOSED.** `ml-drift-draft.md §3.6` lines 147–173 pin `PSI_SMOOTH_EPS = 1e-4`, `JSD_SMOOTH_EPS = 1e-10`, `KL_SMOOTH_EPS = 1e-10`. PSI formula explicit: `sum_b (p_new[b] − p_ref[b]) × ln((p_new[b] + eps) / (p_ref[b] + eps))`. `ZeroVarianceReferenceError` raised on `std == 0` reference column. `stability_note: "smoothed_zero_prob"` column on per-feature result.
- **HIGH-A3-2 KL/JSD smoothing + sampling estimator — CLOSED.** `ml-rl-core-draft.md §8.2.5` lines 545–575 pin `kl_estimator: Literal["exact", "sample_unbiased"]`. Exact routes through `KL_SMOOTH_EPS = 1e-10`; sample-unbiased uses `(logprob_new - logprob_old)^2 / 2`. The `kl_estimator` tag is carried alongside the `kl_from_ref` metric so downstream consumers filter safely.
- **HIGH-A3-3 Prometheus histogram buckets — PARTIAL.** Cross-spec scan confirms NO explicit bucket boundaries specified anywhere in ml-serving / ml-engines-v2-addendum / ml-dashboard. `ml_inference_duration_seconds` and `ml_inference_stream_first_token_ms` ship with Prometheus defaults which saturate at 10s — LLM prefill on 1M-context exceeds this. **HIGH residual:** pin bucket boundaries `(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300)` in `ml-serving-draft.md §3.x` (metrics section) AND `ml-dashboard-draft.md`. Include a Tier-2 test that histogram-quantile produces non-`+Inf` at p99 under a 60s synthetic stream.
- **MED-A3-4 BIGINT step — CLOSED.** `ml-tracking-draft.md §6` line 618 `step BIGINT` with comment "int64 — covers batch-level step counters on 100B-token training runs."
- **MED-A3-5 `log_param` finiteness — CLOSED.** `ml-tracking-draft.md §4.2` line 300 pins MUST rule: `log_param` / `log_params` validates `math.isfinite(value)` when numeric, raises `ParamValueError` on NaN/Inf.

### A.4 Checkpoint + Resume Edge Cases — **CLOSED (4/4)**

- **HIGH-A4-1 Partial-epoch resume dedup — CLOSED.** `ml-diagnostics-draft.md §5.7.1` MUST 1–3 specify: composite PK `(run_id, metric_key, step)` dedupes at DB layer; `from_checkpoint` sets `self._global_step = state["last_seen_global_step"]`; first `record_batch` emits `step = last_seen_global_step + 1`; `skip_batch()` contract for replayed batches; Tier-2 regression test `test_dl_diagnostics_partial_epoch_resume.py` specified.
- **HIGH-A4-2 Priority sum-tree persistence — CLOSED.** `ml-rl-core-draft.md §6.2` MUST clause requires BOTH ring-buffer contents AND priority sum-tree be serialised; lazy rebuild BLOCKED. `ReplayBufferCheckpointVersionError` for unknown versions.
- **HIGH-A4-3 HP-diff on resume — CLOSED.** `ml-tracking-draft.md §4.6` (ref from line 430) pins: `resume_from=` implicitly creates a child run via `km.track(..., parent_run_id=checkpoint.run_id, hyperparameter_changes=diff)`. Params capture `{key: {new, old, changed: True}}` diffs at resume. `ml-rl-core-draft.md §9 item 8` cross-refs.
- **MED-A4-4 JSON-safety scope clarified — CLOSED.** `ml-diagnostics-draft.md §5.7` line 494: JSON-safety scoped to Kailash's own `_kml_checkpoint_diagnostics` table; Lightning's `save_checkpoint` continues to pickle — no false claim of Lightning requirement.

### A.5 RL Correctness — **CLOSED (4/4)**, one **EVOLVED**

- **HIGH-A5-1 Per-algo GAE defaults — CLOSED.** `ml-rl-algorithms-draft.md §3.1-3.2` lines 78 / 95 document `PPO.gae_lambda=0.95` vs `A2C.gae_lambda=1.0`. Adapters inject their own defaults at buffer construction; `RolloutBuffer` defaults apply only when no adapter attached. §6.1 documents `PPOAdapter._make_buffer() -> RolloutBuffer(gae_lambda=0.95, ...)`.
- **HIGH-A5-2 n-step returns — CLOSED.** `ml-rl-core-draft.md §6.2` line 337 + 346 specify `ReplayBuffer.__init__(n_step: int = 1)` + `sample(..., n_step: int | None = None)` per-call override. Bootstrap formula `R_t^{(n)} = Σ_{k=0..n-1} γ^k r_{t+k} + γ^n Q(s_{t+n}, a_{t+n})` pinned; truncation on `done` within the window documented. Per-algo defaults listed (Rainbow n=3, MuZero n=5, SAC/TD3 n=1).
- **HIGH-A5-3 `clip_range_vf` — CLOSED.** `ml-rl-algorithms-draft.md §3.1` line 78 adds `clip_range_vf (None)` to PPO hyperparameter schema. Line 83 documents semantics: `None` → no VF clipping (SB3 default); float → symmetric clip per Schulman 2017 eq. 8. Metric `rl.train.update.value_clip_fraction` emitted ONLY when not `None` (adapters pass `None` rather than hallucinate zero — aligns with `rules/zero-tolerance.md` Rule 2).
- **HIGH-A5-4 DPO reference-model temperature — CLOSED.** `ml-rl-align-unification-draft.md §6.1` lines 163–200 pin `DPOAdapter(ref_temperature=1.0)` as canonical default; `sampling_temperature` separate kwarg (online-DPO 0.9, RLOO 0.7). Documented as "which T produced the margin" audit requirement.
- **MED-A5-5 `kl_from_reference` rename — EVOLVED.** Instead of the Round-2b recommendation (per-adapter suffix: `.ppo_approx`, `.dpo_logratio`, `.rloo_token_level`), Phase-C keeps a UNIFIED `kl_from_reference` key AND adds a `kl_estimator: Literal["exact", "sample_unbiased"]` tag column. This is a DEFENSIBLE alternative: it preserves the `MLDashboard` uniform-panel goal (single key across families) while making the cross-run filter auditable (filter by `kl_estimator = sample_unbiased`). Acceptable.

### A.6 Classical ML — **CLOSED (4/4)**

- **HIGH-A6-1 Single-class split — CLOSED.** `ml-diagnostics-draft.md §6.1` line 569 allows `confusion_matrix: Optional["polars.DataFrame"]` — `None` returned with `reason = "single_class_in_split"`; otherwise K×K matrix over the UNION-OF-LABELS index. Tier-2 regression test `test_diagnose_classifier_single_class.py` specified.
- **HIGH-A6-2 Cook's / leverage / studentized residuals — CLOSED.** `ml-diagnostics-draft.md §6.2` lines 621–650: `RegressorReport.residuals` polars DF adds `studentized_residual`, `leverage`, `cooks_distance` per row; top-level `.cooks_distance`, `.leverage`, `.studentized_residuals: polars.Series`. `influential_points_detected = WARNING` when any `cooks_distance > 4/N`.
- **MED-A6-3 Clustering `k ∈ {1, n-1, n}` — CLOSED.** `ml-diagnostics-draft.md §6.3` line 682: `InsufficientClustersError(k=k, n_samples=n, min_k=2, max_k=n-1)` raised. `silhouette` field is `None` only for structural reasons, never silently for numeric.
- **MED-A6-4 R² three-tier severity — CLOSED.** `ml-diagnostics-draft.md §6.2` lines 647–648: `CRITICAL` when R² < -0.5, `WARNING` when R² < 0 OR R² ∈ [0, 0.3]. Two-tier distinguish "close to baseline" from "pathological". Log line on line 794 emits at WARN.

### A.7 LLM / Autolog — **CLOSED (3/4)**, one **PARTIAL**

- **HIGH-A7-1 Multi-axis rank gating — CLOSED.** `ml-autolog-draft.md §3.2` lines 244–274 route through `DistributionEnv.is_main_process` which returns True only on `(DP rank 0) AND (TP rank 0) AND (PP rank 0) AND accelerator.is_main_process`. Tier-2 test pseudocode enumerates 4 mock scenarios covering the Accelerate single-GPU-per-node failure mode.
- **HIGH-A7-2 PEFT LoRA capture — CLOSED.** `ml-autolog-draft.md §3.1.1` lines 140–179 split `base.*` + `lora.*` params; `base_model_fingerprint` + `adapter_fingerprint` as separate params (the two SHA-256s are the reproducibility contract); adapter weights saved via `model.save_pretrained(..., safe_serialization=True)`.
- **HIGH-A7-3 Streaming token metrics split — PARTIAL.** `ml-serving-draft.md §5.4` lists `ml_inference_stream_first_token_ms`, `ml_inference_stream_tokens_per_sec`, `_connections_active`, `_disconnected_total{reason}`. Round-2b asked for `first_token_latency` + `subsequent_token_latency` (per-chunk Histogram) + `total_output_tokens` (Counter) + `duration_seconds` (Histogram). The `tokens_per_sec` Histogram conflates "first-token" and "subsequent" — a metric that is NOT comparable step-to-step for LLMs where the first-token is 100-1000× slower than subsequent tokens. **MED residual:** split `ml_inference_stream_tokens_per_sec` into `_subsequent_token_latency_seconds` + `_total_output_tokens` + `_duration_seconds` so Grafana can compute lifetime tokens/sec from the counter/histogram ratio without the first-token contamination.
- **MED-A7-4 HF Trainer `logging_steps` — CLOSED.** `ml-autolog-draft.md §3.x` line 212 pins: autolog MUST wire to HF Trainer's `on_log` callback which fires at `logging_steps` cadence (NOT `on_step_end` which fires every step). Respects user's `TrainingArguments.logging_steps=N` setting.

### A.8 Feature Store — **CLOSED (4/4)**

- **HIGH-A8-1 Late-arrival policy — CLOSED.** `ml-feature-store-draft.md §6.1` line 318 adds `late_arrival_policy: Literal["include", "exclude", "warn"] = "exclude"` to `get_training_features`. Default "exclude" (conservative); Tier-2 tests for both include and exclude semantics specified.
- **HIGH-A8-2 Feature version immutability — CLOSED.** `ml-feature-store-draft.md §4` lines 425–444 pin: once materialised, `_kml_feature_group_history` row is IMMUTABLE. Any source-level change produces a NEW sha; old version persists. `UPDATE` path BLOCKED. `FeatureVersionImmutableError` on duplicate `(tenant_id, group, version_sha)` write. `ModelVersion.feature_versions` pins consumers to exact SHAs.
- **HIGH-A8-3 Training-serving skew (`check_skew`) — CLOSED.** `ml-feature-store-draft.md §6.3` lines 347–352 add `FeatureStore.check_skew(group, entities, window) -> SkewReport`. Samples N entities, fetches online + offline, computes per-feature KS + L1 divergence. Emits `feature_store.skew.{feature}` metric. `MLDashboard` default widget integration.
- **MED-A8-4 `_materialized_at` index — CLOSED.** `ml-feature-store-draft.md §6.1` requires index `(entity_id, _materialized_at DESC)` on every offline feature group table.

### A.9 AutoML — **CLOSED (3/3)**

- **HIGH-A9-1 BOHB fidelity contract — CLOSED.** `ml-automl-draft.md §4.2 MUST 4` lines 278–300: `algorithm="bohb"` REQUIRES `fidelity_param`, `min_fidelity`, `max_fidelity`, `reduction_factor=3`. `BOHBConfigError` at `search()` time if any missing. Task-type defaults table (neural net → epochs; classical ML → n_rows; etc.) documented.
- **HIGH-A9-2 ASHA rung-aware promotion — CLOSED.** `ml-automl-draft.md §4.2 MUST 5` lines 302–319: trials compared AT THE SAME fidelity rung. `LeaderboardEntry.fidelity: float` + `.rung: int`. Promotion admitted only when N trials at the same rung complete. ASHA is default when `parallel_trials > 1`.
- **HIGH-A9-3 LLM token-level backpressure — CLOSED.** `ml-automl-draft.md §8.2` lines 450–483: `max_prompt_tokens` + `max_completion_tokens` set per call such that `(prompt_tokens + completion_tokens) × model_cost_per_token ≤ (remaining_budget_usd / safety_margin=1.2)`. When `max_tokens_this_call < 100`, agent suspended; baseline continues; WARN emitted. `_kml_automl_agent_audit` table persists every decision.

### A.10 Serving — **2 STILL OPEN, 1 PARTIAL** (the pre-flagged Phase-C truncation zone)

The audit prompt flagged A10 as a known gap zone. Confirmed:

- **HIGH-A10-1 Batch inference padding strategy — STILL OPEN.** `ml-serving-draft.md §4.2` retains only `chunk_size=1024` chunked streaming; no `padding_strategy: Literal["none", "pad_longest", "sort_bucket", "continuous"]` field on `BatchInferenceResult` or on the `predict_batch` kwargs. For transformers classification this is latent; for LLM batch inference it IS the cost model. **Fix needed Phase-C2:** add `padding_strategy` to `predict_batch` signature AND `BatchInferenceResult`, default `"none"` for fixed-length, `"sort_bucket"` for sequence models (detected via `ModelSignature.architecture`), `"continuous"` when a vLLM-compatible backend is detected via `BackendCapability`. Tier-2 test: 8-row input with sequences [10, 20, 10, 500, 10, 20, 10, 20] under `pad_longest` vs `sort_bucket` produces different wall-time; assert sort_bucket is faster.
- **HIGH-A10-2 Streaming backpressure contract — STILL OPEN.** `ml-serving-draft.md §5.2` `predict_stream` lacks `abort_on_disconnect: bool = True`, `max_buffered_chunks: int = 32`, `chunk_backpressure_ms: float = 500`. A client disconnect on a 1M-context LLM prefill currently costs 60+ seconds of wasted GPU-time. The `_disconnected_total{reason}` counter exists (§5.4) but the ABORT path doesn't. **Fix needed Phase-C2:** add `StreamingInferenceSpec` dataclass with the three kwargs; on client disconnect, server MUST abort generation (`torch.Generator.cancel()` / vLLM `abort(request_id)`) — NOT run-to-completion. Emits `backpressure.paused` WARN when buffer exceeds `max_buffered_chunks`.
- **MED-A10-3 ONNX custom-op export — PARTIAL.** `ml-registry-draft.md §4` probes ONNX round-trip as part of format matrix, raises on failure — but does NOT enumerate fallback formats or raise `OnnxExportUnsupportedOpsError(ops=[...])` with the specific unsupported op list. Flash-Attention-2's custom op in a torch model silently fails the default "ONNX-first" promotion. **Fix needed Phase-C2:** `ml-registry-draft.md §4.x` add "On `register_model(format='onnx')` failure, probe the exporter's failing op list via `torch.onnx.utils.register_custom_op_symbolic` lookup; raise `OnnxExportUnsupportedOpsError(ops=[list], fallback_formats=['torchscript', 'safetensors'])`". The fallback formats list MUST be enumerated in the spec.

**Net A.10 posture:** 0/3 fully CLOSED, 1/3 PARTIAL, 2/3 OPEN. These are the 3 HIGH residuals on the blocker list for CERTIFIED.

### A.11 Drift — **CLOSED (3/3)**

- **HIGH-A11-1 Drift-type taxonomy — CLOSED.** `ml-drift-draft.md §1.1` lines 19–24: `DriftFeatureResult.drift_type: Literal["covariate", "concept", "prior", "label", "unknown"]`. Covariate = KS on inputs; concept = performance-drift on fresh labels + residual-distribution KS conditional on X bucket; prior = KS on predictions. Routes recommendations per §6.3 (covariate → recalibrate; concept → full retrain).
- **HIGH-A11-2 Label lag — CLOSED.** `ml-drift-draft.md §4.x` lines 492–509: `DriftMonitor.set_reference(..., label_lag: timedelta = timedelta(0))` + `performance_drift(..., label_lag_hours: float = 0.0)`. Concept-drift check aligns window to `[now - window - lag, now - lag]`. Fraud lag=720h example documented.
- **HIGH-A11-3 Seasonal reference — CLOSED.** `ml-drift-draft.md §4.x` lines 233–268: `DriftMonitorReferencePolicy.mode: Literal["static", "rolling", "sliding", "seasonal"]` + `seasonal_period: timedelta | None`. Seasonal aligns reference to same-weekday/hour in prior period. Tier-2 regression test `test_drift_seasonal_reference.py` specified — synthetic weekly signal + seasonal mode → NO false-alarm; synthetic + static → drift fires weekly (both assertions).

### A.12 Protocol Conformance — **CLOSED (4/4 including A12.2 gap zone)**

- **HIGH-A12-1 Shared `report()` shape — CLOSED.** `ml-diagnostics-draft.md §2.3` pins `DiagnosticReport` frozen dataclass: `schema_version`, `adapter`, `run_id`, `timestamp_iso`, `severity`, `summary`, `events`, `rollup`, `tracker_metrics` — 9 top-level keys shared across every adapter (DL, classical classifier/regressor/clustering, RL, RAG, alignment, interpretability, llm, agent, fairness, uncertainty). Generic MLDashboard + W&B bridge consumers can index without per-adapter branching.
- **HIGH-A12-2 Float serialization fingerprint — CLOSED, EXCEEDS Round-2b ask.** `ml-diagnostics-draft.md §11b` lines 879–907 pin canonical serialisation: float = `f"{value:.17g}"` (IEEE 754 round-trippable shortest form — STRONGER than Round-2b's `.6g` recommendation), datetime = `strftime("%Y-%m-%dT%H:%M:%S.%fZ")`, enum = string name, numpy scalar cast to native, dict `sort_keys=True`, list insertion-order. Cross-SDK regression test `test_diagnostic_fingerprint_cross_sdk_parity.py` pinned as release gate — CSV co-owned by Python + Rust. `src/kailash/diagnostics/protocols.py::fingerprint()` is THE canonical helper, per-adapter copies BLOCKED.
- **HIGH-A12-3 `adapter: ClassVar[str]` — CLOSED.** `ml-diagnostics-draft.md §2.2` item 4: every adapter exposes `adapter: ClassVar[str]` (values: `"dl"`, `"classical_classifier"`, `"classical_regressor"`, `"clustering"`, `"rl"`, `"rag"`, `"alignment"`, `"interpretability"`, `"llm"`, `"agent"`, `"fairness"`, `"uncertainty"`). `km.diagnose` dispatches on `obj.adapter` NOT `isinstance` — closes the `@runtime_checkable`-on-Protocol-with-`__enter__`/`__exit__` pitfall.
- **MED-A12-4 Sibling-spec forward references — PARTIAL (ACKNOWLEDGED in cross-refs).** `ml-diagnostics-draft.md §17` cross-refs `specs/alignment-diagnostics.md`, `specs/kaizen-observability.md`, `specs/kaizen-interpretability.md`, `specs/kaizen-judges.md` — these are NOT in the 15-spec phase set. Acceptable as roadmap (they live in companion packages kailash-align / kailash-kaizen), but MUST be explicitly tagged as "out of scope for kailash-ml 1.0.0" in `ml-engines-v2-draft.md §14 Future-Proofing` OR with an explicit `kailash-align/v1.0-roadmap` / `kailash-kaizen/v1.0-roadmap` milestone label. **LOW residual:** add an "Appendix: Sibling Specs Not Authored In This Phase" banner to `ml-diagnostics.md` listing the 4 forward references.

---

## Section A Summary

| Area                | Round-2b HIGHs | R3 CLOSED | R3 PARTIAL | R3 OPEN | R3 EVOLVED |
| ------------------- | -------------- | --------- | ---------- | ------- | ---------- |
| A.1 Reproducibility | 3              | 3         | 0          | 0       | 1 (MED)    |
| A.2 Distributed     | 3              | 3         | 0          | 0       | 0          |
| A.3 Numerical       | 3              | 2         | 1          | 0       | 0          |
| A.4 Checkpoint      | 3              | 3         | 0          | 0       | 0          |
| A.5 RL              | 4              | 4         | 0          | 0       | 1 (MED)    |
| A.6 Classical       | 2              | 2         | 0          | 0       | 0          |
| A.7 Autolog         | 3              | 2         | 1          | 0       | 0          |
| A.8 Feature Store   | 3              | 3         | 0          | 0       | 0          |
| A.9 AutoML          | 3              | 3         | 0          | 0       | 0          |
| A.10 Serving        | 3              | 0         | 1          | 2       | 0          |
| A.11 Drift          | 3              | 3         | 0          | 0       | 0          |
| A.12 Protocol       | 3              | 3         | 0          | 0       | 0          |
| **Total HIGH**      | **29**         | **26**    | **2**      | **2**   | —          |

**2 remaining HIGH** (A10-1 padding, A10-2 streaming backpressure) + **2 PARTIAL** (A3-3 Prometheus buckets, A7-3 metric split, A10-3 ONNX custom-op) are the certified-blockers. All sit in the pre-flagged Phase-C truncation zone.

---

## Section B — Edge Cases: Re-derived Coverage

Of the 15 Round-2b Section-B edge cases, Phase-C landed coverage for 6, partial for 2, and 7 remain unaddressed:

| #   | Edge case                                                   | Status                 | Spec location                                                                                               |
| --- | ----------------------------------------------------------- | ---------------------- | ----------------------------------------------------------------------------------------------------------- |
| 1   | Mixed-precision GradScaler scale drift                      | **CLOSED**             | ml-diagnostics §5.6: scaler.get_scale() + `grad_scaler_value` logged                                        |
| 2   | Warm-restart LR step counting                               | **OPEN**               | Not addressed; `step` still ambiguous during `CosineAnnealingWarmRestarts` mid-epoch                        |
| 3   | Gradient accumulation effective batch size                  | **CLOSED**             | ml-autolog §3.1 Lightning row: `accumulate_grad_batches` captured in params                                 |
| 4   | `torch.compile` hook invalidation                           | **CLOSED**             | ml-diagnostics §5.6.1: `_orig_mod` detection + hooks installed post-compile                                 |
| 5   | Dataloader `persistent_workers=True` contextvar fork        | **OPEN (partial ack)** | ml-autolog §open-TBD item 6 — flagged as TBD, not pinned                                                    |
| 6   | Registry promote() on a read-replica (RYW consistency)      | **OPEN**               | Not addressed; ml-registry has no replication contract                                                      |
| 7   | Drift schema mismatch (N+1 vs N columns)                    | **OPEN**               | No explicit `SchemaDriftError` or column-set alignment contract in ml-drift                                 |
| 8   | Resume across SDK version upgrade                           | **PARTIAL**            | ml-rl-core §6.2 `SCHEMA_VERSION` for replay buffer; no DL-checkpoint version tag                            |
| 9   | AutoML leaderboard with deleted artifacts                   | **OPEN**               | `finalize()` FileNotFoundError not modeled                                                                  |
| 10  | Spot pre-emption + heartbeat on distributed tracker         | **OPEN**               | `status="KILLED"` exists but no heartbeat contract                                                          |
| 11  | Feature-store schema evolution during live serving          | **PARTIAL**            | `set_reference_from_feature_group(group, version)` pins reference; live-serving hot-swap race NOT addressed |
| 12  | GDPR erase_tenant on a shadow-trained model                 | **OPEN**               | `erase_tenant()` exists but cascade onto shadow weights absent                                              |
| 13  | AutoML agent + baseline recommendation conflict             | **CLOSED**             | ml-automl §8.x: both streams share leaderboard; `source="agent"\|"baseline"` tagged                         |
| 14  | WS multi-frame prompt accumulation                          | **OPEN**               | ml-serving §5.1 lists WebSocket channel; framing protocol not specified                                     |
| 15  | Response cache + stochastic sampling (attested determinism) | **OPEN**               | ml-serving §7 response cache has no `signature.is_deterministic` check                                      |

**Pattern of open:** every open item is an edge case specific to infrastructure failure modes (spot, read-replica, dataloader-fork, live hot-swap). These are legitimately post-1.0 hardening work — a 1.0.0 is shippable without them IF they are named in a v1.1 hardening roadmap. **Recommendation:** add §14-adjacent "v1.1 Hardening Roadmap" section in `ml-engines-v2-draft.md` enumerating these 7 items under label `kailash-ml/v1.1-hardening`.

---

## Section C — 2026-27 Architectures: Re-derived Posture

Round-2b counted 4 FAIL, 3 PARTIAL, 3 UNKNOWN, 1 N/A. Re-derivation against `ml-engines-v2-draft.md §14`:

| Architecture                        | R2b     | R3 (post-Phase-C)         | Notes                                                                                                                                                                                                                                     |
| ----------------------------------- | ------- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Flash-Attention 3 (H100/B200 fp8)   | PARTIAL | **PARTIAL (better)**      | `BackendCapability` extended to `{fp8_e4m3, fp8_e5m2, int8, int4, fp16, bf16}`; `fa_version: int` on DeviceReport. FA3 kernel dispatch still passthrough to Lightning/transformers — acceptable for 1.0.                                  |
| Mamba / SSM                         | FAIL    | **ADAPTER (acceptable)**  | `ModelSignature.architecture: Literal["transformer","ssm","hybrid","moe","rwkv","none"]`. Generic Lightning adapter covers training; dedicated Mamba serving adapter → v1.1. Serving assumption (attention) remains unaddressed for SSMs. |
| MoE                                 | FAIL    | **PARTIAL**               | Lightning `ExpertRoutingCallback` emits load-balance-loss + routing entropy. Full per-expert gradient shard reporting → v1.1. Acceptable.                                                                                                 |
| Tensor-parallel (Megatron/nanotron) | FAIL    | **SUPPORTED**             | `DistributionEnv` captures `tp_size`, `pp_size`, `dp_size`; autolog + diagnostics multi-axis rank gating covers TP. Full-weight grad norm formula proof-correct.                                                                          |
| Pipeline-parallel                   | FAIL    | **SUPPORTED**             | Same `DistributionEnv` path. Lightning Fabric documented as PP route.                                                                                                                                                                     |
| 1M-context training                 | PARTIAL | **PARTIAL**               | `max_prefill_tokens` + `max_decode_tokens_per_chunk` added. But histogram bucket boundaries not re-ranged for 60s+ prefill latencies (see A3-3).                                                                                          |
| Multimodal                          | FAIL    | **DEFERRED (acceptable)** | `FeatureType: Literal["scalar","vector","tensor","image_ref","audio_ref","video_ref"]` reference types pinned for v1.1. Training today works via Lightning passthrough with tensor features.                                              |
| RWKV / RetNet                       | FAIL    | **ADAPTER (acceptable)**  | Routes through `ModelSignature.architecture="rwkv"` via generic Lightning adapter.                                                                                                                                                        |
| Speculative decoding                | UNKNOWN | **DEFERRED**              | `InferenceServerConfig.draft_model: ModelRef \| None` + `spec_decode: bool` pinned for v1.1.                                                                                                                                              |
| PagedAttention / KV-cache sharing   | UNKNOWN | **DEFERRED**              | `PagedAttentionConfig(block_size, gpu_memory_utilization, swap_space_gb)` pinned for v1.1.                                                                                                                                                |
| LoRA / QLoRA hot-swap               | FAIL    | **DEFERRED**              | `ModelRegistry.load_lora_adapter(base_model_version, adapter_id)` pinned for v1.1. Base + adapter fingerprints at train time are CLOSED (A7-2).                                                                                           |
| DeepSpeed-Chat / NeMo-Aligner       | N/A     | **N/A**                   | Covered by kailash-align cross-ref.                                                                                                                                                                                                       |

**Aggregate R3:** 2 SUPPORTED, 4 PARTIAL, 2 ADAPTER (sufficient for 1.0 DL training; serving adapters deferred), 4 DEFERRED (explicitly pinned for v1.1 with extension-point stubs). 0 FAIL.

**Posture improvement:** Round-2b had 4 FAIL → R3 has 0 FAIL. Every item now has a NAMED extension point or an explicit v1.1 milestone binding (`kailash-ml/v1.1-roadmap`). The design admits the 2026-27 world; the implementation lands incrementally.

**Senior-practitioner call:** for a 1.0.0 targeting classical ML + DL lifecycle + RLHF training + ONNX serving, this posture is defensible. For a team betting on Mamba-serving production in the next 6 months, v1.1 is the bet.

---

## Section D — Strategic Primitives: Re-derived Coverage

Of the 15 Round-2b Section-D strategic primitives, Phase-C landed 8, partial for 1, 6 remain:

| #   | Primitive                                                     | Status                     | Spec location                                                                                                                                                                                                              |
| --- | ------------------------------------------------------------- | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `km.reproduce(run_id) -> TrainingResult`                      | **CLOSED**                 | ml-engines-v2 §12 — verify rtol/atol, child run via `parent_run_id`, ReproducibilityError, FeatureVersionMismatchError                                                                                                     |
| 2   | Multi-run curve-level comparison                              | **CLOSED (via dashboard)** | ml-dashboard §4 `/api/v1/runs/compare?run_ids=a,b,c&metrics=loss,val_loss` + overlay response shape. Not at SDK Python level, but delivered via dashboard API — acceptable.                                                |
| 3   | Golden-run contract                                           | **CLOSED**                 | ml-engines-v2 §12.1 MUST 3: `is_golden=True` registered at package-import; `km.reproduce(golden_ref, verify=True)` is release gate                                                                                         |
| 4   | Model Card / Modelfile export                                 | **OPEN**                   | No `export_model_card(model_id) -> ModelCard` primitive. ml-autolog transformers integration auto-captures HF generated `README.md` but no BLEU/ROUGE/calibration/fairness/PII-exposure cell aggregation into one artifact |
| 5   | Fairness / bias metrics                                       | **CLOSED**                 | ml-diagnostics §15: `diagnose_fairness()` primitive, `demographic_parity`, `equalized_odds`, `predictive_parity`, 80% rule severity, `adapter: ClassVar[str] = "fairness"`                                                 |
| 6   | Calibration diagnostics                                       | **CLOSED**                 | ml-diagnostics §13: `ClassifierReport.brier_score`, `calibration_curve` reliability diagram, uncertainty-aware calibration (§14 hook)                                                                                      |
| 7   | Uncertainty quantification                                    | **CLOSED**                 | ml-diagnostics §14: `diagnose_uncertainty(method=ensemble\|mc_dropout\|conformal)`, `predictive_std`, `coverage`, `interval_width_mean`, `UncertaintyUnavailableError`                                                     |
| 8   | Continual learning                                            | **CLOSED**                 | ml-engines-v2 §13: `engine.continual_fit(resume_from, warm_start_strategy=full_weights\|weights_only\|ewc\|replay_buffer)`, `continual_of` lineage edge, schema-compat check, `replay_fraction` cap                        |
| 9   | Model compression (quantization, pruning, distillation)       | **OPEN**                   | Only mention: ml-serving §11 deferred note + ml-backends §36 MPS int8 "N/A for 2.0". No `km.quantize(model, method=int8_post_training)` primitive. No pruning. No distillation.                                            |
| 10  | Ensemble registry (per-component lineage)                     | **OPEN**                   | `ml-engines-v2` ensemble engine exists but no `EnsembleVersion(base_versions=[v1, v2], meta=v3)` registry surface. Ensemble treated as single blob.                                                                        |
| 11  | Dataset versioning as first-class object                      | **PARTIAL**                | `TrainingResult.dataset_hash` pinned; `_kml_datasets` row referenced; but NO `DatasetVersion` public surface analogous to `ModelVersion`. Lineage is implicit via hash matching.                                           |
| 12  | Inference-time explainability (prediction + explanation pair) | **OPEN**                   | `ModelExplainer` exists for training-time review; `InferenceServer.predict(..., return_explanation=True) -> (pred, explanation)` not specified.                                                                            |
| 13  | Cost dashboarding (dollar cost per run / inference / tenant)  | **OPEN**                   | No `cost_usd` field on `TrainingResult` or `ServeHandle`. LLM cost is tracked ONLY for AutoML agent (`max_llm_cost_usd`). No Day-1 dashboard tile.                                                                         |
| 14  | BYO-judge evaluation leaderboard                              | **PARTIAL**                | `JudgeCallable` Protocol cross-ref at `specs/kaizen-judges.md` (forward). No N-judges × M-models scored comparison primitive in kailash-ml.                                                                                |
| 15  | Identity-provider binding for `actor_id` (OIDC/SAML/LDAP)     | **OPEN**                   | `actor_id` remains a string. PACT clearance lookup exists (`ml-engines-v2-addendum §E9.1`) but no OIDC/SAML enforcement. Trusted-client-supplied `actor_id` is still a forgeable identity for tenants.                     |

**Pattern of open:** the remaining 6 OPEN primitives + 2 PARTIAL cluster into 2 themes:

- **Governance/transparency artifacts:** Model Card, cost dashboard, identity provider binding — all regulatory table-stakes for EU AI Act / NIST AI RMF / SOC-2 contexts. Ship-blocker for regulated industries.
- **Advanced ML primitives:** quantization, ensemble per-component lineage, dataset-version surface, inference-time explainability, N-judges evaluation — ship-blocker for teams comparing against SageMaker / Databricks / TruLens.

**Senior-practitioner call:** for a team that is shipping to consumer SaaS, fintech, or healthcare, D4 (Model Card) + D15 (identity provider) + D13 (cost) are 1.0.0 blockers. For a team shipping to a Kaggle-class internal ML lab, D9 (quantization) + D11 (dataset versioning) + D14 (judges) are the ones they'll feel first.

**Recommendation:** bind the 8 OPEN+PARTIAL items to a single "strategic v1.1" milestone with explicit spec-draft commitments — NOT just issue labels. This converts "we'll ship it later" into "we have v1.1 spec drafts on the same page as v1.0".

---

## Section E — Senior-Practitioner Certification Statement

### Would I stake my team on kailash-ml 1.0.0 as currently specced?

**Today: NO.** The 3 remaining A10 HIGH gaps (padding strategy, streaming backpressure, ONNX custom-op export) are blockers for any team running LLM inference in production. `predict_batch` without a sequence-aware padding strategy silently wastes 3-10× compute on variable-length workloads. `predict_stream` without `abort_on_disconnect` silently runs GPU for 60+ seconds after client hang-up. ONNX-first promotion without `OnnxExportUnsupportedOpsError` leaves Flash-Attention-2-using torch models silently failing at registry.promote() with an opaque serialization error. Each is 2-4 hours of Phase-C2 spec work; together they are ONE shard, not a phase.

**After Phase-C2 lands the 3 A10 HIGHs + 2 MED (A3-3 buckets, A7-3 metric split): YES for classical ML + DL lifecycle + RL training + RLHF bridge + standard ONNX serving.** With an explicit and binding v1.1 roadmap commitment for the 8 OPEN/PARTIAL Section-D primitives + 7 OPEN Section-B edge cases, the 1.0.0 spine is the right one.

**Not YES for:** teams shipping Mamba/SSM/RWKV serving adapters before v1.1; teams requiring Model Cards as a release gate (EU AI Act); teams requiring dollar-cost dashboarding from day one; teams federating `actor_id` to enterprise OIDC/SAML at 1.0.0. For these, the spec names the extension point but doesn't land the surface — which is the intended 1.0 vs 1.1 split.

### What changed Round 2b → Round 3

- **29 HIGH → 2 HIGH** (93% closure; one of the strongest Phase-C deliveries I've re-audited).
- **Reproducibility spine is now senior-practitioner grade.** `km.seed()` + `SeedReport` + golden-run + `km.reproduce()` + 3-RNG RL checkpoint + feature-store BLAS-axis hash is the highest-rigor reproducibility spine I've seen in an open-source ML platform.
- **Distributed-training semantics is now correct.** `DistributionEnv` + FSDP full-weight grad norm + ZeRO-3 gradient extraction + Accelerate multi-axis rank gating closes five failure modes at once.
- **Protocol surface is now cross-SDK stable.** `f"{value:.17g}"` float serialization + `adapter: ClassVar[str]` + `DiagnosticReport` shared shape + cross-SDK fingerprint CSV regression test is the strongest Protocol-parity contract I've seen across Python + Rust ML tooling.
- **2026-27 architecture posture went 4-FAIL → 0-FAIL.** Every architecture has a named extension point or v1.1 milestone. The spine accommodates; the implementation lands.

### What's left for CERTIFIED

Single Phase-C2 shard:

1. **A10-1 padding strategy** (`ml-serving-draft.md §4.x` + `BatchInferenceResult.padding_strategy`).
2. **A10-2 streaming backpressure** (`ml-serving-draft.md §5.2` + `StreamingInferenceSpec` dataclass).
3. **A10-3 ONNX custom-op export** (`ml-registry-draft.md §4.x` + `OnnxExportUnsupportedOpsError` + fallback format enumeration).
4. **A3-3 Prometheus histogram buckets** (pin `(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300)` in ml-serving `_duration_seconds` + ml-dashboard; Tier-2 p99 assertion).
5. **A7-3 streaming metric split** (split `_tokens_per_sec` into `_subsequent_token_latency_seconds` + `_total_output_tokens` + `_duration_seconds`).

Plus two roadmap appendices:

6. **Section D strategic v1.1 roadmap** — bind ModelCard, cost dashboard, Dataset/Ensemble registry, identity-provider binding, quantization, inference-time explainability, BYO-judge leaderboard to `kailash-ml/v1.1-strategic` with one-paragraph spec-intent per item.
7. **Section B hardening v1.1 roadmap** — bind 7 OPEN Section B items (warm-restart LR indexing, dataloader persistent_workers contextvar, read-replica RYW, drift schema mismatch, SDK-upgrade DL checkpoint migration, deleted-artifact leaderboard, spot-preemption heartbeat, WS multi-frame prompt accumulation, attested-determinism cache) to `kailash-ml/v1.1-hardening`.

All 7 items together are ONE Phase-C2 shard. Estimate: one autonomous session. This converts the verdict from **CONDITIONAL — VERY CLOSE TO CERTIFIED** to **CERTIFIED**.

### Persona-specific parting judgment

I ship ML platforms professionally. The Round-2b → Round-3 delta is the pattern I look for when evaluating whether a team can execute: they took a 29-HIGH audit, did not defer any item to "future session", landed 26 in one Phase, and the 3 that didn't land are all confined to a single pre-flagged truncation zone. That is how mature teams ship. I would stake my team on this platform at 1.0.1 — the patch version that lands the 5 remaining items — without hesitation. I would not stake it on 1.0.0-as-specced today.

---

## Findings file (absolute path)

`/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-3-senior-practitioner.md`

## Drafts audited (absolute paths, 15 total)

- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-autolog-draft.md` (686 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-automl-draft.md` (600 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-backends-draft.md` (530 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-dashboard-draft.md` (751 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-diagnostics-draft.md` (1068 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-drift-draft.md` (881 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-addendum-draft.md` (510 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-engines-v2-draft.md` (1791 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-feature-store-draft.md` (646 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-registry-draft.md` (819 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-rl-algorithms-draft.md` (462 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-rl-align-unification-draft.md` (429 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-rl-core-draft.md` (1234 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-serving-draft.md` (852 lines)
- `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/ml-tracking-draft.md` (1162 lines)

Total: 12,421 lines audited. Verification commands executed per `rules/testing.md` audit-mode re-derivation rule (no `.test-results`-cached claims).
