# Integration Architecture: SDK to Platform Data Flow

## Executive Summary

This document defines the architectural boundary between the Kailash SDK trust module and the Enterprise-App platform, specifying data flows, service responsibilities, event models, configuration mapping, and multi-tenancy patterns. It serves as the integration blueprint for connecting SDK trust operations to platform services, APIs, and UI components.

**Key Principle**: The SDK owns all cryptographic operations and trust chain management. The platform owns user sessions, organizational context, UI rendering, and workflow coordination. The integration layer translates between these two domains.

**Architecture Pattern**: The integration follows a **Service Facade** pattern where platform services wrap SDK operations, adding organizational context, access control, event emission, and data persistence.

---

## 1. Service Boundary Definition

### 1.1 SDK Responsibility (Kailash Trust Module)

The SDK is the **source of truth** for all trust operations. It handles:

| Responsibility           | SDK Component                             | Description                            |
| ------------------------ | ----------------------------------------- | -------------------------------------- |
| Cryptographic Operations | `TrustKeyManager`, Ed25519                | Key generation, signing, verification  |
| Trust Chain Management   | `TrustOperations`                         | ESTABLISH, VERIFY, DELEGATE, AUDIT     |
| Chain Storage            | `PostgresTrustStore`                      | Persistent storage of trust chain data |
| Constraint Evaluation    | `ConstraintEnvelope`, `TrustPolicyEngine` | Constraint validation and enforcement  |
| Context Propagation      | `ExecutionContext`, `HumanOrigin`         | Ambient context through operations     |
| Agent Trust              | `TrustedAgent`, `PseudoAgent`             | Trust-aware agent execution            |
| Agent Registry           | `AgentRegistry`, `AgentHealthMonitor`     | Agent discovery and health             |
| Secure Messaging         | `SecureChannel`, `MessageVerifier`        | Encrypted agent-to-agent communication |
| A2A Service              | `A2AHTTPService`                          | HTTP-based agent communication         |
| Trust-Aware Execution    | `TrustAwareOrchestrationRuntime`          | Workflow execution with trust checks   |
| Credential Management    | `CredentialRotation`                      | Automatic key rotation                 |

### 1.2 Platform Responsibility (Enterprise-App)

The platform provides the **operational context** and **user-facing layer**:

| Responsibility          | Platform Component               | Description                                  |
| ----------------------- | -------------------------------- | -------------------------------------------- |
| User Authentication     | SSO Integration (Okta, Azure AD) | Human identity verification                  |
| Session Management      | Session Service                  | User sessions with trust chain references    |
| Organization Management | Organization Service             | Multi-tenant organization structure          |
| API Gateway             | REST API Layer                   | Authentication, authorization, rate limiting |
| UI Rendering            | React Frontend                   | Trust visualization, management dashboards   |
| Event Bus               | Platform Event System            | Trust event distribution to UI and services  |
| Data Persistence        | DataFlow Models                  | Platform-side trust data for queries and UI  |
| Compliance              | Compliance Module                | SOC 2, HIPAA, GDPR reporting                 |
| Governance              | Governance Service               | Budget enforcement, rate limiting, policies  |
| Workflow Coordination   | Objective/Request System         | Task assignment and tracking                 |

### 1.3 Integration Layer Responsibility

The integration layer **bridges** SDK and Platform:

| Responsibility         | Integration Service          | Description                                           |
| ---------------------- | ---------------------------- | ----------------------------------------------------- |
| SSO-to-Trust Mapping   | Genesis Ceremony Service     | Maps SSO claims to HumanOrigin                        |
| Event Translation      | Trust Event Adapter          | Translates SDK events to platform events              |
| Constraint Compilation | Constraint Envelope Compiler | Maps UI config to SDK ConstraintEnvelope              |
| Data Synchronization   | Trust Data Sync Service      | Keeps platform DataFlow models in sync with SDK store |
| Health Aggregation     | Trust Health Service         | Aggregates SDK health data for dashboard              |
| Cascade Orchestration  | Cascade Revocation Engine    | Orchestrates multi-step revocation                    |

---

## 2. Core Data Flows

### 2.1 User Login and Trust Establishment

