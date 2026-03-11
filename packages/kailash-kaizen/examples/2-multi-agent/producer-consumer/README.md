# Producer-Consumer Multi-Agent Pattern

## Overview

The Producer-Consumer pattern demonstrates pipeline processing with queue management using multiple concurrent producers, consumers, and a centralized queue manager. This pattern is ideal for workload distribution, batch processing, and stream processing scenarios.

## Pattern Architecture

```
ProducerAgent(s) generate items
     |
     v (write to SharedMemoryPool)
SharedMemoryPool ["work", "pending", "queue"]
     |
     v (consumers read FIFO)
ConsumerAgent(s) (process in parallel)
     |
     v (write results to SharedMemoryPool)
SharedMemoryPool ["work", "completed", "results"]
     |
     v (manager monitors)
QueueManagerAgent (tracks stats, balancing)
     |
     v
Final Results + Statistics
```

## Quick Start

```python
from workflow import producer_consumer_workflow

# Run the workflow
result = producer_consumer_workflow(
    task_spec="Process customer data records",
    item_count=10,
    producer_count=2,
    consumer_count=3
)

print(f"Status: {result['status']}")
print(f"Items processed: {len(result['results'])}")
```

## Agents

### ProducerAgent
Generates work items with unique IDs and writes to shared memory queue.

### ConsumerAgent
Reads items from queue (FIFO), processes them, and writes results to shared memory.

### QueueManagerAgent
Monitors queue statistics, detects completion, provides load balancing recommendations.

## Test Coverage

21 comprehensive tests covering all aspects of the pattern.

Run tests:
```bash
pytest tests/unit/examples/test_producer_consumer.py -v
```

All tests passing!
