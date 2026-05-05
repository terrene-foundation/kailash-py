# Architecture Plan — Red-Team Round 1 Revisions

**Date:** 2026-05-05
**Trigger:** analyst red-team (`01-redteam-round-1.md`) + reviewer (`02-reviewer-round-1.md`)
**Disposition:** APPROVE_WITH_REVISIONS — both reviewers concur. Patches applied below.

## HIGH findings + verification

### H1 (Dim 3 analyst) — Migration target citations verified

Plan cites `kailash-mcp` and `kaizen.mcp.catalog_server.MemoryRegistry` as
migration targets. Verified existence:

- `packages/kailash-mcp/pyproject.toml` exists (real PyPI sibling package).
- `kaizen.mcp.catalog_server.MemoryRegistry` exists at
  `packages/kailash-kaizen/src/kaizen/mcp/catalog_server/registry.py:43`.

Citations are NOT phantom per `rules/spec-accuracy.md` Rule 1.

### H2 (Dim 3 analyst) — `kaizen.Agent` fallback asymmetry

`kaizen/__init__.py:15-20`:

```python
try:
    from kaizen_agents import Agent  # canonical (when kaizen-agents installed)
except ImportError:
    from kaizen.core.agents import (
        Agent,  # type: ignore[assignment]  # CoreAgent fallback
    )
```

The 5 dead MCP methods live on `kaizen.core.agents.Agent` (CoreAgent), NOT on
`kaizen_agents.Agent`. When `kaizen-agents` IS installed (the canonical path
per ADR-020), `kaizen.Agent` is `kaizen_agents.Agent` — the deleted methods
are not on the user's `kaizen.Agent` surface AT ALL. The deletion only affects
users who explicitly import `from kaizen.core.agents import Agent` (or hit
the `ImportError` fallback path).

**Blast radius is significantly smaller than the plan implied.** Architecture
plan amended below to reflect this.

### H3 (Dim 6 analyst) — `AgentTeam` is itself deprecated

`packages/kaizen-agents/src/kaizen_agents/patterns/core/teams.py:48-55`:

```python
warnings.warn(
    "AgentTeam uses simulated coordination and is deprecated. "
    "Use kaizen.orchestration.runtime.OrchestrationRuntime with "
    "production patterns (DebatePattern, ConsensusPattern, "
    "SupervisorWorkerPattern) for real multi-agent coordination.",
    DeprecationWarning,
    stacklevel=2,
)
```

Adding new typed class-body kwargs (`conflict_resolution`, `performance_optimization`)
to a deprecated class is wrong. Better disposition: add `# type: ignore[attr-defined]`
at `framework.py:824, 825` with a comment pointing to the deprecation, and DO NOT
edit `teams.py`. The cross-package release coordination collapses to zero.

### H4 (Dim 7 #1 analyst) — `_generate_role_based_traits` keyword matching

`packages/kailash-kaizen/src/kaizen/core/framework.py:505-528` — keyword matching
on `role_lower` to derive default behavior traits. Real `rules/agent-reasoning.md`
Rule 1 BLOCKED pattern (deterministic classification of agent input).

**However:** the plan's Shard 1 fix (`agent.behavior_traits = specialized_config.get("behavior_traits", [])`)
does NOT preserve this keyword matching — it only assigns user-supplied traits to
the agent attribute. The keyword-matching anti-pattern is in `_generate_role_based_traits`,
which provides defaults when no traits are passed — orthogonal to the assignment fix.

**Disposition:** out-of-scope for #822. **File a follow-up issue** for an LLM-first
rewrite of `_generate_role_based_traits` (use `Signature` to derive traits from role
description). Not blocking #822.

## MEDIUM findings + revisions

### M1 (Dim 2 analyst) — Shard 2 LOC corrected: ~440, not ~250

Verified deletion ranges:

| Method                                 | Range                  | LOC          |
| -------------------------------------- | ---------------------- | ------------ |
| `Agent.expose_as_mcp_server`           | agents.py 2370–2467    | 99           |
| `Agent.expose_as_mcp_tool`             | agents.py 2540–2614    | 75           |
| `Agent.connect_to_mcp_servers`         | agents.py 2780–2900    | 121          |
| `Agent.call_mcp_tool`                  | agents.py 2900–2920    | 20           |
| `Agent._discover_servers`              | agents.py 2937–2965    | 29           |
| `Kaizen.discover_mcp_tools` ext branch | framework.py 1512–1531 | 20           |
| `Kaizen.mcp_registry`                  | framework.py 1349–1360 | 11           |
| **TOTAL**                              |                        | **~375 LOC** |

Plus ~65 LOC test deletions. Plan's "~250 LOC" was an undercount; correct figure
is ~440 LOC including test sweep. **Still fits Rule 1** (deletion-heavy boilerplate;
single conceptual change "delete fake-MCP-integration") but the prose understates.

### M2 (Dim 4 analyst) — Rule 6a interpretation needs explicit human gate

Plan argues "methods never worked → no deprecation cycle needed." Rule 6a's
BLOCKED rationalization list does NOT explicitly carve out "never functioned."
Both reviewers agree this is plan-interpretation, not rule-text.

