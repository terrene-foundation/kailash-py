# API Gaps: Missing or Incomplete Trust Endpoints for Enterprise-App

## Executive Summary

This document catalogs all trust-related API endpoints documented across the Enterprise-App platform, identifies gaps in coverage, and specifies requirements for missing endpoints. The analysis draws from the SDK client documentation (31-sdk-execution-trust), trust developer docs (18-trust), infrastructure lineage API (16-infrastructure), and governance documentation (09-governance).

**Key Finding**: The platform documentation describes a rich client SDK (`enterprise_app_sdk`) with comprehensive trust chain, delegation, posture, and audit APIs. However, several critical API categories are missing: genesis management, real-time streaming, constraint templates, federation, bulk operations, and trust health aggregation. Additionally, the documented endpoints need verification that corresponding backend implementations exist.

**API Architecture**: The documented pattern uses a REST API with the base path `/api/v1/trust/` for trust operations, with an SDK client wrapper (`enterprise_app_sdk`) providing typed Python access.

---

## 1. Documented API Endpoints (Status: Need Verification)

### 1.1 Trust Chain APIs

**Documented In**: `docs/00-developers/31-sdk-execution-trust/04-trust-chains.md`

| Method   | Endpoint                           | SDK Method                        | Purpose                               | Auth Required       |
| -------- | ---------------------------------- | --------------------------------- | ------------------------------------- | ------------------- |
| `POST`   | `/api/v1/trust/chains`             | `client.trust.chains.establish()` | Create trust chain with HumanOrigin   | Yes (API Key + JWT) |
| `GET`    | `/api/v1/trust/chains/{id}`        | `client.trust.chains.get()`       | Get trust chain details               | Yes                 |
| `GET`    | `/api/v1/trust/chains`             | `client.trust.chains.list()`      | List trust chains with filtering      | Yes                 |
| `DELETE` | `/api/v1/trust/chains/{id}`        | `client.trust.chains.revoke()`    | Revoke trust chain (triggers cascade) | Yes                 |
| `POST`   | `/api/v1/trust/chains/{id}/verify` | `client.trust.chains.verify()`    | Verify action against chain           | Yes                 |

**Establish Trust Chain Request**:

```python
chain = await client.trust.chains.establish(
    agent_id="agent_worker",
    human_origin_data={
        "user_id": "user_123",
        "session_id": "ses_abc",
        "auth_method": "oauth2"
    },
    capabilities=["read:data", "write:reports", "execute:workflows"],
    constraints={
        "max_cost": 1000,
        "allowed_regions": ["us-west-2"],
        "require_approval": ["delete"]
    }
)
```

**Verify Action Request**:

```python
result = await client.trust.chains.verify(
    agent_id="agent_worker",
    action="write",
    resource="report_2024",
    context={"cost": 50, "region": "us-west-2"}
)
# Returns: { allowed: bool, chain_id: str, constraints_applied: dict }
```

**List Chains with Filtering**:

```python
chains = await client.trust.chains.list(
    agent_id="agent_worker",        # Filter by agent
    status="active",                 # active, revoked, expired
    human_origin_id="user_123",     # Filter by human
    page=1, page_size=50            # Pagination
)
```

**Gap Assessment**: Core trust chain CRUD is well-documented. Missing: batch chain creation, chain comparison, chain history/versioning.

---

### 1.2 Delegation APIs

**Documented In**: `docs/00-developers/31-sdk-execution-trust/05-delegations.md`

| Method   | Endpoint                         | SDK Method                          | Purpose                                              | Auth Required |
| -------- | -------------------------------- | ----------------------------------- | ---------------------------------------------------- | ------------- |
| `POST`   | `/api/v1/trust/delegations`      | `client.trust.delegations.create()` | Create delegation (subset of delegator capabilities) | Yes           |
| `GET`    | `/api/v1/trust/delegations`      | `client.trust.delegations.list()`   | List delegations with filtering                      | Yes           |
| `GET`    | `/api/v1/trust/delegations/{id}` | `client.trust.delegations.get()`    | Get delegation details                               | Yes           |
| `DELETE` | `/api/v1/trust/delegations/{id}` | `client.trust.delegations.revoke()` | Revoke delegation                                    | Yes           |

**Create Delegation Request**:

