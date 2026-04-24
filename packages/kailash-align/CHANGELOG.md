# kailash-align Changelog

## [0.6.0] - 2026-04-23

### Added

- **`kailash_align.ml` integration namespace** (W32 §32b amended, M10 Integrations): the spec-mandated integration facade between kailash-align and kailash-ml. Houses the canonical entry points kailash-ml looks up when wiring alignment into the unified ML lifecycle.
  - Re-exports the four W30 RL bridge adapters under canonical spec §2 table names: `DPOTrainer`, `PPOTrainer`, `RLOOTrainer`, `OnlineDPOTrainer` (storage modules remain at `kailash_align.rl_bridge.{DPOAdapter, PPORLHFAdapter, RLOOAdapter, OnlineDPOAdapter}` for W30-compatible call sites).
  - `LoRALightningCallback` — `pytorch_lightning.Callback` subclass that emits `align.lora.{train,val}.<metric>` entries to the ambient `ExperimentRun` tracker on every batch. Rank-0-only emission guard per `specs/ml-rl-align-unification.md` §3.5. Tensor/finite coercion strips NaN/Inf before emission so the tracker never receives non-finite aggregates.
  - `lora_callback_for(trainable) -> Callback | None` — public entry kailash-ml's `MLEngine.fit` looks up to auto-append the callback for alignment LoRA trainables. Returns `None` cleanly when (a) pytorch_lightning is not installed OR (b) the trainable does not declare LoRA semantics (`is_lora_trainable`, `lora_trainable`, or `trainable_kind == "lora"`), so ml can skip wiring without surfacing a coupling error.
  - `trajectory_from_alignment_run(run: AlignmentResult) -> RLLineage` — converts an alignment run into the W30 cross-SDK provenance schema. Populates `sdk_source="kailash-align"`, `paradigm="rlhf"`, and a sanitized `run_id` derived from the adapter name + version. The return type is the canonical `kailash_ml.rl.RLLineage` (spec §7 single-source mandate); kailash-align does NOT define a parallel `Trajectory` class.

### Architecture

- Dependency direction: `kailash_align.ml` imports from `kailash_ml.rl` (one-way, spec §7). `kailash_ml` MUST NOT import from `kailash_align`. `ml_rl_bridge` from the W30 wave remains the only other align → ml import boundary.
- `kailash_align.ml` imports `pytorch_lightning` lazily via `importlib` so `import kailash_align.ml` is cheap + safe on a Lightning-less install. The loud-fail on missing Lightning happens at `LoRALightningCallback.__init__`, not at package import; `lora_callback_for` returns `None` silently when Lightning is absent so ml can skip LoRA wiring without coupling errors.
- `trajectory_from_alignment_run` lazy-imports `kailash_ml.rl.RLLineage` at call time, preserving module-scope independence while matching the spec §5 schema exactly.

### Spec references

- `specs/ml-rl-align-unification.md` v1.0.0 §5 (cross-SDK `RLLineage` schema), §7 (dependency topology, single-source-in-ml), §3.5 (rank-0-only metric emission).
- `workspaces/kailash-ml-audit/todos/active/W32-kaizen-align-pact-integrations.md` §32b (amended 2026-04-23): LoRA Lightning callback + trajectory unification entry point, align namespace re-exports.

### Notes

- Spec-deviation (specs-authority.md MUST Rule 6): the 32b todo refers to the unified schema as "Trajectory" in prose. The W30 implementation named it `RLLineage` to match spec §5 field names. `trajectory_from_alignment_run` retains the caller-facing vocabulary while returning the actual W30 dataclass — no parallel `Trajectory` class is defined in kailash-align (would violate spec §7 single-source mandate).

## [0.5.0] - 2026-04-23

### Added

- **`kailash_align.rl_bridge` package** — TRL-backed adapters satisfying `kailash_ml.rl.protocols.RLLifecycleProtocol`. Implements the align-side half of the W30 M1 RL + Alignment unification wave per `specs/ml-rl-align-unification.md` v1.0.0.
  - `DPOAdapter` (offline preference-pair via `trl.DPOTrainer`) — honors spec §3.4b separation of `ref_temperature` (default `1.0`, TRL-canonical for log-prob extraction) from `sampling_temperature` (default `0.0`). Emits `rl.train.update.ref_temperature` as a categorical tag on every update so dashboards can audit log-prob-extraction drift.
  - `PPORLHFAdapter` (policy-gradient + reward-model via `trl.PPOTrainer`) — metric-rich: emits the full `rl.rollout.step.*` family (`reward_mean`, `kl_from_reference`, `non_score_reward`, `entropy`) plus `rl.train.update.*` (`policy_loss`, `value_loss`, `approx_kl`, `clip_fraction`, `explained_variance`) per spec §3.4.
  - `RLOOAdapter` (REINFORCE Leave-One-Out via `trl.RLOOTrainer`) — default `sampling_temperature=0.7` for diverse rollouts; emits temperature-separation audit tags on every update.
  - `OnlineDPOAdapter` (online preference-pair via `trl.OnlineDPOTrainer`) — default `sampling_temperature=0.9`; emits temperature-separation audit tags.
