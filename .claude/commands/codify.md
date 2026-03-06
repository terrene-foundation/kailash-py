---
name: codify
description: "Load phase 05 (codify) for the current workspace. Create project agents and skills."
---

Load the codification phase for a workspace project.

1. Determine the workspace:
   - If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
   - Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)

2. Read `workspaces/<project>/instructions/05-create-agent-skills.md` and follow those instructions.

3. Check workspace state:
   - Read `workspaces/<project>/04-validate/` to confirm validation passed
   - Read `docs/` and `docs/00-authority/` for knowledge base

4. Output goes to `.claude/agents/project/` and `.claude/skills/project/`.
