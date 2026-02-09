# SDK Trust Implementation Roadmap

## Executive Summary

This document defines a 4-phase implementation plan to achieve full EATP trust compliance across the Kailash SDK ecosystem (Kaizen, Core SDK, DataFlow, Nexus). The plan is designed to deliver incremental value at each phase, with no phase depending on later phases to be useful.

**Total Duration**: 20-24 weeks (5-6 months) with 2-3 engineers
**Total Capabilities**: 31 across all priorities
**Architecture Principle**: Opt-in trust features; backward compatibility guaranteed

---

## Phase 1: Foundation (Weeks 1-6)

### Objective

Complete the Kaizen trust module's core operations and establish the integration layer in Core SDK.

### Why This Phase First

Everything else depends on having a complete, performant trust verification engine and a standardized way for frameworks to interact with it. Without this foundation, subsequent phases cannot proceed.

### Deliverables

#### 1.1 Complete VERIFY Operation (P0-2)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/operations.py`
**Effort**: M (3-5 days)

Work items:

- Implement full chain walking from leaf attestation back to genesis record
- Add clock skew tolerance with configurable window (default: 30 seconds)
- Add revocation checking at every link in the chain
- Add expiry checking at every chain link
- Optimize for <100ms verification with result caching
- Add batch verification for multiple concurrent requests

**Acceptance Criteria**:

- VERIFY traverses complete chain to genesis in all cases
- Clock skew tolerance is configurable
- Revoked links cause verification failure
- Expired links cause verification failure
- 95th percentile latency <100ms (cached)

#### 1.2 Cascade Revocation (P0-6)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/rotation.py`
**Effort**: M (3-5 days)

Work items:

- Implement hierarchical revocation propagation
- When a delegation is revoked, automatically invalidate all child delegations
- Add notification mechanism for affected parties
- Add revocation reason and timestamp tracking
- Add revocation status to VERIFY chain walking

**Acceptance Criteria**:

- Revoking parent invalidates all descendants
- Revocation propagates within one operation (not eventual)
- Affected parties can query revocation status

#### 1.3 Trust Store Persistence (P1-6)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/store.py`
**Effort**: M (3-5 days)

Work items:

- Add persistent backend interface (Protocol class)
- Implement SQLite backend for development/testing
- Implement file-system backend for simple deployments
- Add backend-agnostic API that works with both in-memory and persistent stores
- Ensure trust store survives process restart

**Acceptance Criteria**:

- Trust store data persists across restarts
- SQLite backend passes all existing tests
- In-memory backend remains default for backward compatibility

#### 1.4 Trust Protocol Interfaces (P1-9)

**Location**: `src/kailash/trust/` (new module in Core SDK)
**Effort**: S (1-2 days)

Work items:

- Define `TrustVerifier` protocol (verify method)
- Define `TrustContext` dataclass (delegation chain, constraints, posture)
- Define `ConstraintEnforcer` protocol (check_constraints method)
- Define `AuditAnchorGenerator` protocol (generate_anchor method)
- No implementation in Core SDK; just interfaces

**Acceptance Criteria**:

- Protocols defined with complete type hints
- Kaizen trust module can implement these protocols
- No circular dependency introduced

#### 1.5 Temporal Constraint Enforcement (P1-2)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/constraint_validator.py`
**Effort**: S (1-2 days)

Work items:

- Add timezone-aware timestamp comparison
- Add strong expiry enforcement (fail-closed on expired constraints)
- Add recurring schedule support (e.g., "weekdays 9am-5pm only")
- Add grace period configuration for near-expiry warnings

**Acceptance Criteria**:

- Expired constraints always fail validation (fail-closed)
- Timezone handling works across UTC offsets
- Recurring schedules are evaluatable

#### 1.6 Verification Result Caching (P1-10)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/cache.py`
**Effort**: S (1-2 days)

Work items:

- Enhance existing cache with TTL-based expiry
- Add cache invalidation on revocation events
- Add cache statistics for monitoring
- Add configurable cache size limits

**Acceptance Criteria**:

- Cached verification returns in <10ms
- Cache auto-invalidates on revocation
- Cache size is bounded

### Phase 1 Exit Criteria

- All EATP four operations (ESTABLISH, DELEGATE, VERIFY, AUDIT) pass comprehensive tests
- VERIFY operation achieves <100ms (95th percentile) with caching
- Trust store persists across restarts
- Core SDK has trust protocol interfaces ready for Phase 2

---

## Phase 2: Integration (Weeks 5-12)

### Objective

Propagate trust context through Core SDK runtime and into Nexus request handling.

