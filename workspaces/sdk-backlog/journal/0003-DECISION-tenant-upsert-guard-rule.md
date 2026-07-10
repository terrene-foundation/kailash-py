---
type: DECISION
date: 2026-07-10
author: agent
project: sdk-backlog
topic: Codify the upsert cross-tenant-write-guard pattern as tenant-isolation.md Rule 7
phase: codify
tags: [tenant-isolation, dataflow, security, upsert, codify]
relates_to: 0004-DISCOVERY-cross-tenant-upsert-guard-pattern
---

# DECISION — tenant-isolation.md Rule 7 (upsert ON CONFLICT DO UPDATE tenant-guard)

Receipt for the `/codify` the co-owner directed ("/codify the pattern") after the #1650 cross-tenant upsert write-breach fix + 2.14.5 security release.

## What changed

- Added **Rule 7** to `.claude/rules/tenant-isolation.md`: every `multi_tenant` upsert builder emitting `ON CONFLICT DO UPDATE` (PG/SQLite) / `ON DUPLICATE KEY UPDATE` (MySQL) MUST (a) exclude `tenant_id` from the SET clause and (b) tenant-guard the update (`WHERE {table}.tenant_id = EXCLUDED.tenant_id` / per-column `IF(tenant_id = VALUES(tenant_id),...)`); a guard-suppressed cross-tenant collision routes to the actionable tenant-scoped diagnostic; ALL builders audited, not just the primary.
- Canonical 8-field Trust Posture Wiring (post-MUST-8-SHA, canonical-compliant); `regression_within_grace` generic trigger (no dedicated key — avoids a self-ref edit to trust-posture.md).
- Extended the Audit Protocol grep with the Rule 7 upsert-guard sweep.

## Why authored (not left in memory)

Cascade-valuable per `knowledge-cascade-routing.md` MUST-1 — applies to every multi_tenant upsert in DataFlow AND cross-SDK to the Rust SDK (rs#1712 filed). Routed to a COC artifact (rule), not memory.

## Distinctness

Rule 7 is DISTINCT from Rule 6 (canonical-tenant-source, #1252): Rule 6 ensures the write reads the RIGHT tenant; Rule 7 blocks a correctly-scoped write from overwriting ANOTHER tenant's row via the un-guarded conflict path.

## Not on the self-referential-codify allowlist

tenant-isolation.md governs code behavior, not codify-class surfaces → standard cc-architect review (dispatched), not the mandatory multi-agent self-ref gate.

## Receipts

- Rule fix + release: PR #1650 (merge acb85f5fd) + #1652 (kailash-dataflow 2.14.5, tag dataflow-v2.14.5, publish run 29074366000 success).
- Cross-SDK: rs#1712/#1713/#1714 filed (grant journal/0002).
