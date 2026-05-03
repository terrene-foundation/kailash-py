# ADR-005: Provider Capability Protocol Split

**Status**: ACCEPTED (2026-04-07)
**Scope**: Kaizen providers (kailash-kaizen, kailash-rs LLM layer)
**Deciders**: Platform Architecture Convergence workspace

## Context

Python has **two parallel LLM provider stacks**:

|                    | Monolith                                                                  | Clean Adapters                                                |
| ------------------ | ------------------------------------------------------------------------- | ------------------------------------------------------------- |
| Path               | `packages/kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py`             | `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/` |
| Lines              | **5,001 LOC in ONE file**                                                 | ~8 clean per-provider files                                   |
| Providers          | 14 (incl. Azure, Cohere, HuggingFace, Perplexity, Docker, AzureAIFoundry) | 4 (OpenAI, Anthropic, Google, Ollama)                         |
| Used by            | BaseAgent                                                                 | Delegate                                                      |
| Streaming          | kwargs-only (limited)                                                     | Real `AsyncGenerator`                                         |
| Structured outputs | ✅ json_schema, json_object                                               | ❌ missing                                                    |
| Embeddings         | ✅ 4 providers                                                            | ❌ none                                                       |
| Sync API           | ✅                                                                        | ❌ async-only                                                 |
| BYOK multi-tenant  | ✅ `BYOKClientCache`                                                      | ⚠ OpenAI only                                                 |

**Each stack has features the other lacks.** Users are forced to pick half a platform.

Rust is cleaner: `kailash-kaizen/src/llm/` has 7 files with an `LlmClient` dispatcher and per-provider adapters. But the architecture uses **stateless unit structs** without a trait, and every adapter has every method even if the provider doesn't support it.

### Naive solution and its problem

The obvious convergence target is a single `Provider` interface:

```python
class Provider(ABC):
    def chat(self, messages, **kwargs) -> ChatResponse: ...
    async def chat_async(self, messages, **kwargs) -> ChatResponse: ...
    async def stream_chat(self, messages, **kwargs) -> AsyncGenerator[StreamEvent]: ...
    def embed(self, texts, **kwargs) -> list[list[float]]: ...
    async def embed_async(self, texts, **kwargs) -> list[list[float]]: ...
```

**Problem**: This forces every provider to implement every method. But:

- **Cohere** does embeddings only — has no chat API
- **HuggingFace (TEI)** does embeddings only — has no chat API
- **Anthropic** has no embedding API
- **DockerModelRunner** may have no streaming
- **Mock** has no real streaming protocol

Either the interface forces stub methods that raise `NotImplementedError` (**Zero-Tolerance Rule 2 violation**) or the interface is fat and untyped.

The red team flagged this: "Provider unification forces 'every provider implements every method' which doesn't work."

## Decision

**Replace the single `Provider` interface with a set of narrow capability protocols (one per feature) that providers implement only if they support the capability. A provider declares its capabilities via a capability flag API. The registry returns typed protocols.**

### Protocol hierarchy (Python)

