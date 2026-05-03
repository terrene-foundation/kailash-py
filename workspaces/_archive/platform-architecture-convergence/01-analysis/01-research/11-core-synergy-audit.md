# Core SDK + Cross-Framework Synergy Audit — 2026-04-07

**Audit scope**: Core SDK primitives, full cross-framework dependency matrix, composition flows.

## Core SDK Structure

**661 Python files in `src/kailash/`** across 22 categories.

### Submodules by size

| Module           | Files   | Purpose                                                         | Refactor Status     |
| ---------------- | ------- | --------------------------------------------------------------- | ------------------- |
| `trust`          | **193** | EATP, TrustPlane, PostureStore, BudgetTracker, chain-of-custody | FOUNDATIONAL — KEEP |
| `nodes`          | 145     | 140+ primitive nodes by category                                | CORE — KEEP         |
| `runtime`        | 53      | LocalRuntime, AsyncLocalRuntime, execution engines              | PRIMITIVE — KEEP    |
| `middleware`     | 40      | Gateway, auth, communication, MCP adapters                      | COMPOSITE — REVIEW  |
| `workflow`       | 33      | WorkflowBuilder, Workflow graph, validation                     | PRIMITIVE — KEEP    |
| `edge`           | 26      | Edge deployment, cloud integration                              | PERIPHERAL          |
| `mcp_server`     | 20      | **MCP protocol — EXTRACT to kailash-mcp**                       | EXTRACT             |
| `core`           | 16      | Actors, ML, monitoring, resilience                              | SUPPORT             |
| `infrastructure` | 11      | Queue, idempotency, event/checkpoint stores                     | SUPPORT             |
| `mcp`            | 10      | **Platform MCP integration — EXTRACT**                          | EXTRACT             |
| Others           | 105     | CLI, channels, visualization, testing                           | SUPPORT             |

### Public primitive API (from `kailash/__init__.py`)

```python
Node
NodeParameter
NodeMetadata
Workflow
WorkflowBuilder
LocalRuntime
NodeInstance
Connection
WorkflowVisualizer (lazy)
```

Plus `AsyncLocalRuntime` and 140+ nodes.

### Node categories (145 files, 22 categories)

| Category                                                                  | Count    | Notable                          |
| ------------------------------------------------------------------------- | -------- | -------------------------------- |
| `data`                                                                    | 22       | CSV, JSON, SQL, ETL, streaming   |
| `edge`                                                                    | 14       | Docker, K8s, cloud, scaling      |
| `monitoring`                                                              | 10       | Metrics, health, anomaly         |
| `admin`                                                                   | 8        | RBAC, audit logging, schema      |
| `transaction`                                                             | 8        | 2PC, sagas, DLT                  |
| `security`                                                                | 7        | Credentials, threat detection    |
| `auth`                                                                    | 6        | SSO, MFA, risk, sessions         |
| `api`                                                                     | 7        | REST, GraphQL, rate limit        |
| `enterprise`                                                              | 6        | MCP executor, custom logic       |
| `logic`                                                                   | 7        | Switch, loop, signal/wait, merge |
| `compliance`                                                              | 2        | GDPR, retention                  |
| `transform`, `cache`, `code`, `alerts`, `validation`, `testing`, `system` | 1-3 each |                                  |

## What's in Core SDK That Should Move Out

### HIGH PRIORITY: MCP separation (40+ files)

| Path                                  | Files | Action                                |
| ------------------------------------- | ----- | ------------------------------------- |
| `src/kailash/mcp_server/`             | 20    | Move to `packages/kailash-mcp/`       |
| `src/kailash/mcp/`                    | 10    | Move to `packages/kailash-mcp/`       |
| `src/kailash/api/mcp_integration.py`  | 1     | Move or DELETE (broken, no consumers) |
| `src/kailash/channels/mcp_channel.py` | 1     | Move to `packages/kailash-mcp/`       |
| `src/kailash/middleware/mcp/`         | 6     | Move with mcp_server/                 |

**After extraction**: `kailash` core shrinks by ~5K lines, MCP becomes optional via `kailash[mcp]` extra.

### MEDIUM PRIORITY: Trust embedded (193 files)

**Foundational components that SHOULD stay in Core**:

- Signing (crypto, rotation, CRL)
- Chain-of-custody (TrustLineageChain, AuditAnchor)
- PostureStore, BudgetTracker, BudgetStore
- EATP (esa/)
- TrustPlane (plane/)
- Interop (W3C VC, JWT, DID, UCAN, SD-JWT, Biscuit)

