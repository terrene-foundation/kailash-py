# Expanded Scope — 3 Open Source Repos

**Date**: 2026-03-18

## Repositories

| Repo                                       | Language   | Org                | Status                                       |
| ------------------------------------------ | ---------- | ------------------ | -------------------------------------------- |
| `terrene-foundation/kailash-py`            | Python     | Terrene Foundation | Primary SDK, just released v1.0.0            |
| `terrene-foundation/kailash-coc-claude-py` | COC config | Terrene Foundation | COC template for Claude Code                 |
| `terrene-foundation/kailash-coc-claude-rs` | COC config | Terrene Foundation | COC template for Claude Code (Rust bindings) |

All three are public, Apache 2.0, and should follow identical best practices.

## What Each Repo Needs

### Common (all 3 repos)

- `CODEOWNERS` file
- `dependabot.yml` for automated dependency updates
- Branch protection rules (require PR, require checks)
- `SECURITY.md` vulnerability reporting policy
- `CONTRIBUTING.md` contribution guide

### kailash-py (primary)

- Fix unified-ci.yml to pass on ubuntu-latest
- Python version matrix (3.10-3.13)
- Dependency caching with uv
- OIDC trusted publishing to PyPI (all 6 packages)
- Tag-based auto-release with GitHub Release creation
- CodeQL security scanning
- Sub-package publishing (DataFlow 1.0.0 etc.)

### kailash-coc-claude-py

- Basic CI (lint + validate COC structure)
- Branch protection
- Community files (CODEOWNERS, SECURITY, CONTRIBUTING)

### kailash-coc-claude-rs

- Basic CI (lint + validate COC structure)
- Branch protection
- Community files
