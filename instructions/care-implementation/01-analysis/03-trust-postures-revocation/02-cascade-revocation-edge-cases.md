# Cascade Revocation Edge Cases Analysis

## Executive Summary

The EATP cascade revocation implementation (`revoke_cascade` and `revoke_by_human` in `operations.py`) provides breadth-first revocation but has significant gaps in distributed system edge cases. Race conditions between action execution and revocation, cache staleness, partial propagation during network partitions, and concurrent revocation scenarios are not adequately addressed. This analysis identifies 8 critical failure modes and proposes solutions.

**Complexity Score: Enterprise (26 points)**
- Technical: 10/10 (distributed consensus, eventual consistency, concurrent mutations)
- Business: 8/10 (compliance, audit, immediate effect requirements)
- Operational: 8/10 (monitoring, recovery, incident response)

---

## 1. Current Implementation Analysis

### 1.1 Cascade Revocation Flow

**Location**: `./apps/kailash-kaizen/src/kaizen/trust/operations.py` (lines 1347-1421)

```python
async def revoke_cascade(self, agent_id: str, reason: str) -> List[str]:
    revoked_agents: List[str] = []

    # 1. Revoke this agent
    await self.trust_store.delete_chain(agent_id, soft_delete=True)
    revoked_agents.append(agent_id)

    # 2. Find all delegations FROM this agent
    all_chains = await self.trust_store.list_chains()
    delegatee_ids = []
    for other_chain in all_chains:
        for delegation in other_chain.delegations:
            if delegation.delegator_id == agent_id:
                delegatee_ids.append(delegation.delegatee_id)

    # 3. Recursively revoke in parallel
    cascade_tasks = [
        self.revoke_cascade(delegatee_id, f"Cascade from {agent_id}")
        for delegatee_id in set(delegatee_ids)
    ]
    results = await asyncio.gather(*cascade_tasks, return_exceptions=True)
```

### 1.2 Critical Architecture Issues

1. **No Atomicity**: Revocation is not transactional; partial failures leave inconsistent state
2. **No Ordering Guarantees**: Parallel execution can cause child revocation before parent
3. **Full Chain Scan**: `list_chains()` scans entire database for each revocation level
4. **No Idempotency Protection**: Re-revocation of same agent can cause issues
5. **No Fencing**: In-flight operations not protected against stale trust

---

## 2. Edge Case Analysis

### 2.1 Race Condition: Action Execution vs Revocation

```
Timeline:
T0: Agent A starts action verification
T1: Revocation initiated for Agent A
T2: Agent A's verification returns VALID (from cache or pre-revocation state)
T3: Revocation completes - Agent A marked as revoked
T4: Agent A executes action with stale verification result
T5: Action completes - executed with revoked trust
```

**Current Behavior** (`trusted_agent.py`, lines 369-376):
```python
async def execute_async(self, inputs, action, ...):
    # Verification at start only
    verification_result = await self.verify_trust(action=action, ...)
    # No re-verification before final commit
    result = await self._agent.execute_async(inputs=inputs, **kwargs)
```

**Risk**: CRITICAL - Action executes with revoked trust

**Evidence**:
- No version checking in `verify()` method
- No lock acquisition during verification
- Cache TTL of 300 seconds means stale trust can persist

**Proposed Solution**:
```
+------------------+
| verify_trust()   |  --> Returns (result, trust_version)
+------------------+
        |
        v
+------------------+
| execute_action() |
+------------------+
        |
        v
+------------------+
| commit_action()  |  --> Validates trust_version still current
+------------------+       If version mismatch: ABORT
```

---

### 2.2 Cache Staleness

**Scenario**: Agent A is revoked but cached trust chain is still valid for 300 seconds.

**Current Behavior** (`cache.py`, lines 167-204):
```python
async def get(self, agent_id: str) -> Optional[TrustLineageChain]:
    if agent_id not in self._cache:
        self._misses += 1
        return None

    entry = self._cache[agent_id]
    if entry.is_expired():  # TTL check only
        del self._cache[agent_id]
        return None

    # No revocation check!
    return entry.chain
```

**Risk**: HIGH - 5-minute window where revoked agent can still act

**Evidence**:
- `_invalidate_cache()` in `store.py` is a no-op placeholder (line 559-571)
- No push-based cache invalidation mechanism
- No version/epoch tracking

