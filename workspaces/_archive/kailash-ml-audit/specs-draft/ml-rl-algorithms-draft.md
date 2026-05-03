# Spec (draft) — ML Reinforcement Learning: Algorithm Adapters

Version: 1.0.0 (draft)

**Status:** DRAFT — round-2 Phase-A spec authoring. Not yet authoritative.
**Package:** `kailash-ml` (target: 1.0.0).
**Module:** `kailash_ml.rl.algorithms`.
**Parent spec:** `ml-rl-core-draft.md`.
**Companion spec:** `ml-rl-align-unification-draft.md`.
**Closes round-1 findings:** HIGH-1, HIGH-4, HIGH-10, HIGH-14, MED-4, MED-5.

## 1. Scope

This file enumerates the first-party algorithm adapters shipped with `kailash-ml` 1.0.0. Each adapter:

1. Registers a name with `km.rl.register_algorithm(name, AdapterClass)`.
2. Resolves via `algo="<name>"` in `km.rl_train()`.
3. Declares the required buffer kind, required policy interface, required external extra(s).
4. Exposes a `hyperparameters` schema validated at construction.
5. Emits the canonical `rl.*` metric families (see `ml-rl-core-draft.md` §7.1) via its SB3 / d3rlpy / TRL backend.

Extensibility: user-defined adapters register via `register_algorithm("my-algo", MyAdapter)`. The registry is tenant-scoped (key `kailash_ml:v1:{tenant_id}:rl_algo:{name}`) so per-tenant custom algorithms cannot leak across tenants.

## 2. Adapter Protocol

```python
@runtime_checkable
class AlgorithmAdapter(Protocol):
    name: ClassVar[str]                    # "ppo", "sac", ...
    paradigm: ClassVar[Literal["on-policy", "off-policy", "offline", "rlhf"]]
    buffer_kind: ClassVar[Literal["rollout", "replay", "dataset", "preference"]]
    requires_extra: ClassVar[tuple[str, ...]]   # e.g. ("rl",) or ("rl-offline",)
    default_policy: ClassVar[str]          # "mlp" / "cnn" / "nature-cnn" / "lm" (for RLHF)
    default_hyperparameters: ClassVar[dict[str, Any]]

    def __init__(
        self,
        *,
        env_fn: Callable[[], gym.Env] | None,
        policy: PolicyProtocol | str | None,
        buffer: RolloutBuffer | ReplayBuffer | OfflineDataset | None,
        hyperparameters: dict[str, Any],
        device: DeviceReport,
        seed: int,
        tenant_id: str | None,
    ) -> None: ...

    def build(self) -> Any:              # returns the underlying trainer instance
        ...
    def learn(
        self,
        total_timesteps: int,
        *,
        callbacks: list[Callback],
        eval_env_fn: Callable[[], gym.Env] | None,
        eval_freq: int,
        n_eval_episodes: int,
    ) -> RLTrainingResult: ...
    def save(self, path: Path) -> PolicyArtifactRef: ...
    @classmethod
    def load(cls, ref: PolicyArtifactRef) -> "AlgorithmAdapter": ...
```

Adapters MUST surface the canonical metric families via `_KailashRLCallback` (see parent spec §8.1). Adapters MUST NOT silently swallow SB3 / TRL / d3rlpy internal logger output.

## 3. On-Policy Classical RL

### 3.1 `ppo` — Proximal Policy Optimization

