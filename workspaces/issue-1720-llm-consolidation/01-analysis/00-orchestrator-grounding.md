# #1720 Consolidation — Orchestrator Grounding (evidence-first, self-verified)

Session 2026-07-16. HEAD `e36c5d70`. All anchors below were read directly this
session (NOT carried from the parity-delta journal — PRs #1719/#1738 landed since).

## The two layers

| | Legacy `providers/llm/` | Four-axis `llm/` |
|---|---|---|
| Completion send | SOLE production path | `complete()` @ `client.py:867`, `stream()` @ `client.py:1014` (PR #1719) |
| Request shape | kwargs-driven `chat()` | `CompletionRequest` (`deployment.py`, frozen, `extra="forbid"`) — **8 fields only**: model/messages/temperature/top_p/max_tokens/stop/stream/user |
| Tool calling | FULL — `openai.py:177 chat()`, tools @ `256`, tool_calls parse @ `277`; tool-loop `llm_agent.py:888-939` | **ABSENT** |
| Structured output | `openai.py:249-252` response_format; post-parse `llm_agent.py:1014-1040` | **ABSENT** |
| Reasoning filter | `openai.py:129-171 _filter_reasoning_model_params` | **ABSENT** |
| Extended sampling | seed/logit_bias `openai.py:234-239` | **ABSENT** |
| Per-request BYOK | `llm_agent.py:863-883` | **ABSENT** (auth frozen on deployment) |
| Multimodal | `core/base_agent.py:333-379`, `providers/llm/multi_modal_adapter.py` | **ABSENT** |
| Mock | `providers/llm/mock.py` | **NO mock preset** |
| Embeddings | all providers | `embed()` @ `client.py:445` — OpenAI + Ollama wires only |

## Additive-extension architecture (verified clean)

The four-axis path is a clean data-driven pipeline — new capability = additive field, no caller branch:

1. **`CompletionRequest`** (`deployment.py`) — add optional fields (frozen model, `extra="forbid"`, so additions are backward-safe).
2. **`complete()` / `stream()`** (`client.py:867/1014`) — add matching kwargs.
3. **`_build_completion_request`** (`client.py:762-802`) — thread kwargs → CompletionRequest.
4. **Per-wire shaper** — `_build_completion_payload_and_url` (`client.py:804`) → `shaper.build_request_payload(request)`; `parse_response` extracts. Dispatch tables: `_EMBED_DISPATCH` (`client.py:79`), `_COMPLETE_DISPATCH` (`client.py:105`). 11 wire adapters under `llm/wire_protocols/`.

## LOAD-BEARING SAFETY CLAIM (verified)

`grep -rln LlmClient src/kaizen/ | grep -v /llm/` → **EMPTY**. No production code outside
the `llm/` module consumes four-axis `complete()`/`stream()`. Therefore **Wave 1 (four-axis
parity) is purely additive** — adding tools/structured/multimodal/sampling/mock/embed
capabilities regresses NOTHING in production. This is what gates the wave strategy:
Wave 1 = autonomous (additive, reversible); Waves 2–4 = human-gated (touch/remove the prod path).

## Shared-file contention (drives shard shape)

Every capability axis touches the SAME 2 shared files: `CompletionRequest` (deployment.py)
+ `complete()`/`stream()` signature (client.py). Parallel capability-shards would collide
there. → Wave 1 needs a **foundational serial shard 1a** (CompletionRequest superset +
signature + threading), THEN parallel fan-out (1b) sharded by **wire adapter** (one file =
one owner) + per-capability parse logic. Analysis workflow `wf_f4304516-6dc` refines per-axis
LOC/invariant/wave assignments.

## Consumers to migrate (Waves 3, human-gated) — 10 src files, verified count

`config/__init__.py`, `config/providers.py`, `core/agents.py`, `core/base_agent.py`,
`nodes/ai/__init__.py`, `nodes/ai/embedding_generator.py`, `nodes/ai/llm_agent.py`,
`providers/__init__.py`, `providers/document/provider_manager.py`, `providers/registry.py`.
Ordered migration: llm_agent → base_agent → embedding_generator → registry.

## Delete-gate (Wave 4, irreversible, human-gated)

Legacy `providers/llm/` deleted LAST, gated on a `tests/regression/` four-axis quickstart
running `LlmClient.from_deployment(...).complete(...)` end-to-end green in the release
pipeline (unit-green ≠ release-green).
