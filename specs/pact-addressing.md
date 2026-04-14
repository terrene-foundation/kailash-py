# PACT Governance -- Addressing, Compilation, and Engine

Version: 0.8.1
Package: `kailash-pact` (kailash-pact extras) + `kailash.trust.pact` (core SDK)

Parent domain: PACT Governance Framework. This sub-spec covers the D/T/R addressing grammar, organization compilation into the runtime structure, and the `GovernanceEngine` facade that is the single entry point for all PACT governance decisions. See `pact-envelopes.md` for envelope and clearance semantics, and `pact-enforcement.md` for audit, budget, events, MCP governance, and stores.

Architecture split:

- `kailash.trust.pact` (core SDK) -- D/T/R grammar, addressing, clearance, access, envelopes, compilation, engine, audit, gradient, context, stores, agent, decorators, middleware
- `pact.*` (kailash-pact package) -- PactEngine (Dual Plane bridge), CostTracker, EventBus, WorkResult/WorkSubmission, enforcement modes, MCP governance, REST API, CLI, testing utilities

---

## 1. D/T/R Addressing Model

### 1.1 Purpose

Every entity in a PACT organization has a globally unique positional address encoding both containment (who is inside what) and accountability (who is responsible for what). The address grammar is the foundation for all governance decisions.

### 1.2 Node Types

```python
class NodeType(str, Enum):
    DEPARTMENT = "D"  # Organizational unit (division, department)
    TEAM = "T"        # Working unit within a department
    ROLE = "R"        # Accountability anchor -- a position occupied by a person or agent
```

### 1.3 Address Grammar

Format: `D1-R1-D3-R1-T1-R1`

**Core invariant: every D or T segment MUST be immediately followed by exactly one R segment.** This is enforced by a state machine validator at parse time.

Grammar state machine:

- State 0 (initial / after R): Accept D, T, or R
- State 1 (after D or T): MUST see R next

Violations:

- `D1-D2` -- D not followed by R (GrammarError)
- `D1-T1` -- D not followed by R (GrammarError)
- `D1-R1-T1` -- address ends with T, no trailing R (GrammarError)
- `D1` -- address ends with D, no trailing R (GrammarError)

### 1.4 AddressSegment

```python
@dataclass(frozen=True)
class AddressSegment:
    node_type: NodeType
    sequence: int  # 1-based within parent scope
```

`AddressSegment.parse("D1")` parses a single segment. Validates: non-empty, valid type char (D/T/R, case-insensitive), valid positive integer sequence.

### 1.5 Address

```python
@dataclass(frozen=True)
class Address:
    segments: tuple[AddressSegment, ...]
```

**API:**

- `Address.parse("D1-R1-T1-R1")` -- parse and validate full address string
- `Address.from_segments(seg1, seg2, ...)` -- construct from segments with grammar validation
- `address.depth` -- number of segments
- `address.parent` -- structural parent (segments[:-1]), NOT grammar-validated (intermediate addresses like `D1` are valid as containment references)
- `address.containment_unit` -- nearest ancestor D or T address
- `address.accountability_chain` -- all R segments in order, representing the chain of accountable people from root to leaf
- `address.last_segment` -- final segment
- `address.is_prefix_of(other)` -- strict prefix check
- `address.is_ancestor_of(other)` -- reflexive prefix check (includes equality)
- `address.ancestors()` -- all ancestor addresses from root to parent (not including self)
- `Address.lowest_common_ancestor(addr_a, addr_b)` -- deepest Address that appears in both accountability chains, or None if disjoint

### 1.6 Error Hierarchy

- `PactError` -- base PACT error, inherits from `TrustError`
- `AddressError(PactError, ValueError)` -- malformed address
- `GrammarError(AddressError)` -- D/T/R grammar violation
- `CompilationError(PactError)` -- org compilation structural error
- `ConfigurationError(PactError)` -- YAML/config error
- `MonotonicTighteningError(PactError, ValueError)` -- envelope tightening violation
- `EnvelopeAdapterError(PactError)` -- envelope adapter error
- `GovernanceBlockedError(PactError)` -- governance blocks an action
- `GovernanceHeldError(PactError)` -- governance holds an action for human review

All PACT errors carry `.details: dict[str, Any]` for structured audit context.

### 1.7 Failure Modes

- Empty address string -> `AddressError`
- Invalid type character (e.g., `X1`) -> `AddressError`
- Non-positive sequence (e.g., `D0`) -> `AddressError`
- Grammar violation -> `GrammarError` with positional detail
- Address without terminal R -> `GrammarError`

