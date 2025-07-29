# Performance Patterns

Patterns for optimizing workflow performance, managing resources, and handling scale.

## 🚀 AsyncWorkflowBuilder - 70%+ Code Reduction (NEW)

### High-Performance Async Workflows
```python
from kailash.workflow.async_builder import AsyncWorkflowBuilder
from kailash.workflow.async_patterns import AsyncPatterns

# Build high-performance async workflow with built-in patterns
workflow = (
    AsyncWorkflowBuilder()
    # Resource management
    .with_database("db", host="localhost", min_size=10, max_size=50)
    .with_http_client("api", connection_limit=100)
    .with_cache("cache", backend="redis")

    # Parallel data processing
    .add_async_code("fetch_data", """
db = await get_resource("db")
# Use connection pool efficiently
async with db.acquire() as conn:
    data = await conn.fetch("SELECT * FROM large_table")
result = {"items": [dict(row) for row in data]}
""")

    # Process items in parallel with rate limiting
    .add_parallel_map(
        "process_items",
        """
async def process_item(item):
    api = await get_resource("api")
    cache = await get_resource("cache")

    # Check cache first
    cached = await cache.get(f"item:{item['id']}")
    if cached:
        return json.loads(cached)

    # Process with external API
    response = await api.post("/process", json=item)
    result = await response.json()

    # Cache result
    await cache.setex(f"item:{item['id']}", 300, json.dumps(result))
    return result
""",
        max_workers=20,
        batch_size=100,
        timeout_per_item=5
    )
    .add_connection("fetch_data", "items", "process_items", "items")
    .build()
)

# Patterns for resilience and performance
AsyncPatterns.retry_with_backoff(
    builder, "flaky_operation", "...", max_retries=5
)
AsyncPatterns.circuit_breaker(
    builder, "external_service", "...", failure_threshold=10
)
```

### Performance Benefits
- **20x speedup** for I/O-bound operations
- **Resource pooling** prevents connection exhaustion
- **Automatic retries** improve reliability
- **Built-in caching** reduces external calls
- **Rate limiting** prevents API overwhelm

## 🚀 Phase 5.2 Developer Tools - Performance Optimization (NEW)

### Comprehensive Performance Analysis Workflow
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow import CycleAnalyzer, CycleProfiler, CycleDebugger
from kailash.runtime.local import LocalRuntime

def analyze_and_optimize_workflow(workflow, initial_params):
    """
    Complete workflow performance optimization using Phase 5.2 developer tools.

    This pattern demonstrates systematic performance optimization using
    the comprehensive suite of debugging, profiling, and analysis tools.
    """

    # 1. Initial Performance Baseline
    analyzer = CycleAnalyzer(
        analysis_level="comprehensive",
        enable_profiling=True,
        enable_debugging=True,
        output_directory="./performance_analysis"
    )

    session = analyzer.start_analysis_session("performance_optimization")

    # 2. Baseline Performance Measurement
    print("📊 Measuring baseline performance...")
    trace = analyzer.start_cycle_analysis(
        "baseline_cycle",
        workflow.workflow_id,
        max_iterations=100
    )

    # Execute workflow with tracking
    runtime = LocalRuntime()
    start_time = time.time()
    results, run_id = runtime.execute(workflow.build(), parameters=initial_params)
    baseline_time = time.time() - start_time

    # Complete baseline analysis
    analyzer.complete_cycle_analysis(
        trace,
        converged=True,
        termination_reason="baseline_complete"
    )

    baseline_report = analyzer.generate_cycle_report(trace)
    baseline_efficiency = baseline_report['performance']['efficiency_score']

    print(f"Baseline: {baseline_time:.3f}s, efficiency: {baseline_efficiency:.3f}")

    # 3. Identify Performance Bottlenecks
    profiler = CycleProfiler(enable_advanced_metrics=True)
    profiler.add_trace(trace)

    performance_metrics = profiler.analyze_performance()
    bottlenecks = performance_metrics.bottlenecks

    if bottlenecks:
        print(f"🚨 Bottlenecks identified: {bottlenecks}")

    # 4. Get Optimization Recommendations
    recommendations = profiler.get_optimization_recommendations()

    print("🎯 Optimization Recommendations:")
    for i, rec in enumerate(recommendations[:5], 1):
        print(f"  {i}. [{rec['priority']}] {rec['description']}")
        print(f"     → {rec['suggestion']}")

    # 5. Apply Optimizations and Re-test
    optimized_configs = apply_recommendations(recommendations)

    performance_improvements = []
    for config_name, optimized_config in optimized_configs.items():
        print(f"\n🔧 Testing optimization: {config_name}")

        # Create optimized workflow
        optimized_workflow = create_optimized_workflow(workflow, optimized_config)

        # Test optimized version
        opt_trace = analyzer.start_cycle_analysis(
            f"optimized_{config_name}",
            optimized_workflow.workflow_id
        )

        opt_start = time.time()
        opt_results, opt_run_id = runtime.execute(optimized_workflow.build(), parameters=initial_params)
        opt_time = time.time() - opt_start

        analyzer.complete_cycle_analysis(opt_trace, converged=True, termination_reason="optimization_test")

        opt_report = analyzer.generate_cycle_report(opt_trace)
        opt_efficiency = opt_report['performance']['efficiency_score']

        improvement = (opt_efficiency - baseline_efficiency) / baseline_efficiency * 100
        time_improvement = (baseline_time - opt_time) / baseline_time * 100

        performance_improvements.append({
            'name': config_name,
            'efficiency_improvement': improvement,
            'time_improvement': time_improvement,
            'final_efficiency': opt_efficiency,
            'final_time': opt_time
        })

        print(f"  Efficiency: {opt_efficiency:.3f} ({improvement:+.1f}%)")
        print(f"  Time: {opt_time:.3f}s ({time_improvement:+.1f}%)")

    # 6. Generate Comprehensive Report
    session_report = analyzer.generate_session_report()

    # Export detailed analysis
    analyzer.export_analysis_data(
        "performance_optimization_complete.json",
        include_traces=True
    )

    # 7. Select Best Configuration
    best_config = max(performance_improvements, key=lambda x: x['efficiency_improvement'])

    print(f"\n🏆 Best optimization: {best_config['name']}")
    print(f"   Efficiency improvement: {best_config['efficiency_improvement']:.1f}%")
    print(f"   Time improvement: {best_config['time_improvement']:.1f}%")

    return {
        'baseline': {'efficiency': baseline_efficiency, 'time': baseline_time},
        'best_optimization': best_config,
        'all_optimizations': performance_improvements,
        'session_report': session_report
    }

