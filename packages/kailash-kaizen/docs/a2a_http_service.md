# A2A HTTP Service

The A2A (Agent-to-Agent) HTTP Service provides a FastAPI-based implementation of the A2A protocol with EATP trust extensions for secure agent-to-agent communication.

## Overview

The A2A HTTP Service enables agents to:
- Expose their identity and capabilities via Agent Cards
- Handle JSON-RPC 2.0 method calls from other agents
- Authenticate requests using JWT tokens with trust chain verification
- Verify, delegate, and audit trust relationships via standard methods

## Quick Start

```python
from kaizen.trust import (
    TrustOperations,
    TrustKeyManager,
    OrganizationalAuthorityRegistry,
    PostgresTrustStore,
    generate_keypair,
)
from kaizen.trust.a2a import A2AService, create_a2a_app

# Initialize trust infrastructure
store = PostgresTrustStore()
registry = OrganizationalAuthorityRegistry()
key_manager = TrustKeyManager()
trust_ops = TrustOperations(registry, key_manager, store)

# Generate agent keys
private_key, public_key = generate_keypair()

# Create A2A service
service = A2AService(
    trust_operations=trust_ops,
    agent_id="agent-001",
    agent_name="Data Analyzer",
    agent_version="1.0.0",
    private_key=private_key,
    capabilities=["analyze", "report", "summarize"],
    description="AI agent for data analysis",
    base_url="https://agent.example.com",
)

# Get FastAPI app
app = service.create_app()

# Run with uvicorn
# uvicorn app:app --host 0.0.0.0 --port 8000
```

Or use the convenience function:

```python
app = create_a2a_app(
    trust_operations=trust_ops,
    agent_id="agent-001",
    agent_name="Data Analyzer",
    agent_version="1.0.0",
    private_key=private_key,
    capabilities=["analyze", "report"],
)
```

## Endpoints

### Agent Card: `GET /.well-known/agent.json`

Returns the agent's public identity including capabilities and EATP trust extensions.

**Response:**
```json
{
  "agent_id": "agent-001",
  "name": "Data Analyzer",
  "version": "1.0.0",
  "description": "AI agent for data analysis",
  "capabilities": [
    {"name": "analyze", "description": "Attested capability: ACCESS"}
  ],
  "protocols": ["a2a/1.0", "eatp/1.0"],
  "endpoint": "https://agent.example.com/a2a/jsonrpc",
  "trust": {
    "trust_chain_hash": "abc123...",
    "genesis_authority_id": "org-acme",
    "genesis_authority_type": "ORGANIZATION",
    "verification_endpoint": "https://agent.example.com/a2a/jsonrpc",
    "delegation_endpoint": "https://agent.example.com/a2a/jsonrpc",
    "capabilities_attested": ["analyze"]
  }
}
```

**Caching:** Supports ETag-based caching with `If-None-Match` header.

### JSON-RPC: `POST /a2a/jsonrpc`

Handle JSON-RPC 2.0 method calls. All A2A operations use this endpoint.

**Request Format:**
```json
{
  "jsonrpc": "2.0",
  "method": "method.name",
  "params": {},
  "id": 1
}
```

**Response Format (Success):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {...}
}
```

**Response Format (Error):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": {}
  }
}
```

### Batch Requests: `POST /a2a/jsonrpc/batch`

Handle multiple JSON-RPC requests in a single call.

### Health Check: `GET /health`

Returns service health status.

## A2A Methods

### Public Methods (No Authentication Required)

#### `agent.capabilities`

Get the agent's capabilities.

```json
// Request
{
  "jsonrpc": "2.0",
  "method": "agent.capabilities",
  "id": 1
}

// Response
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "agent_id": "agent-001",
    "capabilities": ["analyze", "report", "summarize"]
  }
}
```

#### `trust.verify`

Verify an agent's trust chain.

