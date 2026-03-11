# Resilient Fallback Agent

Sequential fallback for robust degraded service using `FallbackStrategy`.

## Overview

This example demonstrates how to build a resilient agent that tries multiple strategies in sequence, providing redundancy and graceful degradation when primary services fail.

## Features

- **Sequential fallback**: Try strategies in order until one succeeds
- **Multi-model redundancy**: GPT-4 → GPT-3.5 → local model
- **Cost optimization**: Try expensive first, fall back to cheap
- **Error tracking**: Summary of all failed attempts
- **Built on BaseAgent**: Enterprise features (logging, error handling, performance tracking)

## Use Cases

1. **Multi-Model Fallback**: Maintain service when primary model unavailable
2. **Cost Optimization**: Try expensive high-quality first, fall back to cheaper options
3. **Progressive Degradation**: Graceful degradation for high availability
4. **Redundancy**: Critical operations with multiple backup strategies

## Quick Start

### Basic Fallback

```python
import asyncio
from workflow import ResilientAgent, FallbackConfig

# Configure fallback chain
config = FallbackConfig(
    models=["gpt-4", "gpt-3.5-turbo", "local-model"],
    llm_provider="openai"
)

agent = ResilientAgent(config)

# Query with automatic fallback
result = asyncio.run(agent.query_async("What is AI?"))
print(f"Response: {result['response']}")
print(f"Used model: {config.models[result['_fallback_strategy_used']]}")
```

### Cost Optimization

```python
# Try expensive first, fall back to cheaper
config = FallbackConfig(
    models=[
        "gpt-4",           # $0.03/1K tokens - best quality
        "gpt-3.5-turbo",   # $0.002/1K tokens - good quality
        "local-llama"      # Free - basic quality
    ]
)

agent = ResilientAgent(config)
result = asyncio.run(agent.query_async("Analyze this"))
```

## Configuration Options

```python
@dataclass
class FallbackConfig:
    models: List[str]                    # Fallback chain (required)
    llm_provider: str = "openai"         # LLM provider
    temperature: float = 0.7             # Generation temperature
    max_tokens: int = 300                # Max response length
```

### Fallback Chain Examples

**High Availability**:
```python
models=["primary-api", "backup-api", "local-model"]
```

**Cost Optimization**:
```python
models=["gpt-4", "gpt-3.5-turbo", "gpt-3.5-turbo-instruct"]
```

**Quality Degradation**:
```python
models=["claude-opus", "claude-sonnet", "claude-haiku"]
```

## Architecture

```
ResilientAgent (BaseAgent)
    ├── FallbackStrategy (sequential fallback)
    │   ├── Strategy 1 (Primary: GPT-4)
    │   ├── Strategy 2 (Secondary: GPT-3.5)
    │   └── Strategy 3 (Tertiary: local)
    ├── QuerySignature (I/O structure)
    │   ├── Input: query
    │   └── Output: response
    └── BaseAgent Features
        ├── LoggingMixin
        ├── PerformanceMixin
        └── ErrorHandlingMixin
```

## FallbackStrategy API

### `execute(agent, inputs)` → Dict[str, Any]

Try strategies in sequence until one succeeds.

```python
result = await strategy.execute(agent, {"query": "test"})
```

**Returns**:
```python
{
    "response": "...",
    "_fallback_strategy_used": 0,     # Which strategy succeeded (0-indexed)
    "_fallback_attempts": 1           # Number of attempts made
}
```

**Raises**: `RuntimeError` if all strategies fail

### `get_error_summary()` → List[Dict[str, Any]]

Get summary of errors from failed strategies.

```python
errors = strategy.get_error_summary()
# [{"strategy": "AsyncSingleShotStrategy", "error": "...", "error_type": "ValueError"}]
```

## Performance

### Fallback Behavior

- **Primary succeeds**: Immediate return (no fallback)
- **Primary fails, secondary succeeds**: 2x latency
- **All fail**: N×latency + error summary

### Error Tracking

```python
try:
    result = await agent.query_async("test")
except RuntimeError as e:
    # All strategies failed
    errors = agent.get_error_summary()
    for error in errors:
        print(f"{error['strategy']}: {error['error']}")
```

## Testing

Run the comprehensive test suite:

```bash
pytest tests/unit/examples/test_resilient_fallback.py -v
```

Tests cover:
- Agent initialization with FallbackStrategy
- Sequential fallback execution
- Strategy tracking and metadata
- Error summary generation
- Empty models validation
- Integration with BaseAgent

## Demo

Run the example:

```bash
cd examples/1-single-agent/resilient-fallback
python workflow.py
```

Output:
```
Resilient Fallback Demo - Primary Success
==================================================
Fallback chain: gpt-4 → gpt-3.5-turbo → local-model

Query: What is artificial intelligence?
Response: Placeholder result for response
Strategy used: #0 (gpt-4)
Attempts: 1

Fallback Chain Demo
==================================================
Chain: gpt-4 → gpt-3.5-turbo

1. Query: What is Python?
   Model: gpt-4
   Response: Placeholder result for response...

2. Query: Explain machine learning
   Model: gpt-4
   Response: Placeholder result for response...

3. Query: What are neural networks?
   Model: gpt-4
   Response: Placeholder result for response...

Cost Optimization Demo
==================================================
Strategy: Try expensive model first, fall back to cheap

Fallback chain: gpt-4 → gpt-3.5-turbo → local-llama
  gpt-4: $0.03/1K tokens (best quality)
  gpt-3.5-turbo: $0.002/1K tokens (good quality)
  local-llama: Free (basic quality)

If GPT-4 fails → fall back to GPT-3.5
If GPT-3.5 fails → fall back to local model
Optimize cost while maintaining service
```

## Integration with Core SDK

Convert to workflow node:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create agent
agent = ResilientAgent(config)

# Convert to workflow node
workflow = WorkflowBuilder()
workflow.add_node_instance(agent)

# Execute via Core SDK
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Use Case Examples

### 1. High Availability Service

```python
# Primary cloud, backup cloud, local fallback
config = FallbackConfig(
    models=["openai-gpt-4", "anthropic-claude", "local-llama"]
)
agent = ResilientAgent(config)

# Guaranteed response (unless all fail)
result = await agent.query_async("Critical query")
```

### 2. Cost Optimization

```python
# Try best quality first, fall back to cheaper
config = FallbackConfig(
    models=["gpt-4", "gpt-3.5-turbo"]  # $0.03 vs $0.002 per 1K tokens
)

# Will use GPT-4 if available, GPT-3.5 if not
result = await agent.query_async("Analyze data")
```

### 3. Progressive Quality Degradation

```python
# Best → Good → Basic quality
config = FallbackConfig(
    models=["claude-opus", "claude-sonnet", "claude-haiku"]
)

# Maintains service with graceful quality degradation
result = await agent.query_async("Generate content")
```

## Next Steps

1. **Implement retry logic** for transient failures (before fallback)
2. **Add circuit breakers** to skip known-failing strategies
3. **Monitor strategy success rates** to optimize fallback order
4. **Combine with caching** to reduce fallback frequency

## Related Examples

- `streaming-chat/` - Real-time token streaming
- `batch-processing/` - Concurrent batch processing
- `human-approval/` - Human-in-the-loop approval
- `simple-qa/` - Basic single-shot processing

## References

- `src/kaizen/strategies/fallback.py` - FallbackStrategy implementation
- `tests/unit/strategies/test_fallback_strategy.py` - Strategy tests
- ADR-006: Agent Base Architecture
