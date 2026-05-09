---
name: redteam
description: "Load phase 04 (validate) for the current workspace. Red team testing."
---

## Workspace Resolution

1. If `$ARGUMENTS` specifies a project name, use `workspaces/$ARGUMENTS/`
2. Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
3. If no workspace exists, ask the user to create one first
4. Read all files in `workspaces/<project>/briefs/` for user context

## Phase Check

- Verify `todos/active/` is empty (all implemented) or note remaining items
- Read `workspaces/<project>/03-user-flows/` for validation criteria
- Validation results go into `workspaces/<project>/04-validate/`
- If gaps are found, document them and feed back to implementation (use `/implement` to fix)

## Execution Model

Autonomous execution model (see `rules/autonomous-execution.md`). Red team converges through iterative rounds. Findings are fixed autonomously, not reported for human triage.

## Workflow

### 0. Posture-aware audit depth (MUST consult first)

Read `.claude/learning/posture.json` via `state-io.js::readPosture`. Audit rigor scales with posture per `skills/32-trust-posture/redteam-integration.md`:

- **L5_DELEGATED**: Round 1 OPTIONAL
- **L4_CONTINUOUS_INSIGHT**: Round 1 MANDATORY (mechanical sweeps)
- **L3_SHARED_PLANNING**: Round 1 + Round 2 MANDATORY (closure-parity)
- **L2_SUPERVISED**: full red-team Round 1+2+3 (incl. spec compliance vs every pending_verification rule)
- **L1_PSEUDO_AGENT**: advisory simulation only (no autonomous /implement to red-team)

Surface the posture in the first report line. Under-auditing (e.g., Round 1 only at L3) is itself a violation logged via `appendViolation` against `redteam/posture-aware-depth`.

### 1. Spec compliance audit (MUST run first)

**File existence is NOT compliance.** Use the protocol in `skills/spec-compliance/SKILL.md` to verify each spec promise via AST parsing and targeted greps, NOT file existence or self-reports.

A "spec" is any documented promise about behavior, regardless of where it lives. Sources to audit:

- `specs/**` — domain specifications (PRIMARY source of truth)
- `workspaces/<project>/briefs/**` — user-supplied requirements
- `workspaces/<project>/01-analysis/**` — analyst findings, deep analyses, design notes
- `workspaces/<project>/02-plans/**` — implementation plans, ADRs, contracts
- `workspaces/<project>/todos/completed/**` — what each todo claimed to deliver
- Inline spec sections in README.md, CHANGELOG.md, or design docs the project references

For every spec promise found in these sources:

1. Extract literal acceptance assertions from the spec text (class signatures, field names, decorator call sites, MOVE shim semantics, security tests, migration completion).
2. Verify each assertion via grep or `ast.parse` against the actual code.
3. Re-derive every check from scratch — do NOT trust `.spec-coverage`, `.test-results`, `convergence-verify.py`, or any prior round's self-report. Self-reports are inputs to verify, not evidence to trust.
4. Save the assertion table to `workspaces/<project>/.spec-coverage-v2.md` (the `-v2` suffix prevents confusion with legacy file-existence reports).

**Critical patterns to flag (see `skills/spec-compliance/` for full list):**

- Class/method exists but constructor signature differs from spec
- Frozen dataclass missing spec-required fields (grep returns 0)
- `@deprecated` decorator defined in `deprecation.py` but never applied at call sites
- "MOVE A → B" tasks where source A still exists at full size (drift risk)
- New modules with zero importing tests (`grep -rln "from <new_module>" tests/` empty)
- `def run_stream / async def stream_*` methods with only one `yield` (fake stream)
- Consumer files still importing from OLD path after a "migrate to Y" task

**Specs-to-code verification** — for every file in `specs/`, extract assertions at FIELD level (not just endpoint/class level) and verify against code via grep/AST. Code diverging from spec without a logged deviation = HIGH. **Cross-spec consistency** — grep all specs for shared terms (TTLs, limits, field names, endpoint paths); contradictory values across specs = HIGH. **Brief-to-spec coverage** — for each requirement in `briefs/`, verify it maps to at least one spec section; unmapped requirements = HIGH. **Probe-coverage** — for every semantic harness assertion (refusal/recommendation/compliance/quality), verify a probe definition (schema + scoring rule) exists per `rules/probe-driven-verification.md` MUST-4; regex-on-semantic-claim = HIGH.

