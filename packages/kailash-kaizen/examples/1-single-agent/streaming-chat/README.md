# Streaming Chat Agent

Real-time token streaming for interactive chat applications using `StreamingStrategy`.

## Overview

This example demonstrates how to build a streaming chat agent that displays responses token-by-token in real-time, providing immediate feedback for interactive experiences.

## Features

- **Real-time streaming**: Token-by-token display with async iteration
- **Dual modes**: Both streaming and non-streaming execution
- **Configurable chunks**: Control throughput vs latency tradeoff
- **Built on BaseAgent**: Enterprise features (logging, error handling, performance tracking)

## Use Cases

1. **Interactive Chatbots**: Display responses as they're generated
2. **Long-form Content**: Show progress during lengthy generation
3. **Conversational AI**: Immediate feedback improves user experience
4. **Streaming APIs**: Build real-time chat endpoints

## Quick Start

### Streaming Mode

```python
import asyncio
from workflow import StreamChatAgent, ChatConfig

# Configure streaming mode
config = ChatConfig(
    streaming=True,
    llm_provider="openai",
    model="gpt-3.5-turbo",
    chunk_size=1  # Token-by-token
)

agent = StreamChatAgent(config)

# Stream response token-by-token
async def chat():
    async for token in agent.stream_chat("What is Python?"):
        print(token, end="", flush=True)

asyncio.run(chat())
```

### Non-Streaming Mode

```python
from workflow import StreamChatAgent, ChatConfig

# Configure non-streaming mode
config = ChatConfig(
    streaming=False,
    llm_provider="openai",
    model="gpt-3.5-turbo"
)

agent = StreamChatAgent(config)

# Get complete response
response = agent.chat("What is machine learning?")
print(response)
```

## Configuration Options

```python
@dataclass
class ChatConfig:
    llm_provider: str = "openai"        # LLM provider
    model: str = "gpt-3.5-turbo"        # Model name
    temperature: float = 0.7            # Generation temperature
    max_tokens: int = 500               # Max response length
    streaming: bool = True              # Enable streaming
    chunk_size: int = 1                 # Tokens per chunk
```

### Chunk Size Guide

- `chunk_size=1`: Token-by-token (lowest latency, most overhead)
- `chunk_size=5`: Small chunks (balanced)
- `chunk_size=10`: Large chunks (highest throughput, less real-time feel)

## Architecture

```
StreamChatAgent (BaseAgent)
    ├── StreamingStrategy (async streaming)
    │   ├── stream() → AsyncIterator[str]
    │   └── execute() → Dict[str, Any]
    ├── ChatSignature (I/O structure)
    │   ├── Input: message
    │   └── Output: response
    └── BaseAgent Features
        ├── LoggingMixin
        ├── PerformanceMixin
        └── ErrorHandlingMixin
```

## StreamingStrategy API

### `stream(agent, inputs)` → AsyncIterator[str]

Stream execution results token-by-token.

```python
async for token in strategy.stream(agent, {"message": "Hello"}):
    print(token, end="", flush=True)
```

### `execute(agent, inputs)` → Dict[str, Any]

Execute and return final result (for compatibility).

```python
result = await strategy.execute(agent, {"message": "Hello"})
# Returns: {"response": "...", "chunks": 42, "streamed": True}
```

## Performance

- **Streaming latency**: ~10ms per token
- **Non-streaming**: Standard BaseAgent execution
- **Memory**: Minimal overhead (chunks processed incrementally)

## Testing

Run the comprehensive test suite:

```bash
pytest tests/unit/examples/test_streaming_chat.py -v
```

Tests cover:
- Agent initialization with StreamingStrategy
- Async streaming iteration
- Chunk yielding and reconstruction
- Error handling for non-streaming mode
- Multiple sequential streams
- Integration with BaseAgent

## Demo

Run the example:

```bash
cd examples/1-single-agent/streaming-chat
python workflow.py
```

Output:
```
Streaming Chat Demo
==================================================

Question: What is Python?

Streaming response: This is a streaming response from the agent with multiple tokens.

Non-Streaming Chat Demo
==================================================

Question: What is machine learning?

Response: This is a streaming response from the agent with multiple tokens.
```

## Integration with Core SDK

Convert to workflow node:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create agent
agent = StreamChatAgent(config)

# Convert to workflow node
workflow = WorkflowBuilder()
workflow.add_node_instance(agent)

# Execute via Core SDK
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Next Steps

1. **Try different chunk sizes** to optimize latency vs throughput
2. **Add memory** to maintain conversation context across turns
3. **Integrate with web frameworks** (FastAPI streaming endpoints)
4. **Build multi-turn conversations** with session management

## Related Examples

- `simple-qa/` - Basic Q&A without streaming
- `memory-agent/` - Memory-enabled conversations
- `batch-processing/` - Parallel batch processing for throughput
- `rag-research/` - RAG with vector memory

## References

- `src/kaizen/strategies/streaming.py` - StreamingStrategy implementation
- `tests/unit/strategies/test_streaming_strategy.py` - Strategy tests
- ADR-006: Agent Base Architecture
