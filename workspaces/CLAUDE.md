# Workspaces Scope

Workspaces are session/run records. The `briefs/` directory is the **only place users write** — everything else is agent output. The actual codebase (`src/`, `packages/`, `docs/`) lives at the **project root**, not inside workspaces.

Read `.claude/` freely but never write to it except `.claude/agents/project/` and `.claude/skills/project/` during phase 05.

## Phase Contract

Follow phases in order using slash commands. Each command is self-contained — it includes workspace detection, workflow steps, and agent teams.

Each phase has a human gate — do not proceed without approval.

| Phase | Command      | Workspace Output                              | Project Root Output                                  | Gate              |
| ----- | ------------ | --------------------------------------------- | ---------------------------------------------------- | ----------------- |
| 01    | `/analyze`   | `01-analysis/`, `02-plans/`, `03-user-flows/` |                                                      | Human review      |
| 02    | `/todos`     | `todos/active/`                               |                                                      | Human approval    |
| 03    | `/implement` | `todos/active/` -> `todos/completed/`         | `src/`, `packages/`, `docs/`                         | All tests passing |
| 04    | `/redteam`   | `04-validate/`                                |                                                      | Red team sign-off |
| 05    | `/codify`    |                                               | `.claude/agents/project/`, `.claude/skills/project/` | Human review      |

Additional: `/ws` (status dashboard), `/wrapup` (save session notes before ending).

## User Input Surface

`briefs/` is the only directory users write to. All commands read it for context. Users add numbered files over time:

- `01-product-brief.md` — initial vision, tech stack, constraints, users
- `02-add-payments.md` — new feature request
- `03-gap-feedback.md` — corrections or feedback on agent output
- etc.

Copy `workspaces/_template/` to start a new workspace.

## What Lives Where

**Workspace** (`workspaces/<name>/`) — session record:

- `briefs/` — user input (the ONLY place users write)
- `01-analysis/`, `02-plans/`, `03-user-flows/` — agent research output
- `04-validate/` — red team results
- `todos/` — task tracking

**Project root** — the actual solution:

- `src/` — core SDK codebase
- `packages/` — framework packages (DataFlow, Nexus, Kaizen, EATP)
- `docs/` — project documentation
- `.claude/agents/project/`, `.claude/skills/project/` — codified knowledge
