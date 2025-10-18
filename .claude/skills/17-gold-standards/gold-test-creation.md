---
name: gold-test-creation
description: "Test creation standards with 3-tier strategy, fixtures, and real infrastructure requirements. Use when asking 'test standards', 'test creation', 'test guidelines', '3-tier testing', 'test requirements', or 'testing gold standard'."
---

# Gold Standard: Test Creation

Gold Standard: Test Creation guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `gold-standards`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Gold Standard: Test Creation
- **Category**: gold-standards
- **Priority**: HIGH
- **Trigger Keywords**: test standards, test creation, test guidelines, 3-tier testing, test requirements

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Gold Test Creation implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters
# Reference: sdk-users/2-core-concepts/cheatsheet/gold-test-creation.md

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```


## Common Use Cases

- **Gold-Test-Creation Core Functionality**: Primary operations and common patterns
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
- [`sdk-users/7-gold-standards/test_creation_guide.md`](../../../sdk-users/7-gold-standards/test_creation_guide.md)

## Quick Tips

- 💡 **Tip 1**: Always follow Gold Standard: Test Creation best practices
- 💡 **Tip 2**: Test patterns incrementally
- 💡 **Tip 3**: Reference documentation for details

## Keywords for Auto-Trigger

<!-- Trigger Keywords: test standards, test creation, test guidelines, 3-tier testing, test requirements -->
