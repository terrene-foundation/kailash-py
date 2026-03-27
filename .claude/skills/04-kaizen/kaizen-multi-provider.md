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

## Source Files

- `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/protocol.py`
- `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/registry.py`
- `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/{openai,anthropic,google,ollama}_adapter.py`