| Field               | Value                                                                                                                                                                                                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paradigm            | on-policy actor-critic                                                                                                                                                                                                                                                    |
| Buffer kind         | `rollout`                                                                                                                                                                                                                                                                 |
| Required extra      | `[rl]` (stable-baselines3 ≥ 2.3)                                                                                                                                                                                                                                          |
| Paper               | Schulman et al. 2017 — "Proximal Policy Optimization Algorithms"                                                                                                                                                                                                          |
| SB3 equivalent      | `stable_baselines3.PPO`                                                                                                                                                                                                                                                   |
| Default policy      | `mlp`                                                                                                                                                                                                                                                                     |
| Hyperparameter keys | `n_steps` (2048), `batch_size` (64), `n_epochs` (10), `learning_rate` (3e-4), `gamma` (0.99), `gae_lambda` (0.95), `clip_range` (0.2), `clip_range_vf` (None), `vf_coef` (0.5), `ent_coef` (0.0), `max_grad_norm` (0.5), `target_kl` (None), `normalize_advantage` (True) |
| Metrics surfaced    | `rl.train.update.policy_loss`, `.value_loss`, `.entropy_loss`, `.kl_div`, `.clip_fraction`, `.value_clip_fraction`, `.explained_variance`; `rl.exploration.action_entropy`                                                                                                |

**Per-algo GAE defaults pinned.** The `RolloutBuffer` is constructed by the PPOAdapter with `gae_lambda=0.95, gamma=0.99` — the adapter MUST NOT inherit the user's `RolloutBuffer(gamma=0.99)` default without re-asserting. See §3.5 below for the binding rule.

**`clip_range_vf` semantics.** Optional value-function clip range. When `None` (default), no VF clipping; matches SB3 default. When a float, VF loss is clipped symmetrically per the Schulman 2017 paper equation (8). Emits `rl.train.update.value_clip_fraction` metric ONLY when `clip_range_vf is not None` — adapters pass `None` rather than hallucinate zero. Separate from `clip_range` (policy clip) — the two kwargs are independent.

### 3.2 `a2c` — Advantage Actor-Critic

| Field               | Value                                                                                                                                                                             |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paradigm            | on-policy actor-critic (synchronous A2C)                                                                                                                                          |
| Buffer kind         | `rollout`                                                                                                                                                                         |
| Required extra      | `[rl]`                                                                                                                                                                            |
| Paper               | Mnih et al. 2016 — "Asynchronous Methods for Deep Reinforcement Learning" (synchronous variant)                                                                                   |
| SB3 equivalent      | `stable_baselines3.A2C`                                                                                                                                                           |
| Default policy      | `mlp`                                                                                                                                                                             |
| Hyperparameter keys | `n_steps` (5), `learning_rate` (7e-4), `gamma` (0.99), `gae_lambda` (1.0), `ent_coef` (0.0), `vf_coef` (0.5), `max_grad_norm` (0.5), `rms_prop_eps` (1e-5), `use_rms_prop` (True) |
| Metrics surfaced    | `rl.train.update.policy_loss`, `.value_loss`, `.entropy_loss`, `.explained_variance`; `rl.exploration.action_entropy`                                                             |

### 3.3 `trpo` — Trust Region Policy Optimization

| Field               | Value                                                                                                                                                                                                                              |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paradigm            | on-policy actor-critic (constrained trust region)                                                                                                                                                                                  |
| Buffer kind         | `rollout`                                                                                                                                                                                                                          |
| Required extra      | `[rl]` (stable-baselines3-contrib)                                                                                                                                                                                                 |
| Paper               | Schulman et al. 2015 — "Trust Region Policy Optimization"                                                                                                                                                                          |
| SB3 equivalent      | `sb3_contrib.TRPO`                                                                                                                                                                                                                 |
| Default policy      | `mlp`                                                                                                                                                                                                                              |
| Hyperparameter keys | `n_steps` (2048), `batch_size` (128), `gamma` (0.99), `cg_max_steps` (15), `cg_damping` (0.1), `line_search_shrinking_factor` (0.8), `line_search_max_iter` (10), `n_critic_updates` (10), `gae_lambda` (0.95), `target_kl` (0.01) |
| Metrics surfaced    | same as PPO plus `rl.train.update.kl_before_update`, `.kl_after_update`, `.line_search_success`                                                                                                                                    |

### 3.4 Per-Algo GAE Defaults — Adapter-Injected, Not Buffer-Inherited

