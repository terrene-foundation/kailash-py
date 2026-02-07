# IP Strategy Implementation Checklist

## Document Purpose

Master checklist for implementing all IP strategy actions. Created 3 February 2026.
Updated 7 February 2026 to reflect transition from "Apache 2.0 with Additional Terms" to pure Apache 2.0.

## Status Legend

- [ ] Not started
- [x] Completed
- [~~] SUPERSEDED — no longer applicable after transition to pure Apache 2.0

---

## Part A: Fix Package Metadata (PyPI Classifier Misrepresentation)

Every published package previously declared an incorrect OSI-approved license classifier. The actual license was "Apache-2.0 WITH Additional-Terms" which is NOT OSI-approved (the Additional Terms violate OSI clause 6). All classifiers were changed to `"License :: Other/Proprietary License"`.

> **NOTE (7 February 2026):** These classifier changes to "Other/Proprietary" were subsequently **REVERSED** in Part J. With the transition to pure Apache 2.0 (6 February 2026), the correct classifier is now `"License :: OSI Approved :: Apache Software License"`, which is truthful. Part A was correct at the time but is now superseded by Part J items J3/J4.

- [x] A1. Fix `setup.py` (root) — changed from MIT to Other/Proprietary; added license field
- [x] A2. Fix `pyproject.toml` (root) — changed from Apache Software License to Other/Proprietary
- [x] A3. Fix `apps/kailash-dataflow/setup.py` — changed from Apache Software License to Other/Proprietary
- [x] A4. Fix `apps/kailash-dataflow/pyproject.toml` — changed from Apache Software License to Other/Proprietary
- [x] A5. Fix `apps/kailash-nexus/setup.py` — changed from Apache Software License to Other/Proprietary
- [x] A6. Fix `apps/kailash-nexus/pyproject.toml` — changed from Apache Software License to Other/Proprietary
- [x] A7. Fix `apps/kailash-kaizen/setup.py` — changed from Apache Software License to Other/Proprietary
- [x] A8. Fix `apps/kailash-kaizen/pyproject.toml` — changed from Apache Software License to Other/Proprietary
- [x] A9. Fix `apps/qa_agentic_testing/setup.py` — changed from MIT to Other/Proprietary
- [x] A10. Fix `apps/user_management/setup.py` — changed from MIT to Other/Proprietary

## Part B: License File Distribution

Packages distributed via PyPI must include the LICENSE file. Symlinks do not survive sdist/wheel builds.

- [x] B1. Replace Kaizen LICENSE symlink with actual file copy (was symlink -> ../../LICENSE)
- [x] B2. Add LICENSE to `apps/qa_agentic_testing/`
- [x] B3. Add LICENSE to `apps/user_management/`

## Part C: Patent Notice

Create a PATENTS file at the repository root listing both patent applications.

- [x] C1. Create `/PATENTS` file — lists PCT/SG2024/050503 (SG + US filed) and P251088SG

## Part D: NOTICE File Updates

Update NOTICE files to reference patent portfolio.

- [x] D1. Update root `/NOTICE` — added PATENT NOTICE section
- [x] D2. Update `apps/kailash-dataflow/NOTICE` — added patent reference, corrected product name
- [x] D3. Update `apps/kailash-nexus/NOTICE` — added patent reference, corrected product name
- [x] D4. Create `apps/kailash-kaizen/NOTICE` — new file with patent reference

## Part E: Contributing Guide Update

Add IP/licensing section to CONTRIBUTING.md so contributors understand the implications.

- [x] E1. Add IP and licensing section to `/CONTRIBUTING.md` — added License, CLA, Patent, and summary sections

## Part F: Update IP Strategy Documentation for SG/US Filings

The user confirmed Singapore and United States national phase entries have been filed.

- [x] F1. Update `DECISION-MEMORANDUM.md` — removed URGENT banner, added UPDATE with SG/US filed status
- [x] F2. Update `01-background/04-iprp-chapter-ii-outcome.md` — added Status column to deadline table, marked SG/US as FILED
- [x] F3. Update `04-recommendations/02-patent-filing-strategy.md` — marked Actions 1-2 as COMPLETED, updated filing sequence
- [x] F4. Update `04-recommendations/03-immediate-action-items.md` — marked Action 5 SG/US as completed, CN under filing

## Part G: Stakeholder Communication Documents

Prepare clear, professional documents explaining what it means to use Kailash and the protections in place.

- [x] G1. Create `05-stakeholder-communications/01-using-kailash-your-rights-and-obligations.md` — developer/user guide with rights table, patent explanation, FAQ
- [x] G2. Create `05-stakeholder-communications/02-contributor-ip-guide.md` — contributor IP guide with CLA terms, patent awareness, scenarios
- [x] G3. Create `05-stakeholder-communications/03-enterprise-licensing-overview.md` — enterprise overview with dual-license model, use case guidance, procurement info
- [x] G4. Create `05-stakeholder-communications/04-patent-notice-summary.md` — public-facing patent summary with plain-language explanations
- [x] G5. Update `/README.md` license section — added Patent Protection subsection referencing PATENTS file

