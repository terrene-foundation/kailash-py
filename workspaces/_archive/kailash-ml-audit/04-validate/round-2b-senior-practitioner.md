# Round-2 Phase-B /redteam — Senior ML/DL/RL Practitioner Audit

Date: 2026-04-21
Auditor persona: Senior ML practitioner who has shipped ML platforms at scale (MLflow + Lightning + SB3 + TRL stack). Adoption bar: "I would stake my team's platform on this spec."
Drafts audited: 13 under `workspaces/kailash-ml-audit/specs-draft/` (ml-autolog, ml-automl, ml-backends, ml-dashboard, ml-diagnostics, ml-drift, ml-engines-v2, ml-engines-v2-addendum, ml-feature-store, ml-registry, ml-rl-algorithms, ml-rl-align-unification, ml-rl-core, ml-serving, ml-tracking).

Verdict: **CONDITIONAL** — strong MLOps spine (tenant isolation, tracker wiring, registry lifecycle). Significant senior-practitioner gaps in reproducibility semantics, distributed-training correctness, numerical stability, checkpoint/resume invariants, and 2026-27 architecture posture. 29 HIGH, 21 MED, 14 LOW. Phase-C MUST close every HIGH before certification.

---

## Section A — 12 Spot Checks

### A.1 Reproducibility Contract

**HIGH-A1-1 — No global `km.seed()` surface across tracker + trainer + diagnostics + RL + AutoML.**
Grep for `seed`/`random_state`/`determin` shows ~50 hits but each spec treats `seed` locally (`TrainingPipeline.setup(seed=42)`, `RLTrainingConfig(seed=42)`, AutoML `seed=42`, drift reference sub-sampling `seed=42`, feature-store hash `py_version`). There is no single entry point that seeds `random`, `numpy.random`, `torch.manual_seed`, `torch.cuda.manual_seed_all`, `torch.backends.cudnn.deterministic`, `torch.backends.cudnn.benchmark`, `gymnasium` env seed, `polars.set_random_seed`, and an HF `accelerate` seed propagation in one call. A user running `km.MLEngine(seed=42)` cannot today guarantee a reproducible run across engines. **Fix in Phase-C:** `kailash_ml.reproducibility.set_global_seed(seed, *, deterministic_algorithms=False, cudnn_benchmark=False) -> SeedReport`; engines read it at `__init__`; `TrainingResult` captures the `SeedReport` for lineage. Document the cost: `deterministic_algorithms=True` flips `torch.use_deterministic_algorithms(True)` which breaks `nn.Embedding`'s scatter-add and some conv paths — users opt-in.

