---
title: Parameterized fabric products missed cache — params parsed but dropped on read
type: DISCOVERY
date: 2026-04-08
phase: 03-implement
related:
  - gh#358
  - workspaces/issue-354/02-plans/01-fix-plan.md
  - esperie-enterprise/kailash-rs#273
---

# DISCOVERY — Parameterized product cache params dropped on read path

## What we found

gh#358 reported that fabric products with `mode="parameterized"` never
read from cache via HTTP, even after a successful refresh. Frontends
that depended on parameterized products (ecosystem matrix, gaps,
members, proposals, progress) rendered `null` post-deploy because
every container restart wiped the in-memory cache and the HTTP read
path could never rehydrate from it.

The root cause was a **two-line bug** sitting untouched through a full
2.0 refactor: `fabric/serving.py` parsed query params at the top of the
GET handler, validated them, used them for the refresh path, then
dropped them when calling `self._pipeline.get_cached(name)` for the
read path. The cache lookup used the bare product name and always
missed because parameterized cache keys include the canonical JSON of
the params (e.g. `members:{"ecosystem_id": "eco-a"}`).

`fabric/health.py` had the same bug class: `get_metadata(name)` with
no params aggregation, so every parameterized product reported
`freshness="cold"` regardless of actual cache state. Operators lost
observability exactly where they needed it most.

## Impact

- HTTP GET `/fabric/members?ecosystem_id=abc` → 200 with `data=null`
- `/fabric/_health` → `members.freshness="cold"` forever
- Silent data bug — no error in logs, no exception, no HTTP 5xx. The
  endpoint returned 200 and the frontend trusted the `null`.
- Two-week detection latency (the bug shipped in 1.8.0, was discovered
  during the DataFlow 2.0 Phase 5 wiring work).

## Fix

1. `serving.py` single-GET handler now passes `params=params` to
   `get_cached`, so parameterized lookups hit the correct per-param
   slot. The batch handler returns an explicit routing error for
   parameterized products because the batch request contract has no
   slot to carry per-product params; returning a silent `null` would
   reproduce the original lie.

2. `health.py` now detects `ProductMode.PARAMETERIZED` and aggregates
   metadata across every cached param combination via a new
   `scan_product_metadata` helper on PipelineExecutor. The helper is
   backed by a new `scan_prefix` primitive on `FabricCacheBackend`
   that both the in-memory and Redis backends implement, so the
   health path never transfers payload bytes — Redis scan + HMGET
   metadata only.

3. A separate gh#273 issue was filed on kailash-rs — the Rust SDK has
   the **same** bug at `crates/kailash-dataflow/src/executor.rs:185`
   (bare-name cache key) plus a broader parity gap (no `params` in
   the `execute_product` public API at all, and no HTTP serving
   layer for fabric products in Nexus).

## Why it shipped

The cache-key construction helper `_cache_key(product_name, params,
tenant_id)` is correct — the bug was that the caller forgot to pass
`params`. The helper defaults `params=None`, so the call type-checks
fine. Code review missed it because the file has two call sites for
the same operation 50 lines apart (the refresh path passes params, the
read path doesn't), and the two paths share the same variable name
`params` in the closure scope. A reviewer skimming either one in
isolation sees `params` used correctly — both paths look fine.

## Guardrail

The **framework-first** rule requires that the cache-key construction
API make the params argument REQUIRED when the product is
parameterized. The current shape lets callers opt out silently.
`rules/dataflow-pool.md` Rule 3 ("No Deceptive Configuration") covers
the analogous case for config flags; a similar rule for cache-key
signatures would have caught this at lint time.

Concretely: when `products.py` registers a product with
`mode="parameterized"`, the runtime could require a
`params_schema_fingerprint` on the product that `get_cached` validates
on every call. An unwrapped call to `get_cached("members")` for a
parameterized product would then raise at runtime, not cache-miss
silently. Adds 1-2 lines of boilerplate at the serving layer in
exchange for catching the entire bug class.

## For Discussion

- Is it worth making `params` a required kwarg for parameterized
  products at the `get_cached`/`set_cached` boundary? The trade-off is
  that non-parameterized products either need a different signature
  or pass a conspicuous `params=None`.
- Should `scan_product_metadata` cache results? Health probes fire
  every ~10s per operator dashboard, and for a parameterized product
  with 200 param combinations, SCAN+HMGET runs 201 Redis round-trips
  every probe. A 5-second LRU on `FabricHealthManager` would cap the
  probe cost without sacrificing freshness (health isn't authoritative).
- The bug was found during Phase 5.3 tenant plumbing work, which also
  touches serving.py/health.py. Without Phase 5, this bug would have
  lived in 1.8.0 → 1.9.0 → 2.0.0 until an impact-verse operator
  reported it directly. How much of the rest of fabric is in the same
  class — code that works in unit tests but fails the moment real
  params land?

## Related

- Commit: `ed6e0fc9 fix(dataflow): resolve gh#358 — plumb params
  through serving/health cache reads`
- Cross-SDK: `esperie-enterprise/kailash-rs#273`
- Fix plan: `workspaces/issue-354/02-plans/01-fix-plan.md` (Amendment
  A: tenant plumbing, same failure class)
