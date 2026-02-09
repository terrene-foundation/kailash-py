# Phase 4: Trust API Specifications

## Complete API Endpoint Specifications

### Authentication & Authorization

All endpoints require JWT authentication. Trust operations require additional EATP context.

**Headers**:

```
Authorization: Bearer <jwt_token>
X-Org-ID: <organization_id>
X-Trace-ID: <optional_trace_id>
```

---

### Genesis Management APIs

#### Initiate Genesis Ceremony

```
POST /api/v1/trust/genesis/initiate

Request:
{
  "org_id": "org-acme-corp",
  "redirect_url": "https://app.example.com/callback",
  "initial_capabilities": ["read_documents", "generate_reports"],
  "constraint_template": "standard_office"
}

Response (201 Created):
{
  "ceremony_id": "ceremony-abc123",
  "status": "pending",
  "sso_redirect_url": "https://auth.okta.com/oauth2/authorize?...",
  "expires_at": "2025-01-02T10:05:00Z"
}
```

#### Execute Genesis Ceremony

```
POST /api/v1/trust/genesis/{ceremony_id}/execute

Request:
{
  "sso_token": "<jwt_from_sso_callback>",
  "initial_constraints": {
    "cost_limit": 10000,
    "time_window": "09:00-17:00",
    "timezone": "America/New_York"
  }
}

Response (201 Created):
{
  "ceremony_id": "ceremony-abc123",
  "status": "completed",
  "human_origin": {
    "human_id": "alice@corp.com",
    "display_name": "Alice Chen",
    "auth_provider": "okta"
  },
  "pseudo_agent_id": "pseudo:alice@corp.com",
  "genesis_record_id": "genesis-xyz789",
  "capabilities_granted": ["read_documents", "generate_reports"],
  "completed_at": "2025-01-02T09:01:23Z"
}
```

#### Revoke Genesis

```
POST /api/v1/trust/genesis/{human_id}/revoke

Request:
{
  "reason": "Employee termination",
  "cascade": true,
  "notify_affected_agents": true
}

Response (200 OK):
{
  "human_id": "alice@corp.com",
  "revocation_id": "revoke-def456",
  "agents_revoked": 12,
  "cascade_depth": 3,
  "revocation_time_ms": 423,
  "notification_sent": true
}
```

---

### Delegation APIs

#### Create Delegation

```
POST /api/v1/trust/delegations

Request:
{
  "agent_id": "agent-invoice-processor",
  "task_id": "process-november-invoices",
  "capabilities": ["read_invoices", "process_invoices"],
  "constraints": {
    "cost_limit": 1000,
    "cost_currency": "USD",
    "time_window_start": "09:00",
    "time_window_end": "17:00",
    "time_window_timezone": "UTC",
    "resource_patterns": ["invoices/nov-2025/*"],
    "expires_at": "2025-12-01T00:00:00Z"
  }
}

Response (201 Created):
{
  "delegation_id": "del-abc123",
  "delegator_id": "pseudo:alice@corp.com",
  "delegatee_id": "agent-invoice-processor",
  "task_id": "process-november-invoices",
  "capabilities": ["read_invoices", "process_invoices"],
  "constraints": { ... },
  "human_origin": {
    "human_id": "alice@corp.com",
    "display_name": "Alice Chen"
  },
  "delegation_chain": ["pseudo:alice@corp.com", "agent-invoice-processor"],
  "delegation_depth": 1,
  "delegated_at": "2025-01-02T09:15:00Z",
  "expires_at": "2025-12-01T00:00:00Z"
}
```

#### List Delegations

```
GET /api/v1/trust/delegations?
    human_id=alice@corp.com&
    status=active&
    agent_id=&
    page=1&
    page_size=20

Response (200 OK):
{
  "delegations": [...],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "has_next": true
}
```

#### Get Delegation with Chain

```
GET /api/v1/trust/delegations/{delegation_id}?include_chain=true

Response (200 OK):
{
  "delegation": { ... },
  "trust_chain": {
    "human_origin": { ... },
    "nodes": [
      { "type": "human", "id": "alice@corp.com", ... },
      { "type": "agent", "id": "agent-mgr", "constraints": {...} },
      { "type": "agent", "id": "agent-worker", "constraints": {...} }
    ],
    "edges": [
      { "from": 0, "to": 1, "delegated_at": "...", "constraints_diff": {...} },
      { "from": 1, "to": 2, "delegated_at": "...", "constraints_diff": {...} }
    ]
  }
}
```

