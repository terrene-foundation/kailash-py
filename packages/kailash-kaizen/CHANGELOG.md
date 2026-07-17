# Changelog

All notable changes to the Kaizen AI Agent Framework will be documented in this file.

## [Unreleased]

## [2.34.2] — 2026-07-17 — monitoring installability fix

### Fixed

- **`import kaizen.monitoring` now works on a bare `pip install kailash-kaizen`
  (no `[server]` extra).** `monitoring/dashboard.py` eagerly imported `fastapi`
  at module scope and built a module-level `app = FastAPI(...)`, and
  `monitoring/__init__.py` eagerly imported that `app`, so the very first
  `import kaizen.monitoring` hard-failed with `ModuleNotFoundError: No module
named 'fastapi'` unless the optional `server` extra was installed — taking
  down metrics collection, analytics, and alerting even though only the
  dashboard needs FastAPI. The FastAPI surface is now built lazily: a new
  `create_dashboard_app()` factory and the module-level `app` (resolved via PEP
  562 `__getattr__`) import FastAPI only when actually used, raising a typed
  `MonitoringDependencyError` (an `ImportError` subclass) naming the remedy
  (`pip install 'kailash-kaizen[server]'`) instead of failing at import. The
  dashboard is byte-for-byte functional when FastAPI is present.
- Two pre-existing monitoring dashboard integration-test failures the
  restructure surfaced: `/metrics` now returns `PlainTextResponse` (Prometheus
  scrapers reject the `application/json` FastAPI applied to the bare `str`
  return), and a stale `ws://`-literal test assertion updated to match the
  deployment-agnostic dynamic WebSocket URL the HTML already builds.

## [2.34.1] — 2026-07-17 — #1720 creds-in-logs security sweep (MED-1 sibling class)

### Security

