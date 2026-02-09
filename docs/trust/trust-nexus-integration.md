# Nexus Trust Integration Guide

This guide explains how to use the EATP trust integration in Nexus for HTTP header extraction, trust middleware, MCP agent-to-agent delegation, and session trust propagation.

## Why Trust in Nexus?

Nexus is the multi-channel platform where agents communicate over HTTP and MCP. It is the entry point for trust context into the system:

- **Header extraction**: EATP trust context arrives as HTTP headers and must be parsed into structured objects
- **Request verification**: Middleware enforces trust requirements before requests reach application code
- **Agent-to-agent delegation**: MCP tool calls between agents carry EATP delegation context for accountability
- **Session persistence**: Trust context persists across the session lifecycle, surviving multiple workflow executions

## Quick Start

### Extract EATP Headers

```python
from nexus.trust import EATPHeaderExtractor

extractor = EATPHeaderExtractor()
context = extractor.extract(request.headers)

if context.is_valid():
    print(f"Request from agent: {context.agent_id}")
    print(f"Trace: {context.trace_id}")
```

### Add Trust Middleware

```python
from nexus.trust import TrustMiddleware, TrustMiddlewareConfig
from starlette.applications import Starlette

config = TrustMiddlewareConfig(
    mode="enforcing",
    exempt_paths=["/health", "/metrics"],
    require_human_origin=True,
)

app = Starlette(routes=routes)
app.add_middleware(TrustMiddleware, config=config)
```

### MCP Agent-to-Agent Calls

```python
from nexus.trust import MCPEATPHandler

handler = MCPEATPHandler()
context = await handler.prepare_mcp_call(
    calling_agent="agent-a",
    target_agent="agent-b",
    tool_name="search_documents",
    mcp_session_id="session-123",
)
is_valid = await handler.verify_mcp_response(context, response)
```

### Session Trust

```python
from nexus.trust import TrustContextPropagator, set_current_session_trust

propagator = TrustContextPropagator(default_ttl_hours=8.0)
session = await propagator.create_session(
    human_origin={"user_id": "user-123"},
    agent_id="agent-456",
)
set_current_session_trust(session)
```

## EATP Header Extraction (CARE-022)

The `EATPHeaderExtractor` parses EATP headers from HTTP requests into structured `ExtractedEATPContext` objects.

### EATP Header Specification

| Header                    | Type        | Description                     |
| ------------------------- | ----------- | ------------------------------- |
| `X-EATP-Trace-ID`         | String      | Unique request trace identifier |
| `X-EATP-Agent-ID`         | String      | Requesting agent identifier     |
| `X-EATP-Human-Origin`     | Base64 JSON | Human authorization info        |
| `X-EATP-Delegation-Chain` | CSV or JSON | Agent delegation path           |
| `X-EATP-Delegation-Depth` | Integer     | Depth in delegation tree        |
| `X-EATP-Constraints`      | Base64 JSON | Operation constraints           |
| `X-EATP-Session-ID`       | String      | Session identifier              |
| `X-EATP-Signature`        | String      | Cryptographic signature         |

### Extraction

```python
from nexus.trust import EATPHeaderExtractor, ExtractedEATPContext

extractor = EATPHeaderExtractor()

# From HTTP request headers
context = extractor.extract(request.headers)

# context.trace_id: str or None
# context.agent_id: str or None
# context.human_origin: dict or None (decoded from base64 JSON)
# context.delegation_chain: list of agent IDs
# context.delegation_depth: int or None
# context.constraints: dict or None (decoded from base64 JSON)
# context.session_id: str or None
# context.signature: str or None
# context.raw_headers: dict of all X-EATP-* headers
```

### Validation

```python
if context.is_valid():
    # Has both trace_id and agent_id
    pass

if context.has_human_origin():
    # Has decoded human_origin dict
    pass
```

### Forwarding Headers

Reconstruct headers for downstream services:

```python
headers = extractor.to_headers(context)
# Returns dict with X-EATP-* headers, base64-encoding JSON fields
```

### Case-Insensitive Matching

Headers are matched case-insensitively. `x-eatp-trace-id`, `X-EATP-Trace-ID`, and `X-EATP-TRACE-ID` all work.

### Malformed Header Handling

Malformed base64 or JSON in `Human-Origin` and `Constraints` headers is logged and set to `None` rather than raising exceptions. This prevents a single bad header from breaking the entire request.

## Trust Middleware (CARE-023)

The `TrustMiddleware` is ASGI middleware that verifies EATP trust context on incoming requests.

### Configuration

