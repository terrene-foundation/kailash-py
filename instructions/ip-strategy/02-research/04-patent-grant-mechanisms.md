> **HISTORICAL DOCUMENT — RESEARCH**
>
> This research was conducted as part of the IP strategy development process (February 2026).
> The research informed the final decision to adopt pure Apache 2.0 rather than a custom
> license. On 6 February 2026, the Board decided on unconditional Apache 2.0 donation to
> OCEAN Foundation. See `DECISION-MEMORANDUM.md` and `07-foundation/` for the final strategy.

# 04 - Patent Grant Mechanisms in Software Licenses

## Document Purpose

Research on how patent grants work in software licenses, with focus on defensive patent strategies for fair-code/source-available projects.

## What Is a Patent Grant in a License?

A patent grant is a clause in a software license where the patent holder explicitly grants users the right to practice (use, make, sell) the patented invention, but only within the scope of the licensed software. It bridges the gap between copyright (which protects code) and patents (which protect methods/processes).

Without a patent grant, a user could legally have a copyright license to use the code but still infringe a patent covering the method the code implements.

## Patent Grant Models

### 1. Apache License 2.0 - Express Grant with Defensive Termination

**The Grant (Section 3):**

> Each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable [...] patent license to make, have made, use, offer to sell, sell, import, and otherwise transfer the Work, where such license applies only to those patent claims licensable by such Contributor that are necessarily infringed by their Contribution(s) alone or by combination of their Contribution(s) with the Work to which such Contribution(s) was submitted.

**The Termination:**

> If You institute patent litigation against any entity [...] alleging that the Work or a Contribution incorporated within the Work constitutes direct or contributory patent infringement, then any patent licenses granted to You under this License for that Work shall terminate as of the date such litigation is filed.

**Key Properties:**

- Grant is per-contributor (only covers their own patents)
- Scope limited to patents necessarily infringed by their contributions
- Defensive: terminates if licensee sues over the Work
- Does NOT terminate copyright license, only patent license
- Does NOT cover patents held by non-contributors

### 2. GPLv3 - Broad Grant with Anti-Tivoization

**The Grant (Section 11):**

> Each contributor grants you a non-exclusive, worldwide, royalty-free patent license under the contributor's essential patent claims, to make, use, sell, offer for sale, import and otherwise run, modify and propagate the contents of its contributor version.

**Additional protections:**

- Anti-discrimination: If you distribute under patent license, must extend to all
- Anti-Tivoization: Cannot use patents to restrict hardware installation

### 3. Custom Defensive Patent Pledge

Used by companies like Google (Go), Facebook (React - formerly), and Red Hat:

**Pattern:**

> [Company] hereby grants to each person who uses, copies, or distributes the Software a perpetual, worldwide, non-exclusive, royalty-free patent license to [Company]'s patents that are necessarily infringed by the Software. This license is conditioned upon compliance with the terms of the Software License and terminates automatically if you assert a patent infringement claim against [Company] or any contributor to the Software.

## The "Poison Pill" Strategy

### How It Works

1. Patent holder includes a patent grant in the software license
2. Grant explicitly terminates if the licensee files patent litigation against the licensor or community
3. This creates a mutual-assured-destruction dynamic

### Why It's Effective

