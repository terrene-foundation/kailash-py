# Kailash-Py Current State — LLM Surface

Mapping the existing Python `kaizen` LLM surface to the target four-axis abstraction.

## 1. No `LlmClient` Class Exists Today

Verified via:

```
grep -n "class LlmClient" packages/kailash-kaizen → no matches
grep -rln "import LlmClient\|from.*import LlmClient" packages/kailash-kaizen → no matches
```

**Implication:** The Rust `LlmClient.new() + with_*_key() + from_env()` back-compat surface (Rust ADR D6) does NOT exist in Python. There is NO today-API to preserve byte-for-byte. Python back-compat is against a different surface — the **provider registry** and the **kaizen configuration layer**.

This materially changes the back-compat shape:

- **Rust back-compat** covers `LlmClient` fluent builder.
- **Python back-compat** covers `kaizen.providers.registry.get_provider(name)` + `get_provider_for_model(model)` + `kaizen.config.providers.*` getters + `@db.model`-style agent configuration that consumes these.

Python MUST introduce `LlmClient` / `LlmDeployment` / `AwsBearerToken` as NEW symbols under `kailash.kaizen` (or `kaizen.llm`). The provider registry stays functional; `LlmClient.from_deployment(...)` becomes the additive, preferred path.

## 2. Provider Registry Surface (authoritative today)

`packages/kailash-kaizen/src/kaizen/providers/registry.py`:

- `PROVIDERS: dict[str, type | str]` — 13 entries: `ollama, openai, anthropic, cohere, huggingface, mock, azure, azure_openai, azure_ai_foundry, docker, google, gemini, perplexity, pplx`.
- `_MODEL_PREFIX_MAP` — prefix-dispatch table (declared structural, SPEC-02 §3.1 compliant under `rules/agent-reasoning.md`).
- `get_provider(name)` → concrete provider instance.
- `get_provider_for_model(model)` → prefix-match to provider.
- `get_streaming_provider(...)` → capability-gated.
- `get_available_providers(...)` → introspection for UIs.

Shape is `name → class` (enum-like closed set). The four axes collapse into one identifier — exactly the failure mode Rust #406 is correcting.

## 3. Provider Implementations Touched By Each Shard

```
packages/kailash-kaizen/src/kaizen/providers/
├── base.py                    [S1+S2: ABC + Protocol layer — preserved, augmented]
├── types.py                   [S1+S2: Message, ChatResponse, StreamEvent — preserved]
├── registry.py                [S2/S3/S4a/S5/S6: registry becomes a thin alias layer]
├── llm/
│   ├── openai.py              [S2: migrate to preset-backed + wire_protocol]
│   ├── anthropic.py           [S3: migrate]
│   ├── google.py              [S3: migrate]
│   ├── ollama.py              [S3: migrate]
│   ├── perplexity.py          [S3: migrate]
│   ├── docker.py              [S3: migrate]
│   ├── azure.py               [S6: migrate (merges with unified_azure)]
│   └── mock.py                [S2: migrate; gate mock behind test-utils extra]
├── embedding/
│   ├── cohere.py              [S3: migrate — embedding path]
│   └── huggingface.py         [S3: migrate]
└── document/                  [NOT touched — vision providers are out of four-axis scope]
```

Azure is a special case — lives in BOTH `kaizen/providers/llm/azure.py` (AzureAIFoundryProvider) AND `kaizen/nodes/ai/unified_azure_provider.py` (UnifiedAzureProvider wrapping the 5K-line monolith). S6 MUST converge these onto the `azure_openai` preset and leave `azure_ai_foundry` as a sibling preset if the Foundry API shape differs materially.

## 4. Auth + Env-Key Handling Today

**`packages/kailash-kaizen/src/kaizen/config/providers.py`** — the de-facto "from_env" equivalent:

- `validate_openai_config(api_key=None)` reads `OPENAI_API_KEY` (line 251).
- `validate_anthropic_config(api_key=None)` reads `ANTHROPIC_API_KEY` (line 404).
- `validate_google_config(api_key=None)` reads `GOOGLE_API_KEY` / `GEMINI_API_KEY` (line 488).
- `validate_azure_openai_config()` reads `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION` (lines 140–160, 315–340).
- `autoselect_provider()` (line 567) — picks first configured: OpenAI > (Azure) > Anthropic > Google. **This is the de-facto today-`from_env` behavior** and S7 MUST preserve its semantics as the "legacy per-provider env keys" tier (see Rust spec § 5.3).

**`packages/kailash-kaizen/src/kaizen/nodes/ai/azure_detection.py`** + `azure_backends.py` — Azure-specific env pattern detection (`AZURE_OPENAI_*`, `AZURE_AI_INFERENCE_*`), alias canonicalization (`AZURE_ENDPOINT` ↔ `AZURE_OPENAI_ENDPOINT`). S6 MUST NOT break these detections; they become one branch under the new `azure_openai` preset.

**AWS / Vertex: ZERO presence today.** No `AWS_BEARER_TOKEN_BEDROCK`, `AWS_REGION`, `BEDROCK_MODEL_ID`, `GOOGLE_APPLICATION_CREDENTIALS` handling anywhere in `packages/kailash-kaizen/src`. S4a and S5 are greenfield in Python.

## 5. Test Coverage Map

`packages/kailash-kaizen/tests/`:

- `unit/nodes/ai/test_provider_registry.py` — registry resolution tests (S2/S3 preserve).
- `unit/providers/` and `unit/nodes/ai/test_*_provider.py` — per-provider unit tests (S2/S3 preserve signatures).
- `integration/nodes/ai/test_google_provider_integration.py`, `test_perplexity_provider_integration.py`, `unit/nodes/ai/test_unified_azure_provider.py` — existing integration tests (provider-scoped; must stay green).
- `e2e/providers/test_llm_provider_compatibility_e2e.py` — E2E against real providers.
- `regression/test_issue_255_provider_config_dual_purpose.py` — provider-config regression.

**No Tier 2 test exists for**: `LlmClient`, `LlmDeployment`, `AwsBearerToken`, `AwsSigV4`, `GcpOauth`, `AzureEntra` wiring through a framework facade. Every shard MUST land Tier 2 wiring tests per `rules/orphan-detection.md` + `rules/facade-manager-detection.md`. File naming: `tests/integration/test_<classname>_wiring.py`.

## 6. kaizen.llm Module — NOT Today's LlmClient

`packages/kailash-kaizen/src/kaizen/llm/__init__.py` exports routing + reasoning primitives ONLY (`LLMRouter`, `FallbackRouter`, `TextSimilarityAgent`, `CapabilityMatchAgent`). No `LlmClient`, no `LlmDeployment`. This module is the NATURAL HOME for the new four-axis types:

```
packages/kailash-kaizen/src/kaizen/llm/
├── deployment.py            [NEW: S1+S2 — LlmDeployment, WireProtocol, Endpoint, ResolvedModel, ModelGrammar proto]
├── auth/                    [NEW: S4a/S4b/S5/S6]
│   ├── __init__.py          [AuthStrategy Protocol + Custom]
│   ├── bearer.py            [StaticNone, ApiKeyBearer — S1+S2]
│   ├── aws.py               [AwsBearerToken (S4a), AwsSigV4 + AwsCredentials (S4b)]
│   ├── gcp.py               [GcpOauth (S5)]
│   └── azure.py             [AzureEntra (S6)]
├── client.py                [NEW: S1+S2 — LlmClient.from_deployment / from_env]
├── presets.py               [NEW: S1+S2 onward — each shard adds its preset methods]
├── url_safety.py            [NEW: S1+S2 — SSRF guard + SafeDnsResolver (or S4c)]
├── http_client.py           [NEW: S4c — LlmHttpClient wrapper]
├── grammar/                 [NEW — per-preset ModelGrammar impls]
│   ├── bedrock.py           [S4a]
│   ├── vertex.py            [S5]
│   └── azure_openai.py      [S6]
└── errors.py                [NEW: S1+S2 — LlmClientError / AuthError / EndpointError / ModelGrammarError / LlmError]
```

