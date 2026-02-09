# Trust Posture Transition Analysis

## Executive Summary

The EATP SDK implements a 4-posture model (FULL_AUTONOMY, SUPERVISED, HUMAN_DECIDES, BLOCKED) while Enterprise-App documentation describes a 5-posture model (Pseudo, Supervised, Shared Planning, Continuous Insight, Delegated). This fundamental mismatch creates mapping challenges and potential gaps in enterprise trust semantics. The current implementation provides basic posture mapping from verification results but lacks a formal state machine for transitions, hysteresis protection, and evidence-based progression.

**Complexity Score: Enterprise (24 points)**
- Technical Complexity: 9/10 (distributed state, cryptographic verification, real-time propagation)
- Business Complexity: 8/10 (compliance requirements, audit trails, multi-stakeholder)
- Operational Complexity: 7/10 (monitoring, alerting, incident response)

---

## 1. Current Posture Model Analysis

### 1.1 SDK Implementation (4 Postures)

**Location**: `./apps/kailash-kaizen/src/kaizen/trust/postures.py`

```python
class TrustPosture(str, Enum):
    FULL_AUTONOMY = "full_autonomy"    # Agent can act freely
    SUPERVISED = "supervised"           # Actions logged but not blocked
    HUMAN_DECIDES = "human_decides"     # Each action requires approval
    BLOCKED = "blocked"                 # Action is denied
```

### 1.2 Enterprise-App Model (5 Postures)

**Location**: `./repos/dev/enterprise-app/docs/00-developers/18-trust/04-trust-postures.md`

| Posture | Description |
|---------|-------------|
| Pseudo | Human decides everything; agent is pure interface |
| Supervised | Human approves each action before execution |
| Shared Planning | Human and agent co-plan before execution |
| Continuous Insight | Agent decides, human monitors with alerts |
| Delegated | Full autonomy within constraints |

### 1.3 Mapping Gap Analysis

| Enterprise-App | SDK | Gap |
|------------|-----|-----|
| Pseudo | HUMAN_DECIDES | Semantic overlap but different operational meaning |
| Supervised | SUPERVISED | Partial - SDK logs but doesn't block; Enterprise-App blocks until approval |
| Shared Planning | **MISSING** | No SDK equivalent for co-planning phase |
| Continuous Insight | **PARTIAL** | SUPERVISED logs but lacks alert thresholds |
| Delegated | FULL_AUTONOMY | Close match |

**Critical Gap**: The SDK's SUPERVISED posture logs actions but doesn't require approval before execution. This contradicts the Enterprise-App "Supervised" which requires explicit approval before each action.

---

## 2. Posture Transition Analysis

### 2.1 Current Transition Support

The `TrustPostureMapper` in `postures.py` determines posture based on:

1. **Verification Result Validity** (lines 149-155):
   - Invalid verification → BLOCKED

2. **Constraint Analysis** (lines 161-163):
   - `approval_required` → HUMAN_DECIDES
   - `human_in_loop` → HUMAN_DECIDES
   - `audit_required` → SUPERVISED

3. **Capability/Tool Risk** (lines 166-176):
   - Sensitive capability → SUPERVISED
   - High-risk tool → SUPERVISED

4. **Trust Level** (lines 182-188):
   - High/Full trust → FULL_AUTONOMY
   - Default → SUPERVISED

### 2.2 Missing Transition Mechanisms