---

## 2. Organization Compilation

### 2.1 Purpose

Transforms a declarative `OrgDefinition` (departments, teams, roles) into an address-indexed `CompiledOrg` -- the runtime structure used for address resolution, envelope enforcement, clearance checks, and audit anchoring.

### 2.2 Compilation Limits

Enforced to prevent resource exhaustion from malformed or adversarial org trees:

| Limit                   | Value   | Effect                                     |
| ----------------------- | ------- | ------------------------------------------ |
| `MAX_COMPILATION_DEPTH` | 50      | Maximum address depth (number of segments) |
| `MAX_CHILDREN_PER_NODE` | 500     | Maximum direct children per role           |
| `MAX_TOTAL_NODES`       | 100,000 | Maximum total nodes in compiled org        |

Exceeding any limit raises `CompilationError`.

### 2.3 Key Types

```python
@dataclass(frozen=True)
class RoleDefinition:
    role_id: str
    name: str
    reports_to_role_id: str | None = None
    is_primary_for_unit: str | None = None  # heads which dept/team
    unit_id: str | None = None
    is_vacant: bool = False
    is_external: bool = False  # external governance-only role
    agent_id: str | None = None
    address: str | None = None  # set during compilation

@dataclass(frozen=True)
class OrgNode:
    address: str
    node_type: NodeType
    name: str
    is_vacant: bool = False
    is_external: bool = False

@dataclass
class CompiledOrg:
    org_id: str
    nodes: dict[str, OrgNode]  # address -> OrgNode
```

### 2.4 VacancyDesignation (Section 5.5)

When a role is vacant, the parent role must designate an acting occupant within a configurable deadline (default 24 hours). If no designation is made, all downstream agents of the vacant role are auto-suspended.

```python
@dataclass(frozen=True)
class VacancyDesignation:
    vacant_role_address: str
    acting_role_address: str
    designated_by: str      # parent role that made designation
    designated_at: str      # ISO 8601
    expires_at: str         # ISO 8601 (24h default)
```

The acting occupant inherits the vacant role's envelope (constraints) but does NOT receive clearance upgrades.

### 2.5 API

`compile_org(org_definition) -> CompiledOrg` -- compiles an OrgDefinition into address-indexed nodes. Raises `CompilationError` on structural issues (duplicate IDs, missing parent references, limit violations).

---

## 3. GovernanceEngine

### 3.1 Purpose

The single entry point for all PACT governance decisions. Composes compilation, envelopes, clearance, access enforcement, gradient evaluation, and audit into a thread-safe facade. Every public method acquires `self._lock`.

### 3.2 Constructor

```python
class GovernanceEngine:
    def __init__(
        self,
        org: OrgDefinition | CompiledOrg,
        *,
        envelope_store: EnvelopeStore | None = None,
        clearance_store: ClearanceStore | None = None,
        access_policy_store: AccessPolicyStore | None = None,
        org_store: OrgStore | None = None,
        audit_chain: AuditChain | None = None,
        store_backend: str = "memory",      # "memory" or "sqlite"
        store_url: str | None = None,        # path for sqlite backend
        eatp_emitter: PactEatpEmitter | None = None,
        knowledge_filter: KnowledgeFilter | None = None,
        envelope_cache_ttl_seconds: float | None = None,
        audit_dispatcher: TieredAuditDispatcher | None = None,
        observation_sink: ObservationSink | None = None,
        vacancy_deadline_hours: int = 24,
        require_bilateral_consent: bool = False,
    )
```

**Store backends:**

- `"memory"` (default) -- in-memory OrderedDict stores with bounded size (`MAX_STORE_SIZE = 10,000`), evicts oldest entries on overflow
- `"sqlite"` -- persisted SQLite stores (requires `store_url`), parameterized SQL, file permissions 0o600

If `store_backend="sqlite"` and `store_url=None`, raises `ValueError`.

**At init time:**

- Compiles org if `OrgDefinition` provided; uses directly if `CompiledOrg`
- Saves compiled org to org store
- Initializes vacancy start times for roles that are vacant at compilation
- Emits EATP GenesisRecord if `eatp_emitter` configured
- Initializes bounded envelope cache (`OrderedDict`, max 10,000 entries)
- Initializes bounded bridge approvals (`OrderedDict`, max 10,000)
- Initializes bounded suspensions (`dict`, max 10,000)

