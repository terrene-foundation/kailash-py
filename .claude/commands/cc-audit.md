---
name: cc-audit
description: "Audit CC artifacts for quality, completeness, effectiveness, and token efficiency"
---

# CC Artifact Audit

## What This Does

Systematically reviews all Claude Code artifacts (agents, skills, rules, commands, hooks) for quality across four dimensions: competency, completeness, effectiveness, and token efficiency.

## Your Role

Specify scope: audit everything, or target a specific artifact type or file.

## Workflow

1. **Scope determination**: If no scope specified, audit all artifact types. Otherwise focus on the requested scope.

2. **Inventory**: List all artifacts in scope with file paths and line counts.

3. **Audit each artifact** using the claude-code-architect agent's four-dimension framework:
   - **Competency**: Does it know what it claims? Are instructions precise?
   - **Completeness**: Are there gaps? Edge cases? Missing handoffs?
   - **Effectiveness**: Does it produce reliable behavior? Is the output format specified?
   - **Token Efficiency**: Is it lean? Path-scoped? No redundancy?

4. **Cross-reference check**: Verify all referenced artifacts exist. Flag orphans and broken links.

5. **Token budget analysis**: Calculate baseline per-turn token cost (CLAUDE.md + global rules + agent descriptions).

6. **Report**: Produce findings sorted by severity (CRITICAL → HIGH → NOTE) with specific fix recommendations.

## Agent Teams

| Function                     | Agent                    |
| ---------------------------- | ------------------------ |
| Audit execution              | claude-code-architect    |
| Standards compliance         | gold-standards-validator |
| Cross-reference verification | intermediate-reviewer    |

## Completion Evidence

- Audit report with dimension scores for each artifact
- Token budget summary
- Prioritized fix list with CRITICAL/HIGH/NOTE severity
