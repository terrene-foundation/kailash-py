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

## Execution Model

This phase executes under the **autonomous execution model** (see `rules/autonomous-execution.md`). Red team validation is fully autonomous — agent teams converge through iterative rounds until no gaps remain. This is an execution gate, not a structural gate: the human observes the outcome but does not block convergence. Findings are fixed autonomously (zero-tolerance), not reported for human triage. Do not estimate convergence in human-days; estimate in autonomous red team rounds.

## Workflow

### 1. Spec coverage audit (MUST run first)

Before any code quality checks, verify **what was specified was actually built**:

1. Read every file in `workspaces/<project>/02-plans/` and `workspaces/<project>/todos/completed/`
2. For each planned feature, endpoint, architecture component, or data flow:
   - **Exists?** — grep codebase for the implementation (file/class/function/route)
   - **Wired?** — does it call real APIs/services, or use mock/generated data?
   - **Architecture?** — do planned abstractions (data fabric, ML fabric, etc.) exist as designed, not just replaced with ad-hoc calls?
3. Flag every item that is missing, unwired, or architecturally substituted
4. Write results to `workspaces/<project>/.spec-coverage` (plan item → status: implemented/unwired/missing/substituted). Subsequent rounds read this file to verify coverage was checked.

**A file existing is NOT completion. Real data flowing end-to-end is completion.**

Detection patterns for unwired frontend code:

- Functions named `generate*()` or `mock*()` producing synthetic data
- Constants named `MOCK_*`, `FAKE_*`, `DUMMY_*`, `SAMPLE_*`
- Hardcoded arrays/objects serving as page data instead of API calls
- `fetch()` or API calls that are commented out or absent where plans require them

### 2. End-to-end validation

Review implementation with red team agents using playwright mcp (web) and marionette mcp (flutter).

- Test all workflows end-to-end:
  - Using backend API endpoints only
  - Using frontend API endpoints only
  - Using browser via Playwright MCP only

### 3. User flow validation

Ensure red team agents peruse `workspaces/<project>/03-user-flows/` and fully understand the detailed storyboard for each user.

- Include tests written from user workflow perspectives
  - Workflows must be extremely detailed
  - Every step should include: what is seen, what is clicked, what is expected, how to proceed, does it show value
  - Every transition between steps must be analyzed and evaluated
- Focus on intent, vision, and user requirements — never naive technical assertions
- Every action and expectation from user must be evaluated against implementation

### 4. Test-once protocol — do NOT re-run existing tests

The `/implement` phase already ran the full test suite and wrote `.test-results`. Red team agents MUST:

1. **READ** `workspaces/<project>/.test-results` to verify all tests passed with 0 regressions
2. **READ** test source files to verify coverage and quality — do NOT re-execute them
3. **RUN** only NEW tests that red team writes (E2E user flow tests, Playwright/Marionette tests)
4. If `.test-results` is missing or stale (commit hash doesn't match HEAD), flag it — don't silently re-run

**When to re-run existing tests (exceptions):**

- Red team suspects a specific test is wrong (tests the wrong thing) — re-run THAT test only
- Infrastructure-dependent tests that /implement ran against SQLite but production uses PostgreSQL
- Red team made code changes during convergence — re-run affected tests only, then update `.test-results`

**Iterate until convergence** on gaps found through:

- User flow validation (Playwright/Marionette — these are NEW tests, always run)
- Code review findings that require fixes
- Security audit findings that require fixes
- After each fix, run only the affected tests + the new regression test for the fix

### 5. Report results

Report all detailed steps and results taken in validation and testing tasks.

### 6. Parity check (if required)

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

- **deep-analyst** — **Step 1 owner**: read every plan in `02-plans/`, compare against codebase, produce `.spec-coverage` report. Also: failure points, edge cases, systemic issues.
- **testing-specialist** — Verify 3-tier test coverage, Real infrastructure recommended compliance
- **e2e-runner** — Generate and run Playwright E2E tests (web) or Marionette tests (Flutter)
- **value-auditor** — Evaluate every page/flow from skeptical enterprise buyer perspective
- **security-reviewer** — Full security audit across the codebase

**Validation perspectives (deploy selectively based on findings):**

- **coc-expert** — Check methodological compliance: are guardrails in place? Is institutional knowledge captured? Are the three fault lines addressed?
- **gold-standards-validator** — Compliance check against project standards
- **intermediate-reviewer** — Code quality review across all changed files

**Frontend validation (if applicable):**

- **uiux-designer** — Audit visual hierarchy, responsive behavior, accessibility
- **ai-ux-designer** — Audit AI interaction patterns (if AI-facing UI)

## Convergence Criteria

ALL of the following must be true for convergence:

1. **0 CRITICAL findings** across all agents
2. **0 HIGH findings** across all agents
3. **2 consecutive clean rounds** (no new findings)
4. **Spec coverage: 100%** — every planned feature, endpoint, and architecture component verified as existing AND wired to real data (step 1 audit passes with zero gaps)
5. **Frontend integration: 0 mock data** — no `MOCK_*/FAKE_*/DUMMY_*` constants, no `mock*()`/`generate*Data()`-style functions producing synthetic data, no hardcoded arrays serving as page data in production code

Criteria 1-3 are necessary but NOT sufficient. Without 4-5, convergence certifies code quality on incomplete software.

### Journal

Create journal entries for validation findings:

- **RISK** entries for vulnerabilities, weaknesses, or failure modes discovered
- **GAP** entries for missing tests, documentation, or edge cases
- **CONNECTION** entries for unexpected dependencies or interactions found

Use sequential naming: check the highest existing `NNNN-` prefix and increment.
