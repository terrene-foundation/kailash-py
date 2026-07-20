# Kailash Kaizen -- Domain Specification — Streaming Support

Version: 2.13.1
Package: `kailash-kaizen`

Parent domain: Kailash Kaizen AI agent framework. This file covers streaming support — the `StreamingProvider` protocol, `StreamingStrategy`, `StreamEvent`, and resolving a streaming provider by name or model. Split from `kaizen-providers.md` (specs-authority.md Rule 8 — the original file exceeded the 300-line split threshold). Sibling sub-files covering the rest of the parent domain: `kaizen-providers.md` (index), `kaizen-providers-provider-system.md`, `kaizen-providers-execution-strategies.md`, `kaizen-providers-tool-integration.md`, `kaizen-providers-memory-system.md`, `kaizen-providers-error-handling.md`, `kaizen-providers-streaming.md`. See also `kaizen-core.md`, `kaizen-signatures.md`, and `kaizen-advanced.md`.

---

## 21. Streaming Support

### 21.1 StreamingProvider Protocol

```python
@runtime_checkable
class StreamingProvider(Protocol):
    def stream_chat(
        self,
        messages: List[Message],
        **kwargs,
    ) -> AsyncGenerator[StreamEvent, None]: ...
```

A single synthesized yield does NOT satisfy the contract -- real token-by-token streaming is required.

### 21.2 StreamingStrategy

```python
strategy = StreamingStrategy(chunk_size=1)

# Async generator
async for token in strategy.stream(agent, inputs):
    print(token, end="", flush=True)
```

### 21.3 StreamEvent

Emitted by providers during streaming. Contains token delta, metadata, and completion status.

### 21.4 Resolving a Streaming Provider

```python
from kaizen.providers.registry import get_streaming_provider

provider = get_streaming_provider("openai")       # By name
provider = get_streaming_provider("gpt-4o")        # By model
# Raises CapabilityNotSupportedError if provider can't stream
```
