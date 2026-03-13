# Workspaces

Workspaces are session/run records. They capture what you want done and what the agents produced. The actual solution (`src/`, `packages/`, `docs/`) lives at the project root.

**`briefs/` is the only place users write.** Everything else is agent output.

## Quick Start

```bash
# Copy the template to create a new workspace
cp -r workspaces/_template workspaces/my-project

# Write your brief
edit workspaces/my-project/briefs/01-product-brief.md

# Run the phases
/analyze
/todos
/implement   # repeat until all todos complete
/redteam
/codify
```

## Structure

```
project-root/
  src/                     # Core SDK codebase (persistent)
  packages/                # Framework packages (persistent)
  docs/                    # Project documentation (persistent)
  workspaces/
    _template/             # Copy this to start a new workspace
      briefs/              # User input (the ONLY place users write)
        01-product-brief.md
      01-analysis/         # Agent output: research
      02-plans/            # Agent output: implementation plans
      03-user-flows/       # Agent output: user storyboards
      04-validate/         # Agent output: red team results
      todos/               # Task tracking (active/, completed/)
    <session-name>/        # One directory per sprint/session/run
```

## How It Works

### 1. Create a workspace

Copy the template:

```
cp -r workspaces/_template workspaces/my-saas-app
```

### 2. Write your briefs

Add files to `briefs/` — this is the only place you write. Number them sequentially:

- `01-product-brief.md` — initial vision, tech stack, constraints, users
- `02-add-auth.md` — new feature request mid-session
- `03-gap-feedback.md` — corrections after reviewing agent output

All phase commands read every file in `briefs/` for context.

### 3. Follow the phases using slash commands

Each command is self-contained: it detects the workspace, reads your briefs, includes all workflow steps, and deploys the right agent teams.

| Phase | Command      | Workspace Output                              | Project Root Output                                  | Gate              |
| ----- | ------------ | --------------------------------------------- | ---------------------------------------------------- | ----------------- |
| 01    | `/analyze`   | `01-analysis/`, `02-plans/`, `03-user-flows/` |                                                      | Human review      |
| 02    | `/todos`     | `todos/active/`                               |                                                      | Human approval    |
| 03    | `/implement` | `todos/active/` -> `todos/completed/`         | `src/`, `packages/`, `docs/`                         | All tests passing |
| 04    | `/redteam`   | `04-validate/`                                |                                                      | Red team sign-off |
| 05    | `/codify`    |                                               | `.claude/agents/project/`, `.claude/skills/project/` | Human review      |

Additional commands: `/ws` (status dashboard), `/wrapup` (save session notes before ending).

### 4. Iterate within and between phases

- Phase 03 (implement) is designed to be repeated until all todos move from `todos/active/` to `todos/completed/`
- Phase 03 writes code to `src/`, `packages/` and updates `docs/` at the project root
- Phase 04 (validate) feeds back into 03 — gaps found trigger implementation fixes
- Phase 05 (codify) distills knowledge into reusable project agents and skills
- Add new briefs to `briefs/` at any time — agents pick them up on the next command run

## Key Principles

**`briefs/` is the user input surface.** Under COC, this is the only place users write in the workspace. Everything else is agent output. Users express intent here; agents do the rest.

**Workspaces are session records, not codebases.** They track briefs, analysis, plans, and validation. The actual code and docs live at the project root.

**Commands are self-contained.** Each phase command includes workspace detection, workflow steps, and agent team definitions.

**`.claude/` is infrastructure, not workbench.** Do not modify during project sessions — except for `project/` subdirectories in phase 05.

**Session continuity.** Run `/wrapup` before ending a session to save `.session-notes` in the workspace. The next session automatically detects and resumes.
