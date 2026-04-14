# PACT Governance -- Audit, Budget, Events, MCP, Stores, Configuration

Version: 0.8.1
Package: `kailash-pact` (kailash-pact extras) + `kailash.trust.pact` (core SDK)

Parent domain: PACT Governance Framework. This sub-spec covers the tamper-evident audit chain, budget enforcement and cost management, the event system, work tracking, MCP tool governance, store protocols and implementations, YAML/configuration schema, and thread-safety, fail-closed, bounded-collection, and immutability invariants. See `pact-addressing.md` for D/T/R addressing and `GovernanceEngine`, and `pact-envelopes.md` for envelopes, clearance, access enforcement, and the verification gradient.

---

## 13. Audit Chain

### 13.1 Purpose

Records all governance-layer decisions into a tamper-evident linked chain for compliance review and forensic analysis.

### 13.2 PactAuditAction Types

```python
class PactAuditAction(str, Enum):
    ENVELOPE_CREATED = "envelope_created"
    ENVELOPE_MODIFIED = "envelope_modified"
    CLEARANCE_GRANTED = "clearance_granted"
    CLEARANCE_REVOKED = "clearance_revoked"
    BARRIER_ENFORCED = "barrier_enforced"
    KSP_CREATED = "ksp_created"
    KSP_REVOKED = "ksp_revoked"
    BRIDGE_APPROVED = "bridge_approved"
    BRIDGE_ESTABLISHED = "bridge_established"
    BRIDGE_REVOKED = "bridge_revoked"
    ADDRESS_COMPUTED = "address_computed"
    VACANCY_DESIGNATED = "vacancy_designated"
    VACANCY_SUSPENDED = "vacancy_suspended"
    BRIDGE_CONSENT = "bridge_consent"
    BRIDGE_REJECTED = "bridge_rejected"
    CLEARANCE_TRANSITIONED = "clearance_transitioned"
    PLAN_SUSPENDED = "plan_suspended"
    PLAN_RESUMED = "plan_resumed"
    RESUME_CONDITION_UPDATED = "resume_condition_updated"
```

### 13.3 AuditAnchor

Each anchor contains:

- `anchor_id` -- unique identifier
- `sequence` -- 0-based position in chain
- `previous_hash` -- hash of previous anchor (None for genesis)
- `agent_id` -- agent that performed the action
- `action` -- the action performed
- `verification_level` -- PACT VerificationLevel
- `envelope_id` -- constraint envelope evaluated (if any)
- `result` -- action outcome
- `metadata` -- structured details
- `timestamp` -- when action occurred
- `content_hash` -- SHA-256 hash of this anchor's content (set by `seal()`)

### 13.4 AuditChain

Thread-safe (threading.Lock), tamper-evident linked chain. Each anchor's hash includes the previous anchor's hash, forming an integrity chain verifiable for tampering.

- `append(anchor)` -- seal the anchor (compute content_hash linking to previous) and append
- `verify()` -- walk the chain and verify hash integrity
- HMAC comparison uses `hmac.compare_digest()` (constant-time, no timing side-channel)

### 13.5 TieredAuditDispatcher (PACT-08)

Gradient-aligned persistence tiers. Different verification levels may route to different audit backends (in-memory for AUTO_APPROVED, persistent for BLOCKED).

### 13.6 Audit Details Helper

```python
create_pact_audit_details(action, *, role_address="", target_address="", reason="", step_failed=None, **extra) -> dict
```

Produces structured details suitable for EATP AuditAnchor metadata. Always includes `pact_action` and `role_address`. Other fields included only when non-empty.

---

## 14. Budget Enforcement and Cost Management

### 14.1 CostTracker

```python
class CostTracker:
    def __init__(self, budget_usd: float | None = None, cost_model: Any | None = None)
    def record(self, amount: float, description: str = "")
    @property
    def spent(self) -> float
    @property
    def remaining(self) -> float | None    # None if no budget
    @property
    def utilization(self) -> float | None  # 0.0-1.0+, None if no budget
    @property
    def history(self) -> list[dict]        # bounded to 10,000 entries
    @property
    def cost_model(self) -> Any | None
```

**Thread-safe:** All properties and `record()` acquire `self._lock`.

**NaN/Inf defense:** Both `__init__` and `record()` validate with `math.isfinite()`. Negative values rejected.