**Governance components (PACT)** — already mostly in `trust/pact/`:

- Engine, envelopes, config, compilation, audit

**Status**: Self-contained. No imports from workflow, nodes, or runtime. PACT could be extracted to `kailash-pact` as separate package while keeping EATP core, but the current embedding works fine (per PACT audit, the split is already correct).

### LOW PRIORITY: Edge module

`src/kailash/edge/` (26 files) — peripheral. Could be optional `kailash[edge]` extra. Not critical.

## Cross-Framework Dependency Matrix

### Critical finding: ZERO mandatory external framework imports in Core

```bash
$ grep -r "kailash_dataflow|kailash_nexus|kailash_kaizen|kaizen_agents|kailash_pact|kailash_ml|kailash_align" src/kailash/
src/kailash/mcp/contrib/kaizen.py: from kaizen_agents import Delegate
```

**Exactly ONE match**, and it's in the optional MCP contrib layer (a plugin).

**Conclusion**: **Core SDK has zero hard dependencies on any external framework.** It is architecturally independent and composition-ready. This is the GOOD news.

### Inverse imports (what Core imports from frameworks)

- **None at the primitive level**
- One optional contrib import in `mcp/contrib/kaizen.py`

### Framework-to-Core dependency table

| Framework          | Imports From Core                                                                  | Key Symbols                                                              |
| ------------------ | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `kailash-dataflow` | ✅ `Node`, `WorkflowBuilder`, `LocalRuntime`, `AsyncLocalRuntime`                  | Auto-generated CRUD nodes register as Nodes; queries via WorkflowBuilder |
| `kailash-nexus`    | ✅ `Workflow`, `LocalRuntime`/`AsyncLocalRuntime`, `create_gateway()`, `MCPServer` | Wraps Core SDK enterprise gateway; registers workflows as endpoints      |
| `kailash-kaizen`   | ✅ `Node`, `WorkflowBuilder`, `kailash.trust.pact`, `kailash.mcp_server.client`    | BaseAgent inherits Node; consumes PACT primitives                        |
| `kaizen-agents`    | ✅ `kailash.trust.pact.config`, `kailash.trust`                                    | GovernedSupervisor consumes PACT envelope config                         |
| `kailash-pact`     | ✅ Re-exports `kailash.trust.pact.*`                                               | Engine wraps GovernanceEngine primitive                                  |
| `kailash-ml`       | ✅ `kailash.db.connection.ConnectionManager`, `kailash.db.dialect`                 | Only Core SDK ConnectionManager                                          |
| `kailash-align`    | ⚠️ NONE                                                                            | Fully isolated from kailash framework                                    |

### Violations and circular dependencies

**Inverted dependencies (Primitives importing from Engines)**:

- **None found.** Core SDK correctly has no upward dependencies.

**Mutual imports**:

- **None found.** trust, workflow, nodes, runtime are all one-way or independent.

**Resolved cycles**:

- kailash-ml ↔ kailash-kaizen used to form a cycle → resolved via `kailash-ml-protocols` package, then eliminated when protocols moved into `kailash_ml/types.py`

## Shared Concept Duplication Map (the most important output)

