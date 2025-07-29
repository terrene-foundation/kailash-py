# Edge Computing with Kailash SDK

This directory contains documentation and examples for the comprehensive edge computing platform in the Kailash SDK.

## Overview

The Kailash SDK provides a complete edge computing solution with:
- **State Management**: Full lifecycle control of edge nodes
- **Coordination**: Distributed consensus and global ordering
- **Intelligence**: ML-powered predictive edge warming
- **Observability**: Real-time monitoring and analytics
- **Resource Optimization**: AI-driven resource allocation and analysis
- **Migration**: Zero-downtime workload migration
- **Integration**: Seamless workflow and DataFlow support

## Documentation Structure

### Getting Started
- `EDGE_COMPUTING_SUMMARY.md` - Comprehensive overview of all edge features
- `edge-setup-guide.md` - Complete setup instructions for edge deployments

### Core Features
- `edge-state-management-guide.md` - Edge node lifecycle and state management
- `edge-coordination-guide.md` - Distributed coordination with Raft consensus
- `predictive-warming-guide.md` - ML-powered edge node preparation
- `edge-monitoring-guide.md` - Comprehensive monitoring and observability
- `edge-migration-guide.md` - Live workload migration capabilities
- `resource-allocation-guide.md` - Intelligent resource management and optimization

### Integration & Patterns
- `edge-patterns.md` - Common edge computing patterns and best practices
- `edge-node-reference.md` - Reference for all edge-specific nodes
- `examples/` - Working examples of edge computing scenarios

## Quick Start

1. **Basic Edge Setup**:
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

async def basic_edge_setup():
    workflow = WorkflowBuilder()

    # Initialize edge coordination
    workflow.add_node("EdgeCoordinationNode", "coordinator", {
        "operation": "elect_leader",
        "coordination_group": "edge_cluster"
    })

    # Execute
    runtime = LocalRuntime()
    results, run_id = await runtime.execute_async(workflow.build())
    return results

# Run the setup
asyncio.run(basic_edge_setup())
```

2. **Enable Monitoring**:
```python
async def enable_monitoring():
    workflow = WorkflowBuilder()
    workflow.add_node("EdgeMonitoringNode", "monitor", {
        "operation": "start_monitor",
        "anomaly_detection": True
    })

    runtime = LocalRuntime()
    results, run_id = await runtime.execute_async(workflow.build())
    return results

asyncio.run(enable_monitoring())
```

3. **Set Up Predictive Warming**:
```python
async def setup_warming():
    workflow = WorkflowBuilder()
    workflow.add_node("EdgeWarmingNode", "warmer", {
        "operation": "start_auto",
        "confidence_threshold": 0.7
    })

    runtime = LocalRuntime()
    results, run_id = await runtime.execute_async(workflow.build())
    return results

asyncio.run(setup_warming())
```

## Architecture Components

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| **EdgeStateMachine** | Lifecycle management | States, transitions, leases |
| **EdgeAffinityNode** | Optimal placement | Geographic, data locality, compliance |
| **EdgeCoordinationNode** | Distributed consensus | Raft, leader election, ordering |
| **EdgeWarmingNode** | Predictive preparation | ML models, usage patterns |
| **EdgeMonitoringNode** | Observability | Metrics, health, alerts, analytics |
| **EdgeMigrationNode** | Live migration | Zero-downtime workload migration, shared state |

## Integration Points

### With WorkflowBuilder
- Automatic edge node detection
- Seamless state management
- Built-in coordination

### With DataFlow
```python
@db.model
class EdgeData:
    key: str
    value: Any

    class Config:
        edge_enabled = True
        edge_strategy = "geographic"
```

### With Runtime
- Local, parallel, and distributed execution
- Automatic edge optimization
- Fault tolerance

## Performance Benefits

- **Reduced Latency**: 50-90% improvement for edge-local operations
- **Improved Reliability**: Automatic failover and recovery
- **Optimized Resources**: ML-driven capacity planning
- **Better Observability**: Real-time insights and alerts

## Next Steps

1. Read the `EDGE_COMPUTING_SUMMARY.md` for a complete overview
2. Follow `edge-setup-guide.md` for your first deployment
3. Explore specific features in their respective guides
4. Try the examples in `examples/` directory
