# BaseAgent Mixins

Kaizen provides 7 composable mixins that add cross-cutting concerns to any agent. Each mixin wraps the agent's `run()` method to provide its functionality transparently.

## Available Mixins

| Mixin | Config Flag | Purpose |
|-------|-------------|---------|
| LoggingMixin | `logging_enabled` | Structured logging with execution timing |
| MetricsMixin | `performance_enabled` | Execution counts, duration histograms |
| RetryMixin | `error_handling_enabled` | Exponential backoff for transient failures |
| TimeoutMixin | `memory_enabled` | Operation timeout protection |
| CachingMixin | `batch_processing_enabled` | TTL-based response caching |
| TracingMixin | `transparency_enabled` | Distributed tracing spans |
| ValidationMixin | `mcp_enabled` | Input/output validation against signature |

## Usage

Mixins are automatically applied based on config flags:

```python
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

# Enable specific mixins via config
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4",
    logging_enabled=True,       # LoggingMixin
    performance_enabled=True,   # MetricsMixin
    error_handling_enabled=True # RetryMixin
)

agent = BaseAgent(config=config, signature=MySignature())

# Check which mixins were applied
print(agent._mixins_applied)
# ['LoggingMixin', 'PerformanceMixin', 'ErrorHandlingMixin']
```

## Sync/Async Compatibility

Mixins automatically detect whether the wrapped method is sync or async:

```python
# Sync agent - mixins create sync wrappers
class SyncAgent(BaseAgent):
    def run(self, **inputs) -> Dict[str, Any]:
        return {"result": "sync"}

# Async agent - mixins create async wrappers
class AsyncAgent(BaseAgent):
    async def run(self, **inputs) -> Dict[str, Any]:
        return {"result": "async"}

# Both work correctly with all mixins
sync_agent = SyncAgent(config)
result = sync_agent.run()  # Sync call

async_agent = AsyncAgent(config)
result = await async_agent.run()  # Async call
```

## Individual Mixin Details

### LoggingMixin

Provides structured logging for agent executions:

```python
config = BaseAgentConfig(logging_enabled=True)
agent = BaseAgent(config=config, signature=signature)

result = agent.run(question="test")
# Logs: INFO - Starting execution [AgentName_1234567890]
# Logs: INFO - Execution complete [AgentName_1234567890] in 150.23ms
```

Access the logger:
```python
from kaizen.core.mixins.logging_mixin import LoggingMixin
logger = LoggingMixin.get_logger(agent)
```

### MetricsMixin

Tracks execution metrics:

```python
config = BaseAgentConfig(performance_enabled=True)
agent = BaseAgent(config=config, signature=signature)

agent.run(question="test1")
agent.run(question="test2")

metrics = agent._metrics.get_metrics()
# {
#   'counters': {'agent.AgentName.executions.total': 2, ...},
#   'histograms': {'agent.AgentName.execution.duration_seconds': {...}}
# }
```

### RetryMixin

Automatic retry with exponential backoff:

```python
config = BaseAgentConfig(
    error_handling_enabled=True,
    max_retries=3  # Optional: default is 3
)
agent = BaseAgent(config=config, signature=signature)

# Retries on ConnectionError, TimeoutError, asyncio.TimeoutError
result = agent.run(question="test")
```

### TimeoutMixin

Operation timeout protection:

```python
config = BaseAgentConfig(
    memory_enabled=True,
    timeout=30.0  # Optional: default is 30 seconds
)
agent = BaseAgent(config=config, signature=signature)

try:
    result = agent.run(question="test")
except TimeoutError as e:
    print(f"Operation timed out: {e}")
```

### CachingMixin

TTL-based response caching:

```python
config = BaseAgentConfig(
    batch_processing_enabled=True,
    cache_ttl=300  # Optional: default is 300 seconds
)
agent = BaseAgent(config=config, signature=signature)

# First call - executes and caches
result1 = agent.run(question="test")

# Second call - returns cached result
result2 = agent.run(question="test")

# Bypass cache
result3 = agent.run(question="test", cache_bypass=True)
```

### TracingMixin

Distributed tracing with spans:

```python
config = BaseAgentConfig(transparency_enabled=True)
agent = BaseAgent(config=config, signature=signature)

agent.run(question="test")

spans = agent._tracer.get_spans()
# [Span(name='AgentName.run', duration_ms=150.0, ...)]
```

### ValidationMixin

Input/output validation:

```python
config = BaseAgentConfig(mcp_enabled=True)
agent = BaseAgent(config=config, signature=signature)

try:
    # Raises ValidationError if required fields are missing
    result = agent.run()
except ValidationError as e:
    print(f"Validation failed: {e}")
```

## Mixin Composition

Multiple mixins can be enabled simultaneously. They compose in order:

```python
config = BaseAgentConfig(
    logging_enabled=True,
    performance_enabled=True,
    error_handling_enabled=True
)

# Order of wrapping: Logging -> Performance -> ErrorHandling
# Execution flow:
#   1. LoggingMixin.logged_run starts
#   2. MetricsMixin.metered_run starts
#   3. RetryMixin.retry_run executes (with retries if needed)
#   4. MetricsMixin.metered_run records metrics
#   5. LoggingMixin.logged_run logs completion
```

## Architecture

Each mixin follows the same pattern:

1. **Detection**: Check if original method is async via `inspect.iscoroutinefunction()`
2. **Wrapping**: Create appropriate sync or async wrapper
3. **Replacement**: Replace `agent.run` with wrapped version

This ensures mixins work correctly regardless of whether the base agent uses sync or async execution.