### 2. End-to-end validation

Review implementation with red team agents using playwright mcp (web) and marionette mcp (flutter).

- Test all workflows end-to-end:
  - Using backend API endpoints only
  - Using frontend API endpoints only
  - Using browser via Playwright MCP only

### 3. User flow validation

Red team agents read `workspaces/<project>/03-user-flows/` and validate every detailed storyboard.

- Workflows include: what is seen, clicked, expected, value delivered
- Every transition between steps must be evaluated
- Focus on intent, vision, requirements — never naive technical assertions

### 4. Test verification — re-derive, do NOT trust .test-results

See `rules/testing.md` § Audit Mode Rules.

1. Do NOT read `.test-results` to verify test counts. The file is written by `/implement` and may report old-code coverage while new spec modules have zero tests.
2. Run `pytest --collect-only -q` (or your project's equivalent test enumeration command) on the test directories.
3. For each new module the spec created, grep the test directory for an import of that module. Zero importing tests = HIGH finding regardless of "tests pass".
4. Run any NEW tests that red team writes (E2E, regression tests for findings).
5. If a test is suspected wrong, re-run THAT test specifically.

### 5. Report results

Report all detailed steps and results in validation. Include the assertion tables from Step 1 verbatim — every row must show the literal verification command and its actual output, not "exists: yes".

### 6. Parity check (if required)

If parity required: test-run old system, record outputs. For natural-language output, use LLM evaluation (not keyword/regex). See `.env` for model.

### 7. Log triage gate

Per `rules/observability.md` MUST Rule 5: scan build/test output + `*.log` for WARN+ entries. Group identical entries, disposition each as Fixed (commit SHA) / Deferred (tracked todo) / Upstream (pinned version) / False positive. Unacknowledged WARN+ entries BLOCK convergence.

## Agent Teams

**Core red team (always):**

- **analyst** — Step 1 owner. Reads `skills/spec-compliance/SKILL.md`, derives assertion tables from each plan, runs AST/grep verification, produces `.spec-coverage-v2.md`.
- **testing-specialist** — Step 4 owner. Re-derives test coverage via `pytest --collect-only` (or the project's equivalent). Verifies new modules have new tests.
- **value-auditor** — Skeptical buyer perspective on every page/flow
- **security-reviewer** — Full security audit; verifies every spec § Security Threats subsection has tests

**Validation perspectives (selective):**

- `co-reference` skill — methodological compliance
- **gold-standards-validator** — naming/licensing compliance
- **reviewer** — code quality across changed files

**Frontend validation (if applicable):**

- **uiux-designer** — visual hierarchy, responsive, accessibility, AI interaction

## Convergence Criteria

ALL must be true:

1. **0 CRITICAL findings** across all agents
2. **0 HIGH findings** across all agents
3. **2 consecutive clean rounds** (no new findings)
4. **Spec compliance: 100% AST/grep verified** — every spec section has an assertion table where every row shows a literal verification command (`grep …`, `ast.parse(…)`, `wc -l …`) and its actual output. Rows saying "exists: yes" are BLOCKED.
5. **New code has new tests** — `pytest --collect-only` shows ≥1 test importing each new module. Zero new tests for a new module = HIGH, regardless of suite-level "tests pass".
6. **Frontend integration: 0 mock data** — no `MOCK_*/FAKE_*/DUMMY_*` constants, no `mock*()` / `generate*Data()` functions, no hardcoded display arrays.

Criteria 1-3 are necessary but NOT sufficient. Without 4-6, convergence certifies code quality on incomplete software.

### Journal (MUST — phase-complete gate)

Before reporting `/redteam` complete, create journal entries for journal-worthy findings surfaced during validation:

- **RISK** — vulnerabilities, weaknesses, or failure modes discovered
- **GAP** — missing tests, docs, edge cases, or spec-compliance holes

Use `/journal new <TYPE> <slug>` (or write directly to `workspaces/<project>/journal/NNNN-TYPE-slug.md`). Skip only when validation genuinely produced nothing journal-worthy — use judgment, not formulas. Do not batch: create each entry as you recognize it.
