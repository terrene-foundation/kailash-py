# Spec (draft) — ML Reinforcement Learning: Core Surface

Version: 1.0.0 (draft)
**Status:** DRAFT — round-2 Phase-A spec authoring. Not yet authoritative.
**Package:** `kailash-ml` (target: 1.0.0).
**Modules:** `kailash_ml.rl` (public surface), `kailash_ml.diagnostics.rl` (adapter), top-level `km.rl_train` engine entry.
**Companion specs:** `ml-rl-algorithms-draft.md`, `ml-rl-align-unification-draft.md`.
**Closes round-1 findings:** CRIT-1, CRIT-2, HIGH-1, HIGH-2, HIGH-3, HIGH-4, HIGH-5, HIGH-6, HIGH-7, HIGH-8, HIGH-9, HIGH-15, MED-1, MED-2, MED-3, MED-5.
**Closes round-2b open-TBDs:** RC-01 (EnvPool), RC-02 (MARL), RC-03 (distributed rollout), RC-04 (curriculum), RC-05 (MBPO/Dreamer), RA-02 (MaskablePPO), RA-03 (Decision Transformer).
**Closes round-2b newbie-ux gaps:** G-RL-DIAG-SURFACE (full class surface), G-README-QUICKSTART-MISSING (canonical quick-start + regression test).
**Cross-SDK:** companion to `specs/alignment-training.md` + `specs/alignment-diagnostics.md`.
**Approved decisions respected:** Decision 4 (DDP/FSDP rank-0-only emission), Decision 7 (`n_envs=1` literal default), Decision 8 (Lightning lock-in), Decision 13 (extras: `[rl]`, `[rl-offline]`, `[rl-envpool]`, `[rl-distributed]`, `[rl-bridge]`).

## 1. Scope + Non-Goals

### 1.1 In-scope

The RL surface MUST cover, in v1 of the wired module:

1. **On-policy classical RL** — PPO, A2C, TRPO (via `sb3_contrib`).
2. **Off-policy classical RL** — DQN, SAC, TD3, DDPG.
3. **Offline RL** — Behavioral Cloning (BC), Conservative Q-Learning (CQL), Implicit Q-Learning (IQL). CQL/IQL require the `[rl-offline]` extra (d3rlpy or CORL).
4. **Model-based RL primitive support** — the `RolloutBuffer` / `ReplayBuffer` / `PolicyProtocol` abstractions are expressive enough that a user can plug an MBPO or Dreamer-style world model on top. First-party MBPO/Dreamer adapters are deferred.
5. **RLHF dispatch** — `km.rl_train(..., algo="dpo" | "ppo-rlhf" | "rloo" | "online-dpo")` dispatches to `kailash-align` TRL trainers behind a shared `RLLifecycleProtocol`. See `ml-rl-align-unification-draft.md`.
6. **Environment abstraction** — passthrough `gymnasium.Env` + `SyncVectorEnv` + `AsyncVectorEnv` + offline dataset env wrapper.
7. **Tenant-scoped state** — per `rules/tenant-isolation.md`, every buffer / registry / artifact keyed by `tenant_id`.
8. **Diagnostics adapter** — `RLDiagnostics` satisfies `kailash.diagnostics.protocols.Diagnostic`.
9. **Tracker + dashboard integration** — RL runs are invisible-free through `km.track()` + `MLDashboard`.
10. **Checkpointing + resume** — policy, optimizer, buffer, env RNG all checkpoint; `resume_from=` path.
11. **Device-aware backend** — consult `detect_backend()` per `ml-backends.md`; `DeviceReport` emitted on `RLTrainingResult`.

### 1.2 Out-of-scope (v1; explicit deferral per `rules/zero-tolerance.md` Rule 2)

These MUST NOT be silently stubbed. Each deferred item is either absent from the public surface OR raises a typed `FeatureNotYetSupportedError` with an upstream issue reference.

1. **Frontier envelope parallelism (EnvPool C++ native) — RC-01.** `gymnasium.vector` is sufficient for v1. Post-1.0.0 via `[rl-envpool]` extra. A user passing `envpool=True` to `km.rl_train` in 1.0.0 MUST raise `FeatureNotYetSupportedError("EnvPool backend deferred to 1.1.0; install kailash-ml[rl-envpool] when available. Upstream tracking: issue #RC-01.")`.
2. **Jax JIT backend for rollouts** — `torch` only in 1.0.0. `device="xla"` continues to resolve via `detect_backend()` but a full Jax rollout backend is post-1.0.
3. **Multi-agent RL (MARL / PettingZoo) — RC-02.** Non-goal. `kailash-ml` does not ship PettingZoo adapters, does not accept `pettingzoo.ParallelEnv`, and does not plan to. Users needing MARL MUST use RLlib directly; this is DOCUMENTED and will not change across the 1.x line. Passing a PettingZoo env raises `RLEnvIncompatibleError` with an explicit "MARL is a documented non-goal" remediation.
4. **Distributed rollout workers across machines (rllib-style) — RC-03.** 1.0.0 supports in-process `SyncVectorEnv` + in-process subprocesses via `AsyncVectorEnv`. Multi-node distributed rollout is post-1.0 via the `[rl-distributed]` extra (Ray-backed actor-placement rollout workers). A user passing `distributed=True` in 1.0.0 MUST raise `FeatureNotYetSupportedError("multi-node distributed rollout deferred to 1.2.0; install kailash-ml[rl-distributed] when available. Upstream tracking: issue #RC-03.")`.
5. **Curriculum / task scheduling — RC-04.** 1.0.0 ships a simple `TaskScheduler` hook (declarative `curriculum=[TaskSpec(...), ...]` list consumed by a callback that swaps env / hyperparameter tier at scheduled `total_env_steps` thresholds). Full automatic curriculum learning (ACL, POET, unsupervised environment design) is post-1.0; the hook is the primitive on which post-1.0 ACL builds.
6. **Model-based RL with first-party world models (MBPO, Dreamer-V3) — RC-05.** 1.0.0 ships the primitive Protocols (`RolloutBufferProtocol`, `ReplayBufferProtocol`, `PolicyProtocol`, `ValueProtocol`, `QFunctionProtocol`) that are expressive enough for a user to plug MBPO or Dreamer-style world models on top. First-party MBPO / Dreamer-V3 adapters are post-1.0 under `[rl]` (no new extra required; they build on the same primitives).
7. **`sb3_contrib.MaskablePPO` — RA-02.** Post-1.0 via `sb3_contrib` which is already a sibling of stable-baselines3 under the `[rl]` extra. 1.0.0 ships `ppo` (standard) + `a2c` + `trpo`. MaskablePPO lands in 0.19.0+ as `algo="maskable-ppo"` once `sb3_contrib` is pinned — no additional extra needed, requires only the adapter class at `kailash_ml.rl.algorithms.maskable_ppo_adapter`.
8. **Decision Transformer / Trajectory Transformer — RA-03.** Post-1.0. The Decision Transformer architecture treats RL as sequence modelling under a return-conditioned causal transformer and has a DISTINCT Protocol (no `env.step` rollout loop). 1.0.0 does not attempt to collapse Decision Transformer into the `AlgorithmAdapter` shape; it gets its own Protocol and facade in 1.2.0+ under `[rl]`.

## 2. Delete-or-Wire Decision — WIRE (default)

`kailash_ml/rl/` exists today as a pinned orphan (see `tests/regression/test_rl_orphan_guard.py`). This spec presents BOTH options with trade-offs, then selects WIRE.

### 2.1 Option A — DELETE

**Action:** Remove `packages/kailash-ml/src/kailash_ml/rl/` entirely; remove `[rl]` extra; remove the orphan-guard regression test; update `__init__.py` to not reference RL. The `kailash-align` TRL surface remains as the sole RL-like path (narrow: RLHF over language models only).

**Pros:**

- 1-commit change, no invariant budget burn.
- `rules/orphan-detection.md` §3 ("Removed = Deleted, Not Deprecated") cleanly satisfied.
- Narrows the ML platform's 2026 positioning to supervised + LLM-alignment; honest about capability.

**Cons:**

- The audit brief's Section 1 non-negotiable #4 ("Full lifecycle coverage" — classical ML, DL, RL, AutoML, serving, drift, tracking) becomes unsatisfiable. RL is the primary classical-control / robotics / bandits / recommender-rerank entry point. Deleting it cedes the entire classical RL use-case to SB3 / RLlib / CleanRL.
- The kailash-align TRL path (RLHF) structurally IS RL — it has a policy, a reward model, advantages, KL penalties, clipped objectives. A user doing "baseline bandit with PPO + fine-tune LLM with TRL PPO" in the same experiment gets two APIs, two trackers, two registries. The align path itself benefits from a shared `RLLifecycleProtocol`.
- Research teams evaluating kailash-ml against rllib / Acme / TorchRL see a gap and leave.

### 2.2 Option B — WIRE (selected)

**Action:** Migrate `kailash_ml.rl` into the canonical public surface: add `km.rl_train()` engine entry, `RLDiagnostics` adapter, tenant-scoped `RolloutBuffer`/`ReplayBuffer`/`PolicyRegistry`, `RLTrainingResult ⊂ TrainingResult`, full tracker + dashboard + registry integration, GPU device resolution. Remove `tests/regression/test_rl_orphan_guard.py` and replace with the anti-regression test battery in §18.