```python
# packages/kailash-kaizen/src/kaizen/providers/base.py

from typing import Protocol, runtime_checkable, AsyncGenerator, Any
from dataclasses import dataclass

# ─── Base capability-agnostic protocol ────────────────────────────────

@runtime_checkable
class BaseProvider(Protocol):
    """All providers implement this minimal contract."""

    @property
    def name(self) -> str:
        """Provider name: 'openai', 'anthropic', 'google', etc."""
        ...

    @property
    def capabilities(self) -> set[ProviderCapability]:
        """Set of capability flags this provider supports."""
        ...

    def supports(self, capability: ProviderCapability) -> bool:
        """Check if provider supports a capability."""
        return capability in self.capabilities


class ProviderCapability(Enum):
    """Capability flags for provider feature discovery."""
    CHAT_SYNC = "chat_sync"
    CHAT_ASYNC = "chat_async"
    CHAT_STREAM = "chat_stream"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    EMBEDDINGS = "embeddings"
    VISION = "vision"
    AUDIO = "audio"
    REASONING_MODELS = "reasoning_models"  # o1, o3, o4, etc.
    BYOK = "byok"  # per-request API key override


# ─── Feature-specific protocols ───────────────────────────────────────

@runtime_checkable
class LLMProvider(BaseProvider, Protocol):
    """Providers that support LLM chat (sync)."""

    def chat(self, messages: list[Message], **kwargs) -> ChatResponse:
        """Synchronous chat completion."""
        ...


@runtime_checkable
class AsyncLLMProvider(BaseProvider, Protocol):
    """Providers that support async LLM chat."""

    async def chat_async(self, messages: list[Message], **kwargs) -> ChatResponse:
        """Asynchronous chat completion."""
        ...


@runtime_checkable
class StreamingProvider(BaseProvider, Protocol):
    """Providers that support token streaming."""

    async def stream_chat(
        self,
        messages: list[Message],
        **kwargs
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream tokens as they arrive from the provider."""
        ...


@runtime_checkable
class EmbeddingProvider(BaseProvider, Protocol):
    """Providers that support embeddings."""

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Generate embeddings (sync)."""
        ...

    async def embed_async(self, texts: list[str], **kwargs) -> list[list[float]]:
        """Generate embeddings (async)."""
        ...


@runtime_checkable
class VisionProvider(BaseProvider, Protocol):
    """Providers that support vision inputs."""

    def supports_image_format(self, mime_type: str) -> bool:
        ...

    # Vision works through chat() with image content blocks —
    # this protocol just declares capability.


@runtime_checkable
class AudioProvider(BaseProvider, Protocol):
    """Providers that support audio inputs (transcription or generation)."""

    def supports_audio_format(self, mime_type: str) -> bool:
        ...


@runtime_checkable
class ToolCallingProvider(BaseProvider, Protocol):
    """Providers that support native function calling."""

    def format_tools_for_provider(
        self,
        tools: list[ToolDef]
    ) -> list[dict[str, Any]]:
        """Convert unified ToolDef into provider-specific tool format."""
        ...


@runtime_checkable
class StructuredOutputProvider(BaseProvider, Protocol):
    """Providers that support JSON schema / structured outputs."""

    def format_response_schema(
        self,
        schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert JSON schema into provider-specific response_format."""
        ...
```

### Unified data types

```python
@dataclass
class Message:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[ContentBlock]  # str for plain text, list for multimodal
    name: Optional[str] = None           # for tool messages
    tool_call_id: Optional[str] = None   # for tool messages
    tool_calls: Optional[list[ToolCall]] = None  # for assistant messages


@dataclass
class ContentBlock:
    type: Literal["text", "image_url", "audio_url"]
    text: Optional[str] = None
    image_url: Optional[str] = None  # data URI or http(s) URL
    audio_url: Optional[str] = None


@dataclass
class ChatResponse:
    """Unified response shape across all providers."""
    id: str
    model: str
    content: str
    role: Literal["assistant"] = "assistant"
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] = "stop"
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Optional[float] = None  # populated if cost tracking is enabled


@dataclass
class StreamEvent:
    event_type: Literal["text_delta", "tool_call_start", "tool_call_delta", "done"]
    delta_text: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    finish_reason: Optional[str] = None
    usage: Optional[TokenUsage] = None
```

### Concrete provider example

```python
# packages/kailash-kaizen/src/kaizen/providers/llm/cohere.py

class CohereProvider:
    """Cohere provider — embeddings only.

    Does NOT implement LLMProvider, AsyncLLMProvider, StreamingProvider,
    ToolCallingProvider, or StructuredOutputProvider.
    """

    @property
    def name(self) -> str:
        return "cohere"

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {ProviderCapability.EMBEDDINGS, ProviderCapability.BYOK}

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        ...

    async def embed_async(self, texts: list[str], **kwargs) -> list[list[float]]:
        ...

    # No chat(), chat_async(), stream_chat() — protocol runtime checks
    # will correctly classify this as EmbeddingProvider only.
```

