# SPEC-02: Provider Layer

**Status**: DRAFT
**Implements**: ADR-005 (Provider capability protocol split)
**Cross-SDK issues**: TBD
**Priority**: Phase 2 — shared primitive, consumed by BaseAgent and StreamingAgent

## §1 Overview

Replace the 5,001-line monolith (`kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py`) and the parallel 4-file adapter layer (`kaizen-agents/src/kaizen_agents/delegate/adapters/`) with a unified per-provider module structure at `packages/kailash-kaizen/src/kaizen/providers/`. Each provider implements only the capability protocols it supports (no stub methods). A central registry dispatches by model name prefix.

### What this replaces

| Old                                                    | New                                             | Notes                                   |
| ------------------------------------------------------ | ----------------------------------------------- | --------------------------------------- |
| `kaizen/nodes/ai/ai_providers.py` (5,001 LOC)          | `kaizen/providers/llm/*.py` (~12 files)         | Split into per-provider modules         |
| `kaizen_agents/delegate/adapters/openai_adapter.py`    | merged into `kaizen/providers/llm/openai.py`    | Streaming + sync in one file            |
| `kaizen_agents/delegate/adapters/anthropic_adapter.py` | merged into `kaizen/providers/llm/anthropic.py` |                                         |
| `kaizen_agents/delegate/adapters/google_adapter.py`    | merged into `kaizen/providers/llm/google.py`    |                                         |
| `kaizen_agents/delegate/adapters/ollama_adapter.py`    | merged into `kaizen/providers/llm/ollama.py`    |                                         |
| `kaizen_agents/delegate/adapters/openai_stream.py`     | DELETED (duplicate logic)                       | Merged into openai.py                   |
| `kaizen_agents/delegate/adapters/protocol.py`          | `kaizen/providers/streaming.py`                 | StreamingChatAdapter protocol           |
| `kaizen_agents/delegate/adapters/registry.py`          | `kaizen/providers/registry.py`                  | Unified registry                        |
| (none — Python lacks)                                  | `kaizen/providers/cost.py`                      | NEW — ported from Rust's `cost/` module |

## §2 Wire Types / API Contracts

### §2.1 Capability Protocols

```python
# packages/kailash-kaizen/src/kaizen/providers/base.py

from __future__ import annotations
from enum import Enum
from typing import Any, AsyncGenerator, Optional, Protocol, runtime_checkable


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
    REASONING_MODELS = "reasoning_models"
    BYOK = "byok"


@runtime_checkable
class BaseProvider(Protocol):
    """All providers implement this minimal contract."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> set[ProviderCapability]: ...

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities


@runtime_checkable
class LLMProvider(BaseProvider, Protocol):
    """Synchronous chat completion."""
    def chat(self, messages: list[Message], **kwargs) -> ChatResponse: ...


@runtime_checkable
class AsyncLLMProvider(BaseProvider, Protocol):
    """Asynchronous chat completion."""
    async def chat_async(self, messages: list[Message], **kwargs) -> ChatResponse: ...


@runtime_checkable
class StreamingProvider(BaseProvider, Protocol):
    """Token-by-token streaming."""
    async def stream_chat(self, messages: list[Message], **kwargs) -> AsyncGenerator[StreamEvent, None]: ...


@runtime_checkable
class EmbeddingProvider(BaseProvider, Protocol):
    """Text embeddings."""
    def embed(self, texts: list[str], **kwargs) -> list[list[float]]: ...
    async def embed_async(self, texts: list[str], **kwargs) -> list[list[float]]: ...


@runtime_checkable
class ToolCallingProvider(BaseProvider, Protocol):
    """Native function calling."""
    def format_tools_for_provider(self, tools: list[dict]) -> list[dict]: ...


@runtime_checkable
class StructuredOutputProvider(BaseProvider, Protocol):
    """JSON schema / structured outputs."""
    def format_response_schema(self, schema: dict) -> dict: ...
```

### §2.2 Unified Data Types

