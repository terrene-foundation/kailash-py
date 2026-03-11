---
name: coc-sync-mapping
description: "Transformation rules for syncing BUILD repo artifacts to COC template. Used by coc-sync agent during /codify or on-demand sync."
---

# COC Sync Mapping

## Core Principle

This BUILD repo (`kailash_python_sdk`) has ONE set of agents, skills, rules, and commands. Everything syncs to the COC template (`kailash-coc-claude-py`) with transforms applied. There is no separate "user" set — just transformed copies of what's here.

## Architecture Rules

1. **This is the pure Python SDK BUILD repo** — independent from the Rust SDK BUILD repo (`~/repos/dev/kailash/`). Each has its own coc-sync that manages its own COC template.
2. **NEVER delete COC-only files** — The COC template may have files not in this BUILD repo. These are legitimate template content.
3. **NEVER rsync --delete** — Sync is additive and update-only. Files in COC but not in BUILD are COC-only content, not stale.
4. **Fix in place** — COC-only files with content errors should be fixed using Edit, not deleted and recreated.

## Exclusions (never sync)

| File/Directory                          | Reason                                               |
| --------------------------------------- | ---------------------------------------------------- |
| `agents/management/coc-sync.md`         | Sync infrastructure (meta)                           |
| `skills/management/coc-sync-mapping.md` | Sync infrastructure (meta)                           |
| `rules/learned-instincts.md`            | Auto-generated per repo                              |
| `learning/`                             | Per-repo learning data (observations, evolution log) |

## Transform Categories

### Category 1: As-Is (no transform needed)

Files with no builder-specific content. Copy directly.

**Agents:**

- `agents/frontend/*` — All frontend agents
- `agents/standards/*` — All standards agents (care-expert, coc-expert, eatp-expert)
- `agents/_subagent-guide.md`
- `agents/e2e-runner.md`
- `agents/value-auditor.md`
- `agents/build-fix.md`
- `agents/gold-standards-validator.md`
- `agents/security-reviewer.md`
- `agents/documentation-validator.md`
- `agents/management/gh-manager.md`
- `agents/management/todo-manager.md`

**Skills:**

- `skills/06-cheatsheets/` through `skills/28-coc-reference/` (most of these)
- `skills/08-nodes-reference/`, `skills/09-workflow-patterns/`
- `skills/11-frontend-integration/`, `skills/13-architecture-decisions/`
- `skills/14-code-templates/`, `skills/15-error-troubleshooting/`
- `skills/16-validation-patterns/`, `skills/17-gold-standards/`
- `skills/18-security-patterns/`, `skills/19-flutter-patterns/`
- `skills/20-interactive-widgets/` through `skills/28-coc-reference/`

**Commands:** All commands sync as-is except `codify.md` (see Category 2).

**Rules:**

- `rules/env-models.md`, `rules/git.md`, `rules/security.md`, `rules/e2e-god-mode.md`

**Other:**

- `guides/`, `settings.json`

### Category 2: Strip Builder Paths

Files that reference internal source code paths. Remove lines/paragraphs containing builder paths, keep everything else.

| File/Directory                                | Patterns to Strip                                                                |
| --------------------------------------------- | -------------------------------------------------------------------------------- |
| `agents/deep-analyst.md`                      | `src/kailash/`, `apps/kailash-*`                                                 |
| `agents/pattern-expert.md`                    | `src/kailash/`                                                                   |
| `agents/sdk-navigator.md`                     | `# contrib (removed)/`                                                              |
| `agents/requirements-analyst.md`              | `# contrib (removed)/`                                                              |
| `agents/intermediate-reviewer.md`             | `# contrib (removed)/`                                                              |
| `agents/framework-advisor.md`                 | Internal module references                                                       |
| `agents/tdd-implementer.md`                   | `tests/utils/test-env`                                                           |
| `agents/testing-specialist.md`                | `tests/utils/test-env`                                                           |
| `agents/deployment-specialist.md`             | Internal infrastructure references                                               |
| `agents/management/git-release-specialist.md` | PyPI/version internal references                                                 |
| `agents/frameworks/dataflow-specialist.md`    | `packages/kailash-dataflow/src/`, internal class names                               |
| `agents/frameworks/nexus-specialist.md`       | `packages/kailash-nexus/src/`                                                        |
| `agents/frameworks/kaizen-specialist.md`      | `packages/kailash-kaizen/src/`                                                       |
| `agents/frameworks/mcp-specialist.md`         | Internal references                                                              |
| `skills/01-core-sdk/`                         | `src/kailash/`                                                                   |
| `skills/02-dataflow/`                         | `packages/kailash-dataflow/src/`                                                     |
| `skills/03-nexus/`                            | Internal references                                                              |
| `skills/04-kaizen/`                           | `packages/kailash-kaizen/src/`                                                       |
| `skills/05-kailash-mcp/`                      | Internal references                                                              |
| `skills/10-deployment-git/`                   | Internal CI references                                                           |
| `skills/12-testing-strategies/`               | Internal test infra references                                                   |
| `rules/patterns.md`                           | `src/kailash/` internal references                                               |
| `commands/codify.md`                          | Rewrite: output to `agents/project/`, `skills/project/` (user codification dirs) |

