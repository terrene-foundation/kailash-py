---
name: coc-sync-mapping
description: "Transformation rules for syncing BUILD repo artifacts to COC templates (Claude and Gemini). Used by coc-sync agent during /codify or on-demand sync."
---

# COC Sync Mapping

## Core Principle

This BUILD repo (`kailash_python_sdk`) has ONE set of agents, skills, rules, and commands. Everything syncs to the COC templates with transforms applied. There is no separate "user" set — just transformed copies of what's here.

Two sync targets exist:

| Target     | Template Repo           | Config Root            | Context File |
| ---------- | ----------------------- | ---------------------- | ------------ |
| **Claude** | `kailash-coc-claude-py` | `.claude/`             | `CLAUDE.md`  |
| **Gemini** | `kailash-coc-gemini-py` | `.gemini/` + `.agent/` | `GEMINI.md`  |

All transform categories below (Categories 1-5) apply to BOTH targets. The Gemini target additionally requires the transforms documented in the "Gemini-Specific Transforms" section at the end of this file.

## Architecture Rules

1. **This is the pure Python SDK BUILD repo** — independent from the Rust SDK BUILD repo (`kailash-rs/`). Each has its own coc-sync that manages its own COC template.
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

Files with no builder-specific content. Copy directly to Claude target. For Gemini target, these still require Gemini-specific transforms (tool names, path references) — see "Gemini-Specific Transforms" section.

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
- `skills/14-code-templates/`, `skills/31-error-troubleshooting/`
- `skills/16-validation-patterns/`, `skills/17-gold-standards/`
- `skills/18-security-patterns/`, `skills/19-flutter-patterns/`
- `skills/20-interactive-widgets/` through `skills/28-coc-reference/`

**Commands:** All commands sync as-is to Claude except `codify.md` (see Category 2). For Gemini, ALL commands require MD-to-TOML format conversion (see "Gemini-Specific Transforms").

**Rules:**

- `rules/env-models.md`, `rules/git.md`, `rules/security.md`, `rules/e2e-god-mode.md`

**Other:**

- `guides/`, `settings.json` (for Gemini: guides map to `.gemini/knowledge/`, settings.json requires hook event name remapping)

### Category 2: Strip Builder Paths

Files that reference internal source code paths. Remove lines/paragraphs containing builder paths, keep everything else.

| File/Directory                                | Patterns to Strip                                                                |
| --------------------------------------------- | -------------------------------------------------------------------------------- |
| `agents/deep-analyst.md`                      | `src/kailash/`, `apps/kailash-*`                                                 |
| `agents/pattern-expert.md`                    | `src/kailash/`                                                                   |
| `agents/sdk-navigator.md`                     | `# contrib (removed)/`                                                           |
| `agents/requirements-analyst.md`              | `# contrib (removed)/`                                                           |
| `agents/intermediate-reviewer.md`             | `# contrib (removed)/`                                                           |
| `agents/framework-advisor.md`                 | Internal module references                                                       |
| `agents/tdd-implementer.md`                   | `tests/utils/test-env`                                                           |
| `agents/testing-specialist.md`                | `tests/utils/test-env`                                                           |
| `agents/deployment-specialist.md`             | Internal infrastructure references                                               |
| `agents/management/git-release-specialist.md` | PyPI/version internal references                                                 |
| `agents/frameworks/dataflow-specialist.md`    | `packages/kailash-dataflow/src/`, internal class names                           |
| `agents/frameworks/nexus-specialist.md`       | `packages/kailash-nexus/src/`                                                    |
| `agents/frameworks/kaizen-specialist.md`      | `packages/kailash-kaizen/src/`                                                   |
| `agents/frameworks/mcp-specialist.md`         | Internal references                                                              |
| `skills/01-core-sdk/`                         | `src/kailash/`                                                                   |
| `skills/02-dataflow/`                         | `packages/kailash-dataflow/src/`                                                 |
| `skills/03-nexus/`                            | Internal references                                                              |
| `skills/04-kaizen/`                           | `packages/kailash-kaizen/src/`                                                   |
| `skills/05-kailash-mcp/`                      | Internal references                                                              |
| `skills/10-deployment-git/`                   | Internal CI references                                                           |
| `skills/12-testing-strategies/`               | Internal test infra references                                                   |
| `rules/patterns.md`                           | `src/kailash/` internal references                                               |
| `commands/codify.md`                          | Rewrite: output to `agents/project/`, `skills/project/` (user codification dirs) |

### Category 3: Fix Absolute Paths

Files with hardcoded absolute paths that must become relative.

| File/Directory | Pattern | Replace With      |
| -------------- | ------- | ----------------- |
| Any file       | ``      | (remove entirely) |

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

### Category 5: Context File Rewrite