def apply_recommendations(recommendations):
    """Apply optimization recommendations to create test configurations."""
    configs = {}

    for rec in recommendations:
        if rec['category'] == 'efficiency':
            configs['increased_iterations'] = {
                'max_iterations': int(rec.get('target_improvement', '100').split()[-1])
            }
        elif rec['category'] == 'performance':
            configs['optimized_nodes'] = {
                'enable_caching': True,
                'batch_size': 1000
            }
        elif rec['category'] == 'memory':
            configs['memory_optimized'] = {
                'enable_streaming': True,
                'chunk_size': 500
            }

    return configs

def create_optimized_workflow(original_workflow, optimization_config):
    """Create optimized version of workflow based on configuration."""
    # This would create an optimized workflow based on the config
    # For demo purposes, return the original workflow
    return original_workflow

```

### Real-time Performance Monitoring Pattern
```python
from kailash.workflow import CycleDebugger
import time

def monitor_production_cycle_performance(workflow, runtime, parameters):
    """
    Monitor cycle performance in production with real-time alerts.

    This pattern provides continuous monitoring of cycle health
    with immediate alerts for performance degradation.
    """

    debugger = CycleDebugger(debug_level="detailed", enable_profiling=True)

    # Performance thresholds
    SLOW_ITERATION_THRESHOLD = 2.0  # seconds
    HIGH_MEMORY_THRESHOLD = 1000    # MB
    LOW_EFFICIENCY_THRESHOLD = 0.3  # efficiency score

    # Start monitoring
    trace = debugger.start_cycle(
        "production_monitoring",
        workflow.workflow_id,
        max_iterations=100
    )

    performance_alerts = []

    try:
        # Execute workflow with monitoring
        results, run_id = runtime.execute(workflow, parameters=parameters)

        # Simulate monitoring during execution
        for i in range(10):  # Simulate 10 iterations
            input_data = {"iteration": i, "data": f"data_{i}"}

            iteration = debugger.start_iteration(trace, input_data)

            # Simulate processing time
            processing_start = time.time()
            time.sleep(0.1)  # Simulate work
            processing_time = time.time() - processing_start

            output_data = {"result": f"processed_{i}", "processing_time": processing_time}

            debugger.end_iteration(trace, iteration, output_data)

            # Real-time performance checks
            if iteration.execution_time and iteration.execution_time > SLOW_ITERATION_THRESHOLD:
                alert = {
                    'type': 'SLOW_ITERATION',
                    'iteration': i,
                    'time': iteration.execution_time,
                    'threshold': SLOW_ITERATION_THRESHOLD
                }
                performance_alerts.append(alert)
                print(f"⚠️ ALERT: Slow iteration {i}: {iteration.execution_time:.3f}s")

            if iteration.memory_usage_mb and iteration.memory_usage_mb > HIGH_MEMORY_THRESHOLD:
                alert = {
                    'type': 'HIGH_MEMORY',
                    'iteration': i,
                    'memory_mb': iteration.memory_usage_mb,
                    'threshold': HIGH_MEMORY_THRESHOLD
                }
                performance_alerts.append(alert)
                print(f"⚠️ ALERT: High memory usage at iteration {i}: {iteration.memory_usage_mb:.1f}MB")

        # Complete monitoring
        debugger.end_cycle(trace, converged=True, termination_reason="monitoring_complete")

        # Generate performance report
        report = debugger.generate_report(trace)
        efficiency = report['performance']['efficiency_score']

        if efficiency < LOW_EFFICIENCY_THRESHOLD:
            alert = {
                'type': 'LOW_EFFICIENCY',
                'efficiency': efficiency,
                'threshold': LOW_EFFICIENCY_THRESHOLD
            }
            performance_alerts.append(alert)
            print(f"⚠️ ALERT: Low cycle efficiency: {efficiency:.3f}")

        # Performance summary
        stats = trace.get_statistics()
        print(f"\n📊 Performance Summary:")
        print(f"  Total iterations: {stats['total_iterations']}")
        print(f"  Average iteration time: {stats['avg_iteration_time']:.3f}s")
        print(f"  Efficiency score: {efficiency:.3f}")
        print(f"  Alerts generated: {len(performance_alerts)}")

        return {
            'performance_report': report,
            'alerts': performance_alerts,
            'efficiency': efficiency,
            'recommendations': debugger.generate_report(trace)['recommendations']
        }

    except Exception as e:
        debugger.end_cycle(trace, converged=False, termination_reason=f"error: {e}")
        raise

```

### Comparative Performance Testing Pattern
```python
from kailash.workflow import CycleProfiler

