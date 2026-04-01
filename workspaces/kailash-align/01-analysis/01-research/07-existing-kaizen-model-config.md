# Existing Kaizen Model Configuration Analysis

## 1. How Kaizen Currently Handles Model Configuration

### Environment Variables

The Delegate reads model configuration from environment variables:

| Variable            | Purpose                                               | Used By                  |
| ------------------- | ----------------------------------------------------- | ------------------------ |
| `DEFAULT_LLM_MODEL` | Fallback model when `Delegate(model="")`              | `Delegate.__init__`      |
| `KZ_MODEL`          | Override model via KzConfig env layer                 | `KzConfig` loader        |
| `KZ_PROVIDER`       | Override provider (openai, anthropic, google, ollama) | `KzConfig` loader        |
| `KZ_MAX_TURNS`      | Override max turns                                    | `KzConfig` loader        |
| `KZ_TEMPERATURE`    | Override temperature                                  | `KzConfig` loader        |
| `OPENAI_API_KEY`    | OpenAI API authentication                             | `OpenAIStreamAdapter`    |
| `ANTHROPIC_API_KEY` | Anthropic API authentication                          | `AnthropicStreamAdapter` |
| `GOOGLE_API_KEY`    | Google API authentication                             | `GoogleStreamAdapter`    |
| `OLLAMA_BASE_URL`   | Ollama endpoint (default: localhost:11434)            | `OllamaStreamAdapter`    |

### Provider Configuration

Provider selection is configuration-level logic (not agent reasoning):

```python
# Priority 1: Explicit provider in config
config.provider = "ollama"  # From TOML or KZ_PROVIDER env var

# Priority 2: Model-name prefix heuristic
"claude-*"  -> "anthropic"
"gemini-*"  -> "google"
(default)   -> "openai"

# Priority 3: Default
"openai"
```

Ollama has NO prefix heuristic -- it must be explicitly configured.

### TOML Configuration

```toml
# ~/.kz/config.toml or <project>/.kz/config.toml
model = "claude-sonnet-4-20250514"
provider = "anthropic"
max_turns = 50
temperature = 0.4
```

### API Key Resolution

Each adapter resolves its own API key from environment:

- `OpenAIStreamAdapter`: reads `OPENAI_API_KEY` via openai SDK
- `AnthropicStreamAdapter`: reads `ANTHROPIC_API_KEY` via anthropic SDK
- `GoogleStreamAdapter`: reads `GOOGLE_API_KEY` or `GEMINI_API_KEY`
- `OllamaStreamAdapter`: no API key needed (local service)

## 2. Can a Fine-Tuned Local Model Slot Into the Existing Provider System?

### Yes -- Via Ollama Provider

The simplest integration path:

```python
# After deploying fine-tuned model to Ollama as "my-fine-tuned-model":
delegate = Delegate(
    model="my-fine-tuned-model",
    adapter=OllamaStreamAdapter(
        base_url="http://localhost:11434",
        default_model="my-fine-tuned-model",
    ),
)
```

Or via configuration:

```toml
# .kz/config.toml
model = "my-fine-tuned-model"
provider = "ollama"
```

Then:

```python
delegate = Delegate(model="my-fine-tuned-model")
# Auto-resolves to OllamaStreamAdapter via provider="ollama"
```

### Yes -- Via vLLM (OpenAI-Compatible)

vLLM exposes an OpenAI-compatible API:

```python
delegate = Delegate(
    model="my-fine-tuned-model",
    adapter=OpenAIStreamAdapter(
        base_url="http://localhost:8000/v1",
        default_model="my-fine-tuned-model",
        api_key="not-needed",
    ),
)
```

Or via configuration:

```toml
# .kz/config.toml
model = "my-fine-tuned-model"
provider = "openai"  # vLLM is OpenAI-compatible
```

With `OPENAI_API_KEY=dummy` and `OPENAI_BASE_URL=http://localhost:8000/v1`.

### What KaizenModelBridge Adds

The bridge automates the above configuration:

```python
# Instead of manual adapter construction:
bridge = KaizenModelBridge(registry=adapter_registry)
delegate = await bridge.create_delegate("my-fine-tuned-model")
# Bridge auto-detects: model is deployed on Ollama -> creates OllamaStreamAdapter
```

The value is:

1. **Auto-detection**: Bridge checks where the model is deployed (Ollama? vLLM? local only?)
2. **Registry integration**: Bridge looks up the adapter version in AdapterRegistry for metadata
3. **One-line factory**: `create_delegate()` vs. 5-10 lines of manual adapter construction

## 3. Gaps in Current Provider System for Local Models

### Gap 1: No Model Registry Awareness

The Delegate has no concept of a model registry. It takes a model string and a provider. It does not know:

- Whether the model is fine-tuned or base
- What the base model was
- What LoRA config was used
- Whether the model is deployed or just exists as files

KaizenModelBridge fills this gap by looking up the AdapterRegistry and resolving deployment status.

### Gap 2: No Local Model Discovery

The Delegate cannot discover what models are available locally. It needs to be told exactly which model to use. For cloud providers this is fine (the user knows their API model names). For local models, discovery is valuable:

```python
# What users want:
models = await bridge.discover_deployed_models()
# Returns: [{"name": "my-sft-model", "endpoint": "ollama", "version": "v3"}, ...]
```

This requires querying Ollama's `/api/tags` endpoint and cross-referencing with AdapterRegistry.

### Gap 3: Cost Model Mismatch

The Delegate's `_estimate_cost()` function uses cloud API pricing. For local models, the cost is $0/token (compute cost is separate and not tracked by the Delegate). This means:

- `budget_usd=10.0` with a local model will never exhaust the budget
- Usage tracking shows unrealistically low costs

This is a known gap but low priority. Users running local models for cost reasons already know the cost model is different.

### Gap 4: No Capability Metadata

When routing between multiple agents (via Pipeline.router()), the router uses A2A capability cards to decide which agent handles a request. A fine-tuned model's capabilities are not automatically communicated -- the user must set the system prompt and tool definitions manually.

KaizenModelBridge could auto-populate system prompts based on the adapter's training metadata (e.g., "This model was fine-tuned on customer support data with the following format...").

## 4. Assessment

### Integration Complexity: LOW

The existing provider system already supports local models (Ollama and vLLM). KaizenModelBridge is a convenience layer that:

1. Resolves adapter metadata from AdapterRegistry
2. Detects deployment target (Ollama/vLLM)
3. Constructs the appropriate adapter + Delegate

Estimated implementation: 150-250 lines of production code. No changes to the Delegate or adapter system are needed.

### Recommended Approach

1. KaizenModelBridge uses the existing `OllamaStreamAdapter` for Ollama models
2. KaizenModelBridge uses the existing `OpenAIStreamAdapter` for vLLM models
3. `local_hf` strategy deferred to v1.1 (requires new adapter, low value)
4. Model discovery via Ollama REST API (`/api/tags`) -- straightforward
5. No modifications to the Delegate class itself