```python
# packages/kailash-kaizen/src/kaizen/providers/types.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union


@dataclass
class Message:
    """Unified message format across all providers."""
    role: Literal["system", "user", "assistant", "tool"]
    content: Union[str, list[ContentBlock]]
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None


@dataclass
class ContentBlock:
    type: Literal["text", "image_url", "audio_url"]
    text: Optional[str] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None


@dataclass
class ToolCall:
    id: str
    type: Literal["function"] = "function"
    function: Optional[ToolCallFunction] = None


@dataclass
class ToolCallFunction:
    name: str
    arguments: str  # JSON string


@dataclass
class ChatResponse:
    """Unified response shape across all providers."""
    id: str
    model: str
    content: str
    role: Literal["assistant"] = "assistant"
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter"] = "stop"
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=lambda: TokenUsage())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class StreamEvent:
    """Unified streaming event across all providers."""
    event_type: Literal["text_delta", "tool_call_start", "tool_call_delta", "tool_call_end", "done"]
    delta_text: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    finish_reason: Optional[str] = None
    usage: Optional[TokenUsage] = None
    content: str = ""  # accumulated text so far
```

### §2.3 Cost Module (NEW — ported from Rust)

```python
# packages/kailash-kaizen/src/kaizen/providers/cost.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import threading


@dataclass
class ModelPricing:
    """Per-model token pricing."""
    prompt_price_per_token: float    # USD per token (e.g., 0.000003 for $3/1M)
    completion_price_per_token: float


# Default pricing table (conservative estimates per 1M tokens)
DEFAULT_PRICING: dict[str, ModelPricing] = {
    "gpt-4o": ModelPricing(2.5e-6, 10e-6),
    "gpt-4": ModelPricing(30e-6, 60e-6),
    "gpt-5": ModelPricing(10e-6, 30e-6),
    "o1": ModelPricing(15e-6, 60e-6),
    "o3": ModelPricing(12e-6, 48e-6),
    "o4": ModelPricing(12e-6, 48e-6),
    "claude-": ModelPricing(3e-6, 15e-6),
    "gemini-": ModelPricing(1.25e-6, 5e-6),
}


@dataclass
class CostConfig:
    """Cost tracking configuration."""
    model_pricing: dict[str, ModelPricing] = field(default_factory=lambda: dict(DEFAULT_PRICING))
    budget_limit_usd: Optional[float] = None


class CostTracker:
    """Thread-safe cost accumulator.

    Tracks cumulative cost in microdollars (integer precision) to avoid
    floating-point drift. Converts to USD for the public API.

    Ported from Rust's `kailash-kaizen/src/cost/tracker.rs`.
    """

    def __init__(self, config: Optional[CostConfig] = None):
        self._config = config or CostConfig()
        self._cumulative_microdollars: int = 0
        self._lock = threading.Lock()
        self._per_model: dict[str, int] = {}

    def record_usage(self, model: str, usage: TokenUsage) -> float:
        """Record token usage and return the cost in USD.

        Matches model name against pricing table by prefix.
        Unknown models default to $3/$15 per 1M tokens.
        """
        pricing = self._resolve_pricing(model)
        cost_usd = (
            usage.prompt_tokens * pricing.prompt_price_per_token
            + usage.completion_tokens * pricing.completion_price_per_token
        )
        cost_microdollars = int(cost_usd * 1_000_000)

        with self._lock:
            self._cumulative_microdollars += cost_microdollars
            self._per_model[model] = self._per_model.get(model, 0) + cost_microdollars

        return cost_usd

    @property
    def total_cost_usd(self) -> float:
        with self._lock:
            return self._cumulative_microdollars / 1_000_000

    def check_budget(self) -> bool:
        """Return True if within budget, False if exceeded."""
        if self._config.budget_limit_usd is None:
            return True
        return self.total_cost_usd <= self._config.budget_limit_usd

    def _resolve_pricing(self, model: str) -> ModelPricing:
        for prefix, pricing in self._config.model_pricing.items():
            if model.startswith(prefix):
                return pricing
        return ModelPricing(3e-6, 15e-6)  # conservative default
```

### §2.4 Registry

