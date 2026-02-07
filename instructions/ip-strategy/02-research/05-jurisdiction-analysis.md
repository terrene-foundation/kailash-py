> **HISTORICAL DOCUMENT — RESEARCH**
>
> This research was conducted as part of the IP strategy development process (February 2026).
> The research informed the final decision to adopt pure Apache 2.0 rather than a custom
> license. On 6 February 2026, the Board decided on unconditional Apache 2.0 donation to
> OCEAN Foundation. See `DECISION-MEMORANDUM.md` and `07-foundation/` for the final strategy.

# 05 - Patent Filing Jurisdiction Analysis

## Document Purpose

Analysis of national phase filing jurisdictions for PCT/SG2024/050503, considering Kailash SDK's market, the fair-code model, and commercial strategy.

## Patent Classification

The invention is a **Computer Implemented Invention (CII)** involving:

- Transformation of source metadata to solution metadata
- Data fabric layer architecture
- Composable application development platform
- Process orchestration

This classification matters because software patent eligibility varies significantly by jurisdiction.

## Jurisdiction Analysis

### TIER 1: MUST FILE

#### Singapore (Home Base)

| Factor                       | Assessment                                        |
| ---------------------------- | ------------------------------------------------- |
| **Verdict**                  | FILE                                              |
| **Cost**                     | Low/Medium (~SGD 5,000-15,000)                    |
| **Software patent friendly** | Yes (follows UK approach, technical effect test)  |
| **Grant assistance**         | Enterprise Singapore grants may cover costs       |
| **Strategic value**          | Home jurisdiction, reputation, ASPEC acceleration |
| **Kailash relevance**        | Terrene Foundation is incorporated here                     |

**Notes:**

- Singapore uses the "technical effect" test for CIIs
- The metadata transformation claim has clear technical effect (data format unification)
- Can use Singapore grant to accelerate examination in other ASPEC countries
- ASPEC (ASEAN Patent Examination Cooperation) covers 10 ASEAN countries

#### United States

| Factor                       | Assessment                                            |
| ---------------------------- | ----------------------------------------------------- |
| **Verdict**                  | FILE (Critical)                                       |
| **Cost**                     | High (~USD 10,000-20,000+ over lifetime)              |
| **Software patent friendly** | Complex (Alice Corp v. CLS Bank)                      |
| **Strategic value**          | #1 market for software exits and VC funding           |
| **Kailash relevance**        | Primary market for SDK adoption, enterprise customers |

**Alice Corp Analysis for Kailash's Claims:**

The USPTO applies a two-step test (Alice/Mayo):

**Step 1**: Is the claim directed to an abstract idea?

- Risk: "Transforming data from one format to another" could be characterized as abstract
- Mitigation: The claims specify a particular technical architecture (data fabric layer, source data layer, composable layer, process orchestrator) - this is a specific technical implementation, not a general concept

**Step 2**: If abstract, does it contain an "inventive concept" that transforms it?

- The IPRP's finding of novelty strongly supports this
- The specific architecture (FIG. 3) with defined layers and their interactions is a concrete technical solution
- The examiner's concession that the data fabric transformation is not found in prior art supports inventive concept

**Recommendation:** File with claims emphasizing the technical architecture and specific metadata transformation process, not the business result. Auriga IP should work with a US patent attorney experienced in Alice rejections for CII claims.

### TIER 2: STRONG CONSIDERATION

#### China

| Factor                       | Assessment                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------ |
| **Verdict**                  | Strong consideration                                                           |
| **Cost**                     | Medium (~USD 5,000-10,000)                                                     |
| **Software patent friendly** | Yes (increasingly, if solving "technical problem")                             |
| **Strategic value**          | World's largest manufacturing and logistics hub                                |
| **Kailash relevance**        | FIG. 5 shows Lazada, Shopee (SE Asia/China e-commerce), supply chain use cases |

**Notes:**

- China's patent law is favorable to CIIs that solve a "technical problem"
- Kailash's metadata transformation between heterogeneous data formats is a clear technical problem
- The logistics/supply chain applications (TMS, WMS, eCommerce) shown in FIG. 5 align with China's manufacturing economy
- Having a Chinese patent prevents Chinese competitors from copying the architecture and blocking Kailash's entry into the Chinese market
- CNIPA examination is generally faster than USPTO

