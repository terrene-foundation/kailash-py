# EATP SDK Gaps -- Spec Alignment Evaluation

**Date**: 2026-03-14
**Evaluator**: eatp-expert
**Package**: `packages/eatp/src/eatp/` (v0.1.0)
**Methodology**: Each gap evaluated against the EATP Core Thesis, EATP specification, and architectural principles

---

## Executive Summary

Of the 11 identified gaps, **9 are genuine EATP SDK responsibilities** that should be addressed in the SDK itself. Two gaps (G10, G11) are boundary cases that belong partially in a bridge/adapter layer rather than the core SDK. The proposed priority order is largely sound, with one significant re-ordering recommendation: G5 should be elevated above G1 due to its production safety implications and low implementation complexity.

The analysis also identifies **3 missing gaps** not captured in the original brief that represent trust model weaknesses.

---

## 1. Gap-by-Gap Spec Alignment

### G1: Behavioral Trust Scoring

**Is this gap real?** Yes, with a nuance.

The EATP specification defines trust scoring with five structural factors (chain completeness, delegation depth, constraint coverage, posture level, chain recency). The spec does not explicitly mandate behavioral scoring as a separate module. However, the EATP Core Thesis states that trust postures "upgrade as trust builds through demonstrated performance" and "downgrade instantly if conditions change." The word "demonstrated performance" implies runtime behavioral observation -- not just static chain analysis.

**Spec sections that support this:**

- Trust Postures: "Postures upgrade as trust builds through demonstrated performance."
- Verification Gradient: The FLAGGED/HELD/BLOCKED classification inherently requires understanding of proximity to boundaries, which requires tracking behavioral history.
- The existing `PostureStateMachine` already tracks transition history, and `PostureCircuitBreaker` already tracks failure events -- both are behavioral signals. The gap is that these signals are not unified into the scoring system.

**Where does it belong?**
The EATP SDK is the correct home. The scoring module already lives at `eatp/scoring.py` and computes trust scores. Behavioral scoring is the complement to structural scoring -- together they form the complete trust assessment. Downstream consumers (CARE Platform, Kaizen) should consume the combined score, not build their own behavioral scorer.

**However**: The behavioral factors described (interaction history, approval rate, error rate, posture stability, time-at-posture) require runtime state that the EATP SDK currently does not persist. The SDK would need either:

- A `BehavioralStore` protocol (abstract interface for persisting behavioral data)
- Or acceptance that behavioral scoring operates on in-memory state only (acceptable for single-process deployments)

**Trust model impact:**

- Strengthens verification gradient: behavioral history enables context-aware proximity assessment
- Improves trust scoring fidelity: structural scoring alone is a snapshot; behavioral scoring adds trajectory
- Enables meaningful posture evolution: without behavioral data, posture upgrade/downgrade decisions lack empirical grounding
- Does NOT close a trust circumvention vector directly

**Verdict: REAL GAP. BELONGS IN EATP SDK. Severity CRITICAL is appropriate but the brief's own priority sequencing (G1 = 4th) is correct -- G2, G3, G4 are more foundational.**

---

### G2: Constraint Proximity Thresholds in Verification Gradient

**Is this gap real?** Yes, and it is the most architecturally significant gap.

The EATP specification defines four verification outcomes: AUTO_APPROVED, FLAGGED, HELD, BLOCKED. The current `StrictEnforcer.classify()` method (lines 126-146 of `enforce/strict.py`) bases its classification solely on the _count_ of violations:

- 0 violations = AUTO_APPROVED
- > 0 but < flag_threshold = FLAGGED
- > = flag_threshold = HELD
- invalid result = BLOCKED

This misses the core EATP insight. The verification gradient table explicitly states:

- FLAGGED = "Near constraint boundary"
- HELD = "Soft limit exceeded"

"Near constraint boundary" requires knowing the _utilization ratio_ (used/limit), not just whether a hard violation occurred. An agent at 95% of its budget passes as AUTO_APPROVED because it has not yet violated anything -- but the next action could push it over, resulting in an abrupt BLOCKED with no warning. This defeats the purpose of graduated verification.

