# Classical Reinforcement Learning Ecosystem Research

This document inventories the classical RL ecosystem (2023-2026) and analyzes the architectural trade-offs for adding RL support to the Kailash platform: `kailash-ml[rl]` (optional extra) vs `kailash-rl` (separate package).

---

## 1. Classical RL Ecosystem Inventory

### 1.1 Stable-Baselines3 (SB3)

**Repository**: [DLR-RM/stable-baselines3](https://github.com/DLR-RM/stable-baselines3)
**Current version**: 2.8.0a4 (dev), 2.7.1 (stable, March 2026)
**License**: MIT
**Python**: >=3.10 (v2.7.1 was the last to support 3.9)

The dominant library for single-agent classical RL. Follows a sklearn-like API surface.

#### Core Algorithms (stable-baselines3)

| Algorithm | Type                     | Use Case                                        |
| --------- | ------------------------ | ----------------------------------------------- |
| **PPO**   | On-policy, actor-critic  | General-purpose, most popular starting point    |
| **A2C**   | On-policy, actor-critic  | Simpler PPO, good for quick experiments         |
| **DQN**   | Off-policy, value-based  | Discrete action spaces                          |
| **SAC**   | Off-policy, actor-critic | Continuous control, sample-efficient            |
| **TD3**   | Off-policy, actor-critic | Continuous control, twin critics                |
| **DDPG**  | Off-policy, actor-critic | Continuous control (predecessor to TD3)         |
| **HER**   | Replay strategy          | Goal-conditioned tasks (wraps DQN/SAC/TD3/DDPG) |

#### Additional Algorithms (sb3-contrib)

| Algorithm        | Type                       | Use Case                                |
| ---------------- | -------------------------- | --------------------------------------- |
| **TQC**          | Off-policy, distributional | State-of-the-art continuous control     |
| **CrossQ**       | Off-policy, batch-norm     | Efficient continuous control            |
| **TRPO**         | On-policy, trust region    | Conservative policy updates             |
| **ARS**          | Derivative-free            | Simple, fast, no gradient needed        |
| **RecurrentPPO** | On-policy, LSTM            | Partially observable environments       |
| **MaskablePPO**  | On-policy, action mask     | Environments with invalid actions       |
| **QR-DQN**       | Off-policy, distributional | Discrete actions with distributional RL |

#### API Surface

```python
import gymnasium as gym
from stable_baselines3 import PPO

# Create environment and model
env = gym.make("CartPole-v1")
model = PPO("MlpPolicy", env, verbose=1)

# Train
model.learn(total_timesteps=100_000)

# Predict
obs, info = env.reset()
action, _states = model.predict(obs, deterministic=True)

# Save / Load
model.save("ppo_cartpole")
loaded_model = PPO.load("ppo_cartpole", env=env)

# Evaluate
from stable_baselines3.common.evaluation import evaluate_policy
mean_reward, std_reward = evaluate_policy(model, env, n_eval_episodes=10)
```

Key API methods on every algorithm:

| Method                                   | Purpose                                          |
| ---------------------------------------- | ------------------------------------------------ |
| `__init__(policy, env, **kwargs)`        | Create model with policy network and environment |
| `.learn(total_timesteps, callback, ...)` | Train the agent                                  |
| `.predict(observation, deterministic)`   | Get action from observation                      |
| `.save(path)` / `.load(path, env)`       | Persist and restore model                        |
| `.get_env()` / `.set_env(env)`           | Get/set the training environment                 |
| `.get_parameters()`                      | Get model parameters as dict                     |
| `.set_parameters(params)`                | Set model parameters from dict                   |

#### Extension Patterns

1. **Custom policies**: Subclass or pass `policy_kwargs` with `net_arch`, `activation_fn`, custom `features_extractor_class`
2. **Callbacks**: Subclass `BaseCallback` -- hooks at `_on_step()`, `_on_rollout_start()`, `_on_rollout_end()`, `_on_training_start/end()`
3. **Built-in callbacks**: `EvalCallback`, `CheckpointCallback`, `CallbackList`, `StopTrainingOnRewardThreshold`
4. **Replay buffers**: `ReplayBuffer`, `DictReplayBuffer`, `HerReplayBuffer` -- save/load separately via `save_replay_buffer()` / `load_replay_buffer()`
5. **Wrappers**: `Monitor`, `VecNormalize`, `DummyVecEnv`, `SubprocVecEnv`, `VecFrameStack`
6. **Custom environments**: Any `gymnasium.Env` subclass

#### Save Format

SB3 saves models as zip archives containing:

- `data` (JSON): class parameters, hyperparameters, observation/action space
- `pytorch_variables.pth`: optimizer state
- `policy.pth`: policy network weights
- Optionally: replay buffer (separate file), `VecNormalize` stats

### 1.2 Gymnasium

**Repository**: [Farama-Foundation/Gymnasium](https://github.com/Farama-Foundation/Gymnasium)
**Current version**: 1.x (stable, 2025-2026)
**License**: MIT
**Org**: Farama Foundation (successor to OpenAI Gym)
**Downloads**: 18M+ cumulative since Nov 2023; 1M+ monthly in Apr 2025

Gymnasium is the universal standard for RL environment interfaces. Every serious RL library uses it.

#### Core Interface

```python
import gymnasium as gym

class CustomEnv(gym.Env):
    metadata = {"render_modes": ["human", "rgb_array"]}

    def __init__(self, render_mode=None):
        self.observation_space = gym.spaces.Box(low=-1.0, high=1.0, shape=(4,))
        self.action_space = gym.spaces.Discrete(2)
        self.render_mode = render_mode

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        observation = self.observation_space.sample()
        info = {}
        return observation, info

    def step(self, action):
        observation = self.observation_space.sample()
        reward = 1.0
        terminated = False
        truncated = False
        info = {}
        return observation, reward, terminated, truncated, info

    def render(self):
        pass

    def close(self):
        pass
```

Key API change from OpenAI Gym: `step()` returns 5 values `(obs, reward, terminated, truncated, info)` instead of 4 `(obs, reward, done, info)`. This distinguishes natural episode termination from time-limit truncation.

#### Registration System

```python
gymnasium.register(
    id="CustomEnv-v1",
    entry_point="my_package.envs:CustomEnv",
    max_episode_steps=500,
    kwargs={"render_mode": "rgb_array"},
)

env = gymnasium.make("CustomEnv-v1")
```

ID format: `[namespace/](env_name)[-v(version)]`

#### Built-In Environment Families

| Family              | Count | Examples                                                                                                                          | Install                       |
| ------------------- | ----- | --------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| **Classic Control** | 5     | CartPole, MountainCar, Acrobot, Pendulum                                                                                          | Base                          |
| **Toy Text**        | 4     | Blackjack, Taxi, CliffWalking, FrozenLake                                                                                         | Base                          |
| **Box2D**           | 3     | LunarLander, BipedalWalker, CarRacing                                                                                             | `gymnasium[box2d]`            |
| **MuJoCo**          | 11    | Ant, HalfCheetah, Hopper, Humanoid, Walker2D, Swimmer, Reacher, Pusher, InvertedPendulum, InvertedDoublePendulum, HumanoidStandup | `gymnasium[mujoco]`           |
| **Atari**           | 57+   | Pong, Breakout, SpaceInvaders, etc.                                                                                               | `gymnasium[atari]` + `ale-py` |

#### Spaces

| Space                   | Description             | Example                                  |
| ----------------------- | ----------------------- | ---------------------------------------- |
| `Discrete(n)`           | Integer in [0, n)       | Discrete(4) -- 4 actions                 |
| `Box(low, high, shape)` | Float array with bounds | Box(-1, 1, shape=(3,))                   |
| `MultiBinary(n)`        | Binary vector           | MultiBinary(5)                           |
| `MultiDiscrete(nvec)`   | Multiple discrete       | MultiDiscrete([3, 4])                    |
| `Dict(spaces)`          | Dictionary of spaces    | Dict({"pos": Box(...), "vel": Box(...)}) |
| `Tuple(spaces)`         | Tuple of spaces         | Tuple((Discrete(3), Box(...)))           |

#### Vectorized Environments

```python
envs = gymnasium.make_vec("CartPole-v1", num_envs=8)
observations, infos = envs.reset()
observations, rewards, terminations, truncations, infos = envs.step(actions)
```

### 1.3 RL Baselines3 Zoo (rl-zoo3)

**Repository**: [DLR-RM/rl-baselines3-zoo](https://github.com/DLR-RM/rl-baselines3-zoo)
**License**: MIT

A training framework built on SB3 that provides:

1. **Pre-tuned hyperparameters**: YAML configs for common env/algorithm combinations
2. **Hyperparameter optimization**: Optuna integration for automated tuning
3. **Pre-trained agents**: Collection on Hugging Face Hub with videos
4. **Scripts**: `train.py`, `enjoy.py` (evaluate), `record_video.py`, `plot_training.py`
5. **Experiment tracking**: Weights & Biases and Hugging Face integration

This is the practical toolbox for SB3 users who want to move beyond basic examples.

### 1.4 CleanRL

**Repository**: [vwxyzjn/cleanrl](https://github.com/vwxyzjn/cleanrl)
**License**: MIT

Single-file RL implementations for research. NOT a library -- not designed to be imported.

| Algorithm   | File           | Lines |
| ----------- | -------------- | ----- |
| PPO (Atari) | `ppo_atari.py` | ~340  |
| DQN         | `dqn.py`       | ~200  |
| SAC         | `sac.py`       | ~250  |
| DDPG        | `ddpg.py`      | ~200  |
| TD3         | `td3.py`       | ~250  |
| C51         | `c51.py`       | ~250  |
| PPG         | `ppg.py`       | ~350  |

Design philosophy: duplicate code is acceptable to keep each file self-contained. Researchers modify files directly rather than importing and configuring.

**Relevance to Kailash**: CleanRL is a reference/educational tool, not something to wrap or integrate. Its value is in understanding algorithm internals. No API to consume.

### 1.5 Tianshou

**Repository**: [thu-ml/tianshou](https://github.com/thu-ml/tianshou)
**Current version**: 2.x (complete overhaul)
**License**: MIT
**Python**: >=3.11

Modular PyTorch RL library with 20+ algorithms. Tianshou v2 introduced a clean separation between `Algorithm` (learning logic) and `Policy` (action selection).

Supports:

- Online (on-policy and off-policy) RL
- Offline RL
- Experimental multi-agent RL (MARL)
- Experimental model-based RL

**Relevance to Kailash**: Tianshou is more research-oriented and requires Python 3.11+. Its modular design is excellent but its community is smaller than SB3's. SB3 is the pragmatic choice for a framework; Tianshou is the choice for cutting-edge research.

**Performance note**: Recent benchmarks show SB3 and CleanRL attain superhuman performance in ~50% of trials, while Tianshou and RLlib attain it in less than 15%. This is partially due to default hyperparameter choices, but it affects out-of-box experience.

### 1.6 Ray RLlib

**Repository**: [ray-project/ray](https://github.com/ray-project/ray) (rllib subpackage)
**Current version**: 2.54.x
**License**: Apache 2.0

Enterprise-grade, distributed RL. The heaviest option.

Key differentiators:

- **Distributed training**: Scale across clusters via Ray
- **Multi-agent RL**: Native support for independent, collaborative, and adversarial MARL
- **Three scaling axes**: EnvRunners, vectorized sub-environments, Learner actors
- **RLHF prototype**: Active work on LLM alignment via RL (convergence with kailash-align territory)

**Relevance to Kailash**: RLlib is the correct choice when RL needs distributed training across a cluster. However, it brings a massive dependency (the entire Ray ecosystem). For single-machine RL, SB3 is lighter and more reliable. RLlib would be a future integration target, not a core dependency.

### 1.7 PettingZoo (Multi-Agent)

**Repository**: [Farama-Foundation/PettingZoo](https://github.com/Farama-Foundation/PettingZoo)
**License**: MIT
**Org**: Farama Foundation (same as Gymnasium)

The multi-agent equivalent of Gymnasium. Uses the Agent Environment Cycle (AEC) API where agents act sequentially.

Environment families: Atari (multi-player), Butterfly (cooperative), Classic (card/board games).

**Relevance to Kailash**: MARL is a specialized use case. If Kailash supports multi-agent RL in the future, PettingZoo is the standard. Not a v1 concern.

### 1.8 Ecosystem Summary

```
                    ┌─────────────────────────────────────────────────┐
                    │              Gymnasium (Farama)                  │
                    │         Universal environment interface          │
                    │   Classic Control │ MuJoCo │ Atari │ Custom     │
                    └───────────┬───────────────────┬─────────────────┘
                                │                   │
              ┌─────────────────┴──────┐    ┌───────┴─────────────┐
              │    Stable-Baselines3    │    │     PettingZoo      │
              │   Single-agent algos   │    │   Multi-agent envs  │
              │  PPO SAC DQN TD3 A2C   │    │    AEC API          │
              │     + sb3-contrib       │    └─────────────────────┘
              └────────┬───────────────┘
                       │
              ┌────────┴───────────────┐
              │     RL Zoo (rl-zoo3)    │
              │  Hyperparams, training  │
              │  scripts, benchmarks    │
              └────────────────────────┘

  Research tools:                     Enterprise:
  ┌──────────────┐                   ┌──────────────────┐
  │   CleanRL    │                   │    Ray RLlib      │
  │ Single-file  │                   │  Distributed RL   │
  │  reference   │                   │  Multi-agent      │
  └──────────────┘                   │  Cluster-scale    │
  ┌──────────────┐                   └──────────────────┘
  │  Tianshou    │
  │  Modular,    │
  │  research    │
  └──────────────┘
```

---

## 2. Shared Primitives Analysis

Which kailash-ml engines would classical RL actually use?

### 2.1 ModelRegistry -- YES (Strong Fit)

RL policies are models. They need versioning, stage transitions, artifact storage.

| ML Concept                        | RL Equivalent          | ModelRegistry Fit                                                            |
| --------------------------------- | ---------------------- | ---------------------------------------------------------------------------- |
| Trained model                     | Trained policy         | Direct -- save/load policy weights                                           |
| Model version                     | Policy checkpoint      | Direct -- sequential versions                                                |
| Stage (staging/shadow/production) | Policy lifecycle       | Direct -- train/evaluate/deploy                                              |
| Model signature                   | Policy signature       | Needs adaptation -- obs/action spaces instead of feature schemas             |
| ONNX export                       | Policy export          | Partial -- simple policies can export; complex ones (LSTM, attention) cannot |
| Artifact storage                  | Policy + replay buffer | Needs extension -- replay buffers are large binary artifacts                 |

**What works as-is**: Version management, stage transitions, artifact save/load, metadata storage.

**What needs extension**: The `ModelSignature` type assumes tabular input/output schemas. RL policies have observation spaces and action spaces (gymnasium.Space objects). A `PolicySignature` adapter would bridge this.

### 2.2 ExperimentTracker -- DOES NOT EXIST

kailash-ml does not have a standalone ExperimentTracker engine. Experiment tracking is embedded within `TrainingPipeline` and `HyperparameterSearch`. However, RL experiment tracking has significantly different metrics:

| ML Experiment Tracking    | RL Experiment Tracking                                                     |
| ------------------------- | -------------------------------------------------------------------------- |
| loss, accuracy, F1, AUC   | episode_reward, episode_length                                             |
| Training/validation split | No validation split -- reward is the signal                                |
| Epochs                    | Timesteps, episodes, rollouts                                              |
| Single training curve     | Multiple simultaneous curves (reward, loss, entropy, value, KL divergence) |
| Static dataset            | Dynamic environment interaction                                            |

An RL-specific experiment tracker would log:

- Episode rewards (mean, min, max, std) over time
- Episode lengths
- Policy loss, value loss, entropy loss
- Learning rate schedule
- Exploration rate (epsilon for DQN)
- Success rate (for goal-conditioned tasks)
- Environment-specific metrics

SB3 already integrates with TensorBoard and Weights & Biases for this. A Kailash tracker would need to match or wrap these.

### 2.3 InferenceServer -- MAYBE (Limited Fit)

Serving RL policies differs from serving ML models:

| ML Serving                              | RL Serving                                                        |
| --------------------------------------- | ----------------------------------------------------------------- |
| Batch predictions on tabular/image data | Real-time action selection                                        |
| Latency tolerance: 10-100ms             | Latency requirement: <1ms for real-time control                   |
| Stateless prediction                    | Potentially stateful (recurrent policies, observation history)    |
| Model caching (LRU) works well          | Policy caching works, but less useful (usually one active policy) |

The `InferenceServer` model cache and prediction pipeline could work for non-real-time RL inference (e.g., batch evaluation of a policy). But real-time control loops bypass HTTP serving entirely.

### 2.4 FeatureStore -- NO

RL does not use tabular feature engineering. Observations come directly from the environment.

### 2.5 FeatureEngineer -- NO

Same reasoning. No tabular feature engineering in classical RL.

### 2.6 DataExplorer -- NO

RL data is environment interaction (transitions), not tabular datasets. Different exploration paradigm.

### 2.7 DataVersioner -- DOES NOT EXIST (but also NO)

RL uses environments, not datasets. Environment versioning is handled by Gymnasium's registration system. Replay buffer data could theoretically be versioned, but this is an offline RL concern, not a core pattern.

### 2.8 AutoML / HyperparameterSearch -- PARTIAL

RL hyperparameter tuning exists but works differently:

| ML HPO                            | RL HPO                                                          |
| --------------------------------- | --------------------------------------------------------------- |
| Cross-validation score            | Mean episode reward over N episodes                             |
| Fast evaluation (seconds-minutes) | Slow evaluation (minutes-hours per config)                      |
| Optuna/Ray Tune/grid search       | RL Zoo uses Optuna, RLlib uses Ray Tune                         |
| Deterministic evaluation          | Stochastic evaluation (need many episodes for stable estimates) |

The existing `HyperparameterSearch` engine uses Optuna and could be adapted for RL, but the objective function and evaluation loop differ significantly.

### 2.9 TrainingPipeline -- PARTIAL (Different Loop)

The ML training pipeline is: load data -> split -> train -> evaluate -> register. The RL training loop is fundamentally different:

```
ML:   dataset -> model.fit(X_train, y_train) -> model.score(X_test, y_test) -> done
RL:   env.reset() -> [action = policy(obs) -> obs, reward = env.step(action)] x N -> done
```

RL training is an interaction loop, not a batch fit. The `TrainingPipeline` cannot be adapted -- an RL training engine would need to wrap SB3's `model.learn()` instead.

### 2.10 DriftMonitor -- NO

Concept does not transfer. RL environments can change (non-stationarity), but detecting this requires different metrics (reward degradation, not feature distribution shift).

### 2.11 OnnxBridge -- PARTIAL

Simple feed-forward policies (MLP) can be exported to ONNX for fast inference. Recurrent policies (LSTM/GRU), attention-based policies, and policies with complex observation preprocessing cannot be easily exported. SB3 does not natively support ONNX export (community effort exists but is not mature).

### 2.12 Summary Table

| kailash-ml Engine        | RL Usage                      | Verdict                        |
| ------------------------ | ----------------------------- | ------------------------------ |
| **ModelRegistry**        | Store and version policies    | YES -- core primitive          |
| **TrainingPipeline**     | Different training loop       | NO -- needs RL-specific engine |
| **InferenceServer**      | Serve policies for batch eval | MAYBE -- limited real-time use |
| **HyperparameterSearch** | Tune RL hyperparameters       | PARTIAL -- different objective |
| **OnnxBridge**           | Export simple policies        | PARTIAL -- MLP only            |
| FeatureStore             | Not applicable                | NO                             |
| FeatureEngineer          | Not applicable                | NO                             |
| AutoMLEngine             | Not applicable                | NO                             |
| DataExplorer             | Not applicable                | NO                             |
| DriftMonitor             | Not applicable                | NO                             |

**Conclusion**: Only ModelRegistry is a strong shared primitive. Everything else is either inapplicable or needs substantial adaptation.

---

## 3. RL-Specific Primitives

These primitives do not exist in kailash-ml and would need to be built for a Kailash RL offering.

### 3.1 EnvironmentRegistry

Register, discover, and instantiate Gymnasium environments. Wraps `gymnasium.register()` with Kailash metadata.

```python
class EnvironmentRegistry:
    """Register and discover RL environments with metadata."""

    async def register(self, env_id: str, entry_point: str,
                       metadata: dict | None = None, **kwargs) -> None: ...
    async def list(self, filter: dict | None = None) -> list[EnvSpec]: ...
    async def get(self, env_id: str) -> EnvSpec: ...
    async def make(self, env_id: str, **kwargs) -> gymnasium.Env: ...
    async def benchmark(self, env_id: str, n_episodes: int = 100) -> EnvBenchmark: ...
```

Value: Adds persistence (which environments exist, who created them, what metadata), searchability, and benchmarking on top of Gymnasium's flat registry.

### 3.2 PolicyTrainer

Wraps SB3's training loop with Kailash lifecycle management.

```python
class PolicyTrainer:
    """Orchestrate RL training: create env, train policy, evaluate, register."""

    async def train(self, env_id: str, algorithm: str,
                    config: TrainingConfig,
                    experiment_name: str) -> TrainingResult: ...
    async def evaluate(self, policy_name: str, version: int | None = None,
                       n_episodes: int = 100) -> EvalResult: ...
    async def resume(self, experiment_name: str,
                     additional_timesteps: int) -> TrainingResult: ...

@dataclass
class TrainingConfig:
    algorithm: str                 # "PPO", "SAC", "DQN", "TD3", "A2C", etc.
    total_timesteps: int           # Total environment interactions
    hyperparameters: dict          # Algorithm-specific kwargs
    policy_type: str = "MlpPolicy" # "MlpPolicy", "CnnPolicy", "MultiInputPolicy"
    n_envs: int = 1                # Vectorized environments
    eval_freq: int = 10_000        # Evaluate every N timesteps
    eval_episodes: int = 10        # Episodes per evaluation
    checkpoint_freq: int = 50_000  # Checkpoint every N timesteps
    seed: int | None = None
```

### 3.3 RewardShaper

Compose and manage reward functions for custom environments.

```python
class RewardShaper:
    """Compose reward functions for environment customization."""

    def add_component(self, name: str, fn: Callable, weight: float = 1.0) -> None: ...
    def remove_component(self, name: str) -> None: ...
    def compute(self, state: Any, action: Any, next_state: Any, info: dict) -> float: ...
    def as_wrapper(self) -> type[gymnasium.RewardWrapper]: ...
```

Value: Reward shaping is a common pain point. Providing composable reward functions with weights, logging, and versioning would be a genuine framework value-add.

### 3.4 ReplayBufferStore

Persist and manage large replay buffers beyond SB3's in-memory default.

```python
class ReplayBufferStore:
    """Persist replay buffers for offline RL and training resumption."""

    async def save(self, buffer: ReplayBuffer, name: str,
                   policy_name: str, version: int) -> str: ...
    async def load(self, name: str) -> ReplayBuffer: ...
    async def list(self, policy_name: str | None = None) -> list[BufferInfo]: ...
    async def merge(self, names: list[str]) -> ReplayBuffer: ...
```

Value: SB3's `save_replay_buffer()` writes a pickle file. A managed store would handle versioning, deduplication, and buffer composition for offline RL.

### 3.5 EpisodeRecorder

Record and replay agent episodes for debugging, visualization, and demonstration.

```python
class EpisodeRecorder:
    """Record agent episodes for analysis and playback."""

    async def record(self, env: gymnasium.Env, policy, n_episodes: int = 1,
                     render_mode: str = "rgb_array") -> list[Episode]: ...
    async def save(self, episodes: list[Episode], name: str) -> str: ...
    async def load(self, name: str) -> list[Episode]: ...
    async def to_video(self, episode: Episode, output_path: Path) -> Path: ...

@dataclass
class Episode:
    observations: list[Any]
    actions: list[Any]
    rewards: list[float]
    infos: list[dict]
    total_reward: float
    length: int
    frames: list[np.ndarray] | None  # If render_mode="rgb_array"
```

### 3.6 Multi-Agent Coordination

For future MARL support, wrapping PettingZoo.

```python
class MultiAgentCoordinator:
    """Coordinate multi-agent RL training and evaluation."""

    async def register_agents(self, agents: dict[str, PolicyConfig]) -> None: ...
    async def train(self, env_id: str, config: MATrainingConfig) -> MATrainingResult: ...
    async def evaluate(self, env_id: str, n_episodes: int = 100) -> MAEvalResult: ...
```

**Status**: Future work. Not v1.

### 3.7 Sim-to-Real Transfer

Domain randomization and transfer learning utilities.

**Status**: Active research area (DORAEMON, automated DR). Not v1. Would be a specialized skill when real-world robotics users emerge.

---

## 4. Architecture Decision: kailash-ml[rl] vs kailash-rl

### 4.1 Arguments FOR `kailash-ml[rl]` (Optional Extra)

| Argument                                                                                                                              | Weight                            |
| ------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| **Shared ModelRegistry**: Policies are models. One registry for both.                                                                 | STRONG                            |
| **Lighter install**: Users who already have kailash-ml get RL by adding one extra.                                                    | MODERATE                          |
| **Single package to maintain**: Less release overhead.                                                                                | MODERATE                          |
| **kailash-ml already declares [rl]**: The extra already exists in pyproject.toml with `stable-baselines3>=2.3` and `gymnasium>=0.29`. | STRONG (path of least resistance) |
| **Fewer cross-package dependency issues**: No circular dependency risk.                                                               | MODERATE                          |

### 4.2 Arguments FOR `kailash-rl` (Separate Package)

| Argument                                                                                               | Weight                                                |
| ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------- |
| **Different primitives**: Only ModelRegistry is shared. 5+ new engines needed.                         | STRONG                                                |
| **Different users**: RL researchers/roboticists vs tabular data scientists.                            | STRONG                                                |
| **Different training loop**: RL training is fundamentally different from ML training.                  | STRONG                                                |
| **Identity clarity**: "kailash-ml" suggests tabular/classical ML. RL is a different domain.            | MODERATE                                              |
| **Dependency isolation**: Users who want RL without polars/scikit-learn/lightgbm get a leaner install. | WEAK (RL already needs torch, which is the heavy dep) |
| **Independent release cadence**: RL engines can evolve without touching kailash-ml releases.           | MODERATE                                              |

### 4.3 Arguments FOR Keeping GRPO/RLHF in kailash-align

| Argument                                                                                                                                                                                                  | Weight     |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **LLM-specific, not classical RL**: GRPO (Group Relative Policy Optimization), RLHF, and DPO are LLM alignment techniques. They use RL theory but operate on language models, not gymnasium environments. | DEFINITIVE |
| **Different stack**: TRL/transformers/PEFT vs SB3/gymnasium. Zero shared code.                                                                                                                            | DEFINITIVE |
| **Different users**: LLM fine-tuners vs robotics/game AI researchers.                                                                                                                                     | STRONG     |
| **kailash-align already handles this**: SFT, DPO pipeline is built. GRPO would be a natural extension.                                                                                                    | STRONG     |

**Verdict**: GRPO/RLHF stays in kailash-align. This is not debatable -- the techniques share a name with RL but share zero infrastructure.

### 4.4 What Other ML Platforms Do

| Platform             | RL Approach                                                                                                                                                                | Notes                                             |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| **MLflow**           | No dedicated RL support. Model registry works for policies. Experiment tracking logs RL metrics. Not designed for real-time RL.                                            | General-purpose -- RL is a secondary use case     |
| **Weights & Biases** | No dedicated RL package. W&B experiment tracking integrates with SB3/RLlib via callbacks. Video logging for episode recording.                                             | Experiment tracking layer -- agnostic to RL vs ML |
| **Ray (RLlib)**      | Separate library within Ray ecosystem. `ray[rllib]` is an extra, but RLlib has its own algorithms, environments, and distributed training. NOT part of Ray's ML libraries. | Separate library with its own identity            |
| **Hugging Face**     | `huggingface_hub` stores SB3 models. RL Zoo integrates with HF Hub. No dedicated RL package.                                                                               | Storage layer only                                |
| **Neptune.ai**       | RL experiment tracking via general-purpose logger. No RL-specific features.                                                                                                | Experiment tracking only                          |

**Pattern**: No major ML platform bundles classical RL into their ML package. RL is either a separate library (RLlib) or treated as a use case that existing tools (experiment tracking, model registry) can serve without RL-specific code.

### 4.5 The Decisive Factors

The architectural decision comes down to three questions:

**Q1: How many engines are shared?**
Answer: One (ModelRegistry). Out of 9 kailash-ml engines, only ModelRegistry directly applies to RL. Five are inapplicable, two are partially applicable with significant adaptation, and one (ExperimentTracker) does not exist yet.

**Q2: Is the training loop compatible?**
Answer: No. ML training is `model.fit(X, y)`. RL training is `policy.learn(env, timesteps)`. The `TrainingPipeline` engine cannot be adapted -- a new `PolicyTrainer` engine is needed.

**Q3: Who are the users?**
Answer: Different personas. RL users are roboticists, game AI researchers, control engineers, and operations researchers. ML users are data scientists building classifiers, regressors, and ranking models. Overlap exists (both use PyTorch, both track experiments), but the workflows are distinct.

### 4.6 Recommendation

**`kailash-ml[rl]` for v1, with a path to `kailash-rl` if RL adoption grows.**

Rationale:

1. **The `[rl]` extra already exists** in pyproject.toml. Declaring `stable-baselines3>=2.3` and `gymnasium>=0.29` as optional dependencies is already done. The question is only about engines.

2. **Start with 2-3 RL engines inside kailash-ml**, gated behind the `[rl]` extra:
   - `PolicyTrainer` -- wraps SB3 training loop
   - `EnvironmentRegistry` -- wraps Gymnasium registry with persistence
   - `EpisodeRecorder` -- record and replay agent episodes
   - ModelRegistry is already shared (no new code needed)

3. **Do NOT build all 7+ RL primitives upfront**. RewardShaper, ReplayBufferStore, MultiAgentCoordinator, and sim-to-real are future work. Build when users demand them.

4. **If RL grows to 5+ engines**, extract to `kailash-rl` as a separate package that depends on `kailash-ml` (for ModelRegistry) and `kailash` (for core workflow/runtime).

This follows the kailash-align precedent: kailash-align depends on kailash-ml for ModelRegistry but is a separate package because it has 6 distinct engines and a fundamentally different workflow. Classical RL has the same potential trajectory, but starting with 2-3 engines does not justify a separate package yet.

---

## 5. Dependency Analysis

### 5.1 SB3 Dependency Chain

```
stable-baselines3 >=2.3
    ├── torch >=2.3          (~1.5-2.0 GB)
    ├── gymnasium >=0.29.1   (~5-10 MB)
    ├── numpy >=1.20         (~30-50 MB, likely already installed)
    ├── cloudpickle          (~50 KB)
    ├── pandas               (~50-100 MB, likely already installed)
    └── matplotlib           (~40-60 MB)
```

### 5.2 Overlap with kailash-ml Dependencies

| Dependency   | kailash-ml           | kailash-ml[rl]  | Shared?                    |
| ------------ | -------------------- | --------------- | -------------------------- |
| torch        | Only in `[dl]` extra | Required by SB3 | YES -- if `[dl]` installed |
| numpy        | Required (base)      | Required by SB3 | YES                        |
| scipy        | Required (base)      | Not needed      | NO                         |
| scikit-learn | Required (base)      | Not needed      | NO                         |
| polars       | Required (base)      | Not needed      | NO                         |
| lightgbm     | Required (base)      | Not needed      | NO                         |
| gymnasium    | Not in base          | Required by SB3 | NO (new dep)               |
| matplotlib   | Not required         | Required by SB3 | NO (new dep)               |
| pandas       | Not required         | Required by SB3 | NO (new dep)               |
| cloudpickle  | Not required         | Required by SB3 | NO (new dep)               |

### 5.3 Install Size Scenarios

#### Scenario A: `pip install kailash-ml[rl]` (from scratch)

```
kailash-ml base deps:     ~195 MB (polars, scikit-learn, lightgbm, numpy, scipy, plotly, ONNX)
kailash-ml[dl] deps:      ~1.5-2.0 GB (torch, transformers, etc.)
kailash-ml[rl] deps:      ~10-20 MB (stable-baselines3, gymnasium -- torch already counted)
                          ─────────────
Total:                    ~1.7-2.2 GB
```

#### Scenario B: `pip install kailash-ml[rl]` (kailash-ml[dl] already installed)

```
Incremental:              ~10-20 MB (stable-baselines3, gymnasium, matplotlib, pandas)
```

torch is already installed via `[dl]`. The `[rl]` extra pulls `kailash-ml[dl]` transitively, so torch is always present.

#### Scenario C: Hypothetical `pip install kailash-rl` (standalone, no kailash-ml)

```
kailash (core):           ~5-10 MB
torch:                    ~1.5-2.0 GB
stable-baselines3:        ~10 MB
gymnasium:                ~5-10 MB
numpy + matplotlib:       ~80-100 MB
                          ─────────────
Total:                    ~1.6-2.1 GB
```

This is slightly lighter than Scenario A (no polars, scikit-learn, lightgbm), but torch dominates the install size regardless. The savings from dropping kailash-ml's base deps (~195 MB) are marginal compared to torch's ~1.5-2.0 GB.

### 5.4 Can RL Work Without kailash-ml?

Technically yes, if a standalone `kailash-rl` imported only `kailash` (core) and brought its own minimal model registry. But this would mean:

1. Duplicating ModelRegistry functionality (versioning, artifact storage, stage transitions)
2. Losing ONNX bridge for exportable policies
3. Losing HyperparameterSearch integration (Optuna wiring)
4. Creating a maintenance burden for two model registries

**The pragmatic answer**: RL should depend on kailash-ml. The ~195 MB overhead for kailash-ml's base deps (polars, scikit-learn, etc.) is acceptable given that torch already costs 10x more.

---

## 6. Implementation Roadmap (If Proceeding)

### Phase 1: Minimal Viable RL (2-3 sessions)

1. **PolicyTrainer engine** -- wrap SB3's `model.learn()`, `model.predict()`, `model.save()`/`.load()` with Kailash lifecycle
2. **EnvironmentRegistry** -- persist env registrations in SQLite/PostgreSQL via ConnectionManager
3. **ModelRegistry adapter** -- `PolicySignature` class that maps obs/action spaces to ModelSignature
4. **Basic experiment logging** -- log episode rewards, lengths, losses to ConnectionManager tables

### Phase 2: Evaluation and Recording (1-2 sessions)

5. **EpisodeRecorder** -- record, save, replay episodes with video export
6. **PolicyEvaluator** -- systematic evaluation across environments with statistical reporting
7. **RL Zoo integration** -- import pre-tuned hyperparameters from rl-zoo3

### Phase 3: Advanced (Future, demand-driven)

8. **RewardShaper** -- composable reward functions
9. **ReplayBufferStore** -- persistent, versioned replay buffers for offline RL
10. **Kaizen integration** -- RL policy as a Kaizen agent tool (policy advises actions)
11. **Multi-agent (PettingZoo)** -- if MARL demand emerges
12. **Distributed training (RLlib)** -- if cluster-scale demand emerges

### Effort Estimates (Autonomous Execution)

| Phase                          | Sessions      | Notes                                                               |
| ------------------------------ | ------------- | ------------------------------------------------------------------- |
| Phase 1                        | 2-3           | PolicyTrainer is the critical engine; EnvironmentRegistry is simple |
| Phase 2                        | 1-2           | Builds on Phase 1 infrastructure                                    |
| Phase 3                        | Demand-driven | Each item is 1-2 sessions independently                             |
| **Total to viable RL support** | **3-5**       |                                                                     |

---

## 7. Risk Assessment

### 7.1 Risk: Low Adoption

Classical RL has a smaller user base than tabular ML or LLM fine-tuning. Building 5+ engines for a niche audience may not justify the maintenance cost.

**Mitigation**: Start with `kailash-ml[rl]` and 2-3 engines. Only invest further if users materialize.

### 7.2 Risk: SB3 API Instability

SB3 is mature but still evolving (2.7 -> 2.8 introduced breaking changes around Python version support and PyTorch version requirements).

**Mitigation**: Pin `stable-baselines3>=2.3,<3.0` and handle API differences via version checks.

### 7.3 Risk: Torch Version Conflicts

Both `kailash-ml[dl]` and `kailash-ml[rl]` depend on torch, but via different paths. SB3 requires `torch>=2.3`, while kailash-ml[dl] requires `torch>=2.2`.

**Mitigation**: Already aligned -- both accept torch 2.3+. The `kailash-ml[rl]` extra transitively pulls `kailash-ml[dl]`, ensuring a single torch installation.

### 7.4 Risk: Identity Confusion with kailash-align

Users may confuse "reinforcement learning" (classical RL, gymnasium, game AI) with "RLHF" (LLM alignment). The names overlap.

**Mitigation**: Clear documentation. "kailash-ml[rl] is for training agents to play games, control robots, and optimize operations. kailash-align is for fine-tuning language models."

### 7.5 Risk: Gymnasium Breaking Changes

Gymnasium 1.x introduced breaking changes from 0.x (5-tuple step return). SB3 2.7+ requires gymnasium >=0.29.1,<1.3.0.

**Mitigation**: Follow SB3's compatibility matrix. Do not independently pin gymnasium.

---

## 8. Conclusions

1. **The classical RL ecosystem is mature and stable.** SB3 + Gymnasium is the dominant stack for single-agent RL. RLlib serves distributed/multi-agent use cases. The ecosystem is not fragmented.

2. **Only one kailash-ml engine (ModelRegistry) is directly reusable for RL.** The other 8 engines are either inapplicable or need fundamental redesign for RL workflows.

3. **RL needs 5-7 new primitives** that do not exist in kailash-ml: PolicyTrainer, EnvironmentRegistry, EpisodeRecorder, RewardShaper, ReplayBufferStore, and optionally MultiAgentCoordinator and sim-to-real utilities.

4. **`kailash-ml[rl]` is the right starting architecture.** The `[rl]` extra already exists. Start with 2-3 engines. If RL grows to 5+ engines with distinct users, extract to `kailash-rl` (following the kailash-align precedent).

5. **GRPO/RLHF stays in kailash-align.** LLM alignment techniques share a name with RL but share zero infrastructure (TRL vs SB3, transformers vs gymnasium). This is settled.

6. **Total new dependency weight for `[rl]` is ~10-20 MB incremental** (assuming `[dl]` is already installed for torch). The dependency overhead is negligible.

7. **Estimated effort: 3-5 autonomous sessions** for a viable Phase 1+2 RL offering.

---

## Sources

- [Stable-Baselines3 Documentation](https://stable-baselines3.readthedocs.io/)
- [Stable-Baselines3 GitHub](https://github.com/DLR-RM/stable-baselines3)
- [SB3-Contrib Documentation](https://sb3-contrib.readthedocs.io/)
- [Gymnasium Documentation](https://gymnasium.farama.org/index.html)
- [Gymnasium GitHub](https://github.com/Farama-Foundation/Gymnasium)
- [RL Baselines3 Zoo GitHub](https://github.com/DLR-RM/rl-baselines3-zoo)
- [CleanRL GitHub](https://github.com/vwxyzjn/cleanrl)
- [Tianshou GitHub](https://github.com/thu-ml/tianshou)
- [Ray RLlib Documentation](https://docs.ray.io/en/latest/rllib/index.html)
- [PettingZoo Documentation](https://pettingzoo.farama.org/index.html)
- [Top 10 RL Tools 2026](https://www.devopsschool.com/blog/top-10-reinforcement-learning-tools-in-2025-features-pros-cons-comparison/)
- [6 Best RL Tools 2026](https://www.hud.ai/resources/best-reinforcement-learning-tools)
- [MLflow Model Registry](https://mlflow.org/docs/latest/ml/model-registry/)
- [W&B RL Observability](https://wandb.ai/wandb_fc/genai-research/reports/Observability-tools-for-reinforcement-learning--VmlldzoxNDE3MzExMw)
- [On Interchangeable DRL Implementations (2025)](https://arxiv.org/html/2503.22575v2)
- [Sim-to-Real Transfer Review (2025)](https://www.sciencedirect.com/science/article/abs/pii/S0921889025004245)