Every on-policy adapter constructs its `RolloutBuffer` with ITS OWN `gae_lambda` + `gamma`, NOT the buffer-class defaults. A user who constructs `RolloutBuffer(gamma=0.99)` and then picks A2C MUST see `gae_lambda=1.0`, not `0.95`.

| Algo   | `gamma` | `gae_lambda` | Notes                                                  |
| ------ | ------- | ------------ | ------------------------------------------------------ |
| `ppo`  | 0.99    | 0.95         | Schulman 2017 default                                  |
| `a2c`  | 0.99    | 1.0          | Matches asynchronous A2C literature — MC-style returns |
| `trpo` | 0.99    | 0.95         | Same as PPO                                            |

```python
# DO — adapter injects its own defaults
class PPOAdapter:
    def _make_buffer(self, buffer_size, obs_space, action_space) -> RolloutBuffer:
        return RolloutBuffer(
            buffer_size=buffer_size, obs_space=obs_space, action_space=action_space,
            gae_lambda=0.95, gamma=0.99, tenant_id=self._tenant_id,
        )

class A2CAdapter:
    def _make_buffer(self, buffer_size, obs_space, action_space) -> RolloutBuffer:
        return RolloutBuffer(
            buffer_size=buffer_size, obs_space=obs_space, action_space=action_space,
            gae_lambda=1.0, gamma=0.99, tenant_id=self._tenant_id,
        )

# DO NOT — inherit whatever the caller constructed
buffer = RolloutBuffer(gamma=0.99)  # implicit gae_lambda=0.95
adapter = A2CAdapter(buffer=buffer)  # A2C sees 0.95, diverges from A2C literature
```

**Why:** The `RolloutBuffer` default `gae_lambda=0.95` is the PPO convention; silently using it for A2C shifts every A2C run's advantage estimator off-convention. Senior users comparing against A2C literature see silent divergence. Adapter-injected construction closes the gap.

## 4. Off-Policy Classical RL

### 4.1 `dqn` — Deep Q-Network

| Field               | Value                                                                                                                                                                                                                                                                                                                         |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paradigm            | off-policy value-based (discrete action)                                                                                                                                                                                                                                                                                      |
| Buffer kind         | `replay`                                                                                                                                                                                                                                                                                                                      |
| Required extra      | `[rl]`                                                                                                                                                                                                                                                                                                                        |
| Paper               | Mnih et al. 2015 — "Human-level control through deep RL"                                                                                                                                                                                                                                                                      |
| SB3 equivalent      | `stable_baselines3.DQN`                                                                                                                                                                                                                                                                                                       |
| Default policy      | `mlp` (or `nature-cnn` for Atari)                                                                                                                                                                                                                                                                                             |
| Hyperparameter keys | `learning_rate` (1e-4), `buffer_size` (1_000_000), `learning_starts` (50_000), `batch_size` (32), `tau` (1.0), `gamma` (0.99), `train_freq` (4), `gradient_steps` (1), `target_update_interval` (10_000), `exploration_fraction` (0.1), `exploration_initial_eps` (1.0), `exploration_final_eps` (0.05), `max_grad_norm` (10) |
| Metrics surfaced    | `rl.train.update.q_loss`, `.target_mean`, `.td_error_mean`, `.td_error_std`; `rl.buffer.stats.size`, `.fill_ratio`, `.reward_p50/p90`; `rl.exploration.epsilon`                                                                                                                                                               |

### 4.2 `sac` — Soft Actor-Critic

