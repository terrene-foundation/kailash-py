# Working with Codex CLI on loom COC

A starter guide for developers using the Codex CLI (`@openai/codex`, v0.122+) on a loom-powered COC-enabled repo. Peer guide to `.claude/guides/claude-code/` (CC) and `.claude/guides/gemini/` (Gemini).

## What Codex is

OpenAI's local coding agent CLI. Runs in terminal; reads `AGENTS.md` at session start; spawns shell commands; integrates MCP servers.

```bash
codex                  # interactive session
codex exec "<prompt>"  # one-shot non-interactive
codex review           # git-diff-aware review
```

Install: `npm install -g @openai/codex` (or `brew install codex` on macOS).

## How loom integrates with Codex

loom emits the Codex-side artifacts at `/sync` time:

| Artifact                                 | Source                                 | Emitted to                                                    |
| ---------------------------------------- | -------------------------------------- | ------------------------------------------------------------- |
| `AGENTS.md` (repo-root baseline)         | `.claude/rules/` (composed + abridged) | `<repo>/AGENTS.md`                                            |
| `.codex/config.toml`                     | `.claude/codex-templates/config.toml`  | `<repo>/.codex/config.toml`                                   |
| `.codex/hooks.json`                      | `.claude/codex-templates/hooks.json`   | `<repo>/.codex/hooks.json`                                    |
| `.codex/prompts/<name>.md` (slash cmds)  | `.claude/commands/<name>.md`           | `<repo>/.codex/prompts/<name>.md` (invoked `/prompts:<name>`) |
| `.codex/skills/<nn-name>/SKILL.md`       | `.claude/skills/<nn-name>/SKILL.md`    | `<repo>/.codex/skills/<nn-name>/SKILL.md`                     |
| `.codex-mcp-guard/server.js` (MCP guard) | `.claude/codex-mcp-guard/`             | `<repo>/.codex-mcp-guard/`                                    |
| MCP guard registered in config.toml      | auto-generated `[mcp_servers.*]` block | `<repo>/.codex/config.toml`                                   |

## Five things that are different from CC

1. **Baseline file is `AGENTS.md`, not `CLAUDE.md`.** Codex ignores CLAUDE.md. The loom emitter produces both so the repo supports both CLIs; each loads its own.
2. **Default size cap is 32,768 bytes.** Loom wrappers pass `-c project_doc_max_bytes=65536` to raise it. If you invoke Codex without the wrapper, AGENTS.md may be truncated at 32 KiB.
3. **`paths:` YAML frontmatter is NOT honored.** Codex walks git-root→cwd, concatenating every `AGENTS.md` it finds. Path-scoped rules must be placed in the relevant subdirectory's `AGENTS.md`, not in `.claude/rules/` with `paths:` frontmatter.
4. **Hooks fire on Bash only.** `apply_patch`, Write, MCP tool calls do NOT emit `PreToolUse`/`PostToolUse` — those must enforce via the `.codex-mcp-guard/server.js` MCP server (loom emits it automatically).
5. **Slash commands use `/prompts:<name>` namespace.** CC's flat `/analyze` is `/prompts:analyze` on Codex. The `prompts:` prefix is mandatory.

## Daily flow

```bash
# Interactive session (your usual)
cd my-loom-project
codex                        # reads AGENTS.md + .codex/config.toml auto

# Run a specific phase
/prompts:analyze              # inside the session
/prompts:todos
/prompts:implement

# Review uncommitted changes
codex review --uncommitted --base main

# Non-interactive one-shot
codex exec "Explain the connection-pool rule"
```

## How hooks work here

Hooks are registered in `.codex/hooks.json` (emitted from `.claude/codex-templates/hooks.json`). Event types:

- `SessionStart` — at startup
- `PreToolUse` / `PostToolUse` — around Bash (shell) tools only
- `PermissionRequest` — when the CLI asks to run a restricted command
- `UserPromptSubmit` — when you submit a prompt
- `Stop` — at session end

Each hook runs as a subprocess. Exit code 2 blocks the action. Full hook reference: [developers.openai.com/codex/hooks](https://developers.openai.com/codex/hooks).

## How the MCP guard works

The `.codex-mcp-guard/server.js` wraps non-Bash mutating tools (`apply_patch`, Write, MCP invocations) so they go through the same POLICIES table that `.codex/hooks.json` enforces at the Bash layer. Without the guard, file-write operations run unsupervised.

The guard is registered as an MCP server in `.codex/config.toml`:

```toml
[mcp_servers.codex-mcp-guard]
command = "node"
args = ["./.codex-mcp-guard/server.js"]
```

It ships with `POLICIES_POPULATED=false` and refuses to start (exit 2) until loom's emitter populates the POLICIES table from the hooks.js predicates. If you see "refusing to start with unpopulated POLICIES", `/sync` hasn't completed — that's a feature.

## Specialist delegation in Codex (deterministic shim — 2026-05-15)

Codex's runtime exposes only generic subagent roles (`default`, `explorer`, `worker`); it has no native callable equivalents of COC specialists by name. To close that gap, loom's `emit-cli-artifacts.mjs` emits one `.codex/prompts/specialist-<name>.md` per non-excluded `.claude/agents/**/<name>.md` (function: `emitCodexAgentPrompts`). Each emitted prompt wraps the specialist's full operating spec with a preamble describing three invocation patterns:

1. **Inline persona — most reliable; works headless + interactive.**

   ```text
   /prompts:specialist-dataflow
   ```

   The slash command injects the operating spec into the current session. Provide the task in the same turn; the remainder operates as the named specialist.

2. **Worker subagent delegation — interactive Codex only.**

   ```text
   Delegate to a worker subagent. Operating spec: /prompts:specialist-reviewer.
   Task: ...
   ```

   Codex's native subagent spawn (natural-language, per developers.openai.com/codex/subagents) loads the spec at the spawn-prompt boundary.

3. **Headless `codex exec` fallback.**

   Native subagent spawning is unreliable in headless mode. Use pattern (1).

The shim is the loom-side answer to the 2026-05-15 Codex follow-up that flagged the parity gap (specialists copied to disk but not natively executable). Specialist coverage mirrors Gemini's emitter (`emitGeminiAgents`) — same exclusion intent: peer-CLI architects (`cc-architect`, `codex-architect`, `gemini-architect`), `cli-orchestrator`, `management/**`, and `_README.md` are excluded. `/prompts` autocomplete shows the specialist name + description; type `/prompts:specialist-` as the prefix to filter.

## Known limitations (empirically verified 2026-04-22/23)

- **Headless `codex exec` does not invoke subagents via any syntax.** Native subagents (per developers.openai.com/codex/subagents) use natural-language spawn in interactive sessions. Headless exec may not spawn them reliably. **Workaround**: use the inline-persona pattern above — `/prompts:specialist-<name>` works in both modes.
- **`paths:` YAML frontmatter is completely ignored.** Do not expect path-scoped rule injection. Directory-hierarchy AGENTS.md is the only scoping mechanism. A loom-side pre-tool rule loader is the planned follow-up (Shard 2 of the parity-gap workstream).
- **GitHub Copilot's `.github/instructions/*.instructions.md` with `applyTo:` glob is NOT supported by Codex.** Different tool. Don't expect it.

## Further reading

- CC peer guide: `.claude/guides/claude-code/`
- Gemini peer guide: `.claude/guides/gemini/`
- Codex-architect spec: `.claude/agents/codex-architect.md`
- Official docs: [developers.openai.com/codex](https://developers.openai.com/codex)
- loom codex-templates source: `.claude/codex-templates/`