```python
from nexus.trust import TrustMiddleware, TrustMiddlewareConfig

config = TrustMiddlewareConfig(
    mode="enforcing",               # "disabled", "permissive", "enforcing"
    exempt_paths=["/health", "/metrics", "/docs"],
    require_human_origin=True,      # Require human in delegation chain
)
```

### Modes

| Mode         | Missing Headers | Failed Verification | Use Case                     |
| ------------ | --------------- | ------------------- | ---------------------------- |
| `disabled`   | Pass through    | Pass through        | Development, backward compat |
| `permissive` | Log, pass       | Log, pass           | Rollout, monitoring          |
| `enforcing`  | 401 response    | 403 response        | Production                   |

### HTTP Responses

- **401 Unauthorized**: Required EATP headers missing (enforcing mode)
- **403 Forbidden**: Trust verification failed (enforcing mode)
- **503 Service Unavailable**: Internal trust service error

### Exempt Paths

Paths in `exempt_paths` skip trust verification entirely. Use for health checks, metrics, and public endpoints:

```python
config = TrustMiddlewareConfig(
    mode="enforcing",
    exempt_paths=["/health", "/metrics", "/api/v1/public"],
)
```

### Integration with Starlette/FastAPI

```python
from starlette.applications import Starlette

app = Starlette(routes=routes)
app.add_middleware(TrustMiddleware, config=config)

# With optional TrustOperations backend (for Kaizen verification)
app.add_middleware(
    TrustMiddleware,
    config=config,
    trust_operations=trust_ops,
)
```

### Accessing Trust Context in Handlers

The middleware stores the extracted context in `request.state`:

```python
async def my_endpoint(request):
    eatp_context = getattr(request.state, "eatp_context", None)
    if eatp_context:
        print(f"Agent: {eatp_context.agent_id}")
        print(f"Trace: {eatp_context.trace_id}")
```

## MCP + EATP Agent-to-Agent (CARE-024)

The `MCPEATPHandler` manages trust delegation for agent-to-agent MCP tool calls.

### A2A Call Flow

```
Agent A                          MCPEATPHandler                    Agent B
   |                                  |                                |
   |-- prepare_mcp_call() ----------->|                                |
   |   (calling=A, target=B)          |-- verify permission            |
   |                                  |-- create delegation context    |
   |<-- MCPEATPContext ---------------|                                |
   |                                  |                                |
   |-- call tool with context --------|-------------------------------->|
   |                                  |                                |
   |<-- response ---------------------------------------------------- |
   |                                  |                                |
   |-- verify_mcp_response() -------->|                                |
   |   (context, response)            |-- validate + audit             |
   |<-- is_valid ---------------------|                                |
```

### Preparing a Call

```python
from nexus.trust import MCPEATPHandler, MCPEATPContext

handler = MCPEATPHandler()

context = await handler.prepare_mcp_call(
    calling_agent="agent-a",
    target_agent="agent-b",
    tool_name="search_documents",
    mcp_session_id="session-123",
    constraints={"data_scope": "department:finance"},
)

# context.eatp_trace_id: auto-generated trace ID
# context.delegation_id: unique delegation reference
# context.delegated_capabilities: ["search_documents"]
# context.constraints: inherited from caller
```

### Verifying a Response

```python
is_valid = await handler.verify_mcp_response(context, response_data)
# Validates the response and records it in the audit trail
```

### Audit Trail

```python
history = handler.get_call_history()
# List of dicts with: calling_agent, target_agent, tool_name, timestamp, etc.
```

### Safety Rules

- **Self-call rejection**: An agent cannot call itself (`calling_agent == target_agent` raises error)
- **Constraint inheritance**: Constraints from the calling agent are propagated to the target
- **Call history**: Every call is recorded for audit purposes

### With TrustOperations Backend

```python
handler = MCPEATPHandler(trust_operations=trust_ops)
# Delegations are created through the Kaizen trust backend
```

## Session Trust Propagation (CARE-025)

The `TrustContextPropagator` manages trust context across Nexus unified sessions.

### Session Lifecycle

```python
from nexus.trust import (
    TrustContextPropagator,
    SessionTrustContext,
    get_current_session_trust,
    set_current_session_trust,
)

propagator = TrustContextPropagator(default_ttl_hours=8.0)

# Create a session
session = await propagator.create_session(
    human_origin={"user_id": "user-123", "auth_method": "oauth2"},
    agent_id="agent-456",
    trace_id="trace-789",  # Optional, auto-generated if omitted
)

# session.session_id: "nxs-..." prefix
# session.human_origin: {"user_id": "user-123", ...}
# session.agent_id: "agent-456"
# session.is_active(): True
```

