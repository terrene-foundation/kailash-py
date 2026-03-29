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

This phase executes under the **autonomous execution model** (see `rules/autonomous-execution.md`). Implementation is fully autonomous — agents execute in parallel, self-validate through TDD, and converge through quality gates. The human observes outcomes but does not sit in the execution loop. Pre-existing failures are fixed, not reported (zero-tolerance). Agent-to-agent delegation (intermediate-reviewer, security-reviewer) is autonomous, not human-gated.

## Workflow

### NOTE: Run `/implement` repeatedly until all todos/active have been moved to todos/completed

### 1. Prepare todos

You MUST always use the todo-manager to create detailed todos for EVERY SINGLE TODO in `todos/000-master.md`.

- Review with agents before implementation
- Ensure that both FE and BE detailed todos exist, if applicable

### 2. Implement

Continue with the implementation of the next todo/phase using a team of agents, following procedural directives.

- Ensure that both FE and BE are implemented, if applicable

### 3. Quality standards

Always involve tdd-implementer, testing-specialists, value auditor, ai ui ux specialists, with any agents relevant to the work at hand.

- Test for rigor, completeness, and quality of output from both value and technical user perspectives
- Pre-existing failures often hint that you are missing something obvious and critical
  - Always address pre-existing failures — do not pass until all failures, warnings, hints are resolved
- Always identify the root causes of issues, and implement optimal, elegant fixes

### 4. Testing requirements

Follow the **test-once protocol** from `rules/testing.md`:

1. **Baseline**: Run `pytest tests/ -x --tb=short -q` ONCE before implementing. Record pass/fail counts.
2. **TDD cycle**: tdd-implementer runs affected tests during red-green-refactor (the ONE authoritative run).
3. **Regression check**: Run full suite ONCE when todo is complete. Compare against baseline -- any new failures = regression, STOP and fix.
4. **Write `.test-results`** to `workspaces/<project>/.test-results` (commit hash, pass/fail counts, regression count).
5. **Bug fixes** MUST include regression test in `tests/regression/` marked `@pytest.mark.regression`.

Do NOT run the full suite multiple times per todo. Do NOT re-run tests that tdd-implementer already ran.

### 5. LLM usage

When writing and testing agents, always utilize the LLM's capabilities instead of naive NLP approaches (keywords, regex, etc).

- Use ollama or openai (if ollama is too slow)
- Always check `.env` for api keys and model names to use in development
  - Always assume model names in memory are outdated — perform a web check on model names in `.env` before declaring them invalid

### 6. Update docs and close todos

After completing each todo:

- Move it from `todos/active/` to `todos/completed/`
- Ensure every task is verified with evidence before closing

At the end of each implementation cycle, create and update documentation at the **project root** (not inside the workspace):

- `docs/` (complete detailed docs capturing every detail of the codebase)
  - This is the last resort document that agents use to find elusive and deep documentation
- `docs/00-authority/`
  - Authoritative documents that developers and codegen read first for full situational awareness
  - Ensure you create/update `README.md` (navigating authority documents) and `CLAUDE.md` (preloaded instructions)
- Use as many subdirectories and files as required, naming them sequentially 00-, 01- for easy referencing
- Focus on capturing the essence and intent — the 'what it is' and 'how to use it' — not status/progress/reports

## Agent Teams

Deploy these agents as a team for each implementation cycle:

**Core team (always):**

- **tdd-implementer** — Test-first development, red-green-refactor
- **testing-specialist** — 3-tier test strategy, Real infrastructure recommended in Tier 2-3
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

### Journal

After completing each task, create journal entries for insights produced:
- **DECISION** entries for implementation choices (architecture, library selection, design patterns)
- **DISCOVERY** entries for technical findings during development
- **RISK** entries for potential issues discovered during implementation

Use sequential naming: check the highest existing `NNNN-` prefix and increment.
