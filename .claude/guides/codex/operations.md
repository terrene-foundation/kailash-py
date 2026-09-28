# Codex operations and compatibility

Evidence date: 2026-09-28. Local help was checked on 0.154.0; current official documentation and the latest listed release (0.157.1) can describe newer behavior. No automatic upgrade is implied.

## Headless automation

```bash
codex exec --json --output-last-message result.txt 'Describe the approved task result.'
codex exec --output-schema response.schema.json 'Produce the requested response.'
codex exec resume SESSION_UUID 'Continue the existing task.'
codex exec fork SESSION_UUID 'Explore this alternative in a separate session.'
```

JSONL is an event stream. A process exit, completed event or nonempty output file alone does not prove the requested result was delivered. Parse the final output, validate the schema when used, and verify the task's acceptance criteria. Keep outputs outside tracked source unless they are intended deliverables.

Installed `exec` help also exposes `--ephemeral`, `--ignore-user-config` and `--ignore-rules`. These affect persistence and loaded policy/configuration; they are not routine fixes for failures. Authentication still uses `CODEX_HOME` when user configuration is ignored. Omitted prompts or `-` read stdin; on this version, piped stdin accompanying an explicit prompt is appended as a stdin block. Preserve newlines and use shell-safe argument handling. [Noninteractive command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli)

## Sessions, daemon and remote access

`resume` continues saved state; `fork` creates a new session from saved context. Archive/unarchive changes session visibility, while delete permanently removes a saved session. Confirm exact session identity before a destructive operation.

`codex agents` browses the shared local app-server daemon. `codex queue` addresses independent sessions; use the [coordination skill](../../skills/codex-coordination/SKILL.md) for acknowledgement and result delivery. CLI and running daemon versions can differ after an update. Diagnose both before attributing a missing feature to the CLI binary alone.

The app-server supports client integration, and `--remote` can select Unix/WebSocket endpoints. Remote control has its own setup and authorization lifecycle; this guide does not enable it. Consult `codex app-server --help`, its daemon subcommands, and `codex remote-control --help` on the installed version. Do not expose an endpoint or persist credentials as an incidental troubleshooting action. [App-server](https://learn.chatgpt.com/docs/app-server)

## Worktree isolation

Installed 0.154.0 exposes `--worktree`, while its effective `worktrees` feature was experimental and disabled during the audit. Later releases changed worktree defaults. Flag presence alone does not prove an isolated checkout was created. [Release history](https://learn.chatgpt.com/docs/changelog)

This repository's independent rule still applies: the orchestrator creates a sibling worktree before parallel implementation, pins its absolute path, and each worker verifies resolved git root equals physical cwd. Product-managed worktrees are not an exception to that placement rule. Check the actual resulting location before considering a different workflow; never substitute a shared checkout for isolation.

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
| 0.155–0.157 UI changes | Consult release notes for voice/task controls, daemon changes, usage/UI, imports and fork behavior; do not assume installed 0.154.0 has them |
| 0.157.1 | Latest listed release on audit date; no patch-specific feature highlight was supplied |

Use `codex --version`, `codex features list`, the relevant subcommand help, current official references, and a scoped behavioral probe together. Record what was tested and what remains documentation-only. Avoid fixed model recommendations: model availability and account configuration change independently of this guide.
