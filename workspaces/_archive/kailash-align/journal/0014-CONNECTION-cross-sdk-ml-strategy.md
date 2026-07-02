---
type: CONNECTION
date: 2026-04-01
created_at: 2026-04-01T14:30:00+08:00
author: agent
session_turn: 85
project: kailash-align
topic: Cross-SDK ML strategy — Python wraps, Rust implements natively, alignment is Python-only
phase: analyze
tags: [cross-sdk, architecture, ml, alignment, rl, strategy]
---

# Cross-SDK ML Strategy

## The Three ML Domains and Their SDK Homes

| Domain            | kailash-py                                     | kailash-rs                                           | Rationale                                                         |
| ----------------- | ---------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------- |
| **Classical ML**  | kailash-ml (wraps sklearn/lightgbm, 9 engines) | kailash-ml (native Rust, 17 crates, 455+ algorithms) | Both implement independently per EATP D6. Rust is more ambitious. |
| **LLM Alignment** | kailash-align (wraps TRL, 17+ methods)         | kailash-align-serving (GGUF inference only)          | Training requires PyTorch/TRL — no Rust equivalent. Rust serves.  |
| **Classical RL**  | kailash-ml[rl] (wraps SB3/gymnasium)           | None planned                                         | SB3/gymnasium are Python-only. No Rust RL ecosystem.              |

## Key Architectural Difference

- **Python SDK wraps**: sklearn, lightgbm, TRL, stable-baselines3 — leverage existing ecosystem
- **Rust SDK implements**: Native algorithms, faer linear algebra, type-state traits — own the stack

This is by design (kailash-rs D1 decision): kailash-ml (Rust) is a standalone library with zero Kailash dependency. Python bindings via PyO3 (M14) will make Rust's compute layer available to Python users as well.

## Cross-SDK Workflow

```
Classical ML:
  Python: kailash-ml → sklearn/lightgbm wrappers → fast to ship
  Rust:   kailash-ml → native implementations → performance-focused
  Parity: Matching API semantics (fit/predict/transform), different internals

LLM Alignment:
  Python: kailash-align → TRL trainers → SFT/DPO/GRPO/KTO/ORPO
  Rust:   kailash-align-serving → GGUF loading → production inference
  Bridge: Python exports GGUF → Rust loads and serves via Nexus

Classical RL:
  Python: kailash-ml[rl] → SB3/gymnasium → PolicyTrainer, EnvironmentRegistry
  Rust:   (none)
```

## Implications for kailash-py Development

1. kailash-py kailash-ml can ship faster by wrapping existing libraries
2. kailash-py kailash-align is the ONLY training path for LLM alignment across both SDKs
3. When kailash-rs PyO3 bindings ship (M14), Python users can choose Python-native or Rust-backed compute
4. kailash-py classical RL (kailash-ml[rl]) has no Rust counterpart — this is fine given RL's Python-centric ecosystem

## For Discussion

1. When kailash-rs kailash-ml-python (PyO3) ships, should kailash-py users be migrated to Rust-backed compute, or should both paths coexist?
2. Should kailash-align eventually support Rust-backed inference for GRPO online rollouts (via kailash-align-serving as vLLM alternative)?
3. The Rust kailash-ml targets 0.5-0.7x LightGBM performance in V1. Is this acceptable for production, or do users need V2 (0.8-0.95x) before switching from Python?