**Proposed Solution**:
```python
class TrustChainCache:
    def __init__(self):
        self._revocation_epoch = 0  # Global epoch counter
        self._agent_epochs: Dict[str, int] = {}  # Per-agent epochs

    async def get(self, agent_id: str) -> Optional[TrustLineageChain]:
        # Check if agent's epoch is stale
        current_epoch = await self._get_agent_epoch(agent_id)
        cached_epoch = self._agent_epochs.get(agent_id, 0)
        if current_epoch > cached_epoch:
            await self.invalidate(agent_id)  # Force refresh
            return None
        # ... rest of logic

    async def on_revocation(self, agent_id: str):
        """Called when revocation occurs"""
        self._revocation_epoch += 1
        self._agent_epochs[agent_id] = self._revocation_epoch
        await self.invalidate(agent_id)
```

---

### 2.3 Partial Propagation (Network Partition)

**Scenario**: Network partition during cascade revocation.

```
+--------+         +--------+         +--------+
|  DB    |  <===   | Node A |   X     | Node B |
| Primary|         |Revokes |   X     | Caches |
+--------+         +--------+   X     +--------+
                              Partition

Node A: Revokes Agent 1, 2, 3 successfully
Node B: Has cached trust for Agent 3, doesn't receive invalidation
Result: Agent 3 can act on Node B but is revoked on Node A
```

**Current Behavior**:
- No distributed coordination
- No invalidation broadcast
- No quorum requirement for revocation

**Risk**: CRITICAL - Split-brain trust state

**Proposed Solution**: Implement revocation fencing with epoch numbers:
```python
@dataclass
class RevocationFence:
    epoch: int  # Monotonically increasing
    revoked_at: datetime
    agent_ids: Set[str]

class TrustOperations:
    async def verify(self, agent_id: str, ...):
        # Check against revocation fence
        fence = await self._get_revocation_fence()
        if agent_id in fence.agent_ids:
            return VerificationResult(valid=False, reason="Revoked")

        # Check chain epoch against fence
        chain = await self.trust_store.get_chain(agent_id)
        if chain.epoch < fence.epoch:
            # Chain may be stale, re-validate
            await self._revalidate_chain(chain)
```

---

### 2.4 Circular Delegation (Graph Cycles)

**Scenario**: Delegation chain forms a cycle.

```
Agent A delegates to Agent B
Agent B delegates to Agent C
Agent C delegates to Agent A (cycle!)

Revocation of Agent A:
1. Revoke A
2. Find delegatees: [B]
3. Revoke B
4. Find delegatees: [C]
5. Revoke C
6. Find delegatees: [A] <- Already revoked, but...
7. Infinite recursion?
```

**Current Behavior** (`operations.py`, lines 1381-1390):
```python
async def revoke_cascade(self, agent_id: str, reason: str):
    # Revoke this agent
    try:
        await self.trust_store.delete_chain(agent_id, soft_delete=True)
        revoked_agents.append(agent_id)
    except TrustChainNotFoundError:
        return revoked_agents  # Agent doesn't exist - stops recursion
```

**Analysis**: Cycle detection is IMPLICIT via `TrustChainNotFoundError`. If the chain is already soft-deleted, `get_chain()` raises `TrustChainNotFoundError` and recursion stops.

**Risk**: LOW (implicit protection exists) but brittle

**Proposed Improvement**:
```python
async def revoke_cascade(self, agent_id: str, reason: str,
                         _visited: Optional[Set[str]] = None):
    _visited = _visited or set()

    if agent_id in _visited:
        logger.warning(f"Cycle detected in delegation chain: {agent_id}")
        return []

    _visited.add(agent_id)
    # ... rest of revocation
```

---

### 2.5 Concurrent Revocation (Diamond Problem)

**Scenario**: Two revocations propagate through overlapping subtrees.

```
           Human
           /    \
    Agent A      Agent B
           \    /
           Agent C  <-- Both A and B delegate to C

Revocation 1: Revoke Agent A (cascades to C)
Revocation 2: Revoke Agent B (also cascades to C)

Result: Race to revoke C
```

**Current Behavior**:
```python
cascade_tasks = [
    self.revoke_cascade(delegatee_id, ...)
    for delegatee_id in set(delegatee_ids)
]
results = await asyncio.gather(*cascade_tasks, return_exceptions=True)
```

**Risk**: MEDIUM - Duplicate revocation attempts, potentially duplicate audit records

**Evidence**:
- `set(delegatee_ids)` dedupes at single level
- No cross-cascade deduplication
- `delete_chain()` with soft_delete is idempotent on same agent but may write duplicate audit

