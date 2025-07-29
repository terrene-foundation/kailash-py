# Performance Optimization

Critical patterns for optimizing Kailash workflows and preventing common performance issues.

## Memory Management

### Prevent Memory Leaks in Cycles
```python
from kailash.nodes.base import CycleAwareNode
from kailash.workflow.builder import WorkflowBuilder
import psutil
import gc

class MemoryEfficientNode(CycleAwareNode):
    """Memory-optimized node for cyclic workflows."""

    def process_chunk(self, chunk):
        """Process a chunk of data."""
        return [item * 2 for item in chunk]  # Example processing

    def run(self, **kwargs):
        iteration = self.get_iteration()
        data = kwargs.get("data", [])

        # Process in chunks to prevent memory buildup
        chunk_size = min(1000, len(data) // 4) if data else 1000
        results = []

        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size]
            processed = self.process_chunk(chunk)
            results.extend(processed)
            del chunk, processed  # Immediate cleanup

        # Force garbage collection every 5 iterations
        if iteration % 5 == 0:
            gc.collect()

        return {"results": results, "iteration": iteration}

```

### Efficient Data Structures
```python
from collections import deque
import asyncio
from kailash.nodes.base import CycleAwareNode
from kailash.workflow.builder import WorkflowBuilder

class OptimizedProcessor(CycleAwareNode):
    """Use generators and efficient structures."""

    def process_item(self, item):
        """Process a single item."""
        return item * 2  # Example processing

    def run(self, **kwargs):
        data = kwargs.get("data", [])

        # Generator for memory efficiency
        def process_generator(items):
            for item in items:
                yield self.process_item(item)

        # Fixed-size buffer
        buffer = deque(maxlen=1000)

        for processed in process_generator(data):
            buffer.append(processed)
            if len(buffer) % 100 == 0:
                # Yield control periodically
                asyncio.sleep(0)

        return {"processed_data": list(buffer)}

```

## Async Processing

### Concurrent Task Execution
```python
import asyncio
from kailash.nodes.base_async import AsyncNode

class ConcurrentProcessor(AsyncNode):
    """Process multiple tasks concurrently."""

    async def process_task(self, task):
        """Process a single task asynchronously."""
        import asyncio
        await asyncio.sleep(0.1)  # Simulate async work
        return {"task": task, "processed": True}

    async def async_run(self, **kwargs):
        tasks = kwargs.get("tasks", [])
        max_concurrent = kwargs.get("max_concurrent", 5)

        # Limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_limit(task):
            async with semaphore:
                return await self.process_task(task)

        # Process all tasks
        results = await asyncio.gather(
            *[process_with_limit(t) for t in tasks],
            return_exceptions=True
        )

        # Separate results
        successful = [r for r in results if not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]

        return {
            "results": successful,
            "error_count": len(errors),
            "success_rate": len(successful) / len(tasks)
        }

```

## Database Optimization

