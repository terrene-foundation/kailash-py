# Kailash Python SDK

<p align="center">
  <a href="https://pypi.org/project/kailash/"><img src="https://img.shields.io/pypi/v/kailash.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/kailash/"><img src="https://img.shields.io/pypi/pyversions/kailash.svg" alt="Python versions"></a>
  <a href="https://pepy.tech/project/kailash"><img src="https://static.pepy.tech/badge/kailash" alt="Downloads"></a>
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="Apache 2.0">
  <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
</p>

<p align="center">
  <strong>Enterprise-Grade Workflow Orchestration Platform</strong>
</p>

<p align="center">
  Build production-ready applications with zero-config database operations, multi-channel platforms, AI agents, and comprehensive workflow orchestration. From rapid prototyping to enterprise deployment.
</p>

---

## Latest Release: v0.11.0

**Core SDK v0.11.0** | **DataFlow v0.11.0** | **Nexus v1.3.0** | **Kaizen v1.1.0**

### What's New

- **Nexus v1.3.0**: Native middleware API, NexusAuthPlugin (JWT/RBAC/SSO/rate-limiting/tenant-isolation/audit), handler support (`@app.handler()`), preset system, CORS configuration
- **DataFlow v0.11.0**: `auto_migrate=True` works in Docker/FastAPI via SyncDDLExecutor, centralized logging with sensitive data masking, trust-aware features
- **Kaizen v1.1.0**: CARE framework (Context, Action, Reasoning, Evidence), EATP trust protocol, enhanced multi-agent coordination
- **Core SDK v0.11.0**: 115+ production nodes, runtime parity between sync/async

## Project Architecture

### Three-Layer Architecture

```
Application Frameworks (built ON Core SDK)
  DataFlow  |  Nexus  |  Kaizen
                |
         Core SDK Foundation
  115+ Nodes | Workflows | Runtime | MCP
```

### Project Structure

```
kailash_python_sdk/
├── src/kailash/          # Core SDK - 115+ nodes, workflows, runtime
├── apps/
│   ├── kailash-dataflow/ # Zero-config database framework (v0.11.0)
│   ├── kailash-nexus/    # Multi-channel platform (v1.3.0)
│   └── kailash-kaizen/   # AI agent framework (v1.1.0)
├── tests/                # 7,800+ core SDK tests
├── sdk-users/            # Complete user documentation
├── docs/                 # API reference (Sphinx)
└── scripts/              # Build and CI scripts
```

## Quick Start

### Installation

```bash
# Core SDK only
pip install kailash

# Application frameworks
pip install kailash-dataflow  # Zero-config database framework
pip install kailash-nexus     # Multi-channel platform (API + CLI + MCP)
pip install kailash-kaizen    # AI agent framework
```

### Core SDK: Workflow Orchestration

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": "result = {'message': 'Hello from Kailash!'}"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(results["process"]["result"])  # {'message': 'Hello from Kailash!'}
```

### DataFlow: Zero-Config Database Operations

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: str
    name: str
    email: str

# Automatic node generation: UserCreateNode, UserReadNode, UserUpdateNode,
# UserDeleteNode, UserListNode, UserCountNode, UserUpsertNode,
# UserBulkCreateNode, UserBulkUpdateNode, UserBulkDeleteNode, UserBulkUpsertNode
```

### Nexus: Multi-Channel Platform

```python
from nexus import Nexus

app = Nexus()

@app.handler("greet", description="Greeting handler")
async def greet(name: str, greeting: str = "Hello") -> dict:
    return {"message": f"{greeting}, {name}!"}

app.start()
# Now available as:
# - REST API: POST /workflows/greet {"name": "World"}
# - CLI: nexus run greet --name World
# - MCP: AI agents can call greet tool
```

### Nexus: Enterprise Auth

```python
import os
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig

auth = NexusAuthPlugin.basic_auth(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),  # >= 32 chars
)
app = Nexus()
app.add_plugin(auth)
app.start()
```

### Kaizen: AI Agents

```python
from kaizen.api import Agent

agent = Agent(model="gpt-4")
result = await agent.run("Analyze this document")
```

### Async Runtime (Docker/FastAPI)

