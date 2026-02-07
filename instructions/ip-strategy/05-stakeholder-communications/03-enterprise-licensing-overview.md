# Enterprise Adoption Guide

## Who This Document Is For

This document is for **enterprise customers, procurement teams, and legal departments** evaluating the Kailash SDK for commercial deployment. It explains the licensing model, patent protections, and what enterprises need to know for adoption.

---

## Licensing Model: Pure Apache 2.0

Kailash SDK is licensed under the **Apache License, Version 2.0** — a widely adopted, OSI-approved open-source license. There is no dual licensing, no separate enterprise license, and no additional commercial terms.

### What This Means for Enterprises

| Feature | Status |
| --- | --- |
| Full source code access | Yes |
| Use in commercial applications | Unrestricted |
| Internal use | Unrestricted |
| Create derivative works | Unrestricted |
| Redistribute (modified or unmodified) | Yes, with Apache 2.0 attribution |
| Offer as a managed/hosted service | Unrestricted |
| Standalone commercial redistribution | Unrestricted |
| Patent license grant | Automatic via Apache 2.0 Section 3 |
| Separate enterprise license required | No |
| License fees | None |

### Why Apache 2.0?

Apache 2.0 is one of the most enterprise-friendly open-source licenses available:

- **Well-understood**: Legal departments worldwide are familiar with its terms
- **OSI-approved**: Meets the Open Source Definition
- **Permissive**: No copyleft obligations — you are not required to open-source your product
- **Patent grant**: Built-in patent protection (Section 3)
- **Corporate adoption**: Used by major projects including Kubernetes, TensorFlow, Apache Hadoop, and thousands of others

---

## Patent Portfolio

The Kailash SDK is the subject of a patent portfolio that protects the core technology innovations. These patents are owned by Terrene Foundation and will be transferred to OCEAN Foundation upon its formation.

### Patent 1: Platform Architecture (PCT/SG2024/050503)

- **Scope**: Data fabric layer, composable layer, process orchestrator, output interface
- **Frameworks**: Core SDK, DataFlow, Nexus
- **International Status**: IPRP Chapter II favorable (all 18 claims approved)
- **National Phase**: Filed in Singapore (IPOS) and United States (USPTO); China (CNIPA) under filing
- **Claims**: 18 (9 method + 9 system)

### Patent 2: AI Workflow Orchestration (P251088SG)

- **Scope**: LLM-guided workflow creation, multi-agent orchestration, convergence detection, containerized deployment
- **Frameworks**: Kaizen, Core SDK
- **Status**: Singapore provisional filed; complete application pending
- **Claims**: 11 (1 independent method + 10 dependent)

### Patent Coverage by Framework

| Framework | Patent 1 (Platform) | Patent 2 (AI Orchestration) |
| --- | --- | --- |
| **Core SDK** | Primary | Shared |
| **DataFlow** | Primary | -- |
| **Nexus** | Primary | Shared |
| **Kaizen** | -- | Primary |

### Patent Grant Under Apache 2.0

The Apache 2.0 license (Section 3) provides an automatic patent grant from each Contributor. This grant covers patent claims licensable by the Contributor that are necessarily infringed by their Contribution(s) alone or by combination of their Contribution(s) with the Work to which such Contribution(s) was submitted.

**Important scope clarification**: The Section 3 patent grant does not blanket-license every claim in every patent a Contributor owns. It applies specifically to claims necessarily infringed by the Contribution as combined with the Work. The PATENTS file in the repository lists relevant patent applications for informational purposes but is not a separate patent grant.

**Defensive termination**: If a licensee initiates patent litigation alleging that the Work constitutes patent infringement, patent licenses granted under Section 3 for that Work terminate as of the date such litigation is filed.

---

## Use Case Guidance

### Use Case: Internal Application Development

**License needed**: Apache 2.0 (free, already included)

Your development team uses Kailash to build internal tools, data pipelines, or AI applications. No restrictions apply to internal use.

### Use Case: Commercial Product Built on Kailash

**License needed**: Apache 2.0 (free, already included)