### 3.3 Decision API

#### `verify_action(role_address, action, context=None) -> GovernanceVerdict`

The primary decision method. Combines vacancy check + envelope evaluation + gradient classification + access check. Thread-safe, fail-closed.

**Steps:** 0. Vacancy check (Section 5.5): if role or ancestor is vacant without valid acting occupant, BLOCK

1. Compute effective envelope for `role_address`
2. Evaluate action against envelope constraint dimensions via GradientEngine
3. Classify result into gradient zones (AUTO_APPROVED / FLAGGED / HELD / BLOCKED)
4. If context has `"resource"` (KnowledgeItem), run `check_access` for knowledge clearance
5. Combine envelope verdict + access verdict (most restrictive wins)
6. Emit audit anchor with full details
7. Return `GovernanceVerdict`

**Fail-closed contract:** Any exception during verification returns a BLOCKED verdict. Never raises to caller.

#### `check_access(role_address, knowledge_item, posture, *, query=None) -> AccessDecision`

5-step access enforcement algorithm. Thread-safe, fail-closed.

Pre-step: If a `KnowledgeFilter` is configured, evaluate query scope BEFORE data retrieval. Filter errors are fail-closed to DENY.

Steps 1-5: See Section 6 (Access Enforcement).

**Fail-closed contract:** Any exception returns `AccessDecision(allowed=False, reason="Internal error...", step_failed=0)`.

#### `compute_envelope(role_address) -> ConstraintEnvelopeConfig | None`

Resolve the effective constraint envelope for a role address. Returns `None` if no envelope is assigned. Uses bounded LRU cache with optional TTL.

#### `get_context(role_address, posture) -> GovernanceContext`

Build a frozen, read-only governance snapshot for agent consumption. The returned `GovernanceContext` is the ONLY governance state visible to agents.

### 3.4 Mutation API

All mutation methods acquire `self._lock`, invalidate affected cache entries via prefix-based cascade, and emit audit anchors.

- `set_role_envelope(role_address, envelope)` -- assign a role envelope (monotonic tightening enforced)
- `set_task_envelope(role_address, task_id, envelope)` -- assign a task-scoped envelope (monotonic tightening against role envelope)
- `grant_clearance(clearance: RoleClearance)` -- grant knowledge clearance to a role
- `revoke_clearance(role_address)` -- revoke knowledge clearance
- `transition_clearance(role_address, new_status)` -- FSM transition of vetting status
- `create_bridge(bridge: PactBridge)` -- create a cross-functional bridge (requires LCA approval)
- `approve_bridge(source, target, approver)` -- LCA approves a bridge (24h TTL)
- `consent_bridge(role_address, partner_address)` -- bilateral consent for bridge (when `require_bilateral_consent=True`)
- `reject_bridge(source, target, rejector, reason)` -- reject a bridge proposal
- `create_ksp(ksp: KnowledgeSharePolicy)` -- create a knowledge share policy
- `designate_acting_occupant(vacant, acting, designated_by)` -- vacancy acting occupant designation
- `register_compliance_role(role_address)` -- register alternative bridge approver

### 3.5 Read-Only View

```python
class _ReadOnlyGovernanceView:
    """Proxies read-only methods; blocks mutation methods."""
```

Exposed via `PactEngine.governance` property. Blocks: `set_role_envelope`, `set_task_envelope`, `grant_clearance`, `revoke_clearance`, `transition_clearance`, `compile_org`, `create_bridge`, `approve_bridge`, `consent_bridge`, `reject_bridge`, `register_compliance_role`, `create_ksp`, `designate_acting_occupant`.

### 3.6 Thread-Safety Guarantees

- All public methods acquire `self._lock` (threading.Lock) before accessing shared state
- Subscriber callbacks in EventBus are called OUTSIDE the lock to avoid deadlock
- Cost recording in CostTracker has its own lock
- MCP enforcer has its own lock for rate tracking and policy overlay

### 3.7 Failure Modes

- Unknown role address -> BLOCKED verdict (not an error -- fail-closed)
- Missing envelope -> maximally restrictive defaults (no spending, no actions, no data access, 60s timeout, no delegation)
- NaN/Inf in financial fields -> ValueError at construction; runtime detection returns BLOCKED
- Compilation limit exceeded -> CompilationError
- Invalid store_backend -> ValueError
- vacancy_deadline_hours <= 0 -> ValueError

---

