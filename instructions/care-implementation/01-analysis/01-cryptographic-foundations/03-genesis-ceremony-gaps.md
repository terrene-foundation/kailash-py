# EATP Genesis Ceremony Gap Analysis

## Executive Summary

The genesis ceremony is the foundational security event in EATP, establishing the organizational root of trust. Currently, the implementation provides basic genesis record creation but lacks the formality, security controls, and procedures required for enterprise deployment. This document analyzes gaps versus PKI root CA ceremony best practices and proposes a comprehensive genesis ceremony protocol.

---

## 1. Current Genesis Record Implementation

### 1.1 What Exists Today

**Location**: `/apps/kailash-kaizen/src/kaizen/trust/operations.py:236-338`

```python
async def establish(
    self,
    agent_id: str,
    authority_id: str,
    capabilities: List[CapabilityRequest],
    constraints: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    expires_at: Optional[datetime] = None,
) -> TrustLineageChain:
    # 1. Validate authority exists and is active
    authority = await self._validate_authority(authority_id)

    # 4. Create Genesis Record
    genesis = GenesisRecord(
        id=f"gen-{uuid4()}",
        agent_id=agent_id,
        authority_id=authority_id,
        authority_type=authority.authority_type,
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at,
        signature="",
        signature_algorithm="Ed25519",
        metadata=metadata,
    )

    # 5. Sign genesis record
    genesis_payload = serialize_for_signing(genesis.to_signing_payload())
    genesis.signature = await self.key_manager.sign(
        genesis_payload, authority.signing_key_id
    )
```

**Genesis Record Structure** (`chain.py:67-115`):

