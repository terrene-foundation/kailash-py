# Legacy vs four-axis parity delta (consolidation decision input)

Source: parity-delta analyst, 2026-07-13. READ-ONLY. **Tooling caveat:** ripgrep
absent in that agent's env → Part 4 (test surface) + full consumer enumeration are
DIRECTIONAL; re-grep before committing the consolidation program plan:
`grep -rn 'get_provider\|from kaizen.providers' src/`,
`grep -rln 'providers.llm\|get_provider\|MockProvider' tests/`.

## Headline
Four-axis is a CONFIG superset (24+ presets) but a RUNTIME near-empty-set: `LlmClient`
implements ONE send (`embed()`) for 2 of 11 wires. NO completion send path today.
`CompletionRequest` has NO tools / structured / multimodal / reasoning / seed / logit_bias /
BYOK-per-request. Legacy is the SOLE production completion path.

## Four-axis GAPS vs legacy (block legacy deletion)
- tools/function-calling, structured output, streaming SEND, multimodal, reasoning-param
  filter, seed/penalties, per-request BYOK, sync+async send — ALL absent.
- Protocols (ToolCallingProvider/StructuredOutputProvider/StreamingProvider,
  `providers/base.py:132-179`) exist but UNWIRED.
- NO chat shaper for OpenAiChat (most-used), Bedrock, Vertex, Azure (this session's
  Stream 1 adds OpenAI chat + Vertex/Bedrock handling).
- NO `mock` preset — offline tests depend on it; blocks deletion.
- cohere/huggingface/azure EMBEDDINGS not in embed dispatch.

## Consumers to migrate (5 confirmed; ~8-15 total est)
1. `llm_agent.py:2189-2213` `_provider_llm_response` → get_provider().chat(...,tools). CRITICAL hot path, tool-loop 888-939.
2. `base_agent.py:333-379` `_simple_execute_async` → OpenAIProvider().chat_async, multimodal. HIGH.
3. `embedding_generator.py:661-664` → get_provider(p,"embeddings"). MEDIUM.
4. `registry.py:206` get_streaming_provider. HIGH.
5. `registry.py:165` get_provider_for_model.

## VERIFIED counts (orchestrator re-grep, closes the ripgrep caveat)
- Legacy-consumer src files (10): `config/__init__.py`, `config/providers.py`,
  `core/agents.py`, `core/base_agent.py`, `nodes/ai/__init__.py`,
  `nodes/ai/embedding_generator.py`, `nodes/ai/llm_agent.py`, `providers/__init__.py`,
  `providers/document/provider_manager.py`, `providers/registry.py` (53 total refs).
- Legacy-touching test files: 34. Confirms migration surface for the program plan.

## Verdict — consolidation is a 6-10 session program
(a) four-axis→parity ~4-6 sessions; (b) migrate consumers ~1-2; (c) delete legacy+tests ~1-2.
Highest risk: streaming-with-tools delta accumulation; `_provider_llm_response` tool-loop +
structured post-parse parity; mock-preset absence; RELEASE GATE — no four-axis quick-start
regression exists (unit-green ≠ release-green).

## Decision for THIS session
Close ALL #1717 four-axis gaps now (prerequisite to any consolidation, valuable standalone).
Do NOT delete legacy — naive deletion regresses agent tool-calling/structured-output.
Recommend the ADDITIVE path: build complete() parity → dual-run behind `_provider_llm_response`
→ migrate consumers one at a time → delete legacy LAST, gated on a four-axis quick-start
regression being pipeline-green. Surface this sequenced program to the co-owner as the
redundancy resolution (a structural, multi-session decision — their call to authorize scope).
