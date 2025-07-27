Performance Optimization
========================

This guide provides techniques and best practices for optimizing performance in the
Kailash Python SDK.

Cyclic Workflow Performance
---------------------------

The Kailash SDK's cyclic workflow implementation achieves exceptional performance through optimized execution strategies.

Performance Metrics
^^^^^^^^^^^^^^^^^^^

Based on comprehensive benchmarking, cyclic workflows demonstrate:

- **Throughput**: ~30,000 iterations per second
- **Overhead**: ~0.03-0.04ms per iteration (minimal impact)
- **Memory**: O(1) space complexity with configurable history windows
- **Scalability**: Linear performance up to 1 million iterations

.. code-block:: python

    # Performance test results
    from kailash import Workflow
    from kailash.nodes.base_cycle_aware import CycleAwareNode
    import time

    class BenchmarkNode(CycleAwareNode):
        def run(self, context, **kwargs):
            iteration = self.get_iteration(context)
            prev_state = self.get_previous_state(context)

            value = prev_state.get("value", 0) + 1
            self.set_cycle_state({"value": value})

            return {
                "value": value,
                "converged": iteration >= 999  # 1000 iterations
            }

    # Benchmark results:
    # 1,000 iterations: 0.03 seconds (33,333 iter/sec)
    # 10,000 iterations: 0.36 seconds (27,777 iter/sec)
    # 100,000 iterations: 3.81 seconds (26,246 iter/sec)
    # 1,000,000 iterations: 38.12 seconds (26,227 iter/sec)

Optimization Techniques
^^^^^^^^^^^^^^^^^^^^^^^

1. **State Management**: Efficient copy-on-write for node states
2. **Convergence Detection**: Early termination with trend analysis
3. **Memory Windows**: Configurable history limits prevent unbounded growth
4. **Parallel Execution**: ParallelCyclicRuntime for independent cycles

.. code-block:: python

    # Optimized cycle configuration
    workflow.create_cycle("performance_cycle") \
            .connect("processor", "processor") \
            .max_iterations(10000) \
            .converge_when("converged == True") \
            .timeout(300) \
            .build()

    # Additional performance optimizations can be set at runtime:
    # - state_history_size: Limit state history
    # - enable_profiling: Disable profiling in production
    # - batch_size: Process multiple iterations per batch

Memory Optimization
-------------------

Efficient Data Structures
^^^^^^^^^^^^^^^^^^^^^^^^^

Choose the right data structure for your use case:

.. code-block:: python

    import numpy as np
    import pandas as pd
    from collections import deque
    from typing import List, Dict, Iterator

    # For large numerical datasets, use NumPy
    def process_large_numbers(data: List[float]) -> np.ndarray:
        """Process large numerical data efficiently with NumPy."""
        # Convert to NumPy array for vectorized operations
        arr = np.array(data, dtype=np.float32)  # Use float32 if precision allows

        # Vectorized operations are much faster than loops
        return np.sqrt(arr * 2.0 + 1.0)

    # For structured data with mixed types, use pandas
    def process_structured_data(data: List[Dict]) -> pd.DataFrame:
        """Process structured data efficiently with pandas."""
        df = pd.DataFrame(data)

        # Use categorical data for repeated strings
        if 'category' in df.columns:
            df['category'] = df['category'].astype('category')

        # Use appropriate numeric types
        for col in df.select_dtypes(include=['int64']).columns:
            if df[col].max() < 2**31:
                df[col] = df[col].astype('int32')

        return df

    # For FIFO operations, use deque
    def efficient_queue_processing(items: Iterator) -> List:
        """Process items with efficient queue operations."""
        queue = deque(maxlen=1000)  # Limit memory usage
        results = []

        for item in items:
            queue.append(item)
            if len(queue) == queue.maxlen:
                # Process batch
                batch_result = process_batch(list(queue))
                results.extend(batch_result)
                queue.clear()

        return results

Memory Pooling and Reuse
^^^^^^^^^^^^^^^^^^^^^^^^

Reduce memory allocations by reusing objects:

.. code-block:: python

    import gc
    from typing import Optional

    class MemoryPool:
        """Simple memory pool for reusing objects."""

        def __init__(self, factory_func, max_size: int = 100):
            self.factory = factory_func
            self.pool = []
            self.max_size = max_size

        def get(self):
            """Get an object from the pool or create new one."""
            if self.pool:
                return self.pool.pop()
            return self.factory()

        def put(self, obj):
            """Return an object to the pool."""
            if len(self.pool) < self.max_size:
                # Reset object state before returning to pool
                if hasattr(obj, 'reset'):
                    obj.reset()
                self.pool.append(obj)

    # Example usage in a node
    class MemoryOptimizedNode(Node):
        def __init__(self, node_id: str, config: Dict):
            super().__init__(node_id, config)
            self.buffer_pool = MemoryPool(lambda: bytearray(1024 * 1024))  # 1MB buffers

        def execute(self, inputs: Dict) -> Dict:
            buffer = self.buffer_pool.get()
            try:
                # Use buffer for processing
                result = self.process_with_buffer(inputs, buffer)
                return {"success": True, "data": result}
            finally:
                self.buffer_pool.put(buffer)

Streaming and Chunked Processing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Process large datasets in chunks to control memory usage:

.. code-block:: python

    from typing import Iterator, Dict

    def stream_process_csv(file_path: str, chunk_size: int = 10000) -> Iterator[Dict]:
        """Process large CSV files in chunks."""
        import pandas as pd

        chunk_iter = pd.read_csv(file_path, chunksize=chunk_size)

        for chunk in chunk_iter:
            # Process chunk
            processed = chunk.apply(lambda row: process_row(row), axis=1)

            # Yield results one by one to avoid memory buildup
            for result in processed:
                yield result

            # Force garbage collection after each chunk
            del chunk, processed
            gc.collect()

    class StreamingNode(Node):
        """Node that processes data in streaming fashion."""

        def execute(self, inputs: Dict) -> Dict:
            file_path = inputs["file_path"]
            chunk_size = self.config.get("chunk_size", 10000)

            results = []
            processed_count = 0

            for result in stream_process_csv(file_path, chunk_size):
                results.append(result)
                processed_count += 1

                # Periodically yield intermediate results
                if processed_count % 1000 == 0:
                    self.emit_progress({
                        "processed": processed_count,
                        "status": "processing"
                    })

            return {
                "success": True,
                "data": results,
                "metadata": {"total_processed": processed_count}
            }

CPU Optimization
----------------

Vectorization
^^^^^^^^^^^^^

Use vectorized operations whenever possible:

.. code-block:: python

    import numpy as np
    import pandas as pd
    from numba import jit, vectorize

    # Bad: Python loop (slow)
    def slow_calculation(values):
        result = []
        for v in values:
            result.append(v * 2 + np.sin(v))
        return result

    # Good: NumPy vectorization (fast)
    def fast_calculation(values):
        arr = np.array(values)
        return arr * 2 + np.sin(arr)

    # Better: JIT compilation with Numba (fastest)
    @jit(nopython=True)
    def fastest_calculation(values):
        result = np.empty_like(values)
        for i in range(len(values)):
            result[i] = values[i] * 2 + np.sin(values[i])
        return result

    # Vectorized function for element-wise operations
    @vectorize(['float64(float64)'], target='parallel')
    def vectorized_func(x):
        return x * 2 + np.sin(x)

Parallel Processing
^^^^^^^^^^^^^^^^^^^

Leverage multiple CPU cores for computational tasks:

.. code-block:: python

    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
    import asyncio
    from typing import Callable, List, Any

    class ParallelProcessor:
        """Utility class for parallel processing."""

        @staticmethod
        def cpu_bound_parallel(func: Callable, data: List[Any],
                              workers: int = None) -> List[Any]:
            """Process CPU-bound tasks in parallel using processes."""
            if workers is None:
                workers = min(mp.cpu_count(), len(data))

            with ProcessPoolExecutor(max_workers=workers) as executor:
                return list(executor.map(func, data))

        @staticmethod
        def io_bound_parallel(func: Callable, data: List[Any],
                             workers: int = None) -> List[Any]:
            """Process I/O-bound tasks in parallel using threads."""
            if workers is None:
                workers = min(32, len(data))  # Threads can handle more I/O

            with ThreadPoolExecutor(max_workers=workers) as executor:
                return list(executor.map(func, data))

        @staticmethod
        async def async_parallel(async_func: Callable, data: List[Any],
                                concurrency: int = 10) -> List[Any]:
            """Process async tasks with controlled concurrency."""
            semaphore = asyncio.Semaphore(concurrency)

            async def bounded_task(item):
                async with semaphore:
                    return await async_func(item)

            tasks = [bounded_task(item) for item in data]
            return await asyncio.gather(*tasks)

    # Example: Parallel node execution
    class ParallelWorkflowNode(Node):
        def execute(self, inputs: Dict) -> Dict:
            data_items = inputs["items"]
            processing_type = self.config.get("type", "cpu")

            if processing_type == "cpu":
                results = ParallelProcessor.cpu_bound_parallel(
                    self.process_item, data_items
                )
            elif processing_type == "io":
                results = ParallelProcessor.io_bound_parallel(
                    self.process_item, data_items
                )
            else:
                # Async processing
                results = asyncio.run(
                    ParallelProcessor.async_parallel(
                        self.async_process_item, data_items
                    )
                )

            return {"success": True, "data": results}

Caching Strategies
------------------

Function-Level Caching
^^^^^^^^^^^^^^^^^^^^^^

Cache expensive function calls:

.. code-block:: python

    from functools import lru_cache, wraps
    import time
    import hashlib
    import pickle

    # Simple LRU cache for pure functions
    @lru_cache(maxsize=128)
    def expensive_calculation(x: int, y: int) -> float:
        """Expensive calculation that benefits from caching."""
        time.sleep(0.1)  # Simulate expensive operation
        return (x ** 2 + y ** 2) ** 0.5

    # Custom cache with TTL (Time To Live)
    class TTLCache:
        def __init__(self, maxsize: int = 128, ttl: int = 300):
            self.cache = {}
            self.timestamps = {}
            self.maxsize = maxsize
            self.ttl = ttl

        def get(self, key):
            if key in self.cache:
                if time.time() - self.timestamps[key] < self.ttl:
                    return self.cache[key]
                else:
                    del self.cache[key]
                    del self.timestamps[key]
            return None

        def put(self, key, value):
            if len(self.cache) >= self.maxsize:
                # Remove oldest entry
                oldest_key = min(self.timestamps, key=self.timestamps.get)
                del self.cache[oldest_key]
                del self.timestamps[oldest_key]

            self.cache[key] = value
            self.timestamps[key] = time.time()

    def ttl_cache(ttl: int = 300, maxsize: int = 128):
        """Decorator for TTL caching."""
        cache = TTLCache(maxsize, ttl)

        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Create cache key
                key = hashlib.md5(
                    pickle.dumps((args, kwargs))
                ).hexdigest()

                # Try to get from cache
                result = cache.get(key)
                if result is not None:
                    return result

                # Compute and cache result
                result = func(*args, **kwargs)
                cache.put(key, result)
                return result

            wrapper.cache_info = lambda: {
                "size": len(cache.cache),
                "maxsize": cache.maxsize,
                "ttl": cache.ttl
            }
            wrapper.cache_clear = lambda: cache.cache.clear()
            return wrapper

        return decorator

Node-Level Caching
^^^^^^^^^^^^^^^^^^

Implement caching within nodes for repeated operations:

.. code-block:: python

    class CachedNode(Node):
        """Base class for nodes with caching capabilities."""

        def __init__(self, node_id: str, config: Dict):
            super().__init__(node_id, config)
            self.cache_enabled = config.get("cache_enabled", True)
            self.cache_ttl = config.get("cache_ttl", 300)  # 5 minutes
            self.cache = TTLCache(ttl=self.cache_ttl)

        def execute(self, inputs: Dict) -> Dict:
            if not self.cache_enabled:
                return self._execute_logic(inputs)

            # Generate cache key from inputs
            cache_key = self._generate_cache_key(inputs)

            # Try cache first
            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                return {
                    "success": True,
                    "data": cached_result,
                    "metadata": {"cache_hit": True}
                }

            # Execute and cache result
            result = self._execute_logic(inputs)
            if result.get("success"):
                self.cache.put(cache_key, result["data"])

            result.setdefault("metadata", {})["cache_hit"] = False
            return result

        def _generate_cache_key(self, inputs: Dict) -> str:
            """Generate cache key from inputs."""
            # Remove non-deterministic fields
            clean_inputs = {k: v for k, v in inputs.items()
                           if not k.startswith('_')}

            return hashlib.md5(
                pickle.dumps(clean_inputs, protocol=pickle.HIGHEST_PROTOCOL)
            ).hexdigest()

        def _execute_logic(self, inputs: Dict) -> Dict:
            """Override this method with actual node logic."""
            raise NotImplementedError