```python
# packages/kailash-kaizen/src/kaizen/providers/llm/openai.py

class OpenAIProvider:
    """OpenAI — full-featured LLM provider."""

    @property
    def name(self) -> str:
        return "openai"

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.CHAT_SYNC,
            ProviderCapability.CHAT_ASYNC,
            ProviderCapability.CHAT_STREAM,
            ProviderCapability.TOOLS,
            ProviderCapability.STRUCTURED_OUTPUT,
            ProviderCapability.EMBEDDINGS,
            ProviderCapability.VISION,
            ProviderCapability.AUDIO,
            ProviderCapability.REASONING_MODELS,
            ProviderCapability.BYOK,
        }

    def chat(self, messages, **kwargs) -> ChatResponse: ...
    async def chat_async(self, messages, **kwargs) -> ChatResponse: ...
    async def stream_chat(self, messages, **kwargs) -> AsyncGenerator[StreamEvent]: ...
    def embed(self, texts, **kwargs) -> list[list[float]]: ...
    async def embed_async(self, texts, **kwargs) -> list[list[float]]: ...
    def format_tools_for_provider(self, tools) -> list[dict]: ...
    def format_response_schema(self, schema) -> dict: ...
```

### Registry with typed returns

```python
# packages/kailash-kaizen/src/kaizen/providers/registry.py

_PROVIDERS: dict[str, BaseProvider] = {}

def register_provider(name: str, provider: BaseProvider) -> None:
    _PROVIDERS[name] = provider

def get_provider(name: str) -> BaseProvider:
    if name not in _PROVIDERS:
        raise UnknownProviderError(name)
    return _PROVIDERS[name]

def get_llm_provider(name: str) -> LLMProvider:
    """Get a provider that MUST support synchronous chat."""
    provider = get_provider(name)
    if not isinstance(provider, LLMProvider):
        raise CapabilityNotSupportedError(
            f"Provider {name} does not support synchronous chat. "
            f"Supports: {provider.capabilities}"
        )
    return provider

def get_streaming_provider(name: str) -> StreamingProvider:
    """Get a provider that MUST support streaming."""
    provider = get_provider(name)
    if not isinstance(provider, StreamingProvider):
        raise CapabilityNotSupportedError(
            f"Provider {name} does not support streaming. "
            f"Supports: {provider.capabilities}"
        )
    return provider

def get_embedding_provider(name: str) -> EmbeddingProvider:
    """Get a provider that MUST support embeddings."""
    provider = get_provider(name)
    if not isinstance(provider, EmbeddingProvider):
        raise CapabilityNotSupportedError(
            f"Provider {name} does not support embeddings. "
            f"Supports: {provider.capabilities}"
        )
    return provider


def get_provider_for_model(model: str) -> BaseProvider:
    """Auto-detect provider from model name prefix."""
    if model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return get_provider("openai")
    elif model.startswith("claude-"):
        return get_provider("anthropic")
    elif model.startswith("gemini-"):
        return get_provider("google")
    elif model.startswith(("llama", "mistral", "qwen")):
        return get_provider("ollama")
    # ... etc
    raise UnknownProviderError(f"Cannot detect provider for model: {model}")
```

### Usage from BaseAgent

```python
# packages/kailash-kaizen/src/kaizen/core/base_agent.py

class BaseAgent(Node):
    def __init__(self, config: BaseAgentConfig, ...):
        # Pick the right protocol based on needs
        if config.execution_mode == "streaming":
            self._llm = get_streaming_provider(config.provider_name)
        elif config.execution_mode == "autonomous":
            self._llm = get_llm_provider(config.provider_name)  # sync
        else:
            self._llm = get_provider_for_model(config.model)    # auto-detect

    def run(self, **inputs):
        # Static type checker knows _llm supports chat() here
        response = self._llm.chat(messages, **kwargs)
        return {"text": response.content, "usage": response.usage}
```

