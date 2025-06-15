# Workflow Resilience Patterns

*Added in Session 067 based on real-world enterprise usage*

## Overview

Kailash workflows now include built-in resilience features for enterprise reliability. These features are integrated into the standard `Workflow` class - no separate `ResilientWorkflow` needed.

## Key Features

### 1. Retry Policies

Configure automatic retries with various strategies:

```python
from kailash.workflow import Workflow, RetryStrategy

workflow = Workflow(
    workflow_id="data_pipeline",
    name="Resilient Data Pipeline"
)

# Add a node that might fail
workflow.add_node("fetch_data", HTTPRequestNode, url="https://api.example.com/data")

# Configure retry policy
workflow.configure_retry(
    "fetch_data",
    max_retries=3,
    strategy=RetryStrategy.EXPONENTIAL,  # or LINEAR, IMMEDIATE, FIBONACCI
    base_delay=2.0,  # seconds
    max_delay=30.0,
    retry_on=[ConnectionError, TimeoutError]  # specific exceptions
)
```

### 2. Fallback Nodes

Define backup nodes for automatic failover:

```python
# Primary service
workflow.add_node(
    "primary_llm",
    LLMAgentNode,
    model="gpt-4",
    prompt="Analyze: {data}"
)

# Fallback service
workflow.add_node(
    "fallback_llm",
    LLMAgentNode,
    model="claude-3-sonnet",
    prompt="Analyze: {data}"
)

# Configure fallback
workflow.add_fallback("primary_llm", "fallback_llm")
```

### 3. Circuit Breaker Pattern

Prevent cascading failures:

```python
# Add circuit breaker to prevent repeated failures
workflow.configure_circuit_breaker(
    "api_call",
    failure_threshold=5,      # Open after 5 failures
    success_threshold=2,      # Close after 2 successes
    timeout=60.0             # Try again after 60 seconds
)
```

### 4. Dead Letter Queue

Track failed executions for manual intervention:

```python
# Execute workflow
try:
    result = await workflow.execute(input_data=data)
except Exception as e:
    # Check dead letter queue
    dlq = workflow.get_dead_letter_queue()
    for failed in dlq:
        print(f"Failed at {failed['timestamp']}: {failed['error']}")
        print(f"Node: {failed['node']}, Attempts: {failed['attempts']}")

    # Clear after processing
    workflow.clear_dead_letter_queue()
```

## Complete Example

```python
from kailash.workflow import Workflow, RetryStrategy, apply_resilience_to_workflow

# Option 1: Use decorator for all resilience features
@apply_resilience_to_workflow
class MyWorkflow(Workflow):
    pass

workflow = MyWorkflow(workflow_id="enterprise_pipeline", name="Enterprise Pipeline")

# Option 2: Use standard Workflow with resilience methods
workflow = Workflow(workflow_id="enterprise_pipeline", name="Enterprise Pipeline")

# Add nodes
workflow.add_node("fetch", HTTPRequestNode, url="https://api.primary.com/data")
workflow.add_node("fetch_backup", HTTPRequestNode, url="https://api.backup.com/data")
workflow.add_node("process", DataTransformer, transformation="normalize")

# Configure resilience
workflow.configure_retry("fetch", max_retries=3, strategy=RetryStrategy.EXPONENTIAL)
workflow.add_fallback("fetch", "fetch_backup")
workflow.configure_circuit_breaker("fetch", failure_threshold=5)

# Connect nodes
workflow.connect("fetch", "process", {"response": "data"})

# Execute with monitoring
result = await workflow.execute()

# Get metrics
metrics = workflow.get_resilience_metrics()
print(f"Circuit breaker state: {metrics['circuit_breakers']}")
print(f"Dead letter queue size: {metrics['dead_letter_queue_size']}")
```

## Retry Strategies

### Immediate
No delay between retries - use for transient network issues:
```python
workflow.configure_retry("node", strategy=RetryStrategy.IMMEDIATE)
```

### Linear
Fixed delay increase - use for rate limiting:
```python
workflow.configure_retry(
    "node",
    strategy=RetryStrategy.LINEAR,
    base_delay=2.0  # 2s, 4s, 6s, 8s...
)
```

### Exponential (Recommended)
Exponential backoff - use for most API calls:
```python
workflow.configure_retry(
    "node",
    strategy=RetryStrategy.EXPONENTIAL,
    base_delay=1.0  # 1s, 2s, 4s, 8s...
)
```

### Fibonacci
Fibonacci sequence delays - use for complex retry patterns:
```python
workflow.configure_retry(
    "node",
    strategy=RetryStrategy.FIBONACCI,
    base_delay=1.5  # 1.5s, 1.5s, 3s, 4.5s...
)
```

## Best Practices

1. **Use Exponential Backoff for APIs**: Most external services prefer exponential backoff
2. **Set Reasonable Limits**: Don't retry forever - use `max_delay` and `max_retries`
3. **Be Specific About Exceptions**: Only retry on expected failures
4. **Monitor Circuit Breakers**: Check metrics regularly to identify problematic services
5. **Process Dead Letter Queue**: Don't let failed executions accumulate

## Common Patterns

### Multi-Region Failover
```python
regions = ["us-east-1", "us-west-2", "eu-west-1"]

for i, region in enumerate(regions):
    workflow.add_node(
        f"api_{region}",
        HTTPRequestNode,
        url=f"https://{region}.api.example.com/data"
    )

    if i > 0:  # Add previous as fallback
        workflow.add_fallback(f"api_{regions[i-1]}", f"api_{region}")
```

### Graceful Degradation
```python
# Full feature
workflow.add_node("full_analysis", LLMAgentNode, model="gpt-4")

# Reduced feature
workflow.add_node("basic_analysis", LLMAgentNode, model="gpt-3.5-turbo")

# Minimal feature
workflow.add_node(
    "minimal_analysis",
    PythonCodeNode.from_function(
        name="fallback",
        func=lambda text: {"result": {"analysis": "Basic analysis", "confidence": 0.5}}
    )
)

# Chain fallbacks
workflow.add_fallback("full_analysis", "basic_analysis")
workflow.add_fallback("basic_analysis", "minimal_analysis")
```

## Migration from Separate ResilientWorkflow

If you have code using a separate `ResilientWorkflow` class:

```python
# Old approach (don't use)
from some_module import ResilientWorkflow
workflow = ResilientWorkflow(...)

# New approach (use this)
from kailash.workflow import Workflow
workflow = Workflow(...)
# Resilience methods are already available!
workflow.configure_retry(...)
workflow.add_fallback(...)
```

## Related Documentation

- [03-common-patterns.md](03-common-patterns.md) - Basic workflow patterns
- [07-troubleshooting.md](07-troubleshooting.md) - Error handling
- [09-production-checklist.md](09-production-checklist.md) - Production readiness
