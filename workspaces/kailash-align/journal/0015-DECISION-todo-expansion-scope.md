---
type: DECISION
date: 2026-04-01
created_at: 2026-04-01T14:40:00+08:00
author: co-authored
session_turn: 90
project: kailash-align
topic: Todo expansion from 13 to 27 — full alignment landscape + classical RL + kailash-rs
phase: todos
tags: [scope, planning, alignment, rl, architecture]
---

# Todo Expansion Scope Decision

## Decision

Expanded todo list from 13 (SFT+DPO only) to 27 covering:

| Milestone            | Todos | Scope                                                                   |
| -------------------- | ----- | ----------------------------------------------------------------------- |
| M0: Foundation       | 2     | Package skeleton, TRL bump to >=1.0                                     |
| M1: Core Training    | 4     | SFT, DPO + loss_type (14 variants), AdapterRegistry                     |
| M2: Method Expansion | 6     | MethodRegistry, KTO, ORPO, GRPO, RLOO, experimental trainers            |
| M3: Online RL Infra  | 3     | RewardRegistry (security), vLLM integration, GPU memory                 |
| M4: Eval + Serving   | 3     | Evaluator, GGUF/Ollama, adapter merge                                   |
| M5: Integration      | 3     | Kaizen bridge, on-prem cache, integration tests                         |
| M6: Classical RL     | 4     | PolicyTrainer, EnvironmentRegistry, EpisodeRecorder (in kailash-ml[rl]) |
| M7: Docs + Release   | 2     | README, CHANGELOG, PyPI                                                 |

## Rationale

1. **The user explicitly called out the previous scope as too narrow** — "alignment is not just RLHF, GRPO etc too"
2. **TRL already supports 17+ methods** — not supporting them is leaving value on the table
3. **GRPO (DeepSeek-R1 method) is the industry priority** — must be first-class, not an afterthought
4. **DPO loss_type is zero-effort** — 14 variants unlocked by a single config field
5. **Classical RL has specced deps but no engines** — completing the kailash-ml[rl] story

## Session Estimate

**Optimal (parallel agents)**: 10-12 autonomous sessions
**Sequential**: 15-18 autonomous sessions
**Previous scope**: 6-10 sessions (SFT+DPO only)

## For Discussion

1. Is M6 (Classical RL) the right priority? It's in a different package (kailash-ml, not kailash-align). Should it be a separate workspace?
2. M3 (vLLM + GPU memory) is the hardest milestone — it requires multi-GPU coordination. Should this be deferred if single-GPU GRPO works without vLLM?
3. The total of 27 todos across 7 milestones is large. Should implementation be split into two PRs (M0-M2 as first, M3-M7 as second)?
