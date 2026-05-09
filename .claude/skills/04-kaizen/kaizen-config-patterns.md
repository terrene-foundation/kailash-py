# Kaizen Configuration Patterns

## Core Concept: Domain Config Auto-Extraction

Use domain-specific configs; BaseAgent auto-converts to BaseAgentConfig. No boilerplate.

```python
from kaizen.core.base_agent import BaseAgent
from dataclasses import dataclass

@dataclass
class QAConfig:
    # BaseAgent extracts these automatically:
    llm_provider: str = "openai"
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7
    max_tokens: int = 1000
    # Domain-specific (BaseAgent ignores):
    enable_fact_checking: bool = True
    min_confidence_threshold: float = 0.7

class QAAgent(BaseAgent):
    def __init__(self, config: QAConfig):
        super().__init__(config=config, signature=QASignature())
        self.qa_config = config
```

## Auto-Extracted Fields

```python
# Core (always extracted)
llm_provider: str     # "openai", "anthropic", "ollama", "mock"
model: str            # Model name
temperature: float    # 0.0-1.0
max_tokens: int

# Optional (extracted if present)
timeout: int          # Request timeout seconds
retry_attempts: int
max_turns: int        # Enable BufferMemory if > 0
provider_config: dict # Provider-specific settings
```

All other fields ignored by BaseAgent, available for domain logic.

## Configuration Variants

```python
# Production
@dataclass
class ProductionConfig:
    llm_provider: str = "openai"
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.3
    max_tokens: int = 2000
    timeout: int = 60
    retry_attempts: int = 3
    max_turns: int = 50

# Development
@dataclass
class DevConfig:
    llm_provider: str = "mock"  # No API calls
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7
    debug: bool = True

# Environment-based
@dataclass
class EnvConfig:
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    model: str = os.getenv("LLM_MODEL", "gpt-4")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
```

## FallbackRouter

```python
from kaizen.llm.routing.fallback import FallbackRouter, FallbackRejectedError

router = FallbackRouter(
    primary_model=os.environ["LLM_MODEL"],
    fallback_chain=["claude-3-opus", "gemini-pro"],
)

# Safety: on_fallback fires BEFORE each fallback attempt
def check_fallback(event):
    if event.fallback_model in SMALL_MODELS:
        raise FallbackRejectedError("Cannot downgrade for critical task")

router = FallbackRouter(
    primary_model=os.environ["LLM_MODEL"],
    fallback_chain=["claude-3-opus"],
    on_fallback=check_fallback,
)
```

## Memory Configuration

```python
@dataclass
class MemoryConfig:
    llm_provider: str = "openai"
    model: str = os.environ.get("LLM_MODEL", "")
    max_turns: int = 10  # Enable BufferMemory, 0 = disabled

agent = MemoryAgent(MemoryConfig())
result1 = agent.ask("My name is Alice", session_id="user123")
result2 = agent.ask("What's my name?", session_id="user123")  # "Alice"
```

## Provider Configs

```python
# OpenAI
@dataclass
class OpenAIConfig:
    llm_provider: str = "openai"
    model: str = os.environ.get("LLM_MODEL", "")
    provider_config: dict = None
    def __post_init__(self):
        self.provider_config = {"api_version": "2024-01-01", "seed": 42, "top_p": 0.9}

# Anthropic
@dataclass
class AnthropicConfig:
    llm_provider: str = "anthropic"
    model: str = "claude-3-opus-20240229"
    provider_config: dict = None
    def __post_init__(self):
        self.provider_config = {"api_version": "2023-06-01", "max_retries": 3}

# Ollama (local)
@dataclass
class OllamaConfig:
    llm_provider: str = "ollama"
    model: str = "llama2"
    provider_config: dict = None
    def __post_init__(self):
        self.provider_config = {"base_url": "http://localhost:11434", "num_gpu": 1}

# Azure AI Foundry (v0.7.1) — requires AZURE_AI_INFERENCE_ENDPOINT + AZURE_AI_INFERENCE_API_KEY
@dataclass
class AzureConfig:
    llm_provider: str = "azure"
    model: str = "gpt-4o"
    provider_config: dict = None
    def __post_init__(self):
        self.provider_config = {"api_version": "2024-02-01"}

# Docker Model Runner (v0.7.1) — FREE local, requires Docker Desktop 4.40+
@dataclass
class DockerConfig:
    llm_provider: str = "docker"
    model: str = "ai/llama3.2"  # Or ai/qwen3, ai/gemma3
    provider_config: dict = None
    def __post_init__(self):
        self.provider_config = {"base_url": "http://localhost:12434/engines/llama.cpp/v1"}

# Google Gemini (v0.8.2) — requires GOOGLE_API_KEY, pip install kailash-kaizen[google]
@dataclass
class GoogleGeminiConfig:
    llm_provider: str = "google"  # Or "gemini" alias
    model: str = "gemini-2.0-flash"
    provider_config: dict = None
    def __post_init__(self):
        self.provider_config = {"top_p": 0.9, "top_k": 40}
```

Google Gemini models: Chat (`gemini-2.0-flash`, `gemini-1.5-pro`), Embeddings (`text-embedding-004`, 768-dim).
Docker tool-capable models: `ai/qwen3`, `ai/llama3.3`, `ai/gemma3`.

## Google Gemini Direct Provider

```python
from kaizen.nodes.ai import GoogleGeminiProvider

provider = GoogleGeminiProvider()

# Chat
response = provider.chat(messages=[{"role": "user", "content": "Hello!"}], model="gemini-2.0-flash")

# Vision (multimodal)
import base64
with open("image.png", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()
response = provider.chat(messages=[{"role": "user", "content": [
    {"type": "text", "text": "Describe this image"},
    {"type": "image", "base64": image_b64, "media_type": "image/png"}
]}], model="gemini-2.0-flash")

# Embeddings
embeddings = provider.embed(texts=["Hello world"], model="text-embedding-004")  # 768-dim

# Async
response = await provider.chat_async(messages=[...], model="gemini-2.0-flash")
embeddings = await provider.embed_async(texts=[...], model="text-embedding-004")
```

## Configuration Validation

```python
@dataclass
class ValidatedConfig:
    llm_provider: str = "openai"
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7
    max_tokens: int = 1000
    timeout: int = 30

    def __post_init__(self):
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError("temperature must be between 0.0 and 1.0")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        valid_providers = ["openai", "azure", "anthropic", "google", "gemini",
                          "ollama", "docker", "cohere", "huggingface", "mock"]
        if self.llm_provider not in valid_providers:
            raise ValueError(f"Invalid provider: {self.llm_provider}")
```

## Config Hierarchy

```python
@dataclass
class BaseConfig:
    llm_provider: str = "openai"
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.7

@dataclass
class ResearchConfig(BaseConfig):
    enable_web_search: bool = True
    max_sources: int = 5

@dataclass
class CodeGenConfig(BaseConfig):
    target_language: str = "python"
    include_tests: bool = True
```

## MUST / MUST NOT

- MUST use domain configs (e.g., `QAConfig`, `RAGConfig`) -- let BaseAgent auto-extract
- MUST load `.env` with `load_dotenv()` before creating configs
- MUST NOT create BaseAgentConfig manually
- MUST NOT hardcode API keys in config (use environment variables)

## Anti-Pattern

```python
# WRONG
from kaizen.core.config import BaseAgentConfig
agent_config = BaseAgentConfig(llm_provider=config.llm_provider, model=config.model, ...)
super().__init__(config=agent_config, ...)

# RIGHT
super().__init__(config=config, ...)  # Auto-extraction
```