### Why This Phase Second

The foundation is complete; now we connect it to the frameworks that application code actually uses. Core SDK runtime integration is the critical path because both DataFlow and Nexus depend on it.

### Deliverables

#### 2.1 Core SDK Trust Integration (P0-3)

**Location**: `src/kailash/runtime/base.py`, `src/kailash/runtime/local.py`
**Effort**: L (1-2 weeks)

Work items:

- Add `trust_context: Optional[TrustContext]` parameter to BaseRuntime
- Add `trust_verifier: Optional[TrustVerifier]` parameter to BaseRuntime
- Add pre-execution trust verification in `execute()` method
- Add per-node constraint checking in node execution loop
- Add post-execution audit anchor generation
- Ensure all trust features are opt-in (None defaults)
- Add trust-related execution metadata to results
- Handle AsyncLocalRuntime thread safety for trust operations

**Acceptance Criteria**:

- Existing tests pass without any trust_context (backward compatible)
- When trust_context is provided, delegation is verified before execution
- Per-node constraint enforcement works
- Audit anchor is generated after execution
- AsyncLocalRuntime handles concurrent trust checks safely

#### 2.2 Workflow Delegation Metadata (P1-3)

**Location**: `src/kailash/workflow/builder.py`, `src/kailash/workflow/workflow.py`
**Effort**: M (3-5 days)

Work items:

- Add `trust_metadata` field to Workflow dataclass
- Add `set_delegation()` method to WorkflowBuilder
- Add `set_constraints()` method to WorkflowBuilder
- Add `set_trust_requirements()` method to WorkflowBuilder
- Trust metadata flows through `.build()` to the built workflow

**Acceptance Criteria**:

- WorkflowBuilder can attach delegation records
- Built workflow carries trust metadata
- Runtime reads trust metadata during execution
- Existing workflows without trust metadata work unchanged

#### 2.3 EATP Header Extraction for Nexus (P1-8)

**Location**: `apps/kailash-nexus/src/nexus/core.py`
**Effort**: S (1-2 days)

Work items:

- Add EATP credential extraction from HTTP headers
- Define header names: `X-EATP-Delegation`, `X-EATP-Attestation`, `X-EATP-Constraint`
- Parse and deserialize EATP credentials from headers
- Pass extracted credentials to workflow execution as trust context

**Acceptance Criteria**:

- EATP headers are parsed when present
- Missing headers fall back to existing auth (backward compatible)
- Malformed headers return 400 error
- Extracted credentials create valid TrustContext

#### 2.4 Trust-Aware Sessions in Nexus (P1-4)

**Location**: `apps/kailash-nexus/src/nexus/core.py`
**Effort**: M (3-5 days)

Work items:

- Add `trust_context` field to session data
- Propagate trust context from request to session
- Maintain trust lineage across multiple requests in same session
- Add trust context to MCP session metadata
- Add trust context to CLI session (from environment/config)

**Acceptance Criteria**:

- Sessions carry trust context
- Trust context persists across session requests
- Each channel can provide trust context via its native mechanism

#### 2.5 Human Fallback Mechanism (P1-1)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/fallback.py` (new file)
**Effort**: M (3-5 days)

Work items:

- Define human fallback interface
- Implement fallback trigger on verification failure
- Add approval queue mechanism
- Add timeout handling for pending approvals
- Add fallback audit trail (who approved, when, why)
- Integrate with VERIFY operation as fallback path

**Acceptance Criteria**:

- Verification failure can trigger human fallback instead of rejection
- Approval queue accepts/rejects pending operations
- Timeout on approvals defaults to rejection (fail-closed)
- Fallback decisions are audited

### Phase 2 Exit Criteria

- Trust context flows from Nexus request through Core SDK runtime to node execution
- Workflows carry delegation records
- Sessions maintain trust lineage
- Human fallback mechanism works for edge cases
- End-to-end test: Nexus API request with EATP headers -> trusted workflow execution

---

## Phase 3: Compliance (Weeks 10-16)

### Objective

Achieve EATP-compliant audit and data access control.

### Why This Phase Third

The trust context is now flowing through the system. This phase makes the audit trail trustworthy and adds data-level access control, which are requirements for regulated industries.

### Deliverables

#### 3.1 Immutable Audit Storage (P0-1)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/audit_store.py`
**Effort**: L (1-2 weeks)

Work items:

- Define immutable storage interface (Protocol)
- Implement append-only file storage backend
- Implement Merkle tree hash chaining between records
- Add Ed25519 signing for each audit anchor
- Add tamper detection (verify hash chain integrity)
- Add storage rotation and archival
- Add query API for audit history
- Optionally implement S3/cloud storage backend