```python
delegation = await client.trust.delegations.create(
    chain_id="chain_abc123",
    delegator_id="agent_coordinator",
    delegatee_id="agent_worker",
    capabilities=["read:data", "execute:analysis"],  # Must be subset
    constraints={
        "max_runtime": 3600,
        "sandbox": True,
        "max_cost": 100
    }
)
```

**List Delegations with Filtering**:

```python
# By chain
delegations = await client.trust.delegations.list(chain_id="chain_abc123")

# By delegator
granted = await client.trust.delegations.list(delegator_id="agent_coordinator")

# By delegatee
received = await client.trust.delegations.list(delegatee_id="agent_worker")
```

**Gap Assessment**: Basic delegation CRUD is covered. Missing: batch delegation, delegation tree traversal endpoint, constraint tightening validation endpoint, delegation depth query.

---

### 1.3 Posture APIs

**Documented In**: `docs/00-developers/31-sdk-execution-trust/06-postures.md`

| Method | Endpoint                                         | SDK Method                                    | Purpose                      | Auth Required |
| ------ | ------------------------------------------------ | --------------------------------------------- | ---------------------------- | ------------- |
| `GET`  | `/api/v1/trust/postures/{agent_id}`              | `client.trust.postures.get()`                 | Get current posture          | Yes           |
| `POST` | `/api/v1/trust/postures/{agent_id}/progression`  | `client.trust.postures.request_progression()` | Request posture upgrade      | Yes           |
| `GET`  | `/api/v1/trust/postures/{agent_id}/requirements` | `client.trust.postures.get_requirements()`    | Get progression requirements | Yes           |

**Get Current Posture**:

```python
info = await client.trust.postures.get("agent_worker")
# Returns: {
#   posture: "BASIC",
#   progression_eligible: True,
#   last_assessment: "2025-12-01T10:00:00Z",
#   next_assessment: "2026-01-01T10:00:00Z"
# }
```

**Request Progression**:

```python
result = await client.trust.postures.request_progression(
    "agent_worker",
    target_posture="STANDARD",
    justification="Consistently good performance over 90 days"
)
# Returns: { request_id: str, status: "pending_approval" }
```

**Get Requirements**:

```python
reqs = await client.trust.postures.get_requirements("agent_worker")
# Returns: {
#   current_posture: "BASIC",
#   next_posture: "STANDARD",
#   requirements: {
#     min_successful_actions: 100,
#     max_violations: 0,
#     min_days_at_current: 30
#   },
#   current_metrics: {
#     successful_actions: 85,
#     violations: 0,
#     days_at_current: 22
#   }
# }
```

**Gap Assessment**: Basic posture management is covered. Missing: posture history endpoint, posture comparison across agents, posture regression API (manual demotion), organization-wide posture policy configuration.

---

### 1.4 Audit APIs

**Documented In**: `docs/00-developers/31-sdk-execution-trust/` (implied from client docs)

| Method | Endpoint                     | SDK Method                    | Purpose                          | Auth Required |
| ------ | ---------------------------- | ----------------------------- | -------------------------------- | ------------- |
| `GET`  | `/api/v1/trust/audit`        | `client.trust.audit.list()`   | List audit events with filtering | Yes           |
| `GET`  | `/api/v1/trust/audit/{id}`   | `client.trust.audit.get()`    | Get audit event details          | Yes           |
| `GET`  | `/api/v1/trust/audit/export` | `client.trust.audit.export()` | Export audit data for compliance | Yes           |

**List Audit Events**:

```python
events = await client.trust.audit.list(
    agent_id="agent_worker",
    action="write",
    result="success",
    start_date="2025-12-01",
    end_date="2025-12-31",
    page=1, page_size=100
)
```

**Export Audit Data**:

```python
export = await client.trust.audit.export(
    format="json",              # json, csv, cef
    start_date="2025-12-01",
    end_date="2025-12-31",
    include_chain_data=True
)
```

**Gap Assessment**: Basic audit querying is covered. Missing: audit aggregation endpoint, audit integrity verification endpoint, audit by human origin (documented in trust docs but not in SDK client), real-time audit streaming.

---

### 1.5 Cascade Revocation APIs

**Documented In**: `docs/00-developers/18-trust/03-cascade-revocation.md`

