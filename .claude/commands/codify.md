---
name: codify
description: "Load phase 05 (codify) for the current workspace. Create project agents and skills."
---

Load the codification phase for a workspace project.

1. Determine the workspace:
   - If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
   - Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
   - If no workspace exists, ask the user to create one first

2. Read `workspaces/<project>/instructions/05-create-agent-skills.md` and follow those instructions.

3. Check workspace state:
   - Read `workspaces/<project>/04-validate/` to confirm validation passed
   - Read `docs/` and `docs/00-authority/` for knowledge base

4. Output goes to `.claude/agents/project/` and `.claude/skills/project/`.

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

Reference `.claude/agents/_subagent-guide.md` for agent format and `.claude/guides/claude-code/06-the-skill-system.md` for skill format.
