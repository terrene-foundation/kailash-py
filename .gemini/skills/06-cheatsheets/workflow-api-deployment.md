---
name: workflow-api-deployment
description: "Deploy workflows as REST APIs using WorkflowAPI and Nexus. Use when asking 'workflow API', 'REST API', 'deploy API', 'WorkflowAPI', 'Nexus workflow', 'API deployment', or 'workflow endpoint'."
---

# Workflow API Deployment

Workflow API Deployment guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `deployment`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Workflow API Deployment
- **Category**: deployment
- **Priority**: HIGH
- **Trigger Keywords**: workflow API, REST API, deploy API, WorkflowAPI, Nexus workflow

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Workflow Api Deployment implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```


## Common Use Cases

- **Workflow-Api-Deployment Workflows**: Pre-built patterns for common use cases with best practices built-in
- **Composition Patterns**: Combine multiple workflows, create reusable sub-workflows, build complex orchestrations
- **Error Handling**: Built-in retry logic, fallback paths, compensation actions for resilient workflows
- **Performance Optimization**: Parallel execution, batch operations, async patterns for high-throughput processing
- **Production Readiness**: Health checks, monitoring, logging, metrics collection for enterprise deployments

## Related Patterns

- **For fundamentals**: See [`workflow-quickstart`](#)
- **For connections**: See [`connection-patterns`](#)
- **For parameters**: See [`param-passing-quick`](#)

## When to Escalate to Subagent

Use specialized subagents when:
- Complex implementation needed
- Production deployment required
- Deep analysis necessary
- Enterprise patterns needed

## Documentation References

### Primary Sources

## Quick Tips

- 💡 **Tip 1**: Always follow Workflow API Deployment best practices
- 💡 **Tip 2**: Test patterns incrementally
- 💡 **Tip 3**: Reference documentation for details

## Keywords for Auto-Trigger

<!-- Trigger Keywords: workflow API, REST API, deploy API, WorkflowAPI, Nexus workflow -->
