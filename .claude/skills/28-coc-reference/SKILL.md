---
name: coc-reference
description: Load COC Framework reference. Use when discussing AI-assisted development methodology, the five-layer architecture, vibe coding critique, anti-amnesia patterns, institutional knowledge engineering, or Human-on-the-Loop development.
allowed-tools:
  - Read
  - Glob
  - Grep
---

# COC Framework Reference

This skill provides the reference for the COC (Cognitive Orchestration for Codegen) framework - the five-layer architecture for disciplined AI-assisted development.

## Knowledge Sources

This skill is self-contained — all essential COC knowledge is distilled below from the COC Core Thesis by Dr. Jack Hong. If Foundation source docs exist in this repo, read them for additional depth.

## What is COC?

COC is a five-layer architecture that provides AI coding assistants with the organizational context, guardrails, and operating procedures they need to function as disciplined engineering partners. It applies the CARE framework's Human-on-the-Loop philosophy to software development.

COC is a new term introduced in the thesis paper. It names an architecture that the Kailash ecosystem has implemented. The principles are not new; the systematic five-layer organization is.

## The Problem: Vibe Coding's Three Fault Lines

| Fault Line             | Problem                                            | Root Cause                  |
| ---------------------- | -------------------------------------------------- | --------------------------- |
| **Amnesia**            | AI forgets your instructions as context fills up   | Context window limits       |
| **Convention Drift**   | AI follows internet conventions instead of yours   | Training data overrides     |
| **Security Blindness** | AI takes the shortest path (never the secure path) | Optimization for directness |

**The root cause is not model capability. It is the absence of institutional knowledge surrounding the model.**

## The Value Hierarchy Inversion

```
Vibe Coding:  Better Model → Better Code → Competitive Advantage
COC Reality:  Better Context → Better Output → Competitive Advantage
              (specific to you)  (any model)    (defensible)
```

## The Five-Layer Architecture

```
+--------------------------------------------------+
|          Layer 5: LEARNING                        |
|    Observation → Instinct → Evolution             |
+--------------------------------------------------+
|          Layer 4: INSTRUCTIONS                    |
|    Structured methodology with approval gates     |
+--------------------------------------------------+
|          Layer 3: GUARDRAILS                      |
|    Deterministic enforcement, not suggestions     |
+--------------------------------------------------+
|          Layer 2: CONTEXT                         |
|    Your living institutional handbook             |
+--------------------------------------------------+
|          Layer 1: INTENT                          |
|    Specialized agents, not generalist AI          |
+--------------------------------------------------+
```

### Layer 1: Intent - The Role

- **Solves**: Generalist AI producing generalist output
- **Principle**: Route tasks to specialized expert agents
- **Implementation**: 30 agent definitions, 7 development phases
- **Key specialists**: deep-analyst, security-reviewer, framework specialists
- **What it encodes**: Your organizational structure

### Layer 2: Context - The Library

- **Solves**: AI defaulting to internet conventions
- **Principle**: Replace stale training data with your living institutional handbook
- **Implementation**: Progressive disclosure (CLAUDE.md → SKILL.md → Topic files → Full docs)
- **Two principles**: Framework-First (never code from scratch) + Single Source of Truth
- **Key distinction**: Context engineering (persists across sessions) vs prompt engineering (single interaction)
- **What it encodes**: Your institutional knowledge

### Layer 3: Guardrails - The Supervisor

- **Solves**: Probabilistic compliance ("most of the time" is not enough)
- **Principle**: Deterministic enforcement, not probabilistic compliance
- **Implementation**: 9 rule files (soft) + 9 hook scripts (hard)
- **Key mechanism**: Anti-amnesia hook (`user-prompt-rules-reminder.js`) - fires every message, survives context compression
- **Defense in depth**: Critical rules have 5-8 independent enforcement layers
- **What it encodes**: Your risk tolerance

### Layer 4: Instructions - The Operating Procedures

- **Solves**: No procedural discipline (AI writes code before confirming approach)
- **Principle**: Structured methodology with approval gates
- **Implementation**: 7-phase workflow, 4 quality gates, 20 slash commands (13 framework + 7 workspace phase)
- **Key features**: Evidence-based completion (file-and-line proof), mandatory delegation (security review before every commit)
- **What it encodes**: Your process maturity

