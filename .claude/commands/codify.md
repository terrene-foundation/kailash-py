---
name: codify
description: "Load phase 05 (codify) for the current workspace. Update existing agents and skills with new knowledge."
---

## Workspace Resolution

1. If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
2. Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
3. If no workspace exists, ask the user to create one first
4. Read all files in `workspaces/<project>/briefs/` for user context (this is the user's input surface)

## Phase Check

- Read `workspaces/<project>/04-validate/` to confirm validation passed
- Read `docs/` and `docs/00-authority/` for knowledge base
- Output: update existing agents and skills in their canonical locations (e.g., `agents/frameworks/`, `skills/01-core-sdk/`, `skills/02-dataflow/`, etc.)

## Execution Model

This phase executes under the **autonomous execution model** (see `rules/autonomous-execution.md`). Knowledge extraction and codification are autonomous — agents extract, structure, and validate knowledge without human intervention. The human reviews the codified output at the end (structural gate on what becomes institutional knowledge), but the extraction and synthesis process is fully autonomous.

## Workflow

### 1. Deep knowledge extraction

Using as many subagents as required, peruse `docs/`, especially `docs/00-authority/`.

- Ultrathink and read beyond the docs into the intent of this project/product
- Understand the roles and use of agents, skills, docs:
  - **Agents** — What to do, how to think about this, what can it work with, following procedural directives
  - **Skills** — Distilled knowledge that agents can achieve 100% situational awareness with
  - **`docs/`** — Full knowledge base

### 2. Update existing agents

Improve agents in their canonical locations (e.g., `agents/frameworks/`, `agents/standards/`, etc.).

- Reference `.claude/agents/_subagent-guide.md` for agent format
- Identify which existing agent(s) should absorb the new knowledge
- Add new skills references, update capabilities, refine instructions
- If no existing agent covers the domain, create a new agent in the appropriate canonical directory (e.g., `agents/frameworks/`, `agents/standards/`, `agents/management/`)

### 3. Update existing skills

Improve skills in their canonical locations (e.g., `skills/01-core-sdk/`, `skills/02-dataflow/`, etc.).

- Reference `.claude/guides/claude-code/06-the-skill-system.md` for skill format
- Identify which existing skill directory should absorb the new knowledge
- Add new skill files to the appropriate numbered directory
- Update the directory's `SKILL.md` entry point to reference new files
- Skills must be as detailed as possible so agents can deliver most of their work just by using them
- Should REFERENCE instead of repeating the knowledge base in `docs/`

### 4. Update README.md and documentation (MANDATORY)

After updating agents and skills, ensure user-facing documentation reflects the new capabilities:

1. **README.md** — Verify "Why Kailash?" section includes all new capabilities. Update version numbers in architecture diagram. Ensure no feature claims exceed actual implementation.
2. **Docstrings** — Verify all modified source files have accurate docstrings (no stale claims from pre-implementation state). Run `grep -r "TODO\|FIXME\|STUB" src/` to catch stragglers.
3. **Sphinx docs build** — Run `cd docs && python build_docs.py` locally to verify the docs build succeeds and new modules appear in the API reference. The CI workflow (`docs-deploy.yml`) auto-deploys on push to main, but a local build catches errors before push.

**This step was missed in the v0.13.0 release and caught post-release. Never skip it.**

### 5. Red team the agents and skills

Validate that generated agents and skills are correct, complete, and secure.

## Agent Teams

Deploy these agents as a team for codification:

**Knowledge extraction team:**

- **deep-analyst** — Identify core patterns, architectural decisions, and domain knowledge worth capturing
- **requirements-analyst** — Distill requirements into reusable agent instructions
- **coc-expert** — Ensure agents and skills follow COC five-layer architecture (codification IS Layer 5 evolution)

**Creation team:**

- **documentation-validator** — Validate that skill examples are correct and runnable
- **intermediate-reviewer** — Review agent/skill quality before finalizing

**Validation team (red team the agents and skills):**

- **gold-standards-validator** — Ensure agents follow the subagent guide and skills follow the skill system guide
- **testing-specialist** — Verify any code examples in skills are testable
- **security-reviewer** — Audit generated agents/skills for prompt injection vectors, insecure patterns, or secrets exposure (codified artifacts persist across all future sessions)

**COC template sync (after codification completes):**

- **coc-sync** — Transform and sync all agents, skills, rules, and commands to the COC template repository (`kailash-coc-claude-py`), stripping builder-specific content. Only runs if the repo exists at `kailash-coc-claude-py/`. See `.claude/skills/management/coc-sync-mapping.md` for transform rules.