```
┌──────────┐    ┌──────────────┐    ┌───────────────────┐    ┌─────────────┐
│   User   │    │   Platform   │    │  Integration      │    │    SDK      │
│ Browser  │    │   API/SSO    │    │  Layer            │    │   Trust     │
└────┬─────┘    └──────┬───────┘    └────────┬──────────┘    └──────┬──────┘
     │                 │                      │                      │
     │ 1. Login via SSO│                      │                      │
     │────────────────>│                      │                      │
     │                 │                      │                      │
     │ 2. SSO Response │                      │                      │
     │<────────────────│                      │                      │
     │   (JWT + claims)│                      │                      │
     │                 │                      │                      │
     │                 │ 3. Create Session    │                      │
     │                 │─────────────────────>│                      │
     │                 │   (user_id, claims)  │                      │
     │                 │                      │                      │
     │                 │                      │ 4. Create HumanOrigin│
     │                 │                      │─────────────────────>│
     │                 │                      │   PseudoAgent.       │
     │                 │                      │   create_for_human() │
     │                 │                      │                      │
     │                 │                      │ 5. Establish Trust   │
     │                 │                      │─────────────────────>│
     │                 │                      │   TrustOperations.   │
     │                 │                      │   establish()        │
     │                 │                      │                      │
     │                 │                      │ 6. Return chain_id   │
     │                 │                      │<─────────────────────│
     │                 │                      │                      │
     │                 │ 7. Session + chain_id│                      │
     │                 │<─────────────────────│                      │
     │                 │                      │                      │
     │ 8. Session token│                      │                      │
     │<────────────────│                      │                      │
     │  (includes      │                      │                      │
     │   trust_chain_id)                      │                      │
```

**Data Mapping (SSO Claims to HumanOrigin)**:
| SSO Claim | HumanOrigin Field | Mapping Logic |
|-----------|-------------------|---------------|
| `sub` or `email` | `human_id` | Use email if available, otherwise sub |
| `name` or `given_name + family_name` | `display_name` | Concatenate given + family if no name |
| `iss` (issuer URL) | `auth_provider` | Map issuer URL to provider name |
| Platform session ID | `session_id` | Generated by platform session service |
| `iat` or `auth_time` | `auth_timestamp` | Use auth_time from OIDC if available |
| All claims | `claims` | Store full claim set for audit |

**SSO Provider Mapping Configuration**:

```python
SSO_PROVIDER_MAP = {
    "https://company.okta.com": {
        "provider_name": "okta",
        "user_id_claim": "email",
        "display_name_claim": "name",
        "group_claims": "groups",
        "role_claims": "custom:roles"
    },
    "https://login.microsoftonline.com": {
        "provider_name": "azure_ad",
        "user_id_claim": "preferred_username",
        "display_name_claim": "name",
        "group_claims": "groups",
        "role_claims": "roles"
    },
    "https://accounts.google.com": {
        "provider_name": "google",
        "user_id_claim": "email",
        "display_name_claim": "name",
        "group_claims": None,
        "role_claims": None
    }
}
```

---

### 2.2 Agent Action Verification

```
┌──────────┐    ┌──────────────┐    ┌───────────────────┐    ┌─────────────┐
│   Agent  │    │   Platform   │    │  Integration      │    │    SDK      │
│  Runtime │    │   Service    │    │  (EATPVerifier)   │    │   Trust     │
└────┬─────┘    └──────┬───────┘    └────────┬──────────┘    └──────┬──────┘
     │                 │                      │                      │
     │ 1. Execute tool │                      │                      │
     │────────────────>│                      │                      │
     │  (tool_name,    │                      │                      │
     │   tool_args,    │                      │                      │
     │   trust_chain_id)                      │                      │
     │                 │                      │                      │
     │                 │ 2. Verify action     │                      │
     │                 │─────────────────────>│                      │
     │                 │  (chain_id, action,  │                      │
     │                 │   resource, context) │                      │
     │                 │                      │                      │
     │                 │                      │ 3. Check chain       │
     │                 │                      │─────────────────────>│
     │                 │                      │  TrustOperations.    │
     │                 │                      │  verify()            │
     │                 │                      │                      │
     │                 │                      │ 4. Check constraints │
     │                 │                      │─────────────────────>│
     │                 │                      │  ConstraintEnvelope. │
     │                 │                      │  evaluate()          │
     │                 │                      │                      │
     │                 │                      │ 5. Verification      │
     │                 │                      │<─────────────────────│
     │                 │                      │  result              │
     │                 │                      │                      │
     │                 │ 6. Allowed/Denied    │                      │
     │                 │<─────────────────────│                      │
     │                 │                      │                      │
     │  [If Allowed]   │                      │                      │
     │                 │ 7. Execute tool      │                      │
     │<────────────────│                      │                      │
     │                 │                      │                      │
     │ 8. Tool result  │                      │                      │
     │────────────────>│                      │                      │
     │                 │                      │                      │
     │                 │ 9. Create audit      │                      │
     │                 │─────────────────────>│                      │
     │                 │                      │ 10. Audit anchor     │
     │                 │                      │─────────────────────>│
     │                 │                      │  TrustOperations.    │
     │                 │                      │  audit()             │
     │                 │                      │                      │
     │                 │                      │ 11. Emit event       │
     │                 │                      │──────>Event Bus      │
```

