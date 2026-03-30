# Kailash Python SDK

**Enterprise Workflow Engine with Cryptographic Trust**

The full Kailash SDK in a single container — workflow orchestration, AI agents, database operations, multi-channel deployment, organizational governance, and the CARE/EATP trust framework.

[![PyPI version](https://img.shields.io/pypi/v/kailash.svg)](https://pypi.org/project/kailash/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/terrene-foundation/kailash-py/blob/main/LICENSE)

## Quick Start

```bash
# Interactive Python with the full SDK
docker run -it --rm terrenefoundation/kailash python

# Run a script
docker run --rm -v $(pwd):/app/work terrenefoundation/kailash python /app/work/my_workflow.py

# With environment variables (API keys, database URLs)
docker run --rm --env-file .env terrenefoundation/kailash python /app/work/main.py
```

## What's Included

This image bundles `kailash[all]` — every framework and optional dependency:

| Framework         | Version  | What It Does                                                                      |
| ----------------- | -------- | --------------------------------------------------------------------------------- |
| **Core SDK**      | 2.2.1    | 140+ workflow nodes, sync/async runtimes, cyclic workflows                        |
| **Kaizen**        | 2.3.1    | AI agents with signature-based programming and multi-agent coordination           |
| **kaizen-agents** | 0.5.0    | Delegate architecture for supervised agent execution                              |
| **DataFlow**      | 1.2.1    | Zero-config database operations — one decorator generates 11 CRUD nodes per model |
| **Nexus**         | 1.6.0    | Deploy as REST API + CLI + MCP tool simultaneously                                |
| **PACT**          | 0.4.1    | Organizational governance — D/T/R accountability, operating envelopes             |
| **Trust**         | included | CARE/EATP cryptographic trust chains, constraint propagation, audit trails        |

Plus: PostgreSQL/MySQL/SQLite drivers, Redis, Prometheus, OpenTelemetry, MCP, authentication, scheduling, and more.

## Example: Workflow Orchestration

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": "result = {'message': 'Hello from Kailash!'}"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
print(results["process"]["result"])
```

## Example: AI Agents

```python
import asyncio, os
from kaizen.api import Agent

async def main():
    agent = Agent(model=os.environ["DEFAULT_LLM_MODEL"])
    result = await agent.run("Analyze this report for compliance risks")

asyncio.run(main())
```

## Example: Zero-Config Database

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: str
    name: str
    email: str

# Auto-generates: CreateUser, ReadUser, UpdateUser, DeleteUser,
# ListUser, CountUser, UpsertUser, BulkCreate/Update/Delete/Upsert
```

## Docker Compose

Use with the full development stack (PostgreSQL, Redis, monitoring):

```yaml
services:
  app:
    image: terrenefoundation/kailash:latest
    env_file: .env
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: kailash
      POSTGRES_USER: kailash
      POSTGRES_PASSWORD: kailash
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

## Image Details

- **Base**: `python:3.12-slim`
- **User**: `kailash` (UID 1000, non-root)
- **Working directory**: `/app`
- **Platforms**: `linux/amd64`, `linux/arm64`
- **Python**: 3.12
- **License**: Apache 2.0

## Tags

- `latest` — latest stable release
- `X.Y.Z` — specific version (e.g., `2.2.1`)

## Links

- [GitHub Repository](https://github.com/terrene-foundation/kailash-py)
- [PyPI Package](https://pypi.org/project/kailash/)
- [Changelog](https://github.com/terrene-foundation/kailash-py/blob/main/CHANGELOG.md)
- [Terrene Foundation](https://terrene.dev)

## License

Apache License 2.0 — Terrene Foundation (Singapore CLG)
