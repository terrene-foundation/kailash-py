# COC Sync Agent Reference

Extracted reference material for cc-artifacts compliance.

## Step 4: Transform and Sync

For EVERY file in `.claude/` (except exclusions listed in mapping), do:

1. Read the BUILD source file
2. Apply global transforms (builder path removal, internal class names, absolute paths)
3. Apply template-specific transforms:
   - **Claude**: Rule softening, CLAUDE.md rewrite, write to `.claude/` at same relative path
   - **Gemini**: All Claude transforms PLUS Gemini-specific transforms (tool names, path remapping, command format conversion, hook events, GEMINI.md generation). Write to `.gemini/` or `.agent/` per the path mapping.
4. Track what changed

### Exclusions (never sync)

- `agents/management/coc-sync.md` — sync infrastructure (meta)
- `skills/management/` — sync infrastructure (meta)
- `rules/learned-instincts.md` — auto-generated per repo
- `learning/` — per-repo learning data
  Everything else syncs, with transforms applied.

### Global Transforms

Apply these to ALL files during sync:

**Patterns to REMOVE** (lines/paragraphs containing these):

```
# Internal source paths (users don't have these directories)
src/kailash/
packages/kailash-dataflow/src/
packages/kailash-kaizen/src/
packages/kailash-nexus/src/

# Builder infrastructure
# contrib (removed)/
tests/utils/test-env

# Absolute paths (break on any other machine)

```

**Internal class names to REMOVE** (references, not import statements):

```
TypeAwareFieldProcessor    # Internal field processor — users never use this
DataFlowWorkflowBinder     # Internal workflow binding — users never use this
SyncDDLExecutor            # Internal DDL executor — users only see auto_migrate=True
TenantContextSwitch        # Internal tenancy — users use with_tenant() context manager
```

**Patterns to PRESERVE** (never strip these):

```
# User-facing imports
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
from dataflow import DataFlow

# User-facing paths (Claude)
.claude/skills/
.claude/agents/

# User-facing paths (Gemini) — use these in Gemini target output
.gemini/agents/
.gemini/rules/
.gemini/commands/
.gemini/knowledge/
.agent/skills/

# User-facing patterns
pip install kailash
runtime.execute(workflow.build())
```

**Path references in Gemini output**: When syncing to Gemini, replace `.claude/skills/` with `.agent/skills/`, `.claude/agents/` with `.gemini/agents/`, `.claude/rules/` with `.gemini/rules/`, and `.claude/commands/` with `.gemini/commands/` in all file content.

### Rule Softening

These rules need specific transforms when synced to COC:

| Rule                | Builder Policy                                    | User Transform                                                                   |
| ------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------- |
| `rules/agents.md`   | Mandatory code review after EVERY change          | Change to RECOMMENDED. Users choose their own review workflow                    |
| `rules/agents.md`   | Security review before ANY commit — NO exceptions | Change to RECOMMENDED. Still strongly encouraged but not enforced                |
| `rules/testing.md`  | NO MOCKING in Tier 2/3 tests                      | Remove restriction. Users can mock external services                             |
| `rules/no-stubs.md` | Zero tolerance for TODOs, stubs, placeholders     | Soften to "avoid in production code" — users iterating on projects may use TODOs |
| `rules/git.md`      | Security review "Non-negotiable"                  | Change to "strongly recommended" to match softened agents.md                     |

**Downstream files** that echo rule language must also be updated:

| File                           | What to soften                                                              |
| ------------------------------ | --------------------------------------------------------------------------- |
| `guides/claude-code/CLAUDE.md` | Replace "NO MOCKING", "MUST delegate", "Non-negotiable" with softened forms |
| `skills/04-kaizen/SKILL.md`    | Replace "NO MOCKING", "NEVER mock" with "real infrastructure recommended"   |
| Root `CLAUDE.md`               | "Mandatory Reviews" → "Recommended Reviews"                                 |

### CLAUDE.md Special Handling (Claude target only)

The root `CLAUDE.md` requires the most transformation:

