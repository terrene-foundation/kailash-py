---
name: hook-authoring
description: "Authoring or auditing hooks (CC/Codex/Gemini). hooks.json registration, COC_RUNTIME, instructAndWait emit, Codex trust, event contracts + MCP-guard scope, timeout fallback."
tools:
  - Read
  - Glob
  - Grep
---

# Hook Authoring

Reference for authoring and auditing event hooks across CC, Codex, and Gemini. Hooks are L3 (Guardrails) artifacts in the COC 5-layer architecture per `rules/cc-artifacts.md` — alongside rules, but distinguished by deterministic runtime invocation on tool / session lifecycle events. Sibling to skill-authoring (F1) and command-authoring (F2).

## When To Use

Authoring a new hook script under `.claude/hooks/`. Auditing an existing hook for timeout discipline, output shape, severity grounding, predicate bijection with the MCP guard, or path resolution across CLIs. Deciding whether enforcement belongs in a hook (runtime tripwire, deterministic), an agent (judgment, tools), or a rule (always-on prose guardrail).

## Quick Reference

| CLI    | Registration                                               | Event surface                                                              | Path env                               |
| ------ | ---------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------- |
| CC     | `.claude/settings.json` `hooks` block                      | `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`    | `$CLAUDE_PROJECT_DIR` exported         |
| Codex | `hooks.json` or inline `[hooks]` beside active config layers | Shell (`Bash`), `apply_patch`, MCP and most local functions; hosted tools excluded | Session cwd; resolve launcher from Git root |
| Gemini | `.gemini/settings.json` `hooks` object                     | `BeforeTool` / `AfterTool` / `BeforeAgent` / `SessionStart` / `SessionEnd` | `$GEMINI_PROJECT_DIR` exported         |

| Constraint                | Value                                                                                                                 |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Script location           | `.claude/hooks/<name>.js` — Anthropic-documented path, shared across all three CLIs                                   |
| Module system             | CommonJS (`require`), matching repo convention                                                                        |
| Timeout fallback          | Mandatory per `rules/cc-artifacts.md` Rule 7 — Codex PreToolUse unknown validation denies; other runtime/event fallbacks retain their contract              |
| Stdin / stdout            | Read JSON payload from stdin; emit JSON on stdout                                                                     |
| Halting exit (PreToolUse) | `process.exit(2)` — but ONLY via `lib/instruct-and-wait.js::emit()` shape per `rules/hook-output-discipline.md`       |
| Halting return (post)     | `continue: false` — ONLY via the same emit() shape                                                                    |
| Block severity            | Requires structural / behavioral / AST signal — lexical regex match is BLOCKED per `hook-output-discipline.md` MUST-2 |

## Single Script, Three Runtimes

The authoritative copy of every hook lives at `.claude/hooks/<name>.js`. All three CLIs reference the same file by path; what differs is the registration manifest:

- CC reads `.claude/settings.json` `hooks` → command list. Working directory at hook launch is the project root; CC exports `CLAUDE_PROJECT_DIR`.
- Codex reads trusted hook definitions from active config layers. This repository launches the adapter with `node "$(git rev-parse --show-toplevel)/.claude/hooks/lib/codex-hook-runtime.js" ./.claude/hooks/<name>.js`. The adapter pins `COC_RUNTIME=codex`, `CLAUDE_PROJECT_DIR`, and child cwd to its installed repository root; stdin retains the original session cwd. Source: `.claude/hooks/lib/codex-hook-runtime.js:43-124`.
- Gemini reads `.gemini/settings.json` `hooks` (the `hooks` object) and renames events to its own taxonomy (`BeforeTool`, `AfterTool`). Gemini exports `GEMINI_PROJECT_DIR`.

The single-source contract means every hook MUST work under all three runtimes without per-CLI source forks. The shared library `lib/runtime.js::parseHook()` validates the `COC_RUNTIME` env var (closed enum: `cc` / `codex` / `gemini`) and returns a canonical payload shape regardless of source.

## The COC_RUNTIME Contract