```python
# packages/kailash-kaizen/src/kaizen/providers/registry.py

from __future__ import annotations
from typing import Optional
from kaizen.providers.base import (
    BaseProvider, LLMProvider, AsyncLLMProvider, StreamingProvider,
    EmbeddingProvider, ProviderCapability,
)


_PROVIDERS: dict[str, BaseProvider] = {}
_initialized: bool = False


def _auto_register() -> None:
    """Lazy-register all built-in providers on first access."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    from kaizen.providers.llm.openai import OpenAIProvider
    from kaizen.providers.llm.anthropic import AnthropicProvider
    from kaizen.providers.llm.google import GoogleProvider
    from kaizen.providers.llm.ollama import OllamaProvider
    from kaizen.providers.llm.azure import AzureProvider
    from kaizen.providers.llm.perplexity import PerplexityProvider
    from kaizen.providers.llm.docker import DockerModelRunnerProvider
    from kaizen.providers.llm.mock import MockProvider
    from kaizen.providers.embedding.cohere import CohereEmbeddingProvider
    from kaizen.providers.embedding.huggingface import HuggingFaceEmbeddingProvider

    for p in [
        OpenAIProvider(), AnthropicProvider(), GoogleProvider(),
        OllamaProvider(), AzureProvider(), PerplexityProvider(),
        DockerModelRunnerProvider(), MockProvider(),
        CohereEmbeddingProvider(), HuggingFaceEmbeddingProvider(),
    ]:
        _PROVIDERS[p.name] = p


def get_provider(name: str) -> BaseProvider:
    _auto_register()
    if name not in _PROVIDERS:
        raise UnknownProviderError(f"Unknown provider: {name}")
    return _PROVIDERS[name]


def get_provider_for_model(model: str) -> BaseProvider:
    """Auto-detect provider from model name prefix."""
    _auto_register()

    PREFIX_MAP = {
        ("gpt-", "o1-", "o3-", "o4-", "ft:gpt"): "openai",
        ("claude-",): "anthropic",
        ("gemini-",): "google",
        ("llama", "mistral", "qwen", "phi-", "codellama"): "ollama",
    }

    for prefixes, provider_name in PREFIX_MAP.items():
        if any(model.startswith(p) for p in prefixes):
            return get_provider(provider_name)

    raise UnknownProviderError(f"Cannot detect provider for model: {model}")


def get_streaming_provider(name_or_model: str) -> StreamingProvider:
    """Get a provider that supports streaming. Raises if it doesn't."""
    provider = get_provider(name_or_model) if name_or_model in _PROVIDERS else get_provider_for_model(name_or_model)
    if not isinstance(provider, StreamingProvider):
        raise CapabilityNotSupportedError(
            f"Provider '{provider.name}' does not support streaming. "
            f"Capabilities: {provider.capabilities}"
        )
    return provider


def get_embedding_provider(name: str) -> EmbeddingProvider:
    """Get a provider that supports embeddings. Raises if it doesn't."""
    provider = get_provider(name)
    if not isinstance(provider, EmbeddingProvider):
        raise CapabilityNotSupportedError(
            f"Provider '{provider.name}' does not support embeddings."
        )
    return provider


class UnknownProviderError(Exception): ...
class CapabilityNotSupportedError(Exception): ...
```

### §2.5 Per-Provider Module (Example: OpenAI)

