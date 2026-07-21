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
  The core engine for building trust-verified workflows with 140+ production-ready nodes, sync and async runtimes, cyclic workflow support, and the CARE/EATP cryptographic trust framework. Three application frameworks -- <a href="https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-kaizen">Kaizen</a> (AI agents), <a href="https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-nexus">Nexus</a> (multi-channel platform), and <a href="https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-dataflow">DataFlow</a> (database operations) -- are built on this foundation.
</p>

---

## Why Kailash?

- **Only workflow engine with cryptographic trust chains** -- CARE/EATP provides human-origin tracking, constraint propagation, trust verification, and RFC 3161 timestamped audit trails. No other framework has anything comparable.
- **140+ production-ready workflow nodes** -- AI, API, code execution, data, database, file, logic, monitoring, and transform nodes out of the box.
- **Production-grade durability** -- Real distributed transactions (saga + 2PC with pluggable transport), checkpoint-based workflow resume without duplicate side effects, persistent event store (SQLite WAL), dead letter queue with exponential backoff retry. 72 security findings resolved across 4 red team rounds.
- **Comprehensive observability** -- Prometheus `/metrics` endpoint, OpenTelemetry tracing with per-node spans, comprehensive execution audit trail (NODE_EXECUTED/FAILED events with inputs/outputs), WebSocket live dashboard, search attributes for cross-execution queries.
- **Workflow interaction** -- Send signals to running workflows (`SignalChannel`), query workflow state (`QueryRegistry`), pause/resume execution, cooperative cancellation, built-in scheduling (cron + interval), workflow versioning with semver registry, continue-as-new for infinite-duration workflows.
- **Scale-out ready** -- Distributed circuit breaker (Redis-backed with Lua atomic transitions), multi-worker task queue architecture, resource quotas with semaphore-based concurrency control, coordinated graceful shutdown, Kubernetes deployment manifests.
- **Progressive infrastructure** -- Start with zero config (SQLite), scale to multi-worker PostgreSQL/MySQL by changing environment variables. Dialect-portable SQL via QueryDialect strategy pattern. SQL task queue with `SKIP LOCKED`, worker heartbeat registry, exactly-once idempotent execution. No code changes between Level 0 (dev) and Level 2 (production).
- **Infrastructure-agnostic** -- `LocalRuntime` runs entirely in-process. No server cluster, no external database, no message broker. Deploy anywhere: any cloud, any region, on-prem, edge, air-gapped. Zero vendor lock-in.
- **Unified engine APIs** -- `DataFlowEngine.builder("sqlite:///app.db").build()` and `NexusEngine.builder().preset(Preset.SAAS).build()` provide fluent builder patterns with validation layers, data classification, query monitoring, and enterprise middleware. Cross-SDK parity.
- **Field-level validation and data classification** -- Declarative `@field_validator` and `@classify` decorators on DataFlow models. Built-in validators for email, URL, UUID, phone, length, range, pattern. Classification levels (PII, internal, public) with retention policies and masking strategies.
- **Organizational governance (PACT)** -- D/T/R accountability grammar, operating envelopes with monotonic tightening, knowledge clearance levels, verification gradient, and MCP tool governance. Governs AI agent organizations with fail-closed decisions and anti-self-modification defense.
- **Foundation for four application frameworks** -- [Kaizen](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-kaizen) (AI agents with trust), [Nexus](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-nexus) (multi-channel deploy), [DataFlow](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-dataflow) (zero-config database), and [PACT](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-pact) (organizational governance) are all built on this Core SDK.

---

## Architecture

```
+------------------------------------------------------------------+
|                    Application Frameworks                         |
|                                                                   |
|   Kaizen v2.40.0         Nexus v2.14.0       DataFlow v2.19.0    |
|   AI Agents              Multi-Channel        Zero-Config DB      |
|   CARE/EATP Trust        API + CLI + MCP      @db.model           |
|   Multi-Agent Coord.     Auth + RBAC          11 Nodes/Model      |
+------------------------------------------------------------------+
|                    Core SDK v2.59.0                                 |
|                                                                   |
|   140+ Nodes    |  WorkflowBuilder   |  Runtime (Sync + Async)   |
|   MCP Server    |  Cyclic Workflows  |  CARE Trust Layer          |
|                 |  Conditional Exec  |  Trust Verification        |
+------------------------------------------------------------------+
|                    Progressive Infrastructure                     |
|                                                                   |
|   QueryDialect  |  ConnectionManager |  StoreFactory (L0/L1/L2)  |
|   SQL TaskQueue |  WorkerRegistry    |  IdempotentExecutor        |
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
pip install kailash-pact       # Organizational governance (D/T/R)
pip install kailash-ml         # Classical + deep learning lifecycle
```

