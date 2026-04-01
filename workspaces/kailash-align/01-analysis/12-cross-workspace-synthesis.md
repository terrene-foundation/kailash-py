# Cross-Workspace Synthesis: Alignment + RL Expansion

## Research Summary

11 research documents (01-11) produced across 4 parallel research agents. Key findings synthesized below.

## 1. kailash-align: Method Coverage Gap (CRITICAL)

### Current: 2 methods (SFT + DPO)

### Required: 17+ methods across 4 categories

| Category                    | Methods                          | TRL Support                                                                                            | Priority                             |
| --------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------ |
| **Preference (offline)**    | DPO, IPO, CPO, SimPO, NCA, BCO   | All via DPOTrainer `loss_type`                                                                         | P0 — trivial config change           |
| **Preference (unpaired)**   | KTO                              | KTOTrainer (experimental)                                                                              | P1 — new trainer, new data format    |
| **Preference (monolithic)** | ORPO                             | ORPOTrainer (experimental)                                                                             | P1 — eliminates SFT+DPO pipeline     |
| **Online RL**               | GRPO, RLOO, Online DPO, PPO/RLHF | GRPOTrainer (stable), RLOOTrainer (stable), OnlineDPOTrainer (experimental), PPOTrainer (experimental) | P1 — new pipeline concept (rollouts) |
| **Self-play**               | SPIN, XPO, Nash-MD               | SPINTrainer (experimental), XPOTrainer (experimental), NashMDTrainer (experimental)                    | P2 — experimental                    |
| **Verifier RL**             | RLVR, DAPO                       | Not in TRL (custom)                                                                                    | P3 — requires custom implementation  |

### Quick Win: DPO `loss_type` Parameter

Adding `loss_type` to AlignmentConfig unlocks 14 DPO variants with ZERO new trainer code:

```python
# Current: only "sigmoid" (standard DPO)
# Available: "hinge", "ipo", "exo_pair", "nca_pair", "robust",
#   "bco_pair", "sppo_hard", "aot", "aot_pair", "apo_zero",
#   "apo_down", "simpo", "cpo", "padll"
```

This single field change covers IPO, SimPO, NCA, CPO, BCO, and 9 more variants.

### Architecture Change: Registry-Driven Pipeline

Current `pipeline.py` has hard if-elif on method name. Needs:

1. **MethodRegistry** — maps method name → (TrainerClass, ConfigClass, DataValidator, MetricsExtractor)
2. **Generic `_run_training()`** — replaces `_run_sft()` and `_run_dpo()`
3. **Separate online pipeline** — GRPO/RLOO/PPO need rollout generation, not just dataset training

### Data Format Expansion

| Format                                         | Methods                         | Current Support |
| ---------------------------------------------- | ------------------------------- | --------------- |
| `{prompt, chosen, rejected}`                   | DPO, IPO, CPO, SimPO, NCA, ORPO | YES             |
| `{prompt, completion, label}`                  | KTO, BCO                        | NO              |
| `{prompt}` + reward function                   | GRPO, RLOO, RLVR                | NO              |
| `{prompt, chosen, rejected}` + online rollouts | Online DPO, XPO                 | NO              |

## 2. kailash-rl vs kailash-rl (ARCHITECTURAL DECISION)

### Shared Primitives Analysis

| kailash-ml Engine | Applies to RL? | Notes                                             |
| ----------------- | -------------- | ------------------------------------------------- |
| ModelRegistry     | YES            | Policies are models                               |
| ExperimentTracker | YES            | Track rewards, episodes                           |
| ModelServer       | PARTIAL        | Serve policies via Nexus                          |
| FeatureStore      | NO             | RL uses environments, not features                |
| FeatureEngineer   | NO             | —                                                 |
| DataVersioner     | NO             | RL uses environments, not datasets                |
| DataExplorer      | NO             | —                                                 |
| AutoMLEngine      | NO             | RL hyperparam tuning is different                 |
| TrainingPipeline  | NO             | `model.learn(env, timesteps)` ≠ `model.fit(X, y)` |

**Result**: 2 of 9 engines shared. RL needs 5-7 NEW engines (PolicyTrainer, EnvironmentRegistry, EpisodeRecorder, RewardShaper, ReplayBufferStore).

### Recommendation

**Phase 1**: `kailash-rl` with 2-3 engines. The `[rl]` extra already exists in pyproject.toml.
**Phase 2**: Extract to `kailash-rl` if RL grows to 5+ engines with distinct users (following kailash-align precedent).

### RL-for-LLMs Boundary

| Domain                                   | Library                      | Package            |
| ---------------------------------------- | ---------------------------- | ------------------ |
| GRPO, PPO/RLHF, RLOO, REINFORCE for LLMs | TRL, transformers            | **kailash-align**  |
| PPO, SAC, DQN for environments           | stable-baselines3, gymnasium | **kailash-rl** |

These share a name ("RL") but zero infrastructure.

## 3. kailash-rs Gap (CRITICAL)

kailash-rs has **zero alignment/RL capability**:

- `kailash-ml` crate: inference-only (ONNX, Tract, Candle backends)
- No alignment training, no RL training, no GGUF serving
- No workspace or tracking for this gap

### Recommended Path for kailash-rs

1. **v1.0**: `kailash-align-serving` crate — GGUF loading via llama-cpp-rs, ModelRegistry integration
2. **v1.1**: Optional PyO3 bridge to Python kailash-align for training
3. **v2.0+**: Candle/Burn native training (if ecosystem matures)

Training stays in Python. Rust handles serving.

## 4. Implementation Phases

### Phase A: Quick wins (1 session)

- Add `loss_type` to AlignmentConfig → unlocks 14 DPO variants
- Update method validation to accept all TRL-supported methods
- Update AdapterSignature to accept dynamic method names

### Phase B: Method-agnostic pipeline (2-3 sessions)

- MethodRegistry with trainer/config/validator/metrics per method
- KTOTrainer, ORPOTrainer integration (new data formats)
- Generic `_run_training()` replacing hard-coded methods
- Tests for each method

### Phase C: Online RL methods (2-3 sessions)

- GRPOTrainer integration (rollout-based training)
- RLOOTrainer integration
- Reward function protocol
- Online training pipeline (separate from offline)

### Phase D: Classical RL (2-3 sessions)

- kailash-rl engines: PolicyTrainer, EnvironmentRegistry, EpisodeRecorder
- stable-baselines3 + gymnasium integration
- Tests with CartPole, LunarLander

### Phase E: kailash-rs serving (1-2 sessions, in kailash-rs repo)

- kailash-align-serving crate
- llama-cpp-rs GGUF loading
- Nexus integration for API exposure

## 5. Industry Context (Why This Matters)

- **GRPO is the method behind DeepSeek-R1** — the most impactful open-source model of 2025
- **DPO is being augmented, not replaced** — IPO, SimPO, ORPO are all DPO improvements
- **Binary feedback (KTO) is production-critical** — most real systems have thumbs-up/down, not pairwise preferences
- **RLVR (RL from Verifiable Rewards) is the future** — reasoning tasks need verifiable correctness signals
- **Reference-free methods are winning** — SimPO, ORPO save ~50% GPU memory
