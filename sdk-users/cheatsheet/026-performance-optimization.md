# Performance Optimization

Critical patterns for optimizing Kailash workflows and preventing common performance issues.

## Memory Management

### Prevent Memory Leaks in Cycles
```python
from kailash.nodes.base import CycleAwareNode
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
from kailash.nodes.base import AsyncNode

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

### Connection Pooling
```python
import asyncpg
from contextlib import asynccontextmanager
from kailash.nodes.base import AsyncNode

class DatabaseNode(AsyncNode):
    """Efficient database operations."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pool = None

    async def initialize_pool(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                database="kailash_db",
                min_size=5,
                max_size=20,
                max_inactive_connection_lifetime=300
            )

    @asynccontextmanager
    async def get_connection(self):
        await self.initialize_pool()
        async with self.pool.acquire() as conn:
            yield conn

    async def async_run(self, **kwargs):
        query = kwargs.get("query")
        params = kwargs.get("parameters", [])

        async with self.get_connection() as conn:
            result = await conn.fetch(query, *params)

        return {"data": result, "count": len(result)}

```

## Caching Strategies

### Smart Caching with TTL
```python
import time
import hashlib
from kailash.nodes.base import CycleAwareNode

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
- ✅ Implement connection pooling for databases
- ✅ Add caching for expensive operations
- ✅ Force garbage collection in cycles
- ✅ Monitor memory growth between iterations
- ✅ Use async for I/O-bound operations
- ✅ Batch operations when possible

### Common Bottlenecks
| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| High memory usage | Loading full dataset | Use chunking/generators |
| Slow iterations | Synchronous I/O | Use AsyncNode |
| CPU spikes | Inefficient algorithms | Profile and optimize |
| Memory leaks | Accumulating state | Clear caches periodically |