```json
// Request
{
  "jsonrpc": "2.0",
  "method": "trust.verify",
  "params": {
    "agent_id": "agent-001",
    "verification_level": "STANDARD"  // QUICK, STANDARD, or FULL
  },
  "id": 1
}

// Response
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "valid": true,
    "agent_id": "agent-001",
    "verification_level": "STANDARD",
    "errors": [],
    "trust_chain_summary": {
      "genesis_authority": "org-acme",
      "capabilities_count": 3,
      "delegations_count": 0
    },
    "latency_ms": 12.5
  }
}
```

### Protected Methods (Authentication Required)

Protected methods require a Bearer token in the Authorization header:
```
Authorization: Bearer <jwt_token>
```

#### `agent.invoke`

Invoke the agent with a task. Requires custom implementation.

#### `trust.delegate`

Delegate capabilities to another agent.

```json
// Request
{
  "jsonrpc": "2.0",
  "method": "trust.delegate",
  "params": {
    "delegatee_agent_id": "agent-002",
    "task_id": "task-123",
    "capabilities": ["read_data"],
    "constraints": {"max_records": 1000}
  },
  "id": 1
}

// Response
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "delegation_id": "del-456",
    "delegator_agent_id": "agent-001",
    "delegatee_agent_id": "agent-002",
    "task_id": "task-123",
    "capabilities_delegated": ["read_data"],
    "constraints": {"max_records": 1000},
    "delegated_at": "2024-01-15T10:30:00Z",
    "expires_at": "2024-01-15T11:30:00Z",
    "signature": "..."
  }
}
```

#### `audit.query`

Query the audit trail for an agent.

```json
// Request
{
  "jsonrpc": "2.0",
  "method": "audit.query",
  "params": {
    "agent_id": "agent-001",
    "start_time": "2024-01-01T00:00:00Z",
    "end_time": "2024-01-15T23:59:59Z",
    "action_type": "analyze",
    "limit": 100,
    "offset": 0
  },
  "id": 1
}

// Response
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "agent_id": "agent-001",
    "total_count": 42,
    "actions": [...],
    "delegation_chain": [...]
  }
}
```

## Authentication

### Creating Tokens

```python
# Create a token for agent-to-agent communication
token = await service.authenticator.create_token(
    audience="agent-002",  # Target agent
    capabilities=["analyze", "read_data"],
    constraints={"environment": "production"},
    ttl_seconds=3600,  # 1 hour
)
```

### Token Structure

JWT tokens include:
- Standard claims: `sub`, `iss`, `aud`, `exp`, `iat`, `jti`
- EATP claims: `authority_id`, `trust_chain_hash`, `capabilities`, `constraints`

### Verifying Tokens

```python
# Verify a received token
claims = await service.authenticator.verify_token(
    token,
    expected_audience="agent-001",  # Optional
    verify_trust=True,  # Verify trust chain
)
```

## Custom Method Registration

Register custom JSON-RPC methods:

```python
async def handle_custom_analyze(params: dict, auth_token: str | None):
    """Custom analysis method."""
    data = params.get("data")
    # Perform analysis...
    return {"analysis": "completed", "results": {...}}

service.register_method("custom.analyze", handle_custom_analyze)
```

## Error Codes

### JSON-RPC 2.0 Standard Errors

| Code | Message | Description |
|------|---------|-------------|
| -32700 | Parse error | Invalid JSON |
| -32600 | Invalid Request | Invalid JSON-RPC structure |
| -32601 | Method not found | Method doesn't exist |
| -32602 | Invalid params | Invalid method parameters |
| -32603 | Internal error | Server-side error |

### EATP-Specific Errors

| Code | Message | Description |
|------|---------|-------------|
| -40001 | Trust verification failed | Trust chain verification failed |
| -40002 | Authentication required | Missing or invalid auth token |
| -40003 | Authorization failed | Insufficient permissions |
| -40004 | Delegation failed | Delegation operation failed |
| -40005 | Agent Card error | Error generating Agent Card |

