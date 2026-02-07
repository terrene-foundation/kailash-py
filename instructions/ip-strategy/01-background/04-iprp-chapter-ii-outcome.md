> **HISTORICAL DOCUMENT**
>
> This background analysis was prepared as part of the IP strategy development process
> (February 2026). On 6 February 2026, the decision was made to adopt pure Apache 2.0
> licensing and donate all platform assets to OCEAN Foundation. See `DECISION-MEMORANDUM.md`
> and `07-foundation/` for the final strategy.

# 04 - IPRP Chapter II Outcome

## Document Purpose

Record of the International Preliminary Report on Patentability (Chapter II) for PCT/SG2024/050503, received 4 December 2025.

## Summary

The IPRP Chapter II was completed with a **fully favorable outcome**. All 18 amended claims were found to satisfy all three patentability criteria. This is the strongest possible result from the international phase.

## Key Details

| Field               | Value                                      |
| ------------------- | ------------------------------------------ |
| Application         | PCT/SG2024/050503                          |
| Applicant           | Terrene Foundation                         |
| IPEA                | Korean Intellectual Property Office (KIPO) |
| Examiner            | KIM, Sung Hee                              |
| Date of Completion  | 4 December 2025                            |
| Date of Transmittal | 4 December 2025                            |
| Top-up Search Date  | 3 December 2025                            |
| Claims Assessed     | 1-18 (claims 19-20 cancelled by amendment) |

## Patentability Assessment (Box No. V)

| Criterion                                    | Claims | Result  |
| -------------------------------------------- | ------ | ------- |
| Novelty (Article 33(2) PCT)                  | 1-18   | **YES** |
| Inventive Step (Article 33(3) PCT)           | 1-18   | **YES** |
| Industrial Applicability (Article 33(4) PCT) | 1-18   | **YES** |

## Claim Structure (18 claims, as amended)

### Method Claims (1-9)

- **Claim 1** (Independent): Computer-implemented method for developing a service application on an application development platform, comprising:
  - Receiving an operation request for execution
  - Invoking a data fabric layer configured to transform source metadata to solution metadata into a unified data format, wherein the source metadata includes source data labels from a plurality of data sources in different formats, and wherein the data fabric layer comprises a source data layer configured to identify and extract source metadata from the plurality of data sources
  - Invoking a composable layer comprising configurable components to develop the service application by mapping solution metadata to configurable components
  - Developing the service application on an output interface by the configurable components interacting through a process orchestrator

- **Claims 2-9** (Dependent on Claim 1): Dependent method claims covering specific features of the architecture

### System Claims (10-18)

- **Claim 10** (Independent): Application development platform (system) mirroring the method of Claim 1
- **Claims 11-18** (Dependent on Claim 10): Dependent system claims

## Examiner's Reasoning

The examiner stated:

> "None of the cited documents discloses the features of claim 1 which require: [the data fabric layer limitations including source data layer extraction from heterogeneous formats]. And it is not obvious to a person skilled in the art from the cited documents, when taken individually or in any combination, to arrive at the features of claim 1."

The critical distinguishing feature was the incorporation of the source data layer (from original dependent claim 2 into independent claim 1), which describes the extraction of source metadata from heterogeneous data sources — a feature not found in any of the prior art.

## Top-up Search (Rule 70.2(c))

A top-up search was conducted on 3 December 2025. **No additional relevant documents were found** beyond the 5 documents already cited in the Written Opinion.

## Prior Art Considered

All five documents were found **non-anticipating**:

| Ref | Document           | Relevance                                                                                                                                                                                                                     |
| --- | ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | US 2021/0311710 A1 | Platform architecture for codeless enterprise applications (SCM-focused). Describes a composite service layer as a single API dependency, but NOT a data fabric layer with source data extraction from heterogeneous formats. |
| D2  | US 2023/0359608 A1 | Metadata orchestrator for managing metadata across applications. Describes metadata management/integrity but NOT transformation of source metadata to solution metadata into a unified data format.                           |
| D3  | CN 116028028 A     | Low-code development platform.                                                                                                                                                                                                |
| D4  | WO 2023/039052 A2  | Application development pipeline.                                                                                                                                                                                             |
| D5  | US 2023/0195426 A1 | Data pipeline construction.                                                                                                                                                                                                   |

## IPC Classifications

- G06F 8/38 (primary)
- G06F 8/36
- G06F 8/35
- G06F 8/33
- G06Q 10/10

## Significance for National Phase

The favorable IPRP provides several strategic advantages:

1. **De-risked prosecution**: National patent offices (IPOS, USPTO, CNIPA) will have access to the IPRP and examiner's positive assessment. While not binding, it is persuasive.

2. **Singapore (IPOS)**: Singapore has a modified substantive examination track. The favorable IPRP can be relied upon to accelerate grant. Singapore is also part of the ASPEC (ASEAN Patent Examination Cooperation) network, which allows results to be shared across ASEAN member states.

3. **United States (USPTO)**: The IPRP findings support the case for patentability. The Alice Corp v. CLS Bank risk remains (US-specific), but the detailed technical claim language (data fabric layer, source data extraction, metadata transformation) is well-positioned for surviving Alice scrutiny. The examiner's finding that the claims describe a specific technical architecture (not an abstract idea) is helpful for the Alice analysis.

4. **China (CNIPA)**: The IPRP is given significant weight. The technical nature of the claims aligns well with Chinese patent practice, which is generally more receptive to software patent claims than the US.

## National Phase Deadlines

| Jurisdiction      | Deadline             | Calculation                                         | Status    |
| ----------------- | -------------------- | --------------------------------------------------- | --------- |
| **Singapore**     | **14 February 2026** | Priority (14 Aug 2023) + 30 months                  | **FILED** |
| **United States** | **14 February 2026** | Priority (14 Aug 2023) + 30 months (35 U.S.C. §371) | **FILED** |
| **China**         | **14 March 2026**    | Priority (14 Aug 2023) + 31 months (Rule 100.1)     | Pending   |

**Update (3 February 2026)**: Singapore and United States national phase entries have been filed. China filing remains pending (deadline: 14 March 2026).

## Source Documents

- IPRP Chapter II with annexes (dated 4 December 2025)
- Notification of transmittal of IPRP Chapter II (dated 4 December 2025)
