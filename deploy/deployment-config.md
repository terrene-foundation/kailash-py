# SDK Release Configuration

## Build System

- **Tool**: setuptools (pyproject.toml)
- **Python**: >=3.11

## Publishing

- **Registry**: PyPI (production), TestPyPI (validation)
- **Method**: Trusted Publisher (OIDC) via GitHub Actions
- **Trigger**: Git tags (`v*` for core, `kaizen-v*` for Kaizen, etc.)
- **Workflow**: `.github/workflows/publish-pypi.yml`
- **Strategy**: Tag-triggered automated publishing. No manual twine uploads.

## Packages

| Package          | Tag Pattern        | Current Version |
| ---------------- | ------------------ | --------------- |
| kailash (core)   | `v*`               | 2.9.2           |
| kailash-dataflow | `dataflow-v*`      | 2.2.0           |
| kailash-kaizen   | `kaizen-v*`        | 2.12.3          |
| kailash-nexus    | `nexus-v*`         | 2.2.0           |
| kailash-pact     | `pact-v*`          | 0.10.0          |
| kailash-ml       | `ml-v*`            | 1.1.1           |
| kailash-align    | `align-v*`         | 0.6.0           |
| kailash-mcp      | `mcp-v*`           | 0.2.9           |
| kaizen-agents    | `kaizen-agents-v*` | 0.9.4           |

Last updated: 2026-04-25 (1.1.2 wave — public API expose for read-time classification + tenant-id log hygiene + SHA-256 → BLAKE2b sweep). 3 packages released: kailash 2.9.2 (docstrings), kailash-dataflow 2.2.0 (#601 public API), kailash-kaizen 2.12.3 (#614 + #617 security sweep). Closed without code: #594 / #597 / #610 / #609 (cross-SDK parity-research closures). Deferred to next shard: #607 (SecurityDefinerBuilder port) + #605 (PACT N4/N5 conformance runner). Smoke-test verified: all 3 versions install + import from clean Python 3.12 venv with new public surfaces (`apply_read_classification`, `format_record_id_for_event`, BLAKE2b ApiKey fingerprint).

## Release Runbook

1. Version bump in `pyproject.toml` + `__init__.py`
2. Update CHANGELOG.md
3. Run full test suite
4. Security review
5. Create release branch + PR
6. Merge PR (admin bypass)
7. Tag on main → triggers publish-pypi.yml
8. Verify PyPI install
9. Update COC template dependency pins
10. Document in `deploy/deployments/`

## Documentation

- **Build**: `cd docs && python build_docs.py`
- **Deploy**: Auto via `docs-deploy.yml` on push to main
- **Hosting**: GitHub Pages

## Versioning

- Lockstep: core SDK version bumps require framework dependency pin updates
- SemVer: major (breaking), minor (features), patch (fixes)

## Tag Convention

**IMPORTANT**: Use lightweight tags (NOT annotated) for release triggers.

```bash
# CORRECT — lightweight tag triggers GitHub Actions reliably
git tag v2.5.0
git push origin v2.5.0

# WRONG — annotated tag may NOT trigger publish-pypi.yml
git tag v2.5.0 -m "Release message"
```

GitHub Actions `push.tags` webhook processing handles lightweight tags
more reliably than annotated tags pushed after creation.

## Multi-Tag Release — Push Individually

When releasing multiple packages at once (coordinated patch release), tags
MUST be pushed individually, NOT in a single batch. Batch pushes of 3+ tags
fail to trigger the publish workflow reliably.

```bash
# CORRECT — push tags one at a time
git push origin v2.8.6
git push origin dataflow-v2.0.8
git push origin kaizen-v2.7.4
git push origin nexus-v2.0.2
git push origin mcp-v0.2.4

# WRONG — batch push silently skips workflow triggers
git push origin v2.8.6 dataflow-v2.0.8 kaizen-v2.7.4 nexus-v2.0.2 mcp-v0.2.4
# ↑ observed on 2026-04-14: ZERO of 5 tags triggered publish-pypi.yml.
# Required manual workflow_dispatch for each package.
```

**Why:** GitHub Actions' `push.tags` webhook delivery has undocumented
rate-limiting/batching behavior when multiple tags arrive in a single push
event. The first observed failure mode (2026-04-14): 5 tags pushed at once
triggered zero workflow runs. Individual pushes with a brief pause (≥1s)
between them trigger reliably.

**Recovery if a batch push was already done**: use `workflow_dispatch` to
manually trigger publishing for each affected package. The tags themselves
are still valid — only the auto-trigger was missed.
