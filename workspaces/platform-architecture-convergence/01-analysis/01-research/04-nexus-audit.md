# Nexus Primitive/Engine Audit — 2026-04-07

**Audit scope**: Verify Nexus primitive vs NexusEngine composition, and map MCP/Trust/PACT integration.

## Verdict: Engine Composes Primitive (Good) — But Nexus Duplicates Auth/Audit

NexusEngine is pure composition. However, Nexus itself implements its own auth, JWT, RBAC, rate limiting, audit, EATP headers, and session management — all of which **should consume `kailash.trust`** but don't. Nexus is ALSO missing PACT integration entirely.

## Primitive: `Nexus`

**Location**: `packages/kailash-nexus/src/nexus/core.py` (~1000 lines)

**Architecture**: Thin orchestration over Core SDK enterprise gateway. Wraps `create_gateway()` via `HTTPTransport`.

**Key dependencies** (Core SDK only):

```python
from kailash.runtime import AsyncLocalRuntime
from kailash.servers.gateway import create_gateway
from kailash.workflow import Workflow
from kailash.workflow.builder import WorkflowBuilder
from kailash.channels import ChannelConfig, ChannelType, MCPChannel
from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import APIKeyAuth
```

**Transports** (all unified in Core SDK):

- `HTTPTransport` — wraps `create_gateway()` (not duplicated)
- `MCPTransport` — pluggable MCP transport
- `WebSocketTransport`, `WebhookTransport`

**Public API**: `.register()`, `.start()`, `.create_session()`, `.include_router()`, `.add_middleware()`, `.add_transport()`, `.add_background_service()`, `.add_plugin()`

## Engine: `NexusEngine`

**Location**: `packages/kailash-nexus/src/nexus/engine.py` (220 lines)

**Composition confirmed** (line 174-182):

```python
class NexusEngine:
    def __init__(
        self,
        nexus: Nexus,  # ← REQUIRED, no default
        enterprise_config: Optional[EnterpriseMiddlewareConfig] = None,
        bind_addr: str = "0.0.0.0:3000",
    ):
        self._nexus = nexus
```

**Builder** (line 155):

```python
def build(self) -> NexusEngine:
    nexus = Nexus(**nexus_kwargs)  # Creates primitive
    return NexusEngine(nexus=nexus, ...)  # Wraps it
```

**Delegation**: `.register()`, `.start()` all delegate to `self._nexus`. Engine only adds middleware presets (NONE, SAAS, ENTERPRISE) and bind address.

**Verdict**: ✅ NexusEngine is pure composition — matches DataFlowEngine pattern.

## MCP Integration: GOOD (Not Duplicated)

- `nexus/mcp/` — DEPRECATED, removed old custom JSON server
- `nexus/trust/mcp_handler.py` — MCPEATPHandler for agent-to-agent trust (Nexus-specific)
- `nexus/transports/mcp.py` — MCPTransport wrapping Core SDK MCPServer
- `_initialize_mcp_server()` (core.py:560-800) — calls Core SDK's MCPServer

**Assessment**: Nexus no longer has its own MCP implementation. It composes Core SDK's MCPServer and adds Nexus-specific resources (system info, workflow discovery, config, help). Clean.

## Trust Integration: BAD (Major Duplication)

Nexus has an ENTIRE parallel auth/trust/audit stack that reimplements what `kailash.trust` provides.

### `nexus/trust/` (NOT consuming kailash.trust):

| File             | What It Duplicates                                                              |
| ---------------- | ------------------------------------------------------------------------------- |
| `headers.py`     | `EATPHeaderExtractor` — extracts EATP headers. Should use `kailash.trust`.      |
| `middleware.py`  | `TrustMiddleware` — ASGI middleware for trust verification.                     |
| `mcp_handler.py` | `MCPEATPHandler` — MCP + EATP trust bridge.                                     |
| `session.py`     | `SessionTrustContext`, `TrustContextPropagator` — parallel session trust model. |

### `nexus/auth/` (NOT consuming kailash.trust):

| File          | What It Duplicates                                                               |
| ------------- | -------------------------------------------------------------------------------- |
| `jwt.py`      | 25KB custom JWT implementation. kailash.trust has JWT.                           |
| `rbac.py`     | Custom RBAC with hierarchical roles + permission caching.                        |
| `rate_limit/` | Memory + Redis backends. Should use `kailash.trust.BudgetTracker` or equivalent. |
| `audit/`      | Logging, DataFlow, custom backends. Should use `kailash.trust.AuditStore`.       |
| `sso/`        | Google, Azure, GitHub, Apple OAuth.                                              |
| `tenant/`     | Multi-tenant context, resolver.                                                  |

