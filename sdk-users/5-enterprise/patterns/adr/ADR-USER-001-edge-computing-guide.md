# ADR-USER-001: Edge Computing Architecture Guide

## Status
Implemented (v0.6.6+)

## Overview

The Kailash SDK provides comprehensive edge computing capabilities that enable geo-distributed applications with compliance-aware data routing, automatic consistency management, and zero-downtime migrations. This guide helps you understand when and how to use edge features.

## When to Use Edge Computing

### Use Edge Computing When You Need:
- **Geographic Distribution**: Data and compute closer to users globally
- **Compliance Requirements**: GDPR, HIPAA, or other data locality regulations
- **Low Latency**: Sub-100ms response times for regional users
- **High Availability**: Survive entire region failures
- **Data Sovereignty**: Keep data within specific jurisdictions

### Don't Use Edge Computing When:
- **Single Region**: All users and data in one geographic location
- **Strong Consistency Required**: Need immediate global consistency
- **Simple Applications**: Basic CRUD without geographic requirements
- **Cost Sensitive**: Edge infrastructure has overhead

## Core Edge Components

### 1. Edge Infrastructure (Automatic)
```python
from kailash.workflow.builder import WorkflowBuilder
# WorkflowBuilder automatically manages edge infrastructure
workflow = WorkflowBuilder()
# Edge configuration set via runtime parameters
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
```

### 2. Edge Data Node
```python
from kailash.workflow.builder import WorkflowBuilder
# Distributed data operations with automatic routing
workflow.add_node("EdgeDataNode", "edge_data", {
    "location_id": "us-east-1",
    "action": "write",
    "key": "user_profile",
    "consistency": "eventual"  # or "strong", "causal", "bounded"
})
```

### 3. Edge State Machine
```python
from kailash.workflow.builder import WorkflowBuilder
# Globally unique state instances
workflow.add_node("EdgeStateMachine", "session_state", {
    "location_id": "eu-west-1",
    "state_id": "user_session_123",
    "action": "transition",
    "new_state": "active"
})
```

### 4. Edge Coordination (v0.6.7+)
```python
from kailash.workflow.builder import WorkflowBuilder
# Distributed consensus and leader election
workflow.add_node("EdgeCoordinationNode", "coordinator", {
    "operation": "elect_leader",
    "coordination_group": "payment_processors"
})
```

### 5. Edge Migration (v0.6.7+)
```python
from kailash.workflow.builder import WorkflowBuilder
# Zero-downtime workload migration
workflow.add_node("EdgeMigrationNode", "migrator", {
    "operation": "plan_migration",
    "source_edge": "us-west-1",
    "target_edge": "us-east-1",
    "workloads": ["api-service", "cache-layer"],
    "strategy": "live"  # or "staged", "bulk", "incremental"
})
```

### 6. Edge Monitoring (v0.6.7+)
```python
from kailash.workflow.builder import WorkflowBuilder
# Comprehensive edge observability
workflow.add_node("EdgeMonitoringNode", "monitor", {
    "operation": "record_metric",
    "edge_node": "ap-south-1",
    "metric_type": "latency",
    "value": 0.045
})
```

## Architecture Patterns

### Pattern 1: Global User Profiles
```python
from kailash.workflow.builder import WorkflowBuilder
# Store user data in their region for compliance
workflow = WorkflowBuilder()
# Edge configuration for compliance
edge_config = {"compliance": {"strict_mode": True}}

workflow.add_node("UserLocationNode", "locate_user", {})
workflow.add_node("EdgeDataNode", "store_profile", {
    "action": "write",
    "key": "user_profile",
    "consistency": "strong"
})

# Automatic routing based on user location
workflow.add_connection("locate_user", "location", "store_profile", "location_id")
workflow.add_connection("locate_user", "user_data", "store_profile", "value")
```

### Pattern 2: Edge Caching
```python
from kailash.workflow.builder import WorkflowBuilder
# Cache frequently accessed data at edge
workflow.add_node("EdgeDataNode", "edge_cache", {
    "action": "read",
    "key": "product_catalog",
    "cache_ttl": 3600,
    "consistency": "bounded",  # Max 5 second staleness
    "bounded_staleness_ms": 5000
})
```

### Pattern 3: Distributed Session Management
```python
from kailash.workflow.builder import WorkflowBuilder
# Global sessions with local state
workflow.add_node("EdgeStateMachine", "session", {
    "state_id": "session_123",
    "action": "create",
    "initial_state": "anonymous",
    "location_id": None  # Auto-detect nearest edge
})

# Session follows user across regions
workflow.add_node("EdgeCoordinationNode", "session_coordinator", {
    "operation": "get_leader",
    "coordination_group": "session_managers"
})
```

