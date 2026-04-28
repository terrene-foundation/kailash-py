---
name: admin-nodes-reference
description: "Quick reference for admin and utility nodes. Use when asking 'admin nodes', 'utility nodes', 'helper nodes', 'admin reference', or 'utility functions'."
---

# Admin Nodes Reference

Admin Nodes Reference guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `quick-reference`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Admin Nodes Reference
- **Category**: quick-reference
- **Priority**: HIGH
- **Trigger Keywords**: admin nodes, utility nodes, helper nodes, admin reference

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Admin Nodes Reference implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```


## Common Use Cases

- **System Health Monitoring**: HealthCheckNode for database/API connectivity, service availability checks
- **Operational Management**: Administrative tasks like cache clearing, configuration reloading, maintenance modes
- **Metrics Collection**: TransactionMetricsNode for performance monitoring, latency tracking, throughput analysis
- **Resource Management**: Connection pool management, memory optimization, resource cleanup operations
- **Debugging & Diagnostics**: Workflow state inspection, execution tracing, performance profiling

## Related Patterns

- **For fundamentals**: See [`workflow-quickstart`](#)
- **For patterns**: See [`workflow-patterns-library`](#)
- **For parameters**: See [`param-passing-quick`](#)

## When to Escalate to Subagent

Use specialized subagents when:
- **pattern-expert**: Complex patterns, multi-node workflows
- **testing-specialist**: Comprehensive testing strategies

## Documentation References

### Primary Sources

## Quick Tips

- 💡 **Tip 1**: Follow best practices from documentation
- 💡 **Tip 2**: Test patterns incrementally
- 💡 **Tip 3**: Reference examples for complex cases

## Keywords for Auto-Trigger

<!-- Trigger Keywords: admin nodes, utility nodes, helper nodes, admin reference -->
