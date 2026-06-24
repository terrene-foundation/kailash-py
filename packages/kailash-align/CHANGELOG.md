# kailash-align Changelog

## [0.7.4] — 2026-06-24 — OnlineDPOAdapter.build raises an informative TrainingError (#1429)

Patch release. Bug fix — no public dataclass-signature break; the `online_dpo`
method remains de-registered (as of 0.7.3 / #1426, since trl >=1.0 removed
`OnlineDPOTrainer`/`OnlineDPOConfig` upstream).

### Fixed

- **`OnlineDPOAdapter.build()` now raises an informative `TrainingError`**
  instead of the opaque `AlignmentError: Unknown training method 'online_dpo'`.
  0.7.3 (#1426) de-registered `online_dpo` from the method registry, but
  `OnlineDPOAdapter.build()` still called `get_method("online_dpo")` outside its
  guard, surfacing a registry-miss error that told the user nothing about WHY
  Online-DPO is unavailable or what to use instead. `build()` now raises the
  SAME message `OnlineDPOConfig.to_trl_config()` already raises in `config.py`
  ("Online DPO is unavailable: trl >=1.0 removed … use `dpo` or `grpo`"). A
  parity regression test pins the two messages byte-identical so a future edit
  to one without the other fails loudly.
- **`OnlineDPOAdapter.learn()` surfaces the same informative error.** `learn()`
  builds the trainer first, so it now hits the same `TrainingError`; the
  unreachable post-build trainer-construction body (which constructed a trl
  trainer that can never exist) was dead code and is removed.

## [0.7.3] — 2026-06-23 — trl 1.x compatibility for to_trl_config + pipeline (#1426)

Patch release. Bug fix — 0.7.2 could not run **any** SFT/DPO/KTO/ORPO/Online-DPO
fine-tune against **any** `trl` in its declared `>=1.0,<2.0` range (the config
adapters + trainer setup targeted the trl 0.x API). No public dataclass-signature
break: the user-facing `*Config` fields are unchanged.

### Fixed

- **`*Config.to_trl_config()` now emits trl 1.x kwargs.** `SFTConfig` forwards
  `max_length` (was the removed `max_seq_length`); `DPOConfig`/`KTOConfig` drop
  the removed `max_prompt_length`; `GRPOConfig`/`RLOOConfig` forward `beta`
  (was `kl_coef`) and `vllm_gpu_memory_utilization` (was `vllm_gpu_utilization`).
- **`pipeline.py` no longer passes both a `PeftModel` and `peft_config`** to the
  trainer (trl 1.x raises `ValueError`); the model is pre-wrapped, so `peft_config`
  is omitted when the model is already a `PeftModel`.
- **Trainer lazy-import guard:** a registered method whose trl trainer class was
  removed in trl 1.x (`xpo`/`nash_md`/`ppo`/`cpo`/`bco`) now raises an informative
  `TrainingError` (naming the method + absent class + supported alternatives)
  instead of a raw `ImportError`.

### Changed

- **`orpo` and `online_dpo` de-registered from `METHOD_REGISTRY`.** `trl` >=1.0
  removed `ORPOTrainer`/`ORPOConfig` and `OnlineDPOTrainer`/`OnlineDPOConfig`
  upstream, so these methods raised on every supported `trl`. `validate_method_name`
  / `get_method` now reject them with a redirect to `dpo`/`grpo`/`sft_then_dpo`.
  The `ORPOConfig`/`OnlineDPOConfig` dataclasses are retained for back-compat;
  their `to_trl_config()` raises an informative `TrainingError`.

### Known limitations

- The `[rl-bridge]` `OnlineDPOAdapter` still references the de-registered
  `online_dpo` method on a `kailash-ml[rl]`-gated path (tracked: #1429).

## [0.7.2] — 2026-06-08 — drop defensive `kailash-ml` cap + de-stale floor (#1183)

Patch release. **No source changes** — diff is strictly `pyproject.toml` dependency-floor edits + `__version__` anchor + this CHANGELOG entry.

### Changed

- **`[rl-bridge]` extra: `kailash-ml[rl]>=1.1`** (was `kailash-ml[rl]>=1.1,<2.0`). The `<2.0` defensive cap excluded the current `kailash-ml 2.0.0` — a live resolution break per `dependencies.md` § "No Caps". Verified safe: all 9 `kailash_ml.rl.*` symbols the rl-bridge imports are present in ml 2.0.0, and the rl-bridge test suite (74 tests) passes against it.
- **Core dep `kailash-ml>=1.1`** (was `kailash-ml>=0.11.0`). The `0.11.0` floor was stale (ml is at 2.0.0) and inconsistent with the `[rl-bridge]` floor within the same manifest; raised to the established `>=1.1` minimum.

### Notes

- No public-API changes; no behavior changes; wheel content is identical to 0.7.1 except for the `__version__` constant. Surfaced by the new `tools/check_pin_consistency.py` first-party pin-drift gate (#1183).

## [0.7.1] — 2026-05-09 — kailash floor bump for #890 slim-core alignment

Patch release pairing kailash-align with the kailash 2.18.0 / #890 slim-core layout. **No source changes** — diff is strictly `pyproject.toml` floor bump + `__version__` anchor + this CHANGELOG entry.

### Changed

- **`kailash` floor: 2.16.0** (was `2.11.0`) — aligns with the kailash 2.18.0 slim-core layout. The pre-bump floor still resolved against PyPI, but ≥2.16.0 is the canonical floor for any package depending on the post-#890 surfaces.

### Notes

- No public-API changes; no behavior changes; wheel content is identical to 0.7.0 except for the `__version__` constant. Only the install manifest changed.

## [0.7.0] - 2026-04-27 — W6-016: shared trajectory schema bridge (F-E1-50)

Cross-SDK companion of `kailash-ml 1.3.0`. Closes W5-E1 finding F-E1-50
(HIGH) on the kailash-align side: the trajectory-schema bridge between
`kailash-ml.rl` (producer) and `kailash-align` (consumer) is now wired
through both halves with a Tier-2 round-trip regression test.

### Added

- **`AlignmentPipeline.consume_trajectories(trajectories)`** — align-side
  consumer entry of the cross-SDK bridge. Accepts a single
  `kailash_ml.rl.TrajectorySchema` OR an iterable of them, accumulating
  on repeated calls so multi-stage pipelines (e.g. SFT → DPO each
  consuming distinct upstream trajectories) build provenance over
  multiple steps. Lazy-imports `TrajectorySchema` from `kailash_ml.rl`
  so `import kailash_align` stays cheap when the bridge is unused.
  Non-`TrajectorySchema` items raise `TrainingError`. Per spec
  `ml-rl-align-unification.md` §3.2 + §4.
- **`AlignmentPipeline.consumed_trajectories` property** — read-only
  tuple of every trajectory previously consumed; alignment runs use it
  to record upstream provenance into their own audit trail.
- **`kailash_align.ml.TrajectorySchema` re-export** — single-source-in-ml
  mandate per spec §7: kailash-align re-exports the canonical
  `kailash_ml.rl.TrajectorySchema` and does NOT define a parallel.
  Eager re-export per `rules/orphan-detection.md` §6 (every `__all__`
  entry resolves at module-scope import). Added to `kailash_align.ml.__all__`.

### Tests

- **`tests/integration/ml/test_trajectory_round_trip.py`** — Tier-2
  round-trip regression (11 tests, all green): canonical-type identity
  (`align.ml.TrajectorySchema is kailash_ml.rl.TrajectorySchema`),
  producer-side `RLTrainer.collect_trajectories` correctness, lineage
  required guard, byte-stable dict + JSON round-trip, schema-
  discriminator + version rejection, consumer-side
  `AlignmentPipeline.consume_trajectories` for single + iterable
  payloads, type-rejection, and the full bridge (RL → JSON → Align)
  end-to-end.

### Spec references

- `specs/ml-rl-align-unification.md` v1.0.0 §3.2 (result-type parity),
  §4 (Tier-2 conformance test), §7 (dependency topology — single source
  in ml; align imports, never redefines).
- `workspaces/portfolio-spec-audit/04-validate/W5-E1-findings.md`
  F-E1-50 (HIGH closure).

### Notes

- `kailash-align 0.7.0` requires `kailash-ml>=1.3` at runtime for the
  `TrajectorySchema` re-export and lazy import in
  `AlignmentPipeline.consume_trajectories`. Orchestrators releasing
  this version MUST release `kailash-ml 1.3.0+` first per
  `rules/deployment.md` § "Optional Dependencies Pin to PyPI-Resolvable
  Versions".

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
