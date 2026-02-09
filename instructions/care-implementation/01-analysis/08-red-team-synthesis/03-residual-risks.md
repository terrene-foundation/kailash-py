# CARE/EATP Trust Framework - Residual Risk Analysis

## Executive Summary

After implementing all proposed solutions from the Solution Proposals document, certain risks remain. This document catalogs residual risks, explains acceptance rationale, defines compensating controls, and establishes monitoring procedures.

**Key Finding**: Even with complete solution implementation, **17 residual risks** remain that cannot be fully eliminated. These are accepted with compensating controls that reduce impact to acceptable levels.

**Update (v2.0)**: Five additional residual risks identified during second-pass red team review have been added (RR-013 through RR-017). These address new attack surfaces introduced by the proposed solutions themselves.

**Risk Acceptance Philosophy**: The CARE/EATP framework cannot achieve zero risk. The goal is to reduce risk to levels where the cost of further mitigation exceeds the expected loss from remaining risk, while maintaining usability and performance.

---

## Section 1: Residual Risk Register

### RR-001: Insider Threat with HSM Access

**Original Threat**: CRIT-004 (In-Memory Key Storage)
**Solution Applied**: SOL-CRIT-004 (HSM/KMS Integration)
**Residual Risk**: Personnel with HSM/KMS administrative access can still abuse signing capabilities

**Why Risk Remains**:

- HSM/KMS prevents key extraction but not key usage
- Administrators with IAM permissions can sign arbitrary payloads
- Root/bootstrap keys must exist somewhere
- M-of-N key escrow requires some group to hold shares

**Residual Impact**: HIGH
**Residual Likelihood**: LOW (requires privileged insider)
**Residual Score**: 5/10

**Acceptance Rationale**:
This is an irreducible trust anchor problem. At some level, humans must be trusted with access. The solution reduces the attack surface from "anyone with code access" to "specific administrators with audited access."

**Compensating Controls**:

1. Principle of least privilege for HSM/KMS access
2. Separation of duties (no single person can create + sign + deploy)
3. All HSM/KMS operations logged to tamper-evident audit
4. Regular access reviews (quarterly)
5. Background checks for privileged personnel
6. Anomaly detection on signing patterns

**Monitoring**:

- Alert: > 10 signing operations per minute
- Alert: Signing outside business hours (unless on-call)
- Dashboard: Signing operations by administrator over time
- Quarterly: Access audit and recertification

---

### RR-002: Side-Channel Attacks on Cryptographic Operations

**Original Threat**: CRIT-001, CRIT-004
**Solutions Applied**: SOL-CRIT-001 (Dynamic Salt), SOL-CRIT-004 (HSM/KMS)
**Residual Risk**: Timing attacks, power analysis, cache-based attacks on cryptographic implementations

**Why Risk Remains**:

- Software-based KMS (not HSM) may have timing vulnerabilities
- Cloud HSM may be subject to hypervisor-level attacks
- Ed25519 implementations vary in side-channel resistance
- Python's GIL introduces timing variation

**Residual Impact**: MEDIUM
**Residual Likelihood**: LOW (requires sophisticated attacker)
**Residual Score**: 3/10

**Acceptance Rationale**:
Full side-channel protection requires hardware security modules with FIPS 140-3 Level 4 certification, which is cost-prohibitive for most deployments. The risk is accepted for non-government-classified deployments.

**Compensating Controls**:

1. Use constant-time implementations where available (PyNaCl)
2. Add random delays to mask timing (with jitter)
3. Rate limit cryptographic operations
4. For high-security deployments: mandate hardware HSM

**Monitoring**:

- Track: Average signing latency per operation type
- Alert: Signing latency deviation > 3 standard deviations
- Annual: Third-party security assessment including side-channel review

---

### RR-003: Zero-Day in Ed25519 or Hash Algorithm

**Original Threat**: Foundational cryptography
**Solutions Applied**: Standard EdDSA implementation
**Residual Risk**: Cryptographic break in Ed25519, SHA-256, or composition

**Why Risk Remains**:

- All cryptographic algorithms have finite lifetime
- Quantum computing may eventually break Ed25519
- Novel mathematical attacks are always possible
- Implementation bugs (not algorithm breaks) possible

