---
name: nexus-comparison
description: "Nexus architecture and capabilities. Use when asking 'why nexus', 'nexus benefits', or 'nexus capabilities'."
---

# Nexus Architecture & Capabilities

## Nexus Capabilities

| Feature                  | Description                                           |
| ------------------------ | ----------------------------------------------------- |
| **API**                  | Built-in HTTP transport with auto-generated endpoints |
| **CLI**                  | Built-in CLI generation from registered workflows     |
| **MCP**                  | Built-in MCP server for AI agent integration          |
| **Session Management**   | Unified sessions across all channels                  |
| **Workflow Integration** | Native workflow execution via Core SDK                |
| **Auth Stack**           | Plugin-based authentication and authorization         |
| **Middleware**           | Extensible middleware pipeline                        |
| **Plugin System**        | Protocol-based plugin architecture                    |
| **Learning Curve**       | Low -- zero-config deployment                         |

## When to Use Nexus

- Need API + CLI + MCP from a single registration
- Want unified session management across channels
- Building AI agent integrations with MCP
- Want zero-configuration platform deployment
- Need middleware, auth, and rate limiting built in

## When NOT to Use Nexus

- Simple single-purpose workflows (use Core SDK directly)
- Database-first operations only (use DataFlow)
- Need fine-grained workflow control (use Core SDK)

## Key Benefits

1. **Zero boilerplate** -- one registration deploys all channels
2. **Unified sessions** -- same session across API/CLI/MCP
3. **Native workflows** -- direct Core SDK workflow execution
4. **Built-in CLI** -- automatic CLI generation
5. **MCP ready** -- AI agent integration out of the box
6. **Enterprise auth** -- plugin-based JWT, RBAC, tenant isolation
7. **Middleware support** -- extensible middleware pipeline
8. **Presets** -- one-line configuration for common deployment profiles

## Shared API

```
app = Nexus()
app.register("workflow-name", workflow.build())
app.handler("handler-name", handler_func)
app.add_plugin(auth_plugin)
app.add_middleware(middleware_class)
app.include_router(router)
app.health_check()
app.start()
```

All registration methods expose workflows on all three channels automatically.

See language-specific variant for complete deployment examples with imports and decorator patterns.

<!-- Trigger Keywords: why nexus, nexus benefits, nexus capabilities, nexus architecture -->
