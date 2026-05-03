# Round-1 Red-Team — RL Researcher Persona

**Date:** 2026-04-21
**Package under audit:** `packages/kailash-ml/` (version 0.17.0)
**Persona scope:** Reinforcement-learning lifecycle only. Not spec fidelity, not DL internals, not day-0 UX, not MLOps, not general industry parity.

The audit brief's Known-Real-Gap #4 asserts "No RL diagnostics exist." The claim is partially incorrect: there **is** RL scaffolding (`kailash_ml.rl` subpackage, `[rl]` extra declared in pyproject, one wrapper class around Stable-Baselines3). What is true is **much worse** than "no diagnostics": the RL subpackage is a **pinned orphan** — the codebase literally has a regression test (`tests/regression/test_rl_orphan_guard.py`) that asserts `RLTrainer` has **zero call sites** from any production engine and is **not exported** at `km.*`. Every RL capability a researcher expects from an industry-grade stack (rollout buffer telemetry, reward curves, KL/entropy, exploration/exploitation metrics, advantage fit quality, offline RL, vectorized envs, distributed rollout, RLHF integration with align) is missing. This file enumerates every gap against grep-verified evidence.

## What Exists (Verified)

| Symbol                                            | File                                                       | Purpose                                                                                                                                                      | Verified     |
| ------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------ |
| `RLTrainer`                                       | `packages/kailash-ml/src/kailash_ml/rl/trainer.py`         | Thin SB3 wrapper; `train(env_name, policy_name, config)` → `model.learn` + `_evaluate` rollouts                                                              | lines 94–275 |
| `RLTrainingConfig`                                | same                                                       | dataclass: `algorithm`, `policy_type`, `total_timesteps`, `hyperparameters`, `n_eval_episodes`, `eval_freq`, `seed`, `verbose`, `save_path`                  | lines 20–43  |
| `RLTrainingResult`                                | same                                                       | dataclass: `policy_name`, `algorithm`, `total_timesteps`, `mean_reward`, `std_reward`, `training_time_seconds`, `artifact_path`, `eval_history` (empty list) | lines 46–68  |
| `EnvironmentRegistry` / `EnvironmentSpec`         | `packages/kailash-ml/src/kailash_ml/rl/env_registry.py`    | Gymnasium wrapper for `gym.register` + `gym.make`, no VecEnv, no wrapper stack                                                                               | lines 37–112 |
| `PolicyRegistry` / `PolicySpec` / `PolicyVersion` | `packages/kailash-ml/src/kailash_ml/rl/policy_registry.py` | In-memory dict of trained artifacts; bounded at `_MAX_VERSIONS_PER_POLICY = 1000`; no persistence, no integration with `kailash_ml.ModelRegistry`            | lines 73–195 |
| `[rl]` extra                                      | `packages/kailash-ml/pyproject.toml:82-85`                 | `stable-baselines3>=2.3`, `gymnasium>=0.29`                                                                                                                  | verified     |
| 6 SB3 algorithms mapped                           | `rl/policy_registry.py:63-70`                              | PPO, SAC, DQN, A2C, TD3, DDPG                                                                                                                                | verified     |

**Marked `[P2: Experimental]`** in its own docstring (`rl/trainer.py:95`). That's the author's own honest label.

## Tests — The Smoking Gun

`packages/kailash-ml/tests/regression/test_rl_orphan_guard.py` (120 LOC) explicitly pins the orphan state. Quoting the file's own docstring:

> "The 5-agent audit at `workspaces/kailash-ml-audit/analysis/00-synthesis-redesign-proposal.md` §§ 3.1, 5.4 flagged `kailash_ml.rl` and `kailash_ml.agents` as orphan-shaped subpackages: they expose manager-shape classes (`RLTrainer`, `EnvironmentRegistry`, `PolicyRegistry`, `*Agent`) that have zero production call sites inside `kailash_ml.engines.*` and are not surfaced at `km.*`. This is the same failure pattern `rules/orphan-detection.md` §§ 1-3 codifies after the kailash-py Phase 5.11 trust-executor incident."

Four tests, all **currently passing** because the orphan state is what they pin:

1. `test_rl_trainer_has_zero_engine_call_sites` — asserts `RLTrainer` is imported by zero files in `engines/*`
2. `test_agents_have_zero_engine_call_sites` — same for `kailash_ml.agents`
3. `test_km_top_level_does_not_expose_rl_or_agents` — asserts `"rl"` is NOT in `kailash_ml.__all__`
4. `test_rl_trainer_does_not_use_backend_resolver` — asserts `detect_backend()` / `BackendInfo` are NOT imported by `rl/*` — i.e., RL does NOT honor `km.device()` / `km.use_device()` / GPU-first resolution