```python
# packages/kailash-kaizen/src/kaizen/providers/llm/openai.py

from __future__ import annotations
from typing import Any, AsyncGenerator
from kaizen.providers.base import (
    BaseProvider, LLMProvider, AsyncLLMProvider, StreamingProvider,
    EmbeddingProvider, ToolCallingProvider, StructuredOutputProvider,
    ProviderCapability,
)
from kaizen.providers.types import (
    Message, ChatResponse, StreamEvent, TokenUsage, ToolCall,
)
import os


# Reasoning model prefixes that need special parameter handling
_REASONING_PREFIXES = ("o1-", "o3-", "o4-")


class OpenAIProvider(
    LLMProvider, AsyncLLMProvider, StreamingProvider,
    EmbeddingProvider, ToolCallingProvider, StructuredOutputProvider,
):
    """OpenAI provider — full-featured.

    Implements all capability protocols:
    - chat (sync), chat_async, stream_chat
    - embed, embed_async
    - format_tools_for_provider (OpenAI function calling format)
    - format_response_schema (json_schema with strict mode)

    Handles reasoning models (o1, o3, o4):
    - Uses max_completion_tokens instead of max_tokens
    - Strips temperature, top_p, frequency_penalty, presence_penalty
    - Does not send tools or response_format (not supported)
    """

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

    def chat(self, messages: list[Message], **kwargs) -> ChatResponse:
        """Synchronous chat completion via OpenAI API."""
        from openai import OpenAI

        client = self._get_client(kwargs)
        model = kwargs.get("model", os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o"))
        params = self._build_params(model, messages, kwargs)

        response = client.chat.completions.create(**params)
        return self._parse_response(response)

    async def chat_async(self, messages: list[Message], **kwargs) -> ChatResponse:
        """Asynchronous chat completion."""
        from openai import AsyncOpenAI

        client = self._get_async_client(kwargs)
        model = kwargs.get("model", os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o"))
        params = self._build_params(model, messages, kwargs)

        response = await client.chat.completions.create(**params)
        return self._parse_response(response)

    async def stream_chat(self, messages: list[Message], **kwargs) -> AsyncGenerator[StreamEvent, None]:
        """Stream tokens via OpenAI API."""
        from openai import AsyncOpenAI

        client = self._get_async_client(kwargs)
        model = kwargs.get("model", os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o"))
        params = self._build_params(model, messages, kwargs)
        params["stream"] = True
        params["stream_options"] = {"include_usage": True}

        accumulated_text = ""
        tool_calls: list[ToolCall] = []

        async for chunk in await client.chat.completions.create(**params):
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            if delta.content:
                accumulated_text += delta.content
                yield StreamEvent(
                    event_type="text_delta",
                    delta_text=delta.content,
                    content=accumulated_text,
                )

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    # ... tool call accumulation logic ...
                    pass

            if chunk.choices and chunk.choices[0].finish_reason:
                usage = TokenUsage()
                if chunk.usage:
                    usage = TokenUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )
                yield StreamEvent(
                    event_type="done",
                    content=accumulated_text,
                    finish_reason=chunk.choices[0].finish_reason,
                    usage=usage,
                )

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]:
        from openai import OpenAI
        client = self._get_client(kwargs)
        model = kwargs.get("embedding_model", "text-embedding-3-small")
        response = client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in response.data]

    async def embed_async(self, texts: list[str], **kwargs) -> list[list[float]]:
        from openai import AsyncOpenAI
        client = self._get_async_client(kwargs)
        model = kwargs.get("embedding_model", "text-embedding-3-small")
        response = await client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in response.data]

    def format_tools_for_provider(self, tools: list[dict]) -> list[dict]:
        """Tools are already in OpenAI format — passthrough."""
        return tools

    def format_response_schema(self, schema: dict) -> dict:
        """Format as OpenAI strict JSON schema mode."""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema.get("title", "output"),
                "strict": True,
                "schema": schema,
            },
        }

    # ─── Internal ──────────────────────────────────────────────────────

    def _is_reasoning_model(self, model: str) -> bool:
        return any(model.startswith(p) for p in _REASONING_PREFIXES)

    def _build_params(self, model: str, messages: list[Message], kwargs: dict) -> dict:
        params: dict[str, Any] = {
            "model": model,
            "messages": [self._format_message(m) for m in messages],
        }

        if self._is_reasoning_model(model):
            # Reasoning models: max_completion_tokens, no temperature/tools/response_format
            if "max_tokens" in kwargs:
                params["max_completion_tokens"] = kwargs["max_tokens"]
        else:
            # Standard models
            if "temperature" in kwargs:
                params["temperature"] = kwargs["temperature"]
            if "max_tokens" in kwargs:
                params["max_tokens"] = kwargs["max_tokens"]
            if "tools" in kwargs and kwargs["tools"]:
                params["tools"] = kwargs["tools"]
            if "response_format" in kwargs and kwargs["response_format"]:
                params["response_format"] = kwargs["response_format"]

        return params

    def _format_message(self, msg: Message) -> dict:
        d: dict[str, Any] = {"role": msg.role}
        if isinstance(msg.content, str):
            d["content"] = msg.content
        else:
            d["content"] = [self._format_content_block(b) for b in msg.content]
        if msg.tool_calls:
            d["tool_calls"] = [self._format_tool_call(tc) for tc in msg.tool_calls]
        if msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        if msg.name:
            d["name"] = msg.name
        return d

    def _format_content_block(self, block: Any) -> dict: ...
    def _format_tool_call(self, tc: ToolCall) -> dict: ...
    def _parse_response(self, response: Any) -> ChatResponse: ...

    def _get_client(self, kwargs: dict) -> Any:
        """Get or create OpenAI client (with BYOK support)."""
        from openai import OpenAI
        api_key = kwargs.get("api_key", os.environ.get("OPENAI_API_KEY"))
        base_url = kwargs.get("base_url")
        return OpenAI(api_key=api_key, base_url=base_url)

    def _get_async_client(self, kwargs: dict) -> Any:
        from openai import AsyncOpenAI
        api_key = kwargs.get("api_key", os.environ.get("OPENAI_API_KEY"))
        base_url = kwargs.get("base_url")
        return AsyncOpenAI(api_key=api_key, base_url=base_url)
```

