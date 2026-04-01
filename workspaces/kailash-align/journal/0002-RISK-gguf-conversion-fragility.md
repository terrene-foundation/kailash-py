---
type: RISK
date: 2026-04-01
created_at: 2026-04-01T10:15:00+08:00
author: agent
session_turn: 1
project: kailash-align
topic: GGUF conversion is fragile and can fail silently
phase: analyze
tags: [gguf, llama-cpp, serving, ollama, risk]
---

# GGUF Conversion Fragility Risk

## Risk Description

AlignmentServing's GGUF export pipeline (`export_gguf()`) depends on llama.cpp's `convert_hf_to_gguf.py` script. Research reveals this conversion has MEDIUM reliability:

**What works**: Popular architectures (Llama 2/3, Mistral, Phi-3, Qwen2.5) with standard tokenizer configurations.

**What breaks**: Newer architectures, custom tokenizers, non-standard config.json fields, custom rope_scaling configurations. Critically, failures can be **silent** -- producing a valid-looking GGUF file that crashes only at inference time.

## Specific Failure Modes

1. **Silent malformation**: Renamed tokenizer_config.json keys or missing rope_scaling fields produce GGUF files that load without error but generate garbage or crash mid-inference.
2. **Architecture not supported**: convert_hf_to_gguf.py has a hardcoded architecture list. New model families fail immediately.
3. **LoRA adapter direct conversion**: NOT supported. Adapters MUST be merged into base weights first. Passing adapter_model.safetensors to the converter errors immediately.
4. **External binary dependency**: `llama-quantize` is compiled C++ that must be separately installed and on PATH.

## Likelihood and Impact

- **Likelihood**: HIGH for users working with newer or less popular model architectures
- **Impact**: HIGH -- user completes training (hours), evaluation (30+ minutes), then deployment fails with a cryptic error or silent corruption

## Mitigations (Incorporated into RT3-02)

1. Post-conversion validation: Run single-prompt inference test on GGUF before declaring success
2. "Bring your own GGUF" escape hatch for users who pre-convert using their own tooling
3. Supported architecture allowlist with explicit warnings for untested models
4. F16-first: Always convert to F16, then quantize separately
5. Clear error messages with manual conversion instructions as fallback

## For Discussion

1. Given that GGUF conversion from llama.cpp has known silent failure modes, should AlignmentServing offer vLLM as the _default_ deployment target (since vLLM loads HuggingFace models natively, no format conversion)?
2. If the post-conversion validation (single-prompt inference test) takes 30-60 seconds for an 8B model, is that acceptable latency in the deployment pipeline?
3. Would packaging `convert_hf_to_gguf.py` as a vendored dependency (rather than requiring users to install llama.cpp) reduce friction enough to justify the maintenance burden?
