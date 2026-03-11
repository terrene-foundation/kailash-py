# Azure Unified Provider Guide

**Version**: 0.9.0
**Last Updated**: 2026-01-16

## Overview

The Unified Azure Provider is a single intelligent provider that auto-detects and manages connections to both Azure OpenAI Service and Azure AI Foundry. Instead of requiring users to choose between separate providers, it automatically selects the correct backend based on your endpoint configuration.

### Why Unified?

Previously, Kaizen required separate configuration for Azure OpenAI Service and Azure AI Foundry, leading to:
- Configuration confusion between providers
- Missing features when using the wrong provider
- Manual backend selection for different use cases

The Unified Azure Provider solves these issues by:
- **Auto-detecting** the correct backend from your endpoint URL
- **Exposing capabilities** so you can check feature availability before use
- **Gracefully handling errors** with clear guidance when features aren't supported
- **Supporting legacy configuration** for backward compatibility

## Quick Start

### 1. Set Environment Variables

```bash
# Unified configuration (recommended)
export AZURE_ENDPOINT="https://your-resource.openai.azure.com"
export AZURE_API_KEY="your-api-key"

# Optional
export AZURE_DEPLOYMENT="gpt-4o"      # Default deployment
export AZURE_API_VERSION="2024-10-21" # API version (optional)
```

### 2. Use in Your Agent

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

config = BaseAgentConfig(
    llm_provider="azure",
    model="gpt-4o",
    temperature=0.7
)

agent = BaseAgent(config=config)
result = agent.run(prompt="What is the capital of France?")
```

### 3. Verify Configuration

```python
from kaizen.nodes.ai.ai_providers import get_provider

provider = get_provider("azure")
print(f"Available: {provider.is_available()}")
print(f"Backend: {provider.get_detected_backend()}")
print(f"Detection: {provider.get_detection_source()}")
```

## Configuration

### Environment Variables

#### Unified Variables (Recommended)

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_ENDPOINT` | Yes | Your Azure endpoint URL |
| `AZURE_API_KEY` | Yes | Your Azure API key |
| `AZURE_DEPLOYMENT` | No | Default deployment/model name |
| `AZURE_API_VERSION` | No | API version (default: 2024-10-21) |
| `AZURE_BACKEND` | No | Force backend: `openai` or `foundry` |

#### Legacy Variables (Backward Compatible)

For Azure OpenAI Service:
```bash
export AZURE_OPENAI_ENDPOINT="https://..."
export AZURE_OPENAI_API_KEY="..."
```

For Azure AI Foundry:
```bash
export AZURE_AI_INFERENCE_ENDPOINT="https://..."
export AZURE_AI_INFERENCE_API_KEY="..."
```

Legacy variables are checked if unified variables aren't set.

### Auto-Detection

The provider automatically detects which backend to use based on your endpoint URL:

| Endpoint Pattern | Detected Backend |
|------------------|------------------|
| `*.openai.azure.com` | Azure OpenAI Service |
| `*.inference.ai.azure.com` | Azure AI Foundry |
| `*.services.ai.azure.com` | Azure AI Foundry |
| Unknown patterns | Azure OpenAI (default) |

### Explicit Backend Override

Use `AZURE_BACKEND` to force a specific backend:

```bash
# Force Azure OpenAI Service
export AZURE_BACKEND="openai"

# Force Azure AI Foundry
export AZURE_BACKEND="foundry"
```

## Features

### Supported Features by Backend

| Feature | Azure OpenAI | AI Foundry |
|---------|--------------|------------|
| Chat completions | Yes | Yes |
| Embeddings | Yes | Yes |
| Streaming | Yes | Yes |
| Tool calling | Yes | Yes |
| Structured output (json_schema) | Yes | Yes |
| Vision (images) | Yes | Yes (degraded) |
| Audio input | Yes | No |
| Reasoning models (o1/o3/GPT-5) | Yes | No |
| Llama/Mistral models | No | Yes |
| Phi models | No | Yes |

### Feature Checking

```python
from kaizen.nodes.ai.ai_providers import get_provider

provider = get_provider("azure")

# Check all capabilities
caps = provider.get_capabilities()
print(f"Audio support: {caps.get('audio_input')}")
print(f"Reasoning models: {caps.get('reasoning_models')}")
print(f"Llama models: {caps.get('llama_models')}")

# Check specific feature
if provider.supports("audio_input"):
    # Use audio features
    pass
else:
    print("Audio not supported on this backend")
```

### Handling Feature Gaps

```python
from kaizen.nodes.ai.azure_capabilities import FeatureNotSupportedError

provider = get_provider("azure")

try:
    provider.check_feature("audio_input")
    # Proceed with audio
except FeatureNotSupportedError as e:
    print(f"Feature not available: {e.feature}")
    print(f"Required backend: {e.suggested_backend}")
    print(f"Guidance: {e.guidance}")
```

### Reasoning Models

The provider automatically handles reasoning models (o1, o3, GPT-5) by:
- Removing `temperature` parameter (not supported)
- Removing `top_p` parameter (not supported)
- Converting `max_tokens` to `max_completion_tokens`

```python
# Temperature is automatically filtered for reasoning models
response = provider.chat(
    messages=[{"role": "user", "content": "Solve this step by step"}],
    model="o1-preview",
    generation_config={"temperature": 0.7}  # Ignored for o1
)
```

## Migration

### From Legacy Configuration

1. **Update environment variables**:

```bash
# Old (Azure OpenAI)
export AZURE_OPENAI_ENDPOINT="https://myresource.openai.azure.com"
export AZURE_OPENAI_API_KEY="key123"

# New (unified)
export AZURE_ENDPOINT="https://myresource.openai.azure.com"
export AZURE_API_KEY="key123"
```

