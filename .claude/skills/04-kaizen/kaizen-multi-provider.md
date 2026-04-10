# Multi-Provider LLM Adapters

kaizen-agents supports OpenAI, Anthropic, Google, and Ollama via a unified `StreamingChatAdapter` protocol.

## Provider Selection

```python
from kaizen_agents import Delegate

# Auto-detect from model name prefix:
d1 = Delegate(model="gpt-4o")              # → OpenAI adapter
d2 = Delegate(model="claude-sonnet-4-20250514")  # → Anthropic adapter
d3 = Delegate(model="gemini-2.0-flash")    # → Google adapter
d4 = Delegate(model="llama3:latest")       # → Ollama adapter (localhost)

# Explicit via config:
from kaizen_agents.delegate.adapters import get_adapter
adapter = get_adapter(provider="anthropic", model="claude-sonnet-4-20250514")
```

## StreamingChatAdapter Protocol

```python
from kaizen_agents.delegate.adapters.protocol import StreamingChatAdapter, StreamEvent

class StreamingChatAdapter(Protocol):
    async def stream_chat(
        self, messages: list[dict], tools: list[dict] | None = None, **kwargs
    ) -> AsyncGenerator[StreamEvent, None]: ...
```

### StreamEvent Types

| event_type        | Fields                          | Meaning                |
| ----------------- | ------------------------------- | ---------------------- |
| `text_delta`      | `text`                          | Incremental text chunk |
| `tool_call_start` | `tool_call_id, name`            | Tool call begins       |
| `tool_call_delta` | `tool_call_id, arguments_delta` | Argument streaming     |
| `tool_call_end`   | `tool_call_id`                  | Tool call complete     |
| `done`            | `usage`                         | Stream finished        |

## Adapter Registry

```python
from kaizen_agents.delegate.adapters.registry import get_adapter_for_model

adapter = get_adapter_for_model("claude-sonnet-4-20250514")  # AnthropicStreamAdapter
adapter = get_adapter_for_model("gpt-4o")              # OpenAIStreamAdapter
```

## Lazy Imports

All provider SDKs are lazy-imported. Only `openai` is needed for default behavior. Install others as needed:

```bash
pip install anthropic    # for Anthropic adapter
pip install google-generativeai  # for Google adapter
# Ollama uses httpx (already a dependency)
```

## SPEC-02 Provider Layer (kaizen.providers)

Since SPEC-02, the provider monolith has been split into per-provider modules under `kaizen/providers/`. The old import path `kaizen.nodes.ai.ai_providers` is a backward-compat shim that re-exports all public names.

### ProviderRegistry (14 entries)

```python
from kaizen.providers.registry import get_provider, get_provider_for_model, PROVIDERS

# Named lookup (14 entries including aliases)
provider = get_provider("anthropic")

# Prefix-dispatch model detection
provider = get_provider_for_model("claude-sonnet-4-20250514")  # -> AnthropicProvider
provider = get_provider_for_model("gpt-4o")               # -> OpenAIProvider
provider = get_provider_for_model("gemini-2.0-flash")      # -> GoogleGeminiProvider
provider = get_provider_for_model("llama3:latest")         # -> OllamaProvider
provider = get_provider_for_model("ai/my-model")           # -> DockerModelRunnerProvider
provider = get_provider_for_model("sonar-pro")             # -> PerplexityProvider
```

Registry keys: `ollama`, `openai`, `anthropic`, `cohere`, `huggingface`, `mock`, `azure`, `azure_openai`, `azure_ai_foundry`, `docker`, `google`, `gemini`, `perplexity`, `pplx`.

### ProviderCapability Enum (10 members)

```python
from kaizen.providers.base import ProviderCapability

# CHAT_SYNC, CHAT_ASYNC, CHAT_STREAM, TOOLS, STRUCTURED_OUTPUT,
# EMBEDDINGS, VISION, AUDIO, REASONING_MODELS, BYOK
```

### Runtime-Checkable Protocols (5)

```python
from kaizen.providers.base import (
    BaseProvider,           # name + capabilities
    AsyncLLMProvider,       # chat_async(messages)
    StreamingProvider,      # stream_chat() -> StreamEvent
    ToolCallingProvider,    # chat_with_tools(messages, tools)
    StructuredOutputProvider,  # chat_structured(messages, schema)
)

# Structural checking -- no explicit inheritance needed
if isinstance(provider, StreamingProvider):
    async for event in provider.stream_chat(messages):
        ...
```

### CostTracker (thread-safe)

```python
from kaizen.providers.cost import CostTracker, CostConfig, ModelPricing

tracker = CostTracker(config=CostConfig(pricing={
    "gpt-4o": ModelPricing(prompt_cost_per_1k=0.0025, completion_cost_per_1k=0.01),
}))
cost = tracker.record("gpt-4o", prompt_tokens=500, completion_tokens=100)
print(tracker.total_cost_usd)
```

Thread-safe via `threading.Lock`. Maintains a bounded deque of cost records (maxlen=10000).

### Backward Compatibility

```python
# Old import path still works (shim re-exports everything)
from kaizen.nodes.ai.ai_providers import OpenAIProvider, get_provider

# New canonical import path
from kaizen.providers import OpenAIProvider
from kaizen.providers.registry import get_provider
```

## Source Files

- `packages/kailash-kaizen/src/kaizen/providers/base.py` -- capability enum + protocols + legacy ABCs
- `packages/kailash-kaizen/src/kaizen/providers/registry.py` -- PROVIDERS dict + prefix-dispatch
- `packages/kailash-kaizen/src/kaizen/providers/cost.py` -- CostTracker + ModelPricing
- `packages/kailash-kaizen/src/kaizen/providers/llm/{openai,anthropic,google,ollama,azure,docker,mock,perplexity}.py`
- `packages/kailash-kaizen/src/kaizen/providers/embedding/{cohere,huggingface}.py`
- `packages/kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py` -- backward-compat shim
- `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/protocol.py`
- `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/registry.py`
- `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/{openai,anthropic,google,ollama}_adapter.py`
