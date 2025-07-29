# Intelligent Resource Allocation Guide

## Overview

The Kailash SDK's Phase 4 edge computing features provide AI-driven resource optimization, enabling intelligent allocation, predictive scaling, and cost optimization across distributed edge infrastructure.

## Key Components

### 1. Resource Analyzer
- Real-time resource usage tracking
- Pattern identification and anomaly detection
- Bottleneck identification
- Resource utilization optimization

### 2. Resource Pools
- Unified resource abstraction
- CPU, memory, GPU, storage management
- Network bandwidth allocation
- Edge-specific resource constraints

### 3. Resource Analyzer Node
- Workflow integration for resource analysis
- Pattern detection and recommendations
- Trend analysis and forecasting

## Quick Start

### Basic Resource Analysis

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Record resource metrics
workflow.add_node("ResourceAnalyzerNode", "recorder", {
    "operation": "record_metric",
    "edge_node": "edge-west-1",
    "resource_type": "cpu",
    "used": 3.2,
    "total": 4.0
})

# Analyze resources for patterns
workflow.add_node("ResourceAnalyzerNode", "analyzer", {
    "operation": "analyze",
    "include_patterns": True,
    "include_bottlenecks": True,
    "include_anomalies": True
})

# Get optimization recommendations
workflow.add_node("ResourceAnalyzerNode", "optimizer", {
    "operation": "get_recommendations"
})