**Problem 1: No State Machine**
Current implementation computes posture on each request without tracking previous state. This means:
- No transition validation (e.g., can't jump from BLOCKED to FULL_AUTONOMY)
- No transition logging for audit
- No transition hooks for policy enforcement

**Problem 2: No Transition Guards**
No mechanism prevents invalid transitions:

```
BLOCKED → FULL_AUTONOMY  (Should require intermediate steps)
HUMAN_DECIDES → FULL_AUTONOMY  (Should require evidence)
SUPERVISED → BLOCKED  (Should require reason)
```

**Problem 3: No Temporal Constraints**
No minimum time in posture before promotion:
- Agent could oscillate between postures rapidly
- No "cooling off" period after demotion

---

## 3. Edge Cases in Posture Transitions

### 3.1 Downgrade During Active Execution

**Scenario**: Agent is executing at FULL_AUTONOMY, posture is downgraded to HUMAN_DECIDES mid-execution.

**Current Behavior**:
- `TrustedAgent.execute_async()` verifies at start only (line 371)
- Mid-execution downgrade not detected
- Action completes with stale posture

**Risk**: HIGH - Completed action may violate new posture constraints

**Proposed Solution**:
```
+---------------------+
|  Pre-Execution     |
|  Verification      |
+---------------------+
         |
         v
+---------------------+
|  Checkpoint: 50%   |  <-- Periodic re-verification
|  Re-verify posture |
+---------------------+
         |
         v
+---------------------+
|  Post-Execution    |
|  Final validation  |
+---------------------+
```

### 3.2 Posture Mismatch in Delegation Chain

**Scenario**:
- Parent agent: SUPERVISED
- Child agent: FULL_AUTONOMY (inherited from different authority)

**Current Behavior**:
- `TrustedSupervisorAgent.delegate_to_worker()` doesn't check posture compatibility
- Child can operate at higher autonomy than parent

**Risk**: CRITICAL - Breaks principle of "capabilities can only reduce, constraints can only tighten"

**Evidence from code** (`trusted_agent.py`, line 780-821):
```python
async def delegate_to_worker(self, ...):
    # Passes context for human_origin propagation
    # But NO posture comparison!
    delegation = await self._trust_ops.delegate(...)
```

### 3.3 Rapid Posture Oscillation

**Scenario**: System under load causes verification to alternate between SUPERVISED and FULL_AUTONOMY due to:
- Transient network issues
- Cache invalidation race conditions
- Load balancer routing to different replicas

**Current Behavior**: No hysteresis - each verification computes posture independently

**Risk**: MEDIUM - User confusion, audit trail noise, potential security implications

---

## 4. Proposed Formal State Machine

### 4.1 State Diagram

```
                                +-------+
              Manual Demotion   |BLOCKED|  <-- Automatic on trust revocation
                  +-----------► +-------+
                  |                 |
                  |    Manual Unblock (with reason)
                  |                 v
            +-----+-----+     +------------+
            |FULL_      |     |HUMAN_      |
            |AUTONOMY   | ◄-- |DECIDES     |
            +-----------+     +------------+
                  ▲                 |
                  |    Evidence-based promotion
                  |    (X successful actions)
                  |                 v
            +-----+-----+     +------------+
            |CONTINUOUS |     |SUPERVISED  |
            |INSIGHT    | ◄-- |            |
            +-----------+     +------------+
                  ▲                 |
                  |    Time in posture + metrics
                  |                 v
                  |           +------------+
                  +-----------+SHARED      |
                              |PLANNING    |
                              +------------+
```

### 4.2 Transition Guards

| From | To | Guard Conditions |
|------|-----|-----------------|
| BLOCKED | HUMAN_DECIDES | `reason_provided AND authority_approved` |
| HUMAN_DECIDES | SUPERVISED | `successful_actions >= 10 AND no_violations_24h` |
| SUPERVISED | SHARED_PLANNING | `successful_actions >= 50 AND time_in_posture >= 7d` |
| SHARED_PLANNING | CONTINUOUS_INSIGHT | `plan_approval_rate >= 95% AND time_in_posture >= 14d` |
| CONTINUOUS_INSIGHT | FULL_AUTONOMY | `alert_rate < 5% AND time_in_posture >= 30d` |
| ANY | BLOCKED | `trust_revoked OR constraint_violation OR authority_action` |
| ANY (except BLOCKED) | HUMAN_DECIDES | `multiple_violations OR anomaly_detected` |

### 4.3 Invariants

1. **Posture Monotonicity in Delegation**: Child posture <= Parent posture
2. **Revocation Cascade**: BLOCKED propagates down delegation chain
3. **Audit Requirement**: All transitions logged with human_origin, reason, timestamp
4. **Hysteresis Window**: Minimum 1 hour between posture changes (configurable)

---

## 5. Evidence-Based Posture Progression

### 5.1 Metrics for Promotion

| Metric | Source | Threshold |
|--------|--------|-----------|
| Successful Action Count | `AuditAnchor.result == SUCCESS` | Posture-specific |
| Violation Count | `VerificationResult.violations` | 0 in window |
| Time in Posture | `posture_change_timestamp` | Posture-specific |
| Human Approval Rate | `HUMAN_DECIDES` approval count | >= 95% |
| Alert Rate | Anomaly detection | < 5% |
| Constraint Compliance | `constraint_envelope` evaluation | 100% |

### 5.2 Metrics for Demotion

| Metric | Source | Threshold |
|--------|--------|-----------|
| Failed Actions | `AuditAnchor.result == FAILURE` | > 3 in 1 hour |
| Constraint Violations | `ConstraintViolationError` | Any |
| Anomaly Score | Behavior analysis | > 0.8 |
| Human Override Count | Manual intervention | > 2 in 24h |

---

## 6. Posture Inheritance in Delegation Chains

### 6.1 Current Behavior

From `execution_context.py` (lines 151-193):
```python
def with_delegation(self, delegatee_id, additional_constraints):
    # Preserves human_origin (correct)
    # Merges constraints (correct)
    # BUT: No posture comparison or validation
    return ExecutionContext(
        human_origin=self.human_origin,  # Preserved
        delegation_chain=new_chain,
        delegation_depth=self.delegation_depth + 1,
        constraints=merged_constraints,
        # Missing: posture field
    )
```

### 6.2 Proposed Enhancement

```python
@dataclass
class ExecutionContext:
    human_origin: HumanOrigin
    delegation_chain: List[str]
    delegation_depth: int
    constraints: Dict[str, Any]
    trace_id: str
    # NEW FIELDS:
    posture: TrustPosture
    posture_history: List[PostureChange]
    max_allowed_posture: TrustPosture  # From parent chain

    def with_delegation(self, delegatee_id, ...):
        # Validate: child_posture <= self.posture
        if child_posture.value > self.posture.value:
            raise PostureEscalationError(...)

        return ExecutionContext(
            ...,
            posture=child_posture,
            max_allowed_posture=self.posture,  # Cap from parent
        )
```

---

## 7. Risk Register

| Risk ID | Description | Likelihood | Impact | Mitigation |
|---------|-------------|------------|--------|------------|
| P-001 | Child agent operates at higher posture than parent | HIGH | CRITICAL | Add posture comparison in delegation |
| P-002 | Posture downgrade during execution not detected | MEDIUM | HIGH | Add periodic re-verification checkpoints |
| P-003 | SDK/Enterprise-App posture mismatch causes confusion | HIGH | MEDIUM | Implement 5-posture model in SDK |
| P-004 | No audit trail for posture transitions | HIGH | HIGH | Add PostureTransition audit records |
| P-005 | Rapid posture oscillation under load | MEDIUM | LOW | Implement hysteresis with minimum 1h window |
| P-006 | No evidence-based progression metrics | HIGH | MEDIUM | Implement metrics collection in AuditService |

---

## 8. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Add 5-posture enum matching Enterprise-App
- [ ] Add `posture` field to `ExecutionContext`
- [ ] Implement posture inheritance validation in delegation
- [ ] Add `PostureTransition` audit record type

### Phase 2: State Machine (Week 3-4)
- [ ] Implement `PostureStateMachine` class
- [ ] Define transition guards
- [ ] Add hysteresis logic
- [ ] Implement posture downgrade detection during execution

### Phase 3: Evidence-Based Progression (Week 5-6)
- [ ] Implement metrics collection in AuditService
- [ ] Define promotion/demotion thresholds
- [ ] Create posture recommendation engine
- [ ] Add dashboard for posture monitoring

---

## 9. Decision Points

1. **Should SDK adopt 5-posture model or map to 4?**
   - Recommendation: Adopt 5-posture model for full compatibility

2. **Where should posture state be stored?**
   - Option A: In `TrustLineageChain` (persistent)
   - Option B: Computed on each verification (stateless)
   - Recommendation: Persistent with computed override capability

3. **How to handle legacy agents without posture data?**
   - Recommendation: Default to SUPERVISED with migration path

4. **Who can authorize posture promotions?**
   - Recommendation: Authority-level permission with human approval
