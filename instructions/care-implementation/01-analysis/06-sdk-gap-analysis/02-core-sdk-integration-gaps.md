# Core SDK Runtime Trust Integration Gaps

## Executive Summary

The Core SDK (`./src/kailash/runtime/`) provides the foundational runtime for all Kailash frameworks. Currently, it offers basic security through `enable_security`, `enable_audit`, and `user_context` parameters in BaseRuntime, plus an opt-in RBAC wrapper via AccessControlledRuntime. However, there is no EATP trust chain integration, no trust context propagation through workflow execution, and no EATP-compliant audit generation.

Since Core SDK is the foundation that DataFlow, Nexus, and Kaizen all build upon, these gaps propagate to all downstream frameworks.

---

## 1. Current State Analysis

### BaseRuntime (`base.py:88-686`)

The BaseRuntime provides 29 configuration parameters including security-relevant ones:

| Parameter               | Purpose                            | Trust Relevance                              |
| ----------------------- | ---------------------------------- | -------------------------------------------- |
| `enable_security`       | Boolean flag for security features | No EATP integration; binary on/off           |
| `enable_audit`          | Boolean flag for audit logging     | Not EATP-compliant audit; basic logging only |
| `user_context`          | Dictionary for user metadata       | Not structured for trust chain; opaque dict  |
| `debug`                 | Debug mode                         | Potential information leak in production     |
| `connection_validation` | Validates node connections         | Structural only, no trust validation         |

### AccessControlledRuntime (`access_controlled.py:48-481`)

The AccessControlledRuntime wraps LocalRuntime with RBAC-based permission checks:

| Feature                   | Status              | Trust Gap                                            |
| ------------------------- | ------------------- | ---------------------------------------------------- |
| Role-based access control | Implemented         | Not integrated with EATP capability attestations     |
| Permission checking       | Implemented         | Static permissions, no delegation chain verification |
| User identity             | Basic user_id       | No trust chain identity verification                 |
| Audit logging             | Basic event logging | Not cryptographically signed, not immutable          |

---

## 2. Gap Analysis

| Capability                 | EATP Requirement                                                                 | Core SDK Status                     | Gap                                       | Severity |
| -------------------------- | -------------------------------------------------------------------------------- | ----------------------------------- | ----------------------------------------- | -------- |
| Trust Lineage Integration  | Runtime should verify trust chain before workflow execution                      | NOT PRESENT                         | No TrustChain verification in `execute()` | CRITICAL |
| Workflow-Level Delegation  | Workflows should carry delegation records defining what they're authorized to do | NOT PRESENT                         | No delegation metadata on Workflow object | HIGH     |
| Node-Level Trust           | Individual nodes should check capability attestations before executing           | AccessControlledRuntime only (RBAC) | Not integrated with EATP chain            | HIGH     |
| Audit Trail Linkage        | Workflow execution should produce EATP-compliant audit anchors                   | `enable_audit=False` default        | No EATP-compliant audit                   | CRITICAL |
| Trust Context Propagation  | Trust context should flow through entire execution pipeline                      | `user_context` only (opaque dict)   | No delegation/constraint context          | HIGH     |
| Constraint Enforcement     | Runtime should enforce constraint envelopes during execution                     | NOT PRESENT                         | No constraint checking in execute path    | HIGH     |
| Trust-Aware Error Handling | Trust violations should produce specific error types                             | NOT PRESENT                         | Generic exceptions only                   | MEDIUM   |

---

## 3. Missing Integration Points

### 3.1 BaseRuntime Trust Extension (`base.py`)

**Current initialization** (simplified):

```python
class BaseRuntime:
    def __init__(self, ..., enable_security=False, enable_audit=False, user_context=None):
        self._enable_security = enable_security
        self._enable_audit = enable_audit
        self._user_context = user_context or {}
```

**What is missing**:

```python
# MISSING: Trust-aware execution parameters
class BaseRuntime:
    def __init__(self, ...,
                 trust_context: Optional[TrustContext] = None,
                 trust_verifier: Optional[TrustVerifier] = None,
                 constraint_enforcer: Optional[ConstraintEnforcer] = None,
                 audit_anchor_generator: Optional[AuditAnchorGenerator] = None):
        self._trust_context = trust_context
        self._trust_verifier = trust_verifier
        self._constraint_enforcer = constraint_enforcer
        self._audit_anchor_generator = audit_anchor_generator
```

### 3.2 Workflow Trust Metadata

**Current Workflow object**: Carries node definitions, connections, and parameters only.

**What is missing**:

- `delegation_record`: The delegation chain authorizing this workflow's execution
- `constraint_envelope`: The constraints bounding this workflow's behavior
- `trust_requirements`: The minimum trust level required to execute
- `trust_metadata`: Additional trust-relevant metadata (origin, purpose, classification)

### 3.3 Node Trust Verification

**Current AccessControlledRuntime** (`access_controlled.py:239-285`):

- Checks RBAC permissions (role-based)
- Static permission model
- No delegation chain traversal

**What is missing**:

- EATP capability attestation verification per node
- Constraint envelope enforcement per node execution
- Dynamic trust level checking based on delegation chain
- Trust degradation when node operations exceed delegated scope

### 3.4 Execute Path Trust Integration

**Current execute flow**:

1. Validate workflow structure
2. Resolve dependencies
3. Execute nodes in topological order
4. Collect results
5. Return (results, run_id)

**Missing trust steps**:

1. **Pre-execution**: Verify delegation chain authorizes this workflow
2. **Pre-execution**: Validate constraint envelope is not expired
3. **Per-node**: Check capability attestation covers node's operation
4. **Per-node**: Enforce constraint dimensions (financial, temporal, data access)
5. **Post-execution**: Generate EATP audit anchor
6. **Post-execution**: Submit audit to immutable store