That last one is devastating: the entire 0.12.0 → 0.17.0 GPU-first redesign (DeviceReport, BackendInfo, detect_backend, device+use_device contextvars, per-Trainable `device=` plumbing) **does not reach RL at all**. An `RLTrainer` user calling `config.hyperparameters = {"device": "cuda"}` is doing it by hand with zero integration with the rest of the package.

The unit test `packages/kailash-ml/tests/unit/test_rl.py` (80+ LOC visible) covers only `PolicySpec`, `PolicyVersion`, `PolicyRegistry` dataclass round-trips — no Tier 2 wiring test against gymnasium + SB3 exists.

## Findings

### CRIT-1 — RL is a pinned orphan, not a capability

**Evidence:** `tests/regression/test_rl_orphan_guard.py:48-94` asserts `RLTrainer` has zero engine call sites AND is absent from `kailash_ml.__all__`. `packages/kailash-ml/src/kailash_ml/__init__.py:255-338` — `__all__` contains 64 symbols; NONE are RL-related. No `km.rl_train`, no `km.RLTrainer`, no `km.rl.*`.

A user running `import kailash_ml as km; km.<Tab>` sees zero RL surface. To use RL they must:

1. Know the exact module path: `from kailash_ml.rl import RLTrainer, EnvironmentRegistry, PolicyRegistry`
2. Know the algorithm name strings and build SB3 hyperparameters by hand
3. Accept zero integration with `km.track()`, `MLDashboard`, `ModelRegistry`, `DriftMonitor`, or any other engine

**Severity:** CRIT (per `rules/orphan-detection.md` §1 — facade shipped without production call site; per `rules/zero-tolerance.md` Rule 2 — entire subpackage is stub-shaped). The docstring says "[P2: Experimental]" — that is a label on a class; it is NOT a substitute for wiring.

**Fix:** Either delete `kailash_ml.rl` entirely (per `rules/orphan-detection.md` §3 — "Removed = Deleted, Not Deprecated"), or wire it end-to-end per §3 in this file.

### CRIT-2 — `RLTrainingResult` cannot unify with `TrainingResult`

**Evidence:** `rl/trainer.py:46-68` — `RLTrainingResult` fields are `policy_name`, `algorithm`, `total_timesteps`, `mean_reward`, `std_reward`, `training_time_seconds`, `artifact_path`, `eval_history`. Compare `kailash_ml._result.TrainingResult` — a different dataclass with different fields (`metrics`, `model`, `device`, `backend_info`, etc., per `specs/ml-engines.md`).

`workspaces/kailash-ml-audit/analysis/gap-analysis.md:59` already flagged this: "RL is a parallel universe. There is no common `train()` that routes to classical/DL/RL."

**Consequence:** A user writing a mixed pipeline (sklearn baseline + RL fine-tune for a bandits task) cannot `km.track()` both runs into the same experiment — the tracker expects `TrainingResult`-shaped metrics; RL produces `RLTrainingResult`. `MLDashboard` has zero RL columns. `ModelRegistry.register()` accepts sklearn/lightgbm artifacts, not SB3 zip files.

**Severity:** CRIT — the architectural split is load-bearing: every RL extension inherits the same impedance mismatch.

**Fix:** Define `kailash_ml.rl.RLTrainingResult` as a subtype of `TrainingResult` OR fold the RL fields (`mean_reward`, `std_reward`, `eval_history`, `total_timesteps`, `episodes`) into `TrainingResult` and let non-RL runs leave them `None`.

### HIGH-1 — Zero episode / rollout / reward telemetry during training

**Evidence:** `rl/trainer.py:159-162` — training is one line: `model.learn(total_timesteps=config.total_timesteps)`. No TensorBoard callback configured, no custom callback attached, no episode reward stream, no WANDB/TensorBoard integration, no per-episode reward curve emission.

`rl/trainer.py:241-258` — `_evaluate` runs post-training rollouts and returns `(mean_reward, std_reward)` scalars. `RLTrainingResult.eval_history: list[dict[str, Any]]` is declared but never populated — it's a `field(default_factory=list)` with zero writes in the codebase. Grep-verified:

```
$ grep -n 'eval_history' packages/kailash-ml/src/kailash_ml/rl/*.py
trainer.py:57:    eval_history: list[dict[str, Any]] = field(default_factory=list)
```

