# PHASE 1: Analysis - Existing Project

> **Usage**: Copy this entire file and paste into Claude Code terminal.
> **Next Phase**: After completing this phase, paste `02-planning.md`

---

## HUMAN INPUT REQUIRED

### Project Context

**Repository**: **\*\***\_\_\_**\*\***
**Current State**: (MVP, Production, Legacy, etc.)

**Purpose of Analysis**:

<!-- Check all that apply -->

- [ ] Migration to new architecture
- [ ] Adding major new features
- [ ] Bug investigation
- [ ] Performance optimization
- [ ] Security audit
- [ ] Product pivot/enhancement
- [ ] Creating reusable knowledge base

### Soft Rule: Reusability Target

<!-- This solution follows the 80/15/5 rule -->

- **80%**: Features/efforts that can be reused (agnostic)
- **15%**: Client-specific requirements for self-service functionalities
- **5%**: Pure customization

### Known History

<!-- What do you know that Claude cannot discover from code alone? -->

- Why was the architecture chosen?
- What previous decisions led to current state?
- Known technical debt:
- Previous refactoring attempts:

### Focus Areas

<!-- Specific areas of interest or concern -->

1.
2.
3.

### Constraints

- Technology that MUST be preserved:
- Technology that CAN be replaced:
- Compliance requirements:
- Timeline:

---

## CLAUDE CODE INSTRUCTIONS

### Objective

Achieve 100% trace on this codebase and create a self-sustaining knowledge system.

### Analysis Tasks

#### 1. Full Codebase Trace (100% Coverage)

Using `sdk-navigator` and `deep-analyst`:

1. **Peruse codebase, docs, and tests thoroughly**
   - Analyze with subagents and skills
   - Achieve 100% trace on current state
   - Use independent subagents in parallel to ensure no gaps

2. **Document to extent that any developer can achieve 100% situational awareness**
   - Use as many subdirectories and files as required
   - Name them sequentially: 01-, 02-, etc.
   - Each subdirectory must have README.md for navigation

3. **Validate every claim with evidence from codebase and tests**

Document in: `docs/01-analysis/` with sequential naming

#### 2. Documentation Audit

1. **Check existing documentation**
   - Assume documentation may be misaligned or missing
   - Compare docs against actual implementation
   - Identify gaps and obsolete information