### Pattern 4: Compliance-Aware Processing
```python
from kailash.workflow.builder import WorkflowBuilder
# Process data according to regional regulations
workflow = WorkflowBuilder()
# Edge configuration for compliance
edge_config = {
    "compliance": {
        "classifications": {
            "pii": {"allowed_regions": ["us", "eu"]},
            "financial": {"allowed_regions": ["us"]},
            "health": {"allowed_regions": ["us"], "requires_encryption": True}
        }
    }
}

workflow.add_node("DataClassifierNode", "classifier", {})
workflow.add_node("EdgeDataNode", "compliant_storage", {
    "action": "write",
    "auto_route": True  # Routes based on classification
})
```

## Consistency Models

### 1. Strong Consistency
```python
from kailash.workflow.builder import WorkflowBuilder
# All edges see updates immediately
workflow.add_node("EdgeDataNode", "strong_data", {
    "consistency": "strong",
    "action": "write"
})
# Trade-off: Higher latency (50-200ms)
```

### 2. Eventual Consistency
```python
from kailash.workflow.builder import WorkflowBuilder
# Updates propagate asynchronously
workflow.add_node("EdgeDataNode", "eventual_data", {
    "consistency": "eventual",
    "action": "write"
})
# Trade-off: May see stale data temporarily
```

### 3. Causal Consistency
```python
from kailash.workflow.builder import WorkflowBuilder
# Preserves cause-effect relationships
workflow.add_node("EdgeDataNode", "causal_data", {
    "consistency": "causal",
    "session_id": "user_123",  # Track causality per session
    "action": "write"
})
# Trade-off: More complex, moderate latency
```

### 4. Bounded Staleness
```python
from kailash.workflow.builder import WorkflowBuilder
# Maximum staleness guarantee
workflow.add_node("EdgeDataNode", "bounded_data", {
    "consistency": "bounded",
    "bounded_staleness_ms": 1000,  # Max 1 second stale
    "action": "read"
})
# Trade-off: Balance between performance and consistency
```

## DataFlow Integration

### Automatic Edge Distribution
```python
from kailash.workflow.builder import WorkflowBuilder
from dataflow import DataFlow

db = DataFlow(edge_config={
    "discovery": {"locations": ["us-east-1", "eu-west-1"]},
    "compliance": {"strict_mode": True}
})

@db.model
class User:
    name: str
    email: str
    region: str
    _edge_key: str = "region"  # Automatically distribute by region

# Creates edge-aware nodes automatically
workflow = db.create_workflow("user_management")
```

### Edge-Aware Queries
```python
from kailash.workflow.builder import WorkflowBuilder
# Query respects data locality
@db.operation
async def get_regional_users(region: str):
    return await User.filter(region=region).execute()

# Automatically routes to correct edge
eu_users = await get_regional_users("eu-west-1")
```

## Migration Scenarios

### Scenario 1: Planned Maintenance
```python
from kailash.workflow.builder import WorkflowBuilder
# Migrate workloads before maintenance window
migration_workflow = WorkflowBuilder()
migration_workflow.add_node("EdgeMigrationNode", "migrate", {
    "checkpoint_interval": 60,
    "bandwidth_limit_mbps": 500
})

# Plan migration
plan_result = runtime.execute(migration_workflow.build(), {
    "migrate": {
        "operation": "plan_migration",
        "source_edge": "us-west-1",
        "target_edge": "us-west-2",
        "workloads": ["api", "cache", "sessions"],
        "strategy": "staged",
        "constraints": {
            "time_window": "02:00-06:00 UTC",
            "max_downtime_ms": 100
        }
    }
})
```

### Scenario 2: Disaster Recovery
```python
from kailash.workflow.builder import WorkflowBuilder
# Emergency migration during outage
emergency_result = runtime.execute(migration_workflow.build(), {
    "migrate": {
        "operation": "execute_migration",
        "migration_id": plan_result["migrate"]["plan"]["migration_id"],
        "strategy": "emergency",
        "priority": 10
    }
})
```

## Monitoring Best Practices