| Method | Endpoint                             | Purpose                           | Auth Required  |
| ------ | ------------------------------------ | --------------------------------- | -------------- |
| `GET`  | `/api/v1/trust/revoke/{id}/impact`   | Preview cascade revocation impact | Yes            |
| `POST` | `/api/v1/trust/revoke/{id}/cascade`  | Execute cascade revocation        | Yes (elevated) |
| `POST` | `/api/v1/trust/revoke/by-human/{id}` | Revoke all from human origin      | Yes (elevated) |

**Preview Impact Response**:

```json
{
  "target_agent_id": "agent-456",
  "affected_agents": [
    {
      "agent_id": "agent-789",
      "delegation_depth": 1,
      "active_workloads": 3,
      "capabilities": ["read:data", "write:reports"]
    },
    {
      "agent_id": "agent-101",
      "delegation_depth": 2,
      "active_workloads": 0,
      "capabilities": ["read:data"]
    }
  ],
  "total_affected": 2,
  "max_depth": 2,
  "critical_warnings": [],
  "active_workload_count": 3
}
```

**Execute Cascade Request**:

```json
{
  "reason": "Employee departure - access revoked",
  "confirmed_by": "admin@company.com",
  "force": false
}
```

**Gap Assessment**: Cascade revocation is well-documented but needs backend implementation verification. Missing: partial revocation (revoke specific subtree only), revocation history/timeline, revocation rollback, scheduled revocation (future-dated).

---

### 1.6 Lineage APIs

**Documented In**: `docs/00-developers/16-infrastructure/lineage-api.md`

| Method | Endpoint                  | Purpose                            | Permission       |
| ------ | ------------------------- | ---------------------------------- | ---------------- |
| `GET`  | `/api/lineage`            | List lineages with filtering       | `read:lineage`   |
| `GET`  | `/api/lineage/{id}`       | Get lineage details                | `read:lineage`   |
| `GET`  | `/api/lineage/{id}/graph` | Get lineage graph (D3 format)      | `read:lineage`   |
| `GET`  | `/api/lineage/export`     | Export lineage data (CSV/JSON/CEF) | `export:lineage` |
| `GET`  | `/api/lineage/stats`      | Get lineage statistics             | `read:lineage`   |
| `POST` | `/api/lineage/redact`     | Redact user data (GDPR)            | `gdpr:redact`    |

**Query Parameters for List**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `external_user_id` | string | Filter by external user |
| `external_system_id` | string | Filter by external system |
| `agent_id` | string | Filter by agent |
| `status` | string | Filter by status |
| `start_date` | ISO 8601 | Filter by date range |
| `end_date` | ISO 8601 | Filter by date range |
| `page` | integer | Page number |
| `page_size` | integer | Results per page |

**Graph Response Format**:

```json
{
  "nodes": [
    {
      "id": "node-1",
      "type": "external_agent",
      "label": "Research Agent",
      "metadata": { "provider": "openai", "model": "gpt-4" }
    }
  ],
  "edges": [
    {
      "source": "node-1",
      "target": "node-2",
      "type": "invocation",
      "metadata": { "timestamp": "2025-12-01T10:00:00Z" }
    }
  ]
}
```

**Gap Assessment**: Lineage API is comprehensive for external agent invocation tracking. However, this is a separate concern from EATP trust chain lineage. Missing: EATP trust chain graph endpoint (distinct from invocation lineage), combined view (invocation lineage + trust chain).

---

### 1.7 Governance APIs

**Documented In**: `docs/00-developers/06-gateways/external-agents-governance.md`

| Method | Endpoint                               | Purpose                  |
| ------ | -------------------------------------- | ------------------------ |
| `POST` | `/api/v1/governance/budget`            | Set budget limits        |
| `GET`  | `/api/v1/governance/budget/{scope_id}` | Get budget status        |
| `POST` | `/api/v1/governance/rate-limit`        | Configure rate limits    |
| `POST` | `/api/v1/governance/policy`            | Create governance policy |
| `GET`  | `/api/v1/governance/policy/{id}`       | Get policy details       |
| `POST` | `/api/v1/governance/check`             | Check policy compliance  |

**Budget Configuration**:

```python
budget_config = {
    "monthly_budget_usd": 100.0,
    "daily_budget_usd": 10.0,
    "monthly_execution_limit": 1000,
    "scope": "team",             # organization, team, user, agent
    "scope_id": "team-123"
}
```

**Gap Assessment**: Budget and rate limiting are well-covered. Missing: budget forecasting endpoint, policy template management, multi-dimensional policy evaluation (combining ABAC with trust posture).

---

## 2. Missing API Endpoints (Not Documented)

### 2.1 Genesis Management APIs

**Priority**: P0-Critical
**Rationale**: No documented APIs exist for managing the genesis ceremony -- the foundational trust establishment that connects human SSO identity to the EATP trust chain.

| Method   | Endpoint                           | Purpose                                | Request Body | Response         |
| -------- | ---------------------------------- | -------------------------------------- | ------------ | ---------------- |
| `POST`   | `/api/v1/trust/genesis`            | Create genesis record from SSO         | See below    | GenesisResult    |
| `GET`    | `/api/v1/trust/genesis/{id}`       | Get genesis record details             | -            | GenesisRecord    |
| `GET`    | `/api/v1/trust/genesis`            | List genesis records (org-scoped)      | Query params | GenesisRecord[]  |
| `DELETE` | `/api/v1/trust/genesis/{id}`       | Revoke genesis (cascade to all chains) | Reason       | RevocationResult |
| `POST`   | `/api/v1/trust/genesis/{id}/renew` | Renew expired genesis record           | -            | GenesisResult    |

**Create Genesis Request**:

```json
{
  "user_id": "user_123",
  "sso_claims": {
    "email": "alice@company.com",
    "name": "Alice Smith",
    "provider": "okta",
    "session_id": "okta-sess-abc",
    "roles": ["admin", "team-lead"],
    "groups": ["engineering"]
  },
  "authority_type": "organization",
  "initial_capabilities": [
    { "type": "access", "scope": "read:*" },
    { "type": "action", "scope": "execute:workflows" },
    { "type": "delegation", "scope": "delegate:team" }
  ],
  "initial_constraints": {
    "resource": { "max_total_budget": 10000 },
    "temporal": { "valid_until": "2026-12-31T23:59:59Z" },
    "data_access": { "sensitivity_level": "confidential" }
  }
}
```

**Create Genesis Response**:

```json
{
  "genesis_id": "gen_abc123",
  "pseudo_agent_id": "pa_xyz789",
  "trust_chain_id": "chain_def456",
  "human_origin": {
    "human_id": "alice@company.com",
    "display_name": "Alice Smith",
    "auth_provider": "okta",
    "session_id": "okta-sess-abc",
    "auth_timestamp": "2026-02-07T10:00:00Z"
  },
  "constraints_applied": { ... },
  "created_at": "2026-02-07T10:00:00Z"
}
```

**Authorization**: Requires `admin:trust` or `manage:genesis` permission. Organization admins can create genesis records for users in their organization.

---

### 2.2 Trust Chain Streaming APIs

**Priority**: P1-High
**Rationale**: No real-time trust event streaming API exists. The UI needs live updates for trust chain changes, constraint violations, and revocation events.

| Method | Endpoint                      | Purpose                                  | Protocol           |
| ------ | ----------------------------- | ---------------------------------------- | ------------------ |
| `GET`  | `/api/v1/trust/events/stream` | SSE stream of trust events               | Server-Sent Events |
| `WS`   | `/ws/v1/trust/events`         | WebSocket for bidirectional trust events | WebSocket          |

**SSE Stream Request**:

```
GET /api/v1/trust/events/stream?
  organization_id=org-123&
  event_types=chain.established,chain.revoked,constraint.violated&
  agent_ids=agent-1,agent-2
```

**SSE Event Format**:

```
event: trust.chain.revoked
data: {
  "event_id": "evt_abc123",
  "event_type": "trust.chain.revoked",
  "timestamp": "2026-02-07T14:34:00Z",
  "organization_id": "org-123",
  "agent_id": "agent-456",
  "chain_id": "chain_def789",
  "reason": "Human origin revoked",
  "cascade_impact": {
    "affected_agents": 3,
    "affected_delegations": 5
  },
  "human_origin": {
    "human_id": "alice@company.com",
    "display_name": "Alice Smith"
  }
}
```

