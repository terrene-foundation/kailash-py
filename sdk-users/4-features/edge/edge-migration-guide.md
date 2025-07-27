# Edge Migration Guide

This guide covers the comprehensive edge migration capabilities in the Kailash SDK for zero-downtime workload migration between edge nodes.

## Overview

The Edge Migration system provides:
- **Zero-downtime migration** with live traffic switching
- **Multiple migration strategies** for different scenarios
- **Checkpoint and rollback** capabilities
- **Progress tracking** and monitoring
- **Bandwidth management** and compression
- **Integration** with edge monitoring and coordination
- **Shared state coordination** across multiple workflows and nodes

## Quick Start

### Basic Migration

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def basic_migration():
    workflow = WorkflowBuilder()

    # Plan a migration - shared state automatically available to other nodes
    workflow.add_node("EdgeMigrationNode", "plan", {
        "operation": "plan_migration",
        "source_edge": "edge-west-1",
        "target_edge": "edge-east-1",
        "workloads": ["api-service", "cache-layer"],
        "strategy": "live"
    })

    # Check migration status (demonstrates shared state access)
    workflow.add_node("EdgeMigrationNode", "status", {
        "operation": "get_active_migrations"
    })

    # Connect for sequential execution
    workflow.add_connection("plan", "status", "status", "input")

    # Execute
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    # Migration plan is now accessible across all EdgeMigrationNode instances
    migration_id = results["plan"]["plan"]["migration_id"]
    print(f"Migration {migration_id} planned and visible system-wide")

    return results

# Run the migration
basic_migration()
```

## Migration Strategies

### 1. Live Migration (Default)
Minimal downtime with continuous synchronization:

```python
workflow.add_node("EdgeMigrationNode", "migrate", {
    "operation": "plan_migration",
    "source_edge": "primary",
    "target_edge": "secondary",
    "workloads": ["critical-app"],
    "strategy": "live",
    "constraints": {
        "max_downtime": "30s",
        "sync_interval": "5s"
    }
})
```

### 2. Staged Migration
Controlled phases for large workloads:

```python
workflow.add_node("EdgeMigrationNode", "migrate", {
    "operation": "plan_migration",
    "source_edge": "datacenter-1",
    "target_edge": "datacenter-2",
    "workloads": ["database", "file-storage"],
    "strategy": "staged",
    "constraints": {
        "time_window": "02:00-06:00",
        "validation_required": True
    }
})
```

### 3. Bulk Migration
Fast transfer for non-critical workloads:

```python
workflow.add_node("EdgeMigrationNode", "migrate", {
    "operation": "plan_migration",
    "source_edge": "old-edge",
    "target_edge": "new-edge",
    "workloads": ["batch-processor", "logging"],
    "strategy": "bulk",
    "bandwidth_limit_mbps": 1000
})
```

### 4. Incremental Migration
Delta synchronization for large datasets:

```python
workflow.add_node("EdgeMigrationNode", "migrate", {
    "operation": "plan_migration",
    "source_edge": "primary-db",
    "target_edge": "replica-db",
    "workloads": ["large-database"],
    "strategy": "incremental",
    "constraints": {
        "sync_interval": "10m",
        "delta_threshold": "100MB"
    }
})
```

### 5. Emergency Migration
Fast evacuation for failures:

```python
workflow.add_node("EdgeMigrationNode", "evacuate", {
    "operation": "plan_migration",
    "source_edge": "failing-edge",
    "target_edge": "backup-edge",
    "workloads": ["all-critical"],
    "strategy": "emergency",
    "priority": 10,  # Maximum priority
    "constraints": {
        "skip_validation": True,
        "force_migration": True
    }
})
```

## Migration Phases

Each migration progresses through these phases:

1. **Planning** - Resource validation and capacity check
2. **Pre-sync** - Target environment preparation
3. **Sync** - Data synchronization
4. **Cutover** - Traffic switching
5. **Validation** - Functionality verification
6. **Cleanup** - Source cleanup and resource release

## Progress Monitoring

```python
# Create monitoring workflow
workflow = WorkflowBuilder()