### §2.6 Embedding-Only Provider (Example: Cohere)

```python
# packages/kailash-kaizen/src/kaizen/providers/embedding/cohere.py

class CohereEmbeddingProvider(EmbeddingProvider):
    """Cohere — embeddings only.

    Does NOT implement LLMProvider, StreamingProvider, ToolCallingProvider,
    or StructuredOutputProvider. No stub methods.
    """

    @property
    def name(self) -> str:
        return "cohere"

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {ProviderCapability.EMBEDDINGS, ProviderCapability.BYOK}

    def embed(self, texts: list[str], **kwargs) -> list[list[float]]: ...
    async def embed_async(self, texts: list[str], **kwargs) -> list[list[float]]: ...

    # No chat(), stream_chat(), etc. — this is an embedding-only provider
```

### §2.7 GoogleProvider Structured Output + Tools Guard (Fixes #340)

```python
# packages/kailash-kaizen/src/kaizen/providers/llm/google.py

class GoogleProvider(LLMProvider, AsyncLLMProvider, StreamingProvider,
                     ToolCallingProvider, StructuredOutputProvider):

    def format_response_schema(self, schema: dict) -> dict:
        """Format as Gemini JSON mode.

        IMPORTANT: Gemini 2.5 models do NOT support response_mime_type + tools
        together (400 INVALID_ARGUMENT). The mutual exclusion is enforced in
        _build_params(), not here — this method just formats the schema.
        """
        return {
            "response_mime_type": "application/json",
            "response_json_schema": schema,
        }

    def _build_params(self, model: str, messages, kwargs) -> dict:
        params = { ... }

        has_tools = bool(kwargs.get("tools"))
        has_schema = bool(kwargs.get("response_format"))

        # Gemini 2.5 mutual exclusion guard (fixes #340)
        if has_tools and has_schema:
            # Tools take priority — strip structured output, rely on prompt-based JSON
            import logging
            logging.getLogger(__name__).warning(
                "Gemini: tools and response_format both present. "
                "Stripping response_format (Gemini 2.5 does not support both). "
                "JSON output will be guided by system prompt instead."
            )
            # Don't add response_mime_type or response_json_schema
        elif has_schema:
            schema_config = kwargs["response_format"]
            params["generation_config"]["response_mime_type"] = "application/json"
            if "json_schema" in schema_config:
                params["generation_config"]["response_json_schema"] = schema_config["json_schema"]["schema"]

        if has_tools:
            params["tools"] = self.format_tools_for_provider(kwargs["tools"])

        return params
```

## §3 Semantics

### §3.1 Provider Selection

Consumers call `get_provider_for_model(model)` which matches by prefix. The mapping is:

| Prefix                                          | Provider  |
| ----------------------------------------------- | --------- |
| `gpt-`, `o1-`, `o3-`, `o4-`, `ft:gpt`           | openai    |
| `claude-`                                       | anthropic |
| `gemini-`                                       | google    |
| `llama`, `mistral`, `qwen`, `phi-`, `codellama` | ollama    |

Unknown prefixes raise `UnknownProviderError`.

### §3.2 BYOK Multi-Tenant

Every provider method accepts `api_key=` and `base_url=` in kwargs for per-request credential override. Client instances are cached per key for efficiency (with TTL expiry).

### §3.3 Reasoning Model Handling

Models matching `_REASONING_PREFIXES` (o1-, o3-, o4-) get special treatment:

- `max_tokens` → `max_completion_tokens`
- `temperature`, `top_p`, `frequency_penalty`, `presence_penalty` → stripped
- `tools`, `response_format` → stripped (not supported by reasoning models)

