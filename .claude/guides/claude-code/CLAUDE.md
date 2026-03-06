# Claude Code Setup - Framework Understanding Guide

## Purpose of This Document

This document serves as the **authoritative entry point** for understanding the Kailash Vibe CC Setup framework. It is designed for:

1. **Claude Code itself** - To understand the full context of how this setup works
2. **Developers** - To understand how to instruct and orchestrate Claude effectively
3. **Trainers** - To understand the mental model they should impart to new users

This document explains the **why** behind every design decision, the **philosophy** that drives the setup, and the **complete thought process** that should guide usage.

---

## Table of Contents

1. [The Core Philosophy](#the-core-philosophy)
2. [The Mental Model](#the-mental-model)
3. [System Architecture](#system-architecture)
4. [How Components Interact](#how-components-interact)
5. [The Orchestration Model](#the-orchestration-model)
6. [Best Practices for Instruction](#best-practices-for-instruction)
7. [Anti-Patterns to Avoid](#anti-patterns-to-avoid)
8. [The Learning Loop](#the-learning-loop)
9. [Quick Reference Tables](#quick-reference-tables)

---

## The Core Philosophy

### Philosophy 1: Specialization Over Generalization

Claude Code is a general-purpose AI assistant. This setup transforms it into a **specialized development partner** for Kailash SDK development. The philosophy is:

> "A specialized tool used correctly will outperform a general tool used generally."

This means:

- Every skill is focused on a specific domain
- Every agent has a defined responsibility
- Every hook enforces specific standards
- Claude doesn't guess - it delegates to specialists

**Practical Impact**: When you ask Claude to work with DataFlow, it doesn't try to figure out database operations from first principles. It uses the `dataflow-specialist` agent and the `02-dataflow` skill which contain proven patterns.

### Philosophy 2: Quality is Non-Negotiable

The setup enforces quality at multiple levels:

- **Hooks** block dangerous operations before they happen
- **Rules** define mandatory behaviors Claude must follow
- **Agents** provide specialized review and validation

> "Prevent problems rather than fix them."

**Practical Impact**: Claude cannot commit code without security review. Claude cannot use mocking in integration tests. These aren't suggestions - they're enforced.

### Philosophy 3: Real Infrastructure, Not Mocks

A core tenet of the Kailash development philosophy:

> "Integration and E2E tests use real databases, real APIs, real infrastructure. Mocking hides real-world issues."

This is encoded in:

- The `testing.md` rule file
- The `validate-workflow.js` hook
- The `12-testing-strategies` skill
- The `testing-specialist` agent

**Practical Impact**: When Claude writes tests, it will use SQLite in-memory databases instead of mock objects. It will make real HTTP calls instead of mocking responses.

### Philosophy 4: Continuous Learning

The setup learns from usage:

- Observations are logged during sessions
- Patterns are extracted into instincts
- High-confidence instincts evolve into skills
- The system gets better over time

> "Every session makes the next session better."

**Practical Impact**: If Claude notices you frequently use a specific pattern, it will eventually create a skill for that pattern, making future sessions more efficient.

### Philosophy 5: Explicit Over Implicit

Claude should be explicit about what it's doing and why:

> "NEVER USE DEFAULTS FOR FALLBACKS! Raise clear errors instead of returning defaults. Log all issues with context. Validate everything explicitly. Make debugging easier with informative messages."

**Practical Impact**: Claude will not silently fail. It will tell you what went wrong, why, and how to fix it.

---

## The Mental Model

### How to Think About Claude Code

Think of Claude Code as a **highly capable junior developer** with access to a **library of expert knowledge** (skills) and the ability to **consult specialists** (agents) when needed.

```
┌─────────────────────────────────────────────────────────────┐
│                      YOUR REQUEST                            │
│                  "Build a user CRUD API"                     │
└─────────────────────┬───────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     CLAUDE CODE                              │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Skills    │  │   Agents    │  │   Hooks     │         │
│  │ (Knowledge) │  │(Specialists)│  │(Enforcement)│         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│         ▼                ▼                ▼                 │
│  ┌─────────────────────────────────────────────────┐       │
│  │              INFORMED DECISION                   │       │
│  │  1. Use DataFlow (skill 02-dataflow)            │       │
│  │  2. Consult dataflow-specialist (agent)         │       │
│  │  3. Generate CRUD nodes                         │       │
│  │  4. Write tests (NO MOCKING - rule)             │       │
│  │  5. Deploy via Nexus (skill 03-nexus)           │       │
│  └─────────────────────────────────────────────────┘       │
│                                                              │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      YOUR RESULT                             │
│    Working CRUD API with tests and deployment config         │
└─────────────────────────────────────────────────────────────┘
```

### The Knowledge Hierarchy

```
         ┌─────────────────────────┐
         │      CLAUDE.md          │  ← Project-specific instructions
         │   (Project Context)     │
         └───────────┬─────────────┘
                     │
         ┌───────────▼─────────────┐
         │        Skills           │  ← Domain expertise
         │    (28 directories)     │
         └───────────┬─────────────┘
                     │
         ┌───────────▼─────────────┐
         │        Rules            │  ← Behavioral constraints
         │     (9 files)           │
         └───────────┬─────────────┘
                     │
         ┌───────────▼─────────────┐
         │        Hooks            │  ← Runtime enforcement
         │     (9 scripts)         │
         └───────────┬─────────────┘
                     │
         ┌───────────▼─────────────┐
         │       Agents            │  ← Specialized delegation
         │     (30 agents)         │
         └─────────────────────────┘
```

---

## System Architecture

### Directory Structure

```
.claude/
├── agents/              # 30 specialized sub-agents
│   ├── deep-analyst.md
│   ├── dataflow-specialist.md
│   ├── testing-specialist.md
│   └── ... (27 more)
│
├── commands/            # 19 slash commands
│   ├── sdk.md          # /sdk - Core SDK quick reference
│   ├── db.md           # /db - DataFlow quick reference
│   ├── api.md          # /api - Nexus quick reference
│   ├── analyze.md      # /analyze - Phase 01 workspace
│   ├── ws.md           # /ws - Workspace status dashboard
│   └── ... (10 more)
│
├── guides/              # This documentation
│   ├── README.md       # Navigation hub
│   ├── CLAUDE.md       # This file
│   └── 01-*.md         # Sequential guides
│
├── rules/               # 9 mandatory rule files
│   ├── agents.md       # Agent orchestration rules
│   ├── e2e-god-mode.md # E2E testing requirements
│   ├── env-models.md   # API keys & model names
│   ├── git.md          # Git workflow rules
│   ├── learned-instincts.md # Auto-generated instincts
│   ├── no-stubs.md     # No stubs/TODOs/placeholders
│   ├── patterns.md     # Kailash pattern rules
│   ├── security.md     # Security rules
│   └── testing.md      # Testing policies (NO MOCKING)
│
├── skills/              # 28 knowledge directories
│   ├── 01-core-sdk/    # Core SDK patterns
│   ├── 02-dataflow/    # DataFlow framework
│   ├── 03-nexus/       # Nexus multi-channel
│   ├── 04-kaizen/      # Kaizen AI agents
│   └── ... (24 more)
│
└── settings.json        # Hook configuration

scripts/
├── hooks/               # 9 automation scripts
│   ├── validate-bash-command.js
│   ├── validate-workflow.js
│   ├── session-start.js
│   └── ... (5 more)
│
├── ci/                  # 5 validation scripts
│   ├── validate-agents.js
│   ├── validate-skills.js
│   └── ... (3 more)
│
├── learning/            # 4 learning system scripts
│   ├── observation-logger.js
│   ├── instinct-processor.js
│   └── ... (2 more)
│
└── plugin/              # Distribution scripts
    └── build-plugin.js
```

### Component Purposes

| Component    | Purpose                        | When It's Used                                      |
| ------------ | ------------------------------ | --------------------------------------------------- |
| **Skills**   | Provide domain knowledge       | When Claude needs to understand how to do something |
| **Agents**   | Provide specialized processing | When a task requires deep expertise                 |
| **Hooks**    | Enforce constraints            | Before/after Claude takes actions                   |
| **Rules**    | Define mandatory behaviors     | Always (Claude reads these)                         |
| **Commands** | Quick access to skills         | When user types `/command`                          |

---

## How Components Interact

### Example: User Asks to Create a Database Model

```
User: "Create a User model with DataFlow"

1. CLAUDE RECEIVES REQUEST
   └── Reads project CLAUDE.md
   └── Sees: "For database operations, use DataFlow"

2. CLAUDE LOADS SKILL
   └── Loads /db command (02-dataflow skill)
   └── Learns: @db.model pattern, auto-generated nodes

3. CLAUDE DELEGATES TO AGENT (if complex)
   └── Invokes dataflow-specialist
   └── Gets: Best practices, gotchas, patterns

4. CLAUDE WRITES CODE
   └── Writes model definition
   └── POST-HOOK FIRES: validate-workflow.js
   └── Checks: Primary key named 'id'? No manual timestamps?

5. CLAUDE WRITES TESTS
   └── RULE APPLIED: testing.md
   └── NO MOCKING in Tier 2-3 tests
   └── Uses real SQLite database

6. CLAUDE OFFERS TO COMMIT
   └── RULE APPLIED: agents.md
   └── MUST delegate to security-reviewer
   └── MUST pass security audit before commit
```

### Example: User Runs a Dangerous Command

```
User: "Run rm -rf /"

1. CLAUDE PREPARES BASH TOOL
   └── About to execute: rm -rf /

2. PRE-TOOL-USE HOOK FIRES
   └── validate-bash-command.js runs
   └── Matches: /rm\s+-rf\s+\/(?!\w)/
   └── Returns: { continue: false, exitCode: 2 }

3. COMMAND BLOCKED
   └── Claude never executes the command
   └── User sees: "Blocked: rm -rf / (system destruction)"
```

---

## The Orchestration Model

### When to Use Each Component

| You Want To...                          | Use This                                              |
| --------------------------------------- | ----------------------------------------------------- |
| Quickly reference a pattern             | `/sdk`, `/db`, `/api`, `/ai`, `/test` commands        |
| Have Claude implement something complex | Just ask - Claude will delegate to appropriate agents |
| Enforce a new rule                      | Add to `.claude/rules/`                               |
| Add new knowledge                       | Add to `.claude/skills/`                              |
| Automate quality checks                 | Add to `scripts/hooks/`                               |

### Agent Selection Guide

Claude automatically selects agents based on task type. For reference:

| Task Type              | Primary Agent           | Secondary Agents           |
| ---------------------- | ----------------------- | -------------------------- |
| Database operations    | `dataflow-specialist`   | `testing-specialist`       |
| API deployment         | `nexus-specialist`      | `deployment-specialist`    |
| AI/ML features         | `kaizen-specialist`     | `pattern-expert`           |
| Complex planning       | `deep-analyst`          | `requirements-analyst`     |
| Code review            | `intermediate-reviewer` | `gold-standards-validator` |
| Security audit         | `security-reviewer`     | -                          |
| Test writing           | `tdd-implementer`       | `testing-specialist`       |
| Pattern implementation | `pattern-expert`        | `sdk-navigator`            |

### Instructing Claude Effectively

#### Good Instructions

```
"Create a user registration workflow using DataFlow for the
database and Nexus for the API. Include proper error handling
and write integration tests."
```

Why this works:

- Specifies frameworks (DataFlow, Nexus)
- Specifies requirements (error handling, tests)
- Clear deliverable (user registration workflow)

#### Poor Instructions

```
"Make a login thing"
```

Why this is poor:

- Ambiguous scope
- No framework guidance
- No quality requirements

### The Delegation Pattern

Claude follows this pattern for complex tasks:

```
1. ANALYZE
   └── What frameworks are needed?
   └── What agents should I consult?
   └── What rules apply?

2. PLAN
   └── Create todo list
   └── Break into steps
   └── Identify dependencies

3. EXECUTE
   └── Work through todos
   └── Delegate to specialists
   └── Validate with hooks

4. REVIEW
   └── Delegate to intermediate-reviewer
   └── Address findings
   └── Iterate if needed

5. DELIVER
   └── Present result
   └── Offer next steps
```

---

## Best Practices for Instruction

### Be Specific About Frameworks

Instead of: "Create a database"
Say: "Create a DataFlow model for users with PostgreSQL"

### Mention Quality Requirements

Instead of: "Add authentication"
Say: "Add authentication with security review and integration tests"

### Reference Known Patterns

Instead of: "Make an API"
Say: "Deploy a Nexus API with the user workflow"

### Use Commands for Context Loading

```
/sdk           # Load Core SDK patterns
/db            # Load DataFlow patterns
/api           # Load Nexus patterns
/ai            # Load Kaizen patterns
/test          # Load testing patterns
/validate      # Load gold standards
```

### Trust the Agent System

You don't need to specify which agent to use. Just describe the task:

```
"Review the security of this code before I commit"
→ Claude automatically uses security-reviewer

"Debug why this workflow isn't executing"
→ Claude automatically uses pattern-expert
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Bypassing Hooks

**Don't**: Try to disable or work around hooks
**Why**: Hooks enforce quality that prevents bugs

### Anti-Pattern 2: Ignoring Agent Recommendations

**Don't**: Dismiss intermediate-reviewer findings without addressing
**Why**: Code review catches issues you'll regret later

### Anti-Pattern 3: Rushing Past Planning

**Don't**: "Just write the code, skip the planning"
**Why**: Planning prevents rework and catches design issues

### Anti-Pattern 4: Using Mocks in Integration Tests

**Don't**: "Mock the database for this integration test"
**Why**: Mocks hide real issues; the rule system will flag this

### Anti-Pattern 5: Relative Imports

**Don't**: `from ..workflow import builder`
**Why**: Absolute imports are required; hooks will catch this

### Anti-Pattern 6: Skipping Security Review

**Don't**: "Commit without security review"
**Why**: Non-negotiable rule; prevents security vulnerabilities

---

## The Learning Loop

### How Learning Works

```
┌─────────────────────────────────────────────────────────────┐
│                   DURING SESSION                             │
│                                                              │
│   User Request → Claude Action → Observation Logged          │
│                                                              │
│   Example:                                                   │
│   "Create DataFlow model" → Uses @db.model pattern           │
│   → Logged: { pattern: "dataflow_model", success: true }     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   INSTINCT PROCESSING                        │
│                                                              │
│   Observations → Pattern Analysis → Instinct Formation       │
│                                                              │
│   Example:                                                   │
│   50 DataFlow observations → 90% use @db.model               │
│   → Instinct: "Prefer @db.model for DataFlow models"         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   EVOLUTION                                  │
│                                                              │
│   High-confidence Instincts → New Skills/Commands            │
│                                                              │
│   Example:                                                   │
│   Instinct (95% confidence) → New skill: "dataflow-models"   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Commands for Learning

```bash
/learn           # Log an observation manually
/evolve          # Process instincts into skills
/checkpoint      # Save current learning state
```

---

## Quick Reference Tables

### Essential Commands

#### Framework Commands

| Command     | Purpose           | When to Use                            |
| ----------- | ----------------- | -------------------------------------- |
| `/sdk`      | Core SDK patterns | Working with workflows, nodes, runtime |
| `/db`       | DataFlow patterns | Database operations, models, CRUD      |
| `/api`      | Nexus patterns    | API deployment, multi-channel          |
| `/ai`       | Kaizen patterns   | AI agents, signatures                  |
| `/test`     | Testing patterns  | Writing tests, 3-tier strategy         |
| `/validate` | Gold standards    | Checking compliance                    |

#### Workspace Phase Commands

| Command      | Purpose                   | When to Use                                 |
| ------------ | ------------------------- | ------------------------------------------- |
| `/analyze`   | Phase 01: Research & plan | Starting a new project                      |
| `/todos`     | Phase 02: Task breakdown  | Breaking plans into actionable todos        |
| `/implement` | Phase 03: Build           | Working through active todos                |
| `/redteam`   | Phase 04: Validate        | Red team testing with Playwright/Marionette |
| `/codify`    | Phase 05: Capture         | Creating project agents and skills          |
| `/ws`        | Status dashboard          | Checking workspace phase and progress       |
| `/wrapup`    | Session notes             | Saving context before ending a session      |

### Critical Rules

| Rule                          | Enforcement                 | Consequence         |
| ----------------------------- | --------------------------- | ------------------- |
| NO MOCKING in Tier 2-3        | `validate-workflow.js` hook | Test marked invalid |
| Security review before commit | `agents.md` rule            | Commit blocked      |
| Absolute imports only         | `validate-workflow.js` hook | Warning issued      |
| Use `.build()` before execute | `validate-workflow.js` hook | Warning issued      |

### Framework Selection

| Need              | Framework | Command |
| ----------------- | --------- | ------- |
| Custom workflows  | Core SDK  | `/sdk`  |
| Database CRUD     | DataFlow  | `/db`   |
| Multi-channel API | Nexus     | `/api`  |
| AI agents         | Kaizen    | `/ai`   |

---

## Summary

This setup transforms Claude Code from a general assistant into a specialized Kailash SDK development partner. It does this through:

1. **Skills** - Pre-loaded domain expertise
2. **Agents** - Specialized sub-processes for complex tasks
3. **Hooks** - Runtime enforcement of quality standards
4. **Rules** - Mandatory behavioral constraints
5. **Learning** - Continuous improvement from usage

The key to effective use is:

- Trust the system to enforce quality
- Be specific in your instructions
- Let Claude delegate to specialists
- Don't fight the rules - they prevent bugs

---

## Navigation

- **[README.md](README.md)** - Guide index and navigation
- **[01 - What is Claude Code?](01-what-is-claude-code.md)** - Next: Understanding Claude Code