#### CLAUDE.md (Claude target)

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

#### GEMINI.md (Gemini target)

Generated from the BUILD `CLAUDE.md` with ALL Claude transforms above PLUS these Gemini-specific transforms:

| Section               | Transform                                                                                |
| --------------------- | ---------------------------------------------------------------------------------------- |
| Title                 | "Kailash COC Claude (Python)" → "Kailash COC Gemini (Python)"                            |
| Intro                 | "COC setup for Claude Code" → "COC setup for building with the Kailash SDK using Gemini" |
| All path references   | `.claude/agents/` → `.gemini/agents/`, `.claude/skills/` → `.agent/skills/`, etc.        |
| All tool references   | `Read` → `read_file`, `Write` → `write_file`, `Edit` → `edit`, etc.                      |
| Hook event references | `PreToolUse` → `BeforeTool`, `PostToolUse` → `AfterTool`                                 |
| Rules Index           | Add `@` import lines for each rule file (e.g., `@.gemini/rules/agents.md`)               |
| Skills Navigation     | Update paths from `.claude/skills/` → `.agent/skills/`                                   |
| Commands table        | Note that commands are `.toml` format, not `.md`                                         |
| Settings reference    | `.claude/settings.json` → `.gemini/settings.json`                                        |

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
  # Absolute paths
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
pip install kailash                                     # User-facing
runtime.execute(workflow.build())                       # User-facing pattern
```

**Target-specific path references to preserve** (use the correct set for each target):

```
# Claude target
.claude/skills/                                         # Relative references
.claude/agents/                                         # Relative references