**Residual Impact**: CRITICAL
**Residual Likelihood**: VERY LOW (decades of scrutiny)
**Residual Score**: 3/10

**Acceptance Rationale**:
Ed25519 is widely deployed and reviewed. NIST has standardized EdDSA. While quantum threatens long-term, current classical computers cannot break it. The alternative (custom cryptography) is far more dangerous.

**Compensating Controls**:

1. Cryptographic agility: Algorithm IDs stored with signatures
2. Migration path defined: Ed448 (stronger) or PQC ready
3. Short-lived credentials (hours-days, not years)
4. Monitor NIST/IETF announcements for deprecation

**Monitoring**:

- Subscribe to: NIST announcements, IACR ePrint, CVE feeds
- Annual: Cryptographic posture review
- Plan: 6-month migration runway if algorithm deprecated

---

### RR-004: Sophisticated Constraint Gaming (Novel Attacks)

**Original Threat**: HIGH-007, HIGH-008, HIGH-009, HIGH-010
**Solutions Applied**: Anomaly detection, aggregate limits
**Residual Risk**: Adversary develops novel gaming strategy not covered by detection

**Why Risk Remains**:

- Constraint gaming is an adversarial domain (cat and mouse)
- ML models can be evaded by understanding their training
- Novel attack patterns won't trigger historical-based detection
- Constraints are inherently limited in expressiveness

**Residual Impact**: MEDIUM
**Residual Likelihood**: MEDIUM (motivated attackers exist)
**Residual Score**: 5/10

**Acceptance Rationale**:
Perfect constraint enforcement against adversarial agents is theoretically impossible (halting problem adjacent). The solution raises the bar significantly while accepting that sophisticated adversaries may find gaps.

**Compensating Controls**:

1. Defense in depth: Multiple independent constraint layers
2. Human review for high-value operations regardless of constraints
3. Honeypot constraints to detect gaming attempts
4. Regular red team exercises against constraint system
5. Rapid constraint update mechanism (< 1 hour deployment)

**Monitoring**:

- Real-time: Constraint violation rate by agent
- Alert: Agent approaching but not exceeding limits repeatedly
- Dashboard: Gaming pattern indicators (splitting, timing clusters)
- Quarterly: Red team constraint gaming exercise

---

### RR-005: Partial Cascade Revocation Failure

**Original Threat**: HIGH-012, HIGH-013
**Solutions Applied**: SOL-HIGH-012/14 (Atomic Revocation with Fencing)
**Residual Risk**: Network partition during cascade leaves some agents unrevoked

**Why Risk Remains**:

- CAP theorem: Can't have consistency and partition tolerance
- Delegatees may be in different network segments
- Cloud region failures are real events
- Fencing TTL must eventually expire to prevent permanent blocks

**Residual Impact**: MEDIUM
**Residual Likelihood**: LOW (requires specific failure mode)
**Residual Score**: 3/10

**Acceptance Rationale**:
Perfect consistency would require blocking all operations during revocation propagation, which is unacceptable for availability. The solution uses eventual consistency with bounded inconsistency window.

**Compensating Controls**:

1. Revocation receipts: Each agent must acknowledge revocation
2. Revocation retries: Background job retries failed revocations
3. Revocation audit: Log all revocation attempts and outcomes
4. Periodic consistency check: Scan for "zombie" delegations
5. Manual override: Admin can force-fence specific agents

**Monitoring**:

- Real-time: Revocation propagation time histogram
- Alert: Revocation taking > 30 seconds
- Alert: Revocation receipt not received within 5 minutes
- Daily: Scan for active delegations from revoked agents

---

### RR-006: Trust Posture Mapping Ambiguity

**Original Threat**: CRIT-008 (Posture Mismatch)
**Solutions Applied**: SOL-CRIT-008 (Unified 5-Posture Model)
**Residual Risk**: Edge cases where posture semantics are ambiguous

**Why Risk Remains**:

- Postures are abstractions over complex behavior patterns
- Different interpretations possible for boundary cases
- Legacy systems may not support all postures
- Human mental models vary

**Residual Impact**: LOW
**Residual Likelihood**: MEDIUM
**Residual Score**: 3/10

**Acceptance Rationale**:
Perfect semantic alignment is impossible across distributed systems developed by different teams. The solution provides clear documentation and validation, accepting that edge cases will require human judgment.