**Pros:**

- Closes all 17 HIGH/CRIT findings from round-1-rl-researcher.md.
- Matches industry baseline (SB3 + CleanRL feature set) without requiring the complexity of rllib.
- Makes the align TRL path a first-class RL participant — unified tracker, dashboard, registry, device resolver.
- Mechanical enforcement: once `RLTrainer` has a production call site in `engines/` AND a Tier 2 wiring test, `rules/orphan-detection.md` §1 + `rules/facade-manager-detection.md` §1 close cleanly.

**Cons:**

- Invariant-heavy: tenant_id propagation across buffer / registry / artifact store + SB3 callback plumbing + RLDiagnostics + tracker contextvar hook + device resolver + resume-from-checkpoint = ~6 simultaneous invariants. Fits `rules/autonomous-execution.md` §Capacity budget at the upper bound; MUST be sharded (Tier-D of round-1 synthesis has D1a + D1b).
- ~600 LOC load-bearing across two shards.

### 2.3 Decision

**WIRE** is the default per the audit brief Section 1 non-negotiable #4 (Full lifecycle coverage) and per the round-1 synthesis Tier-D shard. The remaining sections of this spec assume the WIRE decision.

## 3. Unified Public API — `km.rl_train`

### 3.1 Signature

```python
def rl_train(
    env: str | gym.Env | Callable[[], gym.Env] | OfflineDataset,
    *,
    policy: PolicyProtocol | str | None = None,       # None → default per-algo policy
    algo: str = "ppo",                                  # ppo / a2c / trpo / dqn / sac / td3 / ddpg /
                                                        # bc / cql / iql /
                                                        # dpo / ppo-rlhf / rloo / online-dpo
    total_timesteps: int = 100_000,
    n_envs: int | Literal["auto"] = 1,           # LITERAL default: 1 (Decision 7). "auto" → os.cpu_count() explicitly.
    eval_env: str | gym.Env | Callable[[], gym.Env] | None = None,
    eval_freq: int = 10_000,
    n_eval_episodes: int = 10,
    wrappers: list[WrapperSpec] | None = None,
    callbacks: list[Callback] | None = None,
    hyperparameters: dict[str, Any] | None = None,
    seed: int | None = 42,
    experiment: str | None = None,              # routes to km.track(experiment=...)
    register_as: str | None = None,             # routes to ModelRegistry.register(name=...)
    tracker: Optional[ExperimentRun] = None,    # overrides ambient km.track() contextvar; reads via get_current_run()
    model_registry: ModelRegistry | None = None,
    device: str | None = None,                  # honors km.use_device() contextvar
    tenant_id: str | None = None,               # honors km.use_tenant() contextvar; required if model is multi_tenant
    resume_from: str | Path | PolicyArtifactRef | None = None,
    # RLHF-only kwargs — dispatched to align:
    reward_model: Any | None = None,            # torch.nn.Module or HF model ref
    reference_model: Any | None = None,
    preference_dataset: pl.DataFrame | Path | None = None,
    # Offline-RL-only kwarg:
    dataset: OfflineDataset | pl.DataFrame | Path | None = None,
    # Parallel-rollout kwargs:
    workers: int = 0,                           # 0 = in-process SyncVectorEnv; >0 = AsyncVectorEnv subprocess
    parallel_envs: int | None = None,           # alias for n_envs; prefer n_envs (emits DeprecationWarning when both supplied)
) -> RLTrainingResult: ...
```

#### 3.1.1 `n_envs` Default Contract (Decision 7 — pinned)

The literal default is `n_envs=1`. The function MUST NOT silently auto-scale parallel environments — power users opt in via `n_envs="auto"` which dispatches to `os.cpu_count()` EXPLICITLY through a single resolution point:

```python
# Inside rl_train():
def _resolve_n_envs(n_envs: int | Literal["auto"]) -> int:
    """Decision 7 — explicit opt-in for CPU auto-scaling.

    `n_envs=1` is the literal default — reproducible, debuggable,
    works on single-core CI. `n_envs="auto"` is a power-user opt-in
    that MUST dispatch to os.cpu_count() explicitly; silent auto-scaling
    on default construction is BLOCKED.
    """
    if n_envs == "auto":
        resolved = os.cpu_count() or 1
        _logger.info("rl_train.n_envs.auto_resolved", cpu_count=resolved)
        return resolved
    if not isinstance(n_envs, int) or n_envs < 1:
        raise ValueError(f"n_envs must be a positive int or 'auto'; got {n_envs!r}")
    return n_envs
```

Rationale:

- **Reproducibility.** `n_envs=1` means the user's seed produces the same trajectory across machines regardless of core count. `"auto"` couples trajectory shape to the machine, which is acceptable ONLY with an explicit opt-in.
- **CI / debug correctness.** SB3's vectorized envs have subtle ordering effects under `SyncVectorEnv`; beginners hit these first when they run the same seed on a laptop and a GPU node.
- **Explicit beats clever.** `"auto"` resolved at the entry point with a logger event makes the effective `n_envs` visible in the tracker metadata (`rl_train.n_envs.auto_resolved` event carries the resolved value; tracker captures `run.metadata["n_envs_resolved"]`).

**BLOCKED rationalizations:**

- "Beginners want their CPUs used automatically"
- "Other frameworks auto-scale by default"
- "`n_envs=1` is slow on a 32-core box"
- "The `"auto"` default is just as explicit as `1`"

Sibling specs referencing `n_envs`: `ml-rl-algorithms-draft.md` § per-algo adapter rollout sizing, `ml-engines-v2-draft.md` §10.2 Language-Specific Translations.

### 3.2 Return type — `RLTrainingResult ⊂ TrainingResult`

```python
@dataclass
class RLTrainingResult(TrainingResult):
    # Inherited from TrainingResult (specs/ml-engines.md § TrainingResult):
    #   model, metrics, device: DeviceReport, backend_info, run_id, experiment_name
    algorithm: str                         # "ppo", "sac", "dpo", ...
    env_spec: str                          # "CartPole-v1" or "dataset:/path/to/d4rl.parquet"
    total_timesteps: int
    episode_reward_mean: float
    episode_reward_std: float
    episode_length_mean: float
    policy_entropy: float | None           # PPO/A2C/TRPO only
    value_loss: float | None               # actor-critic algos
    kl_divergence: float | None            # PPO (train-time proxy), DPO (train-time), SAC (ent coef proxy)
    explained_variance: float | None       # on-policy actor-critic
    replay_buffer_size: int | None         # off-policy
    total_env_steps: int
    episodes: list[EpisodeRecord]          # MUST be non-empty at training end
    eval_history: list[EvalRecord]         # MUST be non-empty if eval_freq elapses
    policy_artifact: PolicyArtifactRef     # path + SHA + registry version
```

**Invariants:**

- Every `rl_train()` call that runs at least one complete rollout MUST populate `episodes` with length ≥ 1. A zero-length `episodes` at training end is a `rules/zero-tolerance.md` Rule 2 violation (mirror of HIGH-1 finding).
- Every `rl_train()` call with `eval_freq <= total_timesteps` MUST populate `eval_history` with ≥ 1 `EvalRecord` (closes HIGH-2 finding that `eval_freq` was declared but never wired).
- `policy_entropy`, `value_loss`, `kl_divergence`, `explained_variance`, `replay_buffer_size` MAY be `None` when not applicable to the algorithm; they MUST NOT be hallucinated zero.

### 3.3 Newbie one-liner

```python
import kailash_ml as km

result = km.rl_train(env="CartPole-v1", algo="ppo", total_timesteps=100_000)
print(result.episode_reward_mean)   # converges to ~500 on CartPole
print(result.device)                # DeviceReport(backend="cuda"|"mps"|"cpu", ...)
# MLDashboard already has the run — zero extra code.
```

## 4. Environment Abstraction

### 4.1 `EnvironmentProtocol`

A runtime-checkable Protocol mirroring `gymnasium.Env`. Any class satisfying:

```python
class EnvironmentProtocol(Protocol):
    observation_space: gym.Space
    action_space: gym.Space
    def reset(self, *, seed: int | None = None) -> tuple[ObsT, dict]: ...
    def step(self, action: ActT) -> tuple[ObsT, float, bool, bool, dict]: ...
    def close(self) -> None: ...
```

is acceptable. `gymnasium.Env` satisfies it by construction.

### 4.2 Vectorization

- `SyncVectorEnv` (default when `n_envs > 1` and `workers == 0`) — in-process loop; debuggable; lower throughput.
- `AsyncVectorEnv` (when `workers > 0`) — subprocess-per-env; higher throughput; slower startup.
- `n_envs=1` bypasses vectorization entirely (single `gym.Env`).

### 4.3 Wrapper stack (closes HIGH-7)

Declarative `wrappers=[WrapperSpec(...)]` list applied in order inside `_make_env`. v1 ships:

| WrapperSpec                 | gym/SB3 target                                  | Use case                      |
| --------------------------- | ----------------------------------------------- | ----------------------------- |
| `MonitorWrapper`            | `stable_baselines3.common.monitor.Monitor`      | Required for TB `ep_rew_mean` |
| `VecNormalizeWrapper`       | `stable_baselines3.common.vec_env.VecNormalize` | MuJoCo, continuous control    |
| `FrameStackWrapper`         | `gymnasium.wrappers.FrameStack`                 | Atari                         |
| `AtariPreprocessingWrapper` | `gymnasium.wrappers.AtariPreprocessing`         | Atari                         |
| `TimeLimitWrapper`          | `gymnasium.wrappers.TimeLimit`                  | Bounded episode length        |
| `RewardWrapper`             | user-defined `fn(reward, obs) -> reward`        | Reward shaping (closes MED-5) |