def compare_workflow_variants(workflow_variants, test_parameters):
    """
    Compare performance across multiple workflow implementations.

    This pattern enables A/B testing of different workflow configurations
    to identify the best performing approach.
    """

    profiler = CycleProfiler(enable_advanced_metrics=True)
    results = {}

    print(f"🧪 Testing {len(workflow_variants)} workflow variants...")

    # Test each variant
    for variant_name, workflow_config in workflow_variants.items():
        print(f"\n📈 Testing variant: {variant_name}")

        # Create workflow from config
        test_workflow = create_workflow_from_config(workflow_config)

        # Execute multiple runs for statistical significance
        variant_traces = []
        run_times = []

        for run in range(3):  # 3 runs per variant
            print(f"  Run {run + 1}/3...")

            start_time = time.time()
            trace = execute_workflow_with_profiling(test_workflow, test_parameters)
            end_time = time.time()

            variant_traces.append(trace)
            run_times.append(end_time - start_time)
            profiler.add_trace(trace)

        # Calculate variant statistics
        avg_time = sum(run_times) / len(run_times)
        min_time = min(run_times)
        max_time = max(run_times)

        results[variant_name] = {
            'avg_time': avg_time,
            'min_time': min_time,
            'max_time': max_time,
            'traces': variant_traces,
            'consistency': (max_time - min_time) / avg_time  # Lower is better
        }

        print(f"  Average time: {avg_time:.3f}s")
        print(f"  Time range: {min_time:.3f}s - {max_time:.3f}s")
        print(f"  Consistency: {results[variant_name]['consistency']:.3f}")

    # Generate comparative analysis
    performance_report = profiler.generate_performance_report()

    # Rank variants by performance
    ranked_variants = sorted(
        results.items(),
        key=lambda x: x[1]['avg_time']  # Sort by average time
    )

    print(f"\n🏆 Performance Rankings:")
    for i, (variant_name, stats) in enumerate(ranked_variants, 1):
        print(f"  {i}. {variant_name}: {stats['avg_time']:.3f}s (consistency: {stats['consistency']:.3f})")

    # Identify significant performance differences
    best_time = ranked_variants[0][1]['avg_time']
    significant_differences = []

    for variant_name, stats in ranked_variants[1:]:
        improvement_potential = (stats['avg_time'] - best_time) / best_time * 100
        if improvement_potential > 10:  # More than 10% difference
            significant_differences.append({
                'variant': variant_name,
                'improvement_potential': improvement_potential
            })

    if significant_differences:
        print(f"\n⚡ Significant Performance Opportunities:")
        for diff in significant_differences:
            print(f"  {diff['variant']}: {diff['improvement_potential']:.1f}% slower than best")

    # Generate optimization recommendations
    recommendations = profiler.get_optimization_recommendations()

    return {
        'rankings': ranked_variants,
        'performance_report': performance_report,
        'significant_differences': significant_differences,
        'recommendations': recommendations,
        'best_variant': ranked_variants[0][0]
    }

def execute_workflow_with_profiling(workflow, parameters):
    """Execute workflow and return execution trace for profiling."""
    # This would execute the workflow and return a trace
    # Implementation depends on specific workflow execution integration
    pass

def create_workflow_from_config(config):
    """Create workflow instance from configuration."""
    # This would create a workflow based on the provided configuration
    # Implementation depends on specific workflow configuration format
    pass

```

## 1. Caching Pattern

**Purpose**: Reduce redundant computations and external calls

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Advanced caching with TTL and LRU eviction
workflow.add_node("PythonCodeNode", "smart_cache", {}),
    code="""
import hashlib
import json
import time
from collections import OrderedDict

# Initialize cache structure
if not hasattr(self, '_cache'):
    self._cache = OrderedDict()
    self._cache_stats = {
        'hits': 0,
        'misses': 0,
        'evictions': 0
    }

# Configuration
max_cache_size = config.get('max_cache_size', 1000)
ttl_seconds = config.get('ttl_seconds', 3600)  # 1 hour default

# Generate cache key
cache_key = generate_cache_key(request_data)

# Check cache with TTL
cached_entry = self._cache.get(cache_key)
if cached_entry:
    # Check if entry is still valid
    if time.time() - cached_entry['timestamp'] < ttl_seconds:
        # Cache hit
        self._cache_stats['hits'] += 1

        # Move to end (LRU behavior)
        self._cache.move_to_end(cache_key)

        print(f"Cache hit! Stats: {self._cache_stats}")
        result = {
            'data': cached_entry['data'],
            'cache_hit': True,
            'cache_age': time.time() - cached_entry['timestamp']
        }
        return result
    else:
        # Expired entry
        del self._cache[cache_key]

# Cache miss
self._cache_stats['misses'] += 1

# Perform expensive operation
start_time = time.time()
computed_result = perform_expensive_operation(request_data)
computation_time = time.time() - start_time

# Store in cache
self._cache[cache_key] = {
    'data': computed_result,
    'timestamp': time.time()
}

# LRU eviction if needed
while len(self._cache) > max_cache_size:
    # Remove oldest item
    evicted_key = next(iter(self._cache))
    del self._cache[evicted_key]
    self._cache_stats['evictions'] += 1

print(f"Cache miss. Computation took {computation_time:.2f}s. Stats: {self._cache_stats}")

result = {
    'data': computed_result,
    'cache_hit': False,
    'computation_time': computation_time
}

def generate_cache_key(data):
    # Create deterministic cache key
    key_data = json.dumps(data, sort_keys=True)
    return hashlib.sha256(key_data.encode()).hexdigest()

def perform_expensive_operation(data):
    # Simulate expensive computation
    import time
    time.sleep(1)  # Simulate delay
    return {
        'processed': data,
        'timestamp': time.time()
    }
""",
    imports=["hashlib", "json", "time", "from collections import OrderedDict"],
    config={
        "max_cache_size": 500,
        "ttl_seconds": 1800  # 30 minutes
    }
)

# Distributed cache pattern with Redis
workflow.add_node("PythonCodeNode", "redis_cache", {}),
    code="""
import redis
import json
import pickle

# Redis connection
redis_client = redis.Redis(
    host=config.get('redis_host', 'localhost'),
    port=config.get('redis_port', 6379),
    decode_responses=False  # For binary data
)

# Generate cache key with namespace
cache_key = f"{config['cache_namespace']}:{generate_cache_key(request_data)}"

try:
    # Try to get from Redis
    cached_data = redis_client.get(cache_key)

    if cached_data:
        # Deserialize and return
        result_data = pickle.loads(cached_data)
        result = {
            'data': result_data,
            'cache_hit': True,
            'source': 'redis'
        }
        return result

except redis.RedisError as e:
    print(f"Redis error: {e}, falling back to computation")

# Compute if not in cache
computed_result = perform_expensive_operation(request_data)

# Store in Redis with TTL
try:
    serialized_data = pickle.dumps(computed_result)
    redis_client.setex(
        cache_key,
        config.get('ttl_seconds', 3600),
        serialized_data
    )
except redis.RedisError as e:
    print(f"Failed to cache in Redis: {e}")

result = {
    'data': computed_result,
    'cache_hit': False,
    'source': 'computed'
}
""",
    imports=["redis", "json", "pickle"],
    config={
        "redis_host": "localhost",
        "redis_port": 6379,
        "cache_namespace": "kailash:workflow",
        "ttl_seconds": 3600
    }
)

```