| Field               | Value                                                                                                                                                                                                                                                                  |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paradigm            | off-policy maximum-entropy actor-critic (continuous action)                                                                                                                                                                                                            |
| Buffer kind         | `replay`                                                                                                                                                                                                                                                               |
| Required extra      | `[rl]`                                                                                                                                                                                                                                                                 |
| Paper               | Haarnoja et al. 2018 — "Soft Actor-Critic"                                                                                                                                                                                                                             |
| SB3 equivalent      | `stable_baselines3.SAC`                                                                                                                                                                                                                                                |
| Default policy      | `mlp`                                                                                                                                                                                                                                                                  |
| Hyperparameter keys | `learning_rate` (3e-4), `buffer_size` (1_000_000), `learning_starts` (100), `batch_size` (256), `tau` (0.005), `gamma` (0.99), `train_freq` (1), `gradient_steps` (1), `ent_coef` ("auto"), `target_update_interval` (1), `target_entropy` ("auto"), `use_sde` (False) |
| Metrics surfaced    | `rl.train.update.actor_loss`, `.critic_loss`, `.ent_coef`, `.ent_coef_loss`; `rl.buffer.stats.*`; `rl.exploration.log_ent_coef`                                                                                                                                        |

### 4.3 `td3` — Twin Delayed Deep Deterministic Policy Gradient

| Field               | Value                                                                                                                                                                                                                                                           |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paradigm            | off-policy deterministic actor-critic (continuous action, twin critics)                                                                                                                                                                                         |
| Buffer kind         | `replay`                                                                                                                                                                                                                                                        |
| Required extra      | `[rl]`                                                                                                                                                                                                                                                          |
| Paper               | Fujimoto et al. 2018 — "Addressing Function Approximation Error in Actor-Critic Methods"                                                                                                                                                                        |
| SB3 equivalent      | `stable_baselines3.TD3`                                                                                                                                                                                                                                         |
| Default policy      | `mlp`                                                                                                                                                                                                                                                           |
| Hyperparameter keys | `learning_rate` (1e-3), `buffer_size` (1_000_000), `learning_starts` (100), `batch_size` (100), `tau` (0.005), `gamma` (0.99), `train_freq` ((1, "episode")), `gradient_steps` (-1), `policy_delay` (2), `target_policy_noise` (0.2), `target_noise_clip` (0.5) |
| Metrics surfaced    | `rl.train.update.actor_loss`, `.critic_loss`, `.q_overestimation_gap`; `rl.buffer.stats.*`                                                                                                                                                                      |

### 4.4 `ddpg` — Deep Deterministic Policy Gradient

| Field               | Value                                                                                                                                                                                                      |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paradigm            | off-policy deterministic actor-critic (continuous action)                                                                                                                                                  |
| Buffer kind         | `replay`                                                                                                                                                                                                   |
| Required extra      | `[rl]`                                                                                                                                                                                                     |
| Paper               | Lillicrap et al. 2015 — "Continuous control with deep reinforcement learning"                                                                                                                              |
| SB3 equivalent      | `stable_baselines3.DDPG`                                                                                                                                                                                   |
| Default policy      | `mlp`                                                                                                                                                                                                      |
| Hyperparameter keys | `learning_rate` (1e-3), `buffer_size` (1_000_000), `learning_starts` (100), `batch_size` (100), `tau` (0.005), `gamma` (0.99), `train_freq` ((1, "episode")), `gradient_steps` (-1), `action_noise` (None) |
| Metrics surfaced    | `rl.train.update.actor_loss`, `.critic_loss`; `rl.buffer.stats.*`                                                                                                                                          |

## 5. Offline RL (requires `[rl-offline]`)

The `[rl-offline]` extra depends on `d3rlpy>=2.0` (MIT) OR a Foundation-internal implementation if the user prefers dependency-minimal. The adapter protocol is identical; backend selection resolves via `RL_OFFLINE_BACKEND` env var (default `d3rlpy`).

### 5.1 `bc` — Behavioral Cloning

| Field               | Value                                                                                            |
| ------------------- | ------------------------------------------------------------------------------------------------ |
| Paradigm            | offline, supervised imitation                                                                    |
| Buffer kind         | `dataset`                                                                                        |
| Required extra      | `[rl-offline]` (or just `[rl]` — BC is trivial; ships natively)                                  |
| Paper               | Pomerleau 1991 — "Efficient Training of Artificial Neural Networks for Autonomous Navigation"    |
| SB3 equivalent      | n/a (sklearn/torch imitation; native implementation)                                             |
| Default policy      | `mlp`                                                                                            |
| Hyperparameter keys | `learning_rate` (1e-3), `batch_size` (256), `n_epochs` (10), `weight_decay` (0), `dropout` (0.0) |
| Metrics surfaced    | `rl.train.update.bc_loss`, `.action_mse`, `.action_nll`                                          |

