# Supervisor-Worker Multi-Agent Pattern

## Overview

The Supervisor-Worker pattern demonstrates **centralized coordination with task delegation**. A supervisor agent receives complex requests, breaks them into discrete tasks, delegates to worker agents for parallel execution, and aggregates the results. A coordinator agent monitors progress and handles conflicts.

**Pattern Type**: Centralized Coordination
**Complexity**: Intermediate
**Use Cases**: Parallel document processing, data pipeline orchestration, distributed task execution, batch job processing

## Architecture Diagram

```
User Request
     |
     v
SupervisorAgent (breaks into tasks)
     |
     v (writes tasks to SharedMemoryPool)
SharedMemoryPool
     |    [tags: "task", "pending", request_id]
     |    [segment: "tasks"]
     |
     +------------------+------------------+
     |                  |                  |
     v                  v                  v
WorkerAgent 1      WorkerAgent 2      WorkerAgent 3
(execute)          (execute)          (execute)
     |                  |                  |
     +------------------+------------------+
                        |
     v (write results to SharedMemoryPool)
SharedMemoryPool
     |    [tags: "result", "completed", request_id]
     |    [segment: "results"]
     |
     v
CoordinatorAgent (monitors) -----> SupervisorAgent (aggregates)
                                         |
                                         v
                                   Final Result
```

## Agents

### 1. SupervisorAgent

**Role**: Central coordinator and task delegator

**Responsibilities**:
- Receive user requests
- Break requests into discrete tasks
- Delegate tasks to available workers (round-robin)
- Monitor task completion
- Aggregate results from workers
- Handle failures and reassign tasks

**Shared Memory Behavior**:
- **Writes**: Tasks with tags `["task", "pending", request_id, worker_id]`
- **Reads**: Results with tags `["result", "completed", request_id]`
- **Importance**: 0.8 for tasks, 0.9 for reassignments
- **Segments**: `"tasks"`, `"results"`, `"errors"`

**Key Methods**:
- `delegate(request, available_workers, num_tasks)` - Break request into tasks
- `aggregate_results(request_id)` - Combine worker results
- `check_all_tasks_completed(request_id)` - Verify completion
- `check_failures(request_id)` - Detect failed tasks
- `reassign_task(task, new_worker)` - Reassign failed tasks

### 2. WorkerAgent

**Role**: Independent task executor

**Responsibilities**:
- Read assigned tasks from shared memory
- Execute tasks independently
- Write results to shared memory
- Mark tasks as completed
- Report failures

**Shared Memory Behavior**:
- **Reads**: Tasks with tags `["task", "pending", agent_id]`
- **Writes**: Results with tags `["result", "completed", request_id]`
- **Importance**: 0.8 for results, 0.9 for errors
- **Segments**: `"results"`, `"errors"`

**Key Methods**:
- `get_assigned_tasks()` - Read tasks from shared memory
- `execute_task(task)` - Execute task and write result

### 3. CoordinatorAgent

**Role**: Progress monitor and conflict resolver

**Responsibilities**:
- Monitor worker progress
- Detect conflicts (duplicate task assignments)
- Track active workers
- Report system status

**Shared Memory Behavior**:
- **Reads**: ALL insights (`exclude_own=False`)
- **Writes**: Does NOT write (monitoring only)
- **Monitors**: All segments (`"tasks"`, `"results"`, `"progress"`, `"errors"`)

**Key Methods**:
- `monitor_progress()` - Get system status
- `resolve_conflicts()` - Detect and resolve conflicts

## Workflow

### Step-by-Step Execution

1. **Supervisor Delegates Tasks**
   ```python
   tasks = supervisor.delegate("Process 3 documents", available_workers=["worker_1", "worker_2"])
   ```
   - Supervisor receives request
   - Breaks into discrete tasks
   - Assigns tasks to workers (round-robin)
   - Writes tasks to SharedMemoryPool

2. **Workers Execute Tasks**
   ```python
   for worker in workers:
       assigned_tasks = worker.get_assigned_tasks()
       for task in assigned_tasks:
           result = worker.execute_task(task)
   ```
   - Workers read assigned tasks from SharedMemoryPool
   - Execute tasks independently (can be parallel)
   - Write results to SharedMemoryPool

3. **Coordinator Monitors Progress**
   ```python
   progress = coordinator.monitor_progress()
   print(f"Active workers: {progress['active_workers']}")
   print(f"Pending: {progress['pending_tasks']}, Completed: {progress['completed_tasks']}")
   ```
   - Coordinator reads all insights
   - Tracks active workers
   - Counts pending and completed tasks
   - Detects conflicts

4. **Supervisor Aggregates Results**
   ```python
   aggregated = supervisor.aggregate_results(request_id)
   final_result = aggregated['final_result']
   ```
   - Supervisor reads all results for request
   - Aggregates into final result
   - Returns synthesized output