# Start migration
workflow.add_node("EdgeMigrationNode", "migrate", {
    "operation": "execute_migration",
    "migration_id": "existing_migration_id"
})

# Monitor progress
workflow.add_node("EdgeMigrationNode", "progress", {
    "operation": "get_progress"
})

# Check metrics
workflow.add_node("EdgeMigrationNode", "metrics", {
    "operation": "get_metrics"
})

# Connect for continuous monitoring
# Pass migration_id from migrate result to progress
workflow.add_connection("migrate", "result", "progress", "migration_id")
workflow.add_connection("progress", "result", "metrics", "input")
```

## Pause and Resume

For long-running migrations using shared state coordination:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def pause_resume_migration():
    # Create migration plan in first workflow
    plan_workflow = WorkflowBuilder()
    plan_workflow.add_node("EdgeMigrationNode", "plan", {
        "operation": "plan_migration",
        "source_edge": "edge-source",
        "target_edge": "edge-target",
        "workloads": ["long-running-service"],
        "strategy": "incremental"
    })

    runtime = LocalRuntime()
    plan_results, _ = runtime.execute(plan_workflow.build())
    migration_id = plan_results["plan"]["plan"]["migration_id"]

    # Pause migration in separate workflow (shared state coordination)
    pause_workflow = WorkflowBuilder()
    pause_workflow.add_node("EdgeMigrationNode", "pause", {
        "operation": "pause_migration",
        "migration_id": migration_id
    })

    runtime.execute(pause_workflow.build())

    # Resume migration later (again using shared state)
    resume_workflow = WorkflowBuilder()
    resume_workflow.add_node("EdgeMigrationNode", "resume", {
        "operation": "resume_migration",
        "migration_id": migration_id
    })

    resume_results, _ = runtime.execute(resume_workflow.build())
    return resume_results

# Run pause/resume example
pause_resume_migration()
```

## Rollback Capabilities

Automatic and manual rollback options:

```python
# Automatic rollback on failure
workflow.add_node("EdgeMigrationNode", "migrate", {
    "operation": "execute_migration",
    "migration_id": "migration_123",
    "auto_rollback": True
})

# Manual rollback to checkpoint
workflow.add_node("EdgeMigrationNode", "rollback", {
    "operation": "rollback_migration",
    "migration_id": "migration_123",
    "checkpoint_id": "checkpoint_456"  # Optional
})
```

## Bandwidth Management

Control network usage during migration:

```python
workflow.add_node("EdgeMigrationNode", "migrate", {
    "operation": "plan_migration",
    "source_edge": "edge-1",
    "target_edge": "edge-2",
    "workloads": ["large-data"],
    "bandwidth_limit_mbps": 100,  # Limit to 100 Mbps
    "enable_compression": True,    # Enable compression
    "sync_batch_size": 1000       # Records per batch
})
```

## Integration with Edge Monitoring

Monitor migrations with edge observability:

```python
# Start edge monitoring
workflow.add_node("EdgeMonitoringNode", "monitor", {
    "operation": "start_monitor",
    "edge_nodes": ["source-edge", "target-edge"],
    "anomaly_detection": True
})

# Plan migration
workflow.add_node("EdgeMigrationNode", "migrate", {
    "operation": "plan_migration",
    "source_edge": "source-edge",
    "target_edge": "target-edge",
    "workloads": ["monitored-app"]
})

# Get post-migration analytics
workflow.add_node("EdgeMonitoringNode", "analytics", {
    "operation": "get_analytics",
    "edge_nodes": ["source-edge", "target-edge"],
    "time_range": "1h"
})

# Connect for integrated monitoring
workflow.add_connection("monitor", "status", "migrate", "input")
workflow.add_connection("migrate", "plan", "analytics", "migration_info")
```

## Shared State Architecture

The EdgeMigrationNode uses a singleton EdgeMigrationService for shared state coordination across all node instances:

### Cross-Workflow Coordination

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def cross_workflow_coordination():
    """Demonstrates migration coordination across separate workflows."""
    runtime = LocalRuntime()

    # Workflow 1: Planning team creates migration plan
    planning_workflow = WorkflowBuilder()
    planning_workflow.add_node("EdgeMigrationNode", "plan", {
        "operation": "plan_migration",
        "source_edge": "datacenter-east",
        "target_edge": "datacenter-west",
        "workloads": ["user-service", "auth-service"],
        "strategy": "staged",
        "priority": 8
    })

    plan_results, _ = await runtime.execute_async(planning_workflow.build())
    migration_id = plan_results["plan"]["plan"]["migration_id"]
    print(f"Planning team created migration: {migration_id}")

    # Workflow 2: Operations team monitors (different workflow, same state)
    monitoring_workflow = WorkflowBuilder()
    monitoring_workflow.add_node("EdgeMigrationNode", "check_active", {
        "operation": "get_active_migrations"
    })

    monitor_results, _ = runtime.execute(monitoring_workflow.build())
    active_migrations = monitor_results["check_active"]["migrations"]
    active_ids = [m["migration_id"] for m in active_migrations]

    # Migration created by planning team should be visible to operations team
    assert migration_id in active_ids, "Shared state coordination working"
    print(f"Operations team sees migration: {migration_id}")

    # Workflow 3: Execution team pauses migration (shared state access)
    execution_workflow = WorkflowBuilder()
    execution_workflow.add_node("EdgeMigrationNode", "pause", {
        "operation": "pause_migration",
        "migration_id": migration_id
    })

    runtime.execute(execution_workflow.build())
    print(f"Execution team paused migration: {migration_id}")

    return {"migration_id": migration_id, "workflows_coordinated": 3}

# Run cross-workflow example
cross_workflow_coordination()
```

### Thread-Safe Operations

All EdgeMigrationNode instances automatically share state through thread-safe operations:
- Migration plans created by any node are visible to all other nodes
- Progress updates are synchronized across all instances
- Concurrent operations are safely coordinated with locks
- No manual state synchronization required

## Configuration Options

### EdgeMigrationNode Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `checkpoint_interval` | int | 60 | Seconds between checkpoints |
| `sync_batch_size` | int | 1000 | Records per sync batch |
| `bandwidth_limit_mbps` | float | None | Bandwidth limit in Mbps |
| `enable_compression` | bool | True | Enable data compression |

### Migration Constraints

| Constraint | Example | Purpose |
|------------|---------|---------|
| `time_window` | "02:00-06:00" | Maintenance window |
| `bandwidth` | "50mbps" | Network limit |
| `max_downtime` | "5m" | Maximum allowed downtime |
| `sync_interval` | "10s" | Sync frequency |
| `delta_threshold` | "100MB" | Incremental threshold |
| `skip_validation` | True | Emergency mode |
| `force_migration` | True | Override safety checks |

## Best Practices

### 1. Pre-Migration Checklist
- Verify target edge capacity
- Check network connectivity
- Validate workload compatibility
- Schedule maintenance window
- Notify stakeholders

### 2. Migration Strategy Selection
- **Live**: For critical services requiring < 1 minute downtime
- **Staged**: For large workloads with validation requirements
- **Bulk**: For non-critical services during maintenance
- **Incremental**: For databases and large datasets
- **Emergency**: For disaster recovery only

### 3. Resource Planning
```python
# Check resources before migration
workflow.add_node("EdgeMonitoringNode", "check_resources", {
    "operation": "get_health",
    "edge_nodes": ["target-edge"]
})

workflow.add_node("EdgeMigrationNode", "migrate", {
    "operation": "plan_migration",
    "source_edge": "source-edge",
    "target_edge": "target-edge",
    "workloads": ["app"]
})

