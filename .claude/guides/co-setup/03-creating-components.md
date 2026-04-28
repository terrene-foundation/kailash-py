# Creating CO Components

How to create each component type for any domain.

## Agents

**Location** depends on repo type:

- **BUILD repos** (kailash-py, kailash-rs, kailash-prism): `.claude/agents/frameworks/`, `.claude/agents/analysis/`, `.claude/agents/quality/`, etc. (canonical locations). `/codify` in a BUILD repo writes to these canonical locations and creates an upstream proposal for loom/.
- **Downstream USE repos** (consumer project repos that `pip install kailash`): `.claude/agents/project/` for project-specific agents. `/codify` stays local — no upstream proposal.
- **loom/**: `.claude/agents/` with subdirectories (`analysis/`, `frameworks/`, `implementation/`, `quality/`, `release/`, `testing/`, `frontend/`). No `project/` subdirectory — loom/ is the authority, not a project.

**Purpose**: Specialized sub-processes with deep domain knowledge and procedural directives.

**When to create**: When a task area requires deep expertise that goes beyond what skills can provide — judgment, multi-step procedures, or cross-cutting concerns.

### Agent Template

```markdown
---
name: agent-name
description: One-line description of when to use this agent. Include trigger keywords.
model: inherit
allowed-tools:
  - Read
  - Glob
  - Grep
---

# Agent Title

You are an expert in [domain]. Your knowledge covers [scope].

## Authoritative Sources

List the files this agent should read first, in priority order.

## Core Concepts You Must Know

Distilled knowledge the agent needs to operate. Not a copy of docs — the judgment framework for using docs.

## How to Respond

Procedural directives for the agent's behavior.

## Related Experts

When to hand off to other agents.
```

### Best Practices

- **Name describes the specialty**, not the task: `security-reviewer` not `review-security`
- **Description includes trigger phrases**: "Use this agent for questions about X, Y, or Z"
- **Authoritative sources are ordered**: PRIMARY first, then SECONDARY, then REFERENCE
- **Core concepts are for judgment**, not facts: "Distinguish traceability from accountability" not "EATP has 5 elements"
- **Use `model: inherit`** unless the agent needs a different model tier

---

## Skills

**Location** depends on repo type:

- **BUILD repos** and **loom/**: `.claude/skills/<number>-<name>/` with `SKILL.md` entry point (canonical numbered skill directories, e.g., `skills/01-core-sdk/`, `skills/02-dataflow/`). `/codify` updates these in place.
- **Downstream USE repos**: `.claude/skills/project/<name>/` for project-specific skills. `/codify` stays local.

**Purpose**: Distilled domain knowledge that agents reference. The institutional handbook.

**When to create**: When domain knowledge needs to be available on demand, structured for progressive disclosure.

### Skill Template

```markdown
---
name: skill-name
description: One-line description. Triggers when this knowledge is needed.
allowed-tools:
  - Read
  - Glob
  - Grep
---

# Skill Title

Brief overview of what this skill covers.

## Quick Reference

The most critical information in compact form.

## Key Concepts

Core concepts with just enough detail to act on.

## For Detailed Information

Pointers to full documentation.
```

### Best Practices

- **SKILL.md is the entry point** — it should be self-contained for common tasks
- **Additional files in the same directory** for deep reference
- **Reference docs, don't repeat them** — skills point to authoritative sources
- **50-250 lines per file** — if it's longer, split into multiple files
- **No subdirectories** within a skill directory

---

## Rules

**Location**: `.claude/rules/`

**Purpose**: Behavioral constraints the AI reads and follows every session. Soft enforcement (CO L3 Tier 1).

**When to create**: When a behavior needs to be consistent across all sessions, regardless of which agent is active.

### Rule Template

```markdown
# Rule Title

## Scope

When this rule applies (all files, specific directories, specific file types).

## MUST Rules (or RECOMMENDED Rules)

### 1. Rule Name

Description of the rule.

**Correct**: Example of correct behavior
**Incorrect**: Example of incorrect behavior

## MUST NOT Rules

### 1. Rule Name

What to avoid and why.

## Exceptions

When this rule doesn't apply.
```

### Best Practices

- **Coding repos use MUST/MUST NOT** — strict enforcement for production code
- **Non-coding repos use RECOMMENDED/SHOULD** — softer enforcement for governance work
- **Scope section is critical** — without it, rules apply everywhere and cause friction
- **Include examples** — abstract rules are hard to follow; concrete examples are clear
- **Keep rules independent** — each rule file should be self-contained

---

## Commands

**Location**: `.claude/commands/`

**Purpose**: Structured workflows invoked by `/command-name`. CO L4 implementation.

### Command Template

```markdown
---
name: command-name
description: "One-line description shown in /help"
---

## What This Phase Does (present to user)

Plain-language description of what happens when this command runs.

## Your Role (communicate to user)

What the user needs to do (answer questions, approve plans, review results).

## Workspace Resolution

How to determine which workspace to operate on.

## Phase Check

Pre-conditions and output locations.

## Workflow

### 1. Step name

What to do in this step.

### 2. Step name

...

## Agent Teams

Which agents to deploy for this workflow.
```

### Best Practices

- **"What This Phase Does" and "Your Role"** — always present, always in plain language
- **Workflow steps are numbered** — clear sequence with approval gates
- **Agent Teams section at the end** — lists which agents to deploy, organized by function
- **Completion evidence** — every workflow that produces deliverables should require evidence before closing
- **Decision log** — every workflow that involves user decisions should capture them

### The Core Workflow

Every project has these 5+1 commands:

| Command      | Phase | Purpose                                  |
| ------------ | ----- | ---------------------------------------- |
| `/analyze`   | 01    | Research and validate before execution   |
| `/todos`     | 02    | Create roadmap; stops for human approval |
| `/implement` | 03    | Execute one task at a time; repeat       |
| `/redteam`   | 04    | Stress-test and validate                 |
| `/codify`    | 05    | Capture knowledge for future sessions    |
| `/ws`        | —     | Check progress anytime                   |

Plus `/wrapup` (session notes).

---

## Hooks

**Location**: `.claude/hooks/` with registration in `.claude/settings.json`

**Purpose**: Deterministic enforcement outside the AI's context. CO L3 Tier 2.

### Hook Types

| Hook Event         | When It Fires              | Use Case                          |
| ------------------ | -------------------------- | --------------------------------- |
| `UserPromptSubmit` | Every user message         | Anti-amnesia rule injection       |
| `PreToolUse`       | Before a tool runs         | Block dangerous operations        |
| `PostToolUse`      | After a tool runs          | Validate output, remind of rules  |
| `PreCompact`       | Before context compression | Save state, remind of workspace   |
| `SessionStart`     | Session begins             | Load context, detect project type |
| `Stop`             | Session ends               | Persist state, write metrics      |

### Hook Template (JavaScript)

```javascript
// .claude/hooks/hook-name.js
const fs = require("fs");
const path = require("path");

// Read input from stdin
const input = JSON.parse(fs.readFileSync("/dev/stdin", "utf8"));

// Hook logic here
// Access: input.tool_name, input.tool_input, input.session_id, etc.

// Output result
const result = {
  // For PreToolUse: { continue: true/false, reason: "..." }
  // For PostToolUse: { message: "..." } or empty
  // For UserPromptSubmit: { message: "..." } to inject context
};

console.log(JSON.stringify(result));
```

### Registration in settings.json

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "node .claude/hooks/user-prompt-rules-reminder.js"
      }
    ],
    "PreToolUse": [
      {
        "type": "command",
        "command": "node .claude/hooks/validate-bash-command.js",
        "matcher": { "tool_name": "Bash" }
      }
    ]
  }
}
```

### Best Practices

- **Hooks are deterministic** — no AI judgment, no probabilistic behavior
- **Fast execution** — hooks run on every interaction; keep them under 100ms
- **Fail open for non-critical hooks** — if the hook crashes, don't block the workflow
- **Fail closed for security hooks** — if the security hook crashes, block the action
- **Anti-amnesia is the most important hook** — re-inject critical rules every interaction

---

## The CLAUDE.md File

**Location**: Project root

**Purpose**: The master directive. Loaded at the start of every session. CO L2 entry point.

### What to include

1. **What this project is** — one paragraph
2. **Absolute directives** — the 3-5 strongly recommended rules
3. **Available commands** — table with phase and purpose
4. **Available agents** — organized by function
5. **Available skills** — organized by domain
6. **Key file locations** — where to find important content
7. **Project-specific conventions** — terminology, naming, licensing

### What NOT to include

- Implementation details (those go in skills and docs)
- Full agent descriptions (those go in agent files)
- Lengthy explanations (keep it concise — this is loaded every session)
