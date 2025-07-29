# Edge Computing with WorkflowBuilder

## Overview

The Kailash SDK provides seamless edge computing integration directly in WorkflowBuilder, enabling geo-distributed data processing with compliance awareness and automatic infrastructure management.

## Quick Start

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Configure edge infrastructure
edge_config = {
    "discovery": {
        "locations": ["us-east-1", "eu-west-1", "ap-south-1"],
        "refresh_interval": 300
    },
    "compliance": {
        "strict_mode": True,
        "default_classification": "pii"
    }
}

# Create workflow with edge support
workflow = WorkflowBuilder()
# Edge config passed to runtime

# Add edge nodes - infrastructure is automatically injected
workflow.add_node("EdgeDataNode", "writer", {
    "location_id": "us-east-1",
    "action": "write",
    "consistency": "strong"
})

workflow.add_node("EdgeStateMachine", "state", {
    "state_id": "user_session_123",
    "operation": "set"
})

# Execute workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Architecture

### EdgeInfrastructure Singleton

The SDK uses a singleton pattern to share edge infrastructure across all nodes in a workflow:

```python
# Automatically created and managed by WorkflowBuilder
edge_infrastructure = EdgeInfrastructure(edge_config)

# Provides shared services:
- EdgeDiscovery: Manages edge locations and health
- ComplianceRouter: Ensures data placement compliance
- Shared connection pools and caches
```

### Automatic Edge Detection

WorkflowBuilder automatically detects edge nodes by:
1. Checking node type names for "Edge" keyword
2. Looking for edge-specific node classes
3. Examining node interfaces (has_edge_capabilities)

```python
# These are automatically detected as edge nodes:
workflow.add_node("EdgeDataNode", ...)      # ✅ Contains "Edge"
workflow.add_node("EdgeStateMachine", ...)  # ✅ Contains "Edge"
workflow.add_node("MyCustomEdgeNode", ...)  # ✅ Contains "Edge"
workflow.add_node("DataProcessor", ...)     # ❌ Not an edge node
```

## Edge Node Types

### 1. EdgeDataNode
Distributed data storage with consistency guarantees:

```python
workflow.add_node("EdgeDataNode", "data_store", {
    "action": "write",              # write|read|replicate|sync
    "consistency": "eventual",      # strong|eventual|causal|bounded_staleness
    "replication_factor": 3,
    "conflict_resolution": "last_write_wins"
})
```

### 2. EdgeStateMachine
Globally unique state instances (like Cloudflare Durable Objects):

```python
workflow.add_node("EdgeStateMachine", "user_state", {
    "state_id": "session_xyz",      # Globally unique ID
    "operation": "set",             # get|set|update|delete|increment|append|lock|unlock
    "enable_persistence": True,
    "enable_replication": True
})
```

### 3. EdgeNode (Base)
For custom edge implementations:

```python
from kailash.nodes.edge.base import EdgeNode

@register_node()
class CustomEdgeProcessor(EdgeNode):
    async def async_run(self, **kwargs):
        # Your edge logic here
        await self.ensure_compliance(kwargs.get("data"))
        return {"processed": True}
```

## Compliance and Data Routing

### Automatic Compliance Checking

```python
edge_config = {
    "compliance": {
        "strict_mode": True,
        "zones": {
            "gdpr": ["eu-west-1", "eu-central-1"],
            "hipaa": ["us-east-1", "us-west-2"],
            "sox": ["us-east-1", "eu-west-1"]
        },
        "data_classifications": {
            "pii": ["gdpr"],
            "phi": ["hipaa"],
            "financial": ["sox"]
        }
    }
}

workflow = WorkflowBuilder()
# Edge config passed to runtime

# Data is automatically routed to compliant edges
workflow.add_node("EdgeDataNode", "gdpr_store", {
    "action": "write",
    "data": {"email": "user@example.com"},  # Classified as PII
    # Automatically routes to GDPR-compliant edges only
})
```

### Edge Selection Strategies

```python
workflow.add_node("EdgeDataNode", "optimized_store", {
    "edge_strategy": "lowest_latency",  # lowest_latency|balanced|compliance_first
    "preferred_locations": ["us-east-1", "us-west-2"],
    "exclude_locations": ["ap-south-1"]
})
```

## Consistency Models

### Strong Consistency (2PC)
```python
workflow.add_node("EdgeDataNode", "critical_data", {
    "action": "write",
    "consistency": "strong",  # Uses two-phase commit
    "data": {"balance": 1000}
})
```

### Eventual Consistency
```python
workflow.add_node("EdgeDataNode", "analytics_data", {
    "action": "write",
    "consistency": "eventual",  # Async replication
    "data": {"event": "page_view"}
})
```

### Causal Consistency
```python
workflow.add_node("EdgeDataNode", "chat_messages", {
    "action": "write",
    "consistency": "causal",  # Preserves causality
    "data": {"message": "Hello", "thread_id": "123"}
})
```

### Bounded Staleness
```python
workflow.add_node("EdgeDataNode", "cache_data", {
    "action": "read",
    "consistency": "bounded_staleness",
    "staleness_threshold_ms": 5000  # Max 5 seconds stale
})
```

## Advanced Patterns

### Multi-Region Replication

```python
# Configure multi-region setup
edge_config = {
    "discovery": {
        "locations": ["us-east-1", "eu-west-1", "ap-southeast-1"],
        "health_check_interval": 60
    },
    "replication": {
        "strategy": "multi_region",
        "min_regions": 2
    }
}

workflow = WorkflowBuilder()
# Edge config passed to runtime

# Data automatically replicated across regions
workflow.add_node("EdgeDataNode", "global_data", {
    "action": "write",
    "replication_factor": 3,
    "data": {"content": "global_update"}
})
```