**Verification Context Data**:

```python
@dataclass
class VerificationRequest:
    trust_chain_id: str           # From user session or agent session
    agent_id: str                 # Agent requesting action
    action: str                   # Tool name or action type
    resource: str                 # Resource being accessed
    context: Dict[str, Any]       # Contextual data for constraint evaluation
    #   "cost": 50.0,             # For financial constraints
    #   "region": "us-west-2",    # For data access constraints
    #   "time": "2026-02-07T14:00:00Z",  # For temporal constraints
    #   "sensitivity": "confidential",    # For data access constraints
    organization_id: str          # For multi-tenancy scoping
```

---

### 2.3 Delegation Flow

```
┌──────────┐    ┌──────────────┐    ┌───────────────────┐    ┌─────────────┐
│ Manager  │    │   Platform   │    │  Integration      │    │    SDK      │
│  Agent   │    │   Service    │    │  Layer            │    │   Trust     │
└────┬─────┘    └──────┬───────┘    └────────┬──────────┘    └──────┬──────┘
     │                 │                      │                      │
     │ 1. Spawn worker │                      │                      │
     │────────────────>│                      │                      │
     │  (worker_config,│                      │                      │
     │   capabilities, │                      │                      │
     │   constraints)  │                      │                      │
     │                 │                      │                      │
     │                 │ 2. Validate tightening                      │
     │                 │─────────────────────>│                      │
     │                 │  (parent_chain,      │                      │
     │                 │   child_constraints) │                      │
     │                 │                      │                      │
     │                 │                      │ 3. Check tightening  │
     │                 │                      │─────────────────────>│
     │                 │                      │  ConstraintEnvelope. │
     │                 │                      │  validate_tightening()
     │                 │                      │                      │
     │                 │                      │ 4. Create delegation │
     │                 │                      │─────────────────────>│
     │                 │                      │  TrustOperations.    │
     │                 │                      │  delegate()          │
     │                 │                      │                      │
     │                 │                      │ 5. Delegation record │
     │                 │                      │<─────────────────────│
     │                 │                      │                      │
     │                 │ 6. Worker created    │                      │
     │                 │<─────────────────────│                      │
     │                 │                      │                      │
     │                 │                      │ 7. Emit delegation   │
     │                 │                      │    event             │
     │                 │                      │──────>Event Bus      │
     │                 │                      │                      │
     │ 8. Worker agent │                      │                      │
     │<────────────────│                      │                      │
     │  (with new      │                      │                      │
     │   trust_chain_id)                      │                      │
```

**Constraint Tightening Rules** (enforced by SDK):

```
Parent Constraint         Child Constraint         Rule
──────────────────       ──────────────────       ──────────
max_cost = $10,000       max_cost <= $10,000      Child <= Parent
allowed_models = [A,B,C] allowed_models ⊆ [A,B,C] Child subset of Parent
valid_until = Dec 2026   valid_until <= Dec 2026  Child expires same or earlier
sensitivity = internal   sensitivity <= internal   Child same or more restricted
allowed_tools = [X,Y,Z]  allowed_tools ⊆ [X,Y,Z]  Child subset of Parent
```

---

### 2.4 Cascade Revocation Flow

