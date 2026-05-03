---
type: DECISION
date: 2026-03-31
created_at: 2026-03-31T02:10:00Z
author: agent
session_id: session-7
session_turn: 45
project: kailash
topic: Codification of session 7 CI fixes and issue resolutions
phase: codify
tags: [codify, dataflow, pact, sync-express, del-finalizers, sqlite]
---

# Codification: Session 7 CI Fixes + 4 Issue Resolutions

## What Was Codified

### 1. SyncExpress API (skill update)

Updated `skills/02-dataflow/dataflow-express.md` with `db.express_sync` documentation. This is a Python-specific feature (SyncExpress wraps async Express with a persistent daemon thread event loop). Suggested tier: `coc-py`.

### 2. PACT Bridge Approval Requirement (skill update)

Updated `skills/29-pact/pact-governance-engine.md` to show `approve_bridge()` before `create_bridge()`. This reflects the LCA enforcement added in PR #168 — a language-agnostic governance pattern. Suggested tier: `coc`.

### 3. `__del__` Patterns (rule update)

Updated `rules/patterns.md` with two additions:

- Child `__del__` must call `super().__del__(_warnings=_warnings)` (CodeQL enforces this)
- `import warnings` inside `__del__` is prohibited (use `_warnings=warnings` default parameter)

Suggested tier: `coc-py`.

## What Was NOT Codified (and why)

- **SQLite read-back in Express.create()**: Implementation detail, not a pattern. The code handles it transparently — users don't need to know about the read-back.
- **`id_type.__name__` AttributeError fix**: Bug fix in generated node code, not a recurring pattern.
- **SQLite cursor leak fix in async_sql.py**: One-off bug, already fixed.

## For Discussion

- The PACT LCA enforcement change in #168 broke 5 tests that shipped through 2 releases (v2.3.0 and v2.3.1). Should the PACT skill include a "breaking changes" section for governance behavior changes?
- If the SyncExpress approach (daemon thread + persistent event loop) proves fragile in edge cases, would `nest_asyncio` be a safer alternative?
- The 23 `__del__` fixes suggest this pattern was never enforced systematically before — should a hook detect new `import warnings` inside `__del__` methods?
