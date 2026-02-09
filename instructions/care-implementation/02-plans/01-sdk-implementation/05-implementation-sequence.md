# CARE/EATP Implementation Sequence

## Overview

This document provides the overall sequencing for implementing all 38 items identified in the SDK gap analysis. It includes dependency graphs, phase boundaries, milestones, and risk mitigation strategies.

**Total Items**: 38
**Phases**: 5
**Estimated Duration**: 8-12 weeks

---

## Phase Overview

```
Phase 1: P0 Critical Security Fixes (Week 1-2)
         |
         v
Phase 2: Core SDK Trust Integration (Week 3-4)
         |
         v
Phase 3: Framework Integration (Week 5-6)
         |
         +---> DataFlow Integration
         |
         +---> Nexus Integration
         |
         v
Phase 4: Posture & Constraint Systems (Week 7-8)
         |
         v
Phase 5: Enterprise Features & Hardening (Week 9-12)
```

---

## Dependency Graph

### Level 0 (No Dependencies - Start Immediately)

| ID  | Item                                    | Component      | Priority |
| --- | --------------------------------------- | -------------- | -------- |
| 1   | Fix static salt in crypto.py            | Kaizen Trust   | P0       |
| 3   | Add cycle detection to delegation chain | Kaizen Trust   | P0       |
| 4   | Add maximum delegation depth            | Kaizen Trust   | P0       |
| 26  | Implement 5-posture enum                | Posture System | P2       |

### Level 1 (Depends on Level 0)

| ID  | Item                                     | Depends On | Component         |
| --- | ---------------------------------------- | ---------- | ----------------- |
| 2   | Enable delegation signature verification | 1          | Kaizen Trust      |
| 5   | HSM/KMS integration                      | 1          | Kaizen Trust      |
| 27  | Posture state machine                    | 26         | Posture System    |
| 31  | ConstraintDimension protocol             | -          | Constraint System |

### Level 2 (Depends on Level 1)

| ID  | Item                              | Depends On | Component         |
| --- | --------------------------------- | ---------- | ----------------- |
| 6   | Linked state hashing              | 1, 2       | Kaizen Trust      |
| 8   | Transactional chain re-signing    | 5          | Kaizen Trust      |
| 9   | Constraint inheritance validation | 2          | Kaizen Trust      |
| 15  | Add trust_context to BaseRuntime  | 1          | Core SDK          |
| 28  | PostureCircuitBreaker             | 27         | Posture System    |
| 32  | ConstraintDimensionRegistry       | 31         | Constraint System |

### Level 3 (Depends on Level 2)

| ID  | Item                                  | Depends On | Component         |
| --- | ------------------------------------- | ---------- | ----------------- |
| 7   | Revocation event broadcasting         | 6          | Kaizen Trust      |
| 10  | Append-only audit constraints         | 6          | Kaizen Trust      |
| 16  | Create TrustVerifier integration      | 15         | Core SDK          |
| 17  | Propagate delegation through workflow | 15, 16     | Core SDK          |
| 29  | PostureAwareAgent wrapper             | 27, 28     | Posture System    |
| 33  | MultiDimensionEvaluator               | 31, 32     | Constraint System |

### Level 4 (Depends on Level 3)

| ID  | Item                            | Depends On | Component         |
| --- | ------------------------------- | ---------- | ----------------- |
| 11  | Multi-signature genesis         | 5, 8       | Kaizen Trust      |
| 12  | Merkle tree audit verification  | 10         | Kaizen Trust      |
| 13  | Certificate Revocation List     | 7          | Kaizen Trust      |
| 18  | EATP-compliant audit generation | 16, 17     | Core SDK          |
| 19  | Trust-aware query execution     | 16         | DataFlow          |
| 22  | EATP header extraction          | 16         | Nexus             |
| 30  | Posture metrics collection      | 27, 28, 29 | Posture System    |
| 34  | Data access dimension           | 33         | Constraint System |
| 35  | Communication dimension         | 33         | Constraint System |

### Level 5 (Depends on Level 4)

| ID  | Item                           | Depends On | Component    |
| --- | ------------------------------ | ---------- | ------------ |
| 14  | External timestamp anchoring   | 12         | Kaizen Trust |
| 20  | Cryptographically signed audit | 18, 19     | DataFlow     |
| 21  | Trust-aware multi-tenancy      | 19         | DataFlow     |
| 23  | Trust verification middleware  | 22         | Nexus        |
| 24  | MCP + EATP integration         | 22, 23     | Nexus        |
| 25  | Session trust propagation      | 22, 23     | Nexus        |

