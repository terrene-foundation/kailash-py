---
name: gold-parameter-passing
description: "Parameter passing standard with three methods, explicit parameter declaration, and enterprise security patterns. Use when asking 'parameter standard', 'parameter gold', 'parameter validation', 'parameter security', or 'parameter compliance'."
---

# Gold Standard: Parameter Passing

Gold Standard: Parameter Passing guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `gold-standards`
> Priority: `CRITICAL`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Gold Standard: Parameter Passing
- **Category**: gold-standards
- **Priority**: CRITICAL
- **Trigger Keywords**: parameter standard, parameter gold, parameter validation, parameter security

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Gold Parameter Passing implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters
# Reference: sdk-users/2-core-concepts/cheatsheet/gold-parameter-passing.md

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```


## Common Use Cases

- **Gold-Parameter-Passing Core Functionality**: Primary operations and common patterns
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
- [`sdk-users/7-gold-standards/parameter_passing_comprehensive.md`](../../../sdk-users/7-gold-standards/parameter_passing_comprehensive.md)

## Quick Tips

- 💡 **Tip 1**: Always follow Gold Standard: Parameter Passing best practices
- 💡 **Tip 2**: Test patterns incrementally
- 💡 **Tip 3**: Reference documentation for details

## Keywords for Auto-Trigger

<!-- Trigger Keywords: parameter standard, parameter gold, parameter validation, parameter security -->