### ContextVar Thread Safety

Session trust is stored in a Python `ContextVar` for safe access across async code:

```python
# Set for current async context
set_current_session_trust(session)

# Retrieve anywhere in the same async context
current = get_current_session_trust()
if current and current.is_active():
    current.touch()  # Update last_active timestamp
    current.increment_workflow()  # Track workflow count
```

### Session Management

```python
# Get session by ID
session = await propagator.get_session_context(session_id)

# List all active sessions
active = await propagator.list_active_sessions()

# Revoke a specific session
await propagator.revoke_session(session_id, reason="User logout")

# Revoke all sessions for a human
await propagator.revoke_by_human(
    human_origin={"user_id": "user-123"},
    reason="Account suspended",
)

# Clean up expired sessions
removed = await propagator.cleanup_expired()
```

### Session Expiry

Sessions have a TTL (default 8 hours). Expired sessions are automatically denied:

```python
propagator = TrustContextPropagator(default_ttl_hours=2.0)
session = await propagator.create_session(
    human_origin={"user_id": "user-123"},
)

# After 2 hours:
session.is_expired()  # True
session.is_active()   # False
```

### Workflow Tracking

Sessions track how many workflows have been executed:

```python
session.increment_workflow()
print(session.workflow_count)  # 1
session.increment_workflow()
print(session.workflow_count)  # 2
```

## Architecture

```
HTTP Request
    |
    v
EATPHeaderExtractor (CARE-022)
    |  [parse X-EATP-* headers]
    v
TrustMiddleware (CARE-023)
    |  [verify trust, enforce mode]
    |  [store context in request.state]
    v
Application Handler
    |
    |-- Direct execution ---------> Runtime (with trust context)
    |
    |-- MCP call to other agent --> MCPEATPHandler (CARE-024)
    |                                   |  [prepare delegation]
    |                                   |  [verify response]
    |                                   v
    |                               Target Agent
    |
    v
TrustContextPropagator (CARE-025)
    |  [session creation/management]
    |  [ContextVar propagation]
    v
SessionTrustContext
    |  [tracks session lifecycle, workflow count, TTL]
```

## Integration with Core SDK and DataFlow

Nexus trust feeds into the Core SDK runtime trust system and DataFlow trust layer:

```python
from nexus.trust import EATPHeaderExtractor, TrustContextPropagator
from kailash.runtime.trust import RuntimeTrustContext
from kailash.runtime import LocalRuntime

# 1. Extract EATP headers at the HTTP boundary
extractor = EATPHeaderExtractor()
eatp_ctx = extractor.extract(request.headers)

# 2. Create runtime trust context for workflow execution
runtime_ctx = RuntimeTrustContext(
    trace_id=eatp_ctx.trace_id,
    delegation_chain=eatp_ctx.delegation_chain,
    constraints=eatp_ctx.constraints,
)

# 3. Execute workflow with trust context
runtime = LocalRuntime(
    trust_context=runtime_ctx,
    trust_verification_mode="enforcing",
)
results, run_id = runtime.execute(workflow.build())
```

## Testing

All Nexus trust modules work without external dependencies:

```python
from nexus.trust import EATPHeaderExtractor, TrustMiddlewareConfig

def test_header_extraction():
    extractor = EATPHeaderExtractor()
    context = extractor.extract({
        "X-EATP-Trace-ID": "trace-123",
        "X-EATP-Agent-ID": "agent-456",
    })
    assert context.is_valid()
    assert context.trace_id == "trace-123"

async def test_session_lifecycle():
    propagator = TrustContextPropagator(default_ttl_hours=1.0)
    session = await propagator.create_session(
        human_origin={"user_id": "user-123"},
    )
    assert session.is_active()
    await propagator.revoke_session(session.session_id)
    session = await propagator.get_session_context(session.session_id)
    assert not session.is_active()
```

## Test Coverage

| Component         | Tests         | Coverage                                           |
| ----------------- | ------------- | -------------------------------------------------- |
| Header Extraction | 22 tests      | Parsing, base64 JSON, edge cases, case-insensitive |
| Trust Middleware  | 22 tests      | All modes, exempt paths, human origin, error cases |
| MCP + EATP        | 26 tests      | A2A calls, delegation, verification, audit trail   |
| Session Trust     | 34 tests      | Lifecycle, TTL, ContextVar, revocation, cleanup    |
| **Total**         | **104 tests** | All passing                                        |