The `ConstraintCheckResult` dataclass in `constraints/dimension.py` already has `remaining`, `used`, and `limit` fields (lines 101-121). The `MultiDimensionEvaluator` already detects boundary pushing at 0.95 ratio as an anti-gaming flag. The infrastructure for proximity detection exists -- it is just not wired into the enforcement verdict classification.

**Spec sections that support this:**

- Verification Gradient: The four-level table is the defining feature of EATP verification. Without proximity thresholds, the SDK implements a binary (pass/fail) system with violation counting, not a true gradient.
- The kailash-rs implementation already has configurable `flag_threshold` (0.80) and `hold_threshold` (0.95) in `VerificationConfig`, confirming this is an intentional EATP design choice that the Python SDK has not yet implemented.

**Where does it belong?**
Unambiguously in the EATP SDK. The verification gradient is a core EATP concept, not a downstream concern. The `StrictEnforcer` and `ShadowEnforcer` must be extended (not replaced) to consume `ConstraintCheckResult.used`/`limit` ratios when classifying verdicts.

**Trust model impact:**

- Directly enables the verification gradient as specified -- this is not an enhancement, it is completing an incomplete implementation
- Closes a trust circumvention vector: without proximity warnings, agents can operate at 99% of limits indefinitely without any escalation, then suddenly hit BLOCKED
- Enables defense-in-depth: graduated warnings create multiple opportunities for human intervention before hard limits

**Verdict: REAL GAP. BELONGS IN EATP SDK. Severity CRITICAL is correct. Priority #1 is correct -- this is the most impactful gap per line of code.**

---

### G3: EATP Lifecycle Hooks

**Is this gap real?** Yes, but the scope needs tightening.

The EATP spec does not explicitly define a hook system. However, the spec describes trust verification as something that happens "before every agent action" -- which implies an interception mechanism. The current SDK provides only decorators (`@verified`, `@audited`, `@shadow`), which require wrapping individual functions at definition time. This is fine for application developers who control their own code, but insufficient for framework integration where the interception point is at the runtime level.

The proposed hook types map well to EATP operations:

- `PRE_TOOL_USE` / `POST_TOOL_USE` = VERIFY before action, AUDIT after action
- `SUBAGENT_SPAWN` = ESTABLISH for the sub-agent + DELEGATE from parent
- `PRE_DELEGATION` / `POST_DELEGATION` = DELEGATE operation lifecycle

**Where does it belong?**
This is a boundary case. The hook _protocol_ (interface definition, registry pattern, priority ordering) belongs in the EATP SDK. The concrete _implementations_ (intercepting Kaizen tool calls, wiring into specific agent frameworks) belong in downstream packages.

Specifically:

- `eatp/hooks.py` should define `TrustHook` (Protocol/ABC), `HookType` (Enum), `HookRegistry`, and `HookResult`
- `kailash-kaizen` should implement `KaizenToolHook(TrustHook)` that bridges to the Kaizen tool execution lifecycle
- The CARE Platform should register its own hooks for governance-specific interception

**Trust model impact:**

- Enables defense-in-depth: hooks + decorators layer independently, so a bypass of one does not bypass the other
- Improves composability: third parties can add enforcement without modifying core EATP or application code
- Does not directly strengthen the verification gradient or close circumvention vectors -- this is an extensibility mechanism

**Verdict: PARTIALLY REAL GAP. The hook protocol belongs in EATP SDK. Concrete implementations belong downstream. Severity CRITICAL is slightly overstated -- this is HIGH in isolation, but becomes CRITICAL when considering the Kaizen integration dependency. Priority #2 is reasonable.**

---

### G4: Per-Agent Circuit Breaker Registry

**Is this gap real?** Yes.

The `PostureCircuitBreaker` (in `circuit_breaker.py`) already tracks per-agent state internally via `Dict[str, CircuitState]`, `Dict[str, List[FailureEvent]]`, etc. However, the class is designed to be a single shared instance managing all agents. There is no mechanism to:

- Create isolated breaker configurations per agent (different thresholds for different risk profiles)
- Bulk-query circuit status across all agents
- Clean up state for decommissioned agents
- Apply different `CircuitBreakerConfig` per agent

The gap is real but the brief's description slightly mischaracterizes it. The current `PostureCircuitBreaker` already IS a per-agent registry in function (it keys all dicts by `agent_id`). What is missing is:

1. Per-agent configuration overrides (the config is global today)
2. Lazy creation with configurable defaults
3. Bulk status reporting
4. Idle agent cleanup

**Where does it belong?**
EATP SDK. The circuit breaker is already an EATP module. A registry wrapper is a natural extension.

**Trust model impact:**

- Enables differentiated trust management: high-risk agents can have tighter failure thresholds than low-risk agents
- Improves production operability but does not directly strengthen the trust model
- Does not close circumvention vectors

**Verdict: REAL GAP, slightly overstated. BELONGS IN EATP SDK. Severity HIGH is correct. Priority #3 is correct.**

---

### G5: ShadowEnforcer Bounded Memory

**Is this gap real?** Yes, and it is a production safety issue.

The `ShadowEnforcer._records` list (line 88 of `enforce/shadow.py`) grows unbounded. In a long-running shadow deployment evaluating thousands of agent actions per hour, this is a memory leak that will eventually crash the process. The `PostureStateMachine` already solved this problem with bounded history (`_max_history_size = 10000` with oldest-10% trimming, lines 209-232 of `postures.py`). The pattern exists in the codebase; it was simply not applied to ShadowEnforcer.

Additionally:

- Missing `change_rate` metric (how often decisions flip between categories -- an indicator of policy instability)
- Missing `try/except` around shadow evaluation in the `check()` method -- shadow enforcement should never crash the main execution path

**Where does it belong?**
EATP SDK. This is a fix to an existing EATP module.

**Trust model impact:**

- Does not directly affect the trust model
- Prevents denial-of-service through memory exhaustion during shadow rollout
- The `change_rate` metric provides signal about policy instability, which is operationally valuable for tuning constraints

**Verdict: REAL GAP. BELONGS IN EATP SDK. Severity HIGH is correct. I DISAGREE with the priority placement at #5. This should be elevated to #4 (ahead of G1) because it is a simple fix with high production impact and minimal design risk. G1 (behavioral scoring) requires spec alignment work; G5 is a bounded, well-understood fix.**

---

### G6: Dual-Signature on Audit Anchors

**Is this gap real?** Yes, but as a performance optimization, not a correctness gap.

The EATP Core Thesis describes dual signing for speed/non-repudiation separation:

- HMAC-SHA256 for internal verification (symmetric, fast, ~microseconds)
- Ed25519 for external non-repudiation (asymmetric, slower, ~50ms)

The current implementation uses Ed25519 only. This is correct and secure but potentially slower for high-throughput internal verification scenarios. The dual-signature pattern is an optimization for enterprises that verify thousands of audit anchors per second internally and only need Ed25519 for external compliance.

**Where does it belong?**
EATP SDK. The audit anchor signing/verification is a core EATP concern. The dual-signature pattern should be an opt-in feature of the existing crypto and anchor modules.

**Trust model impact:**

- Does not strengthen the verification gradient
- Does not close circumvention vectors
- Enables higher throughput for internal verification, which improves the practical viability of comprehensive audit trails
- Adds defense-in-depth: HMAC provides integrity verification independent of Ed25519

**Verdict: REAL GAP but LOW urgency. BELONGS IN EATP SDK. Severity HIGH is slightly overstated -- this is MEDIUM. Priority #6 is reasonable.**

---

### G7: AWSKMSKeyManager Stub

**Is this gap real?** Yes, and it violates the project's no-stubs directive.

The `AWSKMSKeyManager` class (lines 595-831 of `key_manager.py`) has every method raising `NotImplementedError`. This is a clear stub. The `KeyManagerInterface` ABC is well-defined, and the `InMemoryKeyManager` provides a working implementation -- but production environments need at least one cloud KMS backend.

**Where does it belong?**
This is nuanced. The `KeyManagerInterface` protocol MUST stay in the EATP SDK. But the AWS KMS implementation could reasonably live in:

- The EATP SDK itself (as `eatp.key_manager_aws`) -- simplest for users
- A separate optional package (`eatp-kms-aws`) -- cleaner dependency isolation (avoids requiring boto3 for all EATP users)

I recommend the second approach: ship the AWS KMS backend as an optional extra (`pip install eatp[aws-kms]`) with a lazy import pattern so boto3 is only required when the AWS backend is actually used.

**Trust model impact:**

- Does not affect the trust model directly
- A stub is worse than no class at all because it suggests the capability exists when it does not
- Production readiness depends on having at least one non-in-memory key management backend

**Verdict: REAL GAP. INTERFACE BELONGS IN EATP SDK. Implementation could be EATP SDK optional extra or separate package. Severity MEDIUM is correct. Priority #8 is reasonable.**

---

### G8: Deprecated `get_event_loop()` in Sync Decorators

**Is this gap real?** Yes.

Lines 94 and 182 of `enforce/decorators.py` use `asyncio.get_event_loop()` which is deprecated in Python 3.12+ and will emit `DeprecationWarning`. When called inside a running event loop (common in Jupyter notebooks, async web frameworks), it either:

- Returns the running loop (which then raises `RuntimeError` on `run_until_complete()`)
- Creates a new loop in Python <3.10 (unreliable behavior)

The correct approach for sync wrappers of async code is:

```python
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = None

if loop is not None:
    # Already in an async context -- cannot use run_until_complete
    raise RuntimeError(
        "Cannot use sync decorator inside running event loop. "
        "Use the async version or await directly."
    )
else:
    result = asyncio.run(coroutine)
```

**Where does it belong?**
EATP SDK. This is a bug fix in existing EATP code.

**Trust model impact:**

- None. This is a Python compatibility fix.
- However, if the sync decorators fail silently, enforcement is bypassed entirely -- which IS a trust model concern. So the fix has indirect trust significance.

**Verdict: REAL GAP. BELONGS IN EATP SDK. Severity MEDIUM is correct. Priority #7 is correct.**

---

### G9: asyncio.Lock vs threading.Lock on Circuit Breaker

**Is this gap real?** Yes, but the impact is narrow.

The `PostureCircuitBreaker` uses `asyncio.Lock()` (line 166 of `circuit_breaker.py`), which is safe for concurrent coroutine access within a single thread but does NOT protect against multi-threaded access. If the circuit breaker is used from multiple threads (e.g., in a multi-threaded web server or worker pool), race conditions could cause:

- Failure counts to be lost (non-atomic dict operations)
- Circuit state transitions to be missed
- Double-downgrade of postures

**Where does it belong?**
EATP SDK. The fix is either:

1. Document that `PostureCircuitBreaker` is async-only (acceptable for v0.1.0)
2. Add a `thread_safe` parameter that switches between `asyncio.Lock` and `threading.Lock` + `time.monotonic()` (better)

**Trust model impact:**

- Race conditions in the circuit breaker could cause an agent to continue operating after its circuit should have been opened -- a trust violation
- The impact is limited to multi-threaded deployments

**Verdict: REAL GAP. BELONGS IN EATP SDK. Severity MEDIUM is correct. Priority #10 is correct -- document the limitation first, fix in a subsequent release.**

---

### G10: Posture/Constraint Dimension Adapter Modules

**Is this gap real?** Partially.

The gap claims that there is no canonical bidirectional mapping between "CARE labels" and "EATP SDK vocabulary." However, this presupposes that the CARE Platform uses different terminology for the same concepts -- which is a CARE Platform integration concern, not an EATP SDK concern.

EATP defines its own vocabulary:

- Trust postures: PSEUDO_AGENT, SUPERVISED, SHARED_PLANNING, CONTINUOUS_INSIGHT, DELEGATED
- Constraint types: FINANCIAL, OPERATIONAL, TEMPORAL, DATA_ACCESS, COMMUNICATION
- Verification levels: QUICK, STANDARD, FULL

