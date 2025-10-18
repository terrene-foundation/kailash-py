---
name: switchnode-patterns
description: "Conditional data routing with SwitchNode using conditions and operators. Use when asking 'SwitchNode', 'conditional routing', 'if else workflow', 'route data', 'conditional logic', 'switch patterns', 'branch workflow', 'conditional flow', or 'routing patterns'."
---

# SwitchNode Conditional Routing

SwitchNode Conditional Routing guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `core-sdk`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: SwitchNode Conditional Routing
- **Category**: core-sdk
- **Priority**: HIGH
- **Trigger Keywords**: SwitchNode, conditional routing, if else workflow, route data, conditional logic

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Switchnode Patterns implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters
# Reference: sdk-users/2-core-concepts/cheatsheet/switchnode-patterns.md

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```


## Common Use Cases

- **Switchnode-Patterns Workflows**: Pre-built patterns for common use cases with best practices built-in
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
- [`sdk-users/2-core-concepts/cheatsheet/020-switchnode-conditional-routing.md`](../../../sdk-users/2-core-concepts/cheatsheet/020-switchnode-conditional-routing.md)

## Quick Tips

- 💡 **Tip 1**: Always follow SwitchNode Conditional Routing best practices
- 💡 **Tip 2**: Test patterns incrementally
- 💡 **Tip 3**: Reference documentation for details

## Keywords for Auto-Trigger

<!-- Trigger Keywords: SwitchNode, conditional routing, if else workflow, route data, conditional logic -->
