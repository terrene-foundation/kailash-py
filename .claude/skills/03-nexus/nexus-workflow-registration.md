# Nexus Workflow Registration

Register workflows for multi-channel deployment (API + CLI + MCP) via a single call.

## Registration Methods

| Method                    | Use Case                    | Shared API |
| ------------------------- | --------------------------- | ---------- |
| `app.register(name, wf)`  | WorkflowBuilder workflows   | Yes        |
| `app.handler(name, func)` | Functions (imperative form) | Yes        |
| Handler decorator         | Functions (decorator form)  | Varies     |

## Workflow Registration (Shared API)

```
app = Nexus()

# Build workflow using Core SDK WorkflowBuilder
workflow = build_my_workflow()  # language-specific construction

# Register — name first, built workflow second
app.register("data-fetcher", workflow.build())

# Internally creates:
#   API  -> POST /workflows/data-fetcher/execute
#   CLI  -> nexus execute data-fetcher
#   MCP  -> tool workflow_data-fetcher
```

## Handler Registration (Shared API -- Imperative)

```
app = Nexus()
app.handler("process_order", process_order_func)
app.start()
```

The imperative `handler(name, func)` form works identically across all SDKs.

Decorator-style handler registration is also available but the exact signature varies by language. See language-specific variant for decorator syntax, description parameters, and tags.

## Critical Rules

```
# MUST call .build()
app.register("name", workflow.build())   # correct
app.register("name", workflow)           # WRONG — fails

# MUST use name-first parameter order
app.register(name, workflow.build())     # correct
app.register(workflow.build(), name)     # WRONG — reversed
```

## Auto-Discovery

Nexus can auto-discover workflows from the file system. Patterns vary by SDK.

```
app = Nexus(auto_discovery=True)   # default in some SDKs
app = Nexus(auto_discovery=False)  # recommended with DataFlow
```

**CRITICAL**: Use `auto_discovery=False` when integrating with DataFlow to prevent startup blocking.

## Dynamic Registration

### Configuration-Driven

Workflows can be registered from configuration files (YAML, JSON) by reading config, building workflows programmatically, and calling `app.register()` for each.

### Runtime Discovery

Modules can be loaded at runtime and their exported workflows registered via `app.register()`.

See language-specific variant for dynamic registration code examples.

## Versioning

Use versioned names for production deployments:

```
app.register("data-api:v1.0.0", workflow_v1.build())
app.register("data-api:v2.0.0", workflow_v2.build())
app.register("data-api:latest", workflow_v2.build())
app.register("data-api", workflow_v2.build())  # default = latest
```

## Quick Reference

**Registration flow**: a single `app.register()` or `app.handler()` call exposes the workflow on all channels automatically. No ChannelManager needed.

**Common fixes**:

- Workflow not found -> ensure `.build()` is called
- Auto-discovery blocks with DataFlow -> use `auto_discovery=False`
- Parameters reversed -> name first, workflow second

**Best practices**:

1. Use handlers for simple operations, WorkflowBuilder for complex multi-node workflows
2. Always call `.build()` before registration
3. Use `auto_discovery=False` when integrating with DataFlow
4. Use versioned names (`name:v1.0.0`) for production deployments

## Related Skills

- [nexus-handler-support](nexus-handler-support.md) - Handler patterns
- [nexus-dataflow-integration](nexus-dataflow-integration.md) - DataFlow workflow registration
- [nexus-production-deployment](nexus-production-deployment.md) - Production deployment patterns
- [nexus-troubleshooting](nexus-troubleshooting.md) - Fix registration issues