```
┌──────────┐    ┌──────────────┐    ┌───────────────────┐    ┌─────────────┐
│  Admin   │    │   Platform   │    │  Revocation       │    │    SDK      │
│   UI     │    │   API        │    │  Engine           │    │   Trust     │
└────┬─────┘    └──────┬───────┘    └────────┬──────────┘    └──────┬──────┘
     │                 │                      │                      │
     │ 1. Click Revoke │                      │                      │
     │────────────────>│                      │                      │
     │                 │                      │                      │
     │                 │ 2. Compute impact    │                      │
     │                 │─────────────────────>│                      │
     │                 │                      │                      │
     │                 │                      │ 3. Traverse tree     │
     │                 │                      │─────────────────────>│
     │                 │                      │  PostgresTrustStore. │
     │                 │                      │  get_delegations()   │
     │                 │                      │                      │
     │                 │                      │ 4. Affected agents   │
     │                 │                      │<─────────────────────│
     │                 │                      │                      │
     │                 │ 5. Impact preview    │                      │
     │                 │<─────────────────────│                      │
     │                 │                      │                      │
     │ 6. Show modal   │                      │                      │
     │<────────────────│                      │                      │
     │ (affected count,│                      │                      │
     │  active warnings│                      │                      │
     │  critical alerts│                      │                      │
     │                 │                      │                      │
     │ 7. Confirm      │                      │                      │
     │  (type "REVOKE")│                      │                      │
     │────────────────>│                      │                      │
     │                 │                      │                      │
     │                 │ 8. Execute cascade   │                      │
     │                 │─────────────────────>│                      │
     │                 │                      │                      │
     │                 │                      │ 9. Revoke each agent │
     │                 │                      │─────────────────────>│
     │                 │                      │  [for each affected] │
     │                 │                      │  TrustOperations.    │
     │                 │                      │  revoke()            │
     │                 │                      │                      │
     │                 │                      │ 10. Create audit     │
     │                 │                      │─────────────────────>│
     │                 │                      │  TrustOperations.    │
     │                 │                      │  audit()             │
     │                 │                      │                      │
     │                 │                      │ 11. Emit events      │
     │                 │                      │──────>Event Bus      │
     │                 │                      │  [per revoked agent] │
     │                 │                      │                      │
     │                 │ 12. Cascade complete │                      │
     │                 │<─────────────────────│                      │
     │                 │                      │                      │
     │ 13. Update UI   │                      │                      │
     │<────────────────│                      │                      │
     │  (via SSE events)                      │                      │
```

---

## 3. Event Model

### 3.1 Event Flow Architecture

```
SDK Trust Operations          Event Adapter           Platform Event Bus          Consumers
─────────────────           ──────────────           ──────────────────          ──────────

TrustOperations.establish()  ──>  TrustEventAdapter  ──>  EventBus.publish()  ──>  UI (SSE)
TrustOperations.verify()     ──>  TrustEventAdapter  ──>  EventBus.publish()  ──>  Dashboard
TrustOperations.delegate()   ──>  TrustEventAdapter  ──>  EventBus.publish()  ──>  Notifications
TrustOperations.audit()      ──>  TrustEventAdapter  ──>  EventBus.publish()  ──>  Audit Explorer
AgentHealthMonitor.check()   ──>  HealthEventAdapter ──>  EventBus.publish()  ──>  Health Dashboard
ConstraintEnvelope.violated  ──>  AlertEventAdapter  ──>  EventBus.publish()  ──>  Alert System
CascadeRevocation.execute()  ──>  RevocationAdapter  ──>  EventBus.publish()  ──>  All UI components
```

### 3.2 Event Adapter Interface

```python
class TrustEventAdapter:
    """Translates SDK trust events to platform event bus format."""

    def __init__(self, event_bus: EventBus, org_resolver: OrgResolver):
        self.event_bus = event_bus
        self.org_resolver = org_resolver

    async def on_chain_established(
        self,
        chain: TrustLineageChain,
        human_origin: HumanOrigin,
    ) -> None:
        """Called by SDK after TrustOperations.establish()."""
        await self.event_bus.publish(
            TrustEvent(
                event_type="trust.chain.established",
                organization_id=self.org_resolver.resolve(chain),
                agent_id=chain.agent_id,
                chain_id=chain.chain_id,
                human_origin={
                    "human_id": human_origin.human_id,
                    "display_name": human_origin.display_name,
                    "auth_provider": human_origin.auth_provider,
                },
                timestamp=datetime.now(timezone.utc),
            )
        )

    async def on_chain_verified(
        self,
        chain_id: str,
        action: str,
        result: VerificationResult,
    ) -> None:
        """Called by SDK after TrustOperations.verify()."""
        await self.event_bus.publish(
            TrustEvent(
                event_type="trust.chain.verified",
                chain_id=chain_id,
                action=action,
                allowed=result.allowed,
                constraints_applied=result.constraints_applied,
                timestamp=datetime.now(timezone.utc),
            )
        )

    async def on_delegation_created(
        self,
        delegation: DelegationRecord,
    ) -> None:
        """Called by SDK after TrustOperations.delegate()."""
        await self.event_bus.publish(
            TrustEvent(
                event_type="trust.delegation.created",
                delegation_id=delegation.delegation_id,
                delegator_id=delegation.delegator_id,
                delegatee_id=delegation.delegatee_id,
                capabilities=delegation.capabilities,
                constraints_tightened=delegation.constraints_diff,
                timestamp=datetime.now(timezone.utc),
            )
        )

    async def on_constraint_violated(
        self,
        agent_id: str,
        chain_id: str,
        constraint_type: str,
        violation_details: Dict[str, Any],
    ) -> None:
        """Called by SDK when constraint evaluation fails."""
        await self.event_bus.publish(
            TrustEvent(
                event_type="trust.constraint.violated",
                agent_id=agent_id,
                chain_id=chain_id,
                constraint_type=constraint_type,
                details=violation_details,
                severity="high",
                timestamp=datetime.now(timezone.utc),
            )
        )
```