**Compensating Controls**:

1. Posture compatibility matrix in documentation
2. Validation warnings when postures don't map cleanly
3. Default to more restrictive interpretation when ambiguous
4. Logging of all posture mapping decisions
5. Regular alignment meetings between SDK and Platform teams

**Monitoring**:

- Track: Posture mapping fallback rate (unmapped -> default)
- Alert: > 5% of mappings use fallback
- Quarterly: Review edge cases and update mapping rules

---

### RR-007: Human Origin Forgery at Boundary

**Original Threat**: Trust lineage integrity
**Solutions Applied**: EATP protocol implementation
**Residual Risk**: Initial human authentication (OAuth, SSO) can be compromised

**Why Risk Remains**:

- EATP trusts the identity provider (IdP) at the boundary
- IdP compromise = ability to forge human_origin
- Session hijacking at the human layer is possible
- Social engineering bypasses technical controls

**Residual Impact**: HIGH
**Residual Likelihood**: LOW
**Residual Score**: 5/10

**Acceptance Rationale**:
EATP is designed for human-origin traceability, not human authentication. It trusts the organization's identity infrastructure. Solving IdP security is out of scope.

**Compensating Controls**:

1. Require MFA for all human authentication
2. Short session lifetimes (< 8 hours)
3. Bind human_origin to device fingerprint
4. Detect session anomalies (location, device changes)
5. Audit trail links human_origin to IdP logs

**Monitoring**:

- Real-time: Human session count and locations
- Alert: Same human_origin from multiple geolocations
- Alert: Human session duration > 12 hours
- Integration: SIEM correlation with IdP logs

---

### RR-008: Supply Chain Attack on Dependencies

**Original Threat**: Foundational security
**Solutions Applied**: N/A (not directly addressed)
**Residual Risk**: Compromised dependency (PyNaCl, cryptography, etc.)

**Why Risk Remains**:

- SDK depends on third-party cryptographic libraries
- Transitive dependencies add attack surface
- Package managers (PyPI) have had security issues
- Typosquatting attacks target developer errors

**Residual Impact**: CRITICAL
**Residual Likelihood**: LOW
**Residual Score**: 4/10

**Acceptance Rationale**:
Not using cryptographic libraries would mean implementing crypto from scratch, which is far more dangerous. The risk is accepted with mitigation through dependency management.

**Compensating Controls**:

1. Pin exact dependency versions (no ranges)
2. Verify package hashes on installation
3. Use private PyPI mirror for production
4. Regular dependency audit (Dependabot, Snyk)
5. Minimal dependency policy: only essential packages

**Monitoring**:

- Automated: Daily CVE scan on dependencies
- Alert: Any HIGH/CRITICAL CVE in dependency tree
- Process: 48-hour SLA to patch critical dependency CVE
- Quarterly: Dependency audit and cleanup

---

### RR-009: Performance Degradation Under Attack

**Original Threat**: Availability
**Solutions Applied**: Rate limiting, anomaly detection
**Residual Risk**: DoS through expensive verification requests

**Why Risk Remains**:

- FULL verification level is inherently expensive (~50ms)
- Chain traversal cost grows with delegation depth
- Signature verification cannot be made free
- Attackers can generate valid (but expensive) requests

**Residual Impact**: MEDIUM
**Residual Likelihood**: MEDIUM
**Residual Score**: 4/10

**Acceptance Rationale**:
Cryptographic verification has inherent cost. The solution is to limit when expensive verification is required and implement load shedding.

**Compensating Controls**:

1. Rate limiting per agent and per human_origin
2. QUICK verification for repeated identical requests (cached)
3. Circuit breaker: degrade to QUICK under load
4. Request prioritization: critical operations first
5. Auto-scaling for verification services

**Monitoring**:

- Real-time: Verification latency P50, P95, P99
- Alert: P95 > 100ms
- Alert: FULL verification rate > 1000/sec
- Dashboard: Verification load by agent

---

### RR-010: Regulatory Non-Compliance Edge Cases

**Original Threat**: Compliance requirements
**Solutions Applied**: Immutable audit, trust lineage
**Residual Risk**: Specific regulatory requirements not covered

**Why Risk Remains**:

- Regulations vary by jurisdiction (EU, US, China, etc.)
- Regulations evolve (EU AI Act still being finalized)
- Industry-specific requirements (healthcare, finance)
- Audit format requirements vary

**Residual Impact**: MEDIUM
**Residual Likelihood**: MEDIUM
**Residual Score**: 4/10

**Acceptance Rationale**:
Framework cannot anticipate all regulatory requirements. Core capabilities (immutable audit, traceability) provide foundation; specific compliance features added per deployment.

**Compensating Controls**:

1. Compliance configuration profiles (GDPR, HIPAA, SOX, etc.)
2. Audit export in multiple formats (JSON, W3C PROV, etc.)
3. Legal review of deployment configuration
4. Regular compliance gap assessments
5. Engagement with regulatory bodies for clarification

**Monitoring**:

- Track: Audit log completeness metrics
- Alert: Gaps in audit trail (missing records)
- Annual: Third-party compliance audit
- Ongoing: Monitor regulatory announcements

---

### RR-011: Data Sovereignty Violations in Federation

**Original Threat**: Cross-org federation
**Solutions Applied**: Federation trust model
**Residual Risk**: Data inadvertently crosses sovereignty boundaries

**Why Risk Remains**:

- Federation enables cross-org data sharing by design
- Delegations may cross geographic boundaries
- Constraint enforcement is per-agent, not per-data
- Cloud region selection may violate data locality

**Residual Impact**: HIGH
**Residual Likelihood**: LOW (with proper configuration)
**Residual Score**: 4/10

**Acceptance Rationale**:
Federation's value comes from enabling cross-org collaboration. Restricting it completely would eliminate the feature. Risk is managed through configuration and policy.

**Compensating Controls**:

1. Data classification labels (e.g., "EU_RESIDENT_PII")
2. Constraint: "no_cross_border_transfer" for sensitive data
3. Federation agreements include data locality clauses
4. Audit logs include geographic metadata
5. Geographic enforcement at network layer

**Monitoring**:

- Track: Cross-border delegation count
- Alert: Delegation to federated org in different region
- Dashboard: Data classification distribution by region
- Quarterly: Data sovereignty compliance review

---

### RR-012: Novel Attack Patterns Not Yet Discovered

**Original Threat**: Unknown unknowns
**Solutions Applied**: Defense in depth, red team exercises
**Residual Risk**: Attack patterns not yet conceived

**Why Risk Remains**:

- Security is asymmetric (defender must block all, attacker needs one)
- Trust frameworks are novel (limited attack research)
- Complex systems have emergent vulnerabilities
- Attacker techniques evolve

**Residual Impact**: UNKNOWN
**Residual Likelihood**: MEDIUM (novel systems attract researchers)
**Residual Score**: 5/10 (estimated)

**Acceptance Rationale**:
Unknown risks cannot be eliminated by definition. The approach is continuous improvement through research engagement and rapid response capability.

**Compensating Controls**:

1. Bug bounty program for security researchers
2. Regular third-party penetration testing
3. Academic partnership for protocol review
4. Incident response plan with 4-hour SLA
5. Rapid patching mechanism (hot-fix capability)
6. Defense in depth: assume any component can fail

**Monitoring**:

- Engage: Security research community
- Track: Bug bounty submissions over time
- Annual: Formal protocol security review
- Continuous: Threat intelligence monitoring

---

### RR-013: Prompt Injection in Semantic Constraint Evaluation

**Original Threat**: Constraint gaming (novel attacks)
**Solution Applied**: Semantic constraint layers (LLM-based evaluation)
**Residual Risk**: Adversarial agents craft action descriptions that fool LLM evaluator

**Why Risk Remains**:

- LLMs are fundamentally vulnerable to prompt injection
- Adversarial agents control the input to the evaluator
- No complete defense against prompt injection is known
- LLM evaluation is non-deterministic by nature

**Residual Impact**: MEDIUM
**Residual Likelihood**: MEDIUM
**Residual Score**: 5/10

**Acceptance Rationale**:
Semantic constraints are defense-in-depth, not primary enforcement. Even if the LLM evaluator is fooled, declarative rules still enforce hard limits. The semantic layer adds value by catching novel violations that declarative rules miss, but it is not the sole enforcement mechanism.

**Compensating Controls**:

1. Rate limit semantic evaluator invocations (max 10/minute per agent)
2. Structured input format reduces injection surface area
3. Separate LLM context per evaluation (no cross-contamination)
4. Log all semantic evaluations with full input/output for audit
5. Human review of PERMIT decisions on previously-DENIED patterns

**Monitoring**:

- Track: Semantic override rate (PERMIT when declarative would DENY)
- Alert: Repeated variations of similar action descriptions from same agent
- Dashboard: Semantic decision distribution (PERMIT/DENY/UNCERTAIN)

---

### RR-014: TOCTOU Window in Verification Flow

**Original Threat**: Time-of-Check-to-Time-of-Use race condition
**Solution Applied**: CommitTimeVerifier with optimistic locking
**Residual Risk**: Small window between commit-time re-verification and actual write

**Why Risk Remains**:

- Atomic verify-and-commit requires database-level support
- Network latency between verification service and database
- Distributed transactions have inherent timing windows
- Optimistic locking detects but does not prevent conflicts

**Residual Impact**: LOW
**Residual Likelihood**: LOW
**Residual Score**: 2/10

**Acceptance Rationale**:
Window reduced from ~5 minutes (cache TTL) to ~1-5ms (DB round trip). This is comparable to standard financial system optimistic locking windows. The window is too small for human-speed exploitation and requires precise automated timing.

**Compensating Controls**:

1. Database-level optimistic locking with version columns
2. Serializable isolation level for critical operations
3. Audit trail captures version at both check and commit time
4. Anomaly detection for high retry rates (indicating contention)

**Monitoring**:

- Track: Optimistic locking failure rate per operation type
- Alert: Failure rate > 1% (indicates contention or attack)
- Dashboard: Verification-to-commit delta time distribution

---

### RR-015: Circuit Breaker DoS via Induced Failures

**Original Threat**: PostureCircuitBreaker weaponization
**Solution Applied**: Admin override, failure categorization, jitter
**Residual Risk**: Sophisticated attacker can still cause operational degradation

**Why Risk Remains**:

- External service manipulation can induce genuine failures
- Failure categorization requires correct root cause analysis
- Admin override has human latency (minutes, not milliseconds)
- Jitter adds randomness but does not eliminate predictability

**Residual Impact**: MEDIUM
**Residual Likelihood**: LOW
**Residual Score**: 3/10

**Acceptance Rationale**:
Circuit breaker's purpose is safety -- occasional false positives are preferable to allowing harmful operations through. Admin override provides an escape hatch for legitimate operations during false trips.

**Compensating Controls**:

1. Separate circuit breakers for security vs operational failures
2. Admin override with mandatory audit trail
3. Require sustained failure pattern before tripping (not single event)
4. Auto-correlation of circuit breaker trips with external events
5. Gradual degradation (reduce rate) before full open

**Monitoring**:

- Track: Circuit breaker state transitions per service
- Alert: Multiple breakers tripping simultaneously
- Alert: Breaker opening without corresponding security event
- Dashboard: Failure categorization accuracy over time

---

### RR-016: Migration Replay During Delegation Signature Transition

**Original Threat**: Unsigned to signed delegation migration
**Solution Applied**: Version negotiation, monotonic counters
**Residual Risk**: Narrow window during migration where both signed and unsigned delegations are accepted

**Why Risk Remains**:

- Migration cannot be instantaneous across distributed system
- Compatibility mode required during transition period
- Attacker can capture unsigned delegations pre-migration and replay
- Counter synchronization requires consensus across nodes

**Residual Impact**: MEDIUM
**Residual Likelihood**: LOW
**Residual Score**: 3/10

**Acceptance Rationale**:
Migration is a one-time event with a bounded time window. After strict mode is enabled, this risk drops to zero. The risk only exists during the transition period and can be minimized through operational controls.

**Compensating Controls**:

1. Minimize migration window (target < 1 hour)
2. Increase monitoring sensitivity during migration
3. Log all unsigned delegation acceptance during migration
4. Post-migration audit to verify no unauthorized delegations
5. Rollback capability if anomalies detected during migration

**Monitoring**:

- Track: Unsigned delegation acceptance count during migration
- Alert: Unsigned delegation accepted after migration completion target
- Post-migration: Full audit of all delegations created during window

