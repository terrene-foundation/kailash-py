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

| Repository                                 | Branch | Protection          |
| ------------------------------------------ | ------ | ------------------- |
| `terrene-foundation/kailash-py`            | `main` | Full (admin bypass) |
| `terrene-foundation/kailash-coc-claude-py` | `main` | Full (admin bypass) |
| `terrene-foundation/kailash-coc-claude-rs` | `main` | Full (admin bypass) |
| `esperie/kailash-rs`                       | `main` | Full (admin bypass) |

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
