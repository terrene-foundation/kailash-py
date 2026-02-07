> **SUPERSEDED — 6 February 2026**
>
> This document was drafted as part of the fair-code/source-available licensing strategy.
> On 6 February 2026, the Board decided to transition to pure Apache 2.0 and donate all
> platform assets to OCEAN Foundation. The Kailash Software License v1.0 was never finalized
> or adopted. See `07-foundation/` and `DECISION-MEMORANDUM.md` for the current strategy.
>
> This document is retained for historical reference only.

# Red-Team Review Summary: Kailash Software License v1.0

**Date:** 3 February 2026

**Reviewers:** 4 independent agents with adversarial perspectives

---

## Executive Summary

The Kailash Software License v1.0 has been red-teamed by four independent agents acting as:

1. **Cloud Provider Strategist** - Seeking loopholes to offer Kailash as a managed service
2. **Patent Circumvention Specialist** - Seeking ways to avoid or undermine the patent grant
3. **Fork-and-Compete Competitor** - Seeking to fork, rebrand, and compete directly
4. **Community Advocate** - Representing developers, enterprises, and OSS community concerns

All critical and high-severity issues identified have been addressed in the current draft (v1.0). The license is now substantially more robust than the initial draft and comparable source-available licenses (ELv2, n8n SUL, BSL).

---

## Issues Identified and Resolved

### CRITICAL Issues (All Resolved)

| Issue                                            | Source                          | Resolution                                                                         |
| ------------------------------------------------ | ------------------------------- | ---------------------------------------------------------------------------------- |
| "Internal use" carve-out too broad               | Cloud Provider, Fork-Compete    | Narrowed to exclude workflow/database/API/AI services (2.1 carve-out)              |
| BYOL/marketplace loophole                        | Cloud Provider                  | Added Section 2.1(e) covering facilitation and marketplace models                  |
| "Substantial set of features" ambiguous          | Cloud Provider                  | Changed to "any of the features or functionality" (2.1)                            |
| Section 2/3 conflict unclear                     | Fork-Compete                    | Added explicit priority clause at start of Section 2                               |
| "Unmodified form" patent scope too narrow        | Patent Circumvention            | Expanded to include "normal configuration, parameterization, and use" (6.5(a))     |
| Minor violations kill patent license             | Patent Circumvention, Community | Decoupled via "material compliance" and Section 2-only permanent termination (6.3) |
| No standalone distribution restriction           | Fork-Compete                    | Added Section 2.2 (Standalone Commercial Distribution Restriction)                 |
| SAF definition easily gamed                      | Fork-Compete, Cloud Provider    | Added presumption language and anti-wrapper clause to SAF definition               |
| Patent termination scope includes "any licensee" | Community                       | Removed - only covers claims against Licensor/contributors about the Software      |
| Non-transferable blocks M&A                      | Community                       | Added automatic M&A transfer provision (10.4)                                      |

### HIGH Issues (All Resolved)

| Issue                                       | Source                               | Resolution                                               |
| ------------------------------------------- | ------------------------------------ | -------------------------------------------------------- |
| 50% Affiliate threshold too high            | Patent Circumvention                 | Lowered to 20% with expanded "control" definition        |
| IPR/admin proceedings not covered           | Patent Circumvention                 | Added comprehensive list in Section 6.2                  |
| No patent validity challenge termination    | Patent Circumvention                 | Added to Section 6.2                                     |
| Shell entity/proxy enforcement              | Patent Circumvention, Cloud Provider | "Initiate" definition covers causing, directing, funding |
| Cure-and-continue with no damages           | Cloud Provider                       | Added damages preservation in 7.3 and 7.8                |
| Corporate restructuring resets violations   | Cloud Provider                       | Added successor/transferee language in 7.4               |
| No audit rights                             | Cloud Provider                       | Added Section 2.5 (Compliance Verification)              |
| No injunctive relief clause                 | Cloud Provider                       | Added Section 7.7                                        |
| No patent assignment covenant               | Patent Circumvention                 | Added Section 6.7                                        |
| Permanent termination too harsh             | Community                            | Added 24-month reinstatement path in 7.4                 |
| Attribution "prominent" undefined           | Fork-Compete                         | Defined with specific examples (5.2)                     |
| No confusing similarity protection          | Fork-Compete                         | Added to Section 5.3                                     |
| Modification appears to void patent         | Community                            | Clarified in 6.5(a) and 6.5(c)                           |
| No indemnification reference                | Community                            | Added Section 10.10 enterprise contact                   |
| "Managed service" ambiguous for consultants | Community                            | Added explicit carve-out in Section 3.3                  |

