# PACT Governance -- Envelopes, Clearance, Access, and Gradient

Version: 0.8.1
Package: `kailash-pact` (kailash-pact extras) + `kailash.trust.pact` (core SDK)

Parent domain: PACT Governance Framework. This sub-spec covers operating envelopes (five constraint dimensions), knowledge clearance, the 5-step access enforcement algorithm, the verification gradient, `GovernanceVerdict`, `GovernanceContext`, `PactGovernedAgent`, `PactEngine` (Dual Plane bridge), and enforcement modes. See `pact-addressing.md` for D/T/R addressing and `GovernanceEngine`, and `pact-enforcement.md` for audit, budget, events, MCP governance, and stores.

---

## 4. Operating Envelopes

### 4.1 Purpose

Operating envelopes define the boundaries within which an agent may act. They constrain five dimensions: financial, operational, temporal, data access, and communication. The envelope model is three-layered with a monotonic tightening invariant.

### 4.2 Three-Layer Model

1. **Role Envelope** (`RoleEnvelope`) -- standing constraints attached to a D/T/R position. Persists across tasks.
2. **Task Envelope** (`TaskEnvelope`) -- ephemeral constraints scoped to a specific task. More restrictive than or equal to the role envelope.
3. **Effective Envelope** -- computed intersection of role and task envelopes. This is what governance decisions use.

### 4.3 Five Constraint Dimensions

**Layering note:** `FinancialConstraintConfig` etc. (this spec) are governance-facing configuration types with a simplified field set. The trust-plane EATP layer uses richer `FinancialConstraint` types (see `specs/trust-eatp.md` section 4.2) with additional fields. The config types map to the protocol types at runtime; the protocol types are a superset.

#### Financial (`FinancialConstraintConfig`)

- `max_spend_usd: float` (>= 0) -- maximum USD spend allowed
- `api_cost_budget_usd: float | None` (>= 0) -- LLM API cost budget per billing period
- `requires_approval_above_usd: float | None` (>= 0) -- threshold requiring human approval
- `reasoning_required: bool` -- whether actions touching this dimension need a reasoning trace

All numeric fields validated with `math.isfinite()` -- NaN/Inf rejected at construction.

#### Operational (`OperationalConstraintConfig`)

- `allowed_actions: list[str]` -- actions the agent may perform (empty = all)
- `blocked_actions: list[str]` -- actions explicitly blocked (takes precedence over allowed)
- `max_actions_per_day: int | None` (> 0) -- daily action rate limit
- `max_actions_per_hour: int | None` (> 0) -- hourly rate limit (sliding window)
- `rate_limit_window_type: str` -- `"fixed"` (calendar) or `"rolling"` (sliding window)

#### Temporal (`TemporalConstraintConfig`)

- `active_hours_start: str | None` -- start of active window (HH:MM, 24h format)
- `active_hours_end: str | None` -- end of active window
- `timezone: str` -- timezone for active hours (default "UTC")
- `blackout_periods: list[str]` -- periods when agent must not operate

#### Data Access (`DataAccessConstraintConfig`)

- `allowed_data_paths: list[str]` -- resource paths the agent may access
- `denied_data_paths: list[str]` -- explicitly denied resource paths
- `max_data_classification: str | None` -- maximum data classification level

#### Communication (`CommunicationConstraintConfig`)

- `allowed_channels: list[str]` -- communication channels permitted
- `external_requires_approval: bool` -- whether external communication needs approval
- `max_message_length: int | None` -- maximum message length

### 4.4 Monotonic Tightening Invariant

**A child envelope can NEVER be more permissive than its parent.** This is the core security invariant.

`intersect_envelopes(parent, child) -> ConstraintEnvelopeConfig` takes the min/intersection of every field:

- Numeric fields: `min(parent, child)` (None = unbounded/permissive)
- Set fields: intersection (allowed_actions, allowed_channels)
- Confidentiality: lower (more restrictive) level wins
- Boolean flags: `True` wins over `False` for restrictive flags

Violation raises `MonotonicTighteningError`.