- Change "COC setup for Claude Code" → "COC setup for building with the Kailash SDK"
- Section "Absolute Directives" → Keep all 3 (Framework-First, .env, Implement Don't Document)
- Section 4 "Mandatory Reviews" → Rewrite as "Recommended Reviews" (code review recommended, security review recommended)
- Strip any references to builder-internal infrastructure
- Keep: Critical Execution Rules, Kailash Platform table, Agents listing, Skills Navigation, Rules Index, Workspace Commands

### GEMINI.md Special Handling (Gemini target only)

Generate `GEMINI.md` from the BUILD `CLAUDE.md` with these additional transforms on top of the standard softening:

- Change title to "Kailash COC Gemini (Python)"
- Change "COC setup for Claude Code" → "COC setup for building with the Kailash SDK using Gemini"
- Replace all `.claude/` path references with the appropriate Gemini paths (`.gemini/agents/`, `.agent/skills/`, `.gemini/rules/`, `.gemini/commands/`)
- Replace tool names in code examples: `Read` → `read_file`, `Write` → `write_file`, `Edit` → `edit`, `Grep` → `search_text`, `Glob` → `find_files`, `Bash` → `run_shell_command`
- Replace hook event names: `PreToolUse` → `BeforeTool`, `PostToolUse` → `AfterTool`
- Add `@` import references for rules (Gemini uses `@.gemini/rules/filename.md` in GEMINI.md to import rules)
- Remove references to `settings.json` hook configuration — replace with Gemini's `settings.json` format
- Agents listing: update paths from `.claude/agents/` → `.gemini/agents/`
- Skills navigation: update paths from `.claude/skills/` → `.agent/skills/`

## Gemini-Specific Transforms

These transforms apply ONLY when syncing to the Gemini COC template. They run AFTER all global transforms and rule softening.

### Path Mapping (BUILD → Gemini)

| BUILD Path (`.claude/`)  | Gemini Target Path               | Notes                                         |
| ------------------------ | -------------------------------- | --------------------------------------------- |
| `agents/*.md`            | `.gemini/agents/*.md`            | Same filename, different root                 |
| `agents/frameworks/*.md` | `.gemini/agents/frameworks/*.md` | Subdirectory preserved                        |
| `agents/frontend/*.md`   | `.gemini/agents/frontend/*.md`   | Subdirectory preserved                        |
| `agents/management/*.md` | `.gemini/agents/management/*.md` | Subdirectory preserved (minus coc-sync)       |
| `agents/standards/*.md`  | `.gemini/agents/standards/*.md`  | Subdirectory preserved                        |
| `skills/*/SKILL.md`      | `.agent/skills/*/SKILL.md`       | Skills use `.agent/` root, not `.gemini/`     |
| `skills/*/other.md`      | `.agent/skills/*/other.md`       | All skill content under `.agent/`             |
| `rules/*.md`             | `.gemini/rules/*.md`             | Same filename, different root                 |
| `commands/*.md`          | `.gemini/commands/*.toml`        | Format conversion required (MD → TOML)        |
| `guides/*`               | `.gemini/knowledge/*`            | Guides become knowledge files (legacy compat) |
| `settings.json`          | `.gemini/settings.json`          | Structure differs (see hook events below)     |
| `CLAUDE.md`              | `GEMINI.md`                      | Full rewrite (see GEMINI.md Special Handling) |

### Tool Name Mapping

All references to Claude Code tool names in agent files, skill files, and documentation must be mapped to Gemini equivalents:

| Claude Tool Name | Gemini Tool Name    | Context                 |
| ---------------- | ------------------- | ----------------------- |
| `Read`           | `read_file`         | File reading            |
| `Write`          | `write_file`        | File writing            |
| `Edit`           | `edit`              | File editing            |
| `Grep`           | `search_text`       | Content search          |
| `Glob`           | `find_files`        | File pattern matching   |
| `Bash`           | `run_shell_command` | Shell command execution |

**Where to apply**: Agent frontmatter `tools:` field, agent body text referencing tools, skill instructions, GEMINI.md.

**Example transform** (agent frontmatter):

```yaml
# BUILD (Claude)
tools: Read, Write, Edit, Grep, Glob, Bash

# Gemini output
tools: read_file, write_file, edit, search_text, find_files, run_shell_command
```

### Command Format Conversion (MD → TOML)

Claude commands are Markdown files (`.md`). Gemini commands are TOML files (`.toml`).

**Claude format** (`.claude/commands/analyze.md`):

```markdown
---
description: Load analysis phase for current workspace
---

[instruction content here]
```

**Gemini format** (`.gemini/commands/analyze.toml`):

```toml
description = "Load analysis phase for current workspace"
# Gemini commands use TOML key-value pairs
# The instruction content is placed in the 'steps' or 'prompt' field
prompt = """
[instruction content here]
"""
```

When converting commands:

1. Extract the YAML frontmatter `description` field
2. Convert to TOML `description = "..."` key
3. Place the Markdown body content into the `prompt` field as a TOML multi-line string
4. Change file extension from `.md` to `.toml`

### Hook Event Name Mapping

Claude and Gemini use different event names for hooks in `settings.json`:

| Claude Event       | Gemini Event   | Purpose                          |
| ------------------ | -------------- | -------------------------------- |
| `PreToolUse`       | `BeforeTool`   | Fires before a tool executes     |
| `PostToolUse`      | `AfterTool`    | Fires after a tool executes      |
| `UserPromptSubmit` | `UserPrompt`   | Fires when user submits a prompt |
| `SessionStart`     | `SessionStart` | Fires at session start (same)    |

When syncing `settings.json`, remap all event names. The hook script files themselves (`.js`) may also need event name references updated in their code.

### Settings.json Structure

Claude's `settings.json` lives at `.claude/settings.json`. Gemini's lives at `.gemini/settings.json`. The structure is similar but event names differ per the table above. Transform the keys accordingly.

### GEMINI.md @import Syntax for Rules

Claude loads rules automatically from `.claude/rules/`. Gemini requires explicit `@` imports in `GEMINI.md`:

```markdown
# In GEMINI.md, rules are imported via:

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

When generating `GEMINI.md`, include `@` import lines for every rule file that exists in `.gemini/rules/`.

### Content Path References

Throughout all synced files, replace Claude-specific path references with Gemini equivalents:

| Claude Reference        | Gemini Replacement      |
| ----------------------- | ----------------------- |
| `.claude/skills/`       | `.agent/skills/`        |
| `.claude/agents/`       | `.gemini/agents/`       |
| `.claude/rules/`        | `.gemini/rules/`        |
| `.claude/commands/`     | `.gemini/commands/`     |
| `.claude/settings.json` | `.gemini/settings.json` |
| `.claude/learning/`     | `.gemini/learning/`     |
| `CLAUDE.md`             | `GEMINI.md`             |

## Step 4b: Fixing COC-Only Files

COC-only files (files that exist in the COC template but not in BUILD) may contain errors. To fix them:

1. **Identify the error** — What API/pattern is wrong?
2. **Verify against Python SDK source** — Read the actual implementation in this BUILD repo
3. **Fix the specific error** — Use Edit tool, not Write. Change only what's wrong.
4. **Preserve the file** — Do NOT delete or replace COC-only files. Fix them in place.
5. **Never bulk-replace without source verification** — Read the actual source code for every API, constructor, and return value you're changing. Blind `sed` replacements cause regressions (e.g., double-prefixing node names).

### Source verification checklist

Before changing any API reference in a COC file:

```bash
# Check actual class/method exists
grep "class TypeName\|def method_name" src/kailash/**/*.py apps/kailash-*/src/**/*.py
# Check constructor signature
grep "def __init__" src/kailash/path/to/module.py
# Check return type/structure
grep "return " src/kailash/path/to/method.py
```

If the API doesn't exist in source, it's fabricated — remove the reference entirely.

## Step 5: Validate

After sync, run contamination check for each synced target.

### Claude contamination check

```bash
cd kailash-coc-claude-py
echo "=== Claude COC Builder Contamination Check ==="
echo -n "src/kailash/ refs: "; grep -rl "src/kailash/" .claude/ 2>/dev/null | wc -l
echo -n "apps/kailash-* refs: "; grep -rl "apps/kailash-" .claude/ 2>/dev/null | wc -l
echo -n "# contrib (removed)/ refs: "; grep -rl "# contrib (removed)/" .claude/ 2>/dev/null | wc -l
echo -n "Absolute paths: "; grep -rl "" .claude/ 2>/dev/null | wc -l
echo -n "Sync infra leaked: "; ls .claude/skills/management/ .claude/agents/management/coc-sync.md 2>/dev/null | wc -l
echo -n "learned-instincts: "; diff -q .claude/rules/learned-instincts.md ../kailash_python_sdk/.claude/rules/learned-instincts.md 2>/dev/null && echo "LEAKED (identical to BUILD)" || echo "OK (per-repo)"
```

### Gemini contamination check

```bash
cd kailash-coc-gemini-py
echo "=== Gemini COC Builder Contamination Check ==="
echo -n "src/kailash/ refs: "; grep -rl "src/kailash/" .gemini/ .agent/ 2>/dev/null | wc -l
echo -n "apps/kailash-* refs: "; grep -rl "apps/kailash-" .gemini/ .agent/ 2>/dev/null | wc -l
echo -n "# contrib (removed)/ refs: "; grep -rl "# contrib (removed)/" .gemini/ .agent/ 2>/dev/null | wc -l
echo -n "Absolute paths: "; grep -rl "" .gemini/ .agent/ 2>/dev/null | wc -l
echo -n "Sync infra leaked: "; ls .agent/skills/management/ .gemini/agents/management/coc-sync.md 2>/dev/null | wc -l
echo -n "learned-instincts: "; diff -q .gemini/rules/learned-instincts.md ../kailash_python_sdk/.claude/rules/learned-instincts.md 2>/dev/null && echo "LEAKED (identical to BUILD)" || echo "OK (per-repo)"

echo ""
echo "=== Gemini-Specific Contamination ==="
echo -n "Claude tool names (Read/Write/Edit/Grep/Glob/Bash): "; grep -rPl "\bRead\b|\bWrite\b|\bEdit\b|\bGrep\b|\bGlob\b|\bBash\b" .gemini/agents/ 2>/dev/null | wc -l
echo -n ".claude/ path refs: "; grep -rl "\.claude/" .gemini/ .agent/ GEMINI.md 2>/dev/null | wc -l
echo -n "CLAUDE.md refs: "; grep -rl "CLAUDE\.md" .gemini/ .agent/ GEMINI.md 2>/dev/null | wc -l
echo -n "PreToolUse/PostToolUse refs: "; grep -rl "PreToolUse\|PostToolUse" .gemini/ 2>/dev/null | wc -l
echo -n "MD commands (should be TOML): "; ls .gemini/commands/*.md 2>/dev/null | wc -l
```

All contamination counts should be **0**.

## Step 6: Report

Generate a report for each synced target.

```
## COC Sync Report

### Template: kailash-coc-claude-py/
- SYNCED: agents/frameworks/dataflow-specialist.md (transformed: stripped internal refs)
- SYNCED: rules/agents.md (transformed: mandatory → recommended)
- SYNCED: agents/frontend/react-specialist.md (as-is)
- SKIPPED: agents/management/coc-sync.md (sync infrastructure)
- SKIPPED: skills/management/coc-sync-mapping.md (sync infrastructure)
- SKIPPED: rules/learned-instincts.md (per-repo)
- NO CHANGE: agents/deep-analyst.md (already up to date)

### Template: kailash-coc-gemini-py/
- SYNCED: .gemini/agents/frameworks/dataflow-specialist.md (transformed: stripped internal refs + tool names)
- SYNCED: .gemini/rules/agents.md (transformed: mandatory → recommended)
- SYNCED: .gemini/commands/analyze.toml (transformed: MD → TOML conversion)
- SYNCED: .agent/skills/01-core-sdk/SKILL.md (transformed: path refs updated)
- SYNCED: GEMINI.md (generated from CLAUDE.md with full Gemini transforms)
- SYNCED: .gemini/settings.json (transformed: hook event names)
- SKIPPED: agents/management/coc-sync.md (sync infrastructure)
- SKIPPED: skills/management/coc-sync-mapping.md (sync infrastructure)
- NO CHANGE: .gemini/agents/deep-analyst.md (already up to date)

### Contamination Check (per template)
- src/kailash/ refs: 0
- apps/kailash-* refs: 0
- # contrib (removed)/ refs: 0
- Absolute paths: 0
- Sync infra leaked: 0
- [Gemini only] Claude tool names in agents: 0
- [Gemini only] .claude/ path refs: 0
- [Gemini only] PreToolUse/PostToolUse refs: 0
- [Gemini only] MD commands (should be TOML): 0

### Summary
- Target(s): claude / gemini / both
- Files checked: N
- Files synced: N (N transformed, N as-is)
- Files skipped: N (sync infrastructure)
- Files unchanged: N
- Contamination: CLEAN / N issues
```

## Step 7: Sync Dependency Versions

After syncing agents/skills/rules, update ALL version references in the COC template to match current SDK versions. This covers two scopes:

### 7a. pyproject.toml dependency pins

1. Read versions from this BUILD repo's `pyproject.toml` and `packages/*/pyproject.toml`
2. Update the COC template's `pyproject.toml` dependency pins to match:
   - `kailash>=X.Y.Z` — from root `pyproject.toml`
   - `kailash-nexus>=X.Y.Z` — from `packages/kailash-nexus/pyproject.toml`
   - `kailash-dataflow>=X.Y.Z` — from `packages/kailash-dataflow/pyproject.toml`
   - `kailash-kaizen>=X.Y.Z` — from `packages/kailash-kaizen/pyproject.toml`
   - `eatp>=X.Y.Z` — from `src/kailash/trust/` (EATP version)
   - `trust-plane>=X.Y.Z` — from `src/kailash/trust/plane/` (TrustPlane version)
3. Use `>=` pins (minimum version), not `==` (exact pin)

### 7b. Version references in agent/skill/doc content

1. Grep the COC template for stale version patterns: `v0.12`, `v0.13`, `(v0.12.1)`, `DataFlow v0.12.2`, etc.
2. Update agent description frontmatter that references old versions (e.g., `dataflow-specialist.md` description mentioning `v0.12.2`)
3. Update inline version notes in agent/skill files (e.g., `(v0.12.1)` annotations on feature lists)
4. For features that are now GA and stable, remove the version annotation entirely — they are just "current behavior"
5. Update `ENTERPRISE_BRIEF.md` and any other docs with version-specific claims

### 7c. Validation

After updating, run: `grep -rn '0\.12\.\|0\.13\.\|v0\.12\|v0\.13' --include="*.md" --include="*.toml"` on the COC template to verify no stale references remain (excluding `.venv/`).

Report all version mismatches found and fixed.

## When This Agent Runs

1. **During `/codify` (phase 05)** — after creating/updating agents and skills, sync to COC
2. **On-demand** — when the user asks to sync or update the template
3. **After any agent/skill/rule change** — to keep COC in sync
4. **After any SDK release** — to update dependency versions in the template

## Delegation

- **intermediate-reviewer**: Review sync changes before finalizing
- **coc-expert**: Consult on COC five-layer architecture alignment

## Common Pitfalls

### General (both targets)

1. **Always run contamination check** after sync — catches missed builder paths
2. **Absolute paths are the #1 contamination source** — 35+ hardcoded to builder machine
3. **Rule softening is easy to forget** — the builder's strict policies don't apply to users
4. **Downstream stale language** — softening rules alone is not enough; files that ECHO rule language (guides, skills) must also be updated. Grep for `NO MOCKING`, `MUST delegate`, `Non-negotiable` across the entire output directory after softening
5. **Internal class names slip through** — they appear in version history notes and feature lists
6. **Never sync this agent or the mapping skill** — they are sync infrastructure
7. **`git.md` must match `agents.md`** — if agents.md is softened, git.md's security review reference must also be softened to avoid contradictions
8. **Never delete COC-only files** — they're legitimate template content, not stale
9. **Verify before fixing** — Always check Python SDK source before correcting a COC file. Blind sed/find-replace causes regressions (double-prefixed names, wrong substitutions)
10. **No nested config directories** — `learning/` should only exist at the config root, never inside skill subdirectories
11. **This agent NEVER touches rs COC** — the rs COC has its own BUILD repo and coc-sync agent
12. **Line-by-line accuracy matters** — After bulk contamination sweeps, do deep API accuracy checks: verify constructors, return structures, and method signatures against actual source code

### Gemini-specific pitfalls

13. **Tool name leakage** — Claude tool names (`Read`, `Write`, `Edit`, `Grep`, `Glob`, `Bash`) appearing in Gemini agent files is the most common Gemini-specific contamination. Always run the Gemini contamination check.
14. **Path reference leakage** — `.claude/` paths appearing in Gemini output files. Search for `.claude/` across all `.gemini/` and `.agent/` directories after sync.
15. **Command format mismatch** — Forgetting to convert `.md` commands to `.toml` format. Check that `.gemini/commands/` contains only `.toml` files, never `.md`.
16. **Hook event name mismatch** — `PreToolUse`/`PostToolUse` in `settings.json` or hook scripts must become `BeforeTool`/`AfterTool` for Gemini.
17. **Missing @import lines** — Every rule file synced to `.gemini/rules/` must have a corresponding `@.gemini/rules/filename.md` line in `GEMINI.md`. Missing imports mean the rule is invisible to Gemini.
18. **Skills in wrong root** — Gemini skills go under `.agent/skills/`, NOT `.gemini/skills/`. This is the most confusing path difference.
19. **CLAUDE.md references in GEMINI.md** — After generating `GEMINI.md`, grep for any remaining `CLAUDE.md` or `Claude Code` references that should have been transformed.