### MEDIUM Issues (All Resolved)

| Issue                                     | Source               | Resolution                                         |
| ----------------------------------------- | -------------------- | -------------------------------------------------- |
| "Materially similar" vague in 7.4         | Community            | Changed to "willful violation of Section 2"        |
| Third-party proxy usage                   | Cloud Provider       | Added agency prohibition in 2.1                    |
| Singapore exclusive jurisdiction concerns | Community            | Added injunctive relief in any jurisdiction (10.5) |
| Patent/license jurisdictional mismatch    | Patent Circumvention | Addressed via injunctive relief carve-out          |
| Good faith clause absent                  | Community            | Added Section 10.9                                 |

---

## Strengths Identified by Red-Team

The following provisions were praised as strong protections:

1. **Section 3 (Permitted Uses)** - More comprehensive than ELv2 or n8n SUL
2. **Section 3.3 (Consulting carve-out)** - Explicitly permits professional services
3. **Three-part SAF test** - More rigorous than competitors' vague definitions
4. **Section 6.4 (Patent identification)** - Lists specific patent applications
5. **Section 6.7 (Patent assignment covenant)** - Prevents "troll sale" scenario
6. **Section 7.3 (Damages preservation)** - No free pass during violation period
7. **Section 10.4 (M&A transfer)** - Symmetrical with Licensor's rights
8. **Section 10.9 (Good faith)** - Reduces weaponization risk

---

## Items Not Addressed (Strategic Decisions)

The following items were raised but are strategic business decisions, not drafting gaps:

| Item                                      | Source       | Status                                       |
| ----------------------------------------- | ------------ | -------------------------------------------- |
| BSL-style Change Date (conversion to OSS) | Community    | Not adopted - business decision              |
| Alternative to Singapore jurisdiction     | Community    | Singapore retained with injunctive carve-out |
| Weaker copyleft/share-alike requirement   | Fork-Compete | Not adopted - intentional fair-code model    |
| Registration with Fair Source (fair.io)   | Community    | Deferred until license finalized             |

---

## Comparison with Prior Draft

The red-team process resulted in 25+ substantive changes to the license draft:

| Metric                     | Initial Draft | Final v1.0    |
| -------------------------- | ------------- | ------------- |
| CRITICAL vulnerabilities   | 10            | 0             |
| HIGH vulnerabilities       | 14            | 0             |
| MEDIUM vulnerabilities     | 8             | 0             |
| Sections                   | 10            | 11            |
| Word count                 | ~2,500        | ~4,200        |
| Patent provisions          | Basic         | Comprehensive |
| Anti-circumvention clauses | None          | Multiple      |
| Good faith protections     | None          | Section 10.9  |

---

## Conclusion

The Kailash Software License v1.0 is ready for counsel review. The red-team process has:

1. Closed all identified loopholes for cloud provider abuse
2. Strengthened the patent grant and defensive termination provisions
3. Balanced enforcement power with good faith protections for legitimate users
4. Clarified permitted uses to reduce FUD for developers and enterprises
5. Added M&A transferability to address investor concerns

**Recommendation:** Proceed to legal counsel review with the current draft. No further code-level changes required.

---

## Appendix: Full Red-Team Reports

The complete reports from each red-team agent are available at:

- `/private/tmp/claude/.../tasks/aa6e8cc.output` - Cloud Provider Attack
- `/private/tmp/claude/.../tasks/aa10468.output` - Patent Circumvention
- `/private/tmp/claude/.../tasks/a867d8a.output` - Fork-and-Compete
- `/private/tmp/claude/.../tasks/aeceaa1.output` - Community Advocate

These reports total approximately 15,000 words of adversarial analysis.
