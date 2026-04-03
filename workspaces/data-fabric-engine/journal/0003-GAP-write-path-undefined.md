---
type: GAP
date: 2026-04-02
created_at: 2026-04-02T14:40:00+08:00
author: agent
session_turn: 3
project: data-fabric-engine
topic: Write path (mutations) entirely unaddressed in design
phase: analyze
tags: [mutations, writes, api-design, critical-gap]
---

# Gap: Write Path Is Undefined

## What Is Missing

The entire design focuses on reads. No design document addresses how a frontend sends data THROUGH the fabric back to sources. This means:

- VP2 ("single data contract for frontend") is half-true — reads go through fabric, writes bypass it
- FE still needs direct API access for mutations
- FE team maintains two data access patterns (fabric for reads, custom for writes)

## Why This Matters

If fabric only handles reads, the FE team still writes custom API client code for every mutation (create, update, delete). This undercuts the "single data contract" promise and reduces adoption incentive.

## Proposed Resolution

**v1: Write pass-through with automatic invalidation**

```python
# Write through fabric → source → invalidate dependent products
await fabric.write("users_db", "create", {"name": "Alice", "email": "alice@example.com"})
# 1. Executes write on users_db source (via DataFlow Express for DB sources)
# 2. Triggers refresh of all products that depend on users_db
# 3. Cache updated atomically on successful refresh
```

This is minimal engineering (~300-500 LOC) but closes the "single contract" gap. Full write semantics (transactions, partial updates, conflict resolution) can come in later phases.

## For Discussion

1. For REST API sources, the fabric would need to know the API's write semantics (POST vs PUT vs PATCH, URL patterns, request formats). Is this too much source-specific configuration for a "zero-config" system?
2. If a write succeeds at the source but the subsequent product refresh fails, the cache is stale until the next pipeline cycle. Is this acceptable? Should writes trigger synchronous refresh?
3. Should write access be gated by the staleness policy? (e.g., if the source is down, should writes be blocked or queued?)
