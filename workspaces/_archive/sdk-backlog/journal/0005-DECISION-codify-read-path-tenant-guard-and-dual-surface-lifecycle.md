# DECISION — Codify: data-product read-path tenant-scope guard + dual-surface state reconcile

**Date:** 2026-07-10
**Phase:** 05-codify
**Type:** DECISION

## What was codified

Two new MUST clauses authored on branch `codify/jack-hong-2026-07-10`, distilled from
this session's converged security work:

1. **`rules/tenant-isolation.md` Rule 8 — Data-Product / Materialized-View Read-Path
   Tenant-Scope Guard.** Generalizes the #1654 fabric tenant QueryInterceptor beyond
   fabric: a tenant guard on a data-product / materialized-view / cached-read surface
   MUST prove the tenant predicate was applied to the EXECUTED query (not merely that the
   product is DECLARED `multi_tenant`); PK reads need a type-normalized post-fetch assert;
   reject alternate filtering channels (`$`-operator keys + non-allowlisted kwargs);
   cross-check the declaration flag against the model's actual tenant column at
   registration; blank/None fails closed; refusals don't echo the foreign tenant id;
   read-path scope only (write + source paths are distinct — #1658/#1659).

2. **`rules/eatp.md` — Dual-Surface State Reconciles BOTH Surfaces Atomically Under One
   Lock; Reconcile On A Stable Id.** Distilled from #1510 BH2. A state machine spanning
   two mutable surfaces (in-memory review queue + persisted store) MUST reconcile BOTH
   atomically under one lock on every transition; reconcile on the ORIGINAL (non-re-minted)
   id; a single-surface entry MUST NOT be evictable by a cross-surface event. Generalizes
   the sibling audit-before-state-advance clause from one surface to two.

## Why these two (value-rank)

Both are cascade-valuable security disciplines that generalize beyond the originating
bug: any SDK with tenant-scoped read surfaces / dual-surface state machines inherits them.
The self-referential-codify gate was checked — neither `tenant-isolation` nor `eatp` is on
the Rule-2 allowlist (they govern CODE behavior, not codify-governance), so the mandatory
multi-agent gate did not apply; both clauses were still cc-architect-authored + Origin-
verified against git log + carry canonical 8-field Trust Posture Wiring.

The mask_url credential-mask consolidation (this session, #1655) was NOT given a separate
clause — `security.md` § Credential Decode Helpers + `observability.md` § 6 already mandate
consolidation + canonical mask forms; the session's addition (presigned/SAS key variants +
normalized matching) is an in-family extension, noted here rather than a new rule.

## Receipts

- tenant-isolation Rule 8 Origin: #1654 → kailash-dataflow 2.14.6, PR #1660.
- eatp dual-surface Origin: #1510 BH2 legs 2-3 → kailash 2.46.0, PR #1657.
- Both verified present via `grep -c '**Violation scope:**'` (wiring anchor).
- last_codified anchor advanced from 2026-07-10T06:46:44Z.
