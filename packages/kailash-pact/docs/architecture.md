# Architecture

This document describes the internal architecture of the PACT governance framework.

## Overview

The GovernanceEngine is the single entry point for all governance decisions. It composes six subsystems into a thread-safe facade:

```
                        GovernanceEngine
                              |
              +---------------+---------------+
              |               |               |
         Compilation    Envelopes      Clearance
              |               |               |
         D/T/R Tree    Three-Layer      5-Level
         Addressing     Envelope      Classification
                          Model         + Posture
              |               |               |
              +-------+-------+-------+-------+
                      |               |
                   Access          Audit
                 Enforcement       Chain
                 (5 Steps)        (EATP)
```

## D/T/R Addressing

Every position in a PACT organization has a positional address built from three segment types:

- **D** (Department) -- an organizational unit
- **T** (Team) -- a functional team within a department
- **R** (Role) -- a position occupied by a person or agent

The core invariant: **every D or T must be immediately followed by exactly one R** (its head). This guarantees that every organizational unit has a single accountable person.

### Address Examples

```
D1-R1                         President (heads the first department)
D1-R1-D1-R1                   Provost (heads Academic Affairs under President)
D1-R1-D1-R1-D1-R1             Dean of Engineering (under Provost)
D1-R1-D1-R1-D1-R1-T1-R1       CS Chair (heads CS Department team)
D1-R1-D1-R1-D1-R1-T1-R1-R1    CS Faculty Member (reports to CS Chair)
```

### Compilation

The `compile_org()` function transforms a declarative OrgDefinition (departments, teams, roles with reports_to chains) into a CompiledOrg -- a flat dictionary of address-indexed OrgNodes. Compilation:

1. Validates all references (no dangling, no duplicates, no cycles)
2. Builds the parent-child tree from `reports_to_role_id` chains
3. Assigns positional addresses via depth-first traversal
4. Creates OrgNode entries for departments, teams, and roles
5. Freezes the result with MappingProxyType to prevent post-compilation mutation

Safety limits prevent resource exhaustion: max depth of 50, max 500 children per node, max 100,000 total nodes.

## Three-Layer Envelope Model

Operating envelopes define what a role is allowed to do. PACT uses a three-layer model:

### Layer 1: Role Envelope (Standing)

A RoleEnvelope is a persistent constraint boundary set by a supervisor for their direct report. It defines the maximum permissions for that role across five dimensions:

| Dimension         | What It Controls                         | Example                          |
| ----------------- | ---------------------------------------- | -------------------------------- |
| **Financial**     | Spending limits, approval thresholds     | max_spend_usd: 10000             |
| **Operational**   | Allowed/blocked actions, rate limits     | allowed_actions: [read, write]   |
| **Temporal**      | Active hours, blackout periods           | active_hours: 09:00-17:00        |
| **Data Access**   | Read/write paths, blocked data types     | read_paths: [/data/public]       |
| **Communication** | Internal-only flag, channel restrictions | allowed_channels: [email, slack] |

### Layer 2: Task Envelope (Ephemeral)

A TaskEnvelope is a temporary narrowing of the RoleEnvelope for a specific task. It expires automatically and cannot widen the standing boundaries. Use it when an agent needs temporarily reduced permissions for a sensitive operation.

### Layer 3: Effective Envelope (Computed)

The effective envelope is the intersection of all envelopes from the root to the target role, plus any active task envelope. The computation walks the accountability chain and intersects each dimension using deny-overrides:

- **Financial**: min() of all numeric limits
- **Operational**: set intersection of allowed actions; set union of blocked actions
- **Temporal**: overlap of operating windows; union of blackout periods
- **Data Access**: set intersection of allowed paths; set union of blocked data types
- **Communication**: set intersection of allowed channels; tighter restrictions win

### Monotonic Tightening

Child envelopes can only be equal to or more restrictive than parent envelopes. The Dean cannot give the CS Chair a higher spending limit than the Dean's own limit. This is enforced by `RoleEnvelope.validate_tightening()` which checks each dimension independently.

## Knowledge Clearance

Clearance is independent of authority. A junior specialist can hold higher clearance than a senior executive when the knowledge domain requires it.

### Five Levels

| Level        | Numeric Order | Description                   |
| ------------ | ------------- | ----------------------------- |
| PUBLIC       | 0             | Open information              |
| RESTRICTED   | 1             | Internal use only             |
| CONFIDENTIAL | 2             | Need-to-know basis            |
| SECRET       | 3             | Compartmented access required |
| TOP_SECRET   | 4             | Maximum protection            |

### Posture Ceiling

The effective clearance for any access decision is:

```
effective = min(role.max_clearance, POSTURE_CEILING[current_posture])
```

| Posture            | Ceiling      |
| ------------------ | ------------ |
| PSEUDO_AGENT       | PUBLIC       |
| SUPERVISED         | RESTRICTED   |
| SHARED_PLANNING    | CONFIDENTIAL |
| CONTINUOUS_INSIGHT | SECRET       |
| DELEGATED          | TOP_SECRET   |

Even a role with TOP_SECRET clearance cannot access SECRET data when operating at SUPERVISED posture.

### Compartments

For SECRET and TOP_SECRET items, the role must hold **all** compartments the item belongs to. Compartments are named (e.g., "human-subjects", "personnel", "student-records") and are independent of the classification level.

## 5-Step Access Enforcement Algorithm

The `can_access()` function implements a 5-step algorithm. Default is DENY (fail-closed).

**Step 1: Clearance Resolution**
Find the role's clearance. If missing or vetting status is not ACTIVE, deny immediately.

**Step 2: Classification Check**
Compute effective clearance (min of role clearance and posture ceiling). If effective clearance < item classification, deny.