### `from_brief()` — natural language to running primitive

Every framework in the Kailash family exposes a `from_brief()` entry point that turns a natural-language description into a ready-to-use primitive instance. The brief is the user's intent in plain prose; the framework's Kaizen Signature does ALL the reasoning, and a validated typed plan is materialized into the primitive's canonical shape.

Five surfaces, one consistent pipeline (credential scrub → typed plan → confidence + allowlist gates → realize):

```python
# 1. Workflow.from_brief — synthesize a DAG of nodes from a brief
from kailash.workflow import Workflow

wf = Workflow.from_brief(
    "Summarize uploaded emails and route negative-sentiment ones to support."
)
runtime = LocalRuntime()
results, run_id = runtime.execute(wf.build())
```

```python
# 2. DataFlow.from_brief — synthesize @db.model classes from a brief
from dataflow import DataFlow

db = DataFlow.from_brief(
    "Customers have a name, email, and signup date. Tickets belong to a customer.",
    conn_str="sqlite:///app.db",
)
await db.initialize_deferred_migrations()
await db.express.create("Customer", {"id": 1, "name": "Alice", "email": "alice@example.com"})
```

```python
# 3. Kaizen.signature_from_brief — synthesize a Kaizen Signature subclass
from kaizen import Kaizen
from kaizen.core import BaseAgent

Sig = Kaizen.signature_from_brief(
    "Input: a customer support email. Output: a one-sentence summary and a "
    "priority label (urgent, high, normal, low)."
)
agent = BaseAgent(signature=Sig(), config={"model": os.environ["DEFAULT_LLM_MODEL"]})
```

```python
# 4. kailash.bootstrap — synthesize a Config object for the whole runtime
import kailash

cfg = kailash.bootstrap(
    "Use Postgres at localhost for storage and a local LLM via Ollama for summarization.",
    profile="dev",
)
# cfg.database_url, cfg.llm_model — all derived from the brief
```

```python
# 5. kailash_ml.from_brief — synthesize an ML training plan from brief + dataframe
import polars as pl
import kailash_ml

df = pl.DataFrame({
    "age": [25, 47, 33, 55, 29],
    "tenure_months": [12, 60, 24, 6, 36],
    "monthly_spend": [45.99, 120.50, 75.00, 30.00, 95.75],
    "churned": [0, 1, 0, 1, 0],
})
schema, model_spec, eval_spec = kailash_ml.from_brief(
    "Predict customer churn from account history.", df
)
# schema.field_names → feature columns the LLM picked from df.columns
# model_spec.model_class → classifier matching the prediction goal
# eval_spec.metrics → metrics matching the task type
```

#### Five-surface comparison — why some are `classmethod`, others module-level

The five `from_brief()` surfaces are NOT named inconsistently by accident. The verb form reflects what each call returns:

| Surface   | Entry point                          | Returns                                | Verb form                 | Why                                                                                       |
| --------- | ------------------------------------ | -------------------------------------- | ------------------------- | ----------------------------------------------------------------------------------------- |
| Workflow  | `Workflow.from_brief(brief)`         | `Workflow` instance                    | classmethod               | result IS a Workflow — `cls(...)` is the natural constructor                              |
| DataFlow  | `DataFlow.from_brief(brief, conn)`   | `DataFlow` instance                    | classmethod               | result IS a DataFlow — same naming convention                                             |
| Kaizen    | `Kaizen.signature_from_brief(brief)` | `Signature` SUBCLASS (not a Kaizen)    | classmethod (suffix verb) | result is a Signature, NOT a Kaizen — the `signature_` suffix tells you what you got back |
| Bootstrap | `kailash.bootstrap(brief, profile)`  | `Config` dataclass                     | module-level              | result is a Config, NOT a kailash module — module-level is the honest verb                |
| ML        | `kailash_ml.from_brief(brief, df)`   | `(FeatureSchema, ModelSpec, EvalSpec)` | module-level              | result is a triple of three independent dataclasses — module-level for the same reason    |

Rule of thumb: if the call returns an instance of the host class, it's a classmethod. If the call returns something else, the verb lives at module level so callers don't import-then-call something whose name lies about its return type.

#### Refining the ML schema — the `with_features` adapter

