# Async Execution Guide

Production-ready async execution for Kaizen agents using `run_async()` and AsyncOpenAI.

## Overview

Kaizen agents support both synchronous and asynchronous execution modes. Async execution provides true non-blocking I/O for production FastAPI deployments and high-throughput scenarios.

## Benefits

| Feature | Sync (run) | Async (run_async) |
|---------|-----------|-------------------|
| Single request | 500ms | 500ms (same) |
| 10 concurrent requests | ~5000ms (queued) | ~500ms (parallel) |
| 100 concurrent requests | ~50000ms + timeouts | ~500ms (parallel) |
| Thread pool exhaustion | Yes | No |
| SSL socket blocking | Yes | No |

**Performance**: 10-100x faster for concurrent requests

## Configuration

Enable async mode by setting `use_async_llm=True` in your agent configuration:

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField

# Define signature
class QASignature(Signature):
    question: str = InputField(description="User question")
    answer: str = OutputField(description="Response")

# Enable async mode
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    use_async_llm=True  # ← Required for run_async()
)

# Create agent
agent = BaseAgent(config=config, signature=QASignature())
```

## Usage Patterns

### FastAPI Endpoint

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None

class ChatResponse(BaseModel):
    response: str
    confidence: float | None = None

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Async endpoint - handles 100+ concurrent requests efficiently.
    """
    try:
        result = await agent.run_async(
            question=request.message,
            session_id=request.session_id
        )
        return ChatResponse(
            response=result["answer"],
            confidence=result.get("confidence")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Concurrent Batch Processing

```python
import asyncio

async def process_batch(questions: list[str]) -> list[dict]:
    """
    Process 100+ questions concurrently - all in parallel.
    """
    tasks = [
        agent.run_async(question=q)
        for q in questions
    ]
    results = await asyncio.gather(*tasks)
    return results

# Execute
questions = ["Question 1", "Question 2", ..., "Question 100"]
results = await process_batch(questions)
```

### With Memory and Sessions

```python
@app.post("/api/chat/{session_id}")
async def chat_with_memory(session_id: str, request: ChatRequest):
    """
    Async execution with persistent memory.
    """
    result = await agent.run_async(
        question=request.message,
        session_id=session_id  # Maintains conversation context
    )
    return {"response": result["answer"]}
```

## Error Handling

```python
@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        result = await agent.run_async(question=request.message)
        return {"response": result["answer"]}
    except ValueError as e:
        # Agent not configured for async mode
        raise HTTPException(status_code=500, detail=f"Configuration error: {e}")
    except RuntimeError as e:
        # OpenAI API error
        raise HTTPException(status_code=503, detail=f"Service error: {e}")
    except Exception as e:
        # Unexpected error
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
```

## Configuration Validation

The agent validates async configuration at runtime:

```python
# ✅ Correct: Agent configured for async
config = BaseAgentConfig(use_async_llm=True, llm_provider="openai")
agent = BaseAgent(config=config, signature=sig)
await agent.run_async(question="Hello")  # Works

# ❌ Incorrect: Agent NOT configured for async
config = BaseAgentConfig(use_async_llm=False)  # Default
agent = BaseAgent(config=config, signature=sig)
await agent.run_async(question="Hello")  # Raises ValueError with helpful message
```

Error message:
```
ValueError: Agent not configured for async mode.
Set use_async_llm=True in BaseAgentConfig:

config = BaseAgentConfig(
    llm_provider='openai',
    model='gpt-4',
    use_async_llm=True  # Enable async mode
)
```

## When to Use

### Use run_async() for:

- **FastAPI/async web applications** - Non-blocking I/O
- **High-throughput scenarios** - 10+ concurrent requests
- **Production deployments** - Docker containers with AsyncLocalRuntime
- **Real-time applications** - Chat interfaces, streaming

### Use run() for:

- **CLI scripts and tools** - Simple sequential execution
- **Jupyter notebooks** - Interactive development
- **Synchronous applications** - Traditional Python apps
- **Simple workflows** - No concurrency requirements

## Complete Example

```python
from fastapi import FastAPI
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.signatures import Signature, InputField, OutputField
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define signature
class QASignature(Signature):
    question: str = InputField(description="User question")
    answer: str = OutputField(description="Detailed answer")
    confidence: float = OutputField(description="Confidence score 0.0-1.0")

# Create async agent
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    temperature=0.7,
    max_tokens=500,
    use_async_llm=True  # Enable async execution
)

agent = BaseAgent(config=config, signature=QASignature())

# FastAPI app
app = FastAPI(title="Async Agent API")

class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str
    confidence: float

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Async chat endpoint - handles 100+ concurrent requests.
    """
    result = await agent.run_async(question=request.question)
    return ChatResponse(
        answer=result["answer"],
        confidence=result["confidence"]
    )

@app.post("/batch")
async def batch_process(questions: list[str]):
    """
    Process multiple questions concurrently.
    """
    tasks = [agent.run_async(question=q) for q in questions]
    results = await asyncio.gather(*tasks)
    return {"results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Implementation Details

### AsyncOpenAI Client

The async implementation uses `AsyncOpenAI` client from the OpenAI library:

- **chat_async()** - Non-blocking chat completions
- **embed_async()** - Non-blocking embeddings generation
- Separate client instances for sync/async to avoid conflicts

### Async Provider Methods

```python
from kaizen.nodes.ai.ai_providers import OpenAIProvider

# Initialize with async support
provider = OpenAIProvider(use_async=True)

# Async chat
response = await provider.chat_async(
    messages=[{"role": "user", "content": "Hello"}],
    model="gpt-4",
    generation_config={"temperature": 0.7, "max_tokens": 500}
)

# Async embeddings
embeddings = await provider.embed_async(
    texts=["Text 1", "Text 2"],
    model="text-embedding-3-small"
)
```

### Response Format

Both `run()` and `run_async()` return identical response formats:

```python
{
    "answer": "Response text",
    "confidence": 0.95,
    # ... other signature output fields
}
```

## Testing

### Unit Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_agent():
    """Test async agent execution."""
    config = BaseAgentConfig(use_async_llm=True, llm_provider="openai")
    agent = BaseAgent(config=config, signature=QASignature())

    result = await agent.run_async(question="What is 2+2?")

    assert "answer" in result
    assert "4" in result["answer"]

@pytest.mark.asyncio
async def test_concurrent_execution():
    """Test 10 concurrent requests."""
    config = BaseAgentConfig(use_async_llm=True, llm_provider="openai")
    agent = BaseAgent(config=config, signature=QASignature())

    tasks = [agent.run_async(question=f"Question {i}") for i in range(10)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 10
```

## Backwards Compatibility

Sync execution remains unchanged:

```python
# Sync agent (default)
config = BaseAgentConfig(llm_provider="openai", model="gpt-4")
agent = BaseAgent(config=config, signature=QASignature())

# Sync execution - works as before
result = agent.run(question="Hello")
```

## Related Guides

- [BaseAgent Architecture](baseagent-architecture.md) - Core agent concepts
- [Signature Programming](signature-programming.md) - Type-safe I/O
- [Integration Patterns](integration-patterns.md) - FastAPI integration

## Reference

- **Source**: `src/kaizen/core/base_agent.py:675-937`
- **Providers**: `src/kaizen/nodes/ai/ai_providers.py:862-1135`
- **Tests**: `tests/unit/core/test_async_features.py`
- **Examples**: `examples/1-single-agent/async-execution/`