## 2. Lazy Loading Pattern

**Purpose**: Load data only when needed to reduce memory usage

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
workflow.add_node("PythonCodeNode", "lazy_loader", {}),
    code="""
class LazyDataLoader:
    def __init__(self, data_config):
        self.config = data_config
        self._data = None
        self._loaded_chunks = {}

    def __getitem__(self, key):
        # Load chunk on demand
        chunk_id = key // self.config['chunk_size']

        if chunk_id not in self._loaded_chunks:
            self._load_chunk(chunk_id)

        return self._loaded_chunks[chunk_id][key % self.config['chunk_size']]

    def _load_chunk(self, chunk_id):
        # Simulate loading chunk from disk/database
        print(f"Loading chunk {chunk_id}")

        start_idx = chunk_id * self.config['chunk_size']
        end_idx = start_idx + self.config['chunk_size']

        # In real scenario, this would read from file/database
        chunk_data = load_data_range(
            self.config['data_source'],
            start_idx,
            end_idx
        )

        self._loaded_chunks[chunk_id] = chunk_data

        # Evict old chunks if memory limit reached
        if len(self._loaded_chunks) > self.config['max_chunks_in_memory']:
            # Remove least recently used chunk
            oldest_chunk = min(self._loaded_chunks.keys())
            del self._loaded_chunks[oldest_chunk]
            print(f"Evicted chunk {oldest_chunk}")

# Initialize lazy loader
if not hasattr(self, '_loader'):
    self._loader = LazyDataLoader({
        'data_source': config['data_source'],
        'chunk_size': config.get('chunk_size', 1000),
        'max_chunks_in_memory': config.get('max_chunks', 10)
    })

# Process data lazily
results = []
for idx in processing_indices:
    # Data is loaded on-demand
    item = self._loader[idx]
    processed = process_item(item)
    results.append(processed)

result = {
    'processed_count': len(results),
    'chunks_loaded': len(self._loader._loaded_chunks),
    'results': results
}

def load_data_range(source, start, end):
    # Simulate loading data range
    return list(range(start, end))

def process_item(item):
    return item * 2
""",
    config={
        "data_source": "large_dataset.db",
        "chunk_size": 1000,
        "max_chunks": 5
    }
)

```

## 3. Connection Pooling Pattern

**Purpose**: Reuse expensive connections efficiently

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
workflow.add_node("PythonCodeNode", "connection_pool", {}),
    code="""
import queue
import threading
import time

class ConnectionPool:
    def __init__(self, config):
        self.config = config
        self._pool = queue.Queue(maxsize=config['max_connections'])
        self._all_connections = []
        self._lock = threading.Lock()
        self._stats = {
            'created': 0,
            'active': 0,
            'waiting': 0,
            'total_wait_time': 0
        }

        # Pre-create minimum connections
        for _ in range(config['min_connections']):
            conn = self._create_connection()
            self._pool.put(conn)

    def _create_connection(self):
        # Simulate expensive connection creation
        time.sleep(0.1)

        with self._lock:
            self._stats['created'] += 1
            conn = {
                'id': self._stats['created'],
                'created_at': time.time(),
                'last_used': time.time(),
                'use_count': 0
            }
            self._all_connections.append(conn)

        print(f"Created connection {conn['id']}")
        return conn

    def get_connection(self, timeout=None):
        start_wait = time.time()

        try:
            # Try to get from pool
            conn = self._pool.get(timeout=timeout or self.config['timeout'])

        except queue.Empty:
            # Pool exhausted, create new if under limit
            with self._lock:
                if len(self._all_connections) < self.config['max_connections']:
                    conn = self._create_connection()
                else:
                    raise Exception("Connection pool exhausted")

        # Update stats
        wait_time = time.time() - start_wait
        with self._lock:
            self._stats['active'] += 1
            self._stats['total_wait_time'] += wait_time
            if wait_time > 0.01:
                self._stats['waiting'] += 1

        conn['last_used'] = time.time()
        conn['use_count'] += 1

        return conn

    def return_connection(self, conn):
        # Return to pool
        with self._lock:
            self._stats['active'] -= 1

        # Check if connection is still valid
        if time.time() - conn['created_at'] < self.config['max_lifetime']:
            self._pool.put(conn)
        else:
            # Connection expired, remove it
            with self._lock:
                self._all_connections.remove(conn)
            print(f"Retired connection {conn['id']} (expired)")

# Initialize pool
if not hasattr(self, '_pool'):
    self._pool = ConnectionPool({
        'min_connections': 5,
        'max_connections': 20,
        'timeout': 30,
        'max_lifetime': 300  # 5 minutes
    })

# Use connection from pool
conn = None
try:
    conn = self._pool.get_connection()

    # Use connection for work
    result_data = perform_database_operation(conn, query_data)

    result = {
        'success': True,
        'data': result_data,
        'connection_id': conn['id'],
        'pool_stats': self._pool._stats
    }

finally:
    if conn:
        self._pool.return_connection(conn)

def perform_database_operation(conn, data):
    # Simulate database operation
    time.sleep(0.05)
    return {'query_result': f"Result from connection {conn['id']}"}
""",
    imports=["queue", "threading", "time"]
)

```

## 4. Prefetching Pattern

