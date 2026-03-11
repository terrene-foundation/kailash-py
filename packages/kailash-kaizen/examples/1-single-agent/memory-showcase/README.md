# Memory Systems Showcase

This example demonstrates all 4 memory types available in Kaizen, showing their unique capabilities and use cases.

## Overview

Kaizen provides 4 memory types for conversation management, each optimized for different scenarios:

### 1. BufferMemory
- **Purpose**: Full conversation history with FIFO limiting
- **Use Case**: Short-term conversations, chat applications, debugging
- **Configuration**: `max_turns` parameter (None = unlimited)
- **Example**:
  ```python
  from kaizen.memory.buffer import BufferMemory
  memory = BufferMemory(max_turns=10)
  ```

### 2. SummaryMemory
- **Purpose**: LLM-generated summaries + recent verbatim turns
- **Use Case**: Long conversations requiring context compression
- **Configuration**: `keep_recent` parameter, custom summarizer
- **Example**:
  ```python
  from kaizen.memory.summary import SummaryMemory
  memory = SummaryMemory(keep_recent=5)
  ```

### 3. VectorMemory
- **Purpose**: Semantic search over conversation history
- **Use Case**: Large knowledge bases, RAG applications
- **Configuration**: `top_k`, `similarity_threshold`, custom embedder
- **Example**:
  ```python
  from kaizen.memory.vector import VectorMemory
  memory = VectorMemory(top_k=3)
  ```

### 4. KnowledgeGraphMemory
- **Purpose**: Entity extraction and relationship tracking
- **Use Case**: Complex multi-entity conversations
- **Configuration**: Custom entity extractor
- **Example**:
  ```python
  from kaizen.memory.knowledge_graph import KnowledgeGraphMemory
  memory = KnowledgeGraphMemory()
  ```

## Running the Demo

```bash
cd examples/1-single-agent/memory-showcase
python demo.py
```

The demo will run 6 demonstrations:
1. **BufferMemory** - Shows FIFO limiting with max_turns
2. **SummaryMemory** - Shows automatic summarization
3. **VectorMemory** - Shows semantic search capabilities
4. **KnowledgeGraphMemory** - Shows entity extraction
5. **No Memory** - Baseline comparison (stateless agent)
6. **Session Isolation** - Shows parallel session management

## Key Concepts Demonstrated

### Same Agent, Different Memory Backends
The demo uses the same `DemoAgent` class with different memory types to show how memory affects behavior:

```python
from kaizen.memory.buffer import BufferMemory
from kaizen.memory.summary import SummaryMemory

# Same agent, different memory
buffer_agent = DemoAgent(config, memory=BufferMemory(max_turns=5))
summary_agent = DemoAgent(config, memory=SummaryMemory(keep_recent=3))
```

### Memory vs. No Memory
Compare stateful (with memory) vs. stateless (without memory) execution:

```python
# With memory - can reference previous turns
agent_with_memory = DemoAgent(config, memory=BufferMemory())
agent_with_memory.ask("What is Python?", session_id="session1")
agent_with_memory.ask("Tell me more about it", session_id="session1")  # Works!

# Without memory - each query is independent
agent_no_memory = DemoAgent(config, memory=None)
agent_no_memory.ask("What is Python?")
agent_no_memory.ask("Tell me more about it")  # Loses context
```

### Multi-Turn Conversations
Memory enables agents to maintain context across multiple turns:

```python
agent = DemoAgent(config, memory=BufferMemory())
agent.ask("My name is Alice", session_id="session1")
agent.ask("What's my name?", session_id="session1")  # Returns: Alice
```

### Session Isolation
Multiple sessions can run in parallel without cross-contamination:

```python
agent = DemoAgent(config, memory=BufferMemory())

# Session 1
agent.ask("My name is Alice", session_id="session1")

# Session 2
agent.ask("My name is Bob", session_id="session2")

# Each session maintains separate context
agent.ask("What's my name?", session_id="session1")  # Returns: Alice
agent.ask("What's my name?", session_id="session2")  # Returns: Bob
```

## Memory Type Selection Guide

Choose your memory type based on your use case:

| Use Case | Recommended Memory | Why |
|----------|-------------------|-----|
| Chat application (short sessions) | BufferMemory | Simple, fast, full history |
| Long conversations (100+ turns) | SummaryMemory | Efficient context compression |
| Knowledge base / RAG | VectorMemory | Semantic search capabilities |
| Multi-entity tracking | KnowledgeGraphMemory | Entity relationships |
| Stateless API | No Memory | Privacy, independence |

## Architecture

The demo uses Kaizen's BaseAgent architecture:

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField

class QASignature(Signature):
    question: str = InputField(desc="User question")
    answer: str = OutputField(desc="Agent answer")

class DemoAgent(BaseAgent):
    def __init__(self, config, memory=None):
        agent_config = BaseAgentConfig(
            llm_provider=config.llm_provider,
            model=config.model
        )
        super().__init__(
            config=agent_config,
            signature=QASignature(),
            memory=memory  # Plug in any memory type
        )
```

## Testing

Run the test suite:

```bash
pytest tests/unit/examples/test_memory_showcase.py -v
```

Tests verify:
- All demo functions execute without errors
- DemoAgent initialization with/without memory
- Memory type isolation and behavior
- Session isolation functionality

## Learn More

- **Memory Base Class**: `src/kaizen/memory/conversation_base.py`
- **BufferMemory**: `src/kaizen/memory/buffer.py`
- **SummaryMemory**: `src/kaizen/memory/summary.py`
- **VectorMemory**: `src/kaizen/memory/vector.py`
- **KnowledgeGraphMemory**: `src/kaizen/memory/knowledge_graph.py`
- **BaseAgent**: `src/kaizen/core/base_agent.py`

## Next Steps

1. **Customize Memory**: Implement custom embedders, summarizers, or extractors
2. **Combine Memories**: Use multiple memory types for hybrid approaches
3. **Production Setup**: Configure with real LLM providers (OpenAI, Anthropic)
4. **Optimize**: Tune parameters (max_turns, keep_recent, top_k) for your use case
