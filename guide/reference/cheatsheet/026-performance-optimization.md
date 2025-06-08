# Performance Optimization

## Memory Management in Cycles

### Prevent Memory Leaks
```python
import psutil
import os
from kailash.nodes.base import CycleAwareNode

class MemoryEfficientNode(CycleAwareNode):
    """Node with built-in memory management."""

    def run(self, context, **kwargs):
        # Monitor memory usage
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Get cycle information
        iteration = self.get_iteration(context)

        # Process data in chunks to avoid memory buildup
        data = kwargs.get("data", [])
        chunk_size = min(1000, len(data) // 4) if data else 1000

        results = []
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size]
            processed_chunk = self.process_chunk(chunk)
            results.extend(processed_chunk)

            # Clear intermediate results immediately
            del chunk, processed_chunk

        # Force garbage collection every 5 iterations
        if iteration % 5 == 0:
            import gc
            gc.collect()

        # Monitor memory growth
        memory_after = process.memory_info().rss / 1024 / 1024
        memory_growth = memory_after - memory_before

        # Warning for excessive memory growth
        if memory_growth > 50:  # More than 50MB growth
            self.log_cycle_info(context, f"⚠️ High memory growth: {memory_growth:.1f}MB")

        return {
            "results": results,
            "memory_stats": {
                "memory_before": memory_before,
                "memory_after": memory_after,
                "memory_growth": memory_growth
            }
        }

    def process_chunk(self, chunk):
        """Process data chunk efficiently."""
        # Implement efficient processing logic
        return [self.process_item(item) for item in chunk]
```

### Data Structure Optimization
```python
class OptimizedDataProcessor(CycleAwareNode):
    """Optimized data processing with efficient structures."""

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])

        # Use generators for large datasets
        def process_generator(data):
            for item in data:
                yield self.process_item(item)

        # Use deque for efficient append/pop operations
        from collections import deque
        result_buffer = deque(maxlen=1000)  # Limit buffer size

        # Process with generator to avoid loading all into memory
        for processed_item in process_generator(data):
            result_buffer.append(processed_item)

            # Yield control periodically for async processing
            if len(result_buffer) % 100 == 0:
                import asyncio
                asyncio.sleep(0)  # Yield to event loop

        # Convert to list only at the end
        final_results = list(result_buffer)

        return {"processed_data": final_results}
```

## Cycle Performance Optimization

### Efficient Convergence Checking
```python
class FastConvergenceChecker(CycleAwareNode):
    """Optimized convergence checking with early exit."""

    def run(self, context, **kwargs):
        value = kwargs.get("value", 0.0)
        threshold = kwargs.get("threshold", 0.85)

        # Early exit if clearly converged
        if value >= threshold * 1.1:  # 10% above threshold
            return {
                "converged": True,
                "reason": "early_convergence",
                "value": value,
                "confidence": "high"
            }

        # Use efficient sliding window for stability check
        history = self.accumulate_values(context, "values", value, max_history=10)

        if len(history) >= 5:
            # Fast variance calculation
            recent = history[-5:]
            mean = sum(recent) / len(recent)
            variance = sum((x - mean) ** 2 for x in recent) / len(recent)

            # Quick stability check
            if variance < 0.001 and mean >= threshold:
                return {
                    "converged": True,
                    "reason": "stability_achieved",
                    "value": value,
                    "variance": variance
                }

        return {
            "converged": False,
            "value": value,
            "iterations_remaining": max(0, 20 - self.get_iteration(context))
        }
```

### Batch Processing Patterns
```python
class BatchProcessor(CycleAwareNode):
    """Process data in optimized batches."""

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        batch_size = kwargs.get("batch_size", self.calculate_optimal_batch_size(data))

        # Process in batches
        results = []
        for i in range(0, len(data), batch_size):
            batch = data[i:i+batch_size]

            # Parallel processing within batch
            if len(batch) > 100:
                batch_results = self.process_parallel(batch)
            else:
                batch_results = self.process_sequential(batch)

            results.extend(batch_results)

            # Progress reporting for large datasets
            if len(data) > 10000:
                progress = (i + batch_size) / len(data) * 100
                self.log_cycle_info(context, f"Progress: {progress:.1f}%")

        return {"processed_data": results, "batch_count": len(range(0, len(data), batch_size))}

    def calculate_optimal_batch_size(self, data):
        """Calculate optimal batch size based on data size and available memory."""
        data_size = len(data)
        available_memory = psutil.virtual_memory().available / 1024 / 1024  # MB

        if data_size < 1000:
            return data_size  # Process all at once
        elif available_memory > 1000:  # 1GB available
            return min(5000, data_size // 10)
        else:
            return min(1000, data_size // 20)
```

## Async Processing Optimization

