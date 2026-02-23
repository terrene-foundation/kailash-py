# Kailash SDK

<p align="center">
  <a href="https://pypi.org/project/kailash/"><img src="https://img.shields.io/pypi/v/kailash.svg" alt="PyPI version"></a>
  <a href="https://pypi.org/project/kailash/"><img src="https://img.shields.io/pypi/pyversions/kailash.svg" alt="Python versions"></a>
  <a href="https://pepy.tech/project/kailash"><img src="https://static.pepy.tech/badge/kailash" alt="Downloads"></a>
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="Apache 2.0">
  <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
</p>

<p align="center">
  <strong>Enterprise Workflow Engine with Cryptographic Trust</strong>
</p>

<p align="center">
  The core engine for building trust-verified workflows with 140+ production-ready nodes, sync and async runtimes, cyclic workflow support, and the CARE/EATP cryptographic trust framework. Three application frameworks -- <a href="https://github.com/terrene-foundation/kailash-kaizen">Kaizen</a> (AI agents), <a href="https://github.com/terrene-foundation/kailash-nexus">Nexus</a> (multi-channel platform), and <a href="https://github.com/terrene-foundation/kailash-dataflow">DataFlow</a> (database operations) -- are built on this foundation.
</p>

---

## Why Kailash?

- **Only workflow engine with cryptographic trust chains** -- CARE/EATP provides human-origin tracking, constraint propagation, trust verification, and RFC 3161 timestamped audit trails. No other framework has anything comparable.
- **140+ production-ready workflow nodes** -- AI, API, code execution, data, database, file, logic, monitoring, and transform nodes out of the box.
- **Embeddable runtime with no external dependencies** -- `LocalRuntime` runs entirely in-process. No server cluster, no external database, no message broker. Works in CLI tools, serverless functions, and embedded applications.
- **Sync and async runtime parity** -- `LocalRuntime` and `AsyncLocalRuntime` share the same API and return identical `(results, run_id)` structures. Use sync for scripts, async for Docker/FastAPI.
- **Foundation for three application frameworks** -- [Kaizen](https://github.com/terrene-foundation/kailash-kaizen) (AI agents with trust), [Nexus](https://github.com/terrene-foundation/kailash-nexus) (multi-channel deploy), and [DataFlow](https://github.com/terrene-foundation/kailash-dataflow) (zero-config database) are all built on this Core SDK.

---

## Architecture

```
+------------------------------------------------------------------+
|                    Application Frameworks                         |
|                                                                   |
|   Kaizen v1.2.1          Nexus v1.4.1        DataFlow v0.12.1    |
|   AI Agents              Multi-Channel        Zero-Config DB      |
|   CARE/EATP Trust        API + CLI + MCP      @db.model           |
|   Multi-Agent Coord.     Auth + RBAC          11 Nodes/Model      |
+------------------------------------------------------------------+
|                    Core SDK v0.12.0                                |
|                                                                   |
|   140+ Nodes    |  WorkflowBuilder   |  Runtime (Sync + Async)   |
|   MCP Server    |  Cyclic Workflows  |  CARE Trust Layer          |
|                 |  Conditional Exec  |  Trust Verification        |
+------------------------------------------------------------------+
|                    Enterprise Capabilities                        |
|                                                                   |
|   RBAC + Auth   |  Audit Trails      |  Multi-Tenancy            |
|   Secret Mgmt   |  Resource Limits   |  Access Control            |
+------------------------------------------------------------------+
```

---

## Quick Start

### Installation

```bash
# Core SDK
pip install kailash

# Application frameworks (each includes Core SDK)
pip install kailash-kaizen     # AI agents with trust
pip install kailash-nexus      # Multi-channel platform (API + CLI + MCP)
pip install kailash-dataflow   # Zero-config database operations
```

### Workflow Orchestration

The Core SDK provides `WorkflowBuilder` and `LocalRuntime` for building and executing DAG-based workflows with 140+ built-in nodes.

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

Async runtime for Docker/FastAPI deployments:

```python
import asyncio
from kailash.runtime import AsyncLocalRuntime

async def main():
    runtime = AsyncLocalRuntime()
    results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})
    print(results)

asyncio.run(main())
# Or use `await` directly inside FastAPI route handlers
```

### Trust Verification (CARE/EATP)

Kailash is the only workflow engine with built-in cryptographic trust verification. Trust context propagates through all workflow execution automatically.

```python
from kailash.runtime.trust import (
    RuntimeTrustContext,
    TrustVerificationMode,
    runtime_trust_context,
)
from kailash.runtime import LocalRuntime

# Create a trust context with enforcing verification
ctx = RuntimeTrustContext(
    trace_id="audit-trace-2024-001",
    verification_mode=TrustVerificationMode.ENFORCING,
    delegation_chain=["human-operator-jane", "supervisor-agent", "worker-agent"],
    constraints={"max_tokens": 1000, "allowed_tools": ["read", "analyze"]},
)

# Trust context propagates through all workflow execution
with runtime_trust_context(ctx):
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

# Constraints can only be tightened (immutable pattern)
tighter_ctx = ctx.with_constraints({"allowed_tools": ["read"]})  # Removes "analyze"
node_ctx = ctx.with_node("data_processor")  # Tracks execution path
```

---

## Ecosystem Frameworks

Three application frameworks are built on Core SDK, each in its own repository:

### Kaizen: AI Agents with Cryptographic Trust

Production-ready AI agents with signature-based programming, multi-agent coordination, and the CARE/EATP trust framework.

```python
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from kaizen.api import Agent

async def main():
    model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")
    agent = Agent(model=model)
    result = await agent.run("Analyze this quarterly report for compliance risks")

asyncio.run(main())
```

`pip install kailash-kaizen` | [Repository](https://github.com/terrene-foundation/kailash-kaizen) | [Documentation](https://github.com/terrene-foundation/kailash-kaizen#readme)

### Nexus: Multi-Channel Platform

Write a function once. Deploy it as a REST API, CLI command, and MCP tool simultaneously.

```python
from nexus import Nexus

app = Nexus()

@app.handler("analyze", description="Analyze a document")
async def analyze(document: str, format: str = "summary") -> dict:
    return {"analysis": f"Analyzed '{document}' as {format}"}

app.start()
# REST API:  POST /workflows/analyze {"document": "report.pdf"}
# CLI:       nexus run analyze --document report.pdf
# MCP:       AI agents can call the 'analyze' tool directly
```

`pip install kailash-nexus` | [Repository](https://github.com/terrene-foundation/kailash-nexus) | [Documentation](https://github.com/terrene-foundation/kailash-nexus#readme)

### DataFlow: Zero-Config Database

One decorator generates 11 database operation nodes per model. Supports PostgreSQL, MySQL, and SQLite.

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: str
    name: str
    email: str

# Automatically generated:
# UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode,
# UserListNode, UserCountNode, UserUpsertNode,
# UserBulkCreateNode, UserBulkUpdateNode, UserBulkDeleteNode, UserBulkUpsertNode
```

`pip install kailash-dataflow` | [Repository](https://github.com/terrene-foundation/kailash-dataflow) | [Documentation](https://github.com/terrene-foundation/kailash-dataflow#readme)

---

## CARE Trust Framework

The **CARE** (Context, Action, Reasoning, Evidence) framework and **EATP** (Enterprise Agent Trust Protocol) are Core SDK features that provide:

- **Human origin tracking** -- trace every AI action back to the human who authorized it, across delegation chains
- **Constraint propagation** -- constraints can only be tightened as they flow through agent delegations, never loosened
- **Trust verification** -- three modes (disabled, permissive, enforcing) with cached verification and high-risk node awareness
- **EATP-compliant audit trails** -- every workflow start, node execution, trust verification, and resource access is recorded with RFC 3161 timestamps

Trust verification for workflows, nodes, and resources:

```python
from kailash.runtime.trust import TrustVerifier, TrustVerifierConfig

verifier = TrustVerifier(
    config=TrustVerifierConfig(
        mode="enforcing",
        high_risk_nodes=["BashCommand", "HttpRequest", "DatabaseQuery"],
    ),
)

# Verify before execution -- blocks unauthorized access in enforcing mode
result = await verifier.verify_workflow_access(
    workflow_id="financial-report-gen",
    agent_id="analyst-agent-42",
    trust_context=ctx,
)

if result.allowed:
    # Execute with full audit trail
    pass
```

---

## Competitive Positioning

Kailash occupies a unique position: it is both an embeddable workflow engine (no external services required) and a full AI agent platform with enterprise trust. No other tool combines these capabilities.

| Capability                             | Kailash        | Temporal | Airflow         | LangChain  | CrewAI     | Prefect      |
| -------------------------------------- | -------------- | -------- | --------------- | ---------- | ---------- | ------------ |
| **Cryptographic trust (CARE/EATP)**    | Yes            | No       | No              | No         | No         | No           |
| **AI agent framework**                 | Yes (Kaizen)   | No       | No              | Yes        | Yes        | No           |
| **Multi-channel deploy (API+CLI+MCP)** | Yes (Nexus)    | No       | No              | No         | No         | No           |
| **Embeddable (no server required)**    | Yes            | No       | No              | Yes        | Yes        | No           |
| **Auto-generated DB nodes**            | Yes (DataFlow) | No       | No              | No         | No         | No           |
| **Multi-agent coordination**           | Yes            | No       | No              | Partial    | Yes        | No           |
| **Enterprise auth (JWT/RBAC/SSO)**     | Built-in       | No       | Limited         | No         | No         | Cloud only   |
| **Multi-tenancy**                      | Built-in       | Limited  | Limited         | No         | No         | Cloud only   |
| **Audit trails**                       | EATP-compliant | No       | Limited         | LangSmith  | No         | Cloud only   |
| **DAG + cyclic workflows**             | Yes            | DAG only | DAG only        | Yes        | No         | DAG only     |
| **140+ built-in nodes**                | Yes            | No       | 2000+ operators | AI-focused | AI-focused | Task-focused |

> **Note:** Kailash and Temporal solve different problems. Temporal provides durable execution for long-running workflows that must survive process crashes. Kailash provides trust-aware orchestration for AI agent workflows. They are complementary, not competitive.

**Where each tool wins:**

- **Temporal** wins at durable execution with exactly-once semantics at massive scale (Uber, Netflix, Stripe). Choose Temporal for microservice orchestration where crash recovery is paramount.
- **Airflow** wins at batch ETL with its 2000+ community operators and managed cloud offerings (MWAA, Cloud Composer). Choose Airflow for scheduled data pipelines.
- **LangChain** wins at rapid AI prototyping with deep integrations across every LLM provider and vector database. Choose LangChain for quick AI experiments.
- **Kailash** wins at enterprise AI agents that require trust verification, compliance audit trails, and multi-channel deployment -- backed by a real workflow engine, not just prompt chains. Choose Kailash when your AI agents need to be auditable, trustworthy, and production-grade.

---

## Key Features

### Core SDK (v0.12.0)

- **140+ production nodes**: AI, API, code execution, data, database, file, logic, monitoring, transform
- **Runtime parity**: `LocalRuntime` (sync) and `AsyncLocalRuntime` (async) with identical return structures
- **CARE trust layer**: RuntimeTrustContext, TrustVerifier, RuntimeAuditGenerator
- **Cyclic workflows**: CycleBuilder API with convergence detection
- **MCP integration**: Built-in Model Context Protocol server support
- **Conditional execution**: SwitchNode branching and skip patterns
- **Embeddable**: Runs in-process with no external dependencies
- **Performance optimized**: Cached topological sort, networkx removed from hot path, opt-in resource limits

### Ecosystem Frameworks

| Framework                                                       | Version | Key Capabilities                                                                                   |
| --------------------------------------------------------------- | ------- | -------------------------------------------------------------------------------------------------- |
| [Kaizen](https://github.com/terrene-foundation/kailash-kaizen)     | v1.2.1  | Signature-based AI agents, multi-agent coordination, CARE/EATP trust, FallbackRouter, MCP sessions |
| [Nexus](https://github.com/terrene-foundation/kailash-nexus)       | v1.4.1  | Multi-channel deploy (API+CLI+MCP), handler pattern, NexusAuthPlugin, presets, middleware API      |
| [DataFlow](https://github.com/terrene-foundation/kailash-dataflow) | v0.12.1 | 11 nodes per model, PostgreSQL/MySQL/SQLite parity, auto-wired multi-tenancy, async transactions   |

---

## Testing

```bash
# Core SDK unit tests (7,800+ tests)
pytest tests/unit/ -m 'not (slow or integration or e2e)' --timeout=1

# Runtime parity tests
pytest tests/parity/ -v

# Integration tests (requires Docker for PostgreSQL/Redis)
pytest tests/integration/ --timeout=5

# End-to-end tests
pytest tests/e2e/ --timeout=10
```

**Testing policy**: Tier 1 (unit) allows mocking. Tier 2 (integration) and Tier 3 (E2E) require real infrastructure -- no mocking permitted.

---

## Documentation

| Resource                                                                     | Description                                         |
| ---------------------------------------------------------------------------- | --------------------------------------------------- |
| [SDK Users Guide](sdk-users/)                                                | Complete workflow development guide                 |
| [Kaizen Guide](https://github.com/terrene-foundation/kailash-kaizen#readme)     | AI agents, signatures, multi-modal, CARE/EATP trust |
| [Nexus Guide](https://github.com/terrene-foundation/kailash-nexus#readme)       | Multi-channel platform, auth, middleware, handlers  |
| [DataFlow Guide](https://github.com/terrene-foundation/kailash-dataflow#readme) | Database operations, models, queries, multi-tenancy |
| [Enterprise Patterns](sdk-users/5-enterprise/)                               | Production deployment patterns                      |
| [API Reference](https://terrene-foundation.github.io/kailash_sdk)               | Sphinx-generated API documentation                  |

---

## Contributing

```bash
# Clone and setup
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash_sdk
uv sync

# Run tests
pytest tests/unit/ -m 'not (slow or integration or e2e)' --timeout=1

# Code quality
black .
isort .
ruff check .
```

See [Contributing Guide](CONTRIBUTING.md) for details.

---

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