If the CARE Platform uses different labels for the same concepts, the adapter (mapping layer) should live in the CARE Platform or in a bridge package -- NOT in the EATP SDK. The EATP SDK should be authoritative about its own vocabulary; it should not contain adapters for every possible downstream consumer's terminology.

**Where does it belong?**

- The canonical EATP enums and constants ALREADY live in the EATP SDK (they are well-defined)
- Adapter/mapping functions (`to_eatp()` / `from_eatp()`) belong in the CARE Platform or a `care-eatp-bridge` package
- The EATP SDK MAY provide a `vocabulary.py` module with machine-readable descriptions of all enum values to facilitate downstream adapters

**Trust model impact:**

- Vocabulary drift is a real risk that could cause misclassification, but the mitigation is for downstream consumers to map to EATP vocabulary, not for EATP to maintain adapters for all consumers

**Verdict: PARTIALLY REAL GAP. Does NOT fully belong in EATP SDK. The EATP SDK should be authoritative about its vocabulary; adapters belong downstream. Severity MEDIUM is overstated -- this is LOW from the EATP SDK perspective. Priority #9 is correct given the downstream placement.**

---

### G11: Built-in Dimension Registry Naming Mismatch

**Is this gap real?** Partially.

The `BUILTIN_DIMENSIONS` set in `ConstraintDimensionRegistry` (line 359-368 of `constraints/dimension.py`) uses names like `cost_limit`, `time_window`, `resources`, `rate_limit`, `geo_restrictions`, `budget_limit`, `max_delegation_depth`, `allowed_actions`. The EATP spec's five canonical constraint dimensions are FINANCIAL, OPERATIONAL, TEMPORAL, DATA_ACCESS, COMMUNICATION.

There IS a disconnect: the built-in dimensions use SDK-specific names while the spec uses broader category names. But this is intentional -- the SDK dimensions are more granular than the spec categories. `cost_limit` and `budget_limit` are both FINANCIAL constraints. `rate_limit` and `allowed_actions` are both OPERATIONAL constraints.

The registry should arguably map each built-in dimension to its EATP canonical category. This is a metadata enrichment, not a naming change.

**Where does it belong?**
EATP SDK, as a metadata enhancement to the `ConstraintDimension` base class -- add an `eatp_category` property that maps to the canonical ConstraintType enum.

**Trust model impact:**

- Naming alignment prevents misclassification errors
- Minimal trust model impact

**Verdict: PARTIALLY REAL GAP. The enrichment belongs in EATP SDK. Severity LOW is correct. Priority #11 is correct.**

---

## 2. Boundary Analysis Summary

| Gap                           | EATP SDK?                      | CARE Platform?  | Kaizen?                       | Bridge Package?     |
| ----------------------------- | ------------------------------ | --------------- | ----------------------------- | ------------------- |
| G1 (Behavioral scoring)       | **PRIMARY**                    | Consumes        | Feeds data                    | -                   |
| G2 (Proximity thresholds)     | **PRIMARY**                    | -               | -                             | -                   |
| G3 (Lifecycle hooks)          | **Protocol only**              | Registers hooks | **Implements concrete hooks** | -                   |
| G4 (Circuit breaker registry) | **PRIMARY**                    | -               | Consumes                      | -                   |
| G5 (ShadowEnforcer memory)    | **PRIMARY**                    | -               | -                             | -                   |
| G6 (Dual-signature)           | **PRIMARY**                    | -               | -                             | -                   |
| G7 (KMS stub)                 | **Interface + optional extra** | -               | -                             | -                   |
| G8 (Deprecated async)         | **PRIMARY**                    | -               | -                             | -                   |
| G9 (Threading)                | **PRIMARY**                    | -               | -                             | -                   |
| G10 (Adapters)                | Vocabulary docs only           | **PRIMARY**     | -                             | **Adapter package** |
| G11 (Dimension registry)      | **Metadata enrichment**        | -               | -                             | -                   |

---

## 3. Trust Model Impact Assessment

### Gaps that Strengthen the Verification Gradient

- **G2 (Proximity thresholds)**: DIRECT -- completes the graduated verification system
- **G1 (Behavioral scoring)**: INDIRECT -- provides data for context-aware verification

