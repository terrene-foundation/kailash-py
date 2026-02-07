> **HISTORICAL DOCUMENT**
>
> This background analysis was prepared as part of the IP strategy development process
> (February 2026). On 6 February 2026, the decision was made to adopt pure Apache 2.0
> licensing and donate all platform assets to OCEAN Foundation. See `DECISION-MEMORANDUM.md`
> and `07-foundation/` for the final strategy.

# 02 - Patent Application Summary

## Document Purpose

Summary of the PCT international patent application and its current status.

## Application Details

| Field               | Value                                                                                                 |
| ------------------- | ----------------------------------------------------------------------------------------------------- |
| Application Number  | PCT/SG2024/050503                                                                                     |
| Applicant           | Terrene Foundation                                                                                    |
| Title               | "A System and Method for Development of a Service Application on an Application Development Platform" |
| Priority Date       | 14 August 2023                                                                                        |
| PCT Filing Date     | 8 August 2024                                                                                         |
| Priority Country    | Singapore                                                                                             |
| Attorney            | Auriga IP Pte. Ltd.                                                                                   |
| File Reference      | P2308211PCT                                                                                           |
| ISA                 | Korean Intellectual Property Office (KIPO)                                                            |
| ISA Examiner        | Mr Yang Jeong Rok                                                                                     |
| IPEA Examiner       | KIM, Sung Hee (KIPO)                                                                                  |
| ISA Written Opinion | 2 December 2024                                                                                       |
| Demand Response     | 24 March 2025                                                                                         |
| IPRP Chapter II     | 4 December 2025 — **ALL CLAIMS APPROVED**                                                             |
| Top-up Search       | 3 December 2025 — No additional relevant documents found                                              |

## Examination Status

### Novelty

- **All claims 1-20 found NOVEL by the examiner**
- No novelty objections raised

### Inventive Step

- Examiner raised inventive step objections citing D1 and D2
- D1: Platform architecture for codeless development of enterprise applications (SCM-focused)
- D2: Metadata orchestrator for managing metadata across multiple applications

### Applicant's Response (March 2025)

**Amendments made:**

- Original Claim 2 incorporated into independent Claim 1
- Original Claim 12 incorporated into independent Claim 11
- Claims 2 and 12 deleted; remaining claims renumbered
- Claim 18 (now 16) amended to address Rule 6.1(a) concern

**Key arguments:**

1. D2 only describes a metadata orchestrator for _managing_ metadata integrity and processing, not _transforming_ source metadata to solution metadata into a unified data format
2. D1 describes a composite service layer as a single API dependency, not a data fabric layer with source data extraction from heterogeneous formats
3. Neither D1 nor D2 individually or in combination teach the distinguishing features
4. The technical advantage is the data fabric layer's ability to handle heterogeneous data sources for quicker development and deployment, with scalability and flexibility for evolving data requirements

### The Core Distinguishing Claim

> "A data fabric layer configured to transform source metadata to solution metadata into a unified data format based on the operation request, wherein the source metadata includes source data labels from a plurality of data sources in different formats, and wherein the data fabric layer comprises a source data layer configured to identify and extract source metadata from the plurality of data sources."

### IPRP Chapter II — CONFIRMED FAVORABLE (4 December 2025)

The International Preliminary Report on Patentability (Chapter II) was completed on 4 December 2025 by examiner KIM, Sung Hee at KIPO. The result is unequivocally positive:

**Box No. V — Reasoned Statement:**

| Criterion                             | Claims 1-18 |
| ------------------------------------- | ----------- |
| Novelty (Art. 33(2))                  | **YES**     |
| Inventive Step (Art. 33(3))           | **YES**     |
| Industrial Applicability (Art. 33(4)) | **YES**     |

**Claims 19-20**: Cancelled by amendment (not assessed).

**Examiner's statement**: _"None of the cited documents discloses the features of claim 1 which require: [...] And it is not obvious to a person skilled in the art from the cited documents, when taken individually or in any combination, to arrive at the features of claim 1."_

**Top-up search** (3 December 2025): Conducted under Rule 70.2(c), found **no additional relevant documents** beyond the 5 already cited (D1-D5).

**Prior art considered (all found non-anticipating):**

- D1: US 2021/0311710 A1 — Platform for codeless enterprise applications (SCM)
- D2: US 2023/0359608 A1 — Metadata orchestrator
- D3: CN 116028028 A — Low-code development platform
- D4: WO 2023/039052 A2 — Application development pipeline
- D5: US 2023/0195426 A1 — Data pipeline construction