**Acceptance Criteria**:

- Audit records are append-only (no modification possible)
- Each record is cryptographically signed
- Hash chain links sequential records
- Tamper detection identifies modified records
- Query API retrieves records by time range, entity, operation

#### 3.2 Data Access Constraints (P0-4)

**Location**: `apps/kailash-dataflow/src/dataflow/trust/` (new module)
**Effort**: L (1-2 weeks)

Work items:

- Define data classification levels (public, internal, confidential, restricted)
- Add classification metadata to model fields
- Add trust-to-classification mapping (which trust levels access which classifications)
- Add constraint envelope integration for data queries
- Add row-level filtering based on delegation scope
- Add field-level filtering based on classification

**Acceptance Criteria**:

- Models can define field-level classifications
- Queries are filtered by delegation scope
- Classification levels are enforced at query time
- Constraint envelope limits data access scope

#### 3.3 Cryptographically Signed DataFlow Audit (P1-5)

**Location**: `apps/kailash-dataflow/src/dataflow/core/audit_trail_manager.py`
**Effort**: M (3-5 days)

Work items:

- Integrate with Kaizen's immutable audit storage
- Sign each audit record with Ed25519
- Add hash chaining between DataFlow audit records
- Link DataFlow audit to parent workflow audit anchor
- Add trust context to audit records (who, with what delegation)

**Acceptance Criteria**:

- DataFlow audit records are cryptographically signed
- Audit records link to workflow-level audit anchors
- Trust context (delegation chain) is included in audit

#### 3.4 Trust-Aware Query Execution (P1-7)

**Location**: `apps/kailash-dataflow/src/dataflow/` (multiple files)
**Effort**: L (1-2 weeks)

Work items:

- Add constraint envelope to query context
- Filter queries by delegation scope (tenant, department, data subset)
- Enforce temporal constraints on data access
- Generate audit anchor for each data query
- Add data classification to query results metadata

**Acceptance Criteria**:

- Queries with constraint envelope return only authorized data
- Temporal constraints are enforced (expired access = no data)
- Each query generates an audit anchor
- Results metadata includes classification levels of returned data

### Phase 3 Exit Criteria

- Audit trail is immutable, signed, and hash-chained
- Data access is controlled by classification and delegation scope
- DataFlow audit integrates with EATP audit anchors
- End-to-end test: Agent with scoped delegation -> filtered data query -> signed audit

---

## Phase 4: Enterprise Features (Weeks 14-24)

### Objective

Complete MCP trust integration, implement remaining trust postures, and add advanced features.

### Why This Phase Last

These features enhance the trust model but are not required for basic EATP compliance. They enable sophisticated enterprise use cases like multi-agent coordination, cross-organization trust, and advanced human-AI collaboration patterns.

### Deliverables

#### 4.1 MCP Trust Integration (P0-5)

**Location**: `apps/kailash-nexus/src/nexus/core.py`
**Effort**: L (1-2 weeks)

Work items:

- Add EATP credential extraction from MCP metadata
- Verify trust chain before MCP tool execution
- Generate audit anchor for each MCP tool call
- Support A2A credential passing between agents
- Add trust context to MCP tool responses

**Acceptance Criteria**:

- MCP tools verify EATP credentials before execution
- A2A communication includes trust credentials
- Each MCP tool call generates an audit anchor
- MCP responses include trust metadata

#### 4.2 Shared Planning Posture (P2-1)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/postures.py`
**Effort**: L (1-2 weeks)

Work items:

- Implement collaborative decision-making protocol
- Add proposal/counter-proposal mechanism
- Add joint approval workflow
- Add planning context sharing between human and AI
- Add planning audit trail

#### 4.3 Continuous Insight Posture (P2-2)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/postures.py`
**Effort**: L (1-2 weeks)

Work items:

- Implement real-time monitoring stream
- Add insight notification mechanism
- Add monitoring dashboard integration points
- Add anomaly detection hooks
- Add insight audit trail

#### 4.4 Cross-Tenant Trust Bridging (P2-4)

**Location**: `apps/kailash-dataflow/src/dataflow/trust/` (new module)
**Effort**: L (1-2 weeks)

Work items:

- Add EATP delegation for cross-tenant operations
- Implement trust bridging protocol between tenants
- Add tenant-to-tenant delegation records
- Add cross-tenant audit correlation
- Ensure data isolation is maintained despite trust bridging

#### 4.5 A2A Trust Protocol (P2-8)