# Only migrate if resources available
workflow.add_connection("check_resources", "result", "health", "input")
```

### 4. Testing and Validation
```python
# Add validation phase
workflow.add_node("EdgeMigrationNode", "validate", {
    "operation": "get_progress",
    "validate_functionality": True,
    "test_endpoints": [
        "/api/health",
        "/api/status"
    ]
})
```

## Complete Example: Multi-Stage Migration

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def migrate_application_stack():
    """Migrate complete application stack between regions."""

    workflow = WorkflowBuilder()

    # 1. Start migration service
    workflow.add_node("EdgeMigrationNode", "start_service", {
        "operation": "start_migrator",
        "checkpoint_interval": 30,
        "bandwidth_limit_mbps": 500
    })

    # 2. Enable monitoring
    workflow.add_node("EdgeMonitoringNode", "monitor", {
        "operation": "start_monitor",
        "edge_nodes": ["us-west", "us-east"],
        "anomaly_detection": True
    })

    # 3. Migrate database first (incremental)
    workflow.add_node("EdgeMigrationNode", "migrate_db", {
        "operation": "plan_migration",
        "source_edge": "us-west",
        "target_edge": "us-east",
        "workloads": ["postgres-primary"],
        "strategy": "incremental",
        "priority": 9
    })

    # 4. Execute database migration
    workflow.add_node("EdgeMigrationNode", "exec_db", {
        "operation": "execute_migration"
    })

    # 5. Migrate application tier (staged)
    workflow.add_node("EdgeMigrationNode", "migrate_app", {
        "operation": "plan_migration",
        "source_edge": "us-west",
        "target_edge": "us-east",
        "workloads": ["api-service", "web-frontend"],
        "strategy": "staged",
        "priority": 8
    })

    # 6. Execute application migration
    workflow.add_node("EdgeMigrationNode", "exec_app", {
        "operation": "execute_migration"
    })

    # 7. Migrate cache layer (live)
    workflow.add_node("EdgeMigrationNode", "migrate_cache", {
        "operation": "plan_migration",
        "source_edge": "us-west",
        "target_edge": "us-east",
        "workloads": ["redis-cache"],
        "strategy": "live",
        "priority": 7
    })

    # 8. Execute cache migration
    workflow.add_node("EdgeMigrationNode", "exec_cache", {
        "operation": "execute_migration"
    })

    # 9. Final validation
    workflow.add_node("EdgeMonitoringNode", "validate", {
        "operation": "get_analytics",
        "edge_nodes": ["us-east"],
        "metrics": ["latency", "error_rate", "throughput"]
    })

    # 10. Get migration report
    workflow.add_node("EdgeMigrationNode", "report", {
        "operation": "get_metrics"
    })

    # Connect workflow
    workflow.add_connection("start_service", "status", "monitor", "input")
    workflow.add_connection("monitor", "status", "migrate_db", "input")
    # With shared state, migration_id is automatically accessible across nodes
    workflow.add_connection("migrate_db", "status", "exec_db", "input")
    workflow.add_connection("exec_db", "status", "migrate_app", "input")
    workflow.add_connection("migrate_app", "status", "exec_app", "input")
    workflow.add_connection("exec_app", "status", "migrate_cache", "input")
    workflow.add_connection("migrate_cache", "status", "exec_cache", "input")
    workflow.add_connection("exec_cache", "status", "validate", "input")
    workflow.add_connection("validate", "analytics", "report", "input")

    # Execute migration
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    # Check results
    print(f"Migration completed: {results['report']['metrics']}")
    return results

# Run the migration
if __name__ == "__main__":
    migrate_application_stack()
```

## Troubleshooting

### Common Issues

1. **Insufficient Capacity**
   - Check target edge resources
   - Scale up before migration
   - Use staged strategy

2. **Network Timeouts**
   - Reduce bandwidth limit
   - Increase checkpoint interval
   - Use compression

3. **Validation Failures**
   - Check workload compatibility
   - Verify data integrity
   - Test functionality before cutover

4. **Rollback Required**
   - Use checkpoint_id for specific point
   - Automatic rollback on critical errors
   - Manual intervention for complex cases

## See Also

- [Edge Computing Summary](EDGE_COMPUTING_SUMMARY.md) - Complete edge platform overview
- [Edge State Management Guide](edge-state-management-guide.md) - Lifecycle management
- [Edge Monitoring Guide](edge-monitoring-guide.md) - Observability integration
- [Edge Patterns](edge-patterns.md) - Common migration patterns
