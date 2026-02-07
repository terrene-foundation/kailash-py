# Patent Notice Summary

## Who This Document Is For

This document provides a plain-language summary of the patent applications related to the Kailash SDK. It is intended for **all stakeholders** — developers, contributors, enterprise customers, partners, and the general public.

---

## Patent Portfolio Overview

Terrene Foundation has filed patent applications covering the core technology innovations implemented in the Kailash SDK. Upon formation of the OCEAN Foundation, these patents will be transferred to the Foundation.

| # | Application | Title | Filed | Status |
| --- | --- | --- | --- | --- |
| 1 | PCT/SG2024/050503 | A System and Method for Development of a Service Application on an Application Development Platform | 8 Aug 2024 | National phase: SG and US filed; CN under filing |
| 2 | P251088SG | Method and System for Orchestrating Artificial Intelligence Workflow | 7 Oct 2025 | Provisional filed; complete application pending |

---

## Patent 1: Platform Architecture

### What It Covers

Patent 1 covers the **platform architecture** that enables rapid application development through a two-layer system:

1. **Data Fabric Layer** — A layer that transforms data from multiple sources in different formats into a unified format. In Kailash, this is the DataFlow framework, which takes database schemas from PostgreSQL, MySQL, SQLite, and MongoDB and automatically generates standardized operation nodes.

2. **Composable Layer** — A layer of configurable components that can be assembled into applications. In Kailash, this is the Core SDK's WorkflowBuilder with 110+ nodes, connected through a process orchestrator (the Runtime engine) and deployed through an output interface (Nexus).

### What This Means

The patent covers the specific way Kailash:

- Extracts and normalizes data from heterogeneous sources
- Provides a library of composable, configurable nodes
- Orchestrates these nodes through a runtime engine
- Deploys the result through multiple channels (API, CLI, MCP)

### Examination History

The International Preliminary Report on Patentability (IPRP) under Chapter II was completed on 4 December 2025 by the Korean Intellectual Property Office (KIPO). **All 18 claims were found to be novel, inventive, and industrially applicable.** Five prior art documents were considered; none anticipated the claims.

### Current Status

- **Singapore (IPOS)**: National phase entry filed
- **United States (USPTO)**: National phase entry filed
- **China (CNIPA)**: National phase entry under filing (deadline: 14 March 2026)

---

## Patent 2: AI Workflow Orchestration

### What It Covers

Patent 2 covers the **AI orchestration layer** that enables intelligent workflow creation and execution:

1. **LLM-Guided Workflow Creation** — Using large language models with structured contextual scaffolding to generate workflow components, reducing hallucination through deterministic constraints.

2. **Multi-Agent Orchestration** — A system of software agents that communicate through shared memory, with dynamic role assignment and self-organizing team formation.

3. **Iterative Workflow Engine with Convergence Detection** — Executing workflows in iterative cycles with automatic detection of when results have stabilized (converged), enabling autonomous termination.

4. **Containerized Deployment** — Automatic packaging and deployment of workflows through Docker and Kubernetes.

5. **Smart Server Architecture** — Self-contained execution environments that operate without external AI clients.

### What This Means

The patent covers the specific way Kailash Kaizen:

- Uses LLMs with structured context to create workflows
- Coordinates multiple AI agents with shared memory
- Runs iterative workflows that detect when they are "done"
- Packages everything for production deployment
- Provides autonomous execution without external dependencies

### Current Status

- **Singapore**: Provisional application filed (7 October 2025)
- **Complete application deadline**: 7 October 2026
- **PCT filing decision**: Pending

---

## How the Patents Work Together

```
Patent 1 (Platform Architecture)      Patent 2 (AI Orchestration)
================================      =============================
DataFlow (Data Fabric Layer)          Kaizen (AI Agent Framework)
Core SDK (Composable Layer)     <-->  Core SDK (Iterative Engine)
Nexus (Output Interface)              Nexus (Containerized Deploy)
```

Patent 1 covers **what the platform does** — how it transforms data and orchestrates components. Patent 2 covers **how AI drives the platform** — how agents create, execute, and deploy workflows autonomously.

Together, they describe the technology across all four Kailash frameworks.

---

## Your Rights Under the Patents

### The Apache 2.0 Patent Grant (Section 3)

The Kailash SDK is licensed under the Apache License, Version 2.0. Section 3 of Apache 2.0 provides an automatic patent grant from each Contributor:

> Each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable (except as stated in this section) patent license to make, have made, use, offer to sell, sell, import, and otherwise transfer the Work, where such license applies only to those patent claims licensable by such Contributor that are necessarily infringed by their Contribution(s) alone or by combination of their Contribution(s) with the Work to which such Contribution(s) was submitted.

### What This Means in Practice

**Scope of the grant**: The patent grant covers claims that are necessarily infringed by the Contribution as combined with the Work. It does **not** blanket-license all claims in every patent the Contributor owns. The PATENTS file in the repository lists relevant patent applications for informational transparency, but it is not a separate patent grant — the grant comes from Apache 2.0 Section 3 itself.

**For users**: If you use Kailash under the Apache 2.0 license, you receive the Section 3 patent grant automatically. No separate patent license is needed. No enterprise license is required for patent coverage.

**For contributors**: Contributors acknowledge the existence of the patent applications. Their contributions may implement aspects of the patented technology. Contributors' patent rights are the same as all other users' — governed by Apache 2.0 Section 3.

**Defensive termination**: If you initiate patent litigation alleging that the Work constitutes patent infringement, the patent licenses granted to you under Section 3 for that Work terminate as of the date such litigation is filed. This is a standard defensive clause present in all Apache 2.0-licensed projects.

### No Separate Enterprise Patent License

There is no separate enterprise patent indemnification agreement or commercial patent license. The Apache 2.0 Section 3 grant is the patent protection mechanism for all users equally.

---

## Patent Transfer to OCEAN Foundation

Upon formation of the OCEAN Foundation, both patent applications will be transferred to the Foundation. The Foundation will steward the patents as part of its role as platform steward. The Apache 2.0 license (and its Section 3 patent grant) remains unchanged regardless of patent ownership.

---

## Patent Filings Timeline

```
Aug 2023    Priority date (Patent 1)
Aug 2024    PCT filing (Patent 1)
Oct 2025    Provisional filing (Patent 2)
Dec 2025    IPRP Chapter II favorable (Patent 1)
Feb 2026    SG + US national phase filed; CN under filing (Patent 1)
Oct 2026    Complete application deadline (Patent 2)
```

---

## Contact

For patent-related inquiries: info@terrene.foundation

For the full patent notice, see the [PATENTS](../../PATENTS) file in the repository root.

---

## Document History

- **3 February 2026**: Originally drafted for Apache 2.0 + Additional Terms regime.
- **7 February 2026**: Revised to reflect transition to pure Apache 2.0.