### Production Connection Pooling with WorkflowConnectionPool
```python
from kailash.nodes.data import WorkflowConnectionPool
from kailash.nodes.data.query_router import QueryRouterNode
from contextlib import asynccontextmanager
from kailash.nodes.base_async import AsyncNode

# Create production-grade connection pool with Phase 2 features
pool = WorkflowConnectionPool(
    name="production_pool",
    database_type="postgresql",
    host="localhost",
    port=5432,
    database="kailash_db",
    user="postgres",
    password="password",
    min_connections=10,
    max_connections=50,
    health_threshold=70,      # Auto-recycle unhealthy connections
    pre_warm=True,           # Pre-warm based on patterns
    adaptive_sizing=True,    # NEW: Dynamic pool sizing
    enable_query_routing=True # NEW: Pattern tracking
)

# Initialize pool once at startup
await pool.execute({"operation": "initialize"})

# NEW: Query Router for intelligent routing (Phase 2)
workflow = WorkflowBuilder()
workflow.add_node("QueryRouterNode", "smart_router", {
    "connection_pool": "production_pool",
    "enable_read_write_split": True,  # Route reads to any connection
    "cache_size": 2000,               # Cache prepared statements
    "pattern_learning": True,         # Learn from patterns
    "health_threshold": 60            # Min health for routing
})

# Simple usage with router - no manual connection management!
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_async(workflow.build(), parameters={
    "smart_router": {
        "query": "SELECT * FROM users WHERE active = ?",
        "parameters": [True]
    }
})

# Transaction support with session affinity
results, run_id = await runtime.execute_async(workflow.build(), parameters={
    "smart_router": {
        "query": "BEGIN",
        "session_id": "user_123"
    }
})
results, run_id = await runtime.execute_async(workflow.build(), parameters={
    "smart_router": {
        "query": "UPDATE accounts SET balance = balance - ? WHERE id = ?",
        "parameters": [100, 1],
        "session_id": "user_123"
    }
})
results, run_id = await runtime.execute_async(workflow.build(), parameters={
    "smart_router": {
        "query": "COMMIT",
        "session_id": "user_123"
    }
})

# Context manager for direct pool access (when needed)
@asynccontextmanager
async def get_connection():
    """Safely acquire and release connections."""
    conn = await pool.execute({"operation": "acquire"})
    conn_id = conn["connection_id"]
    try:
        yield conn_id
    finally:
        await pool.execute({
            "operation": "release",
            "connection_id": conn_id
        })

# High-performance query execution
async def execute_batch_queries(queries):
    """Execute multiple queries efficiently."""
    results = []

    async with get_connection() as conn_id:
        for query in queries:
            result = await pool.execute({
                "operation": "execute",
                "connection_id": conn_id,
                "query": query["sql"],
                "params": query.get("params", []),
                "fetch_mode": query.get("fetch_mode", "all")
            })
            results.append(result["data"])

    return results

# Monitor pool health
stats = await pool.execute({"operation": "stats"})
print(f"Pool efficiency: {stats['queries']['executed'] / stats['connections']['created']:.1f} queries/connection")
print(f"Error rate: {stats['queries']['error_rate']:.2%}")
print(f"Active connections: {stats['current_state']['active_connections']}/{stats['current_state']['total_connections']}")

# NEW: Monitor Phase 2 features
if pool.adaptive_controller:
    history = pool.adaptive_controller.get_adjustment_history()
    print(f"Pool size adjustments: {len(history)}")
    print(f"Current pool size: {stats['current_state']['total_connections']}")

# Router metrics
router_metrics = await router.get_metrics()
print(f"Cache hit rate: {router_metrics['cache_stats']['hit_rate']:.2%}")
print(f"Avg routing time: {router_metrics['router_metrics']['avg_routing_time_ms']}ms")

```

## Caching Strategies

### Smart Caching with TTL
```python
import time
import hashlib
from kailash.nodes.base import CycleAwareNode
from kailash.workflow.builder import WorkflowBuilder

class CachedProcessor(CycleAwareNode):
    """Intelligent caching for expensive operations."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cache = {}
        self.cache_stats = {"hits": 0, "misses": 0}

    def _expensive_operation(self, kwargs):
        """Simulate expensive operation."""
        import time
        time.sleep(0.1)  # Simulate processing
        return {"processed": True, "data": kwargs.get("data", [])}

    def run(self, context, **kwargs):
        # Generate cache key
        cache_key = self._generate_key(kwargs)

        # Check cache
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if time.time() - entry["time"] < 300:  # 5 min TTL
                self.cache_stats["hits"] += 1
                return entry["result"]

        # Cache miss - process
        self.cache_stats["misses"] += 1
        result = self._expensive_operation(kwargs)

        # Store in cache
        self.cache[cache_key] = {
            "result": result,
            "time": time.time()
        }

        # Cleanup old entries
        self._cleanup_cache()

        return result

    def _generate_key(self, data):
        key_str = str(sorted(data.items()))
        return hashlib.md5(key_str.encode()).hexdigest()

    def _cleanup_cache(self):
        current_time = time.time()
        self.cache = {
            k: v for k, v in self.cache.items()
            if current_time - v["time"] < 300
        }

```

## Batch Processing

