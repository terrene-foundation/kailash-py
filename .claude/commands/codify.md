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

### 1. Consume learning digest

Before extracting new knowledge, integrate what the learning system has captured:

1. Read `.claude/learning/learning-digest.json` — the structured summary of recent observations
2. Read `.claude/learning/learning-codified.json` — what was previously codified (avoid re-processing)
3. Read recent journal entries referenced in the digest (`decisions` array) — DECISION and DISCOVERY entries contain semantic context
4. Read `.session-notes` — latest session accomplishments and outstanding items

Analyze the digest for actionable findings:

- **Corrections** → Do any rules or skills need updating to match user preferences? Each correction is a real signal where the user pushed back on an approach.
- **Error patterns** → Should any recurring rule violations become new rule sections (DO/DO NOT with examples)?
- **Decisions** → Should any architectural decisions from journals become agent or skill knowledge?
- **Accomplishments** → Do any completed features need documentation in skills?

For each finding, either:

- Update an existing rule (add DO/DO NOT with example and Why)
- Update a skill's SKILL.md or sub-files
- Update an agent's knowledge section
- Skip (not worth codifying — explain why)

After processing, write `.claude/learning/learning-codified.json` to record what was analyzed:

```json
{
  "last_codified": "2026-04-07T12:00:00Z",
  "digest_hash": "<sha256 of digest at time of processing>",
  "actions_taken": [
    { "type": "rule_update", "file": "rules/patterns.md", "reason": "..." },
    {
      "type": "skill_update",
      "file": "skills/03-nexus/SKILL.md",
      "reason": "..."
    }
  ]
}
```

This closes the feedback loop: observe → digest → **codify into real artifacts**.

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
3. **Check for existing proposal** — read `.claude/.proposals/latest.yaml` if it exists:
   - **`status: pending_review`** → this proposal has NOT been reviewed at loom/ yet. MUST NOT overwrite. **Append** this session's changes to the existing `changes:` array (see append format below).
   - **`status: reviewed`** → loom/ has classified this proposal but may not have distributed yet. **Append** — new changes since review still need upstream attention.
   - **`status: distributed`** → fully processed (classified AND distributed to USE templates). Safe to **create fresh** — archive the old file to `.claude/.proposals/archive/{codify_date}-{source_repo}.yaml` first.
   - **File does not exist** → **create fresh**.

   **BLOCKED:** Overwriting a `pending_review` or `reviewed` proposal. This destroys unprocessed changes from prior `/codify` sessions that loom/ has not yet classified.

4. Generate or append `.claude/.proposals/latest.yaml`:

   **Fresh proposal** (new file or after archiving a `distributed` proposal):

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

   **Appending to existing proposal** (status is `pending_review` or `reviewed`):
   - Keep ALL existing top-level fields and `changes:` entries intact
   - Add a YAML comment separator with the session date
   - Append new `changes:` entries below the separator
   - Update `codify_date` and `codify_session` to reflect the latest session
   - Update `sdk_version` and `coc_version` if they changed
   - If status was `reviewed`, reset to `pending_review` (new unreviewed changes added)

   ```yaml
   # Existing entries preserved above...

   # --- YYYY-MM-DD session: type(scope): description ---

     - file: relative/path/to/new-artifact.md
       action: created
       suggested_tier: coc
       reason: "Why this artifact was created"
       diff_lines: "+80"

   status: pending_review  # reset if was reviewed — new unreviewed changes added
   ```

5. For each changed artifact, suggest a tier:
   - **cc**: Claude Code universal (guides, cc-audit)
   - **co**: Methodology universal (CO principles, journal, communication)
   - **coc**: Codegen, language-agnostic (workflow phases, analysis patterns)
   - **coc-py** / **coc-rs**: Language-specific (code examples, SDK patterns)

