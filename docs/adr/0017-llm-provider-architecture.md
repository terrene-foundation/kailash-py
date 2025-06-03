# ADR-0017: LLM Provider Architecture

## Status
Accepted

## Context
The LLMAgentNode node needs to support multiple LLM providers (OpenAI, Anthropic, Ollama, etc.) without becoming a monolithic class with provider-specific dependencies and logic.

## Decision
We will use a **provider-based architecture** with the following components:

1. **LLMAgentNode**: The main node that handles workflow integration, conversation memory, MCP context, and RAG
2. **LLMProvider**: Abstract base class defining the provider interface
3. **Provider Implementations**: Separate classes for each provider (OllamaProvider, OpenAIProvider, etc.)
4. **Provider Registry**: A registry mapping provider names to classes

### Architecture:
```
LLMAgentNode (nodes/ai/llm_agent.py)
    └── uses → LLMProvider (nodes/ai/llm_providers.py)
                    ├── OllamaProvider
                    ├── OpenAIProvider
                    ├── AnthropicProvider
                    └── MockProvider
```

### Key Design Principles:
1. **Single Responsibility**: Each provider manages its own implementation
2. **Dependency Isolation**: Provider-specific dependencies are isolated
3. **Consistent Interface**: All providers implement the same interface
4. **Graceful Degradation**: Missing providers don't break the system
5. **Easy Extension**: New providers can be added without modifying LLMAgentNode

## Consequences

### Positive:
- Clean separation of concerns
- Easy to add new providers
- Provider-specific optimizations possible
- Better testability
- No unnecessary dependencies
- LLMAgentNode remains focused on orchestration

### Negative:
- Slightly more complex than a single class
- Need to maintain provider registry
- Some code duplication across providers (mitigated by base class)

## Implementation

### Adding a New Provider:
1. Create a class inheriting from `LLMProvider`
2. Implement `is_available()` and `chat()` methods
3. Add to `PROVIDERS` registry
4. No changes needed to LLMAgentNode

### Example:
```python
class GeminiProvider(LLMProvider):
    def is_available(self) -> bool:
        # Check if Gemini API is configured
        return bool(os.getenv("GEMINI_API_KEY"))

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        # Implement Gemini API call
        pass

# Register the provider
PROVIDERS["gemini"] = GeminiProvider
```

## Usage
```python
# All providers use the same interface
result = LLMAgentNode().run(
    provider="ollama",  # or "openai", "anthropic", "mock"
    model="llama3.1:8b-instruct-q8_0",
    messages=[{"role": "user", "content": "Hello"}]
)