**Event Types**:
| Event Type | Trigger | Payload |
|------------|---------|---------|
| `trust.chain.established` | New trust chain created | chain_id, agent_id, human_origin |
| `trust.chain.verified` | Action verified against chain | chain_id, action, result |
| `trust.chain.revoked` | Chain revoked (may be cascade) | chain_id, reason, cascade_impact |
| `trust.delegation.created` | New delegation | delegation_id, delegator, delegatee |
| `trust.delegation.revoked` | Delegation revoked | delegation_id, reason |
| `trust.constraint.violated` | Constraint boundary hit | agent_id, constraint_type, details |
| `trust.posture.changed` | Posture progression/regression | agent_id, old_posture, new_posture |
| `trust.health.changed` | Agent health status change | agent_id, old_status, new_status |
| `trust.audit.created` | New audit anchor | audit_id, agent_id, action |

**Authorization**: Requires `read:trust_events` permission. Events are scoped to the user's organization.

---

### 2.3 Constraint Template APIs

**Priority**: P2-Medium
**Rationale**: No APIs exist for managing reusable constraint templates, which are essential for consistent constraint configuration across agents.

| Method   | Endpoint                                           | Purpose                          |
| -------- | -------------------------------------------------- | -------------------------------- |
| `POST`   | `/api/v1/trust/constraint-templates`               | Create constraint template       |
| `GET`    | `/api/v1/trust/constraint-templates`               | List templates (org-scoped)      |
| `GET`    | `/api/v1/trust/constraint-templates/{id}`          | Get template details             |
| `PUT`    | `/api/v1/trust/constraint-templates/{id}`          | Update template                  |
| `DELETE` | `/api/v1/trust/constraint-templates/{id}`          | Delete template                  |
| `POST`   | `/api/v1/trust/constraint-templates/{id}/apply`    | Apply template to agent          |
| `POST`   | `/api/v1/trust/constraint-templates/{id}/validate` | Validate template against parent |

**Create Template Request**:

```json
{
  "name": "CFO Profile",
  "description": "Financial oversight agent with high budget limits",
  "category": "financial",
  "constraints": {
    "resource": {
      "max_cost_per_operation": 50000,
      "max_total_budget": 1000000,
      "max_api_calls": 10000,
      "allowed_models": ["gpt-4", "claude-3-opus"]
    },
    "temporal": {
      "allowed_hours": {
        "start": 6,
        "end": 22,
        "timezone": "America/New_York"
      },
      "max_duration_minutes": 480
    },
    "data_access": {
      "sensitivity_level": "confidential",
      "require_encryption": true,
      "allow_external_transfer": false
    },
    "action": {
      "require_approval_for": [
        "delete",
        "external_transfer",
        "budget_increase"
      ],
      "sandbox_mode": false
    },
    "communication": {
      "require_review": true,
      "allowed_channels": ["email", "slack"],
      "retention_policy": "1y"
    }
  },
  "tags": ["financial", "executive", "high-trust"]
}
```

**Authorization**: Requires `manage:constraint_templates` permission.

---

### 2.4 Federation/Trust Bridge APIs

**Priority**: P2-Medium
**Rationale**: No APIs exist for cross-organization trust bridging, required for federated agent collaboration.

| Method   | Endpoint                              | Purpose                             |
| -------- | ------------------------------------- | ----------------------------------- |
| `POST`   | `/api/v1/trust/bridges`               | Propose trust bridge to another org |
| `GET`    | `/api/v1/trust/bridges`               | List active bridges                 |
| `GET`    | `/api/v1/trust/bridges/{id}`          | Get bridge details                  |
| `PUT`    | `/api/v1/trust/bridges/{id}/accept`   | Accept bridge proposal              |
| `PUT`    | `/api/v1/trust/bridges/{id}/reject`   | Reject bridge proposal              |
| `DELETE` | `/api/v1/trust/bridges/{id}`          | Dissolve trust bridge               |
| `POST`   | `/api/v1/trust/bridges/{id}/verify`   | Verify remote chain via bridge      |
| `GET`    | `/api/v1/trust/bridges/{id}/activity` | Get bridge activity log             |

**Create Bridge Proposal**:

```json
{
  "remote_organization_id": "org-456",
  "bridge_type": "bidirectional",
  "capabilities_offered": ["read:shared_data", "execute:shared_workflows"],
  "capabilities_requested": ["read:partner_data"],
  "constraints": {
    "max_cost_per_operation": 100,
    "data_sensitivity_max": "internal",
    "require_approval": true
  },
  "expiry": "2027-02-07T00:00:00Z",
  "justification": "Joint analysis project between engineering teams"
}
```

**Authorization**: Requires `admin:trust_bridges` permission. Both organizations must approve.

---

### 2.5 Trust Health Aggregation APIs

**Priority**: P1-High
**Rationale**: No APIs exist for organizational trust health metrics, required for the Trust Health Dashboard.

| Method | Endpoint                          | Purpose                               |
| ------ | --------------------------------- | ------------------------------------- |
| `GET`  | `/api/v1/trust/health`            | Get organization trust health summary |
| `GET`  | `/api/v1/trust/health/agents`     | Get per-agent health breakdown        |
| `GET`  | `/api/v1/trust/health/trends`     | Get health trends over time           |
| `GET`  | `/api/v1/trust/health/compliance` | Get compliance readiness metrics      |
| `GET`  | `/api/v1/trust/health/alerts`     | Get active trust health alerts        |

**Organization Health Response**:

```json
{
  "organization_id": "org-123",
  "trust_health_score": 87,
  "timestamp": "2026-02-07T15:00:00Z",
  "agents": {
    "total": 45,
    "healthy": 38,
    "warning": 5,
    "degraded": 1,
    "revoked": 1
  },
  "posture_distribution": {
    "pseudo": 2,
    "supervised": 15,
    "shared_planning": 18,
    "continuous_insight": 8,
    "delegated": 2
  },
  "constraint_utilization": {
    "budget_used_percent": 62,
    "api_calls_used_percent": 45,
    "tokens_used_percent": 38
  },
  "recent_violations": 3,
  "chains_expiring_soon": 2,
  "compliance": {
    "soc2_ready": true,
    "hipaa_ready": false,
    "gdpr_compliant": true
  }
}
```

**Trends Response**:

```json
{
  "time_range": "30d",
  "data_points": [
    {
      "date": "2026-01-08",
      "health_score": 82,
      "total_agents": 40,
      "violations": 5,
      "new_chains": 3,
      "revocations": 1
    }
  ]
}
```

**Authorization**: Requires `read:trust_health` permission.

---

### 2.6 Bulk Operations APIs

**Priority**: P2-Medium
**Rationale**: No bulk operation APIs exist for managing trust at organizational scale.

| Method | Endpoint                                | Purpose                         |
| ------ | --------------------------------------- | ------------------------------- |
| `POST` | `/api/v1/trust/bulk/establish`          | Batch create trust chains       |
| `POST` | `/api/v1/trust/bulk/delegate`           | Batch create delegations        |
| `POST` | `/api/v1/trust/bulk/revoke`             | Batch revoke chains/delegations |
| `POST` | `/api/v1/trust/bulk/update-constraints` | Batch update constraints        |
| `POST` | `/api/v1/trust/bulk/update-posture`     | Batch update postures           |

**Batch Establish Request**:

```json
{
  "chains": [
    {
      "agent_id": "agent-1",
      "human_origin_data": { "user_id": "user_123", "auth_method": "oauth2" },
      "capabilities": ["read:data"],
      "constraints": { "max_cost": 100 }
    },
    {
      "agent_id": "agent-2",
      "human_origin_data": { "user_id": "user_456", "auth_method": "saml" },
      "capabilities": ["read:data", "write:reports"],
      "constraints": { "max_cost": 500 }
    }
  ],
  "fail_strategy": "continue_on_error"
}
```

