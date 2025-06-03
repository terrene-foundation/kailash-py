# ADR-0024: LLM Agent Architecture for Real Integration

## Status

Proposed

Date: 2025-06-01

## Context

The Kailash Python SDK currently contains mock AI agent implementations that don't support real Large Language Model (LLM) integration. Client projects using LangChain and Langgraph require production-ready LLM agents with actual model integration, conversation memory, tool calling, and sophisticated prompt management.

Key drivers for this decision include:

1. **Client Requirements**: Active projects need real LLM integration, not mock implementations
2. **LangChain Compatibility**: Seamless integration with existing LangChain/Langgraph workflows
3. **Multi-Provider Support**: Support for OpenAI, Anthropic, Azure OpenAI, and other providers
4. **Advanced Features**: Conversation memory, tool calling, function execution, and prompt optimization
5. **Production Readiness**: Reliable, scalable LLM agent capabilities for production deployments

The current mock implementations (`ChatAgent`, `RetrievalAgent`, etc.) are placeholders that return static responses, making them unsuitable for real agentic workflows.

## Decision

Implement a comprehensive LLM Agent architecture consisting of:

1. **LLMAgentNode Node**: Core agent with real model integration
2. **Provider Abstraction**: Unified interface for multiple LLM providers
3. **Memory Management**: Conversation history and context persistence
4. **Tool Integration**: Function calling and external tool execution
5. **Prompt Engineering**: Template management and optimization
6. **LangChain Compatibility**: Native integration with LangChain ecosystem

The LLM Agent architecture will be designed as:
- **Provider-Agnostic**: Support multiple LLM providers with consistent interface
- **Memory-Aware**: Sophisticated conversation memory and context management
- **Tool-Enabled**: Native support for function calling and tool execution
- **Observable**: Comprehensive logging of model interactions and decisions
- **Configurable**: Flexible configuration for different use cases and providers

## Rationale

### Why Real LLM Integration is Critical

1. **Client Demand**: Active projects require production-ready LLM capabilities
2. **Competitive Necessity**: Mock implementations are insufficient for real agentic workflows
3. **Ecosystem Integration**: Need to integrate with LangChain/Langgraph ecosystem
4. **Advanced Capabilities**: Tool calling and function execution are essential for agentic systems
5. **Production Readiness**: Clients need reliable, scalable LLM agent solutions

### Alternatives Considered

1. **Continue with Mock Implementations**: Keep current placeholder agents
   - **Rejected**: Doesn't meet client requirements for real LLM integration

2. **Wrapper-Only Approach**: Simple wrapper around LangChain agents
   - **Rejected**: Would limit customization and optimization for Kailash workflows

3. **Single Provider Focus**: Implement only OpenAI integration initially
   - **Rejected**: Clients need multi-provider support for flexibility and cost optimization

4. **External Service Only**: LLM integration only through external API calls
   - **Rejected**: Limits functionality and increases latency for complex workflows

## Consequences

### Positive

- **Client Satisfaction**: Directly addresses urgent client requirements for real LLM integration
- **Production Readiness**: Enables deployment of actual agentic workflows
- **LangChain Compatibility**: Seamless integration with existing client codebases
- **Multi-Provider Flexibility**: Cost optimization and vendor independence
- **Advanced Capabilities**: Tool calling, memory, and sophisticated prompt management
- **Competitive Advantage**: Production-ready LLM agents differentiate the SDK

### Negative

- **Implementation Complexity**: Real LLM integration is significantly more complex than mocks
- **API Dependencies**: Requires external LLM provider APIs and authentication
- **Cost Implications**: Real model usage incurs API costs
- **Rate Limiting**: Need to handle provider rate limits and quotas
- **Error Handling**: Complex error scenarios with external API dependencies
- **Token Management**: Need sophisticated token counting and optimization

### Neutral

- **Configuration Complexity**: More configuration options for providers and models
- **Testing Challenges**: Need both unit tests with mocks and integration tests with real APIs
- **Documentation Requirements**: Comprehensive documentation for provider setup and usage

## Implementation Notes

### Core Components

1. **LLMAgentNode Node**:
   - Unified interface for LLM interactions
   - Provider abstraction layer
   - Conversation memory management
   - Tool calling and function execution
   - Prompt template processing

2. **Provider Implementations**:
   - **OpenAIProvider**: GPT-3.5, GPT-4, GPT-4 Turbo support
   - **AnthropicProvider**: Claude 3 Haiku, Sonnet, Opus support
   - **AzureOpenAIProvider**: Azure-hosted OpenAI models
   - **LangChainProvider**: Generic LangChain LLM wrapper

3. **Memory Systems**:
   - **ConversationMemory**: Simple conversation history
   - **SummaryMemory**: Conversation summarization for long contexts
   - **VectorMemory**: Semantic similarity-based retrieval
   - **EntityMemory**: Entity tracking across conversations

4. **Tool Framework**:
   - **FunctionTool**: Python function calling
   - **APITool**: External API integration
   - **WorkflowTool**: Execute sub-workflows as tools
   - **CustomTool**: User-defined tool implementations

