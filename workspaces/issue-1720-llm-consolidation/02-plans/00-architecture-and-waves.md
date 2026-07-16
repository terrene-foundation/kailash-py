# #1720 — Wave-Decomposed Consolidation Plan

Retire legacy `providers/llm/` onto the four-axis `LlmClient`. Additive-first; the
irreversible delete lands LAST behind a release-gate. Anchors are grep-stable symbols
(re-resolve before building — lines drift per `symbol-anchored-citations.md`).

## Gate structure (what is autonomous vs human-gated)

| Wave  | Content                                                                                   | Blast radius                   | Gate                                                    |
| ----- | ----------------------------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------- |
| **1** | four-axis parity (additive) — nothing in prod consumes `LlmClient.complete/stream` yet    | LOW (additive, reversible)     | **Autonomous** (`/implement`+`/redteam`)                |
| **2** | dual-run behind `_provider_llm_response` (compare, no user-visible change)                | MEDIUM (touches prod hot path) | `/todos` **human gate**                                 |
| **3** | migrate consumers one at a time (llm_agent → base_agent → embedding_generator → registry) | HIGH (prod path swaps)         | `/todos` **human gate**                                 |
| **4** | **delete** legacy `providers/llm/` + `base.py` + `registry.py`                            | IRREVERSIBLE                   | `/todos` **human gate** + release-gate regression green |

Safety anchor (verified this session): `grep -rln LlmClient src/kaizen/ | grep -v /llm/` → EMPTY.
No production consumer of the four-axis completion path exists → Wave 1 regresses nothing.

## Wave 1 sub-decomposition (invariant-surface split per `wave-loop` MUST-1)

Wave 1's unioned invariant surface (~42) exceeds the base-10 ceiling. It splits at the
**shared-file boundary**: every capability adds fields to `CompletionRequest`
(`deployment.py`) + kwargs to `LlmClient.complete`/`LlmClient.stream` (`client.py`), and
capabilities overlap the same `wire_protocols/*` adapter files. So:

### Wave 1a — FOUNDATIONAL (serial, 1 shard, ~120 LOC, ~4 inv) — THIS SESSION

Owns ALL shared-file edits so 1b fan-out is contention-free:

1. `CompletionRequest` (`deployment.py`) — add optional additive fields, all `= None`
   defaults (frozen model + `extra="forbid"` → additions are backward-safe):
   `tools`, `tool_choice`, `response_format`, `seed`, `logit_bias`, `frequency_penalty`,
   `presence_penalty`, `n`, `top_k`.
2. `EmbedOptions` (`deployment.py`) — add `input_type`, `normalize` (Cohere/HF embed).
3. `LlmClient.complete` / `LlmClient.stream` / `_build_completion_request` (`client.py`)
   — thread the new kwargs through to `CompletionRequest`.
4. Shared **normalized-shape contract** — a `_normalize_tool_calls` helper + a documented
   `[{id,type:"function",function:{name,arguments}}]` shape, so every 1b adapter shard
   conforms without a cross-shard code merge.
5. **Byte-neutrality pin tests** — for every wire, `tools=None,...` produces a payload
   byte-identical to today (additive-neutrality regression, `@pytest.mark.regression`).

**Invariant: 1a changes MUST be byte-neutral when all new fields are None.** That is the
whole safety property — no existing call path changes until a caller opts in.

### Wave 1b — PARALLEL fan-out (worktree-isolated, waves of ≤3 per throttle) — after 1a merges

Sharded so **no two shards touch the same file**:

- **Per-wire-adapter shards** (one file = one owner): each of `openai_chat`,
  `anthropic_messages`, `google_generate_content`, `bedrock_invoke`, `mistral_chat`,
  `cohere_generate`, `ollama_native`, `huggingface_inference` implements — for ITS adapter
  only — tools emit+parse, structured-output translate, multimodal content-part translate,
  extended-sampling emit, and (where applicable) streaming tool-delta accumulation. Each
  conforms to the 1a normalized-shape contract. ~60–100 LOC/shard.
- **`mock` preset shard** — offline in-process response path (a mock wire/preset so
  `complete/stream/embed` never POST in Tier-1). Legacy source: `providers/llm/mock.py`.
- **`embed` remainder shard** — cohere/hf/azure embeddings shapers + `_EMBED_DISPATCH`
  entries + the `EmbedOptions` fields 1a added.
- **`byok` shard** — per-request `api_key` override on `complete/stream` (NOT a
  `CompletionRequest` field — it is the cross-SDK byte pre-image; threads through auth
  headers instead). Depends on the base send path (already landed, #1717).

## Verified corrections folded in (from adversarial verification)

- `_COMPLETE_DISPATCH` has **9** wires (incl. `HuggingFaceInference`), not 8.
- `from_deployment`/`from_env` are `LlmClient.from_deployment`/`.from_env` in `client.py`
  (NOT `deployment.py`).
- Consumer count for Wave 3 is **>4**: also `nodes/ai/unified_azure_provider.py`
  (`UnifiedAIProvider` import) + the `nodes/ai/__init__.py` barrel (legacy re-exports).
  The delete-gate mechanical sweep (Wave 4) is what proves zero residual
  `kaizen.providers` imports.
- `tool_choice` default divergence: legacy defaults to `"required"` when tools present;
  the four-axis adapters must **preserve legacy `"required"` semantics** (not silently
  adopt `"auto"`) to keep migration behavior-neutral — decided here, pinned by a 1b test.

## Spec discipline

`specs/kaizen-llm-deployments.md` is extended **code-first per shard** (`spec-accuracy.md`
Rule 5) — each merged shard appends the surface it actually shipped. No forward-written
parity spec.