### 3.3 Event Delivery to UI

```python
# SSE endpoint for trust events
@app.get("/api/v1/trust/events/stream")
async def trust_event_stream(
    request: Request,
    organization_id: str = Depends(get_org_id),
    event_types: Optional[str] = None,  # Comma-separated filter
    agent_ids: Optional[str] = None,     # Comma-separated filter
):
    """Server-Sent Events stream for trust events."""

    async def event_generator():
        async for event in event_bus.subscribe(
            organization_id=organization_id,
            event_types=event_types.split(",") if event_types else None,
            agent_ids=agent_ids.split(",") if agent_ids else None,
        ):
            yield {
                "event": event.event_type,
                "data": json.dumps(event.to_dict()),
                "id": event.event_id,
            }

    return EventSourceResponse(event_generator())
```

---

## 4. Configuration Mapping

### 4.1 Platform UI to SDK Configuration

| Platform UI Element              | Platform Data Format                               | SDK Target                                | Mapping Function                      |
| -------------------------------- | -------------------------------------------------- | ----------------------------------------- | ------------------------------------- |
| Posture Selector                 | `{ posture: "supervised", config: {...} }`         | `TrustPolicyEngine.set_posture()`         | `map_posture_config()`                |
| Constraint Panel (Resource)      | `{ maxCostPerOperation: 5000, ... }`               | `ConstraintEnvelope(RESOURCE_LIMIT, ...)` | `compile_resource_constraints()`      |
| Constraint Panel (Temporal)      | `{ validFrom: "...", validUntil: "..." }`          | `ConstraintEnvelope(TIME_WINDOW, ...)`    | `compile_temporal_constraints()`      |
| Constraint Panel (Data)          | `{ allowedPaths: [...], sensitivityLevel: "..." }` | `ConstraintEnvelope(DATA_SCOPE, ...)`     | `compile_data_constraints()`          |
| Constraint Panel (Action)        | `{ allowedTools: [...], sandboxMode: true }`       | `ConstraintEnvelope(RESOURCE_LIMIT, ...)` | `compile_action_constraints()`        |
| Constraint Panel (Communication) | `{ allowedRecipients: [...], ... }`                | `ConstraintEnvelope(DATA_SCOPE, ...)`     | `compile_communication_constraints()` |

### 4.2 Posture to SDK Execution Mode Mapping

| Platform Posture   | SDK Execution Mode               | Approval Requirements                                | Monitoring Level              |
| ------------------ | -------------------------------- | ---------------------------------------------------- | ----------------------------- |
| Pseudo             | `execution_mode="manual"`        | All actions require human execution                  | Full logging                  |
| Supervised         | `execution_mode="supervised"`    | Every action requires explicit approval              | Full logging                  |
| Shared Planning    | `execution_mode="collaborative"` | Plan review required, low-risk actions auto-approved | Full logging + plan tracking  |
| Continuous Insight | `execution_mode="autonomous"`    | Only high-impact actions require approval            | Dashboard monitoring + alerts |
| Delegated          | `execution_mode="autonomous"`    | No approval required (within constraints)            | Periodic audit + alerts       |

### 4.3 SSO Claims to SDK Fields Mapping

```python
def map_sso_to_human_origin(
    sso_claims: Dict[str, Any],
    provider_config: Dict[str, str],
    session_id: str,
) -> HumanOrigin:
    """Maps SSO claims to SDK HumanOrigin."""
    return HumanOrigin(
        human_id=sso_claims[provider_config["user_id_claim"]],
        display_name=sso_claims.get(provider_config["display_name_claim"], "Unknown"),
        auth_provider=provider_config["provider_name"],
        session_id=session_id,
        auth_timestamp=datetime.fromtimestamp(
            sso_claims.get("auth_time", sso_claims.get("iat", time.time())),
            tz=timezone.utc,
        ),
        claims={
            "groups": sso_claims.get(provider_config.get("group_claims", ""), []),
            "roles": sso_claims.get(provider_config.get("role_claims", ""), []),
            "issuer": sso_claims.get("iss", ""),
            "audience": sso_claims.get("aud", ""),
        },
    )
```

---

