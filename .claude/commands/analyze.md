---
name: analyze
description: "Load phase 01 (analyze) for the current workspace"
---

Load the analysis phase for a workspace project.

1. Determine the workspace:
   - If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
   - Otherwise, list directories under `workspaces/` (excluding `instructions/`) and use the most recently modified one
   - If no workspace exists, ask the user to create one first

2. Read `workspaces/<project>/instructions/01-analyze.md` and follow those instructions.

3. All output goes into `workspaces/<project>/01-analysis/`, `workspaces/<project>/02-plans/`, and `workspaces/<project>/03-user-flows/`.