### §3.4 Error Sanitization

Provider errors are wrapped in `ProviderError(provider_name, status_code, message)`. API keys, connection strings, and internal paths are NEVER included in error messages. The existing `sanitize_provider_error()` utility is preserved and applied uniformly.

## §4 Backward Compatibility

```python
# packages/kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py (v2.x shim)
import warnings
warnings.warn(
    "kaizen.nodes.ai.ai_providers is deprecated since v2.next. "
    "Use `from kaizen.providers import get_provider` instead.",
    DeprecationWarning, stacklevel=2,
)
from kaizen.providers.llm.openai import OpenAIProvider
from kaizen.providers.llm.anthropic import AnthropicProvider
from kaizen.providers.llm.google import GoogleProvider as GoogleGeminiProvider
# ... all 14 provider classes re-exported
```

```python
# packages/kaizen-agents/src/kaizen_agents/delegate/adapters/__init__.py (v2.x shim)
import warnings
warnings.warn(
    "kaizen_agents.delegate.adapters is deprecated since v2.next. "
    "Use `from kaizen.providers import get_streaming_provider` instead.",
    DeprecationWarning, stacklevel=2,
)
from kaizen.providers.streaming import StreamingChatAdapter as StreamingChatAdapter
from kaizen.providers.llm.openai import OpenAIProvider as OpenAIStreamAdapter
# ... adapter re-exports
```

## §5 Security Considerations

