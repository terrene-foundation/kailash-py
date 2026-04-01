# kailash-rl Overview Brief

## What This Is

kailash-rl is a NEW Python package for classical reinforcement learning. It is the 9th Kailash framework. It wraps stable-baselines3 and gymnasium with Kailash ecosystem integration (ModelRegistry, ExperimentTracker, DataFlow, Nexus).

**This is NOT LLM alignment.** GRPO, DPO, RLHF are in kailash-align. kailash-rl handles classical RL: training policies on observation/action spaces for environments (robotics, game AI, control systems).

**Install**: `pip install kailash-rl`

## Dependencies

```
kailash (core)
    +-- kailash-ml (ModelRegistry, ExperimentTracker)
kailash-rl
    +-- kailash, kailash-ml
    +-- stable-baselines3>=2.3
    +-- gymnasium>=0.29
    +-- sb3-contrib>=2.3  (optional, for TQC/RecurrentPPO/MaskablePPO)
```

## Engines

| Engine | Purpose |
|--------|---------|
| PolicyTrainer | Train RL policies via SB3 (PPO, SAC, DQN, A2C, TD3, HER) |
| EnvironmentRegistry | Register/discover gymnasium environments |
| EpisodeRecorder | Record/replay observation/action/reward sequences |

## Key Design

- Policies are models — stored in kailash-ml ModelRegistry
- Experiments tracked in kailash-ml ExperimentTracker
- Episodes persisted via DataFlow (optional)
- Trained policies servable via Nexus

## Backward Compatibility

`kailash-ml[rl]` extra will depend on `kailash-rl` as a redirect. Existing installs continue to work.
