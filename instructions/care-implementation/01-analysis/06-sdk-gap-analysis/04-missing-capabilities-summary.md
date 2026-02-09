# Missing Capabilities Summary

## Executive Summary

This document consolidates all missing trust capabilities across the Kailash SDK ecosystem (Kaizen, Core SDK, DataFlow, Nexus) into a prioritized inventory. Capabilities are grouped by priority level (P0 Critical, P1 High, P2 Medium) and organized by implementation phase.

---

## 1. Priority 0 (CRITICAL) - Must Have for Production Trust

These capabilities are non-negotiable for any production deployment claiming EATP compliance. Without them, the trust model has fundamental gaps.

| #    | Capability                  | Location                      | Description                                                                                                                                 | Effort | Impact                                                                     |
| ---- | --------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------ | -------------------------------------------------------------------------- |
| P0-1 | Immutable Audit Storage     | Kaizen `audit_store.py`       | EATP requires cryptographically anchored, immutable audit trail with witnesses. Current implementation is plain JSON to file.               | L      | Core EATP compliance - without this, audit is not trustworthy              |
| P0-2 | VERIFY Operation Completion | Kaizen `operations.py:97-154` | Chain walking is incomplete (does not always traverse to genesis); clock skew unhandled; <100ms target not met; revocation checking missing | M      | Runtime trust verification - without this, trust chain cannot be validated |
| P0-3 | Core SDK Trust Integration  | `src/kailash/runtime/base.py` | No trust context propagation through workflow execution. All downstream frameworks rely on Core SDK.                                        | L      | Foundation for all trust integration - blocking for DataFlow and Nexus     |
| P0-4 | Data Access Constraints     | DataFlow (new module)         | EATP requires data classification-based constraints. No data classification awareness exists.                                               | L      | Enterprise data security - required for regulated industries               |
| P0-5 | MCP Trust Integration       | Nexus `core.py`               | MCP calls require EATP verification per A2A integration pattern. Currently uses API key only.                                               | L      | AI agent trust - required for trusted agent-to-agent communication         |
| P0-6 | Cascade Revocation          | Kaizen `rotation.py`          | Key rotation exists but hierarchical revocation propagation is missing. Child delegations are not invalidated when parent is revoked.       | M      | Trust chain integrity - without this, revoked delegations remain active    |

### P0 Total Effort: 4 Large + 2 Medium = approximately 10-14 weeks

---

## 2. Priority 1 (HIGH) - Required for Enterprise Deployment

These capabilities are required for production enterprise deployments but the system can function (with known limitations) without them.

| #     | Capability                                | Location                          | Description                                                                      | Effort |
| ----- | ----------------------------------------- | --------------------------------- | -------------------------------------------------------------------------------- | ------ |
| P1-1  | Human Fallback Mechanism                  | Kaizen (new module)               | Graceful degradation with human override when automated trust verification fails | M      |
| P1-2  | Temporal Constraint Enforcement           | Kaizen `constraint_validator.py`  | Strong expiry enforcement including timezone handling, recurring schedules       | S      |
| P1-3  | Workflow Delegation Metadata              | Core SDK `workflow.py`            | Workflows carry delegation records and constraint envelopes                      | M      |
| P1-4  | Trust-Aware Sessions                      | Nexus `core.py`                   | Sessions maintain trust lineage across channels and requests                     | M      |
| P1-5  | Cryptographically Signed Audit (DataFlow) | DataFlow `audit_trail_manager.py` | AuditTrailManager records signed with Ed25519 and hash-chained                   | M      |
| P1-6  | Trust Store Persistence                   | Kaizen `store.py`                 | Persistent backend for trust store (currently in-memory only)                    | M      |
| P1-7  | Trust-Aware Query Execution               | DataFlow (enhancement)            | Queries carry constraint envelope; results filtered by delegation scope          | L      |
| P1-8  | EATP Header Extraction                    | Nexus `core.py`                   | Extract EATP credentials from HTTP headers for API channel                       | S      |
| P1-9  | Trust Protocol Interfaces                 | Core SDK (new module)             | Define trust interfaces as Python protocols for framework integration            | S      |
| P1-10 | Verification Result Caching               | Kaizen `cache.py` (enhancement)   | Cache verification results for <100ms performance target                         | S      |

### P1 Total Effort: 1 Large + 5 Medium + 4 Small = approximately 8-12 weeks

---

## 3. Priority 2 (MEDIUM) - Enhanced Trust Features

These capabilities provide comprehensive trust coverage but are not blocking for initial production deployment.

