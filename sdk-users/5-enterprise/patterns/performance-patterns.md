# Performance Architecture Patterns

*Optimization strategies for high-performance Kailash applications*

## 🚀 Performance Optimization Layers

### 1. **Runtime Optimization**

```python
from kailash.runtime.local import LocalRuntime

# High-performance runtime configuration
runtime = LocalRuntime(
    enable_async=True,           # Enable async execution
    max_concurrency=50,          # Parallel execution limit
    worker_pool_size=20,         # Worker threads
    enable_monitoring=True,      # Performance metrics
    cache_size=1000,            # In-memory cache entries
    batch_mode=True,            # Batch processing
    optimization_level=2         # 0=none, 1=basic, 2=aggressive
)

# Execute with performance tracking
results, run_id = runtime.execute(
    workflow,
    track_performance=True
)

# Get performance metrics
metrics = runtime.get_performance_metrics(run_id)
print(f"Execution time: {metrics['total_time_ms']}ms")
print(f"Node timings: {metrics['node_timings']}")

```

### 2. **Caching Strategies**

#### Multi-Level Cache
```python
# L1: In-memory cache (fastest)
workflow.add_node("InMemoryCacheNode", "l1_cache", {}))

# L2: Redis cache (distributed)
workflow.add_node("RedisCacheNode", "l2_cache", {}))

# L3: Intelligent cache (similarity-based)
workflow.add_node("IntelligentCacheNode", "l3_cache", {}))

# Cache lookup pattern
workflow.add_node("PythonCodeNode", "cache_router", {})

# L1 lookup
if l1_result := l1_cache.get(cache_key):
    result = {"data": l1_result, "cache_hit": "L1"}
# L2 lookup
elif l2_result := l2_cache.get(cache_key):
    l1_cache.set(cache_key, l2_result)  # Promote to L1
    result = {"data": l2_result, "cache_hit": "L2"}
# L3 lookup
elif l3_result := l3_cache.get_similar(query):
    l2_cache.set(cache_key, l3_result)  # Promote to L2
    l1_cache.set(cache_key, l3_result)  # Promote to L1
    result = {"data": l3_result, "cache_hit": "L3"}
else:
    result = {"data": None, "cache_hit": None}
''',
    input_types={"query": dict}
))

```

### 3. **Batch Processing**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Batch reader for large datasets
workflow = WorkflowBuilder()
workflow.add_node("BatchDataReaderNode", "batch_reader", {}))

# Parallel batch processor
workflow = WorkflowBuilder()
workflow.add_node("ParallelProcessorNode", "batch_processor", {}))

# Batch writer with buffering
workflow = WorkflowBuilder()
workflow.add_node("BatchWriterNode", "batch_writer", {}))

```

### 4. **Connection Pooling**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Database connection pooling
workflow = WorkflowBuilder()
workflow.add_node("AsyncSQLDatabaseNode", "db_pool", {}))

# HTTP connection pooling
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

```

## 📊 Performance Patterns

### 1. **Stream Processing Pattern**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Stream processing for real-time data
workflow = WorkflowBuilder()

# Stream reader
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Stream processor with windowing
workflow = WorkflowBuilder()
workflow.add_node("WindowedProcessorNode", "windowed_processor", {}))

# Stream writer
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

```

### 2. **Lazy Loading Pattern**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

class LazyDataNode(Node):
    """Load data only when needed."""

    def __init__(self, "workflow_name", **kwargs):
        self.data_source = kwargs.get("data_source")
        self._data = None
        super().__init__(name=name, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "trigger": NodeParameter(
                name="trigger",
                type=bool,
                required=True
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        if kwargs.get("trigger") and self._data is None:
            # Load data only on first trigger
            self._data = self.load_data()

        return {"data": self._data, "loaded": self._data is not None}

```

### 3. **Circuit Breaker Pattern**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()
workflow.add_node("CircuitBreakerNode", "circuit_breaker", {}))

# Protected service call
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature:
        result = {"data": None, "status": "circuit_open"}
    else:
        # Make API call
        response = make_api_call()
        circuit_breaker.record_success()
        result = {"data": response, "status": "success"}
except Exception as e:
    circuit_breaker.record_failure()
    result = {"data": None, "status": "failed", "error": str(e)}
