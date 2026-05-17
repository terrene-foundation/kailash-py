---
type: DISCOVERY
date: 2026-05-05
created_at: 2026-05-05T00:00:00Z
author: agent
session_id: issue-822-kaizen-typing-cascade
session_turn: /analyze
project: kailash-py / issue-822-kaizen-typing-cascade
topic: MCP orphan imports predate PR #75 split — never existed at any commit
phase: analyze
tags:
  [
    issue-822,
    orphan-detection,
    fake-integration,
    pr-75-not-cause,
    zero-tolerance-rule-2,
  ]
---

# DISCOVERY — MCP orphan imports predate PR #75 split, never existed at any commit

**Date:** 2026-05-05
**Phase:** /analyze (Cluster C deep-dive)
**File:** `01-analysis/03-cluster-c-imports-orphans.md` (deep-dive report)

## Finding

The brief framed the unresolved imports (`..mcp.registry::get_global_registry`,
`..mcp::AutoDiscovery`, `..mcp::MCPConnection`) as cascade collateral from the
typing fixes. Cluster-C deep-dive confirms the opposite: **the imports are not
collateral from anything** — they refer to symbols that have NEVER existed in the
kaizen source tree at any commit, pre- or post-PR #75 (`801de2bb`, 2026-03-25).

Verification:

```bash
git log --oneline --all -- 'packages/kailash-kaizen/src/kaizen/mcp/registry.py'
# (empty — file has never existed)

git show 801de2bb~1:packages/kailash-kaizen/src/kaizen/core/agents.py \
  | grep -nE 'MCPConnection|AutoDiscovery|get_global_registry'
# Same line numbers, same broken imports as today.
```

`kaizen/mcp/__init__.py::__all__` has been `["EnterpriseFeatures", "MCPServerConfig"]`
since `b553104c` (the original `apps/`→`packages/` move). The 5 unresolved-symbol
imports live inside `try/except ImportError` (or `try/except Exception:`) blocks —
they ALWAYS fail in production, the surrounding code returns `None`/`[]`/error-dict,
and 6 documented public-API methods on `Agent` and `Kaizen` have never produced a
real connection.

## Why this matters

This is `rules/zero-tolerance.md` Rule 2 fake-integration on documented public surface:

- `Agent.expose_as_mcp_server` — never registered a server
- `Agent.expose_as_mcp_tool` — never registered a tool
- `Agent.connect_to_mcp_servers` — never connected
- `Agent.call_mcp_tool` — never called
- `Agent._discover_servers` — always returned `[]`
- `Kaizen.discover_mcp_tools(external=True, ...)` — external branch always returned `local_tools` only
- `Kaizen.mcp_registry` — always returned `None`

20+ test references + 9 ADR/doc references treat these as working API. They are not.

## Why "predates PR #75" matters

The brief's framing implied PR #75 (the kaizen-agents split) caused the orphans —
which would have been Issue-#814-class collateral. Cluster C verifies they predate
PR #75. Per `rules/zero-tolerance.md` Rule 1c, a "pre-existing" claim REQUIRES a SHA
ground truth older than session start; that ground truth here goes back to
`b553104c` (~ early March 2026). But Rule 1 still requires the fix in this session
— "if you found it, you own it." Provenance grounding only authorizes the factual
claim, not the deferral.

The optimal disposition per `rules/zero-tolerance.md` Rule 2 + Rule 6a is **Option A:
delete the dead surface + CHANGELOG migration entry** (architecture plan § Shard 2).

`rules/dependencies.md` BLOCKED Anti-Patterns explicitly forecloses the alternative
"silence pyright with `# type: ignore[import-not-found]`" — that is "hiding a missing
module" by name.

## Cross-SDK note

`rules/cross-sdk-inspection.md` Rule 1 mandates inspection of the parallel SDK for
the same orphan pattern. Per `rules/repo-scope-discipline.md` this session stays
in-lane (kailash-py only); architecture plan flags an inspection-then-file follow-up
against `esperie/kailash-rs` as a HUMAN-GATED action per
`rules/upstream-issue-hygiene.md` MUST Rule 1.

## Action

- Architecture plan documents Shard 2 as orphan-deletion shard (~250 LOC) with
  test-sweep + CHANGELOG migration entry per `rules/orphan-detection.md` Rule 4 +
  Rule 6a.
- LOC invariant test required per `rules/refactor-invariants.md` Rule 1 (single
  commit landing the deletion).
- Cross-SDK follow-up flagged for human approval at `/todos` gate.

## For Discussion

1. **Counterfactual:** if the brief had correctly framed these as
   "pre-existing fake-integration orphans" rather than "PR #75 collateral,"
   would the disposition have been the same (delete) or different (closer audit
   of intent — were they ever meant to work)? Does the framing affect the
   action when Rule 2 + Rule 1c both mandate deletion regardless?
2. **Specific data:** 7 surfaces (5 methods + 1 branch + 1 property), 20+ test
   refs + 9 ADR/doc refs, all reachable, all returning None/[]/error-dicts.
   With ~6 weeks since the PR #75 split (the brief's framing) and ~3+ months
   since `b553104c` (actual lineage), how did 20+ test references pass without
   anyone noticing the methods never returned real data? What does that say
   about Tier-1 vs Tier-2 test coverage discipline?
3. **Risk:** the cross-SDK follow-up (todo 3.3) audits kailash-rs for the same
   pattern. Are there other modules in kailash-py with the same try-import-on-
   nonexistent-symbol pattern that this audit didn't catch? How would we
   enumerate them?

## References

- `01-analysis/03-cluster-c-imports-orphans.md` — full per-symbol resolution table
- `02-plans/01-architecture.md` § Shard 2
- Commit `b553104c` (original `apps/`→`packages/` move)
- PR #75 / commit `801de2bb` (structural split — verified red herring)
