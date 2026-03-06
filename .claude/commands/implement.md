---
name: implement
description: "Load phase 03 (implement) for the current workspace. Repeat until all todos complete."
---

Load the implementation phase for a workspace project.

1. Determine the workspace:
   - If `$ARGUMENTS` specifies a project name or todo, parse accordingly
   - Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
   - If no workspace exists, ask the user to create one first

2. Read `workspaces/<project>/instructions/03-implement.md` and follow those instructions.

3. Check workspace state:
   - Read files in `todos/active/` to see what needs doing
   - Read files in `todos/completed/` to see what's done
   - If `$ARGUMENTS` specifies a specific todo, focus on that one
   - Otherwise, pick the next active todo

4. Reference the plans in `workspaces/<project>/02-plans/` for context.

5. After completing each todo, move it from `todos/active/` to `todos/completed/`.

## Agent Teams

Deploy these agents as a team for each implementation cycle:

**Core team (always):**

- **tdd-implementer** — Test-first development, red-green-refactor
- **testing-specialist** — 3-tier test strategy, NO MOCKING in Tier 2-3
- **intermediate-reviewer** — Code review after every file change (MANDATORY)
- **todo-manager** — Track progress, update todo status, verify completion with evidence

**Specialist (invoke ONE matching the current todo):**

- **pattern-expert** — Workflow patterns, node configuration
- **dataflow-specialist** — Database operations (if project uses DataFlow)
- **nexus-specialist** — API deployment (if project uses Nexus)
- **kaizen-specialist** — AI agents (if project uses Kaizen)
- **mcp-specialist** — MCP integration (if project uses MCP)

**Frontend team (when implementing frontend):**

- **uiux-designer** — Design system, visual hierarchy, responsive layouts
- **react-specialist** or **flutter-specialist** — Framework-specific implementation
- **ai-ux-designer** — AI interaction patterns (if AI-facing UI)
- **frontend-developer** — Responsive UI components

**Recovery (invoke when builds break):**

- **build-fix** — Fix build/type errors with minimal changes (NO architectural changes)

**Quality gate (once per todo, before closing):**

- **value-auditor** — Evaluate from user/buyer perspective, not just technical assertions
- **security-reviewer** — Security audit before any commit (MANDATORY)