Every hook invocation MUST set `COC_RUNTIME` to `cc`, `codex`, or `gemini` before the script starts. Codex native registrations use `codex-hook-runtime.js`; the MCP companion stamps the runtime when replaying policies. Manual invocations must set it explicitly. Preserve this adapter to centralize the runtime and project-root contract; do not infer a Codex `execvp` limitation from older notes. Current official command examples use shell substitution. Source: [Hooks](https://learn.chatgpt.com/docs/hooks).

```javascript
// DO — use parseHook for the canonical shape; throws on missing COC_RUNTIME
const { parseHook } = require("./lib/runtime.js");
const payload = parseHook(rawStdin);
// payload = { runtime, event, toolName, toolInput, prompt, sessionId, cwd, projectDir }

// DO NOT — hand-roll stdin parsing; misses runtime validation
const data = JSON.parse(rawStdin);
const event = data.hook_event_name; // CLI taxonomy not normalized
```

`parseHook` normalizes Codex / Gemini snake_case event names back to PascalCase, so downstream branching can compare against canonical event identifiers regardless of the source CLI's event taxonomy.

## Path Resolution Across CLIs

Codex starts command hooks in the **session cwd**, which may be a nested folder. Resolve the adapter launcher from `git rev-parse --show-toplevel`, quote the resulting path, and let the adapter derive its repository root from its installed location. Never treat `payload.cwd` as necessarily the root. Preserve it for checks on the actual requested command. Source: `.claude/hooks/lib/codex-hook-runtime.js:43-124`; [Hooks](https://learn.chatgpt.com/docs/hooks).

The adapter resolves both the requested hook and known registration paths with `realpathSync`, then uses that canonical identity for execution, deadlines, and validator exit handling. Symlink aliases retain the same role, including a registration pointing to an external physical file. Generic hooks remain supported when unrelated known hooks are absent. This identity check does not enforce containment or prevent a check-to-use path swap. Source: `.claude/hooks/lib/codex-hook-runtime.js:53-146`.

## Codex Coverage, Trust, And Event Contracts

Current official documentation includes shell/unified exec (`Bash`), `apply_patch` (`Edit`/`Write` aliases), MCP, and most local function tools. Hosted tools and specialized paths may bypass hooks. A `write_stdin` continuation does not receive a fresh PreToolUse check. Capability is not registration: this repo's `.codex/hooks.json:1-40` registers Bash validation, SessionStart, and post-edit hygiene for `apply_patch`/Edit/Write. An MCP companion can evaluate calls routed through it; installing it does not intercept every native tool.

Non-managed hooks require review and trust of their exact definition through `/hooks`. Changed definitions are skipped until reviewed; project hooks also require project trust. Never auto-approve or bypass this trust during setup. Matching sources accumulate and command hooks can run concurrently. Managed hooks can be enforced by administrative requirements. These lifecycle checks are guardrails, not a complete security boundary.

Use event-specific output: PreToolUse denies with `permissionDecision: "deny"` or exit 2 and stderr; it does not accept `continue` or `stopReason`. PermissionRequest has its own `decision.behavior` schema. PostToolUse feedback cannot undo an effect. Stop blocking feedback requests continuation; SessionEnd is the actual session-end event. See [Hooks](https://learn.chatgpt.com/docs/hooks) for async/MCP handlers, compaction/subagent events, and schemas.

Native hygiene adapts patch targets and checks existing source files after writes; shell-generated writes are not scanned. Limits are 1 MiB per patch/file and 100 targets, with explicit skipped-scan notices. Canonical containment, no-follow file open, and descriptor identity checks reject static out-of-root targets and detected replacements; this is not complete protection against concurrent hostile ancestor mutation. Source: `.claude/hooks/integration-hygiene.js:73-159`.

The local regression suite exercises adapters and output contracts, not a live model session or trusted-hook execution: `node --test .claude/test-harness/tests/codex-hook-compatibility.test.cjs`. Re-test installed CLI dispatch separately before retiring the MCP compatibility path. Policy-generation parity remains a separate distribution check; it proves neither hook trust nor native interception.

## Predicate Function Shapes (Validator-13 Bijection)

A predicate function is any function whose body produces a reject decision. The MCP guard's AST extraction recognizes three structural shapes:

- **Shape A** — `process.exit(N)` with `N >= 2` in the function body.
- **Shape B** — returns `{ exitCode: N, ... }` with `N >= 2`; at least one caller routes that return into a `process.exit(<field>)` call in the same file. The data-flow check is per-predicate (tightened in v6.1).
- **Shape C** — returns `{ isError: true, content: [...] }` — the MCP response form used by the guard server.

Fixtures live at `.claude/fixtures/validator-13/`. Adding a new predicate that the extractor cannot match (a fourth shape, or a borrowed pattern from elsewhere) is BLOCKED until the extractor and fixture set are updated together. Predicate shape is part of the public contract between the hook layer and the MCP guard.

## Output Discipline — instructAndWait

Every halting branch (PostToolUse `continue: false`; PreToolUse `process.exit(2)`) MUST go through `lib/instruct-and-wait.js::emit()` with all six fields populated: `severity`, `what_happened`, `why`, `agent_must_report` (≥1 entry), `agent_must_wait`, `user_summary`. Raw `process.exit(2)` and bare `{continue: false}` writes are BLOCKED per `rules/hook-output-discipline.md` MUST-1.

```javascript
// DO — canonical shape, agent gets actionable report
const { emit } = require("./lib/instruct-and-wait.js");
emit({
  hookEvent: "PostToolUse",
  severity: "halt-and-report",
  what_happened: "Bash command flagged — off-repo write attempt",
  why: "repo-scope-discipline/MUST-NOT-1",
  agent_must_report: [
    "Quote the exact command that triggered detection",
    "State which rule was violated and its origin date",
    "Propose remediation in this turn — no follow-up issue",
  ],
  agent_must_wait: "Do not retry until the user instructs.",
  user_summary: "repo-scope-discipline/MUST-NOT-1 — off-repo gh write",
});

// DO NOT — bare exit, agent sees only "Execution stopped by hook"
process.stdout.write(JSON.stringify({ continue: false }) + "\n");
process.exit(2);
```

The CC UI shows the user "Execution stopped by PostToolUse hook" — useless without the `user_summary` stderr line. The shape converts a silent flow-stop into a structured handoff so user + agent can both act.

## Severity Grounding — No Block From Regex

A finding with `severity: "block"` MUST be grounded in a structural / behavioral / AST / process-state signal that surface rewrites cannot evade. Lexical regex matches against shell command strings, file contents, or agent prose MUST emit `severity: "halt-and-report"` or `severity: "advisory"`, never `block`. Block severity is reserved for facts the agent cannot rationalize away — env vars, exit codes, file existence, AST shape.

```javascript
// DO — block grounded in env var + path prefix (structural)
if (
  process.env.CLAUDE_WORKTREE_PATH &&
  !filePath.startsWith(process.env.CLAUDE_WORKTREE_PATH)
) {
  return { rule_id: "worktree-isolation/MUST-1", severity: "block", evidence };
}

// DO — lexical regex → halt-and-report, never block
const m = command.match(/\bgh\b[^|;]*--repo\s+([^\s]+)/);
if (m && !m[1].includes(path.basename(cwd))) {
  return {
    rule_id: "repo-scope/MUST-NOT-1",
    severity: "halt-and-report",
    evidence,
  };
}
```

Command-string detectors MUST skip captured groups referencing unexpanded shell variables (`$VAR`, `${VAR}`, `$(...)`, backticks) — the pre-expansion form cannot be evaluated at hook invocation time. Per `rules/hook-output-discipline.md` MUST-3, the skip is a structural `null` return; no downgrade-to-advisory, no in-hook shell expansion (that path is a confused-deputy security hole).

## Timeout Fallback

Every hook must finish before the runtime kill window. Codex PreToolUse validation failures, malformed input, and deadlines deny with canonical feedback and exit 2; unknown validation must not authorize a command. The Bash validator keeps its 3s input deadline. Its adapter enforces child deadlines of 4s for validation, 10s for hygiene, and 20s for SessionStart. Every native registration has a separate 30s outer budget that includes login-shell and adapter startup. Bounded children are killed even if synchronous work prevents their own JavaScript timer or signal handler from running. Ordinary lifecycle/advisory exit codes remain unchanged. This margin is not a guarantee under arbitrary scheduling delays. CC/Gemini retain the existing non-blocking fallback shown below. Source: `.claude/hooks/validate-bash-command.js:118-196`; `.claude/hooks/lib/codex-hook-runtime.js:79-146`; `.codex/hooks.json:1-40`.

```javascript
const TIMEOUT_MS = 5000;
const _timeout = setTimeout(() => {
  console.log(JSON.stringify({ continue: true }));
  process.exit(1);
}, TIMEOUT_MS);
```

The CC/Gemini JavaScript fallback examples retain their existing 5s per-tool / 10s SessionStart limits. They are not Codex outer registration limits. Codex registration `timeout` values are seconds; child deadlines and internal JavaScript timers are milliseconds. Do not equate these nested budgets or infer that a JavaScript timer interrupts synchronous work. Native login-shell startup was measured at nearly 5s before Node in the 2026-09-28 diagnosis; increasing only the outer timeout would still leave lifecycle children unbounded. Source: `.claude/hooks/lib/codex-hook-runtime.js:79-128`.

The `setTimeout`-fallback path is the ONE legitimate raw-exit branch. It must emit the runtime/event-specific outcome first (denial for unknown Codex PreToolUse validation); raw `process.exit(N)` from any other branch is BLOCKED per `rules/hook-output-discipline.md` MUST-NOT-1.

## Variant Overlays

CLI-specific or language-specific hook bodies live at `.claude/variants/<axis>/hooks/<name>.js` and overlay only the diverging slot. Axes mirror skills + commands: `variants/codex/`, `variants/gemini/`, `variants/py/`, `variants/rs/`, `variants/base/`, ternary forms like `variants/py-codex/`.

Hook overlays are rare in practice — most behavior is keyed off `payload.runtime` (from `COC_RUNTIME`) rather than full-file forking. When an overlay is genuinely needed (a Codex-only enforcement path that has no CC analog), the overlay file replaces the body wholesale; slot markers are not used in `.js` source.

## Audit Fixtures

Every detector function in `.claude/hooks/lib/violation-patterns.js` MUST ship at least one committed fixture per scope-restriction predicate it relies on, under `.claude/audit-fixtures/violation-patterns/<detector>/`. Required coverage:

- Clean input that MUST NOT flag
- Flagging input that MUST flag
- For command-string detectors, at least one shell-variable input that MUST NOT flag (per `hook-output-discipline.md` MUST-3)

Per `rules/cc-artifacts.md` Rule 9. Fixtures are the mechanical regression lock for scope-restriction predicates; without them, future modifications silently weaken the predicate and the detector starts producing false positives at scale.

## Wrapper Status — Native Hook Registration Is Canonical

Historical per-phase shell-wrapper decisions do not describe current native hook coverage. The native adapter remains required for this repository's runtime stamp and root resolution. Keep the MCP companion until a separately reviewed migration verifies equivalent policy reach, trust setup, and output behavior in the target CLI.

New hooks MUST NOT add `.claude/wrappers/*.sh.template` files. If a future workstream requires external CLI invocation or structured-output enforcement at the hook layer, revival is documented in the journal entry — propose at `/codify`, do not assume the path is live.

## Workspace-Walking Hooks Filter Meta-Dirs

Hooks that enumerate `workspaces/<name>/` directories (e.g. `detectActiveWorkspace`, `findAllSessionNotes`) MUST filter both the literal `instructions` directory AND any directory whose name starts with an underscore. Per `rules/cc-artifacts.md` Rule 8:

```javascript
const projects = entries.filter(
  (e) =>
    e.isDirectory() && e.name !== "instructions" && !e.name.startsWith("_"),
);
```

Leading-underscore is the convention for workspace meta-dirs (`_archive`, `_template`, `_draft`). Archival operations (`git mv workspaces/X (loom-internal reference)`) bump `_archive/`'s mtime; without the filter, the hook surfaces `_archive` as the active workspace and SessionEnd routes journal stubs into (loom-internal reference) — invisible drift the next session must untangle.

## Common Mistakes

### 1. Raw `process.exit(2)` Without instructAndWait

Highest-frequency authoring bug. A new detector ships a halting branch with `process.exit(2)` and no payload; agent gets "Execution stopped by hook" with zero context, files a follow-up issue (violating `autonomous-execution.md` MUST-4), and the rule the hook enforces gets re-asked next session. Fix: route every halting branch through `lib/instruct-and-wait.js::emit()`.

### 2. `severity: "block"` From Regex Evidence

Lexical regex against `payload.tool_input.command` cannot see shell expansion; matching `"$REPO"` as a literal string and reporting block-severity false-positives blocks in-scope work. Fix: lexical matches emit `halt-and-report`; block requires structural evidence (env var, exit code, file existence, AST shape).

### 3. Capability Mistaken For Policy Coverage

Codex supporting `apply_patch` hooks does not wire this repository's Bash validators to edit tools. Match the intended event/tool, validate its distinct input shape, and prove both allowed and denied behavior through the target CLI. Do not describe an installed MCP server as a universal interceptor.

### 4. Missing Timeout Fallback

A JavaScript fallback alone cannot interrupt synchronous work. Keep the runtime-specific fallback and enforce registered Codex child deadlines from the adapter, leaving a separate native startup allowance. Source: `.claude/hooks/lib/codex-hook-runtime.js:79-128`.

### 5. `$CODEX_PROJECT_DIR` Referenced In Hook Registration

A relative adapter launcher fails when the session starts below the repository root. Use the quoted Git-root launcher above, and test a nested working directory containing spaces. Source: `.codex/hooks.json:1-40`; `.claude/hooks/lib/codex-hook-runtime.js:43-124`.

### 6. Gemini Event Names As CC Aliases

Author writes `.gemini/settings.json` with `PreToolUse` / `PostToolUse` keys; Gemini silently ignores them and the hook never fires. Fix: translate to `BeforeTool` / `AfterTool`. CC's `Stop` maps to Gemini's `SessionEnd`; CC's `UserPromptSubmit` has no exact Gemini equivalent (closest is `BeforeModel`).

### 7. Semantic Analysis In Hooks

Hook attempts to reason about the meaning of agent prose, file contents, or commit messages. Policy hooks require bounded execution; semantic analysis is slow and non-deterministic, producing spurious failures that block the session. Fix: hooks check structure (path prefix, env var, exit code, AST shape); agents check semantics at gate review.

### 8. Lexical Hook Detector Without Probe Counterpart

Per `rules/probe-driven-verification.md` MUST-4, every lexical hook detector MUST have a probe-driven gate-review counterpart at `/codify` validation. Hook-only verification of a semantic property is BLOCKED — hooks alone produce false positives at scale; probes alone miss the cumulative-violation count for trust-posture downgrade math. Both layers required.

## Audit Checklist

When auditing an existing hook:

- [ ] File location is `.claude/hooks/<name>.js` (NOT `scripts/hooks/` — obsolete pre-v2.8.31)
- [ ] Timeout fallback installed: Codex PreToolUse denies unknown validation; other runtimes preserve their event contract
- [ ] CC timeout 5s (per-tool) or 10s (SessionStart); never higher than 10s
- [ ] Every halting branch routes through `lib/instruct-and-wait.js::emit()` with all six fields
- [ ] No `severity: "block"` returns whose `evidence` is a regex span
- [ ] Command-string detectors skip shell-variable captures (`$VAR`, `${VAR}`, `$(...)`)
- [ ] `parseHook()` from `lib/runtime.js` used for stdin payload (validates COC_RUNTIME)
- [ ] Codex launcher works from a nested cwd; adapter root and session cwd stay distinct
- [ ] Workspace-walking loops filter `instructions` AND leading-underscore meta-dirs
- [ ] If predicate adds a reject branch, equivalent entry exists in `codex-mcp-guard/policies.json`
- [ ] Predicate shape matches A / B / C per validator-13; new shapes update fixtures + extractor together
- [ ] Audit fixtures committed at `.claude/audit-fixtures/violation-patterns/<detector>/` (clean + flag + shell-var)
- [ ] No `.claude/wrappers/<name>.sh.template` added (wrappers deferred per journal/0006)
- [ ] Lexical detectors paired with a probe-driven gate-review counterpart per `probe-driven-verification.md` MUST-4

## Related

- `rules/cc-artifacts.md` Rule 7 — timeout fallback mandate
- `rules/cc-artifacts.md` Rule 8 — workspace meta-dir filter pattern
- `rules/cc-artifacts.md` Rule 9 — audit fixtures committed alongside detectors
- `rules/cc-artifacts.md` Rule 10 — positive-allowlist sweep pattern
- `rules/hook-output-discipline.md` — instructAndWait emit shape, no raw exit, severity grounding, shell-variable skip
- `rules/probe-driven-verification.md` MUST-4 — lexical hook detectors paired with probe-driven gate review
- `rules/trust-posture.md` — posture state read from main checkout; hooks are the only legitimate writers
- `agents/codex-architect.md` § Hooks Coverage — native reach, trust, and MCP companion limitations
- `agents/gemini-architect.md` § Hook Event Name Translation — CC ↔ Gemini event taxonomy
- `agents/cc-architect.md` — CC-side hook authoring + audit responsibilities
- `codex-mcp-guard/README.md` — POLICIES table population, validator-13, predicate shapes
- `hooks/lib/runtime.js` — `COC_RUNTIME` closed enum + `parseHook` contract
- `hooks/lib/instruct-and-wait.js` — canonical halt-shape emit
- `skill-authoring` (F1) — sibling meta-skill, same shape conventions
- `command-authoring` (F2) — sibling meta-skill, same shape conventions
