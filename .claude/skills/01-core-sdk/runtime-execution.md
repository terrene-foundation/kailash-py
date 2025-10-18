---
name: runtime-execution
description: "Execute workflows with LocalRuntime or AsyncLocalRuntime, with parameter overrides and configuration options. Use when asking 'execute workflow', 'runtime.execute', 'LocalRuntime', 'AsyncLocalRuntime', 'run workflow', 'execution options', 'runtime parameters', 'content-aware detection', or 'workflow execution'."
---

# Runtime Execution Options

Runtime Execution Options guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `core-sdk`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Runtime Execution Options
- **Category**: core-sdk
- **Priority**: HIGH
- **Trigger Keywords**: execute workflow, runtime.execute, LocalRuntime, AsyncLocalRuntime, run workflow

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Runtime Execution implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters
# Reference: sdk-users/2-core-concepts/cheatsheet/runtime-execution.md

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```


## Common Use Cases

- **Runtime-Execution Core Functionality**: Primary operations and common patterns
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
- [`sdk-users/2-core-concepts/cheatsheet/006-execution-options.md`](../../../sdk-users/2-core-concepts/cheatsheet/006-execution-options.md)
- [`CLAUDE.md#L106-137`](../../{doc})

## Quick Tips

- 💡 **Tip 1**: Always follow Runtime Execution Options best practices
- 💡 **Tip 2**: Test patterns incrementally
- 💡 **Tip 3**: Reference documentation for details

## Keywords for Auto-Trigger

<!-- Trigger Keywords: execute workflow, runtime.execute, LocalRuntime, AsyncLocalRuntime, run workflow -->