### 4.5 Envelope Intersection Details

- `_min_optional(a, b)` -- None treated as unbounded; returns the tighter value
- `_min_confidentiality(a, b)` -- returns the lower (more restrictive) confidentiality level
- Financial: min of `max_spend_usd`, `api_cost_budget_usd`, `requires_approval_above_usd`
- Operational: intersection of `allowed_actions`, union of `blocked_actions`, min of rate limits
- Temporal: strictest active hours window (intersection of time ranges)
- Data Access: intersection of `allowed_data_paths`, union of `denied_data_paths`, min classification
- Communication: intersection of `allowed_channels`, OR of `external_requires_approval`

### 4.6 Default Envelopes by Posture

`default_envelope_for_posture(posture: TrustPostureLevel) -> ConstraintEnvelopeConfig` provides sensible defaults ranging from maximally restrictive (PSEUDO) to maximally permissive (AUTONOMOUS).

### 4.7 Degenerate Envelope Detection

`check_degenerate_envelope(envelope) -> list[str]` scans for envelopes that are effectively useless (e.g., zero allowed actions, zero budget, mutually exclusive constraints). Returns a list of warning strings. PactEngine checks all role envelopes at init time and logs warnings.

### 4.8 Envelope Caching

The engine maintains a bounded LRU cache (`OrderedDict`, max 10,000 entries) keyed by `(role_address, task_id)`. Cache is invalidated via prefix-based cascade when envelopes are mutated (setting a role envelope at `D1-R1` invalidates all cached entries starting with `D1-R1`).

### 4.9 Failure Modes

- NaN/Inf in any numeric field -> `ValueError` at construction
- Monotonic tightening violation -> `MonotonicTighteningError` with details
- Missing envelope for a role -> returns `None`; PactEngine applies maximally restrictive defaults
- Passthrough envelope (all fields empty/None) -> detected by `check_passthrough_envelope()`

---

## 5. Knowledge Clearance

### 5.1 Purpose

Per-role classification access independent of organizational authority. A junior role can hold higher clearance than a senior role if the knowledge domain requires it. Clearance is orthogonal to seniority.

### 5.2 Clearance Levels

Ordered from least to most restrictive:

| Level          | Order |
| -------------- | ----- |
| `PUBLIC`       | 0     |
| `RESTRICTED`   | 1     |
| `CONFIDENTIAL` | 2     |
| `SECRET`       | 3     |
| `TOP_SECRET`   | 4     |

### 5.3 Posture Ceiling

Even a role with TOP_SECRET clearance cannot access SECRET data if operating at a lower posture. The effective clearance is `min(role.max_clearance, POSTURE_CEILING[current_posture])`.

| Posture    | Ceiling      |
| ---------- | ------------ |
| PSEUDO     | PUBLIC       |
| TOOL       | RESTRICTED   |
| SUPERVISED | CONFIDENTIAL |
| DELEGATING | SECRET       |
| AUTONOMOUS | TOP_SECRET   |

### 5.4 RoleClearance

```python
@dataclass(frozen=True)
class RoleClearance:
    role_address: str
    max_clearance: ConfidentialityLevel
    compartments: frozenset[str]          # named compartments (SECRET/TOP_SECRET: must hold ALL item compartments)
    granted_by_role_address: str          # audit trail
    vetting_status: VettingStatus         # PENDING, ACTIVE, SUSPENDED, EXPIRED, REVOKED
    review_at: datetime | None            # renewal/review date
    nda_signed: bool                      # required for SECRET/TOP_SECRET
```

### 5.5 Vetting Status FSM

```
PENDING -> ACTIVE, REVOKED
ACTIVE -> SUSPENDED, EXPIRED, REVOKED
SUSPENDED -> ACTIVE, REVOKED
EXPIRED -> ACTIVE, REVOKED
REVOKED -> (terminal -- no transitions out)
```

Only ACTIVE clearances are valid for access decisions. Invalid transition raises `PactError` with from/to status and valid targets.

### 5.6 Effective Clearance