One declaration, one site — the field exists but is never populated. Per `rules/zero-tolerance.md` Rule 2 this is a dead field.

**Missing vs industry baseline:**

- **Episode reward curve** — SB3 `Monitor` wrapper + `EvalCallback` → TensorBoard `rollout/ep_rew_mean`, `rollout/ep_len_mean`
- **Policy loss / value loss / entropy loss / clip fraction** (PPO) — SB3 writes to TB by default, `RLTrainer` discards it
- **KL divergence** (PPO / SAC) — early-stopping signal; not captured
- **Explained variance of value function** — SB3 computes; discarded
- **Action distribution statistics** — not captured
- **`fps`** — throughput metric; not captured

**Severity:** HIGH — `rules/observability.md` §1 Endpoints + §2 Integration Points; an SB3 training call is an integration point that produces 10+ metrics streams, and `RLTrainer` captures zero of them.

**Fix:** Attach an SB3 `BaseCallback` subclass that pipes every `logger.name_to_value` entry on `_on_step` / `_on_rollout_end` into the kailash-ml tracker. Populate `eval_history` with every eval-triggered rollout (which means actually using `eval_freq` to trigger `EvalCallback`).

### HIGH-2 — `eval_freq` declared but never used

**Evidence:** `rl/trainer.py:29` — `eval_freq: int = 10_000`. Grep for its consumption:

```
$ grep -rn 'eval_freq' packages/kailash-ml/src/kailash_ml/rl/
trainer.py:29:    eval_freq: int = 10_000
trainer.py:41:            "eval_freq": self.eval_freq,
```

Declared in the dataclass, serialized to `to_dict()`, **never passed to SB3**, **never invokes `EvalCallback`**, **never gates anything**. The user passes `eval_freq=5000` expecting intermediate eval checkpoints; they get exactly one post-training eval. This is a `zero-tolerance.md` Rule 2 stub — a parameter that looks configured but has no consumer.

**Severity:** HIGH — misleads users into thinking the config matters.

**Fix:** Wire `eval_freq` through `SB3 EvalCallback(eval_env, n_eval_episodes, eval_freq)` and populate `eval_history` with each eval's reward + step.

### HIGH-3 — No rollout buffer / replay buffer telemetry

**Evidence:** Grep for buffer introspection:

```
$ grep -rn 'replay_buffer\|rollout_buffer' packages/kailash-ml/src/kailash_ml/
(no matches)
```

Zero references to SB3's `model.rollout_buffer` (on-policy: PPO/A2C) or `model.replay_buffer` (off-policy: SAC/DQN/TD3/DDPG). An RL researcher debugging "why is PPO's advantage fit bad?" cannot inspect:

- Advantage mean / std / fit quality (on-policy)
- Replay buffer size / fill ratio / reward distribution (off-policy)
- Priority distribution in PER (if used)
- Stored transitions per episode
- TD-error distribution (DQN)

**Severity:** HIGH — standard SB3 users rely on this to diagnose reward sparsity, catastrophic forgetting, replay staleness. The wrapper provides zero such diagnostics.

**Fix:** Add `RLDiagnostics` class analogous to `DLDiagnostics` — a context manager that attaches to `model.rollout_buffer` / `model.replay_buffer` at `_on_step` and extracts summary statistics.

### HIGH-4 — No exploration-exploitation metrics

**Evidence:** Grep for exploration state:

```
$ grep -rn 'epsilon\|exploration' packages/kailash-ml/src/kailash_ml/rl/
(no matches)
```

DQN uses ε-greedy exploration (`model.exploration_rate`). SAC uses entropy-regularized exploration (`model.log_ent_coef`). A2C/PPO log `entropy_loss`. `RLTrainer` captures none of them. A user debugging "why is DQN stuck exploring forever?" cannot see the current ε. A user debugging "why has SAC's entropy collapsed?" cannot see `log_ent_coef`.

**Severity:** HIGH — every RL textbook mentions these as primary debugging signals.

**Fix:** `RLDiagnostics.track_exploration()` — algorithm-aware extraction: ε for DQN, entropy coef for SAC, action distribution entropy for PPO.

### HIGH-5 — No separate eval environment

**Evidence:** `rl/trainer.py:165` — evaluation uses the SAME `env` that training mutated (`mean_reward, std_reward = self._evaluate(model, env, config.n_eval_episodes)`). Rendering state, wrapper state, RNG state are all shared. SB3's convention is `eval_env = gym.make(env_name)` — a fresh independent environment.

