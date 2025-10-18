---
name: param-passing-quick
description: "Three methods of parameter passing in Kailash SDK: node configuration, workflow connections, and runtime parameters. Use when asking 'parameter passing', 'pass parameters', 'runtime parameters', 'node config', 'how to pass data', '3 methods', 'parameter methods', 'node parameters', or 'workflow parameters'."
---

# Parameter Passing - Three Methods

Complete guide to the three methods of passing parameters to nodes in Kailash SDK workflows.

> **Skill Metadata**
> Category: `core-sdk`
> Priority: `CRITICAL`
> SDK Version: `0.7.0+`
> Related Skills: [`workflow-quickstart`](workflow-quickstart.md), [`connection-patterns`](connection-patterns.md), [`error-parameter-validation`](../../5-cross-cutti../15-error-troubleshooting/error-parameter-validation.md)
> Related Subagents: `pattern-expert` (complex parameter patterns)

## Quick Reference

**Three Methods** (in order of reliability):
1. **Node Configuration** (Static) - Most reliable ⭐⭐⭐⭐⭐
2. **Workflow Connections** (Dynamic) - Most reliable ⭐⭐⭐⭐⭐
3. **Runtime Parameters** (Override) - Has edge case ⭐⭐⭐

**CRITICAL**: Every required parameter must come from one of these methods or the workflow fails at build time.

## Core Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Method 1: Node Configuration (static values)
workflow.add_node("EmailNode", "send", {
    "to": "user@example.com",  # Static parameter
    "subject": "Welcome"
})

# Method 2: Workflow Connection (dynamic from another node)
workflow.add_node("UserLookupNode", "lookup", {"user_id": 123})
workflow.add_connection("lookup", "email", "send", "to")  # Override static value

# Method 3: Runtime Parameter (override at execution)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "send": {"to": "override@example.com"}  # Override both config and connection
})
```

## The Three Methods Explained

### Method 1: Node Configuration (Static)
**Use when**: Values known at design time

```python
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com",  # All parameters in config
    "active": True
})
```

**Advantages**:
- Most reliable
- Clear and explicit
- Easy to debug
- Ideal for testing

### Method 2: Workflow Connections (Dynamic)
**Use when**: Values come from other nodes

```python
# Source node
workflow.add_node("FormDataNode", "form", {})

# Target node
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"
    # 'email' will come from connection
})

# Connect data flow
workflow.add_connection("form", "email_field", "create", "email")
```

**Advantages**:
- Dynamic data flow
- Loose coupling
- Enables pipelines
- Natural for transformations

### Method 3: Runtime Parameters (Override)
**Use when**: Values determined at execution time

```python
workflow.add_node("ReportNode", "generate", {
    "template": "monthly"
    # 'start_date' and 'end_date' from runtime
})

runtime.execute(workflow.build(), parameters={
    "generate": {
        "start_date": "2025-01-01",
        "end_date": "2025-01-31"
    }
})
```

**⚠️ Edge Case Warning**:
Fails when ALL conditions met:
- Empty node config `{}`
- All parameters optional
- No connections provide parameters

**Fix**: Provide minimal config: `{"_init": True}`

## Common Mistakes

### ❌ Mistake: Missing Required Parameter
```python
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"
    # ERROR: Missing required 'email'!
})
```

### ✅ Fix: Use One of Three Methods
```python
# Method 1: Add to config
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})

# OR Method 2: Connect from another node
workflow.add_connection("form", "email", "create", "email")

# OR Method 3: Provide at runtime
runtime.execute(workflow.build(), parameters={
    "create": {"email": "alice@example.com"}
})
```

## Related Patterns

- **For connections**: [`connection-patterns`](connection-patterns.md)
- **For workflow creation**: [`workflow-quickstart`](workflow-quickstart.md)
- **For parameter errors**: [`error-parameter-validation`](../../5-cross-cutti../15-error-troubleshooting/error-parameter-validation.md)
- **Gold standard**: [`gold-parameter-passing`](../../17-gold-standards/gold-parameter-passing.md)

## When to Escalate to Subagent

Use `pattern-expert` when:
- Complex parameter flow across many nodes
- Custom node parameter validation
- Enterprise parameter governance
- Advanced parameter patterns

## Documentation References

### Primary Sources
- **Parameter Guide**: [`sdk-users/3-development/parameter-passing-guide.md`](../../../sdk-users/3-development/parameter-passing-guide.md)
- **Gold Standard**: [`sdk-users/7-gold-standards/parameter_passing_comprehensive.md`](../../../sdk-users/7-gold-standards/parameter_passing_comprehensive.md)

### Related Documentation
- **Common Mistakes**: [`sdk-users/2-core-concepts/validation/common-mistakes.md` (lines 24-51)](../../../sdk-users/2-core-concepts/validation/common-mistakes.md#L24-L51)

## Quick Tips

- 💡 **Method 1 for tests**: Most reliable and deterministic
- 💡 **Method 2 for pipelines**: Natural for data flows
- 💡 **Method 3 for user input**: Dynamic values at runtime
- 💡 **Combine methods**: You can use all three together
- 💡 **Avoid edge case**: Never use empty config `{}` with all optional params

## Version Notes

- **v0.7.0+**: Strict parameter validation enforced (security feature)
- **v0.6.0+**: Three methods established as standard pattern

<!-- Trigger Keywords: parameter passing, pass parameters, runtime parameters, node config, how to pass data, 3 methods, parameter methods, node parameters, workflow parameters, parameter flow, provide parameters -->
