# ADR-001: DataFlow Architecture - 100% Kailash SDK Integration

## Status

Accepted

## Context

Developers familiar with Django, Rails, and other web frameworks struggle with Kailash SDK's powerful but complex database infrastructure. They need:

- Zero-configuration development experience
- Production-grade quality without manual configuration
- Familiar patterns while leveraging Kailash's superior architecture
- Easy migration path from existing frameworks

## Decision

Build DataFlow as a thin orchestration layer that composes existing Kailash SDK components:

1. **Use WorkflowConnectionPool** for all database connections
   - Provides 50x capacity improvement over Django
   - Actor-based isolation prevents connection leaks
   - Built-in health monitoring and auto-recovery

2. **Extend AsyncSQLDatabaseNode** for model operations
   - Leverage existing query execution, validation, and pooling
   - Add model-specific query templates (11 nodes per model)
   - Include bulk operations: BulkCreateNode, BulkUpdateNode, BulkDeleteNode, BulkUpsertNode
   - Maintain full compatibility with Kailash workflows

3. **Use ResourceRegistry** for lifecycle management
   - Centralized resource tracking
   - Automatic cleanup and health checks
   - Production-ready from day one

4. **Leverage existing monitoring and transaction nodes**
   - TransactionMonitorNode for real-time monitoring
   - TransactionMetricsNode for performance tracking
   - PerformanceAnomalyNode for anomaly detection
   - DeadlockDetectorNode and RaceConditionDetectorNode for safety
   - DistributedTransactionManagerNode for complex workflows
   - TransactionContextNode for workflow-level coordination

5. **Use Kailash migration system**
   - MigrationRunner for execution
   - MigrationGenerator for creation
   - Full async support

## Consequences

### Positive

- No duplicate code - 100% reuse of battle-tested components
- Automatically inherits all Kailash improvements
- Consistent with SDK architecture patterns
- Easy to maintain and extend
- Production-ready features out of the box

### Negative

- Slight abstraction overhead (negligible in practice)
- Must maintain compatibility with underlying SDK changes
- Limited customization without SDK modifications

### Neutral

- Developers get familiar patterns with superior infrastructure
- Learning curve exists but is worthwhile for benefits gained

## Implementation Notes

### Component Mapping

```
DataFlow Component -> Kailash SDK Component
-----------------------------------------
Connection Management -> WorkflowConnectionPool
Query Execution -> AsyncSQLDatabaseNode
Resource Lifecycle -> ResourceRegistry
Monitoring -> TransactionMonitorNode, etc.
Configuration -> DatabaseConfig + Builders
Migrations -> MigrationRunner + Generator
Schema Management -> Adapted from AdminSchemaManager
```

### Key Design Principles

1. **Composition over inheritance** - Use SDK components as-is
2. **Configuration over code** - Leverage SDK's config system
3. **Convention over configuration** - Add sensible defaults
4. **Progressive disclosure** - Simple by default, powerful when needed

## References

- Kailash SDK architecture: # contrib (removed)/architecture/
- Django comparison: # contrib (removed)/architecture/analysis/kailash-vs-django-architecture.md
- Performance analysis: # contrib (removed)/architecture/perf/
