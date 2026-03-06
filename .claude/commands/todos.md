---
name: todos
description: "Load phase 02 (todos) for the current workspace"
---

Load the todos phase for a workspace project.

1. Determine the workspace:
   - If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
   - Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
   - If no workspace exists, ask the user to create one first

2. Read `workspaces/<project>/instructions/02-todos.md` and follow those instructions.

3. Check current state:
   - Read files in `workspaces/<project>/02-plans/` for context
   - Check if `todos/active/` already has files (resuming)

4. **CRITICAL: Write ALL todos for the ENTIRE project.**
   - Do NOT limit to "phase 1" or "what should be done now"
   - Do NOT prioritize or filter — write EVERY task required to complete the full project
   - Cover backend, frontend, testing, deployment, documentation — everything
   - Each todo should be detailed enough to implement independently
   - If the plans reference it, there must be a todo for it
   - For large projects (20+ todos), organize into numbered milestones/groups for clarity

5. All todos go into `workspaces/<project>/todos/active/`.

6. STOP and wait for human approval before proceeding to implementation.

## Agent Teams

Deploy these agents as a team for todo creation:

- **todo-manager** — Create and organize the detailed todos, ensure completeness
- **requirements-analyst** — Break down requirements, identify missing tasks
- **deep-analyst** — Identify failure points, dependencies, and gaps
- **coc-expert** — Ensure todos include context/guardrails/learning work, not just features (COC five-layer completeness)
- **framework-advisor** — Ensure todos cover the right framework choices (if applicable)

For frontend projects, additionally deploy:

- **uiux-designer** — Ensure UI/UX todos cover design system, responsive layouts, accessibility
- **flutter-specialist** or **react-specialist** — Framework-specific frontend todos

Red team the todo list with agents until they confirm no gaps remain.