## Part H: Verification

- [x] H1. Verify all setup.py classifiers are consistent — all 10 files confirmed "Other/Proprietary License"
- [x] H2. Verify all pyproject.toml classifiers are consistent — all 4 files confirmed "Other/Proprietary License"
- [x] H3. Verify LICENSE files exist in all distributable packages — all 6 directories confirmed (real files, no symlinks)
- [x] H4. Verify PATENTS file is accurate and complete — both patents listed with correct status
- [x] H5. Verify NOTICE files are consistent across packages — all 4 packages have NOTICE with patent references

---

## Part I: Fixes from Independent Review (3 February 2026)

Five independent review agents identified gaps. The following code-level fixes were applied:

- [x] I1. Create MANIFEST.in for DataFlow (LICENSE, NOTICE will now ship in sdist/wheel)
- [x] I2. Create MANIFEST.in for Nexus (LICENSE, NOTICE will now ship in sdist/wheel)
- [x] I3. Update root MANIFEST.in — add NOTICE and PATENTS
- [x] I4. Update Kaizen MANIFEST.in — add NOTICE
- [x] I5. Fix Kaizen pyproject.toml author — "Kailash Team" changed to "Terrene Foundation"
- [x] I6. Fix Nexus pyproject.toml author — "Kailash Team" changed to "Terrene Foundation"

---

## Part J: OCEAN Foundation Transition (6-7 February 2026)

On 6 February 2026, the decision was made to abandon the fair-code/KSL approach entirely in favor of pure Apache 2.0 licensing, as part of the OCEAN Foundation strategy. All code-level changes were completed by 7 February 2026.

**Rationale:** Terrene Foundation's commercial model is built on enterprise-app and client solutions, not on licensing the SDK itself. Pure Apache 2.0 maximizes adoption, eliminates licensing complexity, and provides genuine open-source credibility that restrictive licenses cannot. The OCEAN Foundation will steward the donated assets.

- [x] J1. Decision to abandon fair-code/KSL in favor of pure Apache 2.0
- [x] J2. Remove Additional Terms from all 6 LICENSE files (root, dataflow, nexus, kaizen, qa_agentic_testing, user_management)
- [x] J3. Restore all classifiers to `"License :: OSI Approved :: Apache Software License"` (reverses Part A)
- [x] J4. Restore all SPDX identifiers to `"Apache-2.0"` (reverses Part A license field changes)
- [x] J5. Entity name corrected from "Terrene Foundation" to "Terrene Foundation" across all files
- [x] J6. PATENTS file copied to all 3 sub-package directories (dataflow, kaizen, nexus)
- [x] J7. MANIFEST.in files updated to include PATENTS in all 3 sub-packages
- [x] J8. NOTICE files created for qa_agentic_testing and user_management
- [x] J9. MANIFEST.in files created for qa_agentic_testing and user_management
- [x] J10. `license="Apache-2.0"` added to qa_agentic_testing and user_management setup.py
- [x] J11. Kaizen CONTRIBUTING.md updated to explicitly name "Apache License, Version 2.0"
- [x] J12. 6-agent red-team review completed (Full Audit, OSS Lawyer, Patent Troll, Enterprise Counsel, FSF/OSI Purist, PyPI Compliance)
- [x] J13. All CRITICAL and HIGH findings from red-team resolved

---

## Part K: OCEAN Foundation Strategy (Added 3 February 2026, Updated 7 February 2026)

OCEAN Foundation strategy analyzed and revised after comprehensive red-team scrutiny. Updated to reflect the transition to genuine open source (Apache 2.0).

> **NOTE (7 February 2026):** With the transition to pure Apache 2.0, Kailash is now genuine open source, not "source-available." References to "source-available" in the original OCEAN strategy documents are no longer accurate. The Foundation will steward truly open-source Apache 2.0 code.

- [x] K1. Complete 6-agent red-team analysis (Foundation Skeptic, Commercial Viability Critic, Open Source Purist, SME Advocate, IP Strategy Contradiction Analyst, Singapore Regulatory Expert)
- [x] K2. Create `06-ocean/RED-TEAM-SYNTHESIS.md` documenting all findings and resolutions
- [x] K3. Create `06-ocean/01-executive-summary.md` with unified strategy
- [x] K4. Update `06-ocean/10-recommendations-decision-framework.md` with phased approach

### Key OCEAN Strategy Decisions (Updated for Apache 2.0 Transition)

| Decision                  | Resolution                                                   |
| ------------------------- | ------------------------------------------------------------ |
| Licensing model           | Pure Apache 2.0 (no fair-code, no custom license)            |
| Reference implementations | Specifications only (CC0); NO separate Apache 2.0 code track |
| Foundation timeline       | Year 3 (after commercial traction), not Year 1               |
| Patent pledge             | Narrow: protect SMEs/OSS, retain vs hyperscalers             |
| IPC timeline              | Year 3-4 (realistic), not Year 2                             |
| Mission framing           | "AI education and training" (Singapore regulatory compliant) |
| Honest claims             | "Open source (Apache 2.0)" — genuinely OSI-approved          |

