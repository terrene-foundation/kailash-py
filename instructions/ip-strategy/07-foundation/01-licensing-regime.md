# Licensing Regime

**Document**: 01 of 05
**Date**: 7 February 2026
**Purpose**: Define the licensing structure for all assets

---

## The Simple Rule

**Everything donated to Foundation is Apache 2.0. Period.**

No fair-code. No source-available. No custom terms. True open source, OSI-approved, business-friendly, community-standard.

---

## Why Apache 2.0

| Criterion | Apache 2.0 |
|-----------|------------|
| **OSI Approved** | Yes |
| **Permissive** | Yes - anyone can use, modify, distribute, commercialize |
| **Patent Grant** | Yes - Section 3 includes explicit patent license |
| **Attribution Required** | Yes - maintain copyright notices |
| **Copyleft** | No - no requirement to open-source derivatives |
| **Business Friendly** | Yes - enterprises can use without legal complexity |
| **Community Standard** | Yes - widely understood, no explanation needed |

### What Apache 2.0 Allows

Anyone can:
- Use the software for any purpose
- Modify the software
- Distribute the software
- Distribute modified versions
- Use commercially
- Sublicense
- Use patents covered by the grant

### What Apache 2.0 Requires

- Maintain copyright notices
- Include copy of license
- State significant changes
- Include NOTICE file if one exists

### What Apache 2.0 Does NOT Do

- Require sharing modifications (no copyleft)
- Restrict commercial use
- Restrict hosting as a service
- Restrict competition

---

## License Assignment

### Foundation Assets (Apache 2.0)

| Asset | License | Status |
|-------|---------|--------|
| Kailash SDK | Apache 2.0 | DONE - Additional Terms removed |
| DataFlow | Apache 2.0 | DONE - Additional Terms removed |
| Nexus | Apache 2.0 | DONE - Additional Terms removed |
| Kaizen | Apache 2.0 | DONE - Pure Apache 2.0 created |
| CARE Framework | Apache 2.0 | DONE - New contribution |

### Terrene Foundation Assets (Proprietary)

| Asset | License | Notes |
|-------|---------|-------|
| enterprise-app | Proprietary | Built on Apache 2.0 stack, application layer proprietary |
| Client Solutions | Proprietary | Custom solutions for clients |

---

## Implementation Checklist

### Remove Additional Terms

- [x] `/LICENSE` - Additional Terms removed
- [x] `/apps/kailash-dataflow/LICENSE` - Additional Terms removed
- [x] `/apps/kailash-nexus/LICENSE` - Additional Terms removed
- [x] `/apps/kailash-kaizen/LICENSE` - Pure Apache 2.0 created

### Fix PyPI Classifiers (DONE)

All `setup.py` and `pyproject.toml` files declare:
```
"License :: OSI Approved :: Apache Software License"
```
This is now accurate — Additional Terms have been removed.

### Update NOTICE Files

NOTICE files should reflect:
- Original copyright: Terrene Foundation
- Current steward: OCEAN Foundation
- License: Apache License 2.0

---

## The Hyperscaler Question

**Q: Won't AWS/Azure/GCP just take the Apache 2.0 code and compete?**

**A: Yes, they can. That's the point.**

The companies that adopted restrictive licenses (Redis, Elastic, MongoDB, HashiCorp) did so because their platform IS their product — they sell managed versions of the platform itself. When AWS competes, it directly cannibalizes their revenue.

**Terrene Foundation does not sell the platform. Terrene Foundation sells enterprise-app and client solutions.** The platform creates the market for the product. If AWS hosts Kailash as a service, that grows the market for Terrene Foundation's solutions — more enterprises using Kailash means more demand for the expertise, implementations, and commercial products that Terrene Foundation provides.

Additionally:
1. **Fair-code didn't stop hyperscalers anyway** - They built alternatives when licenses became restrictive
2. **Terrene Foundation's expertise is the moat** - No one knows the stack better than the team that built it
3. **Foundation backing creates legitimacy** - Political/association support is not replicable
4. **Community goodwill drives adoption** - Genuine open source builds loyalty that restrictive licenses cannot

The trade-off is explicit: We give up licensing protection for a platform we don't sell. We gain credibility, community, and ecosystem for the products we do sell.

---

## Transition Plan

### Immediate (DONE)

1. ~~Remove Additional Terms from all LICENSE files~~ DONE
2. ~~Update PyPI classifiers~~ DONE
3. Announce license simplification to community
4. ~~Update repository documentation~~ DONE

### Upon Foundation Formation

1. Transfer repository ownership to Foundation
2. Transfer patent ownership to Foundation
3. Foundation assumes stewardship
4. Terrene Foundation becomes community contributor

---

_Document created 6 February 2026_
_Updated 7 February 2026 — Marked license transition as complete, updated checklist, corrected PATENTS Section 3 language_
_For transmission to OCEAN Foundation_