2. **Update provider usage**:

```python
# Old
from kaizen.nodes.ai.azure_openai_provider import AzureOpenAIProvider
provider = AzureOpenAIProvider()

# New
from kaizen.nodes.ai.ai_providers import get_provider
provider = get_provider("azure")
```

3. **Verify migration**:

```python
provider = get_provider("azure")
assert provider.is_available(), "Azure not configured"
assert provider.get_detected_backend() == "azure_openai"
```

### Verification Script

```python
"""Verify Azure Unified Provider configuration."""

from kaizen.nodes.ai.ai_providers import get_provider

def verify_azure_config():
    provider = get_provider("azure")

    # Check availability
    if not provider.is_available():
        print("ERROR: Azure not configured")
        print("Set AZURE_ENDPOINT and AZURE_API_KEY")
        return False

    # Check detection
    backend = provider.get_detected_backend()
    source = provider.get_detection_source()
    print(f"Backend: {backend}")
    print(f"Detection source: {source}")

    # Check capabilities
    caps = provider.get_capabilities()
    print(f"Capabilities: {caps}")

    # Test basic chat
    try:
        response = provider.chat(
            messages=[{"role": "user", "content": "Say 'hello'"}],
            model="gpt-4o"
        )
        print(f"Chat test: SUCCESS")
        print(f"Response: {response.get('content', '')[:50]}...")
    except Exception as e:
        print(f"Chat test: FAILED - {e}")
        return False

    return True

if __name__ == "__main__":
    success = verify_azure_config()
    exit(0 if success else 1)
```

## Troubleshooting

### Common Errors

#### "No Azure backend configured"

**Cause**: Neither unified nor legacy environment variables are set.

**Solution**:
```bash
export AZURE_ENDPOINT="https://your-resource.openai.azure.com"
export AZURE_API_KEY="your-api-key"
```

#### "Feature 'X' is not supported"

**Cause**: Requested feature not available on detected backend.

**Solution**: Check the feature matrix above. You may need to:
1. Use a different Azure resource/endpoint
2. Set `AZURE_BACKEND` to force the correct backend
3. Use a fallback approach in your code

#### "audience is incorrect"

**Cause**: Auto-detection selected wrong backend for your endpoint.

**Solution**:
```bash
# Force the correct backend
export AZURE_BACKEND="foundry"  # or "openai"
```

#### Temperature Not Supported (Reasoning Models)

**Cause**: o1/o3/GPT-5 models don't support temperature.

**Solution**: The provider automatically filters temperature for these models. No action needed.

#### JSON Schema Errors

**Cause**: API version doesn't support structured outputs.

**Solution**: Ensure you're using a recent API version:
```bash
export AZURE_API_VERSION="2024-10-21"
```

## Best Practices

### Configuration Management

1. **Use unified variables** for new projects
2. **Set AZURE_BACKEND** in CI/CD for deterministic behavior
3. **Store credentials securely** (Azure Key Vault, environment secrets)

### Error Handling

```python
from kaizen.nodes.ai.ai_providers import get_provider
from kaizen.nodes.ai.azure_capabilities import (
    FeatureNotSupportedError,
    FeatureDegradationWarning
)

provider = get_provider("azure")

try:
    response = provider.chat(messages, model="gpt-4o")
except FeatureNotSupportedError as e:
    # Feature not available - use fallback
    logger.warning(f"Feature {e.feature} not available: {e.guidance}")
    response = fallback_provider.chat(messages, model="gpt-4o")
except Exception as e:
    # Other errors
    logger.error(f"Azure chat failed: {e}")
    raise
```

### Performance Considerations

1. **Reuse provider instances** - Don't create new providers per request
2. **Check capabilities once** at startup, cache results
3. **Use appropriate timeouts** for your use case
4. **Consider rate limits** of your Azure resource

## API Reference

### UnifiedAzureProvider

```python
class UnifiedAzureProvider:
    def is_available() -> bool:
        """Check if Azure is configured."""

    def get_detected_backend() -> str:
        """Get detected backend: 'azure_openai' or 'azure_ai_foundry'."""

    def get_detection_source() -> str:
        """Get detection source: 'pattern', 'explicit', 'default', 'error_fallback'."""

    def get_capabilities() -> dict:
        """Get capability dictionary."""

    def supports(feature: str) -> bool:
        """Check if feature is supported."""

    def check_feature(feature: str) -> None:
        """Check feature, raise FeatureNotSupportedError if not supported."""

    def check_model_requirements(model: str) -> None:
        """Check model requirements, raise if not supported."""

    def chat(messages, model, **kwargs) -> dict:
        """Execute chat completion."""

    async def chat_async(messages, model, **kwargs) -> dict:
        """Execute async chat completion."""

    def embed(texts, **kwargs) -> list:
        """Generate embeddings."""
```

### Exceptions

```python
class FeatureNotSupportedError(Exception):
    feature: str           # Feature that's not supported
    current_backend: str   # Current detected backend
    suggested_backend: str # Backend that supports this feature
    guidance: str          # User guidance message

class FeatureDegradationWarning(Warning):
    feature: str           # Feature with degraded support
    guidance: str          # User guidance message
```

## See Also

- [LLM Provider Architecture](../architecture/adr/ADR-017-document-extraction-multi-provider-architecture.md)
- [Ollama Quickstart](./ollama-quickstart.md) - Local LLM alternative
- [Multi-Agent Coordination](./multi-agent-coordination.md) - Using Azure with agents
