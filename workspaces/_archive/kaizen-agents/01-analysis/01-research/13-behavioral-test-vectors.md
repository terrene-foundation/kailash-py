# Cross-SDK Behavioral Test Vectors

**Date**: 2026-03-23
**Purpose**: Conformance target for kailash-rs implementation of kaizen-agents governance

Each section defines input → expected output → invariants for one governance module. The kailash-rs team can use these as test cases to verify behavioral alignment.

---

## 1. Accountability (D/T/R Addressing)

### BT-ACC-01: Root agent address

- **Input**: `register_root("root-001")`
- **Expected**: Address = `"D1-R1"`

### BT-ACC-02: First child address

- **Input**: `register_child("child-1", parent_id="root-001")` after root
- **Expected**: Address = `"D1-R1-T1-R1"`

### BT-ACC-03: Sequential children

- **Input**: 3 children registered under same parent
- **Expected**: Addresses = `"D1-R1-T1-R1"`, `"D1-R1-T2-R1"`, `"D1-R1-T3-R1"`

### BT-ACC-04: Grandchild address

- **Input**: Child of `"D1-R1-T1-R1"`
- **Expected**: Address = `"D1-R1-T1-R1-T1-R1"`

### BT-ACC-05: Sibling detection

- **Input**: Two agents with same parent
- **Expected**: `get_siblings(a)` returns `[b]`, `get_siblings(b)` returns `[a]`

### BT-ACC-06: Duplicate registration rejected

- **Input**: `register_root("x")` twice
- **Expected**: Second call raises ValueError

### Invariant

- Every address follows PACT D/T/R grammar: every D or T is immediately followed by R
- Sequence numbers are 1-based and monotonically increasing per parent

---

## 2. Classification & Clearance

### BT-CLR-01: Monotonic floor

- **Input**: Register key at C3_SECRET, then register same key at C1_INTERNAL
- **Expected**: ValueError "Monotonic floor violation"

### BT-CLR-02: Monotonic upgrade

- **Input**: Register key at C1_INTERNAL, then register same key at C3_SECRET
- **Expected**: Key classification is now C3_SECRET

### BT-CLR-03: Filter by clearance

- **Input**: Register C0 value and C3 value. Filter at C1.
- **Expected**: Only C0 value visible

### BT-CLR-04: Pre-filter API key

- **Input**: `classify("val", "sk-abc123def456ghi789jklmnop")`
- **Expected**: >= C3_SECRET

### BT-CLR-05: Pre-filter SSN

- **Input**: `classify("data", "123-45-6789")`
- **Expected**: >= C4_TOP_SECRET

### BT-CLR-06: Pre-filter private key

- **Input**: `classify("cert", "-----BEGIN RSA PRIVATE KEY-----")`
- **Expected**: >= C4_TOP_SECRET

### BT-CLR-07: Nested secret detection (R1-04)

- **Input**: `classify("cfg", {"nested": {"key": "sk-abc123def456ghi789jklmnop"}})`
- **Expected**: >= C3_SECRET

### BT-CLR-08: Key name heuristic

- **Input**: `classify("api_key", "any_value")`
- **Expected**: >= C3_SECRET

### Invariants

- C0 < C1 < C2 < C3 < C4 (total order)
- Classification can only increase (monotonic floor)
- An agent at clearance level N sees only values at levels <= N

---

## 3. Cascade Revocation

### BT-CAS-01: Tighten propagates to children

- **Input**: Root limit=100, child limit=50. Tighten root to limit=30.
- **Expected**: Child limit = min(30, 50) = 30

### BT-CAS-02: Deep propagation via direct parent

- **Input**: Root→child→grandchild. Root allowed=["read","write"], child allowed=["read"], grandchild allowed=["read","write"]. Tighten root (unchanged).
- **Expected**: Grandchild allowed=["read"] (intersected against child, not root)

### BT-CAS-03: Tighten is monotonic

- **Input**: Agent limit=50. Call tighten with limit=100 (widening attempt).
- **Expected**: Agent limit remains 50 (intersection enforces monotonic tightening)

### BT-CAS-04: Cascade terminate

- **Input**: Root→child→grandchild. Terminate root.
- **Expected**: All 3 terminated (leaves first: grandchild, child, root)

### BT-CAS-05: Budget reclamation on cascade

- **Input**: Child allocated=30, consumed=10. Cascade terminate.
- **Expected**: 20 reclaimed to parent

### BT-CAS-06: NaN in intersection rejected

- **Input**: Child financial limit = NaN. Tighten parent.
- **Expected**: ValueError "Non-finite value"

### Invariants

- Child envelope is always <= parent envelope on every dimension
- Budget consumed + budget reclaimed = budget allocated (conservation)
- NaN and Inf values are rejected (fail-closed)

---

## 4. Vacancy Handling

### BT-VAC-01: Orphan detection

- **Input**: Parent terminates with one child
- **Expected**: orphan_detected event for child

### BT-VAC-02: Acting parent auto-designation

- **Input**: Grandparent→parent→child. Parent terminates.
- **Expected**: Grandparent auto-designated as acting parent for child

### BT-VAC-03: Deadline suspension

- **Input**: Parent terminates (no grandparent). Wait past deadline.
- **Expected**: Child suspended (orphan_suspended event)

### BT-VAC-04: Manual acting parent

- **Input**: Orphaned child. Designate foster parent.
- **Expected**: acting_parent_designated event with auto_designated=False

### Invariants

