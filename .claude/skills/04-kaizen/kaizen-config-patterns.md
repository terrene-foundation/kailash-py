# Kaizen Configuration Patterns

Complete guide to domain configs, BaseAgentConfig, and auto-conversion patterns in Kaizen.

## Core Concept: Domain Config Auto-Extraction

**Key Innovation**: Use domain-specific configs, BaseAgent auto-converts to BaseAgentConfig.

**Benefits:**

- ✅ No boilerplate BaseAgentConfig creation
- ✅ Keep domain-specific fields separate
- ✅ Type-safe configuration
- ✅ Cleaner, more maintainable code

## Pattern: Domain Config (Recommended)

```python
from kaizen.core.base_agent import BaseAgent
from dataclasses import dataclass

# Step 1: Define domain configuration
@dataclass
class QAConfig:
    """
    Domain-specific configuration for Q&A agents.
    NOT BaseAgentConfig - BaseAgent extracts what it needs.
    """
    # BaseAgent extracts these automatically:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7
    max_tokens: int = 1000

    # Domain-specific fields (BaseAgent ignores these):
    enable_fact_checking: bool = True
    min_confidence_threshold: float = 0.7
    max_retries: int = 3

# Step 2: Use directly with BaseAgent
class QAAgent(BaseAgent):
    def __init__(self, config: QAConfig):
        # BaseAgent auto-extracts: llm_provider, model, temperature, max_tokens
        super().__init__(config=config, signature=QASignature())
        self.qa_config = config  # Keep reference for domain fields

    def ask(self, question: str) -> dict:
        result = self.run(question=question)

        # Use domain-specific config
        if result.get("confidence", 0) < self.qa_config.min_confidence_threshold:
            if self.qa_config.enable_fact_checking:
                result = self._recheck_with_facts(result)

        return result
```

## What BaseAgent Auto-Extracts

BaseAgent looks for these fields in your domain config:

```python
# Core fields (extracted automatically)
llm_provider: str     # "openai", "anthropic", "ollama", "mock"
model: str            # Model name (from LLM_MODEL env var)
temperature: float    # Sampling temperature (0.0-2.0)
max_tokens: int       # Maximum tokens to generate

# Optional fields (extracted if present)
timeout: int          # Request timeout in seconds
retry_attempts: int   # Number of retries on failure
max_turns: int        # Enable BufferMemory if > 0
provider_config: dict # Provider-specific operational settings (api_version, deployment)
response_format: dict # Structured output config (json_schema, json_object) — v2.5.0+
structured_output_mode: str  # "auto" (deprecated), "explicit" (recommended), "off"
api_key: str          # Per-request API key override (BYOK)
base_url: str         # Per-request base URL override
```

**All other fields** are ignored by BaseAgent and available for your domain logic.

### Important: response_format vs provider_config (v2.5.0+)

These two fields serve different purposes:

- `response_format` — Structured output config sent to the LLM API. Use for `{"type": "json_schema", ...}` or `{"type": "json_object"}`.
- `provider_config` — Provider-specific operational settings. Use for `{"api_version": "2024-10-21"}`, `{"deployment": "my-gpt4"}`, etc.

**Never** put structured output keys (`type`, `json_schema`, `schema`) in `provider_config`. A deprecation shim will auto-migrate them, but new code should use `response_format` directly.

## Configuration Patterns

### 1. Basic Configuration

```python
@dataclass
class BasicConfig:
    """Minimal configuration for simple agents."""
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7

agent = SimpleQAAgent(BasicConfig())
```

### 2. Production Configuration

```python
@dataclass
class ProductionConfig:
    """Production-ready configuration with all features."""
    # Core LLM settings
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.3  # Lower for consistency
    max_tokens: int = 2000

    # Performance settings
    timeout: int = 60
    retry_attempts: int = 3

    # Memory settings
    max_turns: int = 50  # Enable BufferMemory with limit

    # Domain settings
    enable_logging: bool = True
    log_level: str = "INFO"
    enable_metrics: bool = True
```

### 3. Development Configuration

```python
@dataclass
class DevConfig:
    """Development configuration with debugging."""
    llm_provider: str = "mock"  # No API calls
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7
    max_tokens: int = 500

    # Debug settings
    debug: bool = True
    verbose: bool = True
    save_prompts: bool = True
```

### 4. Environment-Based Configuration

```python
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class EnvConfig:
    """Configuration from environment variables."""
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "1000"))

    # API keys loaded automatically by providers
    # OPENAI_API_KEY, ANTHROPIC_API_KEY from .env
```

