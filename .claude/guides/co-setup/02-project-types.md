# CO Project Types

Every project using CO falls into one of several archetypes. The archetype determines which components to include.

## Archetypes

### 1. Coding (COC)

Software development projects. The AI writes code, tests it, deploys it.

**Examples**: SDK repos, web apps, API services, mobile backends

**Characteristics**:

- Primary output is code
- Testing is critical (unit, integration, e2e)
- Build systems, package managers, deployment pipelines
- Frontend and/or backend components

**Archetype-specific components**:

| Component | What to include                                                                                                                   |
| --------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Commands  | `/deploy`, `/test`, `/api`, `/db`, `/sdk`, `/ai`, `/design`, `/validate`                                                          |
| Commands  | `/i-audit`, `/i-harden`, `/i-polish`, `/learn`                                                                                    |
| Agents    | Framework specialists: `dataflow-specialist`, `nexus-specialist`, `kaizen-specialist`, `mcp-specialist`                           |
| Agents    | Frontend: `uiux-designer`, `react-specialist`, `flutter-specialist`, `react-specialist`, `uiux-designer`                          |
| Agents    | Deployment: `release-specialist`, `testing-specialist`                                                                            |
| Skills    | SDK-specific (01-core-sdk through 25-ai-patterns)                                                                                 |
| Rules     | `zero-tolerance.md` (strict — MUST NOT), `agents.md` (MANDATORY), `testing.md`, `patterns.md`, `e2e-god-mode.md`, `env-models.md` |
| Hooks     | `validate-workflow.js` (SDK pattern enforcement), `validate-deployment.js`                                                        |

**`start.md` orientation**: Product-building. "You describe what you want, the AI builds it."

**`analyze.md` framework**: Platform model, AAA framework, network effects, product-market fit.

**`redteam.md` approach**: User flow testing with Playwright/Marionette, end-to-end validation, parity checks.

---

### 2. Governance / Knowledge Base

Strategic, legal, or governance knowledge work. The AI researches, drafts, reviews, and publishes documents.

**Examples**: Foundation knowledge bases, standards bodies, policy organizations

**Characteristics**:

- Primary output is documents, specifications, strategy
- Cross-reference accuracy is critical
- Terminology consistency with canonical specs
- Publication quality for academic venues
- Constitutional and governance design

**Archetype-specific components**:

| Component | What to include                                                                                                                                        |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Commands  | `/arxiv`, `/publish`, `/governance-layer`, `/co-domain`                                                                                                |
| Agents    | Standards: `constitution-expert`, `governance-layer-expert`, `care-implementation-expert`, `co-domain-expert`                                          |
| Agents    | Architecture: `care-platform-architect`                                                                                                                |
| Agents    | Publications: `publication-expert`                                                                                                                     |
| Skills    | Standards reference (26-eatp, 27-care, 28-coc, co-reference)                                                                                           |
| Skills    | Governance (29-constitution, 30-arxiv, 31-publication, 32-governance-layer, 33-care-implementation, 34-co-domain)                                      |
| Rules     | `zero-tolerance.md` (soft — RECOMMENDED), `agents.md` (RECOMMENDED)                                                                                    |
| Rules     | `constitution.md`, `publication-quality.md`, `arxiv-submission.md`, `governance-layer-positioning.md`, `co-domain-application.md`, `terrene-naming.md` |
| Hooks     | `validate-arxiv-content.js`, `validate-publication-content.js`                                                                                         |

**`start.md` orientation**: Research and governance. "The AI helps you research, draft, review, and publish."

**`analyze.md` framework**: Anchor document alignment, standards cross-reference, governance precedents, regulatory context.

**`redteam.md` approach**: Adversarial governance testing (constitutional capture, logical gaps, positioning integrity, strategic exposure).

---

### 3. Education / Course Development

Non-coding content creation. The AI helps design, write, and organize educational content.

**Examples**: Course platforms, training content, curriculum development

**Characteristics**:

- Primary output is educational content (courses, curricula, assessments)
- Pedagogical quality matters
- Audience awareness is critical
- May involve some code examples but the project itself isn't a software product

**Archetype-specific components**:

| Component | What to include                                                               |
| --------- | ----------------------------------------------------------------------------- |
| Commands  | Domain-specific commands for content types (lessons, assessments, modules)    |
| Agents    | Content specialists (pedagogy-expert, curriculum-designer, assessment-writer) |
| Agents    | Keep SDK agents if course content involves code examples                      |
| Skills    | Domain knowledge about the subject matter being taught                        |
| Rules     | Content quality rules, accessibility requirements                             |

**`start.md` orientation**: Content creation. "You describe the learning objectives, the AI designs the course."

**`analyze.md` framework**: Learning objectives, audience analysis, prerequisite mapping, assessment strategy.

**`redteam.md` approach**: Learner experience testing, knowledge gap analysis, assessment validity.

---

### 4. Platform (Hybrid)

Projects that implement governance standards in code. Part coding, part governance.

**Examples**: Standards-implementing platforms, governance-in-code projects

**Characteristics**:

- Writes code AND governance content
- Must align with CARE/EATP/CO standards
- Tests include both code tests and standards conformance

**Archetype-specific components**: Combine coding agents (tdd-implementer, testing-specialist) with standards experts (`co-reference` skill, `co-reference` skill). Use coding rules (strict no-stubs, testing) with governance-aware agent teams in commands.

---

## Setting Up a New Repo

### Step 1: Identify the archetype

What is the primary output? Code → Coding. Documents → Governance. Content → Education. Mix → Platform.

### Step 2: Copy the shared foundation

Every repo gets:

```
.claude/
├── commands/
│   ├── implement.md      # Core workflow (adapt agent teams)
│   ├── codify.md          # Core workflow (adapt agent teams)
│   ├── todos.md           # Core workflow (adapt expert consultation)
│   ├── start.md           # Write from scratch for this archetype
│   ├── analyze.md         # Write from scratch for this archetype
│   ├── redteam.md         # Write from scratch for this archetype
│   ├── ws.md              # Copy as-is
│   └── wrapup.md          # Copy as-is
├── agents/
│   ├── analyst.md           # Copy as-is
│   ├── analyst.md   # Copy as-is
│   ├── reviewer.md  # Copy as-is
│   ├── gold-standards-validator.md # Copy as-is
│   ├── security-reviewer.md      # Copy as-is
│   ├── open-source-strategist.md # Copy if relevant
│   └── management/
│       ├── todo-manager.md       # Copy as-is
│       ├── gh-manager.md         # Copy as-is
│       └── release-specialist.md # Copy as-is
├── rules/
│   ├── git.md                    # Copy as-is
│   └── security.md               # Write for this archetype
├── guides/
│   ├── claude-code/              # Copy as-is
│   └── co-setup/                 # Copy as-is (this guide)
└── settings.json                 # Configure hooks for this archetype
```

### Step 3: Add archetype-specific components

Add the commands, agents, skills, rules, and hooks from the archetype table above.

### Step 4: Write the three project-specific commands

- `start.md` — Orientation for this project type
- `analyze.md` — Research framework for this domain
- `redteam.md` — Testing/validation approach for this domain

### Step 5: Adapt shared commands

In `implement.md`, `codify.md`, and `todos.md`:

- Replace the **Agent Teams** section with agents appropriate to this project
- Keep the workflow structure (completion evidence, decision log, pattern observation) unchanged

### Step 6: Create the CLAUDE.md

Write a project-level CLAUDE.md that:

- Describes what this project is
- Lists available commands, agents, skills
- Sets project-specific conventions
- References the CO setup guide

## Canonical Source

The canonical source repository for shared CO components is:

- Shared components (utility commands, shared agents, guides)
- The CO setup guide itself
- Improvements to the core workflow commands (implement, codify, todos)

When improvements are made in the canonical source, they should be propagated to other repos using the process described in [04 - Propagation](04-propagation.md).
