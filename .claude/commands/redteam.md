---
name: redteam
description: "Load phase 04 (validate) for the current workspace. Red team testing."
---

## Workspace Resolution

1. If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
2. Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
3. If no workspace exists, ask the user to create one first
4. Read all files in `workspaces/<project>/briefs/` for user context (this is the user's input surface)

## Phase Check

- Verify `todos/active/` is empty (all implemented) or note remaining items
- Read `workspaces/<project>/03-user-flows/` for validation criteria
- Validation results go into `workspaces/<project>/04-validate/`
- If gaps are found, document them and feed back to implementation (use `/implement` to fix)

## Workflow

### 1. End-to-end validation

Review implementation with red team agents using playwright mcp (web) and marionette mcp (flutter).

- Test all workflows end-to-end:
  - Using backend API endpoints only
  - Using frontend API endpoints only
  - Using browser via Playwright MCP only

### 2. User flow validation

Ensure red team agents peruse `workspaces/<project>/03-user-flows/` and fully understand the detailed storyboard for each user.

- Include tests written from user workflow perspectives
  - Workflows must be extremely detailed
  - Every step should include: what is seen, what is clicked, what is expected, how to proceed, does it show value
  - Every transition between steps must be analyzed and evaluated
- Focus on intent, vision, and user requirements — never naive technical assertions
- Every action and expectation from user must be evaluated against implementation

### 3. Iterate until convergence

Continuously engage red team agents:

- Identify root causes of gaps
- Implement the most optimal and elegant fix
- Test and ensure no regressions
- Keep iterating until red team agents find no more gaps/issues/improvements

### 4. Report results

Report all detailed steps and results taken in validation and testing tasks.

### 5. Parity check (if required)

If parity with an existing system is required:

- Do not compare codebases using logic
- Test run the old system via all required workflows and write down the output
  - Run multiple times to determine if outputs are deterministic (labels, numbers) or natural language based
- For all natural language based output:
  - DO NOT test via simple assertions using keywords and regex
  - Use LLM to evaluate the output and output confidence level + rationale
  - The LLM keys are in `.env`, use gpt-5.2-nano

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