**Budget semantics:** `None` budget means unlimited (no constraint). `remaining` returns `max(0.0, budget - spent)` -- never negative. `utilization` with zero budget returns 1.0 if any spend occurred, 0.0 otherwise.

**History:** Bounded `deque(maxlen=10000)`. Each entry: `{amount, description, timestamp, cumulative}`.

### 14.2 PactEngine Budget Integration

PactEngine creates a CostTracker at init. During `submit()`:

1. Acquire submit lock (atomicity)
2. Check `self._costs.remaining` before execution
3. Execute work via supervisor
4. Validate `supervisor_result.budget_consumed` with `math.isfinite()` (NaN/Inf -> record as 0.0)
5. Record cost: `self._costs.record(cost_usd, description)`

### 14.3 Failure Modes

- NaN/Inf budget_usd -> ValueError at construction
- NaN/Inf record amount -> ValueError
- Negative values -> ValueError
- Over-budget detection: remaining budget checked before execution; concurrent safety via asyncio.Lock

---

## 15. Event System

### 15.1 EventBus

```python
class EventBus:
    def __init__(self, maxlen: int = 10000, max_subscribers: int = 1000)
    def subscribe(self, event_type: str, callback: Callable)
    def unsubscribe(self, event_type: str, callback: Callable) -> bool
    def emit(self, event_type: str, data: dict)
    def get_history(self, event_type: str | None = None) -> list[dict]
```

**Thread-safe:** All methods acquire `self._lock` (threading.Lock). Subscribers called OUTSIDE the lock to avoid deadlock.

**Bounded:** History uses `deque(maxlen=N)`, default 10,000.

**Subscriber limits:** Max 1,000 subscribers per event type. Exceeding raises `ValueError`.

**Error isolation:** Subscriber exceptions are logged and swallowed -- one failing subscriber does not block others.

### 15.2 Event Types

Events emitted by PactEngine during `submit()`:

| Event Type                 | When                                           |
| -------------------------- | ---------------------------------------------- |
| `work.submitted`           | Work submitted for governance                  |
| `work.governance_disabled` | DISABLED mode, governance skipped              |
| `work.governance_shadow`   | SHADOW mode, verdict computed but not enforced |
| `work.blocked`             | Governance blocked the action                  |
| `work.completed`           | Work execution completed (success or failure)  |
| `work.failed`              | Supervisor execution failed                    |

### 15.3 Event Record Format

```python
{
    "event_type": str,
    "data": dict,         # event-specific payload
    "timestamp": str       # ISO 8601 UTC
}
```

---

## 16. Work Tracking

### 16.1 WorkSubmission

```python
@dataclass(frozen=True)
class WorkSubmission:
    objective: str             # natural-language description
    role: str                  # D/T/R address
    context: dict = {}
    budget_usd: float | None = None
```

### 16.2 WorkResult

```python
@dataclass(frozen=True)
class WorkResult:
    success: bool
    results: dict = {}
    cost_usd: float = 0.0
    budget_allocated: float | None = None
    events: list[dict] = []
    audit_trail: list[dict] = []          # [{timestamp, event, role_address, details}]
    error: str | None = None
    governance_shadow: bool = False
    governance_verdicts: list[dict] = []
```

**NaN safety:** `__post_init__` validates `cost_usd` and `budget_allocated` with `math.isfinite()`. Non-finite `cost_usd` clamped to 0.0 with warning. Non-finite `budget_allocated` set to None with warning.

**Serialization:** `to_dict()` / `from_dict()` roundtrip. `from_dict()` validates financial fields via `_validated_cost()`.

### 16.3 Audit Trail Format

Each entry in `WorkResult.audit_trail`:

```python
{
    "timestamp": str,          # ISO 8601 UTC
    "event": str,              # e.g., "submission_received", "governance_verified"
    "role_address": str,
    "details": dict
}
```

---

## 17. MCP Tool Governance

### 17.1 Purpose

MCP has zero built-in governance. PACT for MCP adds deterministic governance enforcement as a middleware layer.

### 17.2 McpToolPolicy

```python
@dataclass(frozen=True)
class McpToolPolicy:
    tool_name: str
    allowed_args: frozenset[str] = frozenset()    # empty = all allowed
    denied_args: frozenset[str] = frozenset()     # takes precedence
    max_cost: float | None = None                  # USD per invocation
    clearance_required: str | None = None
    rate_limit: int | None = None                  # max invocations per minute
    description: str = ""
```

