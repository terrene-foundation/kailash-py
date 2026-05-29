# Working with Codex CLI on loom COC

A starter guide for developers using the Codex CLI (`@openai/codex`, v0.128+) on a loom-powered COC-enabled repo. Peer guide to `.claude/guides/claude-code/` (CC) and `.claude/guides/gemini/` (Gemini).

> **Heads up (2026-05-28, issue #385):** OpenAI deprecated custom prompts in favor of skills, and Codex CLI 0.128+ no longer discovers repo-local `.codex/prompts/` (only `~/.codex/prompts/`; see openai/codex#9848). loom's canonical Codex invocation is the **`bin/coc <phase> "<prompt>"` dispatcher** emitted by `/sync` to `<repo>/bin/coc`. Phase shims `bin/coc-<phase>` are symlinks to the same dispatcher.

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
| `bin/coc` unified dispatcher             | `.claude/codex-templates/bin/coc`      | `<repo>/bin/coc` + `<repo>/bin/coc-<phase>` symlinks (invoked `bin/coc <phase> "..."` — see #385) |
| `.codex/prompts/<name>.md` (docs only)   | `.claude/commands/<name>.md`           | `<repo>/.codex/prompts/<name>.md` (reference content; slash invocation deprecated 2026-05-28)    |
| `.codex/skills/<nn-name>/SKILL.md`       | `.claude/skills/<nn-name>/SKILL.md`    | `<repo>/.codex/skills/<nn-name>/SKILL.md`                     |
| `.codex-mcp-guard/server.js` (MCP guard) | `.claude/codex-mcp-guard/`             | `<repo>/.codex-mcp-guard/`                                    |
| MCP guard registered in config.toml      | auto-generated `[mcp_servers.*]` block | `<repo>/.codex/config.toml`                                   |

## Five things that are different from CC

1. **Baseline file is `AGENTS.md`, not `CLAUDE.md`.** Codex ignores CLAUDE.md. The loom emitter produces both so the repo supports both CLIs; each loads its own.
2. **Default size cap is 32,768 bytes.** Loom wrappers pass `-c project_doc_max_bytes=65536` to raise it. If you invoke Codex without the wrapper, AGENTS.md may be truncated at 32 KiB.
3. **`paths:` YAML frontmatter is NOT honored.** Codex walks git-root→cwd, concatenating every `AGENTS.md` it finds. Path-scoped rules must be placed in the relevant subdirectory's `AGENTS.md`, not in `.claude/rules/` with `paths:` frontmatter.
4. **Hooks fire on Bash only.** `apply_patch`, Write, MCP tool calls do NOT emit `PreToolUse`/`PostToolUse` — those must enforce via the `.codex-mcp-guard/server.js` MCP server (loom emits it automatically).
5. **External invocation is `bin/coc <phase>`, NOT slash commands.** OpenAI deprecated custom prompts 2026-05-28 (#385); CC's `/analyze` becomes `bin/coc analyze "..."` on Codex (or `bin/coc-analyze "..."` via the phase shim). The dispatcher runs `codex exec --json --output-schema=… -c project_doc_max_bytes=65536 -- "<prompt>"` against the per-phase schema at `.claude/wrappers/schemas/<phase>.schema.json`.

## Daily flow

```bash
# Interactive session (your usual)
cd my-loom-project
codex                        # reads AGENTS.md + .codex/config.toml auto

# Run a specific phase via the unified dispatcher (canonical path — #385)
bin/coc analyze   "Audit the connection-pool surface."
bin/coc todos     "Plan the dataflow migration."
bin/coc implement "Wire the auth handler."
# Equivalent phase-suffix shims (symlinks to bin/coc):
bin/coc-analyze   "Audit the connection-pool surface."

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

## Specialist delegation in Codex (deterministic shim — 2026-05-15, revised #385)

Codex's runtime exposes only generic subagent roles (`default`, `explorer`, `worker`); it has no native callable equivalents of COC specialists by name. To close that gap, loom's `emit-cli-artifacts.mjs` emits one `.codex/prompts/specialist-<name>.md` per non-excluded `.claude/agents/**/<name>.md` (function: `emitCodexAgentPrompts`) AND retains those files as **on-disk documentation/spec sources**. Each file wraps the specialist's full operating spec.

> **Invocation change (#385, 2026-05-28):** OpenAI deprecated custom prompts in favor of skills; Codex CLI 0.128+ does not discover repo-local `.codex/prompts/`. The historical `prompts:specialist-<name>` slash invocation no longer works in synced consumers. Until a skills-based specialist surface lands, use the patterns below:

1. **Inline persona via `cat` injection — works headless + interactive.**

   ```bash
   bin/coc implement "$(cat .codex/prompts/specialist-dataflow.md)

   Task: <your task here>"
   ```

   The dispatcher injects the operating spec into the prompt; the model operates as the named specialist for that turn.

2. **Worker subagent delegation — interactive Codex only.**

   ```text
   Delegate to a worker subagent. Operating spec — read .codex/prompts/specialist-reviewer.md
   from the workspace and operate per that spec.
   Task: ...
   ```

   Codex's native subagent spawn (natural-language, per developers.openai.com/codex/subagents) loads the spec at the spawn-prompt boundary; the subagent reads the file directly.

3. **Headless `codex exec` fallback** — same as pattern (1) via `bin/coc`.

Specialist coverage mirrors Gemini's emitter (`emitGeminiAgents`) — same exclusion intent: peer-CLI architects (`cc-architect`, `codex-architect`, `gemini-architect`), `cli-orchestrator`, `management/**`, and `_README.md` are excluded.

## Known limitations (empirically verified 2026-04-22/23, revised 2026-05-28 per #385)

- **Custom prompts deprecated; repo-local `.codex/prompts/` not discovered.** OpenAI deprecated the custom-prompts surface 2026-05-28 in favor of skills; repo-local discovery was rejected upstream (openai/codex#9848). loom ships `bin/coc <phase>` (canonical) + `.codex/prompts/` as on-disk reference content.
- **Headless `codex exec` does not invoke subagents via any syntax.** Native subagents (per developers.openai.com/codex/subagents) use natural-language spawn in interactive sessions. Headless exec may not spawn them reliably. **Workaround**: use the inline-persona-via-`cat` pattern above — works in both modes.
- **`paths:` YAML frontmatter is completely ignored.** Do not expect path-scoped rule injection. Directory-hierarchy AGENTS.md is the only scoping mechanism. A loom-side pre-tool rule loader is the planned follow-up (Shard 2 of the parity-gap workstream).
- **GitHub Copilot's `.github/instructions/*.instructions.md` with `applyTo:` glob is NOT supported by Codex.** Different tool. Don't expect it.

## Further reading

- CC peer guide: `.claude/guides/claude-code/`
- Gemini peer guide: `.claude/guides/gemini/`
- Codex-architect spec: `.claude/agents/codex-architect.md`
- Official docs: [developers.openai.com/codex](https://developers.openai.com/codex)
- loom codex-templates source: `.claude/codex-templates/`
