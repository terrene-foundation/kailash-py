# Git Workflow Rules

## Conventional Commits

```
type(scope): description
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

```
feat(auth): add OAuth2 support
fix(api): resolve rate limiting issue
```

**Why:** Non-conventional commits break automated changelog generation and make `git log --oneline` useless for release notes.

## Branch Naming

Format: `type/description` (e.g., `feat/add-auth`, `fix/api-timeout`)

**Why:** Inconsistent branch names prevent CI pattern-matching rules and make `git branch --list` unreadable across contributors.

## Branch Protection

All protected repos require PRs to main. Direct push is rejected by GitHub.

**Why:** Direct pushes bypass CI checks and code review, allowing broken or unreviewed code to reach the release branch.

| Repository                                    | Branch | Protection          |
| --------------------------------------------- | ------ | ------------------- |
| `terrene-foundation/kailash-py`               | `main` | Full (admin bypass) |
| `terrene-foundation/kailash-coc-claude-py`    | `main` | Full (admin bypass) |
| `terrene-foundation/kailash-coc-claude-rs`    | `main` | Full (admin bypass) |
| `esperie/kailash-rs`                          | `main` | Full (admin bypass) |
| `terrene-foundation/kailash-prism`            | `main` | Full (admin bypass) |
| `terrene-foundation/kailash-coc-claude-prism` | `main` | Full (admin bypass) |

**Owner workflow**: Branch → commit → push → PR → `gh pr merge <N> --admin --merge --delete-branch`

**Contributor workflow**: Fork → branch → PR → 1 approving review → CI passes → merge

## PR Description

CC system prompt provides the template. Additionally, always include a `## Related issues` section (e.g., `Fixes #123`).

**Why:** Without issue links, PRs become disconnected from their motivation, breaking traceability and preventing automatic issue closure on merge.

## Rules

- Atomic commits: one logical change per commit, tests + implementation together
- No direct push to main, no force push to main
- No secrets in commits (API keys, passwords, tokens, .env files)
- No large binaries (>10MB single file)
- Commit bodies MUST answer **why**, not **what** (the diff shows what)

**Why:** Mixed commits are impossible to revert cleanly, leaked secrets require immediate key rotation across all environments, and large binaries permanently bloat the repo since git never forgets them. Commit bodies that explain "why" are the cheapest form of institutional documentation — co-located with the code, versioned, searchable via `git log --grep`, and never stale (they describe a point in time). See 0052-DISCOVERY §2.10.

```
# DO — explains why
feat(dataflow): add WARN log on bulk partial failure

BulkCreate silently swallowed per-row exceptions via
`except Exception: continue` with zero logging. Operators
saw `failed: 10663` in the result dict but no WARN line
in the log pipeline, so alerting never fired.

# DO NOT — restates the diff
feat(dataflow): add logging to bulk create

Added logger.warning call in _handle_batch_error method.
Updated BulkResult to emit WARN in __post_init__.
```

## Issue Closure Discipline

Closing a GitHub issue as "completed" MUST include a commit SHA, PR number, or merged-PR link in the close comment. Closing with no code reference is BLOCKED.

```bash
# DO — close with delivered-code reference
gh issue close 351 --comment "Fixed in #412 (commit a1b2c3d)"
gh issue close 370 --comment "Resolved by PR #415 — kailash 2.8.1"

# DO NOT — close with no code proof
gh issue close 351 --comment "Resolved"
gh issue close 374 --comment "Covered by recent refactor"
```

**BLOCKED rationalizations:**

- "Already covered in another PR"
- "Will reference later"
- "Obsoleted by refactor"
- "Resolved without code change"

**Why:** Issues closed with zero delivered code references break traceability; the next session cannot verify whether the fix actually shipped.

## Pre-Commit Hook Workarounds

When pre-commit auto-stash causes commits to fail despite hooks passing in direct invocation, the workaround `git -c core.hooksPath=/dev/null commit ...` MUST be documented in the commit body, AND a follow-up todo MUST be filed against the pre-commit configuration. Silent re-tries with `--no-verify` are BLOCKED.

```bash
# DO — document the bypass in the commit body and file a todo
git -c core.hooksPath=/dev/null commit -m "$(cat <<'EOF'
fix(security): add null-byte rejection to credential decode

Pre-commit auto-stash fails to restore staged changes when
hooks modify the working tree. Bypassed via core.hooksPath=/dev/null.
TODO: fix pre-commit stash/restore interaction (#NNN).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"

# DO NOT — silent --no-verify with no documentation
git commit --no-verify -m "fix(security): add null-byte rejection"
# no record of why hooks were skipped; next session repeats discovery
```

**BLOCKED rationalizations:**

- "Hooks passed when I ran them manually"
- "--no-verify is faster and the CI will catch it"
- "The auto-stash bug is a known issue"

**Why:** Recurring across sessions; without documentation each session re-discovers the workaround at high cost. With documentation the next agent finds it via `git log --grep`.
