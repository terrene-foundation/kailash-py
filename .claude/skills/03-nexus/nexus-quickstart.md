---
skill: nexus-quickstart
description: Zero-config Nexus() setup and basic workflow registration. Start here for all Nexus applications.
priority: CRITICAL
tags: [nexus, quickstart, zero-config, setup]
---

# Nexus Quickstart

Zero-configuration platform deployment. Get running in 30 seconds.

## Instant Start

```
from nexus import Nexus

app = Nexus()
app.start()
```

That creates:

- API Server on `http://localhost:8000`
- Health Check at `http://localhost:8000/health`
- MCP Server on port 3001

## Register a Workflow

```
app = Nexus()

# Build a workflow using the Core SDK WorkflowBuilder
workflow = create_workflow()  # language-specific — see variant

# Register once, available on all channels
app.register("fetch-data", workflow.build())  # MUST call .build()

app.start()
```

## Register a Handler

For simple operations, register a function directly instead of building a workflow:

```
app = Nexus()
app.handler("greet", greet_function)
app.start()
```

Decorator-style handler registration is also available in most SDKs. See language-specific variant for decorator syntax and signature details.

## Test All Three Channels

**API (HTTP)**:

```bash
curl -X POST http://localhost:8000/workflows/fetch-data/execute
```

**CLI**:

```bash
nexus run fetch-data
```

**MCP** (for AI agents):

```json
{
  "method": "tools/call",
  "params": { "name": "fetch-data", "arguments": {} }
}
```

## Critical Rules

### Always Call .build()

```
# CORRECT
app.register("workflow-name", workflow.build())

# WRONG — will fail
app.register("workflow-name", workflow)
```

### Correct Parameter Order

```
# CORRECT — name first, workflow second
app.register("name", workflow.build())

# WRONG — reversed
app.register(workflow.build(), "name")
```

## Common Issues

### Port Conflicts

```
app = Nexus(api_port=8001, mcp_port=3002)
```

### Workflow Not Found

Ensure `.build()` is called before passing the workflow to `register()`.

## Next Steps

- Register handlers: See [nexus-handler-support](nexus-handler-support.md)
- Registration patterns: See [nexus-workflow-registration](nexus-workflow-registration.md)
- Multiple channels: See [nexus-multi-channel](nexus-multi-channel.md)
- DataFlow integration: See [nexus-dataflow-integration](nexus-dataflow-integration.md)
- Authentication: See [nexus-auth-plugin](nexus-auth-plugin.md)

## Key Takeaways

- Zero configuration: `Nexus()` and go
- Always call `.build()` before registration
- Single registration creates API + CLI + MCP
- Default ports: 8000 (API), 3001 (MCP)
- Decorator patterns and route-style endpoints available (see language-specific variant)

See language-specific variant for complete code examples with imports, node types, and decorator patterns.
