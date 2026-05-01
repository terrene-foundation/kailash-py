# Working with Gemini CLI on loom COC

A starter guide for developers using the Gemini CLI (`@google/gemini-cli`, v0.38+) on a loom-powered COC-enabled repo. Peer guide to `.claude/guides/claude-code/` (CC) and `.claude/guides/codex/` (Codex).

## What Gemini CLI is

Google's open-source AI agent that brings Gemini into the terminal. Reads `GEMINI.md` hierarchically from user-global + project-root + subdirectories. Supports native subagents, hooks, skills, MCP, TOML slash commands.

```bash
gemini                       # interactive
gemini -p "<prompt>"         # non-interactive (headless)
gemini -i "<prompt>"         # execute prompt then continue interactive
```

Install: `npm install -g @google/gemini-cli`.

## How loom integrates with Gemini

loom emits Gemini-side artifacts at `/sync` time:

| Artifact                                    | Source                                   | Emitted to                                            |
| ------------------------------------------- | ---------------------------------------- | ----------------------------------------------------- |
| `GEMINI.md` (repo-root baseline)            | `.claude/rules/` (composed + abridged)   | `<repo>/GEMINI.md`                                    |
| `.gemini/settings.json`                     | `.claude/gemini-templates/settings.json` | `<repo>/.gemini/settings.json`                        |
| `.gemini/agents/<name>.md` (subagents)      | `.claude/agents/<category>/<name>.md`    | `<repo>/.gemini/agents/<name>.md` (invoked `@<name>`) |
| `.gemini/commands/<name>.toml` (slash cmds) | `.claude/commands/<name>.md`             | `<repo>/.gemini/commands/<name>.toml` (TOML, NOT md)  |
| `.gemini/skills/<nn-name>/SKILL.md`         | `.claude/skills/<nn-name>/SKILL.md`      | `<repo>/.gemini/skills/<nn-name>/SKILL.md`            |
| MCP servers in settings.json                | auto-generated `mcpServers` block        | `<repo>/.gemini/settings.json`                        |

## Five things that are different from CC

1. **Baseline is `GEMINI.md`, hierarchical loader.** Unlike CC's fixed `CLAUDE.md`, Gemini walks user-global (`~/.gemini/GEMINI.md`) + project root + subdirectories. Subdirectory `GEMINI.md` files load whenever CWD is inside their subtree. `@file.md` imports inside `GEMINI.md` pull in additional content.
2. **Hook event names are `BeforeTool` / `AfterTool` — NOT `PreToolUse` / `PostToolUse`.** This is the #1 CC→Gemini translation pitfall. CC event names silently fire nothing on Gemini.
3. **Slash commands are TOML, not Markdown.** `.gemini/commands/analyze.toml`. CC `.md` slash commands in that directory silently do not register.
4. **Subagents are invoked via `@<agent-name>`** (native in interactive mode). Agent files live at `.gemini/agents/<name>.md` with YAML frontmatter (`name`, `description`, `tools`, `model`). Subagents cannot recursively invoke other subagents.
5. **`paths:` YAML frontmatter is NOT honored.** Path-scoped rules must live in directory-placed `GEMINI.md` files, not in `.claude/rules/*.md` with `paths:` frontmatter.

## Daily flow

```bash
# Interactive session
cd my-loom-project
gemini                         # reads root GEMINI.md + subdirs + .gemini/

# Invoke a subagent
> @dataflow-specialist please review the schema

# Run a slash command
> /analyze                     # flat name, no namespace prefix (vs Codex)

# Non-interactive
gemini -p "Explain the connection-pool rule"

# See composed context
> /memory show                 # prints what Gemini sees from GEMINI.md
```

## How hooks work here

Hooks are registered in `.gemini/settings.json` under the top-level `hooks` object.

```json
{
  "hooks": {
    "BeforeTool": [ { "matcher": "bash", "hooks": [...] } ],
    "AfterTool":  [ { "matcher": "write_file", "hooks": [...] } ],
    "SessionStart": [ {...} ]
  }
}
```

Full event list: `SessionStart`, `SessionEnd`, `BeforeTool`, `AfterTool`, `BeforeAgent`, `AfterAgent`, `BeforeModel`, `AfterModel`, `BeforeToolSelection`, `Notification`, `PreCompress`.

Each hook is a subprocess: stdin JSON in, stdout JSON out, exit-code 2 blocks.

Full reference: [geminicli.com/docs/hooks/reference](https://geminicli.com/docs/hooks/reference).

## Known limitations (empirically verified 2026-04-22/23)

- **Headless `gemini -p` may NOT invoke subagents via `@<agent>` syntax.** Our test harness confirmed: a headless prompt containing `@test-agent` caused the CLI to read the agent file via fs tools and look for a way to invoke, rather than auto-spawning. `@<agent>` works reliably only in interactive mode.
- **`paths:` YAML frontmatter is completely ignored.** Directory-hierarchy `GEMINI.md` is the only scoping mechanism. `@file.md` imports from root `GEMINI.md` are a compression option.
- **Rate limits on the free tier are aggressive** — tests that make many prompt submissions may hit quota before completing. Batch / deduplicate where possible.
- **Subagent recursion is prohibited.** A subagent cannot `@<another-agent>` — compose via parent session.

## Further reading

- CC peer guide: `.claude/guides/claude-code/`
- Codex peer guide: `.claude/guides/codex/`
- Gemini-architect spec: `.claude/agents/gemini-architect.md`
- Official docs: [geminicli.com/docs](https://geminicli.com/docs) + [google-gemini.github.io/gemini-cli/docs](https://google-gemini.github.io/gemini-cli/docs)
- loom gemini-templates source: `.claude/gemini-templates/`