```python
@dataclass
class GenesisRecord:
    id: str
    agent_id: str
    authority_id: str
    authority_type: AuthorityType
    created_at: datetime
    signature: str
    signature_algorithm: str = "Ed25519"
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 1.2 Current Genesis Ceremony (Implicit)

The current "ceremony" is simply:
1. Authority is registered via `OrganizationalAuthorityRegistry.register_authority()`
2. Authority's key is registered via `TrustKeyManager.register_key()`
3. Agents are established via `TrustOperations.establish()`

**No formal ceremony, no multi-person authorization, no key escrow, no audit trail of ceremony itself.**

---

## 2. Gap Analysis: PKI Root CA Best Practices

### 2.1 Physical Security Gaps

| PKI Best Practice | Current EATP State | Gap Severity |
|-------------------|-------------------|--------------|
| Air-gapped ceremony environment | Not addressed | CRITICAL |
| TEMPEST-shielded room | Not addressed | HIGH |
| Video recording of ceremony | Not addressed | HIGH |
| Tamper-evident bags for materials | Not addressed | HIGH |
| Multiple witnesses | Not addressed | CRITICAL |
| Physical access logs | Not addressed | HIGH |

### 2.2 Procedural Security Gaps

| PKI Best Practice | Current EATP State | Gap Severity |
|-------------------|-------------------|--------------|
| Pre-ceremony briefing | Not addressed | HIGH |
| Script/checklist for ceremony | Not addressed | CRITICAL |
| Role assignment (Ceremony Admin, Witnesses, etc.) | Not addressed | HIGH |
| Independent auditor presence | Not addressed | MEDIUM |
| Post-ceremony verification | Not addressed | HIGH |

### 2.3 Cryptographic Security Gaps

| PKI Best Practice | Current EATP State | Gap Severity |
|-------------------|-------------------|--------------|
| HSM for key generation | In-memory only (operations.py:108) | CRITICAL |
| N-of-M threshold signatures | Not implemented | CRITICAL |
| Key activation requires multiple parties | Single party | CRITICAL |
| Key backup with secret sharing | Not implemented | CRITICAL |
| Hardware entropy verification | Not implemented | HIGH |

### 2.4 Succession and Recovery Gaps

| PKI Best Practice | Current EATP State | Gap Severity |
|-------------------|-------------------|--------------|
| Key escrow procedures | Not implemented | CRITICAL |
| Succession planning for key holders | Not implemented | CRITICAL |
| Emergency revocation procedure | Partial (deactivate_authority) | HIGH |
| Disaster recovery for keys | Not implemented | CRITICAL |
| Key holder death/incapacity protocol | Not implemented | HIGH |

### 2.5 Documentation and Audit Gaps

| PKI Best Practice | Current EATP State | Gap Severity |
|-------------------|-------------------|--------------|
| Ceremony report generation | Not implemented | HIGH |
| Witness attestations | Not implemented | HIGH |
| Key fingerprint publication | Not implemented | MEDIUM |
| Ceremony log archival | Not implemented | HIGH |
| Certificate policy documentation | Not implemented | MEDIUM |

---

## 3. Threshold Signature Requirements

### 3.1 Why N-of-M is Required

A single genesis key holder represents a single point of failure and trust. Enterprise environments require:

1. **No single point of compromise**: Any one person's credential loss doesn't compromise system
2. **Collusion resistance**: Requires conspiracy of multiple parties
3. **Availability**: System works even if some key holders unavailable
4. **Auditability**: Multiple signatures provide stronger audit trail

### 3.2 Recommended Threshold Schemes

| Organization Size | Recommended Scheme | Rationale |
|------------------|-------------------|-----------|
| Startup (< 50) | 2-of-3 | Minimum viable security |
| Mid-size (50-500) | 3-of-5 | Balance security and availability |
| Enterprise (500+) | 4-of-7 or 5-of-9 | Strong collusion resistance |
| Critical Infrastructure | 5-of-9 minimum | Regulatory requirements |

### 3.3 Implementation Options

1. **Shamir's Secret Sharing + Ed25519**
   - Split genesis key into N shares
   - Require M shares to reconstruct
   - Pro: Simple, well-understood
   - Con: Key reconstructed in memory (single point of attack)

2. **Multi-signature (Native Ed25519)**
   - Each key holder has own Ed25519 key
   - Genesis record requires M-of-N signatures
   - Pro: Key never reconstructed
   - Con: Larger signatures, more complex verification

3. **Threshold ECDSA/EdDSA**
   - Distributed key generation (DKG)
   - Distributed signing (no key reconstruction)
   - Pro: Most secure
   - Con: Complex implementation, newer cryptography

**Recommendation**: Start with multi-signature (option 2), plan for threshold EdDSA (option 3).

---

## 4. Key Escrow and Recovery Procedures

### 4.1 Current State

No key escrow exists. If the genesis key is lost, the entire trust hierarchy is unrecoverable.

### 4.2 Required Components

1. **Escrow Storage**
   - Bank safe deposit boxes (geographically distributed)
   - Hardware security modules (backup HSMs)
   - Air-gapped offline systems

2. **Split Knowledge**
   - No single party can access escrowed keys
   - Requires coordination of multiple escrow agents
   - Different parties hold different components

3. **Access Procedures**
   - Documented authorization chain for escrow access
   - Requires board-level approval for key recovery
   - Mandatory waiting period (e.g., 72 hours)

4. **Verification**
   - Escrowed material verified periodically (annual)
   - Hash of escrowed material stored separately
   - Verification doesn't expose key material

### 4.3 Proposed Escrow Architecture

```
Genesis Key Material
        |
        v
+------------------+
| Shamir Split 5/7 |
+------------------+
    |  |  |  |  |  |  |
    v  v  v  v  v  v  v
  [S1][S2][S3][S4][S5][S6][S7]
    |   |   |   |   |   |   |
    v   v   v   v   v   v   v
  Bank Bank HSM  HSM  Safe Safe External
  NYC  LON  AWS  GCP  CEO  CTO  Escrow
