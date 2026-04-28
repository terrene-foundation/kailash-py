# CI/CD Modernization Brief

**Date**: 2026-03-18
**Scope**: GitHub Actions CI/CD for open-source Kailash Python SDK
**Depends on**: v1.0.0 released to PyPI

---

## Objectives

1. **GA CI/CD best practices for open-source projects** — Optimize workflows for the Terrene Foundation's public repositories
2. **Workload identity federation** — OIDC-based trusted publishing to PyPI (no stored tokens)
3. **Fix CI dependency resolution** — `kailash[all]` extra fails because sub-packages not yet on PyPI at v1.0.0
4. **Sub-package publishing** — Publish kailash-dataflow, kailash-kaizen, kailash-nexus to PyPI

---

## Current State

### Repositories

- `terrene-foundation/kailash-py` — Main SDK (public, Apache 2.0)
- `terrene-foundation/kailash-coc-claude-py` — COC template (public, Apache 2.0)

### Current CI Issues

1. All workflows were `self-hosted` → switched to `ubuntu-latest` in this session
2. `unified-ci.yml` fails: `kailash-dataflow>=1.0.0` not available on PyPI (only 0.12.4)
3. No OIDC trusted publishing configured (uses stored PyPI tokens)
4. No dependency caching (slow installs)
5. No matrix testing (only Python 3.12)
6. No GitHub Release automation on tag push

### Packages to Publish

| Package          | Current PyPI  | Target | Location                     |
| ---------------- | ------------- | ------ | ---------------------------- |
| kailash          | 1.0.0         | Done   | `src/kailash/`               |
| kailash-dataflow | 0.12.4        | 1.0.0  | `packages/kailash-dataflow/` |
| kailash-kaizen   | 1.2.5 (stale) | 1.3.0  | `packages/kailash-kaizen/`   |
| kailash-nexus    | 1.4.2 (stale) | 1.5.0  | `packages/kailash-nexus/`    |
| kailash-eatp     | 0.8.0         | 0.9.0  | `packages/eatp/`             |
| trustplane       | N/A           | 0.1.0  | `packages/trust-plane/`      |

---

## Requirements

### 1. GA Best Practices for Open Source

- Python version matrix (3.10, 3.11, 3.12, 3.13)
- Dependency caching (`actions/cache` or `uv cache`)
- Parallel test tiers (Tier 1 fast, Tier 2 with services)
- PR checks: lint + type check + Tier 1 tests
- Main branch: full test suite + docs build
- Tag push: auto-publish to PyPI + GitHub Release
- CODEOWNERS file
- Branch protection rules documented
- Security scanning (dependabot, CodeQL)

### 2. Workload Identity Federation (OIDC Trusted Publishing)

- Configure PyPI trusted publisher for all packages
- Remove stored PyPI tokens from GitHub Secrets
- Use `pypa/gh-action-pypi-publish` with OIDC
- Each package gets its own trusted publisher config

### 3. Fix Sub-Package Publishing

- Publish kailash-dataflow 1.0.0 to PyPI
- Update version pins in kailash core's `[all]` extra
- Verify `pip install kailash[all]` works

### 4. GitHub Release Automation

- On tag push (v\*): auto-build + publish to PyPI + create GitHub Release with changelog

---

## Success Criteria

1. `gh workflow run unified-ci.yml` succeeds on ubuntu-latest
2. All packages installable via `pip install kailash[all]`
3. PyPI trusted publishing configured (no stored tokens)
4. Tag push auto-publishes to PyPI + creates GitHub Release
5. Python 3.10-3.13 matrix green
6. PR workflow completes in under 5 minutes