2. **Consolidate into docs/00-developers/**
   - Move and organize un-numbered files
   - Create missing documentation
   - Remove obsolete information
   - Consolidate repeated information

3. **Validate with evidence using subagents**

#### 3. Issue Analysis (If GitHub/Jira Issues Exist)

Using `gh-manager` to access issues:

1. **Analyze and categorize all issues**
   - CRITICALLY: Read the INTENT behind issues/feedback/comments
   - DO NOT treat as naive technical problems requiring patching
   - Create 'user stories' with intent, objective, and deliverable/KPI
   - Assume comments are vague - analyze deeply for root causes

2. **Create knowledge base and procedures**
   - Analyze issues comprehensively
   - Compare requirements against codebase
   - Deep dive into root causes
   - Follow the 80/15/5 soft rule
   - Create well-thought replies to queries

Document in: `docs/01-analysis/issues/`

#### 4. Git History Analysis

- Review git commits to identify recurring activities
- Research development lifecycle patterns
- Document patterns that should be automated

#### 5. Product Enhancement Analysis

Apply the same product frameworks as new projects:

**5.1 Value Proposition & USP**

- Scrutinize and critique intent and vision
- Research competing products for gaps
- Define clear USPs (not just VPs)

**5.2 AAA Framework Evaluation**

- **Automate**: Current vs potential operational cost reduction
- **Augment**: Current vs potential decision-making cost reduction
- **Amplify**: Current vs potential expertise cost reduction

**5.3 Platform Model Assessment**

- Current: Producers, Consumers, Partners
- Gaps in transaction facilitation
- Opportunities for enhancement

**5.4 Network Effects Gaps**

- Assess current coverage: Accessibility, Engagement, Personalization, Connection, Collaboration
- Identify improvement opportunities

**5.5 Apply 80/15/5 Rule**

- 80% reusable product features (no customizations)
- 15% self-service features (user-generated customizations)
- 5% customization and personalized (beyond what users can do themselves)
- Priority: **USP > VP > Features > Codebase**
- Do not reinvent - extend (unless codebase cannot support value propositions)

Document in: `docs/01-analysis/` with appropriate structure

#### 6. Parity Baseline (If Migration/Enhancement)

If this analysis is for migration or enhancement requiring parity validation:

1. **Document current system behavior**
   - Run key workflows through old system
   - Capture outputs for each workflow
   - Classify outputs as Deterministic or NLP

2. **Create baseline document**
   - Document in: `docs/01-analysis/parity-baseline.md`
   - Include: workflow → expected output mappings
   - Flag NLP outputs for LLM evaluation in Phase 4

#### 7. Agent & Skill Creation

Using `sdk-navigator` and any agents to understand agent/skill patterns:

**⚠️ PHASE 2 REQUIRES: At least one agent + SKILL.md entry point**

1. **Create project-specific agents** in `.claude/agents/project/`

   **Minimum Required (at least one):**
   - `[project-name]-analyst.md` - Codebase patterns and architecture
   - OR `[domain]-specialist.md` - Domain expert for business logic

   **For existing projects, consider:**
   - Specialized agents covering 100% of codebase
   - Use-case agents for cross-skill coordination

   **Each agent must include:**
   - Purpose and when to use
   - Reference to `docs/01-analysis/` and `docs/00-developers/`
   - Key patterns and decisions

2. **Create project-specific skills** in `.claude/skills/project/`

   **Required:**
   - `SKILL.md` - Entry point that references all project skills
   - At least one pattern file referenced by SKILL.md

   **Skills must:**
   - Reference `docs/00-developers/` NOT duplicate content
   - Be detailed enough for agents to work without templates

**MANDATORY TEST BEFORE GATE**: Start fresh session. Ask "How do I implement feature X?" using only agents/skills. If agent cannot answer correctly, FAIL Phase 1 and expand agents/skills until test passes.

### Output Requirements

Create the following structure:

```
docs/
├── 00-developers/          # Consolidated developer documentation
│   ├── README.md           # Navigation index
│   └── [organized content]
├── 01-analysis/
│   ├── README.md           # Navigation index
│   ├── 01-codebase-trace.md
│   ├── 02-documentation-audit.md
│   ├── 03-issues-analysis.md (if applicable)
│   ├── 04-value-proposition.md
│   ├── 05-aaa-evaluation.md
│   ├── 06-platform-model.md
│   └── 07-network-effects.md
└── 03-user-flows/
    ├── README.md           # Navigation index (required)
    └── [user journey docs]

.claude/
├── agents/project/
│   └── [project-specific agents]
└── skills/project/
    ├── SKILL.md
    └── [skill files]
```

---

## PHASE 1 COMPLETE - GATE

When analysis is complete, present to human:

1. **Codebase Trace Summary**
   - Coverage percentage achieved
   - Key architectural findings
   - Technical debt identified

2. **Documentation Status**
   - Gaps filled
   - Obsolete content removed
   - Consolidation summary

3. **Issue Analysis** (REQUIRED if GitHub/Jira connected, otherwise state "N/A - no issue tracker")
   - Categorization summary
   - User stories created
   - Root cause patterns

4. **Product Enhancement Assessment**
   - AAA current vs potential
   - Platform model gaps
   - Network effects score

5. **Agents & Skills Created**
   - List of project-specific agents
   - List of project-specific skills
   - Self-sufficiency assessment

6. **Artifacts Created**
   - List all files in docs/\*
   - List all agents/skills created

## ⚠️ APPROVAL GATE ⚠️

**STOP AND WAIT for explicit human approval.**

Human must respond with one of:

- **APPROVED** - Artifacts verified, proceed to Phase 2
- **REVISE: [feedback]** - Make adjustments and re-present
- **ABORT** - Stop work entirely

**Silence is NOT approval.** Wait for explicit response before human pastes `02-planning.md`.

---

_Template Version: 2.0_
_Phase: 1 of 4 (Analysis - Existing Project)_