**Grep result**: Zero `from kailash.trust import ...` in Nexus. Complete parallel implementation.

## PACT Integration: MISSING ENTIRELY

**Grep result**:

```
$ grep -r "pact\|PACT\|governance\|envelope\|operating" packages/kailash-nexus/src/nexus --include="*.py"
[no results]
```

- No imports of `kailash.trust.pact` or `kailash_pact`
- No governance envelope enforcement
- No multi-tenant operating envelope support (despite having an auth/tenant module)
- No constraint validation at request boundary
- No audit trail integration with PACT

**This is a major gap.** Multi-tenant deployments cannot enforce PACT operating envelopes (Financial, Operational, Temporal, Data Access, Communication constraints) at the request boundary.

## Session Management

**Current**: In-memory `SessionManager` (channels.py:247-305). Per-channel state, no persistent backend.

**Should use**: `kailash.trust.trust.session.TrustContextPropagator` which already exists with TTL support and multi-backend persistence.

## DurableWorkflowServer Bug (#175)

**Location**: `src/kailash/servers/durable_workflow_server.py` (Core SDK, not Nexus)

**Issue**: Dedup fingerprinting fails for POST requests — body extraction silently fails, all POSTs get identical fingerprints. Breaks chat, Q&A, non-idempotent workflows. Known workaround: `Nexus(enable_durability=False)`.

## Recommendations

### Must-fix for convergence:

1. **Consolidate auth/audit/rate-limit to `kailash.trust`**
   - Delete `nexus/auth/jwt.py`, `nexus/auth/rbac.py`, `nexus/auth/rate_limit/`, `nexus/auth/audit/`, `nexus/auth/sso/`
   - Move implementations to `kailash.trust.{jwt,rbac,rate_limit,audit,sso}` if not already there
   - Nexus re-exports for backward compat: `from kailash.trust.rbac import RBACManager`

2. **Consolidate EATP header extraction to `kailash.trust`**
   - Delete `nexus/trust/headers.py`, `nexus/trust/middleware.py`, `nexus/trust/session.py`
   - Use `kailash.trust.{headers, middleware, session}` directly

3. **Add PACT integration at Nexus request boundary**
   - New file: `nexus/middleware/governance.py`
   - `PACTMiddleware` class that extracts tenant from request, fetches operating envelope from `GovernanceEngine`, validates request, rejects with envelope reason if blocked
   - Wire into NexusEngine's middleware stack when enterprise config enables governance

4. **Unify session management with Trust**
   - Replace in-memory `SessionManager` with `TrustContextPropagator`
   - Gains persistence, TTL, multi-backend support

### Already correct (no action):

- NexusEngine composition pattern
- Transport layer (HTTPTransport, MCPTransport, WebSocketTransport, WebhookTransport)
- MCP server (uses Core SDK's MCPServer)
- Workflow registration / delegation to Core SDK runtime

### Unrelated bug:

- Fix #175 (DurableWorkflowServer POST deduplication) — investigate why `request.json()` fails in middleware chain. Independent of convergence but should be scheduled.

## Summary Table

| Component                    | Verdict        | Action                              |
| ---------------------------- | -------------- | ----------------------------------- |
| NexusEngine                  | COMPOSITION ✅ | None                                |
| HTTPTransport                | COMPOSITION ✅ | None                                |
| MCPTransport                 | UNIFIED ✅     | None                                |
| WebSocket/Webhook transports | UNIFIED ✅     | None                                |
| MCP server                   | COMPOSITION ✅ | None                                |
| Auth (JWT/RBAC/SSO)          | DUPLICATION ⚠️ | Migrate to kailash.trust            |
| Rate limiting                | DUPLICATION ⚠️ | Migrate to kailash.trust            |
| Audit logging                | DUPLICATION ⚠️ | Migrate to kailash.trust.AuditStore |
| EATP headers                 | DUPLICATION ⚠️ | Migrate to kailash.trust            |
| Session management           | DUPLICATION ⚠️ | Use TrustContextPropagator          |
| PACT integration             | MISSING ❌     | Build PACTMiddleware                |
| DurableWorkflowServer #175   | BUG            | Fix independently                   |