### Edge State Migration

```python
# Stateful edge computations that can migrate
workflow.add_node("EdgeStateMachine", "migratable_state", {
    "state_id": "compute_task_123",
    "operation": "set",
    "lease_duration_ms": 30000,  # 30 second lease
    "enable_migration": True
})

# State automatically migrates to optimal edge based on access patterns
```

### Compliance-Aware Workflows

```python
# Process PII in GDPR regions only
workflow.add_node("EdgeDataNode", "eu_processor", {
    "action": "write",
    "compliance_zones": ["gdpr"],
    "data": {"user_id": "eu_user_123"}
})

# Process financial data in SOX-compliant regions
workflow.add_node("EdgeDataNode", "financial_processor", {
    "action": "write",
    "compliance_zones": ["sox"],
    "data": {"transaction": "payment_456"}
})

# Connect with compliance-aware routing
workflow.add_connection("eu_processor", "result", "financial_processor", "input")
```

## Integration with DataFlow

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder

db = DataFlow()

@db.model
class UserProfile:
    user_id: str
    region: str
    preferences: dict

# Edge-aware workflow
edge_config = {
    "discovery": {"locations": ["us-east-1", "eu-west-1"]},
    "dataflow_integration": True  # Enable DataFlow hooks
}

workflow = WorkflowBuilder()
# Edge config passed to runtime

# DataFlow operations automatically use edge infrastructure
workflow.add_node("UserProfileCreateNode", "create_user", {
    "model": "UserProfile",
    "data": {"user_id": "123", "region": "eu"}
    # Automatically routes to EU edge for GDPR compliance
})
```

## Monitoring and Observability

```python
# Enable edge monitoring
edge_config = {
    "monitoring": {
        "metrics_enabled": True,
        "trace_enabled": True,
        "health_check_interval": 30
    }
}

workflow = WorkflowBuilder()
# Edge config passed to runtime

# Add monitoring node
workflow.add_node("EdgeMonitoringNode", "monitor", {
    "metrics": ["latency", "throughput", "error_rate"],
    "alert_thresholds": {
        "latency_p99_ms": 100,
        "error_rate": 0.01
    }
})
```

## Best Practices

### 1. Resource Efficiency
```python
# Share infrastructure across workflows
edge_config = {"discovery": {"locations": ["us-east-1"]}}

# Multiple workflows share the same EdgeInfrastructure
workflow1 = WorkflowBuilder()
workflow2 = WorkflowBuilder()  # Reuses infrastructure via runtime
```

### 2. Graceful Degradation
```python
workflow.add_node("EdgeDataNode", "resilient_store", {
    "action": "write",
    "fallback_strategy": "any_available",  # Write to any edge if preferred fails
    "min_replicas": 1  # Degrade to 1 replica if needed
})
```

### 3. Zero-Config Operation
```python
# Works without explicit edge_config
workflow = WorkflowBuilder()  # No edge_config

# Edge nodes still work with defaults
workflow.add_node("EdgeDataNode", "auto_edge", {
    "action": "write"
    # Uses default edge discovery and routing
})
```

## Troubleshooting

### Common Issues

1. **"No edge infrastructure available"**
   - Ensure edge_config is passed to WorkflowBuilder
   - Check that edge locations are correctly specified

2. **"Compliance violation: cannot place data"**
   - Verify compliance zones match data classification
   - Check that target edges support required compliance

3. **"Edge node not detected"**
   - Ensure node name contains "Edge" keyword
   - Verify node extends EdgeNode base class

### Debug Mode

```python
import logging

# Enable debug logging
logging.getLogger("kailash.workflow.edge_infrastructure").setLevel(logging.DEBUG)
logging.getLogger("kailash.edge").setLevel(logging.DEBUG)

# Create workflow with debug info
workflow = WorkflowBuilder()
edge_config = {
    "debug": True,
    "discovery": {"locations": ["us-east-1"]}
}
```

## Migration Guide

### From Manual Edge Management

Before:
```python
# Manual edge setup
discovery = EdgeDiscovery(config)
router = ComplianceRouter(zones)
node = EdgeDataNode(discovery=discovery, router=router)
```

After:
```python
# Automatic with WorkflowBuilder
workflow = WorkflowBuilder()
# Edge config passed to runtime
workflow.add_node("EdgeDataNode", "node_id", params)
# Infrastructure automatically injected!
```

### From Separate EdgeWorkflowBuilder

Before:
```python
# Hypothetical separate builder (deprecated pattern)
# workflow = EdgeWorkflowBuilder(edge_config)  # No longer exists
```

After:
```python
# Integrated into main WorkflowBuilder
workflow = WorkflowBuilder()
# Edge config passed to runtime
# Same API, better integration!
```

## Future Enhancements

### Phase 3 Roadmap

1. **Edge Coordination** - Cross-edge transaction coordination
2. **Predictive Edge Warming** - ML-based edge pre-warming
3. **Edge Monitoring** - Advanced observability features
4. **Edge Migration Tools** - Automated state migration

## Summary

The edge WorkflowBuilder integration provides:
- ✅ Automatic edge infrastructure management
- ✅ Shared resources via singleton pattern
- ✅ Compliance-aware data routing
- ✅ Multiple consistency models
- ✅ Seamless DataFlow integration
- ✅ Zero-config operation with smart defaults

Start building geo-distributed, compliant workflows today with just a few lines of code!