`effective_clearance(role_clearance, posture) -> ConfidentialityLevel`

Returns `min(role.max_clearance, POSTURE_CEILING[posture])`. Fail-closed: if no level matches (should never happen), returns PUBLIC.

### 5.7 Failure Modes

- Non-ACTIVE vetting status -> access denied at step 1
- Invalid vetting status transition -> `PactError`
- Missing clearance for role -> access denied at step 1

---

## 6. Access Enforcement (5-Step Algorithm)

### 6.1 Purpose

Determines whether a role can access a specific knowledge item. DEFAULT IS DENY. Fail-closed by design.

### 6.2 KnowledgeItem

```python
@dataclass(frozen=True)
class KnowledgeItem:
    item_id: str
    classification: ConfidentialityLevel
    owning_unit_address: str              # D or T prefix that owns this data
    compartments: frozenset[str]          # for SECRET/TOP_SECRET
    description: str = ""
```

### 6.3 The Algorithm

`can_access(role_address, knowledge_item, posture, compiled_org, clearances, ksps, bridges) -> AccessDecision`

**Step 1: Resolve role clearance**

- Clearance must exist for `role_address`
- Vetting status must be ACTIVE
- Failure: DENY (step_failed=1)

**Step 2: Classification check**

- `effective_clearance(role_clearance, posture) >= item.classification`
- Failure: DENY (step_failed=2)

**Step 3: Compartment check (SECRET/TOP_SECRET only)**

- Role must hold ALL compartments the item belongs to
- Missing compartments listed in reason
- Failure: DENY (step_failed=3)

**Step 4: Containment check (5 sub-paths, first match wins)**

**4a: Same unit** -- role's containment unit matches item's owning unit (or is a child of it). ALLOW.

**4b: Downward** -- role address is a proper prefix of item's owning unit (e.g., `D1-R1` has downward visibility to `D1-R1-T1`). ALLOW.

**4c: T-inherits-D** -- role in a team inherits read access to data owned by any ancestor department. Walks up the role's address looking for the item owner as an ancestor. ALLOW.

**4d: KSP exists** -- an active, non-expired Knowledge Share Policy where:

- Source unit matches item's owning unit (exact or prefix)
- Target unit contains the requesting role
- Item classification <= KSP max_classification
  ALLOW, with `valid_until` set to KSP expiry.

**4e: Bridge exists** -- an active, non-expired Cross-Functional Bridge where:

- One side matches the requesting role (exact match only -- bridges are role-level, not inherited by descendants)
- Other side connects to the item's owning unit
- Item classification <= bridge max_classification
- If unilateral (`bilateral=False`), only A->B direction
  ALLOW, with `valid_until` set to bridge expiry.

**Step 5: No access path found** -- DENY (step_failed=5)

### 6.4 AccessDecision

```python
@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    step_failed: int | None = None  # 1-5, or None if allowed
    audit_details: dict[str, Any]
    valid_until: datetime | None = None  # expiry of KSP/bridge that granted access
```

### 6.5 Knowledge Share Policies (KSPs)

```python
@dataclass(frozen=True)
class KnowledgeSharePolicy:
    id: str
    source_unit_address: str    # D/T prefix sharing knowledge
    target_unit_address: str    # D/T prefix receiving access
    max_classification: ConfidentialityLevel
    compartments: frozenset[str]  # restrict to specific compartments (empty = all)
    created_by_role_address: str
    active: bool = True
    expires_at: datetime | None = None
```

KSPs are directional: source shares WITH target. Expired KSPs are treated as non-existent.

### 6.6 Cross-Functional Bridges

```python
@dataclass(frozen=True)
class PactBridge:
    id: str
    role_a_address: str
    role_b_address: str
    bridge_type: str        # "standing", "scoped", "ad_hoc"
    max_classification: ConfidentialityLevel
    operational_scope: tuple[str, ...]  # limit to specific operations (empty = all)
    bilateral: bool = True              # both roles have mutual access
    expires_at: datetime | None = None
    active: bool = True
```

