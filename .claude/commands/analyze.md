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

## Agent Teams

Deploy these agents as a team for analysis:

- **deep-analyst** — Failure analysis, complexity assessment, identify risks
- **requirements-analyst** — Break down requirements, create ADRs, define scope
- **coc-expert** — Ground analysis in COC methodology; identify institutional knowledge gaps and guard against the three fault lines (amnesia, convention drift, security blindness)
- **framework-advisor** — Choose implementation approach (if applicable)
- **sdk-navigator** — Find existing patterns and documentation before designing from scratch (if applicable)

For product/market analysis, additionally deploy:

- **value-auditor** — Evaluate from enterprise buyer perspective, critique value propositions

For frontend projects, additionally deploy:

- **uiux-designer** — Information architecture, visual hierarchy, design system planning
- **ai-ux-designer** — AI interaction patterns (if the project involves AI interfaces)

Red team the analysis with agents until they confirm no gaps remain in research, plans, and user flows.
