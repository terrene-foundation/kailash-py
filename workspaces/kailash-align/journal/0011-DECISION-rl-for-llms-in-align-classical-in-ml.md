---
type: DECISION
date: 2026-04-01
created_at: 2026-04-01T13:46:00+08:00
author: co-authored
session_turn: 46
project: kailash-align
topic: RL-for-LLMs belongs in kailash-align; classical RL in kailash-ml[rl]
phase: analyze
tags: [architecture, rl, alignment, package-boundary]
---

# RL Domain Boundary Decision

## Decision

Two domains share the name "reinforcement learning" but have zero shared infrastructure:

1. **RL-for-LLMs** (GRPO, PPO/RLHF, RLOO, REINFORCE) → **kailash-align**
   - Uses: TRL, transformers, vLLM
   - Trains: language models on text generation
   - Rewards: verifiable correctness (math, code) or preference models

2. **Classical RL** (PPO for environments, SAC, DQN, TD3) → **kailash-ml[rl]**
   - Uses: stable-baselines3, gymnasium
   - Trains: policies on observation/action spaces
   - Rewards: environment step returns

## Rationale

- Zero shared primitives (different training loops, different data formats, different libraries)
- Different users (LLM alignment researchers vs. robotics/game AI engineers)
- GRPO in kailash-align wraps TRL's GRPOTrainer; PPO in kailash-ml[rl] wraps stable-baselines3's PPO — same algorithm name, completely different implementations
- Putting GRPO in kailash-ml[rl] would force LLM users to install gymnasium; putting SB3 PPO in kailash-align would force alignment users to install stable-baselines3

## Alternatives Considered

1. **Single kailash-rl package for both** — rejected: conflates fundamentally different domains
2. **GRPO in kailash-ml[rl]** — rejected: GRPO uses TRL/transformers, not SB3/gymnasium
3. **Separate kailash-rl for classical RL** — deferred: start as kailash-ml[rl] extra, extract if it grows to 5+ engines

## For Discussion

1. If a user wants to train an LLM agent that plays games (LLM + environment), which package do they use? This is a genuine edge case where both domains overlap.
2. The `kailash-ml[rl]` extra already exists in pyproject.toml but has no engines. At what point does "optional extra with no code" become misleading?
3. If we extract to kailash-rl later, can we do it without breaking `pip install kailash-ml[rl]`? (Yes — make kailash-rl a dependency of the [rl] extra.)
