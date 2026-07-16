# #1720 — Wave-B / Wave-C `/todos` Plan (consumer cutover + legacy delete)

**Status:** DRAFT for the human `/todos` structural gate. Wave B (consumer
cutover) is HIGH-blast (prod LLM path swap); Wave C (delete legacy) is
IRREVERSIBLE. Both are human-gated per `commands/todos.md` + the plan in
`02-plans/01-wave3-refined-decomposition.md`.

Grounded in a code-verified census of the merged Waves 1+2+A foundation
(main @ `25afb9a39`, re-verified at HEAD after the foundation-redteam fixes).
Citations are grep-stable symbols — re-resolve before building.

## What the foundation-redteam established (this session, already landed)

A holistic red-team of the merged four-axis foundation (before drafting this
plan) found + fixed 3 defects the cutover would have inherited (commit
`1d334b7f7`, 15 regression tests):

- **F1** — `legacy_tool_choice_default` is now stream-aware; the node threads
  the live `streaming` mode into the dual-run shadow. **Wave-B relevance:** the
  live cutover's streaming tool path now reproduces legacy `stream_chat`'s
  `"auto"` for openai (was `"required"`).
- **F2** — `EmbedOptions.normalize` now reaches the HuggingFace embed wire
  through `LlmClient.embed`. **Wave-B relevance:** the embedding_generator
  cutover can rely on `normalize` (and `input_type`) actually taking effect.
- **BYOK** — `resolve_deployment_for` now validates a caller-supplied `api_key`
  (control-char/CRLF/non-ASCII) at parity with `LlmClient.complete`.
  **Wave-B relevance:** promoting `resolve_deployment_for` to the live path no
  longer opens a header-injection surface.

**Material correction to the prior plan's premise:** `LlmClient.complete()` is
NOT deferred — it is fully live and is the dual-run shadow's actual call target.
The Wave-2 shadow (`LLMAgentNode._run_llm_dual_run_shadow`) already resolves
provider→deployment via `resolve_deployment_for` and drives `complete()` +
`to_legacy_shape`, comparing against legacy on real traffic. **Wave-B is
essentially "promote the shadow to primary"** — a far lower-risk cutover than a
from-scratch migration.

## Wave-A prerequisite status (verified)

| Prereq                                                             | Status                                |
| ------------------------------------------------------------------ | ------------------------------------- |
| Per-provider `legacy_tool_choice_default` (now stream-aware)       | ✅ LANDED                             |
| Shared `resolve_deployment_for` + azure/azure_openai mapping       | ✅ LANDED                             |
| `EmbedOptions.input_type` threaded (now `normalize` too, F2)       | ✅ LANDED                             |
| F3 HF chat routing (`use_chat_schema` + `huggingface_chat_preset`) | ✅ LANDED                             |
| Google `finish_reason` parity                                      | ❌ OPEN — Wave-B DECISION (see below) |

## The live legacy consumers Wave-B must migrate (census)

Only THREE production chat/embed call sites remain on the legacy stack (grep-
confirmed: `providers.registry.get_provider(` outside `providers/` appears only
in the first two):

| #   | Consumer (symbol)                                     | Legacy call                               | Four-axis target                                                                             | Risk | Blocker                                           |
| --- | ----------------------------------------------------- | ----------------------------------------- | -------------------------------------------------------------------------------------------- | ---- | ------------------------------------------------- |
| 1   | `LLMAgentNode._provider_llm_response`                 | `get_provider(p).chat(...)`               | `resolve_deployment_for` → `complete` → `to_legacy_shape` (shadow already does exactly this) | MED  | `azure_ai_foundry` (no four-axis wire)            |
| 2   | `EmbeddingGeneratorNode._generate_provider_embedding` | `get_provider(p,"embeddings").embed(...)` | `resolve_deployment_for` → `LlmClient.embed`                                                 | MED  | embed() has no `timeout` kwarg; sync↔async bridge |
| 3   | `BaseAgent._simple_execute_async`                     | direct `OpenAIProvider().chat_async`      | `resolve_deployment_for("openai",…)` → `complete`                                            | LOW  | none (openai fully covered)                       |

