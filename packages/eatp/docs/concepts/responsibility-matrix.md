# Responsibility Matrix

EATP follows a PDP/PEP separation: the SDK computes verdicts (Policy Decision Point), but the host framework must enforce them (Policy Enforcement Point).

!!! warning "Unenforced Verdicts"
    Calling VERIFY without enforcing the verdict is a security gap. Always act on the verification result.

## Who Does What

| Responsibility | Standalone SDK | Host Framework |
|---|---|---|
| Tightening validation at delegation time | **Enforced** | N/A |
| VERIFY operation (compute verdict) | **Provided** | Must call |
| BLOCKED enforcement (reject action) | Returns verdict | **Must enforce** |
| HELD enforcement (queue for human) | Returns verdict | **Must enforce** |
| AUTO_APPROVED (allow action) | Returns verdict | **Must enforce** |
| Audit anchor creation | **Provided** | Must call |

## Integration Patterns

### Pattern A: StrictEnforcer (Recommended)

Raises exceptions on BLOCKED/HELD — simplest integration:

```python
from eatp.enforce.strict import StrictEnforcer

enforcer = StrictEnforcer(trust_ops=ops)
# Raises EATPBlockedError on BLOCKED
verdict = await enforcer.enforce(agent_id, action, result)
```

### Pattern B: Decorator

Apply to functions — zero-change integration:

```python
from eatp.enforce.decorators import verified

@verified(agent_id="agent-001", action="analyze", ops=ops)
async def analyze_data():
    return {"result": "done"}
```

### Pattern C: Shadow Mode (Gradual Rollout)

Log without blocking — for production rollout:

```python
from eatp.enforce.shadow import ShadowEnforcer

shadow = ShadowEnforcer(trust_ops=ops)
verdict = await shadow.check(agent_id, action)
# Never blocks, always logs
```

### Pattern D: Manual Check

Full control — for complex enforcement logic:

```python
result = await ops.verify(agent_id="agent-001", action="analyze_data")
if not result.valid:
    logger.error(f"Trust verification failed: {result.reason}")
    raise PermissionError(f"Agent not authorized: {result.reason}")
# Proceed with action
```
