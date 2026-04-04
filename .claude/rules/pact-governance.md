---
paths:
  - "**/pact/**"
  - "**/governance/**"
---

# PACT Governance Rules

### 1. Frozen GovernanceContext

Agents MUST receive `GovernanceContext(frozen=True)`, NEVER `GovernanceEngine`. The engine reference is private (`_engine`).

```python
# DO:
ctx = GovernanceContext(envelope=envelope, engine=engine, frozen=True)
agent.set_governance(ctx)

# DO NOT:
agent.set_governance(engine)  # Exposes mutable engine — self-modification attack vector
```

**Why**: If an agent receives the engine directly, it can modify its own governance constraints at runtime.

### 2. Monotonic Tightening

Child envelopes MUST be equal to or more restrictive than parent. `intersect_envelopes()` takes min/intersection of every field.

```python
# DO:
child_envelope = intersect_envelopes(parent_envelope, requested_envelope)

# DO NOT:
child_envelope = requested_envelope  # Bypasses parent constraints
child_envelope.max_cost = parent_envelope.max_cost + 100  # Widening forbidden
```

**Why**: Governance flows downward. A child can never have more permissions than its parent — violating this allows privilege escalation.

### 3. D/T/R Grammar

Every Department or Team MUST be followed by exactly one Role in any Address.

```python
# DO:
address = Address(org="acme", dept="engineering", role="developer")

# DO NOT:
address = Address(org="acme", dept="engineering")  # Missing Role
```

**Why**: An address without a terminal Role is ambiguous — could match multiple envelopes with different constraints.

### 4. Fail-Closed Decisions

All `verify_action()` and `check_access()` error paths MUST return BLOCKED/DENY, never raise or return permissive results.

```python
# DO:
except Exception:
    return Decision.BLOCKED  # Fail-closed on ANY error

# DO NOT:
except EnvelopeNotFoundError:
    return Decision.ALLOWED  # Fail-open — missing envelope permits everything!
```

**Why**: An error in constraint resolution MUST NOT result in permissive access.

### 5. Default-Deny Tool Registration

Tools MUST be explicitly registered via `register_tool()`. Unregistered tools are BLOCKED.

```python
# DO:
engine.register_tool("web_search", ToolPolicy(allowed_roles=["researcher"]))

# DO NOT:
if tool_name not in self._registered_tools:
    return True  # Unknown tool allowed by default (DANGEROUS)
```

### 6. NaN/Inf on Financial Fields

All numeric constraint fields MUST be validated with `math.isfinite()`.

```python
# DO:
if self.max_cost is not None and not math.isfinite(self.max_cost):
    raise ValueError("max_cost must be finite")

# DO NOT:
if self.max_cost is not None and self.max_cost < 0:
    raise ValueError("negative")  # NaN < 0 is False — NaN passes silently
```

**Why**: `NaN` poisons all comparisons (`NaN < X` is always `False`). If NaN enters a financial field, all budget checks pass silently.

### 7. Compilation Limits

Org compilation MUST enforce: `MAX_COMPILATION_DEPTH` (50), `MAX_CHILDREN_PER_NODE` (500), `MAX_TOTAL_NODES` (100,000).

### 8. Thread Safety

All `GovernanceEngine` and store methods MUST acquire `self._lock` before accessing shared state.

```python
# DO:
def resolve_envelope(self, address: Address) -> GovernanceEnvelope:
    with self._lock:
        return self._envelopes[address.key]
```

## MUST NOT

- Expose `GovernanceEngine` to agent code — agents receive `GovernanceContext` only
- Bypass monotonic tightening — no code path may widen a child envelope beyond parent
- Use bare exceptions for governance errors — all MUST inherit `PactError` with structured `.details`