| #     | Capability                        | Location                           | Description                                                             | Effort |
| ----- | --------------------------------- | ---------------------------------- | ----------------------------------------------------------------------- | ------ |
| P2-1  | Shared Planning Posture           | Kaizen `postures.py`               | Collaborative human-AI decision-making mechanism                        | L      |
| P2-2  | Continuous Insight Posture        | Kaizen `postures.py`               | Real-time monitoring with streaming insight updates                     | L      |
| P2-3  | Communication Constraints         | Kaizen `constraint_validator.py`   | Channel restriction enforcement, recipient limits, content filtering    | M      |
| P2-4  | Cross-Tenant Trust Bridging       | DataFlow (new module)              | EATP delegation for cross-tenant data access                            | L      |
| P2-5  | Witness Verification              | Kaizen `audit_store.py`            | Third-party audit witness mechanism                                     | M      |
| P2-6  | Data Classification on Models     | DataFlow (enhancement)             | Field-level classification (public, internal, confidential, restricted) | M      |
| P2-7  | Trust-Based Rate Limiting         | Nexus `core.py`                    | Rate limits adjust based on trust level of requester                    | S      |
| P2-8  | A2A Trust Protocol                | Nexus (new module)                 | Full agent-to-agent communication with EATP credentials                 | L      |
| P2-9  | Posture Transition Protocol       | Kaizen `postures.py`               | Runtime posture transitions with negotiation and degradation            | M      |
| P2-10 | Trust-Aware Conditional Execution | Core SDK ConditionalExecutionMixin | Branch selection based on trust level                                   | S      |
| P2-11 | Delegation Templates              | Kaizen `operations.py`             | Reusable delegation patterns for common scenarios                       | S      |
| P2-12 | Row-Level Security (Trust-Based)  | DataFlow (enhancement)             | Trust-posture-based row filtering on queries                            | L      |
| P2-13 | Held Verification Level           | Kaizen (new)                       | Hold mechanism for actions requiring human approval before proceeding   | M      |
| P2-14 | Trust-Aware Error Types           | Core SDK (enhancement)             | Specific exception types for trust violations                           | S      |
| P2-15 | CLI Channel Trust Context         | Nexus (enhancement)                | Trust context loading from environment/config for CLI channel           | S      |

### P2 Total Effort: 5 Large + 5 Medium + 5 Small = approximately 14-20 weeks

---

## 4. Cross-Cutting Concerns

These are systemic issues that affect multiple capabilities and must be addressed holistically.

### 4.1 Consistency Gap

- **Problem**: Kaizen has trust, but Core SDK/DataFlow/Nexus do not propagate it
- **Impact**: Trust context is lost at every framework boundary
- **Resolution**: P0-3 (Core SDK integration) + P1-3 (workflow delegation) + P1-9 (trust protocols)

### 4.2 Audit Gap

- **Problem**: Each framework has different audit approaches, none EATP-compliant
- **Impact**: No unified, verifiable audit trail across the stack
- **Resolution**: P0-1 (immutable audit) + P1-5 (DataFlow audit signing)

### 4.3 Integration Gap

- **Problem**: No unified trust context flows through the SDK stack
- **Impact**: Kaizen agent -> Nexus -> Core SDK -> DataFlow loses trust at each transition
- **Resolution**: Unified TrustContext type + trust protocol interfaces

### 4.4 Performance Gap

- **Problem**: No optimization for machine-speed (<100ms) verification
- **Impact**: Trust checks in hot path could unacceptably slow operations
- **Resolution**: P1-10 (verification caching) + parallel verification + verify-once patterns

---

## 5. Implementation Phases

### Phase 1: Foundation (Weeks 1-6)

**Focus**: Complete Kaizen trust module + Core SDK integration layer

| Capability                                 | Priority | Effort | Dependencies |
| ------------------------------------------ | -------- | ------ | ------------ |
| P0-2: VERIFY operation completion          | P0       | M      | None         |
| P0-6: Cascade revocation                   | P0       | M      | None         |
| P1-6: Trust store persistence              | P1       | M      | None         |
| P1-9: Trust protocol interfaces (Core SDK) | P1       | S      | None         |
| P1-2: Temporal constraint enforcement      | P1       | S      | None         |
| P1-10: Verification result caching         | P1       | S      | P0-2         |

**Phase 1 Deliverables**:

- Complete VERIFY operation with full chain walking and clock skew handling
- Cascade revocation propagation through delegation hierarchy
- Persistent trust store backend
- Trust protocol interfaces defined in Core SDK
- Strong temporal constraint enforcement
- Verification caching for <100ms target

### Phase 2: Integration (Weeks 5-12)

**Focus**: Propagate trust through Core SDK, Nexus, and DataFlow

