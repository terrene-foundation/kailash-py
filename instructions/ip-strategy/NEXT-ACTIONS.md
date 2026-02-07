# What You Need To Do Next

## Document Purpose

Prioritized action list for IP strategy implementation. Originally created 3 February 2026.
Updated 7 February 2026 to reflect transition from "Apache 2.0 with Additional Terms" to pure Apache 2.0.

---

## Actions Completed (For Reference)

The following have been implemented in the codebase:

### Original Actions (3 February 2026)

- All 10 PyPI classifiers fixed (setup.py + pyproject.toml)
- LICENSE files distributed to all 6 packages (no symlinks)
- PATENTS file created at repository root
- NOTICE files updated/created across all 4 framework packages
- CONTRIBUTING.md updated with IP section
- MANIFEST.in files created/updated for all packages (legal files will ship in sdist/wheel)
- Author metadata standardized to "Terrene Foundation" across all pyproject.toml files
- IP strategy documentation updated for SG/US national phase filings
- 4 stakeholder communication documents drafted
- README.md updated with patent notice

### Apache 2.0 Transition (6-7 February 2026)

- Additional Terms removed from all 6 LICENSE files (now pure Apache 2.0)
- All classifiers restored to "License :: OSI Approved :: Apache Software License"
- All SPDX identifiers restored to "Apache-2.0"
- Entity name corrected to "Terrene Foundation" everywhere
- PATENTS file copied to all 3 sub-packages (dataflow, kaizen, nexus)
- MANIFEST.in files updated to include PATENTS in all 3 sub-packages
- NOTICE files created for qa_agentic_testing and user_management
- MANIFEST.in files created for qa_agentic_testing and user_management
- license="Apache-2.0" added to qa_agentic_testing and user_management setup.py
- Kaizen CONTRIBUTING.md updated to explicitly name "Apache License, Version 2.0"
- 6-agent red-team review completed; all CRITICAL and HIGH findings resolved

---

## Actions Requiring Your Involvement

### Priority 1: LEGAL COUNSEL (Patent and Trademark)

#### Action 1.1: Patent Assignment Opinion for Foundation Transfer

> **CONTEXT:** With the OCEAN Foundation strategy, patents (PCT/SG2024/050503, P251088SG, and national phase filings) will eventually transfer to the Foundation. Counsel should advise on the mechanics and timing.

**What counsel needs to do**:

1. **Advise on patent assignment** from Terrene Foundation to OCEAN Foundation (once formed)
2. **Validate patent grant language** in Apache 2.0 Section 3 is sufficient for contributor/user protection
3. **Review transfer mechanism** for Singapore, US, and China national phase filings
4. **Confirm defensive patent pledge** language for Foundation use

**Note:** The Kailash Software License v1.0 draft (`06-license-drafts/KAILASH-SOFTWARE-LICENSE-v1.0.md`) is **SUPERSEDED** -- the decision to adopt pure Apache 2.0 eliminates the need for any custom license. Counsel does NOT need to review or finalize the KSL draft.

#### Action 1.2: Trademark Finalization

Trademark counsel is already engaged (confirmed 3 February 2026). Remaining actions:

| Name         | Risk                                | Priority                      | Status          |
| ------------ | ----------------------------------- | ----------------------------- | --------------- |
| **Kailash**  | Core brand -- highest risk          | File immediately (SG, US, CN) | Counsel engaged |
| **DataFlow** | Generic term -- harder to protect   | Evaluate registrability       | Counsel engaged |
| **Nexus**    | Common term -- harder to protect    | Evaluate registrability       | Counsel engaged |
| **Kaizen**   | Established Japanese term -- complex| Evaluate registrability       | Counsel engaged |
| **OCEAN**    | Foundation name -- needed for formation | Evaluate registrability   | Pending         |

#### Action 1.3: Secure Domain Names

Protect against domain squatting for:

- kailash.dev, kailash.ai, kailash.io, kailash.cloud
- kailashsdk.com, kailashsdk.dev
- ocean-foundation (relevant TLDs)

---

### Priority 2: PATENT PORTFOLIO MANAGEMENT (Within 6 Months)

#### Action 2.1: Complete P251088SG Application

**Deadline**: 7 October 2026

**Action**: Instruct Auriga IP to begin preparing the complete application for P251088SG. Key additions recommended by the analysis:

- Add system claims (currently only method claims)
- Strengthen Alice positioning for potential US filing
- Cross-reference PCT/SG2024/050503
- Consider PCT filing from this priority date

#### Action 2.2: Monitor National Phase Prosecution

Once SG, US, and CN national phase entries are filed, monitor for:

- Office actions requiring response
- Third-party oppositions
- Requests for examination (varies by jurisdiction)

---

### Priority 3: COMMUNITY COMMUNICATION (Next 30 Days)

#### Action 3.1: Announce Apache 2.0 Transition

The transition to pure Apache 2.0 is a significant positive event for the community. Announce it:

- **Blog post** explaining the simplification: Kailash is now genuine open source under Apache 2.0
- **GitHub Discussions** thread for community questions
- **Social media** announcement highlighting: no more Additional Terms, full OSI compliance, genuine open source
- **FAQ** addressing: what changed, what it means for existing users, patent protections still in place

**Key messages:**

1. Kailash SDK and all sub-packages are now pure Apache 2.0 -- genuine open source
2. Patent protections remain (PATENTS file, Apache 2.0 Section 3 grant)
3. No restrictions on commercial use, hosting, or modification
4. The OCEAN Foundation will steward the project long-term

