---
name: decide-runtime
description: "Choose between LocalRuntime and AsyncLocalRuntime based on deployment context. Use when asking 'which runtime', 'LocalRuntime vs Async', 'runtime choice', 'sync vs async', 'runtime selection', or 'choose runtime'."
---

# Decision: Runtime Selection

Decision: Runtime Selection guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `cross-cutting`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Decision: Runtime Selection
- **Category**: cross-cutting
- **Priority**: HIGH
- **Trigger Keywords**: which runtime, LocalRuntime vs Async, runtime choice, sync vs async, runtime selection

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Decide Runtime implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters
# Reference: sdk-users/2-core-concepts/cheatsheet/decide-runtime.md

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```


## Common Use Cases

- **Decide-Runtime Core Functionality**: Primary operations and common patterns
- **Integration Patterns**: Connect with other nodes, workflows, external systems
- **Error Handling**: Robust error handling with retries, fallbacks, and logging
- **Performance**: Optimization techniques, caching, batch operations, async execution
- **Production Use**: Enterprise-grade patterns with monitoring, security, and reliability

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
- [`CLAUDE.md#L106-137`](../../{doc})

## Quick Tips

- 💡 **Tip 1**: Always follow Decision: Runtime Selection best practices
- 💡 **Tip 2**: Test patterns incrementally
- 💡 **Tip 3**: Reference documentation for details

## Keywords for Auto-Trigger

<!-- Trigger Keywords: which runtime, LocalRuntime vs Async, runtime choice, sync vs async, runtime selection -->
