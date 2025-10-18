---
name: gold-mocking-policy
description: "Testing policy requiring real infrastructure, no mocking for Tier 2-3 tests. Use when asking 'mocking policy', 'NO MOCKING', 'real infrastructure', 'test policy', 'mock guidelines', or 'testing standards'."
---

# Gold Standard: NO MOCKING Policy

Gold Standard: NO MOCKING Policy guide with patterns, examples, and best practices.

> **Skill Metadata**
> Category: `gold-standards`
> Priority: `CRITICAL`
> SDK Version: `0.9.25+`

## Quick Reference

- **Primary Use**: Gold Standard: NO MOCKING Policy
- **Category**: gold-standards
- **Priority**: CRITICAL
- **Trigger Keywords**: mocking policy, NO MOCKING, real infrastructure, test policy, mock guidelines

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Gold Mocking Policy implementation
workflow = WorkflowBuilder()

# See source documentation for specific node types and parameters
# Reference: sdk-users/2-core-concepts/cheatsheet/gold-mocking-policy.md

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```


## Common Use Cases

- **Gold-Mocking-Policy Core Functionality**: Primary operations and common patterns
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
- [`sdk-users/7-gold-standards/mock-directives-for-testing.md`](../../../sdk-users/7-gold-standards/mock-directives-for-testing.md)

## Quick Tips

- 💡 **Tip 1**: Always follow Gold Standard: NO MOCKING Policy best practices
- 💡 **Tip 2**: Test patterns incrementally
- 💡 **Tip 3**: Reference documentation for details

## Keywords for Auto-Trigger

<!-- Trigger Keywords: mocking policy, NO MOCKING, real infrastructure, test policy, mock guidelines -->
