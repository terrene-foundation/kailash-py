---
name: co-reference
description: Load CO (Cognitive Orchestration) methodology reference. Use when discussing the domain-agnostic base methodology for human-AI collaboration, the eight first principles, the five-layer architecture, or the relationship between CO and domain applications like COC.
allowed-tools:
  - Read
  - Glob
  - Grep
---

# CO (Cognitive Orchestration) Methodology Reference

This skill provides the reference for CO — the domain-agnostic base methodology for structuring human-AI collaboration in any domain where AI agents operate under human oversight.

## Knowledge Sources

This skill is self-contained — all essential CO knowledge is distilled below from the CO Core Thesis by Dr. Jack Hong and the CO specification. If Foundation source docs exist in this repo, read them for additional depth.

## What is CO?

CO (Cognitive Orchestration) is a methodology for structuring institutional knowledge, guardrails, and processes so that AI agents produce trustworthy output in any domain. It is the base methodology from which domain-specific applications are derived.

CO sits in the trinity alongside CARE and EATP:

- **CARE** tells you _what the human is for_
- **EATP** tells you _how to keep the human accountable_
- **CO** tells you _how the human structures AI's work_

## The Eight First Principles

1. **Institutional Knowledge Thesis** — AI capability is commodity; institutional knowledge is the differentiator
2. **Brilliant New Hire Principle** — AI without context = most capable hire with zero onboarding
3. **Three Failure Modes** — Amnesia, Convention Drift, Safety Blindness
4. **Human-on-the-Loop Position** — Human defines/maintains context, not in/out of execution chain
5. **Deterministic Enforcement** — Critical rules enforced outside AI context, not probabilistically
6. **Bainbridge's Irony** — More automation requires deeper human understanding
7. **Knowledge Compounds** — Institutional knowledge accumulates across sessions
8. **Authentic Voice and Responsible Co-Authorship** — Output reflects genuine human intellectual direction; AI assistance disclosed per venue requirements; detection bias mitigated through style, not concealment

## The Five-Layer Architecture

```
Layer 5: LEARNING      — Observe, capture, evolve knowledge across sessions
Layer 4: INSTRUCTIONS  — Structured workflows with approval gates
Layer 3: GUARDRAILS    — Deterministic enforcement outside AI context
Layer 2: CONTEXT       — Organization's institutional knowledge, machine-readable
Layer 1: INTENT        — Route to domain-specialized agents
```

Each layer encodes a different aspect of human judgment:

- Layer 1 encodes organizational structure
- Layer 2 encodes institutional knowledge
- Layer 3 encodes risk tolerance
- Layer 4 encodes process maturity
- Layer 5 encodes everything above, compounding over time

## The Six-Phase Workflow Model

Layer 4 (Instructions) is implemented through a six-phase workflow:

| Phase | Template Command | Target                  | Purpose                                         |
| ----- | ---------------- | ----------------------- | ----------------------------------------------- |
| 01    | `/analyze`       | 01-research/            | Research and understand the problem space       |
| 02    | `/plan`          | 02-planning/            | Structure the work; **human approves**          |
| 03    | `/execute`       | 03-work/                | Do the work one task at a time                  |
| 04    | `/review`        | 04-review/ → 05-output/ | Adversarial critique; produces finalized output |
| 05    | `/learn`         | **.claude/**            | Extract knowledge; upgrade CO artifacts         |
| 06    | `/deliver`       | 05-output/ → recipient  | Package and hand off                            |

**Phase 04 (Review)** produces the finalized work. Review iterates until quality passes, then saves to 05-output/.

**Phase 05 (Learn)** is unique — its output goes OUTSIDE the workspace, back into the CO system (.claude/ artifacts). This is Principle 7 (Knowledge Compounds) made concrete. Every run makes the system stronger. Proposals require human approval before modifying .claude/.

**Phase 06 (Deliver)** packages and ships. Domain applications rename this: `/publish` (COR), `/release` or `/deploy` (COC), `/submit` (student COs).

The workspace has 5 directories (01-research through 05-output) because Phase 05 has no workspace directory.

Domains rename commands to fit their vocabulary but preserve the 6-phase structure. CO does not prescribe the exact number of commands per phase — domains may split phases (COR splits Phase 01 into /teach and /literature) or add specialist commands within phases.

## CO → Domain Applications

| Application       | Short Name | Status      |
| ----------------- | ---------- | ----------- |
| CO for Codegen    | COC        | Production  |
| CO for Research   | COR        | Production  |
| CO for Education  | COE        | Analysis    |
| CO for Governance | COG        | Production  |
| CO for Compliance | COComp     | Sketch      |
| CO for Learners   | COL        | Development |
| COL for Finance   | COL-F      | Production  |

COC is the first and most mature domain application. It proves CO's principles work in practice with 29 agents, 25 skills, 8 rules, 8 hooks, and 12 commands.

COL (CO for Learners) is the subject-agnostic student CO. Subject layers (COL-F for Finance, future COL-H, COL-B, COL-L) inherit COL and add subject-specific commands, agents, skills, and rules.

## CARE → CO Connection

CO inherits CARE's Human-on-the-Loop philosophy. The mapping:

| CARE Concept                           | CO Manifestation                         |
| -------------------------------------- | ---------------------------------------- |
| Trust Plane (humans define boundaries) | Layer 2 (Context) + Layer 3 (Guardrails) |
| Execution Plane (AI at machine speed)  | Layer 1 (Intent agents)                  |
| Constraint Envelopes                   | Layer 3 enforcement mechanisms           |
| Human-on-the-Loop                      | The Human-on-the-Loop practitioner role  |
| Evolutionary Trust                     | Layer 5 (Learning pipeline)              |

## CO → EATP Connection

CO's guardrails connect to EATP's trust infrastructure:

| CO Layer               | EATP Connection                                                     |
| ---------------------- | ------------------------------------------------------------------- |
| Layer 3 (Guardrails)   | Constraint Envelopes — formal boundaries enforced deterministically |
| Layer 4 (Instructions) | Trust Postures — approval gates map to verification gradient        |
| Layer 5 (Learning)     | Audit Anchors — learning observations become audit records          |

## Honest Limitations

- CO does not help with truly novel domains where no institutional knowledge exists yet
- CO does not solve the alignment problem (agents can still achieve prohibited outcomes through individually permitted actions)
- CO's three failure modes are current AI limitations, not permanent boundaries
- Effectiveness depends on the quality of institutional knowledge the human provides

## Quick Reference

```
CO = Cognitive Orchestration
  8 Principles: Institutional Knowledge, Brilliant New Hire, Three Failures,
                Human-on-the-Loop, Deterministic Enforcement, Bainbridge's Irony,
                Knowledge Compounds, Authentic Voice
  5 Layers: Intent → Context → Guardrails → Instructions → Learning
  6 Phases: Analyze → Plan → Execute → Review → Learn → Deliver
  3 Failure Modes: Amnesia, Convention Drift, Safety Blindness
  1 Insight: Institutional knowledge > Model capability
```

## For Detailed Information

If Foundation source docs exist in this repo, read the CO Core Thesis and CO specification for additional depth. For comprehensive analysis, invoke the **co-expert** agent.
