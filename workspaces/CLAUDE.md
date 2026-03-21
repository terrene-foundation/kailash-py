# Workspaces Scope

Workspaces are session/run records. The `briefs/` directory is the **only place users write** — everything else is agent output. The actual codebase (`src/`, `packages/`, `docs/`) lives at the **project root**, not inside workspaces.

Read `.claude/` freely but never write to it except `.claude/agents/project/` and `.claude/skills/project/` during phase 05.

## Phase Contract

Follow phases in order using slash commands. Each command is self-contained — it includes workspace detection, workflow steps, and agent teams.

Phases use two gate types (see `rules/autonomous-execution.md`): **structural gates** require human authority; **execution gates** are autonomous agent convergence (human observes, does not block).

| Phase | Command      | Workspace Output                              | Project Root Output                                  | Gate Type              | Gate                                      |
| ----- | ------------ | --------------------------------------------- | ---------------------------------------------------- | ---------------------- | ----------------------------------------- |
| 01    | `/analyze`   | `01-analysis/`, `02-plans/`, `03-user-flows/` |                                                      | Execution (autonomous) | Red team agents converge                  |
| 02    | `/todos`     | `todos/active/`                               |                                                      | **Structural (human)** | Human approves plan                       |
| 03    | `/implement` | `todos/active/` -> `todos/completed/`         | `src/`, `packages/`, `docs/`                         | Execution (autonomous) | All tests passing, review agents converge |
| 04    | `/redteam`   | `04-validate/`                                |                                                      | Execution (autonomous) | Red team agents find no gaps              |
| 05    | `/codify`    |                                               | `.claude/agents/project/`, `.claude/skills/project/` | **Structural (human)** | Human approves institutional knowledge    |

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
