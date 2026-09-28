# Codex MCP Guardrail Companion

This directory contains an optional MCP policy companion. It evaluates calls explicitly routed to its registered tools and returns policy decisions; registration does not intercept native Codex calls or execute permitted operations. Source: `.claude/codex-mcp-guard/server.js:1107-1132`.

## Installation

The guard depends on `@modelcontextprotocol/sdk` (declared in `package.json`; pinned via `package-lock.json`). On a fresh USE-template install — or after a `/sync` that refreshes this directory — run:

```bash
cd .codex-mcp-guard && npm ci
```

`npm ci` (not `npm install`) is required: it installs the exact versions declared in `package-lock.json` and refuses to mutate the lockfile. This is the **reproducible** install path — every Codex consumer of every USE template gets the same SDK build that loom audited at lockfile-commit time. Running `npm install` instead would silently re-resolve the dependency tree against npm's latest matching versions, breaking the audit chain.

This installs the SDK into `.codex-mcp-guard/node_modules/` so `server.js` can lazy-load it on Codex startup. Without this step, Codex emits:

```
codex-mcp-guard: @modelcontextprotocol/sdk not installed (...).
Install via the USE template's package.json before running stdio mode.
```

…and `MCP client for 'codex-mcp-guard' failed to start: handshaking with MCP server failed: connection closed: initialize response`. The server refuses to start when its dependencies are unavailable; native tools are not thereby blocked. Install the locked dependencies with `npm ci`. Source: `.claude/codex-mcp-guard/server.js:1083-1096`.

`engines.node >= 18` per `package.json`. The package itself is `private: true` — it is never published to npm; only consumed in-place via the USE template's `.codex-mcp-guard/` directory.

## Native hooks and companion scope