I/O Optimization
----------------

Asynchronous I/O
^^^^^^^^^^^^^^^^

Use async I/O for better concurrency:

.. code-block:: python

    import asyncio
    import aiohttp
    import aiofiles
    from typing import List, Dict, Any

    class AsyncIONode(Node):
        """Node optimized for I/O operations."""

        async def async_execute(self, inputs: Dict) -> Dict:
            """Async version of execute method."""
            try:
                if "urls" in inputs:
                    results = await self._fetch_multiple_urls(inputs["urls"])
                elif "files" in inputs:
                    results = await self._process_multiple_files(inputs["files"])
                else:
                    results = await self._async_process_single(inputs)

                return {"success": True, "data": results}
            except Exception as e:
                return {"success": False, "error": str(e)}

        async def _fetch_multiple_urls(self, urls: List[str]) -> List[Dict]:
            """Fetch multiple URLs concurrently."""
            connector = aiohttp.TCPConnector(limit=100)  # Connection pool
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                tasks = [self._fetch_url(session, url) for url in urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Handle exceptions
                clean_results = []
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        clean_results.append({
                            "url": urls[i],
                            "success": False,
                            "error": str(result)
                        })
                    else:
                        clean_results.append(result)

                return clean_results

        async def _fetch_url(self, session: aiohttp.ClientSession,
                            url: str) -> Dict:
            """Fetch single URL."""
            try:
                async with session.get(url) as response:
                    data = await response.text()
                    return {
                        "url": url,
                        "status": response.status,
                        "data": data,
                        "success": True
                    }
            except Exception as e:
                return {
                    "url": url,
                    "success": False,
                    "error": str(e)
                }

        async def _process_multiple_files(self, file_paths: List[str]) -> List[Dict]:
            """Process multiple files concurrently."""
            semaphore = asyncio.Semaphore(10)  # Limit concurrent file operations

            async def process_file(file_path: str) -> Dict:
                async with semaphore:
                    try:
                        async with aiofiles.open(file_path, 'r') as f:
                            content = await f.read()
                            processed = await self._async_process_content(content)
                            return {
                                "file": file_path,
                                "success": True,
                                "data": processed
                            }
                    except Exception as e:
                        return {
                            "file": file_path,
                            "success": False,
                            "error": str(e)
                        }

            tasks = [process_file(fp) for fp in file_paths]
            return await asyncio.gather(*tasks)

Connection Pooling
^^^^^^^^^^^^^^^^^^

Reuse connections for better performance:

.. code-block:: python

    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    class OptimizedHTTPNode(Node):
        """HTTP client with connection pooling and retries."""

        def __init__(self, node_id: str, config: Dict):
            super().__init__(node_id, config)
            self.session = self._create_optimized_session()

        def _create_optimized_session(self) -> requests.Session:
            """Create HTTP session with optimizations."""
            session = requests.Session()

            # Configure retries
            retry_strategy = Retry(
                total=3,
                status_forcelist=[429, 500, 502, 503, 504],
                backoff_factor=1,
                respect_retry_after_header=True
            )

            # Configure connection pooling
            adapter = HTTPAdapter(
                pool_connections=20,  # Number of connection pools
                pool_maxsize=20,     # Max connections per pool
                max_retries=retry_strategy,
                pool_block=False     # Don't block when pool is full
            )

            session.mount("http://", adapter)
            session.mount("https://", adapter)

            # Set reasonable timeouts
            session.timeout = (10, 30)  # (connect, read) timeouts

            return session

        def execute(self, inputs: Dict) -> Dict:
            """Execute HTTP requests with optimized session."""
            try:
                urls = inputs.get("urls", [])
                results = []

                for url in urls:
                    response = self.session.get(url)
                    results.append({
                        "url": url,
                        "status": response.status_code,
                        "data": response.text
                    })

                return {"success": True, "data": results}
            except Exception as e:
                return {"success": False, "error": str(e)}

        def __del__(self):
            """Clean up session on destruction."""
            if hasattr(self, 'session'):
                self.session.close()

Database Optimization
---------------------

Query Optimization
^^^^^^^^^^^^^^^^^^

Optimize database queries for better performance:

.. code-block:: python

    import sqlite3
    from contextlib import contextmanager
    from typing import Iterator, List, Tuple

    class OptimizedDatabaseNode(Node):
        """Database node with query optimizations."""

        def __init__(self, node_id: str, config: Dict):
            super().__init__(node_id, config)
            self.db_path = config["database_path"]
            self.batch_size = config.get("batch_size", 1000)

        @contextmanager
        def get_connection(self) -> Iterator[sqlite3.Connection]:
            """Get database connection with optimizations."""
            conn = sqlite3.connect(self.db_path)
            try:
                # Enable WAL mode for better concurrency
                conn.execute("PRAGMA journal_mode=WAL")

                # Increase cache size
                conn.execute("PRAGMA cache_size=10000")

                # Disable synchronous writes for speed (less safe)
                conn.execute("PRAGMA synchronous=NORMAL")

                # Use memory for temporary storage
                conn.execute("PRAGMA temp_store=MEMORY")

                yield conn
            finally:
                conn.close()

        def bulk_insert(self, table: str, data: List[Tuple]) -> Dict:
            """Perform bulk insert with optimizations."""
            try:
                with self.get_connection() as conn:
                    # Disable autocommit for bulk operations
                    conn.execute("BEGIN TRANSACTION")

                    try:
                        # Use executemany for bulk operations
                        placeholders = ",".join(["?" for _ in data[0]])
                        query = f"INSERT INTO {table} VALUES ({placeholders})"

                        # Process in batches to avoid memory issues
                        total_inserted = 0
                        for i in range(0, len(data), self.batch_size):
                            batch = data[i:i + self.batch_size]
                            conn.executemany(query, batch)
                            total_inserted += len(batch)

                        conn.execute("COMMIT")

                        return {
                            "success": True,
                            "rows_inserted": total_inserted
                        }
                    except Exception as e:
                        conn.execute("ROLLBACK")
                        raise e

            except Exception as e:
                return {"success": False, "error": str(e)}

        def optimized_query(self, query: str, params: Tuple = None) -> Dict:
            """Execute query with fetch optimizations."""
            try:
                with self.get_connection() as conn:
                    # Use row factory for named access
                    conn.row_factory = sqlite3.Row

                    cursor = conn.execute(query, params or ())

                    # Fetch in batches to avoid memory issues
                    results = []
                    while True:
                        batch = cursor.fetchmany(self.batch_size)
                        if not batch:
                            break

                        # Convert to dictionaries
                        results.extend([dict(row) for row in batch])

                    return {"success": True, "data": results}

            except Exception as e:
                return {"success": False, "error": str(e)}

Profiling and Monitoring
------------------------

Performance Profiling
^^^^^^^^^^^^^^^^^^^^^

Profile your code to identify bottlenecks:

.. code-block:: python

    import cProfile
    import pstats
    import time
    from functools import wraps
    from typing import Callable, Any

    def profile_execution(func: Callable) -> Callable:
        """Decorator to profile function execution."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            profiler = cProfile.Profile()
            profiler.enable()

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                execution_time = time.time() - start_time
                profiler.disable()

                # Save profile stats
                stats = pstats.Stats(profiler)
                stats.sort_stats('cumulative')

                # Print top functions
                print(f"\n{func.__name__} execution time: {execution_time:.2f}s")
                print("Top 10 functions by cumulative time:")
                stats.print_stats(10)

        return wrapper

    # Monitor memory usage
    import tracemalloc

    def memory_profile(func: Callable) -> Callable:
        """Decorator to profile memory usage."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracemalloc.start()

            try:
                result = func(*args, **kwargs)

                current, peak = tracemalloc.get_traced_memory()
                print(f"\n{func.__name__} memory usage:")
                print(f"Current: {current / 1024 / 1024:.2f} MB")
                print(f"Peak: {peak / 1024 / 1024:.2f} MB")

                return result
            finally:
                tracemalloc.stop()

        return wrapper

Performance Monitoring in Production
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The SDK includes built-in performance monitoring that automatically tracks metrics
during workflow execution:

Built-in Performance Tracking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from kailash.tracking import TaskManager
    from kailash.visualization.performance import PerformanceVisualizer
    from kailash.runtime.local import LocalRuntime

    # Performance metrics are collected automatically
    task_manager = TaskManager()
    runtime = LocalRuntime()

    # Execute workflow with tracking
    results, run_id = runtime.execute(workflow, task_manager=task_manager)

    # Generate performance visualizations
    perf_viz = PerformanceVisualizer(task_manager)
    outputs = perf_viz.create_run_performance_summary(run_id)

    # Compare multiple runs
    perf_viz.compare_runs([run_id_1, run_id_2, run_id_3])

The SDK automatically collects:
- Node execution times
- CPU usage percentage
- Memory consumption and peaks
- I/O operations (read/write bytes)
- Network I/O for API nodes

Custom Performance Monitoring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For additional custom metrics, you can extend the built-in monitoring:

.. code-block:: python

    import time
    import psutil
    from dataclasses import dataclass
    from typing import Dict, List

    @dataclass
    class PerformanceMetrics:
        execution_time: float
        memory_usage: float
        cpu_usage: float
        node_id: str
        timestamp: float

    class PerformanceMonitor:
        """Monitor performance metrics during workflow execution."""

        def __init__(self):
            self.metrics: List[PerformanceMetrics] = []
            self.process = psutil.Process()

        def start_monitoring(self, node_id: str) -> Dict:
            """Start monitoring for a node execution."""
            return {
                "node_id": node_id,
                "start_time": time.time(),
                "start_memory": self.process.memory_info().rss,
                "start_cpu": self.process.cpu_percent()
            }

        def end_monitoring(self, context: Dict):
            """End monitoring and record metrics."""
            end_time = time.time()
            end_memory = self.process.memory_info().rss
            end_cpu = self.process.cpu_percent()

            metrics = PerformanceMetrics(
                execution_time=end_time - context["start_time"],
                memory_usage=(end_memory - context["start_memory"]) / 1024 / 1024,  # MB
                cpu_usage=end_cpu,
                node_id=context["node_id"],
                timestamp=end_time
            )

            self.metrics.append(metrics)
            return metrics

        def get_summary(self) -> Dict:
            """Get performance summary."""
            if not self.metrics:
                return {"message": "No metrics recorded"}

            execution_times = [m.execution_time for m in self.metrics]
            memory_usage = [m.memory_usage for m in self.metrics]

            return {
                "total_nodes": len(self.metrics),
                "total_execution_time": sum(execution_times),
                "avg_execution_time": sum(execution_times) / len(execution_times),
                "max_execution_time": max(execution_times),
                "total_memory_used": sum(memory_usage),
                "avg_memory_used": sum(memory_usage) / len(memory_usage),
                "max_memory_used": max(memory_usage)
            }

    # Usage in a monitored node
    class MonitoredNode(Node):
        def __init__(self, node_id: str, config: Dict):
            super().__init__(node_id, config)
            self.monitor = PerformanceMonitor()

        def execute(self, inputs: Dict) -> Dict:
            context = self.monitor.start_monitoring(self.node_id)

            try:
                result = self._execute_logic(inputs)
                return result
            finally:
                metrics = self.monitor.end_monitoring(context)
                self.log_performance_metrics(metrics)

        def log_performance_metrics(self, metrics: PerformanceMetrics):
            """Log performance metrics."""
            self.logger.info(
                f"Node {metrics.node_id} - "
                f"Time: {metrics.execution_time:.2f}s, "
                f"Memory: {metrics.memory_usage:.2f}MB, "
                f"CPU: {metrics.cpu_usage:.1f}%"
            )