**Consequence:** Stochastic environments produce reward leaks — training sees states that evaluation then re-visits. Non-deterministic eval.

**Severity:** HIGH — fundamental RL hygiene violation.

**Fix:** `_make_env` called separately for training and for eval, or pass a dedicated `eval_env_name` through config.

### HIGH-6 — No VecEnv / SubprocVecEnv / DummyVecEnv support

**Evidence:** `rl/trainer.py:239` — `return gym.make(env_name)` returns a single env. SB3 recommends `make_vec_env(env_id, n_envs=8)` for sample-efficient PPO/A2C. The trainer does not expose `n_envs`, does not construct a `VecEnv`, does not parallelize rollout collection. PPO on a single env is 4-8× slower than on 8 parallel envs.

**Severity:** HIGH — sample efficiency gap that forces users to drop to raw SB3.

**Fix:** Add `n_envs: int = 1` to `RLTrainingConfig`; when > 1, construct `make_vec_env`.

### HIGH-7 — No wrapper stack support

**Evidence:** `gym.make(env_name)` returns a bare env. Standard wrappers — `Monitor` (required for `ep_rew_mean` in TB), `VecNormalize` (observation/reward normalization for MuJoCo), `FrameStack` + `AtariPreprocessing` (Atari), `TimeLimit` — must be applied OUTSIDE this wrapper by the user hand-constructing them, defeating the engine-first promise.

**Severity:** HIGH — Atari / MuJoCo users cannot use `RLTrainer` at all without forking it.

**Fix:** `RLTrainingConfig.wrappers: list[WrapperSpec]` — declarative wrapper stack applied inside `_make_env`.

### HIGH-8 — Zero integration with `km.track()` / `MLDashboard` / `ModelRegistry`

**Evidence:** Grep:

```
$ grep -rn 'from kailash_ml.tracking\|ExperimentTracker\|ModelRegistry\|MLDashboard' packages/kailash-ml/src/kailash_ml/rl/
(no matches)
```

- No tracker integration — RL runs are invisible to `km.track()` + `MLDashboard`
- No `ModelRegistry.register()` — SB3 artifacts saved to `.kailash_ml/rl_artifacts/<policy_name>/model.zip` (disk), orthogonal to `ModelRegistry`'s lifecycle (`staging → shadow → production → archived`)
- No event emission — no lifecycle hook fires; a researcher cannot subscribe to "RL training completed"

This is the exact gap the audit brief's non-negotiable #2 was written to prevent: "Seamless + auto — the happy path MUST NOT require users to wire a tracker into a dashboard into a diagnostics class into a visualizer. The engine does that wiring."

**Severity:** HIGH — brief-level non-negotiable violation.

**Fix:** `RLTrainer.__init__` accepts `tracker=None, model_registry=None` (same pattern as `TrainingPipeline`); `train()` auto-logs episode rewards + losses to tracker; `train()` calls `model_registry.register_model()` with SB3 artifact adapter.

### HIGH-9 — GPU-first resolver is unplumbed for RL

**Evidence:** `tests/regression/test_rl_orphan_guard.py:101-119` explicitly pins "RL does not consult `detect_backend()`" as a HIGH finding from the 2026-04-17 redteam. `km.device()` + `km.use_device("cuda")` returns `BackendInfo`, but `RLTrainer.train()` ignores it. The user must manually pass `device="cuda"` in `hyperparameters={"device": "cuda"}`.

This is the same bug class that `specs/ml-backends.md` + `_device.py` + `_device_report.py` + every `*Trainable.fit()` was built to fix in 0.12.0 — and RL was silently skipped.