### 5.2 `cql` — Conservative Q-Learning

| Field               | Value                                                                                                                                                                |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paradigm            | offline value-based (conservative Q lower-bound)                                                                                                                     |
| Buffer kind         | `dataset`                                                                                                                                                            |
| Required extra      | `[rl-offline]`                                                                                                                                                       |
| Paper               | Kumar et al. 2020 — "Conservative Q-Learning for Offline Reinforcement Learning"                                                                                     |
| Backend equivalent  | `d3rlpy.algos.CQL`                                                                                                                                                   |
| Default policy      | `mlp`                                                                                                                                                                |
| Hyperparameter keys | `actor_learning_rate` (1e-4), `critic_learning_rate` (3e-4), `batch_size` (256), `gamma` (0.99), `alpha` (1.0), `conservative_weight` (5.0), `n_action_samples` (10) |
| Metrics surfaced    | `rl.train.update.actor_loss`, `.critic_loss`, `.conservative_loss`, `.cql_alpha`; `rl.eval.d4rl_normalized_score`                                                    |

### 5.3 `iql` — Implicit Q-Learning

| Field               | Value                                                                                                                                                                                |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Paradigm            | offline actor-critic (expectile regression)                                                                                                                                          |
| Buffer kind         | `dataset`                                                                                                                                                                            |
| Required extra      | `[rl-offline]`                                                                                                                                                                       |
| Paper               | Kostrikov et al. 2022 — "Offline Reinforcement Learning with Implicit Q-Learning"                                                                                                    |
| Backend equivalent  | `d3rlpy.algos.IQL`                                                                                                                                                                   |
| Default policy      | `mlp`                                                                                                                                                                                |
| Hyperparameter keys | `actor_learning_rate` (3e-4), `critic_learning_rate` (3e-4), `value_learning_rate` (3e-4), `batch_size` (256), `gamma` (0.99), `tau` (0.005), `expectile` (0.7), `weight_temp` (3.0) |
| Metrics surfaced    | `rl.train.update.actor_loss`, `.critic_loss`, `.value_loss`, `.advantage_weighted_nll`; `rl.eval.d4rl_normalized_score`                                                              |

### 5.4 Standard D4RL metrics (emitted for all offline algos)

- `rl.eval.d4rl_normalized_score` — per the D4RL benchmark's reference min/max per env.
- `rl.eval.mean_return` — raw mean cumulative return.
- `rl.eval.success_rate` — when the env supplies `info["is_success"]`.
- `rl.eval.length_mean` — mean episode length in the offline eval rollout.

## 6. RLHF (dispatch to kailash-align)

These names are registered on `km.rl_train` but dispatch to `kailash_align` TRL trainers under a shared `RLLifecycleProtocol`. See `ml-rl-align-unification-draft.md` for the full contract. Only the adapter table appears here.

### 6.1 `dpo` — Direct Preference Optimization

| Field               | Value                                                                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Paradigm            | RLHF (preference-based, closed-form)                                                                                           |
| Buffer kind         | `preference`                                                                                                                   |
| Required extra      | `kailash-align` (peer package)                                                                                                 |
| Paper               | Rafailov et al. 2023 — "Direct Preference Optimization"                                                                        |
| Backend             | `trl.DPOTrainer` via `kailash_align.method_registry["DPOTrainer"]`                                                             |
| Default policy      | `lm` (HuggingFace AutoModelForCausalLM)                                                                                        |
| Required kwargs     | `reference_model`, `preference_dataset`                                                                                        |
| Hyperparameter keys | `beta` (0.1), `learning_rate` (5e-7), `num_train_epochs` (1), `batch_size` (4), `max_prompt_length` (512), `max_length` (1024) |
| Metrics surfaced    | `rl.train.update.dpo_loss`, `.reward_accuracy`, `.reward_margin`, `.kl_from_reference`; aligns with `AlignmentDiagnostics`     |

