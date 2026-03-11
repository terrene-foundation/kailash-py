# OrchestrationRuntime Concurrency Control

OrchestrationRuntime provides enterprise-grade concurrency control for multi-agent orchestration through priority queuing and semaphore-based execution limiting.

## Priority Queue

Tasks are ordered by priority using `asyncio.PriorityQueue`. Lower priority values execute first.

```python
from kaizen.orchestration.runtime import OrchestrationRuntime

runtime = OrchestrationRuntime()

# High priority task (priority=1)
await runtime.task_queue.put((1, {"task_id": "urgent", "agent_id": "agent_1"}))

# Normal priority task (priority=10)
await runtime.task_queue.put((10, {"task_id": "normal", "agent_id": "agent_1"}))

# Tasks are retrieved in priority order
priority, task = await runtime.task_queue.get()  # Returns urgent task first
```

## Concurrency Limiting

The semaphore limits concurrent agent executions to prevent resource exhaustion:

```python
from kaizen.orchestration.runtime import OrchestrationRuntime, OrchestrationRuntimeConfig

# Limit to 5 concurrent agent executions
config = OrchestrationRuntimeConfig(max_concurrent_agents=5)
runtime = OrchestrationRuntime(config)

# Tasks exceeding the limit wait for semaphore acquisition
results = await asyncio.gather(*[
    runtime.execute_task(f"agent_{i}", {"task": f"task_{i}"})
    for i in range(10)  # 10 tasks, but only 5 run concurrently
])
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_concurrent_agents` | 10 | Maximum concurrent agent executions |
| `max_queue_size` | 1000 | Maximum tasks in queue |

## How It Works

1. **Task Submission**: Tasks are added to the PriorityQueue with `(priority, task_data)` tuple
2. **Semaphore Acquisition**: `execute_task` acquires semaphore before execution
3. **Agent Execution**: Task is delegated to the agent's `run()` method
4. **Semaphore Release**: Semaphore is released after execution (success or failure)

This ensures:
- High-priority tasks execute before low-priority ones
- System resources are protected from overload
- Graceful degradation under high load