```

---

## 5. Succession Planning

### 5.1 Key Holder Roles

| Role | Count | Responsibilities | Succession |
|------|-------|------------------|------------|
| Ceremony Administrator | 1-2 | Conducts ceremony | Deputy admin |
| Key Holder | 5-9 | Holds key share/shard | Pre-designated alternate |
| Witness | 2+ | Observes, attests | Pool of approved witnesses |
| Auditor | 1 | Independent verification | External audit firm |
| Escrow Agent | 3+ | Holds escrow shares | Bank/legal designee |

### 5.2 Succession Triggers

1. **Planned succession**: Retirement, role change
2. **Unplanned succession**: Death, incapacity, termination for cause
3. **Emergency succession**: Key compromise, insider threat

### 5.3 Succession Procedure

1. New key holder identified and vetted
2. Background check completed
3. Old key holder transfers share (or share is recovered from escrow)
4. New key holder acknowledges responsibilities (signed document)
5. Key share transferred in ceremony (witnessed)
6. Audit log updated
7. Old share destroyed (witnessed)

---

## 6. HSM Integration Requirements

### 6.1 HSM Capabilities Required

| Capability | Requirement |
|------------|-------------|
| Algorithm Support | Ed25519 (or ability to import Ed25519 keys) |
| FIPS 140-2 Level | Level 3 minimum (Level 4 for critical systems) |
| Key Export | Never (keys generated/used in HSM only) |
| Multi-party Auth | M-of-N for key usage |
| Audit Logging | Complete, tamper-evident |
| API | PKCS#11 or vendor SDK |

### 6.2 Recommended HSMs

| HSM | FIPS Level | Ed25519 Support | Multi-party | Notes |
|-----|-----------|-----------------|-------------|-------|
| Thales Luna | 3 | Yes (recent firmware) | Yes | Industry standard |
| AWS CloudHSM | 3 | Yes | Limited | Cloud-native |
| Azure Dedicated HSM | 3 | Yes | Limited | Azure integration |
| YubiHSM 2 | 3 | Yes | No | Cost-effective |
| Nitrokey HSM 2 | 3 | Yes | No | Open source |

### 6.3 Integration Architecture

```
+----------------------------------+
|          EATP Platform           |
+----------------------------------+
          |
          v