- **`[rl-bridge]` optional extra** — pins `kailash-ml[rl]>=1.1,<2.0` per spec §7 + §8 dependency topology. Install via `pip install kailash-align[rl-bridge]`. Zero align-side imports of `kailash_ml` happen at module-scope of `kailash_align`'s non-`rl_bridge` tree; the bridge activates only when `kailash_align.rl_bridge` is imported (either directly OR lazily via `kailash_ml.rl.align_adapter.resolve_bridge_adapter`).
- **Loud-fail on missing extra** — `import kailash_align.rl_bridge` without `kailash-ml[rl]>=1.1` installed raises `ImportError` naming the `[rl-bridge]` extra, per `rules/dependencies.md` § "Optional Extras with Loud Failure". Silent `None` degradation is BLOCKED.
- **`_BridgeAdapterBase`** — shared mix-in for every bridge adapter: `run_id` / `tenant_id` / `device` instance attributes (RLLifecycleProtocol contract); dual-fan-out `emit_metric` (ambient tracker via `tracker.record_metric` + adapter's own `AlignmentDiagnostics.track_training`); `save` / `load` / `checkpoint` / `resume` defaults that delegate to TRL's native persistence primitives (`trainer.save_model` + `state.save_to_json` + `resume_from_checkpoint`); `__make_for_test__` factory for the spec §4 Protocol-conformance sweep.
- **Cross-SDK Protocol conformance** — all four adapters satisfy `isinstance(adapter, RLLifecycleProtocol)` at runtime via structural duck typing (Protocol is `@runtime_checkable`). Registered in `kailash_ml.rl.align_adapter.BRIDGE_ADAPTERS` under keys `"dpo"`, `"ppo-rlhf"`, `"rloo"`, `"online-dpo"` per spec §9 v1 scope.

### Architecture

- `km.rl_train(algo=<name>)` now routes RLHF algorithm names into this bridge via `kailash_ml.rl.align_adapter.resolve_bridge_adapter`, which lazy-imports `kailash_align.rl_bridge`; the import side-effect registers all four adapters.
- Each adapter populates the `RLLineage` field on its returned `RLTrainingResult` with `sdk_source="kailash-align"`, `paradigm="rlhf"`, and the canonical algorithm name. Downstream `MLDashboard` renders classical-RL and RLHF runs in a unified provenance breadcrumb.
- Adapter `__init__` validates temperature kwargs eagerly (numeric + sign + range). Misconfiguration surfaces at construction time, not deep inside TRL's trainer loop.

### Spec references

- `specs/ml-rl-align-unification.md` v1.0.0 §2 (Protocol contract), §3 (dispatch), §3.2 (result-type parity), §3.3–§3.4 (canonical `rl.*` metric family), **§3.4b (DPO reference-temperature contract)**, §4 (Tier-2 conformance test), §5 (lineage fields), §7 (dependency topology), §8 (version coordination), §9 (v1 scope: DPO, PPO-RLHF, RLOO, OnlineDPO).

### Notes

- `kailash-align 0.5.0` requires `kailash-ml[rl]>=1.1,<2.0` when the `[rl-bridge]` extra is installed. Orchestrators releasing this version MUST release `kailash-ml 1.1.0+` first per `rules/deployment.md` § "Optional Dependencies Pin to PyPI-Resolvable Versions".

## [0.4.0] - 2026-04-20

### Added

- **AlignmentDiagnostics adapter** (issue #567, PR#3 of 7): concrete Align adapter satisfying `kailash.diagnostics.protocols.Diagnostic` (landed PR#0/#570). Observes LLM fine-tuning runs via three primary readings:
  - `evaluate_pair(base_logprobs, tuned_logprobs, preferences)` — closed-form KL(base || tuned), reward-margin, pairwise win-rate
  - `track_training(metrics_iterable)` — bounded-memory deque ingestion of `{step, reward, kl, loss, ...}` dicts from `AlignmentPipeline.metrics_stream()` or equivalent
  - `detect_reward_hacking(threshold=2.5)` — flags the canonical signature of sudden reward spike co-occurring with a KL blow-up
- `report()` returns structured dict with severity-tagged findings; never raises on empty state
- `plot_*()` methods return plotly Figures via `_require_plotly()` loud-fail helper
- `*_df()` accessors return polars DataFrames
- Closed-form KL primary path (numpy); `trl` statistical helpers used as an optimization when available

### Attribution

- Portions originated from MLFP (Apache-2.0) and re-authored for the Kailash ecosystem — see `specs/alignment-diagnostics.md` § "Attribution" for the full donation history.

## [0.2.0] - 2026-04-02

### Fixed

- **AdapterRegistry bounded** (C1): max_adapters=10,000, max_versions_per_adapter=1,000 — prevents OOM
- **Shell script sanitization** (C2): Generated launch_vllm.sh sanitizes adapter_name via regex
- **Subprocess flag injection** (H1): `--` separator added before path arguments in GGUF conversion
- **Division-by-zero guards** (H2/H3): `max(1, total_params)` in pipeline.py, `max(1, hidden_dim_estimate)` in gpu_memory.py

### Security

- R3 red team converged: 0 CRITICAL, 0 HIGH findings
- 391 tests passing, 0 regressions

## [0.1.0] - 2026-03-30

### Added

- Initial release: 12 alignment methods, MethodRegistry, AlignmentPipeline, AdapterRegistry, AlignmentEvaluator, AlignmentServing, KaizenModelBridge, OnPremModelCache
