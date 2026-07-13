# #1717 — Vertex-Claude four-axis completion send path + WIF; legacy/four-axis redundancy

## Analysis (4-agent parallel deep-dive, 2026-07-13)

**Reframed finding — the redundancy is inverse to the issue's framing:**
- LEGACY `providers/llm/` is the PRIMARY and ONLY production LLM completion path.
  `BaseAgent → AgentLoop → LLMAgentNode → get_provider().chat()` (`llm_agent.py:2189`,
  `base_agent.py:333`). Supports tools/function-calling + structured output.
- NEW four-axis `LlmClient` layer is ORPHANED — zero production construction sites,
  `complete()` deliberately unexposed, only `embed()` wire-sends. `CompletionRequest`
  has NO tools / NO structured-output fields.
- ⇒ Four-axis CANNOT replace legacy today without regressing agent tool-calling.
  Closing #1717's gaps is a PREREQUISITE to any consolidation, and is valuable
  regardless of the consolidation decision. So we close all gaps now, compute the
  exact parity delta in parallel, and surface the consolidation as a sequenced program.

## Confirmed gaps (all CONFIRMED at file:line by analysis agents)
- No `complete()`/`stream()` in four-axis layer (`client.py:28-34`). Only `embed()`.
- Anthropic body carries `model`, no `anthropic_version` (`anthropic_messages.py:81-85`).
- `:rawPredict`/`:streamRawPredict` verb only in comments (`presets.py:1289..1438`).
- Bedrock-Claude reuses AnthropicMessages + empty path_prefix (`presets.py:1013-1024`);
  needs `/model/{id}/invoke` + `anthropic_version: bedrock-2023-05-31`.
- GCP auth SA-key-only; `google.auth.default` a presence sentinel; 0 WIF refs
  (`auth/gcp.py:250-276,46,176`). Sync `apply()` cold-raises (`gcp.py:401-408`).
- Region regex rejects `us`/`eu`/`global` (`presets.py:1312`, `from_env.py:70`).
- `_VERTEX_CLAUDE_MAPPING` tops at `claude-opus-4-5`; bare `claude-opus-4-8` raises
  (`grammar/vertex.py:89-101,139`). Gemini already passes `gemini-*` through.
- `from_env` doesn't read `GOOGLE_CLOUD_PROJECT`/`VERTEX_LOCATION`; no vertex selector
  branch (`from_env.py:254-293`).
- No alias layer: `vertex-anthropic` unresolved, `vertex_claude` exact-key only.
- Parity tests assert preset NAMES only, never on-wire bytes (`test_preset_names_match_rust.py`).
- NEW-A: no per-model temperature constraint → HTTP 400 on `claude-opus-4-8`.
- NEW-B: `eu`/`us`/`global` must pass through as valid Vertex locations.
- NEW-C: both `vertex-anthropic` AND `vertex_claude` must resolve to the same preset.

## Test infra
- Mock lib: `respx` (dev dep, httpx-native). HTTP client = httpx via `LlmHttpClient`.
- Runner: `cd packages/kailash-kaizen && python -m pytest ...`. `asyncio_mode=auto`.
- Wire-behavior tests (URL+body+headers) are the uncovered surface to add.

## Execution plan — 2 disjoint-file parallel streams + tests + gate

**Stream 1 — Core completion path** (files: `deployment.py`, `presets.py`, `client.py`,
`http_client.py`, `wire_protocols/anthropic_messages.py`, `wire_protocols/google_generate_content.py`,
new `wire_protocols/*` if needed). Owns the full completion contract: `complete()`/`stream()`,
`_COMPLETE_DISPATCH`, per-wire URL (`:rawPredict`/`:streamRawPredict`, bedrock `/invoke`),
post-shaper Anthropic body transform (strip `model` + inject `anthropic_version`, GATED so
direct paths stay byte-identical), NEW-A temperature constraint, streaming transport,
region `us`/`eu`/`global` (NEW-B), preset aliases (NEW-C). Keep preset factory public
signatures backward-compatible (Stream 2 calls them).

**Stream 2 — Auth + env config + catalog** (files: `auth/gcp.py`, `from_env.py`,
`grammar/vertex.py`). WIF `external_account` (STS + impersonation), metadata-server ADC,
`google.auth.default()` ADC, creds JSON-`type` dispatch; `GOOGLE_CLOUD_PROJECT`/`VERTEX_LOCATION`
+ vertex selector branch; `claude-opus-4-8` catalog (adopt `startswith("claude-")` passthrough
like Gemini). DISJOINT from Stream 1's files.

**Stream 3 — Tests** (after 1+2 merge): respx wire tests (Vertex-Claude `:rawPredict` URL +
`anthropic_version` body + no `model` + Bearer; Vertex-Gemini; Bedrock), cross_sdk_parity
wire extension, streaming, auth-mode tests.

**Gate:** parallel reviewer + security-reviewer → /redteam to convergence (evidence-gated).

## Consolidation decision (surfaced, evidence-backed after parity-delta agent)
Removing legacy requires four-axis to reach feature parity (tools, structured output, full
provider coverage) THEN migrating `LLMAgentNode`+`_simple_execute_async` — a multi-session,
high-risk hot-path program. Not a naive deletion this session (would regress agents).
Recommendation + exact delta to be presented to the co-owner.

Invariant count per stream: S1 ~6 (dispatch, URL-per-wire, body-gate, stream, temp, alias);
S2 ~4 (WIF, metadata-ADC, default-ADC, config-env). Both within budget.
