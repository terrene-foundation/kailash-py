---
name: ws
description: "Show workspace status dashboard. Read-only."
---

Display the current workspace status. Do not modify any files.

1. List all directories under `workspaces/` (excluding `instructions/`).

2. For the most recently modified workspace (or `$ARGUMENTS` if specified):
   - Show workspace name and path
   - Derive current phase from filesystem:
     - Has `01-analysis/` files -> Analysis done
     - Has `todos/active/` files -> Todos created
     - Has `todos/completed/` files -> Implementation in progress
     - Has `04-validate/` files -> Validation done
     - Agents/skills were updated in phase 05 -> Codification done (check workspace `.session-notes` or `04-validate/`)
   - Count files in `todos/active/` vs `todos/completed/`
   - List the 5 most recently modified files in the workspace
   - If `.session-notes` exists, show its contents and age

### Journal
- Read the workspace's `journal/` directory
- Count total entries and entries by type
- Show the 3 most recent entries (number, type, date, topic)

3. Present as a compact summary.