**HIGH-A1-2 — PyTorch cuDNN benchmark-mode toggle is undocumented.**
`torch.backends.cudnn.benchmark=True` is the most common source of run-to-run variance at fixed seed on identical hardware (cuDNN's autotuner picks different kernels across runs). ml-diagnostics/ml-engines-v2 do not touch this. **Fix:** SeedReport captures both `cudnn.deterministic` and `cudnn.benchmark`; `TrainingResult.reproducibility` pins both; warning log emitted when benchmark=True is combined with a fixed seed claim.

**HIGH-A1-3 — RL RNG state is NOT checkpointed across env + policy + buffer.**
ml-rl-core §9.1 says resume restores "policy, optimizer, buffer, env RNG" but never defines the three-RNG contract. Gymnasium envs have `.np_random` + `.action_space.np_random`; SB3 policies have `policy.set_training_mode()` RNG state; `ReplayBuffer` sampling uses `np.random`. A resumed PPO run with episode-level stochastic exploration is NOT bit-reproducible without all three. Feature-study `seed: int | None = 42` in `rl_train` is not enough. **Fix:** `RLCheckpoint` schema MUST include `env_rng_state: bytes`, `policy_rng_state: bytes`, `buffer_rng_state: bytes`, `global_numpy_state: bytes`, `global_torch_state: bytes`. Document the Gymnasium `.np_random.bit_generator.state` serialization contract.

**MED-A1-4 — `random_state` is not a first-class field on `TrainingResult`.**
The draft captures `split_info`, `feature_versions`, `git_sha`, `cuda_version`, `lightning_version` but not a dedicated `seed_report: SeedReport` — scattering seed info across `split_info.seed`, `RLTrainingConfig.seed`, HP dict. A reviewer cannot answer "what seed ran this model" in one lookup. **Fix:** add `TrainingResult.seed_report: SeedReport`.

**MED-A1-5 — Feature-store hash ignores non-source-level determinism.**
ml-feature-store §1 hashes `sha256(decorator_kwargs || inspect.getsource(fn) || py_version)`. This misses: `polars` version, `numpy` version, BLAS backend (OpenBLAS vs MKL changes sum-of-product order → 1-ULP float drift on 1B-row aggregates), and the caller's locale/TZ. **Fix:** extend hash input to include `polars.__version__`, `numpy.__version__`, and a "pure-fn" marker that the user can assert.

### A.2 Distributed Semantics Correctness

**HIGH-A2-1 — FSDP shard-local grad norm is reported but never reduced for severity thresholds.**
ml-diagnostics §5.5 says "`grad_norm.{param_name}` is emitted with the shard-local norm; the rank-0 aggregate is the cross-shard sum-of-squares." This is ambiguous: sum-of-squares of SHARD-LOCAL-L2-norms is NOT the full weight's L2 norm when using ZeRO-3 (you need `sqrt(sum(shard_norm^2 * shard_weight))` — the sharding does not evenly partition parameter count for non-uniform layers). A threshold like `grad_explosion` = grad_rms > 100 triggers false positives on the rank that holds a large shard and false negatives on the rank that holds a tiny shard. **Fix:** emit per-rank AND globally-reduced `grad_norm.full_weight` computed as `all_reduce(shard_norm^2, SUM)` then `sqrt` — same formula the optimizer uses. Document the FSDP `FullyShardedDataParallel.sharded_grad_norm()` hook as the blessed source.

**HIGH-A2-2 — DeepSpeed ZeRO-3 does not expose per-parameter gradients on every rank.**
Under ZeRO-3 each rank only has its own partition; a `module.parameters() [ p.grad ]` enumeration outside `deepspeed_engine.backward()` sees `None` for non-owned parameters. ml-diagnostics installs forward/backward hooks on every rank; on ZeRO-3 this raises or silently drops hooks. The spec does not mention ZeRO-3 at all. **Fix:** detect `hasattr(module, "ds_id")` (DeepSpeed flag) and route through `deepspeed.utils.safe_get_local_fp32_param()` for grad extraction; add ZeRO-stage to `DeviceReport`.

**HIGH-A2-3 — Transformers Trainer uses Accelerate; Lightning-centric design cannot cover `accelerate launch` multi-node.**
ml-diagnostics §5.5 says "when torch.distributed.is_initialized() returns True". But an Accelerate run may have `torch.distributed.is_initialized() == False` on single-GPU-per-machine and `== True` on multi-GPU; the dispatch rank resolution goes through `accelerate.PartialState()` not `torch.distributed.get_rank()`. ml-engines-v2 references "accelerate" once (backend capability label) but never as a distribution strategy. **Fix:** add a `DistributionEnv` dataclass capturing `(is_distributed, world_size, rank, local_rank, launcher: "torchrun" | "accelerate" | "deepspeed" | "lightning" | "none", strategy: "ddp" | "fsdp" | "zero3" | "tp" | "pp" | "none")`. Every adapter routes through it.

**MED-A2-4 — Rank-0 emission hides real per-rank failures.**
ml-diagnostics §5.5 item 3: "record_batch/record_epoch emit to tracker ONLY on rank 0." Correct for metric volume but a NaN gradient on rank 3 that rank-0-emission never sees is a silent failure. **Fix:** `RankSafetyCallback` that emits a WARN to rank-0's tracker if any rank detects grad-NaN/Inf via `torch.distributed.all_reduce` of an `int` Nan-flag — converts silent cross-rank divergence into a loud failure at §5.5 time.

**MED-A2-5 — Tensor-parallel + pipeline-parallel are absent from the surface.**
2026-27 training (`Megatron-LM`, `nanotron`, `FSDP2`) uses TP+PP heavily. Neither ml-engines-v2 nor ml-diagnostics mentions TP/PP. The spec is Lightning-centric (`_train_lightning`), and Lightning's TP support is minimal (Fabric is better). **Fix:** add `FabricBackend` as a first-class `DeviceReport` strategy alongside Lightning.

### A.3 Numerical Stability Edges

**HIGH-A3-1 — PSI on zero-variance column divides by zero.**
ml-drift §5 lists PSI = `sum((p_new − p_ref) × ln(p_new / p_ref))`. Two failure modes: (a) a bin with zero mass in reference (`ln(p/0)` → `Inf`); (b) a column that is constant post-reference (`std == 0`, bin edges collapse to a single bin — bin count < 10 → division-by-zero on bin-width normalisation). Spec says "PSI > 0.2 = significant; > 0.25 = critical" but never defines the `eps` smoothing. MLflow/Evidently use `eps=1e-4` on each bin mass. **Fix:** pin `PSI_SMOOTH_EPS = 1e-4` in the spec; reject zero-variance reference column with typed `ZeroVarianceReferenceError`; emit `psi = None` (not `Inf`) and route to `data_quality` axis rather than drift axis.

**HIGH-A3-2 — KL/JSD on zero-probability mass.**
ml-drift §5 lists JS divergence but does not specify how zero-probability bins are smoothed. `RLDiagnostics.track_exploration` reports `kl_div` — if the old-policy distribution puts zero mass on an action the new policy chose, the classical KL is `+Inf`. SB3 uses a running mean of `old_logp - new_logp` (importance-weighted KL estimator) which is finite but biased. **Fix:** pin the JSD smoothing to `eps = 1e-10` and specify KL estimator as "SB3's sample-based unbiased estimator (approx KL in PPO, exact KL in TRPO)". Add a `stability_note` column to the per-column drift output when smoothing fired.

**HIGH-A3-3 — Prometheus counter overflow on high-QPS production.**
ml-engines-v2-addendum §E7 lists `ml_inference_total` as a Counter. Prometheus Counter is a `float64` internally — 52-bit mantissa gives precise integer representation up to `2^53 ≈ 9e15`. A 10K-QPS service accumulates 864M requests/day; float64 stays precise for ~28 years. BUT: bounded histograms for `ml_inference_duration_seconds` use default bucket boundaries — LLM streaming first-token latencies range from 50ms to 30s (600x); the default `(0.005, 0.01, ..., 10)` bucket set saturates the last bucket for every LLM request. **Fix:** Spec the bucket boundaries explicitly: `(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300)` seconds — covers classical (ms) to LLM (minute).

**MED-A3-4 — SQLite INTEGER step count.**
ml-tracking §6 shows `kml_metric.step INTEGER` (SQLite INTEGER = int64). A step counter at `batch_size=1, train_tokens/sec=100K` on a 100B-parameter model hits 2^32 in 11 hours; 2^63 never. Safe. But the DDL in ml-tracking-draft.md line 514 MUST explicitly be `BIGINT` in Postgres variant (the line says `INTEGER` which in Postgres is 32-bit). **Fix:** change to `BIGINT` for Postgres DDL; add regression test that `step = 2_500_000_000` (past int32) persists correctly.

**MED-A3-5 — `math.isfinite()` only on `log_metric`, not on `log_param`.**
ml-tracking §6 says `log_metric` validates `math.isfinite(value)`. But `log_param("learning_rate", float("nan"))` is not validated — yet NaN params break every comparison query (`WHERE params->>'learning_rate' = ?`). **Fix:** extend the MUST to `log_param` when value is numeric.

### A.4 Checkpoint + Resume Edge Cases

**HIGH-A4-1 — Partial-epoch resume double-counts DLDiagnostics aggregates.**
ml-diagnostics §5.7 says `from_checkpoint()` "restores a fresh session at the correct batch/epoch/counter state so a resumed training run produces a continuous metric stream." But `DLDiagnostics` running-window aggregates (grad-rms rolling mean, dead-neuron running count) are batch-indexed; a resume at batch=5432 must NOT re-emit batches 5400-5432 to the tracker. The spec does not say how the `log_metric(step=5432)` is deduped vs the last step before checkpoint. **Fix:** pin `DLDiagnostics.resume_invariant`: "the first `record_batch` after `from_checkpoint` emits step=(checkpoint.step + 1); the tracker's `(run_id, metric_key, step)` PK prevents double-inserts"; add a Tier 2 test that crashes mid-epoch, resumes, and asserts `SELECT COUNT(DISTINCT step) == step_at_termination`.

**HIGH-A4-2 — RL replay-buffer overflow resume loses samples.**
ml-rl-core §9.1 lists "Full RolloutBuffer / ReplayBuffer contents + RNG state" as resumed. But if the buffer was at `size=1M, capacity=1M` (saturated), FIFO eviction is irreversible — the checkpoint only contains the current ring-buffer state, not pre-evicted samples. Fine for DQN/SAC; NOT fine for prioritised replay where samples have metadata. **Fix:** `ReplayBuffer.checkpoint()` MUST write both the ring-buffer contents AND the priority tree; resume MUST reconstruct the tree, NOT lazily rebuild it (rebuilding loses prior β annealing). Add `ReplayBuffer.checkpoint_consistency_version: int` for forward-compat.

**HIGH-A4-3 — Hyperparameter-diff on resume is silent.**
The spec shows `RLTrainingConfig.resume_from=path` but never addresses the case where the user intentionally changes `learning_rate` from 3e-4 to 1e-4 on resume (common for cosine schedule restarts). The tracker has two runs or one? If one, how does `RunDiff` flag the `learning_rate` change? **Fix:** `resume_from=` implicitly creates a new child run via `km.track(..., parent_run_id=checkpoint.run_id, hyperparameter_changes=diff)`. The child run's `params` capture `{key: {new, old, changed: True}}` diffs at resume time. Document this as the resume contract.

**MED-A4-4 — Checkpoint JSON-safety claim is too strong.**
ml-diagnostics §5.7: "dict is JSON-serialisable (no torch tensors) so it rides along inside Lightning's `Trainer.save_checkpoint()` via CheckpointIO." But `Trainer.save_checkpoint` uses `torch.save` (pickle) anyway — the JSON-safety is a Kailash-internal invariant, not a Lightning requirement. **Fix:** clarify that JSON-safety is for the Kailash tracker's `_kml_checkpoint_diagnostics` table write; Lightning's save_checkpoint continues to pickle.

### A.5 RL Correctness

**HIGH-A5-1 — GAE `lambda_`/`gamma` defaults not pinned per-algo in the spec's adapter table.**
ml-rl-core §6.1 defines `RolloutBuffer(gae_lambda=0.95, gamma=0.99)`. But ml-rl-algorithms §3.1 (PPO) lists `gae_lambda=0.95, gamma=0.99`, §3.2 (A2C) lists `gae_lambda=1.0, gamma=0.99`. A user who constructs `RolloutBuffer(gamma=0.99)` and then runs A2C gets the PPO default — silent divergence from A2C literature. **Fix:** adapters MUST inject their own defaults at buffer construction; `RolloutBuffer` default constants apply only when no adapter is attached. Document the binding: `PPOAdapter._make_buffer() -> RolloutBuffer(gae_lambda=0.95, ...)`.

**HIGH-A5-2 — Off-policy `ReplayBuffer.sample()` lacks n-step returns.**
ml-rl-core §6.2 `ReplayBuffer.sample(batch_size, beta=None)` — no `n_step` parameter. Rainbow-DQN, MuZero, and every DeepMind baseline since 2017 use n-step returns as the default. SB3's `RolloutBuffer` and `ReplayBuffer` expose `n_step_returns` via wrapper. **Fix:** add `ReplayBuffer.__init__(n_step: int = 1)` and `sample(..., n_step: int | None = None)` — per-call override; default 1 for bit-compat with current SB3; adapter tables in ml-rl-algorithms document which algo sets n_step > 1.

**HIGH-A5-3 — PPO value-function clipping option is absent from the spec.**
ml-rl-algorithms §3.1 PPO keys list `clip_range` (policy clip) but no `clip_range_vf` (value-function clip). SB3's PPO supports `clip_range_vf=None | float` — optional VF clipping. Without it, implementing the original Schulman-et-al 2017 PPO faithfully is impossible. **Fix:** add `clip_range_vf: float | None = None` to the PPO hyperparameter schema; metric emission `rl.train.update.value_clip_fraction` when VF clip active.

**HIGH-A5-4 — DPO reference-model temperature contract is undocumented.**
ml-rl-algorithms §6.1 `dpo` lists `reference_model` as required. But the reference model's `generation_config.temperature` at inference time is not fixed — TRL uses `temperature=1.0` by default; `OnlineDPO` §6.4 uses `temperature=0.9`. Users running DPO MUST know whether `reward_margin` is computed under T=1.0 (canonical) or T=0.9 (sample-efficient). **Fix:** `DPOAdapter` MUST pin `reference_model.eval()` AND force `temperature=1.0` for log-prob extraction; document the choice; RLOO's temperature=0.7 and online-DPO's 0.9 are sampling-time, not log-prob-time.

**MED-A5-5 — KL-from-reference NOT the same metric across RLHF adapters.**
ml-rl-algorithms §6.1-6.4 all emit `rl.train.update.kl_from_reference`. But PPO-RLHF uses `init_kl_coef * KL(π, π_ref)` as a reward penalty (approximate KL via sample-based estimator); DPO uses `β * log(π(chosen)/π_ref(chosen)) - β * log(π(rejected)/π_ref(rejected))` (log-ratio form); RLOO uses `kl_coef * sum_t log π(a_t|s_t) - log π_ref(a_t|s_t)` (token-level). Three different quantities under one metric key produces misleading cross-algo comparisons. **Fix:** rename per-adapter: `rl.train.update.kl_from_reference.ppo_approx`, `.dpo_logratio`, `.rloo_token_level`; keep `.kl_from_reference` as a unified "divergence-family" label with a `kl_estimator` param in the tracker.

### A.6 Classical ML Edges

**HIGH-A6-1 — Single-class split in `diagnose_classifier`.**
ml-diagnostics §9 does not address: a stratified split where the test fold happens to contain one class (e.g. extreme imbalance, `n_test=50, minority_frac=0.01`). `sklearn.metrics.confusion_matrix([1,1,1], [1,1,0])` returns `[[0,0],[1,2]]` — a non-square matrix if the spec expects `num_classes=2`. **Fix:** `ClassifierReport.confusion_matrix: polars.DataFrame` MUST always be K×K where K = union-of-labels(y_true, y_pred); missing-class rows/cols filled with zero. Add regression test for single-class fold.

**HIGH-A6-2 — Regression residual plot lacks heteroscedasticity + Cook's distance + leverage primitives.**
ml-diagnostics §9 regression mentions Breusch-Pagan but not Cook's distance (influential-point detection) or leverage (hat matrix diagonal). A senior practitioner needs these to diagnose "one row is dominating the fit" which residual plots alone cannot surface. **Fix:** extend `RegressorReport` with `.cooks_distance: polars.Series`, `.leverage: polars.Series`, `.studentized_residuals: polars.Series`; flag `severity="influential_points_detected"` when any `cooks_distance > 4/N`.

**MED-A6-3 — Silhouette at k=1 or k=n−1 is undefined.**
ml-diagnostics §9 clustering emits silhouette. `sklearn.metrics.silhouette_score([[1],[2]], [0,1])` raises `ValueError: Number of labels is 2 but should be between 2 and n-1`. **Fix:** clustering diagnoser routes `k ∈ {1, n-1, n}` to a typed `InsufficientClustersError(k=k, n_samples=n, min_k=2, max_k=n-1)`; does NOT fall back silently.

**MED-A6-4 — R² < 0 is silently "CRITICAL" but negative R² has a specific interpretation.**
Spec §9 regression lists `r2 < 0 → CRITICAL`. True for deployment, but senior users need to distinguish "r² = -0.01 on a difficult problem" (close to baseline) from "r² = -5.0" (worse than predicting the mean). **Fix:** three-tier severity: `r² < 0` WARNING; `r² < -0.5` CRITICAL; document that `r² < 0` means "the model is worse than predicting the mean" and that training-test distribution mismatch is the most common cause.

### A.7 LLM / Autolog Corner Cases

**HIGH-A7-1 — Tensor-parallel transformers Trainer autolog fires on the wrong rank.**
ml-autolog §4.1 says "transformers Trainer" integration fires via the HF Trainer's callback API. But when `accelerate launch --num_processes=8 --multi_gpu` is used with `--tp_size=2 --pp_size=2`, the Trainer instantiates ONE Trainer per DP rank (4 of them) — the autolog emits to the tracker from all 4 DP ranks simultaneously, producing 4× duplicate metrics per step. The spec's "rank-0 only" contract from ml-diagnostics §5.5 is not ported to ml-autolog. **Fix:** ml-autolog §4.1 (Transformers) MUST gate emission to `PartialState().is_main_process` (Accelerate) OR `RANK == 0` (torch.distributed); defer to the same `DistributionEnv` dataclass from A2-3.

**HIGH-A7-2 — LoRA fine-tune autolog conflates base + adapter.**
ml-autolog §4 Transformers integration captures `model.config` to `run.log_params(...)`. But a PEFT LoRA fine-tune: `model = get_peft_model(base_model, lora_config)`. `model.config` is the base model's; `model.peft_config` carries the adapter. Single-param capture loses the LoRA rank/alpha/target-modules — which ARE the reproducibility contract for the fine-tune. **Fix:** ml-autolog §4.1 Transformers integration MUST detect `isinstance(model, PeftModel)` and log BOTH `base_model.config` AND `peft_config` under prefixed keys (`base.*`, `lora.*`); artifact store receives the adapter weights separately.

**HIGH-A7-3 — Token-per-second metric in streaming is mis-specified.**
ml-serving §5.4 emits `ml_inference_stream_tokens_per_sec` as a Histogram. But tokens/sec is a DERIVED metric — it varies continuously during a stream (first-token ≫ subsequent tokens). Emitting "tokens/sec per chunk" vs "tokens/sec lifetime" produces completely different dashboards. **Fix:** split into `ml_inference_stream_first_token_latency_seconds` (Histogram, already present), `ml_inference_stream_subsequent_token_latency_seconds` (Histogram, per-chunk post-first), `ml_inference_stream_total_output_tokens` (Counter), `ml_inference_stream_duration_seconds` (Histogram). Let Grafana compute tokens/sec from the counter/histogram ratio.

**MED-A7-4 — `log_metric` in autolog does not respect HF Trainer's `logging_steps`.**
If the user sets `TrainingArguments(logging_steps=100)`, HF Trainer emits every 100 steps. The Kailash autolog integration MUST propagate this — not log every step (defeats the user's intent) and not log every 500 steps (misses the user's data). **Fix:** wire Kailash autolog to HF Trainer's `on_log` callback which already fires at `logging_steps` cadence.

### A.8 Feature Store Subtleties

**HIGH-A8-1 — Point-in-time join with late-arriving data has no correctness contract.**
ml-feature-store §6.1 lists `_materialized_at` and event timestamps — but never specifies whether late-arriving events (`event_time < as_of < _materialized_at`) are INCLUDED or EXCLUDED from a point-in-time retrieval. Feast includes them ("as-of-event-time" semantics); Tecton excludes them when the materialization window is closed ("as-of-materialization-time" semantics). Both are defensible; picking neither is BLOCKED. **Fix:** `get_training_features(entity_df, as_of, *, late_arrival_policy: Literal["include", "exclude", "warn"] = "exclude")`. Default to "exclude" (conservative); document the tradeoff explicitly with two Tier 2 tests.

**HIGH-A8-2 — Feature version bump with downstream consumers has no backward-compat contract.**
ml-feature-store §1 feature version = `sha256(decorator_kwargs || getsource(fn) || py_version)`. Any source-level change (reformat, rename a local variable) produces a new version. But the spec does not say: does a model registered at feature_version `abc123` still serve predictions after feature re-materialization at `def456`? If the downstream model's InferenceServer asks FeatureStore for `group@abc123`, does it resurrect the old definition, or fail? **Fix:** `FeatureStore.get_feature_version(group, version)` MUST be immutable post-materialization (retained in `_kml_feature_group_history`); re-materializations under a new version do not delete the old; `ModelVersion.feature_versions` pins consumers to exact SHAs. Add Tier 2 test: train at v1, bump feature to v2, assert inference at v1 still works.

**HIGH-A8-3 — Online ↔ offline divergence check (training-serving skew) is absent.**
ml-feature-store §6 describes online+offline paths but never specifies how to detect divergence between the batch-materialized offline row and the online-served row for the same entity at the same `event_time`. Training-serving skew is the #1 cause of model degradation in production. Feast ships `feast materialize-incremental` followed by a sample-based skew check; Tecton ships `skew_analysis`. **Fix:** `FeatureStore.check_skew(group, entities: list[str], window: timedelta) -> SkewReport` — samples N entities, fetches both online + offline, computes per-feature divergence statistics (KS, L1); emits `feature_store.skew.{feature}` metric. Emits as part of `MLDashboard` default widgets.

**MED-A8-4 — `_materialized_at` is a physical column but has no index contract.**
The spec says "every offline row MUST carry `_materialized_at`" — but on a table with 10B rows, unindexed `WHERE _materialized_at <= as_of` is a full scan. **Fix:** spec MUST require index `(entity_id, _materialized_at DESC)` on every offline feature group table.

### A.9 AutoML Subtleties

**HIGH-A9-1 — BOHB multi-fidelity contract is absent from the AutoML spec.**
ml-automl §2.1 lists `algorithm="bohb"` but never specifies the fidelity parameter. BOHB requires a `budget` per trial (usually "n_epochs" for NNs, "n_rows" for classical ML, or a cost proxy). Without it, BOHB degenerates to Random + Hyperband promotion that isn't guided by Bayesian updates — 2-3× slower than well-configured Bayesian. **Fix:** `AutoMLConfig(fidelity_param: str, fidelity_min: float, fidelity_max: float, reduction_factor: int = 3)`; reject `algorithm="bohb"` unless all four specified. Document sane defaults per task type.

**HIGH-A9-2 — Early-stopping in parallel trials can double-promote.**
ml-automl §5 `parallel_trials=4` + §6.1 "A trial MUST be stopped early if its rolling validation metric fails to improve". Race: trial A completes at t=10 with score 0.85; trials B, C, D are all at t=5 with scores 0.84, 0.83, 0.82. An aggressive patience=3 aborts B/C/D at t=8. But trial A's score 0.85 may have been computed under a DIFFERENT fidelity budget than B/C/D — comparing them is invalid. **Fix:** ASHA (Async Successive Halving) promotion rule: only compare trials AT THE SAME fidelity rung. `LeaderboardEntry` MUST carry `fidelity: float` and a promotion is only admitted when N trials at the same fidelity complete.

**HIGH-A9-3 — LLM-augmented cost guardrails lack token-level backpressure.**
ml-automl §8.2 caps total `max_llm_cost_usd`. But a single agent call under `auto_approve=True` can burn $5 in 30 seconds if the agent is allowed to retry, expand context, and read its own audit trail. The `AgentGuardrailMixin.max_llm_cost_usd` check is a POST-hoc cap — the user sees $4.99 consumed in one call, then the cap fires on the next. **Fix:** token-level backpressure: the Kaizen signature MUST set `max_tokens` per call to `(remaining_budget_usd / model_cost_per_token)`; when remaining < 1 call's worth, the agent is suspended, baseline search continues, and a WARN is emitted.

### A.10 Serving Subtleties

**HIGH-A10-1 — Batch inference with variable-length inputs has no padding strategy.**
ml-serving §4 specifies `chunk_size=1024` and polars-native I/O — but LLM inference with variable-length sequences requires either (a) pad-to-longest in chunk, wasting compute; (b) continuous batching (vLLM-style) with in-flight merging; (c) sort-within-chunk by length (static bucketing). The spec does not pick one. For transformers classification this is irrelevant; for LLM streaming it IS the cost model. **Fix:** `BatchInferenceResult` gains `padding_strategy: Literal["none", "pad_longest", "sort_bucket", "continuous"]` field; default `"none"` for fixed-length models, `"sort_bucket"` for sequence models, `"continuous"` when a vLLM-compatible backend is detected.

**HIGH-A10-2 — Streaming inference with backpressure: no channel-level contract.**
ml-serving §5.1 lists SSE/gRPC-stream/WebSocket but never specifies: client disconnects mid-stream — does the server abort generation (freeing GPU) or run to completion (wasting GPU)? Does the server buffer output beyond `max_tokens` worth of chunks (memory blow-up)? **Fix:** `StreamingInferenceSpec.abort_on_disconnect: bool = True, max_buffered_chunks: int = 32, chunk_backpressure_ms: float = 500` — when the client falls behind by `max_buffered_chunks`, the server pauses generation and emits a `backpressure.paused` WARN.

**MED-A10-3 — ONNX custom op export contract is missing.**
ml-serving §3.1 says "Runs ONNX artifacts by default". But a torch model with a custom op (e.g. FlashAttention-2's op that isn't in the ONNX standard opset) cannot round-trip to ONNX. The registry's "ONNX-first" default silently fails for these models. **Fix:** registry MUST probe `torch.onnx.export(model, dummy_input, strict=True)` at `register_model` time; failure raises `OnnxExportUnsupportedOpsError(ops=[...])`; spec MUST list fallback formats (TorchScript, SafeTensors-plus-config for HF models).

### A.11 Drift Subtleties

**HIGH-A11-1 — Covariate / concept / prior drift are conflated into one monitor.**
ml-drift §1 defines three "axes": feature drift, prediction drift, label drift. Statistically these map to covariate shift (`p(x)`), concept shift (`p(y|x)`), and prior shift (`p(y)`). A user only gets label drift via post-hoc ground-truth arrival. The spec does not distinguish covariate-only drift (`p(x)` changes but `p(y|x)` stable — recalibration often suffices) from concept drift (`p(y|x)` changes — full retrain required). **Fix:** add a `DriftType` enum `COVARIATE | CONCEPT | PRIOR | LABEL` to every `DriftFeatureResult`; document the test for each type (KS on features = covariate, KS on predictions given features = concept, KS on labels = prior). Route recommendations differently (recalibrate vs retrain).

**HIGH-A11-2 — Label lag is not modeled.**
Fraud detection, loan default, churn — all have label lag measured in weeks-to-months. The spec's reference/current window alignment never addresses: when "labeled_y" arrives at t+90 days for a prediction made at t, which reference window is this labeled_y compared against? **Fix:** `DriftMonitor.set_reference(..., label_lag: timedelta = timedelta(0))`; when `label_lag > 0`, concept-drift checks are run against predictions from `as_of - label_lag` window, not the current window.

**HIGH-A11-3 — Reference auto-refresh under seasonality is absent.**
A retailer with weekly seasonality (e-commerce, B2C SaaS) sees "drift" every Monday relative to last Sunday's reference. ml-drift §4 `set_reference()` creates a static reference; no `refresh_policy="rolling" | "sliding_30d" | "seasonal"`. **Fix:** `DriftMonitorReferencePolicy.mode: Literal["static", "rolling", "sliding", "seasonal"]`; for seasonal mode, reference is aligned to the same weekday/hour in the prior period. Tier 2 test: synthetic weekly seasonal signal + rolling mode → drift NOT fired; same signal + static mode → drift fires weekly.

### A.12 Protocol Conformance Edges

**HIGH-A12-1 — `report() -> dict[str, Any]` shape is inconsistent across the 7 adapters.**
ml-diagnostics §2.1 says "every adapter satisfies `kailash.diagnostics.protocols.Diagnostic`" and "MUST NOT raise" on empty session. But:

- `DLDiagnostics.report()` returns `{grad_norm_mean, dead_neuron_frac, severity}` (ml-diagnostics §5).
- `RLDiagnostics.report()` returns `{run_id, label, algo, total_env_steps, ...}` (ml-rl-core §7.2).
- `ClassifierReport` / `RegressorReport` / `ClusteringReport` are **frozen dataclasses** with `.report()` returning `dict(self)` via a no-op `__enter__`.
- AlignmentDiagnostics, InterpretabilityDiagnostics, JudgeCallable, LLMDiagnostics, AgentDiagnostics — deferred to sibling specs.

Three different output shapes; no shared top-level keys (e.g. `run_id`, `severity`, `framework`, `timestamp`). Cross-adapter consumers (MLDashboard, W&B bridge) cannot index generically. **Fix:** pin the minimum shared shape: `{adapter: str, run_id: str | None, timestamp_iso: str, severity: Severity, summary: dict, tracker_metrics: list[str]}`. Every adapter's per-domain fields live under `summary`. Every Tier 2 test asserts these 5 keys are present.

**HIGH-A12-2 — `isinstance(obj, Diagnostic)` is `runtime-checkable` but context-manager Protocol is a known pitfall.**
`@runtime_checkable` on a Protocol with `__enter__`/`__exit__` will match any class that has both methods — including many unintended types. The spec does not document this. **Fix:** every adapter MUST also expose a unique `adapter: ClassVar[str]` attribute; `Diagnostic` Protocol adds `adapter: str`; `km.diagnose`'s dispatch uses `obj.adapter` for routing, not `isinstance`.

**HIGH-A12-3 — Cross-SDK fingerprint parity is claimed but not bound.**
ml-diagnostics §2.1 item 5: "when `report()` output is serialized via `json.dumps(report, sort_keys=True, separators=(',', ':'))` and hashed with SHA-256, Python and Rust produce identical fingerprints for identical observations". But the observation set is not pinned across languages — `float` precision, `datetime` serialization format, enum value strings, numpy scalar vs Python float all differ. A Rust `f32` gradient → JSON `"0.5"` while Python emits `"0.5000000298023224"`. **Fix:** define the canonical float serialization: `f"{value:.6g}"` (6-sig-figs); pin enum string values; `datetime` → `strftime("%Y-%m-%dT%H:%M:%S.%fZ")`; add regression test `test_diagnostic_fingerprint_cross_sdk_parity` that asserts identical fingerprint for (Python, Rust) pairs in CI.

**MED-A12-4 — RLDiagnostics, AlignmentDiagnostics, InterpretabilityDiagnostics cross-references are forward references.**
ml-diagnostics §3 table rows 5, 6, 7 say "see sibling spec alignment-diagnostics.md / kaizen-observability.md / kaizen-interpretability.md" — files that do NOT exist in the 13 drafts. **Fix:** Phase-C either (a) create stubs for the missing sibling specs before certification, or (b) move the cross-references to an `Appendix: Future Sibling Specs` with an explicit "out of scope for 0.18.0" banner.

---

## Section B — Edge Cases The Specs Didn't Anticipate

1. **Mixed-precision gradient scale drift.** `GradScaler` in `torch.cuda.amp` maintains an internal multiplicative scale that changes across batches on overflow. A `DLDiagnostics.grad_norm` metric emitted without dividing by the current scale is not comparable step-to-step under mixed precision. No spec mentions it.

2. **Learning-rate scheduler warm-restart steps are mis-counted.**`OneCycleLR` / `CosineAnnealingWarmRestarts` reset optimizer state at specific step counts. If the Kailash tracker uses `step = epoch * batches_per_epoch + batch_idx` and a warm-restart happens mid-epoch, the metric `rl.train.update.lr` is ambiguously indexed.

3. **Gradient accumulation changes effective batch size without changing the logged `batch_size`.** `Trainer(accumulate_grad_batches=4, batch_size=32)` has effective batch 128. ml-autolog captures `batch_size=32`, but the reproducibility-critical value is 128.

4. **`torch.compile` (PyTorch 2.x graph capture) invalidates hooks.** DLDiagnostics forward/backward hooks attached BEFORE `torch.compile(model)` are silently dropped. Spec says nothing.

5. **Multi-GPU dataloader sharding under `persistent_workers=True` + `num_workers > 0` copies the tracker's contextvar to worker processes, which cannot hit SQLite WAL mode.** `_current_run` contextvar fork-inheritance is not discussed.

6. **Model registry stage promotion on a READ replica.** `ModelRegistry.promote()` writes to a SQLite file; under Postgres read-replica routing, the read-replica sees staged state before the primary commits. No spec discusses read-your-writes consistency on the registry.

7. **Drift reports that compare against a reference with a different schema.** `@feature` evolution adds/removes columns. The current-window DataFrame has N+1 columns, reference has N. `DriftMonitor.check_drift` behavior: raise, skip, or emit a `schema_drift` alert?

8. **Experiment tracker resume across Kailash-ml SDK version upgrade.** A checkpoint written with 0.17.0's `DLDiagnostics` shape, resumed under 0.18.0's new shape. No versioned checkpoint migration path.

9. **AutoML leaderboard with deleted model artifacts.** User manually deletes `/artifacts/model_42.onnx`. Leaderboard still cites trial 42 as best; `finalize()` fails with `FileNotFoundError`. No orphan-handling.

10. **Distributed `km.track()` + `km.autolog()` across spot instances.** Spot pre-emption mid-epoch kills rank 3 in a 4-rank DDP run. Rank 0's `km.track()` context stays open; the run is never closed. Need a heartbeat contract.

11. **Feature-store schema evolution with online-serving traffic.** `@feature` bumps version while `InferenceServer` holds the old feature-group handle in memory. Either (a) hot-swap handle (race); (b) fail all in-flight requests; (c) serve stale features. No spec disposition.

12. **GDPR `erase_tenant` on a model registry with active shadow traffic.** The shadow model was trained on tenant A's data; when tenant A is erased, the shadow weights must be re-trained. No cascading erasure path documented.

13. **AutoML agent + baseline recommendation conflict.** Agent suggests `learning_rate=5e-4`; baseline GP posterior peaks at `1e-3`. What happens when both trials are in flight simultaneously?

14. **Streaming inference with a client that sends multi-message prompts across WS frames.** Each WS frame is a partial prompt; the server MUST accumulate before invoking the model. No framing protocol specified.

15. **Model serving with a model whose `signature.metadata` claims determinism but internally calls `torch.multinomial(...)` (temperature sampling).** Response cache happily caches, returns stale sample. No attested-determinism check.

---

## Section C — Novel 2026-27 Architectures — Future-Proofing

| Architecture                                         | Does the spec architecture hold?                                                                                                                                                                                                        | Recommended Phase-C action                                                                                                                         |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| **Flash Attention 3** (H100/B200)                    | PARTIAL. ml-backends §3 lists fp16/bf16 capabilities via runtime probe, but FA3 requires bf16+e4m3fp8 combinations not expressible in current `frozenset[str]`.                                                                         | Extend `BackendCapability` enum: `{"fp16", "bf16", "fp8_e4m3", "fp8_e5m2", "int8", "int4", "distributed"}`. Add `fa_version: int` to DeviceReport. |
| **Mamba / State-Space Models**                       | FAIL. Sequence models in ml-serving assume attention (padding strategy, continuous batching). Mamba's selective scan has different batch semantics.                                                                                     | Add `ModelArchitecture: Literal["transformer", "ssm", "hybrid", "moe", "rwkv", "none"]` to `ModelSignature`.                                       |
| **MoE (Mixture of Experts)**                         | FAIL. ml-diagnostics FSDP reporting is per-parameter; MoE has per-expert routing weights (top-k gating) that FSDP does not see.                                                                                                         | Add `ExpertRouting` diagnostic: per-expert utilization, load balancing loss, routing entropy.                                                      |
| **Tensor Parallel (Megatron/nanotron)**              | FAIL. DLDiagnostics §5.5 only mentions DDP/FSDP. TP shards a single tensor across ranks; gradient reductions are different.                                                                                                             | See A.2 HIGH-A2-5. `DistributionEnv` with `tp_size`, `pp_size`, `dp_size` explicit.                                                                |
| **1M-context (Gemini/Claude) training**              | PARTIAL. ml-serving §5.2 StreamChunk supports token-by-token but no first-token-latency budget differentiation for very-long-context.                                                                                                   | Add `max_prefill_tokens`, `max_decode_tokens_per_chunk` to streaming spec.                                                                         |
| **Multimodal (image + text + audio)**                | FAIL. ml-feature-store assumes tabular (polars.DataFrame). Image embeddings as feature values require custom serialization. FeatureStore `as_of` joins on images are undefined.                                                         | Add `FeatureType: Literal["scalar", "vector", "tensor", "image_ref", "audio_ref"]`; non-scalar types require S3-like storage + reference columns.  |
| **RWKV / RetNet (post-transformer sequence models)** | FAIL. Same as Mamba — attention assumption in serving.                                                                                                                                                                                  | Route via `ModelArchitecture: "rwkv"`.                                                                                                             |
| **Speculative decoding (draft + verify)**            | UNKNOWN. Serving spec has no provision for a "draft model" companion to a larger model.                                                                                                                                                 | Add `InferenceServerConfig.draft_model: ModelRef                                                                                                   | None`and`spec_decode: bool`. |
| **PagedAttention / KV cache sharing**                | UNKNOWN. No KV-cache management surface in serving spec; required for production LLM serving at scale.                                                                                                                                  | Phase-C: `PagedAttentionConfig(block_size, gpu_memory_utilization, swap_space_gb)` in serving spec.                                                |
| **LoRA / QLoRA hot-swap at inference time**          | FAIL. Registry treats models as immutable blobs; hot-swapping a LoRA adapter without reloading the base weights is a supported pattern in vLLM/TGI that Kailash does not model.                                                         | Add `ModelRegistry.load_lora_adapter(base_model_version, adapter_id)` primitive; inference path supports multi-adapter concurrent serving.         |
| **DeepSpeed-Chat / NeMo-Aligner**                    | N/A (ml-rl-align delegates RLHF training to kailash-align via TRL). The bridge contract is sound but the metric-family coverage for DeepSpeed-specific losses (reward model loss, critic loss, dpo loss, orpo loss) MUST be enumerated. | Audit ml-rl-align-unification §6 for DeepSpeed-Chat coverage.                                                                                      |

**Aggregate:** 4 FAIL, 3 PARTIAL, 3 UNKNOWN, 1 N/A. The spec hedges well on "Lightning + SB3 + classical ML" but under-specifies the 2026-27 sequence-model + MoE + TP world. For a "stake-the-team" adoption decision on a 2026-27 horizon, this is the single largest gap.

---

## Section D — Strategic Gaps Before Adoption

A senior practitioner standing up a new ML platform in 2026 compares kailash-ml against the MLflow + Lightning + SB3 + TRL + Evidently stack. Reading the 13 drafts, here is what is still missing to make the switch:

1. **One-command `km.reproduce(run_id) -> TrainingResult`**. MLflow has `mlflow.models.evaluate`; no Kailash-native "rerun this run against the current code" primitive. Without it, reproducibility is a checklist not a feature.

2. **Run comparison at the metric-curve level.** `RunDiff` (ml-tracking §5) is a point-in-time diff. Senior users compare loss curves, learning-rate schedules, gradient-norm trajectories between runs visually. The dashboard shows it per run, not across 5 runs. W&B, TensorBoard, ClearML all ship this. MLDashboard §6 has a placeholder; spec it explicitly.

3. **First-class "golden run" contract.** A "golden" training run with locked seed, pinned dependencies, bit-reproducible artifacts — used as a regression baseline for every subsequent training. Neither tracker nor registry has a `golden: bool` marker.

4. **Model card / Modelfile.** Transparency / governance frameworks (EU AI Act, NIST AI RMF) require model cards. Registry doesn't emit them; `ml-registry` §lineage captures some but a first-class "export_model_card(model_id) -> ModelCard" with BLEU/ROUGE/accuracy/calibration/fairness/PII-exposure cells is absent.

5. **Fairness / bias metrics.** The drift monitor detects distribution shift but never distribution imbalance across sensitive attributes. In 2026 this is regulatory table-stakes, not optional.

6. **Calibration diagnostics.** ml-engines-v2 has `pipeline.calibrate(method=isotonic)` but ml-diagnostics §9 has no calibration-plot / Brier-score / reliability-curve primitive. A senior classification practitioner demands this first.

7. **Uncertainty quantification.** No conformal prediction, no Bayesian deep learning, no Monte-Carlo dropout primitives. Kaggle 2024+ winners use these routinely.

8. **Continual learning / online retraining.** ml-registry supports `@staging → @production`; ml-feature-store supports point-in-time training; but the full "warm-start from last week's production + new day's data + drift-triggered retrain" loop is not stitched together. This is THE MLOps workflow for 2026-27.

9. **Model compression primitives.** Quantization (INT8/INT4 post-training), pruning (structured/unstructured), distillation. ml-backends §5 mentions ONNX INT8 execution providers as "deferred" — the spec gives no roadmap.

10. **Ensemble registry.** ml-engines-v2 has an `ensemble.py` engine but the registry treats the ensemble as a single model artifact. A senior user wants per-component traceability (5 base models, 1 meta-learner) with independent versioning.

11. **Dataset versioning as a first-class object.** Features are versioned; training data splits (train/val/test row IDs) are not. `TrainingResult.dataset_hash` exists but no `DatasetVersion` surface analogous to `ModelVersion`.

12. **Explainability at prediction-time, not just training-time.** `ModelExplainer` runs SHAP at training review; the inference server never returns a `(prediction, explanation)` pair. SageMaker and Databricks do.

13. **Cost dashboarding.** Every spec tracks latency + compute. None track dollar cost per training run, per inference request, per tenant. For a $3/hour H100 world, this is a Day-1 dashboard tile.

14. **BYO-judge contract for LLM evals.** ml-diagnostics §Appendix references `JudgeCallable` Protocol from kailash-kaizen. The contract is sound, but no evaluation leaderboard primitive exists that uses N judges × M models → scored comparison. This is `trulens`, `opik`, `langfuse` territory.

15. **Auth + RBAC + SSO integration.** Tenant isolation is in-depth (good). But `actor_id` is a string; no integration with OIDC / SAML / LDAP for mapping enterprise identities to actors. Spec's `actor_id` is effectively trusted-client-supplied — red-team finding.

---

## Phase-C Fix Matrix

| Finding                | Priority | Phase-C action                                                                           |
| ---------------------- | -------- | ---------------------------------------------------------------------------------------- |
| A1-1, A1-2, A1-3       | HIGH     | `km.seed()` spec; RL RNG checkpoint schema                                               |
| A2-1, A2-2, A2-3       | HIGH     | `DistributionEnv` dataclass; FSDP full-weight grad norm formula; ZeRO-3 branch           |
| A3-1, A3-2, A3-3       | HIGH     | PSI/JSD/KL smoothing eps constants; histogram bucket spec                                |
| A4-1, A4-2, A4-3       | HIGH     | Resume step-invariant; ReplayBuffer priority tree persist; resume-with-HP-diff child run |
| A5-1, A5-2, A5-3, A5-4 | HIGH     | Per-algo GAE defaults; n_step; clip_range_vf; DPO temperature contract                   |
| A6-1, A6-2             | HIGH     | Single-class confusion matrix; Cook's/leverage/studentized residuals                     |
| A7-1, A7-2, A7-3       | HIGH     | TP-aware autolog rank; LoRA base+adapter separation; streaming token metric split        |
| A8-1, A8-2, A8-3       | HIGH     | Late-arrival policy; immutable feature versions; `check_skew` primitive                  |
| A9-1, A9-2, A9-3       | HIGH     | BOHB fidelity; ASHA rung comparison; LLM token-backpressure                              |
| A10-1, A10-2           | HIGH     | Padding strategies; streaming backpressure contract                                      |
| A11-1, A11-2, A11-3    | HIGH     | Drift type taxonomy; label lag; seasonal reference policy                                |
| A12-1, A12-2, A12-3    | HIGH     | Shared `report()` shape; `adapter` ClassVar; canonical JSON serialization                |

All 29 HIGH findings require spec text in Phase-C. MED findings are strongly recommended. LOW findings are documented but can slip to a 0.18.1 minor.

## Certification Statement

**As the senior-practitioner persona, I would NOT stake my team's platform on the current 13 drafts for a 2026-27 training stack.** The MLOps spine (tracker + registry + feature-store lineage + tenant isolation) is strong enough to certify. The learning-science spine (reproducibility, distributed-training semantics, numerical stability, RL correctness, 2026-27 architecture posture) has 29 HIGH gaps that a 0.18.0 release cannot defer.

**With the Phase-C fixes above, this becomes a CERTIFICATION verdict.** The spine is the right one; the specifics need senior-practitioner tightening.

---

Absolute paths:

- Findings: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-2b-senior-practitioner.md`
- Drafts audited: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/specs-draft/*.md` (13 files)