| Capability                           | Priority | Effort | Dependencies |
| ------------------------------------ | -------- | ------ | ------------ |
| P0-3: Core SDK trust integration     | P0       | L      | P1-9         |
| P1-3: Workflow delegation metadata   | P1       | M      | P0-3         |
| P1-8: EATP header extraction (Nexus) | P1       | S      | None         |
| P1-4: Trust-aware sessions (Nexus)   | P1       | M      | P1-8         |
| P1-1: Human fallback mechanism       | P1       | M      | P0-3         |

**Phase 2 Deliverables**:

- Trust context flows through Core SDK runtime
- Workflows carry delegation records and constraints
- Nexus extracts EATP credentials from requests
- Sessions maintain trust lineage
- Human fallback for failed verifications

### Phase 3: Compliance (Weeks 10-16)

**Focus**: EATP-compliant audit and data access

| Capability                                      | Priority | Effort | Dependencies |
| ----------------------------------------------- | -------- | ------ | ------------ |
| P0-1: Immutable audit storage                   | P0       | L      | Phase 1      |
| P0-4: Data access constraints                   | P0       | L      | P0-3         |
| P1-5: Cryptographically signed audit (DataFlow) | P1       | M      | P0-1         |
| P1-7: Trust-aware query execution               | P1       | L      | P0-4         |

**Phase 3 Deliverables**:

- Cryptographically anchored, immutable audit storage
- Data classification-based access constraints
- DataFlow audit records signed and hash-chained
- Queries filtered by delegation scope

### Phase 4: Enterprise Features (Weeks 14-24)

**Focus**: MCP trust, advanced postures, cross-tenant

| Capability                        | Priority | Effort | Dependencies |
| --------------------------------- | -------- | ------ | ------------ |
| P0-5: MCP trust integration       | P0       | L      | Phase 2      |
| P2-1: Shared planning posture     | P2       | L      | Phase 1      |
| P2-2: Continuous insight posture  | P2       | L      | Phase 1      |
| P2-4: Cross-tenant trust bridging | P2       | L      | Phase 3      |
| P2-8: A2A trust protocol          | P2       | L      | P0-5         |
| P2-3: Communication constraints   | P2       | M      | Phase 1      |
| P2-5: Witness verification        | P2       | M      | P0-1         |

**Phase 4 Deliverables**:

- Full MCP + EATP integration
- All five trust postures implemented
- Cross-tenant trust bridging
- Agent-to-agent trust protocol
- Communication constraint dimension
- Third-party witness verification

---

## 6. Total Effort Summary

| Priority      | Capabilities        | Estimated Effort |
| ------------- | ------------------- | ---------------- |
| P0 (Critical) | 6 capabilities      | 10-14 weeks      |
| P1 (High)     | 10 capabilities     | 8-12 weeks       |
| P2 (Medium)   | 15 capabilities     | 14-20 weeks      |
| **Total**     | **31 capabilities** | **32-46 weeks**  |

**Note**: Phases overlap. With parallel work streams, total calendar time is estimated at 20-24 weeks (5-6 months) with a team of 2-3 engineers.

---

## 7. Risk Register

| Risk                                            | Likelihood | Impact   | Mitigation                                                |
| ----------------------------------------------- | ---------- | -------- | --------------------------------------------------------- |
| Inconsistent trust across frameworks            | HIGH       | CRITICAL | Unified TrustContext type, Core SDK integration first     |
| Performance degradation from trust checks       | MEDIUM     | HIGH     | Caching, parallel verification, <100ms target testing     |
| Backward compatibility breaks                   | MEDIUM     | HIGH     | Opt-in trust features, gradual migration path             |
| Audit storage scalability                       | MEDIUM     | MEDIUM   | External immutable store (S3, append-only DB)             |
| Key management complexity                       | HIGH       | CRITICAL | Hardware security module integration, rotation automation |
| Scope creep in enterprise features              | HIGH       | MEDIUM   | Strict phase gating, MVP-first for each capability        |
| Circular dependency between Core SDK and Kaizen | HIGH       | HIGH     | Interface-based integration, dependency injection         |

---

## 8. Success Criteria

| Criterion              | Measurement                                              | Target                     |
| ---------------------- | -------------------------------------------------------- | -------------------------- |
| EATP Compliance        | All 5 elements and 4 operations fully implemented        | 100%                       |
| Integration Complete   | Trust flows through Core SDK -> DataFlow/Nexus           | End-to-end test passing    |
| Performance Target     | VERIFY operation latency                                 | <100ms for 95th percentile |
| Audit Complete         | Cryptographically signed, immutable audit with witnesses | Tamper detection verified  |
| Test Coverage          | Trust-critical code paths                                | >90% coverage              |
| Backward Compatibility | Existing tests pass without trust features enabled       | 100% pass rate             |