**Location**: `apps/kailash-nexus/src/nexus/trust/` (new module)
**Effort**: L (1-2 weeks)

Work items:

- Define A2A handshake protocol with trust credential exchange
- Implement delegation verification for inter-agent operations
- Add scope narrowing for sub-agent delegation
- Add A2A audit trail linking
- Integrate with MCP transport layer

#### 4.6 Communication Constraints (P2-3)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/constraint_validator.py`
**Effort**: M (3-5 days)

Work items:

- Add channel restriction enforcement (e.g., "only API, not CLI")
- Add recipient limits (e.g., "can communicate with agents A and B only")
- Add content filtering rules (e.g., "no PII in responses")
- Integrate with constraint envelope

#### 4.7 Witness Verification (P2-5)

**Location**: `apps/kailash-kaizen/src/kaizen/trust/audit_store.py`
**Effort**: M (3-5 days)

Work items:

- Define witness interface
- Implement local witness (co-signing service)
- Add witness verification to audit queries
- Add multi-witness support (quorum-based verification)
- Add witness registration and management

### Phase 4 Exit Criteria

- All five trust postures are implemented and testable
- MCP tool calls are trust-verified
- A2A communication includes trust credentials
- Cross-tenant operations use EATP delegation
- All five constraint dimensions are enforced
- Witness verification is operational

---

## Dependency Graph

```
Phase 1 (Foundation)
    |
    +-- P0-2: VERIFY completion --------+
    |                                    |
    +-- P0-6: Cascade revocation         |
    |                                    |
    +-- P1-6: Trust store persistence    |
    |                                    |
    +-- P1-9: Trust protocols -----+     |
    |                              |     |
    +-- P1-2: Temporal constraints |     |
    |                              |     |
    +-- P1-10: Verification cache -+     |
                                   |     |
Phase 2 (Integration)              |     |
    |                              |     |
    +-- P0-3: Core SDK trust ------+     |
    |       |                            |
    |       +-- P1-3: Workflow delegation |
    |       |                            |
    |       +-- P1-1: Human fallback     |
    |                                    |
    +-- P1-8: EATP headers ------+       |
    |       |                    |       |
    |       +-- P1-4: Sessions   |       |
    |                            |       |
Phase 3 (Compliance)             |       |
    |                            |       |
    +-- P0-1: Immutable audit ---+-------+
    |       |
    |       +-- P1-5: DataFlow audit
    |       |
    |       +-- P2-5: Witness verification
    |
    +-- P0-4: Data access constraints
    |       |
    |       +-- P1-7: Trust-aware queries
    |       |
    |       +-- P2-4: Cross-tenant trust
    |
Phase 4 (Enterprise)
    |
    +-- P0-5: MCP trust integration
    |       |
    |       +-- P2-8: A2A trust protocol
    |
    +-- P2-1: Shared planning posture
    +-- P2-2: Continuous insight posture
    +-- P2-3: Communication constraints
```

---

## Resource Allocation

### Recommended Team Structure

| Role                     | Scope                                      | Duration      |
| ------------------------ | ------------------------------------------ | ------------- |
| **Trust Engineer 1**     | Kaizen trust module (Phases 1, 4)          | Full duration |
| **Integration Engineer** | Core SDK + Nexus integration (Phases 2, 4) | Weeks 3-24    |
| **Data Engineer**        | DataFlow trust + audit (Phases 3, 4)       | Weeks 8-24    |

### Parallel Work Streams

| Week  | Stream 1 (Trust Engineer)     | Stream 2 (Integration)        | Stream 3 (Data)                      |
| ----- | ----------------------------- | ----------------------------- | ------------------------------------ |
| 1-2   | P0-2: VERIFY, P1-2: Temporal  | -                             | -                                    |
| 3-4   | P0-6: Revocation, P1-6: Store | P1-9: Trust protocols         | -                                    |
| 5-6   | P1-10: Caching                | P0-3: Core SDK trust (start)  | -                                    |
| 7-8   | Phase 1 testing               | P0-3: Core SDK trust (finish) | -                                    |
| 9-10  | P1-1: Human fallback          | P1-3: Workflow delegation     | P0-1: Immutable audit (start)        |
| 11-12 | Phase 2 testing               | P1-8, P1-4: Nexus             | P0-1: Immutable audit (finish)       |
| 13-14 | -                             | End-to-end testing            | P0-4: Data access constraints        |
| 15-16 | -                             | -                             | P1-5, P1-7: DataFlow audit + queries |
| 17-18 | P2-1: Shared planning         | P0-5: MCP trust               | P2-4: Cross-tenant                   |
| 19-20 | P2-2: Continuous insight      | P2-8: A2A protocol            | Phase 3 testing                      |
| 21-22 | P2-3: Communication           | P2-5: Witness                 | Integration testing                  |
| 23-24 | Final testing                 | Documentation                 | Release preparation                  |

