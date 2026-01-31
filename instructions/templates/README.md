# Claude Code Instruction Templates

These templates are the **definitive interface** between humans and Claude Code. They implement a **multi-session, phase-gated workflow** where:

- Each phase produces **artifacts that survive session restarts**
- Human approval is a **BLOCKING GATE**, not a suggestion
- The goal is to build a **self-sustaining system** (agents + skills)
- Fresh Claude sessions are a **feature, not a bug**

---

## Template Selection Guide

### For New Projects

```
01a-analysis-new.md → 02-planning.md → 03-implementation.md → 04-validation.md
```

### For Existing Projects

```
01b-analysis-existing.md → 02-planning.md → 03-implementation.md → 04-validation.md
```

### Quick Reference

| Phase | Template | Purpose | Gate |
|-------|----------|---------|------|
| **1** | `01a-analysis-new.md` | New project analysis (VP, USP, AAA, Platform) | Human verifies artifacts |
| **1** | `01b-analysis-existing.md` | Existing codebase trace (80/15/5, agents, skills) | Human verifies artifacts |
| **2** | `02-planning.md` | Todo creation, architecture | **HARD: APPROVED/REVISE/ABORT** |
| **3** | `03-implementation.md` | Implementation loop (spam repeatedly) | All todos complete |
| **4** | `04-validation.md` | E2E testing, parity, manual checklist | Human validates |

---

## How to Use

### Step 1: Copy Entire Template
Don't excerpt - copy the **entire file** including all sections.

### Step 2: Fill HUMAN INPUT Section
This is YOUR domain:
- Objectives and vision
- Domain knowledge
- Constraints
- Credentials location

### Step 3: Paste into Claude Terminal
Claude will execute the CLAUDE CODE INSTRUCTIONS section.

### Step 4: Wait for GATE
Claude will stop at the gate and present a summary.

### Step 5: Provide Explicit Approval
Type one of:
- **APPROVED** - Proceed to next phase
- **REVISE: [feedback]** - Make adjustments
- **ABORT** - Stop work

### Step 6: Paste Next Template
When ready, paste the next phase template.

---

## Important Notes

### README.md Files Are Required
Each docs/ subdirectory MUST have a README.md as a navigation index. This is explicitly required despite Claude Code's general instruction to avoid creating documentation files - these are structural navigation files, not prose documentation.

### docs/04-codegen-instructions/ Is Always Created
Phase 2 always creates `docs/04-codegen-instructions/00-session-context.md` as the base context loading document for fresh sessions, even for single-repo projects.

---

## Phase Dependencies

```
┌─────────────────┐
│ PHASE 1         │ Analysis
│ 01a or 01b      │
└────────┬────────┘
         │ Creates: docs/01-analysis/*
         │ Gate: Human verifies artifacts exist
         ▼
┌─────────────────┐
│ PHASE 2         │ Planning
│ 02-planning.md  │
└────────┬────────┘
         │ Creates: todos/active/*, docs/02-plans/*
         │ Gate: Human types APPROVED
         ▼
┌─────────────────┐
│ PHASE 3         │ Implementation (spam repeatedly)
│ 03-implement... │
└────────┬────────┘
         │ Creates: Code, tests, docs/00-developers/*
         │ Gate: All todos complete
         ▼
┌─────────────────┐
│ PHASE 4         │ Validation
│ 04-validation   │
└─────────────────┘
         │ Gate: Human validates and approves
```

---

## Multi-Session Design

### Why Fresh Sessions?

Long sessions accumulate errors. Fresh sessions are MORE reliable:
- Each session starts clean
- Context is focused and curated
- Input (template) is inspectable
- Behavior is reproducible

### The "Spam Repeatedly" Pattern

Phase 3 is designed to be pasted into FRESH sessions repeatedly:

1. Human pastes `03-implementation.md`
2. Claude loads context from docs/04-codegen-instructions/
3. Claude works on next todo
4. Session ends or context fills
5. Human pastes `03-implementation.md` in NEW session
6. Repeat until all todos complete

### Session Resume Documents

Claude creates `docs/04-codegen-instructions/*.md` files that bootstrap fresh sessions:

```markdown
# Session Resume: [Feature Name]

## Context Loading
Peruse this document and reference linked docs.
Check todos/active/ for current state.

## Current State
- Completed: [list]
- In Progress: [current]
- Next: [upcoming]
```

---

## Preserved Frameworks

These frameworks are **NOT in Claude's agents/skills** and are preserved in templates:

### AAA Framework
- **Automate**: Reduce operational costs
- **Augment**: Reduce decision-making costs
- **Amplify**: Reduce expertise costs

### Platform Model
- **Producers**: Offer/deliver products/services
- **Consumers**: Consume products/services
- **Partners**: Facilitate transactions

### Network Effects (5 Behaviors)
- Accessibility, Engagement, Personalization, Connection, Collaboration

### 80/15/5 Reusability Rule
- **80%**: Agnostic, reusable
- **15%**: Configurable self-service
- **5%**: Custom (requires justification)

### LLM-Based NLP Evaluation
- Use LLM evaluation for natural language outputs
- No keyword/regex assertions for NLP

---

## Self-Sustainability Goal

The end state is agents/skills that work WITHOUT these templates.

**Validation Test** (in Phase 4):
1. Start fresh Claude session
2. Ask Claude to implement a new feature using ONLY:
   - `.claude/agents/project/`
   - `.claude/skills/project/`
   - `docs/00-developers/`
3. If Claude can complete the task, system is self-sustaining

---

## Examples

See `examples/` for filled template examples:
- `new-project-inventory-system.md` - New project example
- `feature-request-export-pdf.md` - Feature request example
- `validation-parity-migration.md` - Parity validation example

---

## Related Documentation

- **SOP**: `.claude/guides/claude-code/00-working-with-claude-code.md`
- **Agent System**: `.claude/guides/claude-code/05-the-agent-system.md`
- **Agents**: `.claude/agents/`
- **Skills**: `.claude/skills/`

---

*Version: 2.0*
*Last Updated: 2026-01-31*