```python
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

## Key Features

### Core SDK (v0.11.0)

- **115+ production nodes**: AI, API, Code, Data, Database, File, Logic, Monitoring, Transform
- **Runtime parity**: `LocalRuntime` (sync) and `AsyncLocalRuntime` (async) with identical APIs
- **Cyclic workflows**: CycleBuilder API with convergence detection
- **MCP integration**: Built-in Model Context Protocol server support
- **Conditional execution**: SwitchNode branching and skip patterns

### DataFlow (v0.11.0)

- **11 nodes per model**: Automatic CRUD, query, and bulk operation node generation
- **Multi-database**: PostgreSQL, MySQL, SQLite with full parity
- **Zero-config**: `auto_migrate=True` works everywhere including Docker/FastAPI
- **ExpressDataFlow**: ~23x faster direct CRUD via `db.express`
- **Enterprise migrations**: 8-component migration system with risk assessment

### Nexus (v1.3.0)

- **Multi-channel**: Single registration deploys to API + CLI + MCP simultaneously
- **Handler support**: `@app.handler()` bypasses PythonCodeNode sandbox restrictions
- **NexusAuthPlugin**: JWT, RBAC, SSO (GitHub/Google/Azure), rate limiting, tenant isolation, audit logging
- **Native middleware**: `app.add_middleware()`, `app.include_router()`, `app.add_plugin()`
- **Preset system**: none, lightweight, standard, saas, enterprise configurations

### Kaizen (v1.1.0)

- **Signature-based programming**: Declarative AI agent definitions
- **Multi-agent coordination**: Supervisor-worker, router, ensemble, pipeline patterns
- **CARE framework**: Context, Action, Reasoning, Evidence for structured AI responses
- **EATP trust protocol**: Enterprise Agent Trust Protocol for secure multi-agent systems

## Testing

### Test Suite

```bash
# Core SDK unit tests (7,800+ tests)
pytest tests/unit/ -m 'not (slow or integration or e2e)' --timeout=1

# Nexus tests (1,500+ tests)
pytest apps/kailash-nexus/tests/ -v

# Runtime parity tests
pytest tests/parity/ -v

# Integration tests (requires Docker for PostgreSQL/Redis)
pytest tests/integration/ --timeout=5

# End-to-end tests
pytest tests/e2e/ --timeout=10
```

### Testing Policy

- **Tier 1 (Unit)**: Mocking allowed, fast execution
- **Tier 2 (Integration)**: NO MOCKING - real database, real APIs
- **Tier 3 (E2E)**: NO MOCKING - real everything

## Documentation

### For Users

- **[SDK Users Guide](sdk-users/)**: Complete workflow development guide
- **[DataFlow Guide](sdk-users/apps/dataflow/)**: Database operations, models, queries
- **[Nexus Guide](sdk-users/apps/nexus/)**: Multi-channel platform deployment
- **[Kaizen Guide](sdk-users/apps/kaizen/)**: AI agent framework
- **[Enterprise Patterns](sdk-users/5-enterprise/)**: Production deployment patterns

### API Reference

- **[API Documentation](https://terrene-foundation.github.io/kailash-python-sdk)**: Sphinx-generated API reference

## Contributing

```bash
# Clone and setup
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-python-sdk
uv sync

# Run tests
pytest tests/unit/ -m 'not (slow or integration or e2e)' --timeout=1

# Code quality
black .
isort .
ruff check .
```

See [Contributing Guide](CONTRIBUTING.md) for details.

## License

This project is licensed under the **Apache License, Version 2.0**. You may use, modify, distribute, and commercialize the software freely, subject to the terms of the license.

See the [LICENSE](LICENSE) file for the full license text.

The Kailash SDK is the subject of patent applications owned by Terrene Foundation See the [PATENTS](PATENTS) file for details. Under Apache License 2.0, Section 3, each Contributor grants a patent license covering claims necessarily infringed by their Contribution(s) alone or by combination of their Contribution(s) with the Work, subject to the defensive termination clause in Section 3.

---

<p align="center">
  <a href="https://pypi.org/project/kailash/">Install from PyPI</a> |
  <a href="sdk-users/README.md">Documentation</a> |
  <a href="https://github.com/terrene-foundation/kailash-py">GitHub</a>
</p>
