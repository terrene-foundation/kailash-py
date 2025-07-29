# Performance Tracking and Visualization

This document describes the integrated performance tracking and visualization capabilities added to the Kailash SDK.

## Overview

The performance tracking system provides comprehensive metrics collection during workflow execution, including:

- **Execution Time**: Accurate timing for each node
- **CPU Usage**: Average CPU utilization during node execution
- **Memory Usage**: Peak memory consumption and memory delta
- **I/O Operations**: Read/write operations and data transfer metrics
- **Thread Information**: Thread count and context switches
- **Custom Metrics**: Extensible framework for business-specific metrics

## Architecture

### Components

1. **MetricsCollector** (`kailash.tracking.metrics_collector`)
   - Collects performance metrics using process monitoring
   - Supports both synchronous and asynchronous execution
   - Provides context managers and decorators for easy integration

2. **PerformanceVisualizer** (`kailash.visualization.performance`)
   - Creates various performance charts and reports
   - Integrates with TaskManager to access execution data
   - Supports run comparisons and trend analysis

3. **Enhanced Runtime Integration**
   - LocalRuntime and ParallelRuntime automatically collect metrics
   - Metrics are stored with TaskRun objects via TaskManager
   - No code changes required in existing nodes

## Usage

### Basic Workflow Execution with Metrics

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.tracking import TaskManager

# Create workflow
workflow = WorkflowBuilder()
# Add nodes and connections
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'data': [1, 2, 3]}"
})

# Execute with tracking
task_manager = TaskManager()
runtime = LocalRuntime()

run_id = task_manager.create_run(workflow_name="my_workflow")
results, _ = runtime.execute(
    workflow=workflow.build(),
    task_manager=task_manager
)

# Metrics are automatically collected and stored

```

### Generating Performance Visualizations

```python
from kailash.visualization.performance import PerformanceVisualizer

# Create visualizer
perf_viz = PerformanceVisualizer(task_manager)

# Generate comprehensive performance report
outputs = perf_viz.create_run_performance_summary(run_id)

# outputs contains paths to:
# - execution_timeline: Gantt chart of task execution
# - resource_usage: CPU, memory, and duration charts
# - performance_comparison: Radar chart comparing node types
# - io_analysis: I/O operations breakdown
# - performance_heatmap: Normalized metrics heatmap
# - report: Markdown report with insights

```

### Integrated Performance Dashboard

```python
from kailash.workflow.visualization import WorkflowVisualizer

# Create integrated dashboard
workflow = WorkflowBuilder()
# Add your nodes here
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'data': [1, 2, 3]}"
})

workflow_viz = WorkflowVisualizer(workflow.build())
dashboard = workflow_viz.create_performance_dashboard(
    run_id=run_id,
    task_manager=task_manager
)

# Opens HTML dashboard with all visualizations

```

### Comparing Multiple Runs

```python
# Execute workflow multiple times
run_ids = []
for i in range(3):
    workflow = WorkflowBuilder()
    workflow.add_node("PythonCodeNode", "processor", {
        "code": "result = {'data': [1, 2, 3]}"
    })

    run_id = task_manager.create_run(workflow_name=f"test_run_{i}")
    runtime = LocalRuntime()
    results, _ = runtime.execute(
        workflow=workflow.build(),
        task_manager=task_manager
    )
    run_ids.append(run_id)

# Compare performance
comparison = perf_viz.compare_runs(run_ids)

```

## Metrics Collected

### Standard Metrics

- **duration**: Execution time in seconds
- **cpu_usage**: Average CPU percentage
- **memory_usage_mb**: Peak memory in megabytes
- **memory_delta_mb**: Memory increase during execution
- **io_read_bytes**: Bytes read from disk
- **io_write_bytes**: Bytes written to disk
- **io_read_count**: Number of read operations
- **io_write_count**: Number of write operations
- **thread_count**: Number of threads used
- **context_switches**: Number of context switches

### Custom Metrics

Nodes can report custom metrics through the context:

```python
from kailash.nodes.base import Node, NodeParameter

class MetricsAwareNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(name="data", type=list, required=True)
        }

    def run(self, **kwargs):
        data = kwargs.get("data", [])

        # Process data
        processed_data = [item for item in data if not item.get("error")]
        processed_count = len(data)
        error_count = sum(1 for item in data if item.get("error"))

        # Return custom metrics
        return {
            "data": processed_data,
            "_metrics": {
                "processed_count": processed_count,
                "error_count": error_count,
                "success_rate": (processed_count - error_count) / processed_count if processed_count > 0 else 0
            }
        }

# Use in workflow
workflow = WorkflowBuilder()
workflow.add_node("MetricsAwareNode", "processor", {})

```

## Visualization Types

### 1. Execution Timeline
- Gantt-style chart showing task execution order and duration
- Color-coded by task status (completed, failed, running)
- CPU usage annotations on each task

### 2. Resource Usage Charts
- Bar charts for CPU usage, memory usage, and execution time
- Grouped by node for easy comparison
- Shows both peak and delta values for memory

### 3. Performance Comparison
- Radar chart comparing different node types
- Normalized metrics for fair comparison
- Useful for identifying performance patterns

### 4. I/O Analysis
- Separate charts for data transfer and operation counts
- Read vs write comparison
- Helps identify I/O bottlenecks

### 5. Performance Heatmap
- Matrix view of all metrics across all nodes
- Color-coded intensity for quick identification
- Normalized by metric type

### 6. Performance Report
- Comprehensive markdown report
- Summary statistics and bottleneck analysis
- Task-by-task performance details
- Actionable insights

## Dependencies

- **Required**: None (basic duration tracking works out of the box)
- **Recommended**: `psutil` for comprehensive metrics
  ```bash
  pip install psutil
  ```

## Examples

See `examples/visualization_examples/viz_performance_tracking.py` for a complete demonstration of:
- Creating workflows with different performance characteristics
- Collecting and visualizing performance metrics
- Generating integrated dashboards
- Comparing multiple runs
- Working with custom metrics

## Best Practices

1. **Install psutil** for comprehensive metrics collection
2. **Use TaskManager** to enable automatic metrics collection
3. **Generate visualizations** after workflow execution for insights
4. **Compare runs** to identify performance regressions
5. **Monitor resource usage** to optimize node implementations
6. **Add custom metrics** for business-specific KPIs

## Performance Impact

The metrics collection system is designed to have minimal impact:
- Sampling-based approach for CPU and memory monitoring
- Background thread for resource monitoring
- Configurable sampling interval (default: 100ms)
- Graceful degradation when psutil is not available
