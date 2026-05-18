# Brief: Workstream-B parallel wave (#995/#996/#997)

Parallel implementation of three #979 Workstream-B follow-up issues
filed 2026-05-14, approved for parallel launch 2026-05-16 after
re-validation gate (per `rules/value-prioritization.md` MUST-3).

## Value-anchor (verbatim from `workspaces/issue-979-dataflow-unit-triage/briefs/00-brief.md:48-50`)

> "Any remaining tier-1 test that imports `motor`, `psycopg`, or
> other DB drivers is either gated behind `importorskip` OR moved
> to `tests/integration/`."

## Shard carving (disjoint file scopes)

| Shard | Issue      | Branch                                     | Worktree                         | File surface                                |
| ----- | ---------- | ------------------------------------------ | -------------------------------- | ------------------------------------------- |
| A     | #995 (B-1) | `feat/issue-995-b1-inspector-importorskip` | `.claude/worktrees/issue-995-b1` | 4 top-level `tests/unit/test_inspector*.py` |
| B     | #996 (B-2) | `feat/issue-996-b2-saas-rewrite-move`      | `.claude/worktrees/issue-996-b2` | 6 `tests/unit/templates/test_saas_*.py`     |
| C     | #997 (B-3) | `feat/issue-997-b3-runtime-importer-gates` | `.claude/worktrees/issue-997-b3` | 9 heterogeneous runtime importers           |

### Shard A files (#995)

- `tests/unit/test_inspector.py`
- `tests/unit/test_inspector_realtime_debugging.py`
- `tests/unit/test_inspector_parameter_tracing.py`
- `tests/unit/test_inspector_workflow_analysis.py`

### Shard B files (#996) — amended per plan invariant

**5 files MOVE → `tests/integration/templates/` (rewrite to NO MOCKING per Tier-2 contract):**

- `tests/unit/templates/test_saas_api_keys.py`
- `tests/unit/templates/test_saas_starter_auth.py`
- `tests/unit/templates/test_saas_starter_jwt.py`
- `tests/unit/templates/test_saas_subscriptions.py`
- `tests/unit/templates/test_saas_webhooks.py`

**1 file STAYS in tier-1 (per `02-amendments-v2-post-redteam-r1r2.md` line 264-266; ATTACK-6 R2 verification — 100% mocked, pure-Python, meets contract):**

- `tests/unit/templates/test_saas_tenancy.py` — remove `pytestmark.skip` only; keep in tier-1; keep existing `unittest.mock` (allowed at tier-1 per testing-tiers.md Rule 4)

### Shard C files (#997) — amended per plan invariant

9 files with confirmed bare-top-imports of `kailash.runtime.*` or `kailash.workflow.builder` (after excluding Shard A's inspector files + Shard B's saas-starter-auth):

- `tests/unit/core/test_async_sql_sqlite.py`
- `tests/unit/core/test_workflow_binding.py` ⚠️ **STAYS in tier-1 per HIGH-E plan trap** (refactor to mock-only, do NOT move)
- `tests/unit/core/test_model_registry_runtime_injection.py`
- `tests/unit/nodes/test_count_node.py`
- `tests/unit/test_strict_mode_connection_validation.py`
- `tests/unit/test_strict_mode_workflow_validation.py`
- `tests/unit/test_protection_system_critical_gaps.py`
- `tests/unit/package/test_package_installation_unit.py` (just landed yesterday via S1.8 of #992 commit `8bcd0350` — gate the bare import)
- `tests/unit/test_write_protection_comprehensive.py`

## Spec authority

- Primary: `specs/testing-tiers.md` § Tier-1 Contract Rule 1 (no external infra at import or run time) + Rule 4 (mocking discipline — mocking allowed at Tier-1, BLOCKED at Tier-2/3)
- Plan: `workspaces/issue-979-dataflow-unit-triage/02-plans/02-amendments-v2-post-redteam-r1r2.md` (OPTION-C′ approved 2026-05-13)
- Convergence receipt: `workspaces/issue-979-dataflow-unit-triage/journal/0004-DECISION-redteam-convergence.md`

## Pre-flight base SHA

`origin/main = dcfd626b` (Merge #1021 — #992 closure).

## Plan invariants amended at launch (per `rules/specs-authority.md` MUST-5c)

- Issue #996 body says "move all 6"; amended → "move 5, keep tenancy in tier-1" (ATTACK-6).
- Issue #997 list includes `test_workflow_binding.py`; amended → "keep in tier-1 with mock-only refactor" (HIGH-E).

## Out of scope

- B-4 (#998 db.express async smoke) — deferred.
- B-5 (#999 regression scaffolding) — deferred.
- #1022 (TDD-mode docs-pipeline E2E) — deferred (LOW).
- Upstream aiosqlite issue — deferred (user said "not now").
