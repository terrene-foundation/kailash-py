# User Flow: Enterprise Compliance Officer

## Persona: Compliance Lead at AI-Forward Financial Services Firm

**Context**: Firm uses AI coding assistants across 20 teams. Regulator (SEC/OCC) asks: "How do you govern your AI-assisted development?" Currently the answer is: "We review PRs." Needs a better answer.

---

## Flow 1: Evaluation

### Step 1: Technical Assessment

- Reviews TrustPlane architecture documentation
- Verifies cryptographic chain (Ed25519 signatures, hash-linked anchors)
- Validates three-tier enforcement model
- **Key question**: "Can we prove to a regulator that AI stayed within authorized boundaries?"
- **Answer**: Yes — Tier 3 proxy provides infrastructure-enforced constraints, audit chain is cryptographically verifiable

### Step 2: Pilot Setup

- Single team deploys TrustPlane in shadow mode (no enforcement, observation only)
- 2-week observation period to understand AI behavior patterns
- Review shadow report: what actions were taken, what would have been flagged/held

### Step 3: Constraint Configuration

- Apply `governance` template — conservative defaults for financial services
- Customize: block production database access, limit financial operations, require FULL verification for infrastructure changes
- Run `attest diagnose` to validate constraint quality

---

## Flow 2: Deployment

### Step 4: Graduated Rollout

- Week 1-2: Shadow mode across 3 pilot teams
- Week 3-4: Strict mode for pilot teams, shadow for remaining
- Week 5-8: Strict mode for all teams using AI assistants
- Each transition reviewed by compliance committee

### Step 5: Delegation Setup

```bash
attest delegate --name "Team Lead" --dimensions operational,data_access --expires 90d
```

- Team leads can approve HELD actions within their scope
- Cross-team actions escalate to compliance
- Cascade revocation if team lead leaves

### Step 6: CI Integration

- `attest verify` in all CI pipelines
- PRs without valid trust chain are blocked
- Verification status shown on PR

---

## Flow 3: Audit Response

### Step 7: Regulator Request

Regulator asks: "Show us how AI development was governed last quarter."

### Step 8: Generate Evidence

```bash
attest audit --from 2026-01-01 --to 2026-03-31
attest export --format bundle
```

- Produces audit report with: timeline of all decisions, constraint utilization, held/approved actions, competency map showing human vs. AI contribution
- Verification bundle can be independently verified with public key

### Step 9: Independent Verification

Regulator's auditor runs:

```bash
attest verify --bundle evidence-Q1-2026.json --public-key team-pubkey.pem
```

- No TrustPlane installation needed — bundle is self-contained
- Verifies every anchor in the chain
- Confirms no tampering, no gaps in the audit trail

---

## Enterprise Requirements Matrix

| Requirement                | TrustPlane Status     | Gap                                                 |
| -------------------------- | --------------------- | --------------------------------------------------- |
| Cryptographic audit trail  | IMPLEMENTED           | None                                                |
| Constraint enforcement     | IMPLEMENTED (3 tiers) | None                                                |
| Hold/approve workflow      | IMPLEMENTED           | None                                                |
| Independent verification   | IMPLEMENTED (bundle)  | None                                                |
| Delegation with revocation | IMPLEMENTED           | None                                                |
| SIEM integration           | NOT IMPLEMENTED       | Needs CEF/OCSF export                               |
| SSO/RBAC                   | NOT IMPLEMENTED       | Delegation model is primitive                       |
| Central dashboard          | NOT IMPLEMENTED       | CLI-only                                            |
| Multi-tenant management    | NOT IMPLEMENTED       | Single-project filesystem                           |
| SOC2 evidence mapping      | PARTIAL               | Audit report exists but not mapped to SOC2 controls |
| Key management (HSM)       | NOT IMPLEMENTED       | Local keys only                                     |
| Database backing           | NOT IMPLEMENTED       | Filesystem only                                     |

---

## Compliance Value Proposition

**Before TrustPlane**: "We review PRs and have an acceptable use policy."
**After TrustPlane**: "Every AI action is cryptographically attested. Constraints are infrastructure-enforced. Human oversight is provable. The audit chain is independently verifiable. Here's the evidence."

This is the difference between "we try" and "we can prove."
