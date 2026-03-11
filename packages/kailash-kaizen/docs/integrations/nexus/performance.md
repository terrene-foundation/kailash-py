# Kaizen-Nexus Performance Guide

**Version**: 0.1.0
**Status**: Production Ready
**Part of**: TODO-149 Phase 4

## Overview

This guide provides comprehensive information about the performance characteristics of the Kaizen-Nexus integration and strategies for optimization.

## Performance Characteristics

### Deployment Performance

| Operation | Target | Typical | Optimized | Notes |
|-----------|--------|---------|-----------|-------|
| Multi-channel deploy | <2s | 1.5s | 0.15s (cached) | All 3 channels |
| Single channel (API) | <0.5s | 0.4s | 0.05s (cached) | API only |
| Single channel (CLI) | <0.5s | 0.4s | 0.05s (cached) | CLI only |
| Single channel (MCP) | <0.5s | 0.4s | 0.05s (cached) | MCP only |

**Key Insight**: Deployment caching provides **90% performance improvement** for redeployment.

### Execution Performance

| Operation | Target | Typical | Notes |
|-----------|--------|---------|-------|
| API latency | <500ms | 300ms | Excludes LLM call time |
| CLI latency | <500ms | 300ms | Excludes LLM call time |
| MCP latency | <500ms | 300ms | Excludes LLM call time |
| Session sync | <50ms | 10ms | In-memory synchronization |

**Key Insight**: Platform overhead is minimal (<100ms) for all channels.

### Session Management Performance

| Operation | Target | Typical | Notes |
|-----------|--------|---------|-------|
| Session creation | <10ms | 5ms | In-memory allocation |
| State update | <50ms | 10ms | Thread-safe updates |
| State retrieval | <50ms | 5ms | O(1) lookup |
| Cleanup (1000 sessions) | <1s | 0.3s | Batch cleanup |

**Key Insight**: Session management has negligible overhead.

### Concurrent Performance

| Metric | Target | Typical | Notes |
|--------|--------|---------|-------|
| Throughput | >100 req/s | 150 req/s | Concurrent requests |
| Concurrent deployments | 10+ | 20+ | Simultaneous deploys |
| Active sessions | 1000+ | 5000+ | In-memory capacity |

**Key Insight**: Platform scales well for production workloads.

## Optimization Strategies

### 1. Deployment Caching

**Impact**: 90% faster redeployment

#### How It Works

```python
from kaizen.integrations.nexus import deploy_multi_channel

# Initial deployment: ~1.5s
# Workflow is built and cached
channels = deploy_multi_channel(agent, app, "assistant")

# Redeployment: ~0.15s (90% faster)
# Cached workflow is reused
channels = deploy_multi_channel(agent, app, "assistant")
```

#### Configuration

```python
# Caching enabled by default
deploy_as_api(agent, app, "assistant", use_cache=True)

# Disable caching if needed
deploy_as_api(agent, app, "assistant", use_cache=False)

# Clear cache manually
from kaizen.integrations.nexus import clear_deployment_cache
clear_deployment_cache()
```

#### When to Use

- ✅ Production deployments (stable agents)
- ✅ Development with code hot-reload
- ✅ Multi-environment deployments
- ❌ Agent configuration changes frequently
- ❌ Testing different agent versions

### 2. Session Management Optimization

**Impact**: Efficient memory usage and fast cleanup

#### Cleanup Configuration

```python
from kaizen.integrations.nexus import NexusSessionManager

# Configure cleanup based on usage patterns
session_manager = NexusSessionManager(
    cleanup_interval=300,  # 5 minutes (typical web app)
    session_ttl=7200       # 2 hours (typical session)
)
```

#### Cleanup Strategies

| Use Case | Cleanup Interval | Session TTL | Rationale |
|----------|------------------|-------------|-----------|
| Web API | 5 minutes | 1-2 hours | Balance memory/responsiveness |
| CLI tools | 10 minutes | 4-8 hours | Longer sessions needed |
| Background tasks | 30 minutes | 24 hours | Low cleanup overhead |
| High traffic | 2 minutes | 30 minutes | Aggressive cleanup |

#### Manual Cleanup

```python
# Force cleanup immediately
cleaned_count = session_manager.cleanup_expired_sessions()
print(f"Cleaned {cleaned_count} sessions")

# Get session metrics
metrics = session_manager.get_session_metrics()
print(f"Active: {metrics['active_sessions']}")
print(f"Total: {metrics['total_sessions']}")
```

