# REST API Reference

The PACT governance API exposes all governance operations over HTTP. Endpoints are served by FastAPI and secured with Bearer token authentication.

## Base URL

```
/api/v1/governance
```

## Authentication

All endpoints require authentication via Bearer token in the `Authorization` header:

```
Authorization: Bearer <your-api-token>
```

Set the token via environment variable:

```bash
export PACT_GOVERNANCE_API_TOKEN="your-secret-token"
```

**Dev mode**: When no token is configured, authentication is disabled for local development.

**Scopes**:

- `governance:read` -- query org structure, check access, verify actions
- `governance:write` -- grant clearance, create bridges, create KSPs, set envelopes
- `governance:admin` -- all operations including configuration changes

## Rate Limiting

All endpoints are rate-limited to 60 requests per minute per IP address by default. When exceeded, the API returns HTTP 429 with a JSON error body.

---

## POST /check-access

Evaluate whether a role can access a classified knowledge item using the 5-step access enforcement algorithm.

**Scope**: `governance:read`

**Request**:

```bash
curl -X POST http://localhost:8000/api/v1/governance/check-access \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "role_address": "D1-R1-D1-R1-D1-R1-T1-R1",
    "item_id": "doc-research-001",
    "item_classification": "confidential",
    "item_owning_unit": "D1-R1-D1-R1-D1-R1-T1",
    "item_compartments": [],
    "posture": "shared_planning"
  }'
```

**Request Body**:

| Field               | Type     | Required | Description                                                                      |
| ------------------- | -------- | -------- | -------------------------------------------------------------------------------- |
| role_address        | string   | yes      | D/T/R positional address of the requesting role                                  |
| item_id             | string   | yes      | Unique identifier of the knowledge item                                          |
| item_classification | string   | yes      | One of: public, restricted, confidential, secret, top_secret                     |
| item_owning_unit    | string   | yes      | D or T prefix that owns the knowledge item                                       |
| item_compartments   | string[] | no       | Named compartments the item belongs to (default: [])                             |
| posture             | string   | yes      | One of: pseudo_agent, supervised, shared_planning, continuous_insight, delegated |

**Response** (200):

```json
{
  "allowed": true,
  "reason": "Same unit access: role is within 'D1-R1-D1-R1-D1-R1-T1'",
  "step_failed": null,
  "audit_details": {
    "role_address": "D1-R1-D1-R1-D1-R1-T1-R1",
    "item_id": "doc-research-001",
    "step": "4a",
    "access_path": "same_unit"
  }
}
```

**Response Fields**:

| Field         | Type        | Description                                        |
| ------------- | ----------- | -------------------------------------------------- |
| allowed       | boolean     | Whether access is granted                          |
| reason        | string      | Human-readable explanation                         |
| step_failed   | int or null | Which step (1-5) denied access, or null if allowed |
| audit_details | object      | Structured details for audit logging               |

---

## POST /verify-action

Evaluate an action against the effective constraint envelope for a role. This is the primary governance decision endpoint.

**Scope**: `governance:read`

**Request**:

```bash
curl -X POST http://localhost:8000/api/v1/governance/verify-action \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "role_address": "D1-R1-D1-R1-D1-R1-T1-R1",
    "action": "write",
    "cost": 5000.00
  }'
```

**Request Body**:

| Field        | Type   | Required | Description                                              |
| ------------ | ------ | -------- | -------------------------------------------------------- |
| role_address | string | yes      | D/T/R positional address                                 |
| action       | string | yes      | Action being performed (e.g., "read", "write", "deploy") |
| cost         | float  | no       | Cost in USD for financial constraint checks              |
| resource     | string | no       | Resource path for knowledge access checks                |
| channel      | string | no       | Communication channel for channel constraint checks      |

**Validation**: cost must be finite (NaN and Inf are rejected) and non-negative.

**Response** (200):

```json
{
  "level": "auto_approved",
  "allowed": true,
  "reason": "Action 'write' is within all constraint dimensions",
  "role_address": "D1-R1-D1-R1-D1-R1-T1-R1",
  "action": "write"
}
```

**Response Fields**:

| Field        | Type    | Description                                                    |
| ------------ | ------- | -------------------------------------------------------------- |
| level        | string  | One of: auto_approved, flagged, held, blocked                  |
| allowed      | boolean | True for auto_approved and flagged; false for held and blocked |
| reason       | string  | Human-readable explanation                                     |
| role_address | string  | The role that requested the action                             |
| action       | string  | The action that was evaluated                                  |