### 6.2 `ppo-rlhf` — PPO with Reward Model (TRL)

| Field               | Value                                                                                                                                                                                                |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paradigm            | RLHF (online, reward-model advantages)                                                                                                                                                               |
| Buffer kind         | `rollout` (token-level)                                                                                                                                                                              |
| Required extra      | `kailash-align`                                                                                                                                                                                      |
| Paper               | Ouyang et al. 2022 — "Training language models to follow instructions with human feedback"                                                                                                           |
| Backend             | `trl.PPOTrainer` via `kailash_align.method_registry["PPOTrainer"]`                                                                                                                                   |
| Default policy      | `lm`                                                                                                                                                                                                 |
| Required kwargs     | `reward_model`, `reference_model`                                                                                                                                                                    |
| Hyperparameter keys | `learning_rate` (1.4e-5), `init_kl_coef` (0.2), `target_kl` (6.0), `gamma` (1.0), `lam` (0.95), `cliprange` (0.2), `cliprange_value` (0.2), `vf_coef` (0.1), `mini_batch_size` (1), `ppo_epochs` (4) |
| Metrics surfaced    | structurally IDENTICAL to classical PPO (§3.1): same metric keys under `rl.train.update.*`; additionally `rl.train.update.kl_from_reference`, `.reward_model_score`                                  |

### 6.3 `rloo` — REINFORCE Leave-One-Out

| Field               | Value                                                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Paradigm            | RLHF (online, variance-reduced REINFORCE with leave-one-out baseline)                                                     |
| Buffer kind         | `rollout`                                                                                                                 |
| Required extra      | `kailash-align`                                                                                                           |
| Paper               | Ahmadian et al. 2024 — "Back to Basics: Revisiting REINFORCE Style Optimization for Learning from Human Feedback in LLMs" |
| Backend             | `trl.RLOOTrainer`                                                                                                         |
| Required kwargs     | `reward_model`, `reference_model`                                                                                         |
| Hyperparameter keys | `learning_rate` (1e-6), `rloo_k` (2), `kl_coef` (0.05), `temperature` (0.7), `response_length` (53)                       |
| Metrics surfaced    | `rl.train.update.rloo_loss`, `.baseline_reward`, `.kl_from_reference`, `.reward_model_score`                              |

### 6.4 `online-dpo` — Online DPO

| Field               | Value                                                                                                   |
| ------------------- | ------------------------------------------------------------------------------------------------------- |
| Paradigm            | RLHF (online preferences via a judge / reward model)                                                    |
| Buffer kind         | `rollout` + dynamic preference generation                                                               |
| Required extra      | `kailash-align`                                                                                         |
| Paper               | Guo et al. 2024 — "Direct Language Model Alignment from Online AI Feedback"                             |
| Backend             | `trl.OnlineDPOTrainer`                                                                                  |
| Required kwargs     | `reference_model`, `judge` OR `reward_model`                                                            |
| Hyperparameter keys | `beta` (0.1), `learning_rate` (5e-7), `num_generations` (4), `max_new_tokens` (64), `temperature` (0.9) |
| Metrics surfaced    | same as `dpo` plus `rl.train.update.generation_latency`, `.judge_agreement`                             |

## 7. Hyperparameter Validation

Each adapter ships a `HYPERPARAMETER_SCHEMA: dict[str, HyperparameterSpec]` where `HyperparameterSpec` is:

```python
@dataclass(frozen=True)
class HyperparameterSpec:
    name: str
    kind: Literal["float", "int", "bool", "str", "tuple", "enum", "callable"]
    default: Any
    min_value: float | int | None = None
    max_value: float | int | None = None
    enum_values: tuple[Any, ...] | None = None
    required: bool = False
    description: str = ""
```

