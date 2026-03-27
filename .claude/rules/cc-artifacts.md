---
paths:
  - ".claude/agents/**"
  - ".claude/skills/**"
  - ".claude/rules/**"
  - ".claude/commands/**"
  - "scripts/hooks/**"
---

# CC Artifact Quality Rules

## Scope

These rules apply when creating or modifying CC artifacts (agents, skills, rules, commands, hooks).

## MUST Rules

### 1. Agent Descriptions Under 120 Characters

Agent description fields MUST be under 120 characters and include trigger phrases ("Use when...", "Use for...").

```yaml
# DO:
description: "CC artifact architect. Use for auditing, designing, or improving agents, skills, rules, commands, hooks."

# DO NOT:
description: "A comprehensive specialist for Claude Code architecture who can audit and improve all types of CC artifacts including agents, skills, rules, commands, and hooks across the entire ecosystem."
```

**Why**: Descriptions are loaded into every agent selection decision. Long descriptions waste tokens on every turn.

### 2. Skills Follow Progressive Disclosure

SKILL.md MUST answer 80% of routine questions without requiring sub-file reads. Deep reference goes in separate files.

```markdown
# DO: SKILL.md has quick reference tables + key patterns

## Quick Reference

| Pattern | Usage |
| ------- | ----- |
| ...     | ...   |

# DO NOT: SKILL.md just says "see subdirectory files"

See the files in this directory for details.
```

**Why**: Claude reads SKILL.md first. If it must read 5 additional files for basic answers, that's 5 unnecessary tool calls.

### 3. Rules Include DO/DO NOT Examples

Every MUST rule MUST include a concrete example showing both the correct and incorrect pattern.

```markdown
# DO: Rule with example

### 1. Use Parameterized Queries

``python

# DO:

cursor.execute("SELECT \* FROM users WHERE id = ?", (user_id,))

# DO NOT:

cursor.execute(f"SELECT \* FROM users WHERE id = {user_id}")
``

# DO NOT: Rule without example

### 1. Use Parameterized Queries

All queries must use parameterized queries.
```

**Why**: Without examples, Claude interprets rules differently each session. Examples anchor consistent behavior.

### 4. Rules Include Rationale

Every MUST and MUST NOT rule MUST include a "**Why**:" line.

**Why**: Rationale enables Claude to apply the spirit of the rule in edge cases, not just the letter.

### 5. Commands Under 150 Lines

Command files MUST stay under 150 lines. Move reference material to skills and review criteria to agents.

**Why**: Commands inject as user messages. Long commands compete with actual user intent in the token budget.

### 6. CLAUDE.md Must Be Lean

CLAUDE.md MUST stay under 200 lines. It contains 3-5 repo-specific directives, absolute rules, and navigation tables. It MUST NOT restate rules (they load separately) or embed reference material.

```markdown
# DO: CLAUDE.md with repo identity + navigation + 3 absolute directives (~120 lines)

## Absolute Directives

### 1. [Repo-specific directive]

## Rules Index

| Rule | File | Scope |

## Agents

- **specialist** — Use for X

# DO NOT: CLAUDE.md restating every rule (~600 lines)

## Security Rules

All queries must use parameterized queries... [repeats security.md]

## Testing Rules

Use 3-tier testing... [repeats testing.md]
```

**Why**: CLAUDE.md loads on every turn. Every line beyond navigation and directives is wasted context. Rules have their own files.

### 7. Path-Scoped Rules Use `paths:` Frontmatter

Domain-specific rules MUST use `paths:` (not `globs:`) as the YAML frontmatter key.

```yaml
# DO:
---
paths:
  - "**/db/**"
  - "**/infrastructure/**"
---
# DO NOT:
---
globs:
  - "**/db/**"
---
```

**Why**: `paths:` is the Claude Code documented key for rule file scoping. `globs:` is not recognized.

### 8. /codify Deploys claude-code-architect

Every `/codify` execution MUST include `claude-code-architect` in its validation team. All new or modified artifacts MUST be validated against cc-artifacts rules before completion.