**Significance**: This is the strongest possible outcome from international examination. All 18 amended claims — covering both the method (claims 1-9) and system (claims 10-18) — have been confirmed as novel, inventive, and industrially applicable. This substantially de-risks the national phase filings.

### CRITICAL: National Phase Deadlines

| Deadline                      | Date                 | Days Remaining (from 3 Feb 2026) |
| ----------------------------- | -------------------- | -------------------------------- |
| **30-month** (standard)       | **14 February 2026** | **11 days**                      |
| 31-month (some jurisdictions) | 14 March 2026        | 39 days                          |

**Calculation**: Priority date (14 August 2023) + 30 months = 14 February 2026.

**IMMEDIATE ACTION REQUIRED**: Auriga IP must be instructed NOW to file national phase entries in Singapore and the United States before the 30-month deadline.

## Patent Architecture (From Drawings)

### FIG. 1 - System Architecture (100)

Multi-tenant system with:

- Companies 101, 102, 103 (each with multiple users on multiple device types)
- Network 110
- Firewall 120
- Application Servers 130 (clustered)
- Database 140

### FIG. 2 - Application Server Detail (130)

- Communication Interface 131
- Processor 132
- Memory 133

### FIG. 3 - Application Development Platform (300) - CORE INVENTION

Two-layer architecture:

**Data Fabric Layer (310):**

- Unified Data Layer (312)
- Source Data Layer (314)

**Composable Layer (320):**

- Configurable Component Layer (322)
- Output Interface (324)
- Process Orchestrator (326)

### FIG. 4 - UI Builder

Visual builder with configurable components: Table, Details, Form, Heading, Button, DatePicker, Toggle, Radio, Image, Text, Link, Input, Select, TextArea, CheckBox, Menu

### FIG. 5 - Applications List

Published applications: MiltBank-HMO (Healthcare), ADAS (Solo, Geotab, Teltonika, G7), Telemetry, eCommerce (Lazada, Shopee, Amazon), Platforms (Axway, Boomi), TMS (Versafleet, HopOn, V3CSV), WMS (SAP, Oracle, Infor), EV (HGV, LGV, VHGV), Incidents (SAP, Jira, GPVs)

### FIG. 6 - Data Fabric Output Mapping

- Passive Metadata (source schema): root > tenant, date, order_list > arrayElement > id, order_sn, order_status
- Active Metadata (solution schema): root > tenant, DATE, orderList > arrayElement > id, orderSN, orderStatus
- Demonstrates field-level mapping with type transformation capabilities

### FIG. 7 - Data Fabric Operations

Visual workflow showing:

- Operations palette: Concatenate, Filter, Split, Expression
- Structure Mapping with node-based visual flow
- Multiple field mappings feeding through Concatenate nodes to Output

### FIG. 8 - API Configuration

API definition: "Get Lazada Orders", POST method, HTTPS, with Active Metadata Mapping, Input Mapping, Output Mapping

### FIG. 9 - Workflow Execution (Logistics Scheduler)

Complex data flow showing:

- Aggregated APIs (source integration)
- Node types: Aggregated API Node, Call Node, Switch Node, Join Node
- Service integration: Get Drivers from HR System, Get Orders from CRM, Get Vehicles from Fleet System
- Processing: Check Location, Filter Suitable Drivers, AI-based Scheduling
- Routing: Sync, Async, Distributed server routing
- Output: Combine cost matrix, Status update, Send to Portal, Send to Driver App

### FIG. 10 - Method Claims (400)

Four-step process:

1. (401) Receiving, by the application development platform, an operation request for execution
2. (402) Invoking a data fabric layer configured to transform source metadata to solution metadata in a unified data format based on the operation request, wherein the source metadata includes source data labels from a plurality of sources in different formats
3. (403) Invoking a composable layer comprising a plurality of configurable components configured to develop the service application based on the operation request by mapping one or more of the solution metadata to one or more of the plurality of configurable components
4. (404) Developing the service application on an output interface by the one or more of the plurality of configurable components interacting through a process orchestrator for executing the operation request

## National Phase Considerations

The PCT application provides a 30/31-month window from the priority date for entering national phases. Key jurisdictions identified for filing are analyzed in the jurisdiction analysis document (02-research/05-jurisdiction-analysis.md).

## Source Documents

- Letter Accompanying Demand, March 2025 (Auriga IP to KIPO)
- Complete Application Drawings, 2024-08-07 (10 figures)
