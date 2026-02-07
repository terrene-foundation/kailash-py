> **HISTORICAL DOCUMENT — RESEARCH**
>
> This research was conducted as part of the IP strategy development process (February 2026).
> The research informed the final decision to adopt pure Apache 2.0 rather than a custom
> license. On 6 February 2026, the Board decided on unconditional Apache 2.0 donation to
> OCEAN Foundation. See `DECISION-MEMORANDUM.md` and `07-foundation/` for the final strategy.

# 01 - Fair-Code Definition and Principles

## Document Purpose

Comprehensive research on the fair-code software model, its principles, compatible licenses, and ecosystem.

## What Is Fair-Code?

Fair-code is **not a software license**. It is a **software model** that describes a set of principles for how software should be developed, distributed, and commercialized. The model was created to address the tension between open-source ideals and commercial sustainability.

**Source**: [faircode.io](https://faircode.io/)

## The Four Guiding Principles

### 1. Free and Sustainable

Enables developers to profit from their work while respecting freedom principles. Creates economic viability for authors across all backgrounds.

### 2. Open but Pragmatic

Promotes open specifications, discussion, and collaboration as beneficial practices for software improvement and community growth.

### 3. Community Meets Prosperity

Authors retain exclusive commercialization rights, ensuring long-term profitability while allowing companies to negotiate business relationships with creators.

### 4. Meritocratic and Fair

Recognizes software authors and contributors deserve respect and influence proportional to their contributions.

## The Four Qualifying Criteria

For software to qualify as fair-code, it must:

1. **Have its source code openly available** - The code must be publicly accessible
2. **Be generally free to use and distributable by anybody** - Free for most use cases
3. **Be extensible by anybody in public and private communities** - Open to modification
4. **Be commercially restricted by its authors** - Authors retain commercial control

## Compatible Licenses

The following licenses are recognized by faircode.io as fair-code compatible:

| License                               | Key Restriction                                    | Notable Users                   |
| ------------------------------------- | -------------------------------------------------- | ------------------------------- |
| **Business Source License (BSL)**     | Time-delayed open source conversion                | MariaDB, HashiCorp, CockroachDB |
| **Commons Clause**                    | Prevents selling the software itself               | Added to various OSI licenses   |
| **Confluent Community License**       | Restricts competing SaaS offerings                 | Confluent (Kafka)               |
| **Elastic License 2.0 (ELv2)**        | Prevents managed service offerings                 | Elastic (Elasticsearch, Kibana) |
| **Server Side Public License (SSPL)** | Requires SaaS providers to open-source their stack | MongoDB                         |
| **Sustainable Use License (SUL)**     | Limits to internal/personal/non-commercial use     | n8n                             |

## Why Fair-Code Emerged

### The "AWS Problem"

Large cloud providers (particularly AWS) were taking open-source software, wrapping it in managed services, and profiting without contributing back to the original creators:

- **MongoDB**: Amazon created DocumentDB based on MongoDB's code, offered it as a service
- **Elasticsearch**: AWS created OpenSearch after Elastic changed its license
- **Redis**: AWS created ElastiCache using Redis
- **Kafka**: AWS created Amazon MSK using Confluent's work

### The Response

Open-source companies realized that pure permissive licenses (MIT, Apache 2.0) gave away their competitive advantage. They needed a model that:

- Kept source code open (for community, trust, security)
- Prevented direct commercial exploitation without contribution
- Allowed a sustainable business model around the software

## Fair-Code vs. Open Source

| Aspect                 | Open Source (OSI)    | Fair-Code                         |
| ---------------------- | -------------------- | --------------------------------- |
| Source code available  | Yes                  | Yes                               |
| Free to use            | Yes, for any purpose | Yes, with commercial restrictions |
| Modifiable             | Yes                  | Yes                               |
| Redistributable        | Yes, for any purpose | Yes, with restrictions            |
| Commercial use         | Unrestricted         | Restricted by authors             |
| OSI approved           | Yes                  | No                                |
| Community contribution | Yes                  | Yes                               |
| Sustainable revenue    | Difficult            | Built-in                          |

### Key Difference

OSI-approved open-source licenses cannot discriminate against fields of endeavor (OSD Clause 6). Fair-code licenses explicitly do - they restrict commercial exploitation while permitting all other uses.

## Criticisms of Fair-Code

1. **Not open source**: Purists argue it shouldn't be called anything close to "open source"
2. **Legal grey zones**: Custom licenses lack judicial precedent
3. **Vendor control**: Projects are often controlled by a single company
4. **License change risk**: The controlling company can change terms
5. **Community confusion**: Users may not understand the restrictions

## Key Figures

- **Jan Oberhauser** (n8n CEO): Key figure behind the fair-code initiative
- **faircode.io**: The central registry and definition source
- **Elastic, MongoDB, HashiCorp**: Major companies that moved from open source to fair-code-adjacent models

## Relevance to Kailash

Kailash's current license (Apache 2.0 + Additional Terms) is **philosophically aligned** with fair-code but **not formally recognized** because:

1. The specific license is not on faircode.io's compatible list
2. The terms are custom and untested
3. The "Apache 2.0" branding creates confusion with OSI open source

## Sources

- [faircode.io](https://faircode.io/)
- [What Is Fair Code? - Open Pioneers](https://www.openpioneers.com/p/what-is-fair-code)
- [Fair Code: A Balanced Approach - DEV Community](https://dev.to/ashucommits/fair-code-a-balanced-approach-to-open-source-and-beyond-b2k)
- [Fair Code vs Open Source - FOSS Post](https://fosspost.org/fair-code-open-source)
