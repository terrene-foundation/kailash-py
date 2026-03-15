# SOC2 Control Mapping

This document maps TrustPlane record types to SOC2 Trust Services Criteria controls.

## Overview

TrustPlane's EATP-powered trust chain provides cryptographic evidence for SOC2 audits. Each TrustPlane record type maps to one or more SOC2 controls, providing automated evidence collection.

## Control Mappings

### CC6.2: Inventory of Information Assets

**TrustPlane Source**: Genesis Record

The Genesis Record establishes the project root of trust, documenting:
- Project identity and author
- Initial constraint envelope (5 EATP dimensions)
- Authority public key for cryptographic verification
- Creation timestamp

**Evidence**: The Genesis Record is created once per project via `attest init` and is immutable. It serves as the foundation for all subsequent trust chain entries.

### CC6.3: Removal of Access

**TrustPlane Source**: Delegation Records

Delegation records track the granting and revocation of review authority:
- Delegates are scoped to specific constraint dimensions (operational, data_access, financial, temporal, communication)
- Cascade revocation: revoking a delegate automatically revokes all sub-delegates
- Delegation depth limits prevent unbounded chains
- Each revocation creates an EATP Audit Anchor

**Evidence**: `attest delegate list --all` shows all delegates including revoked ones. Each delegate record includes creation time, revocation time, and the delegator who granted access.

### CC6.7: Restriction of Privileged Access

**TrustPlane Source**: Decision Records

Decision records capture every access decision with full reasoning trace:
- Decision type and description
- Rationale explaining why this choice was made
- Alternatives considered and rejected
- Known risks identified
- Confidence level (0.0-1.0)
- Review requirement level (QUICK/STANDARD/FULL)
- Author identity

**Evidence**: `attest decisions --json-output` exports all decisions. Each decision is backed by an EATP Audit Anchor with cryptographic chain integrity.

### CC6.8: Monitoring

**TrustPlane Source**: Execution Records

Execution records log every autonomous AI action:
- Action description
- Constraint reference (which constraint authorized the action)
- Verification category (AUTO_APPROVED, FLAGGED, HELD, BLOCKED)
- Constraint envelope hash for tamper detection
- Confidence level

**Evidence**: Execution records are part of the Mirror Thesis data, accessible via `attest mirror --json-output`.

### CC7.2: System Monitoring

**TrustPlane Source**: Milestone Records

Milestone records provide versioned checkpoints:
- Version string (e.g., v0.1, v1.0)
- Description of what the milestone represents
- File path and SHA-256 hash for tamper detection
- Decision count at time of milestone
- Author and timestamp

**Evidence**: Milestones enable continuous monitoring of project state. Any change to a milestoned file is detectable via hash comparison.

### CC7.3: Evaluation of Security Events

**TrustPlane Source**: HELD/BLOCKED Verdicts

When the constraint enforcer evaluates an action:
- **HELD**: Action requires human approval before proceeding
- **BLOCKED**: Action is denied outright

Hold records capture:
- The action that triggered the hold
- The resource being accessed
- The reason for the hold (which constraint was violated)
- Resolution status (approved/denied)
- Who resolved it and when

**Evidence**: `attest hold list --json` shows all holds. The violation log CSV in the evidence package lists all holds with resolution details.

## Generating Evidence

```bash
# Generate SOC2 evidence package
attest export --format soc2

# With date range filter
attest export --format soc2 --period 2026-01-01:2026-03-31

# Specify output path
attest export --format soc2 --output evidence-q1-2026.zip
```

The generated ZIP contains:
- `evidence-summary.md` -- Markdown report with all control mappings
- `control-mapping.json` -- Machine-readable control mapping
- `decision-log.csv` -- All decisions in CSV format
- `violation-log.csv` -- All holds/violations in CSV format
- `chain-verification.json` -- EATP chain integrity verification result