### 5. Multi-Provider Configuration

```python
@dataclass
class MultiProviderConfig:
    """Support multiple LLM providers."""
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7
    max_tokens: int = 1000

    # Fallback provider
    fallback_provider: str = "anthropic"
    fallback_model: str = os.environ.get("LLM_MODEL", "")

    # Provider-specific settings
    provider_config: dict = None

    def __post_init__(self):
        if self.provider_config is None:
            self.provider_config = {
                "openai": {"api_version": "2024-01"},
                "anthropic": {"max_retries": 3}
            }
```

## FallbackRouter for Resilient LLM Routing

`FallbackRouter` extends `LLMRouter` with automatic fallback chains for handling provider failures and rate limits.

**Import**: `from kaizen.llm.routing.fallback import FallbackRouter, FallbackRejectedError`

```python
from kaizen.llm.routing.fallback import FallbackRouter, FallbackRejectedError

# Basic usage with fallback chain
router = FallbackRouter(
    primary_model=os.environ["LLM_MODEL"],
    fallback_chain=[os.environ.get("LLM_FALLBACK_MODEL", "")],
)

# Safety: on_fallback callback fires BEFORE each fallback attempt
def check_fallback(event):
    """Reject fallback to small models for critical tasks."""
    if event.fallback_model in SMALL_MODELS:
        raise FallbackRejectedError("Cannot downgrade for critical task")

router = FallbackRouter(
    primary_model=os.environ["LLM_MODEL"],
    fallback_chain=[os.environ.get("LLM_FALLBACK_MODEL", "")],
    on_fallback=check_fallback,  # Fires before each fallback
)
```

**Safety features**:

- `on_fallback` callback fires BEFORE each fallback (raise `FallbackRejectedError` to block)
- WARNING-level logging on every fallback event
- Capability validation skips incompatible models automatically

## Memory Configuration

### Enable Memory with max_turns

```python
@dataclass
class MemoryEnabledConfig:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    max_turns: int = 10  # Enable BufferMemory, keep last 10 turns

agent = MemoryAgent(MemoryEnabledConfig())

# Use session_id for memory continuity
result1 = agent.ask("My name is Alice", session_id="user123")
result2 = agent.ask("What's my name?", session_id="user123")
# Returns: "Your name is Alice"
```

### Disable Memory

```python
@dataclass
class NoMemoryConfig:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    max_turns: int = 0  # Disable memory (default)

agent = StatelessAgent(NoMemoryConfig())
```

## Provider-Specific Configuration

### OpenAI Configuration

```python
@dataclass
class OpenAIConfig:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7
    max_tokens: int = 1000

    # OpenAI-specific settings
    provider_config: dict = None

    def __post_init__(self):
        self.provider_config = {
            "api_version": "2024-01-01",
            "organization": "org-xyz",
            "seed": 42,  # Reproducibility
            "top_p": 0.9
        }
```

### Anthropic Configuration

```python
@dataclass
class AnthropicConfig:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7
    max_tokens: int = 2000

    provider_config: dict = None

    def __post_init__(self):
        self.provider_config = {
            "api_version": "2023-06-01",
            "max_retries": 3
        }
```

### Ollama Configuration (Local)

```python
@dataclass
class OllamaConfig:
    llm_provider: str = "ollama"
    model: str = "llama2"
    temperature: float = 0.7
    max_tokens: int = 1000

    provider_config: dict = None

    def __post_init__(self):
        self.provider_config = {
            "base_url": "http://localhost:11434",
            "num_gpu": 1
        }
```

### Azure Configuration (v2.5.0)

```python
@dataclass
class AzureConfig:
    """Azure configuration.

    Canonical env vars (v2.5.0+):
        export AZURE_ENDPOINT="https://your-endpoint.azure.com"
        export AZURE_API_KEY="your-key"
        export AZURE_API_VERSION="2024-10-21"

    Legacy env vars (deprecated, emit DeprecationWarning):
        AZURE_OPENAI_ENDPOINT, AZURE_AI_INFERENCE_ENDPOINT
        AZURE_OPENAI_API_KEY, AZURE_AI_INFERENCE_API_KEY
        AZURE_OPENAI_API_VERSION
    """
    llm_provider: str = "azure"
    model: str = os.environ.get("LLM_MODEL", "")  # Or any deployed model
    temperature: float = 0.7
    max_tokens: int = 1000

    # Provider-specific settings only (NOT structured output)
    provider_config: dict = None

    def __post_init__(self):
        self.provider_config = {
            "api_version": "2024-10-21"
        }
```