**Validation:** `tool_name` must be non-empty. `max_cost` must be finite and non-negative. `rate_limit` must be >= 1.

### 17.3 McpGovernanceConfig

```python
@dataclass(frozen=True)
class McpGovernanceConfig:
    default_policy: DefaultPolicy = DefaultPolicy.DENY    # DENY or ALLOW for unregistered
    tool_policies: dict[str, McpToolPolicy]               # MappingProxyType (immutable)
    audit_enabled: bool = True
    max_audit_entries: int = 10_000
```

Config dict keys must match policy `tool_name`. `tool_policies` dict replaced with `MappingProxyType` at construction for immutability.

### 17.4 McpGovernanceEnforcer

The core enforcement engine for MCP tool calls.

**Security invariants:**

1. Default-deny for unregistered tools
2. NaN/Inf defense on all numeric fields
3. Thread-safe (all shared state under `self._lock`)
4. Fail-closed (all error paths return BLOCKED)
5. Bounded collections

**Evaluation steps:**

1. Check tool registration (default-deny for unregistered)
2. Validate `cost_estimate` (NaN/Inf -> BLOCKED)
3. Check argument constraints (`denied_args` first, then `allowed_args`)
4. Check cost constraints (`cost_estimate > max_cost` -> BLOCKED; within 20% of max -> FLAGGED)
5. Check rate limits (per-minute sliding window, per agent+tool)
6. All passed -> AUTO_APPROVED

**Rate limiting:** Per `agent_id:tool_name` key. Uses bounded deque per key, max 10,000 total rate tracker entries with oldest-10% eviction.

**Runtime tool registration:** `register_tool(policy)` enforces monotonic tightening against existing policy:

- `max_cost`: new must be <= existing
- `rate_limit`: new must be <= existing
- `allowed_args`: new must be subset
- `denied_args`: new must be superset

### 17.5 McpGovernanceMiddleware

```python
class McpGovernanceMiddleware:
    def __init__(self, enforcer, handler: Callable[..., Awaitable])
    async def invoke(self, tool_name, args=None, agent_id="", *, cost_estimate=None, metadata=None) -> McpInvocationResult
```

Intercepts MCP tool calls. If governance allows (AUTO_APPROVED or FLAGGED), forwards to handler. If HELD or BLOCKED, returns without calling handler. Handler errors captured without affecting governance decision.

### 17.6 McpInvocationResult

```python
class McpInvocationResult:
    decision: GovernanceDecision
    tool_result: Any | None
    tool_error: str | None
    executed: bool              # True if handler was called and succeeded
```

### 17.7 GovernanceDecision

```python
@dataclass(frozen=True)
class GovernanceDecision:
    level: str                  # "auto_approved", "flagged", "held", "blocked"
    tool_name: str
    agent_id: str
    reason: str
    timestamp: datetime
    policy_snapshot: dict | None
    metadata: dict
```

`decision.allowed` -- True for AUTO_APPROVED or FLAGGED.

### 17.8 McpAuditTrail

Bounded, append-only audit trail using `deque(maxlen=N)`. Thread-safe.

```python
class McpAuditTrail:
    def record(*, tool_name, agent_id, decision, reason="", cost_estimate=None, metadata=None) -> McpAuditEntry
    def to_list() -> list[McpAuditEntry]
    def get_by_agent(agent_id) -> list[McpAuditEntry]
    def get_by_tool(tool_name) -> list[McpAuditEntry]
    def get_by_decision(decision) -> list[McpAuditEntry]
    def clear()
```

`McpAuditEntry` is frozen with immutable metadata (MappingProxyType).

### 17.9 Failure Modes

- Unregistered tool + DENY policy -> BLOCKED
- NaN/Inf cost_estimate -> BLOCKED
- Negative cost_estimate -> BLOCKED
- Denied args present -> BLOCKED
- Disallowed args present -> BLOCKED
- Cost exceeds max_cost -> BLOCKED
- Rate limit exceeded -> BLOCKED
- Internal error -> BLOCKED (fail-closed)
- Monotonic tightening violation on register_tool -> ValueError

---

## 18. Store Protocols and Implementations

### 18.1 Protocols

