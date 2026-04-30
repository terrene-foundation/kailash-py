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
| kailash (core)   | `v*`               | 2.13.0          |
| kailash-dataflow | `dataflow-v*`      | 2.6.0           |
| kailash-kaizen   | `kaizen-v*`        | 2.13.1          |
| kailash-nexus    | `nexus-v*`         | 2.5.0           |
| kailash-pact     | `pact-v*`          | 0.11.0          |
| kailash-ml       | `ml-v*`            | 1.6.0           |
| kailash-align    | `align-v*`         | 0.7.0           |
| kailash-mcp      | `mcp-v*`           | 0.2.10          |
| kaizen-agents    | `kaizen-agents-v*` | 0.9.4           |

Last updated: 2026-04-30 — the v2.13.0 cluster cut: `kailash 2.12.0 → 2.13.0` (adds `kailash.utils.lifespan` shared FastAPI helpers + patches 3 sibling FastAPI lifespan sites for #712), `kailash-nexus 2.4.1 → 2.5.0` (adds `Nexus.add_startup_handler` / `add_shutdown_handler` public API for #712), `kailash-dataflow 2.5.0 → 2.6.0` (lazy `runtime` `@property` + setter + `runtime=` kwarg for #713 + 6 subsystem captures → lazy lookups + DDL connection-reuse via `SyncDDLExecutor.execute_ddl_batch_per_statement` for #714). Three tags pushed individually (per multi-tag discipline), three `publish-pypi.yml` runs triggered. Specs landed in PR #728 (`specs/dataflow-core.md` §1.4/1.5/1.6.5 + `specs/nexus-core.md` §10.2/10.3 + `specs/nexus-services.md` §29). Cross-SDK: kailash-rs uses axum + Tokio (no equivalent custom-lifespan footgun for #712, no module-import event-loop binding for #713); analogous DDL connection thrash for #714 may exist — companion issue to be filed.

Prior 2026-04-28 (kailash-dataflow 2.3.3 patch — closes merged-but-unreleased gap from PRs #684 / #689 / #690: `not_null_handler.py` pyright cleanup + 8 migration unit-test mock-method-drift repairs. No production behavior change beyond type-checking cleanup; 13 pre-existing pytest warnings in the migrations suite remain on separate workstreams). kailash-ml 1.5.1 (PR #679) routes the `engines/model_registry.py` `ModelNotFoundError` through the canonical `kailash.ml.errors.ModelNotFoundError` (subclass of `ModelRegistryError → MLError`), removing the divergent local `class ModelNotFoundError(Exception)` that surfaced when the W7-001 LineageGraph walker raised canonical while `ModelRegistry.get_model` raised local. 6 raise sites converted to canonical kwargs; 3 regression tests pin class-identity + AST invariant. PR #679 also adds `scripts/development/find-venv-python.sh` — wrapper that resolves `.venv/bin/python` via `git rev-parse --git-common-dir` so pre-commit hooks run from inside `.claude/worktrees/<X>/` without the `core.hooksPath=/dev/null` bypass; 3 regression tests pin the worktree-safe invariants. Clean-venv install verified live: `kailash-ml==1.5.1` + `ModelNotFoundError canonical identity: OK` + `__all__ count: 50 (AST-derived)`. No sibling drift.

Prior 2026-04-27 — W7 portfolio remediation: kailash-ml 1.5.0 (PR #677 closes #657) ships the cross-engine `LineageGraph` engine module; kailash-dataflow 2.3.2 (PR #678) wires `format_error_for_event` through `emit_train_end` at the emitter.

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
