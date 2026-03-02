# Kailash Python SDK

Monorepo for the Kailash SDK ecosystem: Core SDK, DataFlow, Nexus, and Kaizen. All frameworks are built ON Core SDK — they don't replace it.

## Absolute Directives

These override ALL other instructions.

### 1. Framework-First

Never write code from scratch before checking whether the Kailash frameworks already handle it.

- Instead of direct SQL/SQLAlchemy/Django ORM → check with **dataflow-specialist**
- Instead of FastAPI/custom API gateway → check with **nexus-specialist**
- Instead of custom MCP server/client → check with **mcp-specialist**
- Instead of custom agentic platform → check with **kaizen-specialist**

### 2. .env Is the Single Source of Truth

All API keys and model names MUST come from `.env`. Never hardcode model strings like `"gpt-4"` or `"claude-3-opus"`. Root `conftest.py` auto-loads `.env` for pytest.

See `rules/env-models.md` for model-key pairings and enforcement details.

### 3. Implement, Don't Document

When you discover a missing feature, endpoint, or record — **implement or create it**. Do not note it as a gap and move on. The only acceptable skip is explicit user instruction.

See `rules/e2e-god-mode.md` and `rules/no-stubs.md` for enforcement details.

### 4. Mandatory Reviews

- **Code review** (intermediate-reviewer) after EVERY file change — see `rules/agents.md` Rule 1
- **Security review** (security-reviewer) before EVERY commit — NO exceptions — see `rules/agents.md` Rule 2
- **NO MOCKING** in Tier 2/3 tests — use real infrastructure — see `rules/testing.md`

## Rules Index

| Concern | Rule File | Scope |
|---|---|---|
| Agent orchestration & review mandates | `rules/agents.md` | Global |
| E2E god-mode testing | `rules/e2e-god-mode.md` | `tests/e2e/**`, `**/*e2e*`, `**/*playwright*` |
| API keys & model names | `rules/env-models.md` | `**/*.py`, `**/*.ts`, `**/*.js`, `.env*` |
| Git commits, branches, PRs | `rules/git.md` | Global |
| No stubs, TODOs, or placeholders | `rules/no-stubs.md` | Global |
| Kailash SDK execution patterns | `rules/patterns.md` | `**/*.py`, `**/*.ts`, `**/*.js` |
| Security (secrets, injection) | `rules/security.md` | Global |
| 3-tier testing, no mocking Tiers 2-3 | `rules/testing.md` | `tests/**`, `**/*test*`, `**/*spec*`, `conftest.py` |
| Auto-generated workflow instincts | `rules/learned-instincts.md` | Global |

**Note**: Rules with path scoping are loaded only when editing matching files. Global rules load every session.

## Kailash Platform

| Framework | Docs | Source | Install |
|---|---|---|---|
| **Core SDK** | `sdk-users/` | `src/kailash/` | `pip install kailash` |
| **DataFlow** | `sdk-users/apps/dataflow/` | `apps/kailash-dataflow/` | `pip install kailash-dataflow` |
| **Nexus** | `sdk-users/apps/nexus/` | `apps/kailash-nexus/` | `pip install kailash-nexus` |
| **Kaizen** | `sdk-users/apps/kaizen/` | `apps/kailash-kaizen/` | `pip install kailash-kaizen` |

## Critical Execution Rules

```python
# ALWAYS: runtime.execute(workflow.build())
# NEVER: workflow.execute(runtime)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Async (Docker/FastAPI):
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})

# String-based nodes only
workflow.add_node("NodeType", "node_id", {"param": "value"})

# Return structure is always (results, run_id)
```

## Agents

### Analysis & Planning

- **deep-analyst** — Failure analysis, complexity assessment
- **requirements-analyst** — Requirements breakdown, ADR creation
- **sdk-navigator** — Find patterns before coding
- **framework-advisor** — Choose Core SDK, DataFlow, Nexus, or Kaizen

### Framework Specialists (`agents/frameworks/`)

- **dataflow-specialist** — Database operations, auto-generated nodes
- **nexus-specialist** — Multi-channel platform, middleware, auth, handlers, presets
- **kaizen-specialist** — AI agents, signatures, multi-agent coordination
- **mcp-specialist** — MCP server implementation

### Core Implementation

- **pattern-expert** — Workflow patterns, nodes, parameters
- **tdd-implementer** — Test-first development
- **intermediate-reviewer** — Code review after changes (MANDATORY)
- **gold-standards-validator** — Compliance checking
- **build-fix** — Fix build/type errors with minimal changes
- **security-reviewer** — Security audit before commits (MANDATORY)

### Frontend & Design (`agents/frontend/`)

- **react-specialist** — React/Next.js frontends
- **flutter-specialist** — Flutter mobile/desktop apps
- **frontend-developer** — Responsive UI components
- **uiux-designer** — Enterprise UI/UX design
- **ai-ux-designer** — AI interaction patterns

### Testing & QA

- **testing-specialist** — 3-tier strategy with real infrastructure
- **documentation-validator** — Test code examples
- **e2e-runner** — Playwright E2E test generation
- **value-auditor** — Enterprise demo QA from buyer perspective

### Release & Operations (`agents/management/`)

- **git-release-specialist** — Git workflows, CI, releases
- **deployment-specialist** — Docker/Kubernetes deployment
- **todo-manager** — Project task tracking
- **gh-manager** — GitHub issue/project management

### Standards (`agents/standards/`)

- **care-expert** — CARE governance framework
- **coc-expert** — COC development methodology
- **eatp-expert** — EATP trust protocol

## Skills Navigation

For SDK implementation patterns, see `.claude/skills/` — organized by framework (`01-core-sdk` through `05-kailash-mcp`) and topic (`06-cheatsheets` through `28-coc-reference`).

## Framework-Specific Guides

| Framework | Quick Reference | Full Documentation |
|---|---|---|
| **DataFlow** | `sdk-users/apps/dataflow/CLAUDE.md` | Database operations, gotchas, Docker deployment |
| **Kaizen** | `sdk-users/apps/kaizen/CLAUDE.md` | AI agents, signatures, multi-modal |
| **Nexus** | `sdk-users/apps/nexus/CLAUDE.md` | Multi-channel, auth, middleware, handlers, presets |
| **Core SDK** | `.claude/skills/01-core-sdk/` | WorkflowBuilder, nodes, runtime patterns |

### Key DataFlow Gotchas

1. NEVER manually set `created_at`/`updated_at` (auto-managed)
2. CreateNode uses FLAT params; UpdateNode uses `filter` + `fields`
3. Primary key MUST be named `id`
4. `soft_delete` only affects DELETE, NOT queries
5. Use `$null`/`$exists` operators for NULL checking
6. Template syntax is `${}` NOT `{{}}` — `${input.user_id}` is correct