Bridges grant role-level access paths. Bridges are NOT inherited by descendant roles -- if VP Admin has a bridge, Finance Director does NOT inherit that access (descendant access is governed by KSPs).

**Bridge approval (Section 4.4):** Before creating a cross-functional bridge, the Lowest Common Ancestor (LCA) of the two roles in the D/T/R tree must approve. Approvals have 24h TTL. Optional bilateral consent when `require_bilateral_consent=True`.

### 6.7 Pre-Retrieval Filtering

```python
class KnowledgeFilter(Protocol):
    def filter_before_retrieval(self, role_address, query, envelope) -> FilterDecision: ...
```

Evaluated BEFORE the 5-step algorithm. Can deny the request outright or narrow query scope. Filter errors are fail-closed to DENY. This prevents data from leaving the store if the role's envelope does not permit the query.

### 6.8 Failure Modes

- Missing clearance -> DENY (step 1)
- Non-ACTIVE vetting -> DENY (step 1)
- Insufficient clearance -> DENY (step 2)
- Missing compartments -> DENY (step 3)
- No structural, KSP, or bridge path -> DENY (step 5)
- Internal error -> DENY (step 0, fail-closed)
- KnowledgeFilter error -> DENY (fail-closed)

---

## 7. Verification Gradient

### 7.1 Purpose

Classifies governance decisions into four levels, ranging from fully permitted to fully blocked. Maps PACT's constraint envelopes to EATP's verification gradient concept.

### 7.2 Levels

```python
class VerificationLevel(str, Enum):
    AUTO_APPROVED = "AUTO_APPROVED"  # within all constraints
    FLAGGED = "FLAGGED"              # near a boundary -- allowed but logged
    HELD = "HELD"                    # exceeds soft limit, queued for human approval
    BLOCKED = "BLOCKED"              # violates hard constraint
```

**Allowed:** AUTO_APPROVED, FLAGGED (proceed but log for review)
**Not allowed:** HELD (awaits human), BLOCKED (rejected)

### 7.3 GradientEngine

```python
class GradientEngine:
    def __init__(self, config: ConstraintEnvelopeConfig, gradient: VerificationGradientConfig | None = None)
    def evaluate(self, action: str, context: dict | None = None) -> EvaluationResult
```

Evaluates an action against all five constraint dimensions. Returns `EvaluationResult` with:

- Per-dimension `DimensionResult` (satisfied/not, reason, details)
- Overall `VerificationLevel`
- Matched gradient rule (if any)

**Fail-closed:** Any evaluation error returns BLOCKED.

**Level determination:**

1. Check gradient rules first (pattern matching, first match wins)
2. If any dimension is unsatisfied, escalate to BLOCKED
3. Default: AUTO_APPROVED

### 7.4 Gradient Rules

```python
class GradientRuleConfig:
    pattern: str                  # action pattern (wildcard matching)
    level: VerificationLevel      # verification level for matched actions
```

Configured per-envelope in `VerificationGradientConfig.rules`. Allows org-specific rules like "deploy*to_prod always HELD" or "read*\* always AUTO_APPROVED".

### 7.5 EvaluationResult

```python
@dataclass(frozen=True)
class EvaluationResult:
    level: VerificationLevel
    dimensions: list[DimensionResult]
    action: str
    matched_rule: str
    all_satisfied: bool  # property -- True if all dimension constraints pass
```

---

## 8. GovernanceVerdict

### 8.1 Purpose

The result of `GovernanceEngine.verify_action()` -- the primary governance decision output. Frozen (immutable) record of a governance decision.

### 8.2 Structure

```python
@dataclass(frozen=True)
class GovernanceVerdict:
    level: str                                    # "auto_approved", "flagged", "held", "blocked"
    reason: str
    role_address: str
    action: str
    effective_envelope_snapshot: dict | None       # serialized envelope at decision time
    audit_details: dict[str, Any]
    access_decision: AccessDecision | None         # if knowledge resource was checked
    timestamp: datetime
    envelope_version: str = ""
```

### 8.3 Properties