`kailash_ml.from_brief()` returns a **frozen + content-addressed** `FeatureSchema` (registry-keyable by content hash). End-users refining the schema MUST go through the `with_features()` adapter — direct mutation raises `FrozenInstanceError`:

```python
from kailash_ml.features.schema import FeatureField

# Add an engineered feature; with_features returns a NEW schema with
# version bumped + a fresh content hash.
refined = schema.with_features(
    list(schema.fields) + [
        FeatureField(
            name="monthly_spend",
            dtype="float64",
            description="Average monthly spend in dollars",
        )
    ]
)
# refined.version == schema.version + 1
# refined.content_hash != schema.content_hash  → registry treats it as a new row
```

The frozen-then-adapt pattern keeps the registry deterministic: two byte-identical schemas at the same version resolve to the same `content_hash`, so the registry deduplicates automatically. Mutable refinement would defeat this; the `with_features()` adapter is the structural alternative.

### Class-authoring entry points (still supported)

The class-authoring entry points are still supported for callers who already know their schema and want full control. The `from_brief()` surface is built on top of these — same primitives, different entry path.

```python
# Workflow — direct node wiring
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": "result = {'message': 'Hello from Kailash!'}"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

```python
# DataFlow — @db.model decorator
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: int
    name: str
    email: str
```

```python
# Kaizen — Signature subclassing
from kaizen.core import Signature, InputField, OutputField

class SummarizeSignature(Signature):
    """Summarize a piece of text into one sentence."""
    text: str = InputField(description="The text to summarize")
    summary: str = OutputField(description="One-sentence summary")
```

### Async runtime (Docker / FastAPI deployments)

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

Three application frameworks are built on Core SDK, each in its own package within this monorepo:

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

`pip install kailash-kaizen` | [Repository](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-kaizen) | [Documentation](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-kaizen#readme)

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

`pip install kailash-nexus` | [Repository](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-nexus) | [Documentation](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-nexus#readme)

### DataFlow: Zero-Config Database

One decorator generates 11 database operation nodes per model. Supports PostgreSQL, MySQL, and SQLite.

```python
from dataflow import DataFlow
from dataflow.core import FieldType

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: str
    name: str
    email: str

@db.model
class Document:
    id: str
    embedding: FieldType.Vector(1536)  # pgvector column on PostgreSQL, TEXT elsewhere

# Automatically generated:
# UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode,
# UserListNode, UserCountNode, UserUpsertNode,
# UserBulkCreateNode, UserBulkUpdateNode, UserBulkDeleteNode, UserBulkUpsertNode
```

`FieldType.Vector(dim)` is a parameterized embedding column type -- `vector(N)` via pgvector on PostgreSQL (with a documented `TEXT` fallback when the extension is off), `TEXT` on SQLite, `JSON` on MySQL. Values encode/decode through a canonical `[a,b,c]` codec that never emits scientific notation (small embedding magnitudes round-trip byte-identically) and fails closed on non-finite values or a malformed dimension.

`pip install kailash-dataflow` | [Repository](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-dataflow) | [Documentation](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-dataflow#readme)

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

## Key Features

### Core SDK (v2.59.0)

- **140+ production nodes**: AI, API, code execution, data, database, file, logic, monitoring, transform
- **Runtime parity**: `LocalRuntime` (sync) and `AsyncLocalRuntime` (async) with identical return structures
- **CARE trust layer**: RuntimeTrustContext, TrustVerifier, RuntimeAuditGenerator
- **Cyclic workflows**: CycleBuilder API with convergence detection
- **MCP integration**: Built-in Model Context Protocol server support
- **Conditional execution**: SwitchNode branching and skip patterns
- **Embeddable**: Runs in-process with no external dependencies
- **Performance optimized**: Cached topological sort, networkx removed from hot path, opt-in resource limits

### Ecosystem Frameworks

| Framework                                                                                        | Version | Key Capabilities                                                                                                                            |
| ------------------------------------------------------------------------------------------------ | ------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| [Kaizen](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-kaizen)     | v2.40.0 | Signature-based AI agents, multi-agent coordination, CARE/EATP trust, FallbackRouter, MCP sessions                                          |
| [Nexus](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-nexus)       | v2.14.0 | Multi-channel deploy (API+CLI+MCP), handler pattern, NexusAuthPlugin, presets, middleware API                                               |
| [DataFlow](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-dataflow) | v2.19.0 | 11 nodes per model, PostgreSQL/MySQL/SQLite parity, auto-wired multi-tenancy, async transactions, `FieldType.Vector(dim)` embedding columns |
| [MCP](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-mcp)           | v0.4.2  | Production-ready MCP client/server, transports (stdio/SSE/HTTP), service discovery                                                          |
| [PACT](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-pact)         | v0.16.1 | Governance — D/T/R addressing, envelopes, clearance, verification gradient                                                                  |
| [ML](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-ml)             | v2.2.2  | ML lifecycle — feature stores, model registry, AutoML, drift detection                                                                      |
| [Align](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-align)       | v0.7.4  | LLM fine-tuning + alignment (DPO/SFT/LoRA), GGUF export, Ollama/vLLM serving                                                                |

---

## Progressive Infrastructure

Start with zero config, scale to multi-worker by changing environment variables. No application code changes required.

| Level | What You Set                            | What You Get                                              |
| ----- | --------------------------------------- | --------------------------------------------------------- |
| **0** | Nothing                                 | SQLite stores, in-memory execution, single process        |
| **1** | `KAILASH_DATABASE_URL=postgresql://...` | All stores persist to PostgreSQL/MySQL, queryable history |
| **2** | + `KAILASH_QUEUE_URL=redis://...`       | Multi-worker parallel execution with task queue           |
| **3** | _(v1.1+)_                               | Leader election, distributed locks, global ordering       |

