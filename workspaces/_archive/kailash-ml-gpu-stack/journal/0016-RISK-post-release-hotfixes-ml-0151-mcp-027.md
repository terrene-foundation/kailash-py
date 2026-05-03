---
type: RISK
date: 2026-04-20
created_at: 2026-04-20T07:56:32.455Z
author: agent
session_id: 9f1976ea-96de-4ea2-ab97-ab52a17debbb
session_turn: n/a
project: kailash-ml-gpu-stack
topic: post-release audit hotfixes — kailash-ml 0.15.1 + kailash-mcp 0.2.7
phase: codify
tags:
  [
    auto-generated,
    hotfix,
    security,
    tenant-isolation,
    spdx,
    spec-staleness,
    kailash-ml,
    kailash-mcp,
  ]
related_journal: []
---

# RISK — post-release audit hotfixes — kailash-ml 0.15.1 + kailash-mcp 0.2.7

## Commit

`608f1664ca65` — fix(ml+mcp): post-release audit hotfixes — kailash-ml 0.15.1 + kailash-mcp 0.2.7

## Body

Post-release /redteam on kailash-ml 0.15.0 + kailash-mcp 0.2.6 (merge `bac2b3be`) surfaced three HIGH findings across three parallel audits. All fixed in this hotfix + regression-tested per `rules/agents.md` "After release" gate.

**ML — tenant-isolation bypass (security-reviewer HIGH-1):**
`MLEngine._check_tenant_match` silently allowed an unscoped engine (`tenant_id=None`) to load a tenant-scoped model — violating `specs/ml-engines.md` §5.1 MUST 3 and `rules/tenant-isolation.md` Rule 2. Fix raises `TenantRequiredError` with actionable message naming `MLEngine(tenant_id=...)` as the fix. 5-case regression test locks all four combinations of (engine, model) tenant states.

**MCP — missing SPDX headers (gold-standards HIGH-1):**
`packages/kailash-mcp/src/kailash_mcp/advanced/features.py` and `server.py` lacked `"SPDX-License-Identifier: Apache-2.0"` + copyright header per `rules/terrene-naming.md`. 4-line fix.

**Spec — §12.1 phase-status stale (reviewer HIGH-1 / gold-standards MED-1):**
`specs/ml-engines.md` §12.1 still dated "kailash-ml 0.14.0" and listed all 7 Phase 3/4/5 rows as pending despite 0.15.0 shipping them. Fixed header + reduced table to the 2 intentional deferrals. §12.2 gate items now marked [x] for the 5 satisfied by 0.15.0.

The cross-tenant bypass was the most severe finding: an unscoped engine could silently serve a tenant-scoped model, violating the isolation guarantee. The spec-staleness finding would have misled the next session into re-implementing work already shipped.

## For Discussion

1. **Counterfactual**: The tenant-isolation bypass (`MLEngine._check_tenant_match` silently allowing `tenant_id=None` engines to load tenant-scoped models) was caught by the post-release security-reviewer. If the post-release gate had been skipped (per `rules/agents.md` it is RECOMMENDED not MUST), how many downstream sessions would have built features on top of `MLEngine` assuming the isolation invariant held, before the bypass was discovered in production?

2. **Data-referenced**: The regression test covers "all four combinations of (engine, model) tenant states" — that is: (None, None), (None, scoped), (scoped, None), (scoped, scoped). The failing case was (None, scoped). Is (scoped, None) — a tenant-scoped engine loading an unscoped model — also a security concern, or is it an acceptable "promotion" path where an admin engine reads a shared model?

3. **Pattern**: This is the second hotfix cycle in the 2026-04-20 session (the first was the codify cycle in 0012). Both hotfixes were caught by the post-release reviewer gate. Is the pattern "ship → post-release reviewer finds HIGH → hotfix in the same session" a sign that the pre-release reviewer gate is under-resourced, or does it represent the expected sensitivity curve of a two-gate system where the second gate specializes in fresh-eyes review of merged code?