---

### RR-017: Multi-Region Replication Lag

**Original Threat**: Inconsistent trust enforcement across regions
**Solution Applied**: Hub-and-spoke replication with eventual consistency
**Residual Risk**: 2-second replication lag allows stale trust data in secondary regions

**Why Risk Remains**:

- Speed of light imposes minimum cross-region latency
- CAP theorem forces consistency/availability tradeoff
- Write forwarding to primary adds round-trip latency
- Network congestion can cause lag spikes

**Residual Impact**: LOW
**Residual Likelihood**: MEDIUM
**Residual Score**: 3/10

**Acceptance Rationale**:
2-second lag is acceptable for most trust operations. Critical operations (revocation, new delegation) are routed to the primary region directly. The lag is bounded and monitored, with circuit breakers if it exceeds thresholds.

**Compensating Controls**:

1. Critical operations (revoke, delegate) routed to primary region
2. Replication lag monitoring with < 2s SLA
3. Circuit breaker if lag exceeds 10 seconds
4. Read-after-write consistency for originating client

**Monitoring**:

- Track: Replication lag per region (P50, P95, P99)
- Alert: Lag > 5 seconds in any region
- Critical: Lag > 30 seconds triggers circuit breaker
- Dashboard: Real-time lag visualization across all regions

---

## Section 2: Risk Acceptance Matrix

| ID     | Risk                  | Impact   | Likelihood | Score | Accepted? | Review Trigger                        |
| ------ | --------------------- | -------- | ---------- | ----- | --------- | ------------------------------------- |
| RR-001 | Insider HSM Access    | HIGH     | LOW        | 5     | YES       | Insider incident anywhere in industry |
| RR-002 | Side-Channel          | MEDIUM   | LOW        | 3     | YES       | New side-channel technique published  |
| RR-003 | Crypto Zero-Day       | CRITICAL | VERY LOW   | 3     | YES       | NIST algorithm deprecation            |
| RR-004 | Novel Gaming          | MEDIUM   | MEDIUM     | 5     | YES       | Successful gaming detected            |
| RR-005 | Partial Revocation    | MEDIUM   | LOW        | 3     | YES       | Network partition event               |
| RR-006 | Posture Ambiguity     | LOW      | MEDIUM     | 3     | YES       | Customer complaint about behavior     |
| RR-007 | Human Origin Forgery  | HIGH     | LOW        | 5     | YES       | IdP compromise in industry            |
| RR-008 | Supply Chain          | CRITICAL | LOW        | 4     | YES       | Major supply chain attack             |
| RR-009 | Performance DoS       | MEDIUM   | MEDIUM     | 4     | YES       | DoS incident                          |
| RR-010 | Regulatory Gaps       | MEDIUM   | MEDIUM     | 4     | YES       | New regulation enacted                |
| RR-011 | Data Sovereignty      | HIGH     | LOW        | 4     | YES       | Cross-border incident                 |
| RR-012 | Unknown Unknowns      | UNKNOWN  | MEDIUM     | 5     | YES       | Security incident                     |
| RR-013 | Prompt Injection Eval | MEDIUM   | MEDIUM     | 5     | YES       | Successful LLM bypass detected        |
| RR-014 | TOCTOU Window         | LOW      | LOW        | 2     | YES       | Race condition exploit reported       |
| RR-015 | Circuit Breaker DoS   | MEDIUM   | LOW        | 3     | YES       | Induced failure pattern detected      |
| RR-016 | Migration Replay      | MEDIUM   | LOW        | 3     | YES       | Unsigned delegation post-migration    |
| RR-017 | Replication Lag       | LOW      | MEDIUM     | 3     | YES       | Lag-related enforcement inconsistency |

**Total Accepted Residual Risk Score**: 64/170 (38%)

---

## Section 3: Risk Acceptance Criteria

### Automatic Acceptance (No Review Required)

- Residual Score <= 3
- Compensating controls verified in place
- Monitoring active

### Conditional Acceptance (Manager Review)

- Residual Score 4-5
- Compensating controls partially implemented
- Monitoring configuration pending

### Escalated Acceptance (Executive Review)

- Residual Score 6-7
- Compensating controls have gaps
- Requires additional investment

### Rejected (Remediation Required)

