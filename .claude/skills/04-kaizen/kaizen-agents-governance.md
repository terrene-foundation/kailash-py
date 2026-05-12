# Kaizen-Agents: Governed Multi-Agent Orchestration

`pip install kaizen-agents` (v0.1.0) — PACT-governed L3 autonomous agent orchestration built on kailash-kaizen SDK.

## Architecture: The "Does It Require an LLM?" Boundary

| Layer            | Package          | Purpose                                                           | LLM? |
| ---------------- | ---------------- | ----------------------------------------------------------------- | ---- |
| L3 SDK           | `kailash-kaizen` | Deterministic primitives (EnvelopeTracker, Factory, PlanExecutor) | No   |
| L3 Orchestration | `kaizen-agents`  | Governed agent orchestration with LLM intelligence                | Yes  |
| CLI              | `kaizen-cli-py`  | Thin CLI entry point                                              | No   |

If the operation requires an LLM call, it belongs in `kaizen-agents`. If deterministic, it belongs in `kailash-kaizen`.

## GovernedSupervisor — Progressive Disclosure (3 Layers)

### Layer 1: Simple (2 params)

```python
from kaizen_agents.supervisor import GovernedSupervisor

supervisor = GovernedSupervisor(model=os.environ["LLM_MODEL"], budget_usd=10.0)
result = await supervisor.run("Analyze this codebase")
# result: SupervisorResult (frozen=True)
```

Defaults: empty tools, $1 budget, PUBLIC clearance, default-deny for all tools.

### Layer 2: Configured (8 params)

```python
supervisor = GovernedSupervisor(
    model=os.environ["LLM_MODEL"],
    budget_usd=10.0,
    tools=["read_file", "grep", "write_report"],
    data_clearance="restricted",       # PUBLIC | INTERNAL | RESTRICTED | CONFIDENTIAL | SECRET
    warning_threshold=0.70,            # Budget warning at 70%
    max_children=10,                   # Max child agents
    max_depth=5,                       # Max delegation depth
    policy_source="human@example.com", # D/T/R authority source
)
```

### Layer 3: Advanced (9 governance subsystems, read-only)

```python
# Query governance state — all through read-only views
trail = supervisor.audit.to_list()              # AuditTrail (read-only)
snap = supervisor.budget.get_snapshot("root")    # BudgetTracker (read-only)
chain = supervisor.accountability.trace("agent-1") # AccountabilityTracker
events = supervisor.cascade.get_events()         # CascadeManager
warnings = supervisor.dereliction.get_stats()    # DerelictionDetector
bypasses = supervisor.bypass_manager.get_active() # BypassManager
orphans = supervisor.vacancy.get_orphans()       # VacancyManager
classes = supervisor.clearance.get_classifications() # ClearanceEnforcer
classified = supervisor.classifier.classify("data") # ClassificationAssigner

# Mutation is BLOCKED — AttributeError on any mutation method
# supervisor.budget.allocate(...)  # AttributeError!
```

### Anti-Self-Modification (\_ReadOnlyView)

Governance subsystems are exposed through `_ReadOnlyView` proxies with explicit allowed-method whitelists:

```python
_BUDGET_QUERY_METHODS = frozenset({"get_snapshot", "is_held", "get_events"})
# Only these methods are callable through supervisor.budget
```

The `envelope` property returns `copy.deepcopy()` to prevent mutation through dict reference.

**Source**: `packages/kaizen-agents/src/kaizen_agents/supervisor.py`

## Seven Governance Modules

All modules share cross-cutting patterns:

- **Thread safety**: `threading.Lock` on all public methods
- **Bounded collections**: `deque(maxlen=10000)`, registries capped at 100,000
- **NaN/Inf defense**: `math.isfinite()` on every numeric input
- **Frozen value types**: All record/event/snapshot dataclasses are `frozen=True`

### 1. AccountabilityTracker (D/T/R Addressing)

Maps agent instances to PACT D/T/R addresses. Root = `D1-R1`. Children = `{parent}-T{n}-R1`.