### Concurrent Node Execution
```python
import asyncio
from kailash.nodes.base_async import AsyncNode

class ConcurrentProcessor(AsyncNode):
    """Process multiple tasks concurrently."""

    async def run_async(self, context, **kwargs):
        tasks = kwargs.get("tasks", [])
        max_concurrent = kwargs.get("max_concurrent", 5)

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_task_with_limit(task):
            async with semaphore:
                return await self.process_single_task(task)

        # Process tasks concurrently with limit
        results = await asyncio.gather(
            *[process_task_with_limit(task) for task in tasks],
            return_exceptions=True
        )

        # Separate successful results from errors
        successful = [r for r in results if not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]

        return {
            "results": successful,
            "error_count": len(errors),
            "success_rate": len(successful) / len(tasks) if tasks else 1.0
        }

    async def process_single_task(self, task):
        """Process a single task asynchronously."""
        # Simulate async work
        await asyncio.sleep(0.1)
        return {"task_id": task.get("id"), "result": "processed"}
```

### I/O Optimization for Cycles
```python
class IOOptimizedNode(AsyncNode):
    """Optimized I/O operations for cyclic workflows."""

    async def run_async(self, context, **kwargs):
        file_paths = kwargs.get("file_paths", [])

        # Read files concurrently
        async def read_file_async(path):
            async with aiofiles.open(path, 'r') as f:
                return await f.read()

        # Batch file operations
        file_contents = await asyncio.gather(
            *[read_file_async(path) for path in file_paths],
            return_exceptions=True
        )

        # Process contents efficiently
        processed_data = []
        for content in file_contents:
            if not isinstance(content, Exception):
                processed_data.append(self.process_content(content))

        return {"processed_files": len(processed_data)}
```

## Database and Storage Optimization

### Connection Pooling
```python
import asyncpg
from contextlib import asynccontextmanager

class DatabaseOptimizedNode(AsyncNode):
    """Node with optimized database operations."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connection_pool = None

    async def initialize_pool(self):
        """Initialize database connection pool."""
        if not self.connection_pool:
            self.connection_pool = await asyncpg.create_pool(
                database="kailash_db",
                user="kailash_user",
                password="password",
                host="localhost",
                min_size=5,
                max_size=20,
                max_queries=50000,
                max_inactive_connection_lifetime=300
            )

    @asynccontextmanager
    async def get_connection(self):
        """Get database connection from pool."""
        await self.initialize_pool()
        async with self.connection_pool.acquire() as connection:
            yield connection

    async def run_async(self, context, **kwargs):
        query = kwargs.get("query", "")
        parameters = kwargs.get("parameters", [])

        async with self.get_connection() as conn:
            # Use prepared statements for better performance
            result = await conn.fetch(query, *parameters)

        return {"result_count": len(result), "data": result}
```

### Caching Strategies
```python
import time
from functools import lru_cache
from typing import Dict, Any

class CachedProcessor(CycleAwareNode):
    """Node with intelligent caching."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cache = {}
        self.cache_stats = {"hits": 0, "misses": 0}

    def run(self, context, **kwargs):
        data = kwargs.get("data", [])
        cache_key = self.generate_cache_key(data, kwargs)

        # Check cache first
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if time.time() - cache_entry["timestamp"] < 300:  # 5 minute TTL
                self.cache_stats["hits"] += 1
                return cache_entry["result"]

        # Cache miss - process data
        self.cache_stats["misses"] += 1
        result = self.process_data_expensive(data, kwargs)

        # Store in cache
        self.cache[cache_key] = {
            "result": result,
            "timestamp": time.time()
        }

        # Cleanup old cache entries
        self.cleanup_cache()

        return result

    def generate_cache_key(self, data, kwargs):
        """Generate cache key from data and parameters."""
        import hashlib
        key_data = str(sorted(kwargs.items())) + str(len(data))
        return hashlib.md5(key_data.encode()).hexdigest()

    def cleanup_cache(self):
        """Remove expired cache entries."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if current_time - entry["timestamp"] > 300
        ]
        for key in expired_keys:
            del self.cache[key]

    @lru_cache(maxsize=128)
    def process_data_expensive(self, data_hash, config_hash):
        """Expensive operation with LRU cache."""
        # Simulate expensive computation
        time.sleep(0.1)
        return {"processed": True, "complexity": "high"}
```

## Monitoring and Profiling

### Performance Monitoring
```python
import time
import cProfile
import pstats
from io import StringIO

class ProfiledNode(CycleAwareNode):
    """Node with built-in performance profiling."""

    def run(self, context, **kwargs):
        # Start profiling
        profiler = cProfile.Profile()
        profiler.enable()

        start_time = time.time()
        iteration = self.get_iteration(context)

        try:
            # Execute actual processing
            result = self.process_with_timing(context, **kwargs)

        finally:
            # Stop profiling
            profiler.disable()
            execution_time = time.time() - start_time

            # Generate profile report every 10 iterations
            if iteration % 10 == 0:
                profile_report = self.generate_profile_report(profiler)
                self.log_cycle_info(context, f"Profile report (iteration {iteration}):")
                self.log_cycle_info(context, profile_report)

            # Add performance metrics to result
            if isinstance(result, dict):
                result["performance_metrics"] = {
                    "execution_time": execution_time,
                    "iteration": iteration,
                    "memory_usage": self.get_memory_usage()
                }

        return result

    def generate_profile_report(self, profiler):
        """Generate human-readable profile report."""
        s = StringIO()
        ps = pstats.Stats(profiler, stream=s)
        ps.sort_stats('cumulative').print_stats(10)  # Top 10 functions
        return s.getvalue()

    def get_memory_usage(self):
        """Get current memory usage."""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # MB
```

