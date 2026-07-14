---
type: DISCOVERY
date: 2026-07-14
author: agent
project: issue-1717-vertex-claude
topic: "#1721 read receipt — Rust kaizen from_env legacy precedence (deepseek + broader divergence)"
phase: redteam
tags: [cross-sdk, "1721", read-receipt, from-env, parity]
relates_to: 0004-cross-repo-grant-1721-rust-read
---

# Read receipt — Rust legacy from_env precedence (grant 0004)

Cross-repo READ executed under the journaled grant (0004, `cross-repo-authorized:
esperie-enterprise/kailash-rs`). Read-only, scoped to the from_env legacy-precedence
question. Evidence quoted from the local Rust clone
`/Users/esperie/repos/kailash/build/kailash-rs`.

## Finding 1 — Rust HAS deepseek in its legacy tier (my xfail reason was WRONG)
`crates/kailash-kaizen/src/llm/client.rs:580`:
`if let Ok(key) = std::env::var("DEEPSEEK_API_KEY") { ... keys.insert(LlmProvider::DeepSeek, key); }`
So Python's `DEEPSEEK_API_KEY` legacy entry is cross-SDK-ALIGNED, not "Python-ahead."
The strict-xfail's original reason ("Rust should adopt") is incorrect and must be fixed.

## Finding 2 — genuine, broader Python↔Rust legacy divergence
Actual Rust legacy if-let order (client.rs:481–590):
`OPENAI, ANTHROPIC, GOOGLE(/GEMINI), MISTRAL, COHERE, OLLAMA, HUGGINGFACE,
PERPLEXITY, DEEPSEEK, DOCKER_MODEL_RUNNER` — **10 keys, NO Azure**
(`AZURE_OPENAI_API_KEY` appears in Rust ONLY at client.rs:4967/5137 = test code).

Python `from_env.py::LEGACY_KEY_ORDER`:
`OPENAI, AZURE_OPENAI, ANTHROPIC, GOOGLE, DEEPSEEK` — **5 keys, WITH Azure**.

They genuinely diverge:
- Python HAS `AZURE_OPENAI_API_KEY` in legacy auto-detect; Rust does NOT.
- Rust HAS MISTRAL/COHERE/OLLAMA/HUGGINGFACE/PERPLEXITY/DOCKER in legacy; Python does NOT.
- Both share OPENAI, ANTHROPIC, GOOGLE, DEEPSEEK.

## Finding 3 — the checked-in fixture is stale, matches NEITHER SDK
`tests/cross_sdk_parity/fixtures/rust_from_env_precedence.json::precedence_order[2].key_order`
= `[OPENAI, AZURE_OPENAI, ANTHROPIC, GOOGLE]` (4 keys). This matches neither the actual
Rust source (10 keys, no Azure) nor Python (5 keys). It is stale/incorrect.

## Disposition
- The deepseek-specific question is RESOLVED: Rust has it; Python is aligned.
- The test cannot be cleanly un-xfailed: a genuine Python↔Rust legacy-precedence
  divergence (Azure + 6 providers + order) remains, and the fixture is stale.
- Reconciliation (which legacy set/order is canonical? does Python keep Azure? does
  it adopt the 6 Rust providers? does the fixture regenerate to real Rust?) is a
  cross-SDK DESIGN decision + a WRITE — beyond this read-only grant.
- Action taken IN-REPO (safe, no semantic change): correct the strict-xfail reason
  to the accurate finding; surface the reconciliation to the co-owner on #1721.
- NOT taken (needs co-owner + write authorization): editing the fixture or
  `LEGACY_KEY_ORDER` to force a match — that decides cross-SDK semantics.
