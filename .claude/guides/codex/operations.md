# Codex operations and compatibility

Evidence date: 2026-09-28. Local help was checked on 0.154.0; current official documentation and the latest listed release (0.157.1) can describe newer behavior. No automatic upgrade is implied.

A later version-only check in the same audit returned `codex-cli 0.158.0`.
The fetched official changelog still ended at 0.157.1. Earlier help and parser
checks remain 0.154.0 evidence; no 0.158.0 runtime behavior is certified here.

## Headless automation

```bash
codex exec --json --output-last-message result.txt 'Describe the approved task result.'
codex exec --output-schema response.schema.json 'Produce the requested response.'
codex exec resume SESSION_UUID 'Continue the existing task.'
codex exec fork SESSION_UUID 'Explore this alternative in a separate session.'
```

JSONL is an event stream. A process exit, completed event or nonempty output file alone does not prove the requested result was delivered. Parse the final output, validate the schema when used, and verify the task's acceptance criteria. Keep outputs outside tracked source unless they are intended deliverables.

Installed `exec` help also exposes `--ephemeral`, `--ignore-user-config` and `--ignore-rules`. These affect persistence and loaded policy/configuration; they are not routine fixes for failures. Authentication still uses `CODEX_HOME` when user configuration is ignored. Omitted prompts or `-` read stdin; on this version, piped stdin accompanying an explicit prompt is appended as a stdin block. Preserve newlines and use shell-safe argument handling. [Noninteractive command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli)

## Context size and compaction

`model_context_window` declares the active model's available token window;
`model_auto_compact_token_limit` sets when history compaction starts. Unset values
use model defaults. Neither setting increases the model/provider's actual supported
limit. For a model/provider that supports at least 800,000 tokens, an explicit
800,000-token window with a suggested 700,000-token compaction threshold is:

```bash
codex -c model_context_window=800000 -c model_auto_compact_token_limit=700000
```

For persistence, set the same keys at the top level of the active user config or
selected profile file. Start a new invocation and inspect effective configuration;
do not assume an existing session reloads the values. The default compaction scope
is `total`; `body_after_prefix` counts growth after the carried compaction prefix
instead. This guide does not change either user configuration or repository defaults.
[Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)

## Sessions, daemon and remote access

`resume` continues saved state; `fork` creates a new session from saved context. Archive/unarchive changes session visibility, while delete permanently removes a saved session. Confirm exact session identity before a destructive operation.

`codex agents` browses the shared local app-server daemon. `codex queue` addresses independent sessions; use the [coordination skill](../../skills/codex-coordination/SKILL.md) for acknowledgement and result delivery. CLI and running daemon versions can differ after an update. Diagnose both before attributing a missing feature to the CLI binary alone.

The app-server supports client integration, and `--remote` can select Unix/WebSocket endpoints. Remote control has its own setup and authorization lifecycle; this guide does not enable it. Consult `codex app-server --help`, its daemon subcommands, and `codex remote-control --help` on the installed version. Do not expose an endpoint or persist credentials as an incidental troubleshooting action. [App-server](https://learn.chatgpt.com/docs/app-server)

## Worktree isolation

Installed 0.154.0 exposes `--worktree`, while its effective `worktrees` feature was experimental and disabled during the audit. Later releases changed worktree defaults. Flag presence alone does not prove an isolated checkout was created. [Release history](https://learn.chatgpt.com/docs/changelog)

This repository's independent rule still applies: the orchestrator creates a sibling worktree before parallel implementation, pins its absolute path, and each worker verifies resolved git root equals physical cwd. Product-managed worktrees are not an exception to that placement rule. Check the actual resulting location before considering a different workflow; never substitute a shared checkout for isolation.

## Other daily controls

When explicitly requested, `/goal <objective>` starts a persistent objective;
`/goal` inspects it, and `edit`, `pause`, `resume`, and `clear` manage it.
State completion evidence and stopping conditions before starting autonomous work.
`/side` (alias `/btw`) opens an ephemeral side conversation. `/clear` starts a
fresh chat; clearing only the terminal view does not reset conversation context.
`/keymap` inspects and persists shortcut bindings. `/import` can migrate supported
Claude Code or Cursor material into local files/configuration; review its selected
scope before applying it. These are current documented controls, not a claim that
each was exercised on the installed release.
[Command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli)

Codex executable-command policy files (`.rules`) differ from this repository's
Markdown guidance. Trusted active configuration layers load those command policies;
test both matching and nonmatching commands before changing one. Current docs
describe preview `codex execpolicy check`; verify availability with installed help
before using it. Do not translate Markdown rules into broad allowlist grants.
[Command policies](https://learn.chatgpt.com/docs/agent-configuration/rules)

## Versioned feature inventory

| Surface | Evidence and required check |
| --- | --- |
| Queue/agent browser | Present in 0.154.0 help; queue receipt establishes acceptance only |
| Named agents | Current official agent TOML contract; validate discovery and returned output in the target runtime |
| Hooks | Current coverage/trust/output documentation; require allow/deny controls for actual enforcement claims |
| Skills | Current `.agents/skills` documentation; keep working host compatibility locations until discovery is tested |
| Goals/plugins | Exposed product workflows; availability/configuration and task authorization still apply |
| Doctor/update | Present in local help; diagnose before changing installation |
| Worktrees | Local feature was experimental/disabled; later release defaults differ |
| 0.155–0.157 UI changes | Consult release notes for voice/task controls, daemon changes, usage/UI, imports and fork behavior; do not assume the audited 0.154.0 has them |
| 0.157.1 | Latest listed release on audit date; no patch-specific feature highlight was supplied |

Use `codex --version`, `codex features list`, the relevant subcommand help, current official references, and a scoped behavioral probe together. Record what was tested and what remains documentation-only. Avoid fixed model recommendations: model availability and account configuration change independently of this guide.