### Real-time Performance Dashboard
```python
class PerformanceDashboard(CycleAwareNode):
    """Real-time performance monitoring dashboard."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.metrics_history = []
        self.start_time = time.time()

    def run(self, context, **kwargs):
        current_time = time.time()
        iteration = self.get_iteration(context)

        # Collect current metrics
        metrics = {
            "iteration": iteration,
            "timestamp": current_time,
            "elapsed_time": current_time - self.start_time,
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "cycle_state_size": len(str(context.get("cycle", {}))),
            "parameters_size": len(str(kwargs))
        }

        # Add to history
        self.metrics_history.append(metrics)

        # Keep only last 100 measurements
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]

        # Generate dashboard every 5 iterations
        if iteration % 5 == 0:
            dashboard = self.generate_dashboard()
            print(dashboard)

        return {"metrics": metrics, "dashboard_updated": iteration % 5 == 0}

    def generate_dashboard(self):
        """Generate ASCII dashboard."""
        if not self.metrics_history:
            return "No metrics available"

        recent = self.metrics_history[-10:]  # Last 10 measurements

        avg_cpu = sum(m["cpu_percent"] for m in recent) / len(recent)
        avg_memory = sum(m["memory_percent"] for m in recent) / len(recent)
        iterations_per_sec = len(recent) / (recent[-1]["elapsed_time"] - recent[0]["elapsed_time"]) if len(recent) > 1 else 0

        dashboard = f"""
╔════════════════════════════════════════╗
║            PERFORMANCE DASHBOARD        ║
╠════════════════════════════════════════╣
║ Iterations:     {recent[-1]['iteration']:>6}            ║
║ Iterations/sec: {iterations_per_sec:>6.2f}            ║
║ CPU Usage:      {avg_cpu:>6.1f}%           ║
║ Memory Usage:   {avg_memory:>6.1f}%           ║
║ Elapsed Time:   {recent[-1]['elapsed_time']:>6.1f}s           ║
╚════════════════════════════════════════╝
"""
        return dashboard
```

## Best Practices

### 1. Resource Management
```python
class ResourceManagedNode(CycleAwareNode):
    """Node with comprehensive resource management."""

    def run(self, context, **kwargs):
        # Monitor resource usage
        initial_resources = self.get_resource_snapshot()

        try:
            # Process with resource limits
            with self.resource_limits():
                result = self.process_data(kwargs)

        finally:
            # Cleanup resources
            self.cleanup_resources()

            # Report resource usage
            final_resources = self.get_resource_snapshot()
            resource_diff = self.calculate_resource_diff(initial_resources, final_resources)

            if self.is_resource_usage_excessive(resource_diff):
                self.log_cycle_info(context, f"⚠️ High resource usage: {resource_diff}")

        return result
```

### 2. Scalability Patterns
```python
# Configure for different scales
SCALE_CONFIGS = {
    "small": {
        "batch_size": 100,
        "max_concurrent": 2,
        "cache_size": 1000,
        "memory_limit": "256MB"
    },
    "medium": {
        "batch_size": 1000,
        "max_concurrent": 5,
        "cache_size": 10000,
        "memory_limit": "1GB"
    },
    "large": {
        "batch_size": 10000,
        "max_concurrent": 20,
        "cache_size": 100000,
        "memory_limit": "8GB"
    }
}

def get_scale_config(data_size):
    """Get appropriate configuration based on data size."""
    if data_size < 1000:
        return SCALE_CONFIGS["small"]
    elif data_size < 100000:
        return SCALE_CONFIGS["medium"]
    else:
        return SCALE_CONFIGS["large"]
```

### 3. Bottleneck Identification
```python
def identify_bottlenecks(performance_metrics):
    """Identify performance bottlenecks from metrics."""
    bottlenecks = []

    # Check CPU usage
    if performance_metrics.get("avg_cpu_percent", 0) > 80:
        bottlenecks.append("High CPU usage - consider parallel processing")

    # Check memory usage
    if performance_metrics.get("avg_memory_percent", 0) > 85:
        bottlenecks.append("High memory usage - optimize data structures")

    # Check iteration speed
    if performance_metrics.get("iterations_per_second", 0) < 0.1:
        bottlenecks.append("Slow iteration speed - profile critical paths")

    # Check convergence efficiency
    if performance_metrics.get("avg_iterations_to_converge", 0) > 50:
        bottlenecks.append("Slow convergence - optimize convergence criteria")

    return bottlenecks
```