**Disposition:** Open question #1 in the plan ALREADY surfaces this for human
gate at `/todos`. Restate explicitly that BOTH options (delete with CHANGELOG
migration vs replace bodies with typed `NotImplementedError`) are valid; user
chooses.

### M3 (Dim 5 analyst) — typo'd dict-key path

`kaizen.configure(signature_programming_enabld=True)` (typo) silently flips
the gate to False — same Rule 3 silent-fallback class as the original bug.
Plan's fix using `getattr(...)` over the dataclass field eliminates THIS path
for the dataclass case, but the dict-config path still permits typos.

**Disposition:** add a Tier-2 regression in Shard 1 verifying `kaizen.configure(typo'd_key=True)`
does NOT enable the gate (canonical key gates correctly; typo'd key has no
effect — and ideally raises if the key is unknown, but adding strict-key
validation is a behavior change out-of-#822-scope).

### M4 (reviewer Dim 3) — CHANGELOG lands into existing `[Unreleased]`

`packages/kailash-kaizen/CHANGELOG.md` shows `[Unreleased]` already accumulating
5+ minor-bump-shaped entries; current `__version__ = "2.18.2"`. The #822 work
appends to `[Unreleased]`, NOT a fresh `[2.19.0]` block. The existing entries
already justify a minor bump.

### M5 (reviewer Dim 4) — Test sweep precision

- `test_agents_comprehensive.py`: 45 tests, only 6 touch deleted surface. **Preserve 39.**
- `test_mcp_integration_missing.py`: 16/16 reference deleted surface. **Whole-file delete.**
- `test_agent_execution_patterns_e2e.py`: 17 tests, only 2 touch deleted surface. **Preserve 15.**

Architecture plan's "delete the test files" is too coarse for tests #1 and #3.

### M6 (reviewer Dim 6) — 7 GUARD FIX sites need behavioral regressions

Per `rules/testing.md` MUST: Behavioral Regression. Add
`tests/regression/test_issue_822_optional_call_guards.py` with 7 parametrized
cases — each invokes the GUARD FIX site under None-state and asserts typed
RuntimeError (not bare `AttributeError`).

### M7 (reviewer extra) — `cd packages/kailash-kaizen` for /implement

A stale repo-root `.pyenv` install of `kailash` causes `ImportError: cannot
import name 'Node' from 'kailash.nodes.base'` on `pytest --collect-only` from
the repo root. `/implement` agents MUST `cd packages/kailash-kaizen && uv run pytest`.
Document in Shard 1 + Shard 2 acceptance gates.

### M8 (build-repo-release-discipline.md) — Release scope enumeration

Per the rule loaded mid-session, release scope MUST be enumerated at session
start. For #822, the kailash-kaizen release is the only one #822 directly
triggers, but per Rule 1 the closing /release session sweeps every sibling
package whose main version is ahead of PyPI. Architecture plan adds a release-
scope checklist to the closing /release section.

## Patches to architecture plan

Listed in the order they apply to `02-plans/01-architecture.md`:

1. **TL;DR table** — Shard 2 LOC: `~250` → `~440 (incl. test deletions)`.
2. **Brief Corrections** — no changes; analyst verified accurate.
3. **Shard 1 § 6** — DECLARE on `AgentTeam`: replace with "suppress pyright at
   attach-site (`framework.py:824, 825`) via `# type: ignore[attr-defined]` plus
   inline comment pointing to deprecation; do NOT edit `teams.py`."
4. **Shard 2 § Scope** — restate to clarify CoreAgent-only blast radius:
   "Deletion affects users importing `from kaizen.core.agents import Agent`
   (CoreAgent). Most users get `kaizen_agents.Agent` via the
   `kaizen/__init__.py:15-20` canonical path which doesn't have these methods
   at all."
5. **Shard 2 § Test sweep** — replace whole-file deletions with per-test
   list: 6 tests in `test_agents_comprehensive.py`, 16 in `test_mcp_integration_missing.py`,
   2 in `test_agent_execution_patterns_e2e.py`. Preserve siblings.
6. **Shard 2 § LOC estimate** — `~250 LOC` → `~440 LOC including test sweep`.
7. **NEW Shard 1 regression** — `test_issue_822_signature_programming_typo_path.py`:
   verify dict-config typo'd key does not enable gate.
8. **NEW Shard 1 regression** — `test_issue_822_optional_call_guards.py`:
   parametrized over 7 GUARD FIX sites; each asserts typed `RuntimeError`.
9. **Shard 2 acceptance gate** — add: "All gates run via
   `cd packages/kailash-kaizen && uv run pytest …`."
10. **NEW § Release scope (closing /release)** — enumerate all 8 BUILD packages
    per `rules/build-repo-release-discipline.md` Rule 3.
11. **NEW Open question #4** — `_generate_role_based_traits` keyword-matching
    follow-up (file separate issue; not blocking #822).
12. **Open question #2** — restate to make BOTH delete + NotImplementedError
    options visible per M2.

## Disposition

**APPROVE_WITH_REVISIONS** — patches above land in the architecture plan in this
session. After patches, the plan is ready for the structural human gate at `/todos`.

No structural decomposition changes. Two-shard plan stands.