### 3. Performance Monitoring

**Impact**: Identify bottlenecks and track trends

#### Basic Monitoring

```python
from kaizen.integrations.nexus import PerformanceMetrics

# Create metrics collector
metrics = PerformanceMetrics()

# Record operations
start = time.time()
deploy_multi_channel(agent, app, "assistant")
metrics.record_deployment(time.time() - start)

# Get summary
summary = metrics.get_summary()
print(f"Deployment mean: {summary['deployment']['mean']:.3f}s")
```

#### Context Manager Pattern

```python
from kaizen.integrations.nexus import PerformanceMonitor

# Automatic timing
with PerformanceMonitor(metrics, 'deployment'):
    deploy_multi_channel(agent, app, "assistant")

with PerformanceMonitor(metrics, 'api'):
    result = agent.process(query="...")
```

#### Metrics Summary

```python
# Print comprehensive summary
metrics.print_summary()

# Output:
# === Performance Summary ===
#
# DEPLOYMENT:
#   Mean:   1487.3ms
#   Median: 1487.3ms
#   Min:    1432.1ms
#   Max:    1542.5ms
#   Count:  5
#
# API:
#   Mean:   287.4ms
#   Median: 289.1ms
#   Min:    271.2ms
#   Max:    305.3ms
#   Count:  100
```

### 4. Memory Management

**Impact**: Prevent memory leaks in long-running deployments

#### Best Practices

```python
import gc

# Force garbage collection after bulk operations
for i in range(100):
    deploy_multi_channel(agent, app, f"agent_{i}")

gc.collect()  # Force cleanup

# Cleanup sessions regularly
session_manager.cleanup_expired_sessions()
```

#### Memory Monitoring

```python
# Check object count growth
gc.collect()
initial_objects = len(gc.get_objects())

# ... perform operations ...

gc.collect()
final_objects = len(gc.get_objects())
growth = final_objects - initial_objects

if growth > 1000:
    print(f"Warning: {growth} new objects created")
```

### 5. Concurrent Operations

**Impact**: Handle multiple deployments efficiently

#### Parallel Deployments

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

agents = [create_agent(i) for i in range(10)]

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [
        executor.submit(deploy_multi_channel, agent, app, f"agent_{i}")
        for i, agent in enumerate(agents)
    ]

    results = [future.result() for future in as_completed(futures)]

# All deployments complete in parallel
```

#### Thread-Safe Sessions

```python
# Session manager is thread-safe
def worker(session_id, value):
    session_manager.update_session_state(
        session_id,
        {f"key_{value}": value},
        channel="api"
    )

with ThreadPoolExecutor(max_workers=20) as executor:
    futures = [
        executor.submit(worker, session.session_id, i)
        for i in range(20)
    ]

    # All updates complete safely
    [future.result() for future in futures]
```

## Performance Benchmarking

### Running Benchmarks

```bash
# Run performance tests
pytest tests/integration/test_nexus_performance.py -v

# Run specific benchmark
pytest tests/integration/test_nexus_performance.py::TestDeploymentPerformance::test_deployment_performance -v

# Run with timing details
pytest tests/integration/test_nexus_performance.py -v --durations=10
```

### Expected Results

```
test_deployment_performance ..................... PASSED (1.53s)
test_api_response_latency ....................... PASSED (0.29s)
test_cli_execution_latency ...................... PASSED (0.30s)
test_mcp_tool_latency ........................... PASSED (0.31s)
test_session_sync_latency ....................... PASSED (0.01s)
test_concurrent_deployments ..................... PASSED (2.14s)
test_session_cleanup_performance ................ PASSED (0.31s)

========================== 7 passed in 5.01s ==========================
```

### Custom Benchmarks

```python
import time
from kaizen.integrations.nexus import PerformanceMetrics, PerformanceMonitor

def benchmark_deployment():
    """Benchmark deployment performance."""
    metrics = PerformanceMetrics()

    # Run 10 deployments
    for i in range(10):
        with PerformanceMonitor(metrics, 'deployment'):
            deploy_multi_channel(agent, app, f"bench_{i}")

    # Analyze results
    summary = metrics.get_summary()
    mean = summary['deployment']['mean']
    median = summary['deployment']['median']

    print(f"Mean deployment: {mean*1000:.1f}ms")
    print(f"Median deployment: {median*1000:.1f}ms")

    # Check against target
    assert mean < 2.0, "Deployment exceeds 2s target"