### Configuration Examples

1. **OpenAI Integration**:
```python
workflow.add_node("LLMAgentNode", "ai_assistant", config={
    "provider": "openai",
    "model": "gpt-4",
    "api_key": "${OPENAI_API_KEY}",
    "temperature": 0.7,
    "max_tokens": 2048,
    "memory": {
        "type": "conversation",
        "max_history": 10
    },
    "tools": [
        {"name": "search_web", "function": "web_search_tool"},
        {"name": "calculate", "function": "math_calculator"}
    ]
})
```

2. **Anthropic Integration**:
```python
workflow.add_node("LLMAgentNode", "claude_agent", config={
    "provider": "anthropic",
    "model": "claude-3-sonnet-20240229",
    "api_key": "${ANTHROPIC_API_KEY}",
    "max_tokens": 4096,
    "memory": {
        "type": "summary",
        "max_history": 20,
        "summary_threshold": 10
    },
    "system_prompt": "You are a helpful data analysis assistant."
})
```

3. **LangChain Integration**:
```python
workflow.add_node("LLMAgentNode", "langchain_agent", config={
    "provider": "langchain",
    "agent_type": "openai-functions",
    "llm": {
        "provider": "openai",
        "model": "gpt-3.5-turbo"
    },
    "tools": ["serpapi", "llm-math"],
    "memory": {"type": "vector", "vectorstore": "chroma"}
})
```

### Memory Management

1. **Conversation Memory**:
```python
memory_config = {
    "type": "conversation",
    "max_history": 10,
    "include_system": True,
    "format": "langchain"
}
```

2. **Summary Memory**:
```python
memory_config = {
    "type": "summary",
    "summarizer": {
        "provider": "openai",
        "model": "gpt-3.5-turbo",
        "max_tokens": 500
    },
    "trigger_length": 4000
}
```

3. **Vector Memory**:
```python
memory_config = {
    "type": "vector",
    "embeddings": {
        "provider": "openai",
        "model": "text-embedding-ada-002"
    },
    "vectorstore": "chroma",
    "similarity_threshold": 0.8
}
```

### Tool Integration

1. **Function Tools**:
```python
def calculate_sum(numbers):
    """Calculate the sum of a list of numbers."""
    return sum(numbers)

tools_config = [
    {
        "name": "calculate_sum",
        "function": calculate_sum,
        "description": "Calculate the sum of numbers"
    }
]
```

2. **API Tools**:
```python
tools_config = [
    {
        "name": "weather_api",
        "type": "api",
        "url": "https://api.weather.com/v1/current",
        "method": "GET",
        "auth": {"type": "api_key", "key": "${WEATHER_API_KEY}"}
    }
]
```

## Alternatives Considered

### 1. LangChain-Only Implementation
**Description**: Use only LangChain for all LLM interactions without custom abstraction.
**Pros**: Faster implementation, leverages existing ecosystem
**Cons**: Less flexibility, tight coupling to LangChain evolution
**Verdict**: Rejected - Need custom optimization for Kailash workflows

### 2. Streaming-First Architecture
**Description**: Design around streaming responses as the primary interface.
**Pros**: Better user experience, lower perceived latency
**Cons**: Complexity in workflow state management, not all providers support streaming
**Verdict**: Future enhancement - initial implementation supports both streaming and batch

### 3. Local Model Support
**Description**: Include support for locally-hosted models (Ollama, LocalAI).
**Pros**: No API costs, data privacy, offline capability
**Cons**: Deployment complexity, performance variability
**Verdict**: Future enhancement - focus on cloud providers initially

### 4. Multi-Modal Integration
**Description**: Include vision and audio capabilities from the start.
**Pros**: Future-ready for multi-modal workflows
**Cons**: Adds complexity, not all providers support multi-modal
**Verdict**: Phase 2 feature - focus on text-based agents initially

## Related ADRs

- [ADR-0022: MCP Integration Architecture](0022-mcp-integration-architecture.md) - Context sharing with MCP protocol
- [ADR-0023: A2A Communication Architecture](0023-a2a-communication-architecture.md) - Agent coordination and communication
- [ADR-0015: API Integration Architecture](0015-api-integration-architecture.md) - Foundation for external API integration
- [ADR-0016: Immutable State Management](0016-immutable-state-management.md) - State management for agent memory
- [ADR-0014: Async Node Execution](0014-async-node-execution.md) - Async patterns for LLM API calls

## References

- [OpenAI API Documentation](https://platform.openai.com/docs/api-reference)
- [Anthropic Claude API Documentation](https://docs.anthropic.com/claude/reference/getting-started-with-the-api)
- [LangChain Agent Documentation](https://python.langchain.com/docs/modules/agents/)
- [LangGraph Multi-Agent Patterns](https://langchain-ai.github.io/langgraph/concepts/multi_agent/)
- [Client Agentic Workflow Requirements](../../todos/000-master.md)
- [Function Calling Best Practices](https://platform.openai.com/docs/guides/function-calling)
