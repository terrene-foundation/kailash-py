---
name: redteam
description: "Load phase 04 (validate) for the current workspace. Red team testing."
---

Load the validation phase for a workspace project.

1. Determine the workspace:
   - If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
   - Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
   - If no workspace exists, ask the user to create one first

2. Read `workspaces/<project>/instructions/04-validate.md` and follow those instructions.

3. Check workspace state:
   - Verify `todos/active/` is empty (all implemented) or note remaining items
   - Read `workspaces/<project>/03-user-flows/` for validation criteria

4. Validation results go into `workspaces/<project>/04-validate/`.

5. If gaps are found, document them and feed back to implementation (use `/implement` to fix).

## Agent Teams

Deploy these agents as a red team for validation:

**Core red team (always):**

- **testing-specialist** — Verify 3-tier test coverage, NO MOCKING compliance
- **e2e-runner** — Generate and run Playwright E2E tests (web) or Marionette tests (Flutter)
- **value-auditor** — Evaluate every page/flow from skeptical enterprise buyer perspective
- **security-reviewer** — Full security audit across the codebase

**Validation perspectives (deploy selectively based on findings):**

- **deep-analyst** — Identify failure points, edge cases, systemic issues
- **coc-expert** — Check methodological compliance: are guardrails in place? Is institutional knowledge captured? Are the three fault lines addressed?
- **gold-standards-validator** — Compliance check against project standards
- **intermediate-reviewer** — Code quality review across all changed files

**Frontend validation (if applicable):**

- **uiux-designer** — Audit visual hierarchy, responsive behavior, accessibility
- **ai-ux-designer** — Audit AI interaction patterns (if AI-facing UI)

Run multiple red team rounds. Converge when all agents find no remaining gaps.
