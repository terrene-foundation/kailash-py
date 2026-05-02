---
priority: 20
scope: excluded
exclude_from: [codex, gemini]
paths:
  - ".claude/agents/**"
  - ".claude/skills/**"
  - ".claude/commands/**"
  - ".claude/hooks/**"
---

# CC Artifact Quality Rules

<!-- slot:neutral-body -->

CC-specific residue. Runtime-neutral artifact quality (DO/DO NOT examples, Why: rationale, Loud/Linguistic/Layered test, dangling cross-references) lives in `rules/rule-authoring.md`; cross-CLI artifact rules live in `rules/variant-authoring.md`. See those for the general principles.

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

### 3. Commands Under 150 Lines

Move reference material to skills, review criteria to agents.

**Why:** Commands inject as user messages. Long commands compete with actual user intent.

### 4. CLAUDE.md Under 200 Lines

Contains repo-specific directives, absolute rules, and navigation tables. MUST NOT restate rules or embed reference material.

**Why:** CLAUDE.md loads on every turn. Every line beyond navigation and directives is wasted context.

### 5. Path-Scoped Rules Use `paths:` Frontmatter

Domain-specific rules MUST use `paths:` (not `globs:`) for YAML frontmatter scoping.

**Why:** `globs:` is not a recognized frontmatter key in Claude Code, so rules using it load on every file instead of being scoped, wasting context on irrelevant turns.

### 6. /codify Deploys cc-architect

Every `/codify` execution MUST include `cc-architect` in its validation team.

**Why:** Without artifact validation, `/codify` creates agents with 800-line knowledge dumps and unscoped rules.

### 7. Hooks Include Timeout Handling

Every hook MUST include a setTimeout fallback that returns `{ continue: true }` and exits.

```javascript
const TIMEOUT_MS = 5000;
const timeout = setTimeout(() => {
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);
```

**Why:** A hanging hook blocks the entire Claude Code session indefinitely.

### 8. Workspace-Walking Hooks Filter Leading-Underscore Meta-Dirs

Hooks that enumerate `workspaces/<name>/` MUST filter directories whose name starts with underscore (`_archive`, `_template`, `_draft`, etc.) alongside the existing `instructions` skip. Pattern: `entries.filter(e => e.isDirectory() && e.name !== "instructions" && !e.name.startsWith("_"))`. Same filter applies in any `for ... of entries` loop that walks the workspaces directory.

```javascript
// DO — filter both `instructions` and leading-underscore meta-dirs
const projects = entries.filter(
  (e) =>
    e.isDirectory() && e.name !== "instructions" && !e.name.startsWith("_"),
);

// DO NOT — filter only `instructions` (leaves `_archive`, `_template` to surface as active)
const projects = entries.filter(
  (e) => e.isDirectory() && e.name !== "instructions",
);
```

**BLOCKED rationalizations:**

- "`_archive` is rarely the most-recent dir, the bug is theoretical"
- "We'll add the filter when someone hits the failure mode"
- "The hook only runs at SessionStart, low blast radius"
- "Operators can rename `_archive` to something else"

**Why:** Archival operations (`git mv workspaces/X workspaces/_archive/X`) bump `_archive/`'s mtime to most-recently-modified; without the filter, `detectActiveWorkspace` surfaces `_archive` as the active workspace, and `SessionEnd` routes journal stubs into `workspaces/_archive/journal/.pending/` — invisible drift the next session must triage. The same failure mode applies to `findAllSessionNotes` (SessionStart drift dashboards). Leading-underscore is the convention for workspace meta-dirs (`_archive`, `_template`, future `_draft`); filtering by prefix makes the contract durable as new meta-dir conventions emerge.

Origin: kailash-rs PR #759 (2026-05-02) — `git mv` of 4 workspaces into `_archive/` caused 3 SessionEnd stubs to land in `workspaces/_archive/journal/.pending/`. Fix landed at `.claude/hooks/lib/workspace-utils.js::detectActiveWorkspace` + `findAllSessionNotes`. Codified GLOBAL via /sync rs Gate 1 (2026-05-02 second cycle).

## MUST NOT

- **No knowledge dumps**: Agent files ≤400 lines. Extract reference to skills.

**Why:** Oversized agent files are loaded into context on every delegation, consuming thousands of tokens that crowd out the actual task.

- **No CLAUDE.md duplication**: Skills and rules MUST NOT repeat CLAUDE.md content.

**Why:** Duplicated content loads twice per turn -- once from CLAUDE.md (always loaded) and once from the rule/skill -- doubling context cost for zero benefit.

- **No semantic analysis in hooks**: Hooks check structure; agents check semantics.

**Why:** Hooks run synchronously with hard timeouts; semantic analysis is slow and non-deterministic, causing spurious hook failures that block the session.

<!-- /slot:neutral-body -->