**Purpose**: Load data in advance to reduce latency

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
workflow.add_node("PythonCodeNode", "prefetcher", {}),
    code="""
import threading
import queue
import time

class PrefetchBuffer:
    def __init__(self, fetch_func, config):
        self.fetch_func = fetch_func
        self.config = config
        self.buffer = queue.Queue(maxsize=config['buffer_size'])
        self.current_index = 0
        self.prefetch_thread = None
        self.stop_prefetching = threading.Event()

    def start(self):
        self.prefetch_thread = threading.Thread(target=self._prefetch_worker)
        self.prefetch_thread.daemon = True
        self.prefetch_thread.start()

    def _prefetch_worker(self):
        while not self.stop_prefetching.is_set():
            if self.buffer.qsize() < self.config['buffer_size']:
                # Fetch next batch
                try:
                    batch = self.fetch_func(
                        self.current_index,
                        self.config['batch_size']
                    )

                    for item in batch:
                        self.buffer.put(item, timeout=1)

                    self.current_index += len(batch)
                    print(f"Prefetched batch, buffer size: {self.buffer.qsize()}")

                except Exception as e:
                    print(f"Prefetch error: {e}")

            else:
                # Buffer full, wait
                time.sleep(0.1)

    def get_next(self, timeout=None):
        return self.buffer.get(timeout=timeout or self.config['timeout'])

    def stop(self):
        self.stop_prefetching.set()
        if self.prefetch_thread:
            self.prefetch_thread.join()

# Initialize prefetcher
if not hasattr(self, '_prefetcher'):
    def fetch_batch(start_idx, size):
        # Simulate fetching data batch
        time.sleep(0.5)  # Simulate network delay
        return [{'id': i, 'data': f'item_{i}'} for i in range(start_idx, start_idx + size)]

    self._prefetcher = PrefetchBuffer(fetch_batch, {
        'buffer_size': 50,
        'batch_size': 10,
        'timeout': 30
    })
    self._prefetcher.start()

# Process with prefetching
results = []
process_count = config.get('process_count', 100)

start_time = time.time()
for i in range(process_count):
    # Get prefetched item (no wait if buffer has data)
    item = self._prefetcher.get_next()

    # Process item
    processed = {
        'original': item,
        'processed_at': time.time(),
        'result': item['data'].upper()
    }
    results.append(processed)

    # Simulate processing time
    time.sleep(0.01)

processing_time = time.time() - start_time

result = {
    'processed_count': len(results),
    'processing_time': processing_time,
    'avg_time_per_item': processing_time / len(results) if results else 0,
    'buffer_remaining': self._prefetcher.buffer.qsize()
}

# Cleanup
self._prefetcher.stop()
""",
    imports=["threading", "queue", "time"],
    config={"process_count": 200}
)

```

## 5. Memory-Efficient Streaming Pattern

**Purpose**: Process large datasets without loading everything into memory

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
workflow.add_node("PythonCodeNode", "stream_processor", {}),
    code="""
import io
import csv
import gc

def process_large_file_streaming(file_path, chunk_size=1000):
    '''Generator that yields processed chunks without loading entire file'''

    processed_count = 0
    chunk_buffer = []

    with open(file_path, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)

        for row in reader:
            # Process row
            processed_row = {
                'id': row.get('id'),
                'value': float(row.get('value', 0)) * 2,
                'category': row.get('category', 'unknown').upper()
            }

            chunk_buffer.append(processed_row)
            processed_count += 1

            # Yield chunk when buffer is full
            if len(chunk_buffer) >= chunk_size:
                yield chunk_buffer
                chunk_buffer = []

                # Force garbage collection periodically
                if processed_count % (chunk_size * 10) == 0:
                    gc.collect()
                    print(f"Processed {processed_count} rows")

        # Yield remaining items
        if chunk_buffer:
            yield chunk_buffer

# Stream process with minimal memory usage
output_file = config.get('output_file', 'processed_output.jsonl')
total_processed = 0

with open(output_file, 'w', encoding='utf-8') as out:
    for chunk in process_large_file_streaming(
        config['input_file'],
        config.get('chunk_size', 500)
    ):
        # Process chunk
        for item in chunk:
            # Write as JSON lines (streaming output)
            json.dump(item, out)
            out.write('\\n')

        total_processed += len(chunk)

        # Flush periodically
        if total_processed % 5000 == 0:
            out.flush()

result = {
    'total_processed': total_processed,
    'output_file': output_file,
    'memory_efficient': True
}
""",
    imports=["io", "csv", "gc", "json"],
    config={
        "input_file": "large_dataset.csv",
        "output_file": "processed_stream.jsonl",
        "chunk_size": 1000
    }
)

```

## 6. Async I/O Pattern

**Purpose**: Maximize throughput with non-blocking I/O operations

```python
# Async workflow node
workflow.add_node("PythonCodeNode", "async_io_processor", {}),
    code="""
import asyncio
import aiohttp
import aiofiles
import time

async def fetch_url_async(session, url):
    '''Fetch URL asynchronously'''
    try:
        async with session.get(url, timeout=10) as response:
            return {
                'url': url,
                'status': response.status,
                'data': await response.text(),
                'headers': dict(response.headers)
            }
    except Exception as e:
        return {
            'url': url,
            'error': str(e)
        }

async def process_async_batch(urls, max_concurrent=10):
    '''Process URLs with controlled concurrency'''

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_with_semaphore(session, url):
        async with semaphore:
            return await fetch_url_async(session, url)

    # Create session and fetch all URLs
    async with aiohttp.ClientSession() as session:
        tasks = [
            fetch_with_semaphore(session, url)
            for url in urls
        ]

        results = await asyncio.gather(*tasks)

    return results

async def write_results_async(results, output_file):
    '''Write results asynchronously'''
    async with aiofiles.open(output_file, 'w') as f:
        for result in results:
            await f.write(json.dumps(result) + '\\n')

# Run async operations
urls = config.get('urls', [])
start_time = time.time()

# Create event loop if needed
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Process URLs asynchronously
results = loop.run_until_complete(
    process_async_batch(urls, config.get('max_concurrent', 20))
)

# Write results asynchronously
loop.run_until_complete(
    write_results_async(results, config.get('output_file', 'async_results.jsonl'))
)

elapsed_time = time.time() - start_time

result = {
    'total_urls': len(urls),
    'successful': sum(1 for r in results if 'error' not in r),
    'failed': sum(1 for r in results if 'error' in r),
    'elapsed_time': elapsed_time,
    'urls_per_second': len(urls) / elapsed_time if elapsed_time > 0 else 0
}
""",
    imports=["asyncio", "aiohttp", "aiofiles", "time", "json"],
    config={
        "urls": ["http://example.com/api/1", "http://example.com/api/2"],
        "max_concurrent": 50,
        "output_file": "async_results.jsonl"
    }
)

```