1. **SSRF protection**: All `base_url` values validated against metadata endpoint blocklist (ported from Rust's `LlmClient`).
2. **API keys never logged**: `sanitize_provider_error()` redacts keys from exceptions and log messages.
3. **No eval()/exec()**: JSON response parsing uses `json.loads()` only.
4. **Model name from .env**: Per `rules/env-models.md`, model names MUST come from `.env` or explicit parameter, never hardcoded. The DEFAULT_PRICING dict uses prefixes, not full model names.

## §6 Directory Layout

```
packages/kailash-kaizen/src/kaizen/providers/
├── __init__.py           # Public API re-exports
├── base.py               # Capability protocols (BaseProvider, LLMProvider, etc.)
├── types.py              # Message, ChatResponse, StreamEvent, TokenUsage, ToolCall
├── streaming.py          # StreamingChatAdapter protocol (moved from delegate/adapters/)
├── registry.py           # get_provider(), get_provider_for_model(), etc.
├── cost.py               # CostTracker, ModelPricing, CostConfig (NEW from Rust)
├── errors.py             # ProviderError, UnknownProviderError, CapabilityNotSupportedError
├── llm/
│   ├── __init__.py
│   ├── openai.py         # OpenAI (chat + stream + embed + tools + structured)
│   ├── anthropic.py      # Anthropic (chat + stream + tools + structured, no embed)
│   ├── google.py         # Google Gemini (chat + stream + tools + structured, mutual excl guard)
│   ├── ollama.py         # Ollama (chat + stream, limited tools)
│   ├── azure.py          # Azure OpenAI (wrapper, delegates to OpenAI adapter)
│   ├── perplexity.py     # Perplexity (chat + stream)
│   ├── docker.py         # DockerModelRunner (chat)
│   └── mock.py           # Mock (testing — deterministic responses)
└── embedding/
    ├── __init__.py
    ├── openai.py         # OpenAI embeddings (if separate from LLM — or merged into llm/openai.py)
    ├── cohere.py         # Cohere (embed only)
    ├── huggingface.py    # HuggingFace TEI (embed only)
    └── ollama.py         # Ollama embeddings (if separate)
```

## §7 Interop Test Vectors

### 7.1 Provider capability consistency

```python
def test_provider_capabilities_match_protocols():
    """Every provider's declared capabilities match the protocols it implements."""
    for name, provider in get_all_providers().items():
        caps = provider.capabilities
        if ProviderCapability.CHAT_SYNC in caps:
            assert isinstance(provider, LLMProvider)
        if ProviderCapability.CHAT_STREAM in caps:
            assert isinstance(provider, StreamingProvider)
        if ProviderCapability.EMBEDDINGS in caps:
            assert isinstance(provider, EmbeddingProvider)
        if ProviderCapability.TOOLS in caps:
            assert isinstance(provider, ToolCallingProvider)
        if ProviderCapability.STRUCTURED_OUTPUT in caps:
            assert isinstance(provider, StructuredOutputProvider)
```

### 7.2 Reasoning model parameter filtering

```python
def test_openai_filters_reasoning_model_params():
    provider = OpenAIProvider()
    params = provider._build_params(
        "o3-mini",
        [Message(role="user", content="test")],
        {"temperature": 0.5, "max_tokens": 100, "tools": [...]}
    )
    assert "temperature" not in params
    assert "max_tokens" not in params
    assert "tools" not in params
    assert params["max_completion_tokens"] == 100
```

### 7.3 Gemini mutual exclusion (#340)

```python
def test_google_strips_response_format_when_tools_present():
    provider = GoogleProvider()
    params = provider._build_params(
        "gemini-2.5-flash",
        [...],
        {"tools": [...], "response_format": {"type": "json_schema", ...}}
    )
    assert "response_mime_type" not in params.get("generation_config", {})
    assert "response_json_schema" not in params.get("generation_config", {})
    # Tools ARE present
    assert "tools" in params
```

## §8 Migration Order

1. **Create `kaizen/providers/` directory** with `__init__.py`, `base.py`, `types.py`, `streaming.py`, `registry.py`, `cost.py`, `errors.py`
2. **Extract OpenAI provider** from monolith → `llm/openai.py` (merge sync from monolith + streaming from adapter)
3. **Extract Anthropic** similarly
4. **Extract Google** similarly (include #340 guard)
5. **Extract Ollama** similarly
6. **Extract Azure** (wrapper pattern, delegates to OpenAI)
7. **Extract remaining providers** (Perplexity, Docker, Mock)
8. **Extract embedding providers** (Cohere, HuggingFace)
9. **Port CostTracker from Rust** → `cost.py`
10. **Add backward-compat shims** at old import paths
11. **Migrate BaseAgent** to use `get_provider_for_model()` instead of direct `ai_providers` imports
12. **Delete `kaizen_agents/delegate/adapters/`** (after Delegate migrated to composition facade per SPEC-05)
13. **Run tests** — verify all provider-related tests pass with new import paths

## §9 Test Migration

| Old                                                           | New                                             | Notes                         |
| ------------------------------------------------------------- | ----------------------------------------------- | ----------------------------- |
| `kailash-kaizen/tests/unit/nodes/ai/test_*_provider.py` (13+) | `kailash-kaizen/tests/unit/providers/test_*.py` | Per-provider test files       |
| `kaizen-agents/tests/unit/test_adapters.py`                   | Merged into provider tests                      | Streaming tests               |
| (none)                                                        | `tests/unit/providers/test_registry.py`         | Registry auto-detection tests |
| (none)                                                        | `tests/unit/providers/test_cost.py`             | CostTracker tests             |
| (none)                                                        | `tests/unit/providers/test_capabilities.py`     | Protocol conformance tests    |

## §10 Related Specs

- **SPEC-01** (kailash-mcp): ToolRegistry uses provider's `format_tools_for_provider()` to build LLM tool declarations
- **SPEC-03** (Composition wrappers): `MonitoredAgent` uses `CostTracker` for budget enforcement
- **SPEC-04** (BaseAgent slimming): BaseAgent constructor uses `get_provider_for_model()` to resolve LLM client
- **SPEC-05** (Delegate facade): Delegate passes provider kwargs through to the inner BaseAgent
- **SPEC-09** (Cross-SDK parity): Provider capability protocols must have Rust trait equivalents

## §11 Rust Parallel

Rust already has the correct structure at `crates/kailash-kaizen/src/llm/`. The convergence adds:

1. Capability trait split (per Rust adapter interface patterns from `02-rs-research/02-rs-providers-audit.md`)
2. Ollama, Cohere, HuggingFace, Perplexity, Docker adapters (missing in Rust)
3. Reasoning model parameter filtering (o1/o3/o4 — detected but not applied)
4. CostTracker already exists in Rust (`kailash-kaizen/src/cost/`)

Both SDKs end up with:

- Per-provider modules
- Capability-based dispatch
- CostTracker with microdollar precision
- Reasoning model special handling
- SSRF protection on base_url
- BYOK per-request overrides