**Proposed Solution**:
```python
class RevocationCoordinator:
    def __init__(self):
        self._pending_revocations: Dict[str, asyncio.Event] = {}
        self._completed_revocations: Set[str] = set()

    async def revoke_with_coordination(self, agent_id: str, reason: str):
        # Check if already being revoked
        if agent_id in self._pending_revocations:
            await self._pending_revocations[agent_id].wait()
            return  # Another task completed revocation

        # Check if already revoked
        if agent_id in self._completed_revocations:
            return

        # Claim revocation
        event = asyncio.Event()
        self._pending_revocations[agent_id] = event

        try:
            await self._do_revoke(agent_id, reason)
            self._completed_revocations.add(agent_id)
        finally:
            event.set()
            del self._pending_revocations[agent_id]
```

---

### 2.6 Revocation During Active Delegation

**Scenario**: Agent A is delegating to Agent B while Agent A is being revoked.

```
Timeline:
T0: Agent A calls delegate() to Agent B
T1: Revocation initiated for Agent A
T2: delegate() creates DelegationRecord (in flight)
T3: Revocation completes - Agent A marked revoked
T4: delegate() writes DelegationRecord to B's chain
T5: Agent B has delegation from revoked Agent A
```

**Current Behavior** (`operations.py`, lines 883-1118):
```python
async def delegate(self, delegator_id, delegatee_id, ...):
    # 1. Get delegator's trust chain
    delegator_chain = await self.trust_store.get_chain(delegator_id)

    # 2. Verify delegator has capabilities (no lock held)
    # ... validation logic ...

    # 3. Create delegation record
    delegation = DelegationRecord(...)

    # 4. Store in delegatee's chain (much later)
    await self.trust_store.store_chain(delegatee_chain)
    # No check if delegator was revoked between steps 1 and 4!
```

**Risk**: HIGH - Zombie delegation from revoked delegator

**Proposed Solution**: Optimistic locking with version check
```python
async def delegate(self, delegator_id, delegatee_id, ...):
    # Get chain with version
    delegator_chain, version = await self.trust_store.get_chain_versioned(delegator_id)

    # ... validation and delegation creation ...

    # Final store with version check
    try:
        await self.trust_store.store_chain_conditional(
            delegatee_chain,
            condition={"delegator_version": version}
        )
    except StaleVersionError:
        raise DelegationError("Delegator state changed during delegation")
```

---

### 2.7 Zombie Agents (In-Flight Work)

**Scenario**: Agent A is revoked while it has work in progress.

```
Agent A:
- Started long-running analysis at T0
- Revoked at T1
- Analysis completes at T2
- Tries to write results at T3

Questions:
1. Should the write be allowed?
2. What happens to partial work?
3. How do we track in-flight work for impact assessment?
```

**Current Behavior**:
- No tracking of in-flight work
- `revoke_cascade` doesn't interrupt running operations
- Results may be written after revocation

**Risk**: HIGH - Work completed after revocation may be invalid

**Proposed Solution**:
```python
class WorkTracker:
    """Track in-flight work for graceful revocation"""

    _active_work: Dict[str, List[WorkItem]] = {}

    async def register_work(self, agent_id: str, work_id: str):
        if agent_id not in self._active_work:
            self._active_work[agent_id] = []
        self._active_work[agent_id].append(WorkItem(work_id, datetime.now()))

    async def on_revocation(self, agent_id: str) -> List[str]:
        """Returns list of in-flight work to abort/monitor"""
        return self._active_work.pop(agent_id, [])

class TrustedAgent:
    async def execute_async(self, ...):
        work_id = str(uuid.uuid4())
        await self._work_tracker.register_work(self.agent_id, work_id)

        try:
            # Check for revocation before critical write
            if await self._is_revoked():
                raise RevocationDuringExecutionError()

            result = await self._agent.execute_async(...)

            # Final revocation check before commit
            if await self._is_revoked():
                raise RevocationDuringExecutionError()

            return result
        finally:
            await self._work_tracker.complete_work(self.agent_id, work_id)
```

---

### 2.8 Revocation Rollback

**Scenario**: Mistaken revocation needs to be undone.

**Current Behavior**:
- Soft delete sets `is_active=False`
- No built-in "unrevoke" mechanism
- No audit trail of revocation reason

**Questions**:
1. Should revocation be reversible?
2. What happens to cascaded revocations?
3. How to handle delegations that expired during revocation?

**Risk**: MEDIUM - Manual database intervention currently required

**Proposed Solution**:
```python
async def restore_trust(self, agent_id: str, reason: str, authority_id: str):
    """Restore revoked trust (requires authority approval)"""

    # 1. Verify authority has RESTORE permission
    await self._validate_authority_permission(authority_id, "RESTORE")

    # 2. Check chain exists (soft-deleted)
    chain = await self.trust_store.get_chain(agent_id, include_inactive=True)

    # 3. Verify chain hasn't expired during revocation
    if chain.is_expired():
        raise TrustRestorationError("Chain expired during revocation period")

    # 4. Re-activate (does NOT cascade)
    await self.trust_store.update_chain(agent_id, {"is_active": True})

    # 5. Audit the restoration
    await self.audit(
        agent_id=agent_id,
        action="trust_restored",
        context={"reason": reason, "restored_by": authority_id}
    )

    return chain
```