### 1. Set Up Health Monitoring
```python
from kailash.workflow.builder import WorkflowBuilder
monitor_workflow = WorkflowBuilder()
monitor_workflow.add_node("EdgeMonitoringNode", "health_monitor", {
    "health_check_interval": 30,
    "alert_cooldown": 300
})

# Regular health checks
health_check = runtime.execute(monitor_workflow.build(), {
    "health_monitor": {
        "operation": "get_health",
        "edge_node": "us-east-1"
    }
})
```

### 2. Configure Alerts
```python
from kailash.workflow.builder import WorkflowBuilder
# Set performance thresholds
alert_config = runtime.execute(monitor_workflow.build(), {
    "health_monitor": {
        "operation": "set_threshold",
        "metric_type": "latency",
        "threshold_value": 0.200,  # 200ms
        "severity": "warning"
    }
})
```

### 3. Analyze Trends
```python
from kailash.workflow.builder import WorkflowBuilder
# Get historical analytics
analytics = runtime.execute(monitor_workflow.build(), {
    "health_monitor": {
        "operation": "get_analytics",
        "edge_node": "eu-west-1"
    }
})
```

## Performance Optimization

### 1. Connection Pooling
```python
from kailash.workflow.builder import WorkflowBuilder
edge_config = {
    "performance": {
        "connection_pool_size": 10,
        "connection_timeout": 5000,
        "keepalive": True
    }
}
```

### 2. Batch Operations
```python
from kailash.workflow.builder import WorkflowBuilder
# Batch multiple operations
workflow.add_node("EdgeDataNode", "batch_write", {
    "action": "batch_write",
    "operations": [
        {"key": "user_1", "value": {...}},
        {"key": "user_2", "value": {...}}
    ]
})
```

### 3. Caching Strategy
```python
from kailash.workflow.builder import WorkflowBuilder
# Multi-tier caching
workflow.add_node("EdgeDataNode", "l1_cache", {
    "action": "read",
    "cache_ttl": 60,  # 1 minute L1
    "fallback": "l2_cache"
})

workflow.add_node("EdgeDataNode", "l2_cache", {
    "action": "read",
    "cache_ttl": 3600,  # 1 hour L2
    "fallback": "origin"
})
```

## Security Considerations

### 1. Encryption in Transit
```python
from kailash.workflow.builder import WorkflowBuilder
edge_config = {
    "security": {
        "tls_version": "1.3",
        "cipher_suites": ["TLS_AES_256_GCM_SHA384"],
        "mutual_tls": True
    }
}
```

### 2. Access Control
```python
from kailash.workflow.builder import WorkflowBuilder
workflow.add_node("EdgeDataNode", "secure_data", {
    "action": "write",
    "acl": {
        "read": ["role:viewer", "role:admin"],
        "write": ["role:admin"],
        "delete": ["role:super_admin"]
    }
})
```

## Common Pitfalls

### 1. Over-Distribution
**Problem**: Distributing data that doesn't need edge presence
**Solution**: Only distribute data accessed globally

### 2. Consistency Confusion
**Problem**: Using strong consistency everywhere
**Solution**: Choose consistency model based on use case

### 3. Migration Without Testing
**Problem**: Migrating production without dry runs
**Solution**: Always test migrations in staging

### 4. Ignoring Compliance
**Problem**: Data crossing jurisdiction boundaries
**Solution**: Configure compliance rules upfront

## Cost Optimization

### 1. Edge Selection
- Start with 2-3 strategic edge locations
- Add edges based on user distribution
- Monitor usage patterns before expanding

### 2. Data Tiering
- Hot data: Strong consistency at edge
- Warm data: Eventual consistency with caching
- Cold data: Archive to central storage

### 3. Resource Allocation
- Right-size edge resources
- Use auto-scaling for demand spikes
- Consolidate during off-peak hours

## Getting Started Checklist

1. ✅ Identify geographic distribution needs
2. ✅ Define compliance requirements
3. ✅ Choose initial edge locations
4. ✅ Select consistency models
5. ✅ Plan monitoring strategy
6. ✅ Design migration procedures
7. ✅ Implement security controls
8. ✅ Test in staging environment
9. ✅ Deploy with monitoring
10. ✅ Optimize based on metrics

## References
- [Edge WorkflowBuilder Guide](../../developer/edge-workflowbuilder-guide.md)
- [Edge Node Reference](../../nodes/edge-nodes.md)
- [Consistency Models](../../cheatsheet/054-edge-consistency-patterns.md)
- [Migration Patterns](../../cheatsheet/055-edge-migration-patterns.md)
- [Monitoring Guide](../../cheatsheet/056-edge-monitoring-patterns.md)
