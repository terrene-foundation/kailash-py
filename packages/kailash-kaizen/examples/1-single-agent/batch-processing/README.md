# Batch Processor Agent

Concurrent batch processing for high-throughput use cases using `ParallelBatchStrategy`.

## Overview

This example demonstrates how to build a batch processor that efficiently processes large datasets concurrently with semaphore limiting to prevent resource exhaustion.

## Features

- **Concurrent processing**: Execute multiple items in parallel
- **Semaphore limiting**: Prevent resource exhaustion with max_concurrent
- **Efficient throughput**: Process 1000s of items efficiently
- **Built on BaseAgent**: Enterprise features (logging, error handling, performance tracking)

## Use Cases

1. **Bulk Document Analysis**: Process thousands of documents concurrently
2. **Large-scale Data Transformation**: Transform datasets in parallel
3. **High-throughput API Processing**: Make concurrent API calls efficiently
4. **Embarrassingly Parallel Workloads**: Process independent items concurrently

## Quick Start

### Batch Processing

```python
import asyncio
from workflow import BatchProcessorAgent, BatchConfig

# Configure batch processor
config = BatchConfig(
    max_concurrent=5,  # Process 5 items concurrently
    llm_provider="openai",
    model="gpt-3.5-turbo"
)

agent = BatchProcessorAgent(config)

# Create batch
batch = [
    {"prompt": f"Analyze document {i}"}
    for i in range(100)
]

# Process concurrently
results = asyncio.run(agent.process_batch(batch))
print(f"Processed {len(results)} items")
```

### Single Item Processing

```python
from workflow import BatchProcessorAgent, BatchConfig

config = BatchConfig(max_concurrent=5)
agent = BatchProcessorAgent(config)

# Process single item
result = agent.process_single("Analyze this text")
print(result)
```

## Configuration Options

```python
@dataclass
class BatchConfig:
    llm_provider: str = "openai"        # LLM provider
    model: str = "gpt-3.5-turbo"        # Model name
    temperature: float = 0.1            # Generation temperature
    max_tokens: int = 200               # Max response length
    max_concurrent: int = 10            # Max concurrent executions
```

### Max Concurrent Guide

- `max_concurrent=1`: Sequential processing (no concurrency)
- `max_concurrent=5`: Moderate concurrency (balanced)
- `max_concurrent=10`: High concurrency (default)
- `max_concurrent=50`: Very high concurrency (for powerful systems)

## Architecture

```
BatchProcessorAgent (BaseAgent)
    ├── ParallelBatchStrategy (concurrent batch)
    │   ├── execute_batch() → List[Dict]
    │   ├── execute() → Dict (single item)
    │   └── Semaphore(max_concurrent) → resource limiting
    ├── ProcessingSignature (I/O structure)
    │   ├── Input: prompt
    │   └── Output: result
    └── BaseAgent Features
        ├── LoggingMixin
        ├── PerformanceMixin
        └── ErrorHandlingMixin
```

## ParallelBatchStrategy API

### `execute_batch(agent, batch)` → List[Dict[str, Any]]

Execute batch of inputs concurrently with semaphore limiting.

```python
batch = [{"prompt": f"Item {i}"} for i in range(100)]
results = await strategy.execute_batch(agent, batch)
```

**Key Features**:
- Results returned in same order as inputs
- Semaphore limits actual concurrency
- No resource exhaustion with large batches
- Efficient use of async/await

### `execute(agent, inputs)` → Dict[str, Any]

Execute single input (for compatibility with BaseAgent).

```python
result = await strategy.execute(agent, {"prompt": "Single item"})
```

## Performance

### Throughput Comparison

With 100 items, 0.01s processing time per item:

| max_concurrent | Time      | Throughput   |
|----------------|-----------|--------------|
| 1              | ~1.0s     | 100 items/s  |
| 5              | ~0.2s     | 500 items/s  |
| 10             | ~0.1s     | 1000 items/s |
| 50             | ~0.02s    | 5000 items/s |

### Resource Usage

- **Memory**: Minimal overhead (items processed incrementally)
- **CPU**: Efficient async I/O (not CPU-bound)
- **Network**: Respects max_concurrent for API rate limiting

## Testing

Run the comprehensive test suite:

```bash
pytest tests/unit/examples/test_batch_processing.py -v
```

Tests cover:
- Agent initialization with ParallelBatchStrategy
- Concurrent batch processing
- Semaphore limiting (no resource exhaustion)
- Empty batch handling
- Results order preservation
- Integration with BaseAgent

## Demo

Run the example:

```bash
cd examples/1-single-agent/batch-processing
python workflow.py
```

Output:
```
Batch Processing Demo
==================================================

Processing 20 items with max_concurrent=5...
Completed 20 items in 0.045s
Throughput: 444.4 items/sec

Sample results:
  1. {'response': 'Processed: Process document 0', 'batch': True}
  2. {'response': 'Processed: Process document 1', 'batch': True}
  3. {'response': 'Processed: Process document 2', 'batch': True}

Concurrency Comparison
==================================================
max_concurrent= 1: 10 items in 0.105s (95.2 items/sec)
max_concurrent= 3: 10 items in 0.038s (263.2 items/sec)
max_concurrent= 5: 10 items in 0.025s (400.0 items/sec)
max_concurrent=10: 10 items in 0.016s (625.0 items/sec)
```

## Integration with Core SDK

Convert to workflow node:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create agent
agent = BatchProcessorAgent(config)

# Convert to workflow node
workflow = WorkflowBuilder()
workflow.add_node_instance(agent)

# Execute via Core SDK
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Use Case Examples

### 1. Bulk Document Classification

```python
# Classify 1000 documents
documents = load_documents("data/documents.json")  # 1000 docs
batch = [{"prompt": f"Classify: {doc['text']}"} for doc in documents]

results = await agent.process_batch(batch)

# Save results
for doc, result in zip(documents, results):
    doc['classification'] = result['result']
```

### 2. Data Transformation Pipeline

```python
# Transform customer records
customers = load_customers("customers.csv")  # 5000 records
batch = [{"prompt": f"Extract insights: {c}"} for c in customers]

results = await agent.process_batch(batch)
save_transformed_data(results, "customers_transformed.json")
```

### 3. API Rate Limiting

```python
# Process with rate limiting (max 10 concurrent API calls)
config = BatchConfig(max_concurrent=10)  # Respect API rate limits
agent = BatchProcessorAgent(config)

api_requests = [{"prompt": f"Call API for {item}"} for item in items]
results = await agent.process_batch(api_requests)
```

## Next Steps

1. **Tune max_concurrent** for your workload and system capacity
2. **Add error handling** for individual batch items
3. **Implement retry logic** for failed items
4. **Monitor throughput** and adjust concurrency accordingly

## Related Examples

- `streaming-chat/` - Real-time token streaming
- `simple-qa/` - Basic single-shot processing
- `resilient-fallback/` - Multi-strategy fallback
- `memory-agent/` - Memory-enabled conversations

## References

- `src/kaizen/strategies/parallel_batch.py` - ParallelBatchStrategy implementation
- `tests/unit/strategies/test_parallel_batch_strategy.py` - Strategy tests
- ADR-006: Agent Base Architecture