## Agent Card Generation

### Using AgentCardGenerator

```python
from kaizen.trust.a2a import AgentCardGenerator

generator = AgentCardGenerator(
    trust_operations=trust_ops,
    base_url="https://agent.example.com",
)

# Generate card from agent ID (looks up trust chain)
card = await generator.generate(
    agent_id="agent-001",
    name="Data Analyzer",
    version="1.0.0",
    description="AI agent for analysis",
)

# Or generate directly from trust chain
card = await generator.generate_from_chain(
    chain=trust_chain,
    name="Data Analyzer",
    version="1.0.0",
)
```

### Agent Card Caching

```python
from kaizen.trust.a2a import AgentCardCache

cache = AgentCardCache(ttl_seconds=300)  # 5 minute TTL

# Store card
cache.set("agent-001", card)

# Retrieve card (returns None if expired)
cached_card = cache.get("agent-001")

# Invalidate specific card
cache.invalidate("agent-001")

# Clear all
cache.clear()
```

## Configuration Options

### A2AService Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `trust_operations` | TrustOperations | required | Trust operations instance |
| `agent_id` | str | required | Agent's unique identifier |
| `agent_name` | str | required | Human-readable name |
| `agent_version` | str | required | Version string |
| `private_key` | str | required | Ed25519 private key (base64) |
| `capabilities` | list[str] | [] | Agent capabilities |
| `description` | str | None | Agent description |
| `base_url` | str | None | Base URL for endpoints |
| `cors_origins` | list[str] | ["*"] | Allowed CORS origins |
| `card_cache_ttl` | int | 300 | Agent Card cache TTL (seconds) |

## Integration with Kaizen Agents

### Trust-Aware Agent with A2A Service

```python
from kaizen.trust import TrustedAgent
from kaizen.trust.a2a import A2AService

class MyAnalyzerAgent(TrustedAgent):
    """Agent with A2A HTTP interface."""

    async def execute(self, task):
        # Agent logic here
        return {"result": "analyzed"}

# Create trusted agent
agent = MyAnalyzerAgent(
    agent_id="analyzer-001",
    trust_operations=trust_ops,
)

# Create A2A service for the agent
service = A2AService(
    trust_operations=trust_ops,
    agent_id=agent.agent_id,
    agent_name="Data Analyzer",
    agent_version="1.0.0",
    private_key=private_key,
    capabilities=agent.capabilities,
)

# Register custom invoke handler
async def handle_invoke(params: dict, auth_token: str | None):
    task = params.get("task")
    return await agent.execute(task)

service.register_method("agent.invoke", handle_invoke)
```

## Security Considerations

1. **Private Key Protection**: Store private keys securely (HSM, secrets manager)
2. **Token Expiration**: Use short TTLs for tokens (default: 1 hour)
3. **Trust Verification**: Always verify trust chains before sensitive operations
4. **CORS Configuration**: Configure appropriate CORS origins for production
5. **Rate Limiting**: Implement rate limiting for public endpoints
6. **Logging**: Enable audit logging for all method calls

## Testing

```python
from fastapi.testclient import TestClient

# Create test client
client = TestClient(service.create_app())

# Test Agent Card
response = client.get("/.well-known/agent.json")
assert response.status_code == 200
card = response.json()
assert card["agent_id"] == "agent-001"

# Test JSON-RPC method
response = client.post(
    "/a2a/jsonrpc",
    json={
        "jsonrpc": "2.0",
        "method": "agent.capabilities",
        "id": 1,
    }
)
assert response.json()["result"]["agent_id"] == "agent-001"

# Test protected method with auth
token = await service.authenticator.create_token(audience="agent-001")
response = client.post(
    "/a2a/jsonrpc",
    json={
        "jsonrpc": "2.0",
        "method": "trust.delegate",
        "params": {...},
        "id": 1,
    },
    headers={"Authorization": f"Bearer {token}"}
)
```