- **Closed the creds-in-logs vulnerability class across every LLM / provider /
  MCP / redis / webhook path (#1720).** The 2.34.0 MED-1 fix sanitized a single
  MCP connection-error log; an adversarial redteam sweep to convergence found the
  same class open package-wide. Every credential-bearing exception log and URL
  log now routes through `sanitize_provider_error`, a canonical `_mask_redis_url`,
  or a new `_mask_webhook_url`. `exc_info=True` is dropped on provider / MCP /
  connection error paths — it resurfaced the raw provider exception (carrying an
  api-key or a `user:pass@` URL) via the implicit exception-context chain even
  when the re-raised message was already sanitized. Fixes span the LLM /
  embedding / vision / document providers, the Azure backends, the redis rate
  limiter (which logged its connection URL verbatim on the success path), the MCP
  discovery / tool-execution paths across every agent implementation, the webhook
  alerter (Slack/Discord auth token lives in the URL path — a class the provider
  sanitizer does not cover), and the LLM security nodes (which logged **and
  returned** raw provider exceptions). 22 source files; verified by a six-round
  adversarial sweep to convergence plus 10 behavioral regression tests, and an
  exhaustive grep across all 54 credential-bearing modules confirming zero
  remaining raw-exception logs.

### Changed

- **Live LLM chat and embedding paths now route through the four-axis `LlmClient`
  instead of the legacy `providers/llm/` registry (#1720 Wave-B1, PR #1789).**
  `LLMAgentNode._provider_llm_response`, `EmbeddingGeneratorNode._generate_provider_embedding`,
  and `BaseAgent._simple_execute_async` were cut over from
  `providers.registry.get_provider(...).chat/embed(...)` to
  `resolve_deployment_for(...)` → `LlmClient.complete` / `LlmClient.embed` →
  `to_legacy_shape`. The cutover is behavior-neutral, gated by an offline parity
  harness across the dual-mappable provider matrix. `azure_ai_foundry`
  intentionally remains on the legacy `.chat()` path (Decision-2A); every other
  provider now runs on the consolidated four-axis client.
- **`production/metrics.py` no longer imports `providers.registry` (#1720 Wave-B2b,
  PR #1791).** The provider-name registry (`PROVIDERS` frozenset + model-prefix
  map) was extracted to a registry-independent module (`providers/provider_names.py`),
  decoupling the Prometheus metrics label-bounding (and a bare `import kaizen`)
  from the legacy registry at runtime.

### Added

- **Four-axis embedding wires and the legacy-shape bridge (#1720 Waves 1–2/A).**
  New `LlmClient` embedding wire protocols for cohere and HuggingFace
  (`wire_protocols/cohere_embeddings.py`, `wire_protocols/huggingface_embeddings.py`);
  a `to_legacy_shape` adapter (`llm/_legacy_shape.py`) reproducing the legacy
  provider response envelope so the cutover is behavior-neutral; a shared
  `resolve_deployment_for` deployment resolver (`llm/deployment_resolver.py`) with
  azure / azure_openai mapping; and an offline `mock_transport` harness
  (`llm/testing/mock_transport.py`) that drives the parity matrix without live
  credentials. Existing chat wires (openai, bedrock, google, mistral, ollama,
  HuggingFace inference, cohere generate) were extended to complete the
  consolidated provider matrix.
- **`LlmClient.embed` accepts a `timeout` kwarg** at parity with the legacy
  embedding path, and applies `EmbedOptions.normalize` uniformly across every
  embedding wire (previously a silent no-op on all wires except HuggingFace).

### Deprecated

- **Legacy provider re-exports from the `kaizen.nodes.ai` and `kaizen.providers`
  barrels are deprecated (#1720).** The provider classes `LLMProvider`,
  `AnthropicProvider`, `AzureAIFoundryProvider`, `DockerModelRunnerProvider`,
  `GoogleGeminiProvider`, `MockProvider`, `OllamaProvider`, `OpenAIProvider`,
  `PerplexityProvider` (plus the embedding providers `CohereProvider`,
  `HuggingFaceProvider` on the `kaizen.providers` barrel) and the registry
  accessors `PROVIDERS`, `get_provider`, `get_available_providers` are no longer
  eagerly re-exported from these two barrels. They are now lazy PEP 562
  `__getattr__` shims: importing any of them from the barrel (e.g.
  `from kaizen.nodes.ai import OpenAIProvider` or
  `from kaizen.providers import OpenAIProvider`) now emits a `DeprecationWarning`
  and resolves the real class. A bare `import kaizen.nodes.ai` /
  `import kaizen.providers` does **not** warn — only attribute access does.
  Migrate to the canonical module imports: provider classes from
  `kaizen.providers.llm.<mod>` (e.g. `from kaizen.providers.llm.openai import
OpenAIProvider`) and `kaizen.providers.embedding.<mod>`, the `LLMProvider`
  base from `kaizen.providers.base`, and the registry accessors from
  `kaizen.providers.registry`. The symbols remain in each barrel's `__all__`
  (the public contract is unchanged — only the access path warns). Removal is
  scheduled for Wave-C of #1720 (a following minor release, so these shims live
  through ≥1 published minor cycle first).

### Fixed

- **Foundation and Wave-B1 red-team fixes (#1720).** (1) The legacy per-provider
  `tool_choice` default is now stream-aware — the dual-run shadow threads the live
  `streaming` mode so the four-axis streaming tool path reproduces legacy
  `stream_chat`'s per-provider `"auto"`/`"required"` value. (2) `EmbedOptions.normalize`
  now reaches the HuggingFace embed wire through `LlmClient.embed`. (3) BYOK
  hardening: `resolve_deployment_for` validates a caller-supplied `api_key`
  (control-char / CRLF / non-ASCII) at parity with `LlmClient.complete`, closing a
  header-injection surface on the promoted live path. (4) The embedding cutover no
  longer silently returns a mock embedding on an unresolvable credential provider —
  the legacy loud raise is restored (the sanctioned mock path stays the explicit
  `provider == "mock"` mode only). (5) Google `finish_reason` value-map parity
  (`STOP`→`stop`, `MAX_TOKENS`→`length`, `SAFETY`→`content_filter`, tool→`tool_calls`)
  is preserved on the four-axis google wire.
- **Pre-release red-team fixes (#1720 2.34.0).** (6) `LLMAgentNode` no longer
  returns a fabricated completion when the provider stack fails to import — the
  `ImportError` branch now raises loudly (parity with the embedding path's
  unresolvable-provider raise; no silent mock returned as a real answer). The
  fabricating `_fallback_llm_response` method was removed. (7) Provider errors
  are now routed through `sanitize_provider_error` before reaching the LOG
  surface on the completion path (previously logged raw via `exc_info=True`) —
  a URL-embedded credential in a raw provider exception can no longer leak into
  server logs. (8) Same-class sibling on the MCP retrieval path: the
  `_retrieve_mcp_context` connection-failure log lines now route through
  `sanitize_provider_error` (they previously logged the raw exception while a
  sanitized copy was computed for the return).

## [2.33.1] — 2026-07-15 — RAG verification-parse hardening (#1755)

### Fixed

- **`SelfCorrectingRAGNode` crashed or looped on ill-formed LLM confidence
  (#1755).** Post-2.33.0 the RAG advanced-node parsers consume real LLM output,
  so `_parse_verification_response` sits on a live path. It validated field
  _presence_ only: a `confidence` returned as a string raised an uncaught
  `TypeError` at the numeric gate in `run()`, and a `NaN` confidence
  (`json.loads` accepts the bare `NaN` literal) never met the gate — forcing the
  self-correction loop to run to `max_corrections` every time. Every score field
  is now coerced to a finite float at the single parse chokepoint (`_coerce_score`);
  an ill-formed (non-numeric / non-finite) score routes to the existing heuristic
  fallback.

## [2.33.0] — 2026-07-15 — RAG advanced-node parser fix + Tier-1 test-hang resolution

### Fixed

- **RAG advanced nodes silently ignored LLM output and always used the
  rule-based fallback (#1736).** The four LLM-response parsers backing
  the HyDE, StepBack, SelfCorrecting, and RAGFusion nodes
  (`_parse_verification_response`, `_parse_query_variations`,
  `_parse_hypotheses`, `_parse_abstract_query` in
  `kaizen/nodes/rag/advanced.py`) read `response.get("content", "")` off
  the **outer** `LLMAgentNode.execute()` envelope, but the LLM's actual
  content is nested one level deeper at
  `response["response"]["content"]`. Every one of these nodes therefore
  called the LLM, discarded its output, and silently fell back to the
  rule-based path — invisible in practice because the fallback produced
  plausible-looking output, and the only tests that exercised these code
  paths were hanging on real network calls (see below) rather than
  failing. Each parser now unwraps the nested envelope
  (`inner = response.get("response", response)`, flat-dict tolerant),
  so these four nodes actually consume LLM output for the first time.

- **Kaizen Tier-1 unit tests hung for 300s+ on unmocked LLM/network
  calls (#1736).** `tests/unit/strategies/` and
  `tests/unit/rag/test_advanced_nodes.py` constructed real `BaseAgent` /
  RAG nodes and invoked `.execute()` / `.run()` with no LLM mocking,
  triggering real outbound network calls that `pytest-timeout`'s signal
  method could not reliably abort. Added an autouse conftest stub
  (`tests/unit/strategies/conftest.py`) and a module-scoped fixture in
  `test_advanced_nodes.py` stubbing the provider seam (`get_provider` +
  `OpenAIProvider.{chat,chat_async,is_available}`) so these suites run
  offline and deterministically; `pytest.ini` now sets
  `timeout_method = thread` for stronger hang enforcement; both suites
  are re-included in the kaizen CI gate
  (`.github/workflows/test-kailash-kaizen.yml`) with zero per-test
  deselects. Fixing the test hang is what exposed the parser bug above —
  both are fixed in this release, not just the hang.

### Added

- **`kaizen.manifest` module (#1735).** Declarative agent / app / governance
  manifests (TOML) — parse, validate, and introspect Kaizen agent and
  application definitions, with typed errors (`ManifestError`,
  `ManifestParseError`, `ManifestValidationError`) and a governance budget
  model. Includes hardened parsing: full C0 control-character escaping in TOML
  string emission, `[[agent]]` array-of-tables validation, non-finite / overflow
  budget rejection (`math.isfinite` guard), type-guarded list coercion on every
  `from_dict` / TOML-parse / introspection path, and bounded (`max_len`) error
  messages so a malformed manifest cannot flood logs.

### Deprecated

- **`LlmClient.from_env()` legacy per-provider-key auto-detect tier
  (#1721/#1720).** Resolving a client purely from a per-provider API key
  (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / …) with no `KAILASH_LLM_DEPLOYMENT`
  (URI) or `KAILASH_LLM_PROVIDER` (selector) set now emits a
  `DeprecationWarning`. This backward-compat migration tier will be removed in a
  future major; migrate to the URI or selector tier. The `NoKeysConfigured`
  message + docstring are now derived from the canonical `LEGACY_KEY_ORDER` so
  they cannot drift from the resolver.

### Changed

- **Expanded Kaizen CI unit suite (#1734).** Broader FAST unit-tier coverage
  (LLM + cross-SDK parity) and repaired pre-existing test staleness surfaced by
  the CI-gate audit. No user-facing behavior change.

## [2.31.2] — 2026-07-14 — docs: honest `supports()` contract (provider capability vs client emission)

### Fixed

- **`LlmDeployment.supports()` contract honesty.** The per-preset capability
  matrix advertised `tools=True` / `vision=True` etc., which a caller could
  misread as "the four-axis `LlmClient.complete()` will send my tools" — but the
  four-axis client emits only the shared `CompletionRequest` fields today (no
  tools / structured-output / batch / caching / audio). The matrix is a
  **provider/wire-capability** negotiation surface, byte-parity-locked with the
  Rust SDK, so the rows are unchanged (flipping them would break cross-SDK
  parity); instead the `supports()` + `capabilities` docstrings now state
  explicitly that the rows report provider capability, not client emission
  (client-side wiring tracked in #1720). A contract test pins the reconciliation
  and trips when client emission is added. Docstring/test only — no behavior
  change.

## [2.31.1] — 2026-07-14 — fix: OpenAI GPT-5 / o-series completions (`max_completion_tokens`)

### Fixed

- **`LlmClient.complete()` against OpenAI GPT-5 / o-series models.** The
  `openai_chat` wire shaper emitted `max_tokens` unconditionally; GPT-5 and the
  o-series reasoning models reject it with HTTP 400 (`use 'max_completion_tokens'
instead`) — found by exercising `complete()` against the live OpenAI API. The
  shaper now selects the token-limit field by model family: GPT-5 / o1 / o3 / o4
  use `max_completion_tokens`; OpenAI-compatible providers (DeepSeek, Groq,
  Together, …) keep `max_tokens`. Verified live: OpenAI gpt-5, Anthropic-direct,
  DeepSeek, and Bedrock-Claude completions all succeed through the four-axis
  client. Cross-SDK: the Rust SDK's shaper carries the same defect (#1727).

## [2.31.0] — 2026-07-14 — four-axis `LlmClient` completion send path + Vertex-Claude/Bedrock wire + GCP WIF (#1717)

The four-axis LLM deployment layer previously wire-sent only embeddings; this
adds the completion half so `LlmClient` can drive Vertex-Claude, Vertex-Gemini,
and Bedrock chat completions through the deployment abstraction.

### Added

- **`LlmClient.complete()` + `LlmClient.stream()` (#1717).** Completion send path
  over a `_COMPLETE_DISPATCH` covering all 9 preset-emittable wires (OpenAI chat,
  Anthropic messages, Google/Vertex generate-content, Bedrock invoke, Cohere,
  Mistral, Ollama, HuggingFace). Per-wire URL building appends the correct verb
  (`:rawPredict` / `:streamRawPredict`, `:generateContent` /
  `:streamGenerateContent`, Bedrock `/model/{id}/invoke[-with-response-stream]`);
  `stream()` is a real httpx stream through the single SSRF-checked transport.
  Prompt messages are redacted before the body is shaped.
- **Vertex-Claude / Bedrock-Claude body transform.** A `CompletionRouting` field
  on the deployment gates a platform body transform: for Vertex/Bedrock the
  Anthropic body strips `model` and injects `anthropic_version`
  (`vertex-2023-10-16` / `bedrock-2023-05-31`). Direct-provider bodies stay
  byte-identical (transform gated on wire mode). New `openai_chat` +
  `bedrock_invoke` wire shapers.
- **GCP auth completeness.** `GcpOauth` gains Workload Identity Federation
  (`external_account` + service-account impersonation), metadata-server ADC, and
  `google.auth.default()` ADC, with JSON-`type` credential dispatch. New
  `auth_strategy_kind` discriminants (`gcp_wif` / `gcp_metadata` / `gcp_adc`);
  all failures raise typed, path-fingerprinted `AuthError`s.
- **Config / region / catalog.** `from_env` honors `GOOGLE_CLOUD_PROJECT` /
  `VERTEX_LOCATION` and a `vertex_claude` / `vertex_gemini` selector branch;
  region validation accepts `us` / `eu` / `global` (`eu` passes straight through,
  not remapped to `europe-west1`); the Vertex-Claude grammar adopts an open
  `claude-*` passthrough so current models like `claude-opus-4-8` resolve.
- **Per-model temperature floor.** `claude-opus-4-8`-class models omit
  `temperature` below their minimum instead of hard-400'ing on `temperature=0`.
- **Provider-string aliases.** `vertex-anthropic` and `vertex_claude` both resolve
  to the Vertex-Claude preset (`vertex-gemini` / `vertex-google` → Vertex-Gemini).

### Fixed

- **Model URL-path injection (security).** A caller-controlled `model` is now
  validated fail-closed before it reaches the request URL path (rejects
  traversal / URL-control characters), covering the Google-direct, Bedrock, and
  HuggingFace `{model}`-template wires.
- **Owned-client transport leak.** `complete()` now closes an owned HTTP client on
  a non-httpx send-phase error (SSRF rejection, auth-refresh failure), matching
  `stream()`'s cleanup.
- **Cross-SDK preset parity tests.** Reconciled the stale `RUST_PRESET_NAMES`
  fixture against the 18 documented Python-idiom convenience presets and pinned
  the DeepSeek legacy-precedence divergence as a self-clearing strict-xfail
  (#1721).

## [2.30.0] — 2026-07-13 — real production histogram + LLM token/cost counters reach unified `/metrics` (#1708)

Part of the coordinated 5-package #1708 observability release. Requires
`kailash>=2.50.0` (the unified `/metrics` exposition these metrics now reach).

### Added

- **Real production duration histogram + LLM token/cost counters (#1708
  W4).** `kaizen.production.metrics` previously emitted a duration metric
  with only `_count`/`_sum` (no `le=` buckets), making p95/p99 latency
  impossible to compute. Replaced with a real `prometheus_client` Histogram
  using explicit second-scale buckets. Token and cost data previously
  existed only as `CostUpdateEvent`s on the internal event stream, invisible
  to Prometheus — added `kaizen_llm_prompt_tokens_total`,
  `kaizen_llm_completion_tokens_total`, and
  `kaizen_llm_cost_microdollars_total`, wired at both cost-update emission
  points (primary + per-subagent, double-count-guarded). `model`/`provider`
  labels are bounded via the existing provider-registry maps; no prompt text
  or secrets ever reach a label.

### Fixed

- **Production histogram + LLM counters now reach the unified `/metrics`
  endpoint (#1708 redteam).** The W4 metrics were initially registered on a
  dedicated per-`MetricsCollector`-instance `CollectorRegistry` exposed only
  via a property — no production endpoint ever scraped it. Moved to
  module-level lazy singletons on the global `prometheus_client.REGISTRY`
  (mirroring the core connection-pool histogram's pattern, including its
  dual-import-path duplicate-registration guard), so any co-hosted
  core/Nexus `/metrics` endpoint now folds these metrics in with zero
  additional wiring.
- **`agent_type` label bounded (#1708 redteam).** Unlike `model`/`provider`
  (bounded against a closed enum), `agent_type` had no fixed set of valid
  values and was exported raw — an unbounded cardinality risk. Now bounded
  via a thread-safe top-N admission bucketer
  (`KAIZEN_METRICS_AGENT_TYPE_MAX_VALUES`, default 100 distinct values,
  overflow collapses to `_other`); in-memory stats retain the raw key for
  operators, only the exported Prometheus label is bounded.

## [2.29.0] — 2026-07-10 — outbound governance transport wiring + DeepSeek provider

### Added

- **Outbound governance seam wired to LLM/tool/HTTP transports** (#1517 leg-b). `GovernedProvider`, `GovernedToolInvoker`, and `GovernedHTTPClient` are transparent proxies that route every outbound call through core's outbound-effect governance interceptor, with a fail-closed `resolve_interceptor` — an unresolved interceptor refuses the call rather than passing it through ungoverned.
- **DeepSeek is now a first-class `LlmProvider`** (#1609) — `from_model` / `from_name` resolution, plus `from_env` legacy and selector tiers.

### Security

- **`GovernedHTTPClient` redacts credentials from HTTP audit targets** (redteam L1). `redact_http_target` strips userinfo and query/fragment components before the URL is recorded as an audit target, so a credential-bearing outbound URL never lands in the audit trail verbatim.

## [2.28.0] — 2026-06-19 — LlmClient lifecycle: aclose() + async context manager + opt-in HTTP pooling

### Added

- **`LlmClient` now exposes a lifecycle surface — `aclose()` + `__aenter__`/`__aexit__`
  — with opt-in persistent HTTP-transport pooling** (#1388). Previously
  `kaizen.llm.client.LlmClient` had no `close()`/`aclose()`/`__aexit__`; once a
  client held a persistent HTTP transport its socket was released only at GC,
  emitting `ResourceWarning: unclosed <socket.socket ...>` and failing any run
  under `-W error::ResourceWarning`. The change is strictly additive and
  backward-compatible:
  - One-shot callers are unchanged: `await LlmClient.from_deployment(d).embed(...)`
    still constructs and closes a fresh `LlmHttpClient` per `embed()` call —
    nothing is held between calls, so nothing leaks and no warning is emitted.
  - New managed mode pools the transport: `async with LlmClient.from_deployment(d)
as client:` eagerly creates ONE persistent `LlmHttpClient` on entry, reuses
    it across every `embed()` in the scope (amortizing SSRF-resolver +
    connection-pool setup, and surviving per-call errors), and deterministically
    closes it on exit. `await client.aclose()` is the explicit (idempotent)
    close; a no-op when no transport was created.
  - `__del__` is WARN-ONLY, mirroring `LlmHttpClient.__del__`: a managed client
    that pooled a transport and was never closed emits a `ResourceWarning`
    naming `aclose`; it never calls close from the finalizer (async cleanup in
    `__del__` deadlocks on CPython's root logging lock per
    `rules/patterns.md` § "Async Resource Cleanup"). One-shot unmanaged callers
    hold no transport, so they emit no warning.
  - No sync `close()` is provided: a sync wrapper would need `asyncio.run()` and
    break inside any active event loop (`rules/patterns.md` § "Paired Public
    Surface").
    Regression coverage:
    `tests/regression/test_issue_1388_llmclient_resourcewarning.py` (the
    after-close GC path overrides pytest.ini's global `ignore::ResourceWarning`
    with `error::ResourceWarning` so the no-leak assertion is real).

## [2.27.1] — 2026-06-17 — PEP 563 Signatures: structured output no longer silently empties

### Fixed

- **`Signature` defined under `from __future__ import annotations` (PEP 563) no
  longer breaks `JSONOutputParser`** (#1352). PEP 563 stores each field's
  annotation as a _string_ (`'str'`, `'List[dict]'`) instead of a type object;
  the parser's `isinstance(value, expected_type)` then raised
  `TypeError: isinstance() arg 2 must be a type ...`, which was swallowed by the
  parser's own `except (json.JSONDecodeError, TypeError)` — silently degrading a
  valid JSON response to `{}`. Two layers fix it:
  - `SignatureMeta` resolves string annotations to real type objects at
    class-construction time (using the defining module's globals, exactly as
    `typing.get_type_hints` would), so stored field types are identical with or
    without PEP 563.
  - `JSONOutputParser._convert_to_type` defensively returns the value unchanged
    if an annotation string ever survives construction (dynamically-exec'd
    Signatures, unresolvable forward refs) instead of raising and discarding the
    parse.
    Regression coverage: `tests/regression/test_issue_1352_pep563_signature_parser.py`.

## [2.27.0] — 2026-06-11 — RAG node honesty: strip simulated-capability over-claims

### Deprecated

- **`VisualQuestionAnsweringNode`** (`kaizen.nodes.rag.multimodal`) — its answer is
  a keyword-derived placeholder and its confidence is a fixed value; it does NOT run a
  vision-language model and cannot read image pixels. No VQA backend is implemented.
  Constructing it now emits a `DeprecationWarning`. **Scheduled for removal in the next
  minor release.** Migration: remove the node from workflows — there is no real VQA
  backend to migrate to.
- **`ImageTextMatchingNode`** (`kaizen.nodes.rag.multimodal`) — its match scores are
  keyword-derived placeholders, not CLIP/ALIGN image-text similarity; no image-text
  model is loaded. Constructing it now emits a `DeprecationWarning`. **Scheduled for
  removal in the next minor release.** Migration: remove the node from workflows — no
  real image-text matching backend is provided.

### Changed

- **`MultimodalRAGNode`** docstrings corrected to stop advertising real CLIP/BLIP-2
  vision models. The node wires real LLM query-analysis + response-generation stages
  over a lexical/hash-based placeholder encoder (a deterministic hash heuristic, NOT a
  learned vision model). The hardcoded `gpt-4-vision` model string at the
  response-generation stage is replaced with an env-resolved `OPENAI_VISION_MODEL`
  (falling back to the default LLM model) for `rules/env-models.md` compliance. Removed
  the unverifiable "40-60% quality improvement" / "1-3 seconds" performance claims.
  Runtime behavior unchanged.
- **`FederatedRAGNode`** docstrings corrected to stop advertising real distributed
  cross-host federation. The node demonstrates the federated-RAG aggregation pattern
  over in-process simulated nodes — it does NOT perform real distributed network
  queries. Removed the "2-10 seconds depending on federation size" performance claim.
  Runtime behavior unchanged.
- **`ColBERTRetrievalNode`** docstrings corrected to stop advertising a real
  BERT/ColBERT model. The node is a lexical late-interaction approximation
  (token-overlap MaxSim heuristic), NOT a learned-embedding model; `token_model` is an
  informational label only and loads no model. Removed the "0.92+ accuracy" / "~500ms"
  claims. Also removed the dead, never-called `_create_workflow` method whose
  `token_embedder` generated random `np.random.randn(768)` embeddings (unreachable
  fabrication — the node's `run()` is the only entry point). Runtime behavior of `run()`
  unchanged.

## [2.26.0] — 2026-06-11 — env-model discipline: provider config getters use documented default-model constants

### Changed

- **The nine `get_*_config()` functions in `kaizen.config.providers` no longer
  hold inline hardcoded `default_model` literals** (`rules/env-models.md`,
  FNEW-5). Each provider's final fallback is now a documented module-level
  `DEFAULT_<PROVIDER>_MODEL` constant — provider-intrinsic (the caller has already
  chosen the provider, so the default carries no lock-in), overridable via
  `KAIZEN_<PROVIDER>_MODEL`, and deliberately **not** chained to the
  provider-agnostic `KAIZEN_DEFAULT_MODEL` (chaining would reintroduce the 2.25.0
  provider/model mismatch — e.g. a `claude-*` model returned under
  `provider="openai"`). Zero-config `auto_detect_provider()` is unchanged.
- **User-visible default refresh:** the stale Anthropic default
  `claude-3-haiku-20240307` is refreshed to `claude-haiku-4-5`. Callers using the
  bare `get_anthropic_config()` default (no `model=` arg AND no
  `KAIZEN_ANTHROPIC_MODEL` env) now receive `claude-haiku-4-5`. Set
  `KAIZEN_ANTHROPIC_MODEL` or pass `model=` to pin a specific model. Non-breaking
  (signature and resolution order unchanged; only the final-fallback value moved).
- New regression suite (`tests/regression/test_issue_fnew5_provider_intrinsic_defaults.py`)
  locks default resolution, `KAIZEN_<PROVIDER>_MODEL` / `model=` precedence, and
  the `KAIZEN_DEFAULT_MODEL` no-leak invariant across all nine providers.

## [2.25.1] — 2026-06-11 — hotfix: slim-core import contract for the autonomy hook system

### Fixed

- **`import kaizen_agents.patterns` (and any `kaizen.core.autonomy.hooks` import)
  no longer requires the optional `observability` extra on a clean install.**
  `LoggingHook`, `MetricsHook`, and `TracingHook` eagerly pulled `structlog`,
  `prometheus-client`, and `opentelemetry` (all `[observability]`-extra deps) at
  module-import time through the hook package's eager re-exports, so a slim-core
  `pip install kailash-kaizen` raised `ModuleNotFoundError` the moment anything
  imported the hook system (e.g. for `HookManager`). The three observability
  hooks are now lazy-loaded via PEP 562 `__getattr__`: importing the hook system
  stays slim-core clean, and accessing one of those hooks without the extra raises
  a clear `ImportError` pointing at `pip install 'kailash-kaizen[observability]'`.
  `LoggingHook(format="text")` (the default) now works without `structlog`. Caught
  by the 2.25.0 clean-venv install-verification gate.

## [2.25.0] — 2026-06-11 — env-model discipline: fail-closed provider detection + HF preset router + multi-modal adapter fixes

### Changed — BREAKING (migration): AI-node model defaults now resolve from `KAIZEN_DEFAULT_MODEL`

- **AI-enhanced node constructors no longer ship hardcoded model defaults**
  (`rules/env-models.md`). `SSOAuthenticationNode`, `DirectoryIntegrationNode`,
  `EnterpriseAuthProviderNode`, `AIThreatDetectionNode`, `AIBehaviorAnalysisNode`,
  `GDPRComplianceNode`, `LLMRouter`, and `KaizenNode` previously defaulted to
  hardcoded literals (`gpt-4o-mini`, `gpt-4`, `gpt-3.5-turbo`,
  `ollama:llama3.2:3b`). They now resolve: explicit `model=`/`ai_model=` argument →
  `KAIZEN_DEFAULT_MODEL` env var → typed `kaizen.errors.EnvModelMissing` naming the
  env var (the established `CoreAgent` contract).
  **Migration:** set `KAIZEN_DEFAULT_MODEL` in your `.env` (or pass the model
  explicitly). The security nodes' hardcoded `provider="openai"` defaults are also
  gone — the provider is auto-detected from the resolved model (`gpt-*`/`o1-*` →
  openai, `claude-*` → anthropic) and an explicit `provider=` still wins.
  `GDPRComplianceNode` requires a model only when `ai_analysis=True` and keeps the
  `"ollama:<model>"` prefix convention. New shared helper:
  `kaizen.nodes._env_model.{resolve_default_model, detect_provider}`.
  Provider auto-detection now covers four families (`gpt-*`/`o1-*`/`davinci-*` →
  openai, `claude-*` → anthropic, `llama`/`mistral`/`mixtral`/`bakllava` → ollama,
  `gemini-*` → google) and **fails closed**: an unrecognized model raises the new
  typed `kaizen.errors.ProviderUndetectable` instead of silently routing to the
  mock provider (a fail-open in security/auth/compliance nodes). Pass
  `provider="mock"` explicitly for test contexts.

### Fixed

- **HuggingFace preset targeted the decommissioned `api-inference.huggingface.co`
  host** (DNS NXDOMAIN — the SSRF guard correctly rejected every construction, so
  the preset was unusable). `huggingface_preset` now targets the Inference
  Providers router (`https://router.huggingface.co` + `path_prefix="/hf-inference"`;
  the wire protocol's `/models/{model}` contract is unchanged). The embedding
  provider sibling (`providers/embedding/huggingface.py`) is fixed in the same
  change.
- **`get_multi_modal_adapter` raised `TypeError` for any caller with an OpenAI key
  set**: provider-agnostic kwargs (e.g. `model=`, `whisper_model=`) were forwarded
  verbatim into `OpenAIMultiModalAdapter`, which does not accept them. Kwargs are
  now signature-filtered per adapter at all construction sites; the adapter cache
  key includes the (api_key-excluded) kwargs so differently-configured adapters no
  longer collide on one cache slot.
- **Cross-suite test-state pollution eliminated**: in-process `sys.modules` purges
  in the import-performance and registering-import tests re-imported fresh class
  objects mid-process (silently discarding the test conftest's mock-provider patch
  and breaking exception class identity). All converted to subprocess checks; the
  import-performance targets re-pinned to honest cold-import measurements.

## [2.24.6] — 2026-06-10 — RAG nodes provably correct end-to-end

### Fixed — RAG output-side wiring (F31 Wave 2.5): every LLM stage's OUTPUT now reaches its consumer parsed

- **Every LLMAgentNode stage across the 5 real RAG node files now has its OUTPUT
  parsed before reaching its downstream consumer (PR #1283).** Each stage
  publishes on the `response` port (`{"content": "<text or JSON string>"}`), but
  consumers were reading structured fields off the raw `response` dict — so every
  field resolved to its default and the stage's decision/output was silently
  dropped. The fix inserts a module-level `from_function` response-parser between
  each LLM stage and its consumer that unwraps `response → .content → json.loads`
  (or `.content` directly for prose stages) and publishes the parsed structured
  dict. 15 parsers total — workflows 1, graph 3, query_processing 6, agentic 5 —
  each returning a **typed parse-error sentinel** on malformed/non-JSON/missing-
  field output (never a fabricated default), so a node degrades to an honest
  empty/unadjusted result rather than inventing data.
  - **`AdaptiveRAGWorkflowNode`:** the `rag_strategy_analyzer` decision now drives
    the `SwitchNode` strategy executor + results aggregator (was read off the
    wrong `result` port + unparsed; the strategy choice never reached the
    executor). Closes F31-FU3.
  - **`GraphRAGNode`:** entity-extraction, query-analysis, and global-summary
    outputs are now parsed — the knowledge graph was previously built by iterating
    the unparsed response dict's keys, the query-driven retrieval returned an empty
    subgraph regardless of the LLM's analysis, and the global summary was accepted
    but never read by the synthesizer. Closes F31-FU1.
  - **`Query*` processors (expansion / decomposition / rewriting / intent /
    multi-hop):** all 6 LLM stages were silently defaulting their structured
    output; now parsed.
  - **`AgenticRAGNode` / `ReasoningRAGNode`:** all 5 LLM stages were dropping
    verdicts or raising on prose output read as a missing key; now parsed.
    `ConversationalRAGNode` was already correct and is unchanged.
- Each fix ships a real-`LocalRuntime` end-to-end test with a verified red-pre
  proof + a malformed-output honesty test; non-runnable graphs (networkx sandbox,
  agentic cycle) are proven via structural-wiring + standalone-parser probes.
  RAG suite: 948 passed; `src/kailash/nodes/base.py` untouched. Converged via
  parallel reviewer + security-reviewer (2 consecutive clean rounds).

### Fixed (F9 #1117 — `PrivacyPreservingRAGNode` published nothing at runtime)

- **`PrivacyPreservingRAGNode` now runs end-to-end and PUBLISHES its documented
  output (F9 #1117).** Five codegen stages of the wrapped workflow
  (`query_anonymizer`, `dp_noise_injector`, `secure_aggregator`, `audit_logger`,
  `result_formatter`) DEFINED an inner function that bound a function-LOCAL
  `result` but never CALLED it at module scope, so each `PythonCodeNode`'s output
  gate published nothing — and the workflow actually crashed
  (`Node outputs must be JSON-serializable. Failed keys: ['anonymize_query']`)
  when it tried to serialize the bound function object. Each stage now calls its
  function at module scope (`result = <fn>(...)`) and `del`s the helper, exactly
  as the sibling `evaluation.py` F9 #1117 fix does. Three additional latent
  defects surfaced once the stages actually ran and were fixed in the same pass:
  (a) inter-node edges read non-existent nested output ports
  (`private_rag_executor.retrieval_results`, `audit_logger.audit_record`) instead
  of the single `result` port a `PythonCodeNode` publishes — every edge now reads
  `result` and each downstream stage unwraps the nested shape it needs;
  (b) `query_anonymizer` / `secure_aggregator` / `audit_logger` used `re` /
  `random` / `hashlib` / `datetime` without importing them inside the function
  body (the F9 #1118 separate-`exec`-namespace closure gotcha) — imports moved
  function-local; (c) `perturb_scores` divided by zero on an empty retrieval set
  — guarded. The Wave-2 honesty work (derived `data_minimization` /
  `anonymization_strength` / `pii_redaction_attempted` flags, no fake regulatory
  verdicts) is preserved and now actually reaches the published output. Verified
  end-to-end against a real `LocalRuntime`: a query carrying PII + sample
  documents + consent produces a non-empty `privacy_preserving_results` payload
  with the documented `results` / `privacy_report` / `audit_record` /
  `confidence_bounds` keys and PII (email, phone) redacted.

### Deprecated

- **`SecureMultiPartyRAGNode` is deprecated and slated for removal in a future
  minor release.** It is a NON-FUNCTIONAL simulation: it performs NO cryptography
  (no secret sharing, homomorphic encryption, or multi-party computation) and
  does NOT compute over the supplied `party_data` — it aggregates
  `random.random()` placeholder values, so its `aggregate_result` is unrelated to
  the inputs and its `computation_proof` is a hash label, not a cryptographic
  proof. Instantiating it now emits a `DeprecationWarning`. **Migration:** there
  is no real in-tree replacement; do not use this node for any privacy-sensitive
  workload. If you need genuine secure aggregation, integrate a real
  MPC / secret-sharing / homomorphic-encryption library outside this node. The
  node remains importable and runnable for one minor cycle before removal.

## [2.24.5] — 2026-06-01 — aiosqlite is a core dependency (memory subsystem)

### Fixed

- **`import kaizen.memory` no longer fails on a clean install (`ModuleNotFoundError: aiosqlite`)** — `kaizen/memory/__init__.py` eagerly imports `persistent_tiers`, which has an unconditional module-scope `import aiosqlite`, but the #890 slim-core audit had scoped `aiosqlite` to the optional `db` extra. So the multi-tier memory subsystem (and the path to `DataFlowMemoryBackend`, which itself does not use aiosqlite) required the extra despite being a first-class, eagerly-exported API. Promoted `aiosqlite` to a core dependency — it is a pure-Python async wrapper over the stdlib `sqlite3` (zero compiled/transitive weight) that a core subsystem imports eagerly, so it cannot be optional. `asyncpg` (PostgreSQL trust migration, not eagerly imported) correctly stays in the `db` extra. Verified: `import kaizen.memory` succeeds on `pip install kailash-kaizen` with no extras.

## [2.24.4] — 2026-06-01 — DataFlowMemoryBackend warm-tier persistence (#855)

### Fixed

- **`DataFlowMemoryBackend` warm-tier persistence no longer raises on its own documented schema (#855)** — the `MemoryEntryModel` schema named a field `tags`, which collides with the core SDK's reserved `NodeMetadata.tags` (typed `set[str]`). `store()` passed `tags=json.dumps([...])` (a JSON string) to `MemoryEntryModelCreateNode`, and CreateNode metadata validation rejected it (`WorkflowValidationError: NodeMetadata.tags Input should be a valid set`), so warm-tier persistence raised on first store and had never worked for its own documented schema. Renamed the DataFlow column `tags` → `tag_list` at all four sites (docstring schema, `store()` write key, `store_many()` write key, and the `_record_to_entry()` read-back with a legacy `tags` fallback for pre-rename rows). The in-memory `MemoryEntry.tags` attribute is unchanged; only the persisted column name changes. Verified end-to-end against real SQLite: `store()`→`get()` round-trips content AND tags.

## [2.24.3] — 2026-05-28 — RAG query_processing + workflows defect close-out (F25 Shards D + E)

### Fixed (Shard E — `kaizen.nodes.rag.query_processing`)

- **`AdaptiveQueryProcessorNode` now executes end-to-end (CRITICAL).** The
  adaptive workflow embeds `QueryIntentClassifierNode` as a node-type
  string and wires `intent_analyzer.routing_decision` →
  `adaptive_processor.routing_decision`. Pre-fix the classifier's `run()`
  returned a flat classification dict WITHOUT the `routing_decision`
  field — that field existed only as the strategy_mapper output of the
  classifier's own inner workflow, which is NOT exercised when the node
  is composed as a single Node inside another workflow. Every end-to-end
  call to the adaptive workflow crashed at codegen with
  `NameError: name 'routing_decision' is not defined`. The fix returns
  `routing_decision` from `QueryIntentClassifierNode.run()` as part of
  the documented public contract, so the deterministic `run()` path and
  the LLM-driven inner-workflow path both expose the same field shape.
  Surfaced by the F25 RAG audit.
- **`QueryDecompositionNode` resolver + LLM prompt aligned on
  `depends_on`.** The dependency_resolver PythonCodeNode and the
  `query_decomposer` LLM `system_prompt` now both use `depends_on` as the
  per-sub-question dependency-list field name. This matches the broader
  kaizen RAG convention used by `MultiHopQueryPlannerNode`'s hop_planner.
  The change prevents future LLM outputs trained on the kaizen
  `system_prompt` patterns from silently producing an empty dependency
  graph through field-name drift.

### Fixed (Shard D — `kaizen.nodes.rag.workflows`)

- **`AdvancedRAGWorkflowNode` now exposes a public `documents` parameter
  (required, `list`-typed).** Previously the facade auto-derived
  `quality_analyzer_documents` from the inner-graph node ID, forcing
  callers to know the inner-graph layout. `node.execute(documents=[...])`
  now works directly. Same defect class as the 2.24.2 fix for
  `SimpleRAGWorkflowNode`, applied at the WorkflowNode-facade
  `input_mapping` layer.
- **`AdaptiveRAGWorkflowNode` now exposes public `documents` (required,
  `list`-typed) + `query` (optional `str`, default `""`) parameters.**
  Previously these leaked as `document_preprocessor_documents` /
  `document_preprocessor_query`. Same defect class as above.
- **`RAGPipelineWorkflowNode` now exposes public `documents` (required,
  `list`-typed) + `query` (optional `str`, default `""`) + `strategy`
  (optional `str`, default = `self.default_strategy`) parameters.**
  Previously these leaked as `config_processor_documents` /
  `config_processor_query` / `config_processor_strategy`.
- **`RAGPipelineWorkflowNode` no longer crashes at the entry node on
  first invocation.** The `config_processor` PythonCodeNode codegen
  referenced an undefined `**kwargs` dict (PythonCodeNode binds explicit
  inputs as locals, not a kwargs dict), so every invocation raised
  `NameError: name 'kwargs' is not defined` at the entry node. The
  codegen now constructs the processed_config dict directly from the
  bound input parameters, with `RAGConfig` values safely embedded
  (numeric coercion + `repr()` for string literals — no untrusted-value
  interpolation surface).

### Notes

- Both Shard D (`workflows.py`) and Shard E (`query_processing.py`)
  landed in the same release. Downstream nodes (`embedder` / `vector_db`)
  in the workflow-node variants still require real embedding-provider +
  vector-store configuration to complete the full pipeline end-to-end;
  that broader inner-graph wiring is tracked as a separate scope.

## [2.24.2] — 2026-05-28 — `SimpleRAGWorkflowNode` runnable end-to-end (F25)

### Fixed

- **`SimpleRAGWorkflowNode` now accepts a `text` input.** The Quick Start
  RAG workflow node previously could not be executed: the inner-graph
  `semantic_chunker` required a `text` input that nothing supplied, so
  every call to `runtime.execute(...)` raised
  `WorkflowValidationError: Node 'semantic_chunker' missing required
inputs: ['text']`. The fix wires the chunker's `text` parameter
  through the workflow facade so users can now invoke
  `node.execute(text="document body...")` and the inner chunker
  receives the input as expected. Surfaced by the F25 RAG audit.
  Downstream nodes (`embedder` / `vector_db`) still require real
  embedding-provider + vector-store configuration to complete the full
  pipeline end-to-end; that broader inner-graph wiring is tracked as a
  separate scope.

## [2.24.1] — 2026-05-25 — LLM-path crash fixes (#1140, #1141)

### Fixed

- **`GoogleGeminiProvider._extract_response` no longer crashes on `parts=None`
  candidates (#1140).** Gemini returns candidates whose `.content` is populated
  but `.content.parts` is `None` on SAFETY / MAX_TOKENS / tool-call-only
  finishes. The guard now checks `.parts` before iterating, so these routine
  production responses return a well-formed dict (empty content, empty
  tool_calls) instead of raising `TypeError: 'NoneType' object is not
iterable`. `finish_reason` still surfaces (`content_filter` / `length`) so
  callers can detect the filter fired. The sibling `_format_tool_calls` path
  carried the same None-deref and is fixed in the same change.
- **`JSONOutputParser._convert_to_type` no longer silently corrupts results for
  subscripted-generic OutputField types (#1141).** A `Signature` OutputField
  typed `Optional[List[Dict]]` / `List[X]` / `Dict[K, V]` triggered
  `TypeError: Subscripted generics cannot be used with class and instance
checks` on Python 3.9+, which was swallowed and fell through to regex
  key-value extraction — returning malformed strings while reporting success.
  The parser now unwraps subscripted generics via `typing.get_origin` /
  `get_args` before the `isinstance` check, so well-formed JSON parses into the
  documented `list` / `dict` runtime shapes. Genuine malformed JSON still
  surfaces as a parse failure.

## [2.24.0] — 2026-05-20 — kaizen.nodes.rag provably correct + F9 cleanup (F8 R1)

### Added

- **Behavioral coverage of every preserved RAG class** (F8 B1–B10). 643+ new
  tests + 5 spec sections (`specs/kaizen-rag.md` is now the authoritative
  domain truth for the 58 RAG class definitions: 55 `@register_node`
  classes + 2 `RAGConfig` dataclasses + `RAGWorkflowRegistry`). The brief's
  "provably correct, not merely importable" criterion is now closed —
  every class has at least one behavioral test in the unit, integration,
  or regression tier.
- **`RAGStrategyRouterNode` / `RAGQualityAnalyzerNode` /
  `RAGPerformanceMonitorNode` / `RAGWorkflowRegistry`** all gain Tier-1
  unit + Tier-2a integration coverage (B10). The smoke-test
  zero-`xfail` invariant added in B9c is preserved.

### Fixed

- **`RAGStrategyRouterNode.run()` no longer raises `AttributeError`**
  (F8 B10). The class accessed `self.name` but the kailash `Node` base
  stores name on `self.metadata.name`; every call raised AttributeError
  on the LLMAgentNode init. Routes through `self.metadata.name` now.
- **`pii_detector` codegen** — F9 #1112: dob regex uses non-capturing
  groups so `re.findall` returns full-match strings (not tuples that
  crashed `.encode()`); F9 #1113: function returns its dict on the
  `redact=True` branch (was bound to a function-scope local never
  returned); F9 #1114: codegen now binds `result =
detect_and_redact_pii(text, ...)` at module scope so PythonCodeNode
  reads the redaction dict (the function was defined but never called).
- **`ConversationalRAGNode.create_session` session_id** — F9 #1116:
  now sourced from `secrets.token_hex(16)` (128-bit CSPRNG). The prior
  `sha256(f"{user_or_anon}_{datetime}")[:16]` form admitted ~10⁶
  brute-force ops within a 1-second window on the anonymous flow.
- **`RAGEvaluationNode` codegen** — F9 #1117/#1118:
  `test_executor`, `context_evaluator`, and `metric_aggregator` all
  return their dicts AND invoke their inner functions at module scope.
  `metric_aggregator` now imports the `datetime` class inside the
  function body (a module-scope `from datetime import datetime` is
  shadowed by PythonCodeNode's `datetime` module injection; the bare
  `datetime.now()` against the module raised `AttributeError`).
- **`RealtimeRAGNode.start_monitoring`** — F9 #1121: retains the
  monitoring task on `self._monitor_task`; `stop_monitoring()` is now
  async and cancels + awaits the retained task (the prior
  fire-and-forget made the task GC-eligible and left the loop
  uncancellable from outside).
- **`RealtimeStreamingRAGNode` `processing_time` unit** — F9 #1122:
  reported in SECONDS (the prior `chunk_idx * chunk_interval` form left
  consumers off-by-1000× from the asyncio.sleep call's seconds-based
  semantics; `chunk_interval` is canonically milliseconds).
- **`RAGQualityAnalyzerNode.run()` `expected_results` kwarg** — wired
  through into `quality_analysis["expected_result_count"]` /
  `expected_recall_ratio`; the documented kwarg was previously accepted
  but silently dropped (Rule 3c — documented kwargs without consumption
  is a silent-fallback variant).

### Changed (env-models compliance)

- **All 36 hardcoded `"gpt-4"` model defaults across 9 rag modules
  replaced with env-loaded `_DEFAULT_LLM_MODEL`** (F9 #1126). Mirrors
  the `router.py:22-24` precedent landed in F8 B10:
  ```python
  _DEFAULT_LLM_MODEL = os.environ.get(
      "OPENAI_PROD_MODEL", os.environ.get("DEFAULT_LLM_MODEL")
  )
  ```
  Affected modules: `advanced`, `agentic`, `conversational`, `evaluation`,
  `graph`, `multimodal`, `query_processing`, `similarity`, `workflows`.
  **Behavior change**: existing callers relying on the `"gpt-4"` default
  now get the env-resolved value (or `None` when neither env var is set
  — env-models-compliant). Set `OPENAI_PROD_MODEL` in `.env` to restore
  prior behavior.
- **`kailash.middleware.mcp.enhanced_server.MCPToolNode` /
  `MCPResourceNode`** (F8 A1-core) — constructors now use the canonical
  keyword `super().__init__(name=name, **config)` form. The prior
  `super().__init__(name)` positional form raised `TypeError` on every
  construction (Node base is keyword-only). External subclasses calling
  the constructor positionally MUST migrate to keyword form.

### Migration

- **`StreamingRAGNode` collision** (still active from 2.23.0): the
  realtime variant is `RealtimeStreamingRAGNode`; `optimized` keeps
  `StreamingRAGNode`. No change in 2.24.0.
- **Env-models migration**: if your dev/prod environment relied on the
  baked-in `"gpt-4"` default and does not set `OPENAI_PROD_MODEL` or
  `DEFAULT_LLM_MODEL`, set one of them in `.env`. The `model` config
  block on each LLM-using node now resolves to `None` when neither is
  set, which propagates to the LLMAgentNode constructor.

## [2.23.1] — 2026-05-19 — complete the `[rag]` extra (#891 follow-up)

### Fixed

- **`pip install "kailash-kaizen[rag]"` now imports `kaizen.nodes.rag`.**
  2.23.0 resurrected the package but its `[rag]` extra declared only
  `numpy`/`Pillow`; the resurrected import graph also needs `networkx`
  (graph RAG — was undeclared anywhere) plus `requests` + `aiosqlite`
  (pulled transitively via `kailash.nodes.api.rest` and the kailash data
  path the rag modules import). `pip install "kailash-kaizen[rag]==2.23.0";
import kaizen.nodes.rag` raised `ModuleNotFoundError: networkx`. The
  `[rag]` extra is now the complete dependency set:
  `numpy, Pillow, networkx, requests, aiosqlite`. **`kaizen.nodes.rag`
  requires `pip install "kailash-kaizen[rag]"`** (its node-functional deps
  are intentionally behind the extra per the issue #890 core-dep audit;
  bare `import kaizen` is unaffected — the rag package is deep-import-only).

## [2.23.0] — 2026-05-19 — resurrect `kaizen.nodes.rag` (#891 follow-up)

### Fixed

- **`kaizen.nodes.rag` is importable again** — the 17-module RAG package
  (~53 node classes: GraphRAG, AgenticRAG, FederatedRAG, MultimodalRAG,
  privacy-preserving RAG, ColBERT/HyDE retrieval, RAG evaluation, etc.) was
  **un-importable from the 2026-03-11 monorepo move (`b553104c`) until now** —
  every module's relative imports pointed at a non-existent
  `kaizen.nodes.{base,code,data,logic,security}` / `kaizen.runtime` /
  `kaizen.workflow` tree. All ~40 broken imports across 14 modules are
  repointed to their real `kailash.*` locations. The package now imports clean.

### Changed

- **`rag.realtime.StreamingRAGNode` → `RealtimeStreamingRAGNode`** — once the
  package became importable, `rag.realtime` and `rag.optimized` both registered
  the global name `StreamingRAGNode`, which the kailash 2.23.0 cross-module
  collision guard (#891) rejects at import. The realtime node is renamed
  (`rag/__init__.py` already aliased it `as RealtimeStreamingRAGNode`);
  `rag.optimized` keeps `StreamingRAGNode`. Migration for the realtime node:
  `add_node("StreamingRAGNode", ...)` → `add_node("RealtimeStreamingRAGNode", ...)`.
  Requires `kailash>=2.23.0`.

## [2.22.0] — 2026-05-19 — node-registry collision fix (#891)

### Changed

- **`HybridSearchNode` renamed to `SemanticHybridSearchNode` (#891)** — the RAG
  hybrid-search node (`kaizen.nodes.ai.hybrid_search`) registered the same global
  registry name as kailash-dataflow's pgvector `HybridSearchNode`, making
  `add_node("HybridSearchNode")` resolve import-order-dependently. The class is
  internal-only (not on the package's public `__init__` surface), so no
  deprecation shim is provided. Deep importers migrate:
  `from kaizen.nodes.ai.hybrid_search import HybridSearchNode` →
  `import SemanticHybridSearchNode`; `add_node("HybridSearchNode", ...)` →
  `add_node("SemanticHybridSearchNode", ...)`.

## [2.21.1] — 2026-05-18 — restore `kaizen.api` deprecation shim (#1071)

### Fixed

- **`kaizen.api` restored as a deprecation shim (#1071)** — the structural-split refactor (#75) relocated the unified Agent API from `kaizen.api` to `kaizen_agents.api` and removed `kaizen.api` outright with no deprecation cycle. `from kaizen.api import Agent` raised `ModuleNotFoundError` on every published release — a hard break for every downstream caller on first `pip install --upgrade`. `kaizen.api` is now restored as a PEP 562 deprecation shim: every public symbol that historically lived under `kaizen.api` resolves through it and emits a `DeprecationWarning` naming the new import path on attribute access. The shim will be removed in a future major release.

### Migration — `kaizen.api` → `kaizen`

| Old (deprecated)                  | New                                      |
| --------------------------------- | ---------------------------------------- |
| `from kaizen.api import Agent`    | `from kaizen import Agent`               |
| `from kaizen.api import <symbol>` | `from kaizen_agents.api import <symbol>` |

Where `<symbol>` is any of the historical secondary surface: `AgentConfig`, `AgentResult`, `ToolCallRecord`, `CapabilityPresets`, `AgentCapabilities`, `ExecutionMode`, `MemoryDepth`, `ToolAccess`, `ConfigurationError`, `validate_configuration`, `validate_model_runtime_compatibility`, `resolve_memory_shortcut`, `resolve_runtime_shortcut`, `resolve_tool_access_shortcut`. `Agent` resolves through `kaizen` so the `kaizen_agents` → `kaizen.core.agents` fallback chain is preserved on installs without the optional `kaizen-agents` package.

## [2.21.0] — 2026-05-09 — slim-core decoupling: 9 core deps + provider/observability/db/cache/rag extras (#890)

Minor release shipping the kailash-kaizen side of the kailash 2.18.0 / #890 slim-core decoupling. **Install-shape breaking change** — kaizen drops from 29 → 9 core dependencies. Provider SDKs (Azure, Google, token counters), observability (Prometheus/OpenTelemetry/structlog), database (aiosqlite/asyncpg), cache (Redis), RAG (numpy/Pillow), research-validator (GitPython), and HTTP server (FastAPI/uvicorn) all move to opt-in extras. The new `[all]` umbrella preserves the pre-2.21.0 default install for users who do not want to enumerate which subsystem they consume.

### Migration table

| Surface used                                           | Pre-2.21.0 install           | 2.21.0+ install                                      |
| ------------------------------------------------------ | ---------------------------- | ---------------------------------------------------- |
| Core agent / `BaseAgent` / `Signature` / `Pipeline`    | `pip install kailash-kaizen` | `pip install kailash-kaizen` (unchanged — slim core) |
| Azure OpenAI provider (`providers.llm.azure`)          | `pip install kailash-kaizen` | `pip install 'kailash-kaizen[providers-azure]'`      |
| Google Gemini provider (`providers.llm.google`)        | `pip install kailash-kaizen` | `pip install 'kailash-kaizen[providers-google]'`     |
| Token-counter providers (tiktoken / anthropic counter) | `pip install kailash-kaizen` | `pip install 'kailash-kaizen[providers-tokens]'`     |
| HTTP transports (FastAPI / uvicorn)                    | `pip install kailash-kaizen` | `pip install 'kailash-kaizen[server]'`               |
| Observability (Prometheus / OTEL / structlog)          | `pip install kailash-kaizen` | `pip install 'kailash-kaizen[observability]'`        |
| Database (aiosqlite + asyncpg)                         | `pip install kailash-kaizen` | `pip install 'kailash-kaizen[db]'`                   |
| Distributed cache (Redis)                              | `pip install kailash-kaizen` | `pip install 'kailash-kaizen[cache]'`                |
| RAG / vision (numpy + Pillow)                          | `pip install kailash-kaizen` | `pip install 'kailash-kaizen[rag]'`                  |
| Research validator (GitPython)                         | `pip install kailash-kaizen` | `pip install 'kailash-kaizen[research-validator]'`   |
| Pre-2.21.0 default install (back-compat — everything)  | `pip install kailash-kaizen` | `pip install 'kailash-kaizen[all]'`                  |

### Changed

- **Slim core dependencies** — `pip install kailash-kaizen` now installs 9 deps (down from 29): `kailash`, `kailash-mcp`, `pydantic`, `typing-extensions`, `anyio`, `httpx`, `aiohttp`, `PyJWT`, `cryptography`. Audit per #890:
  - **Provider SDKs (azure-ai-inference, azure-identity, azure-core, google-genai, tiktoken-style counters)** — all imports are function-local in `providers/llm/{azure,google}.py`. Moved to per-provider extras (`[providers-azure]`, `[providers-google]`, `[providers-tokens]`).
  - **HTTP server (fastapi, uvicorn[standard])** — only used by `kaizen.server.*`. Moved to `[server]` extra.
  - **Observability (prometheus-client, opentelemetry-api, opentelemetry-sdk, structlog)** — only used by `kaizen.observability.*`. Moved to `[observability]` extra.
  - **Database (aiosqlite, asyncpg)** — only used by multi-tier memory + trust migration paths. Moved to `[db]` extra.
  - **Distributed cache (redis)** — only used by `governance/rate_limiter.py`. Moved to `[cache]` extra.
  - **RAG numerics (numpy, Pillow)** — only used by similarity / vision / hybrid search nodes. Moved to `[rag]` extra.
  - **Research validator (GitPython)** — only used by repo-introspection validator. Moved to `[research-validator]` extra.
- **`[all]` umbrella extra** — `pip install 'kailash-kaizen[all]'` resolves to `kailash-kaizen[providers-azure,providers-google,providers-tokens,providers-http,server,observability,db,cache,rag,research-validator]`, preserving the pre-2.21.0 default install experience.
- **`kailash` floor: 2.16.0** (was `2.13.4`) — aligns with the kailash 2.18.0 slim-core layout.

### Notes

- **Bare imports of moved subsystems on a slim install raise raw `ModuleNotFoundError`** — e.g. `from kaizen.observability import ...` requires `[observability]`. The migration table above is the authoritative recovery path.
- This is a **packaging / install-shape change only** — every Python public-API symbol that existed in 2.20.0 still exists in 2.21.0 with the same signature and semantics. Users on `pip install 'kailash-kaizen[all]'` see no behavior change.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.20.0] — 2026-05-06 — LLM-first trait derivation per agent-reasoning.md Rule 1 (#829)

### Changed

- **`Kaizen.create_specialized_agent` trait derivation is now LLM-first
  (closes #829).** When `config["behavior_traits"]` is not supplied, the
  framework derives behavioral traits via a `Signature`-driven LLM call
  (`RoleToTraitsSignature` in `kaizen.core._role_traits_signature`) instead of
  keyword-matching the role string against five hardcoded buckets. Derivation
  is cached per `Kaizen` instance keyed by `role.strip().lower()`, and the LLM
  call uses `temperature=0` so derivation is deterministic per
  `(instance, normalized_role)` pair. The previous `if any(word in role_lower
for word in [...])` classifier in `framework.py:513-536` was a direct
  violation of `rules/agent-reasoning.md` Rule 1 (BLOCKED hardcoded
  classification of agent input) and has been removed entirely.

### Behavior change — failure mode

- Trait derivation now requires a working LLM provider. When
  `KAIZEN_DEFAULT_MODEL` is unset OR the underlying LLM call fails (no API
  key, network error, rate limit), `create_specialized_agent` raises
  `RuntimeError` with a message naming both escape hatches:
  - Pass `behavior_traits=[...]` in `config` to skip derivation entirely.
  - Configure a working LLM provider key in `.env`.
- Previously, the keyword classifier returned a default trait list silently
  for any role that did not match the hardcoded buckets. That deterministic
  fallback was the Rule-1 violation; removing it is the fix.
- Empty / unparseable LLM output (zero parsed traits) falls back to the
  default list `["professional", "reliable", "adaptive"]` and emits a WARN
  log line `kaizen.trait_derivation.empty_output`. This is the
  empty-output guard, NOT a deterministic fallback.

### Migration

- **No code change required if your call site supplies `behavior_traits`** in
  the `config` dict — that path is unchanged.
- **No code change required if you have a working LLM provider** configured
  in `.env` — derivation works, with a one-time LLM round-trip per novel
  role per `Kaizen` instance and instant cache hits afterwards.
- **Action required if your call site relies on the old keyword classifier**
  AND you do not want LLM derivation: pass an explicit `behavior_traits`
  list in `config`. The previous keyword-classifier output (e.g.,
  `["analytical", "thorough", "evidence_based", "methodical"]` for roles
  containing "research" / "analyze" / "study") is no longer produced; if
  your code asserted on those exact strings, switch to passing them
  explicitly.

### Security

- **Prompt-injection sanitization on LLM-derived traits.** Every parsed
  trait MUST match `^[a-z0-9_ ]{1,32}$` and the list is capped at 5
  entries. Defends against a malicious `role` string subverting the LLM
  into emitting traits that would otherwise flow unchecked into the
  agent's downstream system prompt at `_generate_role_based_prompt`.
- **Bounded LRU cache.** `self._trait_cache` is an `OrderedDict` capped at
  256 entries with `popitem(last=False)` eviction. Defends against DoS via
  unique-role pollution.
- **Hashed role logging.** WARN-level empty-output log lines emit
  `role_hash=<sha256[:8]>` and `raw_len=<int>` instead of the raw role
  string and raw output. `RuntimeError` messages on derivation failure
  follow the same pattern. Defends against PII leakage to log aggregators
  (per `rules/observability.md` Rule 8 spirit).

### Spec

- `specs/kaizen-core.md` §7.5 (Trait Derivation) added with the full
  contract: cache normalization, determinism, default-model resolution,
  failure modes, sanitization, bounded cache, and out-of-scope clauses.

### Tests

- `tests/regression/test_issue_822_behavior_traits_render.py::test_behavior_traits_default_from_role` rewritten as
  shape-only Tier-2 integration test (per acceptance criterion #2 of #829).
- `tests/unit/test_kaizen_multi_agent_coordination.py::TestSpecializedAgentCreation::test_specialized_agent_role_based_behavior_traits` rewritten
  as shape-only — exact-string keyword-bucket assertions removed.
- New Tier-2 tests at `tests/integration/test_role_to_traits_llm_derivation.py`
  (4 tests covering acceptance criteria #2, #3, plus Risk-1 disposition) and
  `tests/integration/test_role_traits_cache_wiring.py` (2 tests covering
  cache hit + normalization).
- New `tests/unit/conftest.py` autouse fixture stubs
  `Kaizen._generate_role_based_traits` for Tier-1 unit tests so they remain
  deterministic and offline; the stub returns the same 3-element default
  list the keyword classifier returned for unmatched roles.

## [2.19.0] — 2026-05-05 — Dead MCP integration surface deletion (#822) + research/web-search extras (#814 Shard 2)

### Added

- **`research` and `web-search` optional-dependency extras (closes #814 Shard 2).** `pyproject.toml` now declares two optional-extras groups so users opt in to the lazy-imported runtime deps in `kaizen.research.parser` (arXiv paper search + PDF parsing) and `kaizen.tools.native.search_tools` (DuckDuckGo + HTML extraction). Install via `pip install 'kailash-kaizen[research]'` or `pip install 'kailash-kaizen[web-search]'` per `rules/dependencies.md` "Declared = Imported". Replaces the pre-existing pattern where `arxiv`, `pypdf`, `duckduckgo-search`, and `beautifulsoup4` were lazy-imported in source but undeclared in the manifest.
- **`kaizen.llm.testing.mock_preset()` test-only deployment factory (closes #788; cross-SDK parity with kailash-rs `LlmDeployment::mock()` at `crates/kailash-kaizen/src/llm/deployment/presets.rs:1183`).** New module `kaizen.llm.testing` exposes `mock_preset(model: str = "mock-model") -> LlmDeployment` for test code that needs a structurally-valid `LlmDeployment` without binding to a real provider. The deployment carries `preset_name="mock"`, `WireProtocol.OpenAiChat`, `StaticNone` auth, and an endpoint at `https://example.com/v1` (RFC-2606 reserved test host that resolves under the SSRF guard). Cross-SDK parity: Rust gates `mock()` behind `#[cfg(any(test, feature = "test-utils"))]` so the symbol does not exist in production builds; Python lacks cargo features, so the structural defense is **physical module separation** — `LlmDeployment.mock` does NOT exist on the production class, `kaizen.llm.presets.mock_preset` does NOT exist, and `"mock"` is NOT a registered preset. Test code MUST `from kaizen.llm.testing import mock_preset` explicitly. The module path is the deliberate red flag — production code that imports from a module named `testing` is structurally identifiable by `grep -rn 'kaizen.llm.testing' src/`. `mock_preset(...).supports()` returns the fail-closed all-False matrix, matching Rust's `CapabilityMatrix::for_preset("mock")` fall-through behavior (no explicit `"mock"` row in either SDK).
- **7 capability matrix rows for Python-only OpenAI-compatible aggregators + local-server presets (closes #790).** `together`, `fireworks`, `openrouter`, `deepseek`, `lm_studio`, `llama_cpp`, `docker_model_runner` previously fell through to `ALL_FALSE_CAPABILITIES` because they had no row in `kaizen.llm.capabilities._PRESET_CAPABILITIES`. Calls to `LlmDeployment.together(...).supports()` reported the deployment as uncapable for tools / vision even though Together AI hosts tool-calling and vision-capable models. New rows assert the deployment-surface capability following the existing convention (vision=True means "can serve vision-capable models, per-model gating is caller's responsibility" — same as `ollama` / `groq` / `mistral`). `deepseek` is the conservative outlier (vision=False) because `api.deepseek.com/v1` exposes only deepseek-chat / deepseek-coder at the deployment surface; the DeepSeek-VL family is distributed as separate weights, not served by this preset's endpoint. Per-preset shape tests added to `tests/unit/llm/test_supports_capability_matrix.py`; the `_NON_EMPTY_PRESETS` parametrized sweep extended to cover all 7. The `<provider>_default` convenience presets (#787) carry the PARENT preset literal so capability lookup routes through the parent row automatically — no separate `_default` rows needed.
- **Cross-SDK reconciliation note (#790).** kailash-rs `CapabilityMatrix::for_preset` at `crates/kailash-kaizen/src/llm/deployment/capabilities.rs:120-250` does NOT yet have rows for these 7 presets; it currently falls through to `Self::all_false()`. Per `rules/upstream-issue-hygiene.md`, no auto-cross-file — the kailash-rs side should land equivalent rows in a coordinated cross-SDK release. Until then, Python `supports()` reports the canonical capability matrix; Rust returns all-False for the same preset name.

### Changed

- **`WebFetchTool._extract_text` raises `ImportError` when beautifulsoup4 is missing instead of silently returning raw HTML (closes #814).** Pre-fix: caller passed `extract_text=True`, beautifulsoup4 was missing, the helper logged a `WARNING` and returned the original HTML — invisible to the LLM caller, who treated raw markup as extracted text. Post-fix: the helper raises `ImportError("extract_text=True requires beautifulsoup4 — install via `pip install 'kailash-kaizen[web-search]'` or pass extract_text=False to receive raw HTML.")` and `WebFetchTool.execute(...)` catches it at the call site, returning `NativeToolResult.from_error(...)` so the LLM sees the failure. Module-scope `_BeautifulSoup` sentinel replaces the inline `try/except ImportError` per `rules/dependencies.md` BLOCKED anti-pattern (silent fallback to None). Behavioral regression at `tests/regression/test_issue_814_bs4_loud_failure.py`.
- **`cohere_preset` default endpoint advanced from `https://api.cohere.com/v1` (legacy Generate API) to `https://api.cohere.ai/v2` (modern Chat API) for cross-SDK parity with kailash-rs (closes #794).** kailash-rs `LlmDeployment::cohere()` at `crates/kailash-kaizen/src/llm/deployment/presets.rs:386-396` constructs `Endpoint::new("https://api.cohere.ai/v2")`; Python `cohere_preset` previously diverged at `api.cohere.com/v1`, breaking byte-equivalent cross-SDK code-portability per `rules/cross-sdk-inspection.md` § 3 (EATP D6). The on-wire request envelope at `/v2` is OpenAI-Chat-compatible — Rust delegates v2 through `OpenAiAdapter` (see `presets.rs:378-380`) and Python preserves the same `WireProtocol.CohereGenerate` tag for adapter routing continuity. The new `LlmDeployment.cohere_from_env()` constructor from #791 inherits the new default automatically. Both Cohere endpoints currently coexist (v1 has no announced sunset date), but Cohere's published API reference now directs new integrations at v2.

#### Migration — `cohere_preset` endpoint (#794)

Callers who explicitly relied on the legacy v1 Generate API request envelope (different shape from the v2 Chat envelope) MUST opt in via explicit overrides:

```python
from kaizen.llm.presets import cohere_preset

# Default behavior in 2.18.0+: v2 Chat API on api.cohere.ai
dep = cohere_preset(api_key="...", model="command-r-plus")
# → endpoint: https://api.cohere.ai/v2

# Pre-2.18.0 legacy v1 Generate API on api.cohere.com (callers who built
# request bodies in v1 Generate format MUST migrate via this opt-in):
dep = cohere_preset(
    api_key="...",
    model="command-r-plus",
    base_url="https://api.cohere.com",
    path_prefix="/v1",
)
```

Callers who did not pass explicit `base_url` / `path_prefix` overrides AND whose request handling treats Cohere as OpenAI-compatible (the canonical kaizen pattern) require no migration — the v2 Chat API is OpenAI-compatible by design.

### Removed

- **Vestigial `kaizen.research` integration subsystem moved out by PR #75 — 5 source files + 4 test files + 1 example dir (closes #814 Shard 2).** PR #75 (`801de2bb`, 2026-03-25, "structural split — move ~44K lines of L2 engine code to kaizen-agents") relocated `advanced_patterns.py`, `experimental.py`, and `intelligent_optimizer.py` to `packages/kaizen-agents/src/kaizen_agents/research_patterns/` but left `kaizen.research.__init__.py` re-exporting 7 names (`AdvancedPatternBuilder`, `CompositionalPattern`, `HierarchicalPattern`, `AdaptivePattern`, `MetaLearningPattern`, `ExperimentalFeature`, `IntelligentOptimizer`, `FeatureManager`, `IntegrationWorkflow`, `DocumentationGenerator`, `CompatibilityChecker`, `FeatureOptimizer`) and 5 source files (`feature_manager.py`, `integration_workflow.py`, `documentation_generator.py`, `compatibility_checker.py`, `feature_optimizer.py`) all carrying unguarded `from kaizen_agents.research_patterns.experimental import ExperimentalFeature` — `kaizen-agents` is NOT in `kailash-kaizen/pyproject.toml::dependencies`, so any clean `pip install kailash-kaizen` raised `ModuleNotFoundError` at first `from kaizen.research import …`. The full vestigial cluster has been deleted: 5 src files, 4 unit tests (`test_advanced_patterns.py`, `test_experimental_feature.py`, `test_intelligent_optimizer.py`, `test_compatibility_checker.py`, `test_feature_manager.py`, `test_integration_workflow.py`, `test_documentation_generator.py`, `test_feature_optimizer.py`), 1 integration test (`test_phase2_integration.py`), 1 example directory (`examples/research-integration/`).

#### Migration

Per `rules/zero-tolerance.md` Rule 6a, public-API removal normally requires a `DeprecationWarning` shim covering one minor cycle. **No shim owed**: from PR #75 forward (2026-03-25, ~6 weeks before this release), `from kaizen.research import AdvancedPatternBuilder` raised `ModuleNotFoundError` on first use because the underlying `advanced_patterns.py` no longer existed in this package. The `__all__` re-export resolved the name, but `import` failed. **No consumer could have ever successfully imported these symbols on main since 2026-03-25** (verified: `git log --oneline --since=2026-03-25 packages/kailash-kaizen/src/kaizen/research/{advanced_patterns,experimental,intelligent_optimizer}.py` returns zero results). There is no working public surface to deprecate.

Callers who imported the moved patterns SHOULD migrate to `kaizen_agents.research_patterns.*`:

```python
# Before (raised ModuleNotFoundError since 2026-03-25)
from kaizen.research import AdvancedPatternBuilder, ExperimentalFeature

# After (kaizen-agents installed)
from kaizen_agents.research_patterns.advanced_patterns import AdvancedPatternBuilder
from kaizen_agents.research_patterns.experimental import ExperimentalFeature
```

The `FeatureManager`, `IntegrationWorkflow`, `DocumentationGenerator`, `CompatibilityChecker`, `FeatureOptimizer` classes have no migration path — they were a Phase-2 experimental-feature subsystem orchestrating the now-relocated patterns; with patterns owned by `kaizen-agents`, the subsystem belongs there. Re-implementation in `kaizen-agents` is a future workstream tracked in a follow-up issue.

The remaining `kaizen.research` public surface (`ResearchAdapter`, `ResearchParser`, `ResearchValidator`, `ResearchRegistry`, `SignatureAdapter`, `ResearchPaper`, `ValidationResult`, `RegistryEntry`) is unchanged.

- **(BREAKING) Dead MCP integration surface predating `apps/`→`packages/` move — 12 methods + 1 dead branch removed from `kaizen.core.agents.Agent` (CoreAgent) and `kaizen.core.framework.Kaizen` (closes #822 Shard 2).** Twelve documented public methods imported `..mcp.registry::get_global_registry`, `..mcp::AutoDiscovery`, or `..mcp::MCPConnection` — none of which have ever existed in the kaizen source tree at any commit (`git log --oneline --all -- 'packages/kailash-kaizen/src/kaizen/mcp/registry.py'` returns empty; `kaizen/mcp/__init__.py::__all__` has been `["EnterpriseFeatures", "MCPServerConfig"]` since `b553104c` — the original `apps/`→`packages/` move). The methods were wrapped in `try/except ImportError` (or `try/except Exception:`) blocks that ALWAYS fell through, returning `None`, `[]`, or error dicts. Per `rules/zero-tolerance.md` Rule 2 (no fake integration on documented public API) and `rules/dependencies.md` BLOCKED Anti-Patterns (`# type: ignore[import-not-found]` is BLOCKED for hiding a missing module), deletion is the only valid disposition. Deleted from `kaizen.core.agents.Agent`: `expose_as_mcp_server`, `expose_as_mcp_tool`, `get_mcp_tool_registry`, `execute_mcp_tool`, `connect_to_mcp_servers`, `call_mcp_tool`, `_call_mcp_tool` (private), `_discover_servers` (private). Deleted from `kaizen.core.framework.Kaizen`: `mcp_registry` property, `expose_agent_as_mcp_tool`, `list_mcp_tools`, `discover_mcp_tools`. Net deletion: ~600 LOC from `agents.py` (3456 → 2858) + ~200 LOC from `framework.py` (2418 → 2217). LOC invariant tests at `tests/regression/test_issue_822_loc_invariant.py` guard against silent re-introduction.

#### Migration — #822 Shard 2

**Blast radius is scoped to direct CoreAgent imports.** Per `kaizen/__init__.py:15-20`, the canonical user surface `kaizen.Agent` resolves to `kaizen_agents.Agent` (when `kaizen-agents` is installed — the documented ADR-020 path) which never had these methods. Deletion only affects users who explicitly imported `from kaizen.core.agents import Agent`.

These methods have been broken since the original `apps/`→`packages/` move (`b553104c`). The deletion makes the non-functionality explicit instead of hiding it behind broad exception swallows.

Migration targets:

- For external MCP server / tool exposure → use the `kailash-mcp` package directly.
- For in-process MCP registry → use `kaizen.mcp.catalog_server.MemoryRegistry`
  (`packages/kailash-kaizen/src/kaizen/mcp/catalog_server/registry.py:43`).

Per `rules/zero-tolerance.md` Rule 6a, public-API removal normally requires a `DeprecationWarning` shim covering one minor cycle. **No shim owed**: the methods raised `ModuleNotFoundError` (or returned error sentinels) on every import attempt since `b553104c`. There is no working public surface to deprecate.

### Fixed

- **`kaizen.research.adapter.ResearchAdapter.create_signature_adapter` passed `dict` to `Signature(inputs=, outputs=)` which expects `List[str]` (closes #814 Cluster D, shipped in #818).** The adapter was silently corrupting `Signature._inputs_list` since the file was authored — `_inputs_list` was populated with dict iteration order rather than parameter names. Behavioral regression at `tests/regression/test_issue_814_research_adapter_inputs_list.py` exercises both the param-name path and the empty-params fallback.

- **All 22 `BaseTool.execute(...)` overrides across `kaizen.tools.native.*` now widen `**kwargs`per LSP override conformance (closes #814 Cluster A, shipped in #818).** Pre-fix: 17 of 22 override sites declared narrower signatures than the`BaseTool.execute(self, **kwargs)`base, triggering pyright`reportIncompatibleMethodOverride`. Post-fix: every override declares `\*, <named keyword-only params>, **\_kwargs: Any` — keyword-only marker matches the runtime contract (`ToolRegistry`dispatches via`tool.execute_with_timing(\*\*params)`); underscore prefix documents the parameter as a sink. The LLM tool-calling surface is `BaseTool.get_schema()` and is unaffected by the signature widening.

- **6 Optional/None safety issues in `kaizen.tools.native.*` + `kaizen.research.adapter` (closes #814 Cluster B, shipped in #818).** `notebook_tool.py` validator-narrowing across function boundaries; `parser.py` lazy-import sentinel typing; `task_tool.py` typed `None` adapter guard per `rules/zero-tolerance.md` Rule 3a; `interaction_tool.py` `Union[sync, async]` callback narrowing.

## [2.18.1] — 2026-05-03 — issue #781 hygiene release (T2) + #801 test fix

Patch release cutting PyPI for T2 (kaizen TODO-NNN comment-strip) of the issue #781 cleanup workstream, plus the test-only #801 fix already on main.

### Changed (T2 of #781 — comment-only, packages/kailash-kaizen/src/)

- Stripped 80 `TODO-NNN` markers across 31 files in `research/`, `tools/native/`, `core/`, `core/autonomy/`, `mixins/`, `strategies/`, `execution/`, `session/`, `integrations/`, `docs/` per the ratified disposition catalog (19 Class 1a banner / inline-shipped, 54 Class 1b module docstring provenance, 7 Class 3 mid-comment cross-reference). ADR-013 references in `tools/native/skill_tool.py` + `tools/native/task_tool.py` docstrings preserved per the catalog rule (strip TODO-NNN, keep ADR ref).

### Fixed (recap)

- `tests/unit/llm/openai/test_openai_strict_mode.py` — opt explicitly into `response_format` per #801 (already on main).

### Notes

- Comment-only diff for T2 (zero logic changes). The bump cuts PyPI per `build-repo-release-discipline.md` Rule 1.

## [2.17.1] — 2026-05-02 — CodeQL hygiene cleanup (#789 FIX track)

Patch bump. Closes 4 of 13 open CodeQL findings on the kaizen surface
per the #789 Rule 1b deferral track. The remaining 9 findings are tracked
as DEFER with per-finding runtime-safety proofs in #789's triage comment;
all 9 fall into 4 categorical CodeQL false-positive classes (fingerprint
redaction not recognised, runtime-deferred local imports, `Protocol` stub
bodies, `__del__` interpreter-shutdown defense).

### Fixed

- **`packages/kailash-kaizen/src/kaizen/orchestration/runtime.py`** — removed unused `Union` import (closes CodeQL alert #10874, `py/unused-import`).
- **`packages/kailash-kaizen/src/kaizen/signatures/core.py`** — removed unused `TYPE_CHECKING` import; the file's line-41 comment explicitly opts out of TYPE_CHECKING back-edges, so the import was deliberate non-use (closes CodeQL alert #10865, `py/unused-import`).
- **`packages/kailash-kaizen/src/kaizen/strategies/async_single_shot.py`** — refactored two `runtime = AsyncLocalRuntime() / try / finally: runtime.close()` blocks to `async with AsyncLocalRuntime() as runtime:` form (closes CodeQL alerts #10923 + #10924, `py/should-use-with`). `AsyncLocalRuntime` exposes `__aenter__` / `__aexit__` (`src/kailash/runtime/async_local.py:1580,1590`) so the refactor is drop-in. The new form propagates exceptions cleanly through `__aexit__` on every code path including the inner-loop `break` and outer-`except` propagation; the prior form relied on an explicit synchronous `close()` in `finally` that did not await async cleanup.
- **`packages/kailash-kaizen/tests/unit/strategies/test_async_single_shot_tool_calls.py`** — extended 7 `mock_runtime_instance` setups with `__aenter__` / `__aexit__` `AsyncMock` hooks per `orphan-detection.md` Rule 4 (refactor sweeps tests in same commit). 14/14 tool-call tests pass; 456/456 broader strategies + orchestration + signatures sweep clean.

### Known follow-ups (filed separately, not blocking this release)

- **9 remaining CodeQL findings** tracked as DEFER per `zero-tolerance.md` Rule 1b on issue #789 with per-finding runtime-safety proofs. Each finding falls into a categorical CodeQL static-analyzer limitation (not project-specific debt). Rule 1b conditions met: runtime-safety proof ✓, tracking issue (#789) ✓, release-PR link (this CHANGELOG entry) ✓, release-specialist signoff to be confirmed at the release PR review.

## [2.17.0] — 2026-05-02 — `<provider>_from_env` cross-SDK convenience constructors (#791)

Minor bump. Closes the deferred cross-SDK API-shape parity gap surfaced
by the post-2.16.2 audit: kailash-rs exposes 12 zero-arg
`pub fn <provider>() -> Self` classmethods on `LlmDeployment` (constructing
auth-less deployments with the canonical hosted URL; callers chain
`.with_api_key(...)` to populate credentials before use). Python's parent
`<provider>_preset(api_key, model)` factories require both inputs at
construction per `rules/env-models.md`, so a Rust user porting
`LlmDeployment::openai()` directly hit `TypeError`. This release adds an
explicit `_from_env` constructor variant per provider — eager-validates
against the environment, raises typed `MissingCredential` on missing keys
or models, and routes capability lookups through the parent preset row.

### Added

- **12 `<provider>_from_env` convenience constructors on `LlmDeployment` (closes #791; cross-SDK parity with the 12 zero-arg `pub fn <provider>() -> Self` classmethods on kailash-rs `LlmDeployment` at `crates/kailash-kaizen/src/llm/deployment/presets.rs:153,249,346,386,408,430,458,928,964,1000,1036,1072`).** Each `LlmDeployment.<provider>_from_env()` (and module-level `<provider>_from_env_preset()`) reads `<PROVIDER>_API_KEY` plus `<PROVIDER>_PROD_MODEL` (with legacy fallback to `<PROVIDER>_MODEL`) from the environment and delegates to the existing parent factory. Eager-validates per `rules/env-models.md` — missing env vars raise typed `MissingCredential` with the env var name as `source_hint`. Providers covered: `openai`, `anthropic`, `google`, `cohere`, `mistral`, `perplexity`, `huggingface`, `groq`, `together`, `fireworks`, `openrouter`, `deepseek`. Each returned deployment carries the PARENT `preset_name` literal (e.g. `"openai"`, not `"openai_from_env"`) so `LlmDeployment.supports()` and `for_preset(...)` capability lookups route through the parent row automatically — consistent with the `<provider>_default` precedent (#787).
- **Registry round-trip via `get_preset("<provider>_from_env")()`.** Each `<provider>_from_env` name is registered alongside its classmethod attachment so both surfaces produce structurally identical deployments. Cross-SDK parity sweep enumerates all 12 names against a frozen set in `tests/unit/llm/test_from_env_presets.py::test_from_env_preset_names_complete`; adding a new Rust zero-arg classmethod without wiring its Python `_from_env` peer fails the sweep loudly.

### Implementation notes — design rationale (#791)

Three candidate designs were on the issue body; **Option 3 (`_from_env` variant)** was selected because it is the only design that satisfies `rules/env-models.md` ("ALL API keys MUST come from `.env`") while preserving the eager-validation convention every existing `_preset` factory already enforces. Option 1 (auth-less constructor + `.with_api_key(...)` builder) introduces an `LlmDeployment` whose state is structurally unauthenticated until a builder call — a divergent shape from every other Python preset factory. Option 2 (`<provider>(api_key=os.environ.get(...))`) silently couples the default to an env var; the call site cannot tell whether env was consulted, which is the implicit-magic failure pattern the Python idiom rejects. Option 3 is a separate explicit method per provider; the suffix announces env-driven construction at every call site. Per EATP D6 (`rules/cross-sdk-inspection.md` § 3): semantics match Rust (same endpoint, wire protocol, eventual auth strategy); the idiom-difference is the explicit `_from_env` naming + eager validation at construction time.

A user porting Rust `LlmDeployment::openai()` (zero-arg, auth-less, configured later via `.with_api_key(env::var("OPENAI_API_KEY")?)`) transcribes the contract to Python as a single `LlmDeployment.openai_from_env()` call; the resulting deployment is byte-equivalent to the long-form `openai_preset(api_key, model)` shape with credentials sourced from `OPENAI_API_KEY` + `OPENAI_PROD_MODEL`.

### Tested

- `tests/unit/llm/test_from_env_presets.py` — 36 tests covering: cross-SDK registry parity sweep across all 12 names; per-provider deployment shape (wire / auth / preset_name / endpoint URL byte-pinned to the Rust source-of-truth literal); typed `MissingCredential` raise on missing api_key (parametrized × 12) and on missing model (parametrized × 4 representative providers); `<PROVIDER>_PROD_MODEL` precedence over `<PROVIDER>_MODEL`; legacy `<PROVIDER>_MODEL` fallback when PROD is unset; `GEMINI_PROD_MODEL` legacy fallback for `google_from_env`; classmethod ↔ module-function agreement; registry round-trip via `get_preset`; capability-matrix routing through the parent row. All env-mutating tests serialize through a module-scope `threading.Lock` per `rules/testing.md` § "Serialize Env-Var-Mutating Tests Via Module Lock".

### Known follow-ups (filed separately, not blocking this release)

- **Cohere endpoint URL divergence between Python (`api.cohere.com/v1` + `CohereGenerate` wire) and Rust (`api.cohere.ai/v2`).** Surfaced during the #791 cross-SDK source-of-truth audit; pre-dates #791. The `_from_env` wrapper inherits whichever URL the parent `cohere_preset` exposes, so reconciling the parent URL automatically lifts both surfaces. Tracked separately so the URL+wire decision (v1 Generate vs v2 Chat — different on-wire contracts) gets its own design pass.
- **#788 (`LlmDeployment.mock()` test-utils gating), #789 (CodeQL Rule 1b deferral track), #790 (capability rows for 7 Python-only presets).** Sibling cross-SDK parity / hygiene workstreams from the post-2.16.2 audit.

## [2.16.2] — 2026-05-02 — Default-URL convenience presets (cross-SDK parity)

Patch bump. Closes the cross-SDK API-shape parity gap surfaced by the
`/redteam` audit immediately following 2.16.1: kailash-rs exposes four
zero-arg classmethods on `LlmDeployment` for canonical localhost defaults
(`ollama_default()`, `lm_studio_default()`, `llama_cpp_default()`, zero-arg
`docker_model_runner()`); Python required callers to thread the localhost
URL by hand. Same bug class as 2.16.1's preset-alias fix per
`rules/cross-sdk-inspection.md` § 3a — fix-immediately disposition under
`rules/autonomous-execution.md` Rule 4.

### Added

- **`LlmDeployment.ollama_default(model)` + `ollama_default_preset(model)` (cross-SDK parity with kailash-rs `LlmDeployment::ollama_default()` at `crates/kailash-kaizen/src/llm/deployment/presets.rs:509`).** Convenience constructor equivalent to `ollama_preset("http://localhost:11434/v1", model)`. Deployment carries `preset_name="ollama"` (parent literal — mirrors Rust's `Self::ollama(...)` delegation), so capability-matrix lookup routes through the parent row automatically. The `_default` variant is a constructor convenience, not a distinct preset identity.
- **`LlmDeployment.lm_studio_default(model)` + `lm_studio_default_preset(model)` (cross-SDK parity with `LlmDeployment::lm_studio_default()` at `presets.rs:1138`).** Equivalent to `lm_studio_preset("http://localhost:1234", model)`. Deployment carries `preset_name="lm_studio"`.
- **`LlmDeployment.llama_cpp_default(model)` + `llama_cpp_default_preset(model)` (cross-SDK parity with `LlmDeployment::llama_cpp_default()` at `presets.rs:1170`).** Equivalent to `llama_cpp_preset("http://localhost:8080", model)`. Deployment carries `preset_name="llama_cpp"`.
- **`LlmDeployment.docker_model_runner_default(model)` + `docker_model_runner_default_preset(model)` (cross-SDK parity with the zero-arg form of `LlmDeployment::docker_model_runner()` at `presets.rs:527`).** Constructs `http://localhost:12434/engines/llama.cpp/v1` (Rust's engine-specific default). Deployment carries `preset_name="docker_model_runner"`. Note: the convenience variant uses `path_prefix="/engines/llama.cpp/v1"` to match Rust exactly; the long-form `docker_model_runner_preset` retains its existing default `path_prefix="/engines/v1"` (both are valid Docker Model Runner endpoints).

### Implementation notes

- Python idiom-difference vs Rust per EATP D6: `model` is REQUIRED on every Python `_default_preset(model)` factory per `rules/env-models.md` (which mandates explicit model selection at construction time and never silent defaults). Rust accepts truly zero-arg signatures because Rust's preset surface does not carry the same env-driven model-selection convention. Semantics match — both SDKs route requests to a local server with the canonical default URL — only the construction arity differs.
- All four registry names (`ollama_default`, `lm_studio_default`, `llama_cpp_default`, `docker_model_runner_default`) added to `_PRESETS` so `get_preset(name)(model=...)` round-trips identically with the classmethod surface.

### Tested

- `tests/unit/llm/test_default_url_presets.py` — 28 tests covering: cross-SDK parity registry naming, per-preset deployment shape (wire / auth / preset_name / endpoint URL), byte-equivalence with the long-form factory, classmethod ↔ free-function agreement, empty-model rejection (per `rules/env-models.md`), registry round-trip via `get_preset`, and capability-matrix routing through the parent row (`<provider>_default(model).supports() == <provider>_preset(default_url, model).supports()`).

### Known follow-ups (filed separately)

- **`LlmDeployment.mock()` constructor** — kailash-rs gates this behind `cfg(any(test, feature = "test-utils"))` to prevent "mock shipped to prod" at compile time (`presets.rs:1181`). Python parity requires designing an equivalent gate (test-only module, import-side opt-in, or env-var) and cross-SDK alignment per `rules/cross-sdk-inspection.md` § 2; exceeds shard budget.
- **17 open CodeQL findings on the kaizen surface** — including `#10866 py/clear-text-logging-sensitive-data` on `presets.py:101`, which is a verified false positive: `_fingerprint(name)` calls `fingerprint_secret(raw)` (BLAKE2b non-reversible per #617). Tracking via Rule 1b deferral with per-finding runtime-safety proof.
- **Capability matrix rows for 7 Python-only presets** (`together`, `fireworks`, `openrouter`, `deepseek`, `lm_studio`, `llama_cpp`, `docker_model_runner`) — currently fail-closed via the all-False default; provider-specific research + cross-SDK alignment with kailash-rs `CapabilityMatrix::for_preset` required.

## [2.16.1] — 2026-05-02 — `ollama_default` preset alias parity

Patch bump. Closes the deferred cross-SDK parity gap reviewer flagged during
the 2.16.0 pre-release pass: the `"ollama_default"` preset literal kailash-rs
`CapabilityMatrix::for_preset` accepts as an alias for `"ollama"` was missing
from `kaizen.llm.capabilities._PRESET_CAPABILITIES`, so a Python caller
porting the alias from Rust hit the fail-closed all-False default while the
Rust caller saw the wired row.

### Fixed

- **`for_preset("ollama_default")` now returns the canonical Ollama capability row (cross-SDK parity with kailash-rs `CapabilityMatrix::for_preset` line 212 — `str_eq(preset_name, "ollama") || str_eq(preset_name, "ollama_default")`).** Row is byte-identical to `"ollama"` (`tools=True, vision=True, batch=False, caching=False, audio=False`) per `rules/cross-sdk-inspection.md` § 3a. Test surface: `_NON_EMPTY_PRESETS` parametrized sweep in `tests/unit/llm/test_supports_capability_matrix.py` extended to `"ollama_default"` so a future row drift in either SDK fails loudly.

## [2.16.0] — 2026-05-02 — LlmDeployment.supports() + register_bedrock_region

Cross-SDK parity with kailash-rs PR #725 (`CapabilityMatrix::for_preset`)
and PR #726 (`LlmDeployment::register_bedrock_region`). Both build on the
`preset_name` field landed in 2.15.0 (#761/#762).

### Added

- **`LlmDeployment.supports() -> dict[str, bool]` capability negotiation matrix (closes #763; cross-SDK parity with kailash-rs PR #725).** Returns a five-key dict (`tools`, `vision`, `batch`, `caching`, `audio`) describing what the deployment's wire protocol + endpoint surface CAN carry. Per-preset rows are byte-identical to kailash-rs `CapabilityMatrix::for_preset` per `rules/cross-sdk-inspection.md` § 3a so cross-SDK callers see the same capability bits for the same preset name. Fail-closed default (`rules/security.md` § Fail-Closed): unknown / future preset names AND manual constructions whose `preset_name` is `None` return all-False — adding a new preset constructor without wiring its capability row in `kaizen.llm.capabilities._PRESET_CAPABILITIES` leaves the new deployment marked uncapable until the wiring lands. Returned dicts are independent copies; mutating one cannot corrupt the matrix table or another caller's result. Per-model gating (e.g. `gpt-4o` supports vision but `gpt-3.5-turbo` does not) remains the caller's responsibility — the matrix reports the deployment surface, not per-model capability. New module `kaizen.llm.capabilities` (`for_preset`, `ALL_FALSE_CAPABILITIES`, `CAPABILITY_KEYS`).
- **`LlmDeployment.register_bedrock_region(region)` runtime override (closes #764; cross-SDK parity with kailash-rs PR #726).** Hatch-of-last-resort for operators on a newly-published AWS Bedrock region not yet in `BEDROCK_SUPPORTED_REGIONS` (the canonical fix is a kailash-py release that adds the region to the static set; this hatch covers the days/weeks before that release lands). Process-local registry (NOT shared across replicas — operators behind a load balancer MUST register on every replica at boot). Idempotent (repeated registration is a no-op). Format-validated against `^[a-z]{2,3}-[a-z]+-\d+$` (byte-identical regex to kailash-rs); malformed input raises the new typed `kaizen.llm.auth.aws.InvalidRegionFormat`, distinct from `RegionNotAllowed` (well-formed-but-unknown). Static allowlist short-circuits first; runtime registry is consulted only for regions not in `BEDROCK_SUPPORTED_REGIONS`. Thread-safe — copy-on-write `frozenset` swap under `threading.RLock`; readers are lock-free. Kailash-rs gates this behind `cargo feature = "bedrock-region-override"` (default OFF); Python is single-feature-set, so the function exists unconditionally and the call site IS the explicit opt-in.
- **`InvalidRegionFormat` typed error in `kaizen.llm.auth.aws.__all__`.** Distinct from `RegionNotAllowed` so operators can grep "I typo'd" vs "kailash-py hasn't released this region yet" — two-tier signaling per kailash-rs PR #726.

### Tested

- `tests/unit/llm/test_supports_capability_matrix.py` — 13 tests covering shape (five-key dict, all booleans), provider-distinct matrices for openai / anthropic / ollama / perplexity / bedrock_claude (issue AC: ≥3 presets), fail-closed for unknown preset names AND manual `preset_name=None` constructions, returned-dict independence (mutation cannot corrupt the table), compatible-preset inheritance from openai / anthropic rows (#761/#762), and a parametrized cross-SDK row-completeness sweep across 19 documented presets.
- `tests/unit/llm/auth/test_register_bedrock_region.py` — 13 tests covering static-allowlist short-circuit, registered-region validates, registered-region flows through `bedrock_claude(region, auth)` (issue AC), idempotency, malformed-input format rejection (10 parametrized cases mirroring kailash-rs `invalid_format_rejected`), non-string type-confusion rejection, two-tier `InvalidRegionFormat` vs `RegionNotAllowed` signal isolation, classmethod attachment on `LlmDeployment`, and a 16-thread concurrent registration / read soak test for thread-safety.

## [2.15.0] — 2026-05-02 — LlmDeployment escape-hatch presets + `preset_name` retrofit

Minor bump. Two cross-SDK parity issues close together:

- **(Added)** `LlmDeployment.openai_compatible(base_url, api_key)` (#761) and `LlmDeployment.anthropic_compatible(base_url, api_key)` (#762) escape-hatch presets — wrap an arbitrary HTTPS endpoint with the canonical OpenAI Chat / Anthropic Messages wire protocol. Cross-SDK parity with kailash-rs PR #722 / PR #724.
- **(Added)** `LlmDeployment.preset_name: Optional[str]` field, set by every preset factory (24 existing + 2 new) to the canonical literal. Cross-SDK parity with kailash-rs `LlmDeployment::preset_name()`.

### Added

- **`LlmDeployment.openai_compatible(base_url, api_key)` + `LlmDeployment.anthropic_compatible(base_url, api_key)` escape-hatch presets (closes #761, #762; cross-SDK parity with kailash-rs PR #722 / PR #724).** Wraps an arbitrary HTTPS endpoint with the canonical OpenAI Chat / Anthropic Messages wire protocol — useful for vLLM, llama.cpp servers, LM Studio remotes, LiteLLM proxies, OpenRouter Anthropic mode, internal gateways, and third-party OpenAI/Anthropic-compatible providers. SSRF guard runs on `Endpoint.base_url` automatically via the field validator (`deployment.py:129`, `mode="before"`); loopback (literal-IP) / RFC1918 private / link-local / cloud-metadata / non-HTTP(S) URLs raise `InvalidEndpoint` at construction. Anthropic variant defaults `anthropic-version: 2023-06-01` on `Endpoint.required_headers` (overridable). Both factories are reachable via the registry (`get_preset("openai_compatible")`, `get_preset("anthropic_compatible")`) AND the classmethod surface.
- **`LlmDeployment.preset_name: Optional[str]` field — canonical preset literal exposed on every constructed deployment.** Set by every preset factory (all 24 existing presets retrofitted in the same PR per `rules/zero-tolerance.md` Rule 6 Implement Fully) to the literal registered in `_PRESETS`. The literal — NOT the host or any caller-supplied URL fragment — prevents log-aggregator label cardinality blow-up and credential enumeration via observability per `rules/observability.md` § 8 (schema-revealing field names). Manual constructions leave it `None`; that's structural — `preset_name` is a public-API contract for preset-built deployments only. Cross-SDK parity with kailash-rs `LlmDeployment::preset_name()`. Python idiom is field access (`dep.preset_name`) rather than the Rust method-style (`dep.preset_name()`); the field IS the contract surface, and is consumed by the upcoming `supports()` capability matrix (#763) without per-call introspection.
- **`azure_openai_preset` added to `kaizen.llm.presets.__all__`.** Pre-existing orphan-detection §6 violation surfaced by this change (`__all__`-completeness audit) — the preset was eagerly defined and registered at module load, but absent from `__all__`, so `from kaizen.llm.presets import *` silently dropped it from the public re-export. Same-bug-class fix-immediately per `rules/autonomous-execution.md` MUST Rule 4.

### Tested

- `tests/unit/llm/test_preset_name_and_compatible.py` — 22 tests covering both new compatible presets (shape, classmethod parity, empty-arg rejection, parametrized SSRF guard rejection over loopback / private / link-local / cloud-metadata / non-HTTP(S)), every retrofitted preset's `preset_name` literal, registry membership, and a structural `len(list_presets()) == 26` lock so future regressions surface loudly.

## [2.14.0] — 2026-04-30 — Canonical `kaizen.core` re-exports + MLAwareAgent + env-model resolution

Minor bump. Three load-bearing changes land together:

- **(Fixed, HIGH-2)** Restores the canonical Quick Start from `specs/kaizen-core.md` §3 + `rules/patterns.md` § Kaizen — `from kaizen.core import BaseAgent, Signature, InputField, OutputField` now resolves on every fresh install.
- **(Added)** `kaizen.ml.MLAwareAgent` — first production consumer of the §2.4 ML tool-discovery surface, closing F-D-55 (orphan-detection §1).
- **(Changed)** `CoreAgent` + `GovernedSupervisor` no longer hardcode model strings; both resolve from `KAIZEN_DEFAULT_MODEL` per `rules/env-models.md` (closes F-D-02 + F-D-50).

### Fixed

- **`from kaizen.core import BaseAgent, Signature, InputField, OutputField` raised `ImportError` on every fresh install** — the canonical Quick Start documented in `specs/kaizen-core.md` §3 BaseAgent AND the project rule `rules/patterns.md` § Kaizen Quick Start crashed before any agent code ran. `BaseAgent` lives at `kaizen.core.base_agent`; `Signature` / `InputField` / `OutputField` live in `kaizen.signatures`. Neither was re-exported through `kaizen/core/__init__.py`. Surfaced by /sweep Sweep 6 spec-vs-code drift audit (2026-04-30, HIGH-2). Fix: re-export all four symbols from `kaizen.core` and add them to `__all__`. Also adds `StructuredOutput` to `__all__` (pre-existing orphan-detection §6 violation — eagerly imported but absent). Three Tier-1 regression tests in `packages/kailash-kaizen/tests/regression/test_kaizen_core_quickstart_imports.py` pin the contract structurally (import-resolution, `__all__` membership, canonical-module identity).

### Changed

- **Removed hardcoded model strings from `CoreAgent` + `GovernedSupervisor`; both now read from `KAIZEN_DEFAULT_MODEL` env var (closes F-D-02 + F-D-50).** `CoreAgent` (`kaizen.core.agents.Agent`) and `GovernedSupervisor` (`kaizen_agents.supervisor.GovernedSupervisor`) previously defaulted to `"gpt-3.5-turbo"` and `"claude-sonnet-4-6"` respectively when the caller omitted `model=`. This violated `rules/env-models.md` (model identifiers MUST come from `.env`) and locked every default-API deployment to a single provider. Both constructors now resolve the default from `KAIZEN_DEFAULT_MODEL` and raise `kaizen.errors.EnvModelMissing` (new typed error) with an actionable message when the env var is unset. Existing callers passing explicit `model=<literal>` are unaffected. Tier-1 unit tests in `tests/unit/test_kaizen_default_model_env.py` cover env-set, caller-override, env-unset, and empty-string env paths for both constructors.

### Added

- **`kaizen.errors.EnvModelMissing`**: typed `RuntimeError` subclass for "model identifier required but `.env` did not provide it" failures. Carries `env_var` and `component` attributes so multi-call-site triage can disambiguate which entry point raised. Surfaces as a top-level export from `kaizen.errors`.
- **`.env.example` at repo root**: documents `KAIZEN_DEFAULT_MODEL` plus the matching provider API-key entries per `rules/env-models.md` Model-Key Pairings table.
- **W6-012 — `kaizen.ml.MLAwareAgent` wires the §2.4 ML tool-discovery surface to a production call site (closes F-D-55).** Spec `kaizen-ml-integration.md §2.4.6` defined the canonical `BaseAgent` subclass that derives its tool-set from `km.list_engines()` / `km.engine_info()` per the §E11.3 MUST 1 binding clause; the discovery surface (`kaizen.ml.discover_ml_tools`, `kaizen.ml.engine_info`, `kaizen.ml.MLEngineDescriptor`) shipped in 2.12.x but had ZERO production consumer — classic orphan pattern per `rules/orphan-detection.md §1`. `MLAwareAgent` is now that consumer: at construction time it calls `discover_ml_tools(tenant_id=..., clearance_filter=...)`, converts every `MethodSignature` into a `kaizen.tools.types.ToolDefinition` whose `description` field embeds `kailash_ml.__version__` (so the §2.4.4 version-sync invariant is observable on the LLM-visible tool surface), and exposes the result as the immutable `agent.ml_tools` tuple. New file: `packages/kailash-kaizen/src/kaizen/ml/ml_aware_agent.py` (~250 LOC). New Tier-2 wiring test: `packages/kailash-kaizen/tests/integration/ml/test_kaizen_agent_engine_discovery_wiring.py` (4 tests covering tool-count parity, naming convention, immutability, and tenant-id flow per spec §2.4.7). Symbols test updated to enforce the new `MLAwareAgent` export. Per `rules/agent-reasoning.md` Permitted Deterministic Logic clauses 1+5+6: tool-set construction (mapping `MethodSignature → ToolDefinition`) is structural plumbing — the LLM still owns every routing/classification decision.
- **W6-011 — 28 Tier-1 unit tests for `kaizen.judges` (closes F-D-25).** Added `packages/kailash-kaizen/tests/unit/judges/` with 28 tests across construction, signature/protocol conformance, env-sourced model resolution, position-swap bias mitigation, microdollar budget enforcement, error taxonomy, classification-fingerprint redaction, helper-math (`_clamp_unit`, `_resolve_winner`), and wrapper validation (`FaithfulnessJudge`, `SelfConsistencyJudge`, `RefusalCalibrator`, `LLMDiagnostics`). All tests pass <1s per test (full suite 0.16s). Spec `specs/kaizen-judges.md` § 11 mandated 24 Tier-1 tests at `tests/unit/judges/`; the directory did not exist on main. Sibling Tier-2 wiring tests already lived at `packages/kailash-kaizen/tests/integration/judges/test_judges_wiring.py`. Tests use a deterministic `_ScriptedDelegate` (NOT a Mock — a real Python class satisfying the Delegate duck-type with scripted responses) per `rules/testing.md` "Protocol-Satisfying Deterministic Adapters" exception, exercising the same code paths a production Delegate hits.

## [2.13.1] — 2026-04-25 — Fix clean-venv ImportError (post-2.13.0 hotfix)

Patch — guards a pre-existing unconditional `import kaizen_agents.patterns.patterns` in `kaizen/orchestration/__init__.py` behind a `try/except ImportError`. The `kaizen-agents` package is NOT a declared dependency of `kailash-kaizen`; the proxies that consumed it were defensive `mock.patch` aliases for legacy test code. Without the guard, `from kaizen.orchestration import OrchestrationRuntime` (the new #602 surface in 2.13.0) raised `ModuleNotFoundError` for any clean-venv install of `kailash-kaizen` without `kaizen-agents` present. The proxy aliases are now installed only when `kaizen-agents` is co-installed.

### Fixed

- **`kaizen.orchestration` clean-venv import**: `import kaizen_agents.patterns.patterns` (and 3 sibling proxy imports) now wrapped in `try/except ImportError`. Surface unaffected when both packages co-installed; clean-venv `kailash-kaizen` install no longer breaks at module load.

This is the structural defense for `rules/dependencies.md` § "Declared = Imported — No Silent Missing Dependencies" — a verification gap caught by the post-release clean-venv install check (per `rules/build-repo-release-discipline.md` Rule 2).

## [2.13.0] — 2026-04-25 — PlanSuspension parity (#598) + OrchestrationRuntime parity (#602)

Minor bump — two cross-SDK parity surfaces land together: L3 plan suspension (PACT N3) and strategy-driven multi-agent orchestration runtime (kailash-rs ISS-27).

### Added

- **`kaizen.l3.plan.suspension` module** — five-variant `SuspensionReason` tagged union (frozen dataclasses + `Literal` `kind` discriminator) plus `SuspensionRecord` capturing the resume frontier:
  - `HumanApprovalGateReason(held_node, reason)` — node entered Held gradient zone
  - `CircuitBreakerTrippedReason(breaker_id, triggering_node)` — downstream dependency tripped
  - `BudgetExceededReason(dimension, usage_pct, triggering_node)` — envelope dimension hit threshold (default 90%)
  - `EnvelopeViolationReason(dimension, detail, triggering_node)` — envelope check rejected for non-budget reason (clearance, classification, dimension policy). Python-only today; cross-SDK parity for the 5th variant tracked in a sibling kailash-rs issue.
  - `ExplicitCancellationReason(reason, resume_hint)` — caller-initiated cancel
- **`SuspensionRecord.from_plan(reason, plan)`** — partitions plan node states into `running_nodes` / `ready_nodes` / `pending_nodes` (sorted lex for cross-SDK comparison stability), captures `suspended_at` UTC timestamp, and accepts an opaque `resume_context` payload.
- **`Plan.suspension: Optional[SuspensionRecord]`** — present while the plan is in `SUSPENDED` state, cleared on `resume()`. Round-trips through `Plan.to_dict` / `Plan.from_dict`.
- **`PlanExecutor.suspend(plan, reason=...)` / `AsyncPlanExecutor.suspend(plan, reason=...)`** — optional `reason` kwarg attaches the record at suspend time.
- **`PlanExecutor.suspend_for_circuit_breaker(plan, breaker_id, triggering_node)`** + async variant — convenience wrapper for the `CircuitBreakerTripped` variant; required because the breaker-trip signal originates outside the executor's hot loop.
- **`PlanExecutor.cancel(plan, reason="...", resume_hint="...")`** + async variant — always attaches `ExplicitCancellationReason` BEFORE cascading node-skip transitions, so `running_nodes` / `ready_nodes` / `pending_nodes` capture the pre-cancel snapshot.
- **Wire format helpers** — `suspension_reason_to_dict` / `suspension_reason_from_dict` / `suspension_reason_label` matching Rust serde `#[serde(tag = "kind", rename_all = "snake_case")]`. Cross-SDK forensic correlation works without a third-party tagged-union library.

### Changed

- **`PlanExecutor.resume(plan)` / `AsyncPlanExecutor.resume(plan)`** — now clears `plan.suspension` (PACT N3: the suspension record is consumed by resume; downstream callers that need the record for audit MUST capture it before calling `resume()`).
- **`AsyncPlanExecutor._execute_node` BLOCKED-verdict path** — classifies the suspension cause as `BudgetExceededReason` when the verdict reports a numeric overflow (`requested > available` on a known dimension) and `EnvelopeViolationReason` otherwise (structural rejection: clearance, classification, dimension policy).
- **Both executors' `_determine_terminal_state`** — when the loop ends with one or more HELD nodes, attaches `HumanApprovalGateReason` for the lexicographically-first HELD node. Takes precedence over a previously-recorded `EnvelopeViolation` because the actionable resume path is the human-approval gate.

### Cross-SDK Parity

Wire-format `kind` tags (`human_approval_gate`, `circuit_breaker_tripped`, `budget_exceeded`, `envelope_violation`, `explicit_cancellation`) are reserved across SDKs. Field shapes match `kailash-rs/crates/kailash-kaizen/src/l3/core/plan/types.rs:267-396`. The `envelope_violation` variant is the Python SDK's 5th; a follow-up kailash-rs issue tracks adding it for full parity.

### Tests

- 30 Tier 1 unit tests at `tests/unit/l3/plan/test_suspension.py` — variant construction, frozen-dataclass invariant, label stability, wire-format round-trip, parametrized cross-SDK vector table.
- 12 Tier 2 integration tests at `tests/integration/l3/test_suspension_emission.py` — drives each of the 5 trigger conditions end-to-end through `PlanExecutor` / `AsyncPlanExecutor`, asserts `plan.suspension.reason` is the right variant, asserts `Plan.to_dict` / `from_dict` round-trips the suspension field.

### Added (#602 — OrchestrationRuntime parity)

- **`kaizen.orchestration.OrchestrationRuntime`** — strategy-driven multi-agent coordinator mirroring the Rust `kaizen-agents::orchestration::runtime::OrchestrationRuntime` shape. Builder-style `add_agent` / `strategy` / `coordinator` / `config` setters; async `run(input)` returns `OrchestrationResult` with the same five-field shape as the Rust struct (`agent_results`, `final_output`, `total_iterations`, `total_tokens`, `duration_ms`). Sequential / Parallel / Hierarchical / Pipeline strategies dispatch through a single `agent_invoker` seam — Protocol-conforming agents need only implement `name` + `run_async` to participate.
- New surface: `OrchestrationRuntime`, `OrchestrationStrategy` (frozen dataclass + `sequential() / parallel() / hierarchical(name) / pipeline(steps)` factories), `OrchestrationStrategyKind` StrEnum (lowercase values match Rust serde), `OrchestrationConfig`, `OrchestrationResult`, `OrchestrationError`, `Coordinator` Protocol, `AgentLike` Protocol, `SharedMemoryCoordinator` (default in-memory backed by `SharedMemoryPool`), `PipelineStep`, `PipelineInputSource`.
- Coexists with — does NOT replace — `kaizen_agents.patterns.OrchestrationRuntime` (registry/lifecycle runtime for 10-100 agent fleets) and `kaizen.trust.orchestration.TrustAwareOrchestrationRuntime` (trust-policy enforcement).
- Tier 1: 37 unit tests in `tests/unit/orchestration/test_runtime.py`. Tier 2: 9 integration tests in `tests/integration/orchestration/test_runtime_e2e.py` exercising the runtime end-to-end through the real `SharedMemoryPool` coordinator + `TestCrossSdkShapeParity` locking the result-field set against the Rust struct shape.
- Spec: `specs/kaizen-agents-governance.md` § 19.6.

## [2.12.3] — 2026-04-25 — Security sweep (#614 + #617)

Patch bump — defense-in-depth tightening of tenant-id log hygiene and credential-adjacent fingerprinting. No API changes.

### Fixed

- **Raw `tenant_id` leak in `kaizen.judges.llm_diagnostics`** (#614 item 1+2). Five structured log emissions (`kaizen.llm_diagnostics.init` + 4 call-trace lines) shipped `tenant_id` as a plaintext extras key `"llm_diag_tenant_id"`, bleeding tenant identity into log aggregators whose access surface is strictly wider than the production database (per `rules/observability.md` §8 + `rules/tenant-isolation.md` §4). All 5 sites now route through `_hash_tenant_id(tenant_id)` (shared helper in `kaizen.observability.trace_exporter`, SHA-256 `sha256:<8hex>` — cross-SDK contract with `format_record_id_for_event` per `rules/event-payload-classification.md` §2). Regression test: `tests/unit/test_issue_614_tenant_id_no_raw_leak.py` (11 tests, source + behavioral + symlink-rejection).
- **SHA-256 → BLAKE2b sweep across `kaizen.llm.*`** (#617). Five credential-adjacent call sites migrated from `hashlib.sha256` to `kailash.utils.url_credentials.fingerprint_secret` (BLAKE2b) — closes CodeQL `py/weak-sensitive-data-hashing` consistently across the package and eliminates intent-drift between "BLAKE2b here / SHA-256 there". Sites: `kaizen/llm/auth/bearer.py::ApiKey.__init__`, `kaizen/llm/errors.py::_fingerprint`, `kaizen/llm/presets.py::_fingerprint`, `kaizen/llm/from_env.py::_fingerprint_selector`, `kaizen/llm/auth/gcp.py::CachedToken.__post_init__`. Regression test: `tests/unit/test_issue_617_fingerprint_sweep.py` (15 tests, source + direct-call-per-site + docstring-enhancement).

### Changed

- **`fingerprint_secret` docstring** (#617 MEDIUM-2) — added collision-stability + per-tenant-uniqueness + not-a-secret caveats at `src/kailash/utils/url_credentials.py`. Fingerprints ARE collision-stable across installs (intentional — enables cross-node trace correlation) and MUST NOT be treated as per-tenant-unique identifiers or as secrets.

## [2.12.2] — 2026-04-24 — Cyclic-import refactor (issue #612)

### Changed

- **CodeQL `py/unsafe-cyclic-import` hardening** — extracted `kaizen.signatures._types` to break the `signatures/core.py` ↔ `signatures/enterprise.py` static cycle. `SignatureCompositionProtocol` (new) captures the structural shape `core` needs (`.signatures` attribute) without importing `enterprise`; concrete `SignatureComposition` in `enterprise.py` satisfies the Protocol structurally. The protocol is `@runtime_checkable` for static-analyzer compatibility but the canonical runtime check in `core.py` remains `hasattr(sig, "signatures")` — NOT isinstance against the Protocol. Docstring now pins the discouragement against `isinstance(x, SignatureCompositionProtocol)` in security-sensitive paths per sec-review on PR #616.
- **Regression invariant** — new `tests/regression/test_issue_612_protocol_isinstance_invariant.py` greps production trees for `isinstance(..., *Protocol)` and fails loudly; prevents a future session from swapping a concrete admission check (`isinstance(db, DataFlow)`) to a Protocol-based one.

## [2.12.1] — 2026-04-24 — Security patch (issue #613)

### Changed

- **`kaizen.llm.auth.azure` correlation fingerprint** (`py/weak-sensitive-data-hashing`) — migrated `hashlib.sha256(api_key)` to `kailash.utils.url_credentials.fingerprint_secret(api_key)` (BLAKE2b, 8-char) at two sites (`CachedToken.from_raw` line 84, `AzureEntra.__init__` line 181). The value is NOT used for verification — only grep-able correlation in `__repr__` / log lines — so BLAKE2b is architecturally correct AND satisfies the CodeQL scanner. No migration required; neither fingerprint is persisted. Same-class sibling fix in kailash-mcp 0.2.9 per `rules/agents.md` fix-immediately rule.

## [2.12.0] — 2026-04-23 — ML integration (W32.a, kailash-ml wave)

### Why

Kaizen agent runs and kailash-ml training runs currently flow telemetry to
two separate observability surfaces — the Kaizen `TraceExporter` sink and
the kailash-ml `ExperimentTracker`. Researchers running mixed workflows
("train classical RF + use RAG agent for feature engineering + fine-tune
LLM reranker") see two dashboards instead of one. This release unifies
the surfaces: every Kaizen diagnostic adapter auto-emits to the ambient
`km.track()` run when present, a shared `SQLiteSink` writes agent traces
into the same `~/.kailash_ml/ml.db` store `ExperimentTracker` uses, and
the `CostDelta` wire format is migrated to integer microdollars so
Kaizen / PACT / AutoML cost flows share one numeric contract.

Agent tool-set construction gains a discovery-driven entry point
(`kaizen.ml.discover_ml_tools` + `kaizen.ml.engine_info`) so ML-aware
agents pick up new engines at runtime without hardcoded imports —
spec `kaizen-ml-integration.md §2.4.5` blocks the direct-import pattern
as a `rules/specs-authority.md §5b` drift violation.

### Added

- `kaizen.ml` module — public facade for every Kaizen↔kailash-ml
  integration point (spec `kaizen-ml-integration.md §1.1`):
  - `CostDelta` / `CostDeltaError` — cross-SDK microdollar wire format
    with `to_dict` / `from_dict` / `from_usd` helpers. Rejects NaN, Inf,
    and negative USD at the financial-field gate.
  - `SQLiteSink` / `SQLiteSinkError` / `default_ml_db_path` /
    `VALID_AGENT_RUN_STATUSES` — durable `TraceExporter` sink writing
    `_kml_agent_runs` + `_kml_agent_events` to the canonical
    `~/.kailash_ml/ml.db` store. N4 canonical fingerprint parity with
    kailash-rs v3.17.1+.
  - `resolve_active_tracker` / `emit_metric` / `emit_param` /
    `emit_artifact` / `is_emit_rank_0` — tracker-bridge helpers used
    by every diagnostic adapter's auto-emission path. Rank-0-only
    gate for distributed-training parity with `DLDiagnostics`.
  - `discover_ml_tools` / `engine_info` / `MLEngineDescriptor` /
    `MLRegistryUnavailableError` / `MLToolDiscoveryError` —
    discovery-driven agent tool-set construction routed through
    `km.engine_info()` / `km.list_engines()` (spec §2.4).
- `tracker=Optional[ExperimentRun]` kwarg on every Kaizen diagnostic
  adapter:
  - `AgentDiagnostics` (`kaizen.observability.agent_diagnostics`)
  - `LLMDiagnostics` (`kaizen.judges.llm_diagnostics`)
  - `InterpretabilityDiagnostics` (`kaizen.interpretability.core`)
- Auto-emission from every `record_*` / `track_*` event-capture method
  when an ambient tracker is active — NO opt-in flag (spec §1.1 item 2).
  Metric prefixes locked: `agent.*`, `llm.*`, `interp.*` (spec §3.2).

### Changed

- `AgentDiagnostics.record` / `.record_async` now route captured events
  through `_auto_emit` before returning. Behavior when no tracker is
  present is unchanged.
- `LLMDiagnostics.llm_as_judge` / `.faithfulness` / `.self_consistency`
  / `.refusal_calibrator` emit scalar metrics to the ambient tracker
  whenever one resolves at call time.
- `InterpretabilityDiagnostics.attention_heatmap` / `.logit_lens` /
  `.probe` emit scalar metrics to the ambient tracker whenever one
  resolves at call time.

### Related specs

- `specs/kaizen-ml-integration.md` — authoritative spec.
- `specs/kaizen-observability.md` — TraceExporter + AgentDiagnostics
  core (unchanged in shape).

### Related issues

- Implements W32 sub-shard 32a per
  `workspaces/kailash-ml-audit/todos/active/W32-kaizen-align-pact-integrations.md`.

## [2.11.0] — 2026-04-21 — LLM deployment four-axis abstraction (#498)

### Why

Enterprise LLM deployments cannot be expressed by a single provider-name string. Bedrock-Claude is Anthropic's wire protocol with AWS SigV4 auth against a Bedrock endpoint under a Bedrock-specific model grammar; Vertex-Claude is the same wire protocol with GCP OAuth2 auth against a Vertex endpoint under a Vertex-specific model grammar; Azure-OpenAI is OpenAI's wire protocol with Azure Entra auth and pinned api-version. Every new foundation-model host that lands as a per-provider `kaizen.providers.registry.*` class forks the adapter surface further. This release decomposes the LLM call into four orthogonal axes (wire × auth × endpoint × grammar) so each new host becomes a ≤10-LOC preset instead of a full adapter. Cross-SDK parity with kailash-rs#406 is enforced by a shared parity suite (see `packages/kailash-kaizen/tests/cross_sdk_parity/`).

### Added

- `LlmClient.from_deployment(deployment)` + `LlmClient.from_env()` — four-axis LLM deployment abstraction (ADR-0001).
- `LlmDeployment` frozen Pydantic model composing `WireProtocol` + `Endpoint` + `AuthStrategy` + `ModelGrammar` + defaults.
- **24 presets** (cross-SDK parity with kailash-rs): `openai`, `anthropic`, `google`, `cohere`, `mistral`, `perplexity`, `huggingface`, `ollama`, `docker_model_runner`, `groq`, `together`, `fireworks`, `openrouter`, `deepseek`, `lm_studio`, `llama_cpp`, `bedrock_claude`, `bedrock_llama`, `bedrock_titan`, `bedrock_mistral`, `bedrock_cohere`, `vertex_claude`, `vertex_gemini`, `azure_openai`.
- Auth strategies: `ApiKeyBearer`, `StaticNone`, `AwsBearerToken`, `AwsSigV4`, `GcpOauth`, `AzureEntra` (with three mutually-exclusive variants: api-key, workload-identity, managed-identity).
- `LlmClient.from_env()` three-tier precedence: `KAILASH_LLM_DEPLOYMENT` URI > `KAILASH_LLM_PROVIDER` selector > legacy per-provider keys (OpenAI > Azure > Anthropic > Google). Never falls back to mock.
- URI schemes with strict per-scheme regex validation: `bedrock://{region}/{model}`, `vertex://{project}/{region}/{model}`, `azure://{resource}/{deployment}?api-version=…`, `openai-compat://{host}/{model}`.
- Plugin hook `register_preset(name, factory)` with regex-validated name gate (`^[a-z][a-z0-9_]{0,31}$`) for third-party preset extension.
- `LlmHttpClient` — only HTTP client constructor path for LLM calls; grep-auditable. Emits structured log fields `deployment_preset`, `auth_strategy_kind`, `endpoint_host`, `request_id`, `latency_ms`, `method`, `status_code`, `exception_class`.
- `SafeDnsResolver` — post-connect peer-IP revalidation to close the DNS-rebinding window on every LLM HTTP call.
- `check_url(url)` SSRF guard — structural gate at `Endpoint.from_url` rejecting private IPs, loopback, link-local, and non-HTTPS schemes before the endpoint is finalized.
- `BedrockClaudeGrammar`, `BedrockLlamaGrammar`, `BedrockTitanGrammar`, `BedrockMistralGrammar`, `BedrockCohereGrammar`, `VertexClaudeGrammar`, `VertexGeminiGrammar`, `AzureOpenAIGrammar`.
- Cross-SDK parity suite at `packages/kailash-kaizen/tests/cross_sdk_parity/` — 32 tests asserting preset names, from_env precedence, observability field names, and error taxonomy match Rust byte-for-byte.
- Authoritative spec `specs/kaizen-llm-deployments.md` (238 LOC) and migration guide `docs/migration/llm-deployments-v2.md`.
- Optional extras: `kailash-kaizen[bedrock]` (botocore for SigV4), `[vertex]` (google-auth), `[azure]` (azure-identity for workload/managed variants). API-key-only Azure usage does not require `[azure]`.

### Security

- `ApiKey` newtype wraps `SecretStr`. No `__eq__` / `__hash__`; only `ApiKey.constant_time_eq(other)` via `hmac.compare_digest`. Eliminates timing side-channels in credential comparison.
- Every auth class `__repr__` emits `auth_strategy_kind()` + an 8-hex-char SHA-256 fingerprint — the raw credential never reaches a log line, a repr, or a pickled trace event.
- `AwsSigV4.sign_request` routes through `botocore.auth.SigV4Auth`. Inlined `hmac.new` signing is grep-blocked in `packages/kailash-kaizen/src/kaizen/llm/auth/aws.py`.
- `AwsBearerToken` and `AwsSigV4` enforce a region allowlist at construction time (`BEDROCK_SUPPORTED_REGIONS`). No default `AWS_REGION`.
- `ResolvedModel.with_extra_header` deny-lists 7 forbidden header names (`authorization`, `host`, `cookie`, `x-amz-security-token`, `x-api-key`, `x-goog-api-key`, `anthropic-version`) — prevents callers from overriding the deployment's auth or routing layer.
- `ModelGrammar.resolve` validates `caller_model` against `^[a-zA-Z0-9._:/@-]{1,256}$` before any parsing or URL interpolation.
- `LlmDeployment.mock()` is gated behind `KAILASH_TEST_MODE=1` OR the optional `[test-utils]` extra. `LlmClient.from_env()` NEVER returns a mock deployment — empty env raises `NoKeysConfigured`.
- `GcpOauth` and `AzureEntra` token caches use `asyncio.Lock` for single-flight refresh (no thundering herd on expiry).
- `Endpoint` is a frozen Pydantic model with `extra='forbid'`; side-door writes after construction are rejected at type level.

### Changed

- `kaizen.providers.registry.*` and `kaizen.config.providers.*` now route internally through the preset layer. Public API unchanged; no import breakage.

### Deprecated

- `kaizen.providers.registry.get_provider(name)` — preserved through v2.x; v3.0 earliest removal (≥ 18 months coexistence). Prefer `LlmClient.from_deployment(LlmDeployment.<preset>())`. See `docs/migration/llm-deployments-v2.md` for the full symbol-by-symbol mapping. No deprecation warnings in this release; deprecation-window announcement will precede removal.

### Migration Notes

Zero breaking changes. Legacy code paths continue to work unchanged; every `OpenAIProvider`, `AnthropicProvider`, etc. remains importable and functionally identical. When BOTH the new deployment-tier env vars (URI or selector) AND legacy per-provider keys are set, a single `WARNING llm_client.migration.legacy_and_deployment_both_configured` is emitted and the deployment path wins. `tests/regression/test_legacy_key_does_not_leak_into_deployment_path` enforces no credential cross-contamination.

## [2.10.1] — 2026-04-21 — Security patch on kaizen.observability (PR #587 security-reviewer feedback)

### Security

- **C2 (HIGH) — Tier 2 security coverage added.** Three new assertions in the AgentDiagnostics wiring test exercise classified-PK redaction via `payload_hash`, tenant-id scrub on WARN+ log records, and vendor-SDK brand non-leakage in serialized TraceEvent output. Closes `rules/testing.md` audit-mode MUST "Verify security mitigations have tests" for the spec's § Security Threats subsection.
- **H1 (HIGH) — Tenant-id hashed before INFO / WARN emission.** Raw `tenant_id` on WARN+ log lines bled schema-level identifiers into broader-audience log aggregators (Datadog, Splunk, CloudWatch). All five `TraceExporter` log sites plus the two `AgentDiagnostics` log sites now route `tenant_id` through a new `_hash_tenant_id()` helper producing the cross-SDK `sha256:<8-hex>` prefix form (same contract as `payload_hash` per `rules/event-payload-classification.md` §2). Forensic correlation across Python + Rust streams remains stable; log-aggregator enumeration of tenant IDs is no longer possible. Enforces `rules/observability.md` §8 + `rules/tenant-isolation.md` §4.
- **H2 (HIGH) — `JsonlSink` path resolve + `O_NOFOLLOW` symlink refusal.** The original `JsonlSink.__init__` used `Path(path)` verbatim without resolving traversal or applying `O_NOFOLLOW`, so an attacker-planted symlink at the destination silently redirected the trace stream. Fix: `__init__` resolves via `expanduser().resolve(strict=False)` (normalizes `..` segments); `__call__` opens via `os.open(str(path), O_WRONLY|O_CREAT|O_APPEND|O_NOFOLLOW, 0o600)` on POSIX — symlink at destination raises `OSError` instead of being followed. File-mode bits are `0o600` (owner-only). `mode` validation rejects anything but `"a"` or `"w"`. Docstring documents that callers MUST pre-validate tenant-derived paths against an allowlist. Four regression tests at `tests/regression/test_jsonl_sink_path_safety.py`.
- **M1 (MED) — Async sink tasks retained against GC.** `TraceExporter._run_async` used `loop.create_task(awaitable)` without retaining the Task; GC firing mid-coroutine silently cancelled the sink write and lost the trace event. Fix: new `self._pending_tasks: set[asyncio.Task]` on `__init__`; every scheduled task is added + a done-callback discards on completion (bounded retention = "currently in-flight tasks only"). New `async aclose()` awaits outstanding tasks via `asyncio.gather(return_exceptions=True)`; exceptions are WARN-logged not propagated. Three Tier 1 tests cover retention, exception tolerance, and empty-exporter fast path.

No changes to the public API shape beyond the additive `TraceExporter.aclose()` method; the existing `export()` / `export_async()` / sink signatures are unchanged. No breaking changes for consumers.

## [2.10.0] — 2026-04-21 — AgentDiagnostics + TraceExporter → kaizen.observability (#567 PR#6 of 7)

### Added

- **`kaizen.observability.AgentDiagnostics`** — concrete Kaizen-side adapter satisfying the cross-SDK `kailash.diagnostics.protocols.Diagnostic` Protocol. Context-managed agent-run session that captures `TraceEvent` records and produces a `report()` rollup (counts by `event_type`, total cost in integer microdollars, p50/p95 duration, error rate, errored-export count). Signature-free — pure data aggregator; outside `rules/agent-reasoning.md` scope.
- **`kaizen.observability.TraceExporter`** — single-filter-point sink adapter for `TraceEvent` records. Every event stamped with the cross-SDK-locked SHA-256 fingerprint from `kailash.diagnostics.protocols.compute_trace_event_fingerprint` (byte-identical with kailash-rs#468 / v3.17.1+, commit `e29d0bad`). Sinks: `NoOpSink`, `JsonlSink` (append-only JSONL with thread-safe writes), `CallableSink` (sync or async user-supplied callable). No third-party commercial-SDK imports anywhere in the surface per `rules/independence.md`.
- **`BaseAgent.attach_trace_exporter(exporter)` + `BaseAgent.trace_exporter` property** — production hot-path wiring of the exporter. `AgentLoop.run_sync` and `run_async` emit `agent.run.start` and `agent.run.end` TraceEvents through the attached exporter, threading `parent_event_id` from start → end and stamping `duration_ms` + `status`. Fire-and-forget: exporter failures WARN-log and continue so the agent hot path never breaks because a trace sink failed. Closes `rules/orphan-detection.md` §1 for `kaizen.observability`.
- **`kaizen.observability.AgentDiagnosticsReport`** — frozen dataclass shape returned by `AgentDiagnostics.report_dataclass()`; `.to_dict()` matches the `Diagnostic` Protocol's dict-shape contract.
- **`specs/kaizen-observability.md`** — authoritative spec documenting the cross-SDK fingerprint canonicalization contract, BaseAgent wiring surface, tenant-isolation and classification discipline (payload_hash `"sha256:<8-hex>"` per `rules/event-payload-classification.md` §2), security threats subsection, Tier 1 + Tier 2 testing contract, and MLFP attribution history.
- **`specs/diagnostics-catalog.md`** — catalog indexing every `Diagnostic` adapter (`DLDiagnostics`, `RAGDiagnostics`, `AlignmentDiagnostics`, `InterpretabilityDiagnostics`, `LLMJudge` / `LLMDiagnostics`, `AgentDiagnostics`, `GovernanceEngine` extensions) with its Tier 2 wiring-test file name (grep-able per `rules/facade-manager-detection.md` §2), medical-metaphor regression gate, and the additive extension flow for an 8th diagnostic.

### Tests

- **`packages/kailash-kaizen/tests/integration/observability/test_agent_diagnostics_wiring.py`** — 4 Tier 2 tests exercising a real `BaseAgent` + attached `TraceExporter`; asserts start + end events fire via `AgentLoop`, `run_id` stability, `parent_event_id` threading, fingerprint parity with the canonical helper, cost rollup as int microdollars, and short-circuit behaviour when `attach_trace_exporter(None)`.
- **`packages/kailash-kaizen/tests/unit/observability/test_trace_exporter_fingerprint.py`** — 15 Tier 1 tests covering determinism, hex shape, per-field sensitivity of the 6 mandatory fields, canonicalization form (sort-keys, compact separators, `+00:00`, no `Z`), Enum string serialization, `cost_microdollars` MUST-be-int invariant (rejects float, negative, bool), re-export parity, and bounded-counter contract (no unbounded `_events` buffer).

### Cross-SDK Parity

- **kailash-rs#468** (v3.17.1+, commit `e29d0bad`) — the Rust-side `TraceEvent` + `compute_trace_event_fingerprint` pair; 4 round-trip tests green. The Python-side fingerprint contract in this release is byte-identical with the Rust side.
- **kailash-rs#497** — Rust TraceExporter Kaizen-rs wiring tracker; this Python PR integrates against the byte-identical parity locked in kailash-rs#468.

## [2.9.0] — 2026-04-20 — LLMDiagnostics + JudgeCallable → kaizen.judges + kaizen.evaluation split (#567 PR#5 of 7)

### Added

- **`kaizen.judges.LLMJudge`** — concrete Kaizen-side implementation of the cross-SDK `kailash.diagnostics.protocols.JudgeCallable` Protocol (async `__call__(JudgeInput) -> JudgeResult`). Wraps `kaizen_agents.Delegate` so every LLM call routes through the framework's cost tracker + env-sourced model resolution per `rules/framework-first.md` + `rules/env-models.md`. Raw `openai.chat.completions.create` / `litellm.completion` are BLOCKED (`rules/zero-tolerance.md` Rule 4). Structured `Signature(InputField/OutputField)` drives scoring — no regex on LLM output per `rules/agent-reasoning.md` MUST Rule 3.
- **`kaizen.judges.LLMDiagnostics`** — context-managed Diagnostic session satisfying `kailash.diagnostics.protocols.Diagnostic`. Aggregates `llm_as_judge()` / `faithfulness()` / `self_consistency()` / `refusal_calibrator()` into a single `report()` dict with severity banding, polars DataFrame accessors (`judge_df` / `faithfulness_df`), and plotly dashboard (`plot_output_dashboard()`).
- **`kaizen.judges.FaithfulnessJudge`**, **`kaizen.judges.SelfConsistencyJudge`**, **`kaizen.judges.RefusalCalibrator`** — rubric-bound judge wrappers. `SelfConsistencyJudge` shares one `CostTracker` across N independent scorings and surfaces variance statistics (`SelfConsistencyReport`).
- **`kaizen.judges.JudgeBudgetExhaustedError`** — typed error when the judge's integer-microdollar `budget_cap` is hit mid-evaluation. Position-swap bias mitigation plus budget enforcement are routed through a shared `CostTracker` per `rules/tenant-isolation.md` when a `tenant_id` is present.
- **`kaizen.evaluation.ROUGE`**, **`kaizen.evaluation.BLEU`**, **`kaizen.evaluation.BERTScore`** — pure-algorithmic NLP metrics as a **separate namespace** from `kaizen.judges`. Split intentional: judges carry LLM / cost / budget surface; evaluation is lightweight string math. Each metric raises a loud, actionable `ImportError` naming the `[evaluation]` extra if the underlying library is absent per `rules/dependencies.md` "Optional Extras with Loud Failure".
- **New `[judges]` extra**: `bert-score>=0.3.13` + `rouge-score>=0.1.2` + `sacrebleu>=2.4`. Covers the judge runtime's algorithmic fallbacks.
- **New `[evaluation]` extra**: same deps, narrower scope — for users who only want reference-comparison metrics without the judge / cost / budget surface.
- **`specs/kaizen-judges.md`** and **`specs/kaizen-evaluation.md`** — new spec files documenting Protocol conformance contract, public API, cost-budget discipline, position-swap bias mitigation mechanics, security threats, Tier 1 + Tier 2 testing contract, MLFP attribution history. Both referenced from `specs/_index.md`.

### Security

- **No raw openai / litellm imports in `kaizen.judges` / `kaizen.evaluation`** — every LLM call routes through `kaizen_agents.Delegate`.
- **No regex on LLM output for winner selection** — judge verdicts come from structured `OutputField` parsing via Signature. `_parse_score` regex heuristics from the MLFP donor source were replaced with Signature-based extraction.
- **Budget tracking in integer microdollars** — `CostTracker` is the single source of truth; raw USD floats are not accumulated. Cross-SDK parity with `pact.costs.CostTracker`.
- **Typed error on budget exhaustion** — `JudgeBudgetExhaustedError` is raised loud per `rules/zero-tolerance.md` Rule 3 rather than silently returning partial-result dicts that look successful.

### Attribution

- Portions of `LLMJudge` / `LLMDiagnostics` / `FaithfulnessJudge` / `SelfConsistencyJudge` / `RefusalCalibrator` originated in the MLFP diagnostics helpers (`shared/mlfp06/diagnostics/output.py` + `_judges.py`, Apache 2.0) and were re-authored for the Kailash ecosystem with medical-metaphor cleanup, framework-first routing through Delegate, structured Signature scoring, and `run_id` correlation. MLFP donation history recorded in the root `NOTICE` file per Apache-2.0 §4(d) (blocker B4 shipped in #569).

## [2.8.0] — 2026-04-20 — InterpretabilityDiagnostics adapter for open-weight LLM analysis (#567 PR#4 of 7)

### Added

- **`kaizen.interpretability.InterpretabilityDiagnostics` adapter (#567 PR#4 of 7)**: post-hoc interpretability session for local open-weight language models (Llama / Gemma / Phi / Mistral). Satisfies the cross-SDK `kailash.diagnostics.protocols.Diagnostic` Protocol (`run_id` + `__enter__` + `__exit__` + `report()`), so `isinstance(diag, Diagnostic)` holds at runtime for downstream telemetry pipelines. Four analyses expose attention heatmaps (plotly), logit-lens top-`k` predictions per layer (polars DataFrame), scikit-learn linear probes on last-token hidden states, and optional Gemma-Scope SAE feature activations via `sae-lens`. Every per-analysis buffer uses `deque(maxlen=window)` for bounded-memory discipline; `close()` on context exit releases the model and clears CUDA / MPS caches.
- **New `[interpretability]` extra**: `transformers>=4.40,<5.0` + `sae-lens>=3.0`. Plotting methods raise a loud `ImportError` naming the extra if plotly / matplotlib is absent per `rules/dependencies.md` "Optional Extras with Loud Failure". Base-install construction + API-only refusal paths run without the extra installed.
- **`kaizen.interpretability` facade module**: public surface `from kaizen.interpretability import InterpretabilityDiagnostics`. Tier 2 wiring test asserts facade import per `rules/orphan-detection.md` §1.
- **`specs/kaizen-interpretability.md`** — new spec file documenting Protocol conformance contract, public API, VRAM / memory budget guidance, 6 security threats with mitigations, Tier 1 + Tier 2 testing contract, MLFP attribution history. Referenced from `specs/_index.md`.

### Security

- **Local-files-only default** — `from_pretrained(local_files_only=True)` is the default so a diagnostic call NEVER silently downloads multi-GB weights over the network. Operators pass `allow_download=True` explicitly to opt in.
- **No hardcoded HF token** — auth token read from `HF_TOKEN` / `HUGGINGFACE_TOKEN` env vars via `os.environ.get` only.
- **API-only refusal** — `gpt-*` / `o1-*` / `o3-*` / `o4-*` / `claude-*` / `gemini-*` / `deepseek-*` model prefixes are refused with a canonical `{"mode": "not_applicable"}` payload rather than fabricating interpretability readings. Honest failure per `rules/zero-tolerance.md` Rule 2.
- **No raw prompt text in logs** — structured logs carry `interp_run_id` correlation IDs only; `interp_*`-prefixed fields avoid the LogRecord attribute-collision hazard documented in `rules/observability.md` MUST Rule 9.

## [2.7.5] - 2026-04-19 — LlmClient.embed() + trust migration fix + Python 3.14 compatibility (#462 #499 #477)

### Added

- **`LlmClient.embed()` for OpenAI + Ollama (#462, PR #502)**: `LlmClient.embed(texts, *, model)` exposes a first-class embedding API on the existing `LlmClient` surface. Supports OpenAI (`text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`) and Ollama (`nomic-embed-text` and any Ollama-hosted embedding model). Returns a `List[List[float]]` consistent with OpenAI's embedding response shape.

### Fixed

- **LLM endpoint trust migration identifier validation (#499, PR #504)**: `kaizen.llm.migration` used f-string interpolation for identifier names in log and error message paths. All identifier-containing paths now route through `_validate_identifier()` before use.
- **Python 3.14 (PEP 649 / PEP 749) silently broke every class-based `Signature`.**

- **Python 3.14 (PEP 649 / PEP 749) silently broke every class-based `Signature`.** `SignatureMeta.__new__` read `namespace.get("__annotations__", {})` to discover `InputField` / `OutputField` declarations. On 3.14 the compiler emits `namespace["__annotate__"]` (a lazy callable) instead of populating `__annotations__` directly, so the metaclass saw `{}`, produced signatures with zero fields, and every dependent `BaseAgent` refused to construct. The fix routes the read through the new shared helper `kailash.utils.annotations.get_namespace_annotations`, which evaluates `__annotate__` (preferring `Format.VALUE`, falling back to `Format.FORWARDREF` on unresolved names) on 3.14 and reads the eager dict on 3.13 and earlier.
- **`kaizen.deploy.introspect.build_card_for`** previously called `getattr(signature_cls, "__annotations__", {})`, which can raise `NameError` instead of returning a default on 3.14 if the signature has any string forward reference. Replaced with `kailash.utils.annotations.get_class_annotations(signature_cls)` so every annotation read in the SDK flows through the one-place handler for 3.13/3.14 differences.
- **`type_introspector`, `core/autonomy/state/types`, `memory/enterprise`, `strategies/single_shot`, `strategies/multi_cycle`** all updated to read class annotations through `kailash.utils.annotations.get_class_annotations`, so PEP 649 forward references are surfaced safely instead of crashing the introspection path.

### Pyright

- `signatures/core.py` cleanup (touched while applying the 3.14 fix): `description: str = None` → `Optional[str] = None`; dropped `ClassVar[…]` on the `_signature_*` attributes that get per-instance overrides; declared `_outputs_list: List[Union[str, List[str]]]` at class scope so the multi-output return type holds; added a `TYPE_CHECKING` import for `SignatureComposition` (defined in `signatures.enterprise`); added narrowing casts at dispatchers where `hasattr` already proves the discriminator.

## [2.7.3] - 2026-04-12 — Post-Convergence Security Hardening

### Security

- **SQL injection fix in `security/audit.py` `query_events()`**: the prior implementation built a raw f-string `WHERE` clause from caller-supplied `event_type` and `agent_id` parameters. These arguments could contain SQL metacharacters, enabling injection via crafted event type strings. Fixed to use parameterized queries; identifier segments validated with `re.match` before interpolation.
- **Audit forwarding with `exc_info=True`**: `logger.error()` calls in `core/autonomy/observability/audit.py` and `security/audit.py` now include `exc_info=True`, ensuring stack traces appear in the log pipeline rather than just the message string. Previously, exceptions were swallowed silently on the audit forwarding path.

### Changed

- **Strategy deprecation warnings**: `async_single_shot.py` and `single_shot.py` now emit `DeprecationWarning` when invoked, directing users to `DelegateEngine` as the canonical async strategy. The single-shot strategies remain functional but are officially deprecated.

## [2.3.0] - 2026-03-25

### Changed

- **Structural split**: Moved ~44K lines of Layer 2 (LLM-dependent) engine code to kaizen-agents package
- Moved modules: agents/, orchestration/ (→patterns/), journey/, api/, workflows/, coordination/, integrations/dataflow/, runtime/adapters/, research patterns
- `from kaizen import Agent` now conditionally resolves to async Agent from kaizen-agents (fallback: CoreAgent)
- kaizen-agents added to root `[kaizen]` optional dependency group

### Deprecated

- `kaizen.agent.Agent` (sync wrapper) — use `kaizen_agents.api.agent.Agent` (async) instead

### Removed

- `kaizen/agents/` — moved to kaizen-agents package
- `kaizen/orchestration/` — moved to kaizen-agents as `patterns/`
- `kaizen/journey/` — moved to kaizen-agents
- `kaizen/api/` — moved to kaizen-agents (canonical async Agent API)
- `kaizen/workflows/` — moved to kaizen-agents
- `kaizen/coordination/` — moved to kaizen-agents
- `kaizen/integrations/dataflow/` — moved to kaizen-agents
- `kaizen/runtime/adapters/` — moved to kaizen-agents as `runtime_adapters/`

## [2.2.0] - 2026-03-24

### LLM-First Autonomous Agents

All autonomous agents now default to MCP tool discovery enabled, and the framework enforces LLM-first reasoning as an absolute directive.

### Changed

- **ReActAgent**: `mcp_discovery_enabled` default changed from `False` to `True`
- **CodeGenerationAgent**: Added `mcp_enabled: bool = True` to config
- **RAGResearchAgent**: Added `mcp_enabled: bool = True` to config
- **SelfReflectionAgent**: Added `mcp_enabled: bool = True` to config (now classified as autonomous)
- Agent Classification updated: 4 autonomous agents (was 3), SelfReflectionAgent promoted

### Removed

- **ReActAgent.\_discover_mcp_tools()**: Removed no-op stub method. MCP discovery flows through `BaseAgent.discover_mcp_tools()` (the real async implementation)

### Fixed

- `test_memory_agent`: Fixed mock provider detection in execution test
- `test_http_transport`: Fixed `base_url` fixture scope conflict with pytest-base-url plugin
- `test_agent_execution_patterns_e2e`: Relaxed content assertions for mock provider compatibility

## [2.1.0] - 2026-03-22

### L3 Autonomy Primitives

Five deterministic SDK primitives enabling agents that spawn child agents, allocate constrained budgets, communicate through typed channels, and execute dynamic task graphs under PACT governance.

### Added

- **`kaizen.l3.envelope`** — EnvelopeTracker, EnvelopeSplitter, EnvelopeEnforcer (continuous budget tracking, ratio-based division, non-bypassable enforcement)
- **`kaizen.l3.context`** — ScopedContext, ScopeProjection, DataClassification (hierarchical context with projection-based access control and 5-level clearance)
- **`kaizen.l3.messaging`** — MessageChannel, MessageRouter, DeadLetterStore, 6 typed payloads (bounded async channels with priority ordering and 8-step routing validation)
- **`kaizen.l3.factory`** — AgentFactory, AgentInstanceRegistry, AgentSpec, AgentInstance (runtime agent spawning with 6-state lifecycle machine and cascade termination)
- **`kaizen.l3.plan`** — Plan DAG, PlanValidator, PlanExecutor, PlanModification (DAG task graphs with gradient-driven scheduling and 7 typed mutations)
- **`kaizen.agent_config`** — Optional `envelope` field for PACT constraint governance
- **`kaizen.composition.graph_utils`** — Generic cycle detection and topological ordering
- 868 new tests (581 unit + 240 security + 47 integration/E2E)

## [1.2.1] - 2026-02-22

### V4 Audit Hardening Patch

Post-release reliability hardening from V4 final audit.

### Fixed

- **FallbackRouter Error Truncation**: `get_error_summary()` now truncates error messages to 200 characters, matching `execute()` behavior
- **Hardcoded Model Removal**: `BaseAgent._execute_signature` model fallback uses `os.environ` only, no hardcoded `"gpt-4o"`
- **Timestamping Silent Swallows**: 3 bare `except: pass` blocks in RFC 3161 fallback chain replaced with `logger.debug()` calls
- **Stale Tests**: Updated timestamping tests that expected `NotImplementedError` from now-implemented RFC 3161 authority

### Test Results

- Kaizen: 128 fallback-related tests passed, 60 timestamping tests passed

## [1.2.0] - 2026-02-21

### Quality Milestone Release - V4 Audit Cleared

This release completes 4 rounds of production quality audits (V1-V4) with all Kaizen-specific gaps remediated.

### Added

- **FallbackRouter Safety**: `on_fallback` callback fires before each fallback (raise `FallbackRejectedError` to block), WARNING-level logging on every fallback, model capability validation
- **MCP Session Methods**: `discover_mcp_resources()`, `read_mcp_resource()`, `discover_mcp_prompts()`, `get_mcp_prompt()` wired and functional
- **RFC 3161 Timestamping**: Ed25519 local timestamp authority with clock drift detection and production warnings
- **AgentTeam Deprecation**: Proper `DeprecationWarning` with migration guidance to `OrchestrationRuntime`

### Changed

- **Model Fallback**: `BaseAgent._execute_signature` now reads model from `os.environ` instead of hardcoded `"gpt-4"` fallback
- **Error Truncation**: FallbackRouter truncates error messages to 200 chars to prevent log flooding

### Security

- No hardcoded model names in runtime code (all from environment variables)
- Cryptographically secure nonce generation via `secrets.token_hex(16)`
- V4 audit: 0 CRITICAL findings

### Test Results

- 385 unit tests passed (+1 pre-existing)

## [1.0.0] - 2026-01-25

### Added

#### Phase 7: Production Deployment & GA Release

**TODO-199: Performance Optimization**

- Performance benchmarks suite with 15 comprehensive tests
- Schema caching: ~4.6μs per operation
- Embedding caching: ~17.9μs per operation
- Parallel tool execution: 4.6x speedup over sequential
- Hook parallelization: 8.4x speedup over sequential

**TODO-200: Production Deployment Guides**

- Complete Docker deployment guide with multi-stage builds
- Kubernetes orchestration with health checks and auto-scaling
- Monitoring setup with Prometheus, Grafana, and Loki
- Security hardening documentation

**TODO-201: v1.0 GA Release Validation**

- Comprehensive test suite: 7,400+ unit tests, 226+ integration tests
- Docker image builds and runs successfully
- Fresh pip install verified (kailash-kaizen-1.0.0 installs cleanly)
- Security scan completed (4 documented unfixable vulnerabilities in dependencies)

### Changed

- Version bumped to 1.0.0 (GA release)
- `setup.py` version synchronized with `pyproject.toml` and `__init__.py`
- Semver validation regex updated to accept PEP 440 pre-release format
- HTTP transport tests updated for local development (`allow_insecure=True`)
- Rate limiter fixture converted to `@pytest_asyncio.fixture`

### Fixed

- **OrchestrationRuntime**: Removed incompatible `execution_timeout` parameter from AsyncLocalRuntime initialization
- **Governance datetime comparison**: Fixed offset-naive/aware datetime comparison in `timeout_pending_approvals()`
- **Planning agent response extraction**: Enhanced nested response parsing for Ollama models
- **Rate limiter async fixture**: Corrected decorator for pytest-asyncio compatibility
- **Missing dependencies**: Added motor (MongoDB async driver) and trio (async library)

### Security

- Security scan performed with pip-audit
- 4 remaining unfixable vulnerabilities documented:
  - ecdsa: No fix available (low severity)
  - mcp: Version pinned by kailash (acceptable risk)
  - protobuf: No fix version available (low severity)
  - py: Legacy package (acceptable risk)

---

## [1.0.0b1] - 2026-01-24

### Added

#### Phase 6: Autonomous Execution Layer (922+ tests)

Complete implementation of autonomous agent capabilities enabling Claude Code-level functionality.

**TODO-190: Native Tool System**

- `BaseTool`: Abstract base for all native tools with schema generation
- `NativeToolResult`: Standardized result format with success/error handling
- `KaizenToolRegistry`: Central registry with category-based registration
- `DangerLevel`: 5-level danger classification (SAFE, LOW, MEDIUM, HIGH, CRITICAL)
- 7 file tools: ReadFileTool, WriteFileTool, EditFileTool, GlobTool, GrepTool, ListDirectoryTool, FileExistsTool
- 2 search tools: WebSearchTool, WebFetchTool
- 1 bash tool: BashTool with sandboxing support

**TODO-191: Runtime Abstraction Layer**

- `RuntimeAdapter`: Abstract base class for runtime adapters
- `LocalKaizenAdapter`: Native Kaizen runtime for autonomous execution
- `RuntimeSelector`: Automatic adapter selection based on context
- Plugin system for custom runtime adapters

**TODO-192: LocalKaizenAdapter - TAOD Loop (371 tests)**

- Think → Act → Observe → Decide autonomous execution loop
- Tool call management with approval workflows
- Cycle detection and prevention
- Error recovery with automatic retry
- Execution metrics and performance tracking

**TODO-193: Memory Provider Interface (112 tests)**

- `MemoryProvider`: Abstract interface for memory backends
- `InMemoryProvider`: Default in-memory storage
- `HierarchicalMemory`: Hot/Warm/Cold tier system
- Memory search and retrieval with relevance scoring
- Configurable retention policies

**TODO-194: Multi-LLM Routing (145 tests)**

- `LLMRouter`: Intelligent routing across LLM providers
- `TaskAnalyzer`: Task complexity analysis for routing decisions
- `FallbackRouter`: Automatic failover on provider errors
- `RoutingRule`: Configurable routing policies
- Provider capability detection and matching

**TODO-195: Unified Agent API (217 tests)**

- `Agent`: Single class supporting all capability combinations
- `ExecutionMode`: SINGLE, MULTI, AUTONOMOUS modes
- `MemoryDepth`: STATELESS, SESSION, PERSISTENT, HIERARCHICAL
- `ToolAccess`: NONE, READ_ONLY, READ_WRITE, FULL
- `AgentResult`: Standardized execution results with tool call records
- `CapabilityPresets`: 9 pre-configured capability sets
- Progressive configuration from 2-line quickstart to expert mode

**TODO-196: External Runtime Adapters**

- Claude SDK adapter for Claude Code integration
- OpenAI adapter for GPT-based agents
- Extensible adapter architecture

#### Phase 6.5: Enterprise-App Enablement (530+ tests)

**TODO-202: Specialist System - ADR-013 (107 tests)**

- `SpecialistDefinition`: Type-safe specialist definitions
- `SkillDefinition`: Skill specifications with triggers
- `SpecialistRegistry`: Central registry with discovery
- Built-in specialists: sdk-navigator, pattern-expert, testing-specialist
- Plugin architecture for custom specialists

**TODO-203: Task/Skill Tools (132 tests)**

- `TaskTool`: Spawn subagent specialists
- `SkillTool`: Invoke reusable skills
- Background execution with TaskOutput retrieval
- Shared state management between tools

**TODO-204: Enterprise-App Streaming (291 tests)**

- 10 streaming event types for real-time progress
- `StreamingExecutor`: Async streaming execution
- Event buffering and batching
- WebSocket and SSE transport support

#### Phase 6.6: Claude Code Tool Parity (214 tests)

**TODO-207: Full Tool Parity with Claude Code**

- `TodoWriteTool`: Structured task list management
- `NotebookEditTool`: Jupyter notebook cell editing
- `AskUserQuestionTool`: Bidirectional user communication
- `EnterPlanModeTool`: Plan mode workflow entry
- `ExitPlanModeTool`: Plan mode with approval workflow
- `KillShellTool`: Background process termination
- `TaskOutputTool`: Background task output retrieval
- **19 total native tools** via KaizenToolRegistry
- `PlanModeManager`: Coordinated planning tool state
- `ProcessManager`: Background task tracking

**Documentation**

- Unified Agent API Guide: `docs/developers/05-unified-agent-api-guide.md`
- Claude Code Parity Tools Guide: `docs/developers/08-claude-code-parity-tools-guide.md`

### Changed

- Default version updated to 1.0.0b1 (beta release)
- `Agent` class now primary entry point (replaces `BaseAgent` for new code)
- Tool registry now supports 7 categories: file, bash, search, agent, interaction, planning, process

### Fixed

- Timeout error message format in AskUserQuestionTool (includes "timeout" keyword)
- Metadata passthrough in AskUserQuestionTool when no callback configured

---

## [0.8.0] - 2025-12-16

### Added

#### Enterprise Agent Trust Protocol (EATP)

Complete implementation of cryptographically verifiable trust chains for AI agents.

**Phase 1: Foundation & Single Agent Trust (Weeks 1-4)**

- `TrustLineageChain`: Complete trust chain data structure
- `GenesisRecord`: Cryptographic proof of agent authorization
- `CapabilityAttestation`: What agents are authorized to do
- `DelegationRecord`: Trust transfer between agents
- `ConstraintEnvelope`: Limits on agent behavior
- `AuditAnchor`: Tamper-proof action records
- `TrustOperations`: ESTABLISH, DELEGATE, VERIFY, AUDIT operations
- `PostgresTrustStore`: Persistent trust chain storage
- `OrganizationalAuthorityRegistry`: Authority lifecycle management
- `TrustKeyManager`: Ed25519 key management
- `TrustedAgent`: BaseAgent with automatic trust verification
- `TrustedSupervisorAgent`: Delegation to worker agents

**Phase 2: Multi-Agent Trust (Weeks 5-8)**

- `AgentRegistry`: Central registry for agent discovery
- `AgentHealthMonitor`: Background health monitoring
- `SecureChannel`: End-to-end encrypted messaging
- `MessageVerifier`: Multi-step message verification
- `InMemoryReplayProtection`: Replay attack prevention
- `TrustExecutionContext`: Trust state propagation
- `TrustPolicyEngine`: Policy-based trust evaluation
- `TrustAwareOrchestrationRuntime`: Trust-aware workflow execution

**Phase 3: Enterprise Features (Weeks 9-12)**

- `A2AService`: FastAPI A2A protocol service
- `AgentCardGenerator`: A2A Agent Card with trust extensions
- `JsonRpcHandler`: JSON-RPC 2.0 handler
- `A2AAuthenticator`: JWT-based authentication
- `EnterpriseSystemAgent` (ESA): Proxy for legacy systems
- `DatabaseESA`: SQL database ESA (PostgreSQL, MySQL, SQLite)
- `APIESA`: REST API ESA with OpenAPI support (see details below)
- `ESARegistry`: ESA discovery and management
- `TrustChainCache`: LRU cache with TTL (100x+ speedup)
- `CredentialRotationManager`: Periodic key rotation
- `TrustSecurityValidator`: Input validation and sanitization
- `SecureKeyStorage`: Encrypted key storage (Fernet)
- `TrustRateLimiter`: Per-authority rate limiting
- `SecurityAuditLogger`: Security event logging

**APIESA - REST API Enterprise System Agent (2025-12-15)**

Production-ready ESA for trust-aware REST API integration:

_Core Features:_

- OpenAPI/Swagger spec parsing with automatic capability generation
- HTTP operations: GET, POST, PUT, DELETE, PATCH with full async support
- Rate limiting: per-second, per-minute, per-hour with sliding window
- Request/response audit logging with circular buffer (last 1000 requests)
- Flexible authentication: Bearer tokens, API keys, custom headers

_Trust Integration:_

- Full `EnterpriseSystemAgent` inheritance
- `discover_capabilities()`, `execute_operation()`, `validate_connection()`
- Trust establishment and capability delegation support

_Error Handling:_

- Timeout, request, and connection error handling
- Missing parameter validation
- Rate limit exceeded errors with detailed context

_Documentation:_

- API Reference: `docs/trust/esa/APIESA.md`
- Quick Reference: `docs/trust/esa/APIESA_QUICK_REFERENCE.md`
- Example: `examples/trust/esa_api_example.py`
- 33 unit tests in `tests/unit/trust/esa/test_apiesa.py`

**Performance Targets Met**

- VERIFY QUICK: <1ms (target <5ms)
- VERIFY STANDARD: <5ms (target <50ms)
- VERIFY FULL: <50ms (target <100ms)
- Cache hit: <0.5ms (100x+ speedup)

**Testing**

- 691 total tests (548 unit + 143 integration)
- NO MOCKING policy for Tier 2-3 tests
- Real PostgreSQL infrastructure testing

**Documentation**

- API Reference: `docs/api/trust.md`
- Migration Guide: `docs/guides/eatp-migration-guide.md`
- Security Best Practices: `docs/guides/eatp-security-best-practices.md`
- 10 usage examples in `examples/trust/`

### Changed

- `BaseAgent` now supports optional trust verification via `TrustedAgent` subclass
- Orchestration runtime can be trust-aware via `TrustAwareOrchestrationRuntime`

### Fixed

- SecurityEventType enum now includes rotation events
- APIESA capability name generation fixed for path parameters
- Integration tests now use real implementations (NO MOCKING)

---

## [0.1.x] - Previous Releases

See individual release notes for earlier versions.

---

## Migration

To upgrade from 0.7.x to 0.8.0, see the [EATP Migration Guide](docs/guides/eatp-migration-guide.md).

Key changes:

- New `kaizen.trust` module with all EATP components
- Optional trust verification for existing agents
- Backward compatible - existing `BaseAgent` code works unchanged

## Links

- [Documentation](https://docs.kailash.dev/kaizen)
- [GitHub](https://github.com/terrene-foundation/kailash-py)
- [Issues](https://github.com/terrene-foundation/kailash-py/issues)