- **Against competitors**: A competitor using the SDK can't sue the licensor for patent infringement without losing their own right to use the patented technology
- **Against patent trolls**: Limited effectiveness (trolls don't use the software, so they have no license to lose)
- **For community protection**: Prevents community members from suing each other

### Limitations

- Only protects against licensees (people who actually use the software)
- Does NOT protect against entities that don't use the software
- Does NOT prevent someone from independently developing and patenting a similar approach
- Scope is limited to patents "necessarily infringed" by the software

## Patent Grant + Fair-Code License

### The Integration Challenge

Most fair-code licenses (SUL, ELv2, BSL) do NOT include patent grant clauses. This is a gap because:

1. Fair-code licenses are not OSI-approved, so they don't inherit OSI community norms about patents
2. Users of fair-code software have no implicit patent safety net
3. The licensor could theoretically enforce patents against their own users

### The Solution: Supplementary Patent Grant

Add a separate patent grant section to the fair-code license. This can be done as:

**Option A: Embedded in license**
Include the patent grant as a section within the license document itself.

**Option B: Separate patent pledge**
Issue a standalone "Patent Pledge" document that references the license.

**Option C: PATENTS file**
Include a PATENTS file in the repository (similar to what Google does with Go).

### Recommended Structure for Kailash

```
PATENT GRANT

1. Grant of Patent License.
Subject to the terms and conditions of this License, Terrene Foundation
("Licensor") hereby grants to each recipient of the Software ("You") a
perpetual, worldwide, non-exclusive, royalty-free, irrevocable patent
license to make, have made, use, offer to sell, sell, import, and
otherwise transfer the Software, where such license applies only to
those patent claims owned or controlled by the Licensor that are
necessarily infringed by the Software as distributed by the Licensor.

2. Defensive Termination.
If You (including your affiliates) initiate patent litigation (including
a cross-claim or counterclaim in a lawsuit) against the Licensor, any
Contributor to the Software, or any other licensee of the Software,
alleging that the Software or any portion thereof constitutes direct or
contributory patent infringement, then:
(a) any patent licenses granted to You under Section 1 shall terminate
    as of the date such litigation is filed; and
(b) your rights under this License to use, copy, modify, and distribute
    the Software shall also terminate as of the date such litigation
    is filed.

3. Scope.
This patent grant applies only to patent claims that are necessarily
infringed by the Software as provided by the Licensor, and does not
extend to:
(a) modifications made by You or third parties;
(b) combinations of the Software with other software or hardware
    not provided by the Licensor; or
(c) patent claims that are infringed only by such modifications
    or combinations.

4. Patent Identification.
The Licensor's patents covered by this grant include, but are not
limited to:
- PCT/SG2024/050503 and all national phase entries thereof
- Any continuation, divisional, or related applications
```

## How This Interacts with the Commercial License

| License Tier                | Patent Grant                    | Patent Indemnification              |
| --------------------------- | ------------------------------- | ----------------------------------- |
| **Fair-code (community)**   | Yes, with defensive termination | No                                  |
| **Enterprise (commercial)** | Yes, unconditional              | Yes (licensor indemnifies customer) |

The commercial license should include **patent indemnification** - a promise that the licensor will defend the customer if a third party sues them for patent infringement related to the software. This is a standard enterprise license feature and is significantly more valuable than a mere patent grant.

**This is where the patent dramatically increases commercial license value.**

Without a patent: Enterprise license = support + features
With a patent: Enterprise license = support + features + IP protection + indemnification

## Precedents

| Company                    | Approach                 | Patent Referenced         |
| -------------------------- | ------------------------ | ------------------------- |
| Google (Go)                | PATENTS file in repo     | Google's patent portfolio |
| Facebook (React, pre-2017) | BSD + PATENTS file       | Facebook's patents        |
| Red Hat                    | Patent Promise           | Red Hat's portfolio       |
| Apache Foundation          | License Section 3        | Contributor patents       |
| Elastic                    | No patent clause in ELv2 | N/A                       |
| n8n                        | No patent clause in SUL  | N/A                       |

Note: Neither Elastic nor n8n include patent grants because they don't have patents on their core architectures. **Kailash having a patent is a differentiator** - the patent grant clause adds value that competitors cannot offer.

## Sources

- [Patents and Open Source - OSI](https://opensource.org/blog/patents-and-open-source-understanding-the-risks-and-available-solutions-2)
- [Apache License 2.0 Patent Handling](https://milvus.io/ai-quick-reference/how-does-the-apache-license-20-handle-patents)
- [Understanding Patent Provisions in Open Source Licenses](https://patentpc.com/blog/understanding-the-patent-provisions-in-popular-open-source-licenses)
- [Apache 2.0 Patent License Explained](https://opensource.com/article/18/2/apache-2-patent-license)
- [Google Open Source Patent Pledge](https://google.github.io/opencasebook/patents/)
