# TrustPlane Value Audit

**Perspective**: Skeptical enterprise CTO evaluating for potential platform adoption

---

## Value Proposition Assessment

### Core Claim: "The `git init` of AI accountability"

**Strength**: The metaphor communicates simplicity and references a universally understood tool. It positions TrustPlane as infrastructure, not overhead.

**Weakness**: Git had immediate, obvious utility (version control solves a problem you have today). TrustPlane solves a problem most people do not yet recognize they have. The value accrues over time (audit trail) but the cost is immediate (recording decisions).

### The Real Value Statement

> "Today you have policy documents that say what AI should do. TrustPlane proves what AI actually did."

This is the pitch. The current product brief buries this under protocol jargon (EATP, CARE, Mirror Thesis, Genesis Record, Posture State Machine).

### Does It Solve or Just Document?

**Both — and the enforcement story is genuinely strong.** The three-tier architecture separates TrustPlane from pure logging:

- Tier 1 (rules): Advisory — AI can ignore
- Tier 2 (hooks): Process — runs in AI's process
- Tier 3 (proxy): Infrastructure-enforced — AI cannot bypass

Tier 3 is the key differentiator. Fail-closed design means AI physically cannot reach tools without constraint checking. Lead with Tier 3; describe Tiers 1-2 as "defense in depth."

---

## Buyer Persona Analysis

| Segment                                                  | Pain Level | Adoption Likelihood | Barrier                                                             |
| -------------------------------------------------------- | ---------- | ------------------- | ------------------------------------------------------------------- |
| **Regulated enterprises** (finance, healthcare, defense) | HIGH       | MEDIUM              | Need SSO, RBAC, central server, SOC2. TrustPlane lacks all.         |
| **AI safety researchers**                                | HIGH       | HIGH                | Natural fit. Filesystem = inspectable, git-friendly.                |
| **Individual developers**                                | MEDIUM     | LOW-MEDIUM          | Must be zero-effort. Value proposition abstract until audit needed. |
| **Internal dev teams at AI-forward companies**           | HIGH       | MEDIUM              | Filesystem works for single teams; breaks for distributed.          |

**The buyer today**: Technical founder or CTO of an AI-native company building governance from the start. Narrow but high-intent market.

---

## Adoption Friction

### Time to First Value: 15-30 minutes

1. `pip install trust-plane` — installs package + eatp dependency
2. `attest init --name "..." --author "..."` — creates trust directory
3. ... now what?

The README shows `attest decide` and `attest milestone` as next steps. These are manual CLI commands. The developer is expected to manually record decisions — like asking developers to manually write commit messages after every file save.

**Critical gap**: No automatic instrumentation. No `attest watch`. No shadow-mode-first onboarding.

### Missing: Zero-Config Shadow Mode

The single highest-impact feature would be:

```
pip install trust-plane && attest shadow
```

Immediately starts observing AI activity through MCP, producing a report of "here is what your AI did, here is where it pushed boundaries." No configuration, no constraint setup, no ceremony. Value from day one.

---

## Competitive Differentiation

TrustPlane is in a different category from all named competitors:

- **vs. Guardrails AI**: Content quality vs. organizational governance
- **vs. LangSmith**: What happened (observability) vs. what should have happened (governance)
- **vs. OneTrust**: Policy documentation vs. runtime enforcement + attestation
- **vs. Nothing (status quo)**: Primary competitor. Most teams have no AI accountability.

**The risk**: Being first in an unnamed category means educating the market — expensive and benefits later entrants.

---

## Enterprise Readiness Gaps

| Issue                                    | Severity | Impact                                  |
| ---------------------------------------- | -------- | --------------------------------------- |
| No 30-second value proposition in README | CRITICAL | Loses every evaluator at first glance   |
| No shadow-mode-first onboarding          | CRITICAL | Time-to-first-value is 15-30 min        |
| Alpha classification                     | HIGH     | Hard stop for enterprise procurement    |
| No SIEM/GRC integration                  | HIGH     | Cannot fit into existing security stack |
| No HSM/KMS key management                | HIGH     | CISO veto for sensitive deployments     |
| No CI/CD integration (GitHub Action)     | HIGH     | Cannot enforce in automated pipelines   |
| No dashboard/UI                          | MEDIUM   | CLI-only limits visibility              |
| No external security audit               | MEDIUM   | Self-assessed only                      |

---

## What Would Make This Product Great

1. **Zero-config shadow mode**: `attest shadow` — observes AI, produces weekly report. No constraint setup needed.
2. **"Before and after" demo**: Same session without/with TrustPlane. The contrast IS the pitch.
3. **GitHub Action**: `trustplane/verify-action@v1` — runs `attest verify` in CI. Immediate value.
4. **SIEM exporter**: `attest export --format syslog` — feeds into existing security tools.
5. **Graduated messaging**: Lead with business problem, not protocol names. "Prove your AI stayed in bounds."

---

## Bottom Line

TrustPlane is technically ahead of its market. The engineering is strong (7,785 LOC, 431 tests, 12 red team rounds, real crypto chain verification, three-tier enforcement, novel Mirror Thesis concepts). The proxy architecture (Tier 3) is the kind of infrastructure thinking that separates serious governance from checkbox compliance.

The underlying thesis — AI accountability requires cryptographic attestation, not just policy documents — is correct and will become obvious within 18 months as regulation catches up.

The gap between "technically correct" and "market-ready" is: **developer experience, shadow-mode onboarding, ecosystem integration, and messaging that leads with the problem, not the protocol.**