### Gaps that Improve Trust Scoring Fidelity

- **G1 (Behavioral scoring)**: DIRECT -- adds trajectory data to point-in-time structural assessment
- **G11 (Dimension registry)**: MINOR -- prevents category misclassification

### Gaps that Close Trust Circumvention Vectors

- **G2 (Proximity thresholds)**: Prevents "silent approach to limits" pattern
- **G9 (Threading)**: Prevents race-condition-based circuit breaker bypass
- **G5 (ShadowEnforcer memory)**: Prevents denial-of-service during shadow rollout

### Gaps that Enable Defense-in-Depth

- **G3 (Lifecycle hooks)**: Hooks + decorators layer independently
- **G6 (Dual-signature)**: HMAC + Ed25519 provide independent verification paths
- **G4 (Circuit breaker registry)**: Per-agent isolation prevents cross-agent contamination

### Gaps with No Direct Trust Model Impact

- **G7 (KMS stub)**: Production readiness concern, not trust model concern
- **G8 (Deprecated async)**: Python compatibility fix (indirect trust impact if enforcement silently fails)
- **G10 (Adapters)**: Vocabulary alignment concern

---

## 4. Priority Re-evaluation

### Brief's Proposed Order

G2 -> G3 -> G4 -> G1 -> G5 -> G6 -> G8 -> G7 -> G10 -> G9 -> G11

### My Recommended Order

G2 -> G3 -> G4 -> **G5** -> G1 -> G8 -> G6 -> G7 -> G9 -> G10 -> G11

### Rationale for Changes

**G5 elevated from #5 to #4 (ahead of G1):**
G5 (ShadowEnforcer bounded memory) is a simple, well-understood fix with zero design risk. The pattern already exists in `PostureStateMachine`. G1 (behavioral scoring) requires spec alignment work, new data model design, and careful integration with the existing structural scorer. Fixing G5 before starting G1 ensures production stability during shadow rollouts, which are likely happening NOW while G1 is being designed.

**G8 elevated from #7 to #6 (ahead of G6):**
G8 is a Python 3.12+ compatibility fix that affects any user running the sync decorators. If users are on Python 3.12+, the sync enforcement path is broken NOW. G6 (dual-signature) is a performance optimization. Fix the broken path before optimizing the working one.

**G6 moved from #6 to #7:**
Dual-signature is a performance optimization, not a correctness fix. It can wait.

**G10 moved from #9 to #10 (behind G9):**
G10 mostly does not belong in the EATP SDK (see boundary analysis). The EATP SDK contribution is limited to vocabulary documentation, which is low effort and low urgency.

### Recommended Grouping for Implementation

**Sprint 1 (Production Safety)**:

- G2: Proximity thresholds (highest impact, moderate complexity)
- G5: ShadowEnforcer bounded memory (simple fix)
- G8: Deprecated async fix (simple fix)

**Sprint 2 (Extensibility)**:

- G3: Lifecycle hooks protocol
- G4: Circuit breaker registry

**Sprint 3 (Trust Scoring)**:

- G1: Behavioral trust scoring

**Sprint 4 (Production Hardening)**:

- G6: Dual-signature
- G7: KMS implementation (optional extra)
- G9: Threading documentation/fix

**Sprint 5 (Ecosystem Alignment)**:

- G10: Vocabulary documentation (EATP SDK portion)
- G11: Dimension registry metadata enrichment

---

## 5. Missing Gaps

The following trust model weaknesses were NOT identified in the brief but should be considered:

### MG1: No Cascade Revocation Implementation

**Severity: HIGH**

The EATP spec explicitly defines cascade revocation: "When trust is revoked at any level, all downstream delegations are automatically revoked. No orphaned agents continue operating after their authority source is removed."

The current SDK has no implementation of this mechanism. `TrustOperations` has no `revoke()` method. The `DelegationRecord` has `parent_delegation_id` for chain traversal, but there is no code that walks the delegation tree and revokes downstream chains when a parent is revoked.