Two public re-export barrels + one metrics dependency are NOT call paths but
block the Wave-C delete:

| Surface (symbol)                    | Nature                                                                                             | Wave-C obligation                                 |
| ----------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `kaizen.nodes.ai.__init__` barrel   | re-exports legacy provider classes + registry accessors in `__all__`                               | DeprecationWarning shim (zero-tolerance 6a)       |
| `kaizen.providers.__init__` barrel  | same, at the providers package root                                                                | DeprecationWarning shim                           |
| `production/metrics.py`             | imports `registry._MODEL_PREFIX_MAP` + `PROVIDERS` for Prometheus label bounding (not a chat path) | extract the name-registry off `registry.py` first |
| `providers/base.py` (`LLMProvider`) | subclassed by `unified_azure_provider` + cohere/hf embedding providers                             | resolve subclass base before delete               |

## Two decisions the human MUST make at this gate

### Decision 1 — Google `finish_reason` parity (recommend: normalize with the FULL legacy map)

**Corrected from the parity finding.** The finding proposed "one map, lowercase."
Reading legacy `google.py` shows it does MORE than lowercase — it VALUE-MAPS:
`STOP`→`stop`, `MAX_TOKENS`→`length`, `SAFETY`→`content_filter`, tool→`tool_calls`.
The four-axis `google_generate_content` wire emits the raw provider value
(`"STOP"`). A pure lowercase would give `"max_tokens"` where legacy gives
`"length"` — NOT parity.

- **Option A (recommend):** port the FULL legacy value-map into the four-axis
  google wire so migration is behavior-neutral. Implication: Gemini consumers
  testing `finish_reason == "stop"/"length"/"content_filter"` keep working; ~1
  small map in the wire + a parity-harness cell. Con: a behavior change to
  already-merged four-axis code (low blast — google wire only, pinned by the
  parity test that currently documents the delta).
- **Option B:** accept the raw-value four-axis behavior and update consumers.
  Con: every Gemini consumer that reads `finish_reason` must change; buys
  nothing a user asked for.

**Recommendation: A**, folded into shard B1a. It is the behavior-neutral path
and the parity harness gate covers it.

### Decision 2 — `azure_ai_foundry` (recommend: scope OUT of the cutover, partial Wave-C)

`azure_ai_foundry` has NO four-axis wire; `resolve_deployment_for` raises the
typed `UnsupportedDeploymentProvider`. A Foundry-configured agent cannot migrate.

- **Option A (recommend):** SCOPE `azure_ai_foundry` OUT of Wave-B. Keep the
  legacy `AzureAIFoundryProvider` alive; Wave-C becomes a PARTIAL delete
  (everything in `providers/llm/` EXCEPT the azure_ai_foundry path + its
  registry entry). Implication: consolidation completes for all other providers
  now; Foundry stays legacy until a four-axis Foundry wire is a separately-
  scoped capability. Con: `providers/llm/azure.py` + the registry survive Wave-C
  (a smaller, documented residual), so "delete legacy" is 90%, not 100%.
- **Option B:** build a four-axis `azure_ai_foundry` wire as part of Wave-B so
  Wave-C is a full delete. Implication: net-new capability work (a new wire +
  grammar + auth), not consolidation. Con: materially larger scope; blocks the
  whole cutover on new-wire development.

**Recommendation: A** — ship the consolidation value now; treat the Foundry wire
as its own capability item. (User: confirm whether a Foundry four-axis wire is
wanted; if yes, it is Decision-2B and re-scopes Wave-C to a full delete.)

## Wave sequence (explicit declaration per `wave-loop` MUST-1)

Value-ranked; each wave's cumulative invariant surface fits the budget WITH the
offline parity harness as the live executable feedback loop.

### Wave B1 — consumer cutover (HIGH value: retires legacy on all live paths)

Value-anchor: #1720 program goal — retire `providers/llm/` onto four-axis
`LlmClient`; the live path swap is the load-bearing deliverable. Behind the
parity harness green across the dual-mappable matrix. Three parallel shards
(distinct files, worktree-safe):

