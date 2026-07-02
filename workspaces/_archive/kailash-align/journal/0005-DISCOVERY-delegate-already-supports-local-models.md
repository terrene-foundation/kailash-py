---
type: DISCOVERY
date: 2026-04-01
created_at: 2026-04-01T11:00:00+08:00
author: agent
session_turn: 1
project: kailash-align
topic: Kaizen Delegate already has full Ollama and vLLM support via existing adapters
phase: analyze
tags: [kaizen, delegate, ollama, vllm, integration]
---

# Kaizen Delegate Already Supports Local Models

## Discovery

Audit of the Kaizen Delegate implementation (`packages/kaizen-agents/src/kaizen_agents/delegate/`) reveals that local model support is already fully implemented:

1. **OllamaStreamAdapter**: Complete implementation using httpx against Ollama's `/api/chat` endpoint. Supports streaming, tool calling, and token usage tracking. No additional SDK dependency needed.

2. **OpenAIStreamAdapter**: Works with vLLM's OpenAI-compatible API by setting `base_url` to the vLLM endpoint. Already tested pattern.

3. **Provider configuration**: `KzConfig` supports `provider = "ollama"` via TOML config or `KZ_PROVIDER` environment variable.

4. **Adapter injection**: `Delegate(adapter=OllamaStreamAdapter(...))` allows passing a pre-configured adapter directly.

## Implications for KaizenModelBridge

KaizenModelBridge is **simpler than expected**. It does not need to create new adapters or modify the Delegate system. It is a pure convenience layer:

1. Look up adapter metadata from AdapterRegistry
2. Determine deployment target (Ollama or vLLM)
3. Construct the appropriate existing adapter with correct base_url and model name
4. Return a configured Delegate

Estimated code: 150-250 lines. No changes to the Delegate or adapter codebase.

## One Gap: `local_hf` Strategy

The only strategy that requires NEW infrastructure is `local_hf` (direct in-process HuggingFace inference). This has no existing adapter and would require implementing streaming generation from `transformers.pipeline`. However, this is explicitly marked "dev only, slow" in the architecture doc and can be safely deferred to v1.1.

## Cost Model Consideration

The Delegate's `_estimate_cost()` function uses cloud API pricing. For local models, token costs are effectively $0 (compute cost is separate). This means `budget_usd=10.0` with a local model will never trigger budget exhaustion. This is a known gap but low priority -- it does not affect functionality.

## For Discussion

1. Since OllamaStreamAdapter already exists and is well-tested, should KaizenModelBridge be positioned as the ONLY way to connect fine-tuned models to Delegate (opinionated path), or should the existing manual `Delegate(adapter=OllamaStreamAdapter(...))` pattern be documented as an alternative?
2. The Delegate's cost model reports $0 for local inference. Should KaizenModelBridge inject a "local compute cost" estimate based on model size and tokens generated, or is this over-engineering for v1?
3. If vLLM users already know they can use `OpenAIStreamAdapter(base_url="http://localhost:8000/v1")`, what additional value does KaizenModelBridge provide beyond auto-detecting the strategy?
