# PHASE 1: Analysis - New Project

> **Usage**: Copy this entire file and paste into Claude Code terminal.
> **Next Phase**: After completing this phase, paste `02-planning.md`

---

## HUMAN INPUT REQUIRED

### Project Overview

**Project Name**: **\*\***\_\_\_**\*\***

**Vision**:

<!-- What problem does this solve? Who benefits? What's the end state? (2-3 sentences) -->

### User Scenarios

<!-- Define 2-3 key user workflows. Be specific about user roles and outcomes. -->

1. **As a [user type #1]**, this is what I envision as my workflow:
   - Step 1:
   - Step 2:
   - Expected outcome:

2. **As a [user type #2]**, this is what I envision as my workflow:
   - Step 1:
   - Step 2:
   - Expected outcome:

### Domain Knowledge

<!-- Share what Claude cannot know from research alone -->

- Industry context:
- Business rules:
- Compliance requirements:
- Competitive landscape:
- Known pain points:

### Constraints

- **Technology**: (Required stack, existing systems)
- **Timeline**: (Key milestones, deadlines)
- **Budget**: (Resource limitations)
- **Integration**: (External systems, APIs)

### Credentials & Access

- **API Keys**: (Location of .env or secrets)
- **External Documentation**: (Links to specs, APIs)
- **Test Accounts**: (REQUIRED if external APIs used, N/A with justification otherwise)

---

## CLAUDE CODE INSTRUCTIONS

### Objective

Analyze this project through product strategy frameworks and create Phase 1 artifacts in `docs/01-analysis/`.

### Analysis Tasks

#### 1. Value Proposition Analysis

Using `deep-analyst` and web research:

- Research thoroughly and distill the VALUE PROPOSITIONS of this solution
- Scrutinize and critique the vision/intent with focus on product-market fit
- Research competing products, gaps, and pain points

Document in: `docs/01-analysis/01-value-proposition.md`

#### 2. Unique Selling Points (USP)

- Define what makes this solution UNIQUELY different from alternatives
- Be extremely critical - USP ≠ VP. USP is what ONLY this solution provides.
- Document evidence for each claimed USP

Document in: `docs/01-analysis/02-unique-selling-points.md`

#### 3. AAA Framework Evaluation

Evaluate the solution against:

- **Automate**: How does this reduce operational costs?
- **Augment**: How does this reduce decision-making costs?
- **Amplify**: How does this reduce expertise costs (for scaling)?

If a feature doesn't align with AAA, question whether it should be built.

Document in: `docs/01-analysis/03-aaa-evaluation.md`

#### 4. Platform Model Thinking

Analyze the solution as a platform with:

- **Producers**: Users who offer/deliver a product or service
- **Consumers**: Users who consume a product or service
- **Partners**: Facilitators of transactions between producers and consumers

Identify how transactions between these parties are facilitated.

Document in: `docs/01-analysis/04-platform-model.md`

#### 5. Network Effects Analysis

Assess coverage of these 5 network behaviors:

- **Accessibility**: Easy for users to complete a transaction
- **Engagement**: Information useful for completing transactions
- **Personalization**: Information curated for intended use
- **Connection**: Information sources connected to the platform (one/two-way)
- **Collaboration**: Producers and consumers can work together seamlessly

Document in: `docs/01-analysis/05-network-effects.md`

#### 6. User Flow Documentation

Create detailed user journey maps based on the scenarios provided.

Document in: `docs/03-user-flows/` (use sequential naming: 01-, 02-, etc.)

#### 7. 80/15/5 Classification

Apply the reusability rule to planned features:

- **80% reusable**: Product features that work for any client (no customizations)
- **15% self-service**: Client-specific but user-configurable
- **5% custom**: Personalization beyond what users can do themselves (requires justification)

Priority: **USP > VP > Features > Codebase**
Do not reinvent - extend (unless codebase cannot support value propositions).

#### 8. Agent & Skill Foundation (For Self-Sustainability)

Using `sdk-navigator` to understand agent/skill patterns:

**⚠️ PHASE 2 REQUIRES: At least one agent + SKILL.md entry point**

1. **Create initial project agents** in `.claude/agents/project/`

   **Minimum Required (at least one):**
   - `[project-name]-analyst.md` - Project-specific analysis patterns
   - OR `[domain]-specialist.md` - Domain expert for core business logic

   **Each agent must include:**
   - Purpose and when to use
   - Reference to `docs/01-analysis/` for context
   - Key patterns and decisions

2. **Create initial project skills** in `.claude/skills/project/`

   **Required:**
   - `SKILL.md` - Entry point that references all project skills
   - At least one pattern file referenced by SKILL.md

   **Skills must:**
   - Reference `docs/01-analysis/` NOT duplicate content
   - Be detailed enough for agents to work without templates

**MANDATORY TEST BEFORE GATE**: Start fresh session. Ask "What is this project about?" using only agents/skills. If agent cannot answer correctly, FAIL Phase 1 and expand agents/skills until test passes.

These will be expanded in Phase 3 as implementation progresses.

### Output Requirements

Create the following structure:

```
docs/
├── 00-developers/
│   └── README.md              # Navigation index (created now, populated in Phase 3)
├── 01-analysis/
│   ├── README.md              # Navigation index (required)
│   ├── 01-value-proposition.md
│   ├── 02-unique-selling-points.md
│   ├── 03-aaa-evaluation.md
│   ├── 04-platform-model.md
│   ├── 05-network-effects.md
│   └── 06-80-15-5-classification.md
└── 03-user-flows/
    ├── README.md              # Navigation index (required)
    ├── 01-[user-type-1]-flow.md
    └── 02-[user-type-2]-flow.md

.claude/
├── agents/project/
│   └── [domain-specific-agent].md
└── skills/project/
    └── SKILL.md
```

**CRITICAL**: Every docs/ subdirectory MUST have a README.md as a navigation index.

---

## PHASE 1 COMPLETE - GATE

When analysis is complete, present to human:

1. **Executive Summary** (1 paragraph)
2. **VP Summary**: Top 3 value propositions
3. **USP Summary**: Top 3 unique selling points with evidence
4. **AAA Alignment**: Which dimensions this solution covers
5. **Platform Assessment**: Producer/Consumer/Partner dynamics
6. **Network Effects Score**: Coverage of 5 behaviors (Low/Medium/High each)
7. **80/15/5 Classification**: Breakdown with any >5% custom items flagged
8. **Agents & Skills Created**: List of project-specific agents/skills
9. **Artifacts Created**: List of files in docs/01-analysis/, docs/03-user-flows/, and .claude/

## ⚠️ APPROVAL GATE ⚠️

**STOP AND WAIT for explicit human approval.**

Human must respond with one of:

- **APPROVED** - Artifacts verified, proceed to Phase 2
- **REVISE: [feedback]** - Make adjustments and re-present
- **ABORT** - Stop work entirely

**Silence is NOT approval.** Wait for explicit response before human pastes `02-planning.md`.

---

_Template Version: 2.0_
_Phase: 1 of 4 (Analysis)_