---

## Quality Gates

### Phase Gate 1 (Week 6)

- [ ] All EATP operations pass comprehensive test suite
- [ ] VERIFY <100ms (95th percentile, cached)
- [ ] Cascade revocation propagates correctly
- [ ] Trust store persists across restarts
- [ ] Trust protocol interfaces accepted by team review

### Phase Gate 2 (Week 12)

- [ ] Trust context flows from Nexus to Core SDK to nodes
- [ ] Backward compatibility: all existing tests pass
- [ ] EATP headers parsed and validated in Nexus
- [ ] Sessions carry trust context
- [ ] Human fallback triggers on verification failure

### Phase Gate 3 (Week 16)

- [ ] Audit trail is immutable and tamper-detectable
- [ ] Data queries filtered by delegation scope
- [ ] DataFlow audit links to workflow audit anchors
- [ ] End-to-end: trusted request -> filtered data -> signed audit

### Phase Gate 4 (Week 24)

- [ ] MCP tools verify trust before execution
- [ ] All five postures functional
- [ ] A2A protocol operational
- [ ] Cross-tenant trust bridging works
- [ ] Full test suite >90% coverage on trust paths
- [ ] Performance targets met across all frameworks

---

## Migration Guide for Existing Users

### Phase 1-2: No Breaking Changes

- All trust features are opt-in
- Default behavior is unchanged
- Existing code continues to work without modification

### Phase 3-4: Optional Upgrade Path

```python
# Before (works unchanged)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# After (opt-in trust)
from kailash.trust import TrustContext
from kaizen.trust import KaizenTrustVerifier

trust_ctx = TrustContext(
    delegation_chain=[...],
    constraint_envelope=envelope,
    current_posture="delegated"
)

runtime = LocalRuntime(
    trust_context=trust_ctx,
    trust_verifier=KaizenTrustVerifier()
)
results, run_id = runtime.execute(workflow.build())
# Audit anchor automatically generated
```

### DataFlow Migration

```python
# Before (works unchanged)
db = DataFlow("sqlite:///app.db")

# After (opt-in trust)
from dataflow.trust import TrustAwareDataFlow

db = TrustAwareDataFlow(
    "sqlite:///app.db",
    trust_verifier=KaizenTrustVerifier(),
    audit_store=ImmutableAuditStore("audit.db")
)
```

### Nexus Migration

```python
# Before (works unchanged)
app = Nexus()
app.register("workflow", my_workflow)
app.start()

# After (opt-in trust)
app = Nexus(
    trust_verifier=KaizenTrustVerifier(),
    trust_header_extraction=True  # Enable EATP header parsing
)
app.register("workflow", my_workflow, trust_requirements={
    "required_capabilities": ["read:data", "write:report"],
    "minimum_posture": "supervised"
})
app.start()
```

---

## Monitoring and Observability

### Trust Metrics to Track

| Metric                              | Description                    | Alert Threshold                           |
| ----------------------------------- | ------------------------------ | ----------------------------------------- |
| `trust.verify.latency_p95`          | 95th percentile VERIFY latency | >100ms                                    |
| `trust.verify.failure_rate`         | Verification failure rate      | >5% (may indicate misconfiguration)       |
| `trust.revocation.propagation_time` | Time to propagate revocation   | >1s                                       |
| `trust.audit.write_latency`         | Audit anchor write latency     | >500ms                                    |
| `trust.cache.hit_rate`              | Verification cache hit rate    | <80% (cache may be too small)             |
| `trust.constraint.violation_rate`   | Constraint violation rate      | >10% (may indicate too-tight constraints) |
| `trust.fallback.trigger_rate`       | Human fallback trigger rate    | >1% (trust model may need adjustment)     |

---

## Version Plan

| SDK Version | Trust Features Included                                        | Phase   |
| ----------- | -------------------------------------------------------------- | ------- |
| v0.11.0     | Trust protocol interfaces in Core SDK                          | Phase 1 |
| v0.12.0     | Complete Kaizen trust module (VERIFY, revocation, persistence) | Phase 1 |
| v0.13.0     | Core SDK trust integration + Nexus EATP headers                | Phase 2 |
| v0.14.0     | Immutable audit + DataFlow data access constraints             | Phase 3 |
| v1.0.0      | Full EATP compliance across all frameworks                     | Phase 4 |