- `verdict.allowed` -- True if level is `auto_approved` or `flagged`
- `verdict.is_held` -- True if level is `held`
- `verdict.is_blocked` -- True if level is `blocked`

### 8.4 Serialization

`verdict.to_dict()` produces a JSON-safe dict with all fields, including nested `access_decision` if present.

---

## 9. GovernanceContext (Anti-Self-Modification)

### 9.1 Purpose

Agents receive a frozen, read-only governance snapshot -- never the GovernanceEngine itself. This is the anti-self-modification defense. Agents cannot mutate posture, envelope, clearance, or any other governance state.

### 9.2 Structure

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

### 9.3 Security Properties

- `frozen=True` -- `ctx.posture = "delegated"` raises `FrozenInstanceError`
- `__reduce__` blocked -- prevents pickle deserialization (forged context injection)
- `__getstate__` blocked -- prevents pickle serialization
- `from_dict()` emits `UserWarning` -- authoritative construction path is `GovernanceEngine.get_context()`

### 9.4 Contract

Agents receive `GovernanceContext(frozen=True)`, NEVER `GovernanceEngine`. The engine reference is private (`_engine`).

---

## 10. PactGovernedAgent

### 10.1 Purpose

Wraps any agent with PACT governance enforcement. Every tool call goes through governance verification before execution.

### 10.2 API

```python
class PactGovernedAgent:
    def __init__(self, engine, role_address, posture=SUPERVISED)
    @property
    def context(self) -> GovernanceContext  # read-only, frozen
    def register_tool(self, action_name, *, cost=0.0, resource=None)
    def execute_tool(self, action_name, **kwargs) -> Any
```

### 10.3 Tool Execution Flow

1. Check if tool is registered (default-deny for unregistered -> `GovernanceBlockedError`)
2. Build context dict with cost and resource
3. Call `engine.verify_action(role_address, action, context)`
4. BLOCKED -> raise `GovernanceBlockedError(verdict)`
5. HELD -> raise `GovernanceHeldError(verdict)`
6. FLAGGED -> log warning, proceed
7. AUTO_APPROVED -> proceed silently
8. Call the actual tool function (`_tool_fn` kwarg)

### 10.4 @governed_tool Decorator

```python
@governed_tool("write_report", cost=50.0)
def write_report(content: str) -> str:
    return f"Report: {content}"
```

Attaches governance metadata (`_governed`, `_governance_action`, `_governance_cost`, `_governance_resource`) to functions. Does NOT intercept execution -- enforcement happens in `PactGovernedAgent.execute_tool()`.

### 10.5 MockGovernedAgent (Testing)

```python
class MockGovernedAgent:
    def __init__(self, engine, role_address, tools, script, posture=SUPERVISED)
    def run(self) -> list[Any]
```

Executes a scripted sequence of tool actions through full PACT governance enforcement without requiring an LLM. Tools are auto-registered from `@governed_tool` metadata. Governance violations raise `GovernanceBlockedError` or `GovernanceHeldError` (fail-fast).

---

## 11. PactEngine (Dual Plane Bridge)

### 11.1 Purpose

The single facade that bridges the Trust Plane (GovernanceEngine) with the Execution Plane (GovernedSupervisor from kaizen-agents). Provides a progressive disclosure API.

### 11.2 Progressive Disclosure

**Layer 1:** Simple API

```python
engine = PactEngine(org="org.yaml", model="claude-sonnet-4-6")
result = await engine.submit("Analyze Q3 data", role="D1-R1")
```

**Layer 2:** Configuration

```python
engine = PactEngine(org="org.yaml", model="...", budget_usd=50.0, clearance="confidential")
```

**Layer 3:** Direct subsystem access

```python
engine.governance   # read-only GovernanceEngine view
engine.costs        # CostTracker
engine.events       # EventBus
```

### 11.3 Constructor