Each is a `dataclass` with algorithm-agnostic kwargs. Unknown wrapper kind → `ValueError` listing allowed names.

### 4.4 `EnvironmentRegistry`

Tenant-scoped:

```python
class EnvironmentRegistry:
    def __init__(self, *, tenant_id: str | None = None) -> None: ...
    async def register(self, spec: EnvironmentSpec) -> None:
        # Tenant-scoped key per rules/tenant-isolation.md §1:
        #   kailash_ml:v1:{tenant_id}:env:{spec.name}
        # MUST smoke-test via gym.make(spec.name).reset() — closes MED-2.
        ...
    async def resolve(self, name: str) -> gym.Env: ...
    async def list_envs(self) -> list[EnvironmentSpec]: ...
```

Offline datasets register via `OfflineDatasetEnvSpec` (pointer to a polars-readable artifact) so `rl_train(env="dataset:my-d4rl-v1", algo="cql")` resolves uniformly.

## 5. Policy / Value / Q Abstractions

### 5.1 Protocols

```python
@runtime_checkable
class PolicyProtocol(Protocol):
    observation_space: gym.Space
    action_space: gym.Space
    def forward(self, obs: torch.Tensor) -> torch.distributions.Distribution: ...
    def predict(self, obs: np.ndarray, deterministic: bool = False) -> tuple[np.ndarray, dict]: ...

@runtime_checkable
class ValueProtocol(Protocol):
    def forward(self, obs: torch.Tensor) -> torch.Tensor: ...

@runtime_checkable
class QFunctionProtocol(Protocol):
    def forward(self, obs: torch.Tensor, action: torch.Tensor) -> torch.Tensor: ...
```

Any SB3 `ActorCriticPolicy`, `QNetwork`, or user-defined `torch.nn.Module` that matches these signatures is accepted.

### 5.2 Factory helpers

```python
km.rl.make_mlp_policy(obs_space, act_space, hidden=[64, 64], activation="tanh") -> PolicyProtocol
km.rl.make_cnn_policy(obs_space, act_space, arch="nature-cnn") -> PolicyProtocol
km.rl.make_q_network(obs_space, act_space, hidden=[256, 256]) -> QFunctionProtocol
```

String architecture shortcuts: `"mlp"`, `"cnn"`, `"nature-cnn"`, `"mlp-small"`, `"mlp-large"`.

### 5.3 Policy registration

`km.rl.register_policy(name: str, factory: Callable[[gym.Space, gym.Space], PolicyProtocol]) -> None` — symmetric with `register_estimator`; closes MED-4 for policies.

## 6. Buffer Abstractions

### 6.1 `RolloutBuffer` (on-policy)

Tenant-scoped; GAE advantage computation; polars-backed sampling statistics for `RLDiagnostics`.

```python
class RolloutBuffer:
    def __init__(
        self,
        buffer_size: int,
        obs_space: gym.Space,
        action_space: gym.Space,
        *,
        gae_lambda: float = 0.95,
        gamma: float = 0.99,
        tenant_id: str | None = None,
    ) -> None: ...
    def add(self, obs, action, reward, done, value, log_prob) -> None: ...
    def compute_returns_and_advantages(self, last_value: float, last_done: bool) -> None: ...
    def get_batch(self, batch_size: int) -> RolloutBatch: ...
    def summary(self) -> dict:
        """advantage_mean, advantage_std, return_mean, value_mean — for RLDiagnostics."""
```

Storage key (when persistent): `kailash_ml:v1:{tenant_id}:rollout_buffer:{run_id}`.

### 6.2 `ReplayBuffer` (off-policy)

```python
class ReplayBuffer:
    def __init__(
        self,
        buffer_size: int,
        obs_space: gym.Space,
        action_space: gym.Space,
        *,
        prioritized: bool = False,
        alpha: float = 0.6,
        beta: float = 0.4,
        n_step: int = 1,                       # n-step returns (Rainbow-DQN / MuZero default)
        gamma: float = 0.99,                    # discount for n-step bootstrap
        tenant_id: str | None = None,
    ) -> None: ...
    def add(self, obs, action, reward, next_obs, done) -> None: ...
    def sample(
        self,
        batch_size: int,
        beta: float | None = None,
        n_step: int | None = None,              # per-call override (default buffer n_step)
    ) -> ReplayBatch: ...
    def summary(self) -> dict:
        """size, fill_ratio, reward_mean, reward_percentiles, td_error_dist — for RLDiagnostics."""
    # Priority-tree persistence (see §9.1)
    def checkpoint(self) -> bytes: ...
    @classmethod
    def from_checkpoint(cls, payload: bytes) -> "ReplayBuffer": ...
```

Storage key: `kailash_ml:v1:{tenant_id}:replay_buffer:{run_id}`.

#### MUST: N-Step Returns

n-step bootstrap formula: `R_t^{(n)} = Σ_{k=0..n-1} γ^k r_{t+k} + γ^n Q(s_{t+n}, a_{t+n})`. When `n_step > 1`, `sample(...)` returns transitions where `reward` is the n-step discounted sum and `next_obs` / `done` are from step `t+n`. `done` inside the n-step window truncates the sum (no beyond-terminal bootstrap).

Adapter defaults (see `ml-rl-algorithms.md` §3 for the per-algo binding):

- **DQN / Rainbow-DQN**: `n_step=3`
- **MuZero / EfficientZero**: `n_step=5`
- **SAC / TD3**: `n_step=1` (bit-compat with SB3 default)

#### MUST: Prioritised Replay Priority-Tree Persistence

When `prioritized=True`, `ReplayBuffer.checkpoint()` MUST serialise BOTH:

1. The ring-buffer transition contents (observations, actions, rewards, dones, next_obs).
2. The priority sum-tree (binary heap) internal state.
3. The current β (importance-sampling annealing coefficient).
4. The RNG state of the `np.random.Generator` used for sampling.

The serialisation format is a `SCHEMA_VERSION: int = 1` tagged binary blob — forward-compatible changes bump the version. `from_checkpoint(payload)` rejects unknown versions with `ReplayBufferCheckpointVersionError`.

The priority tree MUST be persisted (NOT lazily rebuilt) because lazy rebuild resets β — losing the annealing progress.

**Why:** Rule A4-2 — a saturated buffer's ring-buffer evicted samples FIFO, but the priority metadata rides along with transitions. Lazy rebuild of the tree at resume loses the β schedule — a subtle but real regression for long prioritised-replay training runs.

### 6.3 `OfflineDataset` (polars-native)

```python
class OfflineDataset:
    def __init__(
        self,
        data: pl.DataFrame | Path,
        *,
        obs_cols: list[str],
        action_cols: list[str],
        reward_col: str = "reward",
        next_obs_cols: list[str] | None = None,
        done_col: str = "done",
        tenant_id: str | None = None,
    ) -> None: ...
    def sample(self, batch_size: int) -> OfflineBatch: ...
    def to_replay_buffer(self, *, size: int | None = None) -> ReplayBuffer: ...
    def summary(self) -> dict: ...
```

Contract: the backing polars DataFrame MUST have `obs_cols + action_cols + [reward_col, done_col] + (next_obs_cols or [])` present. Missing columns raise `ValueError` at construction.

## 7. Tracker + Dashboard Integration

### 7.1 Tracker wiring

`km.rl_train()` MUST:

1. Resolve `tracker` kwarg. If `None`, read the ambient `km.track()` contextvar via `kailash_ml.tracking.get_current_run()`; if also `None`, construct a default `ExperimentTracker` via `await ExperimentTracker.create(store_url=None)` (defaults to `~/.kailash_ml/ml.db` per `ml-tracking §2.2`) and open a fresh run.
2. Open a run via `tracker.run(experiment_name=experiment, run_name=f"rl-{algo}-{env}")`. The kwarg type is `Optional[ExperimentRun]` — the user-visible async-context wrapper — not `Optional[ExperimentTracker]`.
3. Auto-attach an SB3 `BaseCallback` (`_KailashRLCallback`) that drives `RLDiagnostics.record_*` calls:
   - On `_on_step`: samples `rl.step.*` metrics (throttled to 1/N steps).
   - On `_on_rollout_end`: emits `rl.policy.*` + `rl.value.*` + `rl.advantage.*` + `rl.rollout.*`.
   - On episode end (via `Monitor` wrapper's episode info): emits `rl.episode.*`.
   - On `EvalCallback` trigger: emits `rl.eval.*`.
4. On training completion: log artifacts (policy zip, normalization stats, env metadata) to the tracker run; call `tracker.log_artifact(run_id, artifact_path, artifact_kind="rl_policy")`. On resume, append to the existing run (do NOT create a new one — §9.1 MUST 6).

Closes HIGH-8.

### 7.2 Dashboard RL tab

`MLDashboard` renders RL-specific panels when a run has `run.metadata["kind"] == "rl"`:

- **Episode reward curve** (mean ± std band, per-step).
- **Policy loss / value loss / entropy loss** time-series.
- **KL divergence + clip fraction (PPO)** / **entropy coefficient (SAC)** / **exploration rate (DQN)** time-series.
- **Evaluation reward distribution** (box plot per `eval_freq` checkpoint).
- **Buffer fill progress** (off-policy) with reward percentile overlay.
- **Explained variance of value function** (on-policy actor-critic).
- **Action distribution** histogram (discrete) or marginal quantiles (continuous).

Panel spec is declarative; panel SPECs live in `kailash_ml.dashboard.rl_panels`. Figure emission contract: `plot_rl_dashboard()` emits as `rl_dashboard`; per-panel emissions follow `§8.5 Figure Emission Contract`.

## 8. `RLDiagnostics` Class Surface

This section is the full class surface for `RLDiagnostics` and closes round-2b G-RL-DIAG-SURFACE. It mirrors the depth of `ml-diagnostics-draft.md §5 DLDiagnostics Public API` — every record method, every polars-DataFrame accessor, every plot, the metric-name schema, the DDP/FSDP safety contract, the checkpoint/resume contract, and the Tier-2 wiring test are enumerated explicitly. `RLDiagnostics` satisfies `kailash.diagnostics.protocols.Diagnostic` (runtime-checkable) — closes HIGH-15.

### 8.1 Construction

```python
from kailash_ml.diagnostics.rl import RLDiagnostics

RLDiagnostics(
    env: "gymnasium.Env",                        # required — the env the policy is evaluated against
    policy: "PolicyProtocol",                    # required — satisfies kailash_ml.rl.PolicyProtocol
    *,
    tracker: Optional[ExperimentRun] = None,     # None → ambient via get_current_run()
    kl_reference: Optional["PolicyProtocol"] = None,  # reference policy for KL tracking (PPO, DPO)
    auto: bool = True,                           # auto-wire to ambient tracker when tracker=None
    algo: Optional[str] = None,                  # "ppo", "sac", "dqn", ... — algo-aware exploration metric
    window: int = 100,                           # running-mean/std window for episode rewards
    log_every_n_steps: int = 50,                 # flush to tracker every N record_step calls
    run_id: Optional[str] = None,                # UUID4 hex when omitted
    rank: Optional[int] = None,                  # DDP rank; auto-detected via torch.distributed when None
    sensitive: bool = False,                     # redact env spec / reward signature per event-payload-classification.md
    tenant_id: Optional[str] = None,             # honored for tenant-scoped metric labels per rules/tenant-isolation.md §4
    label: Optional[str] = None,                 # human-readable label e.g. "cartpole-ppo"
)
```

**Contextvar ambient read:** When `tracker is None` AND `auto is True`, the constructor calls `kailash_ml.tracking.get_current_run() -> Optional[ExperimentRun]` once and stores the resolved handle. Subsequent emissions flow through the stored handle; a later `km.track()` context change does NOT re-bind the diagnostics session (explicit re-binding requires `diag.rebind_tracker(new_run)`).

**Raises:**

- `TypeError` if `env` is not a `gymnasium.Env` (duck-typed: missing `observation_space` / `action_space` / `step` / `reset` raises).
- `TypeError` if `policy` does not satisfy `PolicyProtocol` (runtime-checkable).
- `ValueError` if `window < 1`, `log_every_n_steps < 1`, `run_id == ""`, or `algo` is supplied but not a registered algorithm name.
- `TenantRequiredError` (canonical, `TrackingError` family per `ml-tracking-draft.md §9.1`; re-exported from `kailash_ml.errors`) if the running context has `multi_tenant=True` and `tenant_id` is None.
- `ImportError` from `_require_gymnasium()` / `_require_stable_baselines3()` when the `[rl]` extra is absent AND an algorithm-specific metric is requested.

### 8.2 Methods

#### 8.2.1 `record_episode(reward, length, info) -> None`

```python
def record_episode(
    self,
    reward: float,
    length: int,
    info: dict,
) -> None: ...
```

Called once at the END of every episode. Updates the running window (`window=100` by default) for episode reward mean/std; appends a row to the internal `_episode_df: polars.DataFrame`. Emits `rl.episode.reward` and `rl.episode.length` to the tracker (rank-0 only under DDP per §8.4).

`info` is the `gymnasium.Env.step` final `info` dict (may contain `success`, `TimeLimit.truncated`, `l`, `r` from `Monitor`). Success-boolean is extracted via `info.get("success")` (may be None if env does not expose it).

#### 8.2.2 `record_step(obs, action, reward, done, info) -> None`

```python
def record_step(
    self,
    obs: "numpy.ndarray",
    action: "numpy.ndarray | int",
    reward: float,
    done: bool,
    info: dict,
) -> None: ...
```

OPTIONAL per-step emission (SB3 callbacks throttle this to 1 in every N steps; users calling manually can call every step). Updates the step counter; emits `rl.step.reward` at the sampled cadence. Records observation-statistics (mean, std) in an internal ring buffer without tensor-payload emission (see §8.6 Figure Emission for histogram on demand).

#### 8.2.3 `record_rollout_batch(rollout) -> None`

```python
def record_rollout_batch(
    self,
    rollout: "RolloutBatch",   # kailash_ml.rl.RolloutBatch — the GAE-advantage-computed batch
) -> None: ...
```

On-policy contract. Called once per `_on_rollout_end`. Computes:

- `rl.rollout.length_mean`, `rl.rollout.length_std` — from episode lengths inside the batch.
- `rl.advantage.mean`, `rl.advantage.std` — from `rollout.advantages` (post-normalization if the adapter already normalized).
- Appends a row to `_rollout_df`.

#### 8.2.4 `record_replay_batch(batch) -> None`

```python
def record_replay_batch(
    self,
    batch: "ReplayBatch",   # kailash_ml.rl.ReplayBatch — a sampled mini-batch
) -> None: ...
```

Off-policy contract. Called every train iter or on-demand. Computes:

- `rl.replay.size` — `len(buffer)`.
- `rl.replay.prioritized_max_priority` — when prioritized=True; NULL emitted when False (never hallucinated 0).
- Reward percentile distribution (p10, p50, p90) stored in `_replay_df` but NOT emitted as metrics by default (histograms are opt-in via `plot_*`).

#### 8.2.5 `record_policy_update(loss, kl, entropy, clip_fraction=None, *, kl_estimator) -> None`

```python
def record_policy_update(
    self,
    loss: float,
    kl: float,
    entropy: float,
    clip_fraction: Optional[float] = None,
    *,
    kl_estimator: Literal["exact", "sample_unbiased"] = "sample_unbiased",
) -> None: ...
```

Emits `rl.policy.loss`, `rl.policy.kl_from_ref`, `rl.policy.entropy`, `rl.policy.kl_estimator` (categorical tag). Emits `rl.policy.clip_fraction` only when `clip_fraction is not None` (PPO-family); DQN/SAC/TD3 pass `None` rather than hallucinate zero.

##### MUST: KL Smoothing

The KL value `kl` passed in MUST be finite. Two estimator modes are supported:

- `"exact"` (TRPO) — `KL(π_old || π_new) = Σ_a π_old(a) × ln((π_old(a) + ε) / (π_new(a) + ε))` with `ε = KL_SMOOTH_EPS = 1e-10` (matches the `ml-drift.md` §3.6 constant). Zero-probability actions are smoothed additively before log.
- `"sample_unbiased"` (PPO) — SB3's estimator: `KL ≈ E[(logp_new - logp_old)^2 / 2]` over rollout samples. This is naturally finite (expectation of squared log-ratios); no smoothing required but the emitted metric is an APPROXIMATION.

Callers MUST pass the correct `kl_estimator` for their algorithm. Mixing estimators under the same `rl.policy.kl_from_ref` key corrupts cross-run comparisons; the `kl_estimator` tag makes downstream filtering safe.

Appends row to `_policy_update_df`.

##### MUST: `track_exploration` Entry Point

```python
def track_exploration(
    self,
    *,
    action: "numpy.ndarray | int",
    logprob_new: float,
    logprob_old: float | None = None,
    kl_estimator: Literal["exact", "sample_unbiased"] = "sample_unbiased",
) -> None: ...
```

When `logprob_old` is provided, `track_exploration` computes the per-action KL contribution using the selected estimator (`exact` routes through `KL_SMOOTH_EPS = 1e-10`; `sample_unbiased` uses `(logprob_new - logprob_old)^2 / 2`). When `logprob_old is None`, emits `rl.exploration.entropy_sample` only (no KL). Backing polars DF: `_exploration_df`. Emits `rl.policy.kl_from_ref_per_step` at `log_every_n_steps` cadence.

#### 8.2.6 `record_value_update(loss, explained_variance) -> None`

```python
def record_value_update(
    self,
    loss: float,
    explained_variance: float,
) -> None: ...
```

On-policy actor-critic contract. Emits `rl.value.loss`, `rl.value.explained_variance`.

Appends row to `_value_update_df`.

#### 8.2.7 `record_q_update(loss, overestimation_gap=None) -> None`

```python
def record_q_update(
    self,
    loss: float,
    overestimation_gap: Optional[float] = None,
) -> None: ...
```

Off-policy contract (DQN / SAC / TD3 / DDPG). Emits `rl.q.loss` and — when the adapter computes a twin-Q overestimation gap (TD3, SAC) — `rl.q.overestimation_gap`. DQN passes `None`.

#### 8.2.8 `record_eval_rollout(reward, length, deterministic=True) -> None`

```python
def record_eval_rollout(
    self,
    reward: float,
    length: int,
    deterministic: bool = True,
) -> None: ...
```

Called once per `EvalCallback` trigger. Emits `rl.eval.reward`, `rl.eval.length`. Logs `deterministic=True|False` into the event payload; stochastic eval emits a WARN line (`ml_diagnose.stochastic_eval_warning`) per `rules/observability.md`.

#### 8.2.9 `report() -> DiagnosticReport`

Returns a dataclass conforming to the `Diagnostic` Protocol from `kailash.diagnostics.protocols`:

```python
@dataclass(frozen=True)
class DiagnosticReport:
    run_id: str
    kind: Literal["rl"]
    label: Optional[str]
    algo: Optional[str]
    metrics: dict[str, float | None]    # episode_reward_mean, episode_reward_std, ...
    findings: list[Finding]              # severity-tagged, same schema as DLDiagnostics
    summary_dataframes: dict[str, "polars.DataFrame"]  # {"episodes": _episode_df, ...}
```

Never raises on empty state — returns a report with `metrics = {}` and `findings = []` if no data was recorded. Finding severities match §8.7.

### 8.3 Polars-DataFrame Accessors

```python
def as_dataframe(self, kind: Literal["episode", "step", "rollout", "replay",
                                      "policy_update", "value_update", "q_update",
                                      "eval"]) -> "polars.DataFrame": ...
```

Returns a COPY of the named internal DataFrame. Supported kinds:

| `kind`          | Columns                                                                                              |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| `episode`       | `ep_index`, `step`, `reward`, `length`, `success`, `timestamp`                                       |
| `step`          | `step`, `obs_mean`, `obs_std`, `reward`, `done`, `action_entropy`, `timestamp`                       |
| `rollout`       | `rollout_index`, `step`, `length_mean`, `length_std`, `advantage_mean`, `advantage_std`, `timestamp` |
| `replay`        | `step`, `size`, `fill_ratio`, `reward_p50`, `reward_p90`, `prioritized_max_priority`, `timestamp`    |
| `policy_update` | `update_index`, `step`, `loss`, `kl`, `entropy`, `clip_fraction`, `timestamp`                        |
| `value_update`  | `update_index`, `step`, `loss`, `explained_variance`, `timestamp`                                    |
| `q_update`      | `update_index`, `step`, `loss`, `overestimation_gap`, `timestamp`                                    |
| `eval`          | `eval_index`, `step`, `reward`, `length`, `deterministic`, `timestamp`                               |

Unknown `kind` raises `ValueError` enumerating allowed values.

### 8.4 Plots (requires `[dl]` extra)

All plots return `plotly.graph_objects.Figure`. Each `plot_*` routes through `_require_plotly()` per `ml-diagnostics-draft.md §8.5 Loud Failure Contract` — `ImportError("Plotting requires plotly. Install: pip install kailash-ml[dl]")` when plotly is absent.

```python
def plot_reward_curve(self) -> "plotly.graph_objects.Figure": ...
def plot_entropy_curve(self) -> "plotly.graph_objects.Figure": ...
def plot_kl_curve(self) -> "plotly.graph_objects.Figure": ...
def plot_explained_variance_curve(self) -> "plotly.graph_objects.Figure": ...
def plot_action_distribution(self) -> "plotly.graph_objects.Figure": ...
def plot_value_calibration(self) -> "plotly.graph_objects.Figure": ...
def plot_rl_dashboard(self) -> "plotly.graph_objects.Figure": ...  # composite — all of the above
```

Each plot reads from the underlying polars DataFrame (no re-computation from running state) so `plot_*` is safe to call from a post-training `km.diagnose(kind="rl")` path even after the training loop has exited.

### 8.5 Metric-Name Schema

Metric names MUST follow this exact schema — downstream dashboards, alerting keys, and cross-SDK (kailash-py ↔ kailash-rs) forensic correlation depend on stability:

| Capture source                                           | Metric name (exact)                  | Step index source                               |
| -------------------------------------------------------- | ------------------------------------ | ----------------------------------------------- |
| `record_episode(reward=...)`                             | `rl.episode.reward`                  | episode index (0-based)                         |
| `record_episode(length=...)`                             | `rl.episode.length`                  | episode index                                   |
| `record_step(reward=...)`                                | `rl.step.reward`                     | step index (0-based, monotonic across episodes) |
| `record_policy_update(loss=...)`                         | `rl.policy.loss`                     | update index (0-based)                          |
| `record_policy_update(entropy=...)`                      | `rl.policy.entropy`                  | update index                                    |
| `record_policy_update(kl=...)` (vs `kl_reference`)       | `rl.policy.kl_from_ref`              | update index                                    |
| `record_policy_update(clip_fraction=...)` (PPO only)     | `rl.policy.clip_fraction`            | update index                                    |
| `record_value_update(loss=...)`                          | `rl.value.loss`                      | update index                                    |
| `record_value_update(explained_variance=...)`            | `rl.value.explained_variance`        | update index                                    |
| `record_q_update(loss=...)`                              | `rl.q.loss`                          | update index                                    |
| `record_q_update(overestimation_gap=...)` (TD3/SAC only) | `rl.q.overestimation_gap`            | update index                                    |
| `record_rollout_batch(...)` length mean                  | `rl.rollout.length_mean`             | rollout index (0-based)                         |
| `record_rollout_batch(...)` length std                   | `rl.rollout.length_std`              | rollout index                                   |
| `record_replay_batch(...)` size                          | `rl.replay.size`                     | step index                                      |
| `record_replay_batch(...)` prioritized max priority      | `rl.replay.prioritized_max_priority` | step index                                      |
| `record_rollout_batch(...)` advantage mean               | `rl.advantage.mean`                  | rollout index                                   |
| `record_rollout_batch(...)` advantage std                | `rl.advantage.std`                   | rollout index                                   |
| `record_eval_rollout(reward=...)`                        | `rl.eval.reward`                     | eval index (0-based)                            |
| `record_eval_rollout(length=...)`                        | `rl.eval.length`                     | eval index                                      |

**Step-index contract:**

- `rl.step.*` uses a monotonic step counter that does NOT reset across episodes (mirrors DLDiagnostics batch counter).
- `rl.episode.*` uses an episode counter.
- `rl.policy.*` / `rl.value.*` / `rl.q.*` use the update counter incremented once per `record_*_update`.
- `rl.rollout.*` / `rl.advantage.*` use the rollout counter incremented once per `record_rollout_batch`.
- `rl.replay.*` uses the step counter (since replay samples are drawn at step cadence).
- `rl.eval.*` uses the eval counter.

The tracker distinguishes by the tuple `(metric_name, step)` — the counter identity is metadata only.

### 8.6 Figure Emission Contract

`tracker.log_figure(name, fig)` emission key schema:

| Producing method                  | Figure name                |
| --------------------------------- | -------------------------- |
| `plot_reward_curve()`             | `reward_curve`             |
| `plot_entropy_curve()`            | `entropy_curve`            |
| `plot_kl_curve()`                 | `kl_curve`                 |
| `plot_explained_variance_curve()` | `explained_variance_curve` |
| `plot_action_distribution()`      | `action_distribution`      |
| `plot_value_calibration()`        | `value_calibration`        |
| `plot_rl_dashboard()`             | `rl_dashboard`             |

### 8.7 Findings (severity-tagged)

Every `report()` returns a `findings: list[Finding]` where each `Finding` is `(severity, category, message, suggestion)`:

- **CRIT** — `episode_reward_collapse`: reward dropped by >50% over last `window` episodes AND is below 10% of peak. Suggests catastrophic forgetting. Remediation hint: reduce `learning_rate`, check reward shaping.
- **HIGH** — `entropy_collapse`: policy entropy < 0.01 AND training steps < 20% complete. Suggests premature exploration collapse. Remediation: increase `ent_coef`, reduce `clip_range`.
- **HIGH** — `kl_blowup`: PPO `approx_kl > 2 * target_kl` sustained over 3 updates. Policy diverged. Remediation: reduce learning rate, reduce `n_epochs`, check advantage normalization.
- **HIGH** — `replay_buffer_underfill`: `size / capacity < 0.01` when >10k env steps elapsed. Suggests replay buffer never populated (buffer not passed to algo correctly).
- **MED** — `value_fit_poor`: `explained_variance < 0.05` for >30% of training. Suggests value network too small, or reward scale too large.
- **MED** — `eval_reward_stagnation`: eval `mean_reward` unchanged (±5%) over last 3 evals when training is in first 50%.
- **LOW** — `advantage_scale_drift`: advantage std varies >3× across rollouts (normalization skew).

### 8.8 DDP / FSDP / DeepSpeed Safety (Decision 4 — pinned)

Rank-0-only emission is HARDCODED, not configurable. Every tracker write path MUST gate on `_is_rank_zero()`:

```python
def _is_rank_zero(self) -> bool:
    """Per Decision 4 — rank-0-only emission is HARDCODED, not configurable."""
    if self._rank is not None:
        return self._rank == 0
    try:
        import torch.distributed as dist
        if dist.is_available() and dist.is_initialized():
            return dist.get_rank() == 0
    except ImportError:
        pass
    return True  # single-process → rank 0 by definition

def _emit_metric(self, key: str, value: float, step: int) -> None:
    """Single enforcement point. Every record_* path flows through here."""
    if not self._is_rank_zero():
        return   # non-rank-0 ranks accumulate DataFrames but do NOT emit
    if self._tracker is not None:
        self._tracker.log_metric(key, value, step=step)
```

When `torch.distributed.is_initialized()` returns True AND rank > 0: in-memory DataFrame accumulation continues (for `report()` aggregation via `all_reduce`) but zero tracker writes. This prevents N-way duplicate metric writes on a N-GPU RL run (e.g. PPO with DDP-replicated policy on 64 GPUs).

**Report aggregation:** `self.report()` runs `torch.distributed.all_reduce(...)` on severity-relevant aggregates (mean episode reward, max episode length, cross-rank KL mean) so every rank sees the same summary. If `torch.distributed` is unavailable, the reduce is a no-op.

**Tier-2 test:** `packages/kailash-ml/tests/integration/diagnostics/test_rldiagnostics_ddp_rank0_only_emission.py` MUST spin up a mocked 2-rank distributed group (via `torch.distributed.init_process_group(backend="gloo", rank=…, world_size=2)` on localhost), construct an `RLDiagnostics` session on each rank, call `record_episode` on both, and assert:

1. Rank-0 tracker received exactly 1 metric write per `record_*` call.
2. Rank-1 tracker received ZERO metric writes.
3. Both ranks see identical `report().metrics` (aggregation worked).

### 8.9 Checkpoint + Resume

```python
def checkpoint_state(self) -> dict[str, Any]:
    """Serializable state for checkpoint integration."""

@classmethod
def from_checkpoint(
    cls,
    env: "gymnasium.Env",
    policy: "PolicyProtocol",
    state: dict[str, Any],
    *,
    tracker: Optional[ExperimentRun] = None,
) -> "RLDiagnostics": ...
```

`checkpoint_state()` returns the session's running aggregates (episode counter, step counter, update counter, rolling reward window, RNG state, the DataFrame bodies serialized via `polars.DataFrame.write_ipc`). The dict is JSON-safe at the shell (DataFrames are IPC byte blobs encoded as base64); it rides inside the SB3 checkpoint payload via a custom callback.

`from_checkpoint()` restores a fresh session at the correct counter state so a resumed training run produces a continuous metric stream into the tracker (the tracker run-id is carried in `state["tracker_run_id"]` so `rl_train(resume_from=...)` appends to the existing run).

Restored state MUST include:

1. `episode_counter`, `step_counter`, `update_counter`, `rollout_counter`, `eval_counter`
2. Window buffer for running reward mean / std
3. All internal DataFrames (episode, step, rollout, replay, policy_update, value_update, q_update, eval)
4. RNG state (`numpy.random`, `torch.random`, `random`, `torch.cuda.random` when applicable)

### 8.10 Tier-2 Wiring Test — `test_rldiagnostics_wiring.py`

```python
# packages/kailash-ml/tests/integration/diagnostics/test_rldiagnostics_wiring.py
import pytest
import gymnasium as gym
import kailash_ml as km
from kailash_ml.diagnostics.rl import RLDiagnostics
from kailash_ml.tracking import ExperimentTracker
from kailash.diagnostics.protocols import Diagnostic

@pytest.mark.integration
async def test_rldiagnostics_full_surface(tmp_path):
    """Tier-2 wiring — real gymnasium env + real PPO policy + real tracker.

    Asserts:
      (1) RLDiagnostics satisfies Diagnostic Protocol at runtime (isinstance check).
      (2) After a ≤100-step PPO rollout, ≥5 distinct rl.* metric keys land in tracker.
      (3) ≥1 figure (plot_rl_dashboard) emits to tracker.log_figure.
      (4) DataFrame accessors return non-empty polars DataFrames for "episode" and "policy_update".
      (5) report() returns DiagnosticReport with non-empty metrics dict.
      (6) Checkpoint-and-resume preserves counters across a save/load cycle.
    """
    tracker = await ExperimentTracker.create(f"sqlite:///{tmp_path}/ml.db")
    async with tracker:
        async with tracker.run("test-rldiag") as run:
            env = gym.make("CartPole-v1")
            # Wire a full ≤100-step PPO via km.rl_train:
            result = km.rl_train(
                env="CartPole-v1",
                algo="ppo",
                total_timesteps=100,
                n_envs=1,  # Decision 7 — literal default
                eval_freq=50,
                n_eval_episodes=2,
                tracker=run,
            )
            diag = RLDiagnostics(env=env, policy=result.policy, tracker=run, algo="ppo")
            assert isinstance(diag, Diagnostic)  # Protocol conformance

            # After km.rl_train has flushed metrics into run:
            metrics = await tracker.list_metrics(run_id=run.run_id)
            rl_keys = {m.key for m in metrics if m.key.startswith("rl.")}
            assert len(rl_keys) >= 5, f"expected ≥5 rl.* metrics, got {rl_keys}"

            figures = await tracker.list_figures(run_id=run.run_id)
            assert any(f.name == "rl_dashboard" for f in figures)

            eps_df = diag.as_dataframe("episode")
            assert len(eps_df) >= 1

            report = diag.report()
            assert "episode_reward_mean" in report.metrics

            # Checkpoint round-trip
            state = diag.checkpoint_state()
            restored = RLDiagnostics.from_checkpoint(env=env, policy=result.policy, state=state, tracker=run)
            assert restored._episode_counter == diag._episode_counter
```

This test is the orphan-detection structural gate per `rules/facade-manager-detection.md` §1 — if `RLDiagnostics` has no production call site inside `km.rl_train`, `rl_keys` will be empty and the assertion fires.

## 9. Checkpointing + Resume

### 9.1 `resume_from=` contract

`rl_train(..., resume_from=ref)` where `ref` is one of:

- `Path` or `str` pointing to a checkpoint directory.
- `PolicyArtifactRef` (path + SHA + optional registry version).

Resume MUST restore the full three-RNG contract — `env`, `policy`, `buffer` — AND global Python/NumPy/Torch state, AND tracker continuity, AND the env-step counter. A resumed PPO run with episode-level stochastic exploration is NOT bit-reproducible without ALL of them.

Resume MUST restore:

1. **Policy state** — `torch.nn.Module.state_dict`.
2. **Optimizer state** — `torch.optim.Optimizer.state_dict`.
3. **Buffer state** — rollout or replay buffer contents (off-policy MUST restore to exact replay state including the priority sum-tree per §6.2 MUST).
4. **Env RNG state** — `env.np_random.bit_generator.state` AND `env.action_space.np_random.bit_generator.state` (two separate Gymnasium RNGs). MUST be serialised as JSON-safe dict per `np.random.Generator.bit_generator.state` contract and round-tripped losslessly.
5. **Policy RNG state** — SB3 policies maintain their own RNG for exploration-noise sampling; the `policy._rng` (or equivalent) state MUST be captured as bytes.
6. **Buffer RNG state** — `ReplayBuffer`'s sampling RNG (`np.random.default_rng(seed)`) state MUST be captured as bytes.
7. **Global RNG state** — `numpy.random` default RNG state, `random.getstate()`, `torch.get_rng_state()`, `torch.cuda.get_rng_state_all()` when `device.backend == "cuda"`.
8. **Tracker continuity** — resume MUST call `km.track(..., parent_run_id=<prior_run_id>, resume=True)` so the existing run is extended rather than orphaned; HP-diff on resume follows `ml-tracking.md` §4.6 MUST (resume HP-diff emission).
9. **`total_env_steps` counter** — resumes at the saved value so `total_timesteps` is treated as a target across the RESUMED run, not the new run.

#### `RLCheckpoint` Schema

```python
@dataclass(frozen=True)
class RLCheckpoint:
    schema_version: int = 2                   # bumped for the three-RNG contract
    # Policy + optimizer
    policy_state_dict: dict[str, Any]
    optimizer_state_dict: dict[str, Any]
    # Buffer
    buffer_payload: bytes                      # from ReplayBuffer.checkpoint() / RolloutBuffer.checkpoint()
    buffer_rng_state: bytes
    # Env
    env_rng_state: dict[str, Any]              # env.np_random.bit_generator.state
    action_space_rng_state: dict[str, Any]     # env.action_space.np_random.bit_generator.state
    # Policy sampling
    policy_rng_state: bytes
    # Global
    global_numpy_state: dict[str, Any]
    global_random_state: tuple
    global_torch_state: bytes
    global_cuda_state: list[bytes] | None      # per-device; None on CPU
    # Run continuity
    tracker_run_id: str
    total_env_steps: int
    seed_report: "SeedReport"                  # from ml-engines-v2 §11
```

#### MUST: Tier 2 Three-RNG Round-Trip Test

`tests/integration/test_rl_checkpoint_three_rng_roundtrip.py` MUST:

1. Train 5000 steps of PPO CartPole.
2. Save checkpoint.
3. Destroy all RNGs and load checkpoint.
4. Run 100 more env steps.
5. Save a second checkpoint.
6. Re-load the FIRST checkpoint, run the same 100 env steps.
7. Assert the second run's observations, actions, rewards are bit-identical to the first run.

Failure of any RNG means the test diverges by step 3-4; passing IS the three-RNG contract verification.

### 9.2 Checkpoint frequency

- Default: every `max(total_timesteps // 10, 10_000)` env steps.
- Override via `RLTrainingConfig.checkpoint_freq`.
- Checkpoints MUST write through `ConnectionManager` and the ambient `ModelRegistry` artifact store (tenant-scoped).

## 10. Evaluation Rollouts

### 10.1 Separate `eval_env` (closes HIGH-5)

`eval_env` MUST default to a FRESH environment independent of the training env when unspecified:

```python
if eval_env is None:
    eval_env_fn = _clone_env_spec(env)  # NEW instance, same spec
else:
    eval_env_fn = _resolve_env(eval_env)
```

Sharing RNG / wrapper state between training and eval is BLOCKED — `_clone_env_spec` MUST create a new RNG seed derived from the training seed + a `eval_seed_offset`.

### 10.2 Eval scheduling

SB3 `EvalCallback(eval_env, n_eval_episodes, eval_freq, deterministic=True)` is attached automatically (closes HIGH-2). Every eval produces an `EvalRecord`:

```python
@dataclass
class EvalRecord:
    eval_step: int
    mean_reward: float
    std_reward: float
    mean_length: float
    success_rate: float | None
    n_episodes: int
    timestamp: datetime
```

Appended to `RLTrainingResult.eval_history` AND emitted via `tracker.log_metric("rl.eval.*", value, step=eval_step)`.

### 10.3 Deterministic evaluation

Eval rollouts MUST use `deterministic=True` (policy returns mode / argmax action). Stochastic eval requires explicit `deterministic_eval=False` kwarg AND logs a WARN per `rules/observability.md`.

## 11. Distributed / Parallel Rollout Workers

### 11.1 `n_envs` (vectorized envs)

`n_envs > 1` builds a `SyncVectorEnv` (in-process) or `AsyncVectorEnv` (subprocess) per `workers`:

- `workers == 0` (default): `SyncVectorEnv(n_envs)` — low overhead, debuggable, same process.
- `workers > 0`: `AsyncVectorEnv(n_envs)` with `workers` subprocesses — real parallelism, JSON-safe obs/action shapes, higher throughput for PPO/A2C/TRPO.

### 11.2 Expectation vs rllib

v1 is NOT rllib. It is:

- In-process vectorized envs (gymnasium.vector) — PARITY with SB3.
- Subprocess async envs (gymnasium.vector.AsyncVectorEnv) — PARITY with SB3.
- Single-machine multi-process rollout — PARITY with SB3.

Multi-node distributed rollout (Ray actor placement, parameter-server replication) is `[rl-distributed]` extra for a follow-on release. Users who need it today MUST drop to rllib directly — `rl_train` does not silently no-op when asked for multi-node parallelism; it raises `FeatureNotYetSupportedError` with an upstream issue link.

## 12. Backend / Device Awareness (closes HIGH-9)

`rl_train()` MUST:

1. Resolve device via `device` kwarg → `km.use_device()` contextvar → `detect_backend()`.
2. Pass the resolved device to the SB3 algorithm constructor (`algo_cls(..., device=device)`).
3. Move policy, value network, Q-network, replay buffer tensors to the resolved device.
4. Produce `DeviceReport(backend, device_name, memory, ...)` per `specs/ml-backends.md`.
5. Include `DeviceReport` in the returned `RLTrainingResult.device`.

The orphan-guard regression `test_rl_trainer_does_not_use_backend_resolver` is REMOVED and replaced with its opposite (`test_rl_trainer_resolves_device_via_detect_backend`) in §18.

## 13. Error Taxonomy

All errors live in `kailash_ml.rl.errors` and subclass a base `RLError(Exception)`:

| Error class                                                                                                           | Raised when                                                                                                                                                                                                                                                                                              |
| --------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `RLEnvIncompatibleError`                                                                                              | `env` does not satisfy `EnvironmentProtocol` OR obs/action space mismatch with policy                                                                                                                                                                                                                    |
| `RLPolicyShapeMismatchError`                                                                                          | Policy `observation_space` / `action_space` disagree with env                                                                                                                                                                                                                                            |
| `ReplayBufferUnderflowError`                                                                                          | Off-policy algo attempts to sample from buffer before warmup steps elapse                                                                                                                                                                                                                                |
| `ReplayBufferOverflowError`                                                                                           | Buffer `add` called beyond configured capacity without FIFO eviction                                                                                                                                                                                                                                     |
| `RewardModelRequiredError`                                                                                            | `algo in {"ppo-rlhf", "dpo", "rloo", "online-dpo"}` without `reward_model` kwarg AND without `preference_dataset` kwarg                                                                                                                                                                                  |
| `OfflineDatasetSchemaError`                                                                                           | Polars DataFrame missing required `obs/action/reward/done` columns                                                                                                                                                                                                                                       |
| `OfflineDatasetEmptyError`                                                                                            | Offline algo sees dataset with zero rows                                                                                                                                                                                                                                                                 |
| `RLCheckpointCorruptError`                                                                                            | `resume_from=` points to a checkpoint whose SHA doesn't match manifest                                                                                                                                                                                                                                   |
| `TenantRequiredError` (canonical, re-exported from `kailash_ml.errors` — TrackingError family per `ml-tracking §9.1`) | `multi_tenant=True` policy / buffer constructed without `tenant_id`. RL does NOT define a dedicated `RLTenantRequiredError` — the canonical typed error covers every domain uniformly so callers may write `except TenantRequiredError` across RL + tracking + registry + feature-store + serving paths. |
| `FeatureNotYetSupportedError`                                                                                         | MARL / Jax / multi-node distributed / first-party MBPO-Dreamer                                                                                                                                                                                                                                           |

All error messages MUST include actionable remediation (see `rules/zero-tolerance.md` Rule 3a).

### 13.1 `RewardModelRequiredError` full definition

```python
class RewardModelRequiredError(RLError):
    """Raised when an RLHF algorithm is invoked without a reward model or preference dataset.

    RLHF algorithms (DPO, PPO-RLHF, RLOO, OnlineDPO) require EITHER a parametric
    `reward_model=` (a callable mapping (obs, action) → reward) OR a `preference_dataset=`
    (pairs of preferred/rejected trajectories). Without one, the algorithm has no
    training signal.
    """

    def __init__(self, algo: str):
        self.algo = algo
        super().__init__(
            f"algo={algo!r} requires either `reward_model=` (callable) or "
            f"`preference_dataset=` (polars.DataFrame) — RLHF has no training signal "
            f"without one. See ml-rl-algorithms-draft.md §5.3 for construction examples."
        )
```

## 14. Test Contract

### 14.1 Tier 1 (unit)

Per algorithm adapter: test `make_policy()`, `make_buffer()`, `_build_callback_stack()`, `_resolve_device()` in isolation with MagicMock env.

Per error class: test construction + message shape.

### 14.2 Tier 2 (integration) — `test_rl_train_wiring.py`

```python
@pytest.mark.integration
async def test_km_rl_train_cartpole_wiring(tmp_path):
    """≤100-step PPO on CartPole asserts:
       (1) RLTrainingResult has ≥3 metrics in tracker
       (2) ≥1 final artifact (policy.zip) registered
       (3) RLDiagnostics satisfied Diagnostic protocol
       (4) episodes non-empty, eval_history non-empty
       (5) DeviceReport present
       (6) tenant_id propagated when supplied.
    """
    tracker = await ExperimentTracker.create(f"sqlite:///{tmp_path}/ml.db")
    async with tracker:
        result = km.rl_train(
            env="CartPole-v1",
            algo="ppo",
            total_timesteps=100,
            eval_freq=50,
            n_eval_episodes=2,
            tracker=tracker,
            experiment="test-rl",
            tenant_id="t1",
        )
        assert isinstance(result, RLTrainingResult)
        assert result.device is not None
        assert len(result.episodes) >= 1
        assert len(result.eval_history) >= 1
        metrics = await tracker.list_metrics(run_id=result.run_id)
        rl_metric_keys = {m.key for m in metrics if m.key.startswith("rl.")}
        assert len(rl_metric_keys) >= 3
        assert any(key.startswith("rl.rollout.episode") for key in rl_metric_keys)
        assert any(key.startswith("rl.eval") for key in rl_metric_keys)
```

### 14.3 Tier 2 (integration) — `test_rl_align_cross_sdk_wiring.py`

See `ml-rl-align-unification-draft.md` §4 for the DPOTrainer-under-`km.rl_train` wiring test.

### 14.4 Anti-regression (replaces `test_rl_orphan_guard.py`)

See §15 for the full anti-regression test suite (pinned three assertions). The previous orphan-guard file `packages/kailash-ml/tests/regression/test_rl_orphan_guard.py` is DELETED in 1.0.0 per §17.2.

## 15. Anti-Regression Test Suite (replaces `test_rl_orphan_guard.py`)

The 0.17.0 `test_rl_orphan_guard.py` PINNED `kailash_ml.rl` as an orphan — it asserted the module was absent from `__all__`, the class had zero engine call sites, and `detect_backend()` was NOT consulted. Those assertions are the OPPOSITE of the 1.0.0 contract. Every one MUST be inverted and landed as the new anti-regression battery. The three pinned assertions below are the structural gate for `kailash_ml.rl` being WIRED (per §2.3 Decision = WIRE).

```python
# packages/kailash-ml/tests/regression/test_rl_wired.py
import pytest

@pytest.mark.regression
def test_rl_train_in_public_all():
    """Anti-regression: km.rl_train appears in the public __all__.

    The 0.17.0 orphan-guard asserted the OPPOSITE — that rl_train was
    absent from __all__. Inverted here: 1.0.0 promotes rl_train to
    the canonical public surface per ml-rl-core-draft.md §3.
    """
    import kailash_ml as km
    assert hasattr(km, "rl_train"), "km.rl_train missing from public surface"
    assert "rl_train" in km.__all__, "km.rl_train missing from kailash_ml.__all__"


@pytest.mark.regression
def test_rltrainer_has_production_call_site():
    """Anti-regression: RLTrainer has ≥1 production call site in kailash_ml/engines.

    Per rules/orphan-detection.md §1, every *Trainer-shape class exposed
    on the public surface MUST have ≥1 call site in the framework's
    hot path within 5 commits of the facade landing. The 0.17.0
    orphan-guard asserted the OPPOSITE — that no engine consumed
    RLTrainer. Inverted here.
    """
    import pathlib, re
    engines_dir = pathlib.Path(__file__).resolve().parents[2] / "src" / "kailash_ml" / "engines"
    hits = list(engines_dir.rglob("*.py"))
    rl_refs = [
        f for f in hits
        if re.search(r"\brl_train\b|\bRLTrainer\b", f.read_text())
    ]
    assert len(rl_refs) >= 1, (
        f"RLTrainer must have ≥1 production call site in {engines_dir} — "
        f"this is the orphan-detection gate per rules/orphan-detection.md §1"
    )


@pytest.mark.regression
def test_rl_path_consults_detect_backend():
    """Anti-regression: the RL training path consults detect_backend().

    The 0.17.0 orphan-guard asserted the OPPOSITE — that RLTrainer
    did NOT call detect_backend(). Inverted here: 1.0.0 RL MUST
    route device resolution through kailash_ml.backends.detect_backend
    per ml-backends.md and §12 of this spec.
    """
    import inspect
    from kailash_ml.rl import trainer as rl_trainer_module
    src = inspect.getsource(rl_trainer_module)
    assert "detect_backend" in src, (
        "RL training path must call detect_backend() per ml-backends.md + §12. "
        "Silent device resolution BLOCKED."
    )
```

**Structural note — behavioral vs source-grep:** per `rules/testing.md § MUST: Behavioral Regression Tests Over Source-Grep`, a purely behavioral test that asserts `result.device.backend in {"cuda", "mps", "cpu", ...}` is preferable. The third assertion above is retained as a belt-and-suspenders source-grep because the 0.17.0 orphan-guard used the same shape (source-grep) and the anti-regression MUST literally invert it. The companion Tier-2 test — `test_km_rl_train_cartpole_wiring` in §14.2 — provides the behavioral proof that `detect_backend()` actually ran (via `result.device` non-None + correct backend enum).

## 16. Industry Parity Matrix

v1 target vs 2026 classical-RL baseline:

| Capability                               | `km.rl_train` (0.18.0)  | SB3  | RLlib   | TRL        | CleanRL    |
| ---------------------------------------- | ----------------------- | ---- | ------- | ---------- | ---------- |
| One-line entry                           | YES                     | YES  | YES     | YES        | YES        |
| Tracker integration (shared, cross-algo) | YES (km.track)          | TB   | Tune    | HF         | TB         |
| Dashboard (unified)                      | YES (MLDashboard)       | TB   | Tune UI | WandB      | TB         |
| Registry (persistent, lifecycle)         | YES (ModelRegistry)     | n/a  | Tune    | HF Hub     | n/a        |
| Separate eval env                        | YES (auto)              | conv | YES     | YES        | YES        |
| VecEnv parallel                          | YES                     | YES  | YES     | batched LM | YES        |
| Wrapper stack                            | YES (declarative)       | YES  | YES     | n/a        | YES        |
| Rollout/replay buffer introspection      | YES (RLDiagnostics)     | YES  | YES     | YES        | YES        |
| Exploration metrics (ε/entropy)          | YES (algo-aware)        | YES  | YES     | KL         | YES        |
| Advantage fit (explained variance)       | YES                     | YES  | YES     | n/a        | YES        |
| Offline RL (BC/CQL/IQL)                  | YES ([rl-offline])      | NO   | YES     | NO         | via d3rlpy |
| RLHF (unified)                           | YES (dispatch to align) | NO   | YES     | YES        | NO         |
| MARL                                     | NO (documented)         | NO   | YES     | NO         | NO         |
| Multi-node distributed                   | NO (documented)         | NO   | YES     | accelerate | NO         |
| Curriculum / task scheduling             | Partial (hook)          | NO   | YES     | YES        | partial    |
| GPU device resolver                      | YES (km.device)         | yes  | YES     | accelerate | yes        |
| Shared result w/ classical ML            | YES (TrainingResult ⊂)  | n/a  | n/a     | n/a        | n/a        |

Score: 15 of 17 capabilities fully delivered; 2 deferred with typed errors. Closes round-1 RL score gap (4/21 → 15/17).

## 17. Migration Path + Deletion Manifest

### 17.1 From `kailash_ml.rl.RLTrainer` (0.17.0) to `km.rl_train` (1.0.0)

The 0.17.0 `RLTrainer` stays as a compatibility shim across the 1.x line and is REMOVED in 2.0.0 per Decision 11 (legacy namespace sunset). 1.x emits `DeprecationWarning` on import of the legacy symbol; 2.x removes the shim entirely.

```python
# 0.17.0 (orphan — pinned by test_rl_orphan_guard.py):
from kailash_ml.rl import RLTrainer, RLTrainingConfig
config = RLTrainingConfig(algorithm="PPO", policy_type="MlpPolicy", total_timesteps=100_000)
trainer = RLTrainer()
result = trainer.train(env_name="CartPole-v1", policy_name="cartpole-ppo", config=config)

# 1.0.0 (canonical; legacy shim still works, emits DeprecationWarning):
import kailash_ml as km
result = km.rl_train(env="CartPole-v1", algo="ppo", total_timesteps=100_000)

# 2.0.0 (legacy shim REMOVED).
```

The `DeprecationWarning` MUST include the exact replacement call.

### 17.2 Deleted Artifacts in 1.0.0

The following files MUST be DELETED in the 1.0.0 release PR, in the SAME commit that lands `km.rl_train` + the anti-regression battery of §15. Per `rules/orphan-detection.md` §4 (API removal MUST sweep tests in the same PR) AND §4a (stub implementation MUST sweep deferral tests in the same commit), leaving the orphan-guard test alongside a WIRED `kailash_ml.rl` module flips the test from pass to fail — it becomes the SAME failure mode `rules/orphan-detection.md §4a` blocks.

- **`packages/kailash-ml/tests/regression/test_rl_orphan_guard.py`** — DELETED. Replaced by the §15 anti-regression suite at `packages/kailash-ml/tests/regression/test_rl_wired.py`. The orphan-guard's three assertions (`rl_train NOT in __all__`, `RLTrainer has zero engine call sites`, `RLTrainer does NOT consult detect_backend`) are LITERALLY INVERTED in the new file. Leaving the old file alongside the new one would red-light every CI run with `"DID NOT RAISE"` collection errors.

**BLOCKED rationalizations:**

- "The orphan-guard can stay as documentation of what was fixed"
- "We'll delete it in a follow-up PR"
- "CI will tell us when it fails"
- "The new test supplements the old one, they can coexist"

**Why:** The orphan-guard asserts the RL module is broken; 1.0.0 asserts it works. Both cannot be true. Retaining the orphan-guard causes CI to fail from the moment 1.0.0 ships — the exact failure mode `rules/orphan-detection.md §4a` prevents. DELETION in the same commit is structurally required.

### 17.3 From kailash-align TRL trainers

No user-visible migration for pure-RLHF users — `AlignmentPipeline` continues to work. NEW unified entry `km.rl_train(algo="dpo", ...)` dispatches to the same align trainer under the hood; see `ml-rl-align-unification-draft.md`.

## 18. Attribution

- **Stable-Baselines3** (MIT) — adapter patterns, callback architecture, hyperparameter defaults. Apache NOTICE entry required in `packages/kailash-ml/NOTICE`.
- **Gymnasium** (MIT) — environment protocol.
- **TRL (HuggingFace)** (Apache-2.0) — already attributed in `kailash-align`.
- **d3rlpy** (MIT) — offline RL adapters (when `[rl-offline]` installed).
- **`sb3_contrib`** (MIT) — `MaskablePPO` (post-1.0 per §1.2 RA-02).

Spec revisions:

- **2026-04-21 DRAFT** — initial draft closing round-1-rl-researcher.md findings.
- **2026-04-21 DRAFT (Phase-C-E)** — §1.2 expanded with RC-01 through RC-05 + RA-02 + RA-03 open-TBD closure; §3.1.1 pinned Decision 7 (`n_envs=1` literal default, `"auto"` explicit opt-in); §7 re-ordered as Tracker + Dashboard Integration; §8 new RLDiagnostics Class Surface matching DLDiagnostics §5 depth; §15 new anti-regression suite; §17.2 explicit deletion of `test_rl_orphan_guard.py`.
