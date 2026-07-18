## Summary

Implements the `governance_required` posture for direct LLM egress (#1779, EATP D6 parity) — an **opt-OUT** process/env posture that makes ungoverned direct-LLM egress **fail-closed**. OFF by default (zero back-compat break to adopt).

- **Core (kailash 2.54.0):** `kailash.is_governance_required()` / `set_governance_required()` (override → `KAILASH_GOVERNANCE_REQUIRED` env truthy `{1,true,yes,on}` → default OFF; unrecognized → OFF), typed `kailash.trust.pact.UngovernedEgressRefused` (names both remedies, no secrets).
- **kailash-kaizen 2.35.0:** enforced at every four-axis egress chokepoint — `LlmClient` (all constructors + a defense-in-depth lazy re-check in `embed`/`complete`/`stream`), `Agent`, `BaseAgent`, `LLMAgentNode` (both `workflow_generator` node-config builders + `_legacy_provider_chat` fallback), `EmbeddingGeneratorNode` (four-axis + ollama fallback). `UngovernedEgressRefused` propagates unwrapped (not re-typed).
- **kaizen-agents 0.10.0:** enforced across the ENTIRE direct-egress adapter layer — `kaizen_agents.llm.LLMClient`, every Delegate adapter (`OpenAI`/`Anthropic`/`Google`/`Ollama` stream + embedding), `AgentLoop`'s client factory, the orchestration structured adapters, and the runtime adapters. `ungoverned=True` threaded top-down through `Delegate` → `AgentLoop` → adapter registry → each adapter.

Mock/deterministic paths are exempt by class identity (never a network probe). `#1727` (`max_completion_tokens` for GPT-5/o-series) verified already shipped + regression-covered.

## Verification

- **`/redteam` to convergence** — 7 adversarial rounds (5 parallel lenses each, every finding independently verified; errored/throttled reviewers re-run per the evidence gate). Findings 9 → 10 → 1 → 2 → 3 → adapter-layer → (round 7 confirm). Every finding fixed with a regression test. One CRITICAL (fail-open interceptor exemption), several HIGH (opt-out plumbing, typed-error masking, ungated adapter egress) — all closed.
- **Exhaustive egress grep** (independent): every `AsyncOpenAI`/`OpenAI`/`anthropic`/`genai`/`httpx.AsyncClient` construction across `kaizen` + `kaizen-agents` is on a gated path (sole non-match is a docstring).
- **Tests:** core posture 19, kaizen gate 44, kaizen-agents adapter gate 35, + regression (core pact 1385; kaizen nodes/llm/core 3057; kaizen-agents delegate/orchestration 820). Byte-identity under posture OFF confirmed.
- **OFF-by-default:** the gate is a no-op unless the posture is explicitly enabled.

## Non-coverage (documented in `governance_posture.py`)

Raw direct use of the deprecated `kaizen.providers.llm.*` providers outside `LLMAgentNode` (retiring in #1720 Wave C).

## Related issues

Refs #1779. Cross-SDK (EATP D6) parity issues for the Rust SDK (#1727 defect + #1779 posture verification) filed separately.
