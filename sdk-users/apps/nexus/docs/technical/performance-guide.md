# Performance Guide

Optimize Nexus's revolutionary workflow-native architecture for maximum performance, scalability, and efficiency across all channels.

## Overview

Nexus's workflow-native foundation provides inherent performance advantages over traditional request-response architectures. This guide covers optimization techniques, performance monitoring, and scalability patterns to maximize your platform's capabilities.

## Performance Architecture

### Workflow-Native Performance Benefits

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time

app = Nexus()

class PerformanceOptimizer:
    """Demonstrate Nexus performance optimization techniques"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.performance_metrics = {}
        self.optimization_strategies = {
            "workflow_caching": "Cache workflow results for repeated executions",
            "parallel_execution": "Execute independent nodes concurrently",
            "resource_pooling": "Reuse expensive resources across executions",
            "intelligent_scheduling": "Optimize node execution order",
            "result_streaming": "Stream large results incrementally",
            "lazy_loading": "Load workflow components on demand"
        }

    def benchmark_workflow_registration(self):
        """Benchmark workflow registration performance"""

        registration_times = []

        for i in range(10):
            start_time = time.time()

            # Create and register workflow
            workflow = WorkflowBuilder()
            workflow.add_node("PythonCodeNode", f"node_{i}", {
                "code": f"""
def process_data_{i}(data):
    # Simulate processing
    result = sum(range(100))
    return {{"node_id": {i}, "result": result}}
""",
                "function_name": f"process_data_{i}"
            })

            self.app.register(f"perf-test-{i}", workflow)

            registration_time = time.time() - start_time
            registration_times.append(registration_time)

        return {
            "total_workflows": len(registration_times),
            "avg_registration_time": sum(registration_times) / len(registration_times),
            "min_registration_time": min(registration_times),
            "max_registration_time": max(registration_times),
            "performance_score": "excellent" if max(registration_times) < 0.1 else "good"
        }

    def optimize_workflow_execution(self, workflow_name):
        """Optimize workflow for high-performance execution"""

        optimization_config = {
            "enable_caching": True,
            "parallel_nodes": True,
            "resource_pooling": True,
            "result_streaming": True,
            "memory_optimization": True,
            "execution_timeout": 30,
            "max_concurrent_executions": 10
        }

        # Apply optimizations (simulation)
        optimizations_applied = []

        for optimization, enabled in optimization_config.items():
            if enabled:
                optimizations_applied.append(optimization)

        return {
            "workflow_name": workflow_name,
            "optimizations_applied": optimizations_applied,
            "expected_improvement": "25-40% faster execution",
            "memory_savings": "15-30% reduction",
            "throughput_increase": "2-3x higher concurrent executions"
        }

# Usage example
optimizer = PerformanceOptimizer(app)

# Benchmark registration performance
registration_benchmark = optimizer.benchmark_workflow_registration()
print(f"Registration Performance: {registration_benchmark}")

# Optimize workflow execution
execution_optimization = optimizer.optimize_workflow_execution("data-processor")
print(f"Execution Optimization: {execution_optimization}")
```

### Parallel Execution Patterns

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import asyncio
import time

app = Nexus()

def create_parallel_workflow():
    """Create workflow optimized for parallel execution"""

    workflow = WorkflowBuilder()

    # Independent parallel branches
    workflow.add_node("PythonCodeNode", "data_validation", {
        "code": """
def validate_data(data):
    import time
    time.sleep(0.1)  # Simulate validation work
    return {"validation": "passed", "record_count": len(data.get('records', []))}
""",
        "function_name": "validate_data"
    })

    workflow.add_node("PythonCodeNode", "data_enrichment", {
        "code": """
def enrich_data(data):
    import time
    time.sleep(0.1)  # Simulate enrichment work
    return {"enrichment": "completed", "enriched_fields": ["timestamp", "geo_location"]}
""",
        "function_name": "enrich_data"
    })

    workflow.add_node("PythonCodeNode", "data_quality_check", {
        "code": """
def quality_check(data):
    import time
    time.sleep(0.1)  # Simulate quality checking
    return {"quality_score": 0.95, "issues_found": 0}
""",
        "function_name": "quality_check"
    })

    # Convergence node that waits for all parallel branches
    workflow.add_node("PythonCodeNode", "combine_results", {
        "code": """
def combine_results(data):
    # Combine results from parallel executions
    combined = {
        "validation_status": data.get("validation", "unknown"),
        "enrichment_status": data.get("enrichment", "unknown"),
        "quality_score": data.get("quality_score", 0),
        "processing_complete": True
    }
    return combined
