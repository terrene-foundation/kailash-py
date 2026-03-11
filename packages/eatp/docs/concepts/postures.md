# Trust Postures

Trust postures map verification results to autonomy levels, determining how an agent's actions are handled.

## Five Posture Levels

| Posture | Level | Behavior |
|---------|-------|----------|
| **FULL_AUTONOMY** | 5 | Agent acts freely |
| **ASSISTED** | 4 | AI-assisted with minimal oversight |
| **SUPERVISED** | 3 | Actions logged but not blocked |
| **HUMAN_DECIDES** | 2 | Each action requires human approval |
| **BLOCKED** | 1 | All actions denied |

## Posture State Machine

The `PostureStateMachine` manages transitions between postures with configurable guards:

```python
from eatp.postures import PostureStateMachine, TrustPosture

machine = PostureStateMachine(initial_posture=TrustPosture.SUPERVISED)

# Upgrade requires meeting guard conditions
machine.request_transition(TrustPosture.ASSISTED)

# Emergency downgrade is always allowed
machine.emergency_downgrade(TrustPosture.BLOCKED)
```

## Comparison Operators

Postures support comparison based on autonomy level:

```python
from eatp.postures import TrustPosture

assert TrustPosture.FULL_AUTONOMY > TrustPosture.SUPERVISED
assert TrustPosture.BLOCKED < TrustPosture.HUMAN_DECIDES
assert TrustPosture.SUPERVISED.autonomy_level == 3
```

## Integration with Verification

The verification gradient maps VERIFY results to posture-appropriate actions:

- **AUTO_APPROVED**: Valid chain + sufficient posture → proceed
- **FLAGGED**: Approaching limits → log warning
- **HELD**: Requires review → queue for human
- **BLOCKED**: Violation detected → deny action