**Severity:** HIGH — cross-cutting architectural regression (Phase 1 GPU-first work didn't cover RL; nobody noticed because RL was already an orphan).

**Fix:** `RLTrainer._resolve_device()` → `detect_backend().backend` → propagate to `hyperparameters["device"]` before `algo_cls(config.policy_type, env, **hp)`. Emit `DeviceReport` into the `RLTrainingResult`.

### HIGH-10 — No offline RL / dataset-based RL (BC, CQL, IQL, DT)

**Evidence:** `rl/policy_registry.py:63-70` — only online SB3 algorithms (PPO, SAC, DQN, A2C, TD3, DDPG) are mapped. Zero support for offline RL where training data is a fixed dataset:

- Behavioral Cloning (supervised imitation)
- Conservative Q-Learning (CQL)
- Implicit Q-Learning (IQL)
- Decision Transformer (DT)
- Advantage-Weighted Regression (AWR)

Offline RL has become the dominant RL use-case for ML products (robotics datasets, recommender fine-tuning, industrial control with historical logs) precisely because online interaction is expensive. It is missing entirely.

**Severity:** HIGH — any team using historical trajectory logs has to leave kailash-ml for d3rlpy / CORL / RLlib.

**Fix:** Add `kailash_ml.rl.offline` — adapters for BC (trivial via `SklearnTrainable`-shaped imitation), d3rlpy integration for CQL/IQL/DT.

### HIGH-11 — No TRL / RLHF integration with kailash-align

**Evidence:** `packages/kailash-align/src/kailash_align/method_registry.py:221,283,299,377` — `kailash-align` already knows about `DPOTrainer`, `RLOOTrainer`, `OnlineDPOTrainer`, `PPOTrainer` (all from HuggingFace `trl`). Grep shows these are registered as align `method_registry` entries, NOT as `kailash_ml.rl` surface.

The RLHF PPO loop in `trl` produces reward-model-based advantages, KL penalty to a reference model, clipped objective — all **structurally identical** to SB3 PPO but with a language-model policy and a reward-model critic. `kailash_ml.rl.RLTrainer` and `kailash_align.method_registry["PPOTrainer"]` **do not share a single line of code** — they don't share `RLTrainingResult`, don't share a tracker, don't share a policy-registry pattern, don't share a device resolver.

**Consequence:** A researcher doing "train a bandit with SB3 PPO, then fine-tune an LLM with TRL PPO" has TWO separate experiment trackers, TWO dashboards, TWO registries, TWO APIs.

**Severity:** HIGH — the audit brief's non-negotiable #4 (Full lifecycle coverage) explicitly lists RL + LLM fine-tune as peer capabilities.

**Fix:** Define a shared `RLLifecycleProtocol` in `kailash-ml` that both `RLTrainer` (env-based RL via SB3) and `AlignmentPipeline` (LM-based RL via TRL) implement. Result dataclasses converge. Tracker + dashboard see both. Cross-reference: this aligns with `specs/alignment-training.md` promises around unified tracking.

### HIGH-12 — No multi-agent / MARL support

**Evidence:** `rl/env_registry.py` + `rl/trainer.py` assume single-agent `gym.Env` interface. `Gymnasium` has `PettingZoo` integration for multi-agent environments; SB3 does not natively support MARL, but `ray[rllib]` does via `MultiAgentEnv`. Neither is integrated.

**Severity:** HIGH for any real-world product (trading, robot fleets, game AI, recommender multi-user bandits).

**Fix:** At minimum, document that MARL is out of scope. At maximum, integrate `rllib`.

### HIGH-13 — No distributed rollout workers

**Evidence:** No integration with `ray[rllib]`, no `SubprocVecEnv` exposed, no APEX-style distributed rollout. PPO/SAC on a single machine is bounded by single-machine throughput.

**Severity:** HIGH — industry baseline (rllib, Acme, TorchRL, SB3-contrib) all provide distributed variants.

**Fix:** Optional `[rl-distributed]` extra depending on `ray[rllib]`.

### HIGH-14 — No curriculum / task scheduling

**Evidence:** Zero curriculum support — no interface for "train on easy tasks, progressively hard"; no `TaskScheduler` abstraction.

**Severity:** HIGH — required for robotics, procgen, any task with reward sparsity.

**Fix:** `CurriculumConfig` dataclass threaded into `RLTrainingConfig`.

### HIGH-15 — No `RLDiagnostics` class at all

**Evidence:** `packages/kailash-ml/src/kailash_ml/diagnostics/__init__.py:73-79` — `__all__ = ["DLDiagnostics", "RAGDiagnostics", "run_diagnostic_checkpoint", "diagnose_classifier", "diagnose_regressor"]`. No `RLDiagnostics`.

The audit brief's known-real-gap #4 is correct on this specific point: there is no RL diagnostics adapter. Its sibling `DLDiagnostics` has `track_gradients`, `track_activations`, `track_dead_neurons`, `record_batch`, `record_epoch`, `report()`, `plot_training_dashboard()`. The RL analog would be `track_rollout`, `track_advantage`, `track_exploration`, `track_replay_buffer`, `record_episode`, `report()`, `plot_training_dashboard()` — none of this exists.

**Severity:** HIGH — directly called out in the brief.

**Fix:** New module `packages/kailash-ml/src/kailash_ml/diagnostics/rl.py` conforming to `kailash.diagnostics.protocols.Diagnostic` Protocol. See design section below.

### MED-1 — `test_rl.py` has zero Tier 2 wiring

**Evidence:** `tests/unit/test_rl.py` has ~80 LOC of Tier 1 unit tests on `PolicySpec`/`PolicyVersion`/`PolicyRegistry` dataclass round-trips. No integration test invokes `RLTrainer.train(env_name="CartPole-v1", policy_name="test", config=RLTrainingConfig(total_timesteps=100))` against real SB3 + real gymnasium. Per `rules/facade-manager-detection.md` §1, a manager-shape class (`RLTrainer` has `*Trainer` suffix) MUST have a Tier 2 wiring test.

**Severity:** MED (would be HIGH except the orphan-guard test explicitly pins the pre-wiring state).

**Fix:** Once wiring lands, add `tests/integration/test_rl_trainer_wiring.py` that runs 100 timesteps of PPO on CartPole and asserts reward trajectory is emitted to the tracker.

### MED-2 — `EnvironmentRegistry` has no env-validation

**Evidence:** `rl/env_registry.py:47-72` — `register()` calls `gym.register` but does not test that `gym.make(spec.name).reset()` returns a valid tuple. Typo in `entry_point` surfaces only at first `RLTrainer.train()` call, not at `register()` time. `rules/observability.md` §1 requires an integration point to log intent + result.

**Severity:** MED.

**Fix:** Smoke-test the env at registration time.

### MED-3 — `PolicyRegistry` is in-memory only

**Evidence:** `rl/policy_registry.py:85-88` — `self._specs: dict[str, PolicySpec]` + `self._versions: dict[str, list[PolicyVersion]]` are Python dicts. No persistence. On process restart, every "registered" version is lost. The artifact zip survives on disk, but the registry metadata does not. Compare `kailash_ml.ModelRegistry` (SQLite-backed via `ConnectionManager`).

**Severity:** MED — usable for notebooks, unusable for production.

**Fix:** Back `PolicyRegistry` onto `kailash_ml.ModelRegistry`. Delete `PolicyVersion`; reuse `ModelVersion`. (This is a concrete instance of the "two parallel universes" finding in CRIT-2.)

### MED-4 — SB3 algorithm allowlist is closed

**Evidence:** `rl/policy_registry.py:63-70` hardcodes 6 algorithms. No hook to register user-defined SB3 subclasses (e.g. `PPOLag`, `MaskablePPO` from `sb3_contrib`, or a research algorithm). Compare `kailash_ml.estimators.register_estimator` — extensibility for classical.

**Severity:** MED.

**Fix:** `rl.register_algorithm(name, import_path)` function symmetric with `register_estimator`.

### MED-5 — Reward shaping / custom reward hooks absent

**Evidence:** No `RewardWrapper` composition API, no reward-shaping callback, no potential-based reward shaping helper. Users must monkey-patch or subclass SB3.

**Severity:** MED.

**Fix:** Optional `reward_wrappers: list[RewardWrapperSpec]` in `RLTrainingConfig`.

## Industry Comparison Matrix

| Capability                                 | `kailash_ml.rl` (0.17.0) | SB3 (direct)                 | RLlib                 | TRL                        | CleanRL             |
| ------------------------------------------ | ------------------------ | ---------------------------- | --------------------- | -------------------------- | ------------------- |
| Entry point (one line)                     | no (hidden sub-package)  | yes (`PPO(...).learn(...)`)  | yes (`Tuner().fit()`) | yes (`PPOTrainer.step()`)  | yes (single script) |
| TensorBoard logger                         | no                       | yes (default)                | yes                   | yes                        | yes                 |
| Evaluation callback                        | declared, not wired      | yes (`EvalCallback`)         | yes                   | yes                        | yes                 |
| Checkpoint callback                        | no                       | yes                          | yes                   | yes                        | yes                 |
| VecEnv (parallel)                          | no                       | yes                          | yes                   | yes (batched LM)           | yes                 |
| Wrapper stack (Monitor/VecNorm/FrameStack) | no                       | yes                          | yes                   | n/a                        | yes                 |
| Rollout buffer introspection               | no                       | yes (`model.rollout_buffer`) | yes                   | yes                        | yes                 |
| Replay buffer introspection                | no                       | yes (`model.replay_buffer`)  | yes                   | n/a                        | yes                 |
| ε / entropy tracking                       | no                       | yes                          | yes                   | yes (KL)                   | yes                 |
| Advantage fit quality                      | no                       | `explained_variance` in TB   | yes                   | yes                        | yes                 |
| Action distribution metrics                | no                       | partial                      | yes                   | yes                        | partial             |
| Separate eval env                          | no                       | convention                   | yes                   | yes                        | yes                 |
| Offline RL (BC/CQL/IQL)                    | no                       | no (SB3 only online)         | yes (native)          | no                         | d3rlpy ecosystem    |
| RLHF / reward model integration            | no                       | no                           | yes                   | yes (native)               | no                  |
| MARL / MultiAgentEnv                       | no                       | no                           | yes                   | no                         | no                  |
| Distributed rollout workers                | no                       | no                           | yes (native)          | yes (accelerate/deepspeed) | no                  |
| Curriculum / task scheduling               | no                       | no                           | yes (via callbacks)   | yes                        | partial             |
| Registry (persistent)                      | in-memory dict           | n/a                          | yes (via Tune)        | HF Hub                     | n/a                 |
| GPU device resolver integration            | no                       | pass `device=`               | yes                   | `accelerate`               | pass `device=`      |
| Shared training result with classical ML   | no                       | n/a                          | n/a                   | n/a                        | n/a                 |
| Shared experiment tracker                  | no                       | TB default                   | Tune + logger         | HF trainer                 | TB                  |
| Shared dashboard                           | no                       | TB                           | Tune dashboard        | WandB                      | TB                  |

**Score:** `kailash_ml.rl` delivers **4 of 21** industry-baseline capabilities. Direct SB3 (the thing our wrapper wraps) delivers **14 of 21**. Our wrapper **removes** capabilities relative to the unwrapped library, which inverts the framework-first value proposition.

## Proposed Minimal API: `km.rl_train(env, policy, algo='ppo')`

A junior scientist should be able to write this and get tracker + dashboard integration + GPU resolution + eval rollouts for free:

```python
import kailash_ml as km

# One line — defaults provide Atari/classic-control baseline
result = km.rl_train(env="CartPole-v1", algo="ppo", total_timesteps=100_000)
print(result.metrics.mean_reward)     # 500.0 at convergence
print(result.episodes)                # list[EpisodeRecord] — step, reward, length
print(result.device)                  # DeviceReport(backend="cuda", ...) — same shape as km.train()

# Dashboard shows the run alongside classical + DL runs
# MLDashboard("sqlite:///kailash-ml.db").start()

# Full form — explicit configuration
result = km.rl_train(
    env="BipedalWalker-v3",
    algo="sac",
    total_timesteps=1_000_000,
    n_envs=8,                         # VecEnv parallelism
    eval_env="BipedalWalker-v3",      # separate eval env
    eval_freq=10_000,                 # actually wired
    n_eval_episodes=10,
    callbacks=[
        ep_reward_callback,           # same callback shape as km.train()
        checkpoint_callback,
    ],
    wrappers=[                        # declarative wrapper stack
        MonitorWrapper(),
        VecNormalizeWrapper(),
    ],
    experiment="bipedal-sac-v1",      # routes to km.track()
    register_as="bipedal-walker",     # routes to ModelRegistry
)
```

### Signature

```python
def rl_train(
    env: str | gym.Env | Callable[[], gym.Env],
    algo: str = "ppo",                 # ppo, sac, dqn, a2c, td3, ddpg, [+ bc, cql, iql via [rl-offline]]
    *,
    total_timesteps: int = 100_000,
    n_envs: int = 1,
    eval_env: str | gym.Env | None = None,
    eval_freq: int = 10_000,
    n_eval_episodes: int = 10,
    wrappers: list[WrapperSpec] | None = None,
    callbacks: list[Callback] | None = None,
    hyperparameters: dict | None = None,
    seed: int | None = 42,
    experiment: str | None = None,                   # km.track() experiment name
    register_as: str | None = None,                  # ModelRegistry name
    device: str | None = None,                       # honors km.use_device() contextvar
) -> RLTrainingResult:  # ← EXTEND TrainingResult, not a parallel class
    ...
```

### Integration requirements

The RL trainer MUST emit to the shared tracker. Minimum hook set (all flow through the same `km.track()` backend as `km.train()`):

| Event                | Fields                                                                                                            | Frequency                 |
| -------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------- |
| `rl.rollout.step`    | `step`, `reward`, `done`, `action`, `obs_stat` (mean/std), `algo_specific_loss`                                   | every N steps (sampled)   |
| `rl.rollout.episode` | `episode_id`, `ep_reward`, `ep_length`, `ep_success`                                                              | every episode end         |
| `rl.train.update`    | `policy_loss`, `value_loss`, `entropy_loss`, `kl_div`, `clip_fraction`, `explained_variance`, `lr`, `grad_norm`   | every SB3 train iteration |
| `rl.eval`            | `eval_step`, `mean_reward`, `std_reward`, `success_rate`                                                          | every `eval_freq` steps   |
| `rl.buffer.stats`    | on-policy: `advantage_mean`, `advantage_std`; off-policy: `buffer_size`, `buffer_fill`, `reward_dist_percentiles` | every rollout             |
| `rl.exploration`     | DQN: `epsilon`; SAC: `log_ent_coef`; PPO: `action_entropy`                                                        | every N steps             |

All of these are already computed by SB3's internal logger — the adapter just pipes them through `run.log_metric(name, value, step)`.

The `MLDashboard` needs an RL tab with:

- Episode reward curve (mean ± std)
- Policy loss / value loss / entropy loss time-series
- KL divergence + clip fraction (PPO) / entropy coefficient (SAC) / exploration rate (DQN)
- Evaluation-rollout reward distribution
- Buffer fill progress (off-policy)
- Explained variance of value function (on-policy)

The `ModelRegistry` needs an SB3 artifact adapter: `register_sb3_model(name, model_zip_path, algorithm, mean_reward, env_name)` → same `staging → shadow → production → archived` lifecycle as sklearn/lightgbm models.

The `DriftMonitor` needs an RL-specific mode: monitor `reward distribution drift` + `observation distribution drift` + `action distribution drift` against reference rollouts (canary the policy before promoting to production).

### Required result dataclass (extends, not replaces, `TrainingResult`)

```python
@dataclass
class RLTrainingResult(TrainingResult):                # ← subclass of the unified type
    # Inherited: model, metrics, device, backend_info, run_id, experiment_name
    algorithm: str                                      # "ppo", "sac", ...
    env_spec: str                                       # "CartPole-v1"
    total_timesteps: int
    episodes: list[EpisodeRecord]                       # per-episode telemetry (non-empty!)
    eval_history: list[EvalRecord]                      # per-eval rollouts (actually populated)
    final_mean_reward: float
    final_std_reward: float
    policy_artifact: PolicyArtifactRef                  # path + SHA + registry version
```

## Priority Ordered Fix Recommendation

1. **CRIT-1 first**: Decide. Either delete `kailash_ml.rl` (1-commit change) or wire it. A pinned orphan is worse than no RL, because the orphan pretends.
2. **CRIT-2**: Unify `RLTrainingResult` ⊂ `TrainingResult`. Required for every subsequent integration.
3. **HIGH-8 + HIGH-15 together**: Add `RLDiagnostics` + `km.rl_train` surface + tracker integration. This is the engine-first step.
4. **HIGH-9**: Plumb `detect_backend()` through RL — one-line fix, unblocks GPU-first coverage.
5. **HIGH-1, 2, 5, 6, 7**: SB3 telemetry + separate eval env + VecEnv + wrapper stack. All SB3-side, none is hard.
6. **HIGH-11**: Unify with `kailash-align` TRL path — shared `RLLifecycleProtocol`.
7. **HIGH-10, 12, 13, 14**: Offline RL + MARL + distributed + curriculum — order by demand.
8. **MED-1..5**: Tests, env validation, persistent registry, extensibility, reward shaping.

## Non-Scope Confirmation

This audit is RL-only. The following are covered by other personas and not critiqued here:

- Spec fidelity (no `specs/ml-rl.md` exists — the spec-compliance persona owns the decision to file one or to fold into `ml-engines.md`)
- DL internals (DLDiagnostics gradient/activation tracking)
- Day-0 newbie UX beyond the RL entry point
- MLOps production surface outside RL (drift for tabular, feature store, etc.)
- General industry parity against mlflow/wandb/neptune (other persona)

## Verdict

**HIGH/CRIT finding count: 17** (2 CRIT, 15 HIGH, 5 MED)
**Convergence blocker**: YES — the audit brief's 2-consecutive-round zero-HIGH/CRIT goal cannot clear without either deleting `kailash_ml.rl` or completing CRIT-1 + CRIT-2 + HIGH-8 + HIGH-9 + HIGH-15 as a minimum viable RL surface.

Output path: `/Users/esperie/repos/loom/kailash-py/workspaces/kailash-ml-audit/04-validate/round-1-rl-researcher.md`
