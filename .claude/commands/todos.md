---
name: todos
description: "Load phase 02 (todos) for the current workspace"
---

Load the todos phase for a workspace project.

1. Determine the workspace:
   - If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
   - Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)

2. Read `workspaces/<project>/instructions/02-todos.md` and follow those instructions.

3. Check current state:
   - Read files in `workspaces/<project>/02-plans/` for context
   - Check if `todos/active/` already has files (resuming)

4. All todos go into `workspaces/<project>/todos/active/`.

5. STOP and wait for human approval before proceeding to implementation.
