# ISO 27001 Annex A Control Mapping

This document maps TrustPlane record types to ISO 27001:2022 Annex A controls.

## Overview

TrustPlane's EATP-powered trust chain provides cryptographic evidence for ISO 27001 compliance audits. Each TrustPlane record type maps to relevant Annex A controls, providing automated evidence collection for the Information Security Management System (ISMS).

## Control Mappings

### A.9.2: User Access Management

**TrustPlane Source**: Decision Records

Decision records document every access decision:
- **A.9.2.1 User registration and de-registration**: Delegation records track the lifecycle of review authority, from creation through revocation.
- **A.9.2.2 User access provisioning**: Decision records capture what access was granted, with full rationale and alternatives considered.
- **A.9.2.3 Management of privileged access rights**: The constraint envelope restricts privileged operations across 5 EATP dimensions (operational, data_access, financial, temporal, communication).
- **A.9.2.5 Review of user access rights**: Milestone records trigger periodic review checkpoints.

**Evidence fields**:
- `decision_id`: Unique identifier
- `decision_type`: Category of decision
- `decision`: What was decided
- `rationale`: Why this choice was made
- `alternatives`: Options considered and rejected
- `confidence`: Confidence level (0.0-1.0)
- `author`: Who made the decision
- `timestamp`: When the decision was recorded

### A.12.4: Logging and Monitoring

**TrustPlane Source**: Milestone Records

Milestone records provide audit checkpoints:
- **A.12.4.1 Event logging**: Every decision, milestone, and hold creates an EATP Audit Anchor with cryptographic chain integrity.
- **A.12.4.2 Protection of log information**: The EATP trust chain uses SHA-256 hashing and Ed25519 signing to prevent tampering.
- **A.12.4.3 Administrator and operator logs**: Delegation and revocation events are logged as Audit Anchors.
- **A.12.4.4 Clock synchronisation**: All timestamps are UTC with timezone awareness.

**Evidence fields**:
- `milestone_id`: Unique identifier
- `version`: Version string
- `description`: What the milestone represents
- `file_hash`: SHA-256 hash of the milestoned file
- `decision_count`: Number of decisions at checkpoint
- `timestamp`: When the milestone was recorded

### A.16.1: Management of Information Security Incidents

**TrustPlane Source**: HELD/BLOCKED Verdicts

Hold records document security incidents:
- **A.16.1.1 Responsibilities and procedures**: The constraint enforcer automatically classifies actions as AUTO_APPROVED, FLAGGED, HELD, or BLOCKED.
- **A.16.1.2 Reporting information security events**: HELD and BLOCKED verdicts are immediately recorded as hold records.
- **A.16.1.4 Assessment of and decision on information security events**: Each hold includes the action, resource, reason, and resolution details.
- **A.16.1.5 Response to information security incidents**: Hold resolution tracks who approved/denied and why.
- **A.16.1.6 Learning from information security incidents**: The violation log enables trend analysis across reporting periods.

**Evidence fields**:
- `hold_id`: Unique identifier
- `action`: The action that was held
- `resource`: The resource being accessed
- `reason`: Why the action was held (constraint violation)
- `status`: pending / approved / denied
- `created_at`: When the hold was created
- `resolved_at`: When and if the hold was resolved
- `resolved_by`: Who resolved the hold
- `resolution_reason`: Explanation for the resolution

## Generating Evidence

```bash
# Generate ISO 27001 evidence package
attest export --format iso27001

# With date range filter
attest export --format iso27001 --period 2026-01-01:2026-03-31

# Specify output path
attest export --format iso27001 --output iso-evidence-q1-2026.zip
```

The generated ZIP contains:
- `evidence-summary.md` -- Markdown report with all control mappings
- `control-mapping.json` -- Machine-readable control mapping
- `decision-log.csv` -- All decisions in CSV format
- `violation-log.csv` -- All holds/violations in CSV format
- `chain-verification.json` -- EATP chain integrity verification result

## Cross-Reference with SOC2

| ISO 27001 Control | SOC2 Control | TrustPlane Source |
|---|---|---|
| A.9.2 User Access Management | CC6.7 Restriction of Privileged Access | Decision Records |
| A.12.4 Logging and Monitoring | CC7.2 System Monitoring | Milestone Records |
| A.16.1 Security Incident Management | CC7.3 Evaluation of Security Events | HELD/BLOCKED Verdicts |