### Foundation Launch Criteria (Year 3)

Before launching Foundation, all criteria must be met:

- [ ] Terrene Foundation revenue >S$500K/year
- [ ] 10+ paying enterprise customers
- [ ] OCEAN Specification v1.0 published
- [ ] Founder can commit S$150K/year minimum to Foundation

---

## KSL Draft (SUPERSEDED)

> **SUPERSEDED (6 February 2026):** The Kailash Software License v1.0 draft (`06-license-drafts/KAILASH-SOFTWARE-LICENSE-v1.0.md`) was completed and red-teamed but is **no longer needed**. The decision to adopt pure Apache 2.0 eliminates the need for any custom license. The draft and its red-team summary (`06-license-drafts/RED-TEAM-SUMMARY.md`) are retained for historical reference only.

- [x] ~~**Draft Kailash Software License v1.0**~~ — SUPERSEDED by pure Apache 2.0 decision
  - [x] ~~Explicit patent grant referencing PCT/SG2024/050503 and P251088SG (Section 6.4)~~
  - [x] ~~Patent termination for Section 2 violations and patent litigation (Sections 6.2, 6.3)~~
  - [x] ~~Explicit SaaS/hosted service restriction with examples (Section 2.1)~~
  - [x] ~~No precedence clause ambiguity (standalone license)~~
  - [x] ~~Red-teamed by 4 independent agents — see `06-license-drafts/RED-TEAM-SUMMARY.md`~~
  - [x] ~~All CRITICAL/HIGH vulnerabilities addressed in final draft~~
- ~~[ ] **Counsel review and finalization** of the license draft~~ — NOT NEEDED (pure Apache 2.0)
- ~~[ ] **Review stakeholder communications** against final license before external publication~~ — NOT NEEDED (pure Apache 2.0; stakeholder docs need updating to reflect Apache 2.0)
- ~~[ ] **Stakeholder docs are DRAFTS** — do not publish externally until counsel reviews~~ — Stakeholder docs should be updated to reflect Apache 2.0 before publication

---

## Remaining External Actions (Cannot Be Implemented in Code)

These items require human/legal action. See `NEXT-ACTIONS.md` for detailed guidance.

### CRITICAL -- Patent Deadlines

- [x] File China national phase entry at CNIPA -- **FILED** (confirmed 3 February 2026)
- [ ] Complete P251088SG application or PCT filing (deadline: **7 October 2026**)
- [ ] Obtain legal opinion on patent assignment for Foundation transfer

### HIGH -- Trademark Protection

- [x] Engage trademark counsel for "Kailash" -- **ENGAGED** (confirmed 3 February 2026)
- [ ] Evaluate registrability of "DataFlow", "Nexus", "Kaizen"
- [ ] Secure domain names (kailash.dev, kailash.ai, kailash.io)

### MEDIUM -- Community and Publication

- [ ] Prepare and publish community announcement (blog post, GitHub announcement, FAQ) -- should announce Apache 2.0 simplification
- [ ] Re-publish all PyPI packages with corrected metadata (next release cycle)
- [ ] Update stakeholder communication documents to reflect pure Apache 2.0 (remove KSL references)

---

## Summary

| Part                       | Items  | Completed | Status                               |
| -------------------------- | ------ | --------- | ------------------------------------ |
| A: Classifier Fixes        | 10     | 10        | DONE (subsequently reversed by J)    |
| B: LICENSE Distribution    | 3      | 3         | DONE                                 |
| C: PATENTS File            | 1      | 1         | DONE                                 |
| D: NOTICE Updates          | 4      | 4         | DONE                                 |
| E: Contributing Guide      | 1      | 1         | DONE                                 |
| F: Documentation Updates   | 4      | 4         | DONE                                 |
| G: Stakeholder Docs        | 5      | 5         | DONE (drafts; need Apache 2.0 update)|
| H: Verification            | 5      | 5         | DONE                                 |
| I: Review Fixes            | 6      | 6         | DONE                                 |
| J: Apache 2.0 Transition   | 13     | 13        | DONE                                 |
| K: OCEAN Strategy          | 4      | 4         | DONE (updated for Apache 2.0)        |
| KSL Draft                  | 6      | 6         | SUPERSEDED                           |
| **Code-level total**       | **52** | **52**    | **ALL COMPLETE**                     |
| External actions remaining | 6      | 0         | REQUIRES FOUNDER                     |

---

## Document History

| Date              | Change                                                                                 |
| ----------------- | -------------------------------------------------------------------------------------- |
| 3 February 2026   | Created. Parts A-I implemented and verified.                                           |
| 3 February 2026   | Part K (OCEAN Strategy) added after red-team analysis.                                 |
| 7 February 2026   | Part J added (Apache 2.0 transition). KSL items marked SUPERSEDED. Summary updated.   |
