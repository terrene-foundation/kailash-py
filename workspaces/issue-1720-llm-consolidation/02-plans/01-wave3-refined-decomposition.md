# #1720 — Wave-3 Refined Decomposition (post-mapping, 2026-07-16)

Supersedes the Wave-3/4 rows of `00-architecture-and-waves.md` with a code-grounded
decomposition. Anchors are grep-stable symbols (re-resolve before building per
`symbol-anchored-citations.md`).

## What the parallel mapping established (ground truth)

- Four-axis `LlmClient` is **not yet load-bearing on any live path** — the only non-`llm/`
  callers are the dual-run _shadow_ (`llm_agent.py::_run_llm_dual_run_shadow`) and
  `nodes/ai/azure_backends.py`. Every real agent request still flows legacy
  (`_provider_llm_response` → `providers.registry.get_provider(...).chat(...)`).
- **Shipped Wave-2 shadow bug (ungated, zero-tolerance Rule 1):** `_run_llm_dual_run_shadow`
  builds four-axis calls via `_sampling_kwargs_from_generation_config`, which does NOT
  reproduce the legacy OpenAI/azure/docker default `tool_choice = "required" if tools else
"auto"` (`providers/llm/openai.py::OpenAIProvider.chat` — the `default_choice` block). The
  shadow therefore sends `tool_choice`-unset while legacy forces `"required"`, so
  `diff_legacy_vs_fouraxis` logs **false** `llm.dual_run.divergence` WARNs on every
  tool-using agent.
- **Azure shadow blind spot:** `_shadow_deployment_for` (`llm_agent.py`) maps
  openai/anthropic/google/gemini/cohere/huggingface/perplexity/pplx/ollama/docker — but **no
  azure variant**. Azure traffic is never shadowed; `azure_ai_foundry` has no confirmed
  four-axis wire.
- **`EmbedOptions` gap:** legacy Cohere embeddings pass `input_type="search_document"`
  (`embedding_generator.py::_generate_provider_embedding`); four-axis `EmbedOptions`
  (`deployment.py`) has no `input_type` field — silent semantic drop on migration.
- **F3 (HF chat routing):** the HF shaper (`wire_protocols/huggingface_inference.py::
build_request_payload`) fully implements tools under `use_chat_schema=True`, but
  `client.py::_build_completion_payload_and_url` never passes the flag and `_COMPLETE_DISPATCH`
  routes only to `/models/{model}` (classic text-generation). Tool emission is unreachable →
  live `huggingface_inference.tools_dropped_classic_path` WARNs.
- **Harness determinism:** `MockLlmHttpClient` (four-axis) and `MockProvider` (legacy) are each
  deterministic but NOT byte-identical (documented id/seed divergence). The parity harness MUST
  inject **shared canned bytes** into both boundaries, not rely on each mock self-generating.

## Wave sequence (explicit declaration per `wave-loop` MUST-1)

### Wave A — Autonomous foundation + F3 + parity harness (THIS SESSION, no prod cutover)

Not the cutover — bug-fixes, additive config, and test infrastructure. All in-envelope.
Cumulative invariant surface ~7, WITH the parity harness as the live executable feedback loop
(`autonomous-execution.md` MUST-3 multiplier) → within budget.

**A-core (SERIAL — shared files `client.py` / `deployment.py` / `llm_agent.py`):**

1. `tool_choice="required"` preservation — a shared helper so both the shadow (now) and the
   Wave-B live path (later) reproduce legacy forced-tool-calling when tools present & unset.
   Fixes the shipped shadow false-divergence bug.
2. Shared deployment resolver — promote `_shadow_deployment_for` to a `kaizen.llm`
   surface both `llm_agent` and `embedding_generator` build deployments from identically.
3. Azure mapping in the resolver (`azure` / `azure_openai` → OpenAiChat-compat).
4. `EmbedOptions.input_type` field (Cohere/HF embed) + thread through `client.embed`.
5. F3 — `CompletionRouting.use_chat_schema` discriminator + client dispatch threads it
   (HF-wire-guarded) + a HF chat preset routing `/v1/chat/completions`. Classic path
   byte-neutral (flag defaults off).

**A-tests (PARALLEL fan-out — distinct test files, worktree-safe):** 6. Offline parity harness: `tests/parity/` — plane A (request-payload equivalence) + plane B
(response-parse equivalence) over shared canned-byte fixtures, matrix = 8 dual-mappable
wires × {plain, tools, structured, streaming, embeddings}; azure added once the resolver
maps it; Bedrock/Vertex/Mistral one-sided golden vectors (documented deltas). 7. F3 tests (client-level HF chat routing + byte-neutral classic) + cross-SDK parity test. 8. `azure_ai_foundry` disposition test — assert current behavior; document as blocker.

**A-redteam:** holistic multi-reviewer to convergence (reviewer + security-reviewer +
closure-parity), errored-reviewer evidence gate.

### Wave B — Consumer cutover (HUMAN `/todos` GATE — HIGH blast, prod path swap)

Gated on Wave A green + the two prerequisites RESOLVED: azure resolver mapping (A-core #3) and
`azure_ai_foundry` disposition (A #8). Per-consumer parallel shards once foundation lands:
`base_agent::_simple_execute_async` ‖ `embedding_generator::_generate_provider_embedding` ‖
`llm_agent::_provider_llm_response` (live promotion) ‖ `unified_azure_provider`. The
`nodes/ai/__init__.py` barrel gets a `DeprecationWarning` shim (`zero-tolerance` 6a), not a
drop. Evidence at the gate: parity harness green across the matrix.

### Wave C — DELETE legacy `providers/llm/` + `base.py` + `registry.py` (HUMAN GATE + IRREVERSIBLE + release-gate green)

Blocked on Wave B + zero residual `kaizen.providers` imports (mechanical delete-gate sweep) +
release-pipeline four-axis quickstart green. Requires explicit user confirmation.

## Cross-SDK (per `handoff-completion` — surface, do not imply)

F3's HF chat-schema request body + `/v1/chat/completions` route is a byte-shape parity surface
with the Rust SDK HF adapter (`esperie-enterprise/kailash-rs`). rs#1860 already tracks the HF
embed `/models/{model}` URL bug. A Rust HF chat-routing sibling issue is a PENDING cross-repo
filing needing user authorization (`repo-scope-discipline` five conditions) — surfaced at Wave A
close, not auto-filed.
