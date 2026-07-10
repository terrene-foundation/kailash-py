---
type: DISCOVERY
date: 2026-07-10
author: agent
project: sdk-backlog
topic: Cross-tenant upsert-conflict write breach is a distinct failure mode from tenant-source parity
phase: codify
tags: [tenant-isolation, dataflow, security, upsert, cross-sdk]
relates_to: 0003-DECISION-tenant-upsert-guard-rule
---

# DISCOVERY — the un-guarded ON CONFLICT DO UPDATE tenant breach

The #1650 redteam surfaced a failure mode the existing tenant-isolation rules did NOT cover: on a `multi_tenant` model with a global single-column `id` PK, an upsert with `conflict_on=["id"]` emits `ON CONFLICT (id) DO UPDATE SET ...` with no tenant predicate. A cross-tenant `id` collision is a genuine `ON CONFLICT`, so the `DO UPDATE` resolves it by overwriting the OTHER tenant's row — and, because `tenant_id` was in the SET list, reassigning ownership — while returning success. The collision diagnostic (which only fires on `success=False`) never sees it.

Three properties made it invisible for a long time:

1. It only bites when two tenants collide on the same `id` — rare in casual testing, guaranteed at scale with app-supplied ids.
2. The op returns success; a tenant-scoped read of the victim's row (masked by the tenant filter) looks untouched — only a RAW cross-tenant read reveals the theft.
3. It sits BEHIND the tenant-source-parity rule (Rule 6, #1252): the write reads the RIGHT tenant, so a Rule-6 audit passes — yet the un-guarded conflict path still overwrites another tenant's row.

The completeness lesson: the primary `bulk_upsert` fix left a sibling registered node (`BulkCreatePoolNode`) with the same breach; only the closure-parity round's "audit ALL builders" sweep caught it. Five builders total needed the guard.

Codified as tenant-isolation.md Rule 7 (see journal/0003). Cross-SDK: filed rs#1712 (shared DataFlow architecture).

## For Discussion

1. **Counterfactual:** if the sanitizer/redaction rules (`dataflow-classification.md`) had a symmetric "every mutation-return-path" discipline for WRITE-conflict paths, would this have been caught at authoring time rather than by redteam? Is there a general "every conflict-resolution path is a tenant boundary" rule hiding here, beyond upserts?
2. **Data-specific:** the breach was invisible to `db.express.read` (tenant-scoped) and only visible to a raw cross-tenant `SELECT`. Should the Tier-2 test harness ship a standard `_raw_read_all` helper so every tenant-isolation test asserts against the unmasked table by default, not the tenant-scoped read that hides theft?
3. **Cross-SDK:** rs#1712 assumes the Rust DataFlow shares the builder shape. If the Rust upsert path uses a composite `(tenant_id, id)` unique instead of a global `id` PK, the breach doesn't exist there — should the cross-SDK issue lead with "verify the PK shape" before "apply the guard"?