### Layer 5: Learning - The Performance Review

- **Solves**: Stateless sessions (every session starts from zero)
- **Principle**: Observe, capture, evolve. Knowledge compounds.
- **Implementation**: Observation-Instinct-Evolution pipeline
  - Observation: JSONL logs of tool usage, patterns, errors
  - Instinct: Pattern analysis (confidence = frequency 40% + success 30% + recency 20% + consistency 10%)
  - Evolution: Suggest artifacts (Skills ≥0.7, Commands ≥0.6, Agents ≥0.8) - all require human approval
- **What it encodes**: Everything above, compounding over time

## CARE → COC Mapping

| CARE / EATP Concept | COC Equivalent                |
| ------------------- | ----------------------------- |
| Trust Plane         | Rules + CLAUDE.md             |
| Execution Plane     | Agents + Skills               |
| Genesis Record      | `session-start.js`            |
| Trust Lineage Chain | Mandatory review gates        |
| Audit Anchors       | Hook enforcement              |
| Operating Envelope  | 9 rule files + 9 hook scripts |

## The Human-on-the-Loop Developer

The developer's unique contribution is not writing code but defining and maintaining the institutional context:

- **Layer 1**: Articulate domain structure
- **Layer 2**: Document institutional knowledge
- **Layer 3**: Identify non-negotiable rules
- **Layer 4**: Formalize methodology
- **Layer 5**: Extract patterns from experience

Bainbridge's Irony (1983): The more automated a system becomes, the more critical it is that human operators maintain deep understanding. Every COC layer deepens the developer's expertise.

## The Autonomous Execution Model

COC executes through **autonomous AI agent systems**, not human teams. This is the direct application of CO Principle 4 (Human-on-the-Loop): the human defines the operating envelope; autonomous agents execute within it.

### The 10x Throughput Multiplier

**Default multiplier: 10x** — autonomous AI execution with mature COC institutional knowledge produces ~10x the sustained throughput of an equivalent human team.

| Factor                                                       | Multiplier |
| ------------------------------------------------------------ | ---------- |
| Parallel agent execution                                     | 3-5x       |
| Continuous operation (24/7, no fatigue, zero context-switch) | 2-3x       |
| Knowledge compounding (CO Principle 7)                       | 1.5-2x     |
| Validation overhead                                          | 0.7-0.8x   |
| **Net sustained**                                            | **~10x**   |

### Structural vs Execution Gates

| Gate Type                              | Examples                                                         | Human Role                      |
| -------------------------------------- | ---------------------------------------------------------------- | ------------------------------- |
| **Structural** (human authority)       | Plan approval, release authorization, envelope changes           | Human decides                   |
| **Execution** (autonomous convergence) | Test passing, red team convergence, code review, security review | Agents converge; human observes |

### Impact on Deliberation

When agents deliberate (during /analyze, /redteam, or planning), they MUST:

- Estimate effort in **autonomous sessions**, not human-days
- Recommend the **technically optimal approach** unconstrained by human resource limits
- Default to **maximum parallelization** across agent specializations
- Frame trade-offs in terms of **system complexity** and **validation rigor**, not team bandwidth

See `rules/autonomous-execution.md` for the full principle, multiplier basis, and application rules.

## Honest Limitations

- Novel architecture decisions (no established pattern to follow)
- Distributed systems complexity (emergent problems beyond local guardrails)
- Model-specific limitations (reduced, not eliminated)
- Legacy codebases (fewer frameworks to compose with)
- Greenfield domains where no institutional knowledge exists yet (first session is ~2-3x, not 10x)

## Quick Reference

```
COC = Cognitive Orchestration for Codegen
  5 Layers: Intent → Context → Guardrails → Instructions → Learning
  3 Fault Lines: Amnesia, Convention Drift, Security Blindness
  1 Insight: Institutional knowledge > Model capability

The Kailash COC Implementation:
  30 agents, 28 skills, 9 rules, 9 hooks, 20 commands
  Reference: github.com/terrene-foundation/kailash-coc-claude-py
```

## For Detailed Information

If Foundation source docs exist in this repo, read the COC Core Thesis for additional depth. For comprehensive analysis, invoke the **coc-expert** agent.
