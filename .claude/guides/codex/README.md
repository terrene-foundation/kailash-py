# Working with Codex CLI in this repository

The 2026-09-28 audit began against CLI **0.154.0**. A final version-only recheck reported **0.158.0**, while the fetched [official changelog](https://learn.chatgpt.com/docs/changelog) still listed **0.157.1 (2026-09-26)** as its newest entry. This work did not run an upgrade. Keep the earlier help/parser observations tied to 0.154.0; the later version string alone does not verify 0.158.0 behavior or explain how the installation changed. Neither help nor documentation proves every feature works in this repository. Recheck versions before relying on newer defaults.

## Start and inspect

```bash
codex --version
codex --help
codex doctor --summary
codex features list
codex
```

`codex doctor --json` produces a redacted diagnostic report. `codex update` changes the installed version; run it as an intentional maintenance action, then recheck the daemon and CLI versions. `--strict-config` rejects unknown configuration keys. See [CLI documentation](https://learn.chatgpt.com/docs/codex-cli) and [developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli).

## Repository artifacts and ownership

| Artifact | Role |
| --- | --- |
| `AGENTS.md` | Repository instructions, composed from the COC rule sources |
| `.codex/config.toml` | Trusted project configuration |
| `.codex/hooks.json` | Project hook registrations; definition trust is separate from project trust |
| `bin/coc` | This project's phase dispatcher using `codex exec` and a response schema |
| `.claude/commands/` | COC phase instruction sources |
| `.codex/prompts/` | Compatibility/reference copies of phase and specialist instructions |
| `.codex/agents/*.toml` | Native named specialists when emitted; inspect the files and discovery before dispatch |
| `.claude/skills/` | Authoring sources for project skills |
| `.codex/skills/` | Existing emitted compatibility location; exposed by this session's host |
| `.codex-mcp-guard/` | Compatibility MCP adapter; registration alone does not establish interception of native tools |

The checked-in emitter is `.claude/bin/emit-cli-artifacts.mjs`. Consuming repositories do not acquire an owning parsing manifest: distribution uses its narrowed projection. Historical template-source paths such as `.claude/codex-templates/` and `.claude/sync-manifest.yaml` may be absent here. Preserve source ownership and regenerate derived artifacts; a generated path is not its own authoring source.

Codex reads `AGENTS.md` along the directory hierarchy; `AGENTS.override.md` takes precedence within a directory. YAML `paths:` does not provide a Codex glob-based rule loader. Use the rules-reference skill for this project's path-scoped rules. The native project-document budget defaults to 32 KiB; this project's configuration and dispatcher request 64 KiB. Check the effective configuration and loaded instructions instead of assuming the larger budget took effect. [AGENTS.md reference](https://learn.chatgpt.com/docs/agent-configuration/agents-md)

## Work with another session

For an independently started session, use its session UUID or exact session name:

```bash
codex agents
codex queue --thread SESSION_UUID --message 'From SENDER_UUID in REPO/WORKTREE: please own FILES for TASK. Reply to SENDER_UUID with findings or commit and checks.'
```

These are installed CLI commands. Child-agent messaging tools address agents created in the current agent tree; an independent session can be absent from that tree and still be reachable through `queue`. A queue receipt proves acceptance, not that the recipient read or completed the task. Require a reply with results and evidence. Share bounded file ownership and worktrees before parallel edits. The [coordination skill](../../skills/codex-coordination/SKILL.md) carries the delivery procedure.

## Delegate to specialists

Current Codex supports named custom agents in `.codex/agents/*.toml` and the user-global agents directory. Agent files declare `name`, `description` and `developer_instructions`, with supported execution settings such as model, reasoning effort, sandbox and MCP configuration. Do not translate a Claude Code tool list into a claimed Codex permission boundary. Check the actual child tool inventory and effective permissions. [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)

When the named specialist is discovered, request it by name with a bounded task, relevant specs/rules, absolute worktree and explicit return contract. If the current host does not expose named roles, delegate through its available child-agent tool and pass the specialist's operating specification. Reading `.codex/prompts/specialist-<name>.md` into a turn is a compatibility technique, not a parallel worker.

Headless delegation is not categorically prohibited. It is also not verified by `codex exec --help`: test discovery, dispatch and delivered results in the intended host/version before depending on it in automation. This documentation refresh did not exercise live headless delegation.

## Phase commands and reviews

The project dispatcher remains available:

```bash
bin/coc analyze 'Audit the connection-pool surface.'
bin/coc todos 'Plan the approved change.'
bin/coc implement 'Implement the approved shard.'
```

`bin/coc` invokes `codex exec` with JSONL events, a phase response schema and the instruction-budget override; it does not create an interactive slash command (`bin/coc:96-100`). Keep this project choice separate from native skills and built-in slash commands. Custom prompts are a deprecated compatibility feature; repo-local prompt files are reference content, not proof of slash-command discovery.

Review targets are alternatives:

```bash
codex review --uncommitted
codex review --base dev
codex review --commit COMMIT_SHA
```

Use the actual integration branch. On installed 0.154.0, combining `--uncommitted` with `--base` is rejected by the argument parser. [Command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli)

## Configuration and permissions

Project `.codex/config.toml` is loaded only for trusted projects. Configuration layers and command-line overrides determine the effective values. The current key/value spelling is `approval_policy = "on-request"`; it is separate from the sandbox setting. `--profile NAME` layers `$CODEX_HOME/NAME.config.toml`; legacy `[profiles.NAME]` tables are not the current profile format. Configuration profiles and named permission profiles are distinct concepts. [Basics](https://learn.chatgpt.com/docs/config-file/config-basic), [advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)

Inspect `/permissions` and `/debug-config` when available. Installed help offers `--approve-for-me` for automatic review with workspace-write sandboxing, and `-a on-request|never` for approval policy. `never` prevents approval requests; it does not grant filesystem or network access. Managed policy can constrain local choices. Do not prescribe bypass flags or elevate permissions merely to make automation pass. [Permissions](https://learn.chatgpt.com/docs/permissions)

## Hooks and compatibility adapters

Native hooks now include shell, file edits, MCP and supported local function tools; hosted tools are a distinct surface. Shell/unified-exec hook matching uses `Bash`; file edits can match `apply_patch`, `Edit` or `Write`. Keep the current coverage matrix and event-specific outputs in the [official hooks reference](https://learn.chatgpt.com/docs/hooks), rather than assuming one contract across events.

Open `/hooks` to review and trust each non-managed definition. Changed definitions require renewed trust. Project trust, enabled registration and hook-definition trust are separate checks. Lifecycle includes session end, compaction, subagent and interrupt events as well as session start, tool calls, prompts and Stop. `Stop` is not equivalent to session termination. Handlers may be commands or MCP tools, with event-specific background support.

The COC runtime wrapper stamps the compatibility environment and forwards the hook process; it does not prove that the host called it. The MCP guard declares `apply_patch`, `unified_exec` and `shell` adapters (`.codex-mcp-guard/server.js:90-114`, `WRAPPED_TOOLS`). Do not claim it intercepts every native write or arbitrary MCP call. Verify actual call paths before removing adapters or claiming enforcement parity. Hook registration, output contracts, trust, subdirectory launches and denial behavior require behavioral checks; this refresh alone is not a live-enforcement certificate.

## Skills, plugins and daily controls

Current standalone documentation recommends repository/user `.agents/skills` and optional `agents/openai.yaml` for presentation, invocation policy and dependencies. This repository retains `.codex/skills` because its skills are exposed in the current host; do not move or duplicate them without a discovery test. Explicitly invoke through `/skills` or `$skill-name` where supported. Avoid assuming every skill description is present in a bounded listing. [Build skills](https://learn.chatgpt.com/docs/build-skills)

Use `codex plugin list` and `/plugins` to inspect plugins; `plugin add`, `remove` and marketplace commands change installation state. Service connection and plugin hook trust are separate from installation. `codex mcp` manages external MCP servers consumed by Codex; app-server is the integration surface for clients controlling Codex. [Plugins](https://learn.chatgpt.com/docs/plugins), [MCP](https://learn.chatgpt.com/docs/extend/mcp)

Useful interactive controls include `/model`, `/fast`, `/usage`, `/status`, `/copy`, `/ps` and `/stop`; confirm availability in the current command picker. Persistent goals (`/goal`) are for explicitly requested long-running objectives, with a completion criterion and stop/pause behavior. Do not turn ordinary tasks into persistent goals automatically. [Commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli), [long-running work](https://learn.chatgpt.com/docs/long-running-work)

For automation, remote sessions, worktrees and version-sensitive behavior, see [Operations](operations.md).