#### Action 3.2: Re-Publish PyPI Packages

The classifier fixes, MANIFEST.in additions, and metadata corrections are in the codebase but NOT yet published. On the next release cycle:

- All packages should be re-published to PyPI with corrected metadata
- Verify that LICENSE, NOTICE, and PATENTS files are included in the actual distributed packages
- Classifiers now correctly state "Apache Software License" (truthful)

#### Action 3.3: Update Stakeholder Communication Documents

The documents in `05-stakeholder-communications/` were drafted when the license was "Apache 2.0 with Additional Terms" and referenced a future KSL transition. These need updating:

- Remove references to KSL v1.0 and custom license terms
- Remove SaaS/hosted service restrictions (no longer applicable)
- Update rights tables to reflect pure Apache 2.0 permissions
- Simplify enterprise overview (no dual-license model needed for the SDK)

---

### Priority 4: INTEGRUM COMMERCIAL MODEL (Within 3 Months)

> **NOTE:** Terrene Foundation's commercial model is NOT based on selling SDK licenses. The SDK is open source (Apache 2.0). Terrene Foundation's revenue comes from:
> 1. **enterprise-app** -- proprietary commercial platform built on the open-source stack
> 2. **Client solutions** -- custom implementations and consulting for enterprises

#### Action 4.1: Define enterprise-app Positioning

Decisions needed:

| Decision           | Options                                                  | Impact             |
| ------------------ | -------------------------------------------------------- | ------------------ |
| Pricing structure  | Per-seat, per-deployment, usage-based, flat annual       | Revenue model      |
| Value separation   | What enterprise-app provides beyond the open-source stack    | Market positioning |
| Sales process      | Self-serve, sales-led, or hybrid                         | GTM strategy       |

#### Action 4.2: Client Solutions Framework

Define the consulting/implementation offering:

- Standard engagement models and pricing
- IP ownership for client-specific work
- Support tiers and SLA terms

---

### Priority 5: OCEAN FOUNDATION PREPARATION (Year 2-3)

Foundation formation is not immediate but preparation should begin:

- [ ] Define Foundation governance structure
- [ ] Draft Foundation charter and bylaws
- [ ] Prepare patent assignment documentation
- [ ] Prepare trademark assignment documentation
- [ ] Identify initial board members/directors
- [ ] Budget Foundation operating costs (minimum S$150K/year)

### Foundation Launch Criteria (All must be met)

- [ ] Terrene Foundation revenue >S$500K/year
- [ ] 10+ paying enterprise customers
- [ ] OCEAN Specification v1.0 published
- [ ] Founder can commit S$150K/year minimum

---

## Gaps That Do NOT Need Immediate Action

These were identified by the review but are lower priority:

| Gap                               | Why Lower Priority                                |
| --------------------------------- | ------------------------------------------------- |
| Trade secret policy               | Important but not urgent -- can address in Q3 2026|
| Dependency license audit          | Should be done but won't block anything           |
| Employee IP assignment agreements | Needed for scaling team, not for IP strategy      |
| Investor due diligence packet     | Only needed when fundraising                      |
| Enforcement/litigation strategy   | Only needed when enforcement is contemplated      |
| GDPR/data protection guidance     | Only relevant for enterprise hosted deployments   |
| Competitor patent monitoring      | Ongoing concern, not time-critical                |

---

## Summary: Your Next 5 Steps

| #   | Action                                                                                         | Who                   | Deadline           |
| --- | ---------------------------------------------------------------------------------------------- | --------------------- | ------------------ |
| 1   | **Obtain patent assignment opinion** from counsel for Foundation transfer                      | Founder + Counsel     | Within 60 days     |
| 2   | **Complete P251088SG application** or PCT filing                                               | Auriga IP             | 7 October 2026     |
| 3   | **Announce Apache 2.0 transition** (blog, GitHub, social media)                                | Founder / Dev team    | Within 30 days     |
| 4   | **Re-publish PyPI packages** with corrected metadata and license files                         | Dev team              | Next release cycle |
| 5   | **Finalize trademark registrations** for "Kailash" (and evaluate sub-brands)                   | Trademark counsel     | Within 90 days     |

Everything else follows from these five actions.

---

## OCEAN Foundation Documents

See `07-foundation/` (formerly `06-ocean/`) for the complete OCEAN Foundation strategy:

| Document                                            | Purpose                                |
| --------------------------------------------------- | -------------------------------------- |
| `07-foundation/00-donation-summary.md`              | What Terrene Foundation donates to Foundation    |
| `07-foundation/01-licensing-regime.md`              | Pure Apache 2.0 licensing rationale    |
| `07-foundation/02-patent-transfer.md`               | Patent transfer mechanics              |
| `07-foundation/03-clean-separation.md`              | Separation between Terrene Foundation and Foundation |
| `07-foundation/04-care-framework.md`                | CARE Framework donation                |
| `07-foundation/05-terrene-foundation-benefit.md`              | How Terrene Foundation benefits from the donation |

---

## Document History

| Date              | Change                                                                                       |
| ----------------- | -------------------------------------------------------------------------------------------- |
| 3 February 2026   | Created. Priorities based on independent review of IP strategy implementation.               |
| 3 February 2026   | OCEAN Foundation strategy section added after red-team analysis.                             |
| 7 February 2026   | Major revision: KSL references marked SUPERSEDED. All priorities updated for pure Apache 2.0. faircode.io section removed (no longer relevant). Commercial model updated to reflect enterprise-app focus. |
