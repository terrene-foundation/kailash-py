> **PARTIALLY SUPERSEDED — RECOMMENDATIONS**
>
> These recommendations were prepared during the IP strategy development process (February
> 2026). The licensing recommendations (custom KSL v1.0) were superseded by the 6 February
> 2026 decision to adopt pure Apache 2.0. Patent filing recommendations remain valid and
> actionable. See `DECISION-MEMORANDUM.md` and `07-foundation/` for the current strategy.

# 02 - Patent Filing Strategy

## Document Purpose

Recommended patent filing actions, coordinated with the license transition.

## URGENT: National Phase Deadlines

**IPRP Chapter II confirmed favorable on 4 December 2025.** All 18 claims approved (Novelty, Inventive Step, Industrial Applicability — all YES).

| Deadline              | Date                 | Status                                  |
| --------------------- | -------------------- | --------------------------------------- |
| **30-month** (SG, US) | **14 February 2026** | **FILED** (Singapore and United States) |
| 31-month (CN)         | 14 March 2026        | Pending (39 days as of 3 Feb 2026)      |

## Immediate Actions

### Action 1: File Singapore National Phase — COMPLETED

- ~~Instruct Auriga IP **IMMEDIATELY** to file national phase entry at IPOS~~
- **Deadline: 14 February 2026** — **FILED**
- Can leverage favorable IPRP for expedited examination
- Use for ASPEC acceleration to other ASEAN jurisdictions

### Action 2: File United States National Phase — COMPLETED

- ~~Instruct Auriga IP to engage US associate counsel **IMMEDIATELY**~~
- **Deadline: 14 February 2026** (35 U.S.C. §371) — **FILED**
- Alice-safe claim drafting is essential — counsel must be experienced in software patent prosecution post-Alice
- Consider filing with both original PCT claims and Alice-adapted claims

### Action 3: Prepare China National Phase

- **Deadline: 14 March 2026** (China allows 31-month entry under Rule 100.1)
- Prepare CNIPA filing through Auriga IP's Chinese associate
- Translation preparation should begin now

### Action 3: Budget Allocation

Allocate budget for Tier 1 + Tier 2 filings:

- Singapore: SGD 5,000-15,000
- United States: USD 10,000-20,000
- China: USD 5,000-10,000
- Total: approximately USD 25,000-45,000

## Filing Sequence

1. **Singapore** — FILED
   - Home jurisdiction
   - Lowest cost
   - Can use for ASPEC acceleration
   - Favorable IPRP substantially de-risks prosecution

2. **United States** — FILED
   - Critical market for valuation and enforcement
   - Alice-experienced counsel engaged
   - Favorable IPRP will be considered by USPTO

3. **China** — FILE WITHIN 5 WEEKS (deadline 14 Mar 2026)
   - Strategic market (manufacturing/logistics alignment)
   - Lower cost than US
   - Begin translation preparation immediately
   - Leverage IPRP findings

4. **Europe** (defer decision to 6 months post-launch)
   - Only if enterprise pipeline justifies cost
   - Monitor EU customer traction

## Claim Strategy for US Filing

To mitigate Alice risk, US claims should emphasize:

1. **Specific technical architecture** (data fabric layer with source data layer and unified data layer)
2. **Technical process** (metadata transformation from heterogeneous formats to unified format)
3. **Technical improvement** (reduced development time, improved scalability, format-agnostic processing)

Avoid:

- Abstract business method language
- Generic "computer-implemented" framing without technical specificity
- Claims that read as simple data manipulation

## Second Patent: AI Workflow Orchestration (P251088SG)

On 7 October 2025, Terrene Foundation filed a Singapore provisional application (P251088SG) titled _"Method and System for Orchestrating Artificial Intelligence Workflow"_. This closes the Kaizen framework coverage gap identified in the original IP strategy analysis.

### P251088SG Deadlines

| Event                   | Date               | Status                             |
| ----------------------- | ------------------ | ---------------------------------- |
| Provisional filing      | 7 October 2025     | Filed                              |
| Complete SG application | **7 October 2026** | Pending (8 months from 3 Feb 2026) |
| PCT filing (if desired) | **7 October 2026** | Decision pending                   |

### P251088SG Actions

1. **Prepare complete application** (deadline: 7 October 2026)
   - Add system claims (currently only method claims — 1 independent + 10 dependent)
   - Strengthen Alice positioning for potential US filing
   - Cross-reference PCT/SG2024/050503 to establish portfolio relationship

2. **Decide on PCT filing** (deadline: 7 October 2026)
   - The AI agent orchestration space is rapidly evolving
   - PCT filing would extend international protection from the 7 October 2025 priority date
   - Recommend PCT filing to preserve optionality

3. **Coordinate with Patent 1 national phase**
   - Use same counsel for consistency
   - Cross-reference both applications in prosecution

## Continuation and Extension Patent Considerations

| Extension                 | Covers                                                              | Framework | Status                                             |
| ------------------------- | ------------------------------------------------------------------- | --------- | -------------------------------------------------- |
| AI Agent Orchestration    | Multi-agent coordination, autonomous execution on composable layer  | Kaizen    | **FILED** as P251088SG (7 Oct 2025)                |
| Multi-Channel Deployment  | Simultaneous API/CLI/MCP from single workflow definition            | Nexus     | Consider continuation from Patent 1 or Patent 2    |
| Automatic Node Generation | Model-to-node transformation generating N operation nodes per model | DataFlow  | Consider continuation from Patent 1                |
| Cyclic Workflow Execution | State convergence in cyclic node graphs                             | Core SDK  | Partially covered by Patent 2 (convergence claims) |

The filing of P251088SG substantially strengthens the patent portfolio. The remaining extensions (Multi-Channel Deployment, Automatic Node Generation) should be evaluated after Patent 1 national phase prosecution progresses.

## Coordination with License Transition

| License Event               | Patent Action                                                       |
| --------------------------- | ------------------------------------------------------------------- |
| License drafted             | Patent grant clause references both PCT/SG2024/050503 and P251088SG |
| License published           | PATENTS file added to repository (listing both patent applications) |
| Patent 1 national phase     | Update PATENTS file with national application numbers               |
| Patent 2 complete app filed | Update PATENTS file with complete application number                |
| Patents granted             | Update PATENTS file with grant numbers                              |
| Enterprise license launched | Include patent indemnification referencing both patent families     |