# Connect nodes
workflow.add_connection("recorder", "result", "analyzer", "metrics")
workflow.add_connection("analyzer", "analysis", "optimizer", "input_data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Resource Pool Management

```python
from kailash.edge.resource import (
    ResourcePool,
    ResourceSpec,
    ResourceRequest,
    ResourceUnit,
    AllocationStrategy
)

# Create resource specifications
cpu_spec = ResourceSpec(
    resource_type="cpu",
    capacity=16.0,
    unit=ResourceUnit.CORES,
    shareable=True
)

memory_spec = ResourceSpec(
    resource_type="memory",
    capacity=32768.0,
    unit=ResourceUnit.MEGABYTES,
    shareable=True
)

# Create resource pool
pool = ResourcePool(
    edge_node="edge-west-1",
    resources=[cpu_spec, memory_spec],
    allocation_strategy=AllocationStrategy.BEST_FIT,
    oversubscription_ratio=1.2  # Allow 20% oversubscription
)

# Request resources
request = ResourceRequest(
    requester="ml-service",
    resources={"cpu": 4.0, "memory": 8192.0},
    priority=7,
    duration=3600,  # 1 hour
    preemptible=True
)

# Allocate resources
result = await pool.allocate(request)
if result.success:
    print(f"Allocated: {result.allocations[0].allocation_id}")
else:
    print(f"Failed: {result.reason}")
    print(f"Suggestions: {result.suggestions}")
```

## Resource Analysis Features

### 1. Pattern Detection

The analyzer identifies several types of patterns:

```python
# Start background analysis
workflow.add_node("ResourceAnalyzerNode", "analyzer", {
    "operation": "start_analyzer",
    "analysis_interval": 60,  # Analyze every minute
    "pattern_confidence_threshold": 0.7
})

# Patterns detected:
# - Periodic: Regular usage cycles
# - Spike: Sudden usage increases
# - Growth: Gradual resource growth
# - Imbalance: Uneven distribution
```

### 2. Bottleneck Detection

Identifies various types of bottlenecks:

```python
# Types of bottlenecks:
# - Capacity: Not enough resources
# - Allocation: Poor distribution
# - Contention: Resource conflicts
# - Fragmentation: Wasted space
# - Throttling: Rate limiting

# Example bottleneck response:
{
    "bottleneck_type": "capacity",
    "severity": 0.85,
    "edge_node": "edge-west-1",
    "resource_type": "cpu",
    "description": "Sustained high CPU utilization (92.5%)",
    "impact": {
        "performance_degradation": "high",
        "request_failures": True,
        "user_impact": "significant"
    },
    "resolution": [
        "Increase CPU capacity on edge-west-1",
        "Migrate workloads to other nodes",
        "Optimize resource-intensive operations",
        "Enable vertical scaling"
    ]
}
```

### 3. Trend Analysis

```python
workflow.add_node("ResourceAnalyzerNode", "trends", {
    "operation": "get_trends",
    "edge_node": "edge-west-1",
    "resource_type": "cpu",
    "duration_minutes": 60
})

# Response includes:
# - Current utilization
# - Average, min, max over period
# - Trend direction and slope
# - 1-hour prediction
```

### 4. Anomaly Detection

```python
# Automatic anomaly detection with configurable threshold
workflow.add_node("ResourceAnalyzerNode", "analyzer", {
    "operation": "analyze",
    "anomaly_threshold": 2.5,  # Standard deviations
    "include_anomalies": True
})

# Anomalies include:
# - Unusual resource spikes
# - Unexpected drops
# - Pattern deviations
```

## Resource Allocation Strategies

### 1. First Fit
Allocates to the first available slot:
```python
pool = ResourcePool(
    edge_node="edge-1",
    resources=specs,
    allocation_strategy=AllocationStrategy.FIRST_FIT
)
```

### 2. Best Fit
Finds the smallest adequate slot:
```python
pool = ResourcePool(
    edge_node="edge-1",
    resources=specs,
    allocation_strategy=AllocationStrategy.BEST_FIT
)
```

### 3. Priority Based
Allocates based on request priority:
```python
pool = ResourcePool(
    edge_node="edge-1",
    resources=specs,
    allocation_strategy=AllocationStrategy.PRIORITY_BASED
)

# High priority request
critical_request = ResourceRequest(
    requester="critical-service",
    resources={"cpu": 8.0},
    priority=9  # 1-10, higher is more important
)
```

### 4. Fair Share
Equal distribution among requesters:
```python
pool = ResourcePool(
    edge_node="edge-1",
    resources=specs,
    allocation_strategy=AllocationStrategy.FAIR_SHARE
)
```

## Advanced Features

### 1. Resource Preemption

High-priority requests can preempt lower priority allocations:

```python
# Enable preemption for critical request
critical_request = ResourceRequest(
    requester="emergency-service",
    resources={"cpu": 4.0, "memory": 8192.0},
    priority=9,  # High priority
    preemptible=False  # Cannot be preempted
)

# This may preempt lower priority allocations
result = await pool.allocate(critical_request)
if result.success:
    print(f"Preempted allocations: {len(result.preempted)}")
```

### 2. Oversubscription

Allow controlled oversubscription for better utilization:

```python
# Allow 30% oversubscription
pool = ResourcePool(
    edge_node="edge-1",
    resources=specs,
    oversubscription_ratio=1.3
)
```

### 3. Time-Limited Allocations

Resources automatically released after duration:

```python
# Allocate for 1 hour
temp_request = ResourceRequest(
    requester="batch-job",
    resources={"cpu": 2.0},
    duration=3600  # Seconds
)

# Automatic cleanup of expired allocations
expired_count = await pool.cleanup_expired()
```

### 4. Multi-Node Allocation

```python
from kailash.edge.resource import ResourcePoolManager

# Create pool manager
manager = ResourcePoolManager()
manager.add_pool(pool1)
manager.add_pool(pool2)

# Find best node for allocation
best_node = await manager.find_best_node(
    request,
    strategy="least_loaded"  # or "most_capacity", "balanced"
)

# Allocate with preferred nodes
result = await manager.allocate(
    request,
    preferred_nodes=["edge-west-1", "edge-west-2"]
)
```

## Optimization Recommendations

The analyzer provides actionable recommendations:

```python
workflow.add_node("ResourceAnalyzerNode", "optimizer", {
    "operation": "get_recommendations"
})

# Example recommendations:
[
    {
        "type": "pattern",
        "priority": "high",
        "pattern": "periodic",
        "affected_nodes": ["edge-west-1"],
        "recommendations": [
            "Implement predictive scaling with 300s period",
            "Use time-based resource allocation",
            "Consider workload scheduling optimization"
        ],
        "expected_improvement": "15-25%"
    },
    {
        "type": "bottleneck",
        "priority": "critical",
        "issue": "Sustained high CPU utilization (92.5%)",
        "node": "edge-west-1",
        "resource": "cpu",
        "resolutions": [
            "Increase CPU capacity on edge-west-1",
            "Migrate workloads to other nodes"
        ],
        "impact": {
            "performance_degradation": "high",
            "request_failures": True
        }
    }
]
```

## Integration with Other Edge Features

### 1. With Edge Monitoring

```python
# Monitor resource metrics
workflow.add_node("EdgeMonitoringNode", "monitor", {
    "operation": "record_metric",
    "edge_node": "edge-west-1",
    "metric_type": "resource_usage",
    "value": 85.5
})

# Feed to resource analyzer
workflow.add_node("ResourceAnalyzerNode", "analyzer", {
    "operation": "record_metric",
    "edge_node": "edge-west-1",
    "resource_type": "cpu",
    "used": 3.4,
    "total": 4.0
})

workflow.add_connection("monitor", "metric", "analyzer", "metadata")
```

### 2. With Predictive Warming

```python
# Use resource predictions for warming decisions
workflow.add_node("ResourceAnalyzerNode", "predictor", {
    "operation": "get_trends",
    "duration_minutes": 30
})

workflow.add_node("EdgeWarmingNode", "warmer", {
    "operation": "warm_nodes",
    "auto_execute": True
})

workflow.add_connection("predictor", "trends", "warmer", "resource_hints")
```

### 3. With Edge Migration

```python
# Use resource analysis for migration decisions
workflow.add_node("ResourceAnalyzerNode", "analyzer", {
    "operation": "analyze",
    "include_bottlenecks": True
})

workflow.add_node("EdgeMigrationNode", "migrator", {
    "operation": "plan_migration",
    "strategy": "resource_aware"
})

workflow.add_connection("analyzer", "bottlenecks", "migrator", "resource_constraints")
```

## Best Practices

### 1. Regular Metric Collection
```python
# Collect metrics every 10 seconds
import asyncio

async def collect_metrics():
    while True:
        # Get actual resource usage
        cpu_usage = get_cpu_usage()  # Your implementation
        memory_usage = get_memory_usage()

        await analyzer_node.execute_async(
            operation="record_metric",
            edge_node="edge-1",
            resource_type="cpu",
            used=cpu_usage.used,
            total=cpu_usage.total
        )

        await asyncio.sleep(10)
```

### 2. Proactive Analysis
```python
# Enable background analysis
await analyzer_node.execute_async(
    operation="start_analyzer",
    analysis_interval=60,  # Every minute
    history_window=3600    # 1 hour window
)
```

### 3. Act on Recommendations
```python
# Get and apply recommendations
result = await analyzer_node.execute_async(
    operation="get_recommendations"
)

for rec in result["recommendations"]:
    if rec["priority"] == "critical":
        # Take immediate action
        await apply_recommendation(rec)
```

### 4. Monitor Allocation Success
```python
# Track allocation metrics
allocation_success_rate = successful_allocations / total_requests
if allocation_success_rate < 0.9:
    # Investigate resource constraints
    analysis = await analyzer_node.execute_async(
        operation="analyze"
    )
```

## Performance Considerations

1. **Metric Storage**: Metrics are stored in memory with configurable retention
2. **Analysis Overhead**: Background analysis runs asynchronously
3. **Pattern Detection**: Uses efficient algorithms (FFT for periodicity)
4. **Scalability**: Designed for hundreds of nodes and thousands of metrics

## Troubleshooting

### Common Issues

1. **No Patterns Detected**
   - Ensure sufficient metrics collected (100+ for periodic patterns)
   - Check pattern confidence threshold
   - Verify metric variety

2. **False Anomalies**
   - Adjust anomaly threshold (default 2.5 std devs)
   - Ensure adequate historical data
   - Check for legitimate usage changes

3. **Allocation Failures**
   - Review resource specifications
   - Check oversubscription settings
   - Consider preemption for critical requests

## Summary

The Intelligent Resource Allocation system provides:
- Real-time resource analysis
- Pattern and bottleneck detection
- Optimization recommendations
- Flexible allocation strategies
- Integration with other edge features

This enables efficient resource utilization, proactive problem detection, and optimal performance across your edge infrastructure.