```python
from kaizen_agents.governance.accountability import AccountabilityTracker

tracker = AccountabilityTracker()
tracker.register("supervisor-1", parent_id=None, policy_source="human@org.com")
tracker.register("worker-1", parent_id="supervisor-1")

chain = tracker.trace_accountability("worker-1")
# ["worker-1", "supervisor-1"]

address = tracker.get_address("worker-1")
# "D1-R1-T1-R1"
```

**Source**: `packages/kaizen-agents/src/kaizen_agents/governance/accountability.py`

### 2. BudgetTracker (Reclamation + Predictive Warnings)

Budget exhaustion triggers HELD (not BLOCKED) — siblings may have budget for reallocation.

```python
from kaizen_agents.governance.budget import BudgetTracker

budget = BudgetTracker(warning_threshold=0.80, hold_threshold=0.95)
budget.allocate("agent-1", amount=5.0)
budget.record_consumption("agent-1", amount=1.5)

snap = budget.get_snapshot("agent-1")
# BudgetSnapshot(allocated=5.0, consumed=1.5, remaining=3.5, ...)

# Reclamation: unused budget flows back to parent on completion
budget.reclaim("agent-1")

# Reallocation: resolve HELD by transferring from sibling
budget.reallocate(from_agent="agent-2", to_agent="agent-1", amount=2.0)
```

**Source**: `packages/kaizen-agents/src/kaizen_agents/governance/budget.py`

### 3. CascadeManager (Envelope Tightening + Termination)

Monotonic tightening: child envelopes can only be equal to or more restrictive than parent.

```python
from kaizen_agents.governance.cascade import CascadeManager

cascade = CascadeManager()
cascade.register("supervisor", parent_id=None, envelope=parent_env)
cascade.register("worker-1", parent_id="supervisor", envelope=worker_env)

# Tighten: intersects new constraints with current (never widens)
cascade.tighten_envelope("supervisor", new_constraints)
# BFS propagates to all descendants

# Terminate: cascades to children
cascade.terminate("supervisor", reason="budget_exhausted")
# worker-1 also terminated
```

`_intersect_dicts()` handles: nested dicts (recurse), numerics (take min), "allowed" lists (intersection), "blocked" lists (union). Recursion bounded to depth 10.

**Source**: `packages/kaizen-agents/src/kaizen_agents/governance/cascade.py`

### 4. ClearanceEnforcer + ClassificationAssigner

`DataClassification` is an `IntEnum` (C0=0 through C4=4) — direct comparison works.

```python
from kaizen_agents.governance.clearance import ClearanceEnforcer, ClassificationAssigner

enforcer = ClearanceEnforcer()
enforcer.set_agent_clearance("worker-1", "RESTRICTED")  # C2

# Deterministic regex pre-filter catches known patterns
assigner = ClassificationAssigner()
classification = assigner.classify("sk-abc123xyz...")
# DataClassification.SECRET (C4) — API key pattern detected

# Monotonic floor: classifications can only be raised, never lowered
enforcer.register_value("api_key", DataClassification.SECRET)
enforcer.register_value("api_key", DataClassification.PUBLIC)  # Rejected!
```

Recursive leaf scanning via `_extract_string_leaves()` (bounded to depth 10) catches secrets in nested structures.

**Source**: `packages/kaizen-agents/src/kaizen_agents/governance/clearance.py`

### 5. DerelictionDetector

Detects when a parent delegates with near-identical envelope (failing to narrow governance).

```python
from kaizen_agents.governance.dereliction import DerelictionDetector

detector = DerelictionDetector(threshold=0.15)  # 15% tightening minimum
detector.check_delegation("parent", parent_envelope, "child", child_envelope)
# Returns DerelictionWarning if tightening < threshold

stats = detector.get_stats()
# DerelictionStats(total_warnings=N, dereliction_count=N, ...)
```

**Source**: `packages/kaizen-agents/src/kaizen_agents/governance/dereliction.py`

### 6. BypassManager (Emergency Override)

Time-limited, logged at CRITICAL severity, anti-stacking enforced.

