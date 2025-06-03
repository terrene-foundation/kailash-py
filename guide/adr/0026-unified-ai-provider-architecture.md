# ADR-0026: Unified AI Provider Architecture

## Status
Accepted

Date: 2025-06-02

## Context

The initial implementation had separate provider architectures for LLM operations (`llm_providers.py`) and embedding operations (hardcoded in `embedding_generator.py`). This led to:
- Code duplication for providers supporting both capabilities (Ollama, OpenAI)
- Inconsistent interfaces between LLM and embedding operations
- Difficulty in maintaining provider configurations
- Redundant authentication and client management

## Decision

We will implement a **unified AI provider architecture** that combines LLM and embedding capabilities under a single provider framework:

1. **BaseAIProvider**: Abstract base for all providers
2. **LLMProvider**: Interface for chat/completion operations
3. **EmbeddingProvider**: Interface for embedding operations
4. **UnifiedAIProvider**: Combined interface for providers supporting both
5. **Provider Registry**: Single registry for all AI capabilities

### Architecture:
```
ai_providers.py
├── BaseAIProvider (ABC)
│   ├── is_available() → bool
│   └── get_capabilities() → List[str]
├── LLMProvider (BaseAIProvider)
│   └── chat(messages, **kwargs) → Dict
├── EmbeddingProvider (BaseAIProvider)
│   └── embed(texts, **kwargs) → List[List[float]]
└── UnifiedAIProvider (LLMProvider, EmbeddingProvider)
    ├── chat() [inherited]
    └── embed() [inherited]

Provider Implementations:
├── OllamaProvider (UnifiedAIProvider) - Both LLM & Embeddings
├── OpenAIProvider (UnifiedAIProvider) - Both LLM & Embeddings
├── AnthropicProvider (LLMProvider) - LLM only
├── CohereProvider (EmbeddingProvider) - Embeddings only
├── HuggingFaceProvider (EmbeddingProvider) - Embeddings only
└── MockProvider (UnifiedAIProvider) - Both for testing
```

### Key Design Improvements:
1. **Single Source of Truth**: One provider instance manages both capabilities
2. **Capability Detection**: `get_capabilities()` returns ["chat", "embeddings"] as applicable
3. **Shared Resources**: Single client instance, auth, and configuration
4. **Type Safety**: Provider type parameter ensures correct interface usage
5. **Backward Compatibility**: Falls back to legacy providers if unified not available

## Rationale

**Why a unified architecture?**
- Providers like Ollama and OpenAI support both LLM and embedding operations
- Maintaining separate provider implementations led to code duplication
- Unified interface simplifies provider management and capability discovery
- Shared authentication and client instances reduce resource usage

**Alternatives considered:**
1. **Keep separate providers**: Rejected due to code duplication
2. **Inheritance from single base**: Rejected as it would force all providers to implement both interfaces
3. **Composition pattern**: Rejected as it would complicate the provider API

## Consequences

### Positive:
- Eliminates code duplication between LLM and embedding providers
- Consistent interface for all AI operations
- Easier to add providers with multiple capabilities
- Better resource management (single client per provider)
- Clear capability discovery mechanism
- Simplified configuration and authentication

### Negative:
- More complex class hierarchy
- Breaking change for direct provider imports (mitigated by compatibility layer)
- Providers must declare their capabilities explicitly

## Implementation Notes

### Provider Selection:
```python
# Get provider for specific capability
from kailash.nodes.ai.ai_providers import get_provider

# For LLM operations
llm_provider = get_provider("ollama", "chat")

# For embedding operations
embed_provider = get_provider("ollama", "embeddings")

# Will raise error if capability not supported
cohere_llm = get_provider("cohere", "chat")  # Error: Cohere doesn't support chat
```

### Capability Discovery:
```python
from kailash.nodes.ai.ai_providers import get_available_providers

# Get all providers and their capabilities
providers = get_available_providers()
# Returns: {
#     "ollama": {"available": True, "chat": True, "embeddings": True},
#     "openai": {"available": False, "chat": True, "embeddings": True},
#     "anthropic": {"available": False, "chat": True, "embeddings": False},
#     "cohere": {"available": False, "chat": False, "embeddings": True},
#     ...
# }
```

### Adding a New Unified Provider:
```python
class GeminiProvider(UnifiedAIProvider):
    """Google Gemini with both LLM and embedding support."""

    def is_available(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY"))

    def get_capabilities(self) -> List[str]:
        return ["chat", "embeddings"]

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        # Implement Gemini chat API
        pass

    def embed(self, texts: List[str], **kwargs) -> List[List[float]]:
        # Implement Gemini embeddings API
        pass

# Register the provider
PROVIDERS["gemini"] = GeminiProvider
```

## Migration Path

1. **Phase 1**: Implement unified architecture with backward compatibility ✅ Complete
2. **Phase 2**: Update LLMAgentNode and EmbeddingGeneratorNode to use unified providers ✅ Complete
3. **Phase 3**: Deprecate separate `llm_providers.py` in favor of `ai_providers.py`
4. **Phase 4**: Remove legacy code after deprecation period

## Related ADRs

- [ADR-0024: LLM Agent Architecture](0024-llm-agent-architecture.md) - Superseded by this ADR

## References

- Strategy Pattern for provider selection
- Interface Segregation Principle (SOLID)
- Python multiple inheritance for unified interfaces
