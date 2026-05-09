---
skill: nexus-essential-patterns
description: Essential code patterns for Nexus setup, registration, DataFlow integration, middleware, and configuration
priority: HIGH
tags: [nexus, patterns, setup, handler, dataflow, middleware, configuration]
---

# Nexus Essential Patterns

Quick-reference for the most common Nexus operations using shared API.

## Basic Setup

```
app = Nexus()
app.register("workflow_name", workflow.build())  # ALWAYS .build()
app.start()
```

## Handler Registration

### Imperative (Shared API)

```
app = Nexus()
app.handler("process", process_func)
app.start()
```

### Decorator (Language-Specific)

Decorator-style handler registration is available in most SDKs. The exact syntax varies. See language-specific variant for decorator patterns.

**Why use handlers?**

- Bypasses sandbox restrictions on code nodes
- No import blocking (use any library)
- Automatic parameter derivation from function signature
- Multi-channel deployment (API/CLI/MCP) from single function

## DataFlow Integration (CRITICAL)

```
app = Nexus(auto_discovery=False)  # CRITICAL: prevents startup blocking
```

**WARNING**: Without `auto_discovery=False`, Nexus blocks on startup when DataFlow is present.

## Middleware & Plugin API

These APIs are shared across all SDKs:

```
# Add middleware
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Include existing routers
app.include_router(legacy_router, prefix="/legacy")

# Add plugins (NexusPlugin protocol)
app.add_plugin(auth_plugin)
```

## Presets

```
app = Nexus(preset="saas")
app = Nexus(preset="enterprise")
```

Presets apply one-line middleware stacks for common deployment profiles.

## Configuration Quick Reference

| Use Case          | Config                                             |
| ----------------- | -------------------------------------------------- |
| **With DataFlow** | `Nexus(auto_discovery=False)`                      |
| **Standalone**    | `Nexus()`                                          |
| **With Preset**   | `Nexus(preset="saas")`                             |
| **Custom Ports**  | `Nexus(api_port=8000, mcp_port=3001)`              |
| **Full Features** | `Nexus(auto_discovery=False)` + `add_plugin(auth)` |

## Connection Pattern (WorkflowBuilder)

```
# CORRECT: Explicit connections with dot notation
workflow.add_connection("prepare", "result.filters", "search", "filter")

# WRONG: Template syntax not supported
# "filter": "${prepare.result}"
```

## Health Check

```
health = app.health_check()
```

```bash
curl http://localhost:8000/health
```

## Key Rules

1. **Always call `.build()`** before registering workflows
2. **`auto_discovery=False`** when integrating with DataFlow
3. **Explicit connections** -- NOT template syntax `${...}`
4. **Test all three channels** (API, CLI, MCP) during development

See language-specific variant for decorator syntax, sandbox configuration, input mapping patterns, and complete code examples.