- **B1a — `LLMAgentNode._provider_llm_response` live cutover.** Promote the
  shadow's exact `resolve_deployment_for`→`complete`→`to_legacy_shape` path to
  primary. MUST preserve: the `is_available()` gate, the usage total-coercion
  for None counters (#487), the now-stream-aware per-provider `tool_choice`
  default, and the streaming path. Folds Decision-1A (google finish_reason map).
  `azure_ai_foundry` scoped out per Decision-2A. Invariants ≈ 6.
- **B1b — `EmbeddingGeneratorNode._generate_provider_embedding` cutover.** Move
  to `resolve_deployment_for`→`LlmClient.embed`. Close the gaps: add a `timeout`
  kwarg to `embed()` (legacy passes one) and confirm cohere `input_type` / hf
  `use_api` are honored by the four-axis shapers (F2 already makes `normalize`
  work on the HF wire). Preserve the ImportError fallback. Invariants ≈ 5.
  Value-anchor: retires the legacy embedding path onto four-axis — the #1720
  program goal for embeddings; without it `providers/llm/` cannot be deleted.
  - **Folded in — F2-MEDIUM (deferred from the foundation redteam, tracked
    here):** `EmbedOptions.normalize` is a documented "cross-provider-shared"
    field but is still a silent no-op on the ollama/cohere/openai embed wires
    (only HF applies it, post-F2). The redteam graded this MEDIUM/non-blocking
    (pre-existing; the foundation fix closed the specific HF finding). The
    3c-clean disposition (per the reviewer) is to apply the L2 normalize
    UNIFORMLY for every wire — a single client-side implementation in
    `LlmClient.embed` (pure math), removing the per-shaper copy. Do it here,
    where all-wire embed semantics are the shard's focus, so the embedding
    cutover ships with `normalize` actually honored on every provider it
    migrates. Value-anchor: a consumer asking for normalized embeddings gets
    them regardless of provider — the documented contract the field promises.
- **B1c — `BaseAgent._simple_execute_async` cutover.** openai-only; direct
  `OpenAIProvider` → `resolve_deployment_for("openai",…)`→`complete`. Lowest
  risk. Invariants ≈ 3.

Inter-wave gate after B1 (per `wave-loop` G1–G5): redteam to convergence scoped
to B1; parity-harness matrix green; feed drift forward to B2.

### Wave B2 — delete-gate prep (blocks Wave C)

Value-anchor: makes the IRREVERSIBLE Wave-C delete safe + reviewable — each item
removes a hard coupling to `providers/llm/` / `registry.py`.

- **B2a** — `nodes/ai/__init__` + `providers/__init__` barrels: DeprecationWarning
  shims over ≥1 minor cycle + CHANGELOG migration entry (zero-tolerance 6a). No
  hard drop of the public class exports.
- **B2b** — extract the provider-name registry (`PROVIDERS` frozenset +
  `_MODEL_PREFIX_MAP`) to a registry-independent module so `production/metrics.py`
  no longer imports `providers.registry`.
- **B2c** — resolve `providers/base.py::LLMProvider` subclassers
  (`unified_azure_provider`, cohere/hf embedding providers) — re-base or inline
  before the base class is deleted.

### Wave C — DELETE legacy (IRREVERSIBLE + human gate + release-gate green)

Blocked on B1 + B2 + a mechanical zero-residual sweep (`grep -rn
"kaizen.providers.llm\|providers.registry" src/` returns only the delete set +
scoped-out `azure_ai_foundry` per Decision-2A) + the release-pipeline four-axis
quickstart green (NOTE: the quickstart example currently drives the LIVE legacy
`_provider_llm_response`; B1a's cutover makes it exercise four-axis — verify).
30 test files reference the legacy surface and must be swept in the delete PR
(orphan-detection Rule 4). Requires explicit user confirmation.

## Cross-SDK (surface, do not auto-file — `handoff-completion`)

The BYOK header-injection parity gap fixed this session (control-char api_key on
the `resolve_deployment_for` path) is a likely parity surface with the Rust SDK
four-axis client. PENDING cross-repo filing needing user authorization
(`repo-scope-discipline` five conditions) — surfaced here, not auto-filed.
(Security-reviewer was asked to assess the cross-SDK likelihood.)
