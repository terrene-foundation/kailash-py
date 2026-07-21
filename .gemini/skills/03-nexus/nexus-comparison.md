---
name: nexus-comparison
description: "Nexus architecture and capabilities. Use when asking 'why nexus', 'nexus benefits', or 'nexus capabilities'."
---

# Nexus Architecture & Capabilities

> **Skill Metadata**
> Category: `nexus`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`

## Nexus Capabilities

| Feature | Nexus |
|---------|-------|
| **API** | Built-in HTTP transport |
| **CLI** | Built-in CLI generation |
| **MCP** | Built-in MCP server |
| **Session Management** | Unified across all channels |
| **Workflow Integration** | Native workflow execution |
| **Auth Stack** | NexusAuthPlugin (JWT, RBAC, tenant isolation) |
| **Learning Curve** | Low — zero-config deployment |

## When to Use Nexus

```python
# ✅ Use Nexus when you need:
# - API + CLI + MCP in one app
# - Session management across channels
# - Direct workflow execution
# - Minimal boilerplate

from nexus import Nexus

app = Nexus(workflow, name="MyApp")
app.run()  # All channels ready!
```

## Key Benefits

1. **Zero boilerplate** - One line deploys all channels
2. **Unified sessions** - Same session across API/CLI/MCP
3. **Native workflows** - Direct workflow execution
4. **Built-in CLI** - Automatic CLI generation
5. **MCP ready** - Claude Desktop integration
6. **Enterprise auth** - JWT, RBAC, tenant isolation via NexusAuthPlugin
7. **Middleware support** - Starlette-compatible middleware, router inclusion

## Deployment Example

```python
from nexus import Nexus

app = Nexus(auto_discovery=False)

@app.handler("chat", description="Chat endpoint")
async def chat(message: str) -> dict:
    # Build and execute workflow
    return {"response": "..."}

app.start()  # API + CLI + MCP!
```

## Documentation


<!-- Trigger Keywords: why nexus, nexus benefits, nexus capabilities, nexus architecture -->
