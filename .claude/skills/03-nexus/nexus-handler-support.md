---
skill: nexus-handler-support
description: Register functions as multi-channel workflows using handler() or decorator patterns
priority: HIGH
tags: [nexus, handler, workflow, function]
---

# Nexus Handler Support

Register functions directly as multi-channel workflows, bypassing workflow-builder complexity for simple operations.

## When to Use Handlers

- Service orchestration (database, external APIs)
- Async operations
- Application module imports
- Full language access without sandbox restrictions
- Simple request/response patterns

## Shared API -- Imperative Registration

The imperative `handler(name, func)` form works identically across all SDKs:

```
app = Nexus()
app.handler("process_order", process_order_func)
app.start()
```

## Decorator Registration

Decorator-style handler registration is available in most SDKs but the exact syntax and parameters vary by language.

See language-specific variant for decorator syntax and complete examples.

## Parameter Handling

Handlers derive input parameters from the function signature:

| Concept             | Behavior                  |
| ------------------- | ------------------------- |
| Required parameters | No default value          |
| Optional parameters | Have a default value      |
| Type annotations    | Used for parameter typing |
| Return type         | Typically dict/map        |
| No annotation       | Defaults to string        |

Parameter type mapping details (how language types map to workflow parameter types) are language-specific. See variant.

## Core SDK: HandlerNode

For direct Core SDK usage without Nexus, the HandlerNode wraps functions as workflow nodes:

- Automatic parameter derivation from function signatures
- Type annotation mapping to NodeParameter entries
- Seamless WorkflowBuilder integration
- `make_handler_workflow()` utility builds single-node workflows from functions

See language-specific variant for HandlerNode API and usage examples.

## Handler vs WorkflowBuilder

| Aspect     | Handler                  | WorkflowBuilder         |
| ---------- | ------------------------ | ----------------------- |
| Complexity | Simple functions         | Multi-node pipelines    |
| Sandbox    | No restrictions          | Sandbox rules may apply |
| Parameters | Derived from signature   | Defined in node config  |
| Best for   | Service calls, CRUD, I/O | Complex data pipelines  |

## Best Practices

1. **Use handlers for service orchestration** -- they provide full language access
2. **Add type annotations** -- used for parameter derivation across all SDKs
3. **Return dictionaries/maps** -- non-dict returns are wrapped as `{"result": value}`
4. **Use async functions for I/O** -- sync functions run in executor/thread pool
5. **Add descriptions** -- appear in API docs and MCP tool discovery

## Related Skills

- [nexus-workflow-registration](nexus-workflow-registration.md) - All registration patterns
- [nexus-quickstart](nexus-quickstart.md) - Basic Nexus setup
- [nexus-dataflow-integration](nexus-dataflow-integration.md) - DataFlow integration

See language-specific variant for complete handler examples, decorator API, sandbox configuration, and migration patterns.