```python
class OrgStore(Protocol):
    def save_org(self, org: CompiledOrg) -> None
    def load_org(self, org_id: str) -> CompiledOrg | None
    def get_node(self, org_id: str, address: str) -> OrgNode | None
    def query_by_prefix(self, org_id: str, prefix: str) -> list[OrgNode]

class EnvelopeStore(Protocol):
    def save_role_envelope(self, envelope: RoleEnvelope) -> None
    def get_role_envelope(self, target_role_address: str) -> RoleEnvelope | None
    def save_task_envelope(self, envelope: TaskEnvelope) -> None
    def get_active_task_envelope(self, role_address: str, task_id: str) -> TaskEnvelope | None
    def get_ancestor_envelopes(self, role_address: str) -> dict[str, RoleEnvelope]

class ClearanceStore(Protocol):
    def grant_clearance(self, clearance: RoleClearance) -> None
    def get_clearance(self, role_address: str) -> RoleClearance | None
    def revoke_clearance(self, role_address: str) -> None

class AccessPolicyStore(Protocol):
    def save_ksp(self, ksp: KnowledgeSharePolicy) -> None
    def find_ksp(self, source_prefix: str, target_prefix: str) -> KnowledgeSharePolicy | None
    def list_ksps(self) -> list[KnowledgeSharePolicy]
    def save_bridge(self, bridge: PactBridge) -> None
    def find_bridge(self, role_a_address: str, role_b_address: str) -> PactBridge | None
    def list_bridges(self) -> list[PactBridge]
```

### 18.2 Memory Implementations

All use `OrderedDict` with bounded size (`MAX_STORE_SIZE = 10,000`). Eviction: oldest entries removed when capacity exceeded.

- `MemoryOrgStore`
- `MemoryEnvelopeStore`
- `MemoryClearanceStore`
- `MemoryAccessPolicyStore`

### 18.3 SQLite Implementations

Located in `kailash.trust.pact.stores.sqlite`. Parameterized SQL (no injection). File permissions 0o600 (owner read/write only). Available via `store_backend="sqlite"` + `store_url="/path/to/db"`.

- `SqliteOrgStore`
- `SqliteEnvelopeStore`
- `SqliteClearanceStore`
- `SqliteAccessPolicyStore`
- `SqliteAuditLog`

---

## 19. YAML Configuration

### 19.1 Loading

`load_org_yaml(path: str | Path) -> LoadedOrg` loads an organization definition from a YAML file. Returns a `LoadedOrg` containing:

- `org_definition: OrgDefinition`
- Optional clearance specs, envelope specs, bridge specs, KSP specs

### 19.2 OrgDefinition

```python
class OrgDefinition:
    org_id: str
    name: str
    departments: list[DepartmentConfig]
    teams: list[TeamConfig]
    roles: list[RoleDefinition]
```

### 19.3 Dict Construction

PactEngine also accepts a raw dict for org definition:

```python
engine = PactEngine(org={
    "org_id": "acme",
    "name": "Acme Corp",
    "departments": [{"id": "eng", "name": "Engineering"}],
    "teams": [{"id": "backend", "name": "Backend"}],
    "roles": [{"id": "dev1", "name": "Developer", "reports_to": "eng-head"}],
})
```

---

## 20. Configuration Schema

### 20.1 ConstraintEnvelopeConfig

The top-level envelope configuration (Pydantic model, frozen=True):

- `financial: FinancialConstraintConfig | None`
- `operational: OperationalConstraintConfig | None`
- `temporal: TemporalConstraintConfig | None`
- `data_access: DataAccessConstraintConfig | None`
- `communication: CommunicationConstraintConfig | None`
- `confidentiality_clearance: ConfidentialityLevel | None`
- `max_delegation_depth: int | None`
- `gradient: GradientThresholdsConfig | None`
- `verification_gradient: VerificationGradientConfig | None`

### 20.2 PactConfig

Top-level PACT configuration:

- `genesis: GenesisConfig`
- `platform: PlatformConfig`
- `org: OrgDefinition`
- `agents: list[AgentConfig]`
- `workspaces: list[WorkspaceConfig]`

### 20.3 AgentConfig

Per-agent configuration:

- `agent_id: str`
- `role_address: str`
- `model: str | None`
- `posture: TrustPostureLevel`

---

## 21. Thread-Safety Summary

