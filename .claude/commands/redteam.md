---
name: redteam
description: "Load phase 04 (validate) for the current workspace. Red team testing."
---

Load the validation phase for a workspace project.

1. Determine the workspace:
   - If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
   - Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)

2. Read `workspaces/<project>/instructions/04-validate.md` and follow those instructions.

3. Check workspace state:
   - Verify `todos/active/` is empty (all implemented) or note remaining items
   - Read `workspaces/<project>/03-user-flows/` for validation criteria

4. Validation results go into `workspaces/<project>/04-validate/`.

5. If gaps are found, document them and feed back to implementation (use `/implement` to fix).