```python
class PactEngine:
    def __init__(
        self,
        org: str | Path | dict,           # YAML path, Path, or raw dict
        *,
        model: str | None = None,          # LLM model identifier
        budget_usd: float | None = None,   # maximum budget (None = unlimited)
        clearance: str = "restricted",
        store_backend: str = "memory",
        cost_model: Any | None = None,     # CostModel for LLM token costs
        on_held: HeldActionCallback | None = None,
        enforcement_mode: EnforcementMode = EnforcementMode.ENFORCE,
    )
```

**Validation at init:**

- `budget_usd`: must be finite and non-negative (NaN/Inf raises ValueError)
- `enforcement_mode`: DISABLED requires `PACT_ALLOW_DISABLED_MODE=true` env var
- Degenerate envelopes are detected and logged (up to 50 warnings)

### 11.4 submit() -- Governed Work Execution

```python
async def submit(self, objective: str, role: str, context: dict | None = None) -> WorkResult
```

**Thread-safety:** Acquires `self._submit_lock` (asyncio.Lock) to make check-remaining -> execute -> record-cost atomic. Prevents concurrent submits from both seeing the same remaining budget and overspending.

**Input validation:** Empty/invalid objective or role returns `WorkResult(success=False, error="...")` without raising.

**Enforcement modes:**

| Mode                | Behavior                                                                       |
| ------------------- | ------------------------------------------------------------------------------ |
| `ENFORCE` (default) | Verdicts are binding. BLOCKED actions rejected.                                |
| `SHADOW`            | Verdicts logged but never block. WorkResult includes `governance_shadow=True`. |
| `DISABLED`          | Governance skipped entirely. Requires `PACT_ALLOW_DISABLED_MODE=true` env var. |

**Flow:**

1. Validate inputs
2. Emit `work.submitted` event
3. If DISABLED: skip governance, execute directly
4. Call `governance.verify_action(role, "submit", context)`
5. If SHADOW: log verdict, execute regardless
6. If ENFORCE and not allowed: return blocked WorkResult
7. Execute via GovernedSupervisor (lazy import of kaizen-agents)
8. Record cost via CostTracker
9. Emit completion/failure events

**Fail-closed:** Any governance error returns a BLOCKED WorkResult instead of raising.

**Lazy supervisor:** kaizen-agents is optional. If not installed, returns WorkResult with actionable error message ("Install with: pip install kailash-kaizen").

### 11.5 submit_sync()

Synchronous convenience wrapper. Creates or reuses an event loop. If called from inside an async context, uses ThreadPoolExecutor to avoid blocking.

### 11.6 Envelope Adaptation

`_adapt_envelope(role_address) -> dict` maps the 5 PACT constraint dimensions to supervisor parameters:

| PACT Dimension | Supervisor Parameter                        |
| -------------- | ------------------------------------------- |
| Financial      | `budget_usd`                                |
| Operational    | `tools`, `max_depth` (max_delegation_depth) |
| Data Access    | `data_clearance`                            |
| Temporal       | `timeout_seconds`                           |
| Communication  | `allowed_channels`, `notification_policy`   |

**NaN guard:** Every numeric field validated with `math.isfinite()`. Missing envelope: maximally restrictive defaults (budget=0, tools=[], clearance="none", timeout=60s, max_depth=0).

---

## 12. Enforcement Modes

### 12.1 Purpose

Controls how PactEngine applies governance verdicts. Three modes with decreasing strictness.

### 12.2 Modes

```python
class EnforcementMode(str, Enum):
    ENFORCE = "enforce"    # Default. Verdicts are binding.
    SHADOW = "shadow"      # Run governance but never block. Verdicts logged for calibration.
    DISABLED = "disabled"  # Skip governance entirely. Emergency use only.
```

### 12.3 DISABLED Mode Guard

DISABLED mode requires `PACT_ALLOW_DISABLED_MODE=true` environment variable. Without it, attempting to create a PactEngine with `EnforcementMode.DISABLED` raises `PactError`. This prevents accidental governance bypass.

### 12.4 SHADOW Mode Use Case

Operators use SHADOW mode to calibrate envelopes before switching to ENFORCE. All verdicts are computed and logged but never block execution. WorkResult includes `governance_shadow=True` metadata so downstream consumers know the result was not governed.

---