The EATP Core Thesis acknowledges this is architecturally challenging: "Immediate and atomic is an architectural goal. Distributed systems have propagation latency. Mitigations: short-lived credentials (5-minute validity), push-based revocation, action idempotency."

Even so, the SDK should provide at least:

- A `revoke_delegation()` operation on `TrustOperations`
- A `find_downstream_delegations()` method on `TrustStore`
- Short-lived credential enforcement (credential validity periods with forced re-verification)

This is more impactful than several of the identified gaps and is a core EATP operation, not an enhancement.

### MG2: No Monotonic Constraint Tightening Enforcement at VERIFY Time

**Severity: MEDIUM**

The EATP spec's critical rule: "delegations can only reduce authority, never expand it." The SDK implements `validate_tightening()` on `ConstraintDimension` and `MultiDimensionEvaluator`, but this validation is only called during DELEGATE operations, not during VERIFY.

If a delegation chain is constructed with proper tightening but then the parent delegation's constraints are modified (via store manipulation or a store implementation bug), subsequent VERIFY operations will use the modified (potentially loosened) constraints without detecting the violation.

The VERIFY operation should optionally re-validate monotonic tightening across the delegation chain (at STANDARD or FULL level) to detect constraint corruption.

### MG3: StrictEnforcer.\_records Unbounded (Same Issue as G5)

**Severity: MEDIUM**

The same unbounded memory issue identified in G5 for `ShadowEnforcer._records` also exists in `StrictEnforcer._records` (line 120 of `enforce/strict.py`) and `StrictEnforcer._review_queue` (line 121). These lists grow without bound in long-running processes.

This should be bundled with G5 as a single fix: add bounded memory to all enforcer record lists.

---

## 6. Cross-Reference: EATP Governance Layer Thesis

The brief's gap analysis aligns with the Governance Layer Thesis assessment of Claude Code CLI implementing ~5% of EATP. Specifically:

| EATP Element          | Current SDK Coverage                                             | Gaps That Improve It                                           |
| --------------------- | ---------------------------------------------------------------- | -------------------------------------------------------------- |
| Constraint Envelope   | ~30% (five dimensions implemented, no proximity)                 | G2 directly, G11 indirectly                                    |
| Verification Gradient | ~40% (4-category classification exists, no graduated thresholds) | G2 directly                                                    |
| Trust Postures        | ~70% (5 postures, state machine, transition guards)              | G1 indirectly (behavioral scoring informs posture transitions) |
| Audit Anchor          | ~60% (Ed25519 signing, linear hash chain)                        | G6 (dual-signature)                                            |
| Cascade Revocation    | 0%                                                               | MG1 (not in brief)                                             |
| Monotonic Tightening  | ~50% (validated at DELEGATE, not at VERIFY)                      | MG2 (not in brief)                                             |

---

## 7. Conclusion

The gap analysis is thorough and well-grounded. Nine of 11 gaps are genuine EATP SDK responsibilities. The two boundary cases (G10, G11) are correctly identified as lower priority. Three additional gaps (MG1: cascade revocation, MG2: monotonic tightening at VERIFY, MG3: StrictEnforcer unbounded records) should be added to the backlog.

The most architecturally significant gap is G2 (proximity thresholds), which completes the verification gradient -- the defining feature of EATP's approach to trust verification. The recommended implementation sequence prioritizes production safety (G2, G5, G8), then extensibility (G3, G4), then trust model enrichment (G1), then production hardening (G6-G9), and finally ecosystem alignment (G10-G11).

---

**Files analyzed:**

- `/Users/esperie/repos/kailash/kailash-py/workspaces/eatp-gaps/briefs/01-eatp-sdk-gaps.md`
- `/Users/esperie/repos/kailash/kailash-py/workspaces/eatp-gaps/01-analysis/01-gap-details.md`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/scoring.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/enforce/strict.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/enforce/shadow.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/postures.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/chain.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/operations/__init__.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/enforce/decorators.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/circuit_breaker.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/key_manager.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/constraints/dimension.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/constraints/evaluator.py`
- `/Users/esperie/repos/kailash/kailash-py/packages/eatp/src/eatp/constraints/builtin.py`
