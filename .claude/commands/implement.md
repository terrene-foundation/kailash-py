---
name: implement
description: "Load phase 03 (implement) for the current workspace. Repeat until all todos complete."
---

## Workspace Resolution

1. If `$ARGUMENTS` specifies a project name or todo, parse accordingly
2. Otherwise, use the most recently modified directory under `workspaces/` (excluding `instructions/`)
3. If no workspace exists, ask the user to create one first
4. Read all files in `workspaces/<project>/briefs/` for user context (this is the user's input surface)

## Phase Check

- Read files in `workspaces/<project>/todos/active/` to see what needs doing
- Read files in `workspaces/<project>/todos/completed/` to see what's done
- If `$ARGUMENTS` specifies a specific todo, focus on that one
- Otherwise, pick the next active todo
- Reference plans in `workspaces/<project>/02-plans/` for context

## Execution Model

This phase executes under the **autonomous execution model** (see `rules/autonomous-execution.md`). Implementation is fully autonomous — agents execute in parallel, self-validate through TDD, and converge through quality gates. The human observes outcomes but does not sit in the execution loop. Pre-existing failures are fixed, not reported (zero-tolerance). Agent-to-agent delegation (reviewer, security-reviewer) is autonomous, not human-gated.

## Workflow

### NOTE: Run `/implement` repeatedly until all todos/active have been moved to todos/completed

### 1. Prepare todos

You MUST always use the todo-manager to create detailed todos for EVERY SINGLE TODO in `todos/000-master.md`.

- Review with agents before implementation
- Ensure that both FE and BE detailed todos exist, if applicable

### 2. Context anchoring (MUST run before each todo)

Before implementing ANY todo, re-read the source material that spawned it:

1. **Re-read the plan section** in `02-plans/` that this todo implements — not the whole directory, but the specific plan paragraphs. If the plan describes a `DataFabric` class with 3 methods, you are building that class with those 3 methods.
2. **Re-read relevant journals** in `workspaces/<project>/journal/` — decisions, trade-offs, and risks from analysis inform how to implement. If a journal says "chose event-driven over polling because of X," the implementation must be event-driven.
3. **Re-read the todo itself** — the description, not just the title. Todos have implementation details that get ignored when agents skim titles.

**Why this step exists**: Without it, agents implement from vague memory of what they think the todo means, not from what was actually specified. Plans describe 15 details; agents remember 3. The other 12 become mock data and missing features.

### 3. Implement

Continue with the implementation of the next todo/phase using a team of agents, following procedural directives.

- Ensure that both FE and BE are implemented, if applicable

### 4. Quality standards

Always involve tdd-implementer, testing-specialists, value auditor, ai ui ux specialists, with any agents relevant to the work at hand.

- Test for rigor, completeness, and quality of output from both value and technical user perspectives
- Pre-existing failures often hint that you are missing something obvious and critical
  - Always address pre-existing failures — do not pass until all failures, warnings, hints are resolved
- Always identify the root causes of issues, and implement optimal, elegant fixes

### 5. Testing requirements

Follow the **test-once protocol** from `rules/testing.md`:

1. **Baseline**: Run `pytest tests/ -x --tb=short -q` ONCE before implementing. Record pass/fail counts.
2. **TDD cycle**: tdd-implementer runs affected tests during red-green-refactor (the ONE authoritative run).
3. **Regression check**: Run full suite ONCE when todo is complete. Compare against baseline -- any new failures = regression, STOP and fix.
4. **Write `.test-results`** to `workspaces/<project>/.test-results` (commit hash, pass/fail counts, regression count).
5. **Bug fixes** MUST include regression test in `tests/regression/` marked `@pytest.mark.regression`.

Do NOT run the full suite multiple times per todo. Do NOT re-run tests that tdd-implementer already ran.

### 6. LLM usage

When writing and testing agents, always utilize the LLM's capabilities instead of naive NLP approaches (keywords, regex, etc).

- Use ollama or openai (if ollama is too slow)
- Always check `.env` for api keys and model names to use in development
  - Always assume model names in memory are outdated — perform a web check on model names in `.env` before declaring them invalid

### 7. Spec-verify and close todos

Before moving ANY todo from `active/` to `completed/`, MUST:

1. **Re-read the plan section** that spawned this todo (same files from step 2)
2. **Check every detail** — not "does the file exist" but "does the implementation match what the plan specified, line by line"
3. **Check wiring** — if the todo involves UI, verify it calls real APIs (not mock/generated data). If it involves an architecture component, verify the designed abstraction exists (not ad-hoc replacements).
4. **Check journals** — if analysis journals flagged risks or constraints for this area, verify they were addressed
5. **Write verification record** — append a `## Verification` section to the todo file listing what was checked (plan reference, wiring status, journal constraints addressed). This is the audit trail — without it, "verified" is an unsubstantiated claim.

A todo is complete when the plan says X and the code does X. Not when the code does something and happens to compile.

### 8. Integration hygiene checklist (end of each cycle)

Before reporting the cycle complete, print this 4-line check and tick each box:

```
[ ] Every new endpoint has entry + exit + error logs (observability.md § Mandatory Log Points)
[ ] Every integration point (DB, HTTP, MQ) logged with correlation ID
[ ] Zero raw SQL / direct HTTP / mock data introduced (framework-first.md § Work-Domain Binding)
[ ] Log triage clean or each WARN explicitly acknowledged (observability.md MUST Rule 5)
```

If any box cannot be ticked, fix before closing the cycle. The `integration-hygiene.js` PostToolUse hook catches most violations as they land; this checklist is the final pass.

At the end of each implementation cycle, update documentation at the **project root** (not workspace):

- `docs/` — complete codebase docs; `docs/00-authority/` — authoritative `README.md` + `CLAUDE.md`
- Focus on essence and intent ('what it is', 'how to use it'), not status/progress

## Agent Teams

Deploy these agents as a team for each implementation cycle:

**Core team (always):**

- **tdd-implementer** — Test-first development, red-green-refactor
- **testing-specialist** — 3-tier test strategy, Real infrastructure recommended in Tier 2-3
- **reviewer** — Code review after every file change (MANDATORY)
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
- **uiux-designer** — AI interaction patterns (if AI-facing UI)
- **react-specialist** — Responsive UI components

**Recovery (invoke when builds break):**

- **build-fix** — Fix build/type errors with minimal changes (NO architectural changes)

**Quality gate (once per todo, before closing):**

- **value-auditor** — Evaluate from user/buyer perspective, not just technical assertions
- **security-reviewer** — Security audit before any commit (MANDATORY)

### Journal (MUST — phase-complete gate)

Before reporting each cycle complete, create journal entries for journal-worthy findings produced this cycle:

- **DECISION** — implementation choices made (architecture, library selection, design patterns)
- **DISCOVERY** — technical findings that surprised you or contradict prior assumptions
- **RISK** — potential issues discovered but not yet resolved

Use `/journal new <TYPE> <slug>` (or write directly to `workspaces/<project>/journal/NNNN-TYPE-slug.md`). Skip only when the cycle genuinely produced nothing journal-worthy — use judgment, not formulas. Do not batch: create each entry as you recognize it.