### Level 6 (Final Integration)

| ID  | Item                            | Depends On   | Component        |
| --- | ------------------------------- | ------------ | ---------------- |
| 36  | Knowledge entry structures      | All DataFlow | Knowledge Ledger |
| 37  | Provenance schema               | 36           | Knowledge Ledger |
| 38  | Trust-chain-to-knowledge bridge | 36, 37       | Knowledge Ledger |

---

## Phase 1: P0 Critical Security Fixes

**Duration**: Week 1-2
**Focus**: Address critical security vulnerabilities

### Week 1: Cryptographic Fixes

| Day | Task                                   | Item ID | Owner    | Risk   |
| --- | -------------------------------------- | ------- | -------- | ------ |
| 1   | Implement salt generation in crypto.py | 1       | Security | Low    |
| 2   | Add per-key salt to hash functions     | 1       | Security | Low    |
| 3   | Implement cycle detection in chain.py  | 3       | Trust    | Medium |
| 4   | Add max delegation depth enforcement   | 4       | Trust    | Low    |
| 5   | Unit tests for all P0 fixes            | 1,3,4   | QA       | Low    |

### Week 2: Signature Verification

| Day | Task                                         | Item ID | Owner    | Risk   |
| --- | -------------------------------------------- | ------- | -------- | ------ |
| 1-2 | Enable delegation signature verification     | 2       | Security | High   |
| 3   | Integration tests for signature verification | 2       | QA       | Medium |
| 4   | Update existing tests for new behavior       | 1-4     | QA       | Medium |
| 5   | Security review and sign-off                 | 1-4     | Security | Low    |

### Milestone 1: P0 Complete

**Criteria**:

- [ ] All crypto operations use per-key salt
- [ ] Delegation signatures verified
- [ ] Cycle detection prevents infinite loops
- [ ] Depth limits enforced
- [ ] All security tests pass
- [ ] Security review approved

**Risk Mitigation**:

- Feature flags for gradual rollout
- Backward compatibility mode for legacy chains
- Rollback plan if issues discovered

---

## Phase 2: Core SDK Trust Integration

**Duration**: Week 3-4
**Focus**: Add trust context to Core SDK runtime

### Week 3: Trust Context Types

| Day | Task                                       | Item ID | Owner    | Risk   |
| --- | ------------------------------------------ | ------- | -------- | ------ |
| 1   | Create RuntimeTrustContext type            | 15      | Core SDK | Low    |
| 2   | Implement context propagation (ContextVar) | 15      | Core SDK | Low    |
| 3   | Create TrustVerifier interface             | 16      | Core SDK | Low    |
| 4   | Implement KaizenTrustVerifier              | 16      | Core SDK | Medium |
| 5   | Add trust parameters to BaseRuntime        | 15      | Core SDK | Low    |

### Week 4: Runtime Integration

| Day | Task                                              | Item ID | Owner    | Risk   |
| --- | ------------------------------------------------- | ------- | -------- | ------ |
| 1   | Update LocalRuntime.execute()                     | 17      | Core SDK | Medium |
| 2   | Update AsyncLocalRuntime.execute_workflow_async() | 17      | Core SDK | Medium |
| 3   | Implement RuntimeAuditGenerator                   | 18      | Core SDK | Low    |
| 4   | Integration tests for trust propagation           | 15-18   | QA       | Medium |
| 5   | Performance testing (ensure <5ms overhead)        | 15-18   | Perf     | Medium |

### Milestone 2: Core Trust Complete

**Criteria**:

- [ ] RuntimeTrustContext propagates through execution
- [ ] TrustVerifier integrates with Kaizen
- [ ] Audit events generated for all executions
- [ ] No performance regression (>5ms overhead)
- [ ] Backward compatibility maintained

**Risk Mitigation**:

- All new features disabled by default
- Performance benchmarks before/after
- Extensive backward compatibility tests

---

## Phase 3: Framework Integration

**Duration**: Week 5-6
**Focus**: Integrate trust into DataFlow and Nexus

### Week 5: DataFlow Integration

| Day | Task                                | Item ID | Owner    | Risk   |
| --- | ----------------------------------- | ------- | -------- | ------ |
| 1   | Implement ConstraintEnvelopeWrapper | 19      | DataFlow | Medium |
| 2   | Create TrustAwareQueryExecutor      | 19      | DataFlow | Medium |
| 3   | Implement SignedAuditRecord         | 20      | DataFlow | Low    |
| 4   | Create DataFlowAuditStore           | 20      | DataFlow | Low    |
| 5   | Implement TenantTrustManager        | 21      | DataFlow | High   |

