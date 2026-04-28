# 0005 TRADE-OFF — Semver Major vs Minor For Behavioural Fix

**Date:** 2026-04-28
**Session:** dataflow-prod-incident /todos
**Type:** TRADE-OFF

## The trade-off

Both releases (kailash and kailash-dataflow) include behavioural breaking changes:

- **kailash 2.12.0** — `_get_adapter` fallback path changes from "create unbounded dedicated pool" to "register + cap + fail-fast at cap". Apps relying on the unbounded behaviour see new `PoolExhaustedError`.
- **kailash-dataflow 2.4.0** — `auto_migrate=True` (default) changes from "retry on every access" to "fail-fast on first error". Apps relying on the retry-storm bug as a feature (i.e., expecting eventual recovery as the failed DDL becomes valid) see `DDLFailedError`.

The semver question: **major bump (3.0.0 / 3.0.0)** signaling breaking, OR **minor bump (2.12.0 / 2.4.0)** treating the prior behaviour as a bug?

## Decision: minor bump (2.12.0 / 2.4.0)

Both behaviours WERE bugs. The "feature" was the failure mode this workstream exists to fix. Per `feedback_no_shims` (the user's preference): no deprecation timeline; fix is the same release. Per `feedback_optimal_outcome`: choose the optimal architecture, not the politically safer one.

A major bump would imply the prior behaviour was an intended feature being removed — this is the wrong narrative. The prior behaviour was a bug that produced production incidents (JourneyMate). Treating it as a "feature deprecation" would set the precedent that future bug fixes also require major bumps, which would amplify the existing changelog noise without proportionate benefit.

## What downstream callers experience

Apps with the JourneyMate failure mode see a NEW error class on the failure mode they were already failing on. Net change: same failure → typed error with actionable message + bounded resource cost. Strictly better.

Apps without the failure mode see no change. Their CREATE TABLEs succeed; their pools stay shared.

Apps that intentionally relied on lazy-retry (extremely rare; the retry-storm IS the known bug) get `auto_migrate="warn"` as the explicit opt-in. The CHANGELOG names this escape hatch.

## What this affects in the todos

- DPI-E1 / DPI-E2 use minor bumps (2.11.3 → 2.12.0; 2.3.3 → 2.4.0)
- CHANGELOG entries name the behavioural change but frame it as bug-fix-with-bounded-error, not "removed feature"
- The `auto_migrate="warn"` escape hatch IS documented; legacy apps can opt out

## Alternative considered

**Major bump (3.0.0 / 3.0.0)** — clearer signaling at the cost of artificial breaking-change perception. Rejected per the rationale above.

## Cross-SDK relevance

When the equivalent fixes ship to kailash-rs, the same trade-off applies. The Rust SDK's semver discipline matches Python's; the same minor-bump frame should hold.

## Related

- `feedback_no_shims` (no deprecation timelines)
- `feedback_optimal_outcome` (choose optimal architecture)
- `rules/zero-tolerance.md` Rule 6 (half-implementation is BLOCKED)
- `journal/0004 DECISION` (shard sequencing assumes minor-bump ordering)
