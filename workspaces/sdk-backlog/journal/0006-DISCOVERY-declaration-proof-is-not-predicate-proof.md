# DISCOVERY — "Declared multi-tenant" is not "query was tenant-scoped"; dual-surface reconcile

**Date:** 2026-07-10
**Phase:** 05-codify
**Type:** DISCOVERY

## The pattern the next session should inherit

### 1. Declaration-proof ≠ predicate-proof (tenant read paths)

The #1654 fabric interceptor's core failure mode: the layer partitioned the **cache** by
tenant and the product was **declared** `multi_tenant=True`, yet the product's actual
queries carried **no tenant predicate** (and `tenant_id` was never even passed into the
pipeline context) — so it returned every tenant's rows while looking isolated. A tenant
guard that trusts the declaration or the cache partition is a **silent fallback**. The
guard must inspect the **executed** filter/params.

Adversarial redteam refuted the first "never leaks" claim on **five** axes that a single-
pass review missed: (a) single-PK `read()` has no pre-execution filter → needs a POST-FETCH
assert; (b) empty/blank tenant `""` passed the `is None` check → shared pseudo-tenant;
(c) enforcement gated ONLY on the declaration flag → a model with a tenant column declared
`multi_tenant=False` silently disables all enforcement; (d) a top-level `$or` / an alternate
`**kwarg` filter channel re-admits other tenants while `filter["tenant_id"]` reads correct;
(e) a dev-mode serial-prewarm path ran multi_tenant products unguarded. **Lesson:** a
"prove the filter fired" guard has many bypass surfaces — enumerate every row-returning
path, every filter channel, and the declaration-vs-reality gap.

### 2. Dual-surface state machines re-resolve terminal states

The #1510 BH2 CRITICAL: a lifecycle state living on TWO mutable surfaces (an in-memory
review queue + a persisted store). `expire_holds` advanced the STORE to BLOCKED but left
the queue entry → a late review re-resolved the already-BLOCKED hold to AUTO_APPROVED — a
monotonic **downgrade**. The round-2 HIGH: the fix's reconcile keyed on the corrupt-sentinel's
**re-minted** id, missing the original. **Lesson:** reconcile BOTH surfaces atomically under
ONE lock, key on the STABLE original id, and fence single-surface entries from cross-surface
eviction. This is the two-surface generalization of audit-before-state-advance.

## Process note (for the next codegen session)

Both failures were found by **adversarial redteam that tried to REFUTE**, not confirm —
each round found a progressively narrower fail-open a per-function review could not see
(cross-surface lifecycle, forged-row injection, declaration-vs-model gap). For any
fail-closed security guard, budget ≥2 adversarial rounds and treat each round's finding as
evidence the surface is trickier than the diff shows. Convergence = a round that genuinely
refutes nothing NEW, not a clean per-function review.
