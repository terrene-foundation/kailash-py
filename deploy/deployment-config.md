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
| kailash (core)   | `v*`               | 2.13.4          |
| kailash-dataflow | `dataflow-v*`      | 2.7.6           |
| kailash-kaizen   | `kaizen-v*`        | 2.18.1          |
| kailash-nexus    | `nexus-v*`         | 2.6.1           |
| kailash-pact     | `pact-v*`          | 0.11.0          |
| kailash-ml       | `ml-v*`            | 1.7.1           |
| kailash-align    | `align-v*`         | 0.7.0           |
| kailash-mcp      | `mcp-v*`           | 0.2.11          |
| kaizen-agents    | `kaizen-agents-v*` | 0.9.5           |

Last updated: 2026-05-03 — six-package release closing the issue #781 cleanup workstream (T1-T5 merged via PRs #804/#805/#806/#807/#808): `kailash 2.13.3 → 2.13.4` (T4 core/runtime TODO-NNN comment-strip + T5 CI gate `.pre-commit-config.yaml::no-untracked-todo-nnn` + `tests/regression/test_no_untracked_todo_nnn.py` + `scripts/check_no_untracked_todo_nnn.sh`), `kailash-dataflow 2.7.5 → 2.7.6` (T1, 89 markers stripped), `kailash-kaizen 2.18.0 → 2.18.1` (T2, 80 markers stripped + #801 test fix), `kailash-nexus 2.6.0 → 2.6.1` (T4, 16 markers stripped), `kaizen-agents 0.9.4 → 0.9.5` (T3, 69 markers stripped), `kailash-mcp 0.2.10 → 0.2.11` (sibling sweep per `build-repo-release-discipline.md` Rule 1: W6-002 type fix + 10 ElicitationSystem Tier-2 tests + LOW-6 triage). All six PRs through admin-merge → 6 tags pushed sequentially → publish-pypi.yml (OIDC) workflow runs all `success`. Clean-venv install + import verification documented in `deploy/deployments/2026-05-03-v2.13.4-six-package-issue-781-release.md`. SDK dep pin sweep `kailash>=2.13.4` across all 8 framework packages (released 5 + align/pact/ml unreleased-this-cycle for consistency). Issue #781 closed.

Prior 2026-05-02 — paired release closing #761 + #762 + #763 + #764 + #779: `kailash 2.13.2 → 2.13.3` (catch-up release for #779's auth Rule 2 cleanup that landed without a same-PR version bump per `build-repo-release-discipline.md` Rule 5 — 7 NotImplementedError stubs eliminated across `src/kailash/{nodes,middleware}/auth/` per `zero-tolerance.md` Rule 2 § "Fake dispatch"), `kailash-kaizen 2.14.0 → 2.16.0` (two-minor jump combining PR #780's #761/#762 LlmDeployment.openai_compatible + anthropic_compatible escape-hatch presets + preset_name field, AND PR #783's #763 LlmDeployment.supports() capability matrix + #764 register_bedrock_region runtime override). Cross-SDK parity with kailash-rs PR #722/#724/#725/#726. Both via admin-merge → tag → publish-pypi.yml (OIDC) → workflow runs `25237480388` + `25237487960` succeeded. TestPyPI gate skipped on both with explicit human approval (kailash 2.13.3 is recap-only; kailash-kaizen 2.16.0 surfaces unit-tested with parametrized cross-SDK byte-match coverage and dual-reviewer APPROVED). Clean-venv install + import verification documented in `deploy/deployments/2026-05-02-v2.13.3-kaizen-v2.16.0.md`.

Prior 2026-05-01 — paired patch cut closing #767 + #768: `kailash 2.13.1 → 2.13.2` (durability_middleware short-circuits before draining `StreamingResponse` / `text/event-stream`, restoring SSE + cache-replay semantics for `EventSource` clients on `EnterpriseWorkflowServer`/`Nexus()` for #767), `kailash-dataflow 2.7.1 → 2.7.3` (skipping 2.7.2 — never tagged; `ListNodeCacheIntegration` invalidation patterns aligned with producer key shape for #750, plus `FieldTypeProcessor._resolve_type` now strips parameterized generics + handles PEP 604 `T | None` so `@db.model` accepts `list[str]` / `dict[str, Any]` on Python 3.11+ for #768). Both PRs through admin-merge → tag → publish-pypi.yml (OIDC) → clean-venv install verified live (`kailash==2.13.2` + `kailash-dataflow==2.7.3` import; `_resolve_type(list[str]) is list` + `durability_middleware` source contains `StreamingResponse`). Cross-SDK loop closure for #759/#767/#768 still pending explicit human approval per `upstream-issue-hygiene.md` Rule 1.

Prior 2026-04-30 — the v2.13.0 cluster cut: `kailash 2.12.0 → 2.13.0` (adds `kailash.utils.lifespan` shared FastAPI helpers + patches 3 sibling FastAPI lifespan sites for #712), `kailash-nexus 2.4.1 → 2.5.0` (adds `Nexus.add_startup_handler` / `add_shutdown_handler` public API for #712), `kailash-dataflow 2.5.0 → 2.6.0` (lazy `runtime` `@property` + setter + `runtime=` kwarg for #713 + 6 subsystem captures → lazy lookups + DDL connection-reuse via `SyncDDLExecutor.execute_ddl_batch_per_statement` for #714). Three tags pushed individually (per multi-tag discipline), three `publish-pypi.yml` runs triggered. Specs landed in PR #728 (`specs/dataflow-core.md` §1.4/1.5/1.6.5 + `specs/nexus-core.md` §10.2/10.3 + `specs/nexus-services.md` §29). Cross-SDK: kailash-rs uses axum + Tokio (no equivalent custom-lifespan footgun for #712, no module-import event-loop binding for #713); analogous DDL connection thrash for #714 may exist — companion issue to be filed.

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