**Batch Response**:

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "results": [
    { "agent_id": "agent-1", "chain_id": "chain_abc", "status": "success" },
    { "agent_id": "agent-2", "chain_id": "chain_def", "status": "success" }
  ]
}
```

**Authorization**: Requires `admin:trust` permission.

---

### 2.7 Constraint Validation APIs

**Priority**: P1-High
**Rationale**: No standalone constraint validation APIs exist. The UI needs to validate constraints before saving, check tightening rules during delegation, and preview constraint impact.

| Method | Endpoint                                     | Purpose                             |
| ------ | -------------------------------------------- | ----------------------------------- |
| `POST` | `/api/v1/trust/constraints/validate`         | Validate constraint envelope        |
| `POST` | `/api/v1/trust/constraints/check-tightening` | Verify child is tighter than parent |
| `POST` | `/api/v1/trust/constraints/merge`            | Preview merged constraints          |
| `POST` | `/api/v1/trust/constraints/impact`           | Preview what constraint would block |

**Validate Constraint Request**:

```json
{
  "constraints": {
    "resource": { "max_cost_per_operation": 5000, "max_total_budget": 1000 }
  }
}
```

**Validate Response**:

```json
{
  "valid": false,
  "errors": [
    {
      "field": "resource.max_cost_per_operation",
      "message": "max_cost_per_operation (5000) cannot exceed max_total_budget (1000)",
      "severity": "error"
    }
  ],
  "warnings": []
}
```

**Check Tightening Request**:

```json
{
  "parent_chain_id": "chain_abc",
  "child_constraints": {
    "resource": { "max_cost_per_operation": 6000 }
  }
}
```

**Check Tightening Response**:

```json
{
  "valid": false,
  "violations": [
    {
      "dimension": "resource",
      "field": "max_cost_per_operation",
      "parent_value": 5000,
      "child_value": 6000,
      "message": "Child constraint (6000) exceeds parent constraint (5000). Constraint tightening violated."
    }
  ]
}
```

**Authorization**: Requires `read:trust` permission.

---

### 2.8 Audit Integrity APIs

**Priority**: P1-High
**Rationale**: The compliance documentation references hash-chained audit logs with tamper-evidence verification, but no API endpoint exists to verify audit log integrity.

| Method | Endpoint                                | Purpose                     |
| ------ | --------------------------------------- | --------------------------- |
| `GET`  | `/api/v1/trust/audit/integrity`         | Verify hash chain integrity |
| `GET`  | `/api/v1/trust/audit/by-human/{id}`     | Query audit by human origin |
| `GET`  | `/api/v1/trust/audit/stats`             | Get audit statistics        |
| `POST` | `/api/v1/trust/audit/compliance-report` | Generate compliance report  |

**Integrity Check Response**:

```json
{
  "chain_valid": true,
  "total_records_checked": 15234,
  "first_record": "2025-06-01T00:00:00Z",
  "last_record": "2026-02-07T14:59:59Z",
  "hash_algorithm": "sha256",
  "verification_timestamp": "2026-02-07T15:00:00Z",
  "gaps_detected": 0,
  "tamper_indicators": 0
}
```

**Compliance Report Request**:

```json
{
  "report_type": "soc2",
  "period_start": "2025-07-01",
  "period_end": "2025-12-31",
  "include_sections": [
    "trust_chain_summary",
    "delegation_changes",
    "constraint_violations",
    "posture_changes",
    "revocation_events"
  ],
  "format": "pdf"
}
```

**Authorization**: `verify:audit` for integrity checks, `export:compliance` for compliance reports.

---

## 3. API Authentication and Authorization Summary

### Authentication Methods

| Method    | Use Case                 | Header                              |
| --------- | ------------------------ | ----------------------------------- |
| API Key   | Server-to-server         | `Authorization: Bearer aos_key_...` |
| JWT       | User sessions            | `Authorization: Bearer eyJ...`      |
| OAuth 2.0 | Third-party integrations | Standard OAuth flow                 |

### Authorization Permissions Matrix

| Permission                    | Description                              | Required For             |
| ----------------------------- | ---------------------------------------- | ------------------------ |
| `read:trust`                  | Read trust chains, delegations, postures | All GET endpoints        |
| `write:trust`                 | Create/modify trust chains, delegations  | POST/PUT endpoints       |
| `admin:trust`                 | Full trust management including bulk ops | Bulk operations, genesis |
| `read:trust_events`           | Subscribe to trust event streams         | SSE/WebSocket endpoints  |
| `manage:genesis`              | Create/revoke genesis records            | Genesis management       |
| `manage:constraint_templates` | CRUD constraint templates                | Template management      |
| `admin:trust_bridges`         | Manage cross-org trust bridges           | Federation endpoints     |
| `read:trust_health`           | View trust health metrics                | Health dashboard         |
| `read:lineage`                | Query lineage records                    | Lineage API              |
| `export:lineage`              | Export lineage data                      | Lineage export           |
| `gdpr:redact`                 | Redact user data                         | GDPR compliance          |
| `verify:audit`                | Verify audit integrity                   | Integrity checks         |
| `export:compliance`           | Generate compliance reports              | Compliance exports       |

---

## 4. API Versioning Strategy

### Documented

- Base path: `/api/v1/trust/`
- Version in URL path
- No documented deprecation policy

### Recommended

- Maintain `/api/v1/` for current documented APIs
- Add `/api/v2/` only when breaking changes are required
- Support both versions for minimum 12 months
- Use `Sunset` header for deprecation notices
- Document migration guides for version transitions

---

## 5. Implementation Priority

### Phase 1: Core Trust APIs (Weeks 1-4)

| API Group                     | Endpoints   | Priority | Dependencies             |
| ----------------------------- | ----------- | -------- | ------------------------ |
| Genesis Management            | 5 endpoints | P0       | Genesis Ceremony Service |
| Trust Chain (verify existing) | 5 endpoints | P0       | SDK integration          |
| Delegation (verify existing)  | 4 endpoints | P0       | SDK integration          |
| Constraint Validation         | 4 endpoints | P1       | Constraint Compiler      |

### Phase 2: Operational APIs (Weeks 5-8)

| API Group                 | Endpoints              | Priority | Dependencies      |
| ------------------------- | ---------------------- | -------- | ----------------- |
| Trust Event Streaming     | 2 endpoints (SSE + WS) | P1       | Trust Event Bus   |
| Trust Health              | 5 endpoints            | P1       | Health Service    |
| Audit Integrity           | 4 endpoints            | P1       | Compliance module |
| Posture (verify existing) | 3 endpoints            | P1       | Posture Engine    |

### Phase 3: Scale APIs (Weeks 9-12)

| API Group            | Endpoints   | Priority | Dependencies     |
| -------------------- | ----------- | -------- | ---------------- |
| Bulk Operations      | 5 endpoints | P2       | All core APIs    |
| Constraint Templates | 7 endpoints | P2       | Constraint model |
| Federation/Bridges   | 8 endpoints | P2       | Bridge Service   |

---

## 6. Error Response Standards

All trust API endpoints should follow a consistent error response format:

```json
{
  "error": {
    "code": "TRUST_CHAIN_NOT_FOUND",
    "message": "Trust chain 'chain_abc123' not found",
    "details": {
      "chain_id": "chain_abc123",
      "organization_id": "org-789"
    },
    "request_id": "req_xyz789",
    "timestamp": "2026-02-07T15:00:00Z"
  }
}
```

**Error Code Categories**:
| Prefix | Category | Example |
|--------|----------|---------|
| `TRUST_` | Trust chain errors | `TRUST_CHAIN_NOT_FOUND`, `TRUST_CHAIN_EXPIRED` |
| `DELEGATION_` | Delegation errors | `DELEGATION_TIGHTENING_VIOLATED`, `DELEGATION_CIRCULAR` |
| `CONSTRAINT_` | Constraint errors | `CONSTRAINT_VALIDATION_FAILED`, `CONSTRAINT_EXCEEDED` |
| `POSTURE_` | Posture errors | `POSTURE_REGRESSION_NOT_ALLOWED`, `POSTURE_REQUIREMENTS_NOT_MET` |
| `GENESIS_` | Genesis errors | `GENESIS_ALREADY_EXISTS`, `GENESIS_SSO_MISMATCH` |
| `AUDIT_` | Audit errors | `AUDIT_INTEGRITY_COMPROMISED`, `AUDIT_EXPORT_TOO_LARGE` |
| `BRIDGE_` | Federation errors | `BRIDGE_REMOTE_ORG_NOT_FOUND`, `BRIDGE_MUTUAL_APPROVAL_REQUIRED` |

---

_Document Version: 1.0_
_Analysis Date: February 2026_
_Source: Enterprise-App developer docs (31-sdk-execution-trust, 18-trust, 16-infrastructure/lineage-api, 06-gateways/external-agents-governance, 09-governance)_
_Author: Gap Analysis Agent_
