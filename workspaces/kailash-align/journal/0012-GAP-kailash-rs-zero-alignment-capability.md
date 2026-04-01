---
type: GAP
date: 2026-04-01
created_at: 2026-04-01T13:47:00+08:00
author: agent
session_turn: 47
project: kailash-align
topic: kailash-rs has zero alignment/RL capability — needs kailash-align-serving crate
phase: analyze
tags: [cross-sdk, kailash-rs, alignment, serving, gap]
---

# kailash-rs Zero Alignment Capability

## Gap

The Rust SDK has `kailash-ml` (inference-only via ONNX/Tract/Candle) but zero alignment, fine-tuning, or GGUF serving capability. There is no workspace, issue, or tracking for this gap in kailash-rs.

## Impact

Users who fine-tune models in Python (kailash-align) cannot serve them in Rust production services without bypassing the Kailash ecosystem entirely (e.g., calling Ollama directly).

## Recommended Resolution

Created workspace at `kailash-rs/workspaces/kailash-align-serving/` with brief. Recommended approach:

- **v1.0**: `kailash-align-serving` crate — GGUF loading via llama-cpp-rs, ModelRegistry integration
- Training stays in Python; Rust handles production inference
- Cross-SDK workflow: Python exports GGUF → Rust loads and serves via kailash-nexus

## Cross-References

- `kailash-py/workspaces/kailash-align/01-analysis/01-research/11-kailash-rs-gap-analysis.md`
- `kailash-rs/workspaces/kailash-align-serving/briefs/00-overview.md`

## For Discussion

1. Should kailash-rs also support LoRA adapter hot-swapping at runtime (load base model once, swap LoRA weights)? llama.cpp supports this natively.
2. Is Candle's GGUF support mature enough to avoid the llama-cpp-rs C dependency? Candle is pure Rust but may lag in GGUF format support.
3. Should the kailash-rs workspace be owned by the same team or filed as a cross-SDK issue?
