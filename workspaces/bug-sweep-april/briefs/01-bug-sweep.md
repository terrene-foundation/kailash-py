# Bug Sweep — April 2026

Fix all user-facing bugs from GitHub issues #339-#368 before resuming platform-architecture-convergence.

## Issues (from /analyze triage)

### Critical

- #339 — BaseAgent MCP tools discovered but never executed
- #361 — OllamaStreamAdapter tool-call args sent as JSON string instead of object
- #363 — OllamaStreamAdapter strips tool_call_id and name from tool-role messages

### High

- #340 — GoogleGeminiProvider sends response_mime_type + tools together (crashes Gemini 2.5)
- #362 — PipelineExecutor blocks asyncio event loop during serialize/hash
- #364 — OllamaStreamAdapter stream=True + tools incompatible with many Ollama versions
- #368 — \_on_source_change crashes parameterized products by calling execute_product without params

### Medium

- #357 — BaseAgent MCP auto-discovery breaks structured output on Gemini (depends on #340)

### Low

- #367 — OllamaStreamAdapter polish (num_predict, kwargs merge, ID collisions)
- #355 — Already fixed in code, close issue

## Execution Strategy

Bundle into PRs by affected code area:

- PR A: Ollama fixes (#361 + #363 + #367) — single file
- PR B: Kaizen provider fixes (#340 + #357) — GoogleGeminiProvider
- PR C: DataFlow fixes (#368 + #362) — Fabric runtime/pipeline
- PR D: BaseAgent MCP execution (#339) — largest fix
- PR E: Ollama streaming fallback (#364)