6. Report to the developer:

   **If fresh proposal:**

   > Artifacts updated locally. Proposal created at `.claude/.proposals/latest.yaml`
   > with {N} changes for upstream review.
   > When ready, open loom/ and run `/sync {py|rs}` to classify and distribute.

   **If appended to existing:**

   > Artifacts updated locally. Appended {N} new changes to existing proposal
   > (`.claude/.proposals/latest.yaml`, now {total} changes, status reset to pending_review).
   > Prior {prior_count} changes from earlier sessions are preserved.
   > When ready, open loom/ and run `/sync {py|rs}` to classify and distribute.

### 8. Create upstream proposal (loom only — targets atelier/)

**This step applies ONLY when running at loom/.** Detect by: git remote contains `loom`, or `.claude/sync-manifest.yaml` exists in the repo root.

**If this is NOT loom/**: SKIP this step.

**If this is loom/**: Check whether any artifacts updated in steps 3-4 are CC or CO tier (domain-agnostic methodology, not COC-specific). CC/CO artifacts originate at atelier/ and should be proposed upstream.

1. Identify which updated artifacts are CC or CO tier (guides, rules, agents that are methodology-level, not SDK-specific)
2. If none qualify, skip — report "No CC/CO changes to propose upstream"
3. If CC/CO changes exist, apply the **same append-not-overwrite logic** as Step 7 to `.claude/.proposals/latest.yaml`:
   - Check existing status (`pending_review` / `reviewed` / `distributed` / missing)
   - Append or create fresh accordingly
   - Use `source_repo: loom` and `upstream_target: atelier`

   ```yaml
   source_repo: loom
   upstream_target: atelier
   codify_date: YYYY-MM-DD
   codify_session: "type(scope): description"
   loom_version: "X.Y.Z"
   coc_version: "X.Y.Z"

   changes:
     - file: rules/rule-authoring.md
       action: created
       suggested_tier: cc
       canonical_path: .claude/rules/rule-authoring.md
       reason: "..."
       adaptation_notes: "Notes on what atelier needs to adjust"

   status: pending_review
   ```

4. Report:
   > {N} CC/CO artifacts proposed for upstream to atelier/.
   > Proposal at `.claude/.proposals/latest.yaml` (status: pending_review).
   > When ready, the atelier maintainer reviews and adapts for atelier context.

See `rules/artifact-flow.md` for the full flow rules.

## Agent Teams

Deploy these agents as a team for codification:

**Knowledge extraction team:**

- **analyst** — Identify core patterns, architectural decisions, and domain knowledge worth capturing
- **analyst** — Distill requirements into reusable agent instructions
- `co-reference` skill — Ensure agents and skills follow COC five-layer architecture (codification IS Layer 5 evolution)

**Creation team:**

- **reviewer** — Validate that skill examples are correct and runnable
- **reviewer** — Review agent/skill quality before finalizing

**Validation team (red team the agents and skills):**

- **claude-code-architect** — Verify cc-artifacts compliance: descriptions <120 chars, agents <400 lines, commands <150 lines, rules have `paths:` frontmatter, SKILL.md progressive disclosure, no CLAUDE.md duplication
- **gold-standards-validator** — Terrene naming, licensing accuracy, terminology standards
- **testing-specialist** — Verify any code examples in skills are testable
- **security-reviewer** — Audit agents/skills for prompt injection, insecure patterns, secrets exposure

**Upstream proposals (steps 7-8):**

- BUILD repos (kailash-py, kailash-rs): append to `.claude/.proposals/latest.yaml` — never overwrite unprocessed proposals
- loom/: CC/CO artifacts proposed upstream to atelier/ via `.claude/.proposals/latest.yaml`
- Downstream project repos: skip proposal creation, changes stay local
- See `rules/artifact-flow.md` for the controlled flow and proposal status lifecycle

### Journal (MUST — phase-complete gate)

Before reporting `/codify` complete, create `/journal new <TYPE> <slug>` entries for: **DECISION** (which rules/skills/agents were updated and why), **DISCOVERY** (patterns extracted into institutional knowledge that the next session should inherit). Skip only if nothing is journal-worthy; do not batch.
