# PACT Governance Rules

## Scope

These rules apply when editing `packages/kailash-pact/**` files.

These rules supplement `.claude/rules/security.md` and `.claude/rules/trust-plane-security.md`. All three apply to PACT governance files.
Violations during code review by intermediate-reviewer are BLOCK-level findings.

## MUST Rules

### 1. Frozen GovernanceContext

Agents MUST receive `GovernanceContext(frozen=True)`, NEVER `GovernanceEngine`. The engine reference is private (`_engine`).

```python
# DO:
ctx = GovernanceContext(envelope=envelope, engine=engine, frozen=True)
agent.set_governance(ctx)

# DO NOT:
agent.set_governance(engine)  # Exposes mutable engine — self-modification attack vector
agent._engine = engine        # Private field bypass — same risk
```

**Why**: `GovernanceContext` is an immutable view. If an agent receives the engine directly, it can modify its own governance constraints at runtime — defeating the entire trust model.

### 2. Monotonic Tightening

Child envelopes MUST be equal to or more restrictive than parent envelopes. `intersect_envelopes()` takes the min/intersection of every field.

```python
# DO:
child_envelope = intersect_envelopes(parent_envelope, requested_envelope)
# child_envelope.max_cost <= parent_envelope.max_cost (always)
# child_envelope.allowed_tools ⊆ parent_envelope.allowed_tools (always)

# DO NOT:
child_envelope = requested_envelope  # Bypasses parent constraints entirely
child_envelope.max_cost = parent_envelope.max_cost + 100  # Widening is forbidden
```

**Why**: Governance flows downward through the org hierarchy. A child can never have more permissions than its parent — this is the monotonic tightening invariant. Violating it allows privilege escalation through delegation.

### 3. D/T/R Grammar

Every Department or Team MUST be immediately followed by exactly one Role in any Address.

```python
# DO:
address = Address(org="acme", dept="engineering", role="developer")
address = Address(org="acme", dept="engineering", team="backend", role="senior")

# DO NOT:
address = Address(org="acme", dept="engineering")          # Missing Role
address = Address(org="acme", dept="engineering", team="backend")  # Missing Role after Team
```

**Why**: The D/T/R grammar ensures every address resolves to a concrete governance envelope. An address without a terminal Role is ambiguous — it could match multiple envelopes with different constraints.

### 4. Fail-Closed Decisions

All `verify_action()` and `check_access()` error paths MUST return BLOCKED/DENY, never raise or return permissive results.

```python
# DO:
def verify_action(self, action: Action) -> Decision:
    try:
        envelope = self._resolve_envelope(action.agent_address)
        return self._evaluate(action, envelope)
    except Exception:
        return Decision.BLOCKED  # Fail-closed on ANY error

# DO NOT:
def verify_action(self, action: Action) -> Decision:
    try:
        envelope = self._resolve_envelope(action.agent_address)
        return self._evaluate(action, envelope)
    except EnvelopeNotFoundError:
        return Decision.ALLOWED  # Fail-open — missing envelope permits everything!
    except Exception:
        raise  # Unhandled exception bypasses governance entirely
```

**Why**: Governance is a security boundary. An error in constraint resolution or evaluation MUST NOT result in permissive access. Unknown states are denied — this is the same principle as trust-plane-security.md's monotonic escalation.

### 5. Default-Deny Tool Registration

Tools MUST be explicitly registered via `register_tool()` before execution. Unregistered tools are BLOCKED.

```python
# DO:
engine.register_tool("web_search", ToolPolicy(allowed_roles=["researcher"]))
engine.register_tool("code_execute", ToolPolicy(allowed_roles=["developer"]))
# Only registered tools can be invoked

# DO NOT:
def check_tool(self, tool_name: str) -> bool:
    if tool_name not in self._registered_tools:
        return True  # Unknown tool — allow by default (DANGEROUS)
```

**Why**: Default-allow for tools means any new or misspelled tool name bypasses governance. The tool registry is the allowlist — anything not on it is denied.

### 6. NaN/Inf on Financial Fields

All numeric constraint fields MUST be validated with `math.isfinite()`. Extends trust-plane-security.md rule 3 to governance envelopes.

```python
# DO:
import math

def __post_init__(self):
    if self.max_cost is not None and not math.isfinite(self.max_cost):
        raise ValueError("max_cost must be finite")
    if self.budget_limit is not None and not math.isfinite(self.budget_limit):
        raise ValueError("budget_limit must be finite")

# DO NOT:
def __post_init__(self):
    if self.max_cost is not None and self.max_cost < 0:
        raise ValueError("negative")  # NaN < 0 is False — NaN passes silently
```

**Why**: `NaN` poisons all numeric comparisons (`NaN < X` is always `False`, `NaN > X` is always `False`). If `NaN` enters a governance envelope's financial field, all budget checks pass silently. `Inf` similarly defeats upper-bound checks. Every numeric field in `GovernanceEnvelope` MUST validate with `math.isfinite()`.

### 7. Compilation Limits