**Features**: Chat completions, vision/multi-modal support, embeddings, tool calling, async support.

**Azure with structured output** (use `response_format`, not `provider_config`):

```python
from kaizen.core.structured_output import create_structured_output_config

config = BaseAgentConfig(
    llm_provider="azure",
    model=os.environ["LLM_MODEL"],
    response_format=create_structured_output_config(MySignature(), strict=True),
    provider_config={"api_version": "2024-10-21"},  # Separate from response_format
    structured_output_mode="explicit",
)
```

### Docker Model Runner Configuration (v0.7.1)

```python
@dataclass
class DockerConfig:
    """Docker Model Runner configuration (FREE local inference).

    Prerequisites:
        1. Docker Desktop 4.40+ with Model Runner enabled
        2. Enable TCP access: docker desktop enable model-runner --tcp 12434
        3. Pull model: docker model pull ai/llama3.2
    """
    llm_provider: str = "docker"
    model: str = "ai/llama3.2"  # Or ai/qwen3, ai/gemma3, ai/mxbai-embed-large
    temperature: float = 0.7
    max_tokens: int = 1000

    provider_config: dict = None

    def __post_init__(self):
        self.provider_config = {
            "base_url": "http://localhost:12434/engines/llama.cpp/v1"
        }
```

**Features**: OpenAI-compatible API, GPU acceleration (Metal/CUDA/Vulkan), embeddings, model-dependent tool calling.

**Tool-Capable Models**: `ai/qwen3`, `ai/llama3.3`, `ai/gemma3` (check with `provider.supports_tools(model)`).

### Google Gemini Configuration (v0.8.2)

```python
@dataclass
class GoogleGeminiConfig:
    """Google Gemini configuration (Cloud, multimodal).

    Prerequisites:
        export GOOGLE_API_KEY="your-api-key"
        # Or: export GEMINI_API_KEY="your-api-key"

    Install dependency:
        pip install kailash-kaizen[google]
    """
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")  # Or "gemini" (alias)
    model: str = os.environ.get("LLM_MODEL", "") # Fast, efficient model
    temperature: float = 0.7
    max_tokens: int = 1000

    provider_config: dict = None

    def __post_init__(self):
        self.provider_config = {
            "top_p": 0.9,
            "top_k": 40
        }
```

**Available Models**:

- Chat: `gemini-2.0-flash`, `gemini-1.5-pro`, `gemini-1.5-flash`
- Embeddings: `text-embedding-004` (768 dimensions)

**Features**: Chat completions, vision/multimodal support, embeddings, tool calling, async support.

**Direct Provider Usage**:

```python
from kaizen.nodes.ai import GoogleGeminiProvider

provider = GoogleGeminiProvider()

# Chat
response = provider.chat(
    messages=[{"role": "user", "content": "Hello!"}],
    model=os.environ["LLM_MODEL"]
)

# Vision (multimodal)
import base64
with open("image.png", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

response = provider.chat(
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image"},
            {"type": "image", "base64": image_b64, "media_type": "image/png"}
        ]
    }],
    model=os.environ["LLM_MODEL"]
)

# Embeddings
embeddings = provider.embed(
    texts=["Hello world"],
    model="text-embedding-004"
)
# Returns: [[0.01, -0.02, ...]] (768-dim vectors)

# Async
response = await provider.chat_async(messages=[...], model=os.environ["LLM_MODEL"])
embeddings = await provider.embed_async(texts=[...], model="text-embedding-004")
```

## Configuration Validation

### With Validation Rules

```python
from typing import Optional

@dataclass
class ValidatedConfig:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7
    max_tokens: int = 1000
    timeout: int = 30

    def __post_init__(self):
        # Validate temperature
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError("temperature must be between 0.0 and 1.0")

        # Validate max_tokens
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")

        # Validate timeout
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")

        # Validate provider
        valid_providers = ["openai", "azure", "anthropic", "google", "gemini", "ollama", "docker", "cohere", "huggingface", "mock"]
        if self.llm_provider not in valid_providers:
            raise ValueError(f"Invalid provider: {self.llm_provider}")
```

## Configuration Hierarchy

### Base + Specialized Configs