---

## 3. Risk Register

| ID | Edge Case | Likelihood | Impact | Current Mitigation | Proposed Solution |
|----|-----------|------------|--------|-------------------|-------------------|
| CR-001 | Action executes during revocation | HIGH | CRITICAL | None | Execution fencing with version check |
| CR-002 | Cache serves stale trust | HIGH | HIGH | None (placeholder) | Push invalidation + epoch tracking |
| CR-003 | Network partition splits revocation | MEDIUM | CRITICAL | None | Revocation fencing protocol |
| CR-004 | Circular delegation recursion | LOW | MEDIUM | Implicit via error | Explicit visited set |
| CR-005 | Concurrent revocation race | MEDIUM | LOW | set() dedup | RevocationCoordinator |
| CR-006 | Delegation during revocation | MEDIUM | HIGH | None | Optimistic locking |
| CR-007 | Zombie in-flight work | MEDIUM | HIGH | None | WorkTracker + abort |
| CR-008 | No revocation rollback | LOW | MEDIUM | None | restore_trust() operation |

---

## 4. Sequence Diagrams

### 4.1 Current Cascade Revocation

```
┌─────────┐          ┌───────────┐          ┌───────────┐          ┌───────────┐
│Authority│          │TrustOps   │          │TrustStore │          │  Cache    │
└────┬────┘          └─────┬─────┘          └─────┬─────┘          └─────┬─────┘
     │ revoke_cascade(A)   │                      │                      │
     │────────────────────►│                      │                      │
     │                     │ delete_chain(A)      │                      │
     │                     │─────────────────────►│                      │
     │                     │                      │                      │
     │                     │ list_chains()        │                      │
     │                     │─────────────────────►│                      │
     │                     │◄─────────────────────│                      │
     │                     │                      │                      │
     │                     │─┐ For each delegatee                        │
     │                     │ │ revoke_cascade(B)                         │
     │                     │◄┘                                           │
     │                     │ delete_chain(B)      │                      │
     │                     │─────────────────────►│                      │
     │                     │                      │                      │
     │                     │      [NO CACHE INVALIDATION!]               │
     │◄────────────────────│                      │                      │
     │ return revoked_ids  │                      │                      │
```

### 4.2 Proposed Cascade Revocation with Fencing

```
┌─────────┐      ┌───────────┐      ┌───────────┐      ┌───────────┐      ┌─────────┐
│Authority│      │TrustOps   │      │TrustStore │      │  Cache    │      │Fence Svc│
└────┬────┘      └─────┬─────┘      └─────┬─────┘      └─────┬─────┘      └────┬────┘
     │ revoke(A)       │                  │                  │                 │
     │────────────────►│                  │                  │                 │
     │                 │ acquire_fence(A)                    │                 │
     │                 │────────────────────────────────────────────────────►│
     │                 │                                     │ epoch=42       │
     │                 │◄────────────────────────────────────────────────────│
     │                 │                  │                  │                 │
     │                 │ delete_chain(A, epoch=42)           │                 │
     │                 │──────────────────►│                  │                 │
     │                 │                  │                  │                 │
     │                 │ broadcast_invalidation(A, epoch=42) │                 │
     │                 │─────────────────────────────────────►│                │
     │                 │                  │                  │                 │
     │                 │ publish_revocation_event(A)         │                 │
     │                 │────────────────────────────────────────────────────►│
     │                 │                  │                  │                 │
     │                 │─┐ cascade_revoke_fenced(B, epoch=42)                 │
     │                 │ │                │                  │                 │
     │                 │◄┘                │                  │                 │
     │◄────────────────│                  │                  │                 │
```

---

## 5. Implementation Priority

### Immediate (Week 1-2)
1. **CR-002**: Implement cache invalidation on revocation
2. **CR-004**: Add explicit cycle detection in `revoke_cascade`
3. **CR-007**: Add revocation check before action commit

### Short-term (Week 3-4)
4. **CR-001**: Implement execution fencing with version tokens
5. **CR-006**: Add optimistic locking to delegation
6. **CR-005**: Implement RevocationCoordinator for concurrent revocations

### Medium-term (Week 5-8)
7. **CR-003**: Design and implement revocation fencing protocol
8. **CR-008**: Implement trust restoration with proper safeguards