## Database Connection Pooling Pattern

### Production-Grade Connection Management with WorkflowConnectionPool

```python
from kailash.nodes.data import WorkflowConnectionPool
from kailash.nodes.data.query_router import QueryRouterNode
from kailash.workflow.builder import WorkflowBuilder, WorkflowBuilder
from kailash.runtime.local import LocalRuntime
import asyncio
from contextlib import asynccontextmanager

class DatabaseService:
    """
    Production database service with connection pooling and Phase 2 features.

    This pattern demonstrates best practices for database operations
    in high-concurrency production environments with intelligent routing.
    """

    def __init__(self, config):
        self.pool = WorkflowConnectionPool(
            name="production_pool",
            database_type=config["db_type"],
            host=config["host"],
            port=config["port"],
            database=config["database"],
            user=config["user"],
            password=config["password"],
            min_connections=config.get("min_connections", 5),
            max_connections=config.get("max_connections", 20),
            health_threshold=config.get("health_threshold", 70),
            pre_warm=config.get("pre_warm", True),
            # Phase 2 features
            adaptive_sizing=config.get("adaptive_sizing", True),
            enable_query_routing=config.get("enable_query_routing", True)
        )

        # Phase 2: Query Router for intelligent routing
        self.router = QueryRouterNode(
            name="query_router",
            connection_pool="production_pool",
            enable_read_write_split=config.get("read_write_split", True),
            cache_size=config.get("cache_size", 2000),
            pattern_learning=config.get("pattern_learning", True)
        )

        self._initialized = False

    async def initialize(self):
        """Initialize the connection pool."""
        if not self._initialized:
            await self.pool.execute({"operation": "initialize"})
            self._initialized = True

            # Start monitoring task
            asyncio.create_task(self._monitor_pool_health())

    @asynccontextmanager
    async def get_connection(self):
        """Context manager for safe connection handling."""
        conn = await self.pool.execute({"operation": "acquire"})
        conn_id = conn["connection_id"]

        try:
            yield conn_id
        finally:
            await self.pool.execute({
                "operation": "release",
                "connection_id": conn_id
            })

    async def execute_query(self, query, params=None, fetch_mode="all", use_router=True):
        """Execute a query with automatic connection management.

        Args:
            query: SQL query to execute
            params: Query parameters
            fetch_mode: 'all', 'one', or 'none'
            use_router: Use query router (recommended) or direct pool access
        """
        if use_router:
            # Phase 2: Use router for intelligent routing and caching
            result = await self.router.execute({
                "query": query,
                "parameters": params or [],
                "fetch_mode": fetch_mode
            })
            return result["data"]
        else:
            # Direct pool access (for special cases)
            async with self.get_connection() as conn_id:
                result = await self.pool.execute({
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": query,
                    "params": params or [],
                    "fetch_mode": fetch_mode
                })
                return result["data"]

    async def execute_transaction(self, operations):
        """Execute multiple operations in a transaction."""
        async with self.get_connection() as conn_id:
            try:
                # Start transaction
                await self.pool.execute({
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": "BEGIN",
                    "fetch_mode": "one"
                })

                # Execute operations
                results = []
                for op in operations:
                    result = await self.pool.execute({
                        "operation": "execute",
                        "connection_id": conn_id,
                        "query": op["query"],
                        "params": op.get("params", []),
                        "fetch_mode": op.get("fetch_mode", "one")
                    })
                    results.append(result["data"])

                # Commit transaction
                await self.pool.execute({
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": "COMMIT",
                    "fetch_mode": "one"
                })

                return results

            except Exception as e:
                # Rollback on error
                await self.pool.execute({
                    "operation": "execute",
                    "connection_id": conn_id,
                    "query": "ROLLBACK",
                    "fetch_mode": "one"
                })
                raise

    async def _monitor_pool_health(self):
        """Background task to monitor pool health."""
        while self._initialized:
            try:
                stats = await self.pool.execute({"operation": "stats"})

                # Log warnings for potential issues
                if stats["current_state"]["available_connections"] == 0:
                    logger.warning("Connection pool exhausted!")

                if stats["queries"]["error_rate"] > 0.05:
                    logger.warning(f"High error rate: {stats['queries']['error_rate']:.2%}")

                # Check individual connection health
                for conn_id, health in stats["current_state"]["health_scores"].items():
                    if health < 60:
                        logger.warning(f"Connection {conn_id} health degraded: {health}")

                await asyncio.sleep(30)  # Check every 30 seconds

            except Exception as e:
                logger.error(f"Pool monitoring error: {e}")
                await asyncio.sleep(60)

# Usage in a high-performance workflow
workflow = WorkflowBuilder("order_processing")

# Add database service
workflow.add_node("db_service", "PythonCodeNode", {
    "code": """
# Initialize database service
db_config = {
    "db_type": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "orders",
    "user": "app_user",
    "password": "secure_password",
    "min_connections": 10,
    "max_connections": 50
}

db_service = DatabaseService(db_config)
await db_service.initialize()

# Process orders concurrently
async def process_order(order_id):
    # Get order details
    order = await db_service.execute_query(
        "SELECT * FROM orders WHERE id = $1 AND status = 'pending'",
        [order_id],
        fetch_mode="one"
    )

    if not order:
        return {"order_id": order_id, "status": "not_found"}

    # Process payment and update inventory in transaction
    operations = [
        {
            "query": "UPDATE orders SET status = 'processing' WHERE id = $1",
            "params": [order_id]
        },
        {
            "query": "INSERT INTO payments (order_id, amount, status) VALUES ($1, $2, 'pending')",
            "params": [order_id, order["total_amount"]]
        },
        {
            "query": "UPDATE inventory SET quantity = quantity - $1 WHERE product_id = $2",
            "params": [order["quantity"], order["product_id"]]
        }
    ]

    try:
        await db_service.execute_transaction(operations)
        return {"order_id": order_id, "status": "processed"}
    except Exception as e:
        return {"order_id": order_id, "status": "failed", "error": str(e)}

# Process multiple orders concurrently
order_ids = inputs.get("order_ids", [])
results = await asyncio.gather(*[
    process_order(order_id) for order_id in order_ids
])

# Get pool statistics
stats = await db_service.pool.execute({"operation": "stats"})

result = {
    "processed_orders": results,
    "pool_stats": {
        "total_queries": stats["queries"]["executed"],
        "error_rate": stats["queries"]["error_rate"],
        "pool_efficiency": stats["queries"]["executed"] / stats["connections"]["created"],
        "active_connections": stats["current_state"]["active_connections"]
    }
}
""",
    imports=["asyncio", "logging"],
    parameters={"order_ids": []}
})

```

