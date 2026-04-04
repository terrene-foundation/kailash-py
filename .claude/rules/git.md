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

## Branch Naming

Format: `type/description` (e.g., `feat/add-auth`, `fix/api-timeout`)

## Branch Protection

All protected repos require PRs to main. Direct push is rejected by GitHub.

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

## Rules

- Atomic commits: one logical change per commit, tests + implementation together
- No direct push to main, no force push to main
- No secrets in commits (API keys, passwords, tokens, .env files)
- No large binaries (>10MB single file)