## 5. Multi-Tenancy Architecture

### 5.1 Tenant Isolation Model

```
┌──────────────────────────────────────────────────────────────────┐
│                       API Gateway                                 │
│                                                                   │
│  Request → Extract JWT → Resolve org_id → Add to context         │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │                 Organization Context                      │     │
│  │                                                           │     │
│  │  org_id: "org-123"                                       │     │
│  │  user_id: "user-456"                                     │     │
│  │  roles: ["admin", "team-lead"]                           │     │
│  │  permissions: ["read:trust", "write:trust", ...]         │     │
│  │                                                           │     │
│  └─────────────────────────────────────────────────────────┘     │
│                           │                                       │
│                           ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                   Platform Service                          │  │
│  │                                                              │  │
│  │  # Every SDK call includes organization_id                  │  │
│  │  result = await trust_ops.establish(                         │  │
│  │      organization_id=context.org_id,  # Always present     │  │
│  │      human_origin=human_origin,                             │  │
│  │      ...                                                    │  │
│  │  )                                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                           │                                       │
│                           ▼                                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                   SDK PostgresTrustStore                     │  │
│  │                                                              │  │
│  │  # All queries filtered by organization_id                  │  │
│  │  SELECT * FROM trust_chains                                 │  │
│  │  WHERE organization_id = $1                                 │  │
│  │  AND chain_id = $2                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.2 Tenant Isolation Rules

| Layer            | Isolation Mechanism                | Enforcement Point              |
| ---------------- | ---------------------------------- | ------------------------------ |
| API Gateway      | JWT validation + org_id extraction | Request middleware             |
| Platform Service | org_id parameter in all SDK calls  | Service method signature       |
| SDK Trust Store  | WHERE clause on organization_id    | PostgresTrustStore query layer |
| Event Bus        | Organization-scoped subscriptions  | Event routing layer            |
| DataFlow Models  | organization_id foreign key        | DataFlow model definition      |
| UI               | Organization context in session    | React context provider         |

### 5.3 Cross-Tenant Trust (Federation)

For cross-organization trust (Trust Bridges), the isolation model relaxes at specific, controlled points:

```
Organization A                    Trust Bridge                    Organization B
──────────────                    ────────────                    ──────────────

Agent A-1 ───── chain_a ────── bridge_ab ────── chain_b ────── Agent B-1
                                    │
                            Constraint tightening
                            applied at bridge boundary
                                    │
                            Both orgs maintain
                            separate trust stores
```

**Federation Rules**:

1. Each organization maintains its own trust store
2. Bridge creates a mapping record in both stores
3. Remote chains are verified against bridge constraints
4. Bridge constraints always tighten (never expand) remote capabilities
5. Revocation in either org propagates via bridge

---

## 6. Data Synchronization

### 6.1 SDK Store to Platform DataFlow Sync

The SDK `PostgresTrustStore` is the source of truth for trust chain data. Platform DataFlow models store a **projection** optimized for UI queries.

```
SDK PostgresTrustStore                     Platform DataFlow Models
(Source of Truth)                          (Query-Optimized Projection)
──────────────────                         ────────────────────────────

trust_chains table ─── sync ───────────→  TrustChain model
  - chain_id                                - id (= chain_id)
  - agent_id                                - agent_id
  - human_origin (JSON)                     - human_origin_id (FK to User)
  - genesis_record (JSON)                   - human_display_name
  - capabilities (JSON)                     - status (active/revoked/expired)
  - constraints (JSON)                      - created_at
  - status                                  - posture_level
  - created_at                              - organization_id

delegation_records table ── sync ──────→  TrustDelegation model
  - delegation_id                           - id (= delegation_id)
  - delegator_id                            - delegator_agent_id
  - delegatee_id                            - delegatee_agent_id
  - capabilities (JSON)                     - capabilities_summary
  - constraints (JSON)                      - chain_id (FK to TrustChain)
  - status                                  - status
  - created_at                              - depth
                                            - organization_id

audit_anchors table ──── sync ─────────→  TrustAuditAnchor model
  - anchor_id                               - id (= anchor_id)
  - agent_id                                - agent_id
  - action_type                             - action_type
  - resource_id                             - resource_id
  - result                                  - result
  - human_origin (JSON)                     - human_origin_id (FK to User)
  - chain_state_hash                        - chain_id (FK to TrustChain)
  - timestamp                               - created_at
                                            - organization_id