| Component             | Lock Type        | Scope                                                      |
| --------------------- | ---------------- | ---------------------------------------------------------- |
| GovernanceEngine      | `threading.Lock` | All public methods                                         |
| CostTracker           | `threading.Lock` | `record()`, `spent`, `remaining`, `utilization`, `history` |
| EventBus              | `threading.Lock` | `subscribe`, `unsubscribe`, `emit`, `get_history`          |
| McpGovernanceEnforcer | `threading.Lock` | Policy overlay, rate tracking                              |
| McpAuditTrail         | `threading.Lock` | `record`, `to_list`, query methods                         |
| PactEngine.submit()   | `asyncio.Lock`   | check-remaining -> execute -> record-cost atomicity        |

All subscriber callbacks are called OUTSIDE locks to avoid deadlock.

---

## 22. Fail-Closed Behavior Summary

Every governance decision point is fail-closed. The table below enumerates what happens when governance cannot decide.

| Decision Point                              | Error Behavior                    |
| ------------------------------------------- | --------------------------------- |
| `GovernanceEngine.verify_action()`          | Exception -> BLOCKED verdict      |
| `GovernanceEngine.check_access()`           | Exception -> DENY (step_failed=0) |
| `KnowledgeFilter.filter_before_retrieval()` | Exception -> DENY (fail-closed)   |
| `KnowledgeFilter` returns wrong type        | DENY (fail-closed)                |
| `GradientEngine.evaluate()`                 | Exception -> BLOCKED              |
| `McpGovernanceEnforcer.check_tool_call()`   | Exception -> BLOCKED              |
| `PactEngine.submit()` governance error      | BLOCKED WorkResult                |
| `PactEngine.submit()` execution error       | Failed WorkResult                 |
| Missing envelope                            | Maximally restrictive defaults    |
| Missing clearance                           | Access denied (step 1)            |
| NaN/Inf in cost                             | Rejected or clamped to 0.0        |

---

## 23. Bounded Collections Summary

All long-lived collections are bounded to prevent memory exhaustion (OOM) in long-running processes.

| Collection               | Bound                 | Eviction                   |
| ------------------------ | --------------------- | -------------------------- |
| EventBus history         | 10,000 (configurable) | FIFO (deque maxlen)        |
| CostTracker history      | 10,000                | FIFO (deque maxlen)        |
| McpAuditTrail entries    | 10,000 (configurable) | FIFO (deque maxlen)        |
| Store entries (Memory\*) | 10,000                | Oldest first (OrderedDict) |
| Bridge approvals         | 10,000                | Oldest first (OrderedDict) |
| Vacancy designations     | 10,000                | Dict (bounded by check)    |
| Plan suspensions         | 10,000                | Dict (bounded by check)    |
| Envelope cache           | 10,000                | LRU (OrderedDict)          |
| Rate tracker entries     | 10,000                | Oldest 10% eviction        |
| EventBus subscribers     | 1,000 per event type  | Raises ValueError          |

---

## 24. Immutability Summary

All governance data structures are frozen to prevent post-construction mutation.

| Type                   | Immutability Mechanism                       |
| ---------------------- | -------------------------------------------- |
| `GovernanceVerdict`    | `@dataclass(frozen=True)`                    |
| `AccessDecision`       | `@dataclass(frozen=True)`                    |
| `GovernanceContext`    | `@dataclass(frozen=True)` + pickle blocked   |
| `RoleClearance`        | `@dataclass(frozen=True)`                    |
| `KnowledgeItem`        | `@dataclass(frozen=True)`                    |
| `KnowledgeSharePolicy` | `@dataclass(frozen=True)`                    |
| `PactBridge`           | `@dataclass(frozen=True)`                    |
| `BridgeApproval`       | `@dataclass(frozen=True)`                    |
| `VacancyDesignation`   | `@dataclass(frozen=True)`                    |
| `WorkSubmission`       | `@dataclass(frozen=True)`                    |
| `WorkResult`           | `@dataclass(frozen=True)`                    |
| `McpToolPolicy`        | `@dataclass(frozen=True)`                    |
| `McpGovernanceConfig`  | `@dataclass(frozen=True)` + MappingProxyType |
| `McpActionContext`     | `@dataclass(frozen=True)` + MappingProxyType |
| `McpAuditEntry`        | `@dataclass(frozen=True)` + MappingProxyType |
| `AddressSegment`       | `@dataclass(frozen=True)`                    |
| `Address`              | `@dataclass(frozen=True)`                    |
| `RoleDefinition`       | `@dataclass(frozen=True)`                    |
| All constraint configs | Pydantic `frozen=True`                       |
