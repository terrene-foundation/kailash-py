# Reviewer Round 1 — Issue #822 Architecture Plan

**Reviewer:** quality reviewer
**Date:** 2026-05-05
**Scope:** `02-plans/01-architecture.md` + `02-plans/02-spec-traceability.md`

## 1. Spec accuracy compliance — PASS

`02-spec-traceability.md:74-79` correctly defers spec edits to `/implement`
first-instance per `specs-authority.md` Rule 5 + `spec-accuracy.md` Rule 5
(code-first). The architecture plan freely uses Shard 1/Shard 2 framings
(plans/ is the right surface). No split-state framings appear in either
document's spec-touching content. Brief corrections section follows
`agents.md` MUST: Parallel Brief-Claim Verification.

## 2. Pyright reproducibility — PASS

Counts cited in `01-architecture.md:32-38` reproduce exactly:

- `framework.py`: **4 errors, 21 warnings** (matches `4e/21w`)
- `agents.py`: **3 errors, 12 warnings** (matches `3e/12w`)
- `__init__.py`: **0 errors, 3 warnings** (matches `0e/3w`)

Verified via `uv run pyright <path>` 2026-05-05. Zero discrepancy.

## 3. CHANGELOG alignment — APPROVE_WITH_REVISIONS

Current state: `__version__ = "2.18.2"` (`packages/kailash-kaizen/src/kaizen/__init__.py`);
CHANGELOG `[Unreleased]` carries 5+ substantive entries (research/web-search
extras, mock_preset, capability matrix rows, cohere_preset migration). Most
recent released = `[2.18.1]`.

**Issue:** Plan recommends `v2.19.0` (`01-architecture.md:25, 309, 342`) but
the existing `[Unreleased]` already accumulates entries that look minor-bump-shaped
(new test-only module, 7 new capability rows, default-endpoint migration) — those
were already going to ship as `2.19.0` independent of #822. Per Rule 6a (deprecation
cycle for public-API removal), Shard 2's BREAKING removal is correctly a minor
bump; merging the existing `[Unreleased]` + #822 BREAKING removal into a single
`2.19.0` release is sound, but the plan should state explicitly that #822 lands
INTO the existing `[Unreleased]` block, not as a fresh `[2.19.0]` entry created
from scratch (avoid clobbering prior entries — `artifact-flow.md` "Append, never
overwrite" pattern applies in spirit).

## 4. Test inventory accuracy — APPROVE_WITH_REVISIONS

Collection (via `cd packages/kailash-kaizen && uv run pytest --collect-only`):

- `test_agents_comprehensive.py`: 45 tests; 6 directly touch deleted methods
  (`test_expose_as_mcp_server`, `test_expose_as_mcp_tool`, `test_connect_to_mcp_servers`,
  `test_get_mcp_tool_registry`, `test_execute_mcp_tool`, `test_call_mcp_tool`).
  **39 surviving tests must NOT be deleted** — plan says "delete or port to
  kaizen-agents" without scoping. **REVISION:** narrow Shard 2 deletion list to
  the 6 named MCP test functions only.
- `test_mcp_integration_missing.py`: 16 tests, **all 16 reference deleted
  surface** (every Function in the collection enumerates `expose_mcp_tool`,
  `mcp_tool_registry`, `mcp_server_client`, etc.). Whole-file deletion is
  correct.
- `test_agent_execution_patterns_e2e.py`: 17 tests; 2 touch deleted surface
  (`test_agent_with_mcp_tools_e2e`, `test_mcp_server_exposure_e2e`). **15
  surviving tests must NOT be deleted** — same scoping fix as comprehensive.

## 5. Foundation independence + naming compliance — PASS

Grep for `commercial|partnership|proprietary|databricks|salesforce|oracle|
microsoft|aws|gcp|azure|enterprise edition|community edition` returns zero
hits across both plan files. No commercial coupling, no Terrene-naming drift.

## 6. Coverage gates — APPROVE_WITH_REVISIONS

Plan lists 3 regressions:

- `test_issue_822_signature_programming_gate.py` (Shard 1) — covers REAL bug
- `test_issue_822_behavior_traits_render.py` (Shard 1) — covers dead branch
- LOC invariant test (Shard 2) — covers refactor pressure

**Gap:** 7 GUARD FIX sites + 6 TYPE FIX sites have NO behavioral regression
named. Per `testing.md` MUST "Behavioral Regression Tests Over Source-Grep",
each typed `RuntimeError` guard MUST have a regression asserting the raise
fires (e.g., `framework.py:882, 945, 1077, 1097, 1188, 1258`). **REVISION:**
add `test_issue_822_optional_call_guards.py` with 7 parametrized cases — one
per guard site — asserting `RuntimeError` raises with the typed message when
backing object is None.

## 7. Communication style — PASS

TL;DR (`01-architecture.md:7-26`) answers "what does this fix and what does
it cost" in two paragraphs + a 3-row table. Lede is up-front: "not a 4-line
fix — three structurally distinct workstreams". Cost is named (~390 LOC, two
shards, single 2.19.0 release). Risk is named (LOW/MEDIUM). Lede not buried.

## Additional finding (Rule 1 zero-tolerance signal)

Pre-existing `ImportError: cannot import name 'Node' from 'kailash.nodes.base'`
when running `pytest --collect-only` from the repo root against the kaizen
test files (the .pyenv-installed `kailash` is stale relative to the in-repo
package). This is OUTSIDE #822 scope but `/implement` shard agents will trip
on it when verifying acceptance gates. Recommend documenting the
`cd packages/kailash-kaizen && uv run pytest` invocation in Shard 1/2
acceptance gates so the agent doesn't burn budget rediscovering this.

---

## Final verdict: **APPROVE_WITH_REVISIONS**

Three revisions before `/todos` gate:

1. CHANGELOG framing: state explicitly that #822 lands in existing
   `[Unreleased]` block (do NOT clobber the 5+ accumulated entries).
2. Test-deletion scoping: narrow `test_agents_comprehensive.py` to 6 named
   functions and `test_agent_execution_patterns_e2e.py` to 2 named functions
   — do not blanket-delete. List the surviving test counts (39 + 15) in the
   plan as "preserved".
3. Add `test_issue_822_optional_call_guards.py` — 7 parametrized regressions
   for the GUARD FIX sites per `testing.md` MUST behavioral-regression rule.

Pyright counts, foundation-independence, spec-accuracy compliance, and TL;DR
clarity all PASS as drafted. The plan is structurally sound and ready for
human approval at `/todos` once the three scoping revisions land.