Org compilation MUST enforce `MAX_COMPILATION_DEPTH` (50), `MAX_CHILDREN_PER_NODE` (500), `MAX_TOTAL_NODES` (100,000).

```python
# DO:
MAX_COMPILATION_DEPTH = 50
MAX_CHILDREN_PER_NODE = 500
MAX_TOTAL_NODES = 100_000

def compile_org(self, root: OrgNode, depth: int = 0) -> CompiledOrg:
    if depth > MAX_COMPILATION_DEPTH:
        raise CompilationError(f"Max depth {MAX_COMPILATION_DEPTH} exceeded")
    if len(root.children) > MAX_CHILDREN_PER_NODE:
        raise CompilationError(f"Max children {MAX_CHILDREN_PER_NODE} exceeded")
    self._total_nodes += 1
    if self._total_nodes > MAX_TOTAL_NODES:
        raise CompilationError(f"Max total nodes {MAX_TOTAL_NODES} exceeded")

# DO NOT:
def compile_org(self, root: OrgNode) -> CompiledOrg:
    for child in root.children:  # No depth limit — stack overflow on cyclic input
        self.compile_org(child)  # No node count limit — OOM on large orgs
```

**Why**: Org trees can be arbitrarily deep and wide. Without compilation limits, a malicious or malformed org definition can cause stack overflow (unbounded recursion), memory exhaustion (millions of nodes), or CPU exhaustion (exponential traversal). These limits are defense-in-depth against denial-of-service.

### 8. Thread Safety

All `GovernanceEngine` and store methods MUST acquire `self._lock` before accessing shared state.

```python
# DO:
import threading

class GovernanceEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._envelopes: dict[str, GovernanceEnvelope] = {}

    def resolve_envelope(self, address: Address) -> GovernanceEnvelope:
        with self._lock:
            return self._envelopes[address.key]

    def update_envelope(self, address: Address, envelope: GovernanceEnvelope) -> None:
        with self._lock:
            self._envelopes[address.key] = envelope

# DO NOT:
class GovernanceEngine:
    def resolve_envelope(self, address: Address) -> GovernanceEnvelope:
        return self._envelopes[address.key]  # Race condition — concurrent reads/writes corrupt state
```

**Why**: `GovernanceEngine` is shared across agent threads. Without locking, concurrent envelope updates and reads can produce torn reads (partially updated envelopes) or lost updates. Both lead to incorrect governance decisions.

## MUST NOT Rules

### 1. MUST NOT Expose GovernanceEngine to Agent Code

Agent code receives `GovernanceContext` only. Direct `GovernanceEngine` access enables self-modification attacks.

```python
# DO:
class Agent:
    def __init__(self, ctx: GovernanceContext):
        self._ctx = ctx  # Frozen, read-only view

# DO NOT:
class Agent:
    def __init__(self, engine: GovernanceEngine):
        self._engine = engine  # Agent can call engine.update_envelope() on itself!
```

**Why**: If an agent holds a reference to the engine, it can modify its own governance envelope — removing tool restrictions, raising budget limits, or escalating privileges. The `GovernanceContext` wrapper provides read-only access to the agent's resolved envelope without exposing mutation methods.

### 2. MUST NOT Bypass Monotonic Tightening

No code path may widen a child envelope beyond its parent.

```python
# DO:
child = intersect_envelopes(parent, requested)
assert child.max_cost <= parent.max_cost
assert child.allowed_tools <= parent.allowed_tools  # subset

# DO NOT:
child = GovernanceEnvelope(max_cost=parent.max_cost * 2)  # Widening!
child.allowed_tools = parent.allowed_tools | {"dangerous_tool"}  # Superset!
```

**Why**: Monotonic tightening is the foundational invariant of hierarchical governance. If any code path can widen a child envelope, the entire governance hierarchy is compromised — a leaf agent could accumulate permissions exceeding the root.

### 3. MUST NOT Use Bare Exception for Governance Errors

All governance errors MUST inherit from `PactError` with structured `.details`.

```python
# DO:
from pact.exceptions import PactError, GovernanceViolationError

raise GovernanceViolationError(
    "Budget exceeded",
    details={"max_cost": 100.0, "attempted_cost": 150.0, "agent": "agent-001"}
)

# DO NOT:
raise ValueError("Budget exceeded")  # No structured details, wrong hierarchy
raise Exception("something went wrong")  # Bare exception — uncatchable by governance handlers
```

**Why**: Governance errors carry structured context (`details` dict) that audit systems, dashboards, and parent agents consume. Bare exceptions lose this context and cannot be distinguished from unrelated errors in `except` handlers.

## Cross-References

- `.claude/rules/trust-plane-security.md` — Trust-plane security patterns (NaN/Inf, bounded collections, fail-closed)
- `.claude/rules/eatp.md` — EATP SDK conventions (dataclasses, error hierarchy, cryptography)
- `packages/kailash-pact/src/pact/governance/agent.py` — Anti-self-modification defense
- `packages/kailash-pact/src/pact/governance/envelopes.py` — Monotonic tightening