| Concept                 | Implementations | Locations                                                                                                                                                                                                           | Action                                                 |
| ----------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| **MCP Client**          | 2               | `kailash.mcp_server.client.MCPClient` (1288 LOC), `kaizen_agents.delegate.mcp.McpClient` (509 LOC)                                                                                                                  | Consolidate to `kailash-mcp.MCPClient`                 |
| **MCP Server**          | 7+              | nexus/mcp, mcp_websocket, trust/plane/mcp, api/mcp_integration, channels/mcp_channel, mcp_server/, mcp/                                                                                                             | Server consolidation 85% done; finish in `kailash-mcp` |
| **LLM Provider**        | 2               | `kailash-kaizen/nodes/ai/ai_providers.py` (5001 LOC, 14 providers), `kaizen_agents/delegate/adapters/` (4 providers)                                                                                                | Merge into `kaizen/providers/` modular layout          |
| **Tool Registry**       | 2               | BaseAgent (JSON schemas), Delegate (callable executors)                                                                                                                                                             | Unified registry supporting both                       |
| **Constraint Envelope** | **3**           | `trust.chain.ConstraintEnvelope`, `trust.pact.envelopes.TaskEnvelope`, `trust.plane.models.ConstraintEnvelope`                                                                                                      | **CONSOLIDATE — EATP D6 violation**                    |
| **Budget Tracking**     | 2               | `trust.constraints.budget_tracker.BudgetTracker`, `trust.constraints.spend_tracker.AgentBudget`                                                                                                                     | Merge or clarify roles                                 |
| **Posture**             | 2               | `trust.posture.postures.TrustPosture` (state machine), `trust.agents.posture_agent.PostureAwareAgent` (wrapper)                                                                                                     | Separate concerns — OK                                 |
| **Audit Store**         | **5+**          | `trust.audit_store.AuditStore`, `trust.audit_service.AuditQueryService`, `trust.immutable_audit_log.ImmutableAuditLog`, `nodes.admin.audit_log.EnterpriseAuditLogNode`, `runtime.trust.audit.RuntimeAuditGenerator` | Consolidate to `trust.audit_store`                     |
| **AuditEvent**          | 3               | `trust.immutable_audit_log.AuditEntry`, `nodes.admin.audit_log.AuditEvent`, `runtime.trust.audit.AuditEvent`                                                                                                        | Use trust version                                      |
| **Data Classification** | 2               | `edge.compliance.DataClassification`, `nodes.compliance.data_retention.DataClassification`                                                                                                                          | Consolidate to `trust.constraints`                     |
| **Provider/Adapter**    | 6+              | `nodes.auth.enterprise_auth_provider`, `runtime.secret_provider`, `infrastructure.factory.ProviderFactory`, etc.                                                                                                    | Pattern scattered — create adapter factory             |
| **Registry**            | 7+              | `trust.registry.agent_registry`, `trust.esa.registry`, `infrastructure.worker_registry`, `resources.registry`, `mcp_server.ai_registry_server`, etc.                                                                | Consolidate to `trust.registry`                        |
| **Circuit Breaker**     | 2               | `trust.circuit_breaker.PostureCircuitBreaker`, `core.resilience.distributed_circuit_breaker.DistributedCircuitBreaker`                                                                                              | Consolidate                                            |

**Key insight**: The duplication is mostly within Core SDK itself (audit, registry, circuit breaker), not just across packages. Cleaning Core SDK eliminates the most duplications.

## PyO3 / Rust-Backed Features

**Finding**: No active imports of `kailash._kailash` in Core SDK code.

The `.so` file exists (`_kailash.cpython-312-darwin.so`) but is not actively used. References to `_kailash`:

- `_INSTRUMENTED_ATTR = "_kailash_otel_instrumented"` (internal marker, not PyO3)
- `export_to_kailash()` methods (metadata export, not PyO3 binding)

**Conclusion**: **PyO3 bindings are provisioned but dormant.** Either remove or activate.

## Composition Flows

### Working flows ✅

| Flow                                    | Status     | Path                                                |
| --------------------------------------- | ---------- | --------------------------------------------------- |
| Kaizen agent runs under PACT envelope   | ✅ Working | `PactEngine.execute(workflow, envelope)`            |
| Kaizen agent with Trust budget tracking | ✅ Working | `BudgetTracker` integrated in PACT execution        |
| Nexus deploys workflow + MCP + DataFlow | ✅ Working | `Nexus.register(workflow)` + middleware composition |
| TrustPlane MCP server                   | ✅ Working | FastMCP with TrustProject delegation                |

### Partial flows ⚠️

| Flow                                          | Status     | Issue                                                                                       |
| --------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------- |
| DataFlow audit → Trust AuditStore             | ⚠️ PARTIAL | `RuntimeAuditGenerator` logs node execution but no bridge to `trust.audit_store.AuditStore` |
| DataFlow validates against PACT schema        | ⚠️ PARTIAL | DataFlow models can reference `pact.envelopes` but no automatic integration                 |
| ML AutoML uses Kaizen agents in PACT envelope | ⚠️ UNKNOWN | Likely uses Delegate + envelope wrapping but not verified                                   |

### Broken flows ❌

| Flow                                                   | Status     | Cause                                                                                                 |
| ------------------------------------------------------ | ---------- | ----------------------------------------------------------------------------------------------------- |
| **Kaizen agent calls MCP tool**                        | ❌ BROKEN  | #339 — BaseAgent's MCP path strips server config, system prompt injects text-based ReAct instructions |
| **BaseAgent uses MCP tools**                           | ❌ BROKEN  | Same as above                                                                                         |
| **Delegate agent uses BaseAgent's structured outputs** | ❌ BROKEN  | Delegate has its own signature system, no conversion layer                                            |
| **Nexus enforces PACT operating envelopes**            | ❌ MISSING | Zero PACT integration in Nexus middleware                                                             |