# Gemini target (use these instead of .claude/ paths)
.gemini/agents/                                         # Agents root
.gemini/rules/                                          # Rules root
.gemini/commands/                                       # Commands root
.gemini/knowledge/                                      # Knowledge (legacy compat)
.agent/skills/                                          # Skills root (NOT .gemini/skills/)
```

## Gemini-Specific Transforms

These transforms apply ONLY when syncing to the Gemini COC template (`kailash-coc-gemini-py`). They run AFTER all global transforms and rule softening documented above.

### Structural Differences (Claude vs Gemini)

| Aspect         | Claude COC                        | Gemini COC                                           |
| -------------- | --------------------------------- | ---------------------------------------------------- |
| Config root    | `.claude/`                        | `.gemini/` + `.agent/`                               |
| Context file   | `CLAUDE.md`                       | `GEMINI.md`                                          |
| Agents         | `.claude/agents/*.md`             | `.gemini/agents/*.md`                                |
| Skills         | `.claude/skills/*/SKILL.md`       | `.agent/skills/*/SKILL.md`                           |
| Rules          | `.claude/rules/*.md` (auto-load)  | `.gemini/rules/*.md` (imported via `@` in GEMINI.md) |
| Commands       | `.claude/commands/*.md` (YAML+MD) | `.gemini/commands/*.toml` (TOML format)              |
| Knowledge      | N/A                               | `.gemini/knowledge/*.md` (legacy backward compat)    |
| Settings/Hooks | `.claude/settings.json`           | `.gemini/settings.json`                              |
| Hook events    | PreToolUse / PostToolUse          | BeforeTool / AfterTool                               |

### Path Mapping (BUILD `.claude/` → Gemini target)

| BUILD Path               | Gemini Target Path        |
| ------------------------ | ------------------------- |
| `.claude/agents/**/*.md` | `.gemini/agents/**/*.md`  |
| `.claude/skills/**/*`    | `.agent/skills/**/*`      |
| `.claude/rules/*.md`     | `.gemini/rules/*.md`      |
| `.claude/commands/*.md`  | `.gemini/commands/*.toml` |
| `.claude/guides/*`       | `.gemini/knowledge/*`     |
| `.claude/settings.json`  | `.gemini/settings.json`   |
| `.claude/learning/`      | (excluded — per-repo)     |
| `CLAUDE.md`              | `GEMINI.md`               |

### Tool Name Mapping

Replace Claude Code tool names with Gemini equivalents in ALL synced files:

| Claude Tool | Gemini Tool         | Notes                                       |
| ----------- | ------------------- | ------------------------------------------- |
| `Read`      | `read_file`         | In agent frontmatter `tools:` and body text |
| `Write`     | `write_file`        | In agent frontmatter `tools:` and body text |
| `Edit`      | `edit`              | In agent frontmatter `tools:` and body text |
| `Grep`      | `search_text`       | In agent frontmatter `tools:` and body text |
| `Glob`      | `find_files`        | In agent frontmatter `tools:` and body text |
| `Bash`      | `run_shell_command` | In agent frontmatter `tools:` and body text |

**Apply to**: Agent YAML frontmatter `tools:` field, agent body text that references tools by name, skill instructions, GEMINI.md, and any file that mentions these tool names as part of the AI platform interaction.

**Do NOT replace**: Tool names that appear inside code examples (Python/JS code snippets), or as part of English prose where they are not referring to the AI tool (e.g., "Read the documentation" should stay as-is; "use the Read tool" should become "use the read_file tool").

### Command Format Conversion (MD to TOML)

Every command file undergoes format conversion when syncing to Gemini:

**Source format** (`.claude/commands/example.md`):

```markdown
---
description: Short description of what this command does
---

Instruction content for the AI to follow when this command is invoked.
Multiple paragraphs and formatting allowed.
```

**Target format** (`.gemini/commands/example.toml`):

```toml
description = "Short description of what this command does"

prompt = """
Instruction content for the AI to follow when this command is invoked.
Multiple paragraphs and formatting allowed.
"""
```

**Conversion rules**:

1. Parse YAML frontmatter to extract `description`
2. Write as TOML `description = "..."` (quote the string)
3. Take the Markdown body (everything after the closing `---`)
4. Write as TOML `prompt = """..."""` (triple-quoted multi-line string)
5. Change file extension from `.md` to `.toml`
6. Apply all other transforms (path references, tool names) to the prompt content

### Hook Event Name Mapping

When syncing `settings.json` and hook script files:

| Claude Event       | Gemini Event   |
| ------------------ | -------------- |
| `PreToolUse`       | `BeforeTool`   |
| `PostToolUse`      | `AfterTool`    |
| `UserPromptSubmit` | `UserPrompt`   |
| `SessionStart`     | `SessionStart` |

Apply to:

- Keys in `settings.json` hook configuration
- Event name references inside hook script `.js` files (if they reference their own event type)

### GEMINI.md Rule @import Syntax

Gemini does not auto-load rules from a directory. Each rule must be explicitly imported in `GEMINI.md` using `@` syntax:

```
@.gemini/rules/agents.md
@.gemini/rules/env-models.md
@.gemini/rules/git.md
@.gemini/rules/security.md
@.gemini/rules/no-stubs.md
@.gemini/rules/testing.md
@.gemini/rules/patterns.md
@.gemini/rules/e2e-god-mode.md
@.gemini/rules/deployment.md
```

When generating `GEMINI.md`, enumerate all rule files that were synced to `.gemini/rules/` and add an `@` import line for each one. Place these imports near the top of `GEMINI.md`, after the title and introduction, before the main content sections.

### Gemini-Specific Exclusions

In addition to the standard exclusions, these are excluded from Gemini sync:

| File/Directory                          | Reason                                   |
| --------------------------------------- | ---------------------------------------- |
| `agents/management/coc-sync.md`         | Sync infrastructure (same as Claude)     |
| `skills/management/coc-sync-mapping.md` | Sync infrastructure (same as Claude)     |
| `rules/learned-instincts.md`            | Auto-generated per repo (same as Claude) |
| `learning/`                             | Per-repo learning data (same as Claude)  |

No additional Gemini-specific exclusions at this time. The same files are excluded for both targets.

### Gemini Contamination Checks

After syncing to Gemini, verify zero contamination from Claude-specific artifacts:

| Check                                  | Expected | What it catches                                              |
| -------------------------------------- | -------- | ------------------------------------------------------------ |
| Claude tool names in `.gemini/agents/` | 0        | `Read`, `Write`, `Edit`, `Grep`, `Glob`, `Bash` not replaced |
| `.claude/` paths in output             | 0        | Path references not remapped                                 |
| `CLAUDE.md` references in output       | 0        | Context file name not updated                                |
| `PreToolUse`/`PostToolUse` in output   | 0        | Hook event names not remapped                                |
| `.md` files in `.gemini/commands/`     | 0        | Commands not converted to TOML                               |
| Skills under `.gemini/skills/`         | 0        | Skills placed in wrong root (should be `.agent/`)            |

## Known Contamination Counts

As of 2026-03-07 audit, all builder contamination has been cleaned:

| Pattern                                    | Before | After | Fix Applied                            |
| ------------------------------------------ | ------ | ----- | -------------------------------------- |
| Absolute paths `                           | 44     | 0     | Stripped or converted to relative      |
| `apps/kailash-*/` internal app paths       | 96     | 0     | Stripped `apps/` prefix or genericized |
| `src/kailash/` internal source paths       | 24     | 0     | Converted to `kailash/` package path   |
| `# contrib (removed)/` references          | 5      | 0     | Replaced with prose references         |
| Internal class names                       | 2      | 0     | Replaced with public-facing names      |
| Rule softening (agents, testing, no-stubs) | 3      | 0     | MUST→SHOULD, strict→recommended        |
| CLAUDE.md builder framing                  | 1      | 0     | Rewritten for user context             |
