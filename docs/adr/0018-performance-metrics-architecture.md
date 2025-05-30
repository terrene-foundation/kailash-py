# ADR-0018: Performance Metrics Architecture

## Status
Accepted

## Context
The SDK needed a way to collect and visualize actual performance metrics from workflow execution. Previously, visualization examples used synthetic data, which didn't provide real insights into workflow performance. Users need to understand:
- How long each node takes to execute
- Resource consumption (CPU, memory, I/O)
- Performance bottlenecks in their workflows
- Comparison between different runs

## Decision
We implemented a comprehensive performance metrics system with the following components:

1. **MetricsCollector** (`src/kailash/tracking/metrics_collector.py`)
   - Collects real-time performance data during node execution
   - Uses context managers for easy integration
   - Gracefully degrades when psutil is not available

2. **PerformanceVisualizer** (`src/kailash/visualization/performance.py`)
   - Creates various visualization types from collected metrics
   - Supports timeline charts, resource usage, heatmaps, and comparisons
   - Generates markdown reports with insights

3. **Runtime Integration**
   - LocalRuntime and ParallelRuntime automatically collect metrics
   - Metrics are stored in TaskMetrics for persistence
   - No changes required to existing workflows

## Architecture

### Data Collection Flow
```
Node Execution
    ↓
MetricsCollector (context manager)
    ↓
PerformanceMetrics (dataclass)
    ↓
TaskMetrics (storage)
    ↓
TaskManager (persistence)
```

### Visualization Flow
```
TaskManager
    ↓
PerformanceVisualizer
    ↓
Multiple Chart Types:
- Execution Timeline (Gantt)
- Resource Usage (Line charts)
- Performance Comparison (Radar)
- I/O Analysis (Bar charts)
- Performance Heatmap
- Markdown Reports
```

## Implementation Details

### PerformanceMetrics Dataclass
```python
@dataclass
class PerformanceMetrics:
    duration: float = 0.0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_delta_mb: float = 0.0
    io_read_bytes: int = 0
    io_write_bytes: int = 0
    # ... additional fields
```

### Integration Example
```python
# Automatic collection in runtime
collector = MetricsCollector()
with collector.collect(node_id=node_id) as metrics_context:
    outputs = node_instance.execute(**inputs)
performance_metrics = metrics_context.result()
```

### Visualization Example
```python
# Generate performance visualizations
perf_viz = PerformanceVisualizer(task_manager)
outputs = perf_viz.create_run_performance_summary(run_id, output_dir)
```

## Consequences

### Positive
- Real performance insights without code changes
- Multiple visualization types for different use cases
- Graceful degradation when dependencies are missing
- Easy integration with existing workflows
- Supports performance optimization workflows

### Negative
- Additional dependency on psutil (optional)
- Slight overhead for metrics collection (~1-2%)
- Increased storage for metrics data

### Neutral
- Metrics collection is automatic but can be disabled
- Visualization generation is separate from execution
- Compatible with all runtime engines

## Related ADRs
- ADR-0006: Task Tracking Architecture
- ADR-0011: Workflow Execution Improvements
- ADR-0005: Local Execution Strategy

## References
- PR #63: Complete SDK Implementation
- Issue #62: Test Suite Achievement
- psutil documentation: https://psutil.readthedocs.io/