### Optimal Batch Sizing
```python
import psutil
from kailash.nodes.base import CycleAwareNode
from kailash.workflow.builder import WorkflowBuilder

class BatchProcessor(CycleAwareNode):
    """Dynamic batch processing."""

    def _process_parallel(self, batch):
        """Process batch in parallel."""
        return [item * 2 for item in batch]  # Example processing

    def _process_sequential(self, batch):
        """Process batch sequentially."""
        return [item * 2 for item in batch]  # Example processing

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])

        # Calculate optimal batch size
        batch_size = self._calculate_batch_size(data)
        results = []

        for i in range(0, len(data), batch_size):
            batch = data[i:i+batch_size]

            # Use parallel processing for large batches
            if len(batch) > 100:
                batch_results = self._process_parallel(batch)
            else:
                batch_results = self._process_sequential(batch)

            results.extend(batch_results)

            # Progress reporting
            if len(data) > 10000:
                progress = (i + batch_size) / len(data) * 100
                self.log_cycle_info(context, f"Progress: {progress:.1f}%")

        return {"processed": results, "batches": len(data) // batch_size}

    def _calculate_batch_size(self, data):
        data_size = len(data)
        available_memory = psutil.virtual_memory().available / 1024 / 1024

        if data_size < 1000:
            return data_size
        elif available_memory > 1000:  # 1GB available
            return min(5000, data_size // 10)
        else:
            return min(1000, data_size // 20)

```

## Performance Monitoring

### Real-time Metrics
```python
import time
import psutil
from kailash.nodes.base import CycleAwareNode
from kailash.workflow.builder import WorkflowBuilder

class PerformanceMonitor(CycleAwareNode):
    """Track performance metrics."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.metrics = []
        self.start_time = time.time()

    def run(self, context, **kwargs):
        iteration = self.get_iteration(context)

        # Collect metrics
        metrics = {
            "iteration": iteration,
            "elapsed": time.time() - self.start_time,
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent
        }

        self.metrics.append(metrics)

        # Dashboard every 5 iterations
        if iteration % 5 == 0:
            self._show_dashboard()

        return {"metrics": metrics}

    def _show_dashboard(self):
        recent = self.metrics[-10:]
        avg_cpu = sum(m["cpu_percent"] for m in recent) / len(recent)
        avg_mem = sum(m["memory_percent"] for m in recent) / len(recent)

        print(f"""
Performance Dashboard:
- Iterations: {recent[-1]['iteration']}
- CPU Usage: {avg_cpu:.1f}%
- Memory Usage: {avg_mem:.1f}%
- Runtime: {recent[-1]['elapsed']:.1f}s
        """)

```

## Best Practices

### Scale Configuration
```python
SCALE_CONFIGS = {
    "small": {"batch_size": 100, "max_concurrent": 2, "cache_size": 1000},
    "medium": {"batch_size": 1000, "max_concurrent": 5, "cache_size": 10000},
    "large": {"batch_size": 10000, "max_concurrent": 20, "cache_size": 100000}
}

def get_scale_config(data_size):
    if data_size < 1000:
        return SCALE_CONFIGS["small"]
    elif data_size < 100000:
        return SCALE_CONFIGS["medium"]
    else:
        return SCALE_CONFIGS["large"]

```

### Quick Optimization Checklist
- ✅ Process data in chunks (avoid loading all into memory)
- ✅ Use generators for large datasets
- ✅ Use WorkflowConnectionPool for database operations
- ✅ Monitor connection pool health and efficiency
- ✅ **NEW**: Use QueryRouterNode for automatic connection management
- ✅ **NEW**: Enable adaptive pool sizing for dynamic workloads
- ✅ **NEW**: Monitor cache hit rates (target >80%)
- ✅ **NEW**: Enable pattern learning for workload insights
- ✅ Add caching for expensive operations
- ✅ Force garbage collection in cycles
- ✅ Monitor memory growth between iterations
- ✅ Use async for I/O-bound operations
- ✅ Batch operations when possible
- ✅ Set appropriate pool sizes based on load

### Common Bottlenecks
| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| High memory usage | Loading full dataset | Use chunking/generators |
| Slow iterations | Synchronous I/O | Use AsyncNode |
| CPU spikes | Inefficient algorithms | Profile and optimize |
| Memory leaks | Accumulating state | Clear caches periodically |
| **Connection exhaustion** | Fixed pool size | Enable adaptive_sizing |
| **Slow query routing** | No caching | Use QueryRouterNode |
| **Low cache hits** | Dynamic queries | Use parameterized queries |
| **Pool not scaling** | Resource limits | Check DB max_connections |