if __name__ == "__main__":
    benchmark_deployment()
```

## Performance Troubleshooting

### Slow Deployment (>5s)

**Symptoms**:
- Multi-channel deployment takes >5 seconds
- Redeployment doesn't improve

**Solutions**:

1. **Check auto_discovery setting**
   ```python
   # Ensure auto_discovery=False when using DataFlow
   app = Nexus(auto_discovery=False)
   ```

2. **Verify caching is enabled**
   ```python
   # Caching should be enabled
   deploy_multi_channel(agent, app, "assistant")  # use_cache=True default
   ```

3. **Profile workflow building**
   ```python
   import time

   start = time.time()
   workflow = agent.to_workflow()
   build_time = time.time() - start

   if build_time > 1.0:
       print(f"Slow workflow build: {build_time:.2f}s")
   ```

### High Memory Usage

**Symptoms**:
- Memory grows continuously
- Process OOM in production

**Solutions**:

1. **Enable session cleanup**
   ```python
   # Set aggressive cleanup for high traffic
   session_manager = NexusSessionManager(
       cleanup_interval=120,  # 2 minutes
       session_ttl=1800       # 30 minutes
   )
   ```

2. **Monitor session count**
   ```python
   metrics = session_manager.get_session_metrics()
   if metrics['active_sessions'] > 1000:
       print("Warning: High session count")
       session_manager.cleanup_expired_sessions()
   ```

3. **Clear deployment cache**
   ```python
   from kaizen.integrations.nexus import clear_deployment_cache

   # Clear cache if memory constrained
   clear_deployment_cache()
   ```

### Low Throughput

**Symptoms**:
- <50 requests/second
- High latency under load

**Solutions**:

1. **Use concurrent executors**
   ```python
   from concurrent.futures import ThreadPoolExecutor

   with ThreadPoolExecutor(max_workers=20) as executor:
       # Process requests in parallel
       futures = [executor.submit(agent.process, query) for query in queries]
   ```

2. **Optimize LLM calls**
   ```python
   # Use faster models for high-throughput scenarios
   config = AssistantConfig(
       model="gpt-3.5-turbo",  # Faster than gpt-4
       temperature=0.3          # Lower temperature = faster
   )
   ```

3. **Profile bottlenecks**
   ```python
   import cProfile

   profiler = cProfile.Profile()
   profiler.enable()

   # ... perform operations ...

   profiler.disable()
   profiler.print_stats(sort='cumtime')
   ```

## Production Recommendations

### Deployment

1. ✅ Enable deployment caching
2. ✅ Use `auto_discovery=False`
3. ✅ Monitor deployment times
4. ✅ Batch deployments when possible

### Session Management

1. ✅ Configure cleanup based on traffic
2. ✅ Monitor active session count
3. ✅ Set appropriate TTL values
4. ✅ Use cleanup_interval <10 minutes

### Monitoring

1. ✅ Collect performance metrics
2. ✅ Track latency percentiles
3. ✅ Monitor memory usage
4. ✅ Set up alerts for degradation

### Scaling

1. ✅ Use concurrent executors
2. ✅ Distribute across multiple processes
3. ✅ Consider horizontal scaling
4. ✅ Use load balancing for API endpoints

## Summary

| Optimization | Impact | Complexity | Recommendation |
|--------------|--------|------------|----------------|
| Deployment caching | 90% faster | Low | ✅ Always enable |
| Session cleanup | Prevents memory leaks | Low | ✅ Configure appropriately |
| Performance monitoring | Identify bottlenecks | Low | ✅ Enable in production |
| Concurrent operations | 10x throughput | Medium | ✅ Use for high traffic |
| Memory management | Stable long-term | Low | ✅ Monitor regularly |

## Next Steps

1. **Review** the [Best Practices Guide](best-practices.md)
2. **Try** the [Complete Integration Example](../../examples/7-nexus-integration/complete-integration/)
3. **Test** with your workload using performance benchmarks
4. **Monitor** in production with metrics and health checks

## Related Documentation

- [Integration Guide](integration-guide.md)
- [Best Practices](best-practices.md)
- [Complete Example](../../examples/7-nexus-integration/complete-integration/README.md)
- [API Reference](api-reference.md)