---

## GET /org

Get a summary of the compiled organization structure.

**Scope**: `governance:read`

**Request**:

```bash
curl http://localhost:8000/api/v1/governance/org \
  -H "Authorization: Bearer $TOKEN"
```

**Response** (200):

```json
{
  "org_id": "university-001",
  "name": "State University",
  "department_count": 6,
  "team_count": 5,
  "role_count": 12,
  "total_nodes": 23
}
```

---

## GET /org/nodes/{address}

Look up a single node by its positional address.

**Scope**: `governance:read`

**Request**:

```bash
curl http://localhost:8000/api/v1/governance/org/nodes/D1-R1-D1-R1 \
  -H "Authorization: Bearer $TOKEN"
```

**Response** (200):

```json
{
  "address": "D1-R1-D1-R1",
  "name": "Provost",
  "node_type": "R",
  "parent_address": "D1-R1-D1",
  "is_vacant": false,
  "children": ["D1-R1-D1-R1-D1", "D1-R1-D1-R1-D2"]
}
```

**Response** (404): No node found at address.

---

## GET /org/tree

Get the full organizational tree as a flat list of nodes.

**Scope**: `governance:read`

**Request**:

```bash
curl http://localhost:8000/api/v1/governance/org/tree \
  -H "Authorization: Bearer $TOKEN"
```

**Response** (200):

```json
{
  "org_id": "university-001",
  "nodes": [
    {
      "address": "D1",
      "name": "Office of the President",
      "node_type": "D",
      "parent_address": null,
      "is_vacant": false,
      "children": ["D1-R1"]
    },
    ...
  ]
}
```

---

## POST /clearances

Grant knowledge clearance to a role.

**Scope**: `governance:write`

**Request**:

```bash
curl -X POST http://localhost:8000/api/v1/governance/clearances \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "role_address": "D1-R1-D1-R1-D2-R1-T1-R1",
    "max_clearance": "secret",
    "compartments": ["human-subjects"],
    "granted_by_role_address": "D1-R1-D1-R1-D2-R1"
  }'
```

**Request Body**:

| Field                   | Type     | Required | Description                                                  |
| ----------------------- | -------- | -------- | ------------------------------------------------------------ |
| role_address            | string   | yes      | D/T/R address of the role to grant clearance to              |
| max_clearance           | string   | yes      | One of: public, restricted, confidential, secret, top_secret |
| compartments            | string[] | no       | Named compartments to grant access to (default: [])          |
| granted_by_role_address | string   | yes      | D/T/R address of the granting role (audit trail)             |

**Response** (201):

```json
{
  "status": "granted",
  "role_address": "D1-R1-D1-R1-D2-R1-T1-R1",
  "max_clearance": "secret"
}
```

---

## POST /bridges

Create a Cross-Functional Bridge between two roles.

**Scope**: `governance:write`

**Request**:

```bash
curl -X POST http://localhost:8000/api/v1/governance/bridges \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "role_a_address": "D1-R1-D1-R1",
    "role_b_address": "D1-R1-D2-R1",
    "bridge_type": "standing",
    "max_classification": "restricted",
    "bilateral": false
  }'
```

**Request Body**:

| Field              | Type     | Required | Description                                           |
| ------------------ | -------- | -------- | ----------------------------------------------------- |
| role_a_address     | string   | yes      | First role in the bridge                              |
| role_b_address     | string   | yes      | Second role in the bridge                             |
| bridge_type        | string   | yes      | One of: standing, scoped, ad_hoc                      |
| max_classification | string   | yes      | Maximum classification accessible via this bridge     |
| bilateral          | boolean  | no       | Whether both roles have mutual access (default: true) |
| operational_scope  | string[] | no       | Limit bridge to specific operations (default: [])     |

**Response** (201):

```json
{
  "status": "created",
  "bridge_id": "bridge-a1b2c3d4",
  "bridge_type": "standing"
}
```

---

## POST /ksps

Create a Knowledge Share Policy for cross-unit access.

**Scope**: `governance:write`

**Request**:

```bash
curl -X POST http://localhost:8000/api/v1/governance/ksps \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_unit_address": "D1-R1-D1",
    "target_unit_address": "D1-R1-D2-R1-T1",
    "max_classification": "restricted",
    "created_by_role_address": "D1-R1",
    "compartments": []
  }'
```

**Request Body**:

| Field                   | Type     | Required | Description                                             |
| ----------------------- | -------- | -------- | ------------------------------------------------------- |
| source_unit_address     | string   | yes      | D/T prefix sharing knowledge                            |
| target_unit_address     | string   | yes      | D/T prefix receiving access                             |
| max_classification      | string   | yes      | Maximum classification level shared                     |
| created_by_role_address | string   | yes      | Role that created this policy (audit trail)             |
| compartments            | string[] | no       | Restrict sharing to specific compartments (default: []) |

**Response** (201):

```json
{
  "status": "created",
  "ksp_id": "ksp-e5f6g7h8",
  "source_unit": "D1-R1-D1",
  "target_unit": "D1-R1-D2-R1-T1"
}
```

---

## POST /envelopes

Set a role envelope with constraint dimensions.

**Scope**: `governance:write`

**Request**:

```bash
curl -X POST http://localhost:8000/api/v1/governance/envelopes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "defining_role_address": "D1-R1-D1-R1-D1-R1",
    "target_role_address": "D1-R1-D1-R1-D1-R1-T1-R1",
    "envelope_id": "env-cs-chair",
    "constraints": {
      "financial": {
        "max_spend_usd": 10000,
        "requires_approval_above_usd": 5000
      },
      "operational": {
        "allowed_actions": ["read", "write", "approve"],
        "blocked_actions": ["deploy"]
      }
    }
  }'
```

**Request Body**:

| Field                 | Type   | Required | Description                                        |
| --------------------- | ------ | -------- | -------------------------------------------------- |
| defining_role_address | string | yes      | D/T/R address of the role defining the envelope    |
| target_role_address   | string | yes      | D/T/R address of the role this envelope applies to |
| envelope_id           | string | yes      | Unique identifier for this envelope                |
| constraints           | object | yes      | Constraint dimensions (see below)                  |

**Constraint Dimensions**:

```json
{
  "financial": {
    "max_spend_usd": 10000,
    "api_cost_budget_usd": 500,
    "requires_approval_above_usd": 5000,
    "reasoning_required": false
  },
  "operational": {
    "allowed_actions": ["read", "write"],
    "blocked_actions": ["deploy"],
    "max_actions_per_day": 100,
    "max_actions_per_hour": 20,
    "reasoning_required": false
  }
}
```

**Validation**: All numeric financial fields must be finite (NaN and Inf are rejected).

**Response** (201):

```json
{
  "status": "set",
  "envelope_id": "env-cs-chair",
  "target_role_address": "D1-R1-D1-R1-D1-R1-T1-R1"
}
```

---

## Error Responses

All endpoints return errors in a consistent format:

**401 Unauthorized**:

```json
{
  "detail": "Authentication required: provide Bearer token in Authorization header"
}
```

**404 Not Found**:

```json
{
  "detail": "No node found at address 'D99-R1'"
}
```

**422 Validation Error**:

```json
{
  "detail": [
    {
      "loc": ["body", "cost"],
      "msg": "cost must be finite, got nan. NaN/Inf values bypass governance checks.",
      "type": "value_error"
    }
  ]
}
```

**429 Rate Limited**:

```json
{
  "error": "Rate limit exceeded",
  "detail": "60 per 1 minute"
}
```

---

## WebSocket Events

The governance API emits real-time events over WebSocket for dashboard integration:

| Event Type                     | Trigger                          |
| ------------------------------ | -------------------------------- |
| `governance.access_checked`    | After a check-access evaluation  |
| `governance.action_verified`   | After a verify-action evaluation |
| `governance.clearance_granted` | After granting clearance         |
| `governance.clearance_revoked` | After revoking clearance         |
| `governance.bridge_created`    | After creating a bridge          |
| `governance.ksp_created`       | After creating a KSP             |
| `governance.envelope_set`      | After setting an envelope        |

Events are published to the platform EventBus and are available on the WebSocket endpoint.

---

## Mounting the API

### On an existing FastAPI app

```python
from fastapi import FastAPI
from pact.governance.engine import GovernanceEngine
from pact.governance.api.auth import GovernanceAuth
from pact.governance.api.router import mount_governance_api

app = FastAPI()
engine = GovernanceEngine(org_definition)
auth = GovernanceAuth()

mount_governance_api(app, engine, auth, rate_limit="60/minute")
```

### Standalone app (for testing)

```python
from pact.governance.api.router import create_governance_app

app = create_governance_app(engine, auth, rate_limit="60/minute")

# Run with uvicorn
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=8000)
```