### Category 3: Fix Absolute Paths

Files with hardcoded absolute paths that must become relative.

| File/Directory | Pattern                                        | Replace With      |
| -------------- | ---------------------------------------------- | ----------------- |
| Any file       | `./` | (remove entirely) |

### Category 4: Rule Softening

Rules that enforce strict builder policies need softening for users.

| Rule                | What to Change                                                                                      |
| ------------------- | --------------------------------------------------------------------------------------------------- |
| `rules/agents.md`   | Rule 1: "MUST delegate to intermediate-reviewer" → "SHOULD delegate" / "RECOMMENDED"                |
| `rules/agents.md`   | Rule 2: "MUST delegate to security-reviewer... Exception: NONE" → "RECOMMENDED... Users may skip"   |
| `rules/agents.md`   | "PROHIBITED: Skip Code Review" → "RECOMMENDED: Code Review"                                         |
| `rules/agents.md`   | "PROHIBITED: Commit Without Security Review" → "RECOMMENDED: Security Review Before Commit"         |
| `rules/testing.md`  | "NO MOCKING in Tier 2/3" → Remove restriction, users can mock                                       |
| `rules/testing.md`  | "MUST NOT use mocks, stubs, or fakes in Tier 2-3" → Remove or soften to recommendation              |
| `rules/no-stubs.md` | "MUST NOT contain TODO, FIXME" → "SHOULD NOT contain in production code"                            |
| `rules/no-stubs.md` | "No Deferred Implementation" → Soften: users iterating may defer                                    |
| `rules/git.md`      | "Non-negotiable" security review reference → "strongly recommended" (must match softened agents.md) |

**Downstream files** that echo rule language must also be softened:

| File                           | What to Change                                                              |
| ------------------------------ | --------------------------------------------------------------------------- |
| `guides/claude-code/CLAUDE.md` | Replace "NO MOCKING", "MUST delegate", "Non-negotiable" with softened forms |
| `skills/04-kaizen/SKILL.md`    | Replace "NO MOCKING", "NEVER mock" with "real infrastructure recommended"   |

### Category 5: CLAUDE.md Rewrite

The root `CLAUDE.md` needs the most transformation:

| Section                 | Transform                                                                                                                                                |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Title/intro             | "COC setup for Claude Code" → "COC setup for building with the Kailash SDK"                                                                              |
| Directive 4             | "Mandatory Reviews" → "Recommended Reviews"                                                                                                              |
| Directive 4 code review | "MUST" → "RECOMMENDED"                                                                                                                                   |
| Directive 4 security    | "NO exceptions" → "strongly encouraged"                                                                                                                  |
| Directive 4 NO MOCKING  | Remove or soften to recommendation                                                                                                                       |
| Rules Index             | Update scope descriptions if rules were softened                                                                                                         |
| Keep unchanged          | Framework-First, .env, Implement Don't Document, Critical Execution Rules, Kailash Platform table, Agents listing, Skills Navigation, Workspace Commands |

## Global Patterns

These patterns are stripped from ALL files during sync (not just the ones listed above):

### Always Remove

```
src/kailash/                              # Internal SDK source
packages/kailash-dataflow/src/                # Internal DataFlow source
packages/kailash-kaizen/src/                  # Internal Kaizen source
packages/kailash-nexus/src/                   # Internal Nexus source
# contrib (removed)/                         # Builder-only docs
tests/utils/test-env                      # Internal test infrastructure
./  # Absolute paths
```

### Always Remove (Internal Class Names)

These are SDK internals users never interact with. Remove references (not import examples):

```
SyncDDLExecutor
TypeAwareFieldProcessor
DataFlowWorkflowBinder
TenantContextSwitch
```

### Always Preserve

```
from kailash.workflow.builder import WorkflowBuilder   # User-facing import
from kailash.runtime import LocalRuntime                # User-facing import
from dataflow import DataFlow                           # User-facing import
.claude/skills/                                         # Relative references
.claude/agents/                                         # Relative references
pip install kailash                                     # User-facing
runtime.execute(workflow.build())                       # User-facing pattern
```

## Known Contamination Counts

As of 2026-03-07 audit, all builder contamination has been cleaned:

| Pattern                                    | Before | After | Fix Applied                            |
| ------------------------------------------ | ------ | ----- | -------------------------------------- |
| Absolute paths `./repos/...`  | 44     | 0     | Stripped or converted to relative      |
| `apps/kailash-*/` internal app paths       | 96     | 0     | Stripped `apps/` prefix or genericized |
| `src/kailash/` internal source paths       | 24     | 0     | Converted to `kailash/` package path   |
| `# contrib (removed)/` references             | 5      | 0     | Replaced with prose references         |
| Internal class names                       | 2      | 0     | Replaced with public-facing names      |
| Rule softening (agents, testing, no-stubs) | 3      | 0     | MUST→SHOULD, strict→recommended        |
| CLAUDE.md builder framing                  | 1      | 0     | Rewritten for user context             |
