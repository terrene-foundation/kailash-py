# Deployment — 2026-06-01 — #855 three-package release

Three patch releases closing issue #855 (kaizen warm-tier memory + kaizen-agents
memory-shortcut crash) plus a core-SDK fix surfaced during #855 validation.

## Packages

| Package        | From (PyPI) | To     | Tag                    | publish-pypi.yml run |
| -------------- | ----------- | ------ | ---------------------- | -------------------- |
| kailash (core) | 2.28.1      | 2.28.2 | `v2.28.2`              | 26731952285 success  |
| kailash-kaizen | 2.24.3      | 2.24.4 | `kaizen-v2.24.4`       | 26731958370 success  |
| kaizen-agents  | 0.9.7       | 0.9.8  | `kaizen-agents-v0.9.8` | 26731965177 success  |

All three tags pushed individually from `main` (`fbdff857a`) per multi-tag
discipline. TestPyPI skipped per the patch-release exception (CI green + both
gate reviews clean on the originating PRs).

## What shipped

- **kailash 2.28.2** (PR #1221) — `Node.__init_with_capture` no longer crashes
  with `TypeError: not iterable` when a Node subclass replaces `self.config`
  with a typed config object (e.g. kaizen `BaseAgentConfig`). The dict-only
  param-capture now skips for non-dict configs. Recovered ~93 kaizen-agents
  Pipeline orchestration test errors. Reviewer + security-reviewer APPROVED.
- **kailash-kaizen 2.24.4** (PR #1219) — `DataFlowMemoryBackend` column
  `tags` → `tag_list` (the documented `tags` field collided with the reserved
  `NodeMetadata.tags` `set[str]`, so warm-tier persistence raised on first
  store). store()→get() round-trips content AND tags.
- **kaizen-agents 0.9.8** (PR #1220) — `Agent(memory="persistent"|"learning")`
  no longer raises `TypeError: unexpected keyword argument 'storage_path'`
  (the factories built `HierarchicalMemory` with kwargs it never accepted).
  Both now build a real warm-tier-backed provider via a safe 4-slash SQLite
  DSN helper (`removeprefix`-hardened, `?`/`#`/null-rejecting per
  security-review) + `tag_list` model, degrading to hot-tier-only with a
  logged warning when DataFlow is absent. Plus pyright type-drift fixes in
  `state_manager.py` + `journey/core.py` (19 errors / 14 warnings → 0/0).

## Clean-venv verification (the done gate)

`uv venv` (py3.12) + `uv pip install --refresh kailash==2.28.2
kailash-kaizen==2.24.4 kaizen-agents==0.9.8` resolved + installed from PyPI on
first attempt. Verified live: all three `__version__` strings match; the Node
non-dict-config guard, the `DataFlowMemoryBackend.tag_list` read-back, and the
repaired persistent-shortcut + `removeprefix` DSN hardening are all present in
the installed wheels.

## Sibling drift

Release-time enumeration: no other framework package had `main` ahead of PyPI.

## Follow-up — RESOLVED same session as kailash-kaizen 2.24.5

- **kaizen.memory eagerly imports `aiosqlite` (was an optional extra) — FIXED.**
  `kaizen/memory/__init__.py` → `enterprise` → `persistent_tiers.py:21` imports
  `aiosqlite` unconditionally, but #890 slim-core had scoped `aiosqlite` to the
  optional `db` extra, so `import kaizen.memory` (the path to
  `DataFlowMemoryBackend`) failed on a clean `pip install kailash-kaizen`. A
  subsystem cannot eagerly require a dependency AND declare it optional.
  Disposition after analysis + co-owner approval: **promote `aiosqlite` to a
  core dependency** — pure-Python over the stdlib `sqlite3` (zero
  compiled/transitive weight), eagerly imported by a first-class subsystem, and
  mis-bucketed in #890 (whose real targets were heavy/niche deps). `asyncpg`
  (Postgres, not eagerly imported) stays optional in `db`. Shipped as
  `kailash-kaizen 2.24.5` (PR #1224, tag `kaizen-v2.24.5`, publish run success).
  Verified live: `pip install kailash-kaizen==2.24.5` with **no extras** pulls
  `aiosqlite` via the core dep, `import kaizen.memory` + `DataFlowMemoryBackend`
  succeed, and `Requires-Dist` lists `aiosqlite>=0.19.0` unconditionally.