''',
    input_types={"request": dict}
))

```

### 4. **Resource Pool Pattern**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

class ResourcePoolNode(Node):
    """Manage pooled resources efficiently."""

    def __init__(self, "workflow_name", **kwargs):
        self.pool_size = kwargs.get("pool_size", 10)
        self.resource_type = kwargs.get("resource_type")
        self.pool = self._create_pool()
        super().__init__(name=name, **kwargs)

    def _create_pool(self):
        return [self._create_resource() for _ in range(self.pool_size)]

    def run(self, **kwargs) -> Dict[str, Any]:
        action = kwargs.get("action")

        if action == "acquire":
            resource = self.pool.pop() if self.pool else None
            return {"resource": resource, "available": len(self.pool)}

        elif action == "release":
            resource = kwargs.get("resource")
            if resource:
                self.pool.append(resource)
            return {"released": True, "available": len(self.pool)}

```

## 🎯 Optimization Strategies

### 1. **Query Optimization**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Optimized database queries
workflow = WorkflowBuilder()
workflow.add_node("SQLDatabaseNode", "optimized_query", {}) */
            id, data, created_at
        FROM large_table t
        WHERE created_at >= :start_date
        AND created_at < :end_date
    )
    SELECT * FROM indexed_data
    ORDER BY created_at
    LIMIT :limit OFFSET :offset
    """,
    query_timeout=5,
    fetch_size=1000
))

# Prepared statement caching
workflow = WorkflowBuilder()
workflow.add_node("PreparedStatementNode", "prepared_query", {}))

```

### 2. **Memory Optimization**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Memory-efficient data processing
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "memory_efficient", {}), chunk_size):
    chunk = data[chunk_start:chunk_start + chunk_size]

    # Process chunk
    processed_chunk = process_data(chunk)

    # Write immediately to free memory
    write_results(processed_chunk)
    processed_count += len(processed_chunk)

    # Force garbage collection every 10 chunks
    if (chunk_start // chunk_size) % 10 == 0:
        gc.collect()

result = {"processed": processed_count}
''',
    input_types={"data": list}
))

```

### 3. **Parallel Execution**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Parallel task execution
from concurrent.futures import ThreadPoolExecutor

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "parallel_executor", {}):
    # CPU-bound or I/O-bound task
    return expensive_operation(item)

# Execute in parallel
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {
        executor.submit(process_item, item): item
        for item in items
    }

    results = []
    for future in as_completed(futures):
        try:
            result = future.result(timeout=30)
            results.append(result)
        except Exception as e:
            print(f"Task failed: {e}")

result = {"processed": results, "count": len(results)}
''',
    input_types={"items": list}
))

```

## 📈 Performance Monitoring

### Metrics Collection

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Performance monitoring node
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature)

# Custom metrics
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "custom_metrics", {})
start_memory = psutil.Process().memory_info().rss / 1024 / 1024

# Process data
result_data = process_data(input_data)

# Collect metrics
end_time = time.time()
end_memory = psutil.Process().memory_info().rss / 1024 / 1024

metrics = {
    "processing_time_ms": (end_time - start_time) * 1000,
    "memory_delta_mb": end_memory - start_memory,
    "items_processed": len(result_data),
    "throughput": len(result_data) / (end_time - start_time)
}

result = {"data": result_data, "metrics": metrics}
''',
    input_types={"input_data": list}
))

```

## 🔧 Performance Tuning Checklist

### Database Performance
- [ ] Use connection pooling
- [ ] Add appropriate indexes
- [ ] Use prepared statements
- [ ] Implement query caching
- [ ] Monitor slow queries

### API Performance
- [ ] Implement rate limiting
- [ ] Use connection keep-alive
- [ ] Enable response compression
- [ ] Cache API responses
- [ ] Implement circuit breakers

### Memory Management
- [ ] Process data in chunks
- [ ] Release resources explicitly
- [ ] Use generators for large datasets
- [ ] Monitor memory usage
- [ ] Implement memory limits

### Concurrency
- [ ] Use async operations
- [ ] Implement thread pools
- [ ] Avoid blocking operations
- [ ] Use queues for decoupling
- [ ] Monitor thread usage

## 🎯 Performance Targets

| **Metric** | **Target** | **Optimization Strategy** |
|-----------|-----------|-------------------------|
| Response time | <100ms | Caching, async execution |
| Throughput | >1000 req/s | Load balancing, pooling |
| Memory usage | <512MB | Streaming, chunking |
| CPU usage | <80% | Parallel processing |
| Cache hit rate | >90% | Multi-level caching |

## 🔗 Next Steps

- [Security Patterns](security-patterns.md) - Security architecture
- [Monitoring Guide](../monitoring/) - Observability setup
- [Production Guide](../developer/04-production.md) - Deployment optimization
