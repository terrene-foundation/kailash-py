---
name: todos
description: "Load phase 02 (todos) for the current workspace"
---

## Workspace Resolution

1. If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
2. Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
3. If no workspace exists, ask the user to create one first
4. Read all files in `workspaces/<project>/briefs/` for user context (this is the user's input surface)

## Phase Check

- Read files in `workspaces/<project>/02-plans/` for context
- Check if `todos/active/` already has files (resuming)
- All todos go into `workspaces/<project>/todos/active/`

## Workflow

### 1. Review plans with specialists

Reference plans in `workspaces/<project>/02-plans/` and work through every single file.

- **(Backend)** Work with framework specialists (kailash, kaizen, dataflow, nexus). Follow procedural directives. Review and revise plans as required.
- **(Frontend)** Work with frontend agents. Review implementation plans and todos for frontends. Use a consistent set of design principles for all FE interfaces. Use the latest modern UI/UX principles/components/widgets.

### 2. Codebase locations (project root, not workspace)

- `src/...` for all backend codebase
- `apps/web` for all web FE codebase
- `apps/mobile` for all mobile FE codebase

### 3. Create comprehensive todos

**CRITICAL: Write ALL todos for the ENTIRE project.**

- Do NOT limit to "phase 1" or "what should be done now"
- Do NOT prioritize or filter — write EVERY task required to complete the full project
- Cover backend, frontend, testing, deployment, documentation — everything
- Each todo should be detailed enough to implement independently
- If the plans reference it, there must be a todo for it
- For large projects (20+ todos), organize into numbered milestones/groups for clarity

Create detailed todos for EVERY task required. Place them in `todos/active/`.

### 4. Red team the todo list

Review with red team agents continuously until they are satisfied there are no gaps remaining.

### 5. STOP — wait for human approval before proceeding to implementation.

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