You build a product (e.g., a logistics management system) that uses Kailash as a component. You sell this product to your customers. Fully permitted under Apache 2.0.

### Use Case: Managed/Hosted Service

**License needed**: Apache 2.0 (free, already included)

You offer a hosted service where customers access Kailash's workflow or AI capabilities through your platform (e.g., "workflow-as-a-service"). Fully permitted under Apache 2.0. No additional license required.

### Use Case: System Integrator / Consulting

**License needed**: Apache 2.0 (free, already included)

You use Kailash as part of consulting engagements, building custom solutions for clients. Fully permitted under Apache 2.0.

### Use Case: OEM / Embedding in Hardware

**License needed**: Apache 2.0 (free, already included)

You embed Kailash in a hardware product or appliance. Fully permitted under Apache 2.0, subject to standard attribution requirements.

### Use Case: Redistribution

**License needed**: Apache 2.0 (free, already included)

You redistribute Kailash — modified or unmodified — as part of your product or independently. Fully permitted under Apache 2.0, subject to standard attribution requirements (include LICENSE and NOTICE files, mark modifications).

---

## Compliance Requirements

### For All Users

1. Include the LICENSE and NOTICE files when distributing Kailash (modified or unmodified)
2. Maintain copyright, patent, trademark, and attribution notices
3. State changes if you modify source files (per Apache 2.0 Section 4)
4. Do not use Terrene Foundation's or Kailash's name to imply endorsement (per Apache 2.0 Section 6)

That is the complete set of obligations. There are no reporting requirements, usage fees, or additional terms.

---

## Evaluation and Adoption

### Getting Started

1. **Evaluate**: Install from PyPI (`pip install kailash`). No registration, no approval required.
2. **Prototype**: Build your proof-of-concept. Apache 2.0 applies from day one.
3. **Deploy**: Move to production. No license change, no enterprise license needed.
4. **Scale**: Grow usage as needed. No per-seat, per-instance, or per-deployment fees.

### Information for Procurement

| Item | Details |
| --- | --- |
| Legal entity (current steward) | Terrene Foundation (Singapore) |
| Future steward | OCEAN Foundation (upon formation) |
| Contact | info@terrene.foundation |
| License type | Apache License, Version 2.0 (OSI-approved open source) |
| License classification | Permissive open-source license |
| Patent status | PCT + national phase (SG, US filed; CN under filing) + SG provisional |
| License fees | None |
| Enterprise license required | No |
| Compliance model | Standard Apache 2.0 attribution |

---

## Frequently Asked Questions

### Is Kailash open source?

Yes. Kailash is licensed under Apache 2.0, which is an OSI-approved open-source license. It is genuine open source — not source-available, not fair-code, and not encumbered by additional restrictions.

### Do we need an enterprise license?

No. There is no enterprise license. Apache 2.0 is the only license, and it covers all use cases including commercial products, managed services, redistribution, and embedding.

### Is there a paid support option?

For commercial support, consulting, and solutions built on the Kailash platform, contact info@terrene.foundation. Terrene Foundation offers professional services and its commercial product (enterprise-app) built on the Apache 2.0 stack. These are separate commercial offerings, not license terms.

### What about patent indemnification?

Apache 2.0 Section 3 provides an automatic patent grant for patent claims necessarily infringed by Contributions as combined with the Work. This is the standard protection mechanism used by thousands of Apache 2.0-licensed projects. There is no separate patent indemnification agreement — the license itself provides the grant.

### Can competitors use Kailash?

Yes. Apache 2.0 places no restrictions on who can use the software or for what purpose. This is by design — the platform is open source to grow the ecosystem.

### What about the OCEAN Foundation?

Upon formation, OCEAN Foundation will assume stewardship of the Kailash platform and receive the patent portfolio. The license remains Apache 2.0. The Foundation's role is to steward the platform and train builders — it has no commercial interest.

---

## Document History

- **3 February 2026**: Originally drafted as "Enterprise Licensing Overview" for Apache 2.0 + Additional Terms regime.
- **7 February 2026**: Revised to reflect transition to pure Apache 2.0. Renamed to "Enterprise Adoption Guide" since there is no separate enterprise license.
