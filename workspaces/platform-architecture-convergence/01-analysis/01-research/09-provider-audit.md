# LLM Provider Layer Audit — 2026-04-07

**Audit scope**: Compare the two parallel provider implementations and design the convergence target.

## The Two Stacks

### Stack A: `kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py` (Monolith)

- **Size**: 5,001 lines
- **Provider count**: 14
- **Used by**: BaseAgent
- **Strengths**: Structured outputs, embeddings, sync+async, BYOK multi-tenant, 14 providers including Azure
- **Weaknesses**: Streaming is kwargs-only (not real async streaming), monolithic, broken integration with MCP tools (#339), Gemini structured+tools bug (#340)

### Stack B: `kaizen-agents/src/kaizen_agents/delegate/adapters/` (Clean)

- **Size**: 8 files, much smaller
- **Provider count**: 4 (OpenAI, Anthropic, Google, Ollama)
- **Used by**: Delegate
- **Strengths**: Real async streaming via AsyncGenerator, clean per-provider files, normalized tool format
- **Weaknesses**: No structured outputs, no embeddings, no Azure/Cohere/HuggingFace/Perplexity, no sync variants

## Provider Counts by Stack

| Provider              | Monolith | Clean Adapters |
| --------------------- | -------- | -------------- |
| OpenAI                | ✅       | ✅             |
| Anthropic             | ✅       | ✅             |
| Google Gemini         | ✅       | ✅             |
| Ollama (LLM)          | ✅       | ✅             |
| Ollama (embedding)    | ✅       | ❌             |
| **Azure**             | ✅       | ❌             |
| **Cohere**            | ✅ embed | ❌             |
| **HuggingFace**       | ✅ embed | ❌             |
| **Perplexity**        | ✅       | ❌             |
| **DockerModelRunner** | ✅       | ❌             |
| Mock (testing)        | ✅       | ❌             |
| AzureAIFoundry        | ✅       | ❌             |

**Gap**: Delegate users on Azure cannot use the Delegate at all. Vision agents that depend on monolith's vision providers cannot use Delegate either.

## Provider Class Hierarchy (Monolith)

| Class                       | Purpose                                      |
| --------------------------- | -------------------------------------------- |
| `BaseAIProvider`            | Abstract base with capability detection      |
| `LLMProvider`               | Abstract LLM interface                       |
| `EmbeddingProvider`         | Abstract embedding interface                 |
| `UnifiedAIProvider`         | Combines LLM + embedding                     |
| `OllamaProvider`            | Local Ollama LLM + embedding                 |
| `OpenAIProvider`            | OpenAI (async/sync, reasoning model support) |
| `AnthropicProvider`         | Claude (LLM only)                            |
| `CohereProvider`            | Cohere embeddings only                       |
| `HuggingFaceProvider`       | HuggingFace embeddings only                  |
| `MockProvider`              | Testing/debugging                            |
| `AzureAIFoundryProvider`    | Azure OpenAI, Llama, Mistral                 |
| `DockerModelRunnerProvider` | Local Docker models                          |
| `GoogleGeminiProvider`      | Google Gemini with structured outputs        |
| `PerplexityProvider`        | Perplexity LLM                               |

**Total**: ~93 public/protected methods across the module.

## Feature Matrix

| Feature                              | Monolith                       | Clean Adapters                 |
| ------------------------------------ | ------------------------------ | ------------------------------ |
| **Streaming**                        | kwargs-only (limited)          | Full async generator ✅        |
| **Tool Calling**                     | Sync/async, OpenAI format ✅   | Async only, normalized ✅      |
| **Structured Outputs**               | json_schema, json_object ✅    | **MISSING** ❌                 |
| **Embeddings**                       | 4 providers ✅                 | None ❌                        |
| **Vision**                           | Anthropic, Google, Azure ✅    | Anthropic, Google (limited) ⚠️ |
| **Audio**                            | Google, Azure                  | None ❌                        |
| **Token Tracking**                   | All providers ✅               | All adapters ✅                |
| **Cost Estimation**                  | None                           | None                           |
| **Retry/Backoff**                    | None                           | None                           |
| **Error Sanitization**               | `sanitize_provider_error()` ✅ | Basic try/catch                |
| **BYOK Multi-tenant**                | `BYOKClientCache` ✅           | OpenAI only ⚠️                 |
| **Async Support**                    | Separate async clients ✅      | Async-first ✅                 |
| **Sync API**                         | ✅                             | ❌                             |
| **Reasoning models (o1, o3, gpt-5)** | ✅                             | ✅                             |

## Structured Output Handling (Monolith)

- **OpenAI**: `response_format` parameter with type validation
- **Google Gemini**: Translates OpenAI `json_schema` → `response_mime_type="application/json"` + `response_json_schema`. **Bug #340**: When tools are also present, the request fails on Gemini 2.5
- **Azure**: Vision-aware message conversion
- **Anthropic**: System prompt-based JSON guidance

## Tool Handling (Both Stacks Use OpenAI Format Internally)

**OpenAI normalized format**:

```python
{
    "id": "call_123",
    "type": "function",
    "function": {"name": "read_file", "arguments": '{"path": "/tmp/x"}'}
}
```

- **Monolith**: Forces `tool_choice="required"` when tools present
- **Gemini**: Converts OpenAI tools → `FunctionDeclaration` + `Tool` objects
- **Azure**: Full tool_calls extraction
- **Anthropic adapter**: Tool calls converted from OpenAI format to Anthropic `tool_use` blocks; tool_results wrapped in user message with `tool_result` blocks (NOT `role: "tool"`)

## Provider Config Handling

**Monolith**:

- Per-request API key override (BYOK): `kwargs.get("api_key")`
- Per-request base_url override
- Client caching for BYOK: `BYOKClientCache` with TTL
- **Known issues (all closed)**:
  - #254 Azure json_object requires 'json' in system prompt
  - #255 provider_config dual purpose (Azure api_version misinterpreted)
  - #256 Azure endpoint detection missing cognitiveservices.azure.com pattern
  - #257 AZURE_OPENAI_API_VERSION env var reading

**Adapters**:

- Lazy import per provider
- Resolves API key from kwarg or env var
- No BYOK cache (single-tenant assumption)

## The Capability Gap (Why Both Exist)

| Need                                                 | Monolith Provides | Adapters Provide |
| ---------------------------------------------------- | ----------------- | ---------------- |
| BaseAgent's Signature → JSON schema                  | ✅                | ❌               |
| Real token streaming                                 | ❌                | ✅               |
| RAG embeddings                                       | ✅                | ❌               |
| Backward sync API                                    | ✅                | ❌               |
| 14 providers (Azure, Cohere, HF, Perplexity, Docker) | ✅                | ❌               |
| Clean per-provider files                             | ❌                | ✅               |

**Result**: Two implementations with **incompatible feature sets**. Users have to choose:

- Want structured outputs? Use BaseAgent. Lose streaming, lose Delegate features.
- Want streaming? Use Delegate. Lose structured outputs, lose 10 providers.

This forces users to pick between half a platform.

## Bugs Specific to Each Stack

### Monolith bugs

1. **#340 (Gemini)**: structured outputs + tools both enabled crashes on Gemini 2.5 (`400 INVALID_ARGUMENT`)
2. **Streaming is kwargs-only**: not a real async generator — BaseAgent can't do per-token streaming
3. **No built-in token counter**: users must calculate manually
4. **OpenAI reasoning model parameter filtering**: complex, edge cases possible
5. **Mock provider**: generates synthetic responses (zero-tolerance violation if exposed)

### Adapter bugs

1. **No structured output support**: Delegate agents cannot enforce JSON schema
2. **No embeddings**: Delegate cannot be used for RAG tasks
3. **No Azure**: Enterprise Azure customers can't use Delegate
4. **Ollama tool support unclear**: docs/code don't specify
5. **Default models dated**: claude-3-sonnet-4-6 vs monolith's claude-3-sonnet-20240229 (semantic drift)

## Convergence Target

### New unified provider primitive layer

**Location**: `packages/kailash-kaizen/src/kaizen/providers/`

```
kaizen/providers/
├── __init__.py
├── base.py          # BaseProvider, LLMProvider, EmbeddingProvider (abstract)
├── streaming.py     # StreamingChatAdapter protocol (moved from adapters)
├── registry.py      # Unified provider registry (replaces both)
├── llm/
│   ├── openai.py
│   ├── anthropic.py
│   ├── google.py
│   ├── ollama.py
│   ├── azure.py            # NEW for adapters layer
│   ├── perplexity.py       # NEW for adapters layer
│   └── docker.py           # NEW for adapters layer
├── embedding/
│   ├── openai.py
│   ├── cohere.py
│   ├── huggingface.py
│   └── ollama.py
├── config.py        # ProviderConfig dataclass
└── errors.py        # error_sanitizer, ProviderError
```

### Unified Provider interface

```python
class Provider(ABC):
    """Unified provider for LLM + embedding operations."""

    def is_available(self) -> bool: ...
    def supports_chat(self) -> bool: ...
    def supports_embedding(self) -> bool: ...

    # Sync chat (for BaseAgent backward compat)
    def chat(self, messages: List[Message], **kwargs) -> ChatResponse: ...

    # Async chat
    async def chat_async(self, messages: List[Message], **kwargs) -> ChatResponse: ...

    # Streaming (for Delegate's AgentLoop)
    async def stream_chat(self, messages: List[Message], **kwargs) -> AsyncGenerator[StreamEvent, None]: ...

    # Embeddings (for RAG)
    def embed(self, texts: List[str], **kwargs) -> List[List[float]]: ...
    async def embed_async(self, texts: List[str], **kwargs) -> List[List[float]]: ...
```

### Unified ChatResponse

```python
@dataclass
class ChatResponse:
    id: str
    content: str
    role: str = "assistant"
    model: str = ""
    finish_reason: str = "stop"
    tool_calls: List[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
```

### Capability flags (for both consumers)

```python
class Provider:
    def has_streaming(self) -> bool: ...
    def has_structured_output(self) -> bool: ...
    def has_tools(self) -> bool: ...
    def has_vision(self) -> bool: ...
    def has_audio(self) -> bool: ...
    def has_embeddings(self) -> bool: ...
```

## Migration Path (Zero Breaking Changes)

### Phase 1: Extract base classes

- Move `BaseAIProvider`, `LLMProvider`, `EmbeddingProvider` from `ai_providers.py` to `providers/base.py`
- Move `StreamingChatAdapter` protocol from `adapters/protocol.py` to `providers/streaming.py`
- Update imports in both monolith and adapters
- **Effort**: 2-3 hours

### Phase 2: Consolidate per-provider modules

For each provider (OpenAI, Anthropic, Google, Ollama):

- Merge monolith's `XxxProvider` + adapter's `XxxStreamAdapter` → unified `providers/llm/xxx.py`
- Keep sync methods from monolith (BaseAgent backward compat)
- Add async streaming from adapter (Delegate path)
- Use feature flags to expose both
- **Effort**: 4-6 hours per provider × 4 = 16-24 hours

### Phase 3: Add missing providers to clean structure

- Extract Azure from monolith → `providers/llm/azure.py`
- Extract Perplexity, DockerModelRunner similarly
- **Effort**: 3-4 hours

### Phase 4: Implement streaming everywhere

- Add `stream_chat()` async generator to all 14 providers
- BaseAgent gets optional streaming via `provider.stream_chat()`
- Delegate uses required async path via same method
- **Effort**: 3-4 hours per provider × 14 = 42-56 hours

### Phase 5: Implement structured outputs everywhere

- Move Gemini's `response_format` translation to `providers/config.py`
- Apply pattern to OpenAI, Anthropic, Google, Azure
- Add `response_format` support to adapters
- **Fixes #340 as a side-effect** (single guard at provider layer)
- **Effort**: 2-3 hours

### Phase 6: Unified registry

- Create single `providers/registry.py` serving both consumers
- BaseAgent calls `get_provider(name).chat()` or `get_provider(name).stream_chat()`
- Delegate calls `get_provider(name).stream_chat()` (same method)
- **Effort**: 1-2 hours

### Phase 7: Deprecate old code

- `ai_providers.py` → re-export from `providers/` (backward compat)
- `delegate/adapters/` → re-export from `providers/` (backward compat)
- Add deprecation warnings
- **Effort**: 0.5-1 hour

### Phase 8: Move vision/audio utilities

- Consolidate `vision_utils.py`, `audio_utils.py`
- **Effort**: 1-2 hours

**Total timeline**: 2-3 autonomous execution sessions for full provider unification.

## Tests Affected

- `packages/kailash-kaizen/tests/unit/nodes/ai/test_*_provider.py` (13+ files) — move to `tests/providers/llm/`
- `packages/kaizen-agents/tests/unit/test_adapters.py` — consolidate with provider tests
- New tests:
  - `providers/test_unified_provider_interface.py`
  - `providers/test_feature_flags.py`
  - `providers/test_streaming_vs_sync.py` (verify same results across paths)

## Cross-SDK Alignment

**Rust SDK (kailash-rs)**:

- `kailash-kaizen/src/llm/` has 5 modular files (openai, anthropic, google, azure, mock) + dispatcher (`client.rs`)
- This is **the architecture Python should match**
- Single dispatcher, per-provider modules, no monolith

**Convergence target = Rust's design**. Python's refactor should produce a structure that mirrors the Rust crate layout.

## Why This Unlocks Everything

After provider unification:

- **Delegate gets structured outputs** → kaizen #340 disappears, capability gap closes
- **BaseAgent gets streaming** → can finally do per-token output
- **Both get all 14 providers** → no more "use BaseAgent for Azure"
- **Both share token counting, cost estimation, retry logic, BYOK** → enterprise features apply universally
- **Vision agents work with Delegate** → multi-modal support unified
- **Single source of truth** → adding a new provider = one file, used by both consumers
- **Cross-SDK parity** → matches Rust's `kailash-kaizen/src/llm/` structure