### Cross-SDK parallel (Rust)

Rust already has the per-provider modular structure. It needs to add capability trait split:

```rust
// crates/kailash-kaizen/src/llm/capabilities.rs

#[async_trait]
pub trait LlmProvider: Send + Sync {
    fn name(&self) -> &str;
    fn capabilities(&self) -> &ProviderCapabilities;
}

#[async_trait]
pub trait Chat: LlmProvider {
    async fn chat(&self, request: &LlmRequest) -> Result<LlmResponse, LlmClientError>;
}

#[async_trait]
pub trait Streaming: LlmProvider {
    async fn stream_chat<'a>(
        &'a self,
        request: &'a LlmRequest
    ) -> Pin<Box<dyn Stream<Item = Result<StreamEvent, LlmClientError>> + Send + 'a>>;
}

#[async_trait]
pub trait Embeddings: LlmProvider {
    async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, LlmClientError>;
}

#[async_trait]
pub trait Vision: LlmProvider {
    fn supports_image_format(&self, mime_type: &str) -> bool;
}
```

Providers implement only the traits they support. The `LlmClient` dispatcher uses trait objects:

```rust
pub struct LlmClient {
    providers: HashMap<String, Box<dyn Chat>>,  // at least Chat
    streaming_providers: HashMap<String, Box<dyn Streaming>>,
    embedding_providers: HashMap<String, Box<dyn Embeddings>>,
    // ...
}
```

## Rationale

1. **Resolves the red team's provider interface split concern** — providers only implement what they support, no stub methods, no Zero-Tolerance Rule 2 violations.

2. **Python and Rust can both adopt the same protocol/trait split** — cross-SDK parity preserved.

3. **Enables static typing at the call site** — if you call `get_streaming_provider("cohere")`, you get a clear error ("Cohere does not support streaming") instead of an AttributeError deep in the call stack.

4. **BaseAgent's provider selection becomes type-safe** — if `execution_mode == "streaming"`, the type system guarantees you have a `StreamingProvider`.

5. **Matches Rust's Capability pattern** — Rust's `ProviderCapabilities` struct is the same idea as Python's `ProviderCapability` enum set.

6. **Minimal provider ceremony** — a new provider implements only the protocols it supports. Cohere stays small (just `EmbeddingProvider`). OpenAI implements most of them. Mock implements whatever the tests need.

7. **Supports the provider matrix from the monolith audit** — 14 providers mapped to 8+ capabilities, with the matrix making which-supports-what explicit.

8. **Fixes bug #340 naturally** — the `StructuredOutputProvider.format_response_schema()` on GoogleProvider implements the mutual-exclusion check between `response_format` and `tools`, preventing the Gemini 2.5 crash.

## Consequences

### Positive

- ✅ No stub methods raising NotImplementedError (Zero-Tolerance compliance)
- ✅ Clear capability discovery via `provider.capabilities` set
- ✅ Typed provider access via `get_llm_provider`, `get_streaming_provider`, etc.
- ✅ Providers stay small and focused — Cohere is just `EmbeddingProvider`
- ✅ Easy to add new providers — implement only what you support
- ✅ Cross-SDK alignment — Python protocols ↔ Rust traits
- ✅ Static type checking catches "wrong capability" errors at BaseAgent construction
- ✅ Monolith audit's feature matrix becomes machine-readable via capability flags

### Negative

- ❌ More protocol classes/traits than a single `Provider` interface
- ❌ `runtime_checkable` protocols have some runtime overhead in Python
- ❌ Rust needs trait objects (`Box<dyn Chat>`) which adds vtable indirection (negligible in practice)
- ❌ Users reading provider code have to understand the capability split

### Neutral

- Splitting into protocols doesn't change the wire protocol. Provider adapter code (HTTP request building, response parsing) is unchanged.
- The `monolith → per-provider modules` migration (SPEC-02) is independent of this ADR but complementary.

## Alternatives Considered

### Alternative 1: Single fat `Provider` interface