---

## 4. Recommended Integration Architecture

```
+-------------------+     +------------------+     +------------------+
|   BaseRuntime     | --> | TrustVerifier    | --> | Kaizen Trust     |
| (execute method)  |     | (VERIFY op)      |     | (chain.py)       |
+-------------------+     +------------------+     +------------------+
         |                        |
         v                        v
+-------------------+     +------------------+
|  Workflow         | --> | DelegationRecord |
| (trust_metadata)  |     | (from Kaizen)    |
+-------------------+     +------------------+
         |
         v
+-------------------+     +------------------+
|  Node Execution   | --> | ConstraintEnforcer|
| (per-node check)  |     | (from Kaizen)    |
+-------------------+     +------------------+
         |
         v
+-------------------+     +------------------+
|  Audit Generation | --> | AuditAnchorGen   |
| (post-execution)  |     | (to immutable)   |
+-------------------+     +------------------+
```

### Integration Layer Design

The trust integration should be implemented as an opt-in layer that does not break existing users:

1. **TrustAwareRuntime** - New runtime class that extends LocalRuntime with trust verification
2. **TrustContext** - Unified context object carrying delegation, constraints, and identity
3. **TrustVerifier** - Adapter that bridges Core SDK to Kaizen trust module
4. **AuditAnchorGenerator** - Generates EATP-compliant audit anchors from execution events

### Backward Compatibility Strategy

- All trust features must be opt-in (default: disabled)
- Existing `enable_security` and `enable_audit` flags remain functional
- New `trust_context` parameter is `Optional[TrustContext]` with `None` default
- When `trust_context is None`, runtime behaves exactly as before
- When `trust_context` is provided, full EATP verification activates

---

## 5. Shared Mixin Impact Analysis

The Core SDK uses three shared mixins. Trust integration affects each:

### CycleExecutionMixin

- **Impact**: Cycles may require re-verification of constraints at each iteration
- **Gap**: No constraint checking in cycle execution
- **Recommendation**: Add constraint check before each cycle iteration; abort cycle if constraints violated

### ValidationMixin

- **Impact**: Workflow validation should include trust validation
- **Gap**: Current validation checks structure only, not trust
- **Recommendation**: Add `validate_trust()` method alongside `validate_workflow()`

### ConditionalExecutionMixin

- **Impact**: Branch selection may depend on trust level
- **Gap**: No trust-aware branching
- **Recommendation**: Allow conditional branches to specify trust requirements

---

## 6. AsyncLocalRuntime Considerations

AsyncLocalRuntime inherits from LocalRuntime and adds async-specific features:

| Feature                 | Trust Impact                                                          |
| ----------------------- | --------------------------------------------------------------------- |
| Level-Based Parallelism | Trust verification must be thread-safe                                |
| Semaphore Control       | Trust verification adds latency; semaphore limits may need adjustment |
| Thread Pool             | Sync trust operations in thread pool must not deadlock                |
| WorkflowAnalyzer        | Should consider trust verification in execution strategy selection    |

### Performance Concerns

- Trust verification in the hot path will add latency
- Caching verification results is essential for performance
- Parallel node execution means concurrent trust checks
- Recommendation: Verify delegation once at workflow start; verify constraints per-node with caching

---

## 7. Effort Estimates

| Integration Task                                | Complexity | Effort        | Dependencies                          |
| ----------------------------------------------- | ---------- | ------------- | ------------------------------------- |
| Add `trust_context` to BaseRuntime              | Simple     | S (1-2 days)  | TrustContext type definition          |
| Create TrustVerifier integration layer          | Moderate   | M (3-5 days)  | Kaizen trust module                   |
| Create TrustContext unified type                | Simple     | S (1-2 days)  | None                                  |
| Propagate delegation through workflow execution | Complex    | L (1-2 weeks) | TrustVerifier, Workflow changes       |
| EATP-compliant audit trail generation           | Complex    | L (1-2 weeks) | AuditAnchorGenerator, immutable store |
| Retrofit AccessControlledRuntime for EATP       | Moderate   | M (3-5 days)  | TrustVerifier                         |
| Trust-aware ValidationMixin extension           | Simple     | S (1-2 days)  | TrustContext                          |
| AsyncLocalRuntime trust thread safety           | Moderate   | M (3-5 days)  | All above                             |

**Total Estimated Effort**: 4-6 weeks for full integration

---

## 8. Risk Assessment

| Risk                                             | Likelihood | Impact   | Mitigation                                         |
| ------------------------------------------------ | ---------- | -------- | -------------------------------------------------- |
| Performance degradation from trust checks        | HIGH       | HIGH     | Caching, verify-once-per-workflow pattern          |
| Breaking existing users                          | MEDIUM     | CRITICAL | Opt-in design, backward compatibility tests        |
| Circular dependency (Core SDK depends on Kaizen) | HIGH       | HIGH     | Interface-based integration, no direct import      |
| Thread safety issues in async runtime            | MEDIUM     | HIGH     | Thread-safe trust store, immutable context objects |
| Trust verification latency in hot path           | HIGH       | MEDIUM   | <100ms target with caching                         |

### Circular Dependency Mitigation

The Core SDK MUST NOT directly import Kaizen trust modules. Instead:

1. Define trust interfaces (protocols) in Core SDK
2. Kaizen implements these interfaces
3. Users inject Kaizen trust implementations at runtime
4. This maintains the dependency direction: Kaizen depends on Core SDK, not vice versa