### Phase 2: Intelligent Query Routing Pattern

```python
from kailash.nodes.data.query_router import QueryRouterNode
from kailash.workflow.builder import WorkflowBuilder

# Create workflow with intelligent routing
async def create_intelligent_db_workflow():
    """
    Workflow demonstrating Phase 2 intelligent features:
    - Query classification and routing
    - Prepared statement caching
    - Pattern learning
    - Adaptive pool sizing
    """

    workflow = WorkflowBuilder("intelligent_analytics")

    # Pool with all Phase 2 features enabled
    workflow.add_node(
        "smart_pool",
        WorkflowConnectionPool,
        {
            "database_type": "postgresql",
            "host": "analytics.db.internal",
            "database": "analytics",
            "min_connections": 5,
            "max_connections": 100,
            "adaptive_sizing": True,      # Dynamic pool sizing
            "enable_query_routing": True, # Pattern tracking
            "health_threshold": 70
        }
    )

    # Query router for intelligent routing
    workflow.add_node(
        "router",
        QueryRouterNode,
        {
            "connection_pool": "smart_pool",
            "enable_read_write_split": True,
            "cache_size": 5000,  # Large cache for analytics
            "pattern_learning": True,
            "health_threshold": 60
        }
    )

    # Analytics queries with router
    workflow.add_node(
        "run_analytics",
        "PythonCodeNode",
        {
            "code": """
# Complex analytics queries benefit from caching
queries = [
    # This query will be classified as READ_COMPLEX
    {
        "name": "revenue_by_segment",
        "query": '''
            SELECT
                s.segment_name,
                COUNT(DISTINCT c.customer_id) as customers,
                SUM(o.total_amount) as revenue,
                AVG(o.total_amount) as avg_order_value
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            JOIN segments s ON c.segment_id = s.id
            WHERE o.order_date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY s.segment_name
            ORDER BY revenue DESC
        ''',
        "parameters": []
    },
    # This will be classified as READ_SIMPLE and cached
    {
        "name": "active_products",
        "query": "SELECT * FROM products WHERE status = ? AND category = ?",
        "parameters": ["active", "electronics"]
    }
]

# Execute with router - benefits from caching and optimal routing
results = {}
for q in queries:
    result = await router.execute({
        "query": q["query"],
        "parameters": q["parameters"],
        "fetch_mode": "all"
    })

    results[q["name"]] = {
        "data": result["data"],
        "cache_hit": result["routing_metadata"]["cache_hit"],
        "query_type": result["routing_metadata"]["query_type"],
        "routing_time_ms": result["routing_metadata"]["routing_time_ms"]
    }

# Get performance insights
router_metrics = await router.get_metrics()
pool_stats = await smart_pool.execute({"operation": "stats"})

return {
    "results": results,
    "performance": {
        "cache_hit_rate": router_metrics["cache_stats"]["hit_rate"],
        "avg_routing_time": router_metrics["router_metrics"]["avg_routing_time_ms"],
        "pool_utilization": pool_stats["current_state"]["active_connections"] / pool_stats["current_state"]["total_connections"],
        "queries_per_connection": pool_stats["queries"]["executed"] / pool_stats["connections"]["created"]
    }
}
""",
            "imports": ["asyncio"],
            "inputs": {"router": "{{router}}", "smart_pool": "{{smart_pool}}"}
        }
    )

    return workflow.build()

# Pattern Learning Example
async def demonstrate_pattern_learning():
    """Show how pattern learning improves performance over time."""

    service = DatabaseService({
        "db_type": "postgresql",
        "host": "localhost",
        "database": "app_db",
        "pattern_learning": True,
        "adaptive_sizing": True
    })

    await service.initialize()

    # Simulate typical workload pattern
    for day in range(7):
        print(f"\nDay {day + 1} simulation:")

        # Morning: Light load
        for _ in range(10):
            await service.execute_query(
                "SELECT * FROM users WHERE last_login > ?",
                [datetime.now() - timedelta(days=1)]
            )

        # Afternoon: Heavy analytics
        analytics_queries = [
            "SELECT COUNT(*) FROM orders WHERE status = ?",
            "SELECT SUM(amount) FROM transactions WHERE date > ?",
            "SELECT * FROM products WHERE category = ? LIMIT 100"
        ]

        tasks = []
        for _ in range(50):
            for query in analytics_queries:
                tasks.append(service.execute_query(query, ["active"]))

        await asyncio.gather(*tasks)

        # Evening: Batch updates
        for _ in range(20):
            await service.execute_transaction([
                {"query": "UPDATE users SET last_seen = NOW() WHERE id = ?", "params": [i]}
                for i in range(100, 110)
            ])

        # Check what the system learned
        if service.pool.query_pattern_tracker:
            patterns = service.pool.query_pattern_tracker.get_frequent_patterns()
            forecast = service.pool.query_pattern_tracker.get_workload_forecast()

            print(f"Patterns detected: {len(patterns)}")
            print(f"Predicted peak load: {forecast['peak_hours']}")
            print(f"Recommended pool size: {forecast['recommended_pool_size']}")

        # Pool should adapt its size
        stats = await service.pool.execute({"operation": "stats"})
        print(f"Current pool size: {stats['current_state']['total_connections']}")
```

