# Using Kailash: Your Rights and Obligations

## Who This Document Is For

This document is for **developers, teams, and organizations** who use the Kailash SDK (including DataFlow, Nexus, and Kaizen) in their projects. It explains, in plain language, what you can do, what obligations apply, and what protections are in place.

---

## The License at a Glance

Kailash SDK is licensed under the **Apache License, Version 2.0** — a widely used, OSI-approved open-source license. This is genuine open source, not source-available, not fair-code, and not encumbered by additional terms.

### What You CAN Do

| Use Case | Permitted? | Notes |
| --- | --- | --- |
| Use Kailash in your commercial application | Yes | No restrictions on commercial use |
| Use Kailash internally within your organization | Yes | No restrictions on internal use |
| Create derivative works | Yes | Modify freely for any purpose |
| Integrate Kailash as a component of a larger system | Yes | Use it as part of your architecture |
| Provide services that use Kailash (SaaS, consulting, etc.) | Yes | Including managed/hosted services |
| Redistribute Kailash, modified or unmodified | Yes | Subject to Apache 2.0 attribution requirements |
| Use Kailash for education and research | Yes | Academic and learning use is unrestricted |
| Read, study, and learn from the source code | Yes | Full source access |
| Fork and modify for your own use or distribution | Yes | Modify freely for any purpose |
| Offer Kailash as a managed service | Yes | No managed service restriction |

### Your Obligations Under Apache 2.0

| Obligation | Details |
| --- | --- |
| Include the LICENSE and NOTICE files when distributing | Standard Apache 2.0 requirement |
| State changes if you modify the source files | Mark modified files per Section 4 |
| Retain all copyright, patent, trademark, and attribution notices | Do not strip existing notices |
| Do not use "Kailash" or Terrene Foundation trademarks to imply endorsement | Standard trademark limitation |

### The Key Point

Apache 2.0 is a **permissive** license. You can use, modify, distribute, and commercialize Kailash in any way you choose, provided you comply with the attribution requirements above. There are no restrictions on standalone redistribution, managed service offerings, or commercial use of any kind.

**Example — Permitted**: You build an inventory management system using Kailash's workflow engine and DataFlow for database operations. You sell this system to your customers. Fully permitted.

**Example — Also Permitted**: You take the Kailash SDK, modify it, and offer it as a hosted workflow-as-a-service. Fully permitted, provided you comply with Apache 2.0 attribution requirements.

---

## Patent Protection

The technology in Kailash SDK is the subject of patent applications owned by Terrene Foundation (to be transferred to OCEAN Foundation upon its formation):

### Patent 1: Platform Architecture

- **Application**: PCT/SG2024/050503
- **Title**: "A System and Method for Development of a Service Application on an Application Development Platform"
- **Covers**: The core platform architecture including the data fabric layer, composable layer, process orchestrator, and output interface (implemented as Core SDK, DataFlow, and Nexus)
- **Status**: IPRP Chapter II favorable (all 18 claims approved); national phase filed in Singapore and the United States; China under filing

### Patent 2: AI Workflow Orchestration

- **Application**: P251088SG (Singapore provisional)
- **Title**: "Method and System for Orchestrating Artificial Intelligence Workflow"
- **Covers**: LLM-guided workflow creation, multi-agent orchestration, iterative workflow execution with convergence detection, containerized deployment (implemented as Kaizen)
- **Status**: Provisional filed; complete application pending

### What the Patents Mean for You

**Apache 2.0 Section 3 provides an automatic patent grant.** Under Section 3, each Contributor grants you a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable patent license to make, have made, use, offer to sell, sell, import, and otherwise transfer the Work. This grant applies to patent claims licensable by the Contributor that are necessarily infringed by their Contribution(s) alone or by combination of their Contribution(s) with the Work to which such Contribution(s) was submitted.

**Important scope note**: The Apache 2.0 patent grant is not a blanket license to every claim in every patent the Contributor owns. It covers only those claims necessarily infringed by the Contribution as combined with the Work. The PATENTS file in the repository is informational — it lists relevant patent applications for transparency, but is not a separate patent grant.

**Defensive termination**: Under Apache 2.0 Section 3, if you institute patent litigation alleging that the Work constitutes patent infringement, then any patent licenses granted to you under the License for that Work terminate as of the date such litigation is filed.

---

## Attribution Requirements

When distributing Kailash (modified or unmodified), you must:

1. Include a copy of the Apache 2.0 LICENSE file
2. Include the NOTICE file
3. State any changes you made to the source files
4. Not use Terrene Foundation's or Kailash's name to imply endorsement

In practice, this means keeping the LICENSE and NOTICE files in your distribution, and noting modifications if you have changed the source code.

---

## Frequently Asked Questions

### Can I use Kailash in a closed-source product?

Yes. Apache 2.0 does not require you to open-source your product. You must include the LICENSE and NOTICE files when distributing, but your application code remains yours under whatever terms you choose.

### Can I use Kailash to build a competing workflow platform?

Yes. There are no restrictions on competitive use. You can build any product using Kailash, including a competing platform. Apache 2.0 is a permissive license with no field-of-use restrictions.

### Can I offer Kailash as a hosted/managed service?

Yes. There are no managed service restrictions. You may offer Kailash's functionality as a service without any additional license or agreement.

### Does the patent affect my ability to use the SDK?

The Apache 2.0 patent grant (Section 3) covers patent claims necessarily infringed by the Contributions as combined with the Work. As long as you do not initiate patent litigation against the Work, your patent license remains in effect.

### Can I contribute to Kailash?

Yes. See the CONTRIBUTING.md file for guidelines. Contributors retain copyright of their contributions, which are licensed under the same Apache 2.0 terms as the project.

### What happens if the license changes in the future?

Code you received under Apache 2.0 remains licensed to you under Apache 2.0 in perpetuity. Future versions could theoretically use a different license, but that would not affect your rights to code already released under Apache 2.0.

### Is there a separate enterprise or commercial license?

No. There is no dual licensing, no enterprise license tier, and no separate commercial license. Apache 2.0 is the only license, and it applies to everyone equally.

---

## Summary

| Aspect | Status |
| --- | --- |
| License | Apache License 2.0 (OSI-approved open source) |
| Source code | Freely available |
| Commercial use | Unrestricted |
| Managed service use | Unrestricted |
| Internal use | Unrestricted |
| Redistribution | Permitted (with Apache 2.0 attribution) |
| Patent coverage | Automatic grant via Apache 2.0 Section 3 |
| Enterprise license | None needed — Apache 2.0 covers all use cases |

For complete legal terms, see the [LICENSE](../../LICENSE) and [PATENTS](../../PATENTS) files. For questions, contact info@terrene.foundation.

---

## Document History

- **3 February 2026**: Originally drafted for Apache 2.0 + Additional Terms regime.
- **7 February 2026**: Revised to reflect transition to pure Apache 2.0.
