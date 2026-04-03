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

### 1. Consume L5 learning artifacts

Before extracting new knowledge, integrate what the learning system has already discovered:

1. Read `.claude/learning/evolved/skills/` — if evolved skills exist, integrate them into canonical skill directories
2. Read `.claude/learning/instincts/personal/` — review high-confidence instincts for patterns worth codifying
3. Read `.claude/rules/learned-instincts.md` — verify rendered instincts are accurate and actionable

This closes the L5 feedback loop: observe → instinct → evolve → **codify**.

### 2. Deep knowledge extraction

Using as many subagents as required, peruse `docs/`, especially `docs/00-authority/`.

- Read beyond the docs into the intent of this project/product
- Understand the roles and use of agents, skills, docs:
  - **Agents** — What to do, how to think about this, following procedural directives
  - **Skills** — Distilled knowledge for 100% situational awareness
  - **`docs/`** — Full knowledge base

### 3. Update existing agents

Improve agents in their canonical locations.

- Reference `.claude/agents/_subagent-guide.md` for agent format
- Identify which existing agent(s) should absorb the new knowledge
- If no existing agent covers the domain, create a new agent in the appropriate directory

### 4. Update existing skills

Improve skills in their canonical locations.

- Reference `.claude/guides/claude-code/06-the-skill-system.md` for skill format
- Update the directory's `SKILL.md` entry point to reference new files
- Skills must be detailed enough for agents to achieve situational awareness from them alone

### 5. Update README.md and documentation (MANDATORY)

Ensure user-facing documentation reflects new capabilities. Verify README.md, docstrings, and docs build.

### 6. Red team the agents and skills

Validate that generated agents and skills are correct, complete, and secure. **claude-code-architect** verifies cc-artifacts compliance (descriptions under 120 chars, agents under 400 lines, commands under 150 lines, rules path-scoped, SKILL.md progressive disclosure).

### 7. Create upstream proposal (BUILD repos only)

**This step applies ONLY to BUILD repos** (kailash-py, kailash-rs). Detect by checking:

- Git remote contains `kailash-py` or `kailash-rs`, OR
- `pyproject.toml` contains `name = "kailash"` or `Cargo.toml` contains `name = "kailash"`

**If this is a downstream project repo** (anything else): SKIP this step. Downstream repos consume COC artifacts from templates — they do not propose changes upstream. Artifact changes from `/codify` in downstream repos stay local to that project. Report:

> Artifacts updated locally. This is a downstream project repo — changes stay local.
> Only BUILD repos (kailash-py, kailash-rs) create upstream proposals.

**If this is a BUILD repo**: Create a proposal for upstream review at loom/ (source of truth).

**DO NOT sync directly to COC template repos.** All distribution flows through loom/ via `/sync`.

1. Create `.claude/.proposals/` directory if it doesn't exist
2. Read the SDK version from `pyproject.toml` (py) or `Cargo.toml` (rs) and the COC artifact version from `.claude/VERSION`
3. Generate `.claude/.proposals/latest.yaml` listing all artifact changes:

```yaml
source_repo: kailash-py # or kailash-rs
codify_date: YYYY-MM-DD
codify_session: "type(scope): description of work"
sdk_version: "2.2.1" # from pyproject.toml or Cargo.toml
coc_version: "1.0.0" # from .claude/VERSION

changes:
  - file: relative/path/to/artifact.md
    action: created | modified
    suggested_tier: cc | co | coc | coc-py | coc-rs
    reason: "Why this artifact was created/changed"
    diff_lines: "+N -N" # for modifications

status: pending_review
```

4. For each changed artifact, suggest a tier:
   - **cc**: Claude Code universal (guides, cc-audit)
   - **co**: Methodology universal (CO principles, journal, communication)
   - **coc**: Codegen, language-agnostic (workflow phases, analysis patterns)
   - **coc-py** / **coc-rs**: Language-specific (code examples, SDK patterns)

5. Report to the developer:

> Artifacts updated locally and available in this repo. Proposal created at
> `.claude/.proposals/latest.yaml` with {N} changes for upstream review.
> When ready, open loom/ and run `/sync {py|rs}` to classify and distribute.

See `rules/artifact-flow.md` for the full flow rules.

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

- **claude-code-architect** — Verify cc-artifacts compliance: descriptions <120 chars, agents <400 lines, commands <150 lines, rules have `paths:` frontmatter, SKILL.md progressive disclosure, no CLAUDE.md duplication
- **gold-standards-validator** — Terrene naming, licensing accuracy, terminology standards
- **testing-specialist** — Verify any code examples in skills are testable
- **security-reviewer** — Audit agents/skills for prompt injection, insecure patterns, secrets exposure

**Upstream proposal (step 7 — BUILD repos only):**

- Only in BUILD repos (kailash-py, kailash-rs): generate `.claude/.proposals/latest.yaml` with tier suggestions
- Downstream project repos: skip proposal creation, changes stay local
- See `rules/artifact-flow.md` for the controlled flow: BUILD repo → loom/ → templates

### Journal

Create journal entries for knowledge captured:

- **DECISION** entries for what was codified and why
- **CONNECTION** entries for patterns that connect across the project
- **TRADE-OFF** entries for trade-offs in knowledge representation choices

Use sequential naming: check the highest existing `NNNN-` prefix and increment.