**Rejected**. Forces all providers to implement all methods. Stub methods raise NotImplementedError (Zero-Tolerance violation).

### Alternative 2: No interface — just duck typing

**Rejected**. No static type checking. Errors surface at runtime as AttributeError deep in the call stack. Users can't discover capabilities programmatically.

### Alternative 3: Separate `Provider`, `LLMProvider`, `EmbeddingProvider` with no composition

**Partially adopted**. This ADR extends it by adding `StreamingProvider`, `ToolCallingProvider`, `StructuredOutputProvider`, `VisionProvider`, `AudioProvider` as independent capabilities. The finer-grained split handles providers like Docker (chat but no streaming) and Azure (chat + streaming + vision but different tool format).

### Alternative 4: Capability as mixin classes (multiple inheritance)

**Rejected**. Python multiple inheritance is fragile and doesn't enable static type checking of capabilities the same way Protocols do. Rust doesn't support multiple inheritance at all.

## Implementation Notes

### Capability declaration must match implementation

A provider that claims `ProviderCapability.CHAT_STREAM` in its `capabilities` set MUST implement `StreamingProvider.stream_chat()`. Unit tests validate consistency:

```python
def test_provider_capabilities_match_protocols():
    for name, provider in get_all_providers().items():
        caps = provider.capabilities
        if ProviderCapability.CHAT_SYNC in caps:
            assert isinstance(provider, LLMProvider), f"{name} claims CHAT_SYNC but doesn't implement LLMProvider"
        if ProviderCapability.CHAT_STREAM in caps:
            assert isinstance(provider, StreamingProvider)
        if ProviderCapability.EMBEDDINGS in caps:
            assert isinstance(provider, EmbeddingProvider)
        # ... etc
```

### BYOK capability passes through kwargs

BYOK (Bring Your Own Key) is a capability that every provider can support. It's implemented via `kwargs.get("api_key")` and `kwargs.get("base_url")` in each provider's method — no protocol changes needed.

### Reasoning model capability (o1, o3, o4)

Providers with `ProviderCapability.REASONING_MODELS` MUST filter parameters for reasoning models:

- Use `max_completion_tokens` instead of `max_tokens`
- Do NOT send `temperature`, `top_p`, `frequency_penalty`, `presence_penalty`
- Do NOT send `tools` or `response_format` (not supported by reasoning models as of 2026-04)

This is enforced in the provider's `chat()`, `chat_async()`, `stream_chat()` implementations. Test coverage:

```python
def test_openai_filters_reasoning_model_params():
    provider = OpenAIProvider()
    request = provider._build_request(
        messages=[Message(role="user", content="test")],
        model="o3-mini",
        temperature=0.5,  # should be stripped
        max_tokens=100,   # should become max_completion_tokens
    )
    assert "temperature" not in request
    assert "max_tokens" not in request
    assert request["max_completion_tokens"] == 100
```

### Migration from monolith to protocols

Per SPEC-02. The 5,001-line `ai_providers.py` gets split into:

- 1 file per provider (openai.py, anthropic.py, google.py, ollama.py, azure.py, perplexity.py, docker.py, mock.py)
- 4 files for embedding-only providers (cohere.py, huggingface.py, ollama_embed.py)
- 1 shared base file (base.py — the protocol definitions)
- 1 registry file
- 1 errors file
- Total ~12 files vs 1 monolith

## Related ADRs

- **ADR-001**: Composition over extension points (BaseAgent consumes providers via protocols)
- **ADR-003**: Streaming as wrapper primitive (StreamingAgent uses StreamingProvider)
- **ADR-008**: Cross-SDK lockstep (Python protocols ↔ Rust traits must match semantically)

## Related Research

- `01-research/09-provider-audit.md` — full Python provider audit (both stacks)
- `02-rs-research/02-rs-providers-audit.md` — Rust LLM layer audit

## Related Issues

- Python #340 (Gemini structured + tools crash) — fixed in `GoogleProvider.format_response_schema()` with mutual exclusion guard