```python
@dataclass
class BaseConfig:
    """Base configuration shared across agents."""
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7
    max_tokens: int = 1000

@dataclass
class ResearchConfig(BaseConfig):
    """Research agent specific configuration."""
    enable_web_search: bool = True
    max_sources: int = 5
    citation_style: str = "APA"

@dataclass
class CodeGenConfig(BaseConfig):
    """Code generation specific configuration."""
    target_language: str = "python"
    style_guide: str = "PEP8"
    include_tests: bool = True
```

## structured_output_mode Default Flip (v2.5.0)

Starting in v2.5.0, `structured_output_mode` defaults to `"auto"` but emits a `FutureWarning` on every agent instantiation. In v2.6.0 the default will change to `"explicit"`.

**What changed**: Previously, BaseAgent would auto-generate a `response_format` from the signature whenever `structured_output_mode` was not set. This hidden behavior caused confusion when the auto-generated config did not match user expectations (especially on Azure).

**Migration path**:

```python
# Before (implicit auto — triggers FutureWarning in v2.5.0)
config = BaseAgentConfig(
    llm_provider="openai",
    model=os.environ["LLM_MODEL"],
    # structured_output_mode defaults to "auto" — emits FutureWarning
)

# After (explicit — no warning, future-proof)
from kaizen.core.structured_output import create_structured_output_config

config = BaseAgentConfig(
    llm_provider="openai",
    model=os.environ["LLM_MODEL"],
    response_format=create_structured_output_config(MySignature(), strict=True),
    structured_output_mode="explicit",
)
```

**Timeline**:

- v2.5.0: `"auto"` is the default but emits `FutureWarning`
- v2.6.0: `"explicit"` becomes the default — `"auto"` still works but is opt-in only

## response_format Validation

The `response_format` field is validated at config construction time. It must contain a valid `"type"` key with one of three allowed values:

| `type` value    | Purpose                          | Requires `json_schema` key |
| --------------- | -------------------------------- | -------------------------- |
| `"json_schema"` | Strict structured output (100%)  | Yes                        |
| `"json_object"` | Best-effort JSON mode (70-85%)   | No                         |
| `"text"`        | Plain text response (no parsing) | No                         |

```python
# Valid:
response_format={"type": "json_schema", "json_schema": {"name": "r", "schema": {...}}}
response_format={"type": "json_object"}
response_format={"type": "text"}

# Invalid — raises ValueError at config time:
response_format={"json_schema": {...}}        # Missing "type" key
response_format={"type": "xml"}               # Unknown type
response_format={"type": "json_schema"}       # Missing json_schema key
```

## Three-Field Separation: response_format vs provider_config vs structured_output_mode

These three `BaseAgentConfig` fields serve distinct, non-overlapping purposes:

| Field                    | Scope                                     | Sent to LLM API | Example                                                  |
| ------------------------ | ----------------------------------------- | --------------- | -------------------------------------------------------- |
| `response_format`        | What the LLM should return                | Yes             | `{"type": "json_schema", "json_schema": {...}}`          |
| `provider_config`        | How the provider connection is configured | Depends         | `{"api_version": "2024-10-21", "deployment": "my-gpt4"}` |
| `structured_output_mode` | Whether Kaizen auto-generates format      | No (internal)   | `"explicit"`, `"auto"` (deprecated), `"off"`             |

**Decision tree**:

1. Need structured JSON from the LLM? Set `response_format`.
2. Need provider-specific operational settings (API version, deployment name, org ID)? Set `provider_config`.
3. Want to control whether Kaizen auto-generates `response_format` from your signature? Set `structured_output_mode`.

**A deprecation shim** in BaseAgentConfig detects structured output keys (`type`, `json_schema`, `schema`) inside `provider_config` and auto-migrates them to `response_format` with a `DeprecationWarning`. New code should never rely on this shim.

## The \_run_async_hook() Pattern for BaseAgent Async/Sync Bridging

BaseAgent provides `_run_async_hook()` as an internal helper for running async code from synchronous agent methods. This is used when a `run()` call needs to invoke async operations (provider calls, tool execution, MCP discovery) from a sync context.

**How it works**:

```python
# Inside BaseAgent (simplified)
def _run_async_hook(self, coro):
    """Run an async coroutine from sync context, handling event loop detection."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in async context — schedule on existing loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        # No loop — create one
        return asyncio.run(coro)
```

**When you encounter this**: If subclassing BaseAgent and overriding `run()`, use `_run_async_hook()` to call async methods:

```python
class MyAgent(BaseAgent):
    def run(self, **kwargs):
        # Need to call an async method from sync run()
        result = self._run_async_hook(self._async_process(kwargs))
        return result

    async def _async_process(self, kwargs):
        # Async logic here
        return await self.provider.chat_async(...)
```