At adapter construction, every key in the user-supplied `hyperparameters` dict MUST match a known spec. Unknown keys raise `ValueError` listing allowed names — this closes HIGH-2's failure mode (silently-unused `eval_freq`) at adapter scope too: a parameter that looks configured MUST have a consumer or be rejected.

**Numeric finite-check (`ParamValueError`)**: every numeric hyperparameter (int / float) MUST pass `math.isfinite(value)` at construction. NaN / ±Inf MUST raise `kailash_ml.errors.ParamValueError` (cross-cutting, TrackingError family per `ml-tracking-draft.md §9.1`; multi-inherits `ValueError` per Decision 4 so `except ValueError` continues to catch). Silent coercion to `None` / `0.0` / `str(value)` is BLOCKED. Mirrors the same rule on the non-RL engine path (`ml-engines-v2-draft.md §3.2 MUST 3a`) AND on the tracking path (`ml-tracking-draft.md §4.1`).

## 8. Extensibility — `register_algorithm`

```python
km.rl.register_algorithm(
    name: str,
    adapter_cls: type[AlgorithmAdapter],
    *,
    tenant_id: str | None = None,
    replace: bool = False,
) -> None
```

- Tenant-scoped: the same `name` MAY map to different adapters per tenant. Registry key: `kailash_ml:v1:{tenant_id}:rl_algo:{name}`.
- `replace=True` required to overwrite an existing name (even within the same tenant).
- `adapter_cls` MUST satisfy `AlgorithmAdapter` Protocol (runtime check at registration).
- Registering a name that collides with a first-party name (`ppo`, `sac`, ...) WITHOUT `replace=True` raises `ValueError` with the list of reserved names.

Closes MED-4 (SB3 allowlist was closed in 0.17.0).

## 9. Curriculum + Task Scheduling (optional)

### 9.1 `TaskScheduler`

```python
@runtime_checkable
class TaskScheduler(Protocol):
    def next_env_spec(
        self,
        *,
        step: int,
        eval_history: list[EvalRecord],
    ) -> str | gym.Env | Callable[[], gym.Env] | None: ...
```

`None` return signals "no change; keep current env".

Plugged in via `km.rl_train(..., task_scheduler=MyScheduler())`. `km.rl_train` invokes the scheduler after every `eval_freq` evaluation and (when the return is non-None) swaps the env via a guarded hand-off:

1. Checkpoint current policy + buffer.
2. Close current envs gracefully.
3. Construct new envs from the spec.
4. Restore policy (NOT buffer — buffer resets for on-policy; buffer retained for off-policy).
5. Resume training.

### 9.2 Shipped schedulers

- `LinearDifficultyScheduler(env_specs, switch_at_steps)` — switches env at preset step thresholds.
- `EvalThresholdScheduler(env_specs, mean_reward_thresholds)` — switches env when eval mean_reward exceeds a threshold.
- `CosineAnnealScheduler(env_specs, total_steps)` — smooth transition via env-specific reward scaling.

Closes HIGH-14 with documented scope (hook, not automatic curriculum learning).

## 10. Reward Shaping Hooks (closes MED-5)

Reward shaping lives at the wrapper layer per `ml-rl-core-draft.md` §4.3. The `RewardWrapper` spec accepts a user callable:

```python
@dataclass
class RewardWrapperSpec:
    fn: Callable[[float, dict, int], float]      # (reward, info, step) -> shaped_reward
    potential_fn: Callable[[dict], float] | None = None   # potential-based shaping φ(s)
    gamma: float = 0.99
```

When `potential_fn` is supplied, the wrapper applies `r' = r + γ·φ(s') − φ(s)` (potential-based shaping per Ng et al. 1999 — policy-invariant under optimal policy).

## 11. Algorithm Parity Matrix