**Step 3: Compartment Check**
For SECRET and TOP_SECRET items: if the item has compartments, the role must hold all of them. Missing any compartment means deny.

**Step 4: Containment Check** (5 sub-paths)

- **4a: Same unit** -- role is in the same D or T as the item owner
- **4b: Downward visibility** -- role address is a prefix of the item owner (supervisors see down)
- **4c: T-inherits-D** -- role in a team inherits access to its parent department's data
- **4d: KSP** -- a Knowledge Share Policy grants cross-unit access
- **4e: Bridge** -- a Cross-Functional Bridge grants role-level cross-boundary access

**Step 5: Default Deny**
If no access path was found in Step 4, deny.

## Verification Gradient

When an action is verified against an envelope, the result falls into one of four zones:

| Level             | Meaning                                         | Agent Behavior              |
| ----------------- | ----------------------------------------------- | --------------------------- |
| **AUTO_APPROVED** | Action is within all constraint dimensions      | Proceed silently            |
| **FLAGGED**       | Action is near a boundary (within 20% of limit) | Proceed with logged warning |
| **HELD**          | Action exceeds a soft limit                     | Pause for human approval    |
| **BLOCKED**       | Action violates a hard constraint               | Denied, cannot proceed      |

The GovernanceEngine's `verify_action()` method combines envelope enforcement and knowledge access checks. The most restrictive result wins.

## GovernanceEngine API

The engine exposes three categories of methods:

### Decision API

- `verify_action(role_address, action, context)` -- Primary decision endpoint. Returns a GovernanceVerdict.
- `check_access(role_address, knowledge_item, posture)` -- Knowledge access check. Returns an AccessDecision.
- `compute_envelope(role_address, task_id)` -- Compute effective envelope for a role.

### Query API

- `get_org()` -- Return the compiled organization.
- `get_node(address)` -- Look up a single node.
- `get_context(role_address, posture)` -- Create a frozen GovernanceContext for an agent.

### Mutation API

- `grant_clearance(role_address, clearance)` -- Grant clearance to a role.
- `revoke_clearance(role_address)` -- Revoke clearance from a role.
- `create_bridge(bridge)` -- Create a Cross-Functional Bridge.
- `create_ksp(ksp)` -- Create a Knowledge Share Policy.
- `set_role_envelope(envelope)` -- Set a standing role envelope.
- `set_task_envelope(envelope)` -- Set an ephemeral task envelope.

All methods are thread-safe (internal lock). All error paths are fail-closed (return BLOCKED or DENY). All mutations emit EATP audit anchors when an audit chain is configured.

## GovernanceContext (Anti-Self-Modification)

Agents receive a `GovernanceContext` -- a frozen (immutable) dataclass containing a snapshot of their governance state. They do NOT receive the GovernanceEngine. This is the anti-self-modification defense: agents can see their constraints but cannot change them.

```python
@dataclass(frozen=True)
class GovernanceContext:
    role_address: str
    posture: TrustPostureLevel
    effective_envelope: ConstraintEnvelopeConfig | None
    clearance: RoleClearance | None
    effective_clearance_level: ConfidentialityLevel | None
    allowed_actions: frozenset[str]
    compartments: frozenset[str]
    org_id: str
    created_at: datetime
```

Attempting `ctx.posture = TrustPostureLevel.DELEGATED` raises `FrozenInstanceError`.

## Cross-Functional Bridges

Bridges connect two roles across organizational boundaries. Three types:

| Type         | Duration                            | Use Case                                                     |
| ------------ | ----------------------------------- | ------------------------------------------------------------ |
| **Standing** | Permanent                           | Ongoing coordination (e.g., Provost-VP Admin budget reviews) |
| **Scoped**   | Time-limited with operational scope | Project-specific collaboration (e.g., joint research)        |
| **Ad-Hoc**   | One-time                            | Emergency access for a specific incident                     |

Bridges are role-level (not unit-level). If the VP Admin has a bridge, the Finance Director does NOT inherit it. Use KSPs for unit-level access sharing.

When `bilateral=True`, both roles can access each other's data. When `bilateral=False`, only role_a can access role_b's data (unilateral).

## Knowledge Share Policies (KSPs)

KSPs are directional unit-level access grants. Unlike bridges (role-to-role), KSPs work at the department/team level:

```
source_unit_address -> target_unit_address
```

The source shares knowledge with the target. The `max_classification` caps what level of data may be shared. KSPs are one-way: if Academic Affairs shares with HR, HR cannot read Academic data through the same KSP.

## Store Backends

All governance state (clearances, envelopes, bridges, KSPs, compiled orgs) is persisted through protocol-based stores:

| Store             | Memory                  | SQLite                  |
| ----------------- | ----------------------- | ----------------------- |
| EnvelopeStore     | MemoryEnvelopeStore     | SqliteEnvelopeStore     |
| ClearanceStore    | MemoryClearanceStore    | SqliteClearanceStore    |
| AccessPolicyStore | MemoryAccessPolicyStore | SqliteAccessPolicyStore |
| OrgStore          | MemoryOrgStore          | SqliteOrgStore          |

Memory stores are the default for testing and development. SQLite stores provide persistence:

```python
engine = GovernanceEngine(
    org_definition,
    store_backend="sqlite",
    store_url="/path/to/governance.db",
)
```

## EATP Audit Integration

When configured with an audit chain, every governance decision and mutation is recorded as an EATP audit anchor:

```python
from pact.trust.audit.pipeline import AuditChain

audit = AuditChain()
engine = GovernanceEngine(org_definition, audit_chain=audit)

# Now every verify_action, check_access, grant_clearance, etc.
# emits an audit record to the chain
```

Audit actions include: `verify_action`, `clearance_granted`, `clearance_revoked`, `bridge_established`, `ksp_created`, `envelope_created`.