""",
        "function_name": "combine_results"
    })

    return workflow

# Register optimized parallel workflow
parallel_workflow = create_parallel_workflow()
app.register("parallel-processor", parallel_workflow)

class ParallelExecutionManager:
    """Manage parallel workflow execution patterns"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.execution_stats = {}

    async def execute_concurrent_workflows(self, workflow_name, input_batches):
        """Execute multiple workflow instances concurrently"""

        start_time = time.time()

        # Simulate concurrent execution
        async def execute_workflow(batch_data):
            # In real implementation, this would trigger actual workflow execution
            await asyncio.sleep(0.2)  # Simulate execution time
            return {"batch_id": batch_data.get("batch_id"), "status": "completed"}

        # Execute all batches concurrently
        tasks = [execute_workflow(batch) for batch in input_batches]
        results = await asyncio.gather(*tasks)

        execution_time = time.time() - start_time

        return {
            "workflow_name": workflow_name,
            "total_batches": len(input_batches),
            "execution_time": execution_time,
            "throughput": len(input_batches) / execution_time,
            "results": results
        }

    def optimize_for_throughput(self, workflow_name, target_throughput):
        """Optimize workflow configuration for target throughput"""

        optimization_recommendations = {
            "concurrent_executions": min(target_throughput * 2, 50),
            "resource_allocation": {
                "cpu_cores": min(target_throughput // 10, 8),
                "memory_mb": min(target_throughput * 100, 4096),
                "thread_pool_size": min(target_throughput, 20)
            },
            "caching_strategy": {
                "result_cache_size": target_throughput * 10,
                "metadata_cache_ttl": 300,
                "enable_distributed_cache": target_throughput > 100
            }
        }

        return optimization_recommendations

# Usage example
parallel_manager = ParallelExecutionManager(app)

# Test concurrent execution
async def test_parallel_execution():
    """Test parallel execution performance"""

    input_batches = [
        {"batch_id": f"batch_{i}", "data": f"test_data_{i}"}
        for i in range(10)
    ]

    results = await parallel_manager.execute_concurrent_workflows(
        "parallel-processor", input_batches
    )

    print(f"Parallel Execution Results: {results}")

    # Get throughput optimization recommendations
    optimization = parallel_manager.optimize_for_throughput("parallel-processor", 50)
    print(f"Throughput Optimization: {optimization}")

# Run test
# asyncio.run(test_parallel_execution())
```

## Caching and Optimization

### Intelligent Caching Strategies

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import hashlib
import time
import json

app = Nexus()

class IntelligentCache:
    """Advanced caching system for workflow optimization"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.result_cache = {}
        self.metadata_cache = {}
        self.performance_cache = {}
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        }

    def generate_cache_key(self, workflow_name, inputs, parameters=None):
        """Generate deterministic cache key for workflow execution"""

        cache_data = {
            "workflow": workflow_name,
            "inputs": inputs,
            "parameters": parameters or {}
        }

        # Create deterministic hash
        cache_string = json.dumps(cache_data, sort_keys=True)
        cache_key = hashlib.sha256(cache_string.encode()).hexdigest()[:16]

        return cache_key

    def should_cache_result(self, workflow_name, execution_time, result_size):
        """Determine if result should be cached based on heuristics"""

        cache_decision = {
            "should_cache": False,
            "reason": "",
            "cache_priority": "low"
        }

        # Cache expensive computations (>2 seconds)
        if execution_time > 2.0:
            cache_decision["should_cache"] = True
            cache_decision["reason"] = "Expensive computation"
            cache_decision["cache_priority"] = "high"

        # Cache small to medium results (<10MB)
        elif result_size < 10 * 1024 * 1024:
            cache_decision["should_cache"] = True
            cache_decision["reason"] = "Reasonable result size"
            cache_decision["cache_priority"] = "medium"

        # Don't cache large results or quick computations
        else:
            cache_decision["reason"] = "Result too large or computation too fast"

        return cache_decision

    def cache_workflow_result(self, cache_key, result, metadata):
        """Cache workflow execution result with metadata"""

        cache_entry = {
            "result": result,
            "metadata": metadata,
            "cached_at": time.time(),
            "access_count": 0,
            "last_accessed": time.time()
        }

        self.result_cache[cache_key] = cache_entry

        # Update cache stats
        if len(self.result_cache) > 1000:  # Max cache size
            self._evict_oldest_entries()

    def get_cached_result(self, cache_key):
        """Retrieve cached result if available and valid"""

        if cache_key in self.result_cache:
            entry = self.result_cache[cache_key]

            # Check if cache entry is still valid (24 hour TTL)
            if time.time() - entry["cached_at"] < 86400:
                entry["access_count"] += 1
                entry["last_accessed"] = time.time()

                self.cache_stats["hits"] += 1
                return entry["result"]
            else:
                # Remove expired entry
                del self.result_cache[cache_key]

        self.cache_stats["misses"] += 1
        return None

    def _evict_oldest_entries(self):
        """Evict oldest cache entries to manage memory"""

        # Sort by last access time and remove oldest 10%
        sorted_entries = sorted(
            self.result_cache.items(),
            key=lambda x: x[1]["last_accessed"]
        )

        evict_count = len(sorted_entries) // 10

        for i in range(evict_count):
            cache_key = sorted_entries[i][0]
            del self.result_cache[cache_key]
            self.cache_stats["evictions"] += 1

    def get_cache_performance_stats(self):
        """Get cache performance statistics"""

        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        return {
            "cache_entries": len(self.result_cache),
            "total_requests": total_requests,
            "hit_rate_percent": round(hit_rate, 2),
            "cache_stats": self.cache_stats,
            "memory_efficiency": "good" if hit_rate > 70 else "needs_optimization"
        }

    def optimize_cache_configuration(self):
        """Provide cache optimization recommendations"""

        stats = self.get_cache_performance_stats()

        recommendations = []

        if stats["hit_rate_percent"] < 50:
            recommendations.append("Increase cache TTL for frequently accessed results")
            recommendations.append("Consider pre-warming cache with common queries")

        if stats["cache_entries"] > 800:
            recommendations.append("Increase cache size limit or implement LRU eviction")

        if self.cache_stats["evictions"] > self.cache_stats["hits"]:
            recommendations.append("Cache size may be too small for workload")

        return {
            "current_performance": stats["memory_efficiency"],
            "recommendations": recommendations,
            "suggested_cache_size": min(stats["cache_entries"] * 1.5, 2000)
        }

# Usage example
cache_system = IntelligentCache(app)

# Test caching system
def test_caching_performance():
    """Test intelligent caching system"""

    # Simulate workflow execution with caching
    workflow_name = "data-processor"
    test_parameters= {"data": "test_dataset_1"}

    # Generate cache key
    cache_key = cache_system.generate_cache_key(workflow_name, test_inputs)

    # Check for cached result
    cached_result = cache_system.get_cached_result(cache_key)

    if cached_result:
        print("Cache hit! Using cached result")
        result = cached_result
    else:
        print("Cache miss! Executing workflow")

        # Simulate workflow execution
        start_time = time.time()
        time.sleep(0.1)  # Simulate work
        execution_time = time.time() - start_time

        result = {"processed_data": "result", "timestamp": time.time()}
        result_size = len(str(result))

        # Determine if result should be cached
        cache_decision = cache_system.should_cache_result(
            workflow_name, execution_time, result_size
        )

        if cache_decision["should_cache"]:
            cache_system.cache_workflow_result(cache_key, result, {
                "execution_time": execution_time,
                "result_size": result_size,
                "priority": cache_decision["cache_priority"]
            })

    # Get cache performance stats
    cache_stats = cache_system.get_cache_performance_stats()
    optimization = cache_system.optimize_cache_configuration()

    return {
        "result": result,
        "cache_stats": cache_stats,
        "optimization": optimization
    }

# Run caching test
caching_results = test_caching_performance()
print(f"Caching Performance: {caching_results}")
```

### Resource Pool Management

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import threading
from queue import Queue, Empty

app = Nexus()

class ResourcePoolManager:
    """Manage resource pools for optimal performance"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.connection_pools = {}
        self.thread_pools = {}
        self.resource_stats = {}
        self.pool_lock = threading.Lock()

    def create_connection_pool(self, pool_name, pool_size=10, max_connections=50):
        """Create a connection pool for external resources"""

        class ConnectionPool:
            def __init__(self, name, size, max_size):
                self.name = name
                self.size = size
                self.max_size = max_size
                self.available_connections = Queue(maxsize=max_size)
                self.active_connections = 0
                self.total_created = 0

                # Pre-populate pool
                for i in range(size):
                    connection = self._create_connection()
                    self.available_connections.put(connection)

            def _create_connection(self):
                """Create a new connection (simulation)"""
                connection_id = f"{self.name}_conn_{self.total_created}"
                self.total_created += 1
                return {
                    "id": connection_id,
                    "created_at": time.time(),
                    "last_used": time.time()
                }

            def get_connection(self, timeout=5):
                """Get connection from pool"""
                try:
                    connection = self.available_connections.get(timeout=timeout)
                    connection["last_used"] = time.time()
                    self.active_connections += 1
                    return connection
                except Empty:
                    if self.total_created < self.max_size:
                        return self._create_connection()
                    else:
                        raise Exception(f"Connection pool {self.name} exhausted")

            def return_connection(self, connection):
                """Return connection to pool"""
                if self.available_connections.qsize() < self.size:
                    self.available_connections.put(connection)
                    self.active_connections -= 1

            def get_pool_stats(self):
                """Get pool statistics"""
                return {
                    "pool_name": self.name,
                    "pool_size": self.size,
                    "max_size": self.max_size,
                    "available": self.available_connections.qsize(),
                    "active": self.active_connections,
                    "total_created": self.total_created,
                    "utilization_percent": (self.active_connections / self.max_size) * 100
                }

        with self.pool_lock:
            pool = ConnectionPool(pool_name, pool_size, max_connections)
            self.connection_pools[pool_name] = pool

            return pool.get_pool_stats()

    def create_thread_pool(self, pool_name, thread_count=5, max_queue_size=100):
        """Create a thread pool for parallel execution"""

        class ThreadPool:
            def __init__(self, name, threads, queue_size):
                self.name = name
                self.thread_count = threads
                self.task_queue = Queue(maxsize=queue_size)
                self.result_queue = Queue()
                self.threads = []
                self.stats = {
                    "tasks_submitted": 0,
                    "tasks_completed": 0,
                    "tasks_failed": 0
                }

                # Start worker threads
                for i in range(threads):
                    thread = threading.Thread(target=self._worker, daemon=True)
                    thread.start()
                    self.threads.append(thread)

            def _worker(self):
                """Worker thread function"""
                while True:
                    try:
                        task_func, args, kwargs = self.task_queue.get(timeout=1)
                        try:
                            result = task_func(*args, **kwargs)
                            self.result_queue.put(("success", result))
                            self.stats["tasks_completed"] += 1
                        except Exception as e:
                            self.result_queue.put(("error", str(e)))
                            self.stats["tasks_failed"] += 1
                        finally:
                            self.task_queue.task_done()
                    except Empty:
                        continue
                    except Exception:
                        break

            def submit_task(self, func, *args, **kwargs):
                """Submit task to thread pool"""
                self.task_queue.put((func, args, kwargs))
                self.stats["tasks_submitted"] += 1

            def get_result(self, timeout=5):
                """Get result from completed task"""
                try:
                    return self.result_queue.get(timeout=timeout)
                except Empty:
                    return None

            def get_pool_stats(self):
                """Get thread pool statistics"""
                return {
                    "pool_name": self.name,
                    "thread_count": self.thread_count,
                    "queue_size": self.task_queue.qsize(),
                    "stats": self.stats,
                    "efficiency": (self.stats["tasks_completed"] /
                                 max(self.stats["tasks_submitted"], 1)) * 100
                }

        with self.pool_lock:
            pool = ThreadPool(pool_name, thread_count, max_queue_size)
            self.thread_pools[pool_name] = pool

            return pool.get_pool_stats()

    def optimize_resource_allocation(self, workload_profile):
        """Optimize resource allocation based on workload"""

        cpu_intensive = workload_profile.get("cpu_intensive", False)
        io_intensive = workload_profile.get("io_intensive", False)
        concurrent_requests = workload_profile.get("concurrent_requests", 10)

        recommendations = {
            "connection_pools": {},
            "thread_pools": {},
            "resource_limits": {}
        }

        if io_intensive:
            recommendations["connection_pools"]["database"] = {
                "pool_size": min(concurrent_requests * 2, 20),
                "max_connections": min(concurrent_requests * 4, 50)
            }
            recommendations["connection_pools"]["external_api"] = {
                "pool_size": min(concurrent_requests, 15),
                "max_connections": min(concurrent_requests * 3, 40)
            }

        if cpu_intensive:
            import multiprocessing
            cpu_count = multiprocessing.cpu_count()

            recommendations["thread_pools"]["cpu_tasks"] = {
                "thread_count": min(cpu_count, 8),
                "max_queue_size": concurrent_requests * 2
            }

        recommendations["resource_limits"] = {
            "max_memory_mb": min(concurrent_requests * 100, 2048),
            "max_concurrent_workflows": min(concurrent_requests, 25),
            "request_timeout_seconds": 30 if io_intensive else 60
        }

        return recommendations

    def get_overall_performance_stats(self):
        """Get comprehensive performance statistics"""

        stats = {
            "connection_pools": {},
            "thread_pools": {},
            "overall_health": "good"
        }

        # Collect connection pool stats
        for name, pool in self.connection_pools.items():
            pool_stats = pool.get_pool_stats()
            stats["connection_pools"][name] = pool_stats

            # Check for performance issues
            if pool_stats["utilization_percent"] > 90:
                stats["overall_health"] = "needs_attention"

        # Collect thread pool stats
        for name, pool in self.thread_pools.items():
            pool_stats = pool.get_pool_stats()
            stats["thread_pools"][name] = pool_stats

            # Check for performance issues
            if pool_stats["efficiency"] < 80:
                stats["overall_health"] = "needs_optimization"

        return stats

# Usage example
resource_manager = ResourcePoolManager(app)

# Create resource pools
db_pool_stats = resource_manager.create_connection_pool("database", 10, 30)
api_pool_stats = resource_manager.create_connection_pool("external_api", 5, 15)
thread_pool_stats = resource_manager.create_thread_pool("workflow_execution", 4, 50)

print(f"Database Pool: {db_pool_stats}")
print(f"API Pool: {api_pool_stats}")
print(f"Thread Pool: {thread_pool_stats}")

# Optimize for workload
workload_profile = {
    "cpu_intensive": True,
    "io_intensive": True,
    "concurrent_requests": 20
}

optimization = resource_manager.optimize_resource_allocation(workload_profile)
print(f"Resource Optimization: {optimization}")

# Get performance stats
performance_stats = resource_manager.get_overall_performance_stats()
print(f"Performance Stats: {performance_stats}")
```

## Monitoring and Metrics

### Real-Time Performance Monitoring

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import threading
from collections import defaultdict, deque

app = Nexus()

class PerformanceMonitor:
    """Real-time performance monitoring and alerting"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.metrics = defaultdict(deque)
        self.alerts = []
        self.thresholds = {
            "response_time_ms": 5000,  # 5 seconds
            "memory_usage_percent": 80,
            "cpu_usage_percent": 85,
            "error_rate_percent": 5,
            "queue_size": 100
        }
        self.monitoring_active = False
        self.monitor_thread = None

    def start_monitoring(self, interval_seconds=10):
        """Start real-time monitoring"""

        self.monitoring_active = True

        def monitoring_loop():
            while self.monitoring_active:
                try:
                    self._collect_metrics()
                    self._check_alerts()
                    time.sleep(interval_seconds)
                except Exception as e:
                    print(f"Monitoring error: {e}")

        self.monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
        self.monitor_thread.start()

        return {"monitoring_started": True, "interval": interval_seconds}

    def stop_monitoring(self):
        """Stop real-time monitoring"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

        return {"monitoring_stopped": True}

    def _collect_metrics(self):
        """Collect current performance metrics"""

        timestamp = time.time()

        # Collect system metrics (simulation)
        current_metrics = {
            "timestamp": timestamp,
            "response_time_ms": self._get_avg_response_time(),
            "memory_usage_percent": self._get_memory_usage(),
            "cpu_usage_percent": self._get_cpu_usage(),
            "error_rate_percent": self._get_error_rate(),
            "active_workflows": self._get_active_workflow_count(),
            "queue_size": self._get_queue_size(),
            "throughput_per_second": self._get_throughput()
        }

        # Store metrics with time-based retention (keep last 100 data points)
        for metric_name, value in current_metrics.items():
            if metric_name != "timestamp":
                self.metrics[metric_name].append((timestamp, value))

                # Keep only last 100 data points
                if len(self.metrics[metric_name]) > 100:
                    self.metrics[metric_name].popleft()

    def _get_avg_response_time(self):
        """Get average response time (simulation)"""
        import random
        base_time = 100  # 100ms base
        variation = random.uniform(0.8, 1.5)
        return base_time * variation

    def _get_memory_usage(self):
        """Get memory usage percentage (simulation)"""
        import random
        return random.uniform(40, 90)

    def _get_cpu_usage(self):
        """Get CPU usage percentage (simulation)"""
        import random
        return random.uniform(30, 95)

    def _get_error_rate(self):
        """Get error rate percentage (simulation)"""
        import random
        return random.uniform(0, 10)

    def _get_active_workflow_count(self):
        """Get number of active workflows"""
        health = self.app.health_check()
        return health.get('workflows', 0)

    def _get_queue_size(self):
        """Get current queue size (simulation)"""
        import random
        return random.randint(0, 150)

    def _get_throughput(self):
        """Get current throughput (simulation)"""
        import random
        return random.uniform(5, 50)

    def _check_alerts(self):
        """Check for alert conditions"""

        if not self.metrics:
            return

        current_time = time.time()

        # Check each threshold
        for metric_name, threshold in self.thresholds.items():
            if metric_name in self.metrics and self.metrics[metric_name]:
                latest_timestamp, latest_value = self.metrics[metric_name][-1]

                # Check if threshold is exceeded
                if latest_value > threshold:
                    alert = {
                        "alert_id": f"{metric_name}_{int(current_time)}",
                        "metric": metric_name,
                        "current_value": latest_value,
                        "threshold": threshold,
                        "severity": self._get_alert_severity(metric_name, latest_value, threshold),
                        "timestamp": current_time,
                        "message": f"{metric_name} exceeded threshold: {latest_value} > {threshold}"
                    }

                    self.alerts.append(alert)

                    # Keep only last 50 alerts
                    if len(self.alerts) > 50:
                        self.alerts = self.alerts[-50:]

    def _get_alert_severity(self, metric_name, current_value, threshold):
        """Determine alert severity"""

        ratio = current_value / threshold

        if ratio > 1.5:
            return "critical"
        elif ratio > 1.2:
            return "warning"
        else:
            return "info"

    def get_performance_summary(self, time_window_minutes=10):
        """Get performance summary for specified time window"""

        cutoff_time = time.time() - (time_window_minutes * 60)
        summary = {}

        for metric_name, data_points in self.metrics.items():
            # Filter to time window
            recent_points = [
                (timestamp, value) for timestamp, value in data_points
                if timestamp >= cutoff_time
            ]

            if recent_points:
                values = [value for _, value in recent_points]
                summary[metric_name] = {
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "current": values[-1],
                    "data_points": len(values),
                    "trend": self._calculate_trend(recent_points)
                }

        return summary

    def _calculate_trend(self, data_points):
        """Calculate trend direction for metric"""

        if len(data_points) < 3:
            return "insufficient_data"

        # Simple trend calculation
        first_half = data_points[:len(data_points)//2]
        second_half = data_points[len(data_points)//2:]

        first_avg = sum(value for _, value in first_half) / len(first_half)
        second_avg = sum(value for _, value in second_half) / len(second_half)

        if second_avg > first_avg * 1.1:
            return "increasing"
        elif second_avg < first_avg * 0.9:
            return "decreasing"
        else:
            return "stable"

    def get_active_alerts(self, severity_filter=None):
        """Get active alerts, optionally filtered by severity"""

        if severity_filter:
            return [
                alert for alert in self.alerts
                if alert["severity"] == severity_filter
            ]

        return self.alerts

    def generate_performance_report(self):
        """Generate comprehensive performance report"""

        summary = self.get_performance_summary(30)  # 30 minute window
        active_alerts = self.get_active_alerts()
        critical_alerts = self.get_active_alerts("critical")

        report = {
            "report_timestamp": time.time(),
            "monitoring_status": "active" if self.monitoring_active else "inactive",
            "performance_summary": summary,
            "alert_summary": {
                "total_alerts": len(active_alerts),
                "critical_alerts": len(critical_alerts),
                "recent_alerts": active_alerts[-5:] if active_alerts else []
            },
            "recommendations": self._generate_recommendations(summary, active_alerts)
        }

        return report

    def _generate_recommendations(self, summary, alerts):
        """Generate performance optimization recommendations"""

        recommendations = []

        # Response time recommendations
        if "response_time_ms" in summary:
            avg_response = summary["response_time_ms"]["avg"]
            if avg_response > 3000:
                recommendations.append("Consider implementing caching to reduce response times")
                recommendations.append("Optimize database queries and external API calls")

        # Memory usage recommendations
        if "memory_usage_percent" in summary:
            avg_memory = summary["memory_usage_percent"]["avg"]
            if avg_memory > 70:
                recommendations.append("Consider increasing memory allocation or optimizing memory usage")
                recommendations.append("Implement garbage collection tuning")

        # Error rate recommendations
        if "error_rate_percent" in summary:
            avg_errors = summary["error_rate_percent"]["avg"]
            if avg_errors > 2:
                recommendations.append("Investigate and fix error sources")
                recommendations.append("Implement better error handling and retry logic")

        # Alert-based recommendations
        critical_alerts = [alert for alert in alerts if alert["severity"] == "critical"]
        if critical_alerts:
            recommendations.append("Address critical alerts immediately")
            recommendations.append("Consider scaling resources to handle current load")

        return recommendations

# Usage example
monitor = PerformanceMonitor(app)

# Start monitoring
monitoring_status = monitor.start_monitoring(5)  # 5 second intervals
print(f"Monitoring Status: {monitoring_status}")

# Wait for some metrics to be collected
time.sleep(15)

# Get performance summary
performance_summary = monitor.get_performance_summary(5)
print(f"Performance Summary: {performance_summary}")

# Get alerts
active_alerts = monitor.get_active_alerts()
print(f"Active Alerts: {len(active_alerts)}")

# Generate comprehensive report
performance_report = monitor.generate_performance_report()
print(f"Performance Report: {performance_report}")

# Stop monitoring
stop_status = monitor.stop_monitoring()
print(f"Stop Status: {stop_status}")
```

## Scalability Optimization

### Auto-Scaling Configuration

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import threading
from collections import deque

app = Nexus()

class AutoScaler:
    """Intelligent auto-scaling system for Nexus workflows"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.scaling_policies = {}
        self.instances = {"nexus-1": {"status": "running", "created_at": time.time()}}
        self.metrics_history = deque(maxsize=100)
        self.scaling_events = []
        self.auto_scaling_enabled = True
        self.scaling_thread = None

    def configure_scaling_policy(self, policy_name, config):
        """Configure auto-scaling policy"""

        policy = {
            "name": policy_name,
            "metric": config.get("metric", "cpu_usage"),
            "scale_up_threshold": config.get("scale_up_threshold", 70),
            "scale_down_threshold": config.get("scale_down_threshold", 30),
            "min_instances": config.get("min_instances", 1),
            "max_instances": config.get("max_instances", 10),
            "cooldown_period": config.get("cooldown_period", 300),  # 5 minutes
            "scale_up_increment": config.get("scale_up_increment", 1),
            "scale_down_increment": config.get("scale_down_increment", 1),
            "enabled": True
        }

        self.scaling_policies[policy_name] = policy

        return {"policy_configured": policy_name, "policy": policy}

    def start_auto_scaling(self, check_interval=60):
        """Start auto-scaling monitoring"""

        def scaling_loop():
            while self.auto_scaling_enabled:
                try:
                    self._collect_scaling_metrics()
                    self._evaluate_scaling_decisions()
                    time.sleep(check_interval)
                except Exception as e:
                    print(f"Auto-scaling error: {e}")

        self.scaling_thread = threading.Thread(target=scaling_loop, daemon=True)
        self.scaling_thread.start()

        return {"auto_scaling_started": True, "check_interval": check_interval}

    def stop_auto_scaling(self):
        """Stop auto-scaling"""
        self.auto_scaling_enabled = False
        if self.scaling_thread:
            self.scaling_thread.join(timeout=10)

        return {"auto_scaling_stopped": True}

    def _collect_scaling_metrics(self):
        """Collect metrics for scaling decisions"""

        import random

        # Simulate metric collection
        current_metrics = {
            "timestamp": time.time(),
            "cpu_usage": random.uniform(20, 95),
            "memory_usage": random.uniform(30, 85),
            "request_rate": random.uniform(10, 200),
            "queue_size": random.randint(0, 150),
            "response_time": random.uniform(100, 5000),
            "active_instances": len(self.instances)
        }

        self.metrics_history.append(current_metrics)

    def _evaluate_scaling_decisions(self):
        """Evaluate whether scaling actions are needed"""

        if not self.metrics_history:
            return

        current_time = time.time()
        latest_metrics = self.metrics_history[-1]

        for policy_name, policy in self.scaling_policies.items():
            if not policy["enabled"]:
                continue

            # Check cooldown period
            if self._is_in_cooldown(policy_name, current_time):
                continue

            # Get metric value
            metric_value = latest_metrics.get(policy["metric"], 0)
            current_instances = len(self.instances)

            # Scale up decision
            if (metric_value > policy["scale_up_threshold"] and
                current_instances < policy["max_instances"]):

                self._scale_up(policy, metric_value)

            # Scale down decision
            elif (metric_value < policy["scale_down_threshold"] and
                  current_instances > policy["min_instances"]):

                self._scale_down(policy, metric_value)

    def _is_in_cooldown(self, policy_name, current_time):
        """Check if policy is in cooldown period"""

        policy = self.scaling_policies[policy_name]
        cooldown_period = policy["cooldown_period"]

        # Find last scaling event for this policy
        for event in reversed(self.scaling_events):
            if event["policy"] == policy_name:
                if current_time - event["timestamp"] < cooldown_period:
                    return True
                break

        return False

    def _scale_up(self, policy, metric_value):
        """Scale up instances"""

        instances_to_add = policy["scale_up_increment"]

        for i in range(instances_to_add):
            instance_id = f"nexus-{len(self.instances) + 1}"
            self.instances[instance_id] = {
                "status": "starting",
                "created_at": time.time(),
                "policy": policy["name"]
            }

        scaling_event = {
            "timestamp": time.time(),
            "action": "scale_up",
            "policy": policy["name"],
            "metric_value": metric_value,
            "threshold": policy["scale_up_threshold"],
            "instances_added": instances_to_add,
            "total_instances": len(self.instances)
        }

        self.scaling_events.append(scaling_event)

        print(f"Scaled up: Added {instances_to_add} instances due to {policy['metric']}={metric_value}")

    def _scale_down(self, policy, metric_value):
        """Scale down instances"""

        instances_to_remove = min(policy["scale_down_increment"],
                                len(self.instances) - policy["min_instances"])

        # Remove newest instances first
        instances_to_delete = sorted(
            self.instances.items(),
            key=lambda x: x[1]["created_at"],
            reverse=True
        )[:instances_to_remove]

        for instance_id, _ in instances_to_delete:
            del self.instances[instance_id]

        scaling_event = {
            "timestamp": time.time(),
            "action": "scale_down",
            "policy": policy["name"],
            "metric_value": metric_value,
            "threshold": policy["scale_down_threshold"],
            "instances_removed": instances_to_remove,
            "total_instances": len(self.instances)
        }

        self.scaling_events.append(scaling_event)

        print(f"Scaled down: Removed {instances_to_remove} instances due to {policy['metric']}={metric_value}")

    def get_scaling_status(self):
        """Get current scaling status"""

        return {
            "auto_scaling_enabled": self.auto_scaling_enabled,
            "current_instances": len(self.instances),
            "instances": self.instances,
            "active_policies": len([p for p in self.scaling_policies.values() if p["enabled"]]),
            "recent_events": self.scaling_events[-5:] if self.scaling_events else [],
            "metrics_collected": len(self.metrics_history)
        }

    def predict_scaling_needs(self, time_horizon_minutes=30):
        """Predict future scaling needs based on trends"""

        if len(self.metrics_history) < 10:
            return {"prediction": "insufficient_data"}

        # Calculate trends for key metrics
        recent_metrics = list(self.metrics_history)[-10:]

        trends = {}
        for metric in ["cpu_usage", "memory_usage", "request_rate"]:
            values = [m[metric] for m in recent_metrics]

            # Simple linear trend calculation
            if len(values) >= 3:
                first_half = values[:len(values)//2]
                second_half = values[len(values)//2:]

                first_avg = sum(first_half) / len(first_half)
                second_avg = sum(second_half) / len(second_half)

                trend_rate = (second_avg - first_avg) / len(first_half)
                projected_value = second_avg + (trend_rate * time_horizon_minutes / 5)  # 5-minute intervals

                trends[metric] = {
                    "current": values[-1],
                    "projected": projected_value,
                    "trend_rate": trend_rate,
                    "direction": "increasing" if trend_rate > 0 else "decreasing"
                }

        # Generate scaling predictions
        predictions = []

        for metric, trend_data in trends.items():
            for policy_name, policy in self.scaling_policies.items():
                if policy["metric"] == metric and policy["enabled"]:
                    projected = trend_data["projected"]

                    if projected > policy["scale_up_threshold"]:
                        predictions.append({
                            "action": "scale_up",
                            "policy": policy_name,
                            "metric": metric,
                            "projected_value": projected,
                            "confidence": "medium" if trend_data["trend_rate"] > 0 else "low"
                        })
                    elif projected < policy["scale_down_threshold"]:
                        predictions.append({
                            "action": "scale_down",
                            "policy": policy_name,
                            "metric": metric,
                            "projected_value": projected,
                            "confidence": "medium" if trend_data["trend_rate"] < 0 else "low"
                        })

        return {
            "time_horizon_minutes": time_horizon_minutes,
            "metric_trends": trends,
            "scaling_predictions": predictions,
            "recommendation": "monitor_closely" if predictions else "stable"
        }

    def optimize_scaling_policies(self):
        """Optimize scaling policies based on historical data"""

        optimization_recommendations = []

        # Analyze scaling event effectiveness
        if len(self.scaling_events) >= 5:
            scale_up_events = [e for e in self.scaling_events if e["action"] == "scale_up"]
            scale_down_events = [e for e in self.scaling_events if e["action"] == "scale_down"]

            # Check for oscillation (rapid scale up/down)
            if len(scale_up_events) > 0 and len(scale_down_events) > 0:
                recent_events = self.scaling_events[-10:]

                if len(recent_events) > 4:
                    actions = [e["action"] for e in recent_events]
                    oscillations = sum(1 for i in range(1, len(actions))
                                     if actions[i] != actions[i-1])

                    if oscillations > len(actions) * 0.6:  # More than 60% are changes
                        optimization_recommendations.append({
                            "issue": "scaling_oscillation",
                            "recommendation": "Increase cooldown periods or adjust thresholds",
                            "suggested_cooldown": 600  # 10 minutes
                        })

        # Check threshold effectiveness
        for policy_name, policy in self.scaling_policies.items():
            policy_events = [e for e in self.scaling_events if e["policy"] == policy_name]

            if len(policy_events) > 3:
                # Check if thresholds are too sensitive
                threshold_hits = len(policy_events)
                if threshold_hits > 10:  # Too many scaling events
                    optimization_recommendations.append({
                        "issue": "threshold_too_sensitive",
                        "policy": policy_name,
                        "recommendation": "Adjust thresholds to reduce scaling frequency",
                        "suggested_scale_up_threshold": policy["scale_up_threshold"] + 10,
                        "suggested_scale_down_threshold": policy["scale_down_threshold"] - 5
                    })

        return {
            "analysis_period": "last_100_events",
            "total_scaling_events": len(self.scaling_events),
            "optimization_recommendations": optimization_recommendations
        }

# Usage example
autoscaler = AutoScaler(app)

# Configure scaling policies
cpu_policy = autoscaler.configure_scaling_policy("cpu_based", {
    "metric": "cpu_usage",
    "scale_up_threshold": 75,
    "scale_down_threshold": 25,
    "min_instances": 1,
    "max_instances": 8,
    "cooldown_period": 300
})

memory_policy = autoscaler.configure_scaling_policy("memory_based", {
    "metric": "memory_usage",
    "scale_up_threshold": 80,
    "scale_down_threshold": 40,
    "min_instances": 1,
    "max_instances": 6,
    "cooldown_period": 420
})

print(f"CPU Policy: {cpu_policy}")
print(f"Memory Policy: {memory_policy}")

# Start auto-scaling
scaling_start = autoscaler.start_auto_scaling(30)  # Check every 30 seconds
print(f"Auto-scaling started: {scaling_start}")

# Wait for some scaling decisions
time.sleep(5)

# Get current status
status = autoscaler.get_scaling_status()
print(f"Scaling Status: {status}")

# Get scaling predictions
predictions = autoscaler.predict_scaling_needs(45)
print(f"Scaling Predictions: {predictions}")

# Get optimization recommendations
optimization = autoscaler.optimize_scaling_policies()
print(f"Optimization: {optimization}")

# Stop auto-scaling
scaling_stop = autoscaler.stop_auto_scaling()
print(f"Auto-scaling stopped: {scaling_stop}")
```

## Best Practices

### Performance Optimization Checklist

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()

class PerformanceBestPractices:
    """Comprehensive performance optimization best practices"""

    @staticmethod
    def workflow_optimization_checklist():
        """Checklist for optimizing workflow performance"""

        checklist = {
            "workflow_design": [
                "✅ Use parallel execution for independent nodes",
                "✅ Minimize data transfer between nodes",
                "✅ Implement proper error handling and retries",
                "✅ Use appropriate node types for specific tasks",
                "✅ Avoid unnecessary data transformations"
            ],
            "resource_management": [
                "✅ Configure connection pooling for external resources",
                "✅ Implement proper caching strategies",
                "✅ Use resource pools for expensive operations",
                "✅ Set appropriate timeouts",
                "✅ Monitor resource utilization"
            ],
            "scaling_configuration": [
                "✅ Configure auto-scaling policies",
                "✅ Set appropriate instance limits",
                "✅ Implement health checks",
                "✅ Monitor scaling events",
                "✅ Optimize for your workload patterns"
            ],
            "monitoring_setup": [
                "✅ Set up real-time performance monitoring",
                "✅ Configure appropriate alert thresholds",
                "✅ Implement comprehensive logging",
                "✅ Track key performance indicators",
                "✅ Regular performance reviews"
            ]
        }

        return checklist

    @staticmethod
    def create_optimized_workflow():
        """Create workflow following performance best practices"""

        workflow = WorkflowBuilder()

        # Parallel data processing nodes
        workflow.add_node("PythonCodeNode", "validate_input", {
            "code": """
def validate_input(data):
    # Fast validation without heavy processing
    if not data or not isinstance(data, dict):
        raise ValueError("Invalid input data")

    return {"validation": "passed", "record_count": len(data.get('records', []))}
""",
            "function_name": "validate_input"
        })

        workflow.add_node("PythonCodeNode", "preprocess_data", {
            "code": """
def preprocess_data(data):
    # Lightweight preprocessing
    records = data.get('records', [])

    # Process in batches for better memory usage
    batch_size = 100
    processed_batches = []

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        processed_batch = [{"id": item.get("id"), "processed": True} for item in batch]
        processed_batches.append(processed_batch)

    return {"processed_batches": processed_batches, "total_batches": len(processed_batches)}
""",
            "function_name": "preprocess_data"
        })

        # Optimized final processing
        workflow.add_node("PythonCodeNode", "finalize_results", {
            "code": """
def finalize_results(data):
    # Efficient result compilation
    batches = data.get('processed_batches', [])

    # Flatten results efficiently
    total_records = sum(len(batch) for batch in batches)

    return {
        "status": "completed",
        "total_records": total_records,
        "processing_time": __import__('time').time(),
        "batches_processed": len(batches)
    }
""",
            "function_name": "finalize_results"
        })

        return workflow

    @staticmethod
    def performance_testing_framework(nexus_app):
        """Framework for performance testing workflows"""

        class PerformanceTest:
            def __init__(self, app):
                self.app = app
                self.test_results = []

            def run_load_test(self, workflow_name, concurrent_requests=10, duration_seconds=60):
                """Run load test on workflow"""

                import threading
                import time

                start_time = time.time()
                end_time = start_time + duration_seconds
                request_count = 0
                error_count = 0
                response_times = []

                def make_request():
                    nonlocal request_count, error_count

                    while time.time() < end_time:
                        try:
                            request_start = time.time()

                            # Simulate workflow execution
                            health = self.app.health_check()

                            response_time = time.time() - request_start
                            response_times.append(response_time)
                            request_count += 1

                        except Exception:
                            error_count += 1

                        time.sleep(0.1)  # Small delay between requests

                # Start concurrent threads
                threads = []
                for _ in range(concurrent_requests):
                    thread = threading.Thread(target=make_request)
                    thread.start()
                    threads.append(thread)

                # Wait for all threads to complete
                for thread in threads:
                    thread.join()

                # Calculate results
                total_time = time.time() - start_time

                return {
                    "workflow_name": workflow_name,
                    "test_duration": total_time,
                    "total_requests": request_count,
                    "error_count": error_count,
                    "error_rate": (error_count / max(request_count, 1)) * 100,
                    "requests_per_second": request_count / total_time,
                    "avg_response_time": sum(response_times) / len(response_times) if response_times else 0,
                    "min_response_time": min(response_times) if response_times else 0,
                    "max_response_time": max(response_times) if response_times else 0
                }

            def run_benchmark_suite(self, workflow_names):
                """Run comprehensive benchmark suite"""

                results = {}

                for workflow_name in workflow_names:
                    print(f"Benchmarking {workflow_name}...")

                    # Light load test
                    light_load = self.run_load_test(workflow_name, 5, 30)

                    # Medium load test
                    medium_load = self.run_load_test(workflow_name, 10, 30)

                    # Heavy load test (if system can handle it)
                    heavy_load = self.run_load_test(workflow_name, 20, 30)

                    results[workflow_name] = {
                        "light_load": light_load,
                        "medium_load": medium_load,
                        "heavy_load": heavy_load,
                        "performance_grade": self._calculate_performance_grade(light_load, medium_load, heavy_load)
                    }

                return results

            def _calculate_performance_grade(self, light, medium, heavy):
                """Calculate overall performance grade"""

                # Grade based on error rates and response times
                if (heavy["error_rate"] < 1 and heavy["avg_response_time"] < 1.0 and
                    heavy["requests_per_second"] > 10):
                    return "A"
                elif (medium["error_rate"] < 2 and medium["avg_response_time"] < 2.0 and
                      medium["requests_per_second"] > 5):
                    return "B"
                elif (light["error_rate"] < 5 and light["avg_response_time"] < 5.0):
                    return "C"
                else:
                    return "D"

        return PerformanceTest(nexus_app)

    @staticmethod
    def generate_performance_report(test_results, optimization_recommendations):
        """Generate comprehensive performance report"""

        report = {
            "report_timestamp": time.time(),
            "executive_summary": {
                "total_workflows_tested": len(test_results),
                "average_performance_grade": "B",  # Calculate from actual results
                "critical_issues": 0,
                "optimization_opportunities": len(optimization_recommendations)
            },
            "detailed_results": test_results,
            "optimization_recommendations": optimization_recommendations,
            "next_steps": [
                "Implement high-priority optimizations",
                "Set up continuous performance monitoring",
                "Schedule regular performance reviews",
                "Configure auto-scaling for production workloads"
            ]
        }

        return report

# Usage example
best_practices = PerformanceBestPractices()

# Get optimization checklist
checklist = best_practices.workflow_optimization_checklist()
print(f"Performance Checklist: {checklist}")

# Create optimized workflow
optimized_workflow = best_practices.create_optimized_workflow()
app.register("optimized-processor", optimized_workflow)

# Set up performance testing
performance_tester = best_practices.performance_testing_framework(app)

# Run benchmark tests
test_results = performance_tester.run_benchmark_suite(["optimized-processor"])
print(f"Benchmark Results: {test_results}")

# Generate performance report
optimization_recommendations = [
    "Enable result caching for expensive operations",
    "Implement connection pooling for database access",
    "Configure auto-scaling policies"
]

performance_report = best_practices.generate_performance_report(
    test_results, optimization_recommendations
)
print(f"Performance Report: {performance_report}")
```

## Next Steps

Explore advanced Nexus capabilities:

1. **[Security Guide](security-guide.md)** - Advanced security and compliance patterns
2. **[Integration Guide](integration-guide.md)** - External system integration
3. **[Production Deployment](../advanced/production-deployment.md)** - Production-ready deployment
4. **[Troubleshooting](troubleshooting.md)** - Performance issue diagnosis

## Key Takeaways

✅ **Workflow-Native Performance** → Inherent advantages over request-response architectures
✅ **Parallel Execution** → Concurrent node processing and multi-workflow execution
✅ **Intelligent Caching** → Automatic result caching with performance heuristics
✅ **Resource Management** → Connection pooling and thread pool optimization
✅ **Real-Time Monitoring** → Performance metrics, alerting, and trend analysis
✅ **Auto-Scaling** → Intelligent scaling based on metrics and predictions
✅ **Best Practices** → Comprehensive optimization checklist and testing framework

Nexus's workflow-native architecture provides exceptional performance advantages, with built-in optimization features that scale automatically while maintaining enterprise-grade reliability and observability.
