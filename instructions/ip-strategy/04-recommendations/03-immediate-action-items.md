> **PARTIALLY SUPERSEDED — RECOMMENDATIONS**
>
> These recommendations were prepared during the IP strategy development process (February
> 2026). The licensing recommendations (custom KSL v1.0) were superseded by the 6 February
> 2026 decision to adopt pure Apache 2.0. Patent filing recommendations remain valid and
> actionable. See `DECISION-MEMORANDUM.md` and `07-foundation/` for the current strategy.

# 03 - Immediate Action Items

## Document Purpose

Prioritized list of actions to be taken, ordered by urgency and dependency.

## Actions Requiring No External Approval

These can be done immediately by the development team:

### Action 1: Fix PyPI Classifier (Priority: URGENT)

**Files to modify:**

- `apps/kailash-dataflow/setup.py` - Change classifier
- `apps/kailash-nexus/setup.py` - Change classifier
- `apps/kailash-kaizen/setup.py` - Change classifier

**Change:**

```python
# FROM:
"License :: OSI Approved :: Apache Software License"

# TO:
"License :: Other/Proprietary License"
```

**Why urgent**: Every PyPI download currently misrepresents the license.

### Action 2: Add LICENSE to Kaizen (Priority: HIGH)

**Action**: Copy `/LICENSE` to `apps/kailash-kaizen/LICENSE`

**Why**: Package distributions should include license terms.

### Action 3: Add PATENTS File (Priority: HIGH)

**Action**: Create `/PATENTS` file in repository root:

```
Terrene Foundation Patent Notice

The technology implemented in this software is covered by the following
patent applications:

1. PCT International Application No. PCT/SG2024/050503
   Title: "A System and Method for Development of a Service Application
   on an Application Development Platform"
   Filed: 8 August 2024 (priority date: 14 August 2023)
   Status: IPRP Chapter II favorable (4 December 2025);
   national phase filing in progress

2. Singapore Provisional Application Ref. P251088SG
   Title: "Method and System for Orchestrating Artificial Intelligence
   Workflow"
   Filed: 7 October 2025 (priority date: 7 October 2025)
   Status: Provisional filed; complete application pending

National phase applications (updated as filed):
- [To be updated upon filing]

Subject to the terms of the applicable license, Terrene Foundation
grants users of this software a license under the above patents as
described in the LICENSE file.
```

## Actions Requiring Legal Counsel

### Action 4: Engage Licensing Counsel (Priority: HIGH)

**Action**: Engage a software licensing attorney (separate from patent counsel) to:

- Draft the Kailash Software License v1.0
- Review patent grant clause for legal soundness
- Verify fair-code compliance
- Draft Enterprise License template

**Note**: Auriga IP handles patent prosecution. Licensing is a separate specialty. Consider engaging a firm experienced in open-source/fair-code licensing.

### Action 5: Instruct Auriga IP on National Phase — SG and US COMPLETED

**IPRP Chapter II confirmed favorable on 4 December 2025. All 18 claims approved.**

**Status**: Singapore and United States national phase entries have been **FILED**.

**Remaining action**: Prepare China filing through Chinese associate (deadline: **14 March 2026**).

- ~~File Singapore national phase entry at IPOS before 14 February 2026~~ — **FILED**
- ~~Engage US associate counsel experienced in Alice and file US national phase entry before 14 February 2026~~ — **FILED**
- File China national phase entry at CNIPA **before 14 March 2026** — PENDING
- Calendar all deadlines

### Action 6: Draft License Transition Communication (Priority: MEDIUM)

**Action**: Prepare:

- Blog post explaining the change
- GitHub announcement
- FAQ document
- Community discussion thread

## Actions Requiring Board/Founder Decision

### Decision 1: License Choice

**Options** (see `02-research/03-comparable-licenses.md`):

- A: Adopt Elastic License 2.0 directly (fastest, strongest precedent)
- B: Adopt Sustainable Use License directly (closest to n8n community)
- C: Draft custom Kailash Software License (best fit, more effort)
- D: Adopt ELv2 with supplementary patent grant addendum (balanced)

**Recommendation**: Option C or D

### Decision 2: Patent Filing Budget

**Required**: Approve approximately USD 25,000-45,000 for Tier 1 + Tier 2 filings

- Singapore: SGD 5,000-15,000
- United States: USD 10,000-20,000
- China: USD 5,000-10,000

### Decision 3: Enterprise Licensing Model

**Decisions needed**:

- Pricing structure (per-seat, per-deployment, flat annual)
- Feature separation (`.ee` files or separate packages)
- Sales process (self-serve or sales-led)

## Dependency Graph

```
Action 1 (Fix PyPI) ──────────────────────> Can ship immediately
Action 2 (Kaizen LICENSE) ─────────────────> Can ship immediately
Action 3 (PATENTS file) ──────────────────> Can ship immediately

Decision 1 (License choice) ───> Action 4 (Engage counsel) ───> Draft license
                                                                      │
Action 5 (National phase) ─────────────────────────────────────> File patents
                                                                      │
                                                     Action 6 (Communication)
                                                                      │
                                                          Publish new license
                                                                      │
                                                Decision 3 ───> Enterprise launch
```

## Timeline Summary

| Phase        | Actions                                          | Dependency                   | Deadline             |
| ------------ | ------------------------------------------------ | ---------------------------- | -------------------- |
| **COMPLETED** | ~~File SG and US national phase entries~~       | Founder approval + Auriga IP | ~~14 February 2026~~ FILED |
| Immediate    | Fix PyPI, Add Kaizen LICENSE, Add PATENTS        | None                         | ASAP                 |
| Near-term    | Engage licensing counsel, File CN national phase | Founder approval             | 14 March 2026 (CN)   |
| Medium-term  | Draft license, Draft communication               | Counsel engaged              | —                    |
| Launch       | Publish license, Announce, Register faircode.io  | License finalized            | —                    |
| P251088SG    | Complete application or PCT filing (Patent 2)    | Auriga IP                    | 7 October 2026       |
| Follow-on    | Enterprise license, Extension patents            | Revenue model decided        | —                    |
