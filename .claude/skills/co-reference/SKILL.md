---
name: co-reference
description: Load CO (Cognitive Orchestration) methodology reference. Use when discussing the domain-agnostic base methodology for human-AI collaboration, the seven first principles, the five-layer architecture, or the relationship between CO and domain applications like COC.
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

## The Seven First Principles

1. **Institutional Knowledge Thesis** — AI capability is commodity; institutional knowledge is the differentiator
2. **Brilliant New Hire Principle** — AI without context = most capable hire with zero onboarding
3. **Three Failure Modes** — Amnesia, Convention Drift, Safety Blindness
4. **Human-on-the-Loop Position** — Human defines/maintains context, not in/out of execution chain
5. **Deterministic Enforcement** — Critical rules enforced outside AI context, not probabilistically
6. **Bainbridge's Irony** — More automation requires deeper human understanding
7. **Knowledge Compounds** — Institutional knowledge accumulates across sessions

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

## CO → Domain Applications

| Application       | Short Name | Status                |
| ----------------- | ---------- | --------------------- |
| CO for Codegen    | COC        | Mature, in production |
| CO for Compliance | —          | Planned               |
| CO for Finance    | —          | Planned               |
| CO for Operations | —          | Future                |

COC is the first and most mature domain application. It proves CO's principles work in practice with 29 agents, 25 skills, 8 rules, 8 hooks, and 12 commands.

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
  7 Principles: Institutional Knowledge, Brilliant New Hire, Three Failures,
                Human-on-the-Loop, Deterministic Enforcement, Bainbridge's Irony,
                Knowledge Compounds
  5 Layers: Intent → Context → Guardrails → Instructions → Learning
  3 Failure Modes: Amnesia, Convention Drift, Safety Blindness
  1 Insight: Institutional knowledge > Model capability
```

## For Detailed Information

If Foundation source docs exist in this repo, read the CO Core Thesis and CO specification for additional depth. For comprehensive analysis, invoke the **co-expert** agent.
