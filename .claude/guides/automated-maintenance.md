# Automated Maintenance System

The Kailash Python SDK uses Claude Code Action to automatically fix issues, run the full COC lifecycle, and prepare releases — triggered entirely from GitHub.

## Architecture

```
GitHub Issue/Comment
        │
        ▼
  claude-code-action (GitHub Actions, self-hosted runner)
        │
        ├─ Loads: CLAUDE.md, .claude/rules/, .claude/agents/, .claude/skills/
        ├─ Executes: hooks from .claude/settings.json
        ├─ Runs: full COC lifecycle (analyze → implement → validate → codify)
        │
        ▼
  Creates PR (branch: claude/fix-issue-N)
        │
        ├─ auto-fix label → auto-merge when CI passes
        ├─ needs-review label → admin approval required
        └─ release label → admin approval ALWAYS required
```

## Trigger Methods

### Bug Fixes

```bash
# Assign to Claude
gh issue edit <N> --add-assignee claude

# Label for auto-fix (auto-merges if CI passes)
gh issue edit <N> --add-label auto-fix

# Comment on any issue or PR
# "@claude please fix this"
```

### Release

```bash
# Create a release issue
gh issue create --title "Release v1.1.0" --label release \
  --body "Bump to v1.1.0. Includes fixes #41 #42 #43."

# Or comment on any issue
# "@claude /release v1.1.0"
```

## Autonomy Tiers

| Issue Label | What Claude Does | Auto-merge? | Admin Required? |
|-------------|-----------------|-------------|-----------------|
| `auto-fix` | Full COC lifecycle, creates PR | No (open-source, admin reviews all) | Yes |
| `needs-review` | Full COC lifecycle, creates PR | No | Yes |
| `release` | Runs /release pipeline, creates PR | No | Always |
| _(no label)_ | Assign to `claude` or @mention | Claude decides label | Depends |

## Full COC Lifecycle

### For Bug Fixes

1. **Analyze** — Read issue, identify affected package(s), consult specialist agents
2. **Reproduce** — Write regression test that fails
3. **Fix** — Implement following all rules (zero-tolerance, no-stubs, framework-first)
4. **Validate** — `black`, `ruff`, `pytest`
5. **Codify** — Update agents/skills/rules if the fix revealed documentation gaps
6. **COC Sync** — Cascade updated COC artifacts to `~/repos/kailash/kailash-coc-claude-py`
7. **Commit & PR** — Create branch, commit, push, create PR

### For Releases

1. Pre-release checks (pytest, black, ruff, version consistency)
2. Version bump (pyproject.toml + `__init__.py` for ALL affected packages)
3. Create release PR (ALWAYS requires admin approval)
4. After admin merges: CI tags + publishes to PyPI

## COC Sync Cascade

After any fix that updates COC artifacts:

```
BUILD repo (kailash-py)
    │
    ├─ coc-sync agent transforms BUILD artifacts
    │
    └─► USE repo (~/repos/kailash/kailash-coc-claude-py)
         └─ Updated agents, skills, rules, commands
```

**Important**: kailash-py syncs to kailash-coc-claude-py ONLY.

## Required Secrets

| Secret | Purpose | Set? |
|--------|---------|------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code Max authentication | Yes |
| `DISCORD_WEBHOOK_URL` | Notifications on completion/failure | Yes |

## Required Repo Settings

- Allow auto-merge: `false` (kailash-py is open-source — all PRs need admin approval)
- Delete branch on merge: `true` (enabled)
- Allow squash merge: `true`

**Note**: Unlike kailash-rs (private, auto-merge enabled), kailash-py requires admin approval for ALL PRs because it's an open-source repo. The `auto-fix` label signals "high confidence, ready for review" but does NOT auto-merge.

## Hooks That Run in CI

| Hook | Fires? | Purpose |
|------|--------|---------|
| `validate-workflow.js` (PostToolUse) | Yes | BLOCKS stubs, validates patterns |
| `validate-bash-command.js` (PreToolUse) | Yes | BLOCKS dangerous commands |
| `validate-deployment.js` (PostToolUse) | Yes | BLOCKS credential leaks |
| `auto-format.js` (PostToolUse) | Yes | Auto-formats code |
| `session-start.js` (SessionStart) | Yes | Package freshness + version check |

## Testing

```bash
gh issue create --title "Test: Claude auto-fix" --label auto-fix \
  --body "Test issue. @claude confirm you can read CLAUDE.md and list the absolute directives."
gh run list --workflow=claude.yml --limit=1
```
