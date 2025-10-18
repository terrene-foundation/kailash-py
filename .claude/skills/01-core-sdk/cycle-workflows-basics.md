---
name: cycle-workflows-basics
description: "Create cyclic workflows with convergence criteria, iteration limits, and state management. Use when asking 'cyclic workflow', 'cycles', 'loops', 'iteration', 'convergence', 'max_iterations', 'cyclic patterns', 'workflow loops', 'iterative processing', or 'cycle basics'."
---

# Cyclic Workflows Basics

Cyclic Workflows Basics guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `core-sdk`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Cyclic Workflows Basics
- **Category**: core-sdk
- **Priority**: HIGH
- **Trigger Keywords**: cyclic workflow, cycles, loops, iteration, convergence, max_iterations

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Cycle Workflows Basics implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters
# Reference: sdk-users/2-core-concepts/cheatsheet/cycle-workflows-basics.md

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```


## Common Use Cases

- **Cycle-Workflows-Basics Workflows**: Pre-built patterns for common use cases with best practices built-in
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
- [`sdk-users/2-core-concepts/cheatsheet/019-cyclic-workflows-basics.md`](../../../sdk-users/2-core-concepts/cheatsheet/019-cyclic-workflows-basics.md)
- [`sdk-users/3-development/31-cyclic-workflows-guide.md`](../../../sdk-users/3-development/31-cyclic-workflows-guide.md)

## Quick Tips

- 💡 **Tip 1**: Always follow Cyclic Workflows Basics best practices
- 💡 **Tip 2**: Test patterns incrementally
- 💡 **Tip 3**: Reference documentation for details

## Keywords for Auto-Trigger

<!-- Trigger Keywords: cyclic workflow, cycles, loops, iteration, convergence, max_iterations -->
