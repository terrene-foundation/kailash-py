# 0002 RISK — Multi-Package Coupled Release Blast Radius

**Date:** 2026-04-28
**Session:** dataflow-prod-incident /analyze
**Type:** RISK

## Finding

This workstream's fix touches BOTH `kailash` core (Shard B — `src/kailash/nodes/data/async_sql.py`) AND `kailash-dataflow` (Shards A + C). Both packages need a coupled release because:

1. Shard B's `_PROCESS_POOL_REGISTRY` change in `kailash` IS the underlying mechanism Shard A's regression test depends on (the test asserts `pool_count() <= cap`).
2. `kailash-dataflow` declares `kailash>=2.X.X` in its `pyproject.toml`; bumping kailash without bumping kailash-dataflow's floor leaves a half-released SDK where the pool fix isn't reachable from the DataFlow tests.

## The blast radius

Per `rules/deployment.md` § "Optional Dependencies Pin to PyPI-Resolvable Versions":

- `kailash-dataflow` 2.4.0 must declare `kailash>=2.12.0` after kailash 2.12.0 is on PyPI.
- The release-prep PR for `kailash-dataflow` MUST land AFTER `kailash` 2.12.0 publishes — otherwise `pip install kailash-dataflow==2.4.0` resolves against `kailash` 2.11.3 (pre-fix) and the fix is not present in the user's install.
- Multi-tag push order: `v2.12.0` (kailash) FIRST, sleep, then `dataflow-v2.4.0`. Per `rules/deployment.md` § "Multi-Package Release Tags Pushed Individually" — sequential pushes only, never batched.

## Why this is HIGH risk

Two failure modes exist:

1. **Tag order error:** if `dataflow-v2.4.0` is pushed before `v2.12.0` clears PyPI, the release CI for kailash-dataflow may fail to install kailash 2.12.0 (PyPI cache lag is 30–90 s for `info.version`, longer for simple-index per `feedback_drive_to_completion`).
2. **Floor pin mismatch:** if Shard A's PR (kailash-dataflow) lands BEFORE the kailash floor is bumped to 2.12.0, fresh installs from PyPI resolve to kailash 2.11.3 + the new dataflow that calls `pool_count()` — which doesn't exist in 2.11.3 — `AttributeError: type object 'AsyncSQLDatabaseNode' has no attribute 'pool_count'`.

## Mitigation

1. **Sequence the merge** — Shard B's PR (kailash core) merges + releases FIRST as 2.12.0. Verified clean on PyPI (clean-venv install per `rules/deployment.md`). THEN Shards A + C merge with their kailash floor bump in pyproject.toml in the same PR.
2. **Floor-pin discipline** — Per `rules/deployment.md` § "Optional Dependencies Pin to PyPI-Resolvable Versions", the `kailash-dataflow` 2.4.0 release-prep PR MUST bump `dependencies = ["kailash>=2.12.0", ...]` and verify the floor is on PyPI before tagging.
3. **CI cross-package install** — Per `rules/deployment.md` § "Sibling-Package CI Installs Root SDK Editable", every sub-package CI workflow that imports from `kailash.nodes.data.async_sql` MUST `uv pip install -e "."` the root kailash editable BEFORE installing kailash-dataflow's `[dev]` extras.
4. **Bridge regression test** — Add a Tier-2 cross-package test `tests/integration/test_kailash_dataflow_pool_bridge.py` that imports BOTH `kailash.nodes.data.async_sql.AsyncSQLDatabaseNode.pool_count` AND `kailash_dataflow` and exercises the integration. Per `rules/deployment.md` § "Bi-Directional At Bridge Boundaries" — install BOTH packages editable in BOTH CI workflows.

## What "done" looks like

- `kailash` 2.12.0 on PyPI; clean-venv install verified.
- Wait 60 s for PyPI cache lag.
- `kailash-dataflow` 2.4.0 on PyPI; clean-venv install verified; bridge test passes.
- Both packages report consistent `__version__` per `rules/zero-tolerance.md` Rule 5.
- Issues #696/#697/#698/#685/#686 closed with delivered-code references.

## Related

- `rules/deployment.md` § "Multi-Package Release Tags Pushed Individually"
- `rules/deployment.md` § "Bi-Directional At Bridge Boundaries"
- `rules/zero-tolerance.md` Rule 5 (version consistency on release)
- `feedback_build_repo_release` (BUILD repo sessions MUST proceed through /release after merge)