### Week 6: Nexus Integration

| Day | Task                                  | Item ID | Owner | Risk   |
| --- | ------------------------------------- | ------- | ----- | ------ |
| 1   | Implement EATPHeaderExtractor         | 22      | Nexus | Low    |
| 2   | Create TrustMiddleware                | 23      | Nexus | Medium |
| 3   | Implement MCPEATPHandler              | 24      | Nexus | High   |
| 4   | Create SessionTrustContext propagator | 25      | Nexus | Medium |
| 5   | End-to-end integration tests          | 19-25   | QA    | High   |

### Milestone 3: Framework Integration Complete

**Criteria**:

- [ ] DataFlow queries respect constraints
- [ ] Audit records cryptographically signed
- [ ] Cross-tenant requires delegation
- [ ] Nexus extracts EATP headers
- [ ] MCP calls include trust context
- [ ] Sessions maintain trust state

**Risk Mitigation**:

- Permissive mode before enforcing
- Extensive logging for debugging
- Canary deployment for production

---

## Phase 4: Posture & Constraint Systems

**Duration**: Week 7-8
**Focus**: Implement 5-posture machine and constraint extensibility

### Week 7: Posture System

| Day | Task                             | Item ID | Owner  | Risk   |
| --- | -------------------------------- | ------- | ------ | ------ |
| 1   | Add ASSISTED posture to enum     | 26      | Trust  | Low    |
| 2   | Implement PostureStateMachine    | 27      | Trust  | Medium |
| 3   | Create transition guards         | 27      | Trust  | Low    |
| 4   | Implement PostureCircuitBreaker  | 28      | Trust  | Medium |
| 5   | Create PostureAwareAgent wrapper | 29      | Agents | Medium |

### Week 8: Constraint System

| Day | Task                                  | Item ID | Owner         | Risk   |
| --- | ------------------------------------- | ------- | ------------- | ------ |
| 1   | Define ConstraintDimension protocol   | 31      | Trust         | Low    |
| 2   | Implement ConstraintDimensionRegistry | 32      | Trust         | Low    |
| 3   | Create MultiDimensionEvaluator        | 33      | Trust         | Medium |
| 4   | Implement builtin dimensions          | 34, 35  | Trust         | Low    |
| 5   | Implement TrustMetricsCollector       | 30      | Observability | Low    |

### Milestone 4: Autonomy Systems Complete

**Criteria**:

- [ ] 5 postures functional
- [ ] State machine enforces transitions
- [ ] Circuit breaker auto-downgrades
- [ ] Constraint dimensions pluggable
- [ ] Anti-gaming detection working
- [ ] Metrics collection operational

**Risk Mitigation**:

- Conservative default posture (SUPERVISED)
- Gradual posture upgrade path
- Clear documentation for dimension authors

---

## Phase 5: Enterprise Features & Hardening

**Duration**: Week 9-12
**Focus**: P1/P2 enterprise features and production hardening

### Week 9: P1 Features

| Day | Task                           | Item ID | Owner    | Risk   |
| --- | ------------------------------ | ------- | -------- | ------ |
| 1-2 | HSM/KMS integration (AWS KMS)  | 5       | Security | High   |
| 3   | Linked state hashing           | 6       | Trust    | Medium |
| 4   | Revocation event broadcasting  | 7       | Trust    | Medium |
| 5   | Transactional chain re-signing | 8       | Trust    | High   |

### Week 10: P1 Features (continued)

| Day | Task                              | Item ID | Owner    | Risk   |
| --- | --------------------------------- | ------- | -------- | ------ |
| 1   | Constraint inheritance validation | 9       | Trust    | Low    |
| 2   | Append-only audit constraints     | 10      | Database | Medium |
| 3-5 | Integration testing for P1        | 5-10    | QA       | Medium |

### Week 11: P2 Features

| Day | Task                           | Item ID | Owner | Risk   |
| --- | ------------------------------ | ------- | ----- | ------ |
| 1-2 | Multi-signature genesis        | 11      | Trust | High   |
| 3   | Merkle tree audit verification | 12      | Trust | Medium |
| 4   | Certificate Revocation List    | 13      | Trust | Medium |
| 5   | External timestamp anchoring   | 14      | Trust | Low    |

### Week 12: Knowledge Ledger & Hardening

| Day | Task                                  | Item ID | Owner     | Risk   |
| --- | ------------------------------------- | ------- | --------- | ------ |
| 1   | KnowledgeEntry structures             | 36      | Knowledge | Low    |
| 2   | Provenance schema (W3C PROV-DM)       | 37      | Knowledge | Low    |
| 3   | Trust-chain-to-knowledge bridge       | 38      | Knowledge | Medium |
| 4-5 | Production hardening and load testing | All     | Ops       | Medium |