```python
from kaizen_agents.governance.bypass import BypassManager

mgr = BypassManager()
mgr.grant_bypass("agent-1", duration_seconds=300, reason="emergency", authorizer="admin")
# Anti-stacking: rejects if active bypass already exists

is_active = mgr.is_bypassed("agent-1")
mgr.revoke_bypass("agent-1")
```

Uses `time.monotonic()` for timing. Original envelope preserved for restoration after expiry.

**Source**: `packages/kaizen-agents/src/kaizen_agents/governance/bypass.py`

### 7. VacancyManager (Orphan Detection)

When parent terminates: children become orphans, grandparent auto-designated as acting parent.

```python
from kaizen_agents.governance.vacancy import VacancyManager

vacancy = VacancyManager(deadline_seconds=60)
vacancy.register("parent", parent_id=None)
vacancy.register("child", parent_id="parent")

vacancy.report_termination("parent")
orphans = vacancy.get_orphans()
# [OrphanRecord(agent_id="child", ...)]
```

**Source**: `packages/kaizen-agents/src/kaizen_agents/governance/vacancy.py`

## AuditTrail (EATP Hash Chain)

Append-only with hash chain integrity: `sha256(prev_hash + type + agent_id + action + timestamp)`.

```python
from kaizen_agents.audit.trail import AuditTrail

trail = AuditTrail()
trail.record("delegation", agent_id="supervisor", action="spawned worker-1")

# Verify chain integrity (constant-time hash comparison)
is_valid = trail.verify_chain()

records = trail.to_list()
# [AuditRecord(record_type="genesis", ...), AuditRecord(record_type="delegation", ...)]
```

**Source**: `packages/kaizen-agents/src/kaizen_agents/audit/trail.py`

## Integration with L3 SDK Primitives

### Envelope Allocation via SDK EnvelopeSplitter

```python
from kaizen_agents.policy.envelope_allocator import EnvelopeAllocator, BudgetPolicy, Subtask

policy = BudgetPolicy(reserve_pct=0.10, reallocation_enabled=True)
allocator = EnvelopeAllocator(policy=policy)
subtasks = [
    Subtask(child_id="research", description="Research", complexity=0.3),
    Subtask(child_id="write", description="Write", complexity=0.7),
]
# Converts local ConstraintEnvelope to SDK flat dict, delegates to EnvelopeSplitter
child_envelopes = allocator.allocate_with_sdk(parent_envelope, subtasks)
```

**Source**: `packages/kaizen-agents/src/kaizen_agents/policy/envelope_allocator.py`

### Context Bridging via SDK ScopedContext

```python
from kaizen_agents.context._scope_bridge import ScopeBridge

bridge = ScopeBridge.create_root(owner_id="supervisor-1", clearance="confidential")
child_scope = bridge.create_child_scope(
    child_owner_id="worker-1",
    visible_keys=["project.*"],
    writable_prefix="results",
    clearance="public",
)
context = bridge.inject_context(keys=["project.name"])
merged = bridge.merge_child_results(child_scope)
```

**Source**: `packages/kaizen-agents/src/kaizen_agents/context/_scope_bridge.py`

## Type Adapter Strategy

31 types mapped across kaizen-agents and kailash-kaizen:

- 12 direct swaps (identical semantics)
- 17 need adapters (enum casing, timedelta vs float, dataclass vs dict)
- 2 orchestration-specific (no SDK equivalent): `ConstraintEnvelope`, `MemoryConfig`

Pattern: internal code uses local types. `_sdk_compat.py` adapters convert at SDK boundaries only.

**Source**: `packages/kaizen-agents/src/kaizen_agents/_sdk_compat.py`

## Install

```bash
pip install kaizen-agents  # v0.1.0
# Requires: kailash-kaizen>=2.1.0, kailash-pact>=0.1.0
```

## Related Skills

- **[kaizen-l3-overview](kaizen-l3-overview.md)** — L3 SDK primitives (deterministic layer)
- **[kaizen-l3-envelope](kaizen-l3-envelope.md)** — EnvelopeTracker, Splitter, Enforcer
- **[kaizen-l3-plan-dag](kaizen-l3-plan-dag.md)** — PlanExecutor, gradient rules
- **[kaizen-agents-security](kaizen-agents-security.md)** — Security patterns for governance