**Why**: Without artifact validation, `/codify` creates agents with 800-line knowledge dumps, unscoped rules, and commands that exceed 150 lines — compounding token waste across every future session.

### 9. Hooks Include Timeout Handling

Every hook MUST include a setTimeout fallback that returns `{ continue: true }` and exits.

```javascript
// DO:
const TIMEOUT_MS = 5000;
const timeout = setTimeout(() => {
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);

// DO NOT:
// (no timeout — hook hangs indefinitely if processing stalls)
```

**Why**: A hanging hook blocks the entire Claude Code session indefinitely.

## MUST NOT Rules

### 1. No Knowledge Dumps in Agents

Agent files MUST NOT exceed 400 lines. Extract reference material to a skill directory.

```
# DO: Agent (200 lines) references skill
## Full Documentation
- `.claude/skills/30-claude-code-patterns/` — CC architecture reference

# DO NOT: Agent (600 lines) embeds the entire reference
## CC Architecture
[... 400 lines of reference material ...]
```

**Why**: Agent context competes with task context. Embedded reference loads on every invocation.

### 2. No Duplicating CLAUDE.md in Skills or Rules

Skills and rules MUST NOT repeat instructions already present in CLAUDE.md.

**Why**: CLAUDE.md is always loaded. Duplicating it doubles the token cost with zero benefit.

### 3. No Global Rules That Should Be Path-Scoped

Rules about domain-specific patterns MUST use YAML frontmatter `paths:` scoping.

```yaml
# DO: Scoped rule (loads only when editing matching files)
---
paths:
  - "src/db/**"
  - "migrations/**"
---
# DO NOT: Global rule about SQL (loads when editing CSS, README, etc.)
# (no frontmatter — rule loads every turn)
```

**Why**: A 400-token SQL rule loading on every turn when editing CSS is pure waste.

### 4. No Semantic Analysis in Hooks

Hooks MUST NOT attempt to understand code meaning via regex. Hooks check structure; agents check semantics.

**Why**: Regex-based semantic analysis is brittle and produces false positives.

**Permitted exception**: `pre-compact.js` uses regex to detect which framework is in use (DataFlow/Nexus/Kaizen/Core SDK) for context preservation during compaction. This is structural tagging for checkpoint data, not agent decision-making — the hook never routes, classifies intent, or changes behavior based on the detection. Accepted per decision D1 in journal/0009.

### 5. No BUILD Artifacts in USE Repos

USE repo COC templates (coc-claude-py, coc-claude-rs) MUST NOT contain BUILD-specific artifacts:

```
# BUILD-only (remove from USE repos):
- agents/frontend/          # BUILD repos don't do frontend work
- rules/cross-sdk-inspection.md  # BUILD-only process rule
- skills/*-bindings/        # Internal binding code patterns
- skills/*-enterprise/      # Internal crate documentation
- skills/*-governance/      # Internal governance crate docs

# USE-only (keep in USE repos, remove from BUILD):
- rules/deployment.md (cloud deployment version)
- agents/deployment-specialist.md (cloud deployment)
```

**Why**: BUILD artifacts (SDK internals, binding patterns, crate docs) waste context in USE repos where developers build applications. USE artifacts (cloud deployment, user-facing patterns) waste context in BUILD repos where developers write SDK code.

### 6. No Dangling Cross-References After Extraction

When extracting reference material from agents/commands to skills, MUST verify all cross-references in the trimmed file still point to existing files. When removing skills/agents from a repo, MUST grep for references in remaining files and update them.

```
# DO: After removing skills/10-governance/ from coc-claude-rs
grep -r "10-governance" coc-claude-rs/.claude/agents/  # Find references
# Update each reference to point to existing alternative

# DO NOT: Remove a skill directory without checking for references
rm -rf skills/10-governance/  # Leaves dangling refs in agent files
```

**Why**: Dangling references cause file-not-found errors when agents try to load referenced skills, degrading agent performance.

## Cross-References

- `.claude/skills/30-claude-code-patterns/` — Full CC architecture patterns
- `.claude/agents/claude-code-architect.md` — CC artifact specialist
- `.claude/guides/co-setup/03-creating-components.md` — Component creation guide
