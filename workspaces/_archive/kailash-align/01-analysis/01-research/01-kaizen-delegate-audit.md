# Kaizen Delegate Audit for kailash-align Integration

## 1. How Delegate Currently Discovers and Configures Models

### Model Resolution Chain

The Delegate uses a three-level configuration system:

1. **Explicit `model` parameter** to `Delegate(model="...")` constructor
2. **`DEFAULT_LLM_MODEL` environment variable** (fallback when model is empty)
3. **`KZ_MODEL` environment variable** via `KzConfig` loader (overrides TOML config)

The Delegate does NOT discover models automatically. It requires an explicit model string. There is no registry lookup, no auto-detection of locally available models.

### Provider/Adapter Resolution

Provider selection follows this priority:

1. **Explicit `config.provider`** setting in KzConfig (e.g., `provider = "ollama"`)
2. **Model-name prefix heuristic** in `adapters/registry.py`:
   - `claude-*` -> `anthropic`
   - `gemini-*` -> `google`
   - Everything else -> `openai` (default)
3. **Ollama has no prefix detection** -- it must be explicitly configured via `provider = "ollama"` or by passing an `OllamaStreamAdapter` directly

Key code path: `Delegate.__init__` -> `AgentLoop.__init__` -> `get_adapter_for_model()` -> concrete adapter.

### Adapter Architecture

Four adapters exist, all implementing `StreamingChatAdapter` protocol:

- `OpenAIStreamAdapter` -- OpenAI API (also works with vLLM's OpenAI-compatible endpoint)
- `AnthropicStreamAdapter` -- Anthropic API
- `GoogleStreamAdapter` -- Google Gemini API
- `OllamaStreamAdapter` -- Ollama `/api/chat` endpoint (uses httpx directly, no SDK)

Each adapter accepts: `base_url`, `default_model`, `default_temperature`, `default_max_tokens`.

### Ollama Integration Details

`OllamaStreamAdapter` already exists and is functional:

- Base URL: `OLLAMA_BASE_URL` env var or `http://localhost:11434`
- Streams via `httpx.AsyncClient` against `/api/chat`
- Supports tool calling (Ollama's native function calling format)
- No Python SDK dependency (httpx only, already a transitive dep of openai)

### KzConfig Three-Level Loading

Config loads in order (later overrides earlier):

1. Built-in defaults (`model=""`, `provider="openai"`, `max_turns=50`)
2. User-level: `~/.kz/config.toml`
3. Project-level: `<project>/.kz/config.toml`
4. Environment variables: `KZ_MODEL`, `KZ_PROVIDER`, etc.

## 2. What KaizenModelBridge Needs to Integrate

### The Integration Gap

The architecture doc proposes `KaizenModelBridge.create_delegate()` as a factory that returns a configured Delegate. Based on the audit, this is straightforward because:

1. **Ollama adapter already exists** -- no new adapter needed
2. **`provider="ollama"` is already supported** -- just needs to be set
3. **`base_url` is configurable** -- can point to any Ollama instance

### Concrete Integration Path

```python
# What KaizenModelBridge.create_delegate() actually does:
async def create_delegate(self, adapter_name, version=None, **delegate_kwargs):
    config = await self.get_delegate_config(adapter_name, version)

    # For Ollama strategy:
    # config = {"model": "my-fine-tuned-model", "base_url": "http://localhost:11434"}

    from kaizen_agents.delegate import Delegate
    from kaizen_agents.delegate.adapters.ollama_adapter import OllamaStreamAdapter

    adapter = OllamaStreamAdapter(
        base_url=config["base_url"],
        default_model=config["model"],
    )
    return Delegate(model=config["model"], adapter=adapter, **delegate_kwargs)
```

### For vLLM Strategy

vLLM exposes an OpenAI-compatible API. The existing `OpenAIStreamAdapter` works directly:

```python
# vLLM strategy uses OpenAI adapter with custom base_url:
from kaizen_agents.delegate.adapters.openai_adapter import OpenAIStreamAdapter

adapter = OpenAIStreamAdapter(
    base_url="http://localhost:8000/v1",  # vLLM endpoint
    default_model="my-fine-tuned-model",
    api_key="not-needed",  # vLLM doesn't require auth by default
)
return Delegate(model="my-fine-tuned-model", adapter=adapter, **delegate_kwargs)
```

### For local_hf Strategy (Dev Only)

This is the only strategy that needs NEW work. Direct HuggingFace `transformers.pipeline` inference from Python has no existing adapter. However, this is explicitly marked "dev only, slow" in the architecture doc and could be deferred to v1.1.

## 3. How Delegate Handles Local Model Endpoints

### Already Supported

- **Ollama**: Full support via `OllamaStreamAdapter`. Stream chat, tool calling, token usage tracking all work.
- **vLLM**: Works via `OpenAIStreamAdapter` with custom `base_url`. vLLM's OpenAI-compatible API is well-tested with the OpenAI adapter pattern.

### Not Supported (Would Need New Adapter)

- **Direct `transformers.pipeline` inference**: No adapter exists for in-process HuggingFace model inference. Would require loading the model into GPU memory within the same Python process and implementing streaming generation. This is architecturally different from all existing adapters (HTTP-based).

### Cost Tracking Gap

The Delegate's cost tracking (`_estimate_cost()`) uses cloud provider pricing. For local models (Ollama/vLLM), cost is effectively $0/token but compute cost exists. The cost model has no concept of "free but slow" local inference. This is not blocking but worth noting -- budget tracking with `budget_usd` would incorrectly estimate costs for local models.

## 4. Assessment for kailash-align

### Low Risk

- Ollama integration: Already works, well-tested adapter
- vLLM integration: Already works via OpenAI adapter
- Model string passing: Simple -- just need the model name registered in Ollama/vLLM

### Medium Risk

- Model discovery: `discover_deployed_models()` needs Ollama API calls (`ollama list`) -- straightforward but requires subprocess or httpx calls
- Auto-detection strategy: Checking if Ollama has a model registered requires network calls

### Worth Deferring (v1.1)

- `local_hf` strategy: In-process transformers inference adapter is complex and low-value (users should deploy to Ollama for any real use)
- Cost model for local inference: Non-trivial to estimate compute cost vs. API cost

### Conclusion

KaizenModelBridge is the **simplest component** in kailash-align. The hard infrastructure (Ollama adapter, OpenAI-compatible adapter for vLLM) already exists. The bridge is primarily a config lookup + factory method, estimated at 150-250 lines of production code.
