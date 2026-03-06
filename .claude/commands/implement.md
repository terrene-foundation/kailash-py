---
name: implement
description: "Load phase 03 (implement) for the current workspace. Repeat until all todos complete."
---

Load the implementation phase for a workspace project.

1. Determine the workspace:
   - If `$ARGUMENTS` specifies a project name or todo, parse accordingly
   - Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)

2. Read `workspaces/<project>/instructions/03-implement.md` and follow those instructions.

3. Check workspace state:
   - Read files in `todos/active/` to see what needs doing
   - Read files in `todos/completed/` to see what's done
   - If `$ARGUMENTS` specifies a specific todo, focus on that one
   - Otherwise, pick the next active todo

4. Reference the plans in `workspaces/<project>/02-plans/` for context.

5. After completing each todo, move it from `todos/active/` to `todos/completed/`.