| Algo       | `km.rl_train`      | SB3     | RLlib   | CleanRL | d3rlpy | TRL            |
| ---------- | ------------------ | ------- | ------- | ------- | ------ | -------------- |
| ppo        | yes                | yes     | yes     | yes     | no     | partial (rlhf) |
| a2c        | yes                | yes     | yes     | yes     | no     | no             |
| trpo       | yes (contrib)      | contrib | yes     | no      | no     | no             |
| dqn        | yes                | yes     | yes     | yes     | yes    | no             |
| sac        | yes                | yes     | yes     | yes     | yes    | no             |
| td3        | yes                | yes     | yes     | yes     | yes    | no             |
| ddpg       | yes                | yes     | yes     | no      | yes    | no             |
| bc         | yes                | n/a     | yes     | no      | yes    | partial        |
| cql        | yes ([rl-offline]) | no      | yes     | no      | yes    | no             |
| iql        | yes ([rl-offline]) | no      | yes     | no      | yes    | no             |
| dpo        | yes (dispatch)     | no      | no      | no      | no     | yes            |
| ppo-rlhf   | yes (dispatch)     | no      | partial | no      | no     | yes            |
| rloo       | yes (dispatch)     | no      | no      | no      | no     | yes            |
| online-dpo | yes (dispatch)     | no      | no      | no      | no     | yes            |

13 algorithms shipped; matches the round-1 rl-researcher demand (PPO/SAC/DQN/A2C/TD3/DDPG + BC/CQL/IQL + 4 RLHF).

## 12. Adapter Testing Contract

### 12.1 Tier 1 (per adapter)

Each adapter MUST have:

- `test_<algo>_adapter_construction` — `AlgorithmAdapter` Protocol `isinstance` check at runtime.
- `test_<algo>_hyperparameter_validation_rejects_unknown_keys`.
- `test_<algo>_default_policy_satisfies_policy_protocol`.
- `test_<algo>_build_returns_backend_instance`.
- `test_<algo>_save_load_roundtrip` (Tier 1 via tmp_path — no training).

### 12.2 Tier 2 (integration; per adapter family)

- **On-policy family** (`ppo`, `a2c`, `trpo`): `test_on_policy_adapters_run_100_steps_cartpole.py` — each runs 100 steps on CartPole, emits ≥3 metric families, returns non-empty `episodes`.
- **Off-policy family** (`dqn`, `sac`, `td3`, `ddpg`): `test_off_policy_adapters_run_100_steps.py` — each runs 100 steps on Pendulum / CartPole (discrete for DQN, continuous for others), emits `rl.buffer.stats.*`.
- **Offline family** (`bc`, `cql`, `iql`): `test_offline_adapters_run_1_epoch.py` — each trains for 1 epoch on a small synthetic polars dataset, emits `rl.eval.*`.
- **RLHF family**: see `ml-rl-align-unification-draft.md` §4.

## 13. Extras Matrix

```toml
# pyproject.toml
[project.optional-dependencies]
rl = [
    "stable-baselines3>=2.3",
    "sb3-contrib>=2.3",             # TRPO, MaskablePPO, ...
    "gymnasium>=0.29",
]
rl-offline = [
    "kailash-ml[rl]",
    "d3rlpy>=2.0",
]
rl-distributed = [                  # deferred; opt-in only
    "kailash-ml[rl]",
    "ray[rllib]>=2.10",
]
```

RLHF adapters require `kailash-align` installed (peer dependency; not auto-pulled by `[rl]`).

## 14. Non-Goals (explicit deferral, not silent stub)

- **MaskablePPO / QR-DQN / ARS from sb3_contrib** — easy to add; deferred to 0.19.0.
- **Decision Transformer** — deferred; `[rl-offline]` BC + d3rlpy covers the dominant offline use case; DT adds a distinct policy protocol (sequence model) that warrants its own spec section.
- **MuZero / EfficientZero** — model-based-RL with learned world model; out-of-scope for v1.
- **Population-based training (PBT)** — orthogonal to algorithm adapters; lives in `ml-hyperparameter-search` spec.

Spec revisions:

- **2026-04-21 DRAFT** — initial draft.
