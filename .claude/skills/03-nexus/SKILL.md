---
name: nexus
description: "Kailash Nexus: API+CLI+MCP platform. Use for workflow deploy, sessions, K8s probes, OpenAPI, CSRF, security headers."
---

# Kailash Nexus - Multi-Channel Platform Framework

Nexus is a zero-config multi-channel platform built on Kailash Core SDK that deploys workflows as API + CLI + MCP simultaneously.

## When to Use

Use Nexus when asking about Nexus, multi-channel, platform deployment, API deployment, CLI deployment, MCP deployment, unified sessions, workflow deployment, production deployment, API gateway, FastAPI alternative, session management, health monitoring, enterprise platform, plugins, event system, or workflow registration. Also covers K8s integration: K8s probes, healthz, readyz, startup probe, `ProbeManager`, `ProbeState`, OpenAPI, `openapi.json`, `OpenApiGenerator`, security headers, CSRF middleware, `CSRFMiddleware`, `SecurityHeadersMiddleware`, middleware presets, `Preset`, and HSTS.

## Features

Nexus transforms workflows into a complete platform with:

- **Zero Configuration**: Deploy workflows instantly without boilerplate code
- **Multi-Channel Access**: API, CLI, and MCP from single deployment
- **Unified Sessions**: Consistent session management across all channels
- **Enterprise Features**: Health monitoring, plugins, event system, comprehensive logging
- **DataFlow Integration**: Automatic CRUD API generation from database models
- **Production Ready**: Deployment patterns, monitoring, troubleshooting guides
- **FastAPI Alternative**: Workflow-based platform without manual route definition
- **Async-First**: Uses AsyncLocalRuntime by default for optimal performance

## Quick Start

```python
from nexus import Nexus

# Define workflow
workflow = create_my_workflow()

# Deploy to all channels at once
app = Nexus()
app.register("my_workflow", workflow.build())
app.start()

# Now available via:
# - HTTP API: POST http://localhost:8000/api/workflow/{workflow_id}
# - CLI: nexus run {workflow_id} --input '{"key": "value"}'
# - MCP: Connect via MCP client (Claude Desktop, etc.)
```

## Reference Documentation

### Getting Started

- **[nexus-quickstart](nexus-quickstart.md)** - Quick start guide
- **[nexus-installation](nexus-installation.md)** - Installation and setup
- **[nexus-architecture](nexus-architecture.md)** - Architecture overview
- **[README](README.md)** - Framework overview
- **[nexus-comparison](nexus-comparison.md)** - Nexus vs FastAPI/Flask

### Core Concepts

- **[nexus-workflow-registration](nexus-workflow-registration.md)** - Registering workflows
- **[nexus-multi-channel](nexus-multi-channel.md)** - Multi-channel architecture
- **[nexus-sessions](nexus-sessions.md)** - Session management
- **[nexus-config-options](nexus-config-options.md)** - Configuration options

### Channel-Specific Patterns

- **[nexus-api-patterns](nexus-api-patterns.md)** - HTTP API patterns
- **[nexus-api-input-mapping](nexus-api-input-mapping.md)** - API input handling
- **[nexus-cli-patterns](nexus-cli-patterns.md)** - CLI usage patterns
- **[nexus-mcp-channel](nexus-mcp-channel.md)** - MCP channel configuration

### Integration

- **[nexus-dataflow-integration](nexus-dataflow-integration.md)** - DataFlow + Nexus patterns
- **[nexus-plugins](nexus-plugins.md)** - Plugin system
- **[nexus-event-system](nexus-event-system.md)** - Event-driven architecture

### Production & Operations

- **[nexus-production-deployment](nexus-production-deployment.md)** - Production deployment
- **[nexus-health-monitoring](nexus-health-monitoring.md)** - Health checks and monitoring
- **[nexus-enterprise-features](nexus-enterprise-features.md)** - Enterprise capabilities
- **[nexus-troubleshooting](nexus-troubleshooting.md)** - Common issues and solutions

### v1.3.0 Additions

- **[nexus-handler-support](nexus-handler-support.md)** - `@app.handler()` decorator for direct function registration
- **[nexus-auth-plugin](nexus-auth-plugin.md)** - NexusAuthPlugin unified auth (JWT, RBAC, SSO, rate limiting, tenant, audit)
- **[golden-patterns-catalog](golden-patterns-catalog.md)** - Top 7 production-validated codegen patterns
- **[codegen-decision-tree](codegen-decision-tree.md)** - Decision tree, anti-patterns, scaffolding templates

### M1 ML Integration (`nexus.ml`)

The `nexus.ml` module wires kailash-ml dashboards and serving handles onto a Nexus app: `MLDashboard(auth="nexus")` reuses Nexus's validator adapter and contextvars, and `mount_ml_endpoints(nexus, serve_handle)` registers REST + MCP + WebSocket routes in one call. Live on branch `feat/kailash-ml-1.0.0-m1-foundations` (landed in `60081fed`). For ML-specific behavior, use skill **34-kailash-ml** as the authority.