```

### 6.2 Sync Strategy

| Strategy           | Description                | Use Case                           |
| ------------------ | -------------------------- | ---------------------------------- |
| **Event-Driven**   | Sync on SDK event emission | Real-time sync for active changes  |
| **Periodic Batch** | Full sync every N minutes  | Catch-up for missed events         |
| **On-Demand**      | Sync when UI requests data | Lazy sync for rarely-accessed data |

**Recommended Approach**: Event-driven primary with periodic batch backup (every 5 minutes) and on-demand fallback.

```python
class TrustDataSyncService:
    """Keeps platform DataFlow models in sync with SDK store."""

    async def on_trust_event(self, event: TrustEvent) -> None:
        """Event-driven sync handler."""
        if event.event_type == "trust.chain.established":
            await self._sync_chain(event.chain_id)
        elif event.event_type == "trust.delegation.created":
            await self._sync_delegation(event.delegation_id)
        elif event.event_type == "trust.chain.revoked":
            await self._mark_chain_revoked(event.chain_id)
            await self._mark_delegations_revoked(event.chain_id)
        elif event.event_type == "trust.audit.created":
            await self._sync_audit_anchor(event.audit_id)

    async def full_sync(self, organization_id: str) -> SyncResult:
        """Periodic batch sync for catch-up."""
        sdk_chains = await self.trust_store.list_chains(organization_id)
        platform_chains = await self.chain_model.list(organization_id=organization_id)
        # Diff and sync...