- Residual Score >= 8
- Compensating controls ineffective
- Immediate action required

---

## Section 4: Residual Risk Monitoring Dashboard

### Key Metrics

| Metric                            | Target | Alert Threshold | Critical Threshold |
| --------------------------------- | ------ | --------------- | ------------------ |
| Signing latency (P95)             | < 20ms | > 50ms          | > 100ms            |
| Verification latency (P95)        | < 10ms | > 25ms          | > 50ms             |
| Cache hit rate                    | > 95%  | < 90%           | < 80%              |
| Revocation propagation time (P95) | < 5s   | > 15s           | > 60s              |
| Constraint violation rate         | < 1%   | > 5%            | > 10%              |
| Posture mapping fallback rate     | < 2%   | > 5%            | > 10%              |
| Cross-border delegation rate      | < 5%   | > 15%           | > 25%              |
| Audit trail completeness          | 100%   | < 99.9%         | < 99%              |

### Dashboard Panels

1. **Trust Operations Health**
   - Operations per second (establish, delegate, verify, audit)
   - Error rate by operation type
   - Latency distribution

2. **Revocation Status**
   - Active revocations in progress
   - Revocation completion rate
   - Zombie delegation count

3. **Constraint Enforcement**
   - Violations by type (rate limit, time window, etc.)
   - Gaming pattern indicators
   - Agent approaching limits

4. **Cryptographic Health**
   - HSM/KMS availability
   - Key usage patterns
   - Signature verification failures

5. **Federation Status**
   - Active federation agreements
   - Cross-org delegation flow
   - Data classification distribution

---

## Section 5: Review Schedule

### Weekly

- [ ] Review alert history
- [ ] Check monitoring dashboard anomalies
- [ ] Triage any security reports

### Monthly

- [ ] Review residual risk scores
- [ ] Update compensating control effectiveness
- [ ] Assess any new threats

### Quarterly

- [ ] Comprehensive residual risk review
- [ ] Red team exercise (constraint gaming, revocation)
- [ ] Compliance posture assessment
- [ ] Update risk acceptance decisions

### Annually

- [ ] Third-party security assessment
- [ ] Cryptographic posture review
- [ ] Regulatory compliance audit
- [ ] Risk acceptance re-ratification

---

## Section 6: Escalation Procedures

### Risk Score Increase

If any residual risk score increases:

1. Immediate: Log reason for increase
2. 24 hours: Assess impact on overall risk posture
3. 1 week: Propose enhanced compensating controls
4. 2 weeks: Implement or escalate

### New Risk Identified

If a new residual risk is identified:

1. Immediate: Document in risk register
2. 24 hours: Assign initial score and owner
3. 1 week: Define compensating controls
4. 2 weeks: Implement monitoring
5. 1 month: Review for acceptance

### Security Incident

If a residual risk is exploited:

1. Immediate: Incident response activation
2. 4 hours: Contain and assess impact
3. 24 hours: Initial root cause analysis
4. 1 week: Full post-mortem
5. 2 weeks: Enhanced controls implemented
6. 1 month: Risk register updated with lessons learned

---

## Section 7: Signatures

### Risk Acceptance Sign-Off

| Role             | Name      | Date   | Signature   |
| ---------------- | --------- | ------ | ----------- |
| Security Lead    | [PENDING] | [DATE] | [SIGNATURE] |
| Engineering Lead | [PENDING] | [DATE] | [SIGNATURE] |
| Product Lead     | [PENDING] | [DATE] | [SIGNATURE] |
| Legal/Compliance | [PENDING] | [DATE] | [SIGNATURE] |

### Review History

| Version | Date       | Reviewer                 | Changes                                             |
| ------- | ---------- | ------------------------ | --------------------------------------------------- |
| 1.0     | 2026-02-07 | Deep Analysis Specialist | Initial document                                    |
| 2.0     | 2026-02-07 | Red Team Review          | Added RR-013 through RR-017 from second-pass review |

---

## Document Metadata

| Attribute      | Value                    |
| -------------- | ------------------------ |
| Version        | 2.0                      |
| Created        | 2026-02-07               |
| Author         | Deep Analysis Specialist |
| Classification | Internal - Executive     |
| Review Cycle   | Quarterly                |
| Next Review    | 2026-05-07               |
