# #1720 Wave-2 (DELETE) — Legacy `providers/llm` Retirement Scoping

Read-only /analyze (2026-07-18). Basis for the Wave-2 /todos plan (human gate).
Decision: DELETE (retire legacy `providers/llm`), which subsumes #1803.

## Executive summary

**The DELETE is ~90% surgical, not a bulk migration — and most risk is already retired.**
Prior Waves B1/B2 (PR #1789 + #1791, merged) ALREADY cut the three live hot-path
consumers to the four-axis `LlmClient`, shipped lazy `DeprecationWarning` barrel
shims, and decoupled `metrics.py` from the registry. So this "Wave 2" is the
previously-planned **Wave C surgical delete**, not a fresh consolidation. One
UNIQUE-capability provider — `azure_ai_foundry` (no four-axis wire) — blocks a
100% delete, so `providers/llm/azure.py` + base classes + the registry entry
survive. Invariant surface >10 + irreversible → **Wave 2a/2b split** (wave-loop bound-B).

**Brief-framing correction:** the brief says "consolidate onto four-axis"; that is
DONE on all live `kaizen/src` paths as of `4d0f8a310`. This is the delete phase.

## Coverage map (source of truth: `llm/deployment_resolver.py::resolve_deployment_for`)

- **REDUNDANT (four-axis covers chat+embed+stream):** openai, anthropic, google,
  docker, perplexity, ollama, mock, cohere, huggingface, azure/azure_openai.
- **UNIQUE (blocks 100% delete):** `azure_ai_foundry` — `resolve_deployment_for`
  raises `UnsupportedDeploymentProvider` (`_UNSUPPORTED_PROVIDERS` frozenset).
  Kept via `llm_agent.py::_legacy_provider_chat`.

## Delete inventory (LOC)

- `providers/llm/{openai,anthropic,google,mock,ollama,docker,perplexity}.py` = **3,819 LOC** deletable.
- KEEP: `providers/llm/azure.py` (587) + `providers/base.py` UnifiedAIProvider hierarchy + `registry.py` `get_provider` + azure_ai_foundry entry.
- 2b surface: `providers/embedding/{cohere,huggingface}.py`, `nodes/ai/{unified_azure_provider,azure_backends}.py` (azure/azure_openai now bypassed on live path), barrel shims.
- ~35 test files reference the legacy surface → delete/port in the SAME PR (orphan-detection Rule 4/5).

## Live consumers (all already four-axis EXCEPT one cross-package)

- `nodes/ai/llm_agent.py::_provider_llm_response` — four-axis primary; legacy only for azure_ai_foundry.
- `nodes/ai/embedding_generator.py` — four-axis embed; ollama-direct fallback (not registry).
- `core/agents.py` (BaseAgent) — cut to `resolve_deployment_for`.
- **⚠ `kaizen-agents/streaming_agent.py::_resolve_streaming_provider`** — STILL uses
  `kaizen.providers.registry.get_provider_for_model`. A live legacy consumer in a
  SEPARATE PyPI distribution the prior Wave-B census (scoped to `kaizen/src`) MISSED.
  Must be cut to four-axis stream OR the registry stream surface kept. Separate `/release`.

## Verification caveats (inference — resolve at /todos, before deleting the module)

1. **OpenAI vision content-blocks (hypothesis):** the four-axis `openai_chat` wire shows
   no image/audio block handling (`rg image|vision` → no match) while legacy
   `openai.py::_process_messages` DOES. Deleting `openai.py` may remove the only OpenAI
   vision-transform impl. VERIFY before delete.
2. **Google `finish_reason` value-map:** legacy maps STOP→stop etc.; confirm the four-axis
   `google_generate_content` wire folded the map (prior plan Decision-1A) before delete.

## Public-API deprecation gate (zero-tolerance Rule 6a)

`kaizen.providers` is documented public API (SPEC-02) with real external consumers, even
though `kaizen.__init__` exports none of it. Deletion needs a `DeprecationWarning` shim
living ≥1 minor PyPI cycle + CHANGELOG migration. **Shims already merged (B2a).**
RESOLVED (verified 2026-07-18): the barrel shims landed in commit `b4bf7c4b8` and
shipped in **kaizen 2.34.0** — published on PyPI through 2.34.1 / 2.34.2 / 2.35.0.
The deprecation cycle has ALREADY run ≥1 minor. So barrel-shim removal (2b-A) can
land in the NEXT kaizen minor (2.36.0) with NO hard break — Option A is effectively
free; Option B (delete-now-hard-break) is moot. D1 is resolved in favor of A.

## Shard decomposition (wave-loop bound-B → 2a/2b split confirmed)

- **Wave 2a (1 worktree, serial — the 7 provider deletes converge on registry.py + provider_names.py, coupled by a module-scope drift `assert`):** delete 7 redundant modules; prune `registry.py` PROVIDERS + `provider_names.py::PROVIDER_NAMES` in lockstep (keep azure_ai_foundry); conditional `base.py::LLMProvider` delete. ~5 invariants, ~3,819 LOC.
- **Wave 2b (≤3 parallel worktrees, after 2a + deprecation-release gate):** 2b-A end barrel deprecation cycle (gated on shim PyPI release); 2b-B delete embedding-legacy + azure-unified; 2b-C test sweep + `kaizen-agents/streaming_agent.py` cutover (separate distribution → separate `/release`).

## Out of scope (separate concerns)

- `providers/multi_modal_adapter.py` (609) + `providers/document/*` (2,326) — NO `src/` consumers found; distinct document/multimodal subsystem, own orphan-detection audit if pursued. NOT #1720.
- `llm/from_env.py` legacy-key-autodetect tier — already deprecating; separate subsystem/cycle. Keep out of Wave 2.

## Decisions the /todos plan needs (surfaced to owner)

- **D1 — deprecation ordering: RESOLVED (A).** Shims shipped in kaizen 2.34.0, live ≥1 minor through 2.35.0 → 2b-A barrel removal lands in the next kaizen minor, no hard break. No owner decision needed.
- **D2 — azure_ai_foundry:** keep-as-legacy (2A, recommended — 90% delete) vs build a four-axis Foundry wire (2B, net-new, blocks the delete). Recommend 2A.
- **D3 — cross-SDK:** #1720 is `cross-sdk` labeled; inspect the Rust SDK legacy-provider layer + the BYOK header-injection parity surface. Cross-repo filing PENDING owner authorization (repo-scope-discipline).