## Refactor Priority Recommendations

### Priority 1: Extract MCP to separate package

**Scope**: 40+ files, ~5K lines
**Action**: Create `packages/kailash-mcp/`, move all MCP code, add `kailash[mcp]` extra
**Benefit**: Core SDK shrinks, MCP updates decouple from workflow changes

### Priority 2: Consolidate audit/budget/envelope

**Audit consolidation**:

- Single source: `trust.audit_store.AuditStore`
- `nodes.admin.audit_log` → uses trust.audit_store
- `runtime.trust.audit.RuntimeAuditGenerator` → emits to trust.audit_store
- `trust.immutable_audit_log` logic → folded into audit_store backends
- Single AuditEvent type, pluggable storage (SQLite, filesystem, S3)

**Budget consolidation**:

- `BudgetTracker` is primary
- `AgentBudget` is metadata wrapper → fold into BudgetTracker
- Document boundary clearly

**Envelope consolidation** (the EATP D6 violation):

- `chain.ConstraintEnvelope`
- `pact.TaskEnvelope`/`RoleEnvelope`/`SignedEnvelope`
- `plane.ConstraintEnvelope`
- Audit which is canonical, deprecate others or prove they're semantically different
- Restore cross-SDK semantic matching

### Priority 3: Create shared adapter factory

- Consolidate scattered provider/adapter implementations
- Single `kailash.adapters.factory.AdapterFactory` base
- Consistent discovery, registration, lifecycle

### Priority 4: PACT ownership clarification

- Current state ambiguous: `trust/pact/` is canonical (per audit #5)
- Remove `pact = ["kailash-pact>=0.8.0"]` extra OR clarify it's an optional re-export package
- Document that PACT primitives are core to trust plane

### Priority 5: Edge module separation

- Make `edge/` an optional import or extra
- `kailash[edge] = ["kailash-edge-ops>=X.Y"]`

### Priority 6: Fix broken composition flows

| Flow                               | Root Cause                     | Fix                                                                           |
| ---------------------------------- | ------------------------------ | ----------------------------------------------------------------------------- |
| BaseAgent + MCP tools              | No tool registry bridge        | After MCP extraction + Delegate convergence, BaseAgent uses unified MCPClient |
| BaseAgent vs Delegate signatures   | Incompatible Signature systems | After convergence, Delegate consumes BaseAgent's Signature → JSON schema      |
| DataFlow audit → trust.audit_store | No wiring                      | Instrument DataFlowEngine to emit AuditEvents to trust backend                |
| Nexus PACT enforcement             | Missing integration            | Build PACTMiddleware (per Nexus audit)                                        |

## Summary Health Table

| Dimension                 | Status        | Finding                                                                  |
| ------------------------- | ------------- | ------------------------------------------------------------------------ |
| **Primitive isolation**   | ✅ EXCELLENT  | Zero external framework imports. Core is pure primitive layer.           |
| **Duplication**           | ⚠️ MODERATE   | Audit (5+), Budget (2), Envelope (3), Provider patterns (6+) scattered   |
| **Circular dependencies** | ✅ EXCELLENT  | None detected. DAG is clean.                                             |
| **Framework composition** | ✅ GOOD       | Middleware bridges primitives and frameworks correctly                   |
| **Architectural clarity** | ⚠️ NEEDS WORK | PACT ownership ambiguous, MCP tightly coupled, edge/compliance scattered |
| **Optional dependencies** | ✅ GOOD       | Server, edge, secrets are lazy/optional. MCP is not (should be).         |
| **PyO3 integration**      | ❌ DORMANT    | Rust bindings provisioned but unused                                     |
| **Cross-SDK alignment**   | ⚠️ DIVERGENT  | Envelope proliferation breaks D6                                         |

## Critical Findings

1. **MCP is tightly bound to core** (40+ files): Extract to `kailash-mcp` package
2. **5+ audit implementations** make framework convergence impossible without consolidation
3. **No framework-to-framework imports** in Core SDK — architecture is sound at the primitive layer
4. **PACT/trust/pact boundary is ambiguous**: Document or formalize
5. **BaseAgent + MCP tool composition is broken** (#339): Blocks one of the key integration scenarios
6. **PyO3 bindings exist but unused**: Either remove or activate
7. **3 ConstraintEnvelope types**: EATP D6 semantic divergence within Python SDK