### Milestone 5: Production Ready

**Criteria**:

- [ ] HSM/KMS working in production
- [ ] Revocation broadcasts to all subscribers
- [ ] Multi-sig genesis operational
- [ ] Merkle verification passing
- [ ] Load tests pass at 10x expected volume
- [ ] Security penetration test complete
- [ ] Documentation complete

---

## Risk Matrix

| Risk                            | Impact   | Probability | Mitigation                        |
| ------------------------------- | -------- | ----------- | --------------------------------- |
| Breaking signature verification | High     | Medium      | Feature flags, gradual rollout    |
| Performance regression          | High     | Medium      | Benchmarks, caching, lazy loading |
| HSM integration complexity      | Medium   | High        | Start early, have fallback        |
| Cross-tenant leakage            | Critical | Low         | Extensive testing, code review    |
| Constraint gaming               | Medium   | Medium      | Anti-gaming detection, monitoring |
| Multi-sig key management        | High     | Medium      | Clear procedures, HSM backup      |

---

## Testing Strategy

### Test Pyramid

```
         /\
        /  \         E2E Tests (10%)
       /----\        - Full workflow with trust
      /      \       - Cross-framework integration
     /--------\
    /          \     Integration Tests (30%)
   /------------\    - Component integration
  /              \   - Database operations
 /----------------\
/                  \ Unit Tests (60%)
                     - Crypto functions
                     - Constraint evaluation
                     - State machine transitions
```

### Critical Test Scenarios

1. **Signature Tampering**
   - Modify delegation signature
   - Verify rejection

2. **Delegation Chain Cycle**
   - Create circular delegation
   - Verify cycle detection

3. **Constraint Widening**
   - Attempt to loosen parent constraints
   - Verify rejection

4. **Cross-Tenant Access**
   - Access without delegation
   - Verify blocked

5. **Circuit Breaker**
   - Generate failures
   - Verify automatic downgrade

6. **Emergency Downgrade**
   - Trigger emergency
   - Verify immediate BLOCKED

---

## Rollback Plan

### Phase 1 Rollback

If P0 fixes cause issues:

1. Revert crypto.py changes
2. Disable signature verification via feature flag
3. Restore original delegation chain traversal
4. Deploy rollback within 15 minutes

### Phase 2-5 Rollback

All new features are opt-in:

1. Set `trust_verification_mode="disabled"` in runtime
2. New features gracefully degrade to no-op
3. No data migration required for rollback

---

## Success Metrics

### Phase 1 (Security)

- Zero salt reuse across keys
- 100% delegation signatures verified
- No cycle-related hangs in production

### Phase 2 (Core Integration)

- Trust context propagation: <2ms overhead
- Audit generation: 100% coverage
- Zero backward compatibility issues

### Phase 3 (Framework Integration)

- DataFlow constraint enforcement: 100% queries
- Nexus header extraction: 100% requests
- Cross-tenant blocks: 0 unauthorized access

### Phase 4 (Autonomy)

- Posture transitions: <100ms
- Circuit breaker: <5s to open
- Gaming detection: >90% accuracy

### Phase 5 (Enterprise)

- HSM operations: <50ms
- Multi-sig completion: <5 minutes
- Audit verification: <1s for 1M records

---

## Communication Plan

### Stakeholder Updates

| Week | Update                         | Audience      |
| ---- | ------------------------------ | ------------- |
| 2    | P0 Complete                    | Security Team |
| 4    | Core Integration Complete      | Engineering   |
| 6    | Framework Integration Complete | Product       |
| 8    | Autonomy Systems Complete      | All           |
| 12   | Production Ready               | Executive     |

### Documentation Deliverables

| Phase | Document                                             |
| ----- | ---------------------------------------------------- |
| 1     | Security Advisory for P0 fixes                       |
| 2     | Core SDK Trust Integration Guide                     |
| 3     | DataFlow Trust Guide, Nexus Trust Guide              |
| 4     | Posture Management Guide, Constraint Extension Guide |
| 5     | Production Deployment Guide                          |

---

## Version History

| Version | Date       | Changes              |
| ------- | ---------- | -------------------- |
| 1.0     | 2026-02-07 | Initial plan created |

## References

- 01-kaizen-trust-enhancements.md
- 02-core-sdk-trust-integration.md
- 03-dataflow-nexus-integration.md
- 04-constraint-posture-systems.md
- CARE Framework Specification
- EATP Protocol Design
