---
name: care-reference
description: Load CARE Framework reference. Use when discussing CARE governance philosophy, the Dual Plane Model, Mirror Thesis, Human-on-the-Loop, six human competencies, or the relationship between CARE, EATP, and COC.
allowed-tools:
  - Read
  - Glob
  - Grep
---

# CARE Framework Reference

This skill provides the reference for the CARE (Collaborative Autonomous Reflective Enterprise) framework - the governance philosophy for enterprise AI.

## Authoritative Sources

### PRIMARY: White Paper
- `docs/02-standards/publications/CARE-Core-Thesis.md` - Definitive thesis by Dr. Jack Hong

### PRIMARY: Anchor Documents
- `docs/00-anchor/00-first-principles.md` - Core mission and principles
- `docs/00-anchor/01-core-entities.md` - CARE as core asset
- `docs/00-anchor/02-the-gap.md` - Why CARE exists (the governance gap)

### SECONDARY: CARE Documentation
- `docs/02-standards/care/` - Complete CARE framework (39 documents)
- `docs/02-standards/publications/00-overview.md` - Series overview (5 papers)

## What is CARE?

CARE proposes a third path between human-in-the-loop (bottleneck) and human-out-of-the-loop (no accountability). The central insight: **Trust is human. Execution is shared. The system reveals what only humans can provide.**

## Three Core Propositions

### 1. The Dual Plane Model
| Plane | Contains | Character |
|---|---|---|
| **Trust Plane** | Accountability, authority delegation, values, boundaries | Permanently human |
| **Execution Plane** | Task completion, information processing, coordination | Shared with AI |

- Normative choice, not ontological discovery. Pragmatically justified.
- Prior art: SDN control/data planes, Kubernetes, aviation.
- Humans invest judgment at setup time; AI executes at machine speed; accountability preserved through verifiable trust chains.

### 2. The Mirror Thesis
When AI executes all measurable tasks of a role, what remains visible is the human contribution beyond task execution - judgment, relationships, wisdom that were always the actual source of value but were invisible because they were entangled with execution.

**Circularity acknowledged**: The thesis is closer to an axiom than a derived conclusion. Adopted because it generates useful governance architecture.

**Misuse risk**: The same diagnostic can be used for elimination rather than development. CARE provides the diagnostic; organizations choose how to use it.

### 3. Human-on-the-Loop
- Humans define the operating envelope
- AI executes within it at machine speed
- Humans observe execution patterns
- Humans refine boundaries
- The loop is continuous

**Caveat**: Aspirational architecture, not guaranteed control.

## Six Human Competency Categories

Current AI limitations, not principled impossibilities:

| # | Competency | Core Insight |
|---|---|---|
| 1 | **Ethical Judgment** | Sensing when technically correct is morally wrong |
| 2 | **Relationship Capital** | Trust built through shared vulnerability and history |
| 3 | **Contextual Wisdom** | Knowledge from lived experience that transcends data |
| 4 | **Creative Synthesis** | Evaluating and grounding novel solutions |
| 5 | **Emotional Intelligence** | Reading rooms, sensing tension, genuine care |
| 6 | **Cultural Navigation** | Understanding unwritten rules across contexts |

## Eight CARE Principles

1. **Full Autonomy as Baseline** - AI handles everything it can within trust boundaries
2. **Human Choice of Engagement** - Deliberate judgment, not reflexive approval
3. **Transparency as Foundation** - Every AI action visible; choice not to look is informed
4. **Continuous Operation** - AI maintains quality; humans bring judgment when needed
5. **Human Accountability Preserved** - Every action traces to human authority
6. **Graceful Degradation** - Safe degradation at competence boundaries
7. **Evolutionary Trust** - Boundaries evolve based on demonstrated performance
8. **Purpose Alignment** - AI within human-defined organizational purposes

These form an integrated system. Each constrains and supports the others.

## The Governance Dilemma CARE Solves

Traditional governance assumes a human made the decision. AI breaks this assumption:
- Human-in-the-loop: Preserves accountability but eliminates automation value
- Human-out-of-the-loop: Captures speed but creates unacceptable risk
- CARE: Separate trust establishment (human judgment) from trust verification (machine speed)

## CARE's Relationship to Companion Frameworks

| Framework | Relationship to CARE |
|---|---|
| **EATP** | Operationalizes CARE's trust chains as a verifiable protocol |
| **COC** | Applies CARE's Human-on-the-Loop philosophy to software development |
| **Kailash** | Reference implementation of CARE governance architecture |

## Honest Limitations

- Six competencies are a 2026 snapshot, not permanent boundaries
- Does not solve displacement economics
- Does not guarantee regulatory compliance
- Does not eliminate power asymmetries
- Constraint gaming is the central operational risk

## Quick Reference

```
The Governance Dilemma:
  Human-in-the-loop → Bottleneck
  Human-out-of-the-loop → No accountability
  CARE (Human-on-the-loop) → Third path

CARE = Collaborative Autonomous Reflective Enterprise
  C = Collaborative (human and AI as partners)
  A = Autonomous (AI within human-defined boundaries)
  R = Reflective (system reveals what only humans provide)
  E = Enterprise (organizational-scale design)
```

## For Detailed Information

Read these source documents:
- `docs/02-standards/publications/CARE-Core-Thesis.md` - The thesis paper
- `docs/02-standards/care/01-philosophy/` - Philosophy documents
- `docs/02-standards/care/02-architecture/` - Architecture documents
- `docs/02-standards/care/03-human-competency/` - Competency framework
- `docs/02-standards/care/04-governance/` - Governance model

For comprehensive analysis, invoke the **care-expert** agent.