## 7. Agents / Consumers That Will Adopt the New API

Consumers in kailash-py that select providers today:

- `kaizen/core/agents.py:945` — reads `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` directly for autoselect.
- `kaizen/core/autonomy/observability/manager.py` — references `provider=` in structured logs.
- `kaizen/runtime/adapter.py`, `kaizen/runtime/capabilities.py` — provider capability resolution.
- `kaizen/nodes/ai/llm_agent.py`, `nodes/ai/a2a.py`, `nodes/ai/embedding_generator.py` — consume resolved providers.
- `kaizen/ontology/registry.py` — `provider=` arg on ontology nodes.
- `kaizen/tools/native/search_tools.py` — provider-aware tool.
- `kaizen/cost/tracker.py` — provider-keyed cost metrics.
- `kaizen/agent.py` — top-level agent assembly; will accept `LlmClient` or `LlmDeployment` post-S7.

None of these MUST change for v0 landing; S9 ships a migration guide and (optional) opt-in adapters.

## 8. Pyproject / Dependency Shape

`packages/kailash-kaizen/pyproject.toml` — no `boto3` / `google-auth` / `azure-identity` today. Shards S4a/S5/S6 each add their cloud-auth dep as an optional extra:

```
[project.optional-dependencies]
bedrock  = ["botocore>=1.34"]     # S4a/S4b
vertex   = ["google-auth>=2.0"]   # S5
azure    = ["azure-identity>=1.15"]  # S6
```

With the loud-ImportError fallback pattern per `rules/dependencies.md` § "Exception: Optional Extras with Loud Failure".

## 9. Back-Compat Surface To Preserve (Python-specific)

| Surface                                                   | v0 contract                                                                            |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `kaizen.providers.registry.get_provider(name)`            | unchanged; returns today's provider class instance                                     |
| `kaizen.providers.registry.get_provider_for_model(model)` | unchanged                                                                              |
| `kaizen.providers.registry.PROVIDERS` dict keys           | unchanged (additive-only)                                                              |
| `kaizen.config.providers.validate_*_config()`             | unchanged                                                                              |
| `kaizen.config.providers.autoselect_provider()`           | unchanged semantics; internally MAY route through `LlmClient.from_env()`'s legacy tier |
| Signature-based agent construction                        | unchanged                                                                              |

**New additive surface (S1+S2 onward):** `kailash.kaizen.LlmClient`, `LlmDeployment`, `AwsBearerToken`, `AwsSigV4`, `GcpOauth`, `AzureEntra`, `ApiKeyBearer`, `StaticNone`, `WireProtocol`, `Endpoint`, `ResolvedModel`, `EmbedOptions`, `CompletionRequest`, `StreamingConfig`, `RetryConfig`, `LlmClientError` taxonomy.

## 10. Risks From Current-State Map

- **Provider registry coupling** — 39 files import from `kaizen.providers.*`. Test breakage blast radius is large if S2/S3 refactors the registry instead of shimming it.
- **Azure split brain** — two Azure implementations (`providers/llm/azure.py` + `nodes/ai/unified_azure_provider.py`). S6 MUST pick one as canonical and delegate the other.
- **Prefix-dispatch semantics** — `_MODEL_PREFIX_MAP` is declared as SPEC-02 structural (not agent reasoning) and rule-permitted. Multi-deployment routing in Rust spec § 4.6 needs equivalent Python logic living in `LlmClient._select_deployment(request)` — port the structural-table approach, don't reintroduce.
- **Mock preset gating** — `providers/llm/mock.py` is unconditional today. S2 MUST gate `LlmDeployment.mock()` behind a test/dev flag and ensure `from_env()` never selects it (§ 6.M1).