**Why this matters**: Naive `asyncio.run()` fails when called inside an already-running event loop (e.g., inside FastAPI, Jupyter, or nested agent calls). `_run_async_hook()` detects the context and handles both cases.

## MCP Auto-Discovery on First run()

When an agent is configured with MCP tools but `discover()` has not been called, BaseAgent automatically triggers MCP discovery on the first `run()` call.

**Behavior**:

```python
from kaizen.core.base_agent import BaseAgent

# Agent configured with MCP but no explicit discover()
agent = MyAgent(config=config, signature=sig)
agent.add_mcp_server("my-server", url="http://localhost:3000")

# First run() triggers auto-discovery before execution
result = agent.run(input="Hello")
# Internally: discovers MCP tools → registers them → then executes
```

**Key details**:

- Auto-discovery runs once per agent instance, on the first `run()` call only
- Subsequent `run()` calls skip discovery (tools are cached)
- If you call `agent.discover()` explicitly before `run()`, auto-discovery is skipped
- Discovery failures raise `MCPDiscoveryError` — they do not silently degrade

**When to call discover() explicitly**: When you need to inspect available tools before running, or when you want to handle discovery errors separately from execution errors.

## Anti-Patterns (DON'T DO THIS)

### ❌ Manual BaseAgentConfig Creation

```python
# WRONG - Don't do this!
from kaizen.core.config import BaseAgentConfig

agent_config = BaseAgentConfig(
    llm_provider=config.llm_provider,
    model=config.model,
    temperature=config.temperature,
    max_tokens=config.max_tokens
)
super().__init__(config=agent_config, ...)
```

### ✅ Use Auto-Conversion Instead

```python
# RIGHT - Let BaseAgent do the work
super().__init__(config=config, ...)
```

### ❌ Structured Output in provider_config (Deprecated)

```python
# WRONG - provider_config is for provider settings, not structured output
config = BaseAgentConfig(
    provider_config={"type": "json_schema", "json_schema": {...}}  # DEPRECATED
)
```

### ✅ Use response_format Instead

```python
# RIGHT - response_format is the dedicated field for structured output
config = BaseAgentConfig(
    response_format={"type": "json_schema", "json_schema": {...}},
    structured_output_mode="explicit",
)
```

### ❌ Auto-Generated Config Without Understanding

```python
# RISKY - auto-generates invisible config from signature (deprecated mode)
config = BaseAgentConfig(
    llm_provider="openai",
    model=os.environ["LLM_MODEL"],
    # structured_output_mode defaults to "auto" — generates config you never see
)
```

### ✅ Explicit Config You Control

```python
# RIGHT - you see exactly what config is being sent
config = BaseAgentConfig(
    llm_provider="openai",
    model=os.environ["LLM_MODEL"],
    response_format=create_structured_output_config(MySignature(), strict=True),
    structured_output_mode="explicit",
)
```

## Configuration Testing

```python
def test_config_auto_extraction():
    """Test that domain config is properly extracted."""
    @dataclass
    class TestConfig:
        llm_provider: str = "mock"
        model: str = "test-model"
        temperature: float = 0.5
        custom_field: str = "custom_value"  # Ignored by BaseAgent

    agent = TestAgent(TestConfig())

    # BaseAgent extracted core fields
    assert agent.config.llm_provider == "mock"
    assert agent.config.model == "test-model"
    assert agent.config.temperature == 0.5

    # Domain config still accessible
    assert agent.domain_config.custom_field == "custom_value"
```

## CRITICAL RULES

**ALWAYS:**

- ✅ Use domain configs (e.g., `QAConfig`, `RAGConfig`)
- ✅ Let BaseAgent auto-extract core fields
- ✅ Keep domain-specific fields in domain config
- ✅ Load `.env` with `load_dotenv()` before creating configs

**NEVER:**

- ❌ Create BaseAgentConfig manually
- ❌ Mix BaseAgent fields with domain fields in BaseAgentConfig
- ❌ Skip config validation for production code
- ❌ Hardcode API keys in config (use environment variables)

## Related Skills

- **kaizen-baseagent-quick** - Using configs with BaseAgent
- **kaizen-ux-helpers** - Config convenience methods
- **kaizen-agent-execution** - Config-based execution patterns

## References

- **Source**: `kaizen/core/config.py`
- **Examples**: All agents in the Kaizen examples/`
- **Specialist**: `.claude/agents/frameworks/kaizen-specialist.md` lines 249-267
