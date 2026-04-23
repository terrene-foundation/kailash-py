# kailash-align Changelog

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