---

### Trust Chain Streaming (WebSocket/SSE)

#### SSE Event Stream

```
GET /api/v1/trust/events/stream?
    org_id=org-acme&
    event_types=DELEGATION,VERIFICATION,REVOCATION

Response: text/event-stream

event: DELEGATION
data: {"event_id":"evt-1","timestamp":"2025-01-02T10:30:00Z","actor_id":"alice@corp.com","target_id":"agent-001","details":{...}}

event: VERIFICATION
data: {"event_id":"evt-2","timestamp":"2025-01-02T10:30:01Z","actor_id":"agent-001","action":"read_invoice","result":"VALID","latency_ms":2.3}

event: REVOCATION
data: {"event_id":"evt-3","timestamp":"2025-01-02T10:31:00Z","actor_id":"admin@corp.com","target_id":"bob@corp.com","agents_affected":4}
```

#### WebSocket Connection

```
WS /api/v1/trust/events/ws

// Subscribe message
{
  "action": "subscribe",
  "filters": {
    "org_id": "org-acme",
    "event_types": ["DELEGATION", "VERIFICATION"],
    "human_ids": ["alice@corp.com"]
  }
}

// Event message
{
  "type": "event",
  "event": {
    "event_id": "evt-123",
    "event_type": "VERIFICATION",
    ...
  }
}
```

---

### Trust Health APIs

#### Get Health Report

```
GET /api/v1/trust/health?org_id=org-acme&include_recommendations=true

Response (200 OK):
{
  "generated_at": "2025-01-02T10:00:00Z",
  "org_id": "org-acme",
  "overall_status": "healthy",
  "metrics": {
    "total_active_agents": 156,
    "total_active_delegations": 423,
    "average_delegation_depth": 2.3,
    "verification_success_rate": 0.9987,
    "verification_avg_latency_ms": 1.2
  },
  "sla_metrics": {
    "quick_sla_compliance": 0.998,
    "standard_sla_compliance": 0.999,
    "full_sla_compliance": 1.0
  },
  "security_alerts": {
    "unusual_delegation_patterns": [],
    "expired_delegations_active": 0,
    "constraint_violations_24h": 3
  },
  "recommendations": [
    "Enable trust chain caching for improved QUICK verification SLA"
  ]
}
```

---

### Bulk Operations APIs

#### Bulk Create Delegations

```
POST /api/v1/trust/delegations/bulk

Request:
{
  "delegations": [
    {
      "agent_id": "agent-001",
      "task_id": "task-a",
      "capabilities": ["read"],
      "constraints": { ... }
    },
    {
      "agent_id": "agent-002",
      "task_id": "task-b",
      "capabilities": ["read", "write"],
      "constraints": { ... }
    }
  ],
  "fail_on_first_error": false
}

Response (207 Multi-Status):
{
  "results": [
    { "index": 0, "status": 201, "delegation_id": "del-001" },
    { "index": 1, "status": 201, "delegation_id": "del-002" }
  ],
  "success_count": 2,
  "failure_count": 0
}
```

#### Bulk Revoke Delegations

```
POST /api/v1/trust/delegations/bulk-revoke

Request:
{
  "delegation_ids": ["del-001", "del-002", "del-003"],
  "reason": "Security policy update",
  "cascade": true
}

Response (200 OK):
{
  "revocation_id": "revoke-bulk-123",
  "delegations_revoked": 3,
  "cascaded_agents_revoked": 15,
  "execution_time_ms": 234
}
```

---

### Rate Limiting

| Endpoint Category    | Rate Limit    | Burst |
| -------------------- | ------------- | ----- |
| Genesis ceremonies   | 10/minute     | 5     |
| Delegation CRUD      | 100/minute    | 20    |
| Verification queries | 1000/minute   | 100   |
| Audit queries        | 50/minute     | 10    |
| Bulk operations      | 10/minute     | 2     |
| Event streams        | 5 connections | N/A   |

---
