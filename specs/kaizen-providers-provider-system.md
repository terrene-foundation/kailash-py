# Kailash Kaizen -- Domain Specification — Provider System

Version: 2.13.1
Package: `kailash-kaizen`

Parent domain: Kailash Kaizen AI agent framework. This file covers the provider system — the ABC + Protocol provider hierarchy, capability enum, provider registry, error hierarchy, unified types, and `governance_required` posture coverage. Split from `kaizen-providers.md` (specs-authority.md Rule 8 — the original file exceeded the 300-line split threshold). Sibling sub-files covering the rest of the parent domain: `kaizen-providers.md` (index), `kaizen-providers-provider-system.md`, `kaizen-providers-execution-strategies.md`, `kaizen-providers-tool-integration.md`, `kaizen-providers-memory-system.md`, `kaizen-providers-error-handling.md`, `kaizen-providers-streaming.md`. See also `kaizen-core.md`, `kaizen-signatures.md`, and `kaizen-advanced.md`.

---

## 8. Provider System

### 8.1 Provider Hierarchy

**Legacy ABC layer (backward compatibility):**

```
BaseAIProvider (ABC)
  LLMProvider(BaseAIProvider)       -- chat(), chat_async()
  EmbeddingProvider(BaseAIProvider) -- embed()
  UnifiedAIProvider(LLMProvider, EmbeddingProvider)
```

**SPEC-02 Protocol layer (structural typing):**

```
BaseProvider (Protocol)             -- name, capabilities, supports()
AsyncLLMProvider (Protocol)         -- chat_async()
StreamingProvider (Protocol)        -- stream_chat() -> AsyncGenerator[StreamEvent]
ToolCallingProvider (Protocol)      -- chat_with_tools()
StructuredOutputProvider (Protocol) -- chat_structured()
```

Protocols are `@runtime_checkable`. Concrete providers inherit from the ABC layer and satisfy the Protocol layer structurally.

### 8.2 ProviderCapability Enum

```python
class ProviderCapability(Enum):
    CHAT_SYNC = "chat_sync"
    CHAT_ASYNC = "chat_async"
    CHAT_STREAM = "chat_stream"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    EMBEDDINGS = "embeddings"
    VISION = "vision"
    AUDIO = "audio"
    REASONING_MODELS = "reasoning_models"
    BYOK = "byok"
```

### 8.3 Provider Registry

`#1720 Wave-2` retired the seven legacy chat providers (openai / anthropic / google / ollama / docker / perplexity / mock) onto the four-axis `kaizen.llm.LlmClient` path; `#1820` retired the embedding-legacy providers (cohere / huggingface) and the unified-azure stack (`azure` / `azure_openai`, the `"_unified_azure"` lazy string) the same way. `AzureAIFoundryProvider` is the ONE provider that remains registered — `kaizen.llm.deployment_resolver.resolve_deployment_for` declines to map `azure_ai_foundry` (no confirmed four-axis wire), so callers fall back to this registry:

```python
PROVIDERS: dict[str, type] = {
    "azure_ai_foundry": AzureAIFoundryProvider,
}
```

`kaizen.providers.provider_names.PROVIDER_NAMES` is a SUPERSET of `PROVIDERS.keys()` — it carries every observability-classification family (including the retired names, still labelled by `track_llm_usage` when reached through the four-axis path) for `kaizen.production.metrics` label-bounding. `registry.py` asserts `set(PROVIDERS.keys()) <= PROVIDER_NAMES` at import as a drift tripwire.

#### get_provider(provider_name, provider_type=None, \*, ungoverned=False)

Resolves a provider by name (case-insensitive). Optional `provider_type` filter: `"chat"` or `"embeddings"`.

`ungoverned` (`#1803`) is forwarded to the constructed instance (`provider_class(ungoverned=ungoverned)`) — it does NOT itself evaluate the `governance_required` posture. A caller that will invoke an egress method (e.g. `.chat()`) on the returned instance MUST pass the SAME `ungoverned` value its own gate already enforced, so the caller's outer gate and the instance's inner gate agree instead of double-refusing. See § 8.6 Governance.