## Shared Memory Usage

### Tags

- **`"task"`** - Identifies task assignments
- **`"pending"`** - Task not yet completed
- **`"result"`** - Task execution result
- **`"completed"`** - Task finished
- **`"error"`** - Task failed
- **`"failed"`** - Failed task marker
- **`"conflict"`** - Conflict detected
- **`request_id`** - Groups insights by request (e.g., `"request_abc123"`)
- **`worker_id`** - Identifies assigned worker (e.g., `"worker_1"`)

### Segments

- **`"tasks"`** - Task assignments
- **`"results"`** - Task execution results
- **`"errors"`** - Error reports
- **`"progress"`** - Progress updates
- **`"conflicts"`** - Conflict markers

### Importance Levels

- **0.8** - Normal tasks and results
- **0.9** - Reassigned tasks, errors, conflicts
- **0.5** - Progress updates (lower priority)

## Quick Start

### Basic Usage

```python
from workflow import supervisor_worker_workflow

# Run workflow with default settings
result = supervisor_worker_workflow(
    "Process 5 customer support tickets",
    num_workers=3,
    num_tasks=5
)

print(f"Tasks created: {len(result['tasks'])}")
print(f"Results: {len(result['results'])}")
print(f"Final result: {result['final_result']}")
```

### Advanced Usage

```python
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.core.config import BaseAgentConfig
from workflow import SupervisorAgent, WorkerAgent, CoordinatorAgent

# Setup
pool = SharedMemoryPool()
config = BaseAgentConfig(llm_provider="openai", model="gpt-4")

# Create agents
supervisor = SupervisorAgent(config, pool, agent_id="supervisor_1")
workers = [WorkerAgent(config, pool, agent_id=f"worker_{i}") for i in range(3)]
coordinator = CoordinatorAgent(config, pool, agent_id="coordinator_1")

# Execute workflow
tasks = supervisor.delegate("Process documents", available_workers=["worker_0", "worker_1", "worker_2"])

for worker in workers:
    assigned = worker.get_assigned_tasks()
    for task in assigned:
        worker.execute_task(task)

progress = coordinator.monitor_progress()
print(progress)

result = supervisor.aggregate_results(tasks[0]["request_id"])
print(result)
```

## Configuration

### Supervisor Configuration

```python
config = BaseAgentConfig(
    llm_provider="openai",  # or "anthropic", "mock"
    model="gpt-4",
    logging_enabled=True
)

supervisor = SupervisorAgent(config, shared_pool, agent_id="supervisor_1")
```

### Worker Configuration

```python
# Workers can use different configurations
worker_config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-3.5-turbo",  # Cheaper model for workers
    logging_enabled=False
)

worker = WorkerAgent(worker_config, shared_pool, agent_id="worker_1")
```

### Workflow Parameters

```python
result = supervisor_worker_workflow(
    request="Process documents",
    num_workers=2,        # Number of worker agents
    num_tasks=3           # Number of tasks to create
)
```

## Testing

### Run Unit Tests

```bash
# Run all tests for supervisor-worker pattern
pytest tests/unit/examples/test_supervisor_worker.py -v

# Run specific test class
pytest tests/unit/examples/test_supervisor_worker.py::TestSupervisorTaskDelegation -v

# Run with coverage
pytest tests/unit/examples/test_supervisor_worker.py --cov=examples/2-multi-agent/supervisor-worker
```

### Test Coverage

- ✅ Supervisor task delegation (3 tests)
- ✅ Worker task execution (4 tests)
- ✅ Result aggregation (2 tests)
- ✅ Coordinator monitoring (2 tests)
- ✅ Parallel execution (1 test)
- ✅ Error handling (2 tests)
- ✅ Full workflow (3 tests)

**Total: 17 tests, all passing**

## Use Cases

### 1. Parallel Document Processing

Process multiple documents simultaneously:

```python
result = supervisor_worker_workflow(
    "Analyze sentiment in 100 customer reviews",
    num_workers=5,
    num_tasks=100
)
```

**Benefits**:
- Parallel processing reduces total time
- Supervisor ensures all documents processed
- Workers operate independently

### 2. Data Pipeline Orchestration

Coordinate data processing stages:

```python
# Stage 1: Data extraction
extraction_result = supervisor_worker_workflow(
    "Extract data from 10 sources",
    num_workers=3,
    num_tasks=10
)

# Stage 2: Data transformation
transformation_result = supervisor_worker_workflow(
    "Transform extracted data",
    num_workers=2,
    num_tasks=5
)
```

**Benefits**:
- Clear separation of concerns
- Scalable worker pool
- Progress monitoring

### 3. Distributed Task Execution

Execute long-running tasks across workers:

```python
result = supervisor_worker_workflow(
    "Generate reports for 50 departments",
    num_workers=10,
    num_tasks=50
)

# Check for failures
supervisor = SupervisorAgent(config, pool, "supervisor_1")
failures = supervisor.check_failures(result['tasks'][0]['request_id'])

# Reassign failed tasks
for failure in failures:
    task_id = failure['metadata']['task_id']
    supervisor.reassign_task(task, new_worker="worker_backup")
```

**Benefits**:
- Fault tolerance with reassignment
- Load balancing across workers
- Coordinator monitors health

### 4. Batch Job Processing

Process batches of jobs efficiently:

```python
# Process multiple batches
for batch in batches:
    result = supervisor_worker_workflow(
        f"Process batch {batch.id}",
        num_workers=5,
        num_tasks=len(batch.items)
    )

    # Monitor progress
    coordinator = CoordinatorAgent(config, pool, "coordinator_1")
    progress = coordinator.monitor_progress()
    print(f"Batch {batch.id}: {progress['completed_tasks']}/{progress['pending_tasks']}")
```

**Benefits**:
- Efficient batch processing
- Real-time progress tracking
- Scalable to large batches

## Related Examples

### Similar Patterns

- **[shared-insights](../shared-insights/)** - Multi-agent collaboration (Phase 4 reference)
- **[producer-consumer](../producer-consumer/)** - Queue-based pattern with pipeline processing
- **[domain-specialists](../domain-specialists/)** - Expert routing with domain-specific agents

### Complementary Patterns

- **[consensus-building](../consensus-building/)** - Add voting to supervisor decisions
- **[debate-decision](../debate-decision/)** - Use debate for task prioritization

### When to Use This Pattern

**Use Supervisor-Worker when**:
- You need centralized coordination
- Tasks can be executed independently
- You want parallel execution
- You need result aggregation
- You want progress monitoring

**Consider alternatives when**:
- Tasks require peer collaboration → Use consensus-building
- Tasks need sequential processing → Use producer-consumer
- Tasks require domain expertise → Use domain-specialists

## Implementation Notes

### Thread Safety

Workers can execute in parallel threads:

```python
import threading

def worker_task(worker_id, tasks):
    worker = WorkerAgent(config, pool, agent_id=worker_id)
    for task in tasks:
        worker.execute_task(task)

threads = []
for i, worker_tasks in enumerate(task_groups):
    thread = threading.Thread(target=worker_task, args=(f"worker_{i}", worker_tasks))
    threads.append(thread)
    thread.start()

for thread in threads:
    thread.join()
```

### Load Balancing

Supervisor uses round-robin by default:

```python
# tasks[0] → worker_1
# tasks[1] → worker_2
# tasks[2] → worker_3
# tasks[3] → worker_1 (cycles back)
```

Custom load balancing:

```python
# Assign based on worker capacity
available_workers = [
    ("worker_1", 10),  # Can handle 10 tasks
    ("worker_2", 5),   # Can handle 5 tasks
]

tasks = supervisor.delegate(request, available_workers=[w[0] for w in available_workers])
```

### Error Handling

Detect and reassign failures:

```python
# Check for failures
failures = supervisor.check_failures(request_id)

# Reassign each failed task
for failure in failures:
    task_id = failure['metadata']['task_id']
    task = next(t for t in tasks if t['task_id'] == task_id)
    supervisor.reassign_task(task, new_worker="worker_backup")
```

## Performance Considerations

### Scalability

- **Workers**: Linear scaling up to ~10 workers
- **Tasks**: Can handle 100+ tasks per request
- **Memory**: O(n) where n = number of tasks

### Optimization Tips

1. **Use appropriate number of workers**
   - Too few: Underutilization
   - Too many: Coordination overhead
   - Sweet spot: ~3-5 workers for most cases

2. **Batch task assignment**
   - Assign multiple tasks per worker
   - Reduces shared memory writes
   - Improves throughput

3. **Monitor coordinator overhead**
   - Coordinator polls shared memory
   - Limit polling frequency for large workflows
   - Use progress updates for real-time monitoring

## Limitations

1. **Centralized supervisor** - Single point of coordination (not fully distributed)
2. **Round-robin only** - Default load balancing is simple
3. **No task priorities** - All tasks treated equally
4. **Synchronous aggregation** - Supervisor waits for all tasks

## Future Enhancements

- [ ] Weighted load balancing based on worker capacity
- [ ] Task priorities and preemption
- [ ] Asynchronous result streaming
- [ ] Dynamic worker pool scaling
- [ ] Supervisor failover and recovery

## Author

**Kaizen Framework Team**
Created: 2025-10-02 (Phase 5, Task 5E.1)
Reference: Phase 4 shared-insights example

## License

Part of the Kailash Python SDK - Kaizen AI Framework