- Orphan with acting parent is NOT considered orphaned
- NaN/Inf deadline rejected at construction
- Deadline must be positive

---

## 5. Dereliction Detection

### BT-DER-01: Identical envelopes flagged

- **Input**: Parent and child with identical financial limits
- **Expected**: DerelictionWarning with tightening_ratio < threshold

### BT-DER-02: Sufficient tightening not flagged

- **Input**: Parent limit=100, child limit=50 (50% tightening)
- **Expected**: No warning (50% > 5% threshold)

### BT-DER-03: Stats monotonic after eviction

- **Input**: 20 derelictions with maxlen=5
- **Expected**: dereliction_count=20 (not 5), total_delegations=20

### Invariants

- NaN in envelope dimensions falls back to 0.0 tightening ratio (not NaN propagation)
- Warning history is bounded (deque maxlen)
- Stats counter is monotonic (separate from bounded deque)

---

## 6. Emergency Bypass

### BT-BYP-01: Grant and check

- **Input**: Grant bypass for agent, check is_bypassed
- **Expected**: True

### BT-BYP-02: Auto-expiration

- **Input**: Grant bypass with 10ms duration. Wait 20ms.
- **Expected**: is_bypassed returns False

### BT-BYP-03: Manual revoke

- **Input**: Grant bypass, then revoke
- **Expected**: is_bypassed returns False, revoked record returned

### BT-BYP-04: Stacking rejected (R1-09)

- **Input**: Grant bypass for agent, then grant again without revoking
- **Expected**: ValueError "already has an active bypass"

### BT-BYP-05: Validation

- **Input**: Empty reason, empty authorizer, NaN duration, Inf duration, negative duration
- **Expected**: All rejected with ValueError

### Invariants

- All bypass events logged at CRITICAL severity
- Original envelope preserved for restoration
- Only one active bypass per agent at a time

---

## 7. Budget Tracking

### BT-BUD-01: Warning at threshold

- **Input**: Allocate 100, consume 75, threshold=0.70
- **Expected**: Warning event with utilization=0.75

### BT-BUD-02: Exhaustion HELD (not BLOCKED)

- **Input**: Allocate 100, consume 100, hold_threshold=1.0
- **Expected**: exhaustion_held event, is_held=True

### BT-BUD-03: Reclamation

- **Input**: Child allocated=30, consumed=10. Reclaim child.
- **Expected**: 20 reclaimed to parent, parent allocation increases by 20

### BT-BUD-04: Reallocation resolves hold

- **Input**: Agent held. Reallocate 20 from sibling.
- **Expected**: Agent no longer held

### BT-BUD-05: Warning not repeated

- **Input**: Exceed threshold, then consume more
- **Expected**: Only one warning event total

### BT-BUD-06: NaN/Inf/negative rejected

- **Input**: NaN allocation, Inf consumption, negative reallocation
- **Expected**: All rejected with ValueError

### Invariants

- consumed <= allocated at all times per agent (accounting invariant)
- NaN and Inf values rejected on all numeric paths
- Warning fires exactly once per agent per threshold crossing

---

## 8. GovernedSupervisor

### BT-SUP-01: Dry run default

- **Input**: `GovernedSupervisor().run("task")`
- **Expected**: success=True, budget_consumed=0.0

### BT-SUP-02: Budget tracking

- **Input**: Execute with cost=0.50, budget=5.0
- **Expected**: budget_consumed=0.50, budget_allocated=5.0

### BT-SUP-03: Audit trail contains genesis

- **Input**: Any run
- **Expected**: First audit record has record_type="genesis"

### BT-SUP-04: Non-optional failure halts plan (R1-06)

- **Input**: 2-node plan, first fails (non-optional)
- **Expected**: success=False, second node NOT started

### BT-SUP-05: Optional failure continues

- **Input**: 2-node plan, optional node fails
- **Expected**: success=True (only required nodes matter)

### BT-SUP-06: Reentrance safe (F-01)

- **Input**: Call run() twice on same supervisor
- **Expected**: Both succeed (no ValueError)

### BT-SUP-07: Default-deny tools

- **Input**: `GovernedSupervisor()` without tools
- **Expected**: tools == []

### BT-SUP-08: Plan limit enforcement (R1-10)

- **Input**: Plan with more nodes than max_children \* max_depth
- **Expected**: ValueError

### BT-SUP-09: Layer 3 read-only views (R1-05)

- **Input**: `supervisor.budget.allocate(...)` (mutation via Layer 3)
- **Expected**: AttributeError

### Invariants

- Result is frozen (immutable after construction)
- Envelope property returns deep copy (mutation-safe)
- All Layer 3 properties return read-only views
- NaN/Inf budget rejected at construction

---

## Audit Trail Format

### Record Structure

```json
{
  "record_id": "uuid-v4",
  "record_type": "genesis|delegation|termination|action|held|modification",
  "timestamp": "ISO-8601 UTC",
  "agent_id": "instance-id",
  "parent_id": "parent-instance-id | null",
  "action": "human-readable",
  "details": { "key": "value" },
  "prev_hash": "sha256-hex | 'genesis'",
  "record_hash": "sha256-hex"
}
```

### Hash Chain

- `record_hash = sha256(prev_hash + record_type + agent_id + action + timestamp_iso)`
- First record's prev_hash = "genesis"
- Chain verification uses `hmac.compare_digest` (constant-time)
- Thread-safe (threading.Lock on all public methods)

### Bounded Collection

- Default maxlen = 10,000
- After eviction, verification starts from first surviving record's prev_hash