Full guide: [Progressive Infrastructure](docs/enterprise-infrastructure/01-overview.md) | Quick setup: [Multi-Worker Quickstart](docs/guides/multi-worker-quickstart.md)

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

## Delegate composition primitive (`kailash.delegate`) — Pre-Pledge v0

The Delegate primitive composes `(Connector x Signature x ConstraintEnvelope x Executor)` under EATP audit per the Terrene Delegate Specification v0. Apache 2.0 OSS, zero proprietary dependencies (per [issue #1035](https://github.com/terrene-foundation/kailash-py/issues/1035)).

### What the primitive enforces today (Wave 1-6 shipped)

Structural invariants — re-validated on every dispatch + execute path:

- **F5 monotonic envelope** — the bind-time envelope is the upper bound; runtime widening is BLOCKED, tightening is permitted.
- **Capability gating** — `connector.requires_capabilities ⊆ role.scope.capabilities`, snapshot at S5 `DispatchSurface` bind AND re-checked at S5 `dispatch()` entry per S5 C4-1; S6 `DelegateRuntime` delegates to S5.
- **Lifecycle gating** — `RoleLifecycleState ∈ {DRAFT, ACTIVE}` permits invocation; `SUSPENDED` and `RETIRED` refuse.
- **Tenant isolation** — `connector.tenant_id_observed` is cross-validated against the envelope's tenant scope; mismatch raises `CascadeTenantViolationError` and fails closed BEFORE the surface relays connector audit events.
- **§7 TAOD phase monotonicity** — `DelegateRuntime` is single-shot per receipt; re-execute on a consumed runtime raises `RuntimePhaseError`.
- **Audit binding** — every TAOD transition emits exactly one signed audit event with `run_id` binding. The signer is required at construction; placeholder signers are BLOCKED (cryptographic forgery defense per S5 C2-1).
- **Posture rotation audit** — `with_posture()` emits `POSTURE_OR_SOVEREIGN_HANDOVER` on the source runtime's audit engine BEFORE returning the new instance (S6 MED-1); rotations that cannot be audited are refused.
- **R2 composition** — `(envelope, cascade, dispatch_surface)` triplet identity + signer identity (`is`-check, not `==`) re-validated at every `execute()` start as defense-in-depth on top of the bind-time gate (S5 C4-1 + S6 Invariant 4).

Cross-implementation receipt evidence:

- 5 conformance vectors shipped as package data in `kailash/delegate/conformance/data/canonical.json` (DV-3-001, DV-5-001, DV-7-001, DV-9-001, DV-10-001), loaded via `ConformanceVectorLoader.load_canonical()`.
- 2 vectors (DV-5-001, DV-10-001) vendored byte-for-byte from the cross-SDK canonical per `cross-sdk-inspection.md` Rule 4a.
- `receipts_agree(rs, py)` cross-impl comparator with default timestamp-exclusion (`terminated_at`, `executed_at`, `started_at`, `signed_at`) and ordered comparison for chained data (`audit_chain_entries`, TAOD `transitions`).
- Vector tamper-detection on load — `ConformanceVectorIntegrityError` raises on hash-drift between the fixture's stored `digest` and a re-computed digest.

### What's deferred (follow-up issues against the #1035 umbrella)

- **§10 G1 principal-kind discrimination** ([issue #1143](https://github.com/terrene-foundation/kailash-py/issues/1143)): `DelegateIdentity` does not yet carry a `principal_kind` discriminator; `Role` does not carry `permitted_principal_kinds`. The DV-10-001 vector remains `xfail-strict` until this lands. Estimate: 80-150 LOC of load-bearing logic + 30-50 test updates (exceeded the S7 shard budget).
- **Concurrency contract** (reviewer A1, S6 deferred): concurrent `execute()` on shared substrate. Currently single-shot per `DelegateRuntime` instance (§7), so multi-execute proceeds through fresh runtimes — but `AuditChainEngine` concurrency-safety contract is not yet formally verified. Estimate: requires `AuditChainEngine` review out of delegate-primitive scope.
- **Posture state-file integration** (S6 deferred): `runtime.Posture` is a constructor parameter; integration with `.claude/learning/posture.json` SessionStart-managed state is operator-tooling scope, not primitive scope.

### What the primitive does NOT promise

- **Identity-cascade grantee registry persistence** — `TenantScopedCascade` is in-process and emits one `GrantMoment` per `cascade_child` call without retaining a grantee set. Durable registration is the caller's responsibility. The S5 dispatch validates against the S3 cascade contract, but the cascade itself is not durable.
- **Cryptographic nonce validation** — `with_posture(nonce=...)` is **syntactic** (min-length 16 chars). Cryptographic single-use, signed-by-authority, and expiry checks live in SessionStart / S8+ nonce-registry integration — NOT in the primitive.
- **Audit chain signature verification (forensic)** — `AuditChainEntry` stores per-event Ed25519 signatures, but the primitive does NOT bind signer keys to a public-key registry, fingerprint, or key-rotation epoch. A forensic investigator with only the chain bytes cannot verify signatures against an external attestation. Out-of-band identity-to-key binding is required; operators MUST provide their own attestation surface ([issue #1147](https://github.com/terrene-foundation/kailash-py/issues/1147)).
- **Connector trust** — the `Connector` ABC is the untrust boundary. The primitive validates structural contracts but does NOT sandbox connector execution. Apache 2.0 OSS does not include a sandbox.

### How to verify on your machine

```python
from kailash.delegate import (
    DelegateRuntime, DispatchSurface, Connector, ConnectorInvocationResult,
    DelegateIdentity, Role, RoleScope, CapabilitySet, RoleLifecycleState,
    DelegateConstraintEnvelope, TenantScope, TenantScopedCascade, GrantMoment,
    AuditChainEngine, DelegateEventType, Posture,
    ConformanceVectorLoader,
)

# Load the canonical conformance vectors
vectors = ConformanceVectorLoader.load_canonical()
print(f"{len(vectors)} vectors: {[v.vector_id for v in vectors]}")

# Full composition example: see tests/e2e/delegate/test_delegate_e2e_flows.py
# (Flow A through Flow G exercise every invariant in this pre-pledge against
# real substrate — no mocks of S2-S7 primitives).
```

### Status: pre-pledge

The primitive is **pre-pledge**: structurally complete, byte-shape-pinned against the cross-SDK canonical, deferral set disclosed. Not yet attested to PACT D/T/R compliance or third-party security audit. The post-pledge state requires:

- §10 G1 closure ([issue #1143](https://github.com/terrene-foundation/kailash-py/issues/1143))
- Independent PACT-class audit
- ≥1 production deployment with a non-Terrene operator

Until then, treat as "production-ready for non-adversarial workloads; pre-production for high-stakes adversarial workloads."

---

## Documentation

| Resource                                                                                                      | Description                                         |
| ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| [Kaizen Guide](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-kaizen#readme)     | AI agents, signatures, multi-modal, CARE/EATP trust |
| [Nexus Guide](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-nexus#readme)       | Multi-channel platform, auth, middleware, handlers  |
| [DataFlow Guide](https://github.com/terrene-foundation/kailash-py/tree/main/packages/kailash-dataflow#readme) | Database operations, models, queries, multi-tenancy |
| [Sphinx Docs](docs/)                                                                                          | Full API reference and guides                       |

---

## Contributing

```bash
# Clone and setup
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-py
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
  <a href="docs/">Documentation</a> |
  <a href="https://github.com/terrene-foundation/kailash-py">GitHub</a>
</p>