### Connection Pool Sizing Guidelines

```python
# Calculate optimal pool size based on workload
def calculate_pool_size(config):
    """
    Calculate optimal connection pool size.

    Formula: pool_size = (concurrent_users * queries_per_request) / connection_reuse_factor
    """
    concurrent_users = config.get("concurrent_users", 100)
    queries_per_request = config.get("queries_per_request", 5)
    connection_reuse_factor = config.get("reuse_factor", 10)

    # Base calculation
    optimal_size = (concurrent_users * queries_per_request) // connection_reuse_factor

    # Apply bounds
    min_size = max(2, optimal_size // 4)
    max_size = min(100, optimal_size * 2)  # Database connection limits

    return {
        "min_connections": min_size,
        "max_connections": max_size,
        "optimal": optimal_size
    }

# Workload profiles
profiles = {
    "low_traffic": {
        "concurrent_users": 10,
        "queries_per_request": 3,
        "min_connections": 2,
        "max_connections": 10
    },
    "medium_traffic": {
        "concurrent_users": 100,
        "queries_per_request": 5,
        "min_connections": 5,
        "max_connections": 25
    },
    "high_traffic": {
        "concurrent_users": 1000,
        "queries_per_request": 5,
        "min_connections": 20,
        "max_connections": 100
    },
    "burst_traffic": {
        "concurrent_users": 5000,
        "queries_per_request": 2,
        "min_connections": 50,
        "max_connections": 200,
        "health_threshold": 60  # More aggressive recycling
    }
}
```

### Performance Monitoring Pattern

```python
from kailash.nodes.code import PythonCodeNode

monitoring_node = PythonCodeNode(
    name="pool_monitor",
    code="""
import json
from datetime import datetime

# Get pool statistics
stats = await pool.execute({"operation": "stats"})

# Calculate key metrics
metrics = {
    "timestamp": datetime.now().isoformat(),
    "pool_name": stats["pool_name"],
    "connection_metrics": {
        "total": stats["current_state"]["total_connections"],
        "active": stats["current_state"]["active_connections"],
        "available": stats["current_state"]["available_connections"],
        "utilization": stats["current_state"]["active_connections"] / stats["current_state"]["total_connections"]
    },
    "query_metrics": {
        "total_executed": stats["queries"]["executed"],
        "error_count": stats["queries"]["errors"],
        "error_rate": stats["queries"]["error_rate"],
        "avg_queries_per_connection": stats["queries"]["executed"] / max(1, stats["connections"]["created"])
    },
    "performance": {
        "avg_acquisition_time_ms": stats["performance"]["avg_acquisition_time_ms"],
        "p99_acquisition_time_ms": stats["performance"]["p99_acquisition_time_ms"]
    },
    "health": {
        "avg_health_score": sum(stats["current_state"]["health_scores"].values()) / len(stats["current_state"]["health_scores"]),
        "unhealthy_connections": sum(1 for score in stats["current_state"]["health_scores"].values() if score < 70)
    }
}

# Alert on issues
alerts = []
if metrics["connection_metrics"]["utilization"] > 0.9:
    alerts.append("WARNING: Connection pool near capacity")

if metrics["query_metrics"]["error_rate"] > 0.05:
    alerts.append("ERROR: High database error rate")

if metrics["health"]["unhealthy_connections"] > 2:
    alerts.append("WARNING: Multiple unhealthy connections")

result = {
    "metrics": metrics,
    "alerts": alerts,
    "recommendations": []
}

# Provide recommendations
if metrics["connection_metrics"]["utilization"] > 0.8:
    result["recommendations"].append("Consider increasing max_connections")

if metrics["query_metrics"]["avg_queries_per_connection"] < 10:
    result["recommendations"].append("Connection reuse is low, check for connection leaks")

if metrics["performance"]["p99_acquisition_time_ms"] > 100:
    result["recommendations"].append("Connection acquisition slow, increase min_connections")
""",
    imports=["json", "datetime"],
    parameters={"pool": None}
)
```

## Best Practices

1. **Choose the Right Pattern**:
   - Use caching for repeated expensive operations
   - Use lazy loading for large datasets
   - Use streaming for unbounded data
   - Use async I/O for network operations
   - **NEW**: Use QueryRouterNode for automatic query optimization

2. **Memory Management**:
   - Set appropriate cache sizes
   - Use generators for large data
   - Implement proper cleanup
   - Monitor memory usage
   - **NEW**: Monitor prepared statement cache size

3. **Connection Management**:
   - Always use WorkflowConnectionPool for production
   - Set pool sizes based on concurrent load
   - Monitor health scores and auto-recycling
   - Use context managers for safe connection handling
   - Implement transaction patterns for data consistency
   - **NEW**: Enable adaptive sizing for dynamic workloads
   - **NEW**: Use query router for connection-free query execution

4. **Performance Monitoring**:
   - Track cache hit rates
   - Monitor processing times
   - Log resource usage
   - Set up performance alerts
   - **NEW**: Monitor router cache hit rates (target >80%)
   - **NEW**: Track pool size adjustments
   - **NEW**: Analyze learned query patterns

## See Also
- [Data Processing Patterns](03-data-processing-patterns.md) - Efficient data handling
- [Error Handling Patterns](05-error-handling-patterns.md) - Performance under failure
- [Best Practices](11-best-practices.md) - General optimization guidelines