Current Codex documentation supports hooks for shell/unified exec (`Bash`), `apply_patch`, MCP, and most local function tools. Hosted tools and specialized paths remain outside that coverage. Non-managed hooks require definition-specific trust through `/hooks`, and project hooks require project trust. See [official Hooks documentation](https://learn.chatgpt.com/docs/hooks) (checked 2026-09-28).

The companion exposes `apply_patch`, `unified_exec`, and `shell` policy tools. Other tools are outside its registration; even these three native tools are not automatically redirected to MCP. A successful companion result is permission feedback, not proof the underlying operation executed. Source: `.claude/codex-mcp-guard/server.js:92-98`, `.claude/codex-mcp-guard/server.js:1107-1132`.

## Parity guarantee

The `/sync` emit-time validator 13 enforces AST predicate-set equivalence between `.claude/hooks/*.js` and `server.js`'s `POLICIES` table. Every reject-condition in a hook file MUST have a matching entry here. Divergence blocks sync.

## Compatibility and migration

The historical `codex_hooks = under_development` rationale describes older clients. Current documentation calls the feature `hooks` (enabled by default); `codex_hooks` is a deprecated alias. This does not establish that a particular installation trusts or runs this repository's definitions.

Retain the companion until a reviewed migration proves policy reach, registration, hook trust, event outputs, and negative controls in the target CLI. Adapter unit tests are not live enforcement evidence. Do not remove this directory solely because a feature flag graduated.

## Behavioral differences

Native command hooks run subprocesses and use event-specific JSON or exit codes. Companion calls return MCP responses and only cover their explicit invocation path. Neither is a universal interception boundary. Do not reuse native PreToolUse `continue:false`: current Codex rejects it. Use documented denial output or exit 2 plus stderr. See [Hooks](https://learn.chatgpt.com/docs/hooks).

**`permissionDecision:"ask"` has no hard-block on the Codex lane.** CC's modern `hookSpecificOutput.permissionDecision:"ask"` pauses for interactive human confirmation; the MCP companion has no confirm channel, so the guard collapses a pure `"ask"` (exit 0, no `continue:false`) to the `surface` verdict — it returns permission feedback and surfaces the reason. For this companion's policy interpreter, use `deny` or exit 2 for hard denial; its legacy `continue:false` interpretation is not the current native PreToolUse contract. A `"deny"` co-emitted with an `"ask"` is honored as deny (the deny gate is evaluated first).

## Authoring

The `POLICIES` table is generated from the hooks/\*.js AST + the project's `settings.json` matcher map by `extract-policies.mjs --write-policies`, which emits a sibling `policies.json`. `server.js` loads `policies.json` at startup; `POLICIES_POPULATED` flips true iff at least one wrapped Codex tool has ≥1 policy entry. Do NOT edit `policies.json` by hand — it is regenerated on every `/sync` from the single source of truth in `.claude/hooks/`.

### apply_patch edit-gate lane (the `@coc-codex-edit-gate` marker) — FF-AC6-1

`apply_patch` is the Codex file-edit primitive. A CC hook registered under the edit matcher (`Edit|Write|NotebookEdit`; MultiEdit removed from CC per journal/0276, with a legacy MultiEdit→apply_patch mapping retained in `matcherToCodexTools()` for older consumer settings) fans out to the `apply_patch` policy lane **only when its source carries the `@coc-codex-edit-gate` JSDoc marker**. The marker declares the hook a STATELESS trust gate (posture / 4-eyes / signing) safe to replay against a non-enrolled Codex consumer's file-edits. It is the CONSUMER-AVAILABLE selectivity signal: it lives in the synced hook source because `sync-manifest.yaml`'s `mcp-guard` lane is NOT synced to consumers where the extractor regenerates `policies.json`. The cc-only coordination guards (`adjacency-leasecheck`, `journal-write-guard`, `integrity-guard`) deliberately OMIT the marker — they require the multi-operator roster/claim/journal-slot substrate a consumer lacks and would halt every Codex edit. Default is fail-safe-for-functionality: a new edit hook with no marker is EXCLUDED (so a forgotten coordination guard never halts Codex). Adding/auditing a marker on any of the 3 gates fires the `self-referential-codify.md` multi-agent gate. The marker contract lives at `extract-policies.mjs::CODEX_APPLY_PATCH_GATE_MARKER`.

### Policy execution model

When the MCP server receives an `apply_patch` / `unified_exec` / `shell` invocation:

1. Synthesize a CC-shaped PreToolUse JSON payload (`{ tool_name, tool_input, hook_event_name, cwd, session_id }`). The Codex tool name is translated to the CC-native name the hooks classify by (`shell`/`unified_exec` → `Bash`, `apply_patch` → `Edit`) via `CODEX_TO_CC_TOOL`, and the input is FIELDED-projected (`synthesizePolicyInputs`) to a LIST of CC shapes — one `{ file_path }` per `apply_patch` V4A target (so multi-file patches are gated per-target), `{ command }` for the Bash lane. The projection drops raw patch content (secrets fence, mirroring `synthesizeCaptureInput`).
2. For each policy entry registered for that Codex tool, spawn the underlying hook script as a Node subprocess (`node ../hooks/<source_file>`) with the payload on stdin and a 5-second timeout (`cc-artifacts.md` Rule 7).
3. Read the subprocess exit code:
   - `0` → allow this policy; continue to the next.
   - `2` → deny; translate the hook's stdout (canonical `instructAndWait` shape) into an MCP `isError: true` response and short-circuit.
   - other / timeout / spawn error → allow (fail-open) and append a `codex_mcp_guard_*` entry to `.claude/learning/violations.jsonl`.
4. If all policies allow, return `permit` feedback. The server does not execute the original tool. Source: `.claude/codex-mcp-guard/server.js:1129-1132`.

### Self-check

```bash
node .claude/codex-mcp-guard/server.js --self-check
```

Prints the per-tool policy entry counts, hook-dir resolution, timeout setting, and exits 0 if `POLICIES_POPULATED` is true (2 if false).

### Acceptance fixtures

`.claude/audit-fixtures/codex-mcp-guard/` ships the four canonical scenarios per `cc-artifacts.md` Rule 9: `clean-shell.json` (allow), `flag-shell-rm-rf.json` (deny → validate-bash-command), `flag-shell-force-push-main.json` (deny → validate-bash-command), and `timeout-shell.json` (subprocess hangs → allow + log). Run via `node .claude/codex-mcp-guard/test-server.mjs`.

## Validator 13 — predicate extractor (Phase E6)

`extract-policies.mjs` implements the v6 §4.4 three-shape predicate extraction:

| Shape | Pattern                                                                                              |
| ----- | ---------------------------------------------------------------------------------------------------- |
| A     | `process.exit(N)` with `N >= 2` literal in function body                                             |
| B     | `exitCode: N` with `N >= 2` (literal or via ternary/expr) in returned object, caller pipes to `exit` |
| C     | `return { isError: true, content: [...] }` (MCP response form)                                       |

Usage:

```bash
node .claude/codex-mcp-guard/extract-policies.mjs <hook-dir> [--json | --pretty]
```

Output is a POLICIES-shape JSON enumerating every predicate. The bijection invariant (spec v6 §4.4) is that every predicate function in the hook source appears EXACTLY ONCE in the output — missing or extra entries HARD BLOCK sync.

### Acceptance test

`test-extract-policies.mjs` verifies bijection against `workspaces/multi-cli-coc/fixtures/validator-13/expected-policies.json`. Run on every change to the extractor:

```bash
node .claude/codex-mcp-guard/test-extract-policies.mjs
```

### Real-world baseline (2026-04-22)

Run against `.claude/hooks/` (14 files), the extractor finds 5 predicates — matching the spec's "Why Shape B is load-bearing" empirical audit (v6 §4.4):

| Shape | Predicate               | Source                       | Disposition                                            |
| ----- | ----------------------- | ---------------------------- | ------------------------------------------------------ |
| A     | `main`                  | `validate-prod-deploy.js`    | Orchestrator — filtered as non-policy at emission time |
| B     | `validateBashCommand`   | `validate-bash-command.js`   | Real policy — candidate for POLICIES["shell"]          |
| B     | `validateDeployment`    | `validate-deployment.js`     | Real policy — candidate for POLICIES["shell"]          |
| B     | `checkForRawFrameworks` | `enforce-framework-first.js` | Real policy — candidate for POLICIES["apply_patch"]    |
| B     | `validateFile`          | `validate-workflow.js`       | Real policy — candidate for POLICIES["apply_patch"]    |

Orchestrator filtering + tool-binding assignment belong to the emitter (Phase E4), not the extractor itself. The extractor's contract is: enumerate all predicate functions; classification + binding is the emitter's responsibility.

### Parse strategy

The extractor uses regex + brace-depth counting rather than a proper AST parser (acorn / @babel/parser). Sufficient for the current hook shapes and the 3 fixture cases; upgrade to AST if real-world hook complexity outgrows regex (Phase F+ follow-up).

## References

- `workspaces/multi-cli-coc/02-plans/07-loom-multi-cli-spec-v6.md` §4.4 — validator 13 three-shape contract
- `workspaces/multi-cli-coc/fixtures/validator-13/` — acceptance fixtures (shape-a / shape-b / shape-c + expected-policies.json)
- `.claude/hooks/lib/runtime.js` — shared COC_RUNTIME enum + parseHook contract