## Key Concepts

### Zero-Config Platform

Nexus eliminates boilerplate:

- **No FastAPI routes** - Automatic API generation from workflows
- **No CLI arg parsing** - Automatic CLI creation
- **No MCP server setup** - Automatic MCP integration
- **Unified deployment** - One command for all channels

### Multi-Channel Architecture

Single deployment, three access methods:

1. **HTTP API**: RESTful JSON endpoints
2. **CLI**: Command-line interface
3. **MCP**: Model Context Protocol server

### Unified Sessions

Consistent session management:

- Cross-channel session tracking
- Session state persistence
- Session-scoped workflows
- Concurrent session support

### Enterprise Features

Production-ready capabilities:

- Health monitoring endpoints
- Plugin system for extensibility
- Event system for integrations
- Comprehensive logging and metrics
- Correct channel initialization flow
- Proper workflow registration

## When to Use This Skill

Use Nexus when you need to:

- Deploy workflows as production platforms
- Provide multiple access methods (API/CLI/MCP)
- Build enterprise platforms quickly
- Auto-generate CRUD APIs (with DataFlow)
- Replace FastAPI/Flask with workflow-based platform
- Create multi-channel applications
- Deploy AI agent platforms (with Kaizen)

## Integration Patterns

### With DataFlow (Auto CRUD API)

```python
from nexus import Nexus
from dataflow import DataFlow

# Define models
db = DataFlow(...)
@db.model
class User:
    id: str
    name: str

# Auto-generates CRUD endpoints for all models
app = Nexus()
for name, wf in db.get_workflows().items():
    app.register(name, wf)
app.start()

# GET  /api/User/list
# POST /api/User/create
# GET  /api/User/read/{id}
# PUT  /api/User/update/{id}
# DELETE /api/User/delete/{id}
```

### With Kaizen (Agent Platform)

```python
from nexus import Nexus
from kaizen.core.base_agent import BaseAgent

# Deploy agents via all channels
agent_workflow = create_agent_workflow()
app = Nexus()
app.register("agent", agent_workflow.build())
app.start()

# Agents accessible via API, CLI, and MCP
```

### With Core SDK (Custom Workflows)

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Deploy custom workflows
app = Nexus()
app.register("workflow_1", create_workflow_1().build())
app.register("workflow_2", create_workflow_2().build())
app.register("workflow_3", create_workflow_3().build())
app.start()
```

### Standalone Platform

```python
from nexus import Nexus

# Complete platform from workflows
app = Nexus()
app.register("workflow_a", workflow_a.build())
app.register("workflow_b", workflow_b.build())
app.start()
```

## Critical Rules

- ✅ Use Nexus instead of FastAPI for workflow platforms
- ✅ Register workflows, not individual routes
- ✅ Leverage unified sessions across channels
- ✅ Enable health monitoring in production
- ✅ Use plugins for custom behavior
- ✅ Nexus uses AsyncLocalRuntime by default (correct for Docker)
- ❌ NEVER mix FastAPI routes with Nexus
- ❌ NEVER implement manual API/CLI/MCP servers when Nexus can do it
- ❌ NEVER skip health checks in production

## Deployment Patterns

### Development

```python
app = Nexus()
app.register("my_workflow", workflow.build())
app.start()  # Single process, hot reload
```

### Production (Docker)

```python
from nexus import Nexus

app = Nexus()
app.register("my_workflow", workflow.build())
app.start()  # Uses AsyncLocalRuntime by default (correct for Docker)
```

### With Load Balancer

```bash
# Deploy multiple Nexus instances behind nginx/traefik
docker-compose up --scale nexus=3
```

## Channel Comparison

| Feature       | API  | CLI       | MCP         |
| ------------- | ---- | --------- | ----------- |
| **Access**    | HTTP | Terminal  | MCP Clients |
| **Input**     | JSON | Args/JSON | Structured  |
| **Output**    | JSON | Text/JSON | Structured  |
| **Sessions**  | ✓    | ✓         | ✓           |
| **Auth**      | ✓    | ✓         | ✓           |
| **Streaming** | ✓    | ✓         | ✓           |

## Related Skills

- **[01-core-sdk](../../01-core-sdk/SKILL.md)** - Core workflow patterns
- **[02-dataflow](../dataflow/SKILL.md)** - Auto CRUD API generation
- **[04-kaizen](../kaizen/SKILL.md)** - AI agent deployment
- **[05-kailash-mcp](../05-kailash-mcp/SKILL.md)** - MCP channel details
- **[17-gold-standards](../../17-gold-standards/SKILL.md)** - Best practices

## Support

For Nexus-specific questions, invoke:

- `nexus-specialist` - Nexus implementation and deployment
- `release-specialist` - Production deployment patterns
- `decide-framework` skill - When to use Nexus vs other approaches