Raises `ValueError` for unknown providers or capability mismatches.

#### get_provider_for_model(model: str) -> BaseProvider

RETIRED (`#1720` Wave-2): model-id → provider dispatch always raises `UnknownProviderError`. Model-id → wire dispatch now lives in `kaizen.llm.deployment_resolver.resolve_deployment_for` (four-axis `LlmClient`); the prefix table below moved to `kaizen.production.metrics` label-bounding only (`kaizen.providers.provider_names.MODEL_PREFIX_MAP`), NOT dispatch:

| Prefix                                                    | Family     |
| --------------------------------------------------------- | ---------- |
| `gpt-`, `o1-`, `o3-`, `o4-`, `ft:gpt`                     | openai     |
| `claude-`                                                 | anthropic  |
| `gemini-`                                                 | google     |
| `llama`, `mistral`, `mixtral`, `qwen`, `phi-`, `deepseek` | ollama     |
| `ai/`                                                     | docker     |
| `sonar`, `sonar-`                                         | perplexity |
| `mock-`, `mock`                                           | mock       |

#### get_streaming_provider(name_or_model: str) -> StreamingProvider

Resolves to a provider satisfying the `StreamingProvider` protocol via `get_provider` (registry NAME dispatch only — model-id dispatch is retired, see above). Raises `CapabilityNotSupportedError` if the provider does not support streaming.

### 8.4 Provider Error Hierarchy

```
ProviderError (base)
  UnknownProviderError          -- Provider name not in registry
  ProviderUnavailableError      -- Missing API key, uninstalled SDK, unreachable service
  CapabilityNotSupportedError   -- Requested capability not supported
  AuthenticationError           -- API key/credential validation failure
  RateLimitError                -- Rate limit / quota exceeded
  ModelNotFoundError            -- Model not available on provider
```

All errors carry `provider_name` and optional `original_error` attributes.

### 8.5 Unified Types

#### Message

```python
MessageContent = Union[str, List[Dict[str, Any]]]
Message = Dict[str, Union[str, MessageContent]]
```

#### ChatResponse

```python
@dataclass
class ChatResponse:
    id: str = ""
    content: str | None = ""
    role: str = "assistant"
    model: str = ""
    created: Any = None
    tool_calls: list[Any] = field(default_factory=list)
    finish_reason: str | None = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### TokenUsage

```python
@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
```

#### ToolCall

```python
@dataclass
class ToolCall:
    id: str
    type: str = "function"
    function_name: str = ""
    function_arguments: str = "{}"
```

#### StreamEvent

```python
@dataclass
class StreamEvent:
    # Token-by-token streaming event from LLM provider
```

### 8.6 Governance — `governance_required` Posture Coverage

`kailash.trust.pact.governance_posture` (`#1779`) exposes a process/env `governance_required` posture; when ACTIVE, a bare un-governed construction/egress that WOULD make real LLM/vision egress is refused (`kailash.trust.pact.UngovernedEgressRefused`) unless the caller passes `ungoverned=True` or the posture is OFF (default). `#1779` gated the four-axis `LlmClient` + `Agent`/`BaseAgent`/`LLMAgentNode`/`EmbeddingGeneratorNode` egress; `#1803` extends coverage to the rest of the `kaizen.providers.*` layer:

| Surface                                                          | Gate location                                                                    | `ungoverned` threading                                                             |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `kaizen.providers.llm.azure.AzureAIFoundryProvider`                 | each real-egress method (`chat` / `chat_async` / `stream_chat` / `embed` / `embed_async`) — NOT `__init__` or `is_available`/`get_capabilities`  | `AzureAIFoundryProvider(ungoverned=...)`; `registry.get_provider(..., ungoverned=...)` forwards to the constructed instance |
| `kaizen.providers.document.landing_ai_provider.LandingAIProvider`   | top of `extract()`, before file validation                                          | `LandingAIProvider(ungoverned=...)`                                                    |
| `kaizen.providers.document.openai_vision_provider.OpenAIVisionProvider` | top of `extract()`, before file validation                                     | `OpenAIVisionProvider(ungoverned=...)`                                                 |
| `kaizen.providers.document.ollama_vision_provider.OllamaVisionProvider` | top of `extract()`, before file validation (locality is NOT an exemption)      | `OllamaVisionProvider(ungoverned=...)`                                                 |
| `kaizen.providers.document.provider_manager.ProviderManager`        | forwards to every sub-provider's constructor                                        | `ProviderManager(ungoverned=...)`                                                      |
| `kaizen.providers.multi_modal_adapter.OpenAIMultiModalAdapter`      | top of `process_multi_modal()` (covers vision / Whisper / text branches)            | `OpenAIMultiModalAdapter(ungoverned=...)`                                              |
| `kaizen.providers.multi_modal_adapter.OllamaMultiModalAdapter`      | transitively, via `OllamaProvider.__init__` (through `_get_ollama_vision_provider`)  | `OllamaMultiModalAdapter(ungoverned=...)` → `OllamaVisionConfig(ungoverned=...)`        |
| `kaizen.providers.ollama_provider.OllamaProvider` (= `kaizen.providers.LegacyOllamaProvider`) | `__init__`, before `_check_ollama_available()`'s unconditional real `ollama.list()` | `OllamaConfig(ungoverned=...)` (inherited by `OllamaVisionConfig`) |
| `kaizen.providers.ollama_vision_provider.OllamaVisionProvider` (top-level) | covered through base-class (`OllamaProvider`) construction — no separate gate | same as above (shared `OllamaConfig`/`OllamaVisionConfig`)                             |
| `kaizen.nodes.ai.semantic_memory.SimpleEmbeddingProvider`           | top of `embed_text()`, before the cache check or the aiohttp session (security-review follow-up — real aiohttp embedding-host egress the initial parity sweep's regex couldn't see) | `SimpleEmbeddingProvider(ungoverned=...)`; threaded top-down from every consumer — `SemanticMemoryStoreNode` / `SemanticMemorySearchNode` / `SemanticAgentMatchingNode` (`kaizen.nodes.ai.semantic_memory`) and `SemanticHybridSearchNode` / `AdaptiveSearchNode` (`kaizen.nodes.ai.hybrid_search`) each construct an INSTANCE-level provider (not class-cached) |

No mock concept exists for any provider/backend surface above (`is_mock=False` always); the only exemptions are `ungoverned=True` and the OFF posture. Locality (a local `base_url`, e.g. Ollama's default `http://localhost:11434`) is explicitly NOT a governance exemption — parity with the four-axis `LlmClient` path, which gates Ollama deployments too.

**Retired, not gated (nothing to gate):** `kaizen.nodes.ai.azure_backends` / `unified_azure_provider` do not exist — `#1820` retired the legacy unified-azure stack in favour of the four-axis path (`kaizen.llm.azure_env` module docstring). **Orphaned, not gated (no live construction):** `kaizen.nodes.ai.client_cache.BYOKClientCache` has zero production call sites — a generic bounded cache over an opaque caller-supplied `factory`; if a future PR wires a real provider-client factory through it, that factory's construction site is the gate point, not the cache.

A mechanical parity sweep (`test_no_ungated_egress_construction_site_outside_known_files` in `tests/unit/llm/test_governance_required_gate.py`) greps `kaizen/` for `openai`/`anthropic`/`genai`/`httpx`/`ollama`/Azure client-construction patterns and asserts each containing file also calls `enforce_governance_posture` — or is explicitly allowlisted with a documented reason (the two retired/orphaned surfaces above, plus `kaizen/llm/**` itself, gated at its own `LlmClient` chokepoint rather than per internal call site).