```

---

## 7. Error Handling and Degraded Mode

### 7.1 Failure Scenarios

| Failure                            | Impact                             | Handling                                           |
| ---------------------------------- | ---------------------------------- | -------------------------------------------------- |
| SDK Trust Store unavailable        | Cannot create/verify trust chains  | Queue operations, return "trust_pending" status    |
| Event Bus unavailable              | UI not receiving real-time updates | Fall back to polling, queue events for replay      |
| SSO provider unavailable           | Cannot establish new trust         | Use cached session, prevent new genesis            |
| Platform DB unavailable            | Cannot query DataFlow models       | Fall back to direct SDK store queries              |
| Cascade revocation partial failure | Some agents not revoked            | Retry with exponential backoff, flag inconsistency |

### 7.2 Circuit Breaker Pattern

```python
class TrustServiceCircuitBreaker:
    """Circuit breaker for SDK trust operations."""

    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state = "closed"  # closed, open, half-open

    async def call(self, operation, *args, **kwargs):
        if self.state == "open":
            if time_since_last_failure > self.reset_timeout:
                self.state = "half-open"
            else:
                raise TrustServiceUnavailable("Circuit breaker open")

        try:
            result = await operation(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
            raise
```

### 7.3 Trust Pending State

When the SDK trust store is temporarily unavailable, the platform can operate in a "trust pending" state:

```python
class TrustPendingHandler:
    """Handles operations when SDK trust store is unavailable."""

    async def queue_trust_operation(
        self,
        operation_type: str,
        operation_data: Dict[str, Any],
    ) -> str:
        """
        Queues a trust operation for later execution.
        Returns a pending_operation_id for tracking.
        """
        pending_id = str(uuid.uuid4())
        await self.queue.enqueue(
            pending_id=pending_id,
            operation_type=operation_type,
            data=operation_data,
            created_at=datetime.now(timezone.utc),
            retry_count=0,
            max_retries=10,
        )
        return pending_id

    async def process_pending_operations(self) -> int:
        """
        Called when SDK trust store becomes available.
        Processes all pending operations in order.
        Returns count of processed operations.
        """
        pending = await self.queue.list_pending()
        processed = 0
        for op in pending:
            try:
                await self._execute_operation(op)
                await self.queue.mark_complete(op.pending_id)
                processed += 1
            except Exception as e:
                await self.queue.increment_retry(op.pending_id)
        return processed
```

---

## 8. Performance Considerations

### 8.1 Caching Strategy

| Data                 | Cache Location          | TTL        | Invalidation                   |
| -------------------- | ----------------------- | ---------- | ------------------------------ |
| Trust chain status   | Platform memory (Redis) | 5 minutes  | On revocation event            |
| Constraint envelopes | Platform memory (Redis) | 10 minutes | On constraint update event     |
| Posture levels       | Platform memory (Redis) | 15 minutes | On posture change event        |
| Agent health         | Platform memory (Redis) | 1 minute   | On health event                |
| Delegation tree      | Platform memory (Redis) | 5 minutes  | On delegation/revocation event |

### 8.2 Query Optimization

| Query Pattern             | Optimization                   | Index Required                     |
| ------------------------- | ------------------------------ | ---------------------------------- |
| Get chain by agent_id     | Indexed lookup                 | `(organization_id, agent_id)`      |
| List delegations by chain | Indexed lookup                 | `(chain_id, status)`               |
| Audit by time range       | Partitioned table              | `(organization_id, created_at)`    |
| Health by organization    | Materialized view              | Refresh on health event            |
| Delegation tree traversal | Recursive CTE with depth limit | `(delegator_id)`, `(delegatee_id)` |

### 8.3 Rate Limiting

| Operation                 | Rate Limit     | Scope            |
| ------------------------- | -------------- | ---------------- |
| Chain establishment       | 10/minute      | Per organization |
| Chain verification        | 1000/minute    | Per organization |
| Delegation creation       | 50/minute      | Per organization |
| Cascade revocation        | 5/minute       | Per organization |
| Audit query               | 100/minute     | Per user         |
| Event stream subscription | 10 connections | Per organization |

---

## 9. Testing Strategy

### 9.1 Integration Test Matrix

| Test Scenario              | Platform Component  | SDK Component               | Verification                |
| -------------------------- | ------------------- | --------------------------- | --------------------------- |
| Login establishes trust    | Session Service     | TrustOperations.establish() | Chain exists in SDK store   |
| Action verification        | EATPVerifier        | TrustOperations.verify()    | Correct allow/deny result   |
| Delegation with tightening | Delegation Service  | TrustOperations.delegate()  | Child constraints <= parent |
| Cascade revocation         | Revocation Engine   | PostgresTrustStore          | All affected agents revoked |
| Event emission             | Event Adapter       | Trust callbacks             | Events received on SSE      |
| Multi-tenant isolation     | API Gateway         | PostgresTrustStore          | Cross-org data invisible    |
| SSO claim mapping          | Genesis Service     | HumanOrigin creation        | All fields correctly mapped |
| Constraint compilation     | Constraint Compiler | ConstraintEnvelope          | Valid SDK format            |
| Circuit breaker            | Trust Service       | (Simulated failure)         | Graceful degradation        |

### 9.2 Test Infrastructure

Following the Kailash testing rules (NO MOCKING in Tier 2-3):

- **Tier 1 (Unit)**: Mock SDK interfaces, test mapping logic
- **Tier 2 (Integration)**: Real PostgreSQL, real SDK trust store, real event bus
- **Tier 3 (E2E)**: Real SSO (test provider), real platform API, real SDK, real browser

---

## 10. Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Production Environment                        │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Frontend   │  │   API        │  │   Worker     │          │
│  │   (React)    │  │   Gateway    │  │   Service    │          │
│  │              │  │   (Nexus)    │  │              │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                   │                   │
│         │    ┌────────────┴──────────────┐    │                  │
│         │    │     Platform Services      │    │                  │
│         │    │                            │    │                  │
│         │    │  ┌──────────┐ ┌─────────┐ │    │                  │
│         │    │  │ Genesis  │ │Revocatio│ │    │                  │
│         │    │  │ Service  │ │n Engine │ │    │                  │
│         │    │  └──────────┘ └─────────┘ │    │                  │
│         │    │  ┌──────────┐ ┌─────────┐ │    │                  │
│         │    │  │ EATP     │ │Constraint│ │   │                  │
│         │    │  │ Verifier │ │Compiler │ │    │                  │
│         │    │  └──────────┘ └─────────┘ │    │                  │
│         │    └────────────┬──────────────┘    │                  │
│         │                 │                   │                   │
│    ┌────┴─────────────────┴───────────────────┴─────┐           │
│    │              Event Bus (Redis Streams)           │           │
│    └────┬─────────────────┬───────────────────┬─────┘           │
│         │                 │                   │                   │
│    ┌────┴────┐       ┌────┴────┐        ┌────┴────┐            │
│    │ SDK     │       │Platform │        │ Cache   │            │
│    │ Trust   │       │ DataFlow│        │ (Redis) │            │
│    │ Store   │       │ DB      │        │         │            │
│    │(Postgres)│      │(Postgres)│       │         │            │
│    └─────────┘       └─────────┘        └─────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

**Database Separation**:

- SDK Trust Store: Dedicated PostgreSQL database (or schema) owned by SDK
- Platform DataFlow DB: Separate PostgreSQL database for platform models
- Both share the same PostgreSQL cluster but maintain logical isolation
- Event Bus: Redis Streams for real-time event distribution
- Cache: Redis for trust chain status caching

---

_Document Version: 1.0_
_Analysis Date: February 2026_
_Source: Enterprise-App developer docs + Kailash SDK trust module architecture + Integration patterns analysis_
_Author: Gap Analysis Agent_