### TIER 3: CONDITIONAL

#### Europe (EPO)

| Factor                       | Assessment                                                    |
| ---------------------------- | ------------------------------------------------------------- |
| **Verdict**                  | Only if targeting major EU enterprise clients                 |
| **Cost**                     | Very high (~EUR 15,000-30,000+ including validation)          |
| **Software patent friendly** | Strict ("technical character" required)                       |
| **Strategic value**          | Large enterprise market (SAP, Siemens, etc.)                  |
| **Kailash relevance**        | FIG. 5 shows SAP integration; depends on EU customer pipeline |

**EPO CII Analysis:**

- EPO requires "further technical effect" beyond just running on a computer
- The metadata transformation between heterogeneous data formats likely qualifies
- However, the EPO is strict and expensive
- Post-grant validation in individual countries (Germany, France, UK, etc.) multiplies costs
- Europe's strong open-source culture may make patent enforcement less necessary (copyright + fair-code license may suffice)

**Recommendation:** Defer unless there are specific EU enterprise deals in the pipeline where patent protection would be a competitive advantage.

#### Japan

| Factor                       | Assessment                                                  |
| ---------------------------- | ----------------------------------------------------------- |
| **Verdict**                  | Skip unless specific partner/customer                       |
| **Cost**                     | High (translation costs significant)                        |
| **Software patent friendly** | Reasonable                                                  |
| **Strategic value**          | Lower than US/China for Kailash's current market            |
| **Kailash relevance**        | Unless targeting Japanese automotive/robotics supply chains |

### TIER 4: STRATEGIC RESERVE

#### India

| Factor                       | Assessment                                                     |
| ---------------------------- | -------------------------------------------------------------- |
| **Verdict**                  | Monitor, consider later                                        |
| **Cost**                     | Low                                                            |
| **Software patent friendly** | Restrictive (Section 3(k) excludes "computer programs per se") |
| **Strategic value**          | Large developer community, growing enterprise market           |
| **Kailash relevance**        | India's IT services industry is a potential customer base      |

**Notes:**

- India's patent law explicitly excludes "computer programs per se"
- However, CIIs with "technical effect" may be patentable under recent guidelines
- The metadata transformation claim would need careful framing
- Low cost makes it worth considering if the legal landscape improves

## Filing Timeline

PCT national phase deadline is typically 30 months from priority date. Assuming a 2024 priority date:

| Milestone               | Date (Approximate) |
| ----------------------- | ------------------ |
| Priority filing         | 2024               |
| PCT filed               | 2024               |
| ISA Written Opinion     | December 2024      |
| Demand response         | March 2025         |
| IPRP expected           | Mid-2025           |
| National phase deadline | Early-Mid 2026     |

**ACTION REQUIRED:** National phase entries must be initiated before the deadline. SG and US should be filed as soon as favorable IPRP is received.

## Cost Summary

| Jurisdiction          | Estimated Cost (filing + prosecution) | Priority    |
| --------------------- | ------------------------------------- | ----------- |
| Singapore             | SGD 5,000-15,000                      | Must        |
| United States         | USD 10,000-20,000                     | Must        |
| China                 | USD 5,000-10,000                      | Strong      |
| Europe (EPO)          | EUR 15,000-30,000                     | Conditional |
| Japan                 | USD 8,000-15,000                      | Skip        |
| **Total (Tier 1+2)**  | **~USD 25,000-45,000**                |             |
| **Total (All Tiers)** | **~USD 50,000-80,000**                |             |

## Interaction with Fair-Code Strategy

The patent filing strategy should be coordinated with the license transition:

1. **License change should happen BEFORE national phase grants** - This ensures the patent grant clause is in place when patents are granted
2. **Patent numbers should be referenced in the license** - Once national phase applications are filed, reference them in the patent grant section
3. **Enterprise license should include patent indemnification** - This is a key revenue differentiator
4. **Fair-code + patent = unique positioning** - No other fair-code project (n8n, Elastic, MongoDB) has a patent on their core architecture with an embedded patent grant

## Sources

- Legal advice provided to Terrene Foundation (referenced in user's message)
- PCT/SG2024/050503 filing documents
- Alice Corp. v. CLS Bank International, 573 U.S. 208 (2014)
- ASPEC guidelines (ASEAN Patent Examination Cooperation)
