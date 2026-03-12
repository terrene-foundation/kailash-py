# Trust Postures

Trust postures map verification results to autonomy levels, determining how an agent's actions are handled.

## Five Posture Levels

| Posture | Level | Behavior |
|---------|-------|----------|
| **DELEGATED** | 5 | Agent operates with full autonomy; remote monitoring |
| **CONTINUOUS_INSIGHT** | 4 | Agent executes, human monitors in real-time |
| **SHARED_PLANNING** | 3 | Human and agent co-plan; agent executes approved plans |
| **SUPERVISED** | 2 | Agent proposes actions, human approves each one |
| **PSEUDO_AGENT** | 1 | Agent is interface only; human performs all reasoning |

## Posture State Machine

The `PostureStateMachine` manages transitions between postures with configurable guards:

```python
from eatp.postures import PostureStateMachine, TrustPosture

machine = PostureStateMachine(initial_posture=TrustPosture.SHARED_PLANNING)

# Upgrade requires meeting guard conditions
machine.request_transition(TrustPosture.CONTINUOUS_INSIGHT)

# Emergency downgrade is always allowed
machine.emergency_downgrade(TrustPosture.PSEUDO_AGENT)
```

## Comparison Operators

Postures support comparison based on autonomy level:

```python
from eatp.postures import TrustPosture

assert TrustPosture.DELEGATED > TrustPosture.SHARED_PLANNING
assert TrustPosture.PSEUDO_AGENT < TrustPosture.SUPERVISED
assert TrustPosture.SHARED_PLANNING.autonomy_level == 3
```

## Integration with Verification

The verification gradient maps VERIFY results to posture-appropriate actions:

- **AUTO_APPROVED**: Valid chain + sufficient posture → proceed
- **FLAGGED**: Approaching limits → log warning
- **HELD**: Requires review → queue for human
- **BLOCKED**: Violation detected → deny action