+----------------------------------+
|     HSM Abstraction Layer        |
|   (PKCS#11 / Vendor SDK)         |
+----------------------------------+
          |
          v
+----------------------------------+
|   Hardware Security Module       |
|   - Key Storage (non-exportable) |
|   - Signing Operations           |
|   - Audit Logging                |
+----------------------------------+
```

---

## 7. Proposed Genesis Ceremony Protocol

### 7.1 Pre-Ceremony Phase (T-7 days)

1. **Announcement**
   - Send ceremony date/time to all participants
   - Distribute ceremony script
   - Assign roles (Administrator, Key Holders, Witnesses, Auditor)

2. **Preparation**
   - Verify HSM firmware and configuration
   - Prepare air-gapped ceremony laptop
   - Print ceremony forms (key holder acknowledgments, witness attestations)
   - Prepare tamper-evident bags

3. **Facility Setup**
   - Reserve secure facility
   - Verify video recording equipment
   - Establish chain of custody for all materials

### 7.2 Ceremony Phase (T-0)

**Duration**: 4-6 hours

**Step 1: Opening (30 min)**
- Administrator opens ceremony
- Attendance recorded (ID verification)
- Read ceremony purpose statement
- Distribute and review ceremony script

**Step 2: HSM Initialization (1 hour)**
- Power on air-gapped HSM
- Verify HSM firmware hash
- Initialize HSM with new Security World
- Generate M-of-N administrator cards

**Step 3: Genesis Key Generation (1 hour)**
- Generate Ed25519 key pair in HSM (never exportable)
- Verify key generation (entropy check)
- Record public key fingerprint
- All witnesses verify fingerprint matches
- Sign key attestation document

**Step 4: Escrow Share Creation (1 hour)**
- Generate backup shares using Shamir's Secret Sharing
- Each escrow agent receives share in tamper-evident bag
- Escrow agents verify share (test recovery)
- Escrow agents sign custody acknowledgment

**Step 5: Authority Registration (30 min)**
- Create OrganizationalAuthority record
- Sign with genesis key
- Store in trust store
- Verify signature

**Step 6: Verification (30 min)**
- Perform test establishment and verification
- All witnesses confirm successful verification
- Record verification results

**Step 7: Closing (30 min)**
- Generate ceremony report hash
- All participants sign ceremony report
- Seal ceremony materials in tamper-evident bags
- Video recording secured

### 7.3 Post-Ceremony Phase

1. **Documentation**
   - Generate ceremony report (within 24 hours)
   - Distribute to all participants for signature
   - Archive signed report in secure storage

2. **Publication**
   - Publish public key fingerprint
   - Update organization's security documentation
   - Notify relying parties

3. **Verification**
   - Independent auditor reviews ceremony materials
   - Issues audit report
   - Archive with ceremony materials

---

## 8. Emergency Procedures

### 8.1 Key Compromise Response

**Trigger**: Evidence or reasonable suspicion of genesis key compromise

**Procedure**:
1. **Immediate** (< 1 hour)
   - Notify Security Incident Response team
   - Activate backup authority (if exists)
   - Suspend all trust establishment operations

2. **Short-term** (< 24 hours)
   - Revoke all trust chains established with compromised key
   - Notify all relying parties
   - Initiate forensic investigation

3. **Recovery** (< 7 days)
   - Conduct new genesis ceremony
   - Re-establish all trust chains with new authority
   - Issue incident report

### 8.2 Key Holder Incapacity

**Trigger**: Key holder death, incapacity, or termination

**Procedure**:
1. Verify incapacity status
2. Notify escrow agents (if share recovery needed)
3. Initiate succession procedure
4. Update access controls

### 8.3 Escrow Recovery

**Trigger**: Primary key inaccessible (HSM failure, etc.)

**Procedure**:
1. Board-level authorization required
2. 72-hour waiting period
3. M-of-N escrow agents convene
4. Recovery ceremony (witnessed, recorded)
5. Key imported to new HSM
6. Old escrow shares destroyed, new shares created

---

## 9. Implementation Roadmap

### Phase 1: Foundational (Month 1-2)

| Task | Effort | Priority |
|------|--------|----------|
| Document ceremony procedure | M | HIGH |
| Create ceremony checklist | S | HIGH |
| Design multi-signature genesis record format | M | HIGH |
| Implement HSM abstraction layer interface | M | HIGH |

### Phase 2: Multi-Signature (Month 3-4)

| Task | Effort | Priority |
|------|--------|----------|
| Implement multi-signature genesis verification | L | HIGH |
| Update GenesisRecord with signatures array | M | HIGH |
| Create ceremony CLI tool | M | MEDIUM |
| Implement key holder management | M | HIGH |

### Phase 3: HSM Integration (Month 5-6)

| Task | Effort | Priority |
|------|--------|----------|
| Integrate with specific HSM (e.g., AWS CloudHSM) | L | HIGH |
| Implement PKCS#11 provider | L | HIGH |
| Create HSM ceremony procedures | M | HIGH |
| Test with hardware HSM | M | HIGH |

### Phase 4: Escrow and Recovery (Month 7-8)

| Task | Effort | Priority |
|------|--------|----------|
| Implement Shamir's Secret Sharing | M | HIGH |
| Create escrow storage procedures | M | HIGH |
| Implement recovery procedure | M | HIGH |
| Create succession management system | M | MEDIUM |

### Phase 5: Audit and Compliance (Month 9-10)

| Task | Effort | Priority |
|------|--------|----------|
| Create ceremony audit trail | M | HIGH |
| Implement ceremony report generation | M | MEDIUM |
| External audit of procedures | L | MEDIUM |
| Compliance documentation | M | MEDIUM |

---

## 10. Summary: Critical Gaps

| Gap | Current State | Required State | Business Impact |
|-----|--------------|----------------|-----------------|
| Single genesis key | Yes | N-of-M threshold | Single point of failure |
| HSM storage | No | Required | Key extractable from memory |
| Key escrow | No | Required | Unrecoverable on key loss |
| Ceremony procedure | None | Formal script | Inconsistent security |
| Succession planning | None | Documented | Operational continuity risk |
| Multi-witness | No | Required | Insufficient oversight |
| Air-gapped ceremony | No | Required | Network attack surface |

**Recommendation**: Before production deployment, implement at minimum:
1. Multi-signature genesis records (3-of-5)
2. HSM key storage
3. Documented ceremony procedure with witnesses
4. Key escrow with geographic distribution
