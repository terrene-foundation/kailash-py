---
paths:
  - ".claude/agents/**"
  - ".claude/skills/**"
  - ".claude/rules/**"
  - ".claude/commands/**"
  - "scripts/hooks/**"
---

# CC Artifact Quality Rules

### 1. Agent Descriptions Under 120 Characters

Include trigger phrases ("Use when...", "Use for...").

```yaml
# DO:
description: "CC artifact architect. Use for auditing, designing, or improving agents, skills, rules, commands, hooks."

# DO NOT:
description: "A comprehensive specialist for Claude Code architecture who can audit and improve all types of CC artifacts including agents, skills, rules, commands, and hooks across the entire ecosystem."
```

**Why:** Descriptions load into every agent selection decision. Long descriptions waste tokens on every turn.

### 2. Skills Follow Progressive Disclosure

SKILL.md MUST answer 80% of routine questions without requiring sub-file reads.

**Why:** Claude reads SKILL.md first. If it must read 5 additional files for basic answers, that's 5 unnecessary tool calls.

### 3. Rules Include DO/DO NOT Examples

Every MUST rule MUST include a concrete example showing both correct and incorrect pattern.

**Why:** Without examples, Claude interprets rules differently each session. Examples anchor consistent behavior.

### 4. Rules Include Rationale

Every MUST and MUST NOT rule MUST include a "**Why:**" line.

**Why:** Rationale enables Claude to apply the spirit of the rule in edge cases, not just the letter.

### 5. Commands Under 150 Lines

Move reference material to skills, review criteria to agents.

**Why:** Commands inject as user messages. Long commands compete with actual user intent.

### 6. CLAUDE.md Under 200 Lines

Contains repo-specific directives, absolute rules, and navigation tables. MUST NOT restate rules or embed reference material.

**Why:** CLAUDE.md loads on every turn. Every line beyond navigation and directives is wasted context.

### 7. Path-Scoped Rules Use `paths:` Frontmatter

Domain-specific rules MUST use `paths:` (not `globs:`) for YAML frontmatter scoping.

**Why:** `globs:` is not a recognized frontmatter key in Claude Code, so rules using it load on every file instead of being scoped, wasting context on irrelevant turns.

### 8. /codify Deploys claude-code-architect

Every `/codify` execution MUST include `claude-code-architect` in its validation team.

**Why:** Without artifact validation, `/codify` creates agents with 800-line knowledge dumps and unscoped rules.

### 9. Hooks Include Timeout Handling

Every hook MUST include a setTimeout fallback that returns `{ continue: true }` and exits.

```javascript
const TIMEOUT_MS = 5000;
const timeout = setTimeout(() => {
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);
```

**Why:** A hanging hook blocks the entire Claude Code session indefinitely.

### 10. New Rules Follow `rules/rule-authoring.md`

Every new rule MUST pass the "Loud, Linguistic, Layered" test from `rules/rule-authoring.md`: MUST/MUST NOT as primary modal, BLOCKED phrases for rationalizations, DO/DO NOT examples, `Why:` per clause, `paths:` frontmatter unless universal, `Origin:` line.

**Why:** Rules authored without the meta-rule score 2/6 on quality criteria (validated by subprocess test). With the meta-rule, 6/6. See `guides/deterministic-quality/01-rule-authoring-principles.md` for evidence.

## MUST NOT

- **No knowledge dumps**: Agent files ≤400 lines. Extract reference to skills.

**Why:** Oversized agent files are loaded into context on every delegation, consuming thousands of tokens that crowd out the actual task.

- **No CLAUDE.md duplication**: Skills and rules MUST NOT repeat CLAUDE.md content.

**Why:** Duplicated content loads twice per turn -- once from CLAUDE.md (always loaded) and once from the rule/skill -- doubling context cost for zero benefit.

- **No semantic analysis in hooks**: Hooks check structure; agents check semantics.

**Why:** Hooks run synchronously with hard timeouts; semantic analysis is slow and non-deterministic, causing spurious hook failures that block the session.

- **No BUILD artifacts in USE repos**: BUILD-specific agents, skills, rules waste context in downstream repos.

**Why:** BUILD artifacts reference source internals (module paths, test infra, CI config) that don't exist in USE repos, causing confusing errors and wasted tool calls.

- **No dangling cross-references**: After extracting/removing, grep for references and update them.

**Why:** Dangling references cause Claude to attempt reading non-existent files, wasting tool calls and producing hallucinated content to fill the gap.